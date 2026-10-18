import queue
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image
from app import App
from capture_linux import ViewerUnavailable
from core import Stopped
from navigation import ColourDetector, load_save


class ClockStop:
    def __init__(self):
        self.now = 0
        self.stopped = False

    def is_set(self):
        return self.stopped

    def wait(self, seconds):
        self.now += seconds
        return self.stopped


class StartupCaptureGapTests(unittest.TestCase):
    def tapper(self):
        return Mock(paused=threading.Event(), error=None, presses=10)

    def test_gap_preserves_loading_phase_and_pauses_buttons(self):
        stop = ClockStop()
        tapper = self.tapper()
        blue = Image.new('RGB', (320, 240), (40, 100, 220))
        black = Image.new('RGB', (320, 240), 'black')
        red = Image.new('RGB', (320, 240), (200, 20, 20))
        # Already saw ocean and black. After the gap there is only red;
        # restarting the detector would miss the completed boot sequence.
        frames = iter([blue]*3 + [black]*3 + [None, red, red, red])
        def grab():
            frame = next(frames)
            if frame is None:
                stop.now += 5
                raise ViewerUnavailable('reset interruption')
            if frame is red:
                self.assertTrue(tapper.paused.is_set())
            return frame
        emit = Mock()
        controller = Mock()
        with patch('navigation.time.monotonic', side_effect=lambda: stop.now), \
             patch('navigation._StartupTapper', return_value=tapper):
            result = load_save(controller, grab, ColourDetector(), stop, emit,
                               timeout=1, capture_grace=30)
        self.assertTrue(result.gradient_seen)
        self.assertGreater(result.seconds, 5)
        controller.release.assert_called_once()
        tapper.start.assert_called_once()
        tapper.close.assert_called_once()

    def test_missing_feed_exhausts_grace_and_stops_tapper(self):
        stop = ClockStop()
        tapper = self.tapper()
        def grab():
            stop.now += 2
            raise ViewerUnavailable('offline')
        with patch('navigation.time.monotonic', side_effect=lambda: stop.now), \
             patch('navigation._StartupTapper', return_value=tapper):
            with self.assertRaises(ViewerUnavailable):
                load_save(Mock(), grab, ColourDetector(), stop, Mock(), capture_grace=5)
        self.assertLess(stop.now, 8)
        self.assertTrue(tapper.paused.is_set())
        tapper.close.assert_called_once()

    def test_stop_during_gap_releases_tapper(self):
        stop = ClockStop()
        tapper = self.tapper()
        def grab():
            stop.stopped = True
            raise ViewerUnavailable('offline')
        with patch('navigation._StartupTapper', return_value=tapper):
            with self.assertRaises(Stopped):
                load_save(Mock(), grab, ColourDetector(), stop, Mock(), capture_grace=30)
        tapper.close.assert_called_once()

    def test_hunt_recovers_reset_gap_without_sending_a_second_reset(self):
        bot = App.__new__(App)
        bot.stop = threading.Event()
        bot.confirm = threading.Event(); bot.confirm.set()
        bot.events = queue.Queue(); bot.emit = Mock()
        blue = Image.new('RGB', (320, 240), (40, 100, 220))
        black = Image.new('RGB', (320, 240), 'black')
        red = Image.new('RGB', (320, 240), (200, 20, 20))
        cap = Mock()
        cap.grab.side_effect = [red] + [blue]*3 + [black]*3 + [ViewerUnavailable('reset gap')] + [red]*4
        with tempfile.TemporaryDirectory() as folder, patch('app.OUT', Path(folder)), \
             patch('app.Controller') as controller, patch('app.Capture', return_value=cap), \
             patch('navigation._StartupTapper', return_value=self.tapper()), \
             patch('app.measure', return_value=1), patch('app.wait_for_capture') as recover:
            bot.run('hunt', '10.0.0.105', object(), ColourDetector(),
                    {'capture_source':'NTR wireless', 'forward':0, 'threshold':1.1, 'auto_recover':True},
                    False, (.5, .5))
        resets = [c for c in controller.return_value.hold.call_args_list if c.args[0] == ('L','R','START')]
        self.assertEqual(len(resets), 1)
        recover.assert_not_called()
        self.assertIn(('baseline', 1), list(bot.events.queue))

    def test_repeated_capture_failures_stop_after_three_attempts(self):
        bot = App.__new__(App)
        bot.stop = threading.Event(); bot.confirm = threading.Event()
        bot.events = queue.Queue(); bot.emit = Mock()
        cap = Mock()
        with patch('app.Controller') as controller, patch('app.Capture', return_value=cap), \
             patch('app.ResetStats') as stats, patch('app.load_save', side_effect=ViewerUnavailable('offline')), \
             patch('app.wait_for_capture', return_value=cap) as recover:
            bot.run('hunt', '10.0.0.105', object(), ColourDetector(),
                    {'capture_source':'NTR wireless', 'forward':0, 'threshold':1.1, 'auto_recover':True},
                    True, (.5,.5))
        self.assertEqual(recover.call_count, 2)
        self.assertEqual(stats.return_value.record_failure.call_count, 3)
        self.assertTrue(any(kind == 'alert' and 'three attempts' in message for kind,message in bot.events.queue))
