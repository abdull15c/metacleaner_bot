"""
Утилиты для работы с метаданными.
"""
import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Максимальный размер метаданных в байтах (10KB)
MAX_METADATA_SIZE = 10 * 1024


def truncate_metadata(metadata: Dict[str, Any], max_size: int = MAX_METADATA_SIZE) -> Dict[str, Any]:
    """
    Ограничение размера метаданных для предотвращения memory leak.
    
    Args:
        metadata: Словарь с метаданными
        max_size: Максимальный размер в байтах
        
    Returns:
        Усеченный словарь метаданных
    """
    if not metadata:
        return {}
    
    try:
        # Проверяем размер
        serialized = json.dumps(metadata, ensure_ascii=False)
        size = len(serialized.encode('utf-8'))
        
        if size <= max_size:
            return metadata
        
        # Если слишком большой - усекаем
        logger.warning(f"Metadata too large ({size} bytes), truncating to {max_size} bytes")
        
        # Простое усечение: оставляем только основные поля
        truncated = {}
        current_size = 0
        
        for key, value in metadata.items():
            item_json = json.dumps({key: value}, ensure_ascii=False)
            item_size = len(item_json.encode('utf-8'))
            
            if current_size + item_size > max_size:
                truncated["_truncated"] = True
                truncated["_original_size"] = size
                break
            
            truncated[key] = value
            current_size += item_size
        
        return truncated
        
    except Exception as e:
        logger.error(f"Failed to truncate metadata: {e}", exc_info=True)
        return {"_error": "Failed to process metadata"}
