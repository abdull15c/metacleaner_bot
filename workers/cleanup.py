import asyncio, logging, time
from pathlib import Path
from core.config import settings
from workers.celery_app import app

logger = logging.getLogger(__name__)


def _del(path):
    if not path: return False
    try:
        p = Path(path)
        if p.exists(): p.unlink(); logger.info(f"Deleted: {path}"); return True
        return False
    except Exception as e:
        logger.error(f"Delete failed {path}: {e}"); return False


@app.task(name="workers.cleanup.cleanup_job_files_task", queue="cleanup")
def cleanup_job_files_task(job_uuid):
    async def _run():
        from core.database import get_db_session
        from core.services.job_service import JobService
        async with get_db_session() as session:
            svc = JobService(session)
            job = await svc.get_by_uuid(job_uuid)
            if not job or job.cleanup_done: return {"status":"skipped"}
            _del(job.temp_original_path); _del(job.temp_processed_path)
            await svc.mark_cleanup_done(job); await session.commit()
            return {"status":"cleaned"}
    return asyncio.run(_run())


@app.task(name="workers.cleanup.periodic_cleanup_task", queue="cleanup")
def periodic_cleanup_task():
    async def _run():
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import update
        from core.database import get_db_session
        from core.models import Job, JobStatus, SystemLog, LogLevel
        from core.services.job_service import JobService
        from core.services.settings_service import SettingsService
        from storage.local import storage
        
        async with get_db_session() as session:
            ttl = int(await SettingsService(session).get("cleanup_ttl_minutes", 30))
            
            stuck_cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
            await session.execute(
                update(Job)
                .where(Job.status.in_([JobStatus.pending, JobStatus.processing, JobStatus.downloading]))
                .where(Job.started_at < stuck_cutoff)
                .values(status=JobStatus.failed, error_message="Timeout: stuck in queue")
            )
            await session.commit()
            
            temp_size_mb = storage.temp_total_size_mb()
            if temp_size_mb > 5000:
                msg = f"WARNING: temp/ directory size is {temp_size_mb:.1f} MB, which exceeds 5GB threshold."
                logger.warning(msg)
                session.add(SystemLog(level=LogLevel.WARNING, source="cleanup", message=msg))
                await session.commit()
                
            jobs = await JobService(session).get_jobs_for_cleanup(ttl)
            for job in jobs:
                _del(job.temp_original_path); _del(job.temp_processed_path)
                await JobService(session).mark_cleanup_done(job)
            if jobs: await session.commit()
        return {"cleaned": len(jobs), "orphaned": _orphan_cleanup()}
    return asyncio.run(_run())


def _orphan_cleanup():
    ttl = settings.cleanup_ttl_minutes * 60 * 2
    now = time.time(); deleted = 0
    for d in [settings.temp_upload_dir, settings.temp_processed_dir]:
        if not d.exists(): continue
        for f in d.iterdir():
            if f.is_file() and (now - f.stat().st_mtime) > ttl:
                try: f.unlink(); deleted += 1
                except: pass
    return deleted


def run_manual_cleanup():
    return {"orphaned_deleted": _orphan_cleanup()}
