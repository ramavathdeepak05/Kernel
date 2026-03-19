#!/bin/bash
# ALIS Database Backup Script
# Run via cron: 0 3 * * * /opt/alis/infra/backup/backup.sh >> /var/log/alis/backup.log 2>&1

set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${ALIS_BACKUP_DIR:-/var/backups/alis}"
DB_NAME="${POSTGRES_DB:-alis}"
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_USER="${POSTGRES_USER:-postgres}"
export PGPASSWORD="${POSTGRES_PASSWORD:-postgres}"

MINIO_BUCKET="${MINIO_BACKUP_BUCKET:-alis-backups}"
MINIO_ALIAS="${MINIO_ALIAS:-alisminio}"

DAILY_FILE="${BACKUP_DIR}/daily/alis_${TIMESTAMP}.dump"
WEEKLY_FILE="${BACKUP_DIR}/weekly/alis_$(date +%Y_W%V).dump"

# Ensure directories exist
mkdir -p "${BACKUP_DIR}/daily" "${BACKUP_DIR}/weekly"

echo "[${TIMESTAMP}] Starting ALIS backup..."

# Daily backup (custom format, compressed)
pg_dump \
  --host="${DB_HOST}" \
  --port="${DB_PORT}" \
  --username="${DB_USER}" \
  --format=custom \
  --compress=9 \
  --file="${DAILY_FILE}" \
  "${DB_NAME}"

echo "[${TIMESTAMP}] pg_dump complete: ${DAILY_FILE}"

# Upload to MinIO
if command -v mc &> /dev/null; then
  mc cp "${DAILY_FILE}" "${MINIO_ALIAS}/${MINIO_BUCKET}/daily/"
  echo "[${TIMESTAMP}] Uploaded to MinIO: ${MINIO_BUCKET}/daily/"
else
  echo "[${TIMESTAMP}] WARNING: mc (MinIO client) not found — skipping upload"
fi

# Weekly backup (every Sunday)
if [ "$(date +%u)" = "7" ]; then
  cp "${DAILY_FILE}" "${WEEKLY_FILE}"
  if command -v mc &> /dev/null; then
    mc cp "${WEEKLY_FILE}" "${MINIO_ALIAS}/${MINIO_BUCKET}/weekly/"
    echo "[${TIMESTAMP}] Weekly backup uploaded"
  fi
fi

# Prune daily backups older than 30 days
find "${BACKUP_DIR}/daily" -name "*.dump" -mtime +30 -delete
echo "[${TIMESTAMP}] Pruned old daily backups"

# Prune weekly backups older than 90 days
find "${BACKUP_DIR}/weekly" -name "*.dump" -mtime +90 -delete

echo "[${TIMESTAMP}] Backup complete."
