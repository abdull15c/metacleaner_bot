import asyncio, logging
from pathlib import Path
from core.config import settings
from workers.celery_app import app

logger = logging.getLogger(__name__)


def _fmt(b):
    if b < 1024: return f"{b} B"
    elif b < 1048576: return f"{b/1024:.1f} KB"
    return f"{b/1048576:.1f} MB"


async def _send_doc(bot, chat_id, path, caption, retries=3):
    from aiogram.exceptions import TelegramRetryAfter, TelegramAPIError
    from aiogram.types import FSInputFile
    for attempt in range(retries):
        try:
            await bot.send_document(chat_id=chat_id, document=FSInputFile(path), caption=caption)
            return True
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except TelegramAPIError as e:
            s = str(e).lower()
            if "too big" in s or "chat not found" in s or "blocked" in s: return False
            await asyncio.sleep(2 ** attempt)
        except Exception:
            await asyncio.sleep(2 ** attempt)
    return False


async def _send_msg(bot, chat_id, text, retries=3):
    from aiogram.exceptions import TelegramRetryAfter, TelegramAPIError
    for attempt in range(retries):
        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML"); return True
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except TelegramAPIError as e:
            s = str(e).lower()
            if "chat not found" in s or "blocked" in s: return False
            await asyncio.sleep(2 ** attempt)
        except Exception:
            await asyncio.sleep(2 ** attempt)
    return False


@app.task(name="workers.sender.send_result_task", bind=True, max_retries=3, default_retry_delay=60, queue="video")
def send_result_task(self, job_uuid):
    async def _run():
        from core.database import get_db_session
        from core.services.job_service import JobService
        from core.models import JobStatus
        from aiogram import Bot
        async with get_db_session() as session:
            svc = JobService(session)
            job = await svc.get_by_uuid(job_uuid)
            if not job: return {"error":"not found"}
            if job.status == JobStatus.cancelled: return {"status":"cancelled"}
            if not job.temp_processed_path or not Path(job.temp_processed_path).exists():
                await svc.update_status(job, JobStatus.failed, "Processed file missing"); return {"error":"missing"}
            tg_id = job.user.telegram_id if job.user else None
            if not tg_id:
                await svc.update_status(job, JobStatus.failed, "No telegram_id")
                await session.commit()
                return {"error": "no tg_id"}
            try:
                began = await svc.try_begin_sending(job_uuid)
                if not began:
                    await session.commit()
                    job2 = await svc.get_by_uuid(job_uuid)
                    if job2 and job2.status in (JobStatus.sending, JobStatus.done):
                        return {"status": "duplicate_or_done"}
                    return {"status": "skipped"}
                await session.commit()
                job = await svc.get_by_uuid(job_uuid)
                if not job:
                    return {"error": "missing after lock"}
                bot = Bot(token=settings.bot_token)
                caption = (
                    f"✅ <b>Метаданные очищены!</b>\n\n"
                    f"📁 Исходный: {_fmt(job.original_size_bytes or 0)}\n"
                    f"📁 Итоговый: {_fmt(job.processed_size_bytes or 0)}\n"
                    f"🆔 Задача: <code>#{job.uuid[:8]}</code>"
                )
                ok = await _send_doc(bot, tg_id, job.temp_processed_path, caption)
                if ok:
                    await _send_msg(bot, tg_id, "🗑 Временные файлы удалены. Хорошего дня!")
                    await svc.update_status(job, JobStatus.done); await session.commit()
                    from workers.cleanup import cleanup_job_files_task
                    cleanup_job_files_task.delay(job_uuid)
                else:
                    await svc.update_status(job, JobStatus.failed, "Send failed"); await session.commit()
                    await _send_msg(bot, tg_id,
                        f"❌ Не удалось отправить файл.\nЗадача <code>#{job.uuid[:8]}</code> завершена с ошибкой.")
                    from workers.cleanup import cleanup_job_files_task
                    cleanup_job_files_task.delay(job_uuid)
                await bot.session.close()
                return {"status":"ok" if ok else "send_failed"}
            except Exception as e:
                logger.exception(f"Send error job {job_uuid}")
                try:
                    await svc.update_status(job, JobStatus.failed, str(e)[:200]); await session.commit()
                except: pass
                raise self.retry(exc=e)
    return asyncio.run(_run())


@app.task(name="workers.sender.notify_failure_task", queue="video")
def notify_failure_task(job_uuid):
    async def _run():
        from core.database import get_db_session
        from core.services.job_service import JobService
        from aiogram import Bot
        async with get_db_session() as session:
            svc = JobService(session)
            job = await svc.get_by_uuid(job_uuid)
            if not job or not job.user: return
            bot = Bot(token=settings.bot_token)
            await _send_msg(bot, job.user.telegram_id,
                f"❌ При обработке возникла ошибка.\n"
                f"Задача <code>#{job.uuid[:8]}</code> завершена с ошибкой.\n"
                f"Попробуйте ещё раз.")
            await bot.session.close()
    asyncio.run(_run())
