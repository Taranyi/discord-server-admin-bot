#!/usr/bin/env bash

set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_dir"

bot_executable="$project_dir/.venv/bin/discord-bot"

if [[ ! -x "$bot_executable" ]]; then
    printf 'The project virtual environment is missing. Run: uv sync\n' >&2
    exit 1
fi

exec "$bot_executable" "$@"
