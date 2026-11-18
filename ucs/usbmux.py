"""Apple USB service port forwarding. Original plist/framing implementation.

Only USB-attached devices are selected. The tunnel carries the existing TLS stream;
this module never sees pairing credentials or decrypts media. No library copied.
"""
import plistlib
import socket
import struct
import threading

HEADER=struct.Struct('<IIII')
MAX_PACKET=1024*1024
DEVICE_PORT=49201

class USBError(OSError): pass

def exact(sock,n):
    data=bytearray()
    while len(data)<n:
        part=sock.recv(n-len(data))
        if not part:raise USBError('USB service closed an incomplete message')
        data.extend(part)
    return bytes(data)

def request(sock,fields,tag=1):
    body=plistlib.dumps(dict(ClientVersionString='UCS-0.5',ProgName='UniversalCameraStudio',
        kLibUSBMuxVersion=3,**fields),fmt=plistlib.FMT_XML)
    sock.sendall(HEADER.pack(len(body)+16,1,8,tag)+body)
    size,version,kind,reply_tag=HEADER.unpack(exact(sock,16))
    if not 16<=size<=MAX_PACKET or (version,kind,reply_tag)!=(1,8,tag):
        raise USBError('Invalid USB service response')
    try:result=plistlib.loads(exact(sock,size-16))
    except Exception as exc:raise USBError('Invalid USB service plist') from exc
    if not isinstance(result,dict):raise USBError('Invalid USB service object')
    return result

def usb_device_ids(service=('127.0.0.1',27015)):
    with socket.create_connection(service,timeout=1) as sock:
        result=request(sock,{'MessageType':'ListDevices'})
    return [x['DeviceID'] for x in result.get('DeviceList',[])
        if isinstance(x,dict) and type(x.get('DeviceID')) is int and x.get('Properties',{}).get('ConnectionType')=='USB']

def connect_device(device_id,port=DEVICE_PORT,service=('127.0.0.1',27015)):
    if type(device_id) is not int or device_id<0 or not 1<=port<=65535:raise USBError('Invalid USB target')
    sock=socket.create_connection(service,timeout=1)
    try:
        result=request(sock,{'MessageType':'Connect','DeviceID':device_id,'PortNumber':socket.htons(port)})
        if result.get('MessageType')!='Result' or result.get('Number')!=0:
            raise USBError('Phone application is not listening on USB')
        sock.settimeout(2);sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
        return sock
    except Exception:sock.close();raise

class TunnelRegistry:
    def __init__(self):self.lock=threading.Lock();self.peers=set()
    def add(self,peer):
        with self.lock:self.peers.add(peer)
    def remove(self,peer):
        with self.lock:self.peers.discard(peer)
    def resolve(self,peer):
        with self.lock:return 'USB/usbmux TCP/TLS' if peer in self.peers else 'Wi-Fi/LAN TCP/TLS'

def bridge(left,right,stop,on_counts=None):
    """One 64 KiB buffer per direction, no expanding producer queue."""
    finished=threading.Event();counts=[0,0];lock=threading.Lock()
    def pump(source,target,index):
        try:
            while not stop.is_set() and not finished.is_set():
                try:data=source.recv(65536)
                except socket.timeout:continue
                if not data:break
                target.sendall(data)
                with lock:counts[index]+=len(data)
        except OSError:pass
        finally:
            finished.set()
            for sock in (source,target):
                try:sock.shutdown(socket.SHUT_RDWR)
                except OSError:pass
    workers=[threading.Thread(target=pump,args=(left,right,0),daemon=True),
             threading.Thread(target=pump,args=(right,left,1),daemon=True)]
    for worker in workers:worker.start()
    while not finished.wait(.1):
        if stop.is_set():
            for sock in (left,right):
                try:sock.shutdown(socket.SHUT_RDWR)
                except OSError:pass
            break
    for worker in workers:worker.join(timeout=3)
    if on_counts:on_counts({'usb_to_pc_bytes':counts[0],'pc_to_usb_bytes':counts[1]})

def monitor(host,port,stop,registry,on_event=None,service=('127.0.0.1',27015)):
    while not stop.is_set():
        try:devices=usb_device_ids(service)
        except OSError:
            if on_event:on_event({'event':'usb_status','detail':'Servico Apple USB indisponivel'})
            stop.wait(2);continue
        if on_event:on_event({'event':'usb_status','detail':('iPhone por cabo detectado. Ative USB no app.' if devices else 'Aguardando iPhone por cabo.')})
        for device_id in devices:
            if stop.is_set():break
            try:usb=connect_device(device_id,service=service)
            except OSError:continue
            peer=None
            try:
                with usb,socket.create_connection((host,port),timeout=2) as local:
                    local.settimeout(2);local.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
                    peer=local.getsockname();registry.add(peer)
                    bridge(usb,local,stop,lambda counts:on_event(dict(counts,event='usb_bytes')) if on_event else None)
            except OSError:pass
            finally:
                if peer:registry.remove(peer)
        stop.wait(1)
