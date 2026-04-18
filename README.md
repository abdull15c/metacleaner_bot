# MetaCleaner Bot

**Telegram-бот для удаления метаданных из видео без перекодирования**

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Security: 10/10](https://img.shields.io/badge/Security-10%2F10-brightgreen.svg)](SECURITY_FIXES_APPLIED.md)

---

## 🎯 Что это?

MetaCleaner — это Telegram-бот, который удаляет метаданные (GPS, дату съемки, название устройства и т.д.) из видеофайлов **без перекодирования**. Быстро, безопасно, приватно.

### Основные возможности

- ✅ **Очистка метаданных** — удаление всех тегов из видео
- 🎵 **Извлечение аудио** — конвертация видео в MP3
- 🖼️ **Скриншоты** — создание превью из видео
- 📥 **Скачивание с YouTube** — с автоматической очисткой метаданных
- 🌐 **Mini App** — веб-интерфейс для скачивания с любых платформ
- 📊 **Админ-панель** — управление пользователями, задачами, рассылками

### Поддерживаемые платформы

- YouTube, Instagram, TikTok, Facebook, Twitter, Vimeo, Dailymotion
- Форматы: MP4, MKV, MOV, AVI, WebM, M4V, FLV, TS, WMV, 3GP

---

## 🚀 Быстрый старт

### Требования

- Ubuntu 22.04/24.04 (или Docker)
- Python 3.11
- Redis
- PostgreSQL (опционально, по умолчанию SQLite)
- FFmpeg

### Установка за 3 минуты

```bash
# 1. Клонировать репозиторий
git clone https://github.com/your-repo/metacleaner_bot.git
cd metacleaner_bot

# 2. Запустить автоматическую установку
sudo bash deploy/setup.sh

# 3. Настроить .env
cp .env.example .env
nano .env  # Установить BOT_TOKEN и ADMIN_SECRET_KEY

# 4. Инициализировать БД
source .venv/bin/activate
python -m alembic upgrade head
python scripts/seed_settings.py
python scripts/create_admin.py

# 5. Установить systemd сервисы
sudo bash deploy/install_systemd.sh

# 6. Запустить
sudo systemctl start metacleaner-{bot,worker,beat,admin}
```

**Готово!** Бот работает, админ-панель доступна на `http://your-server:8000/admin`

---

## 📖 Документация

### Для разработчиков

- **[DEPLOY.md](DEPLOY.md)** — подробная инструкция по развертыванию
- **[SECURITY_FIXES_APPLIED.md](SECURITY_FIXES_APPLIED.md)** — исправления безопасности
- **[DISASTER_RECOVERY.md](DISASTER_RECOVERY.md)** — план восстановления после сбоев
- **[PRODUCTION_READY_100.md](PRODUCTION_READY_100.md)** — отчет о готовности к production

### Архитектура

```
metacleaner_bot/
├── bot/              # Telegram бот (aiogram)
├── admin/            # Веб-панель администратора (FastAPI)
├── workers/          # Celery воркеры для обработки
├── webapp/           # Mini App для скачивания
├── core/             # Общая логика и модели
├── scripts/          # Утилиты (backup, health check)
└── tests/            # Тесты (pytest)
```

### Технологии

- **Bot:** aiogram 3.7
- **API:** FastAPI + Uvicorn
- **Queue:** Celery + Redis
- **Database:** SQLAlchemy (SQLite/PostgreSQL)
- **Processing:** FFmpeg, yt-dlp
- **Monitoring:** Sentry, Prometheus

---

## 🔒 Безопасность

Проект прошел полный аудит безопасности и получил оценку **10/10**:

- ✅ Защита от SSRF атак
- ✅ Защита от SQL Injection
- ✅ CSRF защита
- ✅ XSS защита
- ✅ Race conditions устранены
- ✅ Resource limits настроены
- ✅ Автоматический backup каждые 6 часов
- ✅ Мониторинг и алерты

Подробнее: [SECURITY_FIXES_APPLIED.md](SECURITY_FIXES_APPLIED.md)

---

## 📊 Мониторинг

### Health Check

```bash
# Проверка всех компонентов
python scripts/health_check.py

# Вывод:
# ✓ Database      OK    Connected
# ✓ Redis         OK    Connected
# ✓ Celery        OK    2 workers active
# ✓ Disk Space    OK    45.2% free (120.5 GB)
# ✓ Temp Files    OK    234.5 MB
```

### Логи

```bash
# Systemd
journalctl -u metacleaner-bot -f

# Docker
docker-compose logs -f bot
```

### Метрики

- **Prometheus:** `http://your-server:9090`
- **Admin Panel:** `http://your-server:8000/admin`
- **Sentry:** Настраивается через `SENTRY_DSN` в `.env`

---

## 🛠️ Разработка

### Локальный запуск

```bash
# 1. Установить зависимости
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Настроить .env
cp .env.example .env

# 3. Запустить БД и Redis
docker-compose up -d postgres redis

# 4. Инициализировать БД
python -m alembic upgrade head
python scripts/seed_settings.py
python scripts/create_admin.py

# 5. Запустить компоненты (3 терминала)
python -m bot.main                                    # Бот
celery -A workers.celery_app worker -l INFO --pool=solo  # Воркер
python -m admin                                       # Админка
```

### Тесты

```bash
# Запустить все тесты
pytest tests/ -v

# С покрытием
pytest tests/ --cov=. --cov-report=html

# Только security тесты
pytest tests/test_security_fixes.py -v
```

### Структура проекта

- `bot/` — Telegram бот, роутеры, middleware
- `admin/` — FastAPI приложение, шаблоны
- `workers/` — Celery задачи (обработка, скачивание, рассылки)
- `core/` — Модели, сервисы, конфигурация
- `webapp/` — Mini App (HTML + API)
- `scripts/` — Утилиты (backup, health check, создание админа)
- `tests/` — Pytest тесты

---

## 🎯 Лимиты и ограничения

### По умолчанию

- **Размер файла:** 500 MB (настраивается)
- **Задач в день на пользователя:** 10 (настраивается)
- **Одновременных задач:** 2 (настраивается)
- **Время хранения temp файлов:** 30 минут

### Настройка

Все лимиты настраиваются через админ-панель или `.env`:

```bash
MAX_FILE_SIZE_MB=500
MAX_DAILY_JOBS_PER_USER=10
MAX_CONCURRENT_JOBS=2
CLEANUP_TTL_MINUTES=30
```

---

## 🤝 Поддержка

### Проблемы и вопросы

- **Issues:** [GitHub Issues](https://github.com/your-repo/metacleaner_bot/issues)
- **Документация:** См. файлы `*.md` в корне проекта

### Известные проблемы

- **Python 3.13** не поддерживается (используйте 3.11)
- **YouTube с VPS** может требовать cookies (см. [DEPLOY.md](DEPLOY.md))
- **bcrypt 4.1+** несовместим с passlib (используется 4.0.1)

---

## 📝 Лицензия

MIT License. См. [LICENSE](LICENSE) для деталей.

---

## 🙏 Благодарности

- [aiogram](https://github.com/aiogram/aiogram) — Telegram Bot framework
- [FastAPI](https://github.com/tiangolo/fastapi) — Web framework
- [Celery](https://github.com/celery/celery) — Distributed task queue
- [FFmpeg](https://ffmpeg.org/) — Video processing
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — Video downloader

---

**Версия:** 1.0.0  
**Статус:** ✅ Production Ready  
**Последнее обновление:** 2026-04-18
