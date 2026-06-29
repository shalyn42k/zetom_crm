#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="docker-compose.prod.yml"

echo "=== [1/5] git pull ==="
git pull

echo "=== [2/5] pull latest base images (db, cloudflared, python) ==="
docker compose -f "$COMPOSE_FILE" pull --ignore-buildable
docker compose -f "$COMPOSE_FILE" build --pull web

echo "=== [3/5] restart all services ==="
docker compose -f "$COMPOSE_FILE" up -d

echo "=== [4/5] remove dangling images ==="
docker image prune -f

echo "=== [5/5] logs web (30s, Ctrl+C to exit) ==="
timeout 30 docker compose -f "$COMPOSE_FILE" logs -f web || true

echo ""
echo "Deploy done."
