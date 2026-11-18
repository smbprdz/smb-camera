"""Disposable generated-texture consumer; one frame at a time, explicit ACK."""
import hashlib,json,sys
from interop import Device,release

device=texture=staging=None
try:
    config=json.loads(sys.stdin.readline())
    device=Device(config['renderer'])
    if device.info['luid']!=config['luid']:raise RuntimeError('Adapter identity mismatch')
    texture=device.open(config['handle']);staging=device.texture(config['width'],config['height'],True)
    print(json.dumps({'state':'ready'}),flush=True)
    for line in sys.stdin:
        row=json.loads(line)
        if row.get('stop'):break
        data=device.read(texture,staging,config['width'],config['height'])
        print(json.dumps({'frame':row['frame'],'sha256':hashlib.sha256(data).hexdigest()}),flush=True)
finally:
    release(staging);release(texture)
    if device:device.close()
