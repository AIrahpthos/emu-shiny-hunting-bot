#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ ! -f capture_executable.txt ]]; then
  echo 'Run bash Setup.sh first.'
  exit 1
fi
capture_executable=$(cat capture_executable.txt)
if [[ ! -x "$capture_executable" ]]; then
  echo 'Viewer installation moved or is missing. Re-run bash Setup.sh in this folder.'
  exit 1
fi
if [[ -z ${DISPLAY:-} ]]; then
  echo 'Run this from a Terminal on the Pi desktop.'
  exit 1
fi
if ldd "$capture_executable" 2>/dev/null | grep -q 'not found'; then
  echo 'This cc3dsfs binary needs libraries not present on your OS. Send the output below:'
  ldd "$capture_executable"
  exit 1
fi
cd -- "$(dirname -- "$capture_executable")"
exec "$capture_executable"
