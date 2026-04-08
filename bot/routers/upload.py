import logging, uuid
from pathlib import Path
from aiogram import Bot, Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from bot.filters.file_type import VideoFileFilter, UnsupportedFileFilter
from core.config import settings
from core.database import get_db_session
from core.models import JobStatus, SourceType, User
from core.services.job_service import JobService
from core.services.settings_service import SettingsService
from core.services.user_service import UserService

router = Router(name="upload")
logger = logging.getLogger(__name__)


@router.message(VideoFileFilter())
async def handle_video(message: Message, bot: Bot, db_user: User):
    tg = message.from_user
    async with get_db_session() as session:
        ss = SettingsService(session)
        if not await ss.get("processing_enabled", True):
            await message.answer("⚠️ Обработка временно приостановлена. Попробуйте позже."); return
        max_mb = int(await ss.get("max_file_size_mb", settings.max_file_size_mb))
        max_daily = int(await ss.get("max_daily_jobs_per_user", settings.max_daily_jobs_per_user))
        max_bytes = max_mb * 1024 * 1024
        us = UserService(session)
        user = await session.get(User, db_user.id)
        if not user:
            user, _ = await us.get_or_create(telegram_id=tg.id, username=tg.username, first_name=tg.first_name)
        
        if message.document:
            fid = message.document.file_id
            fname = message.document.file_name or "video.mp4"
            fsize = message.document.file_size or 0
        else:
            fid = message.video.file_id
            fname = f"video_{message.video.file_unique_id}.mp4"
            fsize = message.video.file_size or 0
            
        if fsize > max_bytes:
            await message.answer(
                f"❌ Файл слишком большой.\nМаксимум: <b>{max_mb} МБ</b>\n"
                f"Ваш файл: <b>{fsize/(1024*1024):.1f} МБ</b>", parse_mode="HTML"); return
        js = JobService(session)
        active = await js.get_active_job_for_user(user.id)
        if active:
            await message.answer(
                f"⏳ У вас уже обрабатывается задача <code>#{active.uuid[:8]}</code>.\n"
                f"Дождитесь завершения или введите /cancel.", parse_mode="HTML"); return
        if not await us.increment_daily_count(user, max_daily):
            await message.answer(f"⚠️ Дневной лимит задач исчерпан (<b>{max_daily}</b>/день).\nПопробуйте завтра.", parse_mode="HTML"); return
        
        job = await js.create_job(user_id=user.id, source_type=SourceType.upload, original_filename=fname)
        # Store file_id in job metadata or temporary storage if needed, but here we can just pass it via callback
        await session.commit()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🧹 Удалить метаданные", callback_data=f"confirm_action:{job.uuid}:clean:{fid}"),
            InlineKeyboardButton(text="🎵 Извлечь аудио", callback_data=f"confirm_action:{job.uuid}:extract_audio:{fid}")
        ],
        [
            InlineKeyboardButton(text="🖼 Скриншот", callback_data=f"confirm_action:{job.uuid}:screenshot:{fid}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancel_job:{job.uuid}")
        ]
    ])
    
    await message.answer(
        f"📋 Задача <code>#{job.uuid[:8]}</code>\nФайл: <b>{fname}</b>\n\nЧто необходимо сделать?",
        parse_mode="HTML",
        reply_markup=kb
    )

@router.callback_query(F.data.startswith("confirm_action:"))
async def confirm_action_cb(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split(":")
    job_uuid = parts[1]
    action_str = parts[2]
    fid = parts[3]
    
    await callback.message.edit_text(
        f"⏳ <b>Ставлю в очередь...</b>\n📋 Задача <code>#{job_uuid[:8]}</code>",
        parse_mode="HTML"
    )
    
    try:
        settings.temp_upload_dir.mkdir(parents=True, exist_ok=True)
        # We need the filename from the job
        async with get_db_session() as session:
            from core.models import JobAction
            js = JobService(session)
            job = await js.get_by_uuid(job_uuid)
            job.job_action = JobAction(action_str)
            fname = job.original_filename or "video.mp4"
            await session.commit()
            
        ext = "." + fname.rsplit(".", 1)[-1].lower() if "." in fname else ".mp4"
        local = settings.temp_upload_dir / f"{uuid.uuid4()}{ext}"
        
        await callback.message.edit_text(
            f"🔄 <b>Скачиваю видео...</b>\n📋 Задача <code>#{job_uuid[:8]}</code>",
            parse_mode="HTML"
        )
        
        tg_file = await bot.get_file(fid)
        await bot.download_file(tg_file.file_path, destination=str(local))
        
        async with get_db_session() as session:
            js2 = JobService(session)
            job2 = await js2.get_by_uuid(job_uuid)
            await js2.set_file_paths(job2, str(local), local.stat().st_size)
            await session.commit()
            
        from workers.video_processor import process_video_task
        task = process_video_task.delay(job_uuid)
        
        async with get_db_session() as session:
            js2 = JobService(session)
            job2 = await js2.get_by_uuid(job_uuid)
            await js2.set_celery_task_id(job2, task.id)
            await session.commit()
            
        await callback.message.edit_text(
            f"🔄 <b>Очищаю метаданные...</b>\n📋 Задача <code>#{job_uuid[:8]}</code>",
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Upload flow failed: {e}")
        async with get_db_session() as session:
            js2 = JobService(session)
            job2 = await js2.get_by_uuid(job_uuid)
            if job2:
                await js2.update_status(job2, JobStatus.failed, str(e)[:200])
            await session.commit()
        await callback.message.edit_text(f"❌ Ошибка: {e}")

@router.callback_query(F.data.startswith("cancel_job:"))
async def cancel_job_cb(callback: CallbackQuery):
    job_uuid = callback.data.split(":")[1]
    async with get_db_session() as session:
        js = JobService(session)
        job = await js.get_by_uuid(job_uuid)
        if job:
            await js.update_status(job, JobStatus.cancelled, "Cancelled by user")
            await session.commit()
    await callback.message.edit_text("❌ Задача отменена.")

@router.message(UnsupportedFileFilter())
async def handle_unsupported(message: Message):
    name = message.document.file_name or ""
    ext = ("." + name.rsplit(".", 1)[-1].upper()) if "." in name else ""
    await message.answer(
        f"❌ Формат <b>{ext or 'файла'}</b> не поддерживается.\n\n"
        f"<b>Поддерживаемые:</b> MP4, MKV, MOV, AVI, WebM, M4V, FLV, TS, WMV, 3GP\n\n"
        f"Отправьте видео <i>как документ</i> (не сжимая).", parse_mode="HTML")
