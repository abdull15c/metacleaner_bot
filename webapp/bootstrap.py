"""Подключение Mini App к основному ASGI-приложению админки (без смешивания роутов в одном файле)."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from webapp.routes import router as webapp_router


def mount_webapp(app: FastAPI) -> None:
    app.include_router(webapp_router)
    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.is_dir():
        try:
            app.mount("/webapp-static", StaticFiles(directory=str(static_dir)), name="webapp_static")
        except Exception:
            pass
