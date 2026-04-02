import pytest

from core.youtube_cookies import COOKIES_MAX_BYTES, validate_netscape_cookie_file


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
