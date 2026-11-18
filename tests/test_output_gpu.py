"""Only generated pixels; no phone images or user video artifacts."""
import os,unittest,tempfile
from pathlib import Path
from ucs.gl_preview import GLPreview
from ucs.color import ColorState

@unittest.skipUnless(os.environ.get('UCS_TEST_GPU')=='1','requires local GPU')
class OutputGPUTests(unittest.TestCase):
    def frame(self,width=64,height=64):
        import av,numpy as np
        pixels=np.zeros((height,width,3),np.uint8)
        pixels[:height//2,:width//2]=[240,30,40];pixels[:height//2,width//2:]=[30,220,40]
        pixels[height//2:,:width//2]=[30,40,230];pixels[height//2:,width//2:]=[220,220,210]
        frame=av.VideoFrame.from_ndarray(pixels,format='rgb24').reformat(format='yuv420p');frame.color_range=1;frame.colorspace=1
        return frame
    def test_export_matches_treated_preview_for_all_views_and_never_embeds_window_bars(self):
        import numpy as np
        renderer=GLPreview(64,64,window_width=64,window_height=64,hidden=True);color=ColorState();color.set(exposure=.3,contrast=12,saturation=90)
        try:
            renderer.upload(self.frame())
            self.assertIsNone(renderer.output_program)
            for angle in (0,90,180,270):
                for mirror in (False,True):
                    renderer.draw(angle=angle,mirror=mirror,output_format='portrait' if angle in (90,270) else 'landscape',color=color.get())
                    x,y,w,h=renderer.gl.viewport;screen=renderer.pixels();reference=screen[screen.shape[0]-y-h:screen.shape[0]-y,x:x+w]
                    width,height,data=renderer.capture_output();actual=np.frombuffer(data,np.uint8).reshape(height,width,4)
                    self.assertEqual((width,height),(w,h));self.assertEqual(renderer.gl.viewport,(x,y,w,h))
                    np.testing.assert_allclose(actual[:,:,:3],reference[:,:,2::-1],atol=1)
                    self.assertTrue((actual[:,:,3]==255).all())
                    np.testing.assert_allclose(renderer.pixels(),screen,atol=1)
            renderer.clear()
            with self.assertRaises(RuntimeError):renderer.capture_output()
        finally:renderer.close()
    def test_transparency_checker_is_preview_only_and_image_background_is_exported(self):
        import numpy as np
        from PIL import Image
        renderer=GLPreview(64,64,window_width=64,window_height=64,hidden=True)
        try:
            renderer.upload(self.frame());mask=np.full((64,64),255,np.uint8);mask[:,:32]=0
            renderer.draw(alpha=mask,background={'mode':'transparent'})
            w,h,data=renderer.capture_output();actual=np.frombuffer(data,np.uint8).reshape(h,w,4)
            self.assertEqual(int(actual[h//2,8,:3].max()),0)
            self.assertEqual(int(actual[h//2,8,3]),255)
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'synthetic-blue.png';Image.new('RGB',(64,64),(0,0,255)).save(path)
                renderer.draw(alpha=mask,background={'mode':'image','image':str(path),'generation':1})
                w,h,data=renderer.capture_output();actual=np.frombuffer(data,np.uint8).reshape(h,w,4)
                np.testing.assert_allclose(actual[h//2,8],[255,0,0,255],atol=1)
        finally:renderer.close()
    def test_off_path_allocates_no_export_resources_and_full_resolution_is_preserved(self):
        import av
        for width,height in ((1920,1080),(3840,2160)):
            frame=av.VideoFrame(width,height,'nv12');frame.color_range=1;frame.colorspace=1
            for plane,value in zip(frame.planes,[63,128]):plane.update(bytes([value])*plane.buffer_size)
            renderer=GLPreview(width,height,window_width=320,window_height=180,hidden=True)
            try:
                renderer.upload(frame);renderer.draw()
                self.assertIsNone(renderer.output_fbo);self.assertEqual(renderer.output_reads,0)
                w,h,data=renderer.capture_output();self.assertEqual((w,h),(width,height));self.assertEqual(len(data),width*height*4)
            finally:renderer.close()
    def test_hidden_render_exports_current_color_without_touching_preview_surface(self):
        import numpy as np
        renderer=GLPreview(64,64,window_width=64,window_height=64,hidden=True);color=ColorState()
        try:
            renderer.upload(self.frame());renderer.draw();old=renderer.pixels();_,_,before=renderer.capture_output()
            color.set(exposure=1);renderer.draw(color=color.get(),preview=False);_,_,after=renderer.capture_output()
            self.assertNotEqual(before,after);np.testing.assert_array_equal(renderer.pixels(),old)
            renderer.draw(color=color.get());self.assertFalse(np.array_equal(renderer.pixels(),old))
        finally:renderer.close()
