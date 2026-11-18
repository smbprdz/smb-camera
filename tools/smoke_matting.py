"""Bounded asynchronous GPU matting test. Public still with simulated translation.

No camera or network access. Reports throughput/lifecycle, not temporal quality.
"""
import argparse,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import av,numpy as np,psutil
from PIL import Image
from ucs.matting import BackgroundState,MatteWorker

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--backend',choices=['cuda','directml','nvidia'],required=True)
    parser.add_argument('--input',required=True);parser.add_argument('--out',required=True)
    parser.add_argument('--renderer',choices=['sdl','gl'],default='sdl')
    parser.add_argument('--composite',action='store_true');args=parser.parse_args()
    # Construct a bounded public fixture set once, outside the measured run.
    frames=[]
    with Image.open(args.input) as image:
        image=image.convert('RGB');image.thumbnail((1280,720))
        for x in (0,40,80,40):
            canvas=Image.new('RGB',(1920,1080),(30,70,110));canvas.paste(image,(400+x,200))
            frame=av.VideoFrame.from_ndarray(np.array(canvas),format='rgb24').reformat(format='nv12')
            frame.color_range=1;frame.colorspace=1;frames.append(frame)
    renderer=None
    if args.composite:
        if args.renderer=='gl':
            from ucs.gl_preview import GLPreview
            renderer=GLPreview(1920,1080,hidden=True)
        else:
            from ucs.sdl_preview import SDLPreview
            renderer=SDLPreview(1920,1080,hidden=True)
    process=psutil.Process();state=BackgroundState();worker=MatteWorker(state,args.backend)
    initial=process.memory_info().rss;state.set(mode='transparent');start=time.perf_counter()
    cpu=sum(process.cpu_times()[:2]);seen=[];ages=[];pids=set();child_rss=0;child_times={};mask_ranges=[]
    ready_at=None;sent=0;next_frame=start;next_sample=start
    try:
        while time.perf_counter()-start<10:
            now=time.perf_counter()
            if now>=next_frame:
                worker.submit((frames[sent%4],sent,now),state.get()['generation']);sent+=1;next_frame+=1/30
            result=worker.take()
            if result is not None:
                frame,seq,arrival,alpha,generation=result
                assert frame is frames[seq%4] and generation==state.get()['generation']
                if renderer:
                    renderer.upload(frame);renderer.draw(alpha=alpha,background=state.get());renderer.present();renderer.poll()
                if ready_at is None:ready_at=now
                seen.append(seq);ages.append((time.perf_counter()-arrival)*1000)
                mask_ranges.append([int(alpha.min()),int(alpha.max())])
            if now>=next_sample:
                rss=0
                for child in process.children(recursive=True):
                    try:
                        pids.add(child.pid);rss+=child.memory_info().rss
                        child_times[child.pid]=sum(child.cpu_times()[:2])
                    except psutil.NoSuchProcess:pass
                child_rss=max(child_rss,rss)
                next_sample=now+.2
            time.sleep(.003)
        snapshot=worker.snapshot();state.set(mode='off');worker.cancel()
        disabled=time.perf_counter()
        while any(psutil.pid_exists(pid) for pid in pids) and time.perf_counter()-disabled<3:time.sleep(.02)
        released=all(not psutil.pid_exists(pid) for pid in pids)
        off_ms=(time.perf_counter()-disabled)*1000
    finally:
        closed=worker.close()
        if renderer:renderer.close()
    elapsed=time.perf_counter()-start
    result={'backend':args.backend,'sent':sent,'matte_results':len(seen),'worker':snapshot,
        'ready_after_ms':(ready_at-start)*1000 if ready_at else None,
        'warm_output_fps':(len(seen)-1)/(now-ready_at) if ready_at and now>ready_at else None,
        'receive_to_matte_p95_ms':float(np.percentile(ages,95)) if ages else None,
        'parent_rss_before_mib':initial/1048576,'parent_rss_after_mib':process.memory_info().rss/1048576,
        'child_peak_rss_mib':child_rss/1048576,'child_exit_on_disable':released,'disable_ms':off_ms,
        'all_masks_have_foreground_and_background':bool(mask_ranges) and all(lo<20 and hi>200 for lo,hi in mask_ranges),
        'cpu_machine_percent_parent_and_child':100*(sum(process.cpu_times()[:2])-cpu+sum(child_times.values()))/elapsed/psutil.cpu_count(),
        'closed':closed,'gpu_compositor':args.composite,'renderer':args.renderer,
        'scope':'public still translated in synthetic 1080p30 feed; no decode/USB/game/OBS, not real motion quality'}
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)
    if not seen or not released or not closed:raise SystemExit(1)

if __name__=='__main__':main()
