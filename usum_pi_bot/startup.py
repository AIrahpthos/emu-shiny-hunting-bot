"""Migrate the known bot installations to one Openbox startup entry."""
from pathlib import Path
import re
import shlex
import shutil
import time

LAUNCHERS=('Capture_supervisor.sh','Launch_capture.sh','Launch.sh','viewer_supervisor.py','app.py')


def migrate(text, bot, home):
    bot=Path(bot).resolve();home=Path(home).resolve()
    roots=(bot, home/'usum_pi_bot', home/'shiny-bot-github/usum_pi_bot')
    patterns=[re.compile(re.escape(str(root))+r"(?=/|[\s\"';]|$)") for root in roots]
    lines=[]
    for line in text.splitlines():
        expanded=line.replace('${HOME}',str(home)).replace('$HOME',str(home)).replace('~/',str(home)+'/')
        owned=not line.lstrip().startswith('#') and any(pattern.search(expanded) for pattern in patterns)
        if owned and any(name in line for name in LAUNCHERS): continue
        lines.append(line)
    lines.append('bash '+shlex.quote(str(bot/'Launch.sh'))+' >> "$HOME/shiny-integrated.log" 2>&1 &')
    return '\n'.join(lines)+'\n'


def install(bot, home=None):
    home=Path.home() if home is None else Path(home)
    path=home/'.config/openbox/autostart'
    path.parent.mkdir(parents=True,exist_ok=True)
    original=path.read_text() if path.exists() else ''
    updated=migrate(original,bot,home)
    if updated==original: return None
    backup=None
    if path.exists():
        backup=path.with_name('autostart.before-integrated-'+str(time.time_ns()))
        shutil.copy2(path,backup)
    temporary=path.with_name('autostart.integrated.tmp')
    temporary.write_text(updated)
    if path.exists():shutil.copymode(path,temporary)
    temporary.replace(path)
    return backup


if __name__=='__main__':
    import sys
    backup=install(sys.argv[1])
    if backup:print('Previous desktop startup saved to '+str(backup))
    print('Desktop startup now opens the integrated bot instead of the old bot and viewers.')
    print('Existing processes are unchanged. Restart the desktop after stopping the active hunt.')
