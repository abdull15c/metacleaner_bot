import pytest

from core.youtube_cookies import (
    COOKIES_MAX_BYTES,
    preview_youtube_dl_sources,
    validate_netscape_cookie_file,
)


def test_validate_netscape_ok():
    raw = b"""# Netscape HTTP Cookie File
.youtube.com\tTRUE\t/\tTRUE\t0\tVISITOR_INFO1\tabc
"""
    assert validate_netscape_cookie_file(raw) is True


def test_validate_rejects_without_netscape():
    raw = b"just some text youtube.com tabs here"
    assert validate_netscape_cookie_file(raw) is False


def test_validate_rejects_without_youtube():
    raw = b"# Netscape HTTP Cookie File\nother.com\tTRUE\t/\tTRUE\t0\tx\ty\n"
    assert validate_netscape_cookie_file(raw) is False


def test_validate_rejects_too_large():
    raw = b"# Netscape HTTP Cookie File\n" + (b"x" * COOKIES_MAX_BYTES)
    assert validate_netscape_cookie_file(raw) is False


def test_preview_proxy_db_wins(monkeypatch):
    monkeypatch.setattr(
        "core.youtube_cookies.get_effective_youtube_cookies_path", lambda: None
    )
    c, p = preview_youtube_dl_sources("", "http://proxy.example:8080")
    assert c == "none"
    assert p == "db"


def test_preview_cookies_db_absolute_path(tmp_path):
    f = tmp_path / "cookies.txt"
    f.write_text("x", encoding="utf-8")
    c, p = preview_youtube_dl_sources(str(f.resolve()), "")
    assert c == "db"
    assert p == "none"
