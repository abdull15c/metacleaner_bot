import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

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
async def cmd_start(message: Message):
    await message.answer(WELCOME, parse_mode="HTML")

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP, parse_mode="HTML")
