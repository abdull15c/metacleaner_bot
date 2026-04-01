import pytest

from core.models import JobStatus, SourceType
from core.services.job_service import JobService
from core.services.user_service import UserService


@pytest.mark.asyncio
async def test_try_begin_video_processing_once(db_session):
    u, _ = await UserService(db_session).get_or_create(88001)
    await db_session.commit()
    js = JobService(db_session)
    job = await js.create_job(u.id, SourceType.upload, "a.mp4")
    await db_session.commit()
    assert await js.try_begin_video_processing(job.uuid) is True
    await db_session.commit()
    await db_session.refresh(job)
    assert job.status == JobStatus.processing
    assert await js.try_begin_video_processing(job.uuid) is False


@pytest.mark.asyncio
async def test_try_begin_video_from_downloading(db_session):
    u, _ = await UserService(db_session).get_or_create(88002)
    await db_session.commit()
    js = JobService(db_session)
    job = await js.create_job(u.id, SourceType.youtube)
    await js.update_status(job, JobStatus.downloading)
    await db_session.commit()
    assert await js.try_begin_video_processing(job.uuid) is True
    await db_session.commit()
    await db_session.refresh(job)
    assert job.status == JobStatus.processing


@pytest.mark.asyncio
async def test_try_begin_youtube_download_idempotent(db_session):
    u, _ = await UserService(db_session).get_or_create(88003)
    await db_session.commit()
    js = JobService(db_session)
    job = await js.create_job(u.id, SourceType.youtube, source_url="https://youtu.be/test")
    await db_session.commit()
    assert await js.try_begin_youtube_download(job.uuid) is True
    await db_session.commit()
    assert await js.try_begin_youtube_download(job.uuid) is False


@pytest.mark.asyncio
async def test_try_begin_sending_idempotent(db_session):
    u, _ = await UserService(db_session).get_or_create(88004)
    await db_session.commit()
    js = JobService(db_session)
    job = await js.create_job(u.id, SourceType.upload)
    await js.update_status(job, JobStatus.processing)
    await db_session.commit()
    assert await js.try_begin_sending(job.uuid) is True
    await db_session.commit()
    assert await js.try_begin_sending(job.uuid) is False
