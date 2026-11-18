"""Synthetic 4K H.264 through an emulated Apple USB service and real TLS receiver.

The emulation validates protocol/forwarding and decoding, not physical USB support.
"""
from pathlib import Path
import hashlib,json,plistlib,queue,socket,ssl,struct,subprocess,sys,threading,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ucs.identity import create
from ucs.receiver import run
from ucs.usbmux import HEADER,exact,monitor,TunnelRegistry,bridge
from ucs.protocol import HELLO,ACCEPT,VIDEO,STOP,Message,encode,receive,json_message
from ucs.synthetic import access_units

def main():
    root=Path('output')/('usb-smoke-'+str(time.time_ns()));root.mkdir(parents=True)
    identity=root/'identity';create(identity);fixture=root/'test-4k.h264'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i',
        'testsrc2=size=3840x2160:rate=30','-frames:v','6','-c:v','libx264','-preset','ultrafast',
        '-tune','zerolatency','-pix_fmt','yuv420p','-x264-params','aud=1:keyint=30:repeat-headers=1',str(fixture)],check=True)
    reference=root/'reference.md5'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-i',str(fixture),'-pix_fmt','yuv420p','-f','framemd5',str(reference)],check=True)
    stop=threading.Event();registry=TunnelRegistry();receiver_port=queue.Queue();reports=[];errors=[]
    def receiver():
        try:reports.extend(run('127.0.0.1',0,identity,root/'sessions',max_sessions=1,ready=receiver_port.put,transport_resolver=registry.resolve))
        except Exception as exc:errors.append('receiver:'+type(exc).__name__)
    thread=threading.Thread(target=receiver,daemon=True);thread.start();port=receiver_port.get(timeout=5)
    # The physical iPhone NWListener is represented by this one local endpoint.
    phone=socket.socket();phone.bind(('127.0.0.1',0));phone.listen();phone.settimeout(8)
    apple=socket.socket();apple.bind(('127.0.0.1',0));apple.listen();apple.settimeout(8)
    def service():
        try:
            while not stop.is_set():
                client,_=apple.accept()
                with client:
                    size,v,kind,tag=HEADER.unpack(exact(client,16));request=plistlib.loads(exact(client,size-16))
                    if request['MessageType']=='ListDevices':result={'DeviceList':[{'DeviceID':42,'Properties':{'ConnectionType':'USB'}}]}
                    else:
                        assert request['PortNumber']==socket.htons(49201)
                        result={'MessageType':'Result','Number':0}
                    payload=plistlib.dumps(result);client.sendall(HEADER.pack(len(payload)+16,1,8,tag)+payload)
                    if request['MessageType']=='Connect':
                        with socket.create_connection(phone.getsockname()) as device:
                            client.settimeout(1);device.settimeout(1);bridge(client,device,stop)
                        return
        except Exception as exc:errors.append('service:'+type(exc).__name__)
    fake=threading.Thread(target=service,daemon=True);fake.start()
    forwarding=threading.Thread(target=monitor,args=('127.0.0.1',port,stop,registry,None,apple.getsockname()),daemon=True)
    forwarding.start()
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.check_hostname=False;context.verify_mode=ssl.CERT_NONE
    try:raw,_=phone.accept()
    except socket.timeout as exc:
        stop.set();fake.join(1);forwarding.join(3);phone.close();apple.close()
        raise AssertionError(('USB emulator did not reach phone endpoint',errors)) from exc
    raw.settimeout(5)
    # Phone is the TLS CLIENT on a connection physically initiated by the desktop USB service.
    with context.wrap_socket(raw,server_hostname='paired-desktop') as client:
        assert hashlib.sha256(client.getpeercert(binary_form=True)).hexdigest()==(identity/'fingerprint.txt').read_text()
        hello=dict(codec='h264',width=3840,height=2160,fps=30,pixel_format='yuv420p',color='bt709-sdr')
        hello['token']=(identity/'token.txt').read_text();client.sendall(encode(json_message(HELLO,hello)))
        assert receive(client).kind==ACCEPT
        for n,(data,key) in enumerate(access_units(fixture.read_bytes())):
            client.sendall(encode(Message(VIDEO,data,n,round(n*1e6/30),int(key))));time.sleep(1/30)
        client.sendall(encode(Message(STOP)))
    thread.join(10);stop.set();forwarding.join(4);fake.join(4);phone.close();apple.close()
    assert not thread.is_alive() and not errors,(errors,reports)
    assert len(reports)==1 and reports[0]['status']=='stopped' and reports[0]['decoded_frames']==6,reports
    assert reports[0]['decoded_dimensions']==[3840,2160] and reports[0]['transport'].startswith('USB')
    def hashes(path):return [l.rsplit(',',1)[-1].strip() for l in path.read_text().splitlines() if l and not l.startswith('#')]
    decoded=next((root/'sessions').glob('*/decoded.framemd5'));assert hashes(decoded)==hashes(reference)
    result=dict(status='pass',scope='synthetic 6-frame4K stream, emulated usbmux, real TLS/hash decode',
        decoded=reports[0]['decoded_frames'],dimensions=reports[0]['decoded_dimensions'],hashes_equal=True,
        physical_usb_validated=False,iphone_validated=False)
    (root/'summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result));print(root/'summary.json')

if __name__=='__main__':main()
