"""Generated-only keyed GPU resource consumer; no UI/OBS/phone or media files."""
import ctypes as C
import hashlib
import json
import os
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.gpu_lab.interop import Device,KeyedAccess,release


def main():
    config=json.loads(sys.stdin.readline())
    if config.get('scope')!='generated keyed ownership fixture':raise ValueError('Generated fixture required')
    width,height=config['canvas']
    if [width,height] not in ([64,36],[1920,1080]):raise ValueError('Unsupported fixture canvas')
    device=texture=staging=access=None
    try:
        device=Device(config['renderer'])
        if device.info['luid']!=config['luid']:raise ValueError('GPU adapter mismatch')
        texture=device.open(config['handle']);access=KeyedAccess(texture)
        staging=device.texture(width,height,True)
        print(json.dumps({'state':'ready'}),flush=True)
        for line in sys.stdin:
            command=json.loads(line)
            if command.get('stop'):break
            if command.get('epoch')!=config['epoch']:raise ValueError('Resource epoch mismatch')
            deadline=time.monotonic()+.5
            while not access.acquire(1):
                if time.monotonic()>deadline:raise TimeoutError('Producer did not publish ownership')
                time.sleep(.001)
            if command.get('abandon'):
                print(json.dumps({'state':'locked-for-abandonment'}),flush=True)
                os._exit(0)  # intentional process crash, only the generated owner
            # Delay while holding the real resource. The producer must fail to
            # acquire its writer key and must not touch the GL texture.
            print(json.dumps({'state':'locked'}),flush=True)
            if command.get('delay'):
                resume=json.loads(sys.stdin.readline())
                if resume.get('reader_continue') is not True or resume.get('epoch')!=config['epoch']:
                    raise ValueError('Invalid reader continuation')
            try:
                pixels=device.read(texture,staging,width,height)
                digest=hashlib.sha256(pixels).hexdigest()
            finally:
                access.publish(0)
            print(json.dumps({'state':'released','frame':command['frame'],'sha256':digest}),flush=True)
    finally:
        if access:access.close()
        release(staging);release(texture)
        if device:device.close()


if __name__=='__main__':main()
