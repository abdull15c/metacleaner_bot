from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

DEFAULT_ADMIN_CSP = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'none'; "
    "object-src 'none'"
)

# Mini App (/app): нужны скрипты Telegram + fetch; встраивание в web.telegram.org
WEBAPP_CSP = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors https://web.telegram.org https://telegram.org 'self'; "
    "img-src 'self' data: https:; "
    "font-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline' https://telegram.org; "
    "connect-src 'self' https://telegram.org; "
    "object-src 'none'"
)


def _is_webapp_path(path: str) -> bool:
    # Mini App HTML/API/статика; download — тот же CSP (unsafe-inline — осознанно до стабилизации UI).
    return path == "/app" or path.startswith("/api/webapp") or path.startswith("/webapp-static")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, enabled: bool = True, csp: Optional[str] = None):
        super().__init__(app)
        self._enabled = enabled
        if csp == "":
            self._csp = None
        elif csp:
            self._csp = csp
        else:
            self._csp = DEFAULT_ADMIN_CSP

    async def dispatch(self, request: Request, call_next) -> Response:
        resp = await call_next(request)
        if not self._enabled:
            return resp
        path = request.url.path
        if _is_webapp_path(path):
            resp.headers["X-Content-Type-Options"] = "nosniff"
            resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            resp.headers["Content-Security-Policy"] = WEBAPP_CSP
            return resp
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if self._csp is not None:
            resp.headers["Content-Security-Policy"] = self._csp
        return resp
