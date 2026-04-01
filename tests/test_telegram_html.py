import pytest

from core.telegram_html import sanitize_broadcast_html


def test_sanitize_strips_script():
    s = sanitize_broadcast_html('<b>Hi</b><script>alert(1)</script>')
    assert "<script" not in s.lower()
    assert "Hi" in s


def test_sanitize_allows_basic_telegram_tags():
    s = sanitize_broadcast_html('<b>Bold</b> <i>it</i> <code>x</code>')
    assert "<b>" in s or "Bold" in s


def test_sanitize_empty():
    assert sanitize_broadcast_html("") == ""
    assert sanitize_broadcast_html("   <script></script>  ") == ""
