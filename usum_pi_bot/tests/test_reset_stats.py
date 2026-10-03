import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from navigation import LoadResult, load_save
from reset_stats import ResetStats
from core import EncounterStartTimeout
import test_recovery as support


class StatsTests(unittest.TestCase):
    def test_minimum_samples_and_conservative_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            stats=ResetStats(Path(tmp)/'resets.jsonl','profile')
            for i in range(9): stats.record(LoadResult(10,60,3,True))
            self.assertIsNone(stats.limits())
            stats.record(LoadResult(12,75,3,True))
            seconds,taps=stats.limits()
            self.assertGreaterEqual(seconds,13)
            self.assertGreaterEqual(taps,80)

    def test_inferred_results_do_not_train_and_keys_are_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'resets.jsonl'
            stats=ResetStats(path,'A')
            stats.record(LoadResult(10,60,3,True))
            stats.record(LoadResult(30,200,40,False))
            self.assertEqual(len(stats.samples),1)
            self.assertEqual(len(ResetStats(path,'A').samples),1)
            self.assertEqual(len(ResetStats(path,'B').samples),0)
            self.assertEqual(len(path.read_text().splitlines()),2)

    def test_malformed_record_does_not_discard_good_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'resets.jsonl'
            path.write_text('broken\n'+json.dumps({'key':'A','gradient_seen':True,'seconds':5,'a_taps':20})+'\n')
            self.assertEqual(ResetStats(path,'A').samples,[(5,20)])

    def test_fallback_requires_both_time_and_tap_limits(self):
        class Stop:
            def is_set(self): return False
            def wait(self,_): return False
        class Refs:
            tolerance=12
            def matches(self,_): return False
            def score(self,_): return 30
        from unittest.mock import Mock
        controller=Mock()
        ticks=iter(i*.1 for i in range(500))
        with patch('navigation.time.monotonic',side_effect=lambda:next(ticks)):
            result=load_save(controller,lambda:None,Refs(),Stop(),lambda _:None,
                             learned_limits=(1,10))
        self.assertFalse(result.gradient_seen)
        self.assertGreaterEqual(result.seconds,1)
        self.assertEqual(result.a_taps,10)

    def test_invalid_observations_cannot_train(self):
        with tempfile.TemporaryDirectory() as tmp:
            stats=ResetStats(Path(tmp)/'resets.jsonl','A')
            with self.assertRaises(ValueError): stats.record(LoadResult(float('nan'),2,0,True))
            self.assertEqual(stats.samples,[])


class StartupRetryTests(unittest.TestCase):
    bot = support.RecoveryTests.bot
    events = support.RecoveryTests.events
    def test_three_missing_starts_stop_with_suspected_failure(self):
        bot=self.bot()
        with patch('app.Controller') as controller, patch('app.Capture'), patch('app.load_save'), \
             patch('app.measure',side_effect=EncounterStartTimeout('no dark transition')):
            bot.run('hunt','192.168.0.5',1,None,
                    {'forward':0,'threshold':1.1,'adaptive_reset':True},True,(.5,.5))
        events=self.events(bot)
        self.assertTrue(any(kind=='alert' and 'three attempts' in value for kind,value in events))
        self.assertFalse(any(kind=='baseline' for kind,value in events))
        self.assertEqual(sum(call.args and call.args[0]==('L','R','START') for call in controller.return_value.hold.call_args_list),3)

    def test_later_animation_timeout_retries_three_times(self):
        bot=self.bot()
        with patch('app.Controller') as controller, patch('app.Capture'), patch('app.load_save'), \
             patch('app.measure',side_effect=TimeoutError('introduction incomplete')):
            bot.run('hunt','192.168.0.5',1,None,
                    {'forward':0,'threshold':1.1,'adaptive_reset':True},True,(.5,.5))
        self.assertEqual(sum(call.args and call.args[0]==('L','R','START') for call in controller.return_value.hold.call_args_list),3)

    def test_normal_result_clears_failure_streak(self):
        bot=self.bot()
        missing=EncounterStartTimeout('missing dark screen')
        with patch('app.Controller') as controller, patch('app.Capture'), patch('app.load_save'), \
             patch('app.measure',side_effect=[missing,1,missing,missing,1,missing,missing,missing]):
            bot.run('hunt','192.168.0.5',1,None,
                    {'forward':0,'threshold':1.1,'adaptive_reset':True},True,(.5,.5))
        self.assertEqual(sum(call.args and call.args[0]==('L','R','START') for call in controller.return_value.hold.call_args_list),8)
        self.assertEqual(sum(kind=='baseline' for kind,value in self.events(bot)),1)
