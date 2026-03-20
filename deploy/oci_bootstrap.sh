#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/cabin-scheduler}"
APP_USER="${APP_USER:-ubuntu}"
APP_GROUP="${APP_GROUP:-www-data}"
POSTGRES_DB="${POSTGRES_DB:-cabin_scheduler}"
POSTGRES_USER="${POSTGRES_USER:-cabin_scheduler}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root or with sudo."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y \
  build-essential \
  curl \
  git \
  libpq-dev \
  nginx \
  postgresql \
  postgresql-contrib \
  python3 \
  python3-venv \
  unzip

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

if [[ -x /root/.local/bin/uv && ! -x /usr/local/bin/uv ]]; then
  ln -s /root/.local/bin/uv /usr/local/bin/uv
fi

if [[ -x /root/.local/bin/uvx && ! -x /usr/local/bin/uvx ]]; then
  ln -s /root/.local/bin/uvx /usr/local/bin/uvx
fi

install -d -o "${APP_USER}" -g "${APP_GROUP}" "${APP_DIR}"

sudo -u postgres psql <<SQL
DO \$\$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${POSTGRES_USER}') THEN
      CREATE ROLE ${POSTGRES_USER} LOGIN PASSWORD '${POSTGRES_PASSWORD}';
   ELSE
      ALTER ROLE ${POSTGRES_USER} WITH LOGIN PASSWORD '${POSTGRES_PASSWORD}';
   END IF;
END
\$\$;
SQL

if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname = '${POSTGRES_DB}'" | grep -q 1; then
  sudo -u postgres createdb --owner="${POSTGRES_USER}" "${POSTGRES_DB}"
fi

echo "Bootstrap complete."
echo "Next:"
echo "1. Place the application code in ${APP_DIR}"
echo "2. Copy deploy/prod.env.example to ${APP_DIR}/.env and fill in secrets"
echo "3. Run deploy/oci_deploy.sh"
