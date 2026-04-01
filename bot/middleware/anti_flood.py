import logging
import time
from typing import TYPE_CHECKING, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import Message

if TYPE_CHECKING:
    from redis.asyncio.client import Redis

logger = logging.getLogger(__name__)


def _float_from_redis(raw) -> float:
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode()
    return float(raw)


class AntiFloodMiddleware(BaseMiddleware):
    def __init__(
        self,
        cooldown_seconds: float = 3,
        redis: Optional["Redis"] = None,
        key_prefix: str = "mc:flood",
    ):
        self.cooldown = float(cooldown_seconds)
        self._times: Dict[int, float] = {}
        self._redis = redis
        self._key_prefix = key_prefix
        super().__init__()

    async def __call__(self, handler, event, data):
        if not isinstance(event, Message) or not event.from_user:
            return await handler(event, data)
        uid = event.from_user.id
        if self._redis is not None:
            return await self._redis_gate(handler, event, data, uid)
        now = time.monotonic()
        since = now - self._times.get(uid, 0)
        if since < self.cooldown:
            remaining = max(1, round(self.cooldown - since))
            await event.answer(f"⏱ Подождите {remaining} сек. перед следующим запросом.")
            return
        self._times[uid] = now
        return await handler(event, data)

    async def _redis_gate(self, handler, event, data, uid: int):
        now = time.time()
        key = f"{self._key_prefix}:{uid}"
        try:
            raw = await self._redis.get(key)
            if raw is not None:
                last = _float_from_redis(raw)
                elapsed = now - last
                if elapsed < self.cooldown:
                    remaining = max(1, round(self.cooldown - elapsed))
                    await event.answer(f"⏱ Подождите {remaining} сек. перед следующим запросом.")
                    return
            ttl = max(int(self.cooldown * 2) + 1, 10)
            await self._redis.setex(key, ttl, str(now))
        except Exception as e:
            logger.warning("Redis anti-flood failed, allowing message: %s", e)
        return await handler(event, data)
