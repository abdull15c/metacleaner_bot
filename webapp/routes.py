import logging
import re
import uuid
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Optional

from pydantic import BaseModel
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.config import settings
from core.constants import SUPPORTED_VIDEO_EXTENSIONS
from core.database import get_db, get_db_session
from core.models import JobStatus, SourceType
from core.services.job_service import JobService
from core.services.settings_service import SettingsService
from core.services.user_service import UserService
from webapp.result_token import parse_result_download_token
from webapp.tg_init_data import telegram_user_id, validate_webapp_init_data
from core.models import SiteDownloadJob, JobStatus, DownloadFormat
from core.platform_detect import detect_platform, is_supported_url

logger = logging.getLogger(__name__)

_templates_dir = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

router = APIRouter(tags=["webapp"])

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._\-]+")


def _normalize_job_uuid(job_uuid: str) -> str:
    try:
        return str(uuid.UUID(job_uuid))
    except ValueError:
        raise HTTPException(status_code=404, detail="not_found")


def _result_download_filename(job) -> str:
    name = (job.original_filename or "video_clean.mp4").strip() or "video_clean.mp4"
    name = Path(name).name
    name = _SAFE_FILENAME.sub("_", name)[:200]
    if not name.lower().endswith((".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v")):
        suf = Path(job.temp_processed_path or "").suffix.lower() or ".mp4"
        name = (name.rsplit(".", 1)[0] if "." in name else name) + suf
    return name


def _require_telegram_user(init_data: str) -> tuple[int, dict]:
    user_obj = validate_webapp_init_data(init_data.strip(), settings.bot_token)
    if not user_obj:
        raise HTTPException(status_code=401, detail="invalid_init_data")
    try:
        tid = int(user_obj["id"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="invalid_init_data")
    return tid, user_obj


@router.get("/app", response_class=HTMLResponse)
async def mini_app_page(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "webapp_static": "/webapp-static",
            "telegram_bot_username": (settings.telegram_bot_username or "").lstrip("@"),
        },
    )


@router.post("/api/webapp/upload")
async def webapp_upload(
    init_data: str = Form(...),
    file: UploadFile = File(...),
):
    tg_id, tg_user = _require_telegram_user(init_data)
    fname = (file.filename or "video.mp4").strip() or "video.mp4"
    ext = ("." + fname.rsplit(".", 1)[-1].lower()) if "." in fname else ""
    if ext not in SUPPORTED_VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="unsupported_format")

    max_bytes = settings.max_file_size_bytes
    async with get_db_session() as session:
        ss = SettingsService(session)
        if not await ss.get("processing_enabled", True):
            raise HTTPException(status_code=503, detail="processing_disabled")
        if await ss.get("maintenance_mode", False):
            raise HTTPException(status_code=503, detail="maintenance")
        max_mb = int(await ss.get("max_file_size_mb", settings.max_file_size_mb))
        max_daily = int(await ss.get("max_daily_jobs_per_user", settings.max_daily_jobs_per_user))
        max_bytes = max_mb * 1024 * 1024

        us = UserService(session)
        user, _ = await us.get_or_create(
            telegram_id=tg_id,
            username=tg_user.get("username"),
            first_name=tg_user.get("first_name"),
        )
        if user.is_banned:
            raise HTTPException(status_code=403, detail="banned")

        js = JobService(session)
        active = await js.get_active_job_for_user(user.id)
        if active:
            raise HTTPException(status_code=409, detail="active_job_exists")
        if not await us.increment_daily_count(user, max_daily):
            raise HTTPException(status_code=429, detail="daily_limit")

        job = await js.create_job(user.id, SourceType.upload, original_filename=fname)
        job_uuid = job.uuid
        user_id = user.id

    settings.temp_upload_dir.mkdir(parents=True, exist_ok=True)
    disk_name = f"{uuid.uuid4()}{ext or '.mp4'}"
    dest = settings.temp_upload_dir / disk_name
    total = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    dest.unlink(missing_ok=True)
                    async with get_db_session() as session:
                        js = JobService(session)
                        us = UserService(session)
                        j2 = await js.get_by_uuid(job_uuid)
                        if j2:
                            await js.update_status(j2, JobStatus.failed, "File too large")
                        u2 = await us.get_by_id(user_id)
                        if u2:
                            await us.rollback_daily_job_increment(u2)
                    raise HTTPException(status_code=413, detail="file_too_large")
                out.write(chunk)
        if total == 0:
            dest.unlink(missing_ok=True)
            async with get_db_session() as session:
                js = JobService(session)
                us = UserService(session)
                j2 = await js.get_by_uuid(job_uuid)
                if j2:
                    await js.update_status(j2, JobStatus.failed, "Empty file")
                u2 = await us.get_by_id(user_id)
                if u2:
                    await us.rollback_daily_job_increment(u2)
            raise HTTPException(status_code=400, detail="empty_file")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("webapp upload write failed")
        dest.unlink(missing_ok=True)
        async with get_db_session() as session:
            js = JobService(session)
            us = UserService(session)
            j2 = await js.get_by_uuid(job_uuid)
            if j2:
                await js.update_status(j2, JobStatus.failed, str(e)[:200])
            u2 = await us.get_by_id(user_id)
            if u2:
                await us.rollback_daily_job_increment(u2)
        raise HTTPException(status_code=500, detail="save_failed") from e

    async with get_db_session() as session:
        js = JobService(session)
        j2 = await js.get_by_uuid(job_uuid)
        if not j2:
            dest.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail="job_lost")
        await js.set_file_paths(j2, str(dest), total)
        await session.commit()

        try:
            from workers.video_processor import process_video_task
            task = process_video_task.delay(job_uuid)
            async with get_db_session() as session:
                js = JobService(session)
                j3 = await js.get_by_uuid(job_uuid)
                if j3:
                    await js.set_celery_task_id(j3, task.id)
        except Exception as e:
            logger.exception("webapp celery dispatch failed")
            dest.unlink(missing_ok=True)
            async with get_db_session() as session:
                js = JobService(session)
                us = UserService(session)
                j2 = await js.get_by_uuid(job_uuid)
                if j2:
                    await js.update_status(j2, JobStatus.failed, f"Queue: {e}"[:200])
                u2 = await us.get_by_id(user_id)
                if u2:
                    await us.rollback_daily_job_increment(u2)
            raise HTTPException(status_code=503, detail="queue_unavailable") from e

    return JSONResponse({"ok": True, "job_uuid": job_uuid})


