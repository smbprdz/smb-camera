"""Animated background delivery and lifecycle with generated media only."""
import os
from pathlib import Path
import tempfile
import time
import unittest

from PIL import Image

from ucs.background_motion import BackgroundMotion, verify_motion
from ucs.color import ColorState
from ucs.matting import BackgroundState
from ucs.studio_state import snapshot, restore
from ucs.view_transform import ViewTransform


def gif(path, first='red', second='lime'):
    with Image.new('RGB', (32, 32), first) as image, Image.new('RGB', (32, 32), second) as following:
        image.save(path, save_all=True, append_images=[following], duration=[100, 220], loop=0)


class BackgroundMotionTests(unittest.TestCase):
    def test_animation_wraps_and_closes_the_old_file_on_switch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'loop.gif'
            other = Path(directory) / 'other.gif'
            gif(path)
            gif(other, 'blue', 'blue')
            motion = BackgroundMotion()
            try:
                motion.select(str(path))
                seen = []
                until = time.monotonic() + 3
                while time.monotonic() < until and len(seen) < 3:
                    frame, error = motion.snapshot()
                    self.assertFalse(error)
                    if frame is not None:
                        color = frame[2][:3]
                        if not seen or seen[-1] != color:
                            seen.append(color)
                    time.sleep(.006)
                self.assertEqual(seen, [b'\xff\x00\x00', b'\x00\xff\x00', b'\xff\x00\x00'])
                motion.select(str(other))
                until = time.monotonic() + 2
                while time.monotonic() < until:
                    frame, error = motion.snapshot()
                    self.assertFalse(error)
                    if frame is not None:
                        self.assertEqual(frame[2][:3], b'\x00\x00\xff')
                        break
                    time.sleep(.006)
                else:
                    self.fail('The new file did not start')
                path.rename(path.with_name('old.gif'))
                motion.select(None)
                self.assertEqual(motion.snapshot(), (None, ''))
            finally:
                motion.close()
            self.assertFalse(motion.worker.is_alive())
            other.rename(other.with_name('closed.gif'))

    def test_profile_round_trip_and_missing_motion_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'loop.gif'
            gif(path)
            verify_motion(path)
            color, transform, background = ColorState(), ViewTransform(), BackgroundState()
            background.set(mode='motion', image=path)
            saved = snapshot(color, transform, background)
            target = BackgroundState()
            self.assertEqual(restore(saved, color, transform, target), '')
            self.assertEqual(target.get()['mode'], 'motion')
            path.unlink()
            self.assertTrue(restore(saved, color, transform, target))
            self.assertEqual(target.get()['mode'], 'transparent')

    @unittest.skipUnless(os.environ.get('UCS_TEST_GPU') == '1', 'Requires local GPU validation')
    def test_gl_exports_animation_pixels_and_can_return_to_transparent(self):
        import av
        import numpy as np
        from ucs.gl_preview import GLPreview

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'loop.gif'
            gif(path)
            renderer = GLPreview(64, 64, window_width=64, window_height=64, hidden=True)
            try:
                renderer.upload(av.VideoFrame(64, 64, 'yuv420p'))
                mask = np.zeros((64, 64), dtype=np.uint8)
                motion = {'mode': 'motion', 'image': str(path)}
                seen = set()
                until = time.monotonic() + 3
                while time.monotonic() < until and len(seen) < 2:
                    renderer.draw(alpha=mask, background=motion, preview=False)
                    _, _, data = renderer.capture_output(3)
                    if data[3] == 255:
                        seen.add(data[:4])
                    time.sleep(.01)
                self.assertEqual(seen, {bytes((255, 0, 0, 255)), bytes((0, 255, 0, 255))})
                renderer.draw(alpha=mask, background={'mode': 'transparent'}, preview=False)
                self.assertEqual(renderer.capture_output(3)[2][:4], bytes(4))
                self.assertEqual(renderer.motion.snapshot(), (None, ''))
            finally:
                renderer.close()
