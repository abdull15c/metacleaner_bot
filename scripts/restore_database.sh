#!/bin/bash
# Восстановление базы данных из backup
# Использование: ./restore_database.sh <backup_file>

set -e

if [ $# -eq 0 ]; then
    echo "Usage: $0 <backup_file.sql.gz>"
    echo ""
    echo "Available backups:"
    ls -lh /var/backups/metacleaner/metacleaner_*.sql.gz 2>/dev/null || echo "  No backups found"
    exit 1
fi

BACKUP_FILE="$1"
DB_NAME="${POSTGRES_DB:-metacleaner}"
DB_USER="${POSTGRES_USER:-metacleaner}"
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"

echo "=== MetaCleaner Database Restore ==="
echo "Backup file: $BACKUP_FILE"
echo "Database: $DB_NAME"
echo "Host: $DB_HOST:$DB_PORT"
echo ""

# Проверка существования файла
if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file not found: $BACKUP_FILE"
    exit 1
fi

# Проверка целостности
echo "Verifying backup integrity..."
if ! gunzip -t "$BACKUP_FILE"; then
    echo "ERROR: Backup file is corrupted!"
    exit 1
fi
echo "✓ Backup integrity verified"

# Подтверждение
echo ""
echo "WARNING: This will DROP and recreate the database!"
echo "All current data will be lost."
read -p "Are you sure you want to continue? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Restore cancelled."
    exit 0
fi

# Остановка сервисов
echo ""
echo "Stopping services..."
if command -v docker-compose &> /dev/null; then
    docker-compose stop bot worker admin beat || true
elif command -v systemctl &> /dev/null; then
    systemctl stop metacleaner-bot metacleaner-worker metacleaner-admin || true
fi

# Ожидание завершения активных соединений
sleep 5

# Восстановление
echo ""
echo "Restoring database..."

# Удаление существующей БД и создание новой
PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres <<EOF
DROP DATABASE IF EXISTS $DB_NAME;
CREATE DATABASE $DB_NAME;
EOF

# Восстановление данных
gunzip -c "$BACKUP_FILE" | PGPASSWORD="$POSTGRES_PASSWORD" psql \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --quiet

echo "✓ Database restored successfully"

# Запуск миграций (на всякий случай)
echo ""
echo "Running migrations..."
cd "$(dirname "$0")/.."
python -m alembic upgrade head

# Перезапуск сервисов
echo ""
echo "Starting services..."
if command -v docker-compose &> /dev/null; then
    docker-compose start bot worker admin beat
elif command -v systemctl &> /dev/null; then
    systemctl start metacleaner-bot metacleaner-worker metacleaner-admin
fi

echo ""
echo "=== Restore completed successfully ==="
echo "Restored from: $BACKUP_FILE"
echo "Timestamp: $(date)"
