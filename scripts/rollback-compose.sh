#!/usr/bin/env bash
set -euo pipefail

env_file=".env"
image_name="aiops-agent-app"
rollback_tag="${image_name}:rollback"

if [[ ! -f "$env_file" || -L "$env_file" ]]; then
    echo "Expected a regular .env file. Run bash scripts/setup-env.sh first." >&2
    exit 1
fi

if ! rollback_image="$(docker image inspect --format '{{.Id}}' "$rollback_tag" 2>/dev/null)"; then
    echo "No previous image is available. Deploy an update with bash scripts/deploy-compose.sh first." >&2
    exit 1
fi

mapfile -t containers < <(docker compose ps --status running -q aiops-app)
if (( ${#containers[@]} == 0 )); then
    echo "No running aiops-app container found; refusing an automatic rollback." >&2
    exit 1
fi

current_tag="$(sed -n 's/^APP_IMAGE_TAG=//p' "$env_file" | tail -n 1)"
current_tag="${current_tag:-latest}"
replica_count="${#containers[@]}"
rollback_deploy_tag="rollback-$(date -u +%Y%m%dT%H%M%S)-$$"
docker image tag "$rollback_image" "${image_name}:${rollback_deploy_tag}"

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

set_app_tag "$rollback_deploy_tag"

if ! docker compose up -d --wait --wait-timeout 60 --no-deps \
    --scale "aiops-app=$replica_count" aiops-app; then
    echo "Rollback failed; restoring the configured image tag $current_tag." >&2
    set_app_tag "$current_tag"
    if ! docker compose up -d --wait --wait-timeout 60 --no-deps \
        --scale "aiops-app=$replica_count" aiops-app; then
        echo "Restoring the configured image also failed; inspect docker compose logs." >&2
    fi
    exit 1
fi

mkdir -p logs
printf '{"timestamp":"%s","action":"rollback","image":"%s","previous_image":"%s"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$rollback_deploy_tag" "$current_tag" \
    >> logs/deploys.jsonl
echo "Rolled back aiops-app to $rollback_deploy_tag."
