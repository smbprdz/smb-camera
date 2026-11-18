import hashlib,unittest
from tools.prepare_frame_bridge import derive

class FrameBridgeDerivationTests(unittest.TestCase):
    def source(self):
        return b'''#include "pch.h"
        const uint32_t NUM_MEDIATYPES = 2;
        // replaced media type initialization
        RETURN_IF_FAILED(MFCreateAttributes(&m_spAttributes, 10));
        sample->SetSampleTime(MFGetSystemTime());
        sample->SetSampleDuration(333333);
'''
    def lock(self,data):
        digest=hashlib.sha256(data).hexdigest()
        return {'path':'SimpleMediaStream.cpp','sha256':digest,'normalized_lf_sha256':digest}
    def test_only_verified_source_is_derived_and_unrelated_clock_and_tail_are_preserved(self):
        data=self.source();row=self.lock(data);result=derive(data,row)
        self.assertIn(b'bridgeConfig.mode.formats',result)
        self.assertIn(b'FrameDuration()',result)
        self.assertIn(b'SetSampleTime(MFGetSystemTime())',result)
        self.assertEqual(data,self.source())
        self.assertEqual(result,derive(data.replace(b'\n',b'\r\n'),row))
        with self.assertRaises(ValueError):derive(data+b'// unreviewed change',row)
    def test_missing_or_duplicated_anchors_fail_closed_even_when_input_hash_is_updated(self):
        for bad in (self.source().replace(b'333333',b'400000'),self.source()+self.source()):
            with self.assertRaises(ValueError):derive(bad,self.lock(bad))
