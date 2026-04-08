from typing import Optional
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo, MenuButtonWebApp, LoginUrl

from core.config import settings

def webapp_upload_keyboard() -> ReplyKeyboardMarkup:
    url = (settings.telegram_webapp_url or "").strip()
    # Add main buttons
    buttons = [
        [KeyboardButton(text="🧹 Очистить видео"), KeyboardButton(text="📊 Моя статистика")],
        [KeyboardButton(text="❓ Помощь")]
    ]
    
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        persistent=True
    )

def get_main_menu_button() -> MenuButtonWebApp:
    url = (settings.telegram_webapp_url or "").strip()
    return MenuButtonWebApp(
        text="🎬 Загрузить > 50MB",
        web_app=WebAppInfo(url=url)
    )
