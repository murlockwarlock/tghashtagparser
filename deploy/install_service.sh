#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE_NAME="${SERVICE_NAME:-telegram-hashtag-parser}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/telegram-hashtag-parser}"
UNIT_SOURCE="$DEPLOY_PATH/current/deploy/systemd/telegram-hashtag-parser.service"
UNIT_TARGET="/etc/systemd/system/$SERVICE_NAME.service"

if [[ ! -f "$UNIT_SOURCE" ]]; then
  echo "Unit file not found: $UNIT_SOURCE"
  exit 1
fi

cp "$UNIT_SOURCE" "$UNIT_TARGET"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME.service"
systemctl restart "$SERVICE_NAME.service"
systemctl status "$SERVICE_NAME.service" --no-pager
