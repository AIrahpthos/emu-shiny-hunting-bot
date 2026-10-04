import queue
import threading
import unittest
from unittest.mock import Mock, patch
from app import App
from core import EncounterStartTimeout
from navigation import LoadResult

class NTRHuntTests(unittest.TestCase):
    def bot(self):
        bot=App.__new__(App)
        bot.stop=threading.Event(); bot.confirm=threading.Event(); bot.confirm.set()
        bot.events=queue.Queue(); bot.emit=Mock()
        return bot

    def test_fallback_then_three_failed_encounter_checks_stop(self):
        bot=self.bot(); stats=Mock(samples=[],observed_count=0)
        with patch('app.ResetStats',return_value=stats), patch('app.Controller') as controller, patch('app.Capture'), \
             patch('app.load_save',return_value=LoadResult(16,160,100,False)) as load, \
             patch('app.measure',side_effect=EncounterStartTimeout('missing battle')):
            bot.run('hunt','10.0.0.106',1,None,{'capture_source':'NTR wireless','ntr_hz':60,'ntr_load_limit':16,'forward':0,'threshold':1.1,'adaptive_reset':True},True,(.5,.5))
        self.assertEqual(load.call_count,3)
        self.assertEqual(stats.record_failure.call_count,3)
        self.assertFalse(any('Observed load' in call.args[0] for call in bot.emit.call_args_list))
        self.assertTrue(bot.stop.is_set())
        self.assertTrue(any(kind=='alert' and 'three attempts' in text for kind,text in list(bot.events.queue)))
        self.assertEqual(load.call_args.kwargs,{'timeout':16,'hz':60})

    def test_fallback_still_stops_for_measured_suspected_shiny(self):
        bot=self.bot()
        with patch('app.ResetStats',return_value=Mock(samples=[],observed_count=0)), patch('app.Controller'), patch('app.Capture'), \
             patch('app.load_save',return_value=LoadResult(16,160,100,False)) as load, \
             patch('app.measure',side_effect=[1,2.2]):
            bot.run('hunt','10.0.0.106',1,None,{'capture_source':'NTR wireless','forward':0,'threshold':1.1,'adaptive_reset':True},True,(.5,.5))
        self.assertEqual(load.call_count,2)
        self.assertIn(('alert','suspected shiny'),list(bot.events.queue))
