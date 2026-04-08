# MetaCleaner Bot

Telegram-бот для очистки метаданных из видеофайлов.
Удаляет title, GPS, дату записи и другие теги без перекодирования.

## Быстрый деплой на Ubuntu сервер

### Требования
- Ubuntu 22.04 или 24.04
- Минимум 1 ГБ RAM
- Python 3.11 (скрипт установит автоматически)
- Node.js 20 (скрипт установит автоматически)
- FFmpeg (скрипт установит автоматически)

### Установка

  git clone https://github.com/abdull15c/metacleaner_bot.git
  cd metacleaner_bot
  bash deploy/setup.sh

Следуй инструкциям скрипта.

### Известные проблемы

Python 3.13 не поддерживается — используй Python 3.11.
Если сервер поставил 3.13, скрипт setup.sh установит 3.11 из исходников.

bcrypt 4.1+ несовместим с passlib — requirements.txt уже содержит
bcrypt==4.0.1 для фикса.

YouTube скачивание требует Node.js — setup.sh устанавливает автоматически.

YouTube с VPS IP требует cookies — загрузи через Adminку → Настройки.


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
