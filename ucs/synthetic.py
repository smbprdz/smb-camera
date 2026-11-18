"""Send our generated H.264 fixture over the real TLS receiver path."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import socket
import ssl
import time
from .protocol import *

def access_units(data):
    starts = list(re.finditer(b'\x00\x00(?:\x00)?\x01', data))
    cuts = [m.start() for m in starts if m.end()<len(data) and data[m.end()] & 31 == 9]
    if not cuts or cuts[0] != 0:
        raise ValueError('synthetic fixture must begin with AUD and contain one AUD per frame')
    for begin,end in zip(cuts, cuts[1:]+[len(data)]):
        au=data[begin:end]
        key=any(au[m.end()] & 31 == 5 for m in re.finditer(b'\x00\x00(?:\x00)?\x01',au) if m.end()<len(au))
        yield au,key

def connect(host, port, fingerprint):
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    # Exact certificate pin replaces PKI/hostname validation for this paired LAN tool.
    context.check_hostname=False; context.verify_mode=ssl.CERT_NONE
    raw=socket.create_connection((host,port),timeout=5)
    sock=context.wrap_socket(raw,server_hostname=host)
    if hashlib.sha256(sock.getpeercert(binary_form=True)).hexdigest()!=fingerprint:
        sock.close(); raise ProtocolError('certificate pin mismatch')
    return sock

def send(path, host, port, identity, width=1920,height=1080,fps=30):
    identity=Path(identity)
    rtts=[]
    with connect(host,port,(identity/'fingerprint.txt').read_text().strip()) as sock:
        hello={'token':(identity/'token.txt').read_text().strip(),'codec':'h264',
               'width':width,'height':height,'fps':fps,'pixel_format':'yuv420p','color':'bt709-sdr'}
        sock.sendall(encode(json_message(HELLO,hello)))
        if receive(sock).kind!=ACCEPT: raise ProtocolError('no acceptance')
        units=list(access_units(Path(path).read_bytes()))
        start=time.perf_counter()
        count=0
        for count,(au,key) in enumerate(units,1):
            deadline=start+(count-1)/fps
            time.sleep(max(0,deadline-time.perf_counter()))
            sock.sendall(encode(Message(VIDEO,au,count-1,round((count-1)*1e6/fps),int(key))))
            if count%30==0:
                now=time.perf_counter_ns()//1000
                sock.sendall(encode(Message(PING,seq=count,pts_us=now)))
                pong=receive(sock)
                if pong.kind!=PONG or pong.pts_us!=now: raise ProtocolError('bad pong')
                rtts.append((time.perf_counter_ns()//1000-now)/1000)
        sock.sendall(encode(Message(STOP)))
    return {'sent_frames':count,'application_round_trip_ms':rtts,
            'capture_to_display_latency_ms':None,'origin':'generated fixture, not camera'}

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('file');p.add_argument('--host',default='127.0.0.1')
    p.add_argument('--port',type=int,default=49200);p.add_argument('--identity',default='runtime/identity')
    a=p.parse_args(); print(json.dumps(send(a.file,a.host,a.port,a.identity),indent=2))
