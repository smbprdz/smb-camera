import json
import unittest
from tools.probe_live_obs_alpha import FrameSummary,validate_endpoint


class LiveObservationTests(unittest.TestCase):
    def endpoint(self):
        return dict(schema=1,alpha_mode='premultiplied',width=1920,height=1080,
                    canvas=[1920,1080],formats=[3],producer_pid=123,
                    pipe_name='\\\\.\\pipe\\UCS.FrameBridge.00000000-0000-0000-0000-000000000000',
                    epoch_hex='fffffffffedcba98',owner_sid='S-1-5-21-1-2-3-1001')

    def test_only_local_bounded_alpha_endpoints_are_observed(self):
        value=self.endpoint();self.assertEqual(validate_endpoint(value),(1920,1080))
        for change in ({'schema':True},{'pipe_name':'\\\\remote\\pipe\\camera'},
                       {'width':16384,'height':16384,'canvas':[16384,16384]},
                       {'formats':[2]},{'epoch_hex':'0000000000000000'},
                       {'producer_pid':True},{'canvas':[1080,1920]},{'owner_sid':'bad-owner'}):
            with self.assertRaises(ValueError):validate_endpoint(dict(value,**change))

    def test_numeric_report_never_serializes_pixels_or_image_hashes(self):
        stats=FrameSummary()
        first=bytes([0,0,0,0,10,20,30,128,40,50,60,255])
        second=bytes([0,0,0,0,11,21,31,128,41,51,61,255])
        stats.observe(first,1.);stats.observe(first,1.1);stats.observe(second,1.2)
        report=stats.report()
        self.assertEqual(report['output_samples'],3)
        self.assertEqual(report['samples_with_content'],3)
        self.assertEqual(report['distinct_observed_rows'],2)
        self.assertEqual(report['changed_rows'],1)
        self.assertEqual((report['alpha_min'],report['alpha_max']),(0,255))
        self.assertEqual(report['samples_with_partial_alpha'],3)
        self.assertTrue(all(isinstance(x,(int,float)) or x is None for x in report.values()))
        text=json.dumps(report)
        self.assertNotIn(first.hex(),text)
        for digest in stats._hashes:self.assertNotIn(digest.hex(),text)

    def test_gpu_endpoint_requires_explicit_protocol_and_single_reader(self):
        value=dict(self.endpoint(),schema=2,transport='d3d11-keyed-v1',formats=[4],max_readers=1)
        self.assertEqual(validate_endpoint(value),(1920,1080))
        for change in ({'transport':'unknown'},{'formats':[3]},{'max_readers':4}):
            with self.assertRaises(ValueError):validate_endpoint(dict(value,**change))

    def test_blank_or_static_output_is_not_mislabeled_as_new_camera_images(self):
        stats=FrameSummary()
        for i in range(120):stats.observe(bytes(16),1+i/30)
        report=stats.report()
        self.assertEqual(report['output_samples'],120)
        self.assertEqual(report['samples_with_content'],0)
        self.assertEqual(report['distinct_observed_rows'],1)
        self.assertEqual(report['changed_rows'],0)
