FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg nodejs npm curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/temp/uploads /app/temp/processed /app/logs \
    && useradd --create-home --shell /usr/sbin/nologin metacleaner \
    && chown -R metacleaner:metacleaner /app

ENV PYTHONPATH=/app

USER metacleaner
