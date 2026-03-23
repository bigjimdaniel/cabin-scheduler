#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/cabin-scheduler}"
APP_USER="${APP_USER:-ubuntu}"
APP_GROUP="${APP_GROUP:-www-data}"
SERVICE_NAME="${SERVICE_NAME:-cabin-scheduler}"
ENV_FILE="${ENV_FILE:-${APP_DIR}/.env}"
GIT_REMOTE="${GIT_REMOTE:-origin}"
GIT_REF="${GIT_REF:-main}"
PUBLIC_SERVER_NAME="${PUBLIC_SERVER_NAME:-_}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root or with sudo."
  exit 1
fi

if [[ ! -d "${APP_DIR}/.git" ]]; then
  echo "${APP_DIR} is not a git checkout."
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Environment file ${ENV_FILE} does not exist."
  exit 1
fi

export PATH="/usr/local/bin:${HOME}/.local/bin:/root/.local/bin:${PATH}"

cd "${APP_DIR}"
chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}"
sudo -u "${APP_USER}" git fetch "${GIT_REMOTE}"
sudo -u "${APP_USER}" git checkout "${GIT_REF}"
sudo -u "${APP_USER}" git pull --ff-only "${GIT_REMOTE}" "${GIT_REF}"

APP_DIR="${APP_DIR}" \
APP_USER="${APP_USER}" \
APP_GROUP="${APP_GROUP}" \
SERVICE_NAME="${SERVICE_NAME}" \
ENV_FILE="${ENV_FILE}" \
PUBLIC_SERVER_NAME="${PUBLIC_SERVER_NAME}" \
bash "${APP_DIR}/deploy/oci_deploy.sh"
