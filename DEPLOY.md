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
3. **Админка:** `python -m admin` — хост и порт из `.env` (`ADMIN_HOST`, `ADMIN_PORT`, по умолчанию `127.0.0.1:8000`). На сервере часто `ADMIN_HOST=0.0.0.0` и **уникальный** `ADMIN_PORT` (например `8456`), чтобы не конфликтовать с другими сервисами.  
   Снаружи — Nginx с TLS и `proxy_pass` на тот же порт, что в `ADMIN_PORT`.

### systemd (юниты в репозитории)

В каталоге `deploy/systemd/` лежат три unit-файла под типичный VPS:

| Предположение | Значение |
|---------------|----------|
| Клон репозитория | `/root/metacleaner_bot` |
| Виртуальное окружение | `/root/metacleaner_bot/.venv` |
| Пользователь | `root` (для продакшена лучше отдельный пользователь — см. ниже) |

Если venv у вас называется `venv`, а не `.venv`, отредактируйте `ExecStart` в каждом файле или переименуйте каталог.

Установка:

```bash
cd /root/metacleaner_bot
sudo cp deploy/systemd/metacleaner-admin.service /etc/systemd/system/
sudo cp deploy/systemd/metacleaner-worker.service /etc/systemd/system/
sudo cp deploy/systemd/metacleaner-bot.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable metacleaner-admin metacleaner-worker metacleaner-bot
sudo systemctl start metacleaner-admin metacleaner-worker metacleaner-bot
```

Проверка и логи:

```bash
sudo systemctl status metacleaner-admin metacleaner-worker metacleaner-bot
journalctl -u metacleaner-admin -f
journalctl -u metacleaner-worker -f
journalctl -u metacleaner-bot -f
```

Юниты ждут `redis.service` (`Wants=` / `After=`). Если Redis из Docker без systemd-юнита — уберите `After=redis.service` / `Wants=redis.service` или добавьте свой target.

**YouTube с VPS** часто даёт 429 — проще отключить режим ссылок в `.env` и перезапустить сервисы:

```bash
sed -i 's/^YOUTUBE_ENABLED=.*/YOUTUBE_ENABLED=false/' /root/metacleaner_bot/.env
sudo systemctl restart metacleaner-admin metacleaner-worker metacleaner-bot
```

**Не под root:** скопируйте те же шаблоны, замените `WorkingDirectory` и пути к `python` на домашний каталог пользователя (например `/home/metacleaner/metacleaner_bot`), добавьте в `[Service]` строки `User=metacleaner` и `Group=metacleaner`, выставьте права на каталог проекта и `.env` этому пользователю.

### Nginx: лимит логина (несколько воркеров Uvicorn)

In-process лимит `/admin/login` не делится между воркерами. В проде можно добавить:

```nginx
limit_req_zone $binary_remote_addr zone=admin_login:10m rate=10r/m;
location /admin/login {
    limit_req zone=admin_login burst=5 nodelay;
    proxy_pass http://127.0.0.1:8456;  # порт = ADMIN_PORT в .env на сервере
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

## 7. YouTube на VPS (HTTP 429, «Sign in to confirm you’re not a bot»)

YouTube часто режет **IP датацентров** и без «человеческой» сессии отвечает 429 или страницей входа. Это не баг бота, а политика доступа.

**Практично, по приоритету:**

1. **Обновить yt-dlp** на сервере (часто помогает на несколько недель):
   ```bash
   pip install -U yt-dlp
   ```
2. **Cookies из браузера** (Netscape): на ПК залогиниться в YouTube и экспортировать cookies (расширения вроде «Get cookies.txt LOCALLY»).
   - **Удобно:** админка → **Настройки** → блок **«YouTube — cookies»** → загрузить файл. Он сохранится в `secrets/youtube_cookies.txt` (каталог в `.gitignore`). Перезапуск Celery не обязателен.
   - **Либо** путь в `.env`: `YOUTUBE_COOKIES_FILE=/path/to/cookies.txt` — если файл существует, он **имеет приоритет** над загрузкой из админки.
   - Пути `secrets/...` и относительный `YOUTUBE_COOKIES_FILE` резолвятся от **корня репозитория** (каталог с `core/`), а не от `cwd` процесса — воркер всё равно подхватит cookies. При нестандартном запуске задайте `METACLEANER_ROOT=/абсолютный/путь/к/metacleaner_bot`.
   - В логе Celery при скачивании: строка `yt-dlp YouTube: cookies=... proxy=on|off` — так видно, что `--cookies` / `--proxy` реально подставлены.
   Cookies со временем протухают — обновляйте. **Не коммитьте** cookies в git.
3. **Резидентный HTTP(S) прокси** (домашний IP или платный residential), если cookies недостаточно:
   ```env
   YOUTUBE_PROXY=http://user:pass@host:port
   ```
4. **Выключить YouTube в боте** и оставить только загрузку файлов: в админке `youtube_enabled=false` или в настройках БД — пользователи скачивают ролик у себя и шлют файлом.
5. Юридически и по ToS YouTube: режим ссылки в боте — только для контента, на который у вас есть права (как у вас уже в тексте согласия).

## 8. Тесты

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

Интеграционные сценарии (админка, отмена, лимит логина): `tests/test_integration_deploy.py`.

Маркер `integration` стоит на `tests/test_integration_deploy.py`; обычный прогон `pytest tests/` уже включает эти тесты.

## 9. Чеклист перед выкладкой

- [ ] `alembic upgrade head` на прод-БД  
- [ ] Секреты только в `.env`, не в git  
- [ ] HTTPS + `ADMIN_COOKIE_SECURE=true`  
- [ ] Отдельный `ADMIN_SESSION_SECRET` (длинный random)  
- [ ] Бэкапы и мониторинг диска под `temp/` и логи  
