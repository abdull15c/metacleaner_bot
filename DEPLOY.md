# Деплой MetaCleaner (GitHub → сервер)

## 1. Репозиторий и зависимости

```bash
git clone <your-repo-url> metacleaner_bot
cd metacleaner_bot
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 2. PostgreSQL и Redis

**Вариант A — Docker (удобно на VPS):**

```bash
cp .env.example .env
# Задайте POSTGRES_PASSWORD в .env или экспорте, затем:
docker compose up -d postgres redis
```

В `.env` укажите:

```env
DATABASE_URL=postgresql+asyncpg://metacleaner:ВАШ_ПАРОЛЬ@127.0.0.1:5432/metacleaner
REDIS_URL=redis://127.0.0.1:6379/0
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1
```

**Вариант B** — управляемый Postgres/Redis у провайдера: те же переменные, только хосты/порты свои.

## 3. Миграции и данные

```bash
python -m alembic upgrade head
python scripts/seed_settings.py
python scripts/create_admin.py
```

Схема создаётся **только через Alembic** (`init_db()` не вызывает `create_all`).

## 4. Переменные продакшена

Обязательно проверьте:

| Переменная | Зачем |
|------------|--------|
| `BOT_TOKEN` | Telegram |
| `ADMIN_SECRET_KEY` | Подпись cookie входа в админку |
| `ADMIN_SESSION_SECRET` | (опционально) отдельный секрет для cookie сессии CSRF; иначе = `ADMIN_SECRET_KEY` |
| `ADMIN_COOKIE_SECURE=true` | За HTTPS |
| `ENVIRONMENT=production` | Для ясности в логах |
| `DEBUG=false` | |
| `ADMIN_LOGIN_RATE_PER_MINUTE=10` | Лимит POST `/admin/login` с одного IP в минуту (`0` — выкл.) |
| `DATABASE_POOL_SIZE` / `DATABASE_MAX_OVERFLOW` | Пул SQLAlchemy к Postgres (по умолчанию 5 / 10) |
| `ADMIN_SECURITY_HEADERS` | `true` — CSP и прочие заголовки (по умолчанию вкл.) |
| `ADMIN_CSP` | Пусто = встроенный CSP; `""` в .env — отключить только CSP |

## 5. Процессы на сервере

Три долгоживущих процесса (systemd, supervisord или tmux):

1. **Бот:** `python -m bot.main`
2. **Celery:** `celery -A workers.celery_app worker --loglevel=info -Q video,cleanup,broadcast --pool=solo`  
   Для **нескольких воркеров** на одной машине с Postgres можно попробовать `--pool=prefork -c 2` (нагрузите и проверьте пул БД).
3. **Админка:** `uvicorn admin.main:app --host 127.0.0.1 --port 8000`  
   Снаружи — Nginx с TLS и прокси на `127.0.0.1:8000`.

### Nginx: лимит логина (несколько воркеров Uvicorn)

In-process лимит `/admin/login` не делится между воркерами. В проде можно добавить:

```nginx
limit_req_zone $binary_remote_addr zone=admin_login:10m rate=10r/m;
location /admin/login {
    limit_req zone=admin_login burst=5 nodelay;
    proxy_pass http://127.0.0.1:8000;
}
```

## 6. Бэкапы Postgres

На сервере установите клиент `postgresql-client` (`pg_dump`). Синхронный URL без `+asyncpg`:

```bash
export DATABASE_URL=postgresql://metacleaner:ПАРОЛЬ@127.0.0.1:5432/metacleaner
chmod +x scripts/backup_db.sh
./scripts/backup_db.sh
```

Архивы появятся в `backups/*.sql.gz`. Повесьте на cron (например, ежедневно).

## 7. Тесты

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

Интеграционные сценарии (админка, отмена, лимит логина): `tests/test_integration_deploy.py`.

Маркер `integration` стоит на `tests/test_integration_deploy.py`; обычный прогон `pytest tests/` уже включает эти тесты.

## 8. Чеклист перед выкладкой

- [ ] `alembic upgrade head` на прод-БД  
- [ ] Секреты только в `.env`, не в git  
- [ ] HTTPS + `ADMIN_COOKIE_SECURE=true`  
- [ ] Отдельный `ADMIN_SESSION_SECRET` (длинный random)  
- [ ] Бэкапы и мониторинг диска под `temp/` и логи  
