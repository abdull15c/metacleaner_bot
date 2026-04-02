# CHANGELOG_AI.md

Журнал значимых изменений, вносимых при доработках проекта (в т.ч. с помощью AI).

## 2024-01-01 — Initial generation (MVP v1.0)

**Создано через setup.py installer**

- Полный проект MetaCleaner Bot
- bot/, core/, workers/, admin/, storage/, tests/, scripts/
- Три Celery очереди: video, cleanup, broadcast
- Anti-flood middleware, YouTube FSM consent
- FastAPI admin panel с Jinja2 шаблонами
- SQLite + SQLAlchemy async + Alembic

---

## 2026-04-02 — Надёжность, безопасность админки, прод-инфра, CI

### Надёжность и жизненный цикл задач

- Сбой постановки в Celery (`delay`): задача помечается `failed`, для upload удаляется временный файл, откат дневного лимита (`rollback_daily_job_increment`); тексты с подсказкой `/status`.
- `get_active_job_for_user`: `ORDER BY created_at DESC LIMIT 1` + `scalars().first()` — без риска `MultipleResultsFound`.
- `decode_token` в админке: явные исключения (`BadSignature`, `SignatureExpired`, …), куки с `path="/"` и флагом `secure` от настроек.
- Воркеры: атомарные переходы `try_begin_youtube_download`, `try_begin_video_processing`, `try_begin_sending` (UPDATE по статусу) — идемпотентность при дублях задач.
- `/cancel`: логирование ошибки `revoke` вместо голого `except`.
- `ffprobe` / метаданные: узкие `except` и логирование вместо молчаливого `{}`.
- Бот: опционально Redis для FSM и anti-flood (`BOT_REDIS_ENABLED`), fallback в память; `storage.close()` при остановке.

### Схема БД и Postgres

- `init_db()` больше не вызывает `create_all` — только PRAGMA для SQLite; схема **только через Alembic**.
- `migrations/env.py`: корректный async-URL (`sqlite+aiosqlite`, `postgresql+asyncpg`).
- Пул SQLAlchemy для Postgres: `database_pool_size`, `database_max_overflow`.
- Зависимость `asyncpg`; в README / `.env.example` — пример `DATABASE_URL` для PostgreSQL.

### Админка: безопасность

- `SessionMiddleware` для CSRF-сессии; отдельный **`ADMIN_SESSION_SECRET`** или fallback на `ADMIN_SECRET_KEY` (`effective_session_secret`).
- Проверка CSRF на всех POST-формах; скрытые поля в шаблонах; `csrf_token` не пишется в настройки из формы.
- `SecurityHeadersMiddleware`: `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, настраиваемый **CSP** (`ADMIN_CSP`, пустая строка = без CSP).
- **Rate limit** POST `/admin/login` по IP (`ADMIN_LOGIN_RATE_PER_MINUTE`, `0` = выкл.) — in-process; для нескольких воркеров см. `DEPLOY.md` (nginx `limit_req`).
- Рассылки: санитизация HTML под Telegram (`bleach`, `core/telegram_html.py`) при создании и при отправке в воркере.

### Инфраструктура и деплой

- `docker-compose.yml` — Postgres + Redis.
- `DEPLOY.md` — выкладка, миграции, Nginx, бэкапы.
- `scripts/backup_db.sh` — дамп PostgreSQL в `backups/` (в `.gitignore`).
- `scripts/dump_codebase.py` — дамп исходников в один `.txt`.
- `.github/workflows/tests.yml` — CI на **Python 3.11**, `pytest tests/`.

### Тесты

- `pytest.ini`, маркер `integration`.
- `tests/test_integration_deploy.py`: security headers, логин с CSRF, rate limit, отмена job (mock Celery/cleanup), сбой `delay` после загрузки.
- `tests/test_job_lifecycle.py`, `test_telegram_html.py`, `tests/test_csrf.py` и др.

### Конфиг (фрагмент)

- `debug=false` по умолчанию; `admin_cookie_secure`, `bot_redis_enabled`, `admin_login_rate_per_minute`, `admin_security_headers`, `admin_csp`.

### Известные ограничения

- Лимит логина админки — на процесс; глобально при нескольких инстансах — внешний лимитер (см. DEPLOY.md).

---

## 2026-04-02 (доп.) — YouTube с VPS

- В конфиге: `YOUTUBE_COOKIES_FILE`, `YOUTUBE_PROXY` для вызовов `yt-dlp` (обход 429 / «Sign in to confirm…» с датацентровых IP).
- В `DEPLOY.md` — раздел с пошаговыми рекомендациями.

## 2026-04-02 (доп.) — systemd

- `deploy/systemd/`: `metacleaner-admin.service`, `metacleaner-worker.service`, `metacleaner-bot.service` (пути `/root/metacleaner_bot`, venv `.venv`).
- В `DEPLOY.md` — инструкция по установке, `sed` для `YOUTUBE_ENABLED=false`, заметка про Redis из Docker и запуск не от root.

## 2026-04-02 (доп.) — порт админки из .env

- `ADMIN_HOST`, `ADMIN_PORT` (1–65535); запуск `python -m admin` (`admin/__main__.py`), systemd без захардкоженного порта.
- В `.env.example`, README, DEPLOY, `create_admin.py` — учёт порта.

## 2026-04-02 (доп.) — YouTube cookies из админки

- Загрузка Netscape `cookies.txt` в **Настройки** админки → `secrets/youtube_cookies.txt` (`core/youtube_cookies.py`).
- Приоритет для yt-dlp: `YOUTUBE_COOKIES_FILE` в .env, иначе файл из админки; прокси по-прежнему `YOUTUBE_PROXY` в .env.
- `YOUTUBE_COOKIES_ADMIN_PATH` в конфиге для смены пути; `secrets/*` в `.gitignore`.
