#!/usr/bin/env python3
"""Read-only USUM opponent probe for NTR Encounter Reader v3. Standard library only.

Never sends input, resets, memory writes, debugger attaches or stream commands.
Format references: PKMN-NTR LookupTable.WildOffset1 and PKHeX PK7/PokeCrypto.
This reports snapshots; valid data alone does not establish a new encounter.
"""
import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import socket
import struct
import time

HEADER = struct.Struct('<21I')
MAGIC = 0x12345678
COMMAND = 902
GUARD = 0x53484E59
ADDRESS = 0x3254F4AC
SIZE = 232
TITLES = {0x00040000001B5000: 'Ultra Sun', 0x00040000001B5100: 'Ultra Moon'}
# Decryption's four-block ordering for each shuffle value, repeating after 24.
ORDERS = ('ABCD ABDC ACBD ADBC ACDB ADCB BACD BADC CABD DABC CADB DACB '
          'BCAD BDAC CBAD DBAC CDAB DCAB BCDA BDCA CBDA DBCA CDBA DCBA').split()


class ProbeError(Exception):
    pass


@dataclass(frozen=True)
class Pokemon:
    species: int
    personality: int
    encryption_constant: int
    trainer_id: int
    secret_id: int
    shiny_xor: int
    shiny: bool
    encoding: str
    fingerprint: str


def decrypt_record(raw):
    """Decrypt only the 232-byte stored section; ignore party-stat extensions."""
    if len(raw) < SIZE:
        raise ProbeError('Short Pokemon record.')
    raw = raw[:SIZE]
    seed, = struct.unpack_from('<I', raw)
    constant = seed
    words = []
    for word, in struct.iter_unpack('<H', raw[8:]):
        seed = (seed * 0x41C64E6D + 0x6073) & 0xFFFFFFFF
        words.append(word ^ (seed >> 16))
    shuffled = struct.pack('<112H', *words)
    order = ORDERS[((constant >> 13) & 31) % 24]
    return raw[:8] + b''.join(shuffled[(ord(c)-65)*56:(ord(c)-64)*56] for c in order)


def _valid(data):
    if len(data) != SIZE:
        return False
    sanity, checksum, species = struct.unpack_from('<3H', data, 4)
    actual = sum(struct.unpack_from('<112H', data, 8)) & 0xFFFF
    # Both text-field terminators must be zero in a decoded Gen 7 record.
    return (sanity == 0 and checksum == actual and 1 <= species <= 807
            and data[0x58:0x5A] == b'\0\0' and data[0xC8:0xCA] == b'\0\0'
            and not (struct.unpack_from('<I', data, 0x74)[0] & (1 << 30)))


def decode_record(raw):
    if len(raw) < SIZE:
        raise ProbeError('Short Pokemon record.')
    raw = bytes(raw[:SIZE])
    candidates = [(raw, 'decrypted'), (decrypt_record(raw), 'encrypted')]
    valid = {data: encoding for data, encoding in candidates if _valid(data)}
    if len(valid) != 1:
        raise ProbeError('No unambiguous valid Pokemon at this address (empty, incomplete or different layout).')
    data, encoding = next(iter(valid.items()))
    constant, = struct.unpack_from('<I', data)
    species, = struct.unpack_from('<H', data, 8)
    tid, sid = struct.unpack_from('<2H', data, 0xC)
    personality, = struct.unpack_from('<I', data, 0x18)
    xor = tid ^ sid ^ (personality & 0xFFFF) ^ (personality >> 16)
    return Pokemon(species, personality, constant, tid, sid, xor, xor < 16,
                   encoding, hashlib.sha256(raw).hexdigest())


def request_packet(sequence):
    return HEADER.pack(MAGIC, sequence, 0, COMMAND, GUARD, ADDRESS, *([0]*14), 0)


def recv_exact(sock, size):
    out = bytearray()
    while len(out) < size:
        chunk = sock.recv(size-len(out))
        if not chunk:
            raise ProbeError('NTR closed the connection before completing its reply.')
        out.extend(chunk)
    return bytes(out)


