import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from PIL import Image, ImageDraw, ImageFilter
from navigation import ColourDetector, load_save
from ntr_support import choose_viewer, position_ntr
from core import Stopped
from recovery import wait_for_capture


class Stop:
    def is_set(self): return False
    def wait(self,_): return False


class NTRTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.ocean=Image.new('RGB',(320,240),(80,180,220))
        self.red=Image.new('RGB',(320,240),(170,35,25))
        draw=ImageDraw.Draw(self.red)
        for y in range(0,240,4):
            draw.line((0,y,319,y),fill=(210,40,30),width=2)
        self.black=Image.new('RGB',(320,240),'black')
        self.refs=ColourDetector()

    def test_compression_resize_and_blur_preserve_broad_match(self):
        self.assertTrue(self.refs.matches(self.red.resize((40,30)).resize((320,240)).filter(ImageFilter.GaussianBlur(3))))
        self.assertTrue(self.refs.matches(Image.new('RGB',(640,480),(170,40,35))))
        self.assertFalse(self.refs.matches(self.ocean))
        self.assertFalse(self.refs.matches(self.black))

    def test_no_references_are_needed(self):
        with tempfile.TemporaryDirectory() as folder:
            refs=ColourDetector()
            self.assertTrue(refs.matches(self.red))

    def test_darkness_cannot_be_mistaken_for_loaded_neutral_screen(self):
        self.assertTrue(self.refs.dark(self.black))
        self.assertFalse(self.refs.matches(self.black))
        self.assertFalse(self.refs.matches(Image.new('RGB',(320,240),(20,25,30))))

    def test_animated_blue_background_is_spatially_independent(self):
        for x in (30,120,220):
            frame=self.ocean.copy()
            ImageDraw.Draw(frame).ellipse((x,30,x+70,160),fill=(180,220,235))
            self.assertTrue(self.refs.ocean_matches(frame))
        self.assertFalse(self.refs.ocean_matches(self.red))

    def test_nonred_game_screen_does_not_complete_loading(self):
        self.assertFalse(self.refs.matches(Image.new('RGB',(320,240),(40,210,60))))
        self.assertFalse(self.refs.matches(Image.new('RGB',(320,240),(100,105,110))))

    def test_small_red_region_and_grey_noise(self):
        frame=Image.new('RGB',(320,240),(100,100,100))
        ImageDraw.Draw(frame).rectangle((140,100,153,113),fill=(220,30,20))
        self.assertTrue(self.refs.matches(frame))
        self.assertFalse(self.refs.matches(Image.new('RGB',(320,240),(115,100,100))))

    def test_requires_ocean_then_black_before_loaded_match(self):
        frames=iter([self.red]*3+[self.black]*3+[self.ocean]*3+[self.black]*3+[self.red]*3)
        controller=Mock()
        result=load_save(controller,lambda:next(frames),self.refs,Stop(),Mock())
        self.assertTrue(result.gradient_seen)
        # No A presses during any of the three possible loaded-screen matches.

    def test_transient_loaded_colour_does_not_complete(self):
        frames=iter([self.ocean]*3+[self.black]*3+[self.red,self.ocean]+[self.red]*3)
        result=load_save(Mock(),lambda:next(frames),self.refs,Stop(),Mock())
        self.assertTrue(result.gradient_seen)

    def test_loading_limit_tries_encounter_without_claiming_observation(self):
        tick=iter(i*.1 for i in range(100))
        with patch('navigation.time.monotonic',side_effect=lambda:next(tick)):
            result=load_save(Mock(),lambda:self.red,self.refs,Stop(),Mock(),timeout=1,learned_limits=(0,0))
        self.assertFalse(result.gradient_seen)
        self.assertGreaterEqual(result.seconds,1)

    def test_stop_prevents_input(self):
        controller=Mock(); stop=Mock(); stop.is_set.return_value=True
        with self.assertRaises(Stopped):
            load_save(controller,Mock(),self.refs,stop,Mock())
        controller.hold.assert_not_called()

    def test_viewer_sources_and_duplicate_ntr_windows(self):
        windows=[(1,'cc3dsfs_bot - USB'),(2,'NTRViewer-HR (FPS 020/040) [JPEG UDP]')]
        self.assertEqual(choose_viewer(windows),1)
        self.assertEqual(choose_viewer(windows,'NTR wireless'),2)
        with self.assertRaisesRegex(ValueError,'Bottom Only'):
            choose_viewer(windows+[(3,'NTRViewer-HR (FPS 010/020)')],'NTR wireless')

    def test_recovery_looks_for_selected_source(self):
        desktop=Mock(); desktop.windows.return_value=[(1,'cc3dsfs_bot'),(2,'NTRViewer-HR')]
        cap=Mock(hwnd=2)
        factory=Mock(return_value=cap)
        result=wait_for_capture((.5,.5),Stop(),Mock(),desktop_factory=Mock(return_value=desktop),capture_factory=factory,source='NTR wireless')
        self.assertIs(result,cap)
        factory.assert_called_once_with(2,(.5,.5))

    def test_layout_removes_maximization_and_sets_geometry(self):
        with patch('ntr_support.subprocess.run') as run:
            position_ntr()
        self.assertEqual(run.call_args_list[-1].args[0][-1],'0,850,30,320,240')

