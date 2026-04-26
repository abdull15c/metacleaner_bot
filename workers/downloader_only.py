import asyncio
import logging
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.config import settings
from core.database import get_db_session
from core.models import SiteDownloadJob, JobStatus, DownloadFormat
from core.platform_detect import validate_url_security
from core.url_validator import sanitize_url_for_logging
from workers.celery_app import app

logger = logging.getLogger(__name__)

def get_cookies_for_platform(platform: str) -> Optional[Path]:
    if platform == "youtube":
        from core.youtube_cookies import resolve_youtube_dl_cookies_and_proxy
        # Since it's async, we might need a workaround or we handle it in async scope.
        return None  # Handle async resolution explicitly
    elif platform == "instagram":
        return settings.instagram_cookies_file
    elif platform == "tiktok":
        return settings.tiktok_cookies_file
    elif platform == "facebook":
        return settings.facebook_cookies_file
    return None

def get_format_args(format_enum: str) -> list:
    format_enum = DownloadFormat(format_enum)
    format_map = {
        DownloadFormat.best_1080: ["--format", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]"],
        DownloadFormat.best_720:  ["--format", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]"],
        DownloadFormat.best_480:  ["--format", "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]"],
        DownloadFormat.best_360:  ["--format", "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360]"],
        DownloadFormat.best_auto: ["--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best"],
        DownloadFormat.mp3_320:   ["--format", "bestaudio", "--extract-audio", "--audio-format", "mp3", "--audio-quality", "0"],
        DownloadFormat.mp3_192:   ["--format", "bestaudio", "--extract-audio", "--audio-format", "mp3", "--audio-quality", "5"],
        DownloadFormat.m4a_best:  ["--format", "bestaudio[ext=m4a]/bestaudio", "--merge-output-format", "m4a"],
    }
    return format_map.get(format_enum, ["--format", "best"])

def get_extension(format_enum: str) -> str:
    format_enum = DownloadFormat(format_enum)
    if format_enum in [DownloadFormat.mp3_320, DownloadFormat.mp3_192]:
        return "mp3"
    elif format_enum == DownloadFormat.m4a_best:
        return "m4a"
    return "mp4"

