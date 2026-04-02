"""Запуск панели: порт и хост из .env — ADMIN_HOST, ADMIN_PORT.

  python -m admin
"""
import uvicorn

from core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "admin.main:app",
        host=settings.admin_host,
        port=settings.admin_port,
    )
