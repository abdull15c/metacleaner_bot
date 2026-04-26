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
from bot.middleware.force_sub import ForceSubMiddleware
from bot.routers import errors, start, status, upload, youtube, download

log = logging.getLogger(__name__)
_startup_lock = asyncio.Lock()
_startup_done = False
_dispatcher_lock = asyncio.Lock()
_dispatcher_ready = False
_redis_client = None


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


async def ensure_startup(bot: Bot):
    global _startup_done
    if _startup_done:
        return
    async with _startup_lock:
        if _startup_done:
            return
        await on_startup(bot)
        _startup_done = True


async def on_shutdown(bot: Bot):
    log.info("Bot shutting down")
    try:
        await dp.storage.close()
    except Exception:
        pass
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.close()
        except Exception:
            pass
        _redis_client = None
    await bot.session.close()


async def configure_dispatcher():
    global _dispatcher_ready
    if _dispatcher_ready:
        return
    async with _dispatcher_lock:
        if _dispatcher_ready:
            return
        global _redis_client
        storage, _redis_client = await _storage_and_redis()
        dp.storage = storage
        dp.message.middleware(
            AntiFloodMiddleware(cooldown_seconds=settings.user_cooldown_seconds, redis=_redis_client),
        )
        dp.message.middleware(AuthMiddleware())
        dp.callback_query.middleware(AuthMiddleware())
        dp.message.middleware(ForceSubMiddleware(redis=_redis_client))
        dp.callback_query.middleware(ForceSubMiddleware(redis=_redis_client))
        _dispatcher_ready = True


async def ensure_runtime(bot: Bot):
    await configure_dispatcher()
    await ensure_startup(bot)


async def main():
    setup_logging()
    await ensure_runtime(bot)
    if settings.telegram_webhook_url:
        if not settings.telegram_webhook_secret:
            raise RuntimeError("TELEGRAM_WEBHOOK_SECRET is required when TELEGRAM_WEBHOOK_URL is configured")
        log.info(f"Setting webhook to {settings.telegram_webhook_url}")
        await bot.set_webhook(
            url=settings.telegram_webhook_url,
            secret_token=settings.telegram_webhook_secret,
            allowed_updates=["message","callback_query"],
            drop_pending_updates=True
        )
        log.info("Webhook mode enabled. The bot will receive updates via FastAPI.")
        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        finally:
            await on_shutdown(bot)
    else:
        log.info("Starting long polling mode")
        try:
            await dp.start_polling(bot, allowed_updates=["message","callback_query"], drop_pending_updates=True)
        finally:
            await on_shutdown(bot)


bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
dp.include_router(errors.router)
dp.include_router(start.router)
dp.include_router(status.router)
dp.include_router(download.router)
dp.include_router(youtube.router)
dp.include_router(upload.router)

if __name__ == "__main__":
    asyncio.run(main())
