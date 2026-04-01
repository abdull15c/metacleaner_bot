import pytest
from core.models import JobStatus, SourceType
from core.services.job_service import JobService
from core.services.user_service import UserService


@pytest.mark.asyncio
async def test_create_job(db_session):
    u, _ = await UserService(db_session).get_or_create(111); await db_session.commit()
    js = JobService(db_session)
    job = await js.create_job(u.id, SourceType.upload, "test.mp4"); await db_session.commit()
    assert job.uuid and len(job.uuid) == 36
    assert job.status == JobStatus.pending
    assert job.cleanup_done is False


@pytest.mark.asyncio
async def test_status_transitions(db_session):
    u, _ = await UserService(db_session).get_or_create(222); await db_session.commit()
    js = JobService(db_session)
    job = await js.create_job(u.id, SourceType.upload); await db_session.commit()
    await js.update_status(job, JobStatus.processing)
    assert job.started_at is not None
    await js.update_status(job, JobStatus.done)
    assert job.completed_at is not None


@pytest.mark.asyncio
async def test_active_job_detection(db_session):
    u, _ = await UserService(db_session).get_or_create(333); await db_session.commit()
    js = JobService(db_session)
    job = await js.create_job(u.id, SourceType.upload); await db_session.commit()
    assert await js.get_active_job_for_user(u.id) is not None
    await js.update_status(job, JobStatus.done); await db_session.commit()
    assert await js.get_active_job_for_user(u.id) is None


@pytest.mark.asyncio
async def test_cancel_job(db_session):
    u, _ = await UserService(db_session).get_or_create(444); await db_session.commit()
    js = JobService(db_session)
    job = await js.create_job(u.id, SourceType.upload); await db_session.commit()
    await js.cancel_job(job)
    assert job.status == JobStatus.cancelled
