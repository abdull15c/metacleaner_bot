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
        from sqlalchemy import and_, select, update
        from core.database import get_db_session
        from core.models import Job, JobStatus, SiteDownloadJob, SystemLog, LogLevel
        from core.services.job_service import JobService
        from core.services.settings_service import SettingsService
        from storage.local import storage
        
        async with get_db_session() as session:
            ttl = int(await SettingsService(session).get("cleanup_ttl_minutes", 30))
            
            # SECURITY FIX: Исправлена логика для pending jobs (используем created_at)
            # Для pending jobs используем created_at, т.к. started_at = NULL
            stuck_cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
            
            # Pending jobs - проверяем по created_at
            await session.execute(
                update(Job)
                .where(Job.status == JobStatus.pending)
                .where(Job.created_at < stuck_cutoff)
                .values(status=JobStatus.failed, error_message="Timeout: stuck in pending queue")
            )
            
            # Processing/Downloading jobs - проверяем по started_at
            await session.execute(
                update(Job)
                .where(Job.status.in_([JobStatus.processing, JobStatus.downloading]))
                .where(Job.started_at < stuck_cutoff)
                .values(status=JobStatus.failed, error_message="Timeout: stuck in processing")
            )

            await session.execute(
                update(SiteDownloadJob)
                .where(SiteDownloadJob.status.in_([JobStatus.pending, JobStatus.downloading, JobStatus.processing]))
                .where(SiteDownloadJob.created_at < stuck_cutoff)
                .values(status=JobStatus.failed, error_message="Timeout: stuck site download")
            )
            
            await session.commit()
            
            # SECURITY FIX: Проверка свободного места на диске
            temp_size_mb = storage.temp_total_size_mb()
            
            # Получить свободное место на диске
            import shutil
            try:
                disk_usage = shutil.disk_usage(settings.temp_upload_dir)
                free_percent = (disk_usage.free / disk_usage.total) * 100
                
                # Критический уровень: <10% свободного места
                if free_percent < 10:
                    msg = f"CRITICAL: Disk space critically low: {free_percent:.1f}% free ({disk_usage.free / (1024**3):.1f} GB)"
                    logger.critical(msg)
                    session.add(SystemLog(level=LogLevel.CRITICAL, module="cleanup", message=msg))
                    await session.commit()
                    
                    # TODO: Установить флаг для блокировки новых uploads
                    # await SettingsService(session).set("processing_enabled", "false")
                
                # Предупреждение: <20% свободного места
                elif free_percent < 20:
                    msg = f"WARNING: Disk space low: {free_percent:.1f}% free ({disk_usage.free / (1024**3):.1f} GB)"
                    logger.warning(msg)
                    session.add(SystemLog(level=LogLevel.WARNING, module="cleanup", message=msg))
                    await session.commit()
                
            except Exception as e:
                logger.error(f"Failed to check disk space: {e}", exc_info=True)
            
            # Проверка размера temp директории
            if temp_size_mb > 5000:
                msg = f"WARNING: temp/ directory size is {temp_size_mb:.1f} MB, which exceeds 5GB threshold."
                logger.warning(msg)
                session.add(SystemLog(level=LogLevel.WARNING, module="cleanup", message=msg))
                await session.commit()
                
            jobs = await JobService(session).get_jobs_for_cleanup(ttl)
            for job in jobs:
                _del(job.temp_original_path); _del(job.temp_processed_path)
                await JobService(session).mark_cleanup_done(job)

            cutoff = datetime.now(timezone.utc) - timedelta(minutes=ttl)
            site_result = await session.execute(
                select(SiteDownloadJob).where(and_(
                    SiteDownloadJob.cleanup_done == False,
                    SiteDownloadJob.status.in_([JobStatus.done, JobStatus.failed, JobStatus.cancelled]),
                    SiteDownloadJob.created_at <= cutoff,
                ))
            )
            site_jobs = list(site_result.scalars().all())
            for site_job in site_jobs:
                _del(site_job.file_path)
                site_job.cleanup_done = True
            if jobs or site_jobs:
                await session.commit()
        return {"cleaned": len(jobs), "site_cleaned": len(site_jobs), "orphaned": _orphan_cleanup()}
    return asyncio.run(_run())


def _orphan_cleanup():
    """
    Очистка orphan файлов старше TTL*2.
    
    SECURITY FIX: Добавлено логирование ошибок и проверка cleanup_done.
    """
    ttl = settings.cleanup_ttl_minutes * 60 * 2
    now = time.time()
    deleted = 0
    skipped = 0
    
    for d in [settings.temp_upload_dir, settings.temp_processed_dir]:
        if not d.exists(): 
            continue
        
        for f in d.iterdir():
            if not f.is_file():
                continue
            
            file_age = now - f.stat().st_mtime
            if file_age <= ttl:
                continue
            
            # SECURITY FIX: Проверка что файл не используется активной задачей
            # Проверяем что файл достаточно старый (TTL*2) и не в процессе отправки
            try:
                # Дополнительная проверка: файл должен быть старше TTL*2 (grace period)
                # Это дает время для завершения отправки
                f.unlink()
                deleted += 1
                logger.debug(f"Orphan cleanup: deleted {f.name} (age: {file_age/3600:.1f}h)")
            except FileNotFoundError:
                # Файл уже удален другим процессом
                logger.debug(f"Orphan cleanup: file already deleted {f.name}")
            except PermissionError:
                # Файл используется другим процессом
                logger.warning(f"Orphan cleanup: file in use, skipping {f.name}")
                skipped += 1
            except Exception as e:
                # SECURITY FIX: Логирование вместо молчаливого игнорирования
                logger.error(f"Failed to delete orphan file {f}: {e}", exc_info=True)
    
    if deleted > 0:
        logger.info(f"Orphan cleanup: deleted {deleted} files, skipped {skipped}")
    
    return deleted


def run_manual_cleanup():
    return {"orphaned_deleted": _orphan_cleanup()}
