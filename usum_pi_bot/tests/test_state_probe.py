import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock

from encounter_probe import HEADER,MAGIC
from state_probe import GUARD,SCHEMA,COMMAND,REPLY,read_state,parse_state_reply
from state_logging import StateRecorder


def response(status=0, payload=None):
    if payload is None:payload=REPLY.pack(0,0x304b742c,0,0x80008,0,0)
    if status:payload=b''
    args=(status,50,0x1b5100,0x40000,SCHEMA,REPLY.size,GUARD)+tuple([0]*9)
    return HEADER.unpack(HEADER.pack(MAGIC,1,0,COMMAND,*args,len(payload))),payload


class StateProbeTests(unittest.TestCase):
    def test_parses_raw_candidates_without_assuming_game_state(self):
        result=parse_state_reply(*response())
        self.assertEqual(result['game'],'Ultra Moon')
        self.assertEqual(result['battle_candidate']['value'],'304b742c')
        self.assertEqual(result['dialog_candidate']['value'],'00080008')
        self.assertEqual(result['menu_candidate']['value'],'00000000')

    def test_capability_probe_never_requests_a_read(self):
        exchange=Mock(return_value=response(status=0xe1000001))
        self.assertIsNone(read_state(exchange,capability=True))
        self.assertEqual(exchange.call_args.args[1],(GUARD^1,SCHEMA))

    def test_logs_context_and_read_errors_without_controlling_reset(self):
        stop=threading.Event();context={'attempt':3,'phase':'loading'}
        request=Mock(side_effect=[response(status=0xe1000001),response(),response()])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'states.jsonl'
            recorder=StateRecorder(request,stop,path,context,Mock(),interval=.5)
            recorder.start()
            recorder.close()
            rows=[json.loads(x) for x in path.read_text().splitlines()]
            self.assertLessEqual(len(rows),1)
            if rows:self.assertEqual(rows[0]['phase'],'loading')
