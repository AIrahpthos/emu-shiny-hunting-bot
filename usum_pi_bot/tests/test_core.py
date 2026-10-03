import socket
import struct
import threading
import unittest
from unittest.mock import patch
from core import choose_bottom_window, packet, Controller, Stopped, classify, wait_sample, measure


class CoreTests(unittest.TestCase):
    def test_find_bottom_window_by_prefix(self):
        self.assertEqual(choose_bottom_window([(1,'OBS'),(2,'cc3dsfs_bot (60 fps)'),(3,'cc3dsfs_top')]),2)
        with self.assertRaises(ValueError): choose_bottom_window([(1,'OBS')])
        with self.assertRaisesRegex(ValueError,'More than one'):
            choose_bottom_window([(1,'cc3dsfs_bot'),(2,'cc3dsfs_bot extra')])

    def test_neutral_and_reset_packets(self):
        self.assertEqual(struct.unpack('<5I',packet()),(0xfff,0x2000000,0x7ff7ff,0x80800081,0))
        reset=struct.unpack('<5I',packet(('L','R','START','SELECT')))[0]
        self.assertEqual(reset,0xfff & ~((1<<9)|(1<<8)|(1<<3)|(1<<2)))
        self.assertEqual(struct.unpack('<5I',packet(y=1))[2],(0xdd0<<12)|0x800)

    def test_real_udp_press_and_final_release(self):
        server=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        server.bind(('127.0.0.1',0)); server.settimeout(1)
        controller=Controller('127.0.0.1',threading.Event())
        controller.address=server.getsockname()
        try:
            controller.hold(('A',),.06)
            frames=[]
            while True:
                try: frames.append(server.recv(128))
                except socket.timeout: break
            self.assertEqual(struct.unpack('<5I',frames[0])[0],0xffe)
            self.assertEqual(frames[-3:],[packet()]*3)
        finally:
            controller.close(); server.close()

    def test_stop_interrupts_and_releases(self):
        stop=threading.Event(); stop.set()
        controller=Controller('127.0.0.1',stop)
        with patch.object(controller,'release') as release:
            with self.assertRaises(Stopped): controller.hold(('A',),1)
            release.assert_called_once()
        controller.close()

    def test_timing_decision(self):
        self.assertEqual(classify(6.2,5,1.1),'suspected shiny')
        self.assertEqual(classify(3.8,5,1.1),'uncertain')
        self.assertEqual(classify(5.4,5,1.1),'normal')

    def test_transition_requires_consecutive_samples(self):
        values=iter([(0,0,0),(100,100,100),(0,0,0),(100,100,100),(100,100,100),(100,100,100)])
        class FastStop:
            def is_set(self): return False
            def wait(self,_): return False
        self.assertEqual(wait_sample(lambda:next(values),lambda p:p[0]>50,FastStop()),(100,100,100))

    def test_stalled_feed_times_out(self):
        with self.assertRaises(TimeoutError):
            wait_sample(lambda:(0,0,0),lambda p:p[0]>50,threading.Event(),timeout=.01)

    def test_complete_measurement(self):
        values=iter([(0,0,0)]*3+[(100,100,100)]*3+[(200,200,200)]*3)
        class FastStop:
            def is_set(self): return False
            def wait(self,_): return False
        self.assertGreaterEqual(measure(lambda:next(values),FastStop()),0)


if __name__=='__main__': unittest.main()
