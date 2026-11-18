"""Bounded own GPU ownership lab, generated data only. Does not change the app.

Different from the previous performance holdout: verifies exclusion, delayed
consumer, explicit abandonment and fresh-resource recovery at requested30/60Hz.
Readback belongs only to the validation process, not the source transport.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.gpu_lab.interop import Device,Interop,KeyedAccess,AbandonedTexture
from ucs.gl_preview import GLPreview
from ucs.process_job import ProcessJob


def worker(folder,width,height,fps,frames):
    renderer=GLPreview(width,height,window_width=320,window_height=180,hidden=True)
    device=texture=writer=child=job=log=None
    report=dict(scope='generated mutable GPU texture ownership, not phone60 or game acceptance',
                canvas=[width,height],requested_fps=fps,passed=False,frames_verified=0,
                delayed_consumer_exclusion_checks=0,wrong_key_refused=False,
                abandoned_resource_detected=False,fresh_epoch_recovery=False,
                sender_frame_readbacks=0,personal_media_recorded=False,
                receiver_validation_readback=True,cadence_validated=False,phone60_validated=False)
    try:
        device=Device(renderer.info['renderer'])
        log=(folder/'receiver.log').open('wb')

        def create_receiver():
            nonlocal texture,writer,child,job
            texture=Interop(renderer,device,width,height,keyed=True)
            writer=KeyedAccess(texture.texture)
            child=subprocess.Popen([sys.executable,str(Path(__file__).with_name('ownership_receiver.py'))],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True)
            job=ProcessJob(child)
            epoch=uuid.uuid4().hex
            config={'scope':'generated keyed ownership fixture','canvas':[width,height],
                    'renderer':renderer.info['renderer'],'luid':device.info['luid'],
                    'handle':texture.handle,'epoch':epoch}
            child.stdin.write(json.dumps(config)+'\n');child.stdin.flush()
            if json.loads(child.stdout.readline()).get('state')!='ready':raise RuntimeError('Receiver not ready')
            return epoch

        def exchange(index,epoch,delay=False):
            if not writer.acquire(0):raise RuntimeError('Writer accessed unpublished ownership')
            # Stable top/half-alpha bands plus changing opaque byte value. GL
            # clear renders directly, no CPU-generated full-frame upload.
            value=32+index%160
            def render(target):
                target.clear(0,0,0,0)
                target.clear(.125,.25,.375,.5,viewport=(width//3,0,width//3,height))
                target.clear(value/255.,.5,.25,1.,viewport=(2*(width//3),0,width-2*(width//3),height))
            texture.render(render)
            writer.publish(1)
            if writer.acquire(0):raise RuntimeError('Writer key granted before consumer released')
            command={'frame':index,'epoch':epoch,'delay':delay}
            child.stdin.write(json.dumps(command)+'\n');child.stdin.flush()
            if json.loads(child.stdout.readline()).get('state')!='locked':raise RuntimeError('Missing reader ownership')
            if delay:
                time.sleep(.025)
                if writer.acquire(0):raise RuntimeError('Concurrent GPU texture access')
                report['delayed_consumer_exclusion_checks']+=1
                child.stdin.write(json.dumps({'reader_continue':True,'epoch':epoch})+'\n');child.stdin.flush()
            reply=json.loads(child.stdout.readline())
            # Reference consists of constant bands generated directly by clear.
            # Validate alpha and changing color without relying on FPS counters.
            opaque=bytes([value,127,64,255])
            half=bytes([32,64,96,127])
            row=bytes(4)*(width//3)+half*(width//3)+opaque*(width-2*(width//3))
            expected=hashlib.sha256(row*height).hexdigest()
            if reply.get('frame')!=index or reply.get('sha256')!=expected:
                raise RuntimeError('Keyed generated frame mismatch')
            report['frames_verified']+=1

        epoch=create_receiver()
        report['wrong_key_refused']=not writer.acquire(1)
        if not report['wrong_key_refused']:raise RuntimeError('Wrong initial key accepted')
        begin=time.perf_counter();next_at=begin
        for index in range(frames):
            exchange(index,epoch,delay=index%20==0)
            next_at=max(next_at+1/fps,time.perf_counter())
            time.sleep(max(0,next_at-time.perf_counter()))
        report['validation_wall_seconds']=time.perf_counter()-begin
        report['verified_frames_per_second_including_validator']=frames/report['validation_wall_seconds']
        # Kill only the generated child while it actually owns the mutex. The
        # resource must not be reused after WAIT_ABANDONED or unexpected failure.
        if not writer.acquire(0):raise RuntimeError('Final writer ownership unavailable')
        texture.render(lambda f:f.clear(0,0,0,0));writer.publish(1)
        child.stdin.write(json.dumps({'epoch':epoch,'frame':frames,'abandon':True})+'\n');child.stdin.flush()
        if json.loads(child.stdout.readline()).get('state')!='locked-for-abandonment':raise RuntimeError('Receiver did not own before crash')
        child.wait(5)
        try:
            acquired=writer.acquire(0)
            if acquired:raise RuntimeError('Abandoned frame silently reused')
        except AbandonedTexture:
            report['abandoned_resource_detected']=True
        if not report['abandoned_resource_detected']:raise RuntimeError('Owner death not detected')
        child.stdin.close();child.stdout.close();child=None;job.close();job=None
        writer.close();writer=None;texture.close();texture=None
        old_epoch=epoch;epoch=create_receiver()
        if epoch==old_epoch:raise RuntimeError('Recovery epoch reused')
        exchange(frames+1,epoch)
        report['fresh_epoch_recovery']=True
        report['passed']=report['frames_verified']==frames+1 and report['delayed_consumer_exclusion_checks']>0
    except Exception as error:
        report['failure']=type(error).__name__+': '+str(error)
    finally:
        if child:
            if child.poll() is None:
                try:
                    child.stdin.write('{"stop":true}\n');child.stdin.flush();child.wait(3)
                except (OSError,subprocess.TimeoutExpired):
                    if job:job.terminate()
                    child.wait(3)
            child.stdin.close();child.stdout.close()
        if job:job.close()
        if log:log.close()
        if writer:writer.close()
        if texture:texture.close()
        if device:device.close()
        renderer.close()
    (folder/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)
    return 0 if report['passed'] else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--size',choices=['small','1080'],default='small')
    parser.add_argument('--fps',type=int,choices=[30,60],default=30)
    parser.add_argument('--frames',type=int,default=60)
    parser.add_argument('--worker',type=Path,default=None,help=argparse.SUPPRESS)
    args=parser.parse_args()
    if not 20<=args.frames<=180:raise ValueError('Bounded fixture count required')
    width,height=(64,36) if args.size=='small' else (1920,1080)
    if args.worker:return worker(args.worker,width,height,args.fps,args.frames)
    folder=(Path('output/gpu-ownership')/str(time.time_ns())).resolve();folder.mkdir(parents=True)
    with (folder/'worker.log').open('wb') as log:
        child=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--size',args.size,
            '--fps',str(args.fps),'--frames',str(args.frames),'--worker',str(folder)],stdout=log,stderr=subprocess.STDOUT)
        job=ProcessJob(child)
        try:
            try:code=child.wait(60 if args.size=='1080' else 20)
            except subprocess.TimeoutExpired:
                job.terminate();child.wait(5);code=1
                (folder/'summary.json').write_text(json.dumps({'passed':False,'failure':'bounded worker timeout'})+'\n')
        finally:job.close()
    print(json.dumps({'proof_folder':str(folder),'exit':code}),flush=True)
    if (folder/'summary.json').exists():print((folder/'summary.json').read_text(),flush=True)
    return code


if __name__=='__main__':raise SystemExit(main())
