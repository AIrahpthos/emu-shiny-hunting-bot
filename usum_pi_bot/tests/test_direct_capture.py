import io
import os
from pathlib import Path
import socket
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, Mock
from PIL import Image
from frame_feed import FrameStore, Capture
from capture_linux import ViewerUnavailable
from core import Stopped
from ntr_capture import JpegAssembler, control_packet, stream_args, NtrCapture, HEADER, PAYLOAD
from capture_service import CaptureService
from loopy_capture import LoopyCapture


def jpeg_packets(frame_id=1):
    image=Image.new('RGB',(240,320))
    # Distinct corners establish the native portrait -> landscape orientation.
    for y in range(160):
        for x in range(240): image.putpixel((x,y),(255,0,0))
    data=io.BytesIO(); image.save(data,'JPEG',quality=80)
    raw=data.getvalue()
    parts=[raw[i:i+PAYLOAD] for i in range(0,len(raw),PAYLOAD)]
    return [bytes((frame_id,0x10 if i==len(parts)-1 else 0,2,i))+part for i,part in enumerate(parts)]


class DirectFrameTests(unittest.TestCase):
    def test_capture_uses_no_desktop_and_rejects_repeated_frame(self):
        store=FrameStore(); store.publish(Image.new('RGB',(320,240),'red'))
        with patch('capture_linux.Desktop',side_effect=AssertionError('Desktop access')):
            cap=Capture(store,(.5,.5))
            self.assertEqual(cap.grab().size,(320,240))
            with self.assertRaises(ViewerUnavailable): store.next(cap.sequence,timeout=.01)
            store.publish(Image.new('RGB',(320,240),'blue'))
            self.assertEqual(cap.sample(),(0,0,255))

    def test_stale_frames_and_disconnected_frames_rejected(self):
        store=FrameStore(); store.publish(Image.new('RGB',(320,240)),time.monotonic()-3)
        with self.assertRaises(ViewerUnavailable): store.latest()
        store.invalidate('disconnected')
        with self.assertRaisesRegex(ViewerUnavailable,'disconnected'): store.next(timeout=.01)

    def test_stop_interrupts_wait_for_new_frame(self):
        stop=threading.Event(); stop.set()
        with self.assertRaises(Stopped): FrameStore().next(stop=stop)

    def test_latest_only_and_immutable_publish(self):
        store=FrameStore(); image=Image.new('RGB',(320,240),'red')
        store.publish(image); image.paste('green',(0,0,320,240))
        self.assertEqual(store.latest().image.getpixel((0,0)),(255,0,0))
        for _ in range(20): store.publish(image)
        self.assertEqual(store.next().sequence,21)

    def test_quality_and_bandwidth_control_fields(self):
        values=HEADER.unpack(control_packet(4,901,stream_args(40,10)))
        self.assertEqual(values[:4],(0x12345678,4,0,901))
        self.assertEqual(values[4:11],(0,40,10*128*1024,1404036572,8001,0,0))
        self.assertEqual(values[-1],0)
        for q,b in [(0,10),(96,10),(40,0),(40,41)]:
            with self.assertRaises(ValueError): stream_args(q,b)

    def test_out_of_order_packets_bottom_only_and_orientation(self):
        assembler=JpegAssembler(); packets=jpeg_packets()
        top=bytes((1,1,2,0))+packets[0][4:]
        self.assertIsNone(assembler.push(top))
        result=None
        for packet in reversed(packets): result=assembler.push(packet) or result
        self.assertEqual(result.size,(320,240))
        self.assertGreater(result.getpixel((20,100))[0],200)
        self.assertLess(result.getpixel((300,100))[0],20)
        for packet in packets: self.assertIsNone(assembler.push(packet))

    def test_missing_expired_and_old_packets_do_not_publish(self):
        assembler=JpegAssembler(); packets=jpeg_packets()
        self.assertIsNone(assembler.push(packets[-1],now=1))
        for packet in packets[:-1]: self.assertIsNone(assembler.push(packet,now=2))
        result=None
        for packet in jpeg_packets(2): result=assembler.push(packet,now=2.1) or result
        self.assertIsNotNone(result)
        for packet in packets: self.assertIsNone(assembler.push(packet,now=2.2))

    def test_invalid_headers_and_corrupt_jpeg_are_rejected(self):
        assembler=JpegAssembler()
        for data in [b'',b'abcd',bytes((1,0x10,3,0))+b'jpeg',bytes((1,0x10,2,0))+b'\xff\xd8broken\xff\xd9']:
            self.assertIsNone(assembler.push(data))

    def test_wraparound_frame_ids(self):
        assembler=JpegAssembler()
        for fid in [254,255,0,1]:
            result=None
            for packet in jpeg_packets(fid): result=assembler.push(packet) or result
            self.assertIsNotNone(result)

    def test_service_reuses_input_ip_and_usb_has_no_ip_dependency(self):
        with tempfile.TemporaryDirectory() as tmp, patch('capture_service.NtrCapture') as ntr, patch('capture_service.LoopyCapture') as usb:
            service=CaptureService(tmp)
            service.connect('NTR wireless','10.0.0.106',40,10)
            self.assertEqual(ntr.call_args.args[1:4],('10.0.0.106',40,10))
            service.connect('NTR wireless','10.0.0.106',40,10)
            self.assertEqual(ntr.call_count,1)
            service.connect('Loopy USB','not-an-ip',40,10)
            self.assertEqual(usb.call_count,1); ntr.return_value.close.assert_called_once()
            service.close()

    def test_real_tcp_control_and_udp_jpeg_receiver(self):
        tcp=socket.socket(); tcp.bind(('127.0.0.1',0)); tcp.listen()
        tcp_port=tcp.getsockname()[1]
        udp_probe=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        udp_probe.bind(('127.0.0.1',0)); udp_port=udp_probe.getsockname()[1]; udp_probe.close()
        stop=threading.Event(); packets=jpeg_packets(); got=[]; errors=[]
        def console():
            try:
                connection,_=tcp.accept(); connection.settimeout(2)
                with connection:
                    data=b''
                    while len(data)<HEADER.size: data+=connection.recv(HEADER.size-len(data))
                    got.append(HEADER.unpack(data))
                    # Deliberately split a valid heartbeat response across TCP reads.
                    response=control_packet(0)
                    connection.sendall(response[:9]); connection.sendall(response[9:])
                    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:
                        for packet in packets: sender.sendto(packet,('127.0.0.1',udp_port))
                    while not stop.wait(.05): pass
            except Exception as e: errors.append(e)
        thread=threading.Thread(target=console,daemon=True); thread.start()
        original=socket.create_connection
        store=FrameStore(); backend=NtrCapture(store,'127.0.0.1',40,10,port=udp_port)
        try:
            with patch('ntr_capture.socket.create_connection',side_effect=lambda address,timeout:original(('127.0.0.1',tcp_port),timeout)):
                backend.start()
                frame=store.next(timeout=3)
                self.assertEqual(frame.image.size,(320,240))
                self.assertEqual(got[0][3],901)
                self.assertEqual(got[0][8],udp_port)
                stop.set(); backend.close()
        finally:
            stop.set(); backend.close(); tcp.close(); thread.join(3)
        self.assertFalse(errors)
        self.assertTrue(all(not t.is_alive() for t in backend.threads))

    def test_real_native_pipe_and_child_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            helper=Path(tmp)/'fake-helper'
            helper.write_text('''#!/usr/bin/env python3
import os,struct,time
fd=int(os.environ['SHINY_FRAME_FD'])
pixels=bytes([255,0,0])*(240*320)
data=struct.pack('<4sIQQ',b'SBF1',len(pixels),1,time.monotonic_ns())+pixels
while data:
 n=os.write(fd,data[:777]); data=data[n:]
time.sleep(10)
''')
            helper.chmod(0o755)
            store=FrameStore(); backend=LoopyCapture(store,helper,Path(tmp)/'logs')
            try:
                backend.start(); frame=store.next(timeout=3)
                self.assertEqual(frame.image.getpixel((0,0)),(255,0,0))
                proc=backend.process
            finally: backend.close()
            self.assertIsNotNone(proc.poll()); self.assertFalse(backend.thread.is_alive())

