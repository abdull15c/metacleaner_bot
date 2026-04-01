from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

def youtube_consent_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да, у меня есть право", callback_data="yt_consent:yes"),
        InlineKeyboardButton(text="❌ Нет, отмена",           callback_data="yt_consent:no"),
    ]])
