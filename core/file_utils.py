"""
Утилиты для безопасной работы с файловой системой.
"""
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


def validate_file_path(path: str | Path, allowed_dirs: List[Path]) -> Path:
    """
    Проверка пути к файлу на Path Traversal атаки.
    
    Args:
        path: Путь к файлу для проверки
        allowed_dirs: Список разрешенных директорий
    
    Returns:
        Разрешенный абсолютный путь
        
    Raises:
        ValueError: Если путь находится вне разрешенных директорий или не является файлом
    """
    if not path:
        raise ValueError("Path is empty")
    
    # Преобразовать в Path и разрешить символические ссылки
    p = Path(path).resolve()
    
    # Проверить что путь находится внутри одной из разрешенных директорий
    is_allowed = False
    for allowed_dir in allowed_dirs:
        try:
            # resolve() для разрешения symlinks в allowed_dir
            allowed_resolved = allowed_dir.resolve()
            # is_relative_to() проверяет что p находится внутри allowed_resolved
            if p.is_relative_to(allowed_resolved):
                is_allowed = True
                break
        except (ValueError, OSError) as e:
            logger.warning(f"Failed to check path {p} against {allowed_dir}: {e}")
            continue
    
    if not is_allowed:
        raise ValueError(f"Path outside allowed directories: {p}")
    
    # Проверить что это файл (не директория, не symlink на директорию)
    if not p.is_file():
        raise ValueError(f"Not a file: {p}")
    
    return p
