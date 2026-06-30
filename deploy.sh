#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="docker-compose.prod.yml"

echo "=== [1/3] git pull ==="
git -C "$SCRIPT_DIR" pull

echo "=== [2/3] build image ==="
docker compose -f "$SCRIPT_DIR/$COMPOSE_FILE" pull --ignore-buildable
docker compose -f "$SCRIPT_DIR/$COMPOSE_FILE" build --pull web

echo "=== [3/3] spawn helper to restart containers ==="
docker run --rm -d \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$SCRIPT_DIR:$SCRIPT_DIR" \
  -w "$SCRIPT_DIR" \
  docker:cli \
  sh -c "docker compose -f $COMPOSE_FILE up -d && docker image prune -f"

echo "Deploy triggered."
