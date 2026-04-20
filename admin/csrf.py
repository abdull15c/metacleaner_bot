import secrets
import hmac
from starlette.datastructures import FormData
from starlette.requests import Request
from fastapi import HTTPException


def ensure_csrf(request: Request) -> str:
    tok = request.session.get("_csrf")
    if not tok:
        tok = secrets.token_urlsafe(32)
        request.session["_csrf"] = tok
    return tok


def verify_csrf(request: Request, form: FormData) -> None:
    got = form.get("csrf_token")
    if isinstance(got, str):
        pass
    elif got is None:
        got = ""
    else:
        got = str(got)
    expected = request.session.get("_csrf")
    
    # SECURITY FIX: Использование hmac.compare_digest для защиты от timing attacks
    if not expected or not hmac.compare_digest(got, expected):
        raise HTTPException(status_code=403, detail="CSRF validation failed")
