"""Restart cc3dsfs and keep a separate log for each unexpected exit."""
import json
import os
import platform
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from viewer_reports import record_exit
from ntr_support import ntr_executable

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT/'out'/'capture-incidents'
FLAGS = ['--no_audio','--auto_connect','--failure_close','--auto_close',
         '--enabled_both','0','--enabled_top','1','--enabled_low','1',
         '--scaling_top','1','--scaling_low','1',
         '--pos_x_top','850','--pos_y_top','30','--pos_x_low','850','--pos_y_low','350']


def set_current_log(path):
    link = Path.home()/'capture-viewer.log'
    if link.exists() and not link.is_symlink():
        link.rename(link.with_name('capture-viewer.before-reports-'+str(time.time_ns())+'.log'))
    temporary = link.with_name('.capture-viewer-log-'+str(os.getpid()))
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(path)
    os.replace(temporary,link)


def run_viewer_once(viewer, folder, stop, child_state, command=None, current_log=True):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    started = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    path = folder/('viewer-'+time.strftime('%Y%m%d-%H%M%S')+'-'+str(time.time_ns())+'.log')
    arguments = command if command is not None else [str(viewer), *FLAGS]
    metadata = {'started':started, 'command':arguments, 'system':platform.platform(),
                'python':sys.version.split()[0], 'log_file':path.name}
    code = None
    error = None
    with path.open('w', encoding='utf-8') as log:
        log.write(json.dumps(metadata,indent=2)+'\n\n')
        log.flush()
        if current_log:
            set_current_log(path)
        if stop.is_set():
            return None
        try:
            # Line-buffer output where stdbuf is installed; stderr shares the log.
            launch = ['/usr/bin/stdbuf','-oL','-eL',*arguments] if Path('/usr/bin/stdbuf').exists() else arguments
            environment=dict(os.environ)
            if Path(viewer).name=='ntrviewer':
                environment['SDL_VIDEODRIVER']='x11'
            process = subprocess.Popen(launch,cwd=Path(viewer).parent,env=environment,stdout=log,
                                       stderr=subprocess.STDOUT,close_fds=True)
            child_state[0] = process
            if stop.is_set():
                process.terminate()
            code = process.wait()
        except OSError as exception:
            error = str(exception)
            log.write('\nLaunch failed: '+error+'\n')
        finally:
            child_state[0] = None
        log.write('\nViewer exited: '+str(code)+'\n')
    if stop.is_set():
        return None
    if code is not None and code < 0:
        try:
            reason = signal.Signals(-code).name
        except ValueError:
            reason = 'signal '+str(-code)
    elif code == 0:
        reason = 'closed or disconnected (exit 0)'
    elif code is None:
        reason = 'viewer launch failed'
    else:
        reason = 'exit '+str(code)
    bot_log = ROOT/'out'/'events.log'
    if bot_log.exists():
        try:
            with bot_log.open('rb') as file:
                file.seek(0,2)
                length = file.tell()
                file.seek(max(0,length-65536))
                tail = file.read()
            snapshot = path.with_suffix('.bot.log')
            snapshot.write_bytes(tail)
            metadata['bot_log_file'] = snapshot.name
        except OSError as exception:
            metadata['bot_snapshot_error'] = str(exception)
    return record_exit(folder,{**metadata, 'returncode':code,'reason':reason,
                              'launch_error':error,'relaunch_scheduled':True})


def viewer_specs(settings):
    """NTR remains primary; an optional USB bottom window stays visible."""
    usb=Path((ROOT/'capture_executable.txt').read_text().strip()) if (ROOT/'capture_executable.txt').exists() else None
    if settings.get('capture_source')!='NTR wireless':
        if usb is None: raise ValueError('USB capture installation is missing.')
        return [(usb,[str(usb),*FLAGS],True)]
    ntr=ntr_executable()
    specs=[(ntr,[str(ntr)],True)]
    if settings.get('show_loopy_bottom',True) and usb is not None:
        bottom_flags=FLAGS.copy()
        bottom_flags[bottom_flags.index('--enabled_top')+1]='0'
        specs.append((usb,[str(usb),*bottom_flags],False))
    return specs


def supervise(viewer, command, stop, child, current_log):
    while not stop.is_set():
        report=run_viewer_once(viewer,REPORTS,stop,child,command=command,current_log=current_log)
        if report is not None:
            print(f'{viewer.name} interruption recorded: '+report['reason'],flush=True)
        if stop.wait(3): break


def main():
    settings=json.loads((ROOT/'settings.json').read_text()) if (ROOT/'settings.json').exists() else {}
    specs=viewer_specs(settings)
    for viewer,_,_ in specs:
        if not viewer.is_file() or not os.access(viewer,os.X_OK):
            raise RuntimeError(f'Viewer executable is missing: {viewer}')
    stop=threading.Event()
    children=[[None] for _ in specs]
    def shutdown(_signum,_frame):
        stop.set()
        for child in children:
            if child[0] is not None and child[0].poll() is None: child[0].terminate()
    for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):
        signal.signal(sig,shutdown)
    threads=[]
    for (viewer,command,current_log),child in zip(specs,children):
        thread=threading.Thread(target=supervise,args=(viewer,command,stop,child,current_log))
        thread.start(); threads.append(thread)
    for thread in threads: thread.join()


if __name__=='__main__':
    main()
