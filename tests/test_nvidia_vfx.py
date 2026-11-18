"""Opt-in native NVIDIA ABI/state test, no camera and no recorded user media."""
import os,unittest

@unittest.skipUnless(os.environ.get('UCS_TEST_NVIDIA')=='1','requires licensed local NVIDIA VFX runtime and RTX')
class NvidiaTests(unittest.TestCase):
    def test_native_mask_state_reset_and_resource_teardown(self):
        import numpy as np
        from ucs.nvidia_vfx import NvidiaMatte
        model=NvidiaMatte()
        try:
            image=np.zeros((288,512,3),np.uint8)
            first=model.infer_bgr(image)
            self.assertEqual(first.shape,(288,512));self.assertEqual(first.dtype,np.uint8)
            model.reset();second=model.infer_bgr(image)
            self.assertLess(float(first.mean()),5);self.assertLess(float(second.mean()),5)
        finally:model.close()
        self.assertFalse(model.effect.value);self.assertFalse(model.state.value);self.assertFalse(model.images)
