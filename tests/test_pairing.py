import threading
import tempfile
import time
import queue
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import quote
from ucs.pairing import Pairing, parse_pairing, Advertisement
from ucs.identity import create
from ucs.receiver import run
from ucs.synthetic import connect
from ucs.protocol import HELLO, ACCEPT, PING, encode, json_message, Message, receive

def fixture():
    return Pairing('192.168.0.82','Meu PC + camera','a'*64,'b'*64)

class PairingTests(unittest.TestCase):
    def test_url_roundtrip_and_public_service_identity(self):
        value=fixture();uri=value.uri()
        self.assertEqual(parse_pairing(uri),value)
        self.assertIn('Meu%20PC%20%2B%20camera',uri)
        self.assertEqual(value.service_name,'UCS-'+value.pin[:16])
        self.assertNotIn(value.token,repr(value))

    def test_malformed_and_non_lan_inputs_rejected(self):
        uri=fixture().uri()
        invalid=[uri+'&host=192.168.0.1',uri+'&extra=1',uri.replace('v=1','v=2'),
                 uri.replace('192.168.0.82','8.8.8.8'),uri.replace('192.168.0.82','127.0.0.1'),
                 uri.replace('192.168.0.82','169.254.1.2'),uri.replace('192.168.0.82','192.168.000.82'),
                 uri.replace('universalcamera:','https:'),uri.replace('//pair?','//pair:443?'),
                 uri+'#fragment',uri.replace('name=Meu','name=%00Meu'),
                 uri.replace('a'*64,'a'*63),uri.replace('b'*64,'g'*64),uri+'&token', 'x'*4097]
        for value in invalid:
            with self.subTest(case=invalid.index(value)),self.assertRaises(ValueError):parse_pairing(value)

    def test_qr_decodes_to_exact_payload_without_network(self):
        import cv2,numpy,qrcode
        code=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,box_size=6,border=4)
        uri=fixture().uri();code.add_data(uri);code.make(fit=True)
        pixels=numpy.array(code.make_image().convert('RGB'))
        decoded,_,_=cv2.QRCodeDetector().detectAndDecode(pixels)
        self.assertTrue(decoded==uri,'QR did not round-trip; credential values intentionally omitted')

    def test_discovery_does_not_publish_secret(self):
        with patch('zeroconf.Zeroconf'):
            value=fixture();ad=Advertisement(value,49200)
            self.assertNotIn(value.token.encode(),ad.info.text)
            self.assertNotIn(value.token,ad.info.name)
            self.assertEqual(set(ad.info.properties),{b'v',b'name'})
            ad.close()

    def test_idle_receiver_stops_without_new_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            identity=Path(tmp)/'identity';create(identity)
            ready=threading.Event();stop=threading.Event();errors=[]
            def target():
                try:run('127.0.0.1',0,identity,Path(tmp)/'sessions',stop_event=stop,ready=lambda _:ready.set())
                except Exception as exc:errors.append(type(exc).__name__)
            worker=threading.Thread(target=target,daemon=True);worker.start()
            self.assertTrue(ready.wait(5))
            start=time.perf_counter();stop.set();worker.join(2)
            self.assertFalse(worker.is_alive());self.assertFalse(errors)
            self.assertLess(time.perf_counter()-start,1.5)

    def test_desktop_stop_closes_authenticated_session(self):
        class DecoderStub:
            failure=None
            def __init__(self,folder,*args): self.folder=folder
            def close(self):
                (self.folder/'decoded.framemd5').write_text('#dimensions 0: 1920x1080\n')
                return 0
        with tempfile.TemporaryDirectory() as tmp, patch('ucs.receiver.DecodeSink',DecoderStub):
            root=Path(tmp);identity=root/'identity';create(identity)
            port=queue.Queue();disconnect=threading.Event();events=[];errors=[]
            def server():
                try:run('127.0.0.1',0,identity,root/'sessions',max_sessions=1,
                        ready=port.put,disconnect_event=disconnect,on_event=lambda e:events.append(e['event']))
                except Exception as exc:errors.append(type(exc).__name__)
            worker=threading.Thread(target=server,daemon=True);worker.start()
            with connect('127.0.0.1',port.get(timeout=5),(identity/'fingerprint.txt').read_text()) as client:
                hello=dict(codec='h264',width=1920,height=1080,fps=30,pixel_format='yuv420p',color='bt709-sdr')
                hello['token']=(identity/'token.txt').read_text()
                client.sendall(encode(json_message(HELLO,hello)))
                self.assertEqual(receive(client).kind,ACCEPT)
                disconnect.set()
                try:client.sendall(encode(Message(PING)))
                except OSError:pass
                worker.join(2)
                self.assertFalse(worker.is_alive())
            self.assertFalse(errors)
            self.assertEqual(events,['connected','disconnected'])

if __name__=='__main__':unittest.main()
