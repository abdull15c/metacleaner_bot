import asyncio
import logging
from pathlib import Path
from core.config import settings
from workers.celery_app import app

logger = logging.getLogger(__name__)


def _fmt(b):
    if b < 1024: return f"{b} B"
    elif b < 1048576: return f"{b/1024:.1f} KB"
    return f"{b/1048576:.1f} MB"


async def _send_doc(bot, chat_id, path, caption, retries=3, action="clean"):
    from aiogram.exceptions import TelegramRetryAfter, TelegramAPIError
    from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
    
    # Viral sharing button
    bot_username = (settings.telegram_bot_username or "").lstrip("@")
    kb = None
    if bot_username:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↗️ Поделиться ботом", switch_inline_query=f"check this bot @{bot_username}")]
        ])

    for attempt in range(retries):
        try:
            if action == "extract_audio":
                await bot.send_audio(chat_id=chat_id, audio=FSInputFile(path), caption=caption, reply_markup=kb)
            elif action == "screenshot":
                await bot.send_photo(chat_id=chat_id, photo=FSInputFile(path), caption=caption, reply_markup=kb)
            else:
                await bot.send_document(chat_id=chat_id, document=FSInputFile(path), caption=caption, reply_markup=kb)
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
                proc_path = Path(job.temp_processed_path)
                proc_size = proc_path.stat().st_size if proc_path.exists() else 0
                limit = settings.telegram_bot_max_send_document_bytes
                action = job.job_action.value if hasattr(job.job_action, "value") else str(job.job_action)
                
                labels = {
                    "clean": "✅ <b>Метаданные очищены!</b>",
                    "extract_audio": "🎵 <b>Аудио извлечено!</b>",
                    "screenshot": "🖼 <b>Скриншот готов!</b>"
                }
                
                caption = (
                    f"{labels.get(action, labels['clean'])}\n\n"
                    f"📁 Исходный: {_fmt(job.original_size_bytes or 0)}\n"
                    f"📁 Итоговый: {_fmt(job.processed_size_bytes or proc_size)}\n"
                    f"🆔 Задача: <code>#{job.uuid[:8]}</code>\n\n"
                    f"<i>Очищено с помощью @{(settings.telegram_bot_username or 'MetaCleanerBot').lstrip('@')}</i>"
                )
                ok = False
                if proc_size <= limit:
                    ok = await _send_doc(bot, tg_id, job.temp_processed_path, caption, action=action)
                    if ok:
                        await _send_msg(bot, tg_id, "🗑 Временные файлы удалены. Хорошего дня!")
                        await svc.update_status(job, JobStatus.done)
                        await session.commit()
                        from workers.cleanup import cleanup_job_files_task

                        cleanup_job_files_task.delay(job_uuid)
                    else:
                        await svc.update_status(job, JobStatus.failed, "Send failed")
                        await session.commit()
                        await _send_msg(
                            bot,
                            tg_id,
                            f"❌ Не удалось отправить файл.\nЗадача <code>#{job.uuid[:8]}</code> завершена с ошибкой.",
                        )
                        from workers.cleanup import cleanup_job_files_task

                        cleanup_job_files_task.delay(job_uuid)
                else:
                    base = settings.public_download_base_url
                    if base:
                        from urllib.parse import quote
                        from webapp.result_token import create_result_download_token

                        token = create_result_download_token(job.uuid, tg_id)
                        link = f"{base}/api/webapp/result/{job.uuid}?t={quote(token)}"
                        msg = (
                            f"✅ <b>Метаданные очищены.</b>\n"
                            f"Файл <b>{_fmt(proc_size)}</b> больше лимита отправки бота (~{settings.telegram_bot_max_send_document_mb} МБ).\n\n"
                            f"<a href=\"{link}\">⬇️ Скачать результат</a>\n\n"
                            f"Ссылка действительна несколько дней. Задача <code>#{job.uuid[:8]}</code>\n"
                            f"Либо откройте Mini App — там тоже можно скачать файл."
                        )
                        await _send_msg(bot, tg_id, msg)
                    else:
                        await _send_msg(
                            bot,
                            tg_id,
                            f"✅ <b>Готово.</b> Файл {_fmt(proc_size)} слишком большой для отправки в чат.\n"
                            f"Укажите <code>PUBLIC_BASE_URL</code> или <code>TELEGRAM_WEBAPP_URL</code> в настройках сервера "
                            f"и откройте Mini App для скачивания.\nЗадача <code>#{job.uuid[:8]}</code>",
                        )
                    await svc.update_status(job, JobStatus.done)
                    await session.commit()
                    ok = True
                await bot.session.close()
                return {"status": "ok" if ok else "send_failed"}
            except Exception as e:
                logger.exception(f"Send error job {job_uuid}")
                try:
                    await svc.update_status(job, JobStatus.failed, str(e)[:200]); await session.commit()
                except Exception as update_error:
                    # SECURITY FIX: Логирование вместо молчаливого игнорирования
                    logger.error(f"Failed to update job status after send error: {update_error}", exc_info=True)
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
