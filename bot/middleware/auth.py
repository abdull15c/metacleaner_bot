import logging
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if not isinstance(event, Message) or not event.from_user:
            return await handler(event, data)
        from core.database import get_db_session
        from core.services.user_service import UserService
        from core.services.settings_service import SettingsService
        tg = event.from_user
        async with get_db_session() as session:
            maintenance = await SettingsService(session).get("maintenance_mode", False)
            user, _ = await UserService(session).get_or_create(
                telegram_id=tg.id, username=tg.username, first_name=tg.first_name)
            if user.is_banned:
                await event.answer("🚫 Вы заблокированы."); return
            if maintenance and (event.text or "").strip() != "/start":
                await event.answer("🛠 Бот на техническом обслуживании. Попробуйте позже."); return
            data["db_user"] = user
        return await handler(event, data)
