"""
Интеграционные проверки для деплоя: общая async engine приложения, TestClient админки, отмена job.
"""
import asyncio

import core.models  # noqa: F401 — все таблицы на Base.metadata
import re
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message

pytestmark = pytest.mark.integration
@pytest.fixture
def admin_client(app_schema):
    from starlette.testclient import TestClient
    from admin.main import app

    with TestClient(app, follow_redirects=False) as client:
        yield client


def _csrf_from_login_page(html: str) -> str:
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m, "csrf_token not found in login HTML"
    return m.group(1)


def test_admin_login_sets_security_headers(admin_client):
    r = admin_client.get("/admin/login")
    assert r.status_code == 200
    assert r.headers.get("x-frame-options") == "DENY"
    assert "content-security-policy" in {k.lower() for k in r.headers.keys()}


def test_admin_login_success(admin_client):
    from admin.auth import hash_password
    from core.database import async_session_factory
    from core.models import Admin

    async def seed():
        async with async_session_factory() as session:
            session.add(
                Admin(
                    username="itestadm",
                    password_hash=hash_password("itestpw123"),
                    is_active=True,
                )
            )
            await session.commit()

    asyncio.run(seed())

    g = admin_client.get("/admin/login")
    tok = _csrf_from_login_page(g.text)
    p = admin_client.post(
        "/admin/login",
        data={
            "username": "itestadm",
            "password": "itestpw123",
            "csrf_token": tok,
        },
    )
    assert p.status_code == 303
    assert p.headers.get("location", "").endswith("/admin/dashboard")


def test_admin_login_rate_limit(app_schema, mocker):
    mocker.patch(
        "admin.login_rate.get_settings",
        return_value=MagicMock(admin_login_rate_per_minute=2),
    )
    from admin.login_rate import reset_counters_for_tests

    reset_counters_for_tests()

    from starlette.testclient import TestClient
    from admin.main import app
    from admin.auth import hash_password
    from core.database import async_session_factory
    from core.models import Admin

    async def seed():
        async with async_session_factory() as session:
            session.add(
                Admin(
                    username="rlimit",
                    password_hash=hash_password("pw"),
                    is_active=True,
                )
            )
            await session.commit()

    asyncio.run(seed())

    with TestClient(app) as client:
        for i in range(2):
            g = client.get("/admin/login")
            tok = _csrf_from_login_page(g.text)
            r = client.post(
                "/admin/login",
                data={"username": "rlimit", "password": "wrong", "csrf_token": tok},
            )
            assert r.status_code == 401, i
        g = client.get("/admin/login")
        tok = _csrf_from_login_page(g.text)
        r3 = client.post(
            "/admin/login",
            data={"username": "rlimit", "password": "wrong", "csrf_token": tok},
        )
        assert r3.status_code == 429

    reset_counters_for_tests()


@pytest.mark.asyncio
async def test_cancel_pending_revokes_celery_and_enqueues_cleanup(app_schema, mocker):
    mocker.patch("workers.cleanup.cleanup_job_files_task.delay")
    revoke = mocker.patch("workers.celery_app.app.control.revoke")

    from bot.routers.status import cmd_cancel
    from core.database import async_session_factory
    from core.models import Job, JobStatus, SourceType, User

    tid = 777001
    user_db_id = None
    async with async_session_factory() as session:
        u = User(
            telegram_id=tid,
            daily_job_count=0,
            daily_reset_at=datetime.now(timezone.utc),
        )
        session.add(u)
        await session.flush()
        user_db_id = u.id
        job = Job(
            uuid=str(uuid.uuid4()),
            user_id=u.id,
            source_type=SourceType.upload,
            status=JobStatus.pending,
            celery_task_id="celery-task-id-xyz",
        )
        session.add(job)
        await session.commit()

    message = MagicMock(spec=Message)
    message.from_user = MagicMock()
    message.from_user.id = tid
    message.answer = AsyncMock()

    await cmd_cancel(message)

    revoke.assert_called_once_with("celery-task-id-xyz", terminate=False)
    from workers.cleanup import cleanup_job_files_task

    cleanup_job_files_task.delay.assert_called_once()

    async with async_session_factory() as session:
        from sqlalchemy import select

        r = await session.execute(select(Job).where(Job.user_id == user_db_id))
        j = r.scalar_one()
        assert j.status == JobStatus.cancelled


@pytest.mark.asyncio
async def test_upload_celery_dispatch_failure_marks_job_failed(app_schema, mocker):
    mocker.patch(
        "workers.video_processor.process_video_task.delay",
        side_effect=ConnectionError("broker down"),
    )
    mocker.patch(
        "core.mime_validator.validate_video_file_mime",
        return_value=(True, "OK"),
    )

    from pathlib import Path

    from bot.routers.upload import confirm_action_cb, handle_video
    from core.database import async_session_factory
    from core.models import Job, JobStatus
    from core.services.settings_service import SettingsService

    uid = 888002

    async def seed():
        async with async_session_factory() as session:
            await SettingsService(session).seed_defaults()
            await session.commit()

    await seed()

    doc = MagicMock()
    doc.file_id = "fid"
    doc.file_name = "v.mp4"
    doc.file_size = 50
    message = MagicMock()
    message.from_user = MagicMock()
    message.from_user.id = uid
    message.from_user.username = "u"
    message.from_user.first_name = "U"
    message.document = doc
    message.video = None
    message.answer = AsyncMock()
    message.edit_text = AsyncMock()

    async def fake_download(file_path, destination=None, **kwargs):
        p = Path(destination)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x" * 200)

    bot = MagicMock()
    bot.get_file = AsyncMock(return_value=MagicMock(file_path="path"))
    bot.download_file = AsyncMock(side_effect=fake_download)

    from core.models import User

    db_user = User(id=1, telegram_id=uid, username="u", first_name="U")

    await handle_video(message, bot, db_user)

    async with async_session_factory() as session:
        from sqlalchemy import select
        from core.models import User

        u = (await session.execute(select(User).where(User.telegram_id == uid))).scalar_one()
        r = await session.execute(select(Job).where(Job.user_id == u.id))
        j = r.scalar_one()

    callback = MagicMock(spec=Message)
    callback.data = f"confirm_action:{j.uuid}:clean:fid"
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock()

    await confirm_action_cb(callback, bot)

    async with async_session_factory() as session:
        from sqlalchemy import select

        r = await session.execute(select(Job).where(Job.uuid == j.uuid))
        j = r.scalar_one()
        assert j.status == JobStatus.failed
        assert "Queue dispatch" in (j.error_message or "")
