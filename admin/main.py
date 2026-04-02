import logging
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware
from admin.auth import authenticate, set_cookie, clear_cookie, get_current_admin
from admin.csrf import ensure_csrf, verify_csrf
from admin.login_rate import check_admin_login_rate
from admin.security_headers import SecurityHeadersMiddleware
from core.config import settings as app_settings
from core.database import get_db_session, get_db
from core.telegram_html import sanitize_broadcast_html

logger = logging.getLogger(__name__)
app = FastAPI(title="MetaCleaner Admin", docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    SessionMiddleware,
    secret_key=app_settings.effective_session_secret,
    session_cookie="metacleaner_sess",
    same_site="lax",
    https_only=app_settings.admin_cookie_secure,
    max_age=60 * 60 * 24 * 14,
)
app.add_middleware(
    SecurityHeadersMiddleware,
    enabled=app_settings.admin_security_headers,
    csp=app_settings.admin_csp,
)

try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception:
    pass

templates = Jinja2Templates(directory="admin/templates")
templates.env.globals["csrf_token"] = ensure_csrf


class NeedsLogin(Exception): pass


@app.exception_handler(NeedsLogin)
async def login_redirect(request, exc):
    return RedirectResponse("/admin/login", status_code=303)


async def require_admin(request: Request, session: AsyncSession = Depends(get_db)):
    admin = await get_current_admin(request, session)
    if not admin: raise NeedsLogin()
    return admin


@app.get("/admin/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/admin/login")
async def login_submit(request: Request, session: AsyncSession = Depends(get_db)):
    check_admin_login_rate(request)
    form = await request.form()
    verify_csrf(request, form)
    username = str(form.get("username","")).strip()
    password = str(form.get("password","")).strip()
    admin = await authenticate(session, username, password)
    if not admin:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный логин или пароль"}, status_code=401)
    resp = RedirectResponse("/admin/dashboard", status_code=303)
    set_cookie(resp, admin.id)
    return resp


@app.get("/admin/logout")
async def logout():
    resp = RedirectResponse("/admin/login", status_code=303)
    clear_cookie(resp); return resp


@app.get("/admin")
async def admin_root(): return RedirectResponse("/admin/dashboard", status_code=303)


@app.get("/admin/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    from core.services.job_service import JobService
    from core.services.user_service import UserService
    from core.models import JobStatus
    from storage.local import storage
    js = JobService(session); us = UserService(session)
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "admin": admin, "active_page": "dashboard",
        "total_jobs":      await js.count_total(),
        "today_jobs":      await js.count_today(),
        "errors_24h":      await js.count_errors_24h(),
        "pending_jobs":    await js.count_by_status(JobStatus.pending) + await js.count_by_status(JobStatus.processing),
        "total_users":     await us.count_total(),
        "active_today":    await us.count_active_today(),
        "recent_jobs":     await js.get_recent_jobs(limit=10),
        "temp_files":      storage.temp_file_count(),
        "temp_size_mb":    storage.temp_total_size_mb(),
    })


