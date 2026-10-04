#!/usr/bin/env bash
set -euo pipefail
bot_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
python3 - "$HOME/.config/openbox/autostart" "$bot_dir" <<'PY'
import sys,shlex
from pathlib import Path
path=Path(sys.argv[1]);bot=Path(sys.argv[2])
path.parent.mkdir(parents=True,exist_ok=True)
text=path.read_text() if path.exists() else ''
backup=path.with_name('autostart.before-integrated-capture')
if path.exists() and not backup.exists():backup.write_text(text)
# Only replace this installation's entries. Other installations remain untouched.
lines=[line for line in text.splitlines() if not (str(bot) in line and any(x in line for x in ['Capture_supervisor.sh','Launch_capture.sh','Launch.sh']))]
lines.append('bash '+shlex.quote(str(bot/'Launch.sh'))+' >> "$HOME/shiny-integrated.log" 2>&1 &')
path.write_text('\n'.join(lines)+'\n')
PY
printf 'Integrated bot startup installed. Remove any old installation entries before the next desktop start.\n'
