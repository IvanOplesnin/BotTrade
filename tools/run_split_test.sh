#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

exec docker compose -f docker-compose.dev.yml --profile split up --build "$@"
