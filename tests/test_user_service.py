import pytest
from datetime import datetime, timezone

from core.models import User
from core.services.user_service import UserService


@pytest.mark.asyncio
async def test_rollback_daily_job_increment(db_session):
    u = User(
        telegram_id=99001001,
        daily_job_count=3,
        daily_reset_at=datetime.now(timezone.utc),
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    svc = UserService(db_session)
    await svc.rollback_daily_job_increment(u)
    await db_session.commit()
    await db_session.refresh(u)
    assert u.daily_job_count == 2


@pytest.mark.asyncio
async def test_rollback_daily_noop_at_zero(db_session):
    u = User(telegram_id=99001002, daily_job_count=0, daily_reset_at=datetime.now(timezone.utc))
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    svc = UserService(db_session)
    await svc.rollback_daily_job_increment(u)
    await db_session.commit()
    await db_session.refresh(u)
    assert u.daily_job_count == 0


@pytest.mark.asyncio
async def test_get_by_id(db_session):
    u = User(telegram_id=99001003, daily_job_count=0, daily_reset_at=datetime.now(timezone.utc))
    db_session.add(u)
    await db_session.commit()
    uid = u.id
    svc = UserService(db_session)
    found = await svc.get_by_id(uid)
    assert found is not None and found.telegram_id == 99001003
