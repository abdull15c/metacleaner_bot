import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from pathlib import Path

from bot.keyboards.main_menu import webapp_upload_keyboard, get_main_menu_button
from aiogram import Bot
from aiogram.types import FSInputFile

router = Router(name="start")
logger = logging.getLogger(__name__)

WELCOME = """
👋 <b>Привет! Я MetaCleaner Bot.</b>

Убираю метаданные из видеофайлов без изменения качества.

<b>Что я делаю:</b>
✅ Удаляю title, GPS, дату записи и другие теги
✅ Не перекодирую видео — только чищу заголовки файла
✅ Автоматически удаляю файлы после отправки

<b>Как использовать:</b>
📎 Отправь видео <i>как документ</i> (не сжимая)
📤 Или кнопку <b>«Загрузить видео (Mini App)»</b> — если включено на сервере
🔗 Или ссылку на своё YouTube-видео

/status — ваши задачи
/help — помощь
""".strip()

HELP = """
📖 <b>Помощь</b>

<b>Форматы:</b> MP4, MKV, MOV, AVI, WebM, M4V, FLV, TS, WMV, 3GP
<b>Макс. размер:</b> 500 МБ
<b>Лимит:</b> 10 задач в сутки, 1 активная задача одновременно

/status — последние задачи
/cancel — отменить текущую задачу
""".strip()


@router.message(Command("start"))
async def cmd_start(message: Message, bot: Bot):
    # Set WebApp Menu Button
    await bot.set_chat_menu_button(
        chat_id=message.chat.id,
        menu_button=get_main_menu_button()
    )
    
    kb = webapp_upload_keyboard()
    
    # Try to send onboarding banner if exists
    banner_path = Path("static/banner.png")
    if banner_path.exists():
        await message.answer_photo(
            photo=FSInputFile(str(banner_path)),
            caption=WELCOME,
            parse_mode="HTML",
            reply_markup=kb
        )
    else:
        await message.answer(WELCOME, parse_mode="HTML", reply_markup=kb)

@router.message(F.text == "🧹 Очистить видео")
async def msg_clean_hint(message: Message):
    await message.answer("📎 <b>Отправьте видео файлом</b> (без сжатия), чтобы я очистил его от метаданных.")

@router.message(F.text == "📊 Моя статистика")
async def msg_stats(message: Message):
    from core.database import get_db_session
    from core.services.user_service import UserService
    async with get_db_session() as session:
        us = UserService(session)
        user, _ = await us.get_or_create(message.from_user.id)
        # Assuming we might want to add more stats later
        await message.answer(
            f"📊 <b>Ваша статистика:</b>\n\n"
            f"Задач за сегодня: <b>{user.daily_job_count}</b>\n"
            f"Дата регистрации: <b>{user.created_at.strftime('%d.%m.%Y')}</b>",
            parse_mode="HTML"
        )

@router.message(F.text == "❓ Помощь")
async def msg_help_btn(message: Message):
    await message.answer(HELP, parse_mode="HTML")

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP, parse_mode="HTML")

@router.message(Command("delete_me"))
async def cmd_delete_me(message: Message):
    from core.database import get_db_session
    from core.services.user_service import UserService
    async with get_db_session() as session:
        us = UserService(session)
        success = await us.delete_me(message.from_user.id)
        await session.commit()
    
    if success:
        await message.answer("✅ Ваш аккаунт и все связанные данные успешно удалены из базы.", parse_mode="HTML")
    else:
        await message.answer("❌ Аккаунт не найден.", parse_mode="HTML")
