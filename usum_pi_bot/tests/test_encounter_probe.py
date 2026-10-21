import importlib.util
from pathlib import Path
import socket
import struct
import sys
import threading
import unittest

spec = importlib.util.spec_from_file_location('encounter_probe', Path(__file__).resolve().parents[1]/'encounter_probe.py')
probe = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)


def pokemon(xor=16, constant=0xDEADBEEF):
    data = bytearray(232)
    struct.pack_into('<I',data,0,constant)
    struct.pack_into('<H',data,8,717)
    tid, sid, low = 12345, 45678, 0xABCD
    high = tid ^ sid ^ low ^ xor
    struct.pack_into('<HH',data,0xC,tid,sid)
    struct.pack_into('<I',data,0x18,(high<<16)|low)
    for offset, value in [(0x38,0x5555),(0x70,0x6666),(0xA8,0x7777),(0xE0,0x8888)]:
        struct.pack_into('<H',data,offset,value)
    checksum = sum(struct.unpack_from('<112H',data,8)) & 0xFFFF
    struct.pack_into('<H',data,6,checksum)
    return bytes(data)


def encrypt(data):
    ec, = struct.unpack_from('<I',data)
    order = probe.ORDERS[((ec>>13)&31)%24]
    blocks = [b'']*4
    for i, c in enumerate(order):
        blocks[ord(c)-65] = data[8+i*56:8+(i+1)*56]
    seed = ec
    result = bytearray(data[:8])
    for word, in struct.iter_unpack('<H',b''.join(blocks)):
        seed = (seed*0x41C64E6D+0x6073)&0xFFFFFFFF
        result.extend(struct.pack('<H',word^(seed>>16)))
    return bytes(result)


class DecoderTests(unittest.TestCase):
    def test_shiny_boundaries_and_expected_identity(self):
        for xor, expected in [(0,True),(15,True),(16,False),(65535,False)]:
            p = probe.decode_record(pokemon(xor))
            self.assertEqual((p.species,p.trainer_id,p.secret_id,p.shiny_xor,p.shiny),
                             (717,12345,45678,xor,expected))

    def test_encrypted_all_shuffle_values(self):
        for shuffle in range(32):
            plain = pokemon(15, (shuffle<<13)|0x123)
            encrypted = encrypt(plain)
            self.assertEqual(probe.decrypt_record(encrypted),plain)
            self.assertTrue(probe.decode_record(encrypted).shiny)
            self.assertEqual(probe.decode_record(encrypted).encoding,'encrypted')

    def test_empty_short_corrupt_and_egg_are_rejected(self):
        corrupt = bytearray(pokemon()); corrupt[20] ^= 1
        egg = bytearray(pokemon()); struct.pack_into('<I',egg,0x74,1<<30)
        struct.pack_into('<H',egg,6,sum(struct.unpack_from('<112H',egg,8))&0xFFFF)
        for data in [b'', b'\0'*232, corrupt, egg, pokemon()[:231]]:
            with self.assertRaises(probe.ProbeError): probe.decode_record(data)


class TransportTests(unittest.TestCase):
    def test_real_tcp_fragmented_response_and_error_without_data(self):
        server = socket.socket(); server.bind(('127.0.0.1',0)); server.listen(1)
        failures = []
        def respond():
            try:
                with server, server.accept()[0] as sock:
                    for status in (0,0xE1000002):
                        request = probe.HEADER.unpack(probe.recv_exact(sock,84))
                        self.assertEqual(request[3],902)
                        self.assertEqual(request[4:6],(probe.GUARD,probe.ADDRESS))
                        self.assertEqual(request[-1],0)
                        args=[status,0x31,0x1B5100,0x40000,probe.ADDRESS,232,probe.GUARD]+[0]*9
                        payload=b'' if status else encrypt(pokemon(15))
                        message=probe.HEADER.pack(probe.MAGIC,request[1],0,902,*args,len(payload))+payload
                        for i in range(0,len(message),7): sock.sendall(message[i:i+7])
            except BaseException as error: failures.append(error)
        thread=threading.Thread(target=respond,daemon=True);thread.start()
        with probe.EncounterReader('127.0.0.1',server.getsockname()[1]) as reader:
            meta, raw=reader.read();self.assertEqual(meta['game'],'Ultra Moon')
            self.assertTrue(probe.decode_record(raw).shiny)
            meta,raw=reader.read();self.assertIsNone(raw);self.assertEqual(meta['result'],'e1000002')
        thread.join(5);self.assertFalse(thread.is_alive());self.assertFalse(failures,failures)

    def test_truncated_stream_is_not_a_normal_result(self):
        a,b=socket.socketpair()
        try:
            a.sendall(b'abc');a.close()
            with self.assertRaises(probe.ProbeError): probe.recv_exact(b,4)
        finally: a.close();b.close()

    def test_cli_offline_does_not_connect(self):
        import contextlib,io,tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'sample.bin';path.write_bytes(encrypt(pokemon(15)))
            with patch.object(socket,'create_connection',side_effect=AssertionError('Network not permitted')),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(probe.main(['--file',str(path)]),0)


if __name__ == '__main__': unittest.main()
