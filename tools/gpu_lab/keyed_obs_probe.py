"""Generated mutable keyed texture -> own OBS source, bounded and isolated.

No phone, audio, recordings, user OBS profiles, plugin installation or live app
changes. This is not the production control plane; stdin/private fixture file
are used only by the disposable processes of this experiment.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.gpu_lab.interop import Device,Interop,KeyedAccess
from ucs.gl_preview import GLPreview
from ucs.process_job import ProcessJob


def worker(folder,fps):
    renderer=GLPreview(1920,1080,window_width=320,window_height=180,hidden=True)
    device=child=job=None;resources=[]
    report=dict(scope='generated mutable1920x1080 keyed GPU source in isolated official OBS engine',
                requested_fps=fps,passed=False,phone60_validated=False,app_transport_changed=False,
                sender_readback=False,frames_published=0,busy_writer_skips=0,
                resource_epochs=0,personal_media_recorded=False)
    config_path=folder/'generated-resource.json'
    child_log=[]
    try:
        device=Device(renderer.info['renderer'])
        def allocate():
            texture=Interop(renderer,device,1920,1080,keyed=True)
            access=KeyedAccess(texture.texture);resources.append((access,texture))
            config=dict(scope='generated keyed OBS ownership',width=1920,height=1080,
                        handle=texture.handle,epoch=uuid.uuid4().hex)
            temp=config_path.with_suffix('.tmp');temp.write_text(json.dumps(config));temp.replace(config_path)
            report['resource_epochs']+=1
            return access,texture
        access,texture=allocate()
        child=subprocess.Popen([sys.executable,str(Path(__file__).with_name('obs_keyed_receiver.py'))],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        job=ProcessJob(child)
        child.stdin.write(json.dumps(dict(scope='generated keyed OBS ownership',width=1920,height=1080,
                                         config=str(config_path),result_path=str(folder/'obs-result.json'),fps=fps))+'\n');child.stdin.close()
        while True:
            line=child.stdout.readline()
            if not line:raise RuntimeError('OBS process exited before ready')
            child_log.append(line)
            if line.strip()=='KEYED_OBS_READY':break
        begin=time.perf_counter();next_at=begin;swapped=False;index=0
        while time.perf_counter()-begin<6:
            elapsed=time.perf_counter()-begin
            if elapsed>=3.5 and not swapped:
                access,texture=allocate();swapped=True
            if not 1.5<=elapsed<3.0:
                if access.acquire(0):
                    def render(target):
                        target.clear(0,0,0,0)
                        target.clear(.125,.25,.375,.5,viewport=(640,0,640,1080))
                        target.clear((index&255)/255.,((index>>8)&255)/255.,.25,1.,viewport=(1280,0,640,1080))
                    texture.render(render);access.publish(1)
                    report['frames_published']+=1;index+=1
                else:report['busy_writer_skips']+=1
            next_at=max(next_at+1/fps,time.perf_counter())
            time.sleep(max(0,next_at-time.perf_counter()))
        child_log.extend(child.stdout.readlines());child.wait(5)
        result_path=folder/'obs-result.json'
        result=json.loads(result_path.read_text())
        report['obs_result']=result
        report['passed']=result['passed'] and report['resource_epochs']==2 and child.returncode==0
    except Exception as error:
        report['failure']=type(error).__name__+': '+str(error)
    finally:
        if child:
            if child.poll() is None:
                if job:job.terminate()
                child.wait(5)
            child.stdout.close()
        if job:job.close()
        (folder/'obs.log').write_text(''.join(child_log),encoding='utf-8')
        for access,texture in reversed(resources):access.close();texture.close()
        if device:device.close()
        renderer.close()
    (folder/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)
    return 0 if report['passed'] else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fps',type=int,choices=[30,60],default=30)
    parser.add_argument('--worker',type=Path,default=None,help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.worker:return worker(args.worker,args.fps)
    folder=(Path('output/gpu-keyed-obs')/str(time.time_ns())).resolve();folder.mkdir(parents=True)
    with (folder/'worker.log').open('wb') as log:
        child=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--fps',str(args.fps),'--worker',str(folder)],
                               stdout=log,stderr=subprocess.STDOUT)
        job=ProcessJob(child)
        try:
            try:code=child.wait(30)
            except subprocess.TimeoutExpired:
                job.terminate();child.wait(5);code=1
                (folder/'summary.json').write_text(json.dumps({'passed':False,'failure':'bounded worker timeout'})+'\n')
        finally:job.close()
    print(json.dumps({'proof_folder':str(folder),'exit':code}),flush=True)
    if (folder/'summary.json').exists():print((folder/'summary.json').read_text(),flush=True)
    return code


if __name__=='__main__':raise SystemExit(main())
