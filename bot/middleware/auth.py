import logging
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        tg = None
        if isinstance(event, Message) and event.from_user:
            tg = event.from_user
        elif isinstance(event, CallbackQuery) and event.from_user:
            tg = event.from_user
        if not tg:
            return await handler(event, data)
        from core.database import get_db_session
        from core.services.user_service import UserService
        from core.services.settings_service import SettingsService
        async with get_db_session() as session:
            maintenance = await SettingsService(session).get("maintenance_mode", False)
            user, _ = await UserService(session).get_or_create(
                telegram_id=tg.id, username=tg.username, first_name=tg.first_name)
            if user.is_banned:
                if isinstance(event, Message):
                    await event.answer("🚫 Вы заблокированы.")
                else:
                    await event.answer("🚫 Вы заблокированы.", show_alert=True)
                return
            if maintenance:
                if isinstance(event, Message):
                    if (event.text or "").strip() != "/start":
                        await event.answer("🛠 Бот на техническом обслуживании. Попробуйте позже.")
                        return
                else:
                    await event.answer("🛠 Бот на техническом обслуживании. Попробуйте позже.", show_alert=True)
                    return
            data["db_user"] = user
        return await handler(event, data)
