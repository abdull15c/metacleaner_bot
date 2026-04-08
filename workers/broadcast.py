import asyncio, logging
from core.config import settings
from workers.celery_app import app

logger = logging.getLogger(__name__)


@app.task(name="workers.broadcast.send_broadcast_chunk_task", queue="broadcast", max_retries=0)
def send_broadcast_chunk_task(broadcast_id):
    async def _run():
        from datetime import datetime, timezone
        from sqlalchemy import and_, select
        from sqlalchemy.orm import selectinload
        from core.database import get_db_session
        from core.models import Broadcast, BroadcastRecipient, BroadcastStatus, RecipientStatus
        from aiogram import Bot
        from aiogram.exceptions import TelegramRetryAfter, TelegramAPIError
        from core.telegram_html import sanitize_broadcast_html

        bot = Bot(token=settings.bot_token)
        async with get_db_session() as session:
            r = await session.execute(select(Broadcast).where(Broadcast.id == broadcast_id))
            bc = r.scalar_one_or_none()
            if not bc or bc.status != BroadcastStatus.running:
                await bot.session.close(); return {"status":"skipped"}
            rr = await session.execute(
                select(BroadcastRecipient)
                .where(and_(BroadcastRecipient.broadcast_id == broadcast_id,
                            BroadcastRecipient.status == RecipientStatus.pending))
                .limit(50))
            recipients = list(rr.scalars().all())
            if not recipients:
                bc.status = BroadcastStatus.done
                bc.completed_at = datetime.now(timezone.utc)
                await session.commit(); await bot.session.close()
                return {"status":"done"}

        sent = failed = 0
        for rec in recipients:
            async with get_db_session() as session:
                r = await session.execute(select(Broadcast).where(Broadcast.id == broadcast_id))
                bc = r.scalar_one_or_none()
                if not bc or bc.status != BroadcastStatus.running: break
                rr = await session.execute(
                    select(BroadcastRecipient).where(BroadcastRecipient.id == rec.id)
                    .options(selectinload(BroadcastRecipient.user)))
                rec_full = rr.scalar_one_or_none()
                if not rec_full or not rec_full.user:
                    failed += 1
                    bc.failed_count += 1
                    rec_full.status = RecipientStatus.failed
                    rec_full.error = "User not found"
                    await session.commit()
                    continue
                tg_id = rec_full.user.telegram_id
                text = sanitize_broadcast_html(bc.message_text or "")
            ok = False
            err = None
            if not (text or "").strip():
                err = "empty message"
            else:
                for attempt in range(3):
                    try:
                        await bot.send_message(chat_id=tg_id, text=text, parse_mode="HTML")
                        ok = True
                        break
                    except TelegramRetryAfter as e:
                        await asyncio.sleep(e.retry_after + 1)
                    except TelegramAPIError as e:
                        s = str(e).lower()
                        if "blocked" in s or "chat not found" in s:
                            err = str(e)[:200]
                            break
                        err = str(e)[:200]
                        await asyncio.sleep(2 ** attempt)
                    except Exception as e:
                        err = str(e)[:200]
                        await asyncio.sleep(2 ** attempt)
            async with get_db_session() as session:
                r = await session.execute(select(BroadcastRecipient).where(BroadcastRecipient.id == rec.id))
                r2 = await session.execute(select(Broadcast).where(Broadcast.id == broadcast_id))
                ro = r.scalar_one_or_none(); bo = r2.scalar_one_or_none()
                if ro and bo:
                    if ok: ro.status = RecipientStatus.sent; ro.sent_at = datetime.now(timezone.utc); bo.sent_count += 1; sent += 1
                    else: ro.status = RecipientStatus.failed; ro.error = err; bo.failed_count += 1; failed += 1
                    await session.commit()
            await asyncio.sleep(settings.broadcast_delay_seconds)

        async with get_db_session() as session:
            r = await session.execute(select(Broadcast).where(Broadcast.id == broadcast_id))
            bo = r.scalar_one_or_none()
            if bo and bo.status == BroadcastStatus.running:
                rr = await session.execute(
                    select(BroadcastRecipient).where(and_(
                        BroadcastRecipient.broadcast_id == broadcast_id,
                        BroadcastRecipient.status == RecipientStatus.pending)).limit(1))
                if rr.scalar_one_or_none():
                    send_broadcast_chunk_task.apply_async(args=[broadcast_id], countdown=1, queue="broadcast")
        await bot.session.close()
        return {"sent": sent, "failed": failed}
    return asyncio.run(_run())
