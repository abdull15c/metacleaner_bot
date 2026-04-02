"""Cookies YouTube (Netscape): БД (админка), .env, файл из формы загрузки."""
import logging
import os
from pathlib import Path
from typing import Any, Optional, Tuple

from core.config import settings

logger = logging.getLogger(__name__)

COOKIES_MAX_BYTES = 512 * 1024


def resolve_admin_cookies_path() -> Path:
    p = Path(settings.youtube_cookies_admin_path)
    if not p.is_absolute():
        p = settings.project_root / p
    return p.resolve()


def get_effective_youtube_cookies_path() -> Optional[Path]:
    """Сначала .env (YOUTUBE_COOKIES_FILE), иначе файл, загруженный из админки.

    Относительные пути считаются от `project_root` (каталог репозитория), не от cwd —
    иначе Celery worker с другим рабочим каталогом не находит cookies.
    """
    env_p = settings.youtube_cookies_file
    if env_p:
        ep = Path(env_p)
        if not ep.is_absolute():
            ep = settings.project_root / ep
        if ep.is_file():
            return ep.resolve()
    admin_p = resolve_admin_cookies_path()
    if admin_p.is_file():
        return admin_p
    return None


def _db_cookies_path_if_valid(raw: Any, *, log_if_missing: bool = True) -> Optional[Path]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    p = Path(s)
    if not p.is_absolute():
        p = settings.project_root / p
    if p.is_file():
        return p.resolve()
    if log_if_missing:
        logger.warning("youtube_cookies_file (DB) path not found: %s", p)
    return None


async def resolve_youtube_dl_cookies_and_proxy() -> Tuple[Optional[Path], Optional[str]]:
    """Актуальные cookies и прокси для yt-dlp: сначала ключи из БД, затем .env и файл из админки."""
    from core.database import get_db_session
    from core.services.settings_service import SettingsService

    async with get_db_session() as session:
        ss = SettingsService(session)
        db_cf = await ss.get("youtube_cookies_file", "")
        db_px = await ss.get("youtube_proxy", "")

    cookies = _db_cookies_path_if_valid(db_cf)
    if cookies is None:
        cookies = get_effective_youtube_cookies_path()

    proxy: Optional[str] = None
    if db_px is not None and str(db_px).strip():
        proxy = str(db_px).strip()
    elif settings.youtube_proxy:
        proxy = str(settings.youtube_proxy).strip()

    return cookies, proxy or None


def preview_youtube_dl_sources(db_cookies_file_raw: Any, db_proxy_raw: Any) -> Tuple[str, str]:
    """Источники для подсказки в админке: cookies — db|env|admin|none; proxy — db|env|none."""
    if _db_cookies_path_if_valid(db_cookies_file_raw, log_if_missing=False) is not None:
        cookie_src = "db"
    else:
        eff = get_effective_youtube_cookies_path()
        if eff is None:
            cookie_src = "none"
        else:
            env_p = settings.youtube_cookies_file
            cookie_src = "admin"
            if env_p:
                ep = Path(env_p)
                if not ep.is_absolute():
                    ep = settings.project_root / ep
                if ep.is_file() and eff.resolve() == ep.resolve():
                    cookie_src = "env"

    if db_proxy_raw is not None and str(db_proxy_raw).strip():
        proxy_src = "db"
    elif settings.youtube_proxy and str(settings.youtube_proxy).strip():
        proxy_src = "env"
    else:
        proxy_src = "none"

    return cookie_src, proxy_src


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
