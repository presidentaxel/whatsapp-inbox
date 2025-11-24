#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"

echo "[deploy] Pulling latest changes..."
git -C "$REPO_DIR" pull --rebase

echo "[deploy] Building and starting containers..."
cd "$REPO_DIR/deploy"
export DOMAIN=${DOMAIN:-example.com}
export EMAIL=${EMAIL:-admin@example.com}
docker compose -f docker-compose.prod.yml up -d --build

echo "[deploy] Cleaning old images..."
docker image prune -f >/dev/null || true

echo "[deploy] Done."

