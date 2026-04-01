import pytest
from fastapi import HTTPException
from starlette.datastructures import FormData

from admin.csrf import ensure_csrf, verify_csrf


class _Req:
    def __init__(self):
        self.session = {}


def test_ensure_csrf_stable():
    r = _Req()
    a = ensure_csrf(r)
    b = ensure_csrf(r)
    assert a == b and len(a) > 8


def test_verify_csrf_ok():
    r = _Req()
    ensure_csrf(r)
    tok = r.session["_csrf"]
    verify_csrf(r, FormData([("csrf_token", tok)]))


def test_verify_csrf_fails():
    r = _Req()
    r.session["_csrf"] = "expected"
    with pytest.raises(HTTPException) as ei:
        verify_csrf(r, FormData([("csrf_token", "wrong")]))
    assert ei.value.status_code == 403
