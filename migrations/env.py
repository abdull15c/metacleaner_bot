import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from logging.config import fileConfig
from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from core.config import settings
from core.database import Base
from core.models import User, Job, JobReport, Admin, Broadcast, BroadcastRecipient, SystemLog, Setting  # noqa

def _alembic_async_url(url: str) -> str:
    if "+aiosqlite" in url or "+asyncpg" in url:
        return url
    if url.startswith("sqlite+") or url.startswith("postgresql+"):
        return url
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://"):]
    return url


config = context.config
config.set_main_option("sqlalchemy.url", _alembic_async_url(settings.database_url))
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"),
                      target_metadata=target_metadata, literal_binds=True,
                      render_as_batch=True)
    with context.begin_transaction(): context.run_migrations()


def do_run(connection: Connection):
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction(): context.run_migrations()


async def run_async():
    cfg = config.get_section(config.config_ini_section, {})
    engine = async_engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with engine.connect() as conn: await conn.run_sync(do_run)
    await engine.dispose()


def run_migrations_online(): asyncio.run(run_async())

if context.is_offline_mode(): run_migrations_offline()
else: run_migrations_online()
