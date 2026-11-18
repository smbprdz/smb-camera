"""Private local binary pipe worker. Small tensors/masks only; no network/files of video."""
import argparse,contextlib,json,struct,sys,os
from pathlib import Path

def exact(stream,n):
    result=bytearray()
    while len(result)<n:
        data=stream.read(n-len(result))
        if not data:raise EOFError('matting pipe closed')
        result.extend(data)
    return bytes(result)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--backend',choices=['cuda','directml','nvidia'],required=True)
    parser.add_argument('--quality',choices=['quality','performance'],default='quality');args=parser.parse_args()
    incoming=sys.stdin.buffer;outgoing=os.fdopen(os.dup(sys.stdout.fileno()),'wb',buffering=0)
    # Keep native SDK/TensorRT output off the binary protocol, including C stdout.
    os.dup2(sys.stderr.fileno(),sys.stdout.fileno())
    import numpy as np
    from .matting import PortraitModel
    with contextlib.redirect_stdout(sys.stderr):
        if args.backend=='nvidia':
            from .nvidia_vfx import NvidiaMatte
            model=NvidiaMatte(2 if args.quality=='quality' else 3)
        else:model=PortraitModel(args.backend)
    outgoing.write(b'READ');outgoing.flush()
    while True:
        try:
            size=struct.unpack('!I',exact(incoming,4))[0]
            if size==0:
                if hasattr(model,'reset'):model.reset()
                outgoing.write(b'RSET');outgoing.flush();continue
            if args.backend=='nvidia':
                if size!=512*288*3:raise ValueError('invalid NVIDIA input size')
                bgr=np.frombuffer(exact(incoming,size),dtype=np.uint8).reshape(288,512,3)
                alpha=model.infer_bgr(bgr).tobytes()
            else:
                if size!=1*3*256*256*4:raise ValueError('invalid matting tensor size')
                tensor=np.frombuffer(exact(incoming,size),dtype=np.float32).reshape(1,3,256,256)
                if not np.isfinite(tensor).all():raise ValueError('nonfinite matting tensor')
                output=model.session.run(None,{model.name:tensor})[0]
                if output.shape!=(1,1,256,256) or not np.isfinite(output).all():raise ValueError('invalid matte')
                alpha=np.ascontiguousarray((np.clip(output[0,0],0,1)*255).round().astype(np.uint8)).tobytes()
            outgoing.write(struct.pack('!I',len(alpha))+alpha);outgoing.flush()
        except EOFError:break

if __name__=='__main__':main()
