"""Mash A through startup; stop when the static loaded-save gradient appears."""
import time
from PIL import Image, ImageChops, ImageStat
from core import Stopped

STAGES = ('gradient',)
LABELS = {'gradient':'Loaded-save gradient on the bottom screen'}


def signature(image,region):
    w,h=image.size
    x0,y0,x1,y1=region
    return image.convert('RGB').crop((round(x0*w),round(y0*h),round(x1*w),round(y1*h))).resize((32,24),Image.Resampling.BILINEAR)


def distance(a,b):
    return sum(ImageStat.Stat(ImageChops.difference(a,b)).mean)/3


class References:
    def __init__(self,folder,config=None,tolerance=12):
        self.region=(0,0,1,1)
        try:
            with Image.open(folder/'gradient.png') as image:
                self.target=signature(image,self.region)
        except FileNotFoundError:
            raise ValueError('Capture the gradient once in Screen setup first.') from None
        self.tolerance=tolerance

    def score(self,image):
        return distance(self.target,signature(image,self.region))

    def matches(self,image):
        return self.score(image)<=self.tolerance


def load_save(controller,grab,refs,stop,emit,timeout=45):
    start=time.monotonic()
    # Do not mistake a leftover pre-reset gradient frame for the newly loaded save.
    emit('Waiting for the reset to leave the current screen...')
    absent=0
    while absent<3:
        if stop.is_set(): raise Stopped()
        if time.monotonic()-start>=timeout:
            raise TimeoutError('Reset did not leave the gradient screen. Stopped.')
        absent=0 if refs.matches(grab()) else absent+1
        if absent<3 and stop.wait(.05): raise Stopped()
    emit('Tapping A through startup until the loaded-save gradient appears...')
    consecutive=0
    presses=0
    while time.monotonic()-start<timeout:
        if stop.is_set(): raise Stopped()
        image=grab()
        score=refs.score(image)
        if score<=refs.tolerance:
            # Suspend A on the FIRST possible match. Confirm on three frames
            # without sending extra inputs into the loaded save.
            consecutive+=1
            if consecutive>=3:
                emit(f'loaded-save gradient recognised after {time.monotonic()-start:.2f}s and {presses} A taps (match error {score:.1f}).')
                return
        else:
            consecutive=0
            controller.hold(('A',),.1)
            presses+=1
        if stop.wait(.05): raise Stopped()
    raise TimeoutError(f'loaded-save gradient not seen within {timeout}s. A tapping stopped; last match error {score:.1f}.')
