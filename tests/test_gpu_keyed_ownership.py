"""Exact Windows keyed-mutex statuses and ownership transitions, no driver."""
import ctypes as C
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.gpu_lab.interop import KeyedAccess,AbandonedTexture,mutex_status,Device,TextureDesc,SHARED_KEYEDMUTEX


class KeyedOwnershipTests(unittest.TestCase):
    def access(self):
        value=KeyedAccess.__new__(KeyedAccess)
        value.pointer=C.c_void_p(1);value.held=False
        return value

    def test_positive_wait_statuses_are_never_treated_as_success(self):
        self.assertTrue(mutex_status(0))
        self.assertFalse(mutex_status(258))
        with self.assertRaises(AbandonedTexture):mutex_status(128)
        for code in (1,-1,-2147467259):
            with self.assertRaises(RuntimeError):mutex_status(code)

    def test_busy_or_abandoned_resource_never_grants_ownership(self):
        value=self.access()
        with patch('tools.gpu_lab.interop.method',return_value=lambda *args:258):
            self.assertFalse(value.acquire(0));self.assertFalse(value.held)
        with patch('tools.gpu_lab.interop.method',return_value=lambda *args:128):
            with self.assertRaises(AbandonedTexture):value.acquire(0)
            self.assertFalse(value.held)

    def test_only_owner_can_publish_and_unbounded_or_recursive_acquire_is_refused(self):
        value=self.access()
        with self.assertRaises(RuntimeError):value.publish(1)
        for key,timeout in ((True,0),(-1,0),(2**64,0),(0,51),(0,-1),(0,True)):
            with self.assertRaises(ValueError):value.acquire(key,timeout)
        with patch('tools.gpu_lab.interop.method',return_value=lambda *args:0):
            self.assertTrue(value.acquire(0))
            with self.assertRaises(RuntimeError):value.acquire(0)
            value.publish(1);self.assertFalse(value.held)
            with self.assertRaises(RuntimeError):value.publish(0)

    def test_sdk_keyed_texture_flag_is_used_without_legacy_shared_or_indirect_flags(self):
        device=Device.__new__(Device);device.device=C.c_void_p(1);seen=[]
        def create(pointer,description,data,result):
            desc=C.cast(description,C.POINTER(TextureDesc)).contents
            seen.append((desc.misc,desc.bind,desc.usage))
            C.cast(result,C.POINTER(C.c_void_p))[0]=C.c_void_p(2)
            return 0
        with patch('tools.gpu_lab.interop.method',return_value=create):
            device.texture(64,36,keyed=True)
        self.assertEqual(SHARED_KEYEDMUTEX,0x100)
        self.assertEqual(seen,[(0x100,0x28,0)])
        with self.assertRaises(ValueError):device.texture(64,36,staging=True,keyed=True)

    @unittest.skipUnless(os.name=='nt' and Path('C:/Program Files/obs-studio/bin/64bit/lua51.dll').is_file(),'existing OBS LuaJIT')
    def test_obs_wrapper_errno_contract_is_distinct_from_direct_dxgi_hresult(self):
        import json
        from test_obs_alpha_transport import Lua
        runtime=Lua()
        try:
            path=(Path(__file__).resolve().parents[1]/'tools/gpu_lab/obs_sync_status.lua').as_posix()
            runtime.run('local s=dofile('+json.dumps(path)+'); '
                        'assert(s.classify(0)=="acquired"); '
                        'assert(s.classify(138)=="busy"); '
                        'assert(s.classify(258)=="failed"); '
                        'assert(s.classify(128)=="failed"); '
                        'assert(s.classify(-1)=="failed")')
        finally:runtime.close()
