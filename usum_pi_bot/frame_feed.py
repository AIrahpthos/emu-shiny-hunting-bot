"""Latest-frame transport, independent of desktop visibility."""
from dataclasses import dataclass
import threading
import time
from PIL import ImageStat
from capture_linux import ViewerUnavailable
from core import Stopped


@dataclass(frozen=True)
class Frame:
    sequence: int
    received: float
    image: object


class FrameStore:
    def __init__(self, stale_seconds=2):
        self.condition=threading.Condition()
        self.frame=None
        self.sequence=0
        self.stale_seconds=stale_seconds
        self.error='Capture is not connected.'

    def publish(self, image, received=None):
        if image.size != (320,240):
            raise ValueError('Bottom frames must be 320×240.')
        image=image.convert('RGB').copy()
        received=time.monotonic() if received is None else received
        with self.condition:
            self.sequence+=1
            self.frame=Frame(self.sequence,received,image)
            self.error=''
            self.condition.notify_all()

    def invalidate(self, reason):
        with self.condition:
            self.frame=None
            self.error=str(reason)
            self.condition.notify_all()

    def latest(self):
        with self.condition:
            frame=self.frame
            if frame is None or time.monotonic()-frame.received>self.stale_seconds:
                raise ViewerUnavailable(self.error or 'Bottom-screen feed has stalled.')
            return frame

    def next(self, after=0, stop=None, timeout=2):
        deadline=time.monotonic()+timeout
        with self.condition:
            while True:
                if stop is not None and stop.is_set(): raise Stopped()
                frame=self.frame
                if frame is not None and frame.sequence>after and time.monotonic()-frame.received<=self.stale_seconds:
                    return frame
                remaining=deadline-time.monotonic()
                if remaining<=0:
                    raise ViewerUnavailable(self.error or 'No fresh bottom-screen frame arrived.')
                self.condition.wait(min(.05,remaining))


class Capture:
    def __init__(self, store, point, stop=None):
        self.store,self.point,self.stop=store,point,stop
        self.sequence=0

    def grab(self):
        frame=self.store.next(self.sequence,self.stop)
        self.sequence=frame.sequence
        return frame.image.copy()

    def sample(self):
        image=self.grab()
        x,y=int(image.width*self.point[0]),int(image.height*self.point[1])
        return tuple(ImageStat.Stat(image.crop((max(0,x-2),max(0,y-2),min(image.width,x+3),min(image.height,y+3)))).mean)

    def close(self):
        pass  # The GUI owns the shared feed; ending a hunt leaves its preview running.


def wait_for_capture(point, stop, emit, store, timeout=120):
    cap=Capture(store,point,stop)
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if stop.is_set(): raise Stopped()
        try:
            for _ in range(3): cap.grab()
            emit('Fresh bottom-screen frames restored. Resuming the active hunt.')
            return cap
        except ViewerUnavailable:
            if stop.wait(.2): raise Stopped()
    raise TimeoutError('Capture did not recover within two minutes.')
