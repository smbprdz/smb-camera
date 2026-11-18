import io,plistlib,socket,struct,threading,unittest
from unittest.mock import patch
from ucs.usbmux import HEADER,MAX_PACKET,USBError,request,usb_device_ids,connect_device,TunnelRegistry,bridge

class Stream:
    def __init__(self,data):self.stream=io.BytesIO(data);self.sent=b''
    def recv(self,n):return self.stream.read(min(n,3))
    def sendall(self,data):self.sent+=data
    def settimeout(self,t):pass
    def setsockopt(self,*args):pass
    def close(self):pass
    def __enter__(self):return self
    def __exit__(self,*args):pass

def reply(obj):
    data=plistlib.dumps(obj);return HEADER.pack(len(data)+16,1,8,1)+data

class USBTests(unittest.TestCase):
    def test_network_devices_are_excluded(self):
        source=Stream(reply({'DeviceList':[{'DeviceID':1,'Properties':{'ConnectionType':'Network'}},
            {'DeviceID':2,'Properties':{'ConnectionType':'USB'}}]}))
        with patch('socket.create_connection',return_value=source):self.assertEqual(usb_device_ids(),[2])
    def test_port_endianness_and_refused_application(self):
        source=Stream(reply({'MessageType':'Result','Number':0}))
        with patch('socket.create_connection',return_value=source):self.assertIs(connect_device(2),source)
        fields=plistlib.loads(source.sent[16:]);self.assertEqual(fields['PortNumber'],socket.htons(49201))
        with patch('socket.create_connection',return_value=Stream(reply({'MessageType':'Result','Number':3}))):
            with self.assertRaises(USBError):connect_device(2)
    def test_untrusted_size_and_correlation_rejected(self):
        for header in [HEADER.pack(MAX_PACKET+1,1,8,1),HEADER.pack(16,2,8,1),HEADER.pack(16,1,8,9)]:
            with self.assertRaises(USBError):request(Stream(header),{'MessageType':'ListDevices'})
    def test_duplex_stream_and_shutdown(self):
        app,left=socket.socketpair();right,server=socket.socketpair();stop=threading.Event();counts=[]
        for sock in [app,left,right,server]:sock.settimeout(1)
        worker=threading.Thread(target=bridge,args=(left,right,stop,counts.append),daemon=True);worker.start()
        app.sendall(b'camera');self.assertEqual(server.recv(6),b'camera')
        server.sendall(b'control');self.assertEqual(app.recv(7),b'control')
        stop.set();worker.join(2);self.assertFalse(worker.is_alive())
        self.assertEqual(counts,[{'usb_to_pc_bytes':6,'pc_to_usb_bytes':7}])
        for sock in [app,left,right,server]:sock.close()
    def test_usb_label_only_for_registered_peer(self):
        registry=TunnelRegistry();peer=('127.0.0.1',51000)
        self.assertNotIn('USB',registry.resolve(peer));registry.add(peer)
        self.assertIn('USB',registry.resolve(peer));registry.remove(peer)
        self.assertNotIn('USB',registry.resolve(peer))

if __name__=='__main__':unittest.main()
