#!/usr/bin/env python3
"""Read-only USUM state diagnostics for the NTR v4 endpoint.

The three addresses are candidates from PKMN-NTR's updated-USUM bot, not yet
validated on this console's older game revision. Raw values are deliberately
logged without assigning them a game-state meaning.
"""
import argparse
import json
from pathlib import Path
import struct
import time

from encounter_probe import EncounterReader, ProbeError, TITLES

COMMAND = 903
GUARD = 0x53544154
SCHEMA = 1
ADDRESSES = (0x67107c, 0x6a668c, 0x6a60ea)
LABELS = ('battle_candidate', 'dialog_candidate', 'menu_candidate')
REPLY = struct.Struct('<6I')


def parse_state_reply(header, payload, capability=False):
    if len(header) != 21 or header[3] != COMMAND or header[10] != GUARD or header[8] != SCHEMA or header[9] != REPLY.size:
        raise ProbeError('Unexpected state-reader response.')
    status = header[4]
    if capability:
        if status != 0xe1000001 or payload or header[-1] != 0:
            raise ProbeError('NTR State Reader v4 endpoint was not confirmed.')
        return None
    if header[-1] != len(payload) or len(payload) != (REPLY.size if status == 0 else 0):
        raise ProbeError('Invalid state-reader payload length.')
    title = header[6] | (header[7] << 32)
    result = {'result':f'{status:08x}', 'process_id':header[5],
              'title_id':f'{title:016x}', 'game':TITLES.get(title)}
    if status == 0:
        if title not in TITLES: raise ProbeError('Reply did not identify USUM.')
        values = REPLY.unpack(payload)
        for i, label in enumerate(LABELS):
            code, value = values[2*i:2*i+2]
            result[label] = {'address':f'{ADDRESSES[i]:08x}', 'result':f'{code:08x}',
                             'value':f'{value:08x}' if code == 0 else None}
    return result


def read_state(exchange, capability=False):
    args = (GUARD ^ 1 if capability else GUARD, SCHEMA)
    return parse_state_reply(*exchange(COMMAND, args, 'USUM state diagnostics'), capability=capability)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', help='3DS IP; defaults to bot settings.json')
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--interval', type=float, default=.25)
    parser.add_argument('--out', type=Path, help='JSONL result path')
    args=parser.parse_args(argv)
    if not 0 < args.seconds <= 3600 or not .1 <= args.interval <= 60:
        parser.error('Use duration 0–3600 seconds and interval 0.1–60 seconds.')
    root=Path(__file__).resolve().parent
    if not args.host:
        try:args.host=json.loads((root/'settings.json').read_text())['ip']
        except (OSError, ValueError, KeyError):parser.error('Supply --host or save the bot IP.')
    target=args.out or (root/'out'/('state-probe-'+time.strftime('%Y%m%d-%H%M%S')+'.jsonl'))
    try:
        with EncounterReader(args.host) as reader:
            reader._exchange(0, (), 'NTR heartbeat')
            read_state(reader._exchange,capability=True)
            target.parent.mkdir(parents=True,exist_ok=True)
            print(f'State Reader v4 confirmed. Logging raw candidates to {target}',flush=True)
            deadline=time.monotonic()+args.seconds
            with target.open('a',encoding='utf-8') as log:
                while time.monotonic()<deadline:
                    sample=read_state(reader._exchange)
                    sample['utc_ns']=time.time_ns()
                    log.write(json.dumps(sample)+'\n');log.flush()
                    if sample['result']!='00000000':print('Game state unavailable: '+sample['result'],flush=True)
                    time.sleep(min(args.interval,max(0,deadline-time.monotonic())))
    except (OSError, ValueError, ProbeError) as error:
        print('State probe stopped: '+str(error),flush=True)
        return 1
    print(f'Finished. Saved {target}',flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
