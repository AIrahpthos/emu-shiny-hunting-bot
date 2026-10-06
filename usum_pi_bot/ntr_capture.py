"""Bottom-only NTR JPEG Compat receiver; no viewer or screenshot dependency.

Protocol fields checked against xzn/ntrviewer-hr ntr_hb.c and ntr_rp.c.
Reliable Stream and Delta formats are intentionally not requested.
"""
from collections import OrderedDict
from io import BytesIO
from pathlib import Path
import ipaddress
import select
import socket
import struct
import threading
import time
from PIL import Image

HEADER=struct.Struct('<21I')
PAYLOAD=1444
MAX_PACKETS=256


def control_packet(sequence, command=0, args=()):
    if len(args)>16: raise ValueError('Too many NTR arguments.')
    return HEADER.pack(0x12345678,sequence,0,command,*args,*([0]*(16-len(args))),0)


def stream_args(quality, bandwidth, port=8001):
    if type(quality) is not int or not 1<=quality<=95: raise ValueError('JPEG quality must be 1–95.')
    if type(bandwidth) is not int or not 1<=bandwidth<=40: raise ValueError('Bandwidth must be 1–40 Mbps.')
    if not 1024<=port<=65535: raise ValueError('Invalid video port.')
    # top priority=false, factor=0: bottom screen only. Audio and stereo disabled.
    return (0,quality,bandwidth*128*1024,1404036572,port,0,0)


class JpegAssembler:
    """Bounded reassembly: discard incomplete, expired and obsolete frames."""
    def __init__(self, max_age=.5):
        self.frames=OrderedDict()
        self.max_age=max_age
        self.last_id=None
        self.dropped=0
        self.last_completion=0

    def push(self, packet, now=None):
        now=time.monotonic() if now is None else now
        for key in list(self.frames):
            if now-self.frames[key]['created']>self.max_age:
                del self.frames[key]; self.dropped+=1
        if not 4<len(packet)<=1448: return None
        frame_id,flags,format_code,index=packet[:4]
        # Bottom is screen bit 0=0; JPEG Compat full resolution is format 2.
        if flags & ~0x11 or flags & 1 or format_code!=2: return None
        data=packet[4:]; end=bool(flags&0x10)
        if not end and len(data)!=PAYLOAD: return None
        if self.last_id is not None and now-self.last_completion<=self.max_age and ((frame_id-self.last_id)&255) not in range(1,128): return None
        frame=self.frames.setdefault(frame_id,{'created':now,'parts':{},'end':None})
        self.frames.move_to_end(frame_id)
        while len(self.frames)>4:
            self.frames.popitem(last=False); self.dropped+=1
        existing=frame['parts'].get(index)
        if existing is not None and existing!=data:
            del self.frames[frame_id]; self.dropped+=1; return None
        frame['parts'][index]=data
        if end:
            if frame['end'] is not None and frame['end']!=index:
                del self.frames[frame_id]; self.dropped+=1; return None
            frame['end']=index
        last=frame['end']
        if last is None or not all(i in frame['parts'] for i in range(last+1)): return None
        raw=b''.join(frame['parts'][i] for i in range(last+1))
        del self.frames[frame_id]
        if not raw.startswith(b'\xff\xd8') or not raw.endswith(b'\xff\xd9'): self.dropped+=1; return None
        try:
            with Image.open(BytesIO(raw)) as image:
                if image.size!=(240,320): raise ValueError('Unexpected NTR dimensions.')
                image.load()
                result=image.convert('RGB').transpose(Image.Transpose.ROTATE_90)
        except (OSError,ValueError): self.dropped+=1; return None
        self.last_id=frame_id; self.last_completion=now
        return result


