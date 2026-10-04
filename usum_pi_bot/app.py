"""USUM real-hardware static encounter bot. cc3dsfs bottom-screen viewer must stay visible on X11."""
import json
import queue
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk, ImageStat
from capture_linux import Capture, Desktop, ViewerUnavailable
from recovery import wait_for_capture
from core import Controller, Stopped, EncounterStartTimeout, measure, classify, choose_bottom_window, BOTTOM_WINDOW_PREFIX, trigger_encounter
from navigation import ColourDetector, load_save
from ntr_support import SOURCES, choose_viewer, position_ntr
from reset_stats import ResetStats
from viewer_reports import read_reports, export_reports

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'out'
OUT.mkdir(exist_ok=True)


class App:
    def __init__(self, root):
        self.root = root
        root.title('USUM Pi Shiny Hunter — recovery reports')
        root.geometry('760x780+10+10')
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
            self.report_ack_count=max(0,int(json.loads((OUT/'capture-report-ack.json').read_text()).get('count',0)))
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
        reports=ttk.Frame(tabs,padding=12)
        tabs.add(reports,text='Recovery reports')
        self.tabs=tabs
        self.reports_tab=reports
        self.report_summary=tk.StringVar(value='Capture interruptions: 0')
        ttk.Label(reports,textvariable=self.report_summary,wraplength=710,font=('Segoe UI',12)).pack(anchor='w',pady=8)
        ttk.Label(reports,text='Saved across bot restarts. Exit 0 can mean a disconnect or manual close.\nIntentional desktop shutdowns are excluded. Showing the latest 200 interruptions.',wraplength=710).pack(anchor='w',pady=6)
        report_list=ttk.Frame(reports); report_list.pack(fill='both',expand=True,pady=8)
        self.report_tree=ttk.Treeview(report_list,columns=('time','reason'),show='headings',selectmode='extended')
        self.report_tree.heading('time',text='Time'); self.report_tree.heading('reason',text='Viewer exit / restart reason')
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
        ttk.Label(frame, text='Keep the bottom viewer visible. For NTR, choose Bottom Only, hide settings and fit.').pack(anchor='w', pady=5)
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
        self.layout_button=ttk.Button(row,text='Fit NTR bottom screen',command=self.layout_ntr)
        self.layout_button.pack(side='left')
        self.setup_buttons.extend((self.source_entry,self.layout_button))
        self.show_loopy_bottom=tk.BooleanVar(value=saved.get('show_loopy_bottom',True))
        self.loopy_toggle=ttk.Checkbutton(frame,text='Keep Loopy bottom viewer open in NTR mode',variable=self.show_loopy_bottom,command=self.source_changed)
        self.loopy_toggle.pack(anchor='w')
        self.setup_buttons.append(self.loopy_toggle)
        row = ttk.Frame(frame); row.pack(fill='x', pady=5)
        ttk.Label(row,text='Bottom screen:').pack(side='left',padx=4)
        self.window_name=tk.StringVar(value='Looking for cc3dsfs_bot...')
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
        ttk.Label(setup,text='Both Loopy and NTR use majority blue → black → red.\nNo screenshots or gradient references are needed.\nKeep the selected bottom-screen viewer visible and free of settings overlays.',wraplength=730).pack(anchor='w',pady=8)
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
        root.protocol('WM_DELETE_WINDOW',self.close)
        self.refresh()
        self.refresh_reports()
        root.after(100,self.poll)

    def refresh_reports(self):
        folder=OUT/'capture-incidents'
        index=folder/'incidents.jsonl'
        try:
            stat=index.stat() if index.exists() else None
            signature=(stat.st_mtime_ns,stat.st_size) if stat else None
            if signature!=self.report_signature or not hasattr(self,'reports_loaded'):
                records=read_reports(folder)
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
            (OUT/'capture-report-ack.json').write_text(json.dumps({'count':len(self.capture_reports)}))
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

    def refresh(self):
        desktop=None
        try:
            desktop=Desktop()
            self.windows=desktop.windows()
        except Exception as e:
            self.windows=[]
            self.window_name.set(str(e))
            return
        finally:
            if desktop: desktop.close()
        try:
            hwnd=choose_viewer(self.windows,self.source())
            self.window_name.set(next(title for wid,title in self.windows if wid==hwnd))
        except ValueError as e:
            self.window_name.set(str(e))

    def source(self):
        return self.capture_source.get() if hasattr(self,'capture_source') else 'Loopy USB'

    def source_changed(self):
        try:
            saved=json.loads((ROOT/'settings.json').read_text()) if (ROOT/'settings.json').exists() else {}
            saved['capture_source']=self.source()
            saved['show_loopy_bottom']=self.show_loopy_bottom.get()
            (ROOT/'settings.json').write_text(json.dumps(saved,indent=2))
        except (OSError,ValueError) as e:
            messagebox.showerror('Capture source',str(e))
        self.refresh()

    def layout_ntr(self):
        try: position_ntr()
        except Exception as e: messagebox.showerror('NTR layout',str(e))

    def selected(self, navigation=False):
        self.refresh()
        return choose_viewer(self.windows,self.source())

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
            options['capture_source']=self.source()
            options['show_loopy_bottom']=self.show_loopy_bottom.get()
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
                    try:
                        duration=measure(cap.sample,self.stop,skip_changes=skip_changes,emit=self.emit)
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
                    self.emit(f'CAPTURE LOST during {phase}: {e}. Controls released; waiting for viewer recovery.')
                    if phase=='unclassified encounter':
                        self.emit('Interrupted encounter is unclassified. Automatic retry may reset an unseen shiny.')
                    cap.close(); cap=None
                    cap=wait_for_capture(point,self.stop,self.emit,source='NTR wireless') if o.get('capture_source')=='NTR wireless' else wait_for_capture(point,self.stop,self.emit)
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
            elif kind=='done':
                self.confirm_button.configure(state='disabled')
                for b in (self.start_button,self.test_button,self.preview_button,self.refresh_button,*self.setup_buttons): b.configure(state='readonly' if b in (self.source_entry,self.rate_entry) else 'normal')
        if time.monotonic()-self.report_check_time>=2:
            self.report_check_time=time.monotonic()
            self.refresh_reports()
        self.root.after(100,self.poll)

    def close(self):
        self.stop.set()
        if ((self.worker and self.worker.is_alive()) or
            (self.report_export_thread and self.report_export_thread.is_alive())):
            self.root.after(100,self.close)
        else: self.root.destroy()


if __name__=='__main__':
    root=tk.Tk(); App(root); root.mainloop()
