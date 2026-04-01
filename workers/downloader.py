import asyncio, json, logging, subprocess, uuid
from pathlib import Path
from core.config import settings
from core.exceptions import DownloadError, InvalidYouTubeURLError
from workers.celery_app import app

logger = logging.getLogger(__name__)


def download_youtube_video(url, output_dir):
    name = str(uuid.uuid4())
    template = str(output_dir / f"{name}.%(ext)s")
    info_r = subprocess.run(["yt-dlp","--dump-json","--no-playlist","--quiet",url],
                            capture_output=True, text=True, timeout=30)
    if info_r.returncode != 0: raise InvalidYouTubeURLError(f"Cannot access: {info_r.stderr[:200]}")
    try: title = json.loads(info_r.stdout).get("title","video")
    except: title = "video"
    dl_r = subprocess.run(
        ["yt-dlp","--no-playlist","--format",
         "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]",
         "--merge-output-format","mp4","--output",template,"--no-progress","--quiet",url],
        capture_output=True, text=True, timeout=600)
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
                settings.temp_upload_dir.mkdir(parents=True, exist_ok=True)
                path, title = download_youtube_video(job.source_url, settings.temp_upload_dir)
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
                await svc.update_status(job, JobStatus.failed, str(e)); await session.commit()
                from workers.sender import notify_failure_task
                notify_failure_task.delay(job_uuid)
                return {"error":str(e)}
            except Exception as e:
                logger.exception(f"Download error job {job_uuid}")
                await svc.update_status(job, JobStatus.failed, str(e)[:200]); await session.commit()
                raise self.retry(exc=e)
    return asyncio.run(_run())
