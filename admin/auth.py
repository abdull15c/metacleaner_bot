from typing import Optional
from datetime import datetime, timezone
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from core.config import settings
from core.models import Admin

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_s = URLSafeTimedSerializer(settings.admin_secret_key)
COOKIE = settings.admin_session_cookie
MAX_AGE = 60 * 60 * 8


def hash_password(plain): return pwd.hash(plain)
def verify_password(plain, hashed): return pwd.verify(plain, hashed)
def create_token(admin_id): return _s.dumps({"admin_id": admin_id})


def decode_token(token) -> Optional[int]:
    try:
        data = _s.loads(token, max_age=MAX_AGE)
        aid = data.get("admin_id")
        return int(aid) if aid is not None else None
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None


def get_token(request: Request): return request.cookies.get(COOKIE)


def set_cookie(response, admin_id):
    response.set_cookie(
        COOKIE, create_token(admin_id),
        httponly=True, max_age=MAX_AGE, samesite="lax", path="/",
        secure=settings.admin_cookie_secure,
    )


def clear_cookie(response):
    response.delete_cookie(
        COOKIE, path="/", samesite="lax", secure=settings.admin_cookie_secure,
    )


async def authenticate(session: AsyncSession, username, password) -> Optional[Admin]:
    r = await session.execute(select(Admin).where(Admin.username == username, Admin.is_active == True))
    admin = r.scalar_one_or_none()
    if not admin or not verify_password(password, admin.password_hash): return None
    admin.last_login_at = datetime.now(timezone.utc)
    return admin


async def get_admin_by_id(session, admin_id) -> Optional[Admin]:
    r = await session.execute(select(Admin).where(Admin.id == admin_id, Admin.is_active == True))
    return r.scalar_one_or_none()


async def get_current_admin(request: Request, session) -> Optional[Admin]:
    token = get_token(request)
    if not token: return None
    aid = decode_token(token)
    if not aid: return None
    return await get_admin_by_id(session, aid)
