from aiogram.filters import BaseFilter
from aiogram.types import Message

from core.constants import SUPPORTED_VIDEO_EXTENSIONS

SUPPORTED_EXTENSIONS = SUPPORTED_VIDEO_EXTENSIONS


class VideoFileFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        if message.video: return True
        if message.document:
            name = message.document.file_name or ""
            ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
            return ext in SUPPORTED_EXTENSIONS
        return False


class UnsupportedFileFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return bool(message.document and not await VideoFileFilter()(message))
