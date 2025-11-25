#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"

DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"

echo "[deploy] Syncing repository (branch: $DEPLOY_BRANCH)..."
git -C "$REPO_DIR" fetch origin "$DEPLOY_BRANCH"
git -C "$REPO_DIR" reset --hard "origin/$DEPLOY_BRANCH"
git -C "$REPO_DIR" clean -fd

echo "[deploy] Building and starting containers..."
cd "$REPO_DIR/deploy"
export DOMAIN=${DOMAIN:-example.com}
export EMAIL=${EMAIL:-admin@example.com}
docker compose -f docker-compose.prod.yml up -d --build

echo "[deploy] Reloading Caddy configuration..."
if ! docker compose -f docker-compose.prod.yml exec -T caddy caddy reload --config /etc/caddy/Caddyfile; then
  echo "[deploy] Caddy reload failed, restarting container..."
  docker compose -f docker-compose.prod.yml restart caddy
fi

echo "[deploy] Cleaning old images..."
docker image prune -f >/dev/null || true

echo "[deploy] Done."

