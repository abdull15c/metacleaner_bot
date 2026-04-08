"""Одноразовые ссылки на скачивание результата (слишком большой для sendDocument)."""
from __future__ import annotations

from typing import Any, Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from core.config import settings

_SALT = "mc-webapp-result-v1"


def create_result_download_token(job_uuid: str, telegram_id: int) -> str:
    ser = URLSafeTimedSerializer(settings.admin_secret_key, salt=_SALT)
    return ser.dumps({"j": job_uuid, "tg": int(telegram_id)})


def parse_result_download_token(token: str, max_age_seconds: int = 86400 * 7) -> Optional[dict[str, Any]]:
    ser = URLSafeTimedSerializer(settings.admin_secret_key, salt=_SALT)
    try:
        data = ser.loads(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict) or "j" not in data or "tg" not in data:
        return None
    return data
