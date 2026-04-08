"""Ограничение частоты POST /admin/login по IP с использованием Redis."""
import time
from fastapi import HTTPException
from starlette.requests import Request
from redis import Redis

from core.config import get_settings

_WINDOW_SEC = 60

def check_admin_login_rate(request: Request) -> None:
    settings = get_settings()
    lim = settings.admin_login_rate_per_minute
    if not lim or lim <= 0:
        return
        
    client = request.client
    ip = (client.host if client else "") or "unknown"
    
    # We use a simple redis counter with expiration
    try:
        r = Redis.from_url(settings.redis_url)
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
        # If Redis is down, we don't block login, just log warning if we had logger
        pass