class DirectRecoveryTests(unittest.TestCase):
    def test_loopy_exit_is_logged_and_helper_restarts(self):
        from viewer_reports import read_reports
        with tempfile.TemporaryDirectory() as tmp:
            helper=Path(tmp)/'fake-helper'
            helper.write_text('''#!/usr/bin/env python3
import os,struct,time
from pathlib import Path
marker=Path('first-run')
if not marker.exists():
 marker.write_text('done'); raise SystemExit(7)
fd=int(os.environ['SHINY_FRAME_FD'])
pixels=bytes([0,0,255])*(240*320)
data=struct.pack('<4sIQQ',b'SBF1',len(pixels),1,time.monotonic_ns())+pixels
while data:
 n=os.write(fd,data);data=data[n:]
time.sleep(10)
''')
            helper.chmod(0o755);store=FrameStore()
            backend=LoopyCapture(store,helper,Path(tmp)/'logs')
            try:
                backend.start();frame=store.next(timeout=6)
                self.assertEqual(frame.image.getpixel((0,0)),(0,0,255))
                reports=read_reports(Path(tmp)/'logs')
                self.assertEqual(len(reports),1)
                self.assertEqual(reports[0]['returncode'],7)
                self.assertTrue((Path(tmp)/'logs'/reports[0]['log_file']).is_file())
            finally:backend.close()
            self.assertEqual(len(read_reports(Path(tmp)/'logs')),1)

    def test_ntr_video_can_arrive_after_control_disconnect_without_reconnect(self):
        from viewer_reports import read_reports
        with tempfile.TemporaryDirectory() as tmp:
            server=socket.socket();server.bind(('127.0.0.1',0));server.listen();server.settimeout(7)
            tcp_port=server.getsockname()[1]
            udp_probe=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
            udp_probe.bind(('127.0.0.1',0));port=udp_probe.getsockname()[1];udp_probe.close()
            stop=threading.Event();requests=[];errors=[];packets=jpeg_packets()
            def console():
                try:
                    conn,_=server.accept();conn.settimeout(3)
                    with conn:
                        raw=b''
                        while len(raw)<HEADER.size:raw+=conn.recv(HEADER.size-len(raw))
                        requests.append(HEADER.unpack(raw))
                    # The independent UDP sender keeps working after TCP closes.
                    stop.wait(.1)
                    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:
                        for packet in packets:sender.sendto(packet,('127.0.0.1',port))
                    stop.wait(3)
                except Exception as e:errors.append(e)
            thread=threading.Thread(target=console,daemon=True);thread.start()
            original=socket.create_connection;store=FrameStore()
            backend=NtrCapture(store,'127.0.0.1',40,10,port=port,logs=Path(tmp)/'logs')
            try:
                with patch('ntr_capture.socket.create_connection',side_effect=lambda address,timeout:original(('127.0.0.1',tcp_port),timeout)):
                    backend.start();store.next(timeout=7)
                    self.assertEqual(len(requests),1)
                    self.assertEqual(requests[0][3],901)
                    self.assertEqual(len(read_reports(Path(tmp)/'logs')),0)
                    stop.set();backend.close()
            finally:
                stop.set();backend.close();server.close();thread.join(3)
            self.assertFalse(errors)

