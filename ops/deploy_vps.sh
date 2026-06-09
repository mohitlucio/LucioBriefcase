#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: ./ops/deploy_vps.sh <domain>"
  exit 1
fi

DOMAIN="$1"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required. Install Docker first."
  exit 1
fi

if ! command -v docker compose >/dev/null 2>&1; then
  echo "Docker Compose plugin is required."
  exit 1
fi

export DOMAIN

echo "Deploying LucioBriefcase for domain: $DOMAIN"
docker compose -f docker-compose.prod.yml up -d --build

echo "Deployment complete."
echo "Check status: docker compose -f docker-compose.prod.yml ps"
echo "Check logs: docker compose -f docker-compose.prod.yml logs -f --tail=200"
