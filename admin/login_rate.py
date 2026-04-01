"""Ограничение частоты POST /admin/login по IP (in-process). На нескольких воркерах Uvicorn — см. DEPLOY.md (nginx limit_req)."""
import time
from collections import deque
from typing import Deque, Dict

from fastapi import HTTPException
from starlette.requests import Request

from core.config import get_settings

_counters: Dict[str, Deque[float]] = {}
_WINDOW_SEC = 60.0


def reset_counters_for_tests():
    _counters.clear()


def check_admin_login_rate(request: Request) -> None:
    lim = get_settings().admin_login_rate_per_minute
    if not lim or lim <= 0:
        return
    client = request.client
    ip = (client.host if client else "") or "unknown"
    now = time.monotonic()
    dq = _counters.setdefault(ip, deque())
    while dq and now - dq[0] > _WINDOW_SEC:
        dq.popleft()
    if len(dq) >= lim:
        raise HTTPException(
            status_code=429,
            detail="Слишком много попыток входа. Подождите минуту.",
        )
    dq.append(now)
