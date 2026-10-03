import json
import tempfile
import unittest
from pathlib import Path
from navigation import LoadResult
from reset_stats import ResetStats


class ResetCounterTests(unittest.TestCase):
    def test_counter_keeps_growing_and_survives_reload_with_bounded_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'resets.jsonl'
            stats=ResetStats(path,'A')
            for number in range(137):
                stats.record(LoadResult(5,20,0,True))
            self.assertEqual(stats.observed_count,137)
            self.assertEqual(len(stats.samples),100)
            self.assertEqual(stats.limits(),(6,25))
            reloaded=ResetStats(path,'A')
            self.assertEqual(reloaded.observed_count,137)
            self.assertEqual(len(reloaded.samples),100)
            reloaded.record(LoadResult(5,20,0,True))
            self.assertEqual(reloaded.observed_count,138)
            self.assertEqual(ResetStats(path,'B').observed_count,0)

    def test_inferred_failed_invalid_and_other_profiles_do_not_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'resets.jsonl'
            stats=ResetStats(path,'A')
            stats.record(LoadResult(5,20,0,False))
            stats.record_failure(1,'startup','timeout',1)
            ResetStats(path,'B').record(LoadResult(5,20,0,True))
            with path.open('a') as file:
                file.write(json.dumps({'key':'A','gradient_seen':True,'seconds':-1,'a_taps':20})+'\n')
                file.write('invalid JSON\n')
            self.assertEqual(ResetStats(path,'A').observed_count,0)
