import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from redis.asyncio import Redis
from sqlalchemy import select

from core.database import get_db_session
from core.models import SponsorChannel, User
from core.config import settings

logger = logging.getLogger(__name__)

class ForceSubMiddleware(BaseMiddleware):
    def __init__(self, redis: Optional[Redis] = None):
        self.redis = redis
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, (Message, CallbackQuery)):
            return await handler(event, data)

        user: Optional[User] = data.get("db_user")
        if not user:
            return await handler(event, data)

        # 1. Check if enabled in Redis (fast path)
        force_sub_enabled = "false"
        if self.redis:
            val = await self.redis.get("settings:force_sub:enabled")
            if val:
                force_sub_enabled = val.decode() if isinstance(val, bytes) else str(val)
        
        if force_sub_enabled != "true":
            return await handler(event, data)

        # 2. Check Cache
        user_id = event.from_user.id
        cache_key = f"user_sub_verified:{user_id}"
        if self.redis:
            if await self.redis.get(cache_key):
                return await handler(event, data)

        # 3. Check Subscriptions
        async with get_db_session() as session:
            stmt = select(SponsorChannel).where(SponsorChannel.is_active == True)
            res = await session.execute(stmt)
            channels = res.scalars().all()

        if not channels:
            return await handler(event, data)

        bot: Bot = data["bot"]
        not_subscribed = []

        for ch in channels:
            try:
                member = await bot.get_chat_member(chat_id=ch.channel_id, user_id=user_id)
                if member.status in ["left", "kicked"]:
                    not_subscribed.append(ch)
            except Exception as e:
                logger.warning(f"Failed to check sub for channel {ch.channel_id}: {e}")
                # If error (bot not admin), assume subscribed to not block user
                continue

        if not not_subscribed:
            # All good, cache for 10 min
            if self.redis:
                await self.redis.set(cache_key, "1", ex=600)
            return await handler(event, data)

        # 4. Block and show UI
        kb_list = []
        for ch in not_subscribed:
            kb_list.append([InlineKeyboardButton(text=f"📢 {ch.name}", url=ch.url)])
        
        kb_list.append([InlineKeyboardButton(text="🔄 Я подписался!", callback_data="check_subs")])
        
        msg_text = "⚠️ <b>Для использования бота необходимо подписаться на наши каналы:</b>"
        
        if isinstance(event, Message):
            await event.answer(msg_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))
        else:
            await event.message.answer(msg_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))
            await event.answer()
        
        return
