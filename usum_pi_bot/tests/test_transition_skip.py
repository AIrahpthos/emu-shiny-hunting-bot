import unittest
from unittest.mock import patch
from core import measure, Stopped


class FastStop:
    def is_set(self): return False
    def wait(self,_): return False


class TransitionSkipTests(unittest.TestCase):
    def test_cutscene_transitions_are_consumed_before_timed_pair(self):
        # Three stable samples per screen. Last change is real battle completion.
        values=iter([(0,0,0)]*3+[(80,80,80)]*3+[(0,0,0)]*3+
                    [(100,100,100)]*3+[(200,200,200)]*3)
        seen=[]; messages=[]
        def sample():
            value=next(values); seen.append(value); return value
        with patch('core.time.monotonic',side_effect=iter(range(100))):
            duration=measure(sample,FastStop(),skip_changes=2,emit=messages.append)
        self.assertEqual(len(seen),15)
        self.assertEqual(len(messages),3)
        self.assertIn('1/2',messages[0]); self.assertIn('2/2',messages[1])
        self.assertGreater(duration,0)

    def test_zero_skips_preserves_normal_sequence(self):
        values=iter([(0,0,0)]*3+[(100,100,100)]*3+[(200,200,200)]*3)
        self.assertGreaterEqual(measure(lambda:next(values),FastStop(),0),0)

    def test_stop_during_skip_propagates(self):
        with patch('core.wait_sample',side_effect=[(0,0,0),Stopped()]):
            with self.assertRaises(Stopped): measure(lambda:None,FastStop(),2)

    def test_missing_skip_transition_times_out_without_result(self):
        with patch('core.wait_sample',side_effect=[(0,0,0),TimeoutError('missing')]):
            with self.assertRaises(TimeoutError): measure(lambda:None,FastStop(),1)

    def test_invalid_counts_rejected(self):
        for count in (-1,21,1.5,'2',True):
            with self.assertRaises(ValueError): measure(lambda:None,FastStop(),count)
