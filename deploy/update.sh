#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${DBYT_REPO_DIR:-/opt/dbyt}"
cd "$REPO_DIR"

if [ "$(id -u)" -eq 0 ]; then
    DOCKER=(docker)
else
    DOCKER=(sudo docker)
fi

"${DOCKER[@]}" compose -f deploy/docker-compose.prod.yml pull caddy
"${DOCKER[@]}" compose -f deploy/docker-compose.prod.yml up -d --build --remove-orphans
"${DOCKER[@]}" compose -f deploy/docker-compose.prod.yml ps
