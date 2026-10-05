"""Own one selected bottom feed for both preview and hunt detection."""
from pathlib import Path
from frame_feed import FrameStore
from capture_linux import ViewerUnavailable
from ntr_capture import NtrCapture
from loopy_capture import LoopyCapture


class CaptureService:
    def __init__(self, root, emit=lambda _:None):
        self.root=Path(root); self.emit=emit
        self.store=FrameStore(); self.backend=None; self.config=None

    def connect(self, source, ip='', quality=40, bandwidth=10):
        if source not in ('Loopy USB','NTR wireless'): raise ValueError('Unknown capture source.')
        config=(source,ip,quality,bandwidth) if source=='NTR wireless' else (source,)
        if self.backend and config==self.config:
            try:
                self.store.latest()
                return self.store
            except ViewerUnavailable:
                # An explicit Connect click must retry a failed/stale backend.
                pass
        self.close()
        if source=='NTR wireless':
            backend=NtrCapture(self.store,ip,quality,bandwidth,self.emit,logs=self.root/"out/capture-incidents")
        else:
            backend=LoopyCapture(self.store,self.root/'native/bin/cc3dsfs',self.root/'out/capture-incidents',self.emit)
        try: backend.start()
        except Exception:
            backend.close(); raise
        self.backend=backend; self.config=config
        return self.store

    def close(self):
        if self.backend: self.backend.close()
        self.backend=None; self.config=None
        self.store.invalidate('Capture disconnected.')
