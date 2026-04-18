import asyncio, json, logging, subprocess, uuid
from pathlib import Path
from typing import Optional

from core.config import settings
from core.exceptions import DownloadError, InvalidYouTubeURLError
from core.url_validator import validate_download_url, InvalidURLError, sanitize_url_for_logging
from workers.celery_app import app

logger = logging.getLogger(__name__)


def _yt_dlp_extra_args(cookies_path: Optional[Path], proxy: Optional[str]) -> list:
    """Собрать --cookies / --proxy (значения из resolve_youtube_dl_cookies_and_proxy)."""
    args: list = []
    if cookies_path:
        args.extend(["--cookies", str(cookies_path)])
    elif settings.youtube_cookies_file:
        logger.warning(
            "YOUTUBE_COOKIES_FILE in .env but file missing (project root): %s",
            settings.youtube_cookies_file,
        )
    if proxy:
        args.extend(["--proxy", proxy])
    logger.info(
        "yt-dlp YouTube: cookies=%s proxy=%s",
        str(cookies_path) if cookies_path else "(none)",
        "on" if proxy else "off",
    )
    return args


def download_youtube_video(url, output_dir, cookies_path: Optional[Path], proxy: Optional[str]):
    # SECURITY: Валидация URL для защиты от SSRF
    try:
        url = validate_download_url(url, platform="youtube")
    except InvalidURLError as e:
        logger.warning(f"URL validation failed: {e}")
        raise InvalidYouTubeURLError(str(e))
    
    name = str(uuid.uuid4())
    template = str(output_dir / f"{name}.%(ext)s")
    extra = _yt_dlp_extra_args(cookies_path, proxy)
    
    # SECURITY: Логируем только безопасную часть URL
    safe_url = sanitize_url_for_logging(url)
    logger.info(f"Starting download from: {safe_url}")
    
    info_r = subprocess.run(
        ["yt-dlp", "--js-runtimes", "node",
         "--extractor-args", "youtube:player_client=web,default",
         *extra, "--dump-json", "--no-playlist", "--quiet", url],
        capture_output=True, text=True, timeout=30,
    )
    # SECURITY FIX: Не показывать stderr пользователю (может содержать пути, версии)
    if info_r.returncode != 0:
        logger.error(f"yt-dlp info failed for {safe_url}: {info_r.stderr[:200]}")
        raise InvalidYouTubeURLError("Cannot access video. Please check the URL.")
    try:
        info_json = json.loads(info_r.stdout)
        title = info_json.get("title","video")
        filesize = info_json.get("filesize") or info_json.get("filesize_approx")
        if filesize and filesize > settings.max_file_size_bytes:
            raise DownloadError("Файл слишком большой")
    except DownloadError:
        raise
    except:
        title = "video"
    dl_r = subprocess.run(
        [
            "yt-dlp", "--js-runtimes", "node",
            "--extractor-args", "youtube:player_client=web,default",
            *extra, "--no-playlist", "--format",
            "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]",
            "--merge-output-format", "mp4", "--output", template, "--no-progress", "--quiet", url,
        ],
        capture_output=True, text=True, timeout=600,
    )
    if dl_r.returncode != 0: raise DownloadError(f"yt-dlp failed: {dl_r.stderr[:300]}")
    files = list(output_dir.glob(f"{name}.*"))
    if not files: raise DownloadError("Downloaded file not found")
    return str(files[0]), title


@app.task(name="workers.downloader.download_youtube_task", bind=True, max_retries=1, default_retry_delay=10, queue="video")
def download_youtube_task(self, job_uuid):
    async def _run():
        from core.database import get_db_session
        from core.services.job_service import JobService
        from core.models import JobStatus
        async with get_db_session() as session:
            svc = JobService(session)
            job = await svc.get_by_uuid(job_uuid)
            if not job: return {"error":"not found"}
            if job.status == JobStatus.cancelled: return {"status":"cancelled"}
            if not job.source_url:
                await svc.update_status(job, JobStatus.failed, "No URL")
                await session.commit()
                return {"error": "no url"}
            began = await svc.try_begin_youtube_download(job_uuid)
            if not began:
                await session.commit()
                job2 = await svc.get_by_uuid(job_uuid)
                if job2 and job2.status == JobStatus.downloading:
                    return {"status": "duplicate"}
                if job2 and job2.status == JobStatus.cancelled:
                    return {"status": "cancelled"}
                return {"status": "skipped"}
            await session.commit()
            job = await svc.get_by_uuid(job_uuid)
            try:
                from core.youtube_cookies import resolve_youtube_dl_cookies_and_proxy

                settings.temp_upload_dir.mkdir(parents=True, exist_ok=True)
                cookies_path, proxy = await resolve_youtube_dl_cookies_and_proxy()
                path, title = download_youtube_video(
                    job.source_url, settings.temp_upload_dir, cookies_path, proxy
                )
                size = Path(path).stat().st_size
                if size > settings.max_file_size_bytes:
                    Path(path).unlink(missing_ok=True)
                    await svc.update_status(job, JobStatus.failed, "Too large after download")
                    await session.commit()
                    return {"error": "too large"}
                await svc.set_file_paths(job, path, size)
                if not job.original_filename: job.original_filename = f"{title[:100]}.mp4"
                await session.commit()
                from workers.video_processor import process_video_task
                process_video_task.delay(job_uuid)
                return {"status":"ok"}
            except (InvalidYouTubeURLError, DownloadError) as e:
                await svc.update_status(job, JobStatus.failed, str(e))
                if job.user:
                    from core.services.user_service import UserService
                    us = UserService(session)
                    await us.rollback_daily_job_increment(job.user)
                await session.commit()
                from workers.sender import notify_failure_task
                notify_failure_task.delay(job_uuid)
                return {"error":str(e)}
            except Exception as e:
                logger.exception(f"Download error job {job_uuid}")
                await svc.update_status(job, JobStatus.failed, str(e)[:200]); await session.commit()
                raise self.retry(exc=e)
    return asyncio.run(_run())
