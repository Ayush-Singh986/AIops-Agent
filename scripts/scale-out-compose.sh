#!/usr/bin/env bash
set -euo pipefail

maximum_replicas=3
mapfile -t containers < <(docker compose ps --status running -q aiops-app)
current_replicas="${#containers[@]}"

if (( current_replicas == 0 )); then
    echo "Cannot scale: no running aiops-app container was found." >&2
    exit 1
fi

if (( current_replicas >= maximum_replicas )); then
    echo "Cannot scale beyond $maximum_replicas aiops-app replicas." >&2
    exit 1
fi

target_replicas=$((current_replicas + 1))
docker compose up -d --wait --wait-timeout 60 --no-deps \
    --scale "aiops-app=$target_replicas" aiops-app
echo "Scaled aiops-app from $current_replicas to $target_replicas replicas."
