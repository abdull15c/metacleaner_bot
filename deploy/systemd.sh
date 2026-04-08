#!/bin/bash
# Установка systemd сервисов для MetaCleaner

PROJECT_DIR=/root/metacleaner_bot
VENV=$PROJECT_DIR/.venv
NODE_PATH=$(which node)

# Бот
cat > /etc/systemd/system/metacleaner-bot.service << EOF
[Unit]
Description=MetaCleaner Bot
After=network.target redis.service

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$VENV/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$VENV/bin/python -m bot.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Воркер
cat > /etc/systemd/system/metacleaner-worker.service << EOF
[Unit]
Description=MetaCleaner Celery Worker
After=network.target redis.service

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$VENV/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$VENV/bin/celery -A workers.celery_app worker --loglevel=info -Q video,cleanup,broadcast --pool=solo
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Админка
cat > /etc/systemd/system/metacleaner-admin.service << EOF
[Unit]
Description=MetaCleaner Admin Panel
After=network.target redis.service

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$VENV/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$VENV/bin/python -m admin
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable metacleaner-bot metacleaner-worker metacleaner-admin
systemctl start metacleaner-bot metacleaner-worker metacleaner-admin
systemctl status metacleaner-bot metacleaner-worker metacleaner-admin --no-pager
echo "=== Сервисы запущены ==="
