"""Conservative memory decisions gated by the existing encounter-start detector."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
from encounter_probe import GUARD, ProbeError, decode_record, parse_encounter_reply
from core import Stopped
from species_names import species_name


class MemoryCheckError(RuntimeError):
    """An unknown encounter must not enter automatic reset recovery."""


class MemoryHunt:
    def __init__(self, request, stop, log_path):
        self.request=request;self.stop=stop;self.path=Path(log_path)
        self.before=None;self.previous=None

    def check_capability(self):
        header,payload=self.request(self.stop,capability=True)
        if header[3]!=902 or header[4]!=0xE1000001 or header[10]!=GUARD or payload:
            raise MemoryCheckError('NTR Encounter Reader v3 was not confirmed. No reset sent.')

    def read(self):
        if self.stop.is_set(): raise Stopped()
        return parse_encounter_reply(*self.request(self.stop))

    @staticmethod
    def identity(metadata,raw):
        if raw is None:return None
        return (metadata['process_id'],hashlib.sha256(raw).hexdigest())

    def prepare(self):
        metadata,raw=self.read()
        self.before=self.identity(metadata,raw)

    def observe(self, timeout=10, interval=.1):
        start=time.monotonic();deadline=start+timeout;candidate=None
        last_reason='No valid opponent data.'
        while time.monotonic()<deadline:
            metadata,raw=self.read()
            identity=self.identity(metadata,raw)
            try:
                if raw is None: raise ProbeError('Opponent memory is not readable: '+metadata['result'])
                pokemon=decode_record(raw)
                if identity in (self.before,self.previous):
                    raise ProbeError('Opponent data has not changed since the previous observation.')
                # Stop immediately on any valid shiny read. Confirmation is required only to reset.
                if pokemon.shiny or candidate==identity:
                    record={'time':time.strftime('%Y-%m-%d %H:%M:%S'),**metadata,
                            **asdict(pokemon),'species_name':species_name(pokemon.species),
                            'check_seconds':time.monotonic()-start}
                    self.path.parent.mkdir(parents=True,exist_ok=True)
                    with self.path.open('a',encoding='utf-8') as log:
                        log.write(json.dumps(record)+'\n');log.flush()
                    self.previous=identity
                    return pokemon,record['check_seconds']
                candidate=identity
                last_reason='Waiting for a second matching normal snapshot.'
            except ProbeError as error:
                candidate=None;last_reason=str(error)
            if self.stop.wait(min(interval,max(0,deadline-time.monotonic()))): raise Stopped()
        raise MemoryCheckError('Memory check stayed unknown; stopped without another reset. '+last_reason)
