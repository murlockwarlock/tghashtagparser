#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ENV="${DEPLOY_ENV:-$ROOT_DIR/deploy.env}"

if [[ ! -f "$DEPLOY_ENV" ]]; then
  echo "Missing deploy env: $DEPLOY_ENV"
  echo "Copy deploy.example.env to deploy.env and fill server settings."
  exit 1
fi

set -a
source "$DEPLOY_ENV"
set +a

: "${DEPLOY_HOST:?DEPLOY_HOST is required}"
: "${DEPLOY_PATH:?DEPLOY_PATH is required}"
: "${SERVICE_NAME:?SERVICE_NAME is required}"

SERVICE_MANAGER="${SERVICE_MANAGER:-systemd}"
if [[ "$SERVICE_MANAGER" == "pm2" ]]; then
  : "${PM2_PROCESS_NAME:?PM2_PROCESS_NAME is required for PM2 deploy}"
fi

if ! git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Deploy must be run from a git repository."
  exit 1
fi

if [[ -n "$(git -C "$ROOT_DIR" status --porcelain)" ]]; then
  echo "Refusing to deploy a dirty worktree."
  echo "Commit or stash changes first, then deploy again."
  git -C "$ROOT_DIR" status --short
  exit 1
fi

COMMIT_SHA="$(git -C "$ROOT_DIR" rev-parse HEAD)"
COMMIT_SHORT="$(git -C "$ROOT_DIR" rev-parse --short HEAD)"

DEPLOY_PORT="${DEPLOY_PORT:-22}"
RELEASE_ID="$(date +%Y%m%d_%H%M%S)_$COMMIT_SHORT"
REMOTE_RELEASES="$DEPLOY_PATH/releases"
REMOTE_RELEASE="$REMOTE_RELEASES/$RELEASE_ID"
REMOTE_CURRENT="$DEPLOY_PATH/current"
REMOTE_SHARED="$DEPLOY_PATH/shared"

SSH_OPTS=(-p "$DEPLOY_PORT" -o StrictHostKeyChecking=accept-new)
SSH_CMD=(ssh)
if [[ -n "${SSHPASS:-}" ]]; then
  SSH_CMD=(sshpass -e ssh)
fi
if [[ -n "${SSH_KEY:-}" ]]; then
  SSH_OPTS+=(-i "$SSH_KEY")
fi
if [[ -n "${SSH_EXTRA_OPTS:-}" ]]; then
  EXTRA_OPTS=($SSH_EXTRA_OPTS)
  SSH_OPTS+=("${EXTRA_OPTS[@]}")
fi

echo "Running local checks..."
python3 -m py_compile $(find "$ROOT_DIR/app" "$ROOT_DIR/tests" -name '*.py')
python3 -m pytest -q "$ROOT_DIR/tests"

echo "Creating remote release: $REMOTE_RELEASE"
"${SSH_CMD[@]}" "${SSH_OPTS[@]}" "$DEPLOY_HOST" \
  "set -Eeuo pipefail; mkdir -p '$REMOTE_RELEASE' '$REMOTE_SHARED/data' '$REMOTE_SHARED/logs'"

echo "Uploading exact git commit: $COMMIT_SHA"
git -C "$ROOT_DIR" archive --format=tar HEAD app requirements.txt pyproject.toml | "${SSH_CMD[@]}" "${SSH_OPTS[@]}" "$DEPLOY_HOST" \
  "set -Eeuo pipefail; tar -xf - -C '$REMOTE_RELEASE'; printf '%s\n' '$COMMIT_SHA' > '$REMOTE_RELEASE/REVISION'"

echo "Installing dependencies and switching release atomically..."
"${SSH_CMD[@]}" "${SSH_OPTS[@]}" "$DEPLOY_HOST" "bash -s" <<REMOTE
set -Eeuo pipefail
cd "$REMOTE_RELEASE"

ln -sfn "$REMOTE_SHARED/.env" "$REMOTE_RELEASE/.env"
ln -sfn "$REMOTE_SHARED/data" "$REMOTE_RELEASE/data"
ln -sfn "$REMOTE_SHARED/logs" "$REMOTE_RELEASE/logs"

if [[ ! -d "$REMOTE_SHARED/venv" ]]; then
  python3 -m venv "$REMOTE_SHARED/venv"
  "$REMOTE_SHARED/venv/bin/pip" install --upgrade pip
fi
ln -sfn "$REMOTE_SHARED/venv" "$REMOTE_RELEASE/venv"

./venv/bin/pip install -r requirements.txt
./venv/bin/python -m py_compile \$(find app -name '*.py')
./venv/bin/python -m app.db.init_db

ln -sfn "$REMOTE_RELEASE" "$REMOTE_CURRENT"

if [[ "$SERVICE_MANAGER" == "pm2" ]]; then
  if pm2 describe "$PM2_PROCESS_NAME" >/dev/null 2>&1; then
    pm2 delete "$PM2_PROCESS_NAME"
  fi
  cd "$REMOTE_CURRENT"
  pm2 start "$REMOTE_CURRENT/venv/bin/python" \
    --name "$PM2_PROCESS_NAME" \
    --cwd "$REMOTE_CURRENT" \
    -- -m app.main
  pm2 save
  pm2 describe "$PM2_PROCESS_NAME" >/dev/null
elif systemctl list-unit-files | grep -q "^$SERVICE_NAME.service"; then
  systemctl restart "$SERVICE_NAME.service"
  systemctl is-active --quiet "$SERVICE_NAME.service"
else
  cat > "/etc/systemd/system/$SERVICE_NAME.service" <<UNIT
[Unit]
Description=Telegram Hashtag Parser Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$REMOTE_CURRENT
EnvironmentFile=$REMOTE_SHARED/.env
Environment=LOG_DIR=$REMOTE_SHARED/logs
ExecStart=$REMOTE_CURRENT/venv/bin/python -m app.main
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable "$SERVICE_NAME.service"
  systemctl restart "$SERVICE_NAME.service"
  systemctl is-active --quiet "$SERVICE_NAME.service"
fi

find "$REMOTE_RELEASES" -mindepth 1 -maxdepth 1 -type d | sort | head -n -5 | xargs -r rm -rf
REMOTE

echo "Deploy completed: $RELEASE_ID ($COMMIT_SHA)"
