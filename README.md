# MetaCleaner Bot

Telegram-бот для очистки метаданных из видеофайлов.
Удаляет title, GPS, дату записи и другие теги без перекодирования.

## Быстрый старт

```bash
# 1. Установить зависимости
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt

# 2. Настроить .env
copy .env.example .env
# Заполнить BOT_TOKEN и ADMIN_SECRET_KEY

# 3. Создать таблицы БД (только Alembic; create_all отключён)
python -m alembic upgrade head

# 4. Заполнить настройки
python scripts\seed_settings.py

# 5. Создать администратора
python scripts\create_admin.py

# 6. Запустить (3 отдельных окна)

# Окно 1 — бот:
python -m bot.main

# Окно 2 — воркер:
celery -A workers.celery_app worker --loglevel=info -Q video,cleanup,broadcast --pool=solo

# Окно 3 — панель (порт и хост в .env: ADMIN_HOST, ADMIN_PORT):
python -m admin
```

Подробный чеклист деплоя (VPS, Docker, Postgres, Nginx, бэкапы): [DEPLOY.md](DEPLOY.md).

## База данных

- **SQLite** (по умолчанию): `DATABASE_URL=sqlite+aiosqlite:///./metacleaner.db`
- **PostgreSQL**: `DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname` (нужен пакет `asyncpg`), затем `alembic upgrade head`.

В продакшене за HTTPS включите в `.env`: `ADMIN_COOKIE_SECURE=true`.

## Панель администратора

http://127.0.0.1:8000/admin (порт по умолчанию 8000, см. `ADMIN_PORT` в `.env`)

## Тесты

```bash
python -m pytest tests/ -v
```

## Форматы

MP4, MKV, MOV, AVI, WebM, M4V, FLV, TS, WMV, 3GP
