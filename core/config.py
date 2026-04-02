from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Каталог репозитория (рядом с `core/`). Для Celery/admin важнее, чем `os.getcwd()`.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8",
        case_sensitive=False, extra="ignore",
    )
    bot_token: str
    admin_secret_key: str
    admin_session_secret: Optional[str] = None
    database_url: str = "sqlite+aiosqlite:///./metacleaner.db"
    database_pool_size: int = 5
    database_max_overflow: int = 10
    redis_url: str = "redis://localhost:6379/0"
    admin_host: str = "127.0.0.1"
    admin_port: int = Field(default=8000, ge=1, le=65535)
    admin_session_cookie: str = "metacleaner_admin"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    celery_concurrency: int = 2
    temp_upload_dir: Path = Path("./temp/uploads")
    temp_processed_dir: Path = Path("./temp/processed")
    logs_dir: Path = Path("./logs")
    max_file_size_mb: int = 500
    max_concurrent_jobs: int = 2
    max_daily_jobs_per_user: int = 10
    cleanup_ttl_minutes: int = 30
    user_cooldown_seconds: int = 3
    broadcast_delay_seconds: float = 0.05
    processing_enabled: bool = True
    maintenance_mode: bool = False
    youtube_enabled: bool = True
    youtube_cookies_file: Optional[Path] = None
    youtube_cookies_admin_path: Path = Path("secrets/youtube_cookies.txt")
    youtube_proxy: Optional[str] = None
    # Переопределить корень проекта (если воркер стартует не из каталога репозитория).
    metacleaner_root: Optional[Path] = None
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    admin_cookie_secure: bool = False
    bot_redis_enabled: bool = True
    admin_login_rate_per_minute: int = 10
    admin_security_headers: bool = True
    admin_csp: Optional[str] = None

    @field_validator("admin_secret_key")
    @classmethod
    def key_long_enough(cls, v):
        if len(v) < 16:
            raise ValueError("ADMIN_SECRET_KEY must be at least 16 chars")
        return v

    @field_validator("admin_session_secret")
    @classmethod
    def session_secret_long_enough(cls, v: Optional[str]):
        if v is not None and len(v) < 16:
            raise ValueError("ADMIN_SESSION_SECRET must be at least 16 chars if set")
        return v

    @property
    def effective_session_secret(self) -> str:
        return self.admin_session_secret or self.admin_secret_key

    @property
    def max_file_size_bytes(self): return self.max_file_size_mb * 1024 * 1024

    @property
    def project_root(self) -> Path:
        if self.metacleaner_root is not None:
            return self.metacleaner_root.expanduser().resolve()
        return _PROJECT_ROOT

    def ensure_dirs(self):
        for d in [self.temp_upload_dir, self.temp_processed_dir, self.logs_dir]:
            d.mkdir(parents=True, exist_ok=True)
        secrets_parent = Path(self.youtube_cookies_admin_path).parent
        if not secrets_parent.is_absolute():
            secrets_parent = self.project_root / secrets_parent
        secrets_parent.mkdir(parents=True, exist_ok=True)


@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
