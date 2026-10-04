"""Own and supervise the cc3dsfs direct bottom-frame helper."""
import os
from pathlib import Path
import socket
import struct
import subprocess
import threading
import time
from PIL import Image

HEADER=struct.Struct('<4sIQQ')
FRAME_BYTES=240*320*3


def read_exact(sock, size, stop):
    data=bytearray()
    deadline=time.monotonic()+5
    while len(data)<size:
        if stop.is_set(): return None
        if time.monotonic()>=deadline: raise TimeoutError("Loopy helper stopped delivering frames.")
        try: chunk=sock.recv(size-len(data))
        except socket.timeout: continue
        if not chunk: raise ConnectionError('Loopy frame helper exited.')
        data.extend(chunk)
    return bytes(data)


class LoopyCapture:
    def __init__(self, store, executable, logs, emit=lambda _:None):
        self.store,self.executable,self.logs,self.emit=store,Path(executable),Path(logs),emit
        self.stop=threading.Event(); self.thread=None; self.process=None; self.sock=None

    def start(self):
        if not self.executable.is_file(): raise ValueError('Loopy capture helper is not installed. Run Setup_integrated.sh.')
        self.thread=threading.Thread(target=self._run,daemon=True); self.thread.start()

    def _run(self):
        self.logs.mkdir(parents=True,exist_ok=True)
        while not self.stop.is_set():
            log_path=self.logs/f'loopy-{time.time_ns()}.log'
            parent,child=socket.socketpair()
            parent.settimeout(.1); self.sock=parent
            started=time.time(); proc=None
            try:
                env={**os.environ,'SHINY_FRAME_FD':str(child.fileno())}
                with log_path.open('wb') as log:
                    proc=subprocess.Popen([str(self.executable),'--no_audio','--no_auto_save'],
                                          cwd=str(self.executable.parent),env=env,pass_fds=(child.fileno(),),
                                          stdout=log,stderr=subprocess.STDOUT)
                    self.process=proc; child.close()
                    self.emit('Loopy USB capture helper started.')
                    while not self.stop.is_set():
                        raw=read_exact(parent,HEADER.size,self.stop)
                        if raw is None: break
                        magic,size,seq,received_ns=HEADER.unpack(raw)
                        if magic!=b'SBF1' or size!=FRAME_BYTES: raise ValueError('Invalid Loopy frame header.')
                        pixels=read_exact(parent,size,self.stop)
                        if pixels is None: break
                        # Timestamp comes from the native capture loop, not GUI display.
                        received=received_ns/1e9
                        if time.monotonic()-received>self.store.stale_seconds: continue
                        image=Image.frombytes('RGB',(240,320),pixels).transpose(Image.Transpose.ROTATE_90)
                        self.store.publish(image,received)
            except (OSError,ValueError) as e:
                if not self.stop.is_set():
                    self.store.invalidate(str(e)); self.emit(f'Loopy capture lost: {e}. Retrying in 3 seconds.')
            finally:
                child.close(); parent.close(); self.sock=None
                if proc and proc.poll() is None:
                    proc.terminate()
                    try: proc.wait(3)
                    except subprocess.TimeoutExpired: proc.kill(); proc.wait()
                self.process=None
                if not self.stop.is_set():
                    # Same incident index used by the existing Recovery reports tab.
                    from viewer_reports import record_exit
                    record_exit(self.logs, {'log_file':log_path.name, 'started':started,
                                'returncode':proc.returncode if proc else -1,
                                'reason':'Loopy direct capture exited', 'capture_source':'Loopy USB'})
            self.stop.wait(3)

    def close(self):
        self.stop.set()
        if self.process and self.process.poll() is None: self.process.terminate()
        if self.sock:
            try: self.sock.shutdown(socket.SHUT_RDWR)
            except OSError: pass
        if self.thread: self.thread.join(5)
        self.store.invalidate('Loopy USB capture disconnected.')
