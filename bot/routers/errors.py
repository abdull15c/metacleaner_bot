import logging
from aiogram import Router
from aiogram.types import ErrorEvent

router = Router(name="errors")
logger = logging.getLogger(__name__)


@router.errors()
async def error_handler(event: ErrorEvent) -> bool:
    logger.exception(f"Unhandled exception: {event.exception}", exc_info=event.exception)
    msg = None
    if event.update.message: msg = event.update.message
    elif event.update.callback_query and event.update.callback_query.message:
        msg = event.update.callback_query.message
    if msg:
        try: await msg.answer("❌ Внутренняя ошибка. Попробуйте позже.")
        except: pass
    return True