@app.get("/admin/jobs", response_class=HTMLResponse)
async def jobs_list(request: Request, page: int = 1, session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    from core.services.job_service import JobService
    js = JobService(session); limit = 20; offset = (page-1)*limit
    total = await js.count_total()
    return templates.TemplateResponse("jobs.html", {
        "request": request, "admin": admin, "active_page": "jobs",
        "jobs": await js.get_recent_jobs(limit=limit, offset=offset),
        "page": page, "total_pages": max(1,(total+limit-1)//limit), "total": total,
    })


@app.get("/admin/jobs/{job_id}", response_class=HTMLResponse)
async def job_detail(request: Request, job_id: str, session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    from core.services.job_service import JobService
    return templates.TemplateResponse("job_detail.html", {
        "request": request, "admin": admin, "active_page": "jobs",
        "job": await JobService(session).get_by_uuid(job_id),
    })


@app.get("/admin/users", response_class=HTMLResponse)
async def users_list(request: Request, page: int = 1, session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    from sqlalchemy import select
    from core.models import User
    from core.services.user_service import UserService
    limit = 30; offset = (page-1)*limit
    r = await session.execute(select(User).order_by(User.created_at.desc()).limit(limit).offset(offset))
    total = await UserService(session).count_total()
    return templates.TemplateResponse("users.html", {
        "request": request, "admin": admin, "active_page": "users",
        "users": list(r.scalars().all()), "page": page,
        "total_pages": max(1,(total+limit-1)//limit), "total": total,
    })


@app.get("/admin/users/{telegram_id}", response_class=HTMLResponse)
async def user_detail(request: Request, telegram_id: int, session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    from core.services.user_service import UserService
    from core.services.job_service import JobService
    us = UserService(session); user = await us.get_by_telegram_id(telegram_id)
    jobs = await JobService(session).get_user_jobs(user.id, limit=10) if user else []
    return templates.TemplateResponse("user_detail.html", {"request": request, "admin": admin, "active_page": "users", "user": user, "jobs": jobs})


@app.post("/admin/users/{telegram_id}/ban")
async def ban(request: Request, telegram_id: int, session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    form = await request.form()
    verify_csrf(request, form)
    from core.services.user_service import UserService
    await UserService(session).ban_user(telegram_id); await session.commit()
    return RedirectResponse(f"/admin/users/{telegram_id}", status_code=303)


@app.post("/admin/users/{telegram_id}/unban")
async def unban(request: Request, telegram_id: int, session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    form = await request.form()
    verify_csrf(request, form)
    from core.services.user_service import UserService
    await UserService(session).unban_user(telegram_id); await session.commit()
    return RedirectResponse(f"/admin/users/{telegram_id}", status_code=303)


@app.get("/admin/broadcasts", response_class=HTMLResponse)
async def broadcasts(request: Request, session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    from sqlalchemy import select
    from core.models import Broadcast
    r = await session.execute(select(Broadcast).order_by(Broadcast.created_at.desc()).limit(50))
    return templates.TemplateResponse("broadcasts.html", {
        "request": request, "admin": admin, "active_page": "broadcasts",
        "broadcasts": list(r.scalars().all()),
        "form_error": request.query_params.get("err"),
    })


@app.post("/admin/broadcasts")
async def create_broadcast(request: Request, session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    from core.models import Broadcast, BroadcastRecipient, BroadcastStatus, RecipientStatus
    from core.services.user_service import UserService
    form = await request.form()
    verify_csrf(request, form)
    title = str(form.get("title", "")).strip()
    text = sanitize_broadcast_html(str(form.get("message_text", "")))
    if not title or not text:
        return RedirectResponse("/admin/broadcasts?err=empty", status_code=303)
    users = await UserService(session).get_all_active_users()
    bc = Broadcast(title=title, message_text=text, status=BroadcastStatus.draft, target_count=len(users), created_by=admin.id)
    session.add(bc); await session.flush()
    for u in users: session.add(BroadcastRecipient(broadcast_id=bc.id, user_id=u.id, status=RecipientStatus.pending))
    await session.commit()
    return RedirectResponse("/admin/broadcasts", status_code=303)


@app.post("/admin/broadcasts/{bid}/start")
async def bc_start(request: Request, bid: int, session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    form = await request.form()
    verify_csrf(request, form)
    from sqlalchemy import select
    from core.models import Broadcast, BroadcastStatus
    from datetime import datetime, timezone
    r = await session.execute(select(Broadcast).where(Broadcast.id == bid))
    bc = r.scalar_one_or_none()
    if bc and bc.status in (BroadcastStatus.draft, BroadcastStatus.paused):
        bc.status = BroadcastStatus.running; bc.started_at = bc.started_at or datetime.now(timezone.utc); await session.commit()
        from workers.broadcast import send_broadcast_chunk_task
        send_broadcast_chunk_task.apply_async(args=[bid], queue="broadcast")
    return RedirectResponse("/admin/broadcasts", status_code=303)


@app.post("/admin/broadcasts/{bid}/pause")
async def bc_pause(request: Request, bid: int, session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    form = await request.form()
    verify_csrf(request, form)
    from sqlalchemy import select
    from core.models import Broadcast, BroadcastStatus
    from datetime import datetime, timezone
    r = await session.execute(select(Broadcast).where(Broadcast.id == bid))
    bc = r.scalar_one_or_none()
    if bc and bc.status == BroadcastStatus.running:
        bc.status = BroadcastStatus.paused; bc.paused_at = datetime.now(timezone.utc); await session.commit()
    return RedirectResponse("/admin/broadcasts", status_code=303)


@app.get("/admin/errors", response_class=HTMLResponse)
async def errors_page(request: Request, page: int = 1, session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    from sqlalchemy import select
    from core.models import SystemLog, LogLevel
    limit = 50; offset = (page-1)*limit
    r = await session.execute(select(SystemLog).where(SystemLog.level.in_([LogLevel.ERROR,LogLevel.CRITICAL])).order_by(SystemLog.created_at.desc()).limit(limit).offset(offset))
    return templates.TemplateResponse("errors.html", {"request": request, "admin": admin, "active_page": "errors", "logs": list(r.scalars().all()), "page": page})


async def _youtube_admin_template_ctx(request: Request, session: AsyncSession):
    from pathlib import Path

    from core.config import settings as cfg
    from core.services.settings_service import SettingsService
    from core.youtube_cookies import preview_youtube_dl_sources, resolve_admin_cookies_path

    ss = SettingsService(session)
    db_cf = await ss.get("youtube_cookies_file", "")
    db_px = await ss.get("youtube_proxy", "")
    cookie_src, proxy_src = preview_youtube_dl_sources(db_cf, db_px)

    ap = resolve_admin_cookies_path()
    admin_exists = ap.is_file()
    admin_size = ap.stat().st_size if admin_exists else 0
    env_p = cfg.youtube_cookies_file
    env_ep = Path(env_p) if env_p else None
    if env_ep and not env_ep.is_absolute():
        env_ep = cfg.project_root / env_ep
    env_ok = bool(env_ep and env_ep.is_file())
    err_map = {
        "nofile": "Файл не выбран.",
        "invalid": "Некорректный файл: нужен Netscape cookies с youtube.com.",
        "io": "Не удалось записать файл.",
    }
    err = request.query_params.get("youtube_err")
    return {
        "youtube_admin_exists": admin_exists,
        "youtube_admin_size": admin_size,
        "youtube_cookie_source": cookie_src,
        "youtube_proxy_source": proxy_src,
        "youtube_env_cookies_ok": env_ok,
        "youtube_ok": request.query_params.get("youtube_ok"),
        "youtube_del": request.query_params.get("youtube_del"),
        "youtube_err": err,
        "youtube_err_msg": err_map.get(err) if err else None,
    }


@app.get("/admin/settings", response_class=HTMLResponse)
async def settings_page(request: Request, session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    from core.services.settings_service import SettingsService
    ctx = {
        "request": request, "admin": admin, "active_page": "settings",
        "settings": await SettingsService(session).get_all_with_meta(),
        "saved": request.query_params.get("saved"),
    }
    ctx.update(await _youtube_admin_template_ctx(request, session))
    return templates.TemplateResponse("settings.html", ctx)


@app.post("/admin/settings")
async def update_settings(request: Request, session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    from core.services.settings_service import ALLOWED_SETTING_KEYS, SettingsService
    form = await request.form()
    verify_csrf(request, form)
    svc = SettingsService(session)
    for k, v in form.items():
        if k.startswith("_") or k == "csrf_token":
            continue
        if k not in ALLOWED_SETTING_KEYS:
            continue
        if v.lower() in ("true","on","yes","1"): v = "true"
        elif v.lower() in ("false","off","no","0"): v = "false"
        await svc.set(k, v, admin_id=admin.id)
    await session.commit()
    return RedirectResponse("/admin/settings?saved=1", status_code=303)


@app.post("/admin/youtube/cookies")
async def admin_upload_youtube_cookies(request: Request, admin=Depends(require_admin)):
    form = await request.form()
    verify_csrf(request, form)
    uf = form.get("cookies_file")
    if uf is None or not hasattr(uf, "read"):
        return RedirectResponse("/admin/settings?youtube_err=nofile", status_code=303)
    try:
        raw = await uf.read()
        from core.youtube_cookies import save_admin_cookies

        save_admin_cookies(raw)
    except ValueError:
        return RedirectResponse("/admin/settings?youtube_err=invalid", status_code=303)
    except OSError:
        return RedirectResponse("/admin/settings?youtube_err=io", status_code=303)
    return RedirectResponse("/admin/settings?youtube_ok=1", status_code=303)


@app.post("/admin/youtube/cookies/delete")
async def admin_delete_youtube_cookies(request: Request, admin=Depends(require_admin)):
    form = await request.form()
    verify_csrf(request, form)
    from core.youtube_cookies import delete_admin_cookies

    delete_admin_cookies()
    return RedirectResponse("/admin/settings?youtube_del=1", status_code=303)


@app.post("/admin/cleanup/run")
async def manual_cleanup(request: Request, admin=Depends(require_admin)):
    form = await request.form()
    verify_csrf(request, form)
    from workers.cleanup import run_manual_cleanup
    r = run_manual_cleanup()
    return RedirectResponse(f"/admin/settings?saved=cleanup&orphaned={r['orphaned_deleted']}", status_code=303)


@app.post("/admin/processing/pause")
async def proc_pause(request: Request, session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    form = await request.form()
    verify_csrf(request, form)
    from core.services.settings_service import SettingsService
    await SettingsService(session).set("processing_enabled","false",admin.id); await session.commit()
    return RedirectResponse("/admin/settings", status_code=303)


@app.post("/admin/processing/resume")
async def proc_resume(request: Request, session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    form = await request.form()
    verify_csrf(request, form)
    from core.services.settings_service import SettingsService
    await SettingsService(session).set("processing_enabled","true",admin.id); await session.commit()
    return RedirectResponse("/admin/settings", status_code=303)


@app.post("/admin/maintenance/on")
async def maint_on(request: Request, session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    form = await request.form()
    verify_csrf(request, form)
    from core.services.settings_service import SettingsService
    await SettingsService(session).set("maintenance_mode","true",admin.id); await session.commit()
    return RedirectResponse("/admin/settings", status_code=303)


@app.post("/admin/maintenance/off")
async def maint_off(request: Request, session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    form = await request.form()
    verify_csrf(request, form)
    from core.services.settings_service import SettingsService
    await SettingsService(session).set("maintenance_mode","false",admin.id); await session.commit()
    return RedirectResponse("/admin/settings", status_code=303)


@app.on_event("startup")
async def startup():
    app_settings.ensure_dirs()
    from core.database import init_db
    await init_db()
    async with get_db_session() as session:
        from core.services.settings_service import SettingsService
        await SettingsService(session).seed_defaults(); await session.commit()
