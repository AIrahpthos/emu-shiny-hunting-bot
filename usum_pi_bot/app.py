"""USUM real-hardware bot with integrated direct bottom-screen capture."""
import json
import queue
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk, ImageStat
from capture_linux import ViewerUnavailable
from frame_feed import Capture, wait_for_capture
from capture_service import CaptureService
from core import Controller, Stopped, EncounterStartTimeout, measure, classify, choose_bottom_window, BOTTOM_WINDOW_PREFIX, trigger_encounter
from navigation import ColourDetector, load_save
from ntr_support import SOURCES
from reset_stats import ResetStats
from viewer_reports import read_reports, export_reports, is_capture_interruption

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'out'
OUT.mkdir(exist_ok=True)


class App:
    def __init__(self, root):
        self.root = root
        root.title('USUM Pi Shiny Hunter — integrated capture')
        root.geometry('780x750+10+10')
        self.capture_service=CaptureService(ROOT,self.emit_capture)
        self.preview_sequence=0
        self.capture_connect_thread=None
        self.stop = threading.Event()
        self.confirm = threading.Event()
        self.events = queue.Queue()
        self.worker = None
        self.point = (.5,.5)
        self.baseline = None
        self.pending_baseline = None
        self.windows = []
        self.setup_buttons = []
        self.capture_reports=[]
        self.report_signature=None
        self.report_check_time=0
        self.report_export_thread=None
        try:
            ack=json.loads((OUT/'capture-report-ack.json').read_text())
            self.report_ack_count=max(0,int(ack.get('count',0))) if ack.get('counter_version')==2 else 0
        except (OSError,ValueError,TypeError,AttributeError):
            self.report_ack_count=0
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
        capture_diagnostics=ttk.Frame(tabs,padding=12)
        tabs.add(capture_diagnostics,text='Capture diagnostics')
        ttk.Label(capture_diagnostics,text='Connection messages, stream statistics and console diagnostics.\nThese do not change the hunt result or count as interruptions by themselves.',wraplength=730).pack(anchor='w',pady=6)
        capture_scroll=ttk.Scrollbar(capture_diagnostics)
        capture_scroll.pack(side='right',fill='y')
        self.capture_log=tk.Text(capture_diagnostics,state='disabled',wrap='word',yscrollcommand=capture_scroll.set)
        self.capture_log.pack(fill='both',expand=True)
        capture_scroll.configure(command=self.capture_log.yview)
        reports=ttk.Frame(tabs,padding=12)
        tabs.add(reports,text='Recovery reports')
        self.tabs=tabs
        self.reports_tab=reports
        self.report_summary=tk.StringVar(value='Capture interruptions: 0')
        ttk.Label(reports,textvariable=self.report_summary,wraplength=710,font=('Segoe UI',12)).pack(anchor='w',pady=8)
        ttk.Label(reports,text='Saved across bot restarts. NTR reports count video outages, not control retries.\nIntentional desktop shutdowns are excluded. Showing the latest 200 interruptions.',wraplength=710).pack(anchor='w',pady=6)
        report_list=ttk.Frame(reports); report_list.pack(fill='both',expand=True,pady=8)
        self.report_tree=ttk.Treeview(report_list,columns=('time','reason'),show='headings',selectmode='extended')
        self.report_tree.heading('time',text='Time'); self.report_tree.heading('reason',text='Capture interruption')
        self.report_tree.column('time',width=230,stretch=False); self.report_tree.column('reason',width=440)
        report_scroll=ttk.Scrollbar(report_list,orient='vertical',command=self.report_tree.yview)
        self.report_tree.configure(yscrollcommand=report_scroll.set)
        report_scroll.pack(side='right',fill='y'); self.report_tree.pack(side='left',fill='both',expand=True)
        report_actions=ttk.Frame(reports); report_actions.pack(fill='x',pady=8)
        self.export_reports_button=ttk.Button(report_actions,text='Save selected reports as ZIP',command=self.save_capture_reports)
        self.export_reports_button.pack(side='left')
        ttk.Button(report_actions,text='Mark all reviewed',command=self.acknowledge_reports).pack(side='left',padx=8)
        ttk.Label(reports,text='Select one or more interruptions to export. With no selection, the latest 100 are included.\nThe ZIP contains viewer output, exit details and the recent bot log. Nothing is uploaded automatically.',wraplength=710).pack(anchor='w',pady=8)
        self.report_export_status=tk.StringVar(value='ZIP reports are saved in usum_pi_bot/out for download using Termius SFTP.')
        ttk.Label(reports,textvariable=self.report_export_status,wraplength=710).pack(anchor='w',pady=8)
        ttk.Label(frame, text='USUM static encounters on a real 3DS', font=('Segoe UI',16)).pack(anchor='w')
        ttk.Button(frame,textvariable=self.report_summary,command=lambda:self.tabs.select(self.reports_tab)).pack(anchor='w',pady=4)
        ttk.Label(frame, text='Bottom-screen capture is integrated. Covering the preview does not affect detection.').pack(anchor='w', pady=5)
        row = ttk.Frame(frame); row.pack(fill='x', pady=5)
        ttk.Label(row,text='3DS IP:').pack(side='left')
        self.ip = tk.StringVar(value=saved.get('ip',''))
        ttk.Entry(row,textvariable=self.ip,width=20).pack(side='left',padx=8)
        self.test_button = ttk.Button(row,text='Test controls (D-pad right)',command=lambda:self.start('test'))
        self.test_button.pack(side='left')
        row = ttk.Frame(frame); row.pack(fill='x', pady=3)
        ttk.Label(row,text='Capture source:').pack(side='left')
        self.capture_source=tk.StringVar(value=saved.get('capture_source','Loopy USB'))
        self.source_entry=ttk.Combobox(row,textvariable=self.capture_source,values=SOURCES,state='readonly',width=16)
        self.source_entry.pack(side='left',padx=8)
        self.source_entry.bind('<<ComboboxSelected>>',lambda _:self.source_changed())
        self.connect_button=ttk.Button(row,text='Connect capture',command=self.connect_capture)
        self.connect_button.pack(side='left')
        self.setup_buttons.extend((self.source_entry,self.connect_button))
        row=ttk.Frame(frame); row.pack(fill='x',pady=4)
        self.ntr_quality=tk.StringVar(value=str(saved.get('ntr_quality',40)))
        self.ntr_bandwidth=tk.StringVar(value=str(saved.get('ntr_bandwidth',10)))
        ttk.Label(row,text='NTR JPEG quality:').pack(side='left')
        self.quality_entry=ttk.Spinbox(row,from_=1,to=95,width=4,textvariable=self.ntr_quality)
        self.quality_entry.pack(side='left',padx=8)
        ttk.Label(row,text='Bandwidth (Mbps):').pack(side='left')
        self.bandwidth_entry=ttk.Spinbox(row,from_=1,to=40,width=4,textvariable=self.ntr_bandwidth)
        self.bandwidth_entry.pack(side='left',padx=8)
        self.setup_buttons.extend((self.quality_entry,self.bandwidth_entry))
        self.window_name=tk.StringVar(value='Capture disconnected. Choose a source and connect.')
        ttk.Label(frame,textvariable=self.window_name,wraplength=730).pack(anchor='w',pady=4)
        self.refresh_button=ttk.Button(frame,text='Reconnect capture',command=lambda:self.connect_capture(reconnect=True))
        self.refresh_button.pack(anchor='w')
        self.preview_button=ttk.Button(frame,text='Show bottom screen',command=self.preview)
        self.preview_button.pack(anchor='w',pady=3)
        self.preview_label = ttk.Label(setup,text='Bottom-screen preview')
        self.preview_label.pack(pady=5)
        self.preview_label.configure(text='Bottom-screen preview will appear here after connecting.')
        self.preview_label.bind('<Button-1>',self.pick)
        settings = ttk.Frame(frame); settings.pack(fill='x',pady=8)
        self.values = {}
        for index,(label,key,default) in enumerate([('Shiny extra seconds','threshold',1.1),('Forward hold seconds','forward',1)]):
            ttk.Label(settings,text=label).grid(row=index//2,column=(index%2)*2,sticky='w',padx=5,pady=3)
            var=tk.StringVar(value=str(saved.get(key,default))); self.values[key]=var
            ttk.Entry(settings,textvariable=var,width=7).grid(row=index//2,column=(index%2)*2+1,padx=8)
        self.repeat=tk.BooleanVar(value=False)
        ttk.Checkbutton(frame,text='Repeat normal encounters automatically (leave off for the first test)',variable=self.repeat).pack(anchor='w')
        self.auto_recover=tk.BooleanVar(value=saved.get('auto_recover',False))
        ttk.Checkbutton(frame,text='Resume after capture crash (retry may reset an unseen shiny)',variable=self.auto_recover).pack(anchor='w')
        self.adaptive_reset=tk.BooleanVar(value=saved.get('adaptive_reset',False))
        ttk.Checkbutton(frame,text='Retry failed attempts (may reset an unseen shiny)',variable=self.adaptive_reset).pack(anchor='w')
        row=ttk.Frame(frame); row.pack(fill='x',pady=3)
        self.ultra_beast=tk.BooleanVar(value=saved.get('ultra_beast',False))
        self.skip_changes=tk.StringVar(value=str(saved.get('skip_changes',0)))
        self.ub_toggle=ttk.Checkbutton(row,text='Ultra Beast mode',variable=self.ultra_beast)
        self.ub_toggle.pack(side='left')
        ttk.Label(row,text='Screen changes to skip:').pack(side='left',padx=8)
        self.skip_entry=ttk.Spinbox(row,from_=0,to=20,width=4,textvariable=self.skip_changes)
        self.skip_entry.pack(side='left')
        self.setup_buttons.extend((self.ub_toggle,self.skip_entry))
        row=ttk.Frame(frame); row.pack(fill='x',pady=8)
        self.start_button=ttk.Button(row,text='Start',command=lambda:self.start('hunt')); self.start_button.pack(side='left')
        ttk.Button(row,text='STOP',command=self.stop.set).pack(side='left',padx=8)
        self.confirm_button=ttk.Button(row,text='Confirm first encounter is normal',command=self.confirm.set,state='disabled'); self.confirm_button.pack(side='left')
        self.status=tk.StringVar(value='Ready. Test controls first; then preview the bottom screen.')
        ttk.Label(frame,textvariable=self.status,wraplength=730).pack(anchor='w',pady=6)
        self.log=tk.Text(frame,height=10,state='disabled',wrap='word'); self.log.pack(fill='both',expand=True)
        ttk.Label(setup,text='Save-load detection',font=('Segoe UI',15)).pack(anchor='w')
        ttk.Label(setup,text='Both Loopy and NTR use majority blue → black → red.\nNo screenshots or gradient references are needed.\nFrames come directly from the selected capture source; window visibility is irrelevant.',wraplength=730).pack(anchor='w',pady=8)
        rate_row=ttk.Frame(setup); rate_row.pack(fill='x',pady=8)
        ttk.Label(rate_row,text='Checks per second:').pack(side='left')
        self.ntr_hz=tk.StringVar(value=str(saved.get('colour_hz',saved.get('ntr_hz',30))))
        self.rate_entry=ttk.Combobox(rate_row,textvariable=self.ntr_hz,values=('10','30','60'),state='readonly',width=5)
        self.rate_entry.pack(side='left',padx=8)
        ttk.Label(rate_row,text='Try encounter after seconds:').pack(side='left')
        self.ntr_load_limit=tk.StringVar(value=str(saved.get('load_limit',saved.get('ntr_load_limit',16))))
        self.limit_entry=ttk.Entry(rate_row,textvariable=self.ntr_load_limit,width=6)
        self.limit_entry.pack(side='left',padx=8)
        self.setup_buttons.extend((self.rate_entry,self.limit_entry))
        self.auto_connect_capture=tk.BooleanVar(value=saved.get('auto_connect_capture',True))
        ttk.Checkbutton(setup,text='Connect saved capture automatically when the bot opens',
                        variable=self.auto_connect_capture,command=self.save_auto_connect).pack(anchor='w',pady=6)
        root.protocol('WM_DELETE_WINDOW',self.close)
        self.refresh()
        self.refresh_reports()
        root.after(100,self.poll)
        root.after(500,self.connect_saved_capture)

    def refresh_reports(self):
        folder=OUT/'capture-incidents'
        index=folder/'incidents.jsonl'
        try:
            stat=index.stat() if index.exists() else None
            signature=(stat.st_mtime_ns,stat.st_size) if stat else None
            if signature!=self.report_signature or not hasattr(self,'reports_loaded'):
                records=[record for record in read_reports(folder) if is_capture_interruption(record)]
                self.capture_reports=records
                self.report_signature=signature
                self.reports_loaded=True
                for item in self.report_tree.get_children(): self.report_tree.delete(item)
                for number,record in list(enumerate(records))[-200:]:
                    self.report_tree.insert('', 'end', iid='incident-'+str(number),
                                            values=(record.get('timestamp',''),record.get('reason','unknown exit')))
            count=len(self.capture_reports)
            unread=max(0,count-self.report_ack_count)
            latest=self.capture_reports[-1].get('timestamp','unknown') if count else 'none'
            self.report_summary.set(f'Capture interruptions: {count} | Unreviewed: {unread} | Last: {latest}')
        except (OSError,ValueError) as e:
            self.report_summary.set(f'Could not read recovery reports: {e}')

    def acknowledge_reports(self):
        self.refresh_reports()
        try:
            (OUT/'capture-report-ack.json').write_text(json.dumps({'count':len(self.capture_reports),'counter_version':2}))
            self.report_ack_count=len(self.capture_reports)
            self.refresh_reports()
        except OSError as e:
            messagebox.showerror('Recovery reports',str(e))

    def save_capture_reports(self):
        if self.report_export_thread and self.report_export_thread.is_alive(): return
        self.refresh_reports()
        selected=self.report_tree.selection()
        records=([self.capture_reports[int(item.split('-')[1])] for item in selected]
                 if selected else self.capture_reports[-100:])
        if not records:
            messagebox.showinfo('Recovery reports','No capture interruptions have been recorded yet.'); return
        filename=str(OUT/('capture-report-'+time.strftime('%Y%m%d-%H%M%S')+'-'+str(time.time_ns())+'.zip'))
        self.report_export_status.set('Saving diagnostic ZIP...')
        self.export_reports_button.configure(state='disabled')
        def export():
            try:
                export_reports(OUT/'capture-incidents',filename,records,OUT/'events.log')
                self.events.put(('report_export_done',(True,filename)))
            except Exception as e:
                self.events.put(('report_export_done',(False,str(e))))
        self.report_export_thread=threading.Thread(target=export,daemon=True)
        self.report_export_thread.start()

    def save_auto_connect(self):
        try:
            saved=json.loads((ROOT/'settings.json').read_text()) if (ROOT/'settings.json').exists() else {}
            saved['auto_connect_capture']=self.auto_connect_capture.get()
            (ROOT/'settings.json').write_text(json.dumps(saved,indent=2))
        except (OSError,ValueError) as e:
            messagebox.showerror('Capture settings',str(e))

    def connect_saved_capture(self):
        if self.stop.is_set() or not self.auto_connect_capture.get(): return
        if self.source()=='NTR wireless' and not self.ip.get().strip():
            self.emit('Enter the 3DS IP, then click Connect capture.'); return
        self.connect_capture()

    def capture_options(self):
        quality=int(self.ntr_quality.get()); bandwidth=int(self.ntr_bandwidth.get())
        if self.source()=='NTR wireless':
            from ntr_capture import stream_args
            stream_args(quality,bandwidth)
            import ipaddress
            ipaddress.IPv4Address(self.ip.get().strip())
        return quality,bandwidth

    def refresh(self):
        try:
            frame=self.capture_service.store.latest()
            self.window_name.set(f'{self.source()} bottom feed connected — frame {frame.sequence}')
        except ViewerUnavailable as e:
            self.window_name.set(str(e))

    def source(self):
        return self.capture_source.get() if hasattr(self,'capture_source') else 'Loopy USB'

    def source_changed(self):
        self.status.set('Source changed. Click Connect capture to apply.')

    def connect_capture(self, reconnect=False):
        if self.worker and self.worker.is_alive(): return
        if self.capture_connect_thread and self.capture_connect_thread.is_alive(): return
        try:
            quality,bandwidth=self.capture_options()
            source=self.source(); ip=self.ip.get().strip()
            saved=json.loads((ROOT/'settings.json').read_text()) if (ROOT/'settings.json').exists() else {}
            saved.update(capture_source=source,ip=ip,ntr_quality=quality,ntr_bandwidth=bandwidth,
                         auto_connect_capture=self.auto_connect_capture.get())
            (ROOT/'settings.json').write_text(json.dumps(saved,indent=2))
        except Exception as e:
            messagebox.showerror('Capture connection',str(e)); return
        self.connect_button.configure(state='disabled')
        self.refresh_button.configure(state='disabled')
        self.start_button.configure(state='disabled')
        self.source_entry.configure(state='disabled')
        def connect():
            try:
                if reconnect: self.capture_service.close()
                self.capture_service.connect(source,ip,quality,bandwidth)
            except Exception as e: self.emit(f'Capture connection failed: {e}')
            finally: self.events.put(('capture_connected',None))
        self.capture_connect_thread=threading.Thread(target=connect,daemon=True)
        self.capture_connect_thread.start()

    def selected(self, navigation=False):
        if self.capture_connect_thread and self.capture_connect_thread.is_alive():
            raise ValueError('Wait for capture connection to finish.')
        quality,bandwidth=self.capture_options()
        expected=(self.source(),self.ip.get().strip(),quality,bandwidth) if self.source()=='NTR wireless' else (self.source(),)
        if self.capture_service.config!=expected:
            raise ValueError('Click Connect capture to apply the selected source and settings first.')
        self.capture_service.store.latest()
        return self.capture_service.store

    def preview(self):
        try:
            frame=self.capture_service.store.latest()
            self.display_preview(frame)
            self.tabs.select(1)
        except ViewerUnavailable as e: self.window_name.set(str(e))

    def display_preview(self,frame):
        if frame.sequence==self.preview_sequence: return
        self.preview_sequence=frame.sequence
        image=frame.image.copy()
        image.thumbnail((320,240))
        self.preview_size=image.size
        self.preview_image=ImageTk.PhotoImage(image)
        self.preview_label.configure(image=self.preview_image,text='')

    def pick(self,event):
        if self.worker and self.worker.is_alive(): return
        if hasattr(self,'preview_size'):
            w,h=self.preview_size
            self.point=(min(.98,max(.02,event.x/w)),min(.98,max(.02,event.y/h)))
            self.status.set(f'Detection point selected: {self.point[0]:.0%} across, {self.point[1]:.0%} down.')

    def emit(self,text): self.events.put(('log',text))

    def emit_capture(self,text): self.events.put(('capture_log',text))

    def start(self,mode):
        if self.worker and self.worker.is_alive(): return
        try:
            options={key:float(var.get()) for key,var in self.values.items()}
            limits={'threshold':(.1,10),'forward':(0,5)}
            for key,value in options.items():
                low,high=limits[key]
                if not low <= value <= high: raise ValueError(f'{key} must be between {low} and {high}.')
            options['capture_source']=self.source()
            options['auto_connect_capture']=self.auto_connect_capture.get()
            options['ntr_quality'],options['ntr_bandwidth']=self.capture_options()
            options['colour_hz']=int(self.ntr_hz.get())
            options['load_limit']=float(self.ntr_load_limit.get())
            if options['colour_hz'] not in (10,30,60): raise ValueError('Check rate must be 10, 30 or 60 Hz.')
            if not 5<=options['load_limit']<=45: raise ValueError('Loading limit must be 5–45 seconds.')
            options['auto_recover']=self.auto_recover.get()
            options['adaptive_reset']=self.adaptive_reset.get()
            options['ultra_beast']=self.ultra_beast.get()
            options['skip_changes']=int(self.skip_changes.get())
            if not 0 <= options['skip_changes'] <= 20:
                raise ValueError('Screen changes to skip must be an integer from 0 to 20.')
            ip=self.ip.get().strip()
            import ipaddress
            ipaddress.IPv4Address(ip)
            hwnd=self.selected() if mode=='hunt' else None
            refs=ColourDetector() if mode=='hunt' else None
            if refs is not None:
                detector_key='ntr-sequence-v3-red' if self.source()=='NTR wireless' else 'usb-sequence-v1-red'
                options['stats_key']=f'{ip}|colour-categories|{detector_key}'
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
        trigger_cancel=threading.Event()
        baseline=None
        attempts=0
        consecutive_failures=0
        stats=None
        try:
            stats=ResetStats(OUT/'reset-observations.jsonl',o.get('stats_key','unconfigured')) if mode=='hunt' else None
            controller=Controller(ip,self.stop)
            if mode=='test':
                controller.hold(('RIGHT',),.25)
                self.emit('D-pad right sent. UDP has no connection acknowledgement: verify the console moved.'); return
            cap=Capture(hwnd,point)
            if hasattr(cap,"stop"): cap.stop=self.stop
            while not self.stop.is_set():
                phase='before encounter'
                try:
                    cap.grab()
                    attempts+=1; self.emit(f'Encounter {attempts}: resetting...')
                    controller.hold(('L','R','START'),.15)
                    controller.wait(1.0)
                    reset_start=time.monotonic()
                    loaded=load_save(controller,cap.grab,refs,self.stop,self.emit,
                                     timeout=o.get('load_limit',o.get('ntr_load_limit',16)),
                                     hz=o.get('colour_hz',o.get('ntr_hz',30)))
                    stats.record(loaded)
                    if loaded.gradient_seen:
                        self.emit(f'Observed load #{stats.observed_count}; blue → black → red confirmed.')
                    self.emit(f'Startup wait took {time.monotonic()-reset_start:.2f}s; load '+('confirmed.' if loaded.gradient_seen else 'inferred; encounter check required.'))
                    trigger_errors=[]
                    trigger_cancel.clear()
                    def trigger():
                        try:
                            trigger_encounter(controller,o['forward'],trigger_cancel)
                        except Exception as e:
                            trigger_errors.append(e)
                            self.stop.set()
                    phase='unclassified encounter'
                    self.emit('Watching bottom screen: dark -> first change -> second change.')
                    skip_changes=o.get('skip_changes',0) if o.get('ultra_beast',False) else 0
                    if skip_changes:
                        self.emit(f'Ultra Beast mode: skipping {skip_changes} changes after the initial dark screen before timing the encounter.')
                    trigger_thread=threading.Thread(target=trigger,daemon=True)
                    trigger_thread.start()
                    def stop_encounter_input():
                        trigger_cancel.set()
                        trigger_thread.join()
                        controller.release()
                        if trigger_errors:
                            raise trigger_errors[0]
                        self.emit('Battle-start dark screen detected. Controls released for timing.')
                    try:
                        duration=measure(cap.sample,self.stop,skip_changes=skip_changes,emit=self.emit,
                                         on_dark=stop_encounter_input)
                    finally:
                        trigger_cancel.set()
                        trigger_thread.join()
                        controller.release()
                    if trigger_errors: raise trigger_errors[0]
                    stamp=time.strftime('%Y%m%d-%H%M%S')
                    self.emit(f'Measured introduction: {duration:.3f}s.')
                    # Classify before taking a screenshot. Capture loss must never
                    # discard a suspected-shiny or uncertain result already measured.
                    if baseline is not None:
                        result=classify(duration,baseline,o['threshold'])
                        self.emit(f'{result.upper()}: baseline {baseline:.3f}s; difference {duration-baseline:+.3f}s.')
                        if result=='uncertain' and o.get('adaptive_reset',False):
                            raise TimeoutError('Measured introduction is too short to classify reliably.')
                        if result != 'normal':
                            try:
                                cap.grab().save(OUT/f'encounter-{stamp}.png')
                            except Exception as e:
                                self.emit(f'Could not save result screenshot: {e}')
                            self.events.put(('alert',result)); return
                        baseline=min(baseline,duration)
                        consecutive_failures=0
                        self.events.put(('confirmed',baseline))
                        phase='confirmed normal encounter'
                    try:
                        cap.grab().save(OUT/f'encounter-{stamp}.png')
                    except ViewerUnavailable:
                        if baseline is None or repeat:
                            raise
                        self.emit('Capture disappeared after the normal result; single test remains stopped.')
                    if baseline is None:
                        self.events.put(('baseline',duration))
                        self.emit('Paused: inspect this encounter. Confirm only if it is NORMAL and the battle menu has appeared. Otherwise press STOP.')
                        while not self.confirm.wait(.05):
                            if self.stop.is_set(): raise Stopped()
                        if self.stop.is_set(): raise Stopped()
                        baseline=duration
                        consecutive_failures=0
                        self.events.put(('confirmed',baseline))
                    if not repeat:
                        self.emit('Single-encounter test complete. No further reset.'); return
                except TimeoutError as e:
                    controller.release()
                    if self.stop.is_set(): raise Stopped()
                    if not o.get('adaptive_reset',False): raise
                    consecutive_failures+=1
                    stats.record_failure(attempts,phase,e,consecutive_failures)
                    self.emit(f'Attempt failed during {phase} ({consecutive_failures}/3 consecutive failures). {e}')
                    if consecutive_failures>=3:
                        self.events.put(('alert','repeated detection failure: three attempts in a row; inspect the game and capture feed'))
                        return
                    self.emit('Retrying the game soft reset; unobserved encounter status is unknown.')
                except ViewerUnavailable as e:
                    trigger_cancel.set()
                    if trigger_thread and trigger_thread.is_alive(): trigger_thread.join()
                    controller.release()
                    if self.stop.is_set(): raise Stopped()
                    if not o.get('auto_recover',False): raise
                    self.emit(f'CAPTURE LOST during {phase}: {e}. Controls released; waiting for fresh capture frames.')
                    if phase=='unclassified encounter':
                        self.emit('Interrupted encounter is unclassified. Automatic retry may reset an unseen shiny.')
                    cap.close(); cap=None
                    cap=wait_for_capture(point,self.stop,self.emit,store=hwnd)
                    stamp=time.strftime('%Y%m%d-%H%M%S')
                    try:
                        cap.grab().save(OUT/f'recovered-{stamp}.png')
                    except ViewerUnavailable:
                        continue
                    self.emit(f'Retrying after capture loss. Attempt count {attempts}; baseline preserved.')
        except Stopped: self.emit('Stopped. Controls released.')
        except Exception as e: self.emit(f'STOPPED: {type(e).__name__}: {e}')
        finally:
            self.stop.set()
            trigger_cancel.set()
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
            elif kind=='capture_log':
                self.capture_log.configure(state='normal')
                self.capture_log.insert('end',f'{time.strftime("%H:%M:%S")}  {value}\n')
                lines=int(self.capture_log.index('end-1c').split('.')[0])
                if lines>500: self.capture_log.delete('1.0',f'{lines-500}.0')
                self.capture_log.see('end'); self.capture_log.configure(state='disabled')
            elif kind=='baseline':
                self.pending_baseline=value; self.confirm_button.configure(state='normal')
            elif kind=='confirmed':
                self.baseline=value; self.confirm_button.configure(state='disabled')
            elif kind=='alert':
                self.root.bell()
                messagebox.showinfo('Hunt stopped',f'{value.upper()}. Inspect the 3DS. The bot has stopped and will not reset.')
            elif kind=='report_export_done':
                self.export_reports_button.configure(state='normal')
                ok,text=value
                if ok: self.report_export_status.set(f'Saved: {text}\nDownload this ZIP using Termius SFTP and attach it here.')
                else: self.report_export_status.set('Report export failed: '+text)
            elif kind=='capture_connected':
                self.connect_button.configure(state='normal')
                self.refresh_button.configure(state='normal')
                self.start_button.configure(state='normal')
                self.source_entry.configure(state='readonly')
            elif kind=='done':
                self.confirm_button.configure(state='disabled')
                for b in (self.start_button,self.test_button,self.preview_button,self.refresh_button,*self.setup_buttons): b.configure(state='readonly' if b in (self.source_entry,self.rate_entry) else 'normal')
        if time.monotonic()-self.report_check_time>=2:
            self.report_check_time=time.monotonic()
            self.refresh_reports()
        try:
            frame=self.capture_service.store.latest()
            self.display_preview(frame)
            self.window_name.set(f'Bottom feed connected — frame {frame.sequence}')
        except ViewerUnavailable as e:
            self.window_name.set(str(e))
        self.root.after(100,self.poll)

    def close(self):
        self.stop.set()
        if ((self.worker and self.worker.is_alive()) or
            (self.report_export_thread and self.report_export_thread.is_alive())):
            self.root.after(100,self.close)
        elif self.capture_connect_thread and self.capture_connect_thread.is_alive():
            self.root.after(100,self.close)
        else:
            self.capture_service.close()
            self.root.destroy()


if __name__=='__main__':
    root=tk.Tk(); App(root); root.mainloop()