class NtrControlHealthTests(unittest.TestCase):
    def test_control_timeout_keeps_live_video_and_does_not_record_capture_crash(self):
        from viewer_reports import read_reports
        with tempfile.TemporaryDirectory() as tmp:
            store=FrameStore();store.publish(Image.new('RGB',(320,240),'blue'))
            messages=[];backend=NtrCapture(store,'10.0.0.106',emit=messages.append,logs=Path(tmp))
            backend.stream_requested=True
            self.assertIsNone(backend._control_failure(socket.timeout('timed out')))
            self.assertEqual(store.latest().sequence,1)
            self.assertEqual(read_reports(tmp),[])
            backend._control_failure(socket.timeout('timed out'))
            self.assertEqual(len(messages),1)

    def test_control_failure_before_first_video_is_not_an_interruption(self):
        from viewer_reports import read_reports
        with tempfile.TemporaryDirectory() as tmp:
            store=FrameStore();backend=NtrCapture(store,'10.0.0.106',logs=Path(tmp))
            self.assertEqual(backend._control_failure(ConnectionError('closed')),3)
            self.assertEqual(len(read_reports(tmp)),0)
            with self.assertRaises(ViewerUnavailable):store.latest()

    def test_no_control_reconnect_after_stream_requested_even_if_video_stale(self):
        backend=NtrCapture(FrameStore(),'10.0.0.106');backend.stream_requested=True
        with patch('ntr_capture.socket.create_connection') as connect:
            backend._control()
        connect.assert_not_called()

    def test_video_gap_does_not_resend_stream_command_and_closed_tcp_does_not_retry(self):
        backend=NtrCapture(FrameStore(),'10.0.0.106')
        fake=Mock();fake.recv.return_value=b''
        sent=[]
        fake.sendall.side_effect=lambda data: sent.append(HEADER.unpack(data)[3])
        with patch('ntr_capture.socket.create_connection',return_value=fake) as connect, \
             patch('ntr_capture.select.select',side_effect=[([],[],[]),([fake],[],[])]), \
             patch('ntr_capture.time.monotonic',side_effect=__import__('itertools').chain([0],__import__('itertools').repeat(60))), \
             patch.object(backend,'_wait_to_retry') as retry:
            backend._control()
        self.assertEqual(sent,[901,0])
        self.assertEqual(connect.call_count,1)
        retry.assert_not_called()

    def test_initial_connection_attempts_are_bounded(self):
        backend=NtrCapture(FrameStore(),'10.0.0.106')
        with patch('ntr_capture.socket.create_connection',side_effect=OSError('offline')) as connect, \
             patch.object(backend,'_wait_to_retry'):
            backend._control()
        self.assertEqual(connect.call_count,3)

    def test_quiet_retry_is_interrupted_when_video_has_stalled(self):
        backend=NtrCapture(FrameStore(),'10.0.0.106')
        with patch.object(backend.stop,'wait') as wait:
            backend._wait_to_retry(30)
        wait.assert_not_called()

