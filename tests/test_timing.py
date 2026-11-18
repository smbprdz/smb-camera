import math,struct,unittest
from ucs.timing import phone_metrics,receive_age,pong_timestamps
from ucs.protocol import ProtocolError

class TimingTests(unittest.TestCase):
    def test_reply_and_age_with_bounded_uncertainty(self):
        self.assertEqual(struct.unpack('!QQ',pong_timestamps(100,120)),(100,120))
        metrics=phone_metrics({'clock_offset_us':10000,'clock_uncertainty_us':500,'encoder_p95_ms':12})
        self.assertEqual(receive_age(120000,100000,metrics),
            {'capture_to_receive_estimate_ms':10.0,'clock_uncertainty_ms':0.5})
    def test_untrusted_stats_rejected(self):
        for value in [True,float('inf'),float('nan'),-1,'10']:
            with self.assertRaises(ProtocolError):phone_metrics({'encoder_p95_ms':value})
        self.assertEqual(phone_metrics({'private':'discarded'}),{})
        with self.assertRaises(ProtocolError):pong_timestamps(5,1)
    def test_unknown_and_incompatible_clocks_not_reported_as_latency(self):
        self.assertEqual(receive_age(100,200,{}),{})
        self.assertEqual(receive_age(0,20000,{'clock_offset_us':0,'clock_uncertainty_us':1}),{})
        self.assertEqual(receive_age(100,200,{'clock_offset_us':0,'clock_uncertainty_us':200000}),{})

if __name__=='__main__':unittest.main()
