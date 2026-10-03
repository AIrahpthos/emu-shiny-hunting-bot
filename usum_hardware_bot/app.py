"""USUM real-hardware static encounter bot. Windows capture viewer must stay visible."""
import ctypes
import json
import queue
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk, ImageStat
import mss
import win32gui
from core import Controller, Stopped, measure, classify, choose_bottom_window, BOTTOM_WINDOW_PREFIX
from navigation import References, STAGES, LABELS, load_save

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except (AttributeError, OSError):
    pass

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'out'
OUT.mkdir(exist_ok=True)
REFS = ROOT / 'references'
REFS.mkdir(exist_ok=True)


class Capture:
    def __init__(self, hwnd, point):
        self.hwnd, self.point = hwnd, point
        self.sct = mss.mss()

    def grab(self):
        if not win32gui.IsWindow(self.hwnd) or win32gui.IsIconic(self.hwnd):
            raise RuntimeError('Capture window is closed or minimised.')
        left, top, right, bottom = win32gui.GetClientRect(self.hwnd)
        left, top = win32gui.ClientToScreen(self.hwnd, (left, top))
        right, bottom = win32gui.ClientToScreen(self.hwnd, (right, bottom))
        width, height = right-left, bottom-top
        if width < 100 or height < 100:
            raise RuntimeError('Capture window is too small.')
        # Reject another window covering the image. These are visible desktop pixels.
        for u, v in ((.1,.1),(.9,.1),(.1,.9),(.9,.9),self.point):
            hit = win32gui.WindowFromPoint((left+int(width*u), top+int(height*v)))
            if hit != self.hwnd and win32gui.GetAncestor(hit, 2) != self.hwnd:
                raise RuntimeError('Another window covers the capture. Keep the bottom screen visible.')
        raw = self.sct.grab({'left':left, 'top':top, 'width':width, 'height':height})
        return Image.frombytes('RGB', raw.size, raw.rgb)

    def sample(self):
        image = self.grab()
        x, y = (int(image.width*self.point[0]), int(image.height*self.point[1]))
        return tuple(ImageStat.Stat(image.crop((max(0,x-2),max(0,y-2),x+3,y+3))).mean)

    def close(self):
        self.sct.close()


