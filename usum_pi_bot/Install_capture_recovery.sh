#!/usr/bin/env bash
set -euo pipefail
bot_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
python3 "$bot_dir/startup.py" "$bot_dir"