class ViewerPlanTests(unittest.TestCase):
    def test_ntr_keeps_only_loopy_bottom_and_separate_primary_log(self):
        import viewer_supervisor as supervisor
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'capture_executable.txt').write_text('/viewer/cc3dsfs')
            with patch.object(supervisor,'ROOT',root), patch.object(supervisor,'ntr_executable',return_value=Path('/viewer/ntrviewer')):
                specs=supervisor.viewer_specs({'capture_source':'NTR wireless'})
        self.assertEqual(len(specs),2)
        self.assertEqual(specs[0],(Path('/viewer/ntrviewer'),['/viewer/ntrviewer'],True))
        command=specs[1][1]
        self.assertEqual(command[command.index('--enabled_top')+1],'0')
        self.assertEqual(command[command.index('--enabled_low')+1],'1')
        self.assertFalse(specs[1][2])

    def test_wireless_can_run_without_usb_and_usb_keeps_original_layout(self):
        import viewer_supervisor as supervisor
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'capture_executable.txt').write_text('/viewer/cc3dsfs')
            with patch.object(supervisor,'ROOT',root), patch.object(supervisor,'ntr_executable',return_value=Path('/viewer/ntrviewer')):
                self.assertEqual(len(supervisor.viewer_specs({'capture_source':'NTR wireless','show_loopy_bottom':False})),1)
                specs=supervisor.viewer_specs({'capture_source':'Loopy USB'})
        self.assertEqual(len(specs),1)
        command=specs[0][1]
        self.assertEqual(command[command.index('--enabled_top')+1],'1')
        self.assertEqual(command[command.index('--enabled_low')+1],'1')

class SamplingRateTests(unittest.TestCase):
    def test_capture_periods_at_10_30_and_60_hz(self):
        for hz in (10,30,60):
            with self.subTest(hz=hz):
                now=[0.]
                frames=iter([Image.new('RGB',(32,24),(60,150,220))]*3+
                            [Image.new('RGB',(32,24),'black')]*3+
                            [Image.new('RGB',(32,24),(170,40,35))]*3)
                samples=[]
                class ClockStop:
                    def is_set(self): return False
                    def wait(self,seconds): now[0]+=seconds; return False
                def grab():
                    samples.append(now[0]); now[0]+=.002
                    return next(frames)
                worker=Mock(error=None,presses=5)
                with patch('navigation.time.monotonic',side_effect=lambda:now[0]), patch('navigation._StartupTapper',return_value=worker):
                    result=load_save(Mock(),grab,ColourDetector(),ClockStop(),Mock(),hz=hz)
                self.assertTrue(result.gradient_seen)
                self.assertEqual(len(samples),9)
                for first,second in zip(samples,samples[1:]): self.assertAlmostEqual(second-first,1/hz,places=6)
                worker.close.assert_called_once()

    def test_default_16_second_fallback_and_worker_cleanup(self):
        now=[0.]
        class ClockStop:
            def is_set(self): return False
            def wait(self,seconds): now[0]+=seconds; return False
        worker=Mock(error=None,presses=160)
        with patch('navigation.time.monotonic',side_effect=lambda:now[0]), patch('navigation._StartupTapper',return_value=worker):
            result=load_save(Mock(),lambda:Image.new('RGB',(32,24),(170,40,35)),ColourDetector(),ClockStop(),Mock())
        self.assertFalse(result.gradient_seen)
        self.assertGreaterEqual(result.seconds,16)
        self.assertLess(result.seconds,16.04)
        worker.close.assert_called_once()

    def test_capture_loss_is_not_a_timer_fallback(self):
        from capture_linux import ViewerUnavailable
        worker=Mock(error=None,presses=1)
        with patch('navigation._StartupTapper',return_value=worker):
            with self.assertRaises(ViewerUnavailable):
                load_save(Mock(),Mock(side_effect=ViewerUnavailable('closed')),ColourDetector(),Stop(),Mock())
        worker.close.assert_called_once()

    def test_actual_tapper_cancels_inflight_hold_and_releases(self):
        import threading, time
        from navigation import _StartupTapper
        entered=threading.Event()
        controller=Mock()
        def hold(buttons,seconds,cancel):
            entered.set()
            while not cancel.is_set(): time.sleep(.001)
        controller.hold.side_effect=hold
        tapper=_StartupTapper(controller,threading.Event())
        tapper.start()
        self.assertTrue(entered.wait(1))
        tapper.close()
        self.assertFalse(tapper.thread.is_alive())
        controller.release.assert_called_once()

    def test_screen_checks_continue_while_input_hold_is_blocked(self):
        import threading
        from navigation import load_save
        entered=threading.Event(); finished=threading.Event()
        controller=Mock()
        def hold(buttons,seconds,cancel):
            entered.set()
            # Simulate an input call lasting much longer than a sample period.
            finished.wait(.2)
        controller.hold.side_effect=hold
        frames=iter([Image.new('RGB',(32,24),(60,150,220))]*3+
                    [Image.new('RGB',(32,24),'black')]*3+
                    [Image.new('RGB',(32,24),(170,40,35))]*3)
        checks_during_hold=[]
        def grab():
            self.assertTrue(entered.wait(1))
            checks_during_hold.append(not finished.is_set())
            image=next(frames)
            if len(checks_during_hold)==9: finished.set()
            return image
        result=load_save(controller,grab,ColourDetector(),threading.Event(),Mock(),hz=30)
        self.assertTrue(result.gradient_seen)
        self.assertEqual(len(checks_during_hold),9)
        self.assertTrue(all(checks_during_hold))

    def test_rates_and_timer_are_validated_before_input(self):
        controller=Mock()
        for options in ({'hz':0},{'hz':120},{'timeout':0},{'timeout':46}):
            with self.assertRaises(ValueError):
                load_save(controller,Mock(),ColourDetector(),Stop(),Mock(),**options)
        controller.hold.assert_not_called()
