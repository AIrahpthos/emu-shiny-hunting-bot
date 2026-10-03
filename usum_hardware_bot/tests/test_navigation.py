import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw
from core import Stopped
from navigation import References, load_save

class FastStop:
    def is_set(self): return False
    def wait(self,_): return False

class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.folder=Path(self.temp.name)
        self.gradient=Image.new('RGB',(320,240),(220,60,20))
        ImageDraw.Draw(self.gradient).rectangle((80,60,120,100),fill='black')
        self.blank=Image.new('RGB',(320,240),'black')
        self.gradient.save(self.folder/'gradient.png')
        self.refs=References(self.folder,{'gradient':[.1,.1,.5,.5]})
    def tearDown(self): self.temp.cleanup()
    def test_match_with_resize_and_small_noise(self):
        image=self.gradient.copy(); ImageDraw.Draw(image).rectangle((40,40,42,42),fill='white')
        self.assertTrue(self.refs.matches(image)); self.assertTrue(self.refs.matches(image.resize((640,480))))
        self.assertFalse(self.refs.matches(self.blank))
    def test_whole_screen_comparison(self):
        image=self.gradient.copy(); ImageDraw.Draw(image).rectangle((0,120,319,239),fill='white')
        self.assertFalse(self.refs.matches(image))
    def test_subtle_gradient_needs_no_manual_region(self):
        image=Image.new('RGB',(320,240),(80,80,80))
        ImageDraw.Draw(image).rectangle((0,120,319,239),fill=(82,82,82))
        image.save(self.folder/'gradient.png')
        refs=References(self.folder)
        self.assertTrue(refs.matches(image))
    def execute(self,frames):
        presses=[]; values=iter(frames)
        class Controller:
            def hold(self,buttons,seconds): presses.append(buttons)
        load_save(Controller(),lambda:next(values),self.refs,FastStop(),lambda _:None)
        return presses
    def test_taps_until_gradient_then_no_extra_a(self):
        presses=self.execute([self.blank]*5+[self.gradient]*3)
        self.assertEqual(presses,[('A',),('A',)])
    def test_waits_for_old_gradient_to_disappear_after_reset(self):
        self.assertEqual(self.execute([self.gradient]*3+[self.blank]*3+[self.gradient]*3),[])
    def test_transient_match_suspends_tapping_but_does_not_finish(self):
        self.assertEqual(self.execute([self.blank]*3+[self.gradient,self.blank]+[self.gradient]*3),[('A',)])
    def test_stop_and_timeout(self):
        stop=threading.Event(); stop.set()
        class Controller:
            def hold(self,*args): pass
        with self.assertRaises(Stopped):
            load_save(Controller(),lambda:self.blank,self.refs,stop,lambda _:None)
        ticks=iter(i*.1 for i in range(100))
        with patch('navigation.time.monotonic',side_effect=lambda:next(ticks)):
            with self.assertRaisesRegex(TimeoutError,'loaded-save gradient not seen'):
                load_save(Controller(),lambda:self.blank,self.refs,FastStop(),lambda _:None,timeout=1)

if __name__=='__main__': unittest.main()