class NtrCapture:
    def __init__(self, store, ip, quality=40, bandwidth=10, emit=lambda _:None, port=8001, logs=None):
        self.store=store
        self.ip=str(ipaddress.IPv4Address(ip))
        self.args=stream_args(quality,bandwidth,port)
        self.callback=emit; self.port=port
        self.logs=Path(logs) if logs else None
        self.log_lock=threading.Lock(); self.log_path=None
        if self.logs:
            self.logs.mkdir(parents=True,exist_ok=True)
            self.log_path=self.logs/f"ntr-{time.time_ns()}.log"
        self.stop=threading.Event(); self.sock=None; self.tcp=None
        self.assembler=JpegAssembler()
        self.threads=[]
        self.stream_requested=False
        self.control_warning=False
        self.had_video=False
        self.video_outage=False

    def emit(self, message):
        if self.log_path:
            with self.log_lock, self.log_path.open("a",encoding="utf-8") as log:
                log.write(time.strftime("%Y-%m-%d %H:%M:%S")+" "+message+"\n")
        self.callback(message)

    def start(self):
        udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try:
            udp.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,1024*1024)
            udp.bind(('',self.port)); udp.settimeout(.1)
        except Exception:
            udp.close(); raise
        self.sock=udp
        self.threads=[threading.Thread(target=self._video,daemon=True),threading.Thread(target=self._control,daemon=True)]
        for thread in self.threads: thread.start()

    def _video(self):
        last_report=time.monotonic(); frames=0; last_frames=0; last_dropped=0
        while not self.stop.is_set():
            now=time.monotonic()
            self._check_video_health(now)
            if now-last_report>=5:
                self.emit(f'NTR bottom feed: {(frames-last_frames)/(now-last_report):.1f} FPS, {self.assembler.dropped-last_dropped} incomplete/invalid frames dropped in this interval.')
                last_report=now; last_frames=frames; last_dropped=self.assembler.dropped
            try:
                data,address=self.sock.recvfrom(2048)
                if address[0]!=self.ip: continue
                image=self.assembler.push(data)
                if image is not None:
                    self.store.publish(image); frames+=1
                    self._video_arrived()
            except socket.timeout: continue
            except OSError:
                if not self.stop.is_set():
                    self.emit('NTR video socket closed unexpectedly.')
                    self._record_video_outage('NTR video socket closed unexpectedly.')
                return

    def _video_arrived(self):
        self.had_video=True
        if self.video_outage:
            self.emit('NTR bottom video restored.')
            self.video_outage=False

    def _record_video_outage(self, reason):
        if not self.had_video or self.video_outage or self.stop.is_set(): return
        self.video_outage=True
        self.emit(reason)
        if self.logs:
            from viewer_reports import record_exit
            with self.log_lock:
                record_exit(self.logs, {'log_file':self.log_path.name,'returncode':-1,
                            'reason':reason,'capture_source':'NTR wireless',
                            'incident_kind':'video_loss'})
                self.log_path=self.logs/f'ntr-{time.time_ns()}.log'

    def _check_video_health(self, now=None):
        now=time.monotonic() if now is None else now
        if now-self.assembler.last_completion>self.store.stale_seconds:
            self._record_video_outage('NTR bottom video stalled: no fresh frames for two seconds.')

    def _feed_live(self):
        from capture_linux import ViewerUnavailable
        try:
            self.store.latest()
            return True
        except ViewerUnavailable:
            return False

    def _control_failure(self, error):
        """TCP failure does not imply loss of the independent UDP video feed."""
        if self._feed_live():
            if not self.control_warning:
                self.emit(f'NTR control link unavailable: {error}. Bottom video is still live; continuing capture without reconnecting control.')
                self.control_warning=True
            return None if self.stream_requested else 3
        if self.stream_requested:
            self.emit(f'NTR control unavailable: {error}. Automatic stream restart disabled; use Reconnect capture if video does not return.')
            return None
        self.emit(f'NTR control unavailable and no fresh video: {error}. Retrying in 3 seconds.')
        return 3

    def _wait_to_retry(self, delay):
        # Quiet retries while streaming, but respond promptly if video also stalls.
        deadline=time.monotonic()+delay
        while not self.stop.is_set() and time.monotonic()<deadline:
            if delay>3 and not self._feed_live(): return
            self.stop.wait(.1)

    def _control(self):
        if self.stream_requested: return
        attempts=0
        while not self.stop.is_set():
            tcp=None
            retry_delay=3
            attempts+=1
            try:
                if not self.control_warning:
                    self.emit(f'Connecting NTR bottom stream to {self.ip} (JPEG Compat).')
                tcp=socket.create_connection((self.ip,8000),timeout=3)
                self.tcp=tcp; tcp.settimeout(1)
                sequence=0
                buffer=bytearray(); heartbeat=time.monotonic(); partial_since=None
                while not self.stop.is_set():
                    ready,_,_=select.select([tcp],[],[],.1)
                    if ready:
                        chunk=tcp.recv(65536)
                        if not chunk: raise ConnectionError('NTR control connection closed.')
                        if not buffer: partial_since=time.monotonic()
                        buffer.extend(chunk)
                        while len(buffer)>=HEADER.size:
                            header=HEADER.unpack_from(buffer)
                            if header[0]!=0x12345678 or header[-1]>1024*1024:
                                raise ValueError('Invalid NTR control response.')
                            size=HEADER.size+header[-1]
                            if len(buffer)<size: break
                            message=bytes(buffer[HEADER.size:size])
                            del buffer[:size]
                            if self.control_warning:
                                self.emit('NTR control link restored.')
                                self.control_warning=False
                            if header[3]==0 and message:
                                self.emit('NTR: '+message.decode('utf-8','replace').strip()[:1000])
                        if not buffer: partial_since=None
                    now=time.monotonic()
                    # Match NTRViewer-HR: complete incoming packets before sending.
                    # A truncated response must not accumulate more control traffic.
                    if buffer:
                        if now-partial_since>=2:
                            raise TimeoutError('Incomplete NTR control response for two seconds.')
                        continue
                    if now-heartbeat>=.25:
                        tcp.sendall(control_packet(sequence)); sequence=(sequence+1)&0xffffffff
                        heartbeat=now
                        if not self.stream_requested:
                            # The working viewer sends heartbeat seq=0, then start seq=1.
                            tcp.sendall(control_packet(sequence,901,self.args)); sequence=(sequence+1)&0xffffffff
                            self.stream_requested=True
                            self.emit('NTR stream requested after initial heartbeat; waiting for bottom-screen frames.')
            except (OSError,ValueError) as e:
                if not self.stop.is_set():
                    retry_delay=self._control_failure(e)
            finally:
                self.tcp=None
                if tcp: tcp.close()
            if self.stream_requested or retry_delay is None: return
            if attempts>=3:
                self.emit('NTR initial connection failed three times; use Reconnect capture to try again.')
                return
            self._wait_to_retry(retry_delay)

    def close(self):
        self.stop.set()
        for sock in (self.tcp,self.sock):
            if sock:
                try: sock.shutdown(socket.SHUT_RDWR)
                except OSError: pass
                sock.close()
        for thread in self.threads: thread.join(4)
        self.store.invalidate('NTR capture disconnected.')
