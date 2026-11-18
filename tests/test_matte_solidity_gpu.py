import os
import unittest
from ucs.gl_preview import GLPreview


@unittest.skipUnless(os.environ.get('UCS_TEST_GPU')=='1','requires local GPU')
class SolidityShaderTests(unittest.TestCase):
    def test_boost_preserves_zero_alpha_color_premultiplication_and_opaque_original(self):
        import av
        import numpy as np
        frame=av.VideoFrame(64,64,'yuv420p');frame.color_range=1;frame.colorspace=1
        for plane,value in zip(frame.planes,(110,100,150)):plane.update(bytes([value])*plane.buffer_size)
        mask=np.tile(np.linspace(0,255,64).round().astype(np.uint8),(64,1))
        renderer=GLPreview(64,64,window_width=64,window_height=64,hidden=True)
        try:
            renderer.upload(frame);renderer.draw();original=renderer.alpha_pixels()
            previous=None
            for strength in (0,25,50,100):
                renderer.draw(alpha=mask,background={'mode':'transparent','solidity':strength})
                actual=renderer.alpha_pixels()
                expected=np.minimum(mask.astype(float)/(1-.0075*strength),255)
                np.testing.assert_allclose(actual[:,:,3],expected,atol=1)
                np.testing.assert_allclose(actual[:,:,:3],original[:,:,:3].astype(float)*actual[:,:,3:4]/255.,atol=2)
                self.assertTrue((actual[:,:,3][:,0]==0).all())
                self.assertTrue((actual[:,:,3][:,-1]==255).all())
                self.assertTrue((actual[:,:,:3]<=actual[:,:,3:4]).all())
                if previous is not None:self.assertTrue((actual[:,:,3]>=previous).all())
                previous=actual[:,:,3].copy()
                # Both preview and every exporter consume this same treated
                # foreground; no second inference/pixel pass is introduced.
                w,h,data=renderer.capture_output(3)
                output=np.frombuffer(data,np.uint8).reshape(h,w,4)
                np.testing.assert_allclose(output[h//2,:,3],expected[32],atol=1)
            renderer.draw(background={'mode':'off','solidity':100})
            np.testing.assert_array_equal(renderer.alpha_pixels(),original)
            with self.assertRaises(ValueError):renderer.draw(background={'mode':'transparent','solidity':float('nan')})
        finally:renderer.close()
