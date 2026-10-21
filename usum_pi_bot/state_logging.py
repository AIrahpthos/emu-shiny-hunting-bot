"""Passive state sampling alongside the existing video-guided hunt."""
import json
from pathlib import Path
import threading
import time

from state_probe import parse_state_reply


class StateRecorder:
    def __init__(self, request, stop, path, context, emit, interval=.1):
        self.request=request;self.stop=stop;self.path=Path(path)
        self.context=context;self.emit=emit;self.interval=interval
        self.done=threading.Event();self.thread=None

    def start(self):
        parse_state_reply(*self.request(self.stop,capability=True),capability=True)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.thread=threading.Thread(target=self._run,daemon=True)
        self.thread.start()

    def _run(self):
        warned=False
        with self.path.open('a',encoding='utf-8') as log:
            while not self.done.is_set() and not self.stop.is_set():
                start=time.monotonic()
                try:
                    state=parse_state_reply(*self.request(self.stop))
                    state.update(utc_ns=time.time_ns(),attempt=self.context['attempt'],phase=self.context['phase'])
                    log.write(json.dumps(state)+'\n');log.flush()
                    if warned:
                        self.emit('State diagnostics resumed.')
                        warned=False
                except Exception as error:
                    if self.done.is_set() or self.stop.is_set():return
                    log.write(json.dumps({'utc_ns':time.time_ns(),'attempt':self.context['attempt'],
                                          'phase':self.context['phase'],'error':str(error)})+'\n')
                    log.flush()
                    if not warned:
                        self.emit('State diagnostics paused: '+str(error))
                        warned=True
                    if self.done.wait(1):return
                self.done.wait(max(0,self.interval-(time.monotonic()-start)))

    def close(self):
        self.done.set()
        if self.thread:self.thread.join(timeout=5)
