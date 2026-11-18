"""1080p30 synthetic TLS -> receiver -> real H.264 decode, two sessions."""
import json
import argparse
import secrets
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ucs.identity import create
from ucs.receiver import run
from ucs.synthetic import send,connect
from ucs.protocol import *

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--decoder',choices=['cpu','d3d11va'],default='cpu')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]/'output'/('smoke-'+str(time.time_ns()))
    root.mkdir(parents=True)
    identity=root/'identity';create(identity)
    fixture=root/'fixture.h264'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i',
        'testsrc2=size=1920x1080:rate=30','-frames:v','90','-c:v','libx264','-preset','ultrafast',
        '-tune','zerolatency','-pix_fmt','yuv420p','-colorspace','bt709','-color_primaries','bt709',
        '-color_trc','bt709','-x264-params','aud=1:keyint=30:repeat-headers=1',str(fixture)],check=True)
    reference=root/'reference.framemd5'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-i',str(fixture),
                    '-f','framemd5',str(reference)],check=True)
    port_queue=queue.Queue();results=[];failures=[]
    def server():
        try: results.extend(run('127.0.0.1',0,identity,root/'sessions',max_sessions=2,ready=port_queue.put,decoder=args.decoder))
        except Exception as exc: failures.append(repr(exc))
    worker=threading.Thread(target=server,daemon=True);worker.start();port=port_queue.get(timeout=10)
    pin=(identity/'fingerprint.txt').read_text()
    # A wrong pin and bad auth must not kill the listener or create a media session.
    try: connect('127.0.0.1',port,'0'*64)
    except ProtocolError: pass
    else: raise AssertionError('wrong pin accepted')
    with connect('127.0.0.1',port,pin) as sock:
        # Invalid-length random fixture, never a persisted credential.
        sock.sendall(encode(json_message(HELLO,{'token':secrets.token_hex(16)})))
        try: receive(sock)
        except (EOFError,OSError): pass
        else: raise AssertionError('bad auth accepted')
    sent=[send(fixture,'127.0.0.1',port,identity) for _ in range(2)]
    worker.join(timeout=20)
    assert not worker.is_alive() and not failures,failures
    def hashes(path):
        return [line.rsplit(',',1)[-1].strip() for line in path.read_text().splitlines() if line and not line.startswith('#')]
    ref=hashes(reference)
    assert len(ref)==90
    assert len(results)==2,results
    for report in results:
        assert report['status']=='stopped' and report['decoded_frames']==90 and report['sequence_gaps']==0,report
    for decoded in (root/'sessions').glob('*/decoded.framemd5'):
        assert hashes(decoded)==ref,'decoded image mismatch'
    summary={'status':'pass','scope':'synthetic 1080p30 H.264, loopback TLS, decoder='+args.decoder,
             'sessions':results,'senders':sent,'decoded_hashes_equal':True,
             'iphone_tested':False,'virtual_camera_tested':False,
             'security_checks':['certificate pin rejection','token rejection','listener survives rejection'],
             'command':'python tools/smoke.py'}
    (root/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print('PASS:',root/'summary.json')

if __name__=='__main__': main()