class NtrOutageReportingTests(unittest.TestCase):
    def test_only_one_report_per_established_video_outage(self):
        from viewer_reports import read_reports, is_capture_interruption
        with tempfile.TemporaryDirectory() as tmp:
            backend=NtrCapture(FrameStore(),'10.0.0.106',logs=Path(tmp))
            # Startup control failures and a never-connected feed are not outages.
            backend._check_video_health(now=10)
            self.assertEqual(read_reports(tmp),[])
            backend.assembler.last_completion=10;backend._video_arrived()
            backend._check_video_health(now=11)
            self.assertEqual(read_reports(tmp),[])
            backend._check_video_health(now=13)
            backend._check_video_health(now=14)
            for _ in range(3):backend._control_failure(TimeoutError('timed out'))
            reports=read_reports(tmp)
            self.assertEqual(len(reports),1)
            self.assertTrue(is_capture_interruption(reports[0]))
            self.assertEqual(reports[0]['incident_kind'],'video_loss')
            # A new report requires video to have returned, then been lost again.
            backend.assembler.last_completion=20;backend._video_arrived()
            backend._check_video_health(now=23)
            self.assertEqual(len(read_reports(tmp)),2)

    def test_intentional_shutdown_is_not_reported(self):
        from viewer_reports import read_reports
        with tempfile.TemporaryDirectory() as tmp:
            backend=NtrCapture(FrameStore(),'10.0.0.106',logs=Path(tmp))
            backend._video_arrived();backend.stop.set()
            backend._check_video_health(now=10)
            self.assertEqual(read_reports(tmp),[])

    def test_legacy_tcp_reports_are_retained_but_not_counted(self):
        from viewer_reports import is_capture_interruption
        legacy={'capture_source':'NTR wireless','reason':'timed out'}
        self.assertFalse(is_capture_interruption(legacy))
        self.assertTrue(is_capture_interruption({**legacy,'incident_kind':'video_loss'}))
        self.assertTrue(is_capture_interruption({'capture_source':'Loopy USB','reason':'exit 7'}))

    def test_capture_messages_use_separate_ui_event(self):
        from app import App
        from queue import Queue
        app=object.__new__(App);app.events=Queue()
        app.emit_capture('Connected');app.emit('Encounter timing started')
        self.assertEqual(app.events.get(),('capture_log','Connected'))
        self.assertEqual(app.events.get(),('log','Encounter timing started'))
