"""
Валидация MIME-типов загружаемых файлов.
"""
import logging
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

# Разрешенные MIME-типы для видео
ALLOWED_VIDEO_MIME_TYPES = {
    'video/mp4',
    'video/x-matroska',  # mkv
    'video/quicktime',   # mov
    'video/x-msvideo',   # avi
    'video/webm',
    'video/x-m4v',       # m4v
    'video/x-flv',       # flv
    'video/mp2t',        # ts
    'video/x-ms-wmv',    # wmv
    'video/3gpp',        # 3gp
}

# Соответствие расширений и MIME-типов
EXTENSION_TO_MIME = {
    '.mp4': 'video/mp4',
    '.mkv': 'video/x-matroska',
    '.mov': 'video/quicktime',
    '.avi': 'video/x-msvideo',
    '.webm': 'video/webm',
    '.m4v': 'video/x-m4v',
    '.flv': 'video/x-flv',
    '.ts': 'video/mp2t',
    '.wmv': 'video/x-ms-wmv',
    '.3gp': 'video/3gpp',
}


def validate_video_file_mime(file_path: Path) -> Tuple[bool, str]:
    """
    Проверка MIME-типа файла по magic bytes.
    
    Args:
        file_path: Путь к файлу для проверки
    
    Returns:
        (is_valid, error_message)
    """
    if not file_path or not file_path.exists():
        return False, "File does not exist"
    
    if not file_path.is_file():
        return False, "Not a file"
    
    try:
        # Попытка использовать python-magic
        try:
            import magic
            mime = magic.from_file(str(file_path), mime=True)
        except ImportError:
            logger.error("python-magic is not installed; MIME validation cannot verify uploaded files safely")
            return False, "MIME validation unavailable on server"
        
        # Проверка MIME-типа
        if mime not in ALLOWED_VIDEO_MIME_TYPES:
            return False, f"Invalid MIME type: {mime}"
        
        return True, "OK"
        
    except Exception as e:
        logger.error(f"MIME validation error for {file_path}: {e}", exc_info=True)
        return False, f"Validation error: {str(e)}"


def get_safe_extension(file_path: Path) -> str:
    """
    Получить безопасное расширение файла на основе MIME-типа.
    
    Args:
        file_path: Путь к файлу
    
    Returns:
        Расширение файла (например, '.mp4')
    """
    try:
        import magic
        mime = magic.from_file(str(file_path), mime=True)
        
        # Найти расширение по MIME-типу
        for ext, mime_type in EXTENSION_TO_MIME.items():
            if mime_type == mime:
                return ext
        
        # Если не найдено, вернуть оригинальное расширение
        return file_path.suffix.lower() or '.mp4'
        
    except ImportError:
        logger.warning("python-magic is not installed; using original extension as fallback")
        return file_path.suffix.lower() or '.mp4'
    except Exception as e:
        logger.error(f"Failed to get safe extension for {file_path}: {e}")
        return '.mp4'
