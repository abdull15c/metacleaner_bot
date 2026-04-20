import logging, re
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from bot.keyboards.youtube_consent import youtube_consent_keyboard
from bot.states.youtube import YouTubeConsentStates
from core.config import settings
from core.database import get_db_session
from core.models import JobStatus, SourceType, User
from core.services.job_service import JobService
from core.services.log_service import LogService
from core.services.settings_service import SettingsService
from core.services.user_service import UserService
from core.platform_detect import validate_url_security

router = Router(name="youtube")
logger = logging.getLogger(__name__)
YT_RE = re.compile(r"(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)[\w\-]{11}", re.I)

CONSENT = """
🔗 <b>Вижу YouTube-ссылку.</b>

⚠️ <b>Этот режим ТОЛЬКО для:</b>
• Ваших собственных видео
• Видео с разрешения автора
• Материалов с открытой лицензией (CC)

<b>Подтвердите наличие права на использование:</b>
""".strip()


# Disabled the regex matcher since it is moved to download.py

# @router.message(F.text.regexp(r"https?://").as_("url"))
async def handle_url(message: Message, state: FSMContext, db_user: User):
    # This handler is now called from download.py if platform is youtube
    text = message.text or ""
    
    # SECURITY: Валидация URL на SSRF
    is_valid, error_msg = validate_url_security(text)
    if not is_valid:
        await message.answer(f"❌ Недопустимый URL: {error_msg}")
        logger.warning(f"Blocked YouTube URL from user {db_user.telegram_id}: {error_msg}")
        return
    
    async with get_db_session() as session:
        ss = SettingsService(session)
        if not await ss.get("youtube_enabled", True):
            await message.answer("⚠️ YouTube-режим временно отключён."); return
        if not await ss.get("processing_enabled", True):
            await message.answer("⚠️ Обработка приостановлена. Попробуйте позже."); return
        us = UserService(session)
        user = await session.get(User, db_user.id)
        if not user:
            user, _ = await us.get_or_create(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
            )
        active = await JobService(session).get_active_job_for_user(user.id)
        if active:
            await message.answer(f"⏳ У вас уже обрабатывается задача <code>#{active.uuid[:8]}</code>.\n/cancel для отмены.", parse_mode="HTML"); return
    await state.set_state(YouTubeConsentStates.waiting_for_consent)
    await state.update_data(youtube_url=text)
    await message.answer(CONSENT, parse_mode="HTML", reply_markup=youtube_consent_keyboard())


@router.callback_query(YouTubeConsentStates.waiting_for_consent, F.data == "yt_consent:yes")
async def consent_yes(callback: CallbackQuery, state: FSMContext, db_user: User):
    data = await state.get_data(); url = data.get("youtube_url", "")
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    tg = callback.from_user
    
    # SECURITY FIX: Не логировать полный URL (может содержать токены)
    from urllib.parse import urlparse
    parsed_url = urlparse(url)
    safe_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
    logger.info(f"YouTube consent GRANTED user={tg.id} domain={parsed_url.netloc}")
    
    async with get_db_session() as session:
        await LogService(session).info("youtube", "Consent granted", user_id=tg.id, url=safe_url)
        ss = SettingsService(session); us = UserService(session); js = JobService(session)
        max_daily = int(await ss.get("max_daily_jobs_per_user", settings.max_daily_jobs_per_user))
        user = await session.get(User, db_user.id)
        if not user:
            user, _ = await us.get_or_create(telegram_id=tg.id, username=tg.username, first_name=tg.first_name)
        
        # SECURITY FIX: Проверка глобального лимита MAX_CONCURRENT_JOBS
        max_concurrent = int(await ss.get("max_concurrent_jobs", settings.max_concurrent_jobs))
        current_active = await js.count_active_jobs()
        
        if current_active >= max_concurrent:
            await callback.message.answer(
                f"⏳ Система перегружена. Активных задач: {current_active}/{max_concurrent}\n"
                f"Попробуйте через несколько минут.", parse_mode="HTML"
            )
            await callback.answer()
            return
        
        if not await us.increment_daily_count(user, max_daily):
            await callback.message.answer(
                f"⚠️ Дневной лимит задач исчерпан (<b>{max_daily}</b>/день).", parse_mode="HTML")
            await callback.answer()
            return
        
        job = await js.create_job(user_id=user.id, source_type=SourceType.youtube, source_url=url)
        await js.set_youtube_consent(job, True); await session.commit()
    status_msg = await callback.message.answer(
        f"✅ <b>Право подтверждено.</b>\n📋 Задача <code>#{job.uuid[:8]}</code>\n\n📥 Скачиваю...", parse_mode="HTML")
    try:
        from workers.downloader import download_youtube_task
        task = download_youtube_task.delay(job.uuid)
        async with get_db_session() as session:
            js2 = JobService(session); job2 = await js2.get_by_uuid(job.uuid)
            await js2.set_celery_task_id(job2, task.id); await session.commit()
        import redis.asyncio as aioredis
        r = aioredis.from_url(str(settings.redis_url))
        queue_len = await r.scard("active_processing_jobs")
        await r.close()
        queue_str = f" Задач перед вами: {queue_len}." if queue_len > 0 else ""
        
        await status_msg.edit_text(
            f"✅ <b>Право подтверждено.</b>\n📋 Задача <code>#{job.uuid[:8]}</code>\n\n"
            f"🔄 В очереди на скачивание и обработку.{queue_str}", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Celery dispatch failed: {e}")
        async with get_db_session() as session:
            js2 = JobService(session)
            us = UserService(session)
            job2 = await js2.get_by_uuid(job.uuid)
            if job2:
                await js2.update_status(job2, JobStatus.failed, f"Queue dispatch failed: {e}")
                u = await us.get_by_id(job2.user_id)
                if u:
                    await us.rollback_daily_job_increment(u)
            await session.commit()
        await status_msg.edit_text(
            "❌ Не удалось поставить задачу в очередь. Попробуйте позже.\n"
            "Проверьте /status — слот дня возвращён.",
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(YouTubeConsentStates.waiting_for_consent, F.data == "yt_consent:no")
async def consent_no(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Понял. Скачайте видео и отправьте мне файлом 📎")
    await callback.answer()
