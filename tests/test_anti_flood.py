import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bot.middleware.anti_flood import AntiFloodMiddleware


def msg(uid):
    m = MagicMock(); m.from_user = MagicMock(); m.from_user.id = uid
    m.answer = AsyncMock(); return m


@pytest.mark.asyncio
async def test_first_message_passes():
    mw = AntiFloodMiddleware(3); handler = AsyncMock(); m = msg(1)
    await mw(handler, m, {}); handler.assert_called_once()


@pytest.mark.asyncio
async def test_second_blocked():
    mw = AntiFloodMiddleware(5); handler = AsyncMock(); m = msg(2)
    await mw(handler, m, {})
    handler.reset_mock(); await mw(handler, m, {})
    handler.assert_not_called(); m.answer.assert_called_once()


@pytest.mark.asyncio
async def test_passes_after_cooldown():
    mw = AntiFloodMiddleware(1); handler = AsyncMock(); m = msg(3)
    await mw(handler, m, {})
    mw._times[3] -= 2
    handler.reset_mock(); await mw(handler, m, {})
    handler.assert_called_once()


@pytest.mark.asyncio
async def test_different_users_independent():
    mw = AntiFloodMiddleware(10); handler = AsyncMock()
    await mw(handler, msg(10), {}); await mw(handler, msg(11), {})
    assert handler.call_count == 2


@pytest.mark.asyncio
async def test_redis_backend_first_message():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    mw = AntiFloodMiddleware(5, redis=redis)
    handler = AsyncMock()
    m = msg(201)
    await mw(handler, m, {})
    handler.assert_called_once()
    redis.setex.assert_called_once()


@pytest.mark.asyncio
async def test_redis_backend_blocks_within_cooldown():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=b"999.0")
    redis.setex = AsyncMock()
    mw = AntiFloodMiddleware(60, redis=redis)
    handler = AsyncMock()
    m = msg(202)
    m.answer = AsyncMock()
    with patch("bot.middleware.anti_flood.time.time", return_value=1000.0):
        await mw(handler, m, {})
    handler.assert_not_called()
    m.answer.assert_called_once()
