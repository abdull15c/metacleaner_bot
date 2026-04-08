"""Проверка подписи Telegram Web App initData (не доверять user id из JS)."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, Optional
from urllib.parse import parse_qsl


def validate_webapp_init_data(init_data: str, bot_token: str, *, max_age_seconds: int = 86400) -> Optional[dict[str, Any]]:
    """
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    Возвращает распарсенный объект user (dict) при успехе, иначе None.
    """
    if not init_data or not bot_token:
        return None
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    except ValueError:
        return None
    recv_hash = pairs.pop("hash", None)
    if not recv_hash:
        return None
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calc = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, recv_hash):
        return None
    try:
        auth_date = int(pairs.get("auth_date", 0))
    except (TypeError, ValueError):
        return None
    if auth_date and (time.time() - auth_date) > max_age_seconds:
        return None
    raw_user = pairs.get("user")
    if not raw_user:
        return None
    try:
        user = json.loads(raw_user)
    except json.JSONDecodeError:
        return None
    if not isinstance(user, dict) or "id" not in user:
        return None
    return user


def telegram_user_id(init_data: str, bot_token: str) -> Optional[int]:
    u = validate_webapp_init_data(init_data, bot_token)
    if not u:
        return None
    try:
        return int(u["id"])
    except (KeyError, TypeError, ValueError):
        return None