@router.get("/api/webapp/job/{job_uuid}")
async def webapp_job_status(
    job_uuid: str,
    session: AsyncSession = Depends(get_db),
    x_telegram_init_data: Annotated[Optional[str], Header(alias="X-Telegram-Init-Data")] = None,
):
    job_uuid = _normalize_job_uuid(job_uuid)
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="missing_init_data")
    tg_id = telegram_user_id(x_telegram_init_data.strip(), settings.bot_token)
    if tg_id is None:
        raise HTTPException(status_code=401, detail="invalid_init_data")

    js = JobService(session)
    job = await js.get_by_uuid(job_uuid)
    if not job:
        raise HTTPException(status_code=404, detail="not_found")
    if not job.user or job.user.telegram_id != tg_id:
        raise HTTPException(status_code=404, detail="not_found")

    proc_path = job.temp_processed_path
    proc_ok = bool(proc_path and Path(proc_path).is_file())
    proc_size = Path(proc_path).stat().st_size if proc_ok else None
    return {
        "uuid": job.uuid,
        "status": job.status.value if hasattr(job.status, "value") else str(job.status),
        "error_message": job.error_message,
        "original_filename": job.original_filename,
        "processed_size_bytes": proc_size,
        "result_download_available": job.status == JobStatus.done and proc_ok,
        "telegram_send_limit_bytes": settings.telegram_bot_max_send_document_bytes,
    }


class DownloadInfoRequest(BaseModel):
    url: str

class DownloadStartRequest(BaseModel):
    url: str
    format: str
    clean_metadata: bool

@router.post("/api/webapp/download/info")
async def download_info(
    req: DownloadInfoRequest, 
    x_telegram_init_data: Annotated[Optional[str], Header(alias="X-Telegram-Init-Data")] = None
):
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="missing_init_data")
    url = req.url
    platform = detect_platform(url)
    if platform == "unknown":
        return JSONResponse({"supported": False}, status_code=400)
    
    try:
        from core.config import settings
        cmd = ["yt-dlp", "--dump-json", "--no-playlist", "--quiet", url]
        if platform == "youtube":
            cmd.extend(["--js-runtimes", "node", "--extractor-args", "youtube:player_client=web,default"])
            
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return JSONResponse({"error": "Failed to get info", "details": r.stderr[:200]}, status_code=400)
            
        info = json.loads(r.stdout)
        
        formats = [
            {"id": "best_1080", "label": "MP4 1080p", "ext": "mp4"},
            {"id": "best_720",  "label": "MP4 720p",  "ext": "mp4"},
            {"id": "best_480",  "label": "MP4 480p",  "ext": "mp4"},
            {"id": "best_360",  "label": "MP4 360p",  "ext": "mp4"},
            {"id": "best_auto", "label": "MP4 Auto",  "ext": "mp4"},
            {"id": "mp3_320",   "label": "MP3 320kbps", "ext": "mp3"},
            {"id": "mp3_192",   "label": "MP3 192kbps", "ext": "mp3"},
            {"id": "m4a_best",  "label": "M4A Best",  "ext": "m4a"}
        ]
        
        return {
            "platform": platform,
            "title": info.get("title", "Unknown Title"),
            "duration_sec": info.get("duration", 0),
            "thumbnail": info.get("thumbnail"),
            "formats": formats,
            "supported": True
        }
    except Exception as e:
        logger.error(f"Failed getting download info: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@router.post("/api/webapp/download/start")
async def download_start(
    req: DownloadStartRequest,
    session: AsyncSession = Depends(get_db),
    x_telegram_init_data: Annotated[Optional[str], Header(alias="X-Telegram-Init-Data")] = None
):
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="missing_init_data")
    tg_id = telegram_user_id(x_telegram_init_data.strip(), settings.bot_token)
    if tg_id is None:
        raise HTTPException(status_code=401, detail="invalid_init_data")
        
    url = req.url
    platform = detect_platform(url)
    if platform == "unknown":
        raise HTTPException(status_code=400, detail="Unsupported platform")
        
    today = datetime.utcnow().date()
    stmt = select(SiteDownloadJob).where(
        SiteDownloadJob.telegram_id == tg_id,
        SiteDownloadJob.created_at >= datetime(today.year, today.month, today.day)
    )
    result = await session.execute(stmt)
    today_count = len(result.scalars().all())
    
    if today_count >= 5:
        raise HTTPException(status_code=429, detail="Daily limit of 5 downloads reached")

    job_uuid = str(uuid.uuid4())
    job = SiteDownloadJob(
        uuid=job_uuid,
        telegram_id=tg_id,
        platform=platform,
        source_url=url,
        format=req.format,
        clean_metadata=req.clean_metadata,
        status=JobStatus.pending
    )
    session.add(job)
    await session.commit()
    
    from workers.downloader_only import download_only_task
    task = download_only_task.delay(job_uuid)
    
    job.celery_task_id = task.id
    await session.commit()
    
    return {"job_id": job_uuid, "platform": platform}

