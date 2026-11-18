import os,tempfile,unittest
from pathlib import Path
from ucs.gl_preview import GLPreview
from ucs.color import ColorState

@unittest.skipUnless(os.environ.get('UCS_TEST_GPU')=='1','requires local GPU')
class NV12OutputTests(unittest.TestCase):
    def verify(self,renderer):
        import numpy as np
        w,h,bgra=renderer.capture_output(2);_,_,nv12=renderer.capture_output(1)
        rgb=np.frombuffer(bgra,np.uint8).reshape(h,w,4)[:,:,2::-1].astype(float)/255
        expected_y=np.rint(16+219*(rgb@np.array([.2126,.7152,.0722])))
        averaged=rgb.reshape(h//2,2,w//2,2,3).mean(axis=(1,3))
        expected_uv=np.rint(128+224*(averaged@np.array([[-.114572,.5],[-.385428,-.454153],[.5,-.045847]])))
        raw=np.frombuffer(nv12,np.uint8)
        self.assertEqual(len(nv12),w*h*3//2)
        np.testing.assert_allclose(raw[:w*h].reshape(h,w),expected_y,atol=1)
        np.testing.assert_allclose(raw[w*h:].reshape(h//2,w//2,2),expected_uv,atol=1)
        self.assertTrue((raw[:w*h]>=16).all() and (raw[:w*h]<=235).all())
        self.assertTrue((raw[w*h:]>=16).all() and (raw[w*h:]<=240).all())
        return raw
    def test_subsampled_output_matches_composed_color_views_and_backgrounds(self):
        import numpy as np
        from PIL import Image
        from test_output_gpu import OutputGPUTests
        renderer=GLPreview(64,64,window_width=64,window_height=64,hidden=True)
        color=ColorState();color.set(exposure=.4,contrast=17,saturation=120,temperature=-8)
        try:
            renderer.upload(OutputGPUTests().frame());mask=np.full((64,64),255,np.uint8);mask[:,:16]=0
            for angle in (0,90,180,270):
                for mirror in (False,True):
                    renderer.draw(angle=angle,mirror=mirror,output_format='portrait' if angle in (90,270) else 'landscape',pan_x=.3,pan_y=-.2,alpha=mask,background={'mode':'transparent'},color=color.get())
                    self.verify(renderer)
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'generated-background.png';Image.new('RGB',(64,64),(20,90,200)).save(path)
                renderer.draw(alpha=mask,background={'mode':'image','image':str(path),'generation':1});self.verify(renderer)
            renderer.draw(alpha=np.zeros((64,64),np.uint8),background={'mode':'transparent'})
            w,h,data=renderer.capture_output(1);self.assertEqual(data,bytes([16])*(w*h)+bytes([128])*(w*h//2))
        finally:renderer.close()
    def test_full_size_export_has_no_readback_when_off_and_rejects_odd_nv12(self):
        import av
        for w,h in ((1920,1080),(3840,2160)):
            frame=av.VideoFrame(w,h,'nv12');frame.color_range=1;frame.colorspace=1
            for plane,value in zip(frame.planes,[63,128]):plane.update(bytes([value])*plane.buffer_size)
            renderer=GLPreview(w,h,window_width=320,window_height=180,hidden=True)
            try:
                renderer.upload(frame);renderer.draw();self.assertIsNone(renderer.output_program);self.assertEqual(renderer.output_reads,0)
                width,height,data=renderer.capture_output(1);self.assertEqual((width,height,len(data)),(w,h,w*h*3//2))
                renderer.last_scene['canvas_size']=(63,64)
                with self.assertRaises(ValueError):renderer.capture_output(1)
            finally:renderer.close()
