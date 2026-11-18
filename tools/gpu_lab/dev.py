"""B_dev fixed generated-only interop correctness check."""
from pathlib import Path
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import av
import numpy as np
from interop import Device,Interop,release
from ucs.gl_preview import GLPreview
from ucs.color import ColorState


def draw_export(renderer,target):
    viewport=renderer.gl.viewport
    try:
        target.use();renderer.gl.viewport=(0,0,*renderer.canvas)
        for name,value in renderer.last_scene.items():renderer.output_program[name]=value
        renderer.foreground.use(0);renderer.background.use(1)
        renderer.output_vao.render(vertices=3)
    finally:
        renderer.gl.screen.use();renderer.gl.viewport=viewport


def main():
    width,height=64,36
    pixels=np.empty((height,width,3),np.uint8)
    pixels[:height//2,:width//2]=[220,40,60]
    pixels[:height//2,width//2:]=[40,210,60]
    pixels[height//2:,:width//2]=[40,60,220]
    pixels[height//2:,width//2:]=[200,160,80]
    frame=av.VideoFrame.from_ndarray(pixels,format='rgb24').reformat(format='nv12')
    frame.color_range=1;frame.colorspace=1
    mask=np.full((height,width),128,np.uint8);mask[:,:width//3]=0;mask[:,2*width//3:]=255
    r=GLPreview(width,height,window_width=64,window_height=36,hidden=True)
    sender=receiver=shared=opened=stage=None
    report={'scope':'generated B_dev64x36 across two devices only','passed':False,'frames':0,'personal_media_recorded':False,'obs_or_live_runtime_modified':False}
    try:
        sender=Device(r.info['renderer']);receiver=Device(r.info['renderer'])
        shared=Interop(r,sender,width,height);opened=receiver.open(shared.handle);stage=receiver.texture(width,height,True)
        report['adapter_luid_match']=sender.info['luid']==receiver.info['luid']
        r.upload(frame);color=ColorState()
        for index in range(60):
            color.set(exposure=(index%5)*.1)
            r.draw(angle=180 if index%2 else 0,mirror=bool(index%3),alpha=mask,
                background={'mode':'transparent'},color=color.get(),preview=False)
            _,_,baseline=r.capture_output(3)
            before=r.output_reads
            shared.render(lambda target:draw_export(r,target))
            actual=receiver.read(opened,stage,width,height)
            if actual!=baseline:
                a=np.frombuffer(actual,np.uint8);b=np.frombuffer(baseline,np.uint8)
                report['mismatched_components']=int((a!=b).sum());report['max_difference']=int(np.abs(a.astype(int)-b).max())
                raise RuntimeError('Generated shared texture pixels differ')
            assert r.output_reads==before,'Candidate sender performed a readback'
            report['frames']+=1
        report['passed']=True
    except Exception as error:
        report['error']=str(error)
    finally:
        release(stage);release(opened)
        if shared:shared.close()
        if receiver:receiver.close()
        if sender:sender.close()
        r.close()
    Path('output/gpu-lab/dev-result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
