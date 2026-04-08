import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from core.database import get_db_session
from core.models import JobStatus
from core.services.job_service import JobService
from core.services.user_service import UserService

router = Router(name="status")
logger = logging.getLogger(__name__)

EMOJI = {JobStatus.pending:"⏳",JobStatus.downloading:"📥",JobStatus.processing:"🔄",
         JobStatus.sending:"📤",JobStatus.done:"✅",JobStatus.failed:"❌",JobStatus.cancelled:"🚫"}
LABEL = {JobStatus.pending:"В очереди",JobStatus.downloading:"Скачивается",JobStatus.processing:"Обрабатывается",
         JobStatus.sending:"Отправляется",JobStatus.done:"Готово",JobStatus.failed:"Ошибка",JobStatus.cancelled:"Отменена"}


@router.message(Command("status"))
async def cmd_status(message: Message):
    async with get_db_session() as session:
        user = await UserService(session).get_by_telegram_id(message.from_user.id)
        if not user: await message.answer("У вас ещё нет задач."); return
        
        from sqlalchemy import select, func
        from core.models import Job
        r = await session.execute(
            select(func.count(Job.id), func.sum(Job.processed_size_bytes))
            .where(Job.user_id == user.id)
            .where(Job.status == JobStatus.done)
        )
        total_jobs_ever, total_bytes = r.fetchone()
        total_jobs_ever = total_jobs_ever or 0
        total_bytes = total_bytes or 0
        total_mb = total_bytes / (1024 * 1024)
        
        jobs = await JobService(session).get_user_jobs(user.id, limit=5)
        
        stats_msg = (
            f"📈 <b>Ваша статистика:</b>\n"
            f"Всего файлов обработано: <b>{total_jobs_ever}</b>\n"
            f"Сэкономлено места: <b>{total_mb:.2f} MB</b> (метаданные удалены)\n"
            f"Первое использование: <b>{user.created_at.strftime('%Y-%m-%d')}</b>\n\n"
        )
        
        if not jobs: await message.answer(f"{stats_msg}Задач пока нет. Отправьте видеофайл для начала.", parse_mode="HTML"); return
        
        lines = [f"{stats_msg}📋 <b>Ваши последние задачи:</b>\n"]
        for j in jobs:
            src = "YouTube" if j.source_type.value == "youtube" else "Файл"
            lines.append(f"{EMOJI.get(j.status,'❓')} <code>#{j.uuid[:8]}</code> — {LABEL.get(j.status,j.status.value)} [{src}]")
        await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message):
    async with get_db_session() as session:
        user = await UserService(session).get_by_telegram_id(message.from_user.id)
        if not user: await message.answer("У вас нет активных задач."); return
        js = JobService(session)
        job = await js.get_active_job_for_user(user.id)
        if not job: await message.answer("У вас нет активных задач."); return
        if job.status in (JobStatus.processing, JobStatus.sending):
            await message.answer(f"⚠️ Задача <code>#{job.uuid[:8]}</code> уже в процессе — отменить нельзя.", parse_mode="HTML"); return
        await js.cancel_job(job); await session.commit()
        if job.celery_task_id:
            try:
                from workers.celery_app import app as ca
                ca.control.revoke(job.celery_task_id, terminate=False)
            except Exception as e:
                logger.debug("Celery revoke failed for %s: %s", job.celery_task_id, e)
        from workers.cleanup import cleanup_job_files_task
        cleanup_job_files_task.delay(job.uuid)
        await message.answer(f"🚫 Задача <code>#{job.uuid[:8]}</code> отменена.", parse_mode="HTML")
