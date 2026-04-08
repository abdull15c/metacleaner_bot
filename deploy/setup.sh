#!/bin/bash
# MetaCleaner — полная установка на чистый Ubuntu сервер
# Запуск: bash deploy/setup.sh

set -e
echo "=== MetaCleaner Setup ==="

# 1. Системные зависимости
apt-get update
apt-get install -y \
    build-essential zlib1g-dev libncurses5-dev libgdbm-dev \
    libnss3-dev libssl-dev libreadline-dev libffi-dev \
    libsqlite3-dev wget libbz2-dev software-properties-common \
    ffmpeg redis-server curl

# 2. Node.js 20 (нужен для yt-dlp YouTube)
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs
echo "Node.js: $(node --version)"

# 3. Python 3.11 (если нет)
if ! command -v python3.11 &> /dev/null; then
    echo "Устанавливаем Python 3.11..."
    cd /tmp
    wget -q https://www.python.org/ftp/python/3.11.9/Python-3.11.9.tgz
    tar -xf Python-3.11.9.tgz
    cd Python-3.11.9
    ./configure --enable-optimizations --quiet
    make -j$(nproc)
    make altinstall
    cd ~
fi
echo "Python: $(python3.11 --version)"

# 4. Virtual environment
cd /root/metacleaner_bot
python3.11 -m venv .venv
source .venv/bin/activate

# 5. Python зависимости
pip install --upgrade pip --quiet
pip install bcrypt==4.0.1 --quiet  # фикс совместимости с passlib
pip install -r requirements.txt --quiet
pip install -U yt-dlp --quiet      # всегда свежая версия

# 6. yt-dlp JS runtime скрипт
mkdir -p ~/.config/yt-dlp
curl -sL https://github.com/yt-dlp/yt-dlp/raw/master/yt_dlp/extractor/_ytdlp_youtube_ext.js \
    -o ~/.config/yt-dlp/youtube_ext.js
echo "yt-dlp: $(.venv/bin/yt-dlp --version)"

# 7. .env из примера
if [ ! -f .env ]; then
    cp .env.example .env
    echo "СОЗДАН .env — заполни BOT_TOKEN и ADMIN_SECRET_KEY!"
fi

# 8. Структура папок
mkdir -p temp/uploads temp/processed logs secrets

echo "=== Готово! ==="
echo "Следующие шаги:"
echo "1. nano .env  (заполни BOT_TOKEN и ADMIN_SECRET_KEY)"
echo "2. source .venv/bin/activate"
echo "3. python -m alembic upgrade head"
echo "4. python scripts/seed_settings.py"
echo "5. python scripts/create_admin.py"
echo "6. bash deploy/systemd.sh"
