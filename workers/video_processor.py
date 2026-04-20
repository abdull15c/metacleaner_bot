import asyncio, json, logging, subprocess, uuid
from pathlib import Path
from core.config import settings
from core.constants import SUPPORTED_VIDEO_EXTENSIONS
from core.exceptions import FFmpegError, FFmpegNotFoundError
from workers.celery_app import app

logger = logging.getLogger(__name__)
SUPPORTED_EXTENSIONS = SUPPORTED_VIDEO_EXTENSIONS


def check_ffmpeg():
    for b in ["ffmpeg","ffprobe"]:
        try:
            r = subprocess.run([b,"-version"], capture_output=True, text=True, timeout=5)
            if r.returncode != 0: raise FFmpegNotFoundError(f"{b} error")
        except FileNotFoundError:
            raise FFmpegNotFoundError(f"{b} not found. Install FFmpeg and add to PATH.")
    return "ffmpeg","ffprobe"


def extract_metadata(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            logger.debug("ffprobe exit %s for %s", r.returncode, path)
            return {}
        data = json.loads(r.stdout)
        meta = {}
        if "format" in data and "tags" in data["format"]:
            meta["format_tags"] = data["format"]["tags"]
        for i, s in enumerate(data.get("streams", [])):
            if "tags" in s:
                meta[f"stream_{i}_tags"] = s["tags"]
        return meta
    except json.JSONDecodeError as e:
        logger.warning("ffprobe JSON decode failed for %s: %s", path, e)
        return {}
    except subprocess.TimeoutExpired:
        logger.warning("ffprobe timeout for %s", path)
        return {}
    except OSError as e:
        logger.warning("ffprobe failed for %s: %s", path, e)
        return {}


def strip_metadata(input_path, output_path):
    cmd = ["ffmpeg","-y","-i",input_path,"-map_metadata","-1","-map_chapters","-1",
           "-c","copy","-movflags","+faststart",output_path]
    logger.info(f"FFmpeg: {' '.join(cmd)}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode != 0: raise FFmpegError(r.returncode, r.stderr)
        return True, r.stderr
    except subprocess.TimeoutExpired:
        raise FFmpegError(-1, "FFmpeg timed out")


def get_output_path(input_path, action="clean"):
    ext = Path(input_path).suffix.lower()
    u = uuid.uuid4()
    if action == "extract_audio":
        return str(settings.temp_processed_dir / f"{u}_audio.mp3")
    elif action == "screenshot":
        return str(settings.temp_processed_dir / f"{u}_thumb.jpg")
    return str(settings.temp_processed_dir / f"{uuid.uuid4()}_clean{ext}")

def run_ffmpeg_action(input_path, output_path, action="clean"):
    if action == "extract_audio":
        # Extract audio to MP3 192k
        cmd = ["ffmpeg", "-y", "-i", input_path, "-vn", "-acodec", "libmp3lame", "-ab", "192k", output_path]
    elif action == "screenshot":
        # Take a screenshot at 1 second mark (or 0)
        cmd = ["ffmpeg", "-y", "-i", input_path, "-ss", "00:00:01", "-vframes", "1", output_path]
    else:
        # Default clean
        cmd = ["ffmpeg", "-y", "-i", input_path, "-map_metadata", "-1", "-map_chapters", "-1",
               "-c", "copy", "-movflags", "+faststart", output_path]
               
    logger.info(f"FFmpeg ({action}): {' '.join(cmd)}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode != 0: raise FFmpegError(r.returncode, r.stderr)
        return True, r.stderr
    except subprocess.TimeoutExpired:
        raise FFmpegError(-1, "FFmpeg timed out")


@app.task(name="workers.video_processor.process_video_task", bind=True, max_retries=2, default_retry_delay=30, queue="video")
def process_video_task(self, job_uuid):
    async def _run():
        from core.database import get_db_session
        from core.services.job_service import JobService
        from core.models import JobStatus
        async with get_db_session() as session:
            svc = JobService(session)
            job = await svc.get_by_uuid(job_uuid)
            if not job: return {"error":"not found"}
            if job.status == JobStatus.cancelled: return {"status":"cancelled"}
            input_path = job.temp_original_path
            if not input_path or not Path(input_path).exists():
                await svc.update_status(job, JobStatus.failed, "Input file missing")
                await session.commit()
                return {"error": "missing"}
                
            began = await svc.try_begin_video_processing(job_uuid)
            if not began:
                await session.commit()
                job2 = await svc.get_by_uuid(job_uuid)
                if job2 and job2.status == JobStatus.processing:
                    return {"status": "duplicate"}
                return {"status": "skipped"}
                
            await session.commit()
            
            job = await svc.get_by_uuid(job_uuid)
            action = job.job_action.value if hasattr(job.job_action, "value") else str(job.job_action)
            try:
                meta_before = extract_metadata(input_path)
                output_path = get_output_path(input_path, action=action)
                settings.temp_processed_dir.mkdir(parents=True, exist_ok=True)
                run_ffmpeg_action(input_path, output_path, action=action)
                if not Path(output_path).exists(): raise FFmpegError(-1,"Output not created")
                meta_after = extract_metadata(output_path)
                size = Path(output_path).stat().st_size
                await svc.set_processed_file(job, output_path, size, meta_before, meta_after)
                await session.commit()
                from workers.sender import send_result_task
                send_result_task.delay(job_uuid)
                return {"status":"ok"}
            except FFmpegError as e:
                await svc.update_status(job, JobStatus.failed, str(e)); await session.commit()
                from workers.sender import notify_failure_task
                notify_failure_task.delay(job_uuid)
                return {"error":str(e)}
            except Exception as e:
                logger.exception(f"Unexpected error job {job_uuid}")
                try:
                    await svc.update_status(job, JobStatus.failed, str(e)[:200]); await session.commit()
                except Exception as update_error:
                    # SECURITY FIX: Логирование вместо молчаливого игнорирования
                    logger.error(f"Failed to update job status after error: {update_error}", exc_info=True)
                raise self.retry(exc=e)
    return asyncio.run(_run())
