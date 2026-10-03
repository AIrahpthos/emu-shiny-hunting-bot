"""Learn loading limits only from directly recognised gradient screens."""
import json
import math
import statistics
import time
from pathlib import Path


class ResetStats:
    MIN_SAMPLES = 10
    WINDOW = 100

    def __init__(self, path, key):
        self.path = Path(path)
        self.key = key
        self.samples = []
        self.observed_count = 0
        if self.path.exists():
            with self.path.open(encoding='utf-8') as file:
                for line in file:
                    try:
                        record = json.loads(line)
                        if not isinstance(record, dict):
                            continue
                        if record.get('key') == key and record.get('gradient_seen') is True:
                            self._accept(record)
                    except (ValueError, TypeError, KeyError):
                        continue

    def _accept(self, record):
        seconds, taps = record['seconds'], record['a_taps']
        if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 0 <= seconds <= 45:
            raise ValueError('Invalid observed reset duration')
        if not isinstance(taps, int) or not 0 <= taps <= 1000:
            raise ValueError('Invalid A tap count')
        self.observed_count += 1
        self.samples.append((seconds, taps))
        self.samples = self.samples[-self.WINDOW:]

    @staticmethod
    def upper(values, margin):
        median = statistics.median(values)
        mad = statistics.median(abs(value-median) for value in values)
        # Use all recent observed successes, rather than assuming a normal
        # distribution or interpreting tap count as independent of duration.
        return max(max(values)+margin, median+6*1.4826*mad+margin)

    def limits(self):
        if len(self.samples) < self.MIN_SAMPLES:
            return None
        seconds = min(44.5, self.upper([x[0] for x in self.samples], 1.0))
        taps = math.ceil(self.upper([x[1] for x in self.samples], 5))
        # Do not create an earlier limit than any actual recent success.
        if seconds <= max(x[0] for x in self.samples):
            return None
        return seconds, taps

    def record(self, result):
        record = {'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                  'key': self.key, 'gradient_seen': result.gradient_seen,
                  'seconds': result.seconds, 'a_taps': result.a_taps,
                  'match_error': result.match_error}
        if result.gradient_seen:
            self._accept(record)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('a', encoding='utf-8') as file:
            file.write(json.dumps(record, allow_nan=False)+'\n')

    def record_failure(self, attempt, phase, reason, consecutive):
        record = {'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                  'key': self.key, 'gradient_seen': False, 'type': 'attempt_failure',
                  'attempt': attempt, 'phase': phase, 'reason': str(reason),
                  'consecutive_failures': consecutive}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('a', encoding='utf-8') as file:
            file.write(json.dumps(record)+'\n')
