"""Ограничение частоты POST /admin/login по IP с использованием Redis."""
import time
from fastapi import HTTPException
from starlette.requests import Request
from redis import Redis

from core.config import get_settings

_WINDOW_SEC = 60
_memory_counters: dict[str, list[float]] = {}


def reset_counters_for_tests() -> None:
    _memory_counters.clear()


def _check_in_memory_rate(ip: str, limit: int) -> None:
    now = time.time()
    window_start = now - _WINDOW_SEC
    attempts = [ts for ts in _memory_counters.get(ip, []) if ts > window_start]
    if len(attempts) >= limit:
        raise HTTPException(
            status_code=429,
            detail="Слишком много попыток входа. Подождите минуту.",
        )
    attempts.append(now)
    _memory_counters[ip] = attempts

def check_admin_login_rate(request: Request) -> None:
    settings = get_settings()
    lim = settings.admin_login_rate_per_minute
    if not lim or lim <= 0:
        return
        
    client = request.client
    ip = (client.host if client else "") or "unknown"

    redis_url = getattr(settings, "redis_url", None)
    if not redis_url:
        _check_in_memory_rate(ip, lim)
        return

    try:
        r = Redis.from_url(redis_url)
        key = f"admin_login_rate:{ip}"

        current = r.get(key)
        if current and int(current) >= lim:
            raise HTTPException(
                status_code=429,
                detail="Слишком много попыток входа. Подождите минуту.",
            )

        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, _WINDOW_SEC)
        pipe.execute()
    except HTTPException:
        raise
    except Exception:
        _check_in_memory_rate(ip, lim)
