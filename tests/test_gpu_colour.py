"""Explicit GPU pixel/readback tests, opt-in on a Windows graphics session."""
import os,unittest
from ucs.sdl_preview import SDLPreview

@unittest.skipUnless(os.environ.get('UCS_TEST_GPU')=='1','requires local Windows D3D11 test session')
class ColourTests(unittest.TestCase):
    renderer_class=SDLPreview
    expected_backend='direct3d11'
    releases_effect_textures=True
    def test_stale_preview_can_be_cleared_and_a_new_frame_can_resume(self):
        import av,numpy as np
        frame=av.VideoFrame(64,64,'yuv420p');frame.color_range=1;frame.colorspace=1
        for plane,value in zip(frame.planes,[63,102,240]):plane.update(bytes([value])*plane.buffer_size)
        renderer=self.renderer_class(64,64,window_width=64,window_height=64,hidden=True)
        try:
            renderer.upload(frame);renderer.draw();original=renderer.pixels()[32,32,:3].astype(int)
            self.assertGreater(int(original[0]),245)
            renderer.clear();self.assertLessEqual(int(renderer.pixels()[:,:,:3].max()),2)
            renderer.upload(frame);renderer.draw()
            np.testing.assert_allclose(renderer.pixels()[32,32,:3],original,atol=2)
        finally:renderer.close()

    def test_alpha_is_real_premultiplied_rgba_and_image_background_blends(self):
        import av,numpy as np,tempfile
        from pathlib import Path
        from PIL import Image
        frame=av.VideoFrame(64,64,'yuv420p');frame.color_range=1;frame.colorspace=1
        for plane,value in zip(frame.planes,[63,102,240]):plane.update(bytes([value])*plane.buffer_size)
        alpha=np.empty((64,64),np.uint8);alpha[:,:32]=0;alpha[:,32:]=128
        renderer=self.renderer_class(64,64,window_width=64,window_height=64,hidden=True)
        try:
            renderer.upload(frame)
            renderer.draw(alpha=alpha,background={'mode':'transparent','image':None})
            rgba=renderer.alpha_pixels()
            self.assertLessEqual(int(rgba[32,16].max()),2)
            self.assertLessEqual(abs(int(rgba[32,48,3])-128),2)
            self.assertLessEqual(abs(int(rgba[32,48,0])-128),4)
            self.assertLessEqual(int(rgba[32,48,1:3].max()),4)
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)/'background.png';Image.new('RGB',(64,64),(0,0,255)).save(p)
                renderer.draw(alpha=alpha,background={'mode':'image','image':str(p)})
                pixels=renderer.pixels()
                self.assertLessEqual(np.max(np.abs(pixels[32,16,:3].astype(int)-[0,0,255])),4)
                self.assertLessEqual(np.max(np.abs(pixels[32,48,:3].astype(int)-[128,0,127])),5)
            renderer.draw(background={'mode':'off'})
            if self.releases_effect_textures:
                self.assertIsNone(renderer.foreground_texture);self.assertIsNone(renderer.mask_texture)
                self.assertIsNone(renderer.background_texture)
        finally:renderer.close()

    def test_rotation_and_mirror_preserve_quadrants(self):
        import av,numpy as np
        colors=[((63,102,240),(255,0,0)),((173,42,26),(0,255,0)),
                ((32,240,118),(0,0,255)),((235,128,128),(255,255,255))]
        frame=av.VideoFrame(64,32,'yuv420p');frame.color_range=1;frame.colorspace=1
        for p_index,plane in enumerate(frame.planes):
            w,h=(64,32) if p_index==0 else (32,16)
            data=np.zeros((h,plane.line_size),dtype=np.uint8)
            for index,(yuv,_) in enumerate(colors):
                row,col=divmod(index,2);data[row*h//2:(row+1)*h//2,col*w//2:(col+1)*w//2]=yuv[p_index]
            plane.update(data.tobytes())
        reference=np.array([x[1] for x in colors]).reshape(2,2,3)
        renderer=self.renderer_class(64,32,window_width=96,window_height=96,hidden=True)
        try:
            renderer.upload(frame)
            for angle in (0,90,180,270):
                for mirror in (False,True):
                    output_format='portrait' if angle in (90,270) else 'landscape'
                    renderer.draw(angle,mirror,output_format);pixels=renderer.pixels()
                    expected=np.rot90(reference[:,::-1] if mirror else reference,-angle//90)
                    from ucs.view_transform import crop_geometry
                    w,h=crop_geometry(64,32,angle,output_format)['canvas']
                    scale=min(pixels.shape[1]/w,pixels.shape[0]/h)
                    left=(pixels.shape[1]-w*scale)/2;top=(pixels.shape[0]-h*scale)/2
                    for row in range(2):
                        for col in range(2):
                            x=int(left+(col+.5)*w*scale/2);y=int(top+(row+.5)*h*scale/2)
                            self.assertLessEqual(np.max(np.abs(pixels[y,x,:3].astype(int)-expected[row,col])),4,
                                (angle,mirror,row,col,pixels[y,x,:3],expected[row,col],pixels.shape))
        finally:renderer.close()

    def test_bt709_limited_range_nv12_and_planar_pixel_colours(self):
        import av,numpy as np
        patches=[((16,128,128),(0,0,0)),((235,128,128),(255,255,255)),
                 ((63,102,240),(255,0,0)),((173,42,26),(0,255,0)),((32,240,118),(0,0,255))]
        for format in ('nv12','yuv420p'):
            renderer=self.renderer_class(64,64,window_width=64,window_height=64,hidden=True)
            try:
                self.assertEqual(renderer.info['name'],self.expected_backend);self.assertTrue(renderer.info['accelerated'])
                for (y,u,v),rgb in patches:
                    frame=av.VideoFrame(64,64,format);frame.color_range=1;frame.colorspace=1
                    frame.planes[0].update(bytes([y])*frame.planes[0].buffer_size)
                    if format=='nv12':frame.planes[1].update(bytes([u,v])*(frame.planes[1].buffer_size//2))
                    else:
                        frame.planes[1].update(bytes([u])*frame.planes[1].buffer_size)
                        frame.planes[2].update(bytes([v])*frame.planes[2].buffer_size)
                    renderer.upload(frame);renderer.draw();pixels=renderer.pixels()
                    actual=pixels[pixels.shape[0]//2,pixels.shape[1]//2,:3].astype(int)
                    self.assertLessEqual(np.max(np.abs(actual-np.array(rgb))),4,(format,rgb,actual))
            finally:renderer.close()

if __name__=='__main__':unittest.main()