class App:
    def __init__(self, root):
        self.root = root
        root.title('USUM Hardware Shiny Hunter — Automatic bottom window v0.5')
        root.geometry('780x790')
        self.stop = threading.Event()
        self.confirm = threading.Event()
        self.events = queue.Queue()
        self.worker = None
        self.point = (.5,.5)
        self.baseline = None
        self.pending_baseline = None
        self.windows = []
        self.setup_buttons = []
        try:
            saved = json.loads((ROOT/'settings.json').read_text())
        except (OSError, ValueError):
            saved = {}
        tabs = ttk.Notebook(root)
        tabs.pack(fill='both',expand=True)
        frame = ttk.Frame(tabs,padding=12)
        setup = ttk.Frame(tabs,padding=12)
        tabs.add(frame,text='Hunt')
        tabs.add(setup,text='Screen setup')
        ttk.Label(frame, text='USUM static encounters on a real 3DS', font=('Segoe UI',16)).pack(anchor='w')
        ttk.Label(frame, text='Keep the bottom-screen viewer visible. Start from a saved encounter position.').pack(anchor='w', pady=5)
        row = ttk.Frame(frame); row.pack(fill='x', pady=5)
        ttk.Label(row,text='3DS IP:').pack(side='left')
        self.ip = tk.StringVar(value=saved.get('ip',''))
        ttk.Entry(row,textvariable=self.ip,width=20).pack(side='left',padx=8)
        self.test_button = ttk.Button(row,text='Test controls (D-pad right)',command=lambda:self.start('test'))
        self.test_button.pack(side='left')
        row = ttk.Frame(frame); row.pack(fill='x', pady=5)
        ttk.Label(row,text='Bottom screen:').pack(side='left',padx=4)
        self.window_name=tk.StringVar(value='Looking for 3DS Capture - Bottom...')
        self.window = ttk.Label(row,textvariable=self.window_name)
        self.window.pack(side='left',fill='x',expand=True)
        self.refresh_button = ttk.Button(row,text='Refresh windows',command=self.refresh)
        self.refresh_button.pack(side='left',padx=5)
        self.preview_button = ttk.Button(frame,text='Preview bottom screen',command=self.preview)
        self.preview_button.pack(anchor='w',pady=5)
        self.preview_label = ttk.Label(frame,text='Bottom-screen preview')
        self.preview_label.pack(pady=5)
        self.preview_label.bind('<Button-1>',self.pick)
        settings = ttk.Frame(frame); settings.pack(fill='x',pady=8)
        self.values = {}
        for index,(label,key,default) in enumerate([('Shiny extra seconds','threshold',1.1),('Forward hold seconds','forward',1)]):
            ttk.Label(settings,text=label).grid(row=index//2,column=(index%2)*2,sticky='w',padx=5,pady=3)
            var=tk.StringVar(value=str(saved.get(key,default))); self.values[key]=var
            ttk.Entry(settings,textvariable=var,width=7).grid(row=index//2,column=(index%2)*2+1,padx=8)
        self.repeat=tk.BooleanVar(value=False)
        ttk.Checkbutton(frame,text='Repeat normal encounters automatically (leave off for the first test)',variable=self.repeat).pack(anchor='w')
        row=ttk.Frame(frame); row.pack(fill='x',pady=8)
        self.start_button=ttk.Button(row,text='Start',command=lambda:self.start('hunt')); self.start_button.pack(side='left')
        ttk.Button(row,text='STOP',command=self.stop.set).pack(side='left',padx=8)
        self.confirm_button=ttk.Button(row,text='Confirm first encounter is normal',command=self.confirm.set,state='disabled'); self.confirm_button.pack(side='left')
        self.status=tk.StringVar(value='Ready. Test controls first; then preview the bottom screen.')
        ttk.Label(frame,textvariable=self.status,wraplength=730).pack(anchor='w',pady=6)
        self.log=tk.Text(frame,height=10,state='disabled',wrap='word'); self.log.pack(fill='both',expand=True)
        ttk.Label(setup,text='One reference: the loaded-save gradient',font=('Segoe UI',15)).pack(anchor='w')
        ttk.Label(setup,text='The bottom-screen window is found automatically.\nClick Capture while the patterned gradient is visible just after loading.',wraplength=730).pack(anchor='w',pady=8)
        for stage in STAGES:
            button=ttk.Button(setup,text='Capture: '+LABELS[stage],command=lambda stage=stage:self.capture_reference(stage))
            button.pack(anchor='w',pady=8)
            self.setup_buttons.append(button)
        ttk.Label(setup,text='Capture once while the gradient is visible, before Rotom appears.\nThe whole screen is saved automatically.\nAfter resetting, the bot taps A until that screen appears, then starts the encounter.',wraplength=730).pack(anchor='w',pady=10)
        self.refs_status=tk.StringVar(value='Capture the loaded-save gradient reference once before starting a hunt.')
        ttk.Label(setup,textvariable=self.refs_status,wraplength=730).pack(anchor='w',pady=8)
        root.protocol('WM_DELETE_WINDOW',self.close)
        self.refresh()
        root.after(100,self.poll)

    def refresh(self):
        self.windows=[]
        def collect(hwnd,_):
            title=win32gui.GetWindowText(hwnd)
            if title and win32gui.IsWindowVisible(hwnd) and hwnd != self.root.winfo_id() and not title.startswith('USUM Hardware'):
                self.windows.append((hwnd,title))
        win32gui.EnumWindows(collect,None)
        matches=[(hwnd,title) for hwnd,title in self.windows if title.startswith(BOTTOM_WINDOW_PREFIX)]
        self.window_name.set(matches[0][1] if len(matches)==1 else
                             ('Bottom viewer not open' if not matches else 'Close duplicate bottom viewers'))

    def selected(self, navigation=False):
        # Re-enumerate so restarting the capture viewer does not keep an old handle.
        self.refresh()
        return choose_bottom_window(self.windows)

    def references(self):
        return References(REFS)

    def capture_reference(self,stage):
        if self.worker and self.worker.is_alive(): return
        cap=None
        try:
            cap=Capture(self.selected(),(.5,.5))
            image=cap.grab()
            image.save(REFS/'gradient.png')
            self.refs_status.set('Gradient saved. Ready to run a single-encounter test.')
        except Exception as e:
            messagebox.showerror('Reference capture',str(e))
        finally:
            if cap: cap.close()

    def preview(self):
        try:
            cap=Capture(self.selected(),self.point)
            try: image=cap.grab()
            finally: cap.close()
            image.thumbnail((480,300))
            self.preview_size=image.size
            self.photo=ImageTk.PhotoImage(image)
            self.preview_label.configure(image=self.photo,text='')
            self.status.set(f'Detection point: {self.point[0]:.0%} across, {self.point[1]:.0%} down. Default is the centre.')
        except Exception as e: messagebox.showerror('Preview',str(e))

    def pick(self,event):
        if self.worker and self.worker.is_alive(): return
        if hasattr(self,'preview_size'):
            w,h=self.preview_size
            self.point=(min(.98,max(.02,event.x/w)),min(.98,max(.02,event.y/h)))
            self.status.set(f'Detection point selected: {self.point[0]:.0%} across, {self.point[1]:.0%} down.')

    def emit(self,text): self.events.put(('log',text))

    def start(self,mode):
        if self.worker and self.worker.is_alive(): return
        try:
            options={key:float(var.get()) for key,var in self.values.items()}
            limits={'threshold':(.1,10),'forward':(0,5)}
            for key,value in options.items():
                low,high=limits[key]
                if not low <= value <= high: raise ValueError(f'{key} must be between {low} and {high}.')
            ip=self.ip.get().strip()
            import ipaddress
            ipaddress.IPv4Address(ip)
            hwnd=self.selected() if mode=='hunt' else None
            refs=self.references() if mode=='hunt' else None
            if mode=='hunt' and not messagebox.askokcancel('Start hunt', 'The bot will soft-reset the game. Save at the intended encounter first.\n\nThe first encounter pauses for visual confirmation. Continue?'): return
            (ROOT/'settings.json').write_text(json.dumps({'ip':ip,**options},indent=2))
        except Exception as e:
            messagebox.showerror('Setup',str(e)); return
        self.stop.clear(); self.confirm.clear()
        self.pending_baseline=None
        for b in (self.start_button,self.test_button,self.preview_button,self.refresh_button,*self.setup_buttons): b.configure(state='disabled')
        self.worker=threading.Thread(target=self.run,args=(mode,ip,hwnd,refs,options,self.repeat.get(),self.point),daemon=True)
        self.worker.start()

    def run(self,mode,ip,hwnd,refs,o,repeat,point):
        controller=None; cap=None; trigger_thread=None
        try:
            controller=Controller(ip,self.stop)
            if mode=='test':
                controller.hold(('RIGHT',),.25)
                self.emit('D-pad right sent. UDP has no connection acknowledgement: verify the console moved.'); return
            cap=Capture(hwnd,point); cap.grab()
            baseline=None
            attempts=0
            while not self.stop.is_set():
                attempts+=1; self.emit(f'Encounter {attempts}: resetting...')
                controller.hold(('L','R','START','SELECT'),.15)
                reset_start=time.monotonic()
                load_save(controller,cap.grab,refs,self.stop,self.emit)
                self.emit(f'Reset-to-loaded-save took {time.monotonic()-reset_start:.2f}s; no fixed loading waits.')
                # Start observing before A/movement so a fast encounter transition
                # cannot finish while the input routine is still holding forward.
                trigger_errors=[]
                def trigger():
                    try:
                        controller.hold(('A',),.15)
                        if o['forward']: controller.hold(seconds=o['forward'],y=1)
                    except Exception as e:
                        trigger_errors.append(e)
                        self.stop.set()
                trigger_thread=threading.Thread(target=trigger,daemon=True)
                self.emit('Watching bottom screen: dark -> first change -> second change.')
                trigger_thread.start()
                duration=measure(cap.sample,self.stop)
                trigger_thread.join()
                if trigger_errors: raise trigger_errors[0]
                stamp=time.strftime('%Y%m%d-%H%M%S')
                cap.grab().save(OUT/f'encounter-{stamp}.png')
                self.emit(f'Measured introduction: {duration:.3f}s. Screenshot saved.')
                if baseline is None:
                    self.events.put(('baseline',duration))
                    self.emit('Paused: inspect this encounter. Confirm only if it is NORMAL and the battle menu has appeared. Otherwise press STOP.')
                    while not self.confirm.wait(.05):
                        if self.stop.is_set(): raise Stopped()
                    if self.stop.is_set(): raise Stopped()
                    baseline=duration
                    self.events.put(('confirmed',baseline))
                else:
                    result=classify(duration,baseline,o['threshold'])
                    self.emit(f'{result.upper()}: baseline {baseline:.3f}s; difference {duration-baseline:+.3f}s.')
                    if result != 'normal':
                        self.events.put(('alert',result)); return
                    baseline=min(baseline,duration)
                    self.events.put(('confirmed',baseline))
                if not repeat:
                    self.emit('Single-encounter test complete. No further reset.'); return
                # Screen is ready: next reset can begin immediately.
        except Stopped: self.emit('Stopped. Controls released.')
        except Exception as e: self.emit(f'STOPPED: {type(e).__name__}: {e}')
        finally:
            self.stop.set()
            if trigger_thread and trigger_thread.is_alive(): trigger_thread.join()
            try:
                if controller: controller.close()
            except Exception as e: self.emit(f'Release failed: {e}. Disable InputRedirection on the 3DS if a control remains held.')
            try:
                if cap: cap.close()
            finally: self.events.put(('done',None))

    def poll(self):
        while True:
            try: kind,value=self.events.get_nowait()
            except queue.Empty: break
            if kind=='log':
                text=f'{time.strftime("%H:%M:%S")}  {value}'
                self.status.set(value)
                self.log.configure(state='normal'); self.log.insert('end',text+'\n'); self.log.see('end'); self.log.configure(state='disabled')
                with (OUT/'events.log').open('a',encoding='utf-8') as f: f.write(text+'\n')
            elif kind=='baseline':
                self.pending_baseline=value; self.confirm_button.configure(state='normal')
            elif kind=='confirmed':
                self.baseline=value; self.confirm_button.configure(state='disabled')
            elif kind=='alert':
                self.root.bell()
                messagebox.showinfo('Hunt stopped',f'{value.upper()}. Inspect the 3DS. The bot has stopped and will not reset.')
            elif kind=='done':
                self.confirm_button.configure(state='disabled')
                for b in (self.start_button,self.test_button,self.preview_button,self.refresh_button,*self.setup_buttons): b.configure(state='normal')
        self.root.after(100,self.poll)

    def close(self):
        self.stop.set()
        if self.worker and self.worker.is_alive():
            self.root.after(100,self.close)
        else: self.root.destroy()


if __name__=='__main__':
    root=tk.Tk(); App(root); root.mainloop()
