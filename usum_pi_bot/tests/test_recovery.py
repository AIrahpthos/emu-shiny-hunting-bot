import queue
import threading
import unittest
from unittest.mock import Mock, patch

from app import App
from capture_linux import ViewerUnavailable
from core import Controller, Stopped
from recovery import wait_for_capture


class RecoveryTests(unittest.TestCase):
    def bot(self):
        stats = Mock(samples=[])
        stats.limits.return_value = None
        patcher = patch('app.ResetStats', return_value=stats)
        patcher.start()
        self.addCleanup(patcher.stop)
        bot = App.__new__(App)
        bot.stop = threading.Event()
        bot.confirm = threading.Event()
        bot.confirm.set()
        bot.events = queue.Queue()
        bot.emit = Mock()
        return bot

    def events(self, bot):
        result = []
        while not bot.events.empty():
            result.append(bot.events.get_nowait())
        return result

    def test_reacquires_new_window_after_absence(self):
        stop = Mock()
        stop.is_set.return_value = False
        stop.wait.return_value = False
        desktop = Mock()
        desktop.windows.side_effect = [[], [(99, 'cc3dsfs_bot')]] * 1 + [[(99, 'cc3dsfs_bot')]] * 2
        cap = Mock(hwnd=99)
        factory = Mock(return_value=cap)
        self.assertIs(wait_for_capture((.5,.5), stop, Mock(),
                         desktop_factory=Mock(return_value=desktop), capture_factory=factory), cap)
        self.assertEqual(cap.grab.call_count, 3)
        self.assertEqual(desktop.close.call_count, 4)

    def test_stop_during_recovery_closes_candidate(self):
        stop = Mock()
        stop.is_set.return_value = False
        stop.wait.return_value = True
        desktop = Mock()
        desktop.windows.return_value = [(99, 'cc3dsfs_bot')]
        cap = Mock(hwnd=99)
        with self.assertRaises(Stopped):
            wait_for_capture((.5,.5), stop, Mock(), desktop_factory=Mock(return_value=desktop),
                             capture_factory=Mock(return_value=cap))
        cap.close.assert_called_once()

    def test_recovery_preserves_baseline_and_suspected_result(self):
        bot = self.bot()
        original, restored, controller = Mock(), Mock(), Mock()
        with patch('app.Controller',return_value=controller), patch('app.Capture',return_value=original), \
             patch('app.load_save'), patch('app.measure',side_effect=[1, ViewerUnavailable('crashed'), 1, 2.2]), \
             patch('app.wait_for_capture',return_value=restored) as recover:
            bot.run('hunt','192.168.0.5',1,None,{'forward':0,'threshold':1.1,'auto_recover':True},True,(.5,.5))
        recover.assert_called_once()
        events = self.events(bot)
        self.assertEqual(sum(kind=='baseline' for kind,value in events),1)
        self.assertIn(('alert','suspected shiny'),events)
        self.assertEqual(sum(call.args and call.args[0]==('L','R','START') for call in controller.hold.call_args_list),4)
        original.close.assert_called_once()
        restored.close.assert_called_once()

    def test_disabled_recovery_stops(self):
        bot = self.bot()
        with patch('app.Controller'), patch('app.Capture') as cap, patch('app.load_save'), \
             patch('app.measure',side_effect=ViewerUnavailable('crashed')), patch('app.wait_for_capture') as recover:
            bot.run('hunt','192.168.0.5',1,None,{'forward':0,'threshold':1.1,'auto_recover':False},True,(.5,.5))
        recover.assert_not_called()
        self.assertTrue(bot.stop.is_set())

    def test_screenshot_loss_never_resets_suspected_shiny(self):
        bot = self.bot()
        cap = Mock()
        cap.grab.side_effect = [Mock(), Mock(), Mock(), ViewerUnavailable('lost after measured shiny')]
        with patch('app.Controller'), patch('app.Capture',return_value=cap), patch('app.load_save'), \
             patch('app.measure',side_effect=[1,2.2]), patch('app.wait_for_capture') as recover:
            bot.run('hunt','192.168.0.5',1,None,{'forward':0,'threshold':1.1,'auto_recover':True},True,(.5,.5))
        recover.assert_not_called()
        self.assertIn(('alert','suspected shiny'),self.events(bot))

    def test_window_obstruction_is_not_treated_as_crash(self):
        bot = self.bot()
        with patch('app.Controller'), patch('app.Capture') as cap, patch('app.wait_for_capture') as recover:
            cap.return_value.grab.side_effect=RuntimeError('Another window covers viewer')
            bot.run('hunt','192.168.0.5',1,None,{'forward':0,'threshold':1.1,'auto_recover':True},True,(.5,.5))
        recover.assert_not_called()

    def test_cancelled_hold_sends_only_release(self):
        controller = Controller.__new__(Controller)
        controller.stop = threading.Event()
        controller.sock = Mock()
        controller.address = ('192.168.0.5',4950)
        cancel = threading.Event(); cancel.set()
        controller.hold(('UP',),seconds=1,cancel=cancel)
        self.assertEqual(controller.sock.sendto.call_count,3)


if __name__=='__main__':
    unittest.main()
