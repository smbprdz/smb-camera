"""Public Win64 SDK ABI and bounds, without creating a GPU device."""
import ctypes as C
import os
import unittest
from tools.gpu_lab.interop import AdapterDesc,Device,GUID,LUID,Mapped,TextureDesc,guid


@unittest.skipUnless(os.name=='nt' and C.sizeof(C.c_void_p)==8,'Windows x64 SDK ABI')
class GPUInteropLabContractTests(unittest.TestCase):
    def test_public_d3d11_dxgi_structs_have_sdk_sizes_and_pointer_alignment(self):
        self.assertEqual(C.sizeof(GUID),16)
        self.assertEqual(C.sizeof(LUID),8)
        self.assertEqual(C.sizeof(TextureDesc),44)
        self.assertEqual(TextureDesc.misc.offset,40)
        self.assertEqual(C.sizeof(Mapped),16)
        self.assertEqual(Mapped.row_pitch.offset,8)
        self.assertEqual(C.sizeof(AdapterDesc),312)
        self.assertEqual(AdapterDesc.luid.offset,296)
        value=guid('770aae78-f26f-4dba-a829-253c83d1b387')
        self.assertEqual((value.a,value.b,value.c),(0x770aae78,0xf26f,0x4dba))

    def test_invalid_sizes_are_rejected_before_entering_the_driver(self):
        device=Device.__new__(Device)
        for width,height in ((True,4),(0,4),(4,-1),(16384,16384),(4.5,4)):
            with self.assertRaises(ValueError):device.texture(width,height)
        with self.assertRaises(ValueError):device.texture(64,36,staging=1)

    def test_invalid_shared_handles_are_rejected_before_com_dispatch(self):
        device=Device.__new__(Device)
        for handle in (None,True,0,-1,2**32,'123'):
            with self.assertRaises(ValueError):device.open(handle)
