import tempfile
import unittest
import secrets
from unittest.mock import patch
from ucs.protocol import *
from ucs.receiver import serve_session
from test_protocol import Fragmented

class Connection(Fragmented):
    def settimeout(self,value): pass
    def sendall(self,data): self.sent=data

class SessionTests(unittest.TestCase):
    def test_timing_negotiation_preserves_legacy_and_replies_with_clock_samples(self):
        import json,struct
        class Peer(Connection):
            def __init__(self,data):super().__init__(data);self.responses=[]
            def sendall(self,data):self.responses.append(receive(Fragmented(data)))
        class Sink:
            failure=None
            def __init__(self,folder,*args):self.folder=folder
            def close(self):
                (self.folder/'decoded.framemd5').write_text('#dimensions 0: 1920x1080\n')
                return 0
        for timing in (False,True):
            hello=dict(token='a'*64,codec='h264',pixel_format='yuv420p',color='bt709-sdr',width=1920,height=1080,fps=30)
            if timing:hello['timing']=1
            payload=b'{"encoder_p95_ms":12}' if timing else b'legacy-echo'
            data=b''.join(map(encode,[json_message(HELLO,hello),Message(PING,payload,seq=8,pts_us=99),Message(STOP)]))
            with tempfile.TemporaryDirectory() as folder,patch('ucs.receiver.DecodeSink',Sink):
                peer=Peer(data);report=serve_session(peer,'a'*64,folder)
            accept,pong=peer.responses
            self.assertEqual(json.loads(accept.payload).get('timing'),1 if timing else None)
            self.assertEqual((pong.kind,pong.seq,pong.pts_us),(PONG,8,99))
            if timing:
                received,sent=struct.unpack('!QQ',pong.payload);self.assertGreaterEqual(sent,received)
                self.assertEqual(report['sender_metrics']['encoder_p95_ms'],12)
            else:self.assertEqual(pong.payload,payload)

    def test_auth_and_state_fail_closed_before_media_process(self):
        invalid_token = secrets.token_hex(16) # Deliberately shorter than the 256-bit pairing token.
        for msg in [Message(VIDEO,b'\0\0\1x',flags=1),
                    json_message(HELLO,{'token':invalid_token}),
                    json_message(HELLO,{'token':'a'*64,'codec':'hevc'})]:
            with tempfile.TemporaryDirectory() as output:
                with self.assertRaises(ProtocolError):
                    serve_session(Connection(encode(msg)),'a'*64,output)

    def test_reordered_frames_and_false_keyframe_are_rejected(self):
        hello=json_message(HELLO,dict(token='a'*64,codec='h264',pixel_format='yuv420p',
            color='bt709-sdr',width=1920,height=1080,fps=30))
        au=b'\0\0\1\x67a\0\0\1\x68b\0\0\1\x65c'
        class Sink:
            failure=None
            def __init__(self,folder,*args):
                self.folder=folder;self.frames=0
            def put(self,data):self.frames+=1
            def close(self):
                # Stub only decoder, testing state machine without asserting real decoding.
                (self.folder/'decoded.framemd5').write_text('#dimensions 0: 1920x1080\n'+
                    '\n'.join('0,0,0,1,1,x' for _ in range(self.frames)))
                return 0
        cases=[([Message(VIDEO,au,2,100,1),Message(VIDEO,au,2,101,1)],'non-monotonic'),
               ([Message(VIDEO,au,2,100,1),Message(VIDEO,au,3,99,1)],'non-monotonic'),
               ([Message(VIDEO,b'\0\0\1\x41x',0,100,1)],'IDR/SPS/PPS'),
               ([Message(PONG)],'unexpected')]
        for messages,error in cases:
            with tempfile.TemporaryDirectory() as output, patch('ucs.receiver.DecodeSink',Sink):
                report=serve_session(Connection(b''.join(encode(m) for m in [hello,*messages])),
                                     'a'*64,output)
                self.assertEqual(report['status'],'failed')
                self.assertIn(error,report['error'])

if __name__=='__main__': unittest.main()
