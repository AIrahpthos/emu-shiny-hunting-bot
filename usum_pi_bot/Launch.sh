#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
[[ -x .venv/bin/python ]] || { echo 'Run bash Setup_integrated.sh first.'; exit 1; }
[[ -n ${DISPLAY:-} ]] || { echo 'Open the bot in a desktop/VNC session, or set DISPLAY=:1 from SSH.'; exit 1; }
exec .venv/bin/python app.py
