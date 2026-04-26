import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from core.models import Job, JobReport, JobStatus, SourceType


class JobService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_job(self, user_id, source_type, original_filename=None, source_url=None):
        job = Job(uuid=str(uuid.uuid4()), user_id=user_id, source_type=source_type,
                  original_filename=original_filename, source_url=source_url, status=JobStatus.pending)
        self.session.add(job)
        await self.session.flush()
        await self._report(job.id, "created")
        return job

    async def get_by_uuid(self, job_uuid) -> Optional[Job]:
        r = await self.session.execute(
            select(Job).where(Job.uuid == job_uuid).options(selectinload(Job.reports), selectinload(Job.user)))
        return r.scalar_one_or_none()

    async def get_active_job_for_user(self, user_id) -> Optional[Job]:
        active = [JobStatus.pending, JobStatus.downloading, JobStatus.processing, JobStatus.sending]
        r = await self.session.execute(
            select(Job)
            .where(and_(Job.user_id == user_id, Job.status.in_(active)))
            .order_by(Job.created_at.desc())
            .limit(1),
        )
        return r.scalars().first()
    
    async def count_active_jobs(self) -> int:
        """
        Подсчет всех активных задач в системе.
        
        SECURITY FIX: Добавлено для проверки глобального лимита MAX_CONCURRENT_JOBS.
        """
        active_statuses = [
            JobStatus.pending,
            JobStatus.downloading,
            JobStatus.processing
        ]
        r = await self.session.execute(
            select(func.count(Job.id)).where(Job.status.in_(active_statuses))
        )
        return r.scalar() or 0

    async def get_user_jobs(self, user_id, limit=5):
        r = await self.session.execute(select(Job).where(Job.user_id == user_id).order_by(Job.created_at.desc()).limit(limit))
        return list(r.scalars().all())

    async def update_status(self, job, status, error_message=None):
        job.status = status
        if status == JobStatus.processing: job.started_at = datetime.now(timezone.utc)
        elif status in (JobStatus.done, JobStatus.failed, JobStatus.cancelled): job.completed_at = datetime.now(timezone.utc)
        if error_message: job.error_message = error_message
        await self._report(job.id, status.value, error_message)

    async def set_celery_task_id(self, job, task_id): job.celery_task_id = task_id
    async def set_file_paths(self, job, path, size): job.temp_original_path = path; job.original_size_bytes = size

    async def set_processed_file(self, job, path, size, metadata_before=None, metadata_after=None):
        """
        Установить обработанный файл с метаданными.
        
        SECURITY FIX: Ограничение размера метаданных для предотвращения memory leak.
        """
        from core.metadata_utils import truncate_metadata
        
        job.temp_processed_path = path
        job.processed_size_bytes = size
        
        if metadata_before is not None:
            job.metadata_before = truncate_metadata(metadata_before)
        
        if metadata_after is not None:
            job.metadata_after = truncate_metadata(metadata_after)

        job.status = JobStatus.done
        job.completed_at = datetime.now(timezone.utc)
        await self._report(job.id, JobStatus.done.value)

    async def set_youtube_consent(self, job, consented):
        job.youtube_consent = consented
        if consented: job.youtube_consent_at = datetime.now(timezone.utc)

    async def mark_cleanup_done(self, job):
        job.cleanup_done = True; job.cleanup_at = datetime.now(timezone.utc)
        await self._report(job.id, "cleanup", "Temp files deleted")

    async def get_jobs_for_cleanup(self, ttl_minutes):
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=ttl_minutes)
        r = await self.session.execute(select(Job).where(and_(
            Job.cleanup_done == False,
            Job.status.in_([JobStatus.done, JobStatus.failed, JobStatus.cancelled]),
            Job.created_at <= cutoff,
        )))
        return list(r.scalars().all())

    async def cancel_job(self, job): await self.update_status(job, JobStatus.cancelled, "Cancelled by user")

    async def try_begin_youtube_download(self, job_uuid: str) -> bool:
        now = datetime.now(timezone.utc)
        r = await self.session.execute(
            update(Job)
            .where(and_(Job.uuid == job_uuid, Job.status == JobStatus.pending))
            .values(status=JobStatus.downloading, started_at=now)
            .returning(Job.id),
        )
        row = r.first()
        if row:
            await self._report(row[0], JobStatus.downloading.value)
            return True
        return False

    async def try_begin_video_processing(self, job_uuid: str) -> bool:
        now = datetime.now(timezone.utc)
        r = await self.session.execute(
            update(Job)
            .where(and_(
                Job.uuid == job_uuid,
                Job.status.in_((JobStatus.pending, JobStatus.downloading)),
            ))
            .values(status=JobStatus.processing, started_at=now)
            .returning(Job.id),
        )
        row = r.first()
        if row:
            await self._report(row[0], JobStatus.processing.value)
            return True
        return False

    async def try_begin_sending(self, job_uuid: str) -> bool:
        r = await self.session.execute(
            update(Job)
            .where(and_(Job.uuid == job_uuid, Job.status == JobStatus.processing))
            .values(status=JobStatus.sending)
            .returning(Job.id),
        )
        row = r.first()
        if row:
            await self._report(row[0], JobStatus.sending.value)
            return True
        return False

    async def count_total(self):
        r = await self.session.execute(select(func.count(Job.id))); return r.scalar() or 0

    async def count_today(self):
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        r = await self.session.execute(select(func.count(Job.id)).where(Job.created_at >= today))
        return r.scalar() or 0

    async def count_by_status(self, status):
        r = await self.session.execute(select(func.count(Job.id)).where(Job.status == status))
        return r.scalar() or 0

    async def count_errors_24h(self):
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        r = await self.session.execute(select(func.count(Job.id)).where(
            and_(Job.status == JobStatus.failed, Job.created_at >= cutoff)))
        return r.scalar() or 0

    async def get_recent_jobs(self, limit=20, offset=0):
        r = await self.session.execute(
            select(Job).options(selectinload(Job.user)).order_by(Job.created_at.desc()).limit(limit).offset(offset))
        return list(r.scalars().all())

    async def _report(self, job_id, event, details=None):
        self.session.add(JobReport(job_id=job_id, event=event, details=details))
