import os,unittest
import test_gpu_colour as baseline
from ucs.gl_preview import GLPreview
from ucs.color import ColorState
from test_color import cube

class OpenGLParityTests(baseline.ColourTests):
    renderer_class=GLPreview
    expected_backend='OpenGL'
    releases_effect_textures=False

@unittest.skipUnless(os.environ.get('UCS_TEST_GPU')=='1','requires local GPU')
class GradingTests(unittest.TestCase):
    def test_padded_yuv_pitch_does_not_shift_or_bleed_the_visible_image(self):
        import av,numpy as np
        for format in ('nv12','yuv420p'):
            frame=av.VideoFrame(66,34,format);frame.color_range=1
            y=np.full((34,frame.planes[0].line_size),235,np.uint8);y[:,:66]=16;frame.planes[0].update(y.tobytes())
            for plane in frame.planes[1:]:plane.update(bytes([128])*plane.buffer_size)
            renderer=GLPreview(66,34,window_width=132,window_height=68,hidden=True)
            try:
                renderer.upload(frame);renderer.draw();rgba=renderer.alpha_pixels()
                self.assertLessEqual(int(rgba[:,:,:3].max()),2)
            finally:renderer.close()
    def test_saturation_temperature_lut_bypass_and_alpha(self):
        import av,numpy as np
        frame=av.VideoFrame(64,64,'yuv420p');frame.color_range=1;frame.colorspace=1
        for plane,value in zip(frame.planes,[63,102,240]):plane.update(bytes([value])*plane.buffer_size)
        renderer=GLPreview(64,64,window_width=64,window_height=64,hidden=True);color=ColorState()
        try:
            renderer.upload(frame);renderer.draw();original=renderer.pixels()[32,32,:3].astype(int)
            color.set(saturation=0);renderer.draw(color=color.get());gray=renderer.pixels()[32,32,:3].astype(int)
            self.assertLessEqual(int(gray.max()-gray.min()),2)
            color.enable(False);renderer.draw(color=color.get());np.testing.assert_allclose(renderer.pixels()[32,32,:3],original,atol=2)
            color.reset();color.set_lut(cube(True));renderer.draw(color=color.get())
            np.testing.assert_allclose(renderer.pixels()[32,32,:3],[0,255,0],atol=4)
            alpha=np.full((64,64),128,np.uint8);renderer.draw(alpha=alpha,color=color.get(),background={'mode':'transparent'})
            rgba=renderer.alpha_pixels()[32,32].astype(int)
            np.testing.assert_allclose(rgba,[0,128,0,128],atol=4)
        finally:renderer.close()
    def test_exposure_is_applied_in_linear_light(self):
        import av,numpy as np
        frame=av.VideoFrame(64,64,'nv12');frame.color_range=1
        frame.planes[0].update(bytes([100])*frame.planes[0].buffer_size);frame.planes[1].update(bytes([128])*frame.planes[1].buffer_size)
        renderer=GLPreview(64,64,window_width=64,window_height=64,hidden=True);color=ColorState();color.set(exposure=1)
        try:
            renderer.upload(frame);renderer.draw(color=color.get())
            value=(100-16)/219;linear=((value+.055)/1.055)**2.4
            expected=(1.055*(linear*2)**(1/2.4)-.055)*255
            self.assertLessEqual(abs(int(renderer.pixels()[32,32,0])-expected),3)
        finally:renderer.close()
