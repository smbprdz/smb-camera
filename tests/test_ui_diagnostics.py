import unittest
from collections import deque
from unittest.mock import patch
from ucs.ui_diagnostics import UIDiagnostics,measure_poll
from ucs.live_preview import LivePreviewSink

class UIDiagnosticTests(unittest.TestCase):
    def test_disabled_probe_does_not_sample_clock_or_collect_ui_data(self):
        def forbidden():raise AssertionError('Disabled diagnostics sampled the clock')
        diagnostics=UIDiagnostics(False,forbidden)
        class Controller:
            @measure_poll
            def poll(self):return 'normal UI'
        controller=Controller();controller.diagnostics=diagnostics
        self.assertEqual(controller.poll(),'normal UI');self.assertIsNone(diagnostics.start_navigation());self.assertEqual(diagnostics.snapshot(),{})
    def test_numeric_samples_are_bounded_and_navigation_at_clock_zero_is_valid(self):
        now=[0.];diagnostics=UIDiagnostics(True,lambda:now[0]);started=diagnostics.start_navigation();now[0]=.025
        diagnostics.finish_navigation(started)
        for i in range(500):diagnostics.record('poll',i)
        data=diagnostics.snapshot()['ui_diagnostics']
        self.assertEqual(data['poll']['count'],120);self.assertEqual(data['navigation_to_idle']['max_ms'],25)
        self.assertEqual(set(data),{'poll','heartbeat_late','navigation_to_idle'})
    def test_poll_failure_is_timed_without_suppressing_the_original_error(self):
        now=[0.];diagnostics=UIDiagnostics(True,lambda:now[0])
        class Controller:
            @measure_poll
            def poll(self):now[0]=.003;raise ValueError('failure')
        controller=Controller();controller.diagnostics=diagnostics
        with self.assertRaises(ValueError):controller.poll()
        self.assertEqual(diagnostics.snapshot()['ui_diagnostics']['poll']['max_ms'],3)
    def test_frame_gap_counts_only_submitted_frames_and_has_no_startup_interval(self):
        sink=LivePreviewSink.__new__(LivePreviewSink);sink.last_submit_time=None;sink.submit_gaps=deque(maxlen=300)
        sink.submitted=0;sink.preview_age=deque(maxlen=300)
        with patch('ucs.live_preview.time.perf_counter',side_effect=[100.,100.033,100.133]):
            sink._submitted(99.99);sink._submitted(100.02);sink._submitted(100.12)
        self.assertEqual(sink.submitted,3);self.assertEqual(len(sink.submit_gaps),2)
        self.assertAlmostEqual(sink.submit_gaps[-1],100)
