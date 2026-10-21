import json
from pathlib import Path
import queue
import socket
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from PIL import Image
from core import Stopped
from encounter_probe import HEADER, MAGIC, COMMAND, GUARD, ADDRESS, decode_record
from memory_hunt import MemoryHunt, MemoryCheckError
from species_names import species_name
from test_encounter_probe import pokemon, encrypt


def reply(raw=None, status=0, pid=50, seq=0):
    args=[status,pid,0x1b5100,0x40000,ADDRESS,232,GUARD]+[0]*9
    raw=b'' if status else (raw if raw is not None else b'\0'*232)
    return HEADER.unpack(HEADER.pack(MAGIC,seq,0,COMMAND,*args,len(raw))),raw


class MemoryDecisionTests(unittest.TestCase):
    def test_old_snapshot_is_rejected_until_two_matching_new_normals(self):
        before=encrypt(pokemon(16,1));new=encrypt(pokemon(16,2))
        request=Mock(side_effect=[reply(before),reply(before),reply(new),reply(new)])
        with tempfile.TemporaryDirectory() as folder:
            hunt=MemoryHunt(request,threading.Event(),Path(folder)/'log.jsonl')
            hunt.prepare();result,_=hunt.observe(interval=0)
            self.assertEqual(result.encryption_constant,2);self.assertFalse(result.shiny)
            self.assertEqual(request.call_count,4)
            record=json.loads((Path(folder)/'log.jsonl').read_text())
            self.assertEqual(record['species'],717)
            self.assertEqual(record['species_name'],'Yveltal')

    def test_species_names_are_available_offline(self):
        self.assertEqual(species_name(639),'Terrakion')
        self.assertEqual(species_name(797),'Celesteela')
        self.assertEqual(species_name(0),'species #0')

    def test_shiny_stops_on_first_valid_fresh_read(self):
        request=Mock(side_effect=[reply(),reply(encrypt(pokemon(15)))])
        with tempfile.TemporaryDirectory() as folder:
            hunt=MemoryHunt(request,threading.Event(),Path(folder)/'log.jsonl')
            hunt.prepare();result,_=hunt.observe()
            self.assertTrue(result.shiny);self.assertEqual(request.call_count,2)

    def test_invalid_memory_expires_as_nonretryable_error(self):
        now=[0.]
        class Stop:
            def is_set(self):return False
            def wait(self,seconds):now[0]+=seconds;return False
        with tempfile.TemporaryDirectory() as folder,patch('memory_hunt.time.monotonic',side_effect=lambda:now[0]):
            hunt=MemoryHunt(Mock(return_value=reply()),Stop(),Path(folder)/'log.jsonl')
            hunt.prepare()
            with self.assertRaises(MemoryCheckError):hunt.observe(timeout=.3)
            self.assertFalse((Path(folder)/'log.jsonl').exists())

    def test_stop_prevents_memory_request(self):
        stop=threading.Event();stop.set();request=Mock()
        hunt=MemoryHunt(request,stop,Path('unused'))
        with self.assertRaises(Stopped):hunt.prepare()
        request.assert_not_called()


class SharedNtrConnectionTests(unittest.TestCase):
    def test_memory_commands_and_video_use_one_connection(self):
        from ntr_capture import NtrCapture,control_packet
        from frame_feed import FrameStore
        from test_direct_capture import jpeg_packets
        from encounter_probe import recv_exact
        server=socket.socket();server.bind(('127.0.0.1',0));server.listen()
        port=server.getsockname()[1]
        udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);udp.bind(('127.0.0.1',0))
        udp_port=udp.getsockname()[1];udp.close()
        stop=threading.Event();errors=[];commands=[]
        raw=encrypt(pokemon(16))
        def console():
            try:
                with server.accept()[0] as conn:
                    conn.settimeout(4)
                    while not stop.is_set():
                        head=HEADER.unpack(recv_exact(conn,84));commands.append(head[3])
                        if head[3]==0:conn.sendall(control_packet(head[1]))
                        elif head[3]==901:
                            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:
                                for packet in jpeg_packets():sender.sendto(packet,('127.0.0.1',udp_port))
                        elif head[3]==902:
                            status=0 if head[4]==GUARD else 0xe1000001
                            response,payload=reply(raw,status,seq=head[1])
                            data=HEADER.pack(*response)+payload
                            conn.sendall(data[:11]);conn.sendall(data[11:])
            except Exception as error:
                if not stop.is_set():errors.append(error)
        thread=threading.Thread(target=console,daemon=True);thread.start()
        real_connect=socket.create_connection
        backend=NtrCapture(FrameStore(),'127.0.0.1',port=udp_port)
        try:
            with patch('ntr_capture.socket.create_connection',side_effect=lambda address,timeout:real_connect(('127.0.0.1',port),timeout)) as connect:
                backend.start();backend.store.next(timeout=3)
                with tempfile.TemporaryDirectory() as folder:
                    hunt=MemoryHunt(backend.encounter_request,threading.Event(),Path(folder)/'log')
                    hunt.check_capability()
                    meta,data=hunt.read();self.assertEqual(meta['game'],'Ultra Moon')
                    self.assertEqual(decode_record(data).species,717)
                self.assertEqual(connect.call_count,1)
                self.assertEqual(commands.count(901),1)
                self.assertEqual(commands.count(902),2)
                stop.set();backend.close()
        finally:stop.set();backend.close();server.close();thread.join(5)
        self.assertFalse(errors,errors);self.assertFalse(thread.is_alive())


