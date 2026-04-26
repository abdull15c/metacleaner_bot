import asyncio, os, pytest, pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

_ORIGINAL_ASYNCIO_RUN = asyncio.run

os.environ.setdefault("BOT_TOKEN", "1234567890:test_token_aaaaaaaaaaaaaaaaaaaaaaaaaaa")
os.environ.setdefault("ADMIN_SECRET_KEY", "test_secret_key_that_is_long_enough_32c")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/15")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/15")
os.environ.setdefault("TEMP_UPLOAD_DIR", "/tmp/mc_test/uploads")
os.environ.setdefault("TEMP_PROCESSED_DIR", "/tmp/mc_test/processed")
os.environ.setdefault("LOGS_DIR", "/tmp/mc_test/logs")
os.environ.setdefault("ADMIN_LOGIN_RATE_PER_MINUTE", "0")


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop(); yield loop; loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_session():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from core.database import Base
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def app_schema():
    from core.database import Base, engine

    async def up():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def down():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    _ORIGINAL_ASYNCIO_RUN(up())
    yield
    _ORIGINAL_ASYNCIO_RUN(down())
