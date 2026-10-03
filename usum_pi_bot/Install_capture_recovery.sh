#!/usr/bin/env bash
set -euo pipefail
bot_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
if [[ ! -f "$bot_dir/capture_executable.txt" ]]; then
  echo "Cannot find $bot_dir/capture_executable.txt. Run this as jack after installing the bot."
  exit 1
fi
if [[ $(id -u) -eq 0 ]]; then
  echo 'Run this as jack, without sudo.'
  exit 1
fi
command -v flock >/dev/null
mkdir -p "$HOME/.config/openbox"
cat > "$bot_dir/Capture_supervisor.sh" <<'SUPERVISOR'
#!/usr/bin/env bash
set -u
cd -- "$(dirname -- "$0")" || exit 1
if [[ -z ${DISPLAY:-} ]]; then
  echo 'Launch this from the VNC desktop terminal.'
  exit 1
fi
exec 9> .capture-supervisor.lock
flock -n 9 || { echo 'Capture supervisor is already running.'; exit 0; }
viewer=$(cat capture_executable.txt) || exit 1
[[ -x "$viewer" ]] || { echo 'Capture executable is missing.'; exit 1; }
if [[ ! -f viewer_supervisor.py ]]; then
  echo 'Viewer reporting update is missing. Install the full update.'
  exit 1
fi
exec python3 viewer_supervisor.py

SUPERVISOR
chmod +x "$bot_dir/Capture_supervisor.sh"
python3 - "$HOME/.config/openbox/autostart" "$bot_dir" <<'PY'
import sys
from pathlib import Path
from shlex import quote
p = Path(sys.argv[1])
bot = Path(sys.argv[2])
s = p.read_text() if p.exists() else ''
backup = p.with_name('autostart.before-capture-recovery')
if p.exists() and not backup.exists():
    backup.write_text(s)
if 'Capture_supervisor.sh' not in s:
    if 'Launch_capture.sh' in s:
        s = s.replace('Launch_capture.sh', 'Capture_supervisor.sh')
    else:
        s += '\nbash ' + quote(str(bot / 'Capture_supervisor.sh')) + ' >> ' + quote(str(Path.home()/'capture-supervisor.log')) + ' 2>&1 &\n'
s = '\n'.join(line.replace('capture-viewer.log','capture-supervisor.log')
              if 'Capture_supervisor.sh' in line else line for line in s.split('\n'))
p.write_text(s)
PY
echo 'Capture recovery installed. It will run at the next desktop start.'
echo 'The supervisor reopens the viewer even after you close it manually.'
echo 'It restarts exited processes; it does not detect a frozen viewer.'