@app.task(name="workers.downloader_only.download_only_task", queue="video")
def download_only_task(job_uuid: str):
    async def _run():
        async with get_db_session() as session:
            from sqlalchemy import select
            result = await session.execute(select(SiteDownloadJob).where(SiteDownloadJob.uuid == job_uuid))
            job = result.scalar_one_or_none()
            
            if not job or job.status == JobStatus.cancelled:
                return {"status": "cancelled or not found"}
            
            is_valid, error_msg = validate_url_security(job.source_url)
            if not is_valid:
                job.status = JobStatus.failed
                job.error_message = f"Invalid URL: {error_msg}"[:500]
                await session.commit()
                return {"error": "invalid_url"}

            job.status = JobStatus.downloading
            job.started_at = datetime.now(timezone.utc)
            await session.commit()

            try:
                settings.temp_upload_dir.mkdir(parents=True, exist_ok=True)
                
                # Fetch cookies
                cookies_path = None
                proxy = None
                if job.platform == "youtube":
                    from core.youtube_cookies import resolve_youtube_dl_cookies_and_proxy
                    cookies_path, proxy = await resolve_youtube_dl_cookies_and_proxy()
                else:
                    cookies_path = get_cookies_for_platform(job.platform)

                # Prepare yt-dlp arguments
                name = str(uuid.uuid4())
                ext = get_extension(job.format)
                template = str(settings.temp_upload_dir / f"{name}.%(ext)s")
                
                cmd = ["yt-dlp", "--no-playlist"]
                
                if cookies_path:
                    cmd.extend(["--cookies", str(cookies_path)])
                if proxy:
                    cmd.extend(["--proxy", proxy])
                if job.platform == "youtube":
                    cmd.extend(["--js-runtimes", "node", "--extractor-args", "youtube:player_client=web,default"])
                
                cmd.extend(get_format_args(job.format))
                if ext == "mp4":
                    cmd.extend(["--merge-output-format", "mp4"])
                
                cmd.extend(["--output", template, "--quiet", "--no-warnings", job.source_url])
                
                logger.info(
                    "Running yt-dlp for site download job %s platform=%s url=%s",
                    job_uuid,
                    job.platform,
                    sanitize_url_for_logging(job.source_url),
                )
                
                dl_r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
                if dl_r.returncode != 0:
                    raise Exception(f"yt-dlp failed: {dl_r.stderr[:300]}")
                
                files = list(settings.temp_upload_dir.glob(f"{name}.*"))
                if not files:
                    raise Exception("Downloaded file not found")
                
                downloaded_file = files[0]
                final_file = downloaded_file
                if downloaded_file.stat().st_size > settings.max_file_size_bytes:
                    downloaded_file.unlink(missing_ok=True)
                    raise Exception("Downloaded file exceeds size limit")
                
                # Strip metadata if requested
                if job.clean_metadata:
                    settings.temp_processed_dir.mkdir(parents=True, exist_ok=True)
                    clean_file = settings.temp_processed_dir / f"{name}_clean{downloaded_file.suffix}"
                    ffmpeg_cmd = [
                        "ffmpeg", "-y", "-i", str(downloaded_file),
                        "-map", "0", "-c", "copy",
                        "-map_metadata", "-1",
                        str(clean_file)
                    ]
                    ff_r = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=600)
                    if ff_r.returncode != 0:
                        raise Exception(f"FFmpeg failed: {ff_r.stderr[:300]}")
                    
                    downloaded_file.unlink(missing_ok=True)
                    final_file = clean_file
                    if final_file.stat().st_size > settings.max_file_size_bytes:
                        final_file.unlink(missing_ok=True)
                        raise Exception("Processed file exceeds size limit")
                
                # Update job success
                job.file_path = str(final_file)
                job.file_size_bytes = final_file.stat().st_size
                job.status = JobStatus.done
                job.completed_at = datetime.now(timezone.utc)
                await session.commit()
                try:
                    await _notify_download_ready(job)
                except Exception:
                    logger.exception("Failed to notify site download completion for %s", job_uuid)
                return {"status": "done"}
                
            except Exception as e:
                logger.exception(f"Download failed for {job_uuid}")
                job.status = JobStatus.failed
                job.error_message = str(e)[:500]
                job.completed_at = datetime.now(timezone.utc)
                await session.commit()
                try:
                    await _notify_download_failed(job)
                except Exception:
                    logger.exception("Failed to notify site download failure for %s", job_uuid)
                return {"error": str(e)}

    return asyncio.run(_run())


async def _notify_download_ready(job: SiteDownloadJob) -> None:
    if not settings.bot_token or not settings.public_download_base_url:
        return
    from aiogram import Bot
    from urllib.parse import quote
    from webapp.result_token import create_result_download_token

    bot = Bot(token=settings.bot_token)
    try:
        token = create_result_download_token(job.uuid, job.telegram_id)
        link = f"{settings.public_download_base_url}/api/webapp/download/result/{job.uuid}?t={quote(token)}"
        title = (job.original_title or "Видео")[:120]
        await bot.send_message(
            chat_id=job.telegram_id,
            text=(
                f"✅ <b>Скачивание готово.</b>\n"
                f"<b>{title}</b>\n\n"
                f"<a href=\"{link}\">⬇️ Скачать файл</a>\n"
                f"Файл будет удалён через {settings.cleanup_ttl_minutes} минут."
            ),
            parse_mode="HTML",
        )
    finally:
        await bot.session.close()


async def _notify_download_failed(job: SiteDownloadJob) -> None:
    if not settings.bot_token:
        return
    from aiogram import Bot

    bot = Bot(token=settings.bot_token)
    try:
        await bot.send_message(
            chat_id=job.telegram_id,
            text="❌ Не удалось скачать файл. Проверьте ссылку или попробуйте позже.",
        )
    finally:
        await bot.session.close()
