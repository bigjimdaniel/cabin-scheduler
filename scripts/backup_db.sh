#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${1:-/var/backups/cabin-scheduler}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "${BACKUP_DIR}"
pg_dump \
  --format=custom \
  --file="${BACKUP_DIR}/cabin-scheduler-${TIMESTAMP}.dump" \
  "${POSTGRES_DB:-cabin_scheduler}"