@router.get("/api/webapp/download/job/{job_id}")
async def get_download_job(
    job_id: str, 
    session: AsyncSession = Depends(get_db),
    x_telegram_init_data: Annotated[Optional[str], Header(alias="X-Telegram-Init-Data")] = None
):
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="missing_init_data")
    tg_id = telegram_user_id(x_telegram_init_data.strip(), settings.bot_token)
    if tg_id is None:
        raise HTTPException(status_code=401, detail="invalid_init_data")
        
    stmt = select(SiteDownloadJob).where(SiteDownloadJob.uuid == job_id, SiteDownloadJob.telegram_id == tg_id)
    result = await session.execute(stmt)
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    return {
        "uuid": job.uuid,
        "status": job.status,
        "platform": job.platform,
        "title": job.original_title or "Video",
        "file_size_bytes": job.file_size_bytes,
        "download_url": f"/api/webapp/download/result/{job.uuid}",
        "expires_in_minutes": 30
    }

@router.get("/api/webapp/download/result/{job_id}")
async def download_result(
    job_id: str, 
    session: AsyncSession = Depends(get_db),
    t: Annotated[Optional[str], Query(description="Signed token")] = None,
    x_telegram_init_data: Annotated[Optional[str], Header(alias="X-Telegram-Init-Data")] = None,
):
    tg_id = _resolve_result_telegram_id(job_id, t, x_telegram_init_data)
    
    stmt = select(SiteDownloadJob).where(SiteDownloadJob.uuid == job_id, SiteDownloadJob.telegram_id == tg_id)
    result = await session.execute(stmt)
    job = result.scalar_one_or_none()
    
    if not job or job.status != JobStatus.done or not job.file_path:
        raise HTTPException(status_code=404, detail="File not ready or not found")
        
    path = Path(job.file_path)
    if not path.exists():
        raise HTTPException(status_code=410, detail="File deleted or not found")
        
    return FileResponse(path, filename=path.name)


def _resolve_result_telegram_id(
    job_uuid: str,
    t: Optional[str],
    x_telegram_init_data: Optional[str],
) -> int:
    if t:
        data = parse_result_download_token(t)
        if not data or data.get("j") != job_uuid:
            raise HTTPException(status_code=401, detail="invalid_token")
        try:
            return int(data["tg"])
        except (KeyError, TypeError, ValueError):
            raise HTTPException(status_code=401, detail="invalid_token")
    if x_telegram_init_data:
        tid = telegram_user_id(x_telegram_init_data.strip(), settings.bot_token)
        if tid is None:
            raise HTTPException(status_code=401, detail="invalid_init_data")
        return tid
    raise HTTPException(status_code=401, detail="auth_required")


@router.get("/api/webapp/result/{job_uuid}")
async def webapp_download_result(
    job_uuid: str,
    session: AsyncSession = Depends(get_db),
    t: Annotated[Optional[str], Query(description="Подписанный токен из сообщения бота")] = None,
    x_telegram_init_data: Annotated[Optional[str], Header(alias="X-Telegram-Init-Data")] = None,
):
    job_uuid = _normalize_job_uuid(job_uuid)
    tg_id = _resolve_result_telegram_id(job_uuid, t, x_telegram_init_data)

    js = JobService(session)
    job = await js.get_by_uuid(job_uuid)
    if not job or not job.user or job.user.telegram_id != tg_id:
        raise HTTPException(status_code=404, detail="not_found")
    if job.status != JobStatus.done:
        raise HTTPException(status_code=409, detail="not_ready")
    path = job.temp_processed_path
    if not path or not Path(path).is_file():
        raise HTTPException(status_code=410, detail="file_gone")

    fn = _result_download_filename(job)
    return FileResponse(
        path,
        filename=fn,
    media_type="application/octet-stream",
    headers={"X-Accel-Redirect": f"{settings.x_accel_prefix}{path.name}"} if settings.use_x_accel_redirect else None
)
