import queue, threading, tempfile, unittest
from pathlib import Path
from unittest.mock import Mock, patch
from PIL import Image
from app import App
from navigation import ColourDetector, LoadResult
from core import EncounterStartTimeout

class USBColourTests(unittest.TestCase):
    def bot(self):
        bot=App.__new__(App)
        bot.stop=threading.Event(); bot.confirm=threading.Event(); bot.confirm.set()
        bot.events=queue.Queue(); bot.emit=Mock()
        return bot

    def test_usb_runs_real_colour_sequence_without_a_reference_file(self):
        bot=self.bot()
        red=Image.new('RGB',(32,24),(170,35,25))
        blue=Image.new('RGB',(32,24),(60,150,220))
        black=Image.new('RGB',(32,24),'black')
        cap=Mock(); cap.grab.side_effect=[red]+[blue]*3+[black]*3+[red]*4
        with tempfile.TemporaryDirectory() as folder, patch('app.OUT',Path(folder)), \
             patch('app.Controller'), patch('app.Capture',return_value=cap), patch('app.measure',return_value=1):
            bot.run('hunt','10.0.0.106',1,ColourDetector(),{'capture_source':'Loopy USB','colour_hz':60,'load_limit':16,'forward':0,'threshold':1.1},False,(.5,.5))
        self.assertIn(('baseline',1),list(bot.events.queue))
        self.assertTrue(any('blue → black → red confirmed' in call.args[0] for call in bot.emit.call_args_list))
        self.assertFalse(any(kind=='alert' for kind,_ in list(bot.events.queue)))

    def test_usb_uses_timer_and_stops_after_three_failed_checks(self):
        bot=self.bot()
        with patch('app.Controller'), patch('app.Capture'), patch('app.ResetStats',return_value=Mock(observed_count=0)), \
             patch('app.load_save',return_value=LoadResult(16,160,100,False)) as load, \
             patch('app.measure',side_effect=EncounterStartTimeout('missing battle')):
            bot.run('hunt','10.0.0.106',1,ColourDetector(),{'capture_source':'Loopy USB','colour_hz':30,'load_limit':16,'forward':0,'threshold':1.1,'adaptive_reset':True},True,(.5,.5))
        self.assertEqual(load.call_count,3)
        self.assertEqual(load.call_args.kwargs,{'timeout':16,'hz':30})
        self.assertTrue(any(kind=='alert' and 'three attempts' in message for kind,message in list(bot.events.queue)))
