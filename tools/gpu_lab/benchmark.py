"""Fixed B_test: generated 1080p/4K, different source/mask, ABBA export comparison.

Receiver readbacks are validator-only and excluded equally from sender timings.
This is a sender-stage result, not an end-to-end or gameplay benchmark.
"""
from pathlib import Path
import argparse
import hashlib,json,os,statistics,subprocess,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import av
import numpy as np
from interop import Device,Interop
from dev import draw_export
from ucs.gl_preview import GLPreview
from ucs.color import ColorState


def p95(values):return sorted(values)[int((len(values)-1)*.95)]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',type=int,choices=range(8),required=True);args=parser.parse_args()
    rows=[];report={'scope':'generated B_test sender export stage, not full engine/gameplay',
        'passed':False,'personal_media_recorded':False,'frames_per_phase':120,
        'readback_in_gpu_sender_hot_path':False,'receiver_readback':'validation only, equal for both routes',
        'live_or_obs_runtime_modified':False}
    for size_index,(width,height) in enumerate(((1920,1080),(3840,2160))):
        if size_index!=args.phase//4:continue
        r=GLPreview(width,height,window_width=320,window_height=180,hidden=True)
        sender=shared=child=None
        try:
            frame=av.VideoFrame(width,height,'nv12');frame.color_range=1;frame.colorspace=1
            # Fixed holdout pattern unlike B_dev quadrants.
            for plane,value in zip(frame.planes,(108,134)):plane.update(bytes([value])*plane.buffer_size)
            yy,xx=np.mgrid[:288,:512]
            mask=((xx*3+yy*5)%256).astype(np.uint8)
            r.upload(frame);color=ColorState()
            sender=Device(r.info['renderer']);shared=Interop(r,sender,width,height)
            child=subprocess.Popen([sys.executable,str(Path(__file__).with_name('receiver.py'))],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                creationflags=subprocess.CREATE_NO_WINDOW)
            config={'renderer':r.info['renderer'],'luid':sender.info['luid'],'handle':shared.handle,'width':width,'height':height}
            child.stdin.write(json.dumps(config)+'\n');child.stdin.flush()
            if json.loads(child.stdout.readline()).get('state')!='ready':raise RuntimeError('Receiver did not become ready')
            for phase_index,kind in enumerate(('ram','gpu','gpu','ram')):
                if phase_index!=args.phase%4:continue
                times=[];cpu=[];begin=time.perf_counter();next_at=begin
                for index in range(128):
                    color.set(exposure=(index%7)*.08)
                    r.draw(angle=180 if index%2 else 0,mirror=bool(index%3),alpha=mask,
                        background={'mode':'transparent'},color=color.get(),preview=False)
                    # Validator reference computed outside the candidate timed region.
                    _,_,reference=r.capture_output(3);expected=hashlib.sha256(reference).hexdigest()
                    before=time.perf_counter();cpu_before=time.thread_time();reads=r.output_reads
                    if kind=='ram':
                        _,_,data=r.capture_output(3)
                    else:
                        shared.render(lambda target:draw_export(r,target))
                        if r.output_reads!=reads:raise RuntimeError('GPU sender read back pixels')
                    submitted=time.perf_counter();used=time.thread_time()-cpu_before
                    if kind=='ram':
                        if data!=reference:raise RuntimeError('RAM reference changed')
                        # The two paths validate the exact same render surface.
                        shared.render(lambda target:draw_export(r,target))
                    child.stdin.write(json.dumps({'frame':index})+'\n');child.stdin.flush()
                    result=json.loads(child.stdout.readline())
                    if result.get('frame')!=index or result.get('sha256')!=expected:raise RuntimeError('Holdout shared pixels mismatch')
                    if index>=8:
                        times.append((submitted-before)*1000);cpu.append(used*1000)
                    next_at=max(next_at+1/30,time.perf_counter());time.sleep(max(0,next_at-time.perf_counter()))
                rows.append({'canvas':[width,height],'route':kind,'frames':len(times),
                    'sender_wall_p95_ms':p95(times),'sender_thread_cpu_p95_ms':p95(cpu),
                    'sender_wall_median_ms':statistics.median(times),'all_pixels_equal':True})
        finally:
            if child:
                if child.poll() is None:
                    child.stdin.write('{"stop":true}\n');child.stdin.flush()
                    try:child.wait(5)
                    except subprocess.TimeoutExpired:child.kill();child.wait(2)
                child.stdin.close();child.stdout.close();child.stderr.close()
            if shared:shared.close()
            if sender:sender.close()
            r.close()
    report.update(rows=rows,phase=args.phase,passed=len(rows)==1 and rows[0]['frames']==120)
    Path(f'output/gpu-lab/test-phase-{args.phase}.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
