"""Cookies YouTube (Netscape) из админки или YOUTUBE_COOKIES_FILE в .env."""
import os
from pathlib import Path
from typing import Optional

from core.config import settings

COOKIES_MAX_BYTES = 512 * 1024


def resolve_admin_cookies_path() -> Path:
    p = Path(settings.youtube_cookies_admin_path)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.resolve()


def get_effective_youtube_cookies_path() -> Optional[Path]:
    """Сначала .env (YOUTUBE_COOKIES_FILE), иначе файл, загруженный из админки."""
    env_p = settings.youtube_cookies_file
    if env_p:
        ep = Path(env_p)
        if ep.is_file():
            return ep.resolve()
    admin_p = resolve_admin_cookies_path()
    if admin_p.is_file():
        return admin_p
    return None


def validate_netscape_cookie_file(raw: bytes) -> bool:
    if len(raw) > COOKIES_MAX_BYTES or len(raw) < 40:
        return False
    text = raw.decode("utf-8", errors="replace").lower()
    if "netscape" not in text[:8000]:
        return False
    if "youtube.com" not in text:
        return False
    return True


def save_admin_cookies(raw: bytes) -> Path:
    if not validate_netscape_cookie_file(raw):
        raise ValueError("invalid_cookies")
    path = resolve_admin_cookies_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def delete_admin_cookies() -> bool:
    path = resolve_admin_cookies_path()
    if path.is_file():
        path.unlink()
        return True
    return False
