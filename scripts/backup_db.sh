#!/usr/bin/env bash
# Снимок PostgreSQL в ./backups/ (запуск на сервере рядом с БД).
# Использование: export DATABASE_URL=postgresql://user:pass@localhost:5432/metacleaner
#   ./scripts/backup_db.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/backups"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
OUT="$ROOT/backups/metacleaner_${STAMP}.sql.gz"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "Set DATABASE_URL (sync URL for pg_dump), e.g. postgresql://metacleaner:pass@127.0.0.1:5432/metacleaner" >&2
  exit 1
fi

# pg_dump ожидает libpq URL без +asyncpg
URL="${DATABASE_URL//+asyncpg/}"
echo "Writing $OUT"
pg_dump "$URL" | gzip -9 > "$OUT"
echo "Done: $OUT"
