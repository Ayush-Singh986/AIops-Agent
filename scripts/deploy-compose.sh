#!/usr/bin/env bash
set -euo pipefail

env_file=".env"
image_name="aiops-agent-app"
rollback_tag="${image_name}:rollback"

if [[ ! -f "$env_file" || -L "$env_file" ]]; then
    echo "Expected a regular .env file. Run bash scripts/setup-env.sh first." >&2
    exit 1
fi

current_tag="$(sed -n 's/^APP_IMAGE_TAG=//p' "$env_file" | tail -n 1)"
current_tag="${current_tag:-latest}"
mapfile -t containers < <(docker compose ps --status running -q aiops-app)
if (( ${#containers[@]} == 0 )); then
    echo "No running aiops-app container found. Start the stack before deploying." >&2
    exit 1
fi

previous_image="$(docker inspect --format '{{.Image}}' "${containers[0]}")"
docker image tag "$previous_image" "$rollback_tag"

replica_count="${#containers[@]}"
new_tag="deploy-$(date -u +%Y%m%dT%H%M%S)-$$"

if ! APP_IMAGE_TAG="$new_tag" docker compose build aiops-app; then
    echo "Build failed; the running deployment was left unchanged." >&2
    exit 1
fi

set_app_tag() {
    local value="$1"
    local temporary
    temporary="$(mktemp "${env_file}.XXXXXX")"
    chmod 600 "$temporary"
    awk -v value="$value" '
        BEGIN { found = 0 }
        /^APP_IMAGE_TAG=/ {
            if (!found) print "APP_IMAGE_TAG=" value
            found = 1
            next
        }
        { print }
        END {
            if (!found) print "APP_IMAGE_TAG=" value
        }
    ' "$env_file" > "$temporary"
    mv "$temporary" "$env_file"
    chmod 600 "$env_file"
}

set_app_tag "$new_tag"
if ! docker compose up -d --wait --wait-timeout 60 --no-deps \
    --scale "aiops-app=$replica_count" aiops-app; then
    echo "Deployment failed; attempting to restore the previous image." >&2
    set_app_tag "$current_tag"
    if ! docker compose up -d --wait --wait-timeout 60 --no-deps \
        --scale "aiops-app=$replica_count" aiops-app; then
        echo "Restoring the previous image also failed; inspect docker compose logs." >&2
    fi
    exit 1
fi

mkdir -p logs
printf '{"timestamp":"%s","action":"deploy","image":"%s","previous_image":"%s"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$new_tag" "$current_tag" >> logs/deploys.jsonl
echo "Deployment $new_tag is healthy; rollback image is available as $rollback_tag."
