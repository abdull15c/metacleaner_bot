"""Общие константы бота и воркеров."""

# Расширения видео: бот (фильтр) и FFmpeg-обработка должны совпадать.
SUPPORTED_VIDEO_EXTENSIONS = frozenset(
    {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".flv", ".ts", ".wmv", ".3gp"}
)
