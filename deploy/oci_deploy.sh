#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/cabin-scheduler}"
APP_USER="${APP_USER:-ubuntu}"
APP_GROUP="${APP_GROUP:-www-data}"
SERVICE_NAME="${SERVICE_NAME:-cabin-scheduler}"
ENV_FILE="${ENV_FILE:-${APP_DIR}/.env}"
NGINX_SITE="${NGINX_SITE:-/etc/nginx/sites-available/${SERVICE_NAME}}"
FORCE_NGINX_SITE_REFRESH="${FORCE_NGINX_SITE_REFRESH:-false}"

if [[ ! -d "${APP_DIR}" ]]; then
  echo "Application directory ${APP_DIR} does not exist."
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Environment file ${ENV_FILE} does not exist."
  exit 1
fi

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root or with sudo."
  exit 1
fi

set -a
source "${ENV_FILE}"
set +a

export PATH="/usr/local/bin:${HOME}/.local/bin:/root/.local/bin:${PATH}"

cd "${APP_DIR}"
chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}"
sudo -u "${APP_USER}" uv sync
sudo -u "${APP_USER}" uv run python manage.py migrate
sudo -u "${APP_USER}" uv run python manage.py collectstatic --noinput

if [[ -n "${DJANGO_SUPERUSER_USERNAME:-}" && -n "${DJANGO_SUPERUSER_EMAIL:-}" && -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]]; then
  sudo -u "${APP_USER}" uv run python manage.py shell -c \
    "from django.contrib.auth import get_user_model; User=get_user_model(); username='${DJANGO_SUPERUSER_USERNAME}'; email='${DJANGO_SUPERUSER_EMAIL}'; password='${DJANGO_SUPERUSER_PASSWORD}'; user, created = User.objects.get_or_create(username=username, defaults={'email': email, 'is_staff': True, 'is_superuser': True}); user.email = email; user.is_staff = True; user.is_superuser = True; user.set_password(password); user.save()"
fi

install -m 0644 deploy/gunicorn.service "/etc/systemd/system/${SERVICE_NAME}.service"
sed -i "s#User=ubuntu#User=${APP_USER}#" "/etc/systemd/system/${SERVICE_NAME}.service"
sed -i "s#WorkingDirectory=/opt/cabin-scheduler#WorkingDirectory=${APP_DIR}#" "/etc/systemd/system/${SERVICE_NAME}.service"
sed -i "s#EnvironmentFile=/opt/cabin-scheduler/.env#EnvironmentFile=${ENV_FILE}#" "/etc/systemd/system/${SERVICE_NAME}.service"
sed -i "s#ExecStart=/opt/cabin-scheduler/.venv/bin/gunicorn#ExecStart=${APP_DIR}/.venv/bin/gunicorn#" "/etc/systemd/system/${SERVICE_NAME}.service"

SKIP_NGINX_SITE_REFRESH=false
if [[ -f "${NGINX_SITE}" && "${FORCE_NGINX_SITE_REFRESH}" != "true" ]]; then
  if grep -Eq 'listen 443|ssl_certificate|managed by Certbot' "${NGINX_SITE}"; then
    SKIP_NGINX_SITE_REFRESH=true
  fi
fi

if [[ "${SKIP_NGINX_SITE_REFRESH}" == "true" ]]; then
  echo "Preserving existing HTTPS-enabled Nginx site at ${NGINX_SITE}."
else
  install -m 0644 deploy/nginx.conf "${NGINX_SITE}"
  if [[ -n "${PUBLIC_SERVER_NAME:-}" ]]; then
    sed -i "s/server_name _;/server_name ${PUBLIC_SERVER_NAME};/" "${NGINX_SITE}"
  fi
fi

ln -sf "${NGINX_SITE}" "/etc/nginx/sites-enabled/${SERVICE_NAME}"
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"
systemctl enable --now nginx
systemctl restart nginx

echo "Deployment complete."
echo "App directory: ${APP_DIR}"
echo "Service: ${SERVICE_NAME}"
