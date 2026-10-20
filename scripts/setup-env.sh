#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"

if [[ -L "$env_file" ]]; then
    echo "Refusing to modify symlink: $env_file" >&2
    exit 1
fi

if [[ -f "$env_file" ]] && grep -Eq '^GF_SECURITY_ADMIN_PASSWORD=.+$' "$env_file"; then
    chmod 600 "$env_file"
    echo "Grafana password is already configured in $env_file (permissions set to 600)."
    exit 0
fi

if [[ -f "$env_file" ]] && grep -q '^GF_SECURITY_ADMIN_PASSWORD=' "$env_file"; then
    echo "GF_SECURITY_ADMIN_PASSWORD is present but empty in $env_file; set a non-empty value first." >&2
    exit 1
fi

password="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"

if [[ -e "$env_file" ]]; then
    printf '\nGF_SECURITY_ADMIN_PASSWORD=%s\n' "$password" >> "$env_file"
else
    (umask 077; printf 'GF_SECURITY_ADMIN_PASSWORD=%s\n' "$password" > "$env_file")
fi

chmod 600 "$env_file"
echo "Generated a Grafana password in $env_file with permissions 600."
