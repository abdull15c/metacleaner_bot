import asyncio, logging, logging.config
from pathlib import Path
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from core.config import settings
from core.database import init_db
from bot.middleware.anti_flood import AntiFloodMiddleware
from bot.middleware.auth import AuthMiddleware
from bot.routers import errors, start, status, upload, youtube

log = logging.getLogger(__name__)


async def _storage_and_redis():
    if not settings.bot_redis_enabled:
        return MemoryStorage(), None
    try:
        from redis.asyncio import Redis
        from aiogram.fsm.storage.redis import RedisStorage

        r = Redis.from_url(settings.redis_url)
        await r.ping()
        return RedisStorage(redis=r), r
    except Exception as e:
        log.warning("Redis недоступен для бота (%s); FSM и антифлуд в памяти процесса.", e)
        return MemoryStorage(), None


def setup_logging():
    cfg = Path("config/logging.yaml")
    if cfg.exists():
        import yaml
        logging.config.dictConfig(yaml.safe_load(cfg.read_text()))
    else:
        logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO),
                            format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s")


async def on_startup(bot: Bot):
    settings.ensure_dirs()
    await init_db()
    from core.database import get_db_session
    from core.services.settings_service import SettingsService
    async with get_db_session() as session:
        await SettingsService(session).seed_defaults(); await session.commit()
    info = await bot.get_me()
    log.info("Bot started: @%s", info.username)


async def main():
    setup_logging()
    storage, redis_client = await _storage_and_redis()
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=storage)

    async def on_shutdown(bot: Bot):
        log.info("Bot shutting down")
        try:
            await dp.storage.close()
        except Exception:
            pass
        await bot.session.close()

    dp.message.middleware(
        AntiFloodMiddleware(cooldown_seconds=settings.user_cooldown_seconds, redis=redis_client),
    )
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    dp.include_router(errors.router)
    dp.include_router(start.router)
    dp.include_router(status.router)
    dp.include_router(youtube.router)
    dp.include_router(upload.router)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    await dp.start_polling(bot, allowed_updates=["message","callback_query"], drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
