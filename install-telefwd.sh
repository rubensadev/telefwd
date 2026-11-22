#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/rubensadev/telefwd.git"
APP_DIR="/opt/telefwd"
VENV_DIR="${APP_DIR}/.venv"
SERVICE_USER="telefwd"
SERVICE_FILE="/etc/systemd/system/telefwd.service"

if [[ $EUID -ne 0 ]]; then
  echo "Please run this script as root (e.g., sudo bash $0)"
  exit 1
fi

echo "[1/6] Installing git, curl, and uv..."
apt-get update -qq
apt-get install -y -qq git curl ca-certificates

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/usr/local/bin" sh
fi

echo "[2/6] Creating service user '${SERVICE_USER}' (if missing)..."
if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd -r -s /usr/sbin/nologin -d "${APP_DIR}" "${SERVICE_USER}"
fi

echo "[3/6] Cloning or updating repository in ${APP_DIR}..."
if [[ -d "${APP_DIR}/.git" ]]; then
  git -C "${APP_DIR}" pull --ff-only
else
  git clone "${REPO_URL}" "${APP_DIR}"
fi
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}"

echo "[4/6] Setting up .venv and installing dependencies with uv..."
if [[ -f "${APP_DIR}/uv.lock" || -f "${APP_DIR}/pyproject.toml" ]]; then
  sudo -u "${SERVICE_USER}" env UV_CACHE_DIR="${APP_DIR}/.uv-cache" uv sync --project "${APP_DIR}" --no-dev
else
  sudo -u "${SERVICE_USER}" env UV_CACHE_DIR="${APP_DIR}/.uv-cache" uv venv "${VENV_DIR}"
  if [[ -f "${APP_DIR}/requirements.txt" ]]; then
    sudo -u "${SERVICE_USER}" env UV_CACHE_DIR="${APP_DIR}/.uv-cache" uv pip install --python "${VENV_DIR}/bin/python" -r "${APP_DIR}/requirements.txt"
  fi
fi

echo "[5/6] Writing systemd service unit to ${SERVICE_FILE}..."
cat > "${SERVICE_FILE}" <<'EOF'
[Unit]
Description=Telefwd Telegram-to-IRC Relay Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=telefwd
Group=telefwd
WorkingDirectory=/opt/telefwd
EnvironmentFile=-/opt/telefwd/.env
ExecStart=/opt/telefwd/.venv/bin/python /opt/telefwd/main.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=telefwd

# Basic hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/telefwd

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload

echo "[6/6] Setup complete."
echo ""
echo "Next steps:"
echo "  1. Create/edit ${APP_DIR}/.env (if required by telefwd) and run: chmod 600 ${APP_DIR}/.env && chown ${SERVICE_USER}:${SERVICE_USER} ${APP_DIR}/.env"
echo "  2. If Telethon needs an interactive Telegram login code to create its .session file, run once:"
echo "       sudo -u ${SERVICE_USER} ${VENV_DIR}/bin/python ${APP_DIR}/main.py"
echo "     (Press Ctrl+C once authenticated.)"
echo "  3. Enable and start the background service:"
echo "       sudo systemctl enable --now telefwd"
echo "       sudo systemctl status telefwd"