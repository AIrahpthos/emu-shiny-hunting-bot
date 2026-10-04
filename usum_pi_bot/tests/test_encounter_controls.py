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


class EncounterMeasurementInputTests(unittest.TestCase):
    def test_dark_detection_stops_worker_before_transition_samples(self):
        from core import measure
        from unittest.mock import patch
        cancel=threading.Event(); started=threading.Event()
        class Control:
            released=False
            def hold(self, *args, **kwargs):
                started.set()
                cancel.wait(1)
            def release(self): self.released=True
        control=Control()
        worker=threading.Thread(target=trigger_encounter,args=(control,1,cancel))
        worker.start()
        self.assertTrue(started.wait(1))
        values=iter([(0,0,0)]*3+[(100,100,100)]*3+[(200,200,200)]*3)
        samples=[]
        def sample():
            value=next(values)
            if samples and len(samples)>=3:
                self.assertFalse(worker.is_alive())
                self.assertTrue(control.released)
            samples.append(value)
            return value
        def on_dark():
            cancel.set(); worker.join(1)
            self.assertFalse(worker.is_alive())
        try:
            with patch('core.time.monotonic',side_effect=iter(range(100))):
                # Normal monotonic timing is sufficient; skip the sampling sleeps.
                class Stop:
                    def is_set(self): return False
                    def wait(self, seconds): return False
                measure(sample,Stop(),on_dark=on_dark)
            self.assertEqual(len(samples),9)
        finally:
            cancel.set(); worker.join(1)

    def test_no_dark_does_not_call_input_stop_callback(self):
        from core import measure, EncounterStartTimeout
        from unittest.mock import patch, Mock
        callback=Mock()
        with patch('core.wait_sample',side_effect=TimeoutError('missing dark')):
            with self.assertRaises(EncounterStartTimeout):
                measure(lambda:None,threading.Event(),on_dark=callback)
        callback.assert_not_called()
