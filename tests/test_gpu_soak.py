import ctypes as C
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.probe_obs_alpha import VideoData


@unittest.skipUnless(sys.platform == 'win32', 'Windows diagnostic fixture')
class SoakObserverTest(unittest.TestCase):
    def test_repeated_rows_do_not_count_as_new_images(self):
        from tools.gpu_soak import Observer, OUTPUT

        width, height = OUTPUT
        stride = width * 4 + 16
        pixels = (C.c_uint8 * (height * stride))()
        frame = VideoData()
        frame.data[0] = C.cast(pixels, C.POINTER(C.c_uint8))
        frame.linesize[0] = stride
        observer = Observer()
        def observe():
            observer.receive(C.pointer(frame))

        observe()
        middle = (height // 2) * stride
        pixels[middle + 4 * (width // 2) + 3] = 128
        pixels[middle + 4 * (width * 7 // 8) + 3] = 255
        observe()
        observe()
        pixels[middle + 4 * (width * 7 // 8)] = 91
        observe()
        self.assertEqual(observer.snapshot(), dict(samples=4, valid=3, changed=1, blank=1))
        frame.linesize[0] = 1
        observe()
        observer.reset()
        self.assertEqual(observer.errors, 1)
        self.assertEqual(observer.snapshot()['samples'], 0)

    def test_frozen_output_cannot_pass_steady_gate(self):
        from tools.gpu_soak import Observer, steady_state

        observer = Observer()
        usage = dict(private_mib=1, handles=1, cpu_seconds=1)
        with tempfile.TemporaryDirectory() as folder, patch('tools.gpu_soak.resources', return_value=usage), \
                patch('tools.gpu_soak.time.sleep'), patch('tools.gpu_soak.time.monotonic', side_effect=range(0, 60, 10)), \
                patch.object(observer, 'snapshot', side_effect=[
                    dict(samples=300, valid=300, changed=0, blank=0),
                    dict(samples=300, valid=0, changed=0, blank=300),
                    dict(samples=300, valid=0, changed=0, blank=300)]):
            self.assertFalse(steady_state(10, Path(folder), observer, lambda show: None))
