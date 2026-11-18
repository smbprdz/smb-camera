"""Own output pixel contract with generated pixels and masks, no camera."""
import os
import unittest
from ucs.gl_preview import GLPreview
from ucs.color import ColorState


@unittest.skipUnless(os.environ.get('UCS_TEST_GPU') == '1', 'requires local GPU')
class AlphaOutputTests(unittest.TestCase):
    def test_premultiplied_alpha_preserves_color_geometry_and_composites_without_checker(self):
        import av
        import numpy as np
        renderer = GLPreview(64, 64, window_width=64, window_height=64, hidden=True)
        pixels = np.empty((64, 64, 3), np.uint8)
        pixels[:32, :32] = [220, 40, 60]
        pixels[:32, 32:] = [40, 210, 60]
        pixels[32:, :32] = [40, 60, 220]
        pixels[32:, 32:] = [200, 160, 80]
        frame = av.VideoFrame.from_ndarray(pixels, format='rgb24').reformat(format='yuv420p')
        frame.color_range = 1
        frame.colorspace = 1
        mask = np.empty((64, 64), np.uint8)
        mask[:, :20] = 0
        mask[:, 20:44] = 128
        mask[:, 44:] = 255
        color = ColorState()
        color.set(exposure=.3, saturation=90, contrast=12)
        try:
            renderer.upload(frame)
            self.assertIsNone(renderer.output_fbo)
            for angle in (0, 90, 180, 270):
                for mirror in (False, True):
                    for canvas in ('landscape', 'portrait'):
                        view = dict(angle=angle, mirror=mirror, output_format=canvas,
                                    pan_x=.35, pan_y=.65, color=color.get())
                        renderer.draw(**view)
                        w, h, data = renderer.capture_output(3)
                        original = np.frombuffer(data, np.uint8).reshape(h, w, 4).copy()
                        self.assertTrue((original[:, :, 3] == 255).all())
                        renderer.draw(**view, alpha=mask, background={'mode': 'transparent'})
                        w, h, data = renderer.capture_output(3)
                        rgba = np.frombuffer(data, np.uint8).reshape(h, w, 4)
                        _, _, data = renderer.capture_output(2)
                        opaque = np.frombuffer(data, np.uint8).reshape(h, w, 4)
                        np.testing.assert_allclose(rgba[:, :, :3], opaque[:, :, 2::-1], atol=1)
                        self.assertTrue((rgba[:, :, 3] == 0).any())
                        self.assertTrue(((rgba[:, :, 3] > 0) & (rgba[:, :, 3] < 255)).any())
                        self.assertTrue((rgba[:, :, 3] == 255).any())
                        np.testing.assert_array_equal(rgba[rgba[:, :, 3] == 0], 0)
                        alpha = rgba[:, :, 3:4].astype(float) / 255
                        np.testing.assert_allclose(rgba[:, :, :3], original[:, :, :3] * alpha, atol=2)
                        self.assertTrue((rgba[:, :, :3] <= rgba[:, :, 3:4]).all())
                        # Exercise premultiplied composition against a colored
                        # destination, independently of the checkerboard preview.
                        background = np.array([24, 100, 160], float)
                        composed = rgba[:, :, :3] + background * (1 - alpha)
                        reference = original[:, :, :3] * alpha + background * (1 - alpha)
                        np.testing.assert_allclose(composed, reference, atol=2)
            renderer.clear()
            with self.assertRaises(RuntimeError):
                renderer.capture_output(3)
        finally:
            renderer.close()

    def test_alpha_output_retains_full_resolution_and_stays_unallocated_without_demand(self):
        import av
        import numpy as np
        for width, height in ((1920, 1080), (3840, 2160)):
            renderer = GLPreview(width, height, window_width=320, window_height=180, hidden=True)
            try:
                frame = av.VideoFrame(width, height, 'nv12')
                frame.color_range = 1
                frame.colorspace = 1
                for plane, value in zip(frame.planes, (63, 128)):
                    plane.update(bytes([value]) * plane.buffer_size)
                renderer.upload(frame)
                renderer.draw(alpha=np.full((32, 32), 128, np.uint8),
                              background={'mode': 'transparent'}, preview=False)
                self.assertIsNone(renderer.output_fbo)
                self.assertEqual(renderer.output_reads, 0)
                w, h, data = renderer.capture_output(3)
                self.assertEqual((w, h), (width, height))
                self.assertEqual(len(data), width * height * 4)
                self.assertTrue((np.frombuffer(data, np.uint8)[3::4] == 128).all())
            finally:
                renderer.close()
