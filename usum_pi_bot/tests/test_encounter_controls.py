import threading
import unittest
from core import Stopped, trigger_encounter


class EncounterControlsTests(unittest.TestCase):
    def test_taps_continue_after_forward_and_cancel_releases(self):
        cancel = threading.Event()
        class Control:
            def __init__(self): self.calls=[]; self.releases=0
            def hold(self, buttons=(), seconds=0, y=0, cancel=None):
                self.calls.append((buttons,seconds,y))
                if len(self.calls)==4: cancel.set()
            def release(self): self.releases+=1
        control=Control()
        trigger_encounter(control,1,cancel)
        self.assertEqual(control.calls,[(('A',),.15,0),((),1,1),(('A',),.10,0),(('A',),.10,0)])
        self.assertEqual(control.releases,1)

    def test_cancel_during_forward_does_not_send_another_a(self):
        cancel=threading.Event()
        class Control:
            def __init__(self): self.calls=[]; self.released=False
            def hold(self, buttons=(), seconds=0, y=0, cancel=None):
                self.calls.append(buttons)
                if y: cancel.set()
            def release(self): self.released=True
        control=Control(); trigger_encounter(control,1,cancel)
        self.assertEqual(control.calls,[('A',),()]); self.assertTrue(control.released)

    def test_stop_or_transport_error_releases_and_propagates(self):
        for error in (Stopped(),OSError('UDP failed')):
            class Control:
                released=False
                def hold(self,*args,**kwargs): raise error
                def release(self): self.released=True
            control=Control()
            with self.assertRaises(type(error)): trigger_encounter(control,1,threading.Event())
            self.assertTrue(control.released)

    def test_already_cancelled_sends_no_press(self):
        from unittest.mock import Mock
        control=Mock(); cancel=threading.Event(); cancel.set()
        trigger_encounter(control,1,cancel)
        control.hold.assert_not_called(); control.release.assert_called_once()
