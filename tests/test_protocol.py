import io
import struct
import unittest
from ucs.protocol import *

class Fragmented:
    def __init__(self,data,step=1): self.stream=io.BytesIO(data);self.step=step
    def recv_into(self,view):
        data=self.stream.read(min(len(view),self.step));view[:len(data)]=data;return len(data)

class ProtocolTests(unittest.TestCase):
    def test_golden_vector(self):
        self.assertEqual(encode(Message(PING,seq=2,pts_us=3)).hex(),
            '5543533101040000000000000000000000000002000000000000000300000000')
    def test_fragmentation_and_coalescing(self):
        messages=[json_message(HELLO,{'x':1}),Message(VIDEO,b'\0\0\1abc',8,23,1),Message(STOP)]
        for step in [1,2,7,31,10000]:
            sock=Fragmented(b''.join(map(encode,messages)),step)
            self.assertEqual([receive(sock) for _ in messages],messages)
    def test_truncations(self):
        data=encode(Message(VIDEO,b'\0\0\1abc',flags=1))
        for length in range(len(data)):
            with self.assertRaises(EOFError): receive(Fragmented(data[:length]))
    def test_untrusted_header_rejected_before_allocation(self):
        for magic,version,kind,flags,size,reserved in [
            (b'XXXX',1,3,0,1,0),(b'UCS1',2,3,0,1,0),
            (b'UCS1',1,99,0,1,0),(b'UCS1',1,3,2,1,0),
            (b'UCS1',1,3,0,MAX_VIDEO+1,0),(b'UCS1',1,1,0,MAX_CONTROL+1,0),
            (b'UCS1',1,3,0,1,1),(b'UCS1',1,3,0,0,0)]:
            with self.assertRaises(ProtocolError):
                receive(Fragmented(HEADER.pack(magic,version,kind,flags,size,0,0,reserved)))
    def test_json(self):
        for payload in [b'[]',b'null',b'\xff',b'{']:
            with self.assertRaises(ProtocolError): read_json(Message(HELLO,payload))
    def test_format_validation(self):
        valid=dict(codec='h264',pixel_format='yuv420p',color='bt709-sdr',width=3840,height=2160,fps=60)
        self.assertEqual(validate_stream(valid),valid)
        for key,value in [('fps',True),('width',1921),('height',0),('codec','hevc'),('color','hdr')]:
            with self.assertRaises(ProtocolError): validate_stream(dict(valid,**{key:value}))

if __name__=='__main__': unittest.main()
