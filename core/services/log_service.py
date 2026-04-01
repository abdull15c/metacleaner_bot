from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from core.models import LogLevel, SystemLog


class LogService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def write(self, level, module, message, context=None):
        self.session.add(SystemLog(level=level, module=module, message=message, context=context))

    async def info(self, module, message, **ctx): await self.write(LogLevel.INFO, module, message, ctx or None)
    async def warning(self, module, message, **ctx): await self.write(LogLevel.WARNING, module, message, ctx or None)
    async def error(self, module, message, **ctx): await self.write(LogLevel.ERROR, module, message, ctx or None)
    async def critical(self, module, message, **ctx): await self.write(LogLevel.CRITICAL, module, message, ctx or None)
