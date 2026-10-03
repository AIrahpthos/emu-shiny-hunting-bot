#!/usr/bin/env bash
set -eu
cd -- "$(dirname -- "$0")"
[[ -n ${DISPLAY:-} ]] || { echo 'Run from the X11/VNC desktop.'; exit 1; }
exec 9> .capture-supervisor.lock
flock -n 9 || { echo 'Capture supervisor is already running.'; exit 0; }
exec python3 viewer_supervisor.py
