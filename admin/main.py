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
from webapp.bootstrap import mount_webapp

logger = logging.getLogger(__name__)
app = FastAPI(title="MetaCleaner Admin", docs_url=None, redoc_url=None, openapi_url=None)

try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app, include_in_schema=False, should_gzip=True)
except ImportError:
    pass

@app.post("/webhook")
async def telegram_webhook(request: Request):
    from aiogram.types import Update
    from bot.main import bot, dp
    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.get("/health")
async def health_check():
    import redis.asyncio as aioredis
    from sqlalchemy import text
    from core.database import engine
    from core.config import settings
    
    db_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        pass
        
    redis_ok = False
    try:
        r = aioredis.from_url(str(settings.redis_url))
        await r.ping()
        redis_ok = True
        await r.close()
    except Exception:
        pass
        
    status = "ok" if db_ok and redis_ok else "error"
    return {"status": status, "db": "ok" if db_ok else "error", "redis": "ok" if redis_ok else "error"}

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

mount_webapp(app)

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
        "force_sub_enabled": (await SettingsService(session).get("force_sub_enabled", "false")) == "true",
        "temp_files":      storage.temp_file_count(),
        "temp_size_mb":    storage.temp_total_size_mb(),
    })


from fastapi.responses import StreamingResponse
import io
import csv

