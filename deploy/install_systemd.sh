#!/bin/bash
# MetaCleaner — унифицированная установка systemd сервисов
# Запуск от root: bash deploy/install_systemd.sh

set -e

echo "=== MetaCleaner Systemd Installation ==="

# Проверка что запущено от root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Запустите от root: sudo bash deploy/install_systemd.sh"
    exit 1
fi

# Определение пути к проекту
PROJECT_DIR="${PROJECT_DIR:-/opt/metacleaner_bot}"
if [ ! -d "$PROJECT_DIR" ]; then
    echo "❌ Директория проекта не найдена: $PROJECT_DIR"
    echo "   Установите переменную: PROJECT_DIR=/path/to/project bash deploy/install_systemd.sh"
    exit 1
fi

echo "Директория проекта: $PROJECT_DIR"

# Создание непривилегированного пользователя
if ! id -u metacleaner &>/dev/null; then
    echo "Создание пользователя metacleaner..."
    useradd --system --no-create-home --shell /bin/false metacleaner
fi

# Права на директории
echo "Настройка прав доступа..."
chown -R metacleaner:metacleaner "$PROJECT_DIR"
chmod 750 "$PROJECT_DIR"
chmod 640 "$PROJECT_DIR/.env"

# Создание директорий для данных
mkdir -p "$PROJECT_DIR/temp/uploads" "$PROJECT_DIR/temp/processed" "$PROJECT_DIR/logs"
chown -R metacleaner:metacleaner "$PROJECT_DIR/temp" "$PROJECT_DIR/logs"
chmod 750 "$PROJECT_DIR/temp" "$PROJECT_DIR/logs"

# Копирование systemd unit файлов
echo "Установка systemd сервисов..."

# Bot service
cat > /etc/systemd/system/metacleaner-bot.service <<EOF
[Unit]
Description=MetaCleaner Telegram Bot
After=network.target redis.service postgresql.service
Wants=redis.service

[Service]
Type=simple
User=metacleaner
Group=metacleaner
WorkingDirectory=$PROJECT_DIR

# Изоляция и безопасность
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
NoNewPrivileges=yes
ReadWritePaths=$PROJECT_DIR/temp $PROJECT_DIR/logs

# Ограничения ресурсов
MemoryLimit=1G
CPUQuota=100%
TasksMax=100

# Переменные окружения
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=$PROJECT_DIR/.env

ExecStart=$PROJECT_DIR/.venv/bin/python -m bot.main

# Graceful shutdown
TimeoutStopSec=30
KillMode=mixed
KillSignal=SIGTERM

Restart=on-failure
RestartSec=10
StartLimitBurst=5
StartLimitIntervalSec=300

[Install]
WantedBy=multi-user.target
EOF

# Worker service
cat > /etc/systemd/system/metacleaner-worker.service <<EOF
[Unit]
Description=MetaCleaner Celery Worker
After=network.target redis.service postgresql.service
Wants=redis.service

[Service]
Type=simple
User=metacleaner
Group=metacleaner
WorkingDirectory=$PROJECT_DIR

# Изоляция и безопасность
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
NoNewPrivileges=yes
ReadWritePaths=$PROJECT_DIR/temp $PROJECT_DIR/logs

# Ограничения ресурсов (больше для обработки видео)
MemoryLimit=4G
CPUQuota=200%
TasksMax=200

# Переменные окружения
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=$PROJECT_DIR/.env

ExecStart=$PROJECT_DIR/.venv/bin/celery -A workers.celery_app worker -l INFO -c 2 -Q video,broadcast,cleanup,celery

# Graceful shutdown
TimeoutStopSec=60
KillMode=mixed
KillSignal=SIGTERM

Restart=on-failure
RestartSec=10
StartLimitBurst=5
StartLimitIntervalSec=300

[Install]
WantedBy=multi-user.target
EOF

# Beat service
cat > /etc/systemd/system/metacleaner-beat.service <<EOF
[Unit]
Description=MetaCleaner Celery Beat Scheduler
After=network.target redis.service
Wants=redis.service

[Service]
Type=simple
User=metacleaner
Group=metacleaner
WorkingDirectory=$PROJECT_DIR

# Изоляция и безопасность
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
NoNewPrivileges=yes
ReadWritePaths=$PROJECT_DIR/logs

# Ограничения ресурсов
MemoryLimit=256M
CPUQuota=25%
TasksMax=50

# Переменные окружения
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=$PROJECT_DIR/.env

ExecStart=$PROJECT_DIR/.venv/bin/celery -A workers.celery_app beat -l INFO

# Graceful shutdown
TimeoutStopSec=30
KillMode=mixed
KillSignal=SIGTERM

Restart=on-failure
RestartSec=10
StartLimitBurst=3
StartLimitIntervalSec=300

[Install]
WantedBy=multi-user.target
EOF

# Admin service
cat > /etc/systemd/system/metacleaner-admin.service <<EOF
[Unit]
Description=MetaCleaner Admin Panel
After=network.target redis.service postgresql.service
Wants=redis.service

[Service]
Type=simple
User=metacleaner
Group=metacleaner
WorkingDirectory=$PROJECT_DIR

# Изоляция и безопасность
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
NoNewPrivileges=yes
ReadWritePaths=$PROJECT_DIR/temp $PROJECT_DIR/logs

# Ограничения ресурсов
MemoryLimit=512M
CPUQuota=50%
TasksMax=100

# Переменные окружения
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=$PROJECT_DIR/.env

ExecStart=$PROJECT_DIR/.venv/bin/python -m admin

# Graceful shutdown
TimeoutStopSec=30
KillMode=mixed
KillSignal=SIGTERM

Restart=on-failure
RestartSec=10
StartLimitBurst=5
StartLimitIntervalSec=300

[Install]
WantedBy=multi-user.target
EOF

# Перезагрузка systemd
echo "Перезагрузка systemd daemon..."
systemctl daemon-reload

# Включение автозапуска
echo "Включение автозапуска сервисов..."
systemctl enable metacleaner-bot.service
systemctl enable metacleaner-worker.service
systemctl enable metacleaner-beat.service
systemctl enable metacleaner-admin.service

echo ""
echo "✅ Systemd сервисы установлены!"
echo ""
echo "Управление сервисами:"
echo "  systemctl start metacleaner-bot"
echo "  systemctl start metacleaner-worker"
echo "  systemctl start metacleaner-beat"
echo "  systemctl start metacleaner-admin"
echo ""
echo "Или все сразу:"
echo "  systemctl start metacleaner-{bot,worker,beat,admin}"
echo ""
echo "Проверка статуса:"
echo "  systemctl status metacleaner-bot"
echo ""
echo "Логи:"
echo "  journalctl -u metacleaner-bot -f"
echo ""
echo "Остановка:"
echo "  systemctl stop metacleaner-{bot,worker,beat,admin}"