class AppMemoryTests(unittest.TestCase):
    def run_bot(self,observe,repeat=False,capability_error=None):
        from app import App
        bot=App.__new__(App);bot.stop=threading.Event();bot.confirm=threading.Event();bot.confirm.set()
        bot.events=queue.Queue();bot.emit=Mock();bot.capture_service=Mock()
        cap=Mock();cap.grab.return_value=Image.new('RGB',(320,240))
        memory=Mock();memory.observe.side_effect=observe
        if capability_error:memory.check_capability.side_effect=capability_error
        def dark(*args,**kwargs):kwargs['on_dark']();return (0,0,0)
        with tempfile.TemporaryDirectory() as folder,patch('app.OUT',Path(folder)),patch('app.Capture',return_value=cap),\
             patch('app.Controller') as controller,patch('app.load_save'),patch('app.ResetStats'),\
             patch('app.MemoryHunt',return_value=memory),patch('app.wait_battle_dark',side_effect=dark) as dark_gate,\
             patch('app.measure') as timing,patch('app.wait_for_capture') as recovery:
            bot.run('hunt','10.0.0.87',object(),Mock(),
                    {'memory_check':True,'capture_source':'NTR wireless','forward':0,'threshold':1.1,
                     'adaptive_reset':True,'auto_recover':True},repeat,(.5,.5))
        resets=[c for c in controller.return_value.hold.call_args_list if c.args[0]==('L','R','START')]
        timing.assert_not_called();recovery.assert_not_called()
        self.assertEqual(dark_gate.call_count,len(resets))
        return bot,len(resets),memory

    def test_shiny_stops_after_one_reset_even_with_repeat(self):
        bot,resets,_=self.run_bot([(decode_record(pokemon(15)),.1)],True)
        self.assertEqual(resets,1)
        self.assertIn(('alert','shiny confirmed by memory'),list(bot.events.queue))
        self.assertTrue(any('Yveltal (#717)' in call.args[0] for call in bot.emit.call_args_list))

    def test_unknown_memory_never_enters_adaptive_reset(self):
        bot,resets,_=self.run_bot(MemoryCheckError('Unknown'),True)
        self.assertEqual(resets,1);self.assertTrue(bot.stop.is_set())

    def test_missing_endpoint_prevents_first_reset(self):
        bot,resets,_=self.run_bot([],True,MemoryCheckError('Unsupported'))
        self.assertEqual(resets,0)

    def test_normal_single_test_does_not_take_another_reset(self):
        bot,resets,memory=self.run_bot([(decode_record(pokemon(16)),.1)])
        self.assertEqual(resets,1);memory.prepare.assert_called_once()
        self.assertIn(('memory_confirmation',None),list(bot.events.queue))

    def test_repeat_resets_normal_then_stops_at_shiny(self):
        bot,resets,memory=self.run_bot([(decode_record(pokemon(16,1)),.1),
                                       (decode_record(pokemon(15,2)),.1)],True)
        self.assertEqual(resets,2);self.assertEqual(memory.prepare.call_count,2)
        self.assertIn(('alert','shiny confirmed by memory'),list(bot.events.queue))
