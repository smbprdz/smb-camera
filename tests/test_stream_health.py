import unittest
from ucs.stream_health import StreamWindow, PreviewFreshness, connection_view, MAX_SAMPLES
from ucs.protocol import ProtocolError
from ucs.timing import phone_metrics


class StreamHealthTests(unittest.TestCase):
    def test_clock_estimates_are_bounded_recent_and_not_assumed_for_legacy(self):
        window=StreamWindow();window.video(10,9_990_000)
        self.assertIsNone(window.snapshot(10)['capture_to_receive_p95_ms'])
        window.phone_sample({'clock_offset_us':2000,'clock_uncertainty_us':500},10)
        window.video(10.033,10_021_000)
        self.assertEqual(window.snapshot(10.033)['capture_to_receive_p95_ms'],10)
        self.assertEqual(window.snapshot(10.033)['clock_uncertainty_ms'],.5)
        stale=window.snapshot(13.1)
        self.assertIsNone(stale['capture_to_receive_p95_ms'])
        self.assertIsNone(stale['clock_uncertainty_ms'])
        window.phone_sample({'clock_offset_us':2000,'clock_uncertainty_us':150000},14)
        window.video(14,13_998_000)
        self.assertEqual(window.snapshot(14)['capture_to_receive_samples'],0)
        self.assertIsNone(window.snapshot(14)['clock_uncertainty_ms'])

    def test_samples_and_time_window_cannot_grow_with_long_sessions(self):
        window=StreamWindow()
        window.phone_sample({'clock_offset_us':0,'clock_uncertainty_us':1},100)
        for index in range(2000):window.video(100+index*.001,round((100+index*.001)*1e6))
        self.assertEqual(len(window.frames),MAX_SAMPLES)
        self.assertEqual(len(window.ages),MAX_SAMPLES)
        self.assertEqual(window.snapshot(102)['receive_frame_gap_p95_ms'],1)
        window.snapshot(108)
        self.assertEqual(len(window.frames),0);self.assertEqual(len(window.ages),0)

    def test_clock_recalibration_does_not_mix_incompatible_ages(self):
        window=StreamWindow();window.phone_sample({'clock_offset_us':0,'clock_uncertainty_us':10},1)
        window.video(1.01,1_000_000)
        window.phone_sample({'clock_offset_us':100000,'clock_uncertainty_us':10},2)
        window.video(2.02,1_900_000)
        self.assertEqual(window.snapshot(2.02)['capture_to_receive_samples'],1)
        self.assertEqual(window.snapshot(2.02)['capture_to_receive_p95_ms'],20)

    def test_preview_expires_once_then_resumes_without_decoding_reference_drops(self):
        preview=PreviewFreshness()
        self.assertFalse(preview.should_clear(100))
        self.assertTrue(preview.accept(100,100.1))
        self.assertFalse(preview.should_clear(100.999))
        self.assertTrue(preview.should_clear(101))
        for now in (101.1,102,1000):self.assertFalse(preview.should_clear(now))
        self.assertFalse(preview.accept(100,102));self.assertTrue(preview.blank)
        self.assertTrue(preview.accept(102.1,102.15));self.assertFalse(preview.blank)
        self.assertEqual((preview.clears,preview.expired_frames),(1,1))

    def test_connection_view_never_labels_stale_metrics_as_current_video(self):
        state={'state':'connected','transport':'USB/TLS','metrics_at':10,
               'metrics':{'last_video_receive_monotonic_s':10,'receive_fps':30,
                          'timing_sample_age_ms':2900,'capture_to_receive_p95_ms':25,'clock_uncertainty_ms':1}}
        status,view=connection_view(state,10)
        self.assertEqual(status,'Video recebido');self.assertIn('25.0 ms',view['timing'])
        status,view=connection_view(state,10.2)
        self.assertIn('Indisponivel',view['timing'])
        status,view=connection_view(state,14)
        self.assertEqual(status,'Sem video recente');self.assertNotIn('30.0',view['rates'])
        state['state']='waiting';status,view=connection_view(state,14)
        self.assertEqual(status,'Aguardando iPhone');self.assertEqual(view['transport'],'Desconectado')
        state['state']='connected';state['metrics']['timing_sample_age_ms']=None
        connection_view(state,10)

    def test_untrusted_timing_payload_requires_an_object(self):
        for value in (None,[],3,'stats'):
            with self.assertRaises(ProtocolError):phone_metrics(value)
