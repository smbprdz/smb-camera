import struct
import unittest
from ucs.frame_output import FrameOutput,REQUEST,REPLY
from tools.probe_frame_output import classify_packet


class FrameDiagnosticTests(unittest.TestCase):
    def packet(self):
        out=FrameOutput(clock=lambda:1.,tick_ms=lambda:1000,epoch=7,formats=(3,))
        out.set_canvas(4,2);request=REQUEST.pack(0x51534355,1,24,3,4,2,0)
        out.request(request,wait=0);out.publish(4,2,bytes([0,0,0,128])*8,1.,3)
        return out.request(request,wait=0)

    def test_expired_packet_is_reported_without_accepting_stale_video(self):
        packet=self.packet()
        self.assertEqual(classify_packet(packet,{'epoch':7},4,2,3,1100)[0],'frame')
        self.assertEqual(classify_packet(packet,{'epoch':7},4,2,3,1251),('expired',None))
        with self.assertRaises(ValueError):classify_packet(packet,{'epoch':7},4,2,3,999)

    def test_identity_structure_and_empty_reply_still_fail_closed(self):
        packet=self.packet()
        with self.assertRaises(ValueError):classify_packet(packet,{'epoch':8},4,2,3,1100)
        wrong=bytearray(packet);struct.pack_into('<I',wrong,92,0)
        with self.assertRaises(ValueError):classify_packet(wrong,{'epoch':7},4,2,3,1400)
        empty=REPLY.pack(0x52534355,1,0,0,0,0,7)
        self.assertEqual(classify_packet(empty,{'epoch':7},4,2,3,1100),('empty',None))
        with self.assertRaises(ValueError):classify_packet(empty+b'bad',{'epoch':7},4,2,3,1100)
