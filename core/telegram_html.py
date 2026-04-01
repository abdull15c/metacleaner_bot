"""Ограниченный набор HTML для Telegram (parse_mode=HTML). Убирает script/on* и лишние теги."""
import re
import bleach

# https://core.telegram.org/bots/api#html-style
_ALLOWED_TAGS = frozenset({
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "tg-spoiler", "tg-emoji", "a", "code", "pre", "br",
})
_ALLOWED_ATTRS = {"a": ["href"]}


def sanitize_broadcast_html(raw: str, max_len: int = 4090) -> str:
    if not raw or not raw.strip():
        return ""
    s = raw.strip()[: max_len + 64]
    s = re.sub(r"(?is)<script[^>]*>.*?</script>", "", s)
    s = re.sub(r"(?i)\son\w+\s*=", " data-removed=", s)
    clean = bleach.clean(
        s,
        tags=list(_ALLOWED_TAGS),
        attributes=_ALLOWED_ATTRS,
        strip=True,
    )
    return clean[:max_len]
