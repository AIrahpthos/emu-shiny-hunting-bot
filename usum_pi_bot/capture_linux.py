"""X11 desktop capture adapter for cc3dsfs on Raspberry Pi OS."""
import os
from PIL import Image, ImageStat


class ViewerUnavailable(RuntimeError):
    """The selected viewer window no longer exists or is no longer visible."""
    pass


def require_x11():
    if os.environ.get('XDG_SESSION_TYPE','').lower()=='wayland' or os.environ.get('WAYLAND_DISPLAY'):
        raise RuntimeError('This build needs an X11 desktop. Use sudo raspi-config > Advanced Options > Wayland > X11, then reboot.')
    if not os.environ.get('DISPLAY'):
        raise RuntimeError('Open the bot from the Pi desktop, not a plain SSH terminal.')


def overlaps(a,b):
    return a[0]<b[0]+b[2] and b[0]<a[0]+a[2] and a[1]<b[1]+b[3] and b[1]<a[1]+a[3]


class Desktop:
    def __init__(self):
        require_x11()
        from Xlib import display, X
        self.X=X
        self.display=display.Display()
        self.root=self.display.screen().root
        self.atoms={name:self.display.intern_atom(name) for name in
                    ('_NET_CLIENT_LIST_STACKING','_NET_CLIENT_LIST','_NET_WM_NAME','UTF8_STRING','_NET_FRAME_EXTENTS','_NET_WM_STATE','_NET_WM_STATE_HIDDEN')}

    def ids(self,stacking=False):
        name='_NET_CLIENT_LIST_STACKING' if stacking else '_NET_CLIENT_LIST'
        prop=self.root.get_full_property(self.atoms[name],self.X.AnyPropertyType)
        if prop is None:
            raise RuntimeError('Desktop window list unavailable. Use the standard Raspberry Pi X11 desktop.')
        return [int(x) for x in prop.value]

    def window(self,wid): return self.display.create_resource_object('window',wid)

    def title(self,wid):
        window=self.window(wid)
        prop=window.get_full_property(self.atoms['_NET_WM_NAME'],self.atoms['UTF8_STRING'])
        if prop is not None:
            return bytes(prop.value).decode('utf-8','replace')
        return window.get_wm_name() or ''

    def visible(self,wid):
        window=self.window(wid)
        if window.get_attributes().map_state!=self.X.IsViewable: return False
        state=window.get_full_property(self.atoms['_NET_WM_STATE'],self.X.AnyPropertyType)
        return state is None or self.atoms['_NET_WM_STATE_HIDDEN'] not in state.value

    def windows(self):
        result=[]
        from Xlib.error import XError
        for wid in self.ids():
            try:
                if self.visible(wid): result.append((wid,self.title(wid)))
            except XError: continue  # A window can close while the list is read.
        return result

    def bounds(self,wid,frame=False):
        window=self.window(wid)
        geo=window.get_geometry()
        position=self.root.translate_coords(window,0,0)
        left,top,width,height=position.x,position.y,geo.width,geo.height
        if frame:
            prop=window.get_full_property(self.atoms['_NET_FRAME_EXTENTS'],self.X.AnyPropertyType)
            if prop is not None and len(prop.value)==4:
                l,r,t,b=map(int,prop.value)
                left-=l; top-=t; width+=l+r; height+=t+b
        return (left,top,width,height)

    def close(self): self.display.close()


class Capture:
    def __init__(self,hwnd,point):
        import mss
        self.desktop=Desktop()
        self.hwnd,self.point=hwnd,point
        self.sct=mss.mss()

    def grab(self):
        from Xlib.error import XError
        try:
            if not self.desktop.visible(self.hwnd):
                raise ViewerUnavailable('Bottom-screen viewer is closed or minimised.')
            bounds=self.desktop.bounds(self.hwnd)
            left,top,width,height=bounds
            if width<100 or height<100: raise RuntimeError('Bottom-screen viewer is too small.')
            screen=self.desktop.display.screen()
            if left<0 or top<0 or left+width>screen.width_in_pixels or top+height>screen.height_in_pixels:
                raise RuntimeError('Keep the entire bottom-screen viewer on the desktop.')
            stack=self.desktop.ids(stacking=True)
            if self.hwnd not in stack: raise ViewerUnavailable('Bottom-screen viewer disappeared.')
            for wid in stack[stack.index(self.hwnd)+1:]:
                try:
                    if self.desktop.visible(wid) and overlaps(bounds,self.desktop.bounds(wid,frame=True)):
                        raise RuntimeError('Another window covers the bottom-screen viewer. Move it aside.')
                except XError: continue
            raw=self.sct.grab({'left':left,'top':top,'width':width,'height':height})
            return Image.frombytes('RGB',raw.size,raw.rgb)
        except XError as e:
            raise ViewerUnavailable('Capture viewer changed or closed.') from e

    def sample(self):
        image=self.grab()
        x,y=int(image.width*self.point[0]),int(image.height*self.point[1])
        return tuple(ImageStat.Stat(image.crop((max(0,x-2),max(0,y-2),x+3,y+3))).mean)

    def close(self):
        try: self.sct.close()
        finally: self.desktop.close()
