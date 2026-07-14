#!/usr/bin/env bash
set -euo pipefail

required=(DATABASE_URL REDIS_URL NEXT_PUBLIC_API_BASE_URL)
missing=()

for key in "${required[@]}"; do
  if [[ -z "${!key:-}" ]]; then
    missing+=("$key")
  fi
done

if (( ${#missing[@]} > 0 )); then
  printf 'Missing required environment variables: %s\n' "${missing[*]}" >&2
  exit 1
fi

echo "Environment variables are present. Values were not printed to protect secrets."
