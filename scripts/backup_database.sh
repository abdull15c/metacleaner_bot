#!/bin/bash
# Автоматический backup PostgreSQL базы данных
# Запускать через cron каждые 6 часов

set -e

# Конфигурация
BACKUP_DIR="${BACKUP_DIR:-/var/backups/metacleaner}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
DB_NAME="${POSTGRES_DB:-metacleaner}"
DB_USER="${POSTGRES_USER:-metacleaner}"
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"

# S3 конфигурация (опционально)
S3_BUCKET="${S3_BACKUP_BUCKET:-}"
S3_PREFIX="${S3_BACKUP_PREFIX:-metacleaner/}"

# Создать директорию для backup
mkdir -p "$BACKUP_DIR"

# Имя файла с timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/metacleaner_${TIMESTAMP}.sql.gz"
BACKUP_LOG="$BACKUP_DIR/backup_${TIMESTAMP}.log"

echo "=== MetaCleaner Database Backup ===" | tee "$BACKUP_LOG"
echo "Started at: $(date)" | tee -a "$BACKUP_LOG"
echo "Database: $DB_NAME" | tee -a "$BACKUP_LOG"
echo "Backup file: $BACKUP_FILE" | tee -a "$BACKUP_LOG"

# Проверка доступности PostgreSQL
if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" > /dev/null 2>&1; then
    echo "ERROR: PostgreSQL is not available at $DB_HOST:$DB_PORT" | tee -a "$BACKUP_LOG"
    exit 1
fi

# Создание backup
echo "Creating backup..." | tee -a "$BACKUP_LOG"
if PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --format=plain \
    --no-owner \
    --no-acl \
    --verbose \
    2>> "$BACKUP_LOG" | gzip > "$BACKUP_FILE"; then
    
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "Backup created successfully: $BACKUP_SIZE" | tee -a "$BACKUP_LOG"
else
    echo "ERROR: Backup failed!" | tee -a "$BACKUP_LOG"
    exit 1
fi

# Проверка целостности backup
echo "Verifying backup integrity..." | tee -a "$BACKUP_LOG"
if gunzip -t "$BACKUP_FILE" 2>> "$BACKUP_LOG"; then
    echo "Backup integrity verified" | tee -a "$BACKUP_LOG"
else
    echo "ERROR: Backup file is corrupted!" | tee -a "$BACKUP_LOG"
    exit 1
fi

# Загрузка в S3 (если настроено)
if [ -n "$S3_BUCKET" ]; then
    echo "Uploading to S3: s3://$S3_BUCKET/$S3_PREFIX" | tee -a "$BACKUP_LOG"
    
    if command -v aws &> /dev/null; then
        if aws s3 cp "$BACKUP_FILE" "s3://$S3_BUCKET/$S3_PREFIX$(basename $BACKUP_FILE)" 2>> "$BACKUP_LOG"; then
            echo "Uploaded to S3 successfully" | tee -a "$BACKUP_LOG"
        else
            echo "WARNING: S3 upload failed" | tee -a "$BACKUP_LOG"
        fi
    else
        echo "WARNING: AWS CLI not installed, skipping S3 upload" | tee -a "$BACKUP_LOG"
    fi
fi

# Удаление старых backup (старше RETENTION_DAYS дней)
echo "Cleaning up old backups (older than $RETENTION_DAYS days)..." | tee -a "$BACKUP_LOG"
find "$BACKUP_DIR" -name "metacleaner_*.sql.gz" -type f -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "backup_*.log" -type f -mtime +$RETENTION_DAYS -delete

REMAINING_BACKUPS=$(find "$BACKUP_DIR" -name "metacleaner_*.sql.gz" -type f | wc -l)
echo "Remaining backups: $REMAINING_BACKUPS" | tee -a "$BACKUP_LOG"

# Отправка алерта при ошибке
if [ $? -ne 0 ]; then
    # Отправить webhook уведомление
    if [ -n "$ALERT_WEBHOOK_URL" ]; then
        curl -X POST "$ALERT_WEBHOOK_URL" \
            -H "Content-Type: application/json" \
            -d "{\"level\":\"critical\",\"message\":\"Database backup failed\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" \
            2>> "$BACKUP_LOG" || true
    fi
fi

echo "Completed at: $(date)" | tee -a "$BACKUP_LOG"
echo "======================================" | tee -a "$BACKUP_LOG"

# Вывод статистики
echo ""
echo "Backup Statistics:"
echo "  Total backups: $REMAINING_BACKUPS"
echo "  Latest backup: $BACKUP_FILE ($BACKUP_SIZE)"
echo "  Disk usage: $(du -sh $BACKUP_DIR | cut -f1)"
