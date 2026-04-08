from typing import Optional

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

from core.config import settings


def webapp_upload_keyboard() -> Optional[ReplyKeyboardMarkup]:
    url = (settings.telegram_webapp_url or "").strip()
    if not url:
        return None
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="📤 Загрузить видео (Mini App)",
                    web_app=WebAppInfo(url=url),
                )
            ]
        ],
        resize_keyboard=True,
    )