@app.get("/admin/jobs/export.csv")
async def export_jobs_csv(session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from core.models import Job
    
    async def iter_jobs():
        yield "ID,UUID,User_ID,Source,Status,Created_At,Completed_At\n"
        
        stmt = select(Job).options(selectinload(Job.user)).order_by(Job.created_at.desc())
        r = await session.stream(stmt)
        
        async for row in r:
            job = row[0]
            uid = job.user.telegram_id if job.user else ""
            status = job.status.value if hasattr(job.status, "value") else str(job.status)
            src = job.source_type.value if hasattr(job.source_type, "value") else str(job.source_type)
            cat = job.created_at.isoformat() if job.created_at else ""
            comat = job.completed_at.isoformat() if job.completed_at else ""
            
            line = f"{job.id},{job.uuid},{uid},{src},{status},{cat},{comat}\n"
            yield line
            
    return StreamingResponse(iter_jobs(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=jobs_export.csv"})

@app.get("/admin/users/export.csv")
async def export_users_csv(session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    from sqlalchemy import select
    from core.models import User
    
    async def iter_users():
        yield "ID,Telegram_ID,Username,First_Name,Created_At,Last_Seen_At,Jobs_Count,Banned\n"
        
        stmt = select(User).order_by(User.created_at.desc())
        r = await session.stream(stmt)
        
        async for row in r:
            u = row[0]
            uname = (u.username or "").replace(",", "")
            fname = (u.first_name or "").replace(",", "")
            cat = u.created_at.isoformat() if u.created_at else ""
            lsat = u.last_seen_at.isoformat() if u.last_seen_at else ""
            
            line = f"{u.id},{u.telegram_id},{uname},{fname},{cat},{lsat},{u.daily_job_count},{u.is_banned}\n"
            yield line
            
    return StreamingResponse(iter_users(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=users_export.csv"})

@app.get("/admin/jobs", response_class=HTMLResponse)
async def jobs_list(request: Request, page: int = 1, q: str = "", status: str = "", session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    from sqlalchemy import select, or_, func
    from sqlalchemy.orm import selectinload
    from core.models import Job, JobStatus, User
    limit = 20; offset = (page-1)*limit
    
    stmt = select(Job).options(selectinload(Job.user))
    
    q_val = q.strip()
    if q_val:
        stmt = stmt.join(User, isouter=True).where(
            or_(
                Job.uuid.ilike(f"%{q_val}%"),
                User.username.ilike(f"%{q_val}%")
            )
        )
        
    if status and hasattr(JobStatus, status):
        stmt = stmt.where(Job.status == JobStatus[status])
        
    count_stmt = select(func.count(Job.id))
    if q_val:
        count_stmt = count_stmt.join(User, isouter=True).where(
            or_(
                Job.uuid.ilike(f"%{q_val}%"),
                User.username.ilike(f"%{q_val}%")
            )
        )
    if status and hasattr(JobStatus, status):
        count_stmt = count_stmt.where(Job.status == JobStatus[status])
        
    total_r = await session.execute(count_stmt)
    total = total_r.scalar() or 0
    
    r = await session.execute(stmt.order_by(Job.created_at.desc()).limit(limit).offset(offset))
    jobs = list(r.scalars().all())

    return templates.TemplateResponse("jobs.html", {
        "request": request, "admin": admin, "active_page": "jobs",
        "jobs": jobs,
        "page": page, "total_pages": max(1, (total+limit-1)//limit), "total": total,
        "q": q_val, "status": status
    })


@app.get("/admin/jobs/{job_id}", response_class=HTMLResponse)
async def job_detail(request: Request, job_id: str, session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    from core.services.job_service import JobService
    return templates.TemplateResponse("job_detail.html", {
        "request": request, "admin": admin, "active_page": "jobs",
        "job": await JobService(session).get_by_uuid(job_id),
    })


@app.get("/admin/users", response_class=HTMLResponse)
async def users_list(request: Request, page: int = 1, q: str = "", session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    from sqlalchemy import select, or_, cast, String, func
    from core.models import User
    from core.services.user_service import UserService
    limit = 30; offset = (page-1)*limit
    stmt = select(User)
    
    q_val = q.strip()
    if q_val:
        stmt = stmt.where(
            or_(
                User.username.ilike(f"%{q_val}%"),
                User.first_name.ilike(f"%{q_val}%"),
                cast(User.telegram_id, String).ilike(f"%{q_val}%")
            )
        )
    
    count_stmt = select(func.count(User.id))
    if q_val:
        count_stmt = count_stmt.where(
            or_(
                User.username.ilike(f"%{q_val}%"),
                User.first_name.ilike(f"%{q_val}%"),
                cast(User.telegram_id, String).ilike(f"%{q_val}%")
            )
        )
    
    total_r = await session.execute(count_stmt)
    total = total_r.scalar() or 0

    r = await session.execute(stmt.order_by(User.created_at.desc()).limit(limit).offset(offset))
    
    return templates.TemplateResponse("users.html", {
        "request": request, "admin": admin, "active_page": "users",
        "users": list(r.scalars().all()), "page": page,
        "total_pages": max(1,(total+limit-1)//limit), "total": total,
        "q": q_val
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


@app.get("/admin/sponsors", response_class=HTMLResponse)
async def sponsors_list(request: Request, session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    from sqlalchemy import select
    from core.models import SponsorChannel
    from core.services.settings_service import SettingsService
    r = await session.execute(select(SponsorChannel))
    force_sub = await SettingsService(session).get("force_sub_enabled", "false")
    return templates.TemplateResponse("sponsors.html", {
        "request": request, "admin": admin, "active_page": "sponsors",
        "channels": list(r.scalars().all()),
        "force_sub_enabled": force_sub == "true"
    })

@app.post("/admin/sponsors")
async def create_sponsor(request: Request, session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    from core.models import SponsorChannel
    form = await request.form()
    verify_csrf(request, form)
    cid = int(form.get("channel_id"))
    name = str(form.get("name"))
    url = str(form.get("url"))
    
    session.add(SponsorChannel(channel_id=cid, name=name, url=url))
    await session.commit()
    return RedirectResponse("/admin/sponsors", status_code=303)

@app.post("/admin/sponsors/{sid}/delete")
async def delete_sponsor(sid: int, request: Request, session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    from sqlalchemy import delete
    from core.models import SponsorChannel
    form = await request.form()
    verify_csrf(request, form)
    await session.execute(delete(SponsorChannel).where(SponsorChannel.id == sid))
    await session.commit()
    return RedirectResponse("/admin/sponsors", status_code=303)

@app.post("/admin/sponsors/toggle")
async def toggle_force_sub(request: Request, session: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    from core.services.settings_service import SettingsService
    import redis.asyncio as aioredis
    from core.config import settings
    form = await request.form()
    verify_csrf(request, form)
    
    svc = SettingsService(session)
    current = await svc.get("force_sub_enabled", "false")
    new_val = "true" if current == "false" else "false"
    await svc.set("force_sub_enabled", new_val, admin.id)
    await session.commit()
    
    # Sync to Redis
    r = aioredis.from_url(str(settings.redis_url))
    await r.set("settings:force_sub:enabled", new_val)
    await r.close()
    
    return RedirectResponse("/admin/sponsors", status_code=303)


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
    from sqlalchemy import select, func
    from core.models import SystemLog, LogLevel
    limit = 50; offset = (page-1)*limit
    r = await session.execute(select(SystemLog).where(SystemLog.level.in_([LogLevel.ERROR,LogLevel.CRITICAL])).order_by(SystemLog.created_at.desc()).limit(limit).offset(offset))
    total_query = await session.execute(select(func.count(SystemLog.id)).where(SystemLog.level.in_([LogLevel.ERROR,LogLevel.CRITICAL])))
    total = total_query.scalar() or 0
    return templates.TemplateResponse("errors.html", {
        "request": request, "admin": admin, "active_page": "errors", 
        "logs": list(r.scalars().all()), "page": page,
        "total_pages": max(1, (total + limit - 1) // limit), "total": total
    })


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
