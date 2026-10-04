"""Recognise loading colours independently of startup button tapping."""
import time
import threading
from dataclasses import dataclass
from PIL import Image
from core import Stopped

@dataclass
class LoadResult:
    seconds: float
    a_taps: int
    match_error: float
    # Retain this history field for compatibility; it means sequence confirmed.
    gradient_seen: bool


def signature(image,region):
    w,h=image.size
    x0,y0,x1,y1=region
    return image.convert('RGB').crop((round(x0*w),round(y0*h),round(x1*w),round(y1*h))).resize((32,24),Image.Resampling.BILINEAR)


class ColourDetector:
    """Reference-free colour categories for animated wireless loading screens."""
    region=(.05,.05,.95,.95)

    @classmethod
    def fractions(cls,image):
        small=signature(image,cls.region)
        data=small.load()
        pixels=[data[x,y] for y in range(small.height) for x in range(small.width)]
        count=len(pixels)
        blue=dark=neutral=visible=bright=red=0
        for r,g,b in pixels:
            hi=max(r,g,b); lo=min(r,g,b)
            blue+=b>=50 and b-r>=15 and b>=g-10 and hi-lo>=32
            red+=r>=70 and r-g>=30 and r-b>=25
            dark+=hi<=35
            neutral+=hi-lo<=35
            visible+=hi>=65
            bright+=hi>=100
        return {key:value/count for key,value in
                [('blue',blue),('dark',dark),('neutral',neutral),('visible',visible),('bright',bright),('red',red)]}

    @staticmethod
    def classify(f):
        return {'ocean':f['blue']>=.55,
                'black':f['dark']>=.90,
                'red':f['red']>=1/768}

    def score(self,image):
        return 100*(1-self.fractions(image)['red'])

    def matches(self,image):
        return self.classify(self.fractions(image))['red']

    def ocean_matches(self,image):
        return self.classify(self.fractions(image))['ocean']

    def dark(self,image):
        return self.classify(self.fractions(image))['black']


class _StartupTapper:
    """Keep button holds off the capture thread."""
    def __init__(self,controller,stop):
        self.controller=controller
        self.stop=stop
        self.done=threading.Event()
        self.paused=threading.Event()
        self.presses=0
        self.error=None
        self.thread=threading.Thread(target=self.run,name='startup-input')

    def is_set(self):
        return self.done.is_set() or self.paused.is_set() or self.stop.is_set()

    def start(self): self.thread.start()

    def run(self):
        try:
            while not self.done.is_set() and not self.stop.is_set():
                if self.paused.is_set():
                    self.done.wait(.005)
                    continue
                self.presses+=1
                self.controller.hold(('A',),.05,cancel=self)
                if self.done.wait(.05): break
        except Exception as e:
            self.error=e
        finally:
            try: self.controller.release()
            except Exception as e:
                if self.error is None: self.error=e

    def close(self):
        self.done.set()
        self.thread.join()
        if self.error is not None: raise self.error


def load_save(controller,grab,refs,stop,emit,timeout=16,learned_limits=None,hz=30):
    """Sample independently of input; try an encounter after a missed sequence."""
    if hz not in (10,30,60): raise ValueError('Check rate must be 10, 30 or 60 Hz.')
    if not 0<timeout<=45: raise ValueError('Loading limit must be between 0 and 45 seconds.')
    start=time.monotonic()
    phase='ocean'
    stable=0
    score=100.
    period=1/hz
    emit(f'Startup: checking at {hz} Hz for blue -> black -> red; loading limit {timeout:g}s.')
    last_report=start-2
    tapper=_StartupTapper(controller,stop)
    if stop.is_set(): raise Stopped()
    tapper.start()
    try:
        while time.monotonic()-start<timeout:
            if stop.is_set(): raise Stopped()
            if tapper.error is not None: raise tapper.error
            sample_start=time.monotonic()
            image=grab()
            fractions=refs.fractions(image)
            score=100*(1-fractions['red'])
            matched=refs.classify(fractions)[phase]
            now=time.monotonic()
            if now-last_report>=2:
                emit(f'Startup waiting for {phase}: blue {fractions["blue"]:.0%}, black {fractions["dark"]:.0%}, red {fractions["red"]:.1%}.')
                last_report=now
            stable=stable+1 if matched else 0
            if stable>=3:
                if phase=='red':
                    elapsed=time.monotonic()-start
                    emit(f'Red after black recognised after {elapsed:.2f}s and {tapper.presses} A taps (red pixels {100-score:.1f}%).')
                    return LoadResult(elapsed,tapper.presses,score,True)
                phase='black' if phase=='ocean' else 'red'
                stable=0
                emit('Majority-blue screen seen; waiting for black.' if phase=='black'
                     else 'Black transition seen; waiting for red.')
            if phase=='red' and matched: tapper.paused.set()
            else: tapper.paused.clear()
            remaining=max(0.,period-(time.monotonic()-sample_start))
            if stop.wait(remaining): raise Stopped()
        if stop.is_set(): raise Stopped()
        elapsed=time.monotonic()-start
        emit(f'Loading limit reached after {elapsed:.2f}s while waiting for {phase}. Assuming a missed colour sequence; stopping startup taps and trying one encounter. Load is unconfirmed.')
        return LoadResult(elapsed,tapper.presses,score,False)
    finally:
        # No startup presses may overlap encounter triggering or an error exit.
        tapper.close()
