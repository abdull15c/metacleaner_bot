import json
from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.models import Setting

DEFAULTS = {
    "cleanup_ttl_minutes":      ("30",    "Minutes before temp files force-deleted"),
    "max_file_size_mb":         ("500",   "Max upload size in MB"),
    "max_concurrent_jobs":      ("2",     "Max simultaneous processing jobs"),
    "max_daily_jobs_per_user":  ("10",    "Daily job limit per user"),
    "user_cooldown_seconds":    ("3",     "Seconds between user messages"),
    "broadcast_delay_seconds":  ("0.05",  "Delay between broadcast messages"),
    "processing_enabled":       ("true",  "Enable/disable processing globally"),
    "maintenance_mode":         ("false", "Maintenance mode"),
    "youtube_enabled":          ("true",  "Enable YouTube URL processing"),
    "youtube_cookies_file": (
        "",
        "Путь к Netscape cookies для yt-dlp (от корня проекта). Очистить поле — только .env и загрузка ниже.",
    ),
    "youtube_proxy": (
        "",
        "Прокси для yt-dlp. Пусто — из .env (YOUTUBE_PROXY).",
    ),
}

# Ключи, разрешённые к изменению через POST /admin/settings (защита от лишних полей формы).
ALLOWED_SETTING_KEYS = frozenset(DEFAULTS.keys())


class SettingsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, key, default=None):
        import redis.asyncio as aioredis
        from core.config import settings
        r_client = aioredis.from_url(str(settings.redis_url))
        cache_key = f"setting:{key}"
        
        cached = await r_client.get(cache_key)
        if cached is not None:
            await r_client.close()
            try: return json.loads(cached)
            except: return cached.decode('utf-8')
            
        r = await self.session.execute(select(Setting).where(Setting.key == key))
        s = r.scalar_one_or_none()
        
        val = default
        if s is not None:
            try: val = json.loads(s.value)
            except: val = s.value
            
        try:
            await r_client.setex(cache_key, 60, json.dumps(val) if not isinstance(val, str) else val)
        except Exception:
            pass
            
        await r_client.close()
        return val

    async def set(self, key, value, admin_id=None):
        r = await self.session.execute(select(Setting).where(Setting.key == key))
        s = r.scalar_one_or_none()
        v = json.dumps(value) if not isinstance(value, str) else value
        if s is None:
            desc = DEFAULTS.get(key, (None, None))[1]
            self.session.add(Setting(key=key, value=v, description=desc,
                                     updated_at=datetime.now(timezone.utc), updated_by=admin_id))
        else:
            s.value = v; s.updated_at = datetime.now(timezone.utc); s.updated_by = admin_id
            
        import redis.asyncio as aioredis
        from core.config import settings
        r_client = aioredis.from_url(str(settings.redis_url))
        cache_key = f"setting:{key}"
        await r_client.delete(cache_key)
        await r_client.close()

    async def get_all(self):
        r = await self.session.execute(select(Setting))
        out = {}
        for s in r.scalars().all():
            try: out[s.key] = json.loads(s.value)
            except: out[s.key] = s.value
        return out

    async def get_all_with_meta(self):
        r = await self.session.execute(select(Setting).order_by(Setting.key))
        return list(r.scalars().all())

    async def seed_defaults(self):
        for key, (value, description) in DEFAULTS.items():
            r = await self.session.execute(select(Setting).where(Setting.key == key))
            if r.scalar_one_or_none() is None:
                self.session.add(Setting(key=key, value=value, description=description))
