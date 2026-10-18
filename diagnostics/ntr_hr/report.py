#!/usr/bin/env python3
"""Summarise durable loader checkpoints without treating missing records as proof of a crash."""
import argparse
import re
from pathlib import Path

RECORD = re.compile(
    r'^NTRPLG/1 launch=([0-9a-f]{8}) seq=([0-9a-f]{8}) stage=([a-z-]+) '
    r'result=([0-9a-f]{8}) a=([0-9a-f]{8}) b=([0-9a-f]{8}) detail=(.*)$')


def analyse(text):
    launches = []
    malformed = 0
    for line in text.splitlines():
        match = RECORD.fullmatch(line)
        if not match:
            if line.strip(): malformed += 1
            continue
        launch, sequence, stage, result, a, b, detail = match.groups()
        record = dict(launch=int(launch,16), sequence=int(sequence,16), stage=stage,
                      result=int(result,16), a=int(a,16), b=int(b,16), detail=detail)
        if stage == 'begin' or not launches:
            launches.append([])
        launches[-1].append(record)
    return launches, malformed


def summarise(text):
    launches, malformed = analyse(text)
    lines = [f'Launch attempts retained: {len(launches)}; unreadable/partial lines: {malformed}.']
    for records in launches[-5:]:
        first, last = records[0], records[-1]
        plugins = [r['detail'] for r in records if r['stage'] == 'plugin-file']
        state = 'run returned' if last['stage'] == 'run-exit' else 'no run-exit checkpoint recorded'
        lines.append(f'Launch {first["launch"]}: {state}; last checkpoint: {last["stage"]}.')
        lines.append('  Plugin files attempted: ' + (', '.join(plugins) if plugins else 'none recorded'))
        for r in records:
            if r['stage'] in ('title-exit', 'plugins-ready', 'options', 'overlays', 'debug-next', 'plugin-hash') or r['result']:
                lines.append(f'  {r["stage"]}: result={r["result"]:08x} a={r["a"]:08x} b={r["b"]:08x} {r["detail"]}')
    lines.append('An unfinished trace can also mean power-off, failed logging or an interrupted write; it is not proof of a crash at that operation.')
    return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('log', type=Path)
    args = parser.parse_args()
    print(summarise(args.log.read_text(errors='replace')))
