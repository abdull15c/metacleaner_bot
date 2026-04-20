import asyncio
import logging
import json
import subprocess
import uuid
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from core.platform_detect import detect_platform, validate_url_security
from core.database import get_db_session
from core.models import SiteDownloadJob, JobStatus, User
from bot.routers.youtube import handle_url as handle_youtube_url
from sqlalchemy import select, func

router = Router(name="download")
logger = logging.getLogger(__name__)

CONSENT_MSG = """
🔗 <b>Ссылка распознана.</b>

⚠️ <b>Политика использования:</b>
Этот режим предназначен ТОЛЬКО для:
• Ваших собственных материалов
• Видео с разрешения автора
• Материалов с открытой лицензией (CC)

Подтверждаете наличие прав?
""".strip()

def format_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="MP4 1080p", callback_data="dl_fmt:best_1080"),
            InlineKeyboardButton(text="MP4 720p", callback_data="dl_fmt:best_720")
        ],
        [
            InlineKeyboardButton(text="MP4 480p", callback_data="dl_fmt:best_480"),
            InlineKeyboardButton(text="MP3 320k", callback_data="dl_fmt:mp3_320")
        ]
    ])

def mode_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📥 Только скачать", callback_data="dl_mode:raw"),
            InlineKeyboardButton(text="🧹 Скачать + очистить", callback_data="dl_mode:clean")
        ]
    ])

def consent_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, подтверждаю", callback_data="dl_consent:yes")],
        [InlineKeyboardButton(text="Нет, отмена", callback_data="dl_consent:no")]
    ])


def _fetch_video_info(url: str, platform: str) -> dict:
    cmd = ["yt-dlp", "--dump-json", "--no-playlist", "--quiet", url]
    if platform == "youtube":
        cmd.extend(["--js-runtimes", "node", "--extractor-args", "youtube:player_client=web,default"])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "yt-dlp failed")
    return json.loads(result.stdout)

@router.message(F.text.startswith("/download"))
async def download_command(message: Message):
    await message.answer(
        "🔗 Отправьте ссылку на видео.\n\n"
        "Поддерживаю:\n"
        "▸ YouTube  ▸ TikTok  ▸ Instagram\n"
        "▸ Twitter/X  ▸ VK  ▸ Facebook\n\n"
        "Или просто отправьте ссылку в чат."
    )

# Since bot/routers/youtube.py might conflict, ensure handlers are coordinated in main.py order.
# We will catch all general links here assuming it's loaded appropriately.
@router.message(F.text.regexp(r"https?://"))
async def handle_any_url(message: Message, state: FSMContext, db_user: User):
    url = message.text.strip()
    
    # SECURITY: Валидация URL на SSRF и другие атаки
    is_valid, error_msg = validate_url_security(url)
    if not is_valid:
        await message.answer(f"❌ Недопустимый URL: {error_msg}")
        logger.warning(f"Blocked URL from user {db_user.telegram_id}: {error_msg}")
        return
    
    platform = detect_platform(url)
    
    if platform == "unknown":
        # Fallback or error
        await message.answer("❌ Платформа не поддерживается.")
        return

    if platform == "youtube":
        # Redirect to youtube router handler
        return await handle_youtube_url(message, state, db_user)

    # Prompt consent
    await state.set_state("download:waiting_for_consent")
    await state.update_data(dl_url=url, platform=platform)
    await message.answer(CONSENT_MSG, parse_mode="HTML", reply_markup=consent_keyboard())


@router.callback_query(F.data.startswith("dl_consent:"))
async def dl_consent_cb(callback: CallbackQuery, state: FSMContext):
    ans = callback.data.split(":")[1]
    if ans == "no":
        await state.clear()
        await callback.message.edit_text("Отменено.")
        return
        
    await callback.message.edit_text("⏳ Получаю информацию о видео...")
    data = await state.get_data()
    url = data.get("dl_url")
    platform = data.get("platform")
    
    try:
        info = await asyncio.to_thread(_fetch_video_info, url, platform)
        title = info.get("title", "Video")
        await state.update_data(dl_title=title)
        
        await state.set_state("download:waiting_for_format")
        await callback.message.edit_text(f"🎥 <b>{title[:100]}</b>\n\nВыберите формат:", parse_mode="HTML", reply_markup=format_keyboard())
    except Exception as e:
        logger.error(f"yt-dlp info error: {e}")
        await callback.message.edit_text("❌ Ошибка при получении информации о видео.")


@router.callback_query(F.data.startswith("dl_fmt:"))
async def dl_format_cb(callback: CallbackQuery, state: FSMContext):
    fmt = callback.data.split(":")[1]
    await state.update_data(dl_format=fmt)
    
    await state.set_state("download:waiting_for_mode")
    await callback.message.edit_text("Выберите режим обработки:", reply_markup=mode_keyboard())


@router.callback_query(F.data.startswith("dl_mode:"))
async def dl_mode_cb(callback: CallbackQuery, state: FSMContext, db_user: User):
    mode = callback.data.split(":")[1]
    clean = (mode == "clean")
    
    data = await state.get_data()
    url = data.get("dl_url")
    platform = data.get("platform")
    fmt = data.get("dl_format")
    title = data.get("dl_title")
    
    await state.clear()
    
    async with get_db_session() as session:
        # Separate limit for SiteDownloadJob
        today = datetime.utcnow().date()
        stmt = select(func.count(SiteDownloadJob.id)).where(
            SiteDownloadJob.telegram_id == db_user.telegram_id,
            SiteDownloadJob.created_at >= datetime(today.year, today.month, today.day)
        )
        count_r = await session.execute(stmt)
        today_count = count_r.scalar() or 0
        
        if today_count >= 5:
            await callback.message.edit_text("⚠️ Достигнут дневной лимит скачиваний (5/день).")
            return
            
        job_uuid = str(uuid.uuid4())
        job = SiteDownloadJob(
            uuid=job_uuid,
            telegram_id=db_user.telegram_id,
            platform=platform,
            source_url=url,
            format=fmt,
            clean_metadata=clean,
            original_title=title,
            status=JobStatus.pending
        )
        session.add(job)
        await session.commit()
        
        from workers.downloader_only import download_only_task
        task = download_only_task.delay(job_uuid)
        job.celery_task_id = task.id
        await session.commit()

    await callback.message.edit_text("⏳ Скачиваю... Это может занять несколько минут.\nРезультат придёт отдельным сообщением.")