class EncounterReader:
    def __init__(self, host, port=8000, timeout=4):
        self.host = str(ipaddress.IPv4Address(host))
        self.port, self.timeout, self.sequence = port, timeout, 0
        self.sock = None

    def __enter__(self):
        self.sock = socket.create_connection((self.host, self.port), self.timeout)
        self.sock.settimeout(self.timeout)
        return self

    def __exit__(self, *args):
        if self.sock:
            self.sock.close()
            self.sock = None

    def read(self):
        self.sequence = (self.sequence + 1) & 0xFFFFFFFF
        self.sock.sendall(request_packet(self.sequence))
        header = HEADER.unpack(recv_exact(self.sock, HEADER.size))
        if header[0] != MAGIC or header[1] != self.sequence or header[3] != COMMAND:
            raise ProbeError('Unexpected NTR reply; this probe requires Encounter Reader v3.')
        status, pid, low, high, address, size, guard = header[4:11]
        length = header[-1]
        if (guard != GUARD or address != ADDRESS or size != SIZE
                or length != (0 if status else SIZE)):
            raise ProbeError('Invalid encounter-reader response.')
        title = low | (high << 32)
        metadata = {'result': f'{status:08x}', 'process_id': pid,
                    'title_id': f'{title:016x}', 'address': f'{address:08x}'}
        if status:
            return metadata, None
        if title not in TITLES:
            raise ProbeError('Reply did not identify Ultra Sun or Ultra Moon.')
        metadata['game'] = TITLES[title]
        return metadata, recv_exact(self.sock, length)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', help='3DS IP; defaults to the bot settings.json IP')
    parser.add_argument('--seconds', type=float, default=15, help='Read for this many seconds (default 15)')
    parser.add_argument('--interval', type=float, default=.5, help='Seconds between requests (minimum 0.1)')
    parser.add_argument('--out', type=Path, help='Result directory')
    parser.add_argument('--file', type=Path, help='Decode an existing raw Pokemon file without connecting')
    args = parser.parse_args(argv)
    if args.file:
        try:
            print(json.dumps(asdict(decode_record(args.file.read_bytes())), indent=2))
            return 0
        except (ProbeError, OSError) as error:
            parser.exit(2, str(error)+'\n')
    if not .1 <= args.interval <= 60 or not 0 < args.seconds <= 3600:
        parser.error('Use interval 0.1–60 seconds and duration 0–3600 seconds.')
    root = Path(__file__).resolve().parent
    host = args.host
    if not host:
        try:
            host = json.loads((root/'settings.json').read_text())['ip']
        except (OSError, ValueError, KeyError):
            parser.error('Supply --host with your 3DS IP, or place this beside the bot settings.json.')
    folder = args.out or root/'out'/('memory-probe-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+str(time.time_ns()))
    folder.mkdir(parents=True, exist_ok=True)
    print('Read-only probe. Close the bot/viewer before connecting. No inputs or resets are sent.', flush=True)
    print('Results: '+str(folder), flush=True)
    valid_count = 0
    seen = set()
    last_summary = None
    try:
        with EncounterReader(host) as reader, (folder/'observations.jsonl').open('a') as log:
            deadline = time.monotonic()+args.seconds
            while time.monotonic() < deadline:
                start = time.monotonic()
                metadata, raw = reader.read()
                row = {'time': datetime.now(timezone.utc).isoformat(), **metadata}
                if raw is None:
                    summary = 'Read unavailable: '+metadata['result']+' (game absent or memory query/copy failed).'
                    row['valid'] = False
                else:
                    digest = hashlib.sha256(raw).hexdigest()
                    row['raw_file'] = digest+'.bin'
                    if digest not in seen:
                        (folder/row['raw_file']).write_bytes(raw)
                        seen.add(digest)
                    try:
                        pokemon = decode_record(raw)
                        row.update(valid=True, **asdict(pokemon))
                        valid_count += 1
                        summary = (f'{metadata["game"]}: species #{pokemon.species}, '
                                   f'PID {pokemon.personality:08X}, '
                                   f'{"SHINY" if pokemon.shiny else "normal"}, XOR {pokemon.shiny_xor}')
                    except ProbeError as error:
                        row.update(valid=False, reason=str(error))
                        summary = str(error)
                row['read_ms'] = round((time.monotonic()-start)*1000, 3)
                log.write(json.dumps(row)+'\n')
                log.flush()
                if summary != last_summary:
                    print(summary, flush=True)
                    last_summary = summary
                time.sleep(max(0, min(args.interval-(time.monotonic()-start), deadline-time.monotonic())))
    except (OSError, ValueError, ProbeError) as error:
        print(f'Probe stopped: {error}. Check v3 is installed and other NTR clients are closed.', flush=True)
        return 2
    except KeyboardInterrupt:
        print('Probe stopped by user.', flush=True)
    print(f'{valid_count} valid snapshots. Snapshots are not encounter counts. No resets performed.', flush=True)
    return 0 if valid_count else 2


if __name__ == '__main__':
    raise SystemExit(main())
