"""Ограниченный набор HTML для Telegram (parse_mode=HTML). Убирает script/on* и лишние теги."""
import bleach

# https://core.telegram.org/bots/api#html-style
_ALLOWED_TAGS = frozenset({
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "tg-spoiler", "tg-emoji", "a", "code", "pre", "br",
})
_ALLOWED_ATTRS = {"a": ["href"]}


def sanitize_broadcast_html(raw: str, max_len: int = 4090) -> str:
    """
    Санитизация HTML для Telegram broadcast.
    
    SECURITY FIX: Убраны regex (могут быть обойдены), полагаемся только на bleach.
    """
    if not raw or not raw.strip():
        return ""
    
    s = raw.strip()[: max_len + 64]
    
    # SECURITY FIX: Убраны regex для <script> и on* атрибутов
    # bleach.clean() уже удаляет все неразрешенные теги и атрибуты
    clean = bleach.clean(
        s,
        tags=list(_ALLOWED_TAGS),
        attributes=_ALLOWED_ATTRS,
        strip=True,
    )
    
    return clean[:max_len]
