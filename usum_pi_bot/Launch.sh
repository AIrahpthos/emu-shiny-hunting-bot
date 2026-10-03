#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo 'Run bash Setup.sh first.'
  exit 1
fi
if [[ ${XDG_SESSION_TYPE:-} == wayland || -n ${WAYLAND_DISPLAY:-} ]]; then
  echo 'This build needs X11: sudo raspi-config > Advanced Options > Wayland > X11, then reboot.'
  exit 1
fi
if [[ -z ${DISPLAY:-} ]]; then
  echo 'Run this from a Terminal on the Pi desktop, not a plain SSH session.'
  exit 1
fi
exec .venv/bin/python app.py
