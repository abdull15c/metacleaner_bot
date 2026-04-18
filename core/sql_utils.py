"""
Утилиты для безопасной работы с SQL запросами.
"""

def escape_like_pattern(pattern: str, max_len: int = 100) -> str:
    """
    Экранирование спецсимволов для LIKE/ILIKE запросов.
    
    Args:
        pattern: Строка для экранирования
        max_len: Максимальная длина (защита от DoS)
    
    Returns:
        Экранированная строка
    """
    if not pattern:
        return ""
    
    # Ограничить длину
    pattern = pattern[:max_len]
    
    # Экранировать спецсимволы LIKE
    pattern = pattern.replace('\\', '\\\\')  # Сначала backslash
    pattern = pattern.replace('%', '\\%')
    pattern = pattern.replace('_', '\\_')
    
    return pattern
