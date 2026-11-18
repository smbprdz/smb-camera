import threading,time,unittest
from ucs.preview_visibility import PreviewVisibility
from ucs.matting import BackgroundState,MatteWorker

class VisibilityTests(unittest.TestCase):
    def test_visibility_is_explicit_and_rejects_non_boolean_state(self):
        state=PreviewVisibility();self.assertTrue(state.is_visible())
        state.set_visible(False);self.assertFalse(state.is_visible())
        for value in (None,0,1,'iconic'):
            with self.assertRaises(ValueError):state.set_visible(value)
    def test_suspended_worker_does_not_load_a_model(self):
        calls=[];state=BackgroundState();state.set(mode='transparent')
        worker=MatteWorker(state,factory=lambda:calls.append(1))
        try:
            worker.set_suspended(True)
            for index in range(30):worker.submit((object(),index,time.perf_counter()),state.get()['generation'])
            time.sleep(.12);self.assertFalse(calls);self.assertEqual(worker.snapshot()['matting_frames'],0)
        finally:self.assertTrue(worker.close())
    def test_inflight_result_cannot_reappear_after_suspend_and_resume_resets_temporal_state(self):
        import numpy as np
        entered=threading.Event();release=threading.Event();completed=threading.Event();resets=[];calls=[]
        class Model:
            def infer(self,frame,angle=0,mirror=False):
                calls.append(frame);entered.set();release.wait(1);completed.set();return np.full((2,2),128,np.uint8)
            def reset(self):resets.append(True)
        state=BackgroundState();state.set(mode='transparent');worker=MatteWorker(state,factory=Model)
        try:
            old=object();worker.submit((old,1,time.perf_counter()),state.get()['generation']);self.assertTrue(entered.wait(1))
            worker.set_suspended(True);release.set();self.assertTrue(completed.wait(1));time.sleep(.02)
            self.assertIsNone(worker.take());self.assertEqual(worker.snapshot()['matting_frames'],0)
            for index in range(5):worker.submit((old,index,time.perf_counter()),state.get()['generation'])
            worker.set_suspended(False);new=object();worker.submit((new,10,time.perf_counter()),state.get()['generation'])
            end=time.monotonic()+1;result=None
            while result is None and time.monotonic()<end:result=worker.take();time.sleep(.002)
            self.assertIsNotNone(result);self.assertIs(result[0],new);self.assertEqual(calls,[old,new]);self.assertEqual(len(resets),1)
        finally:release.set();self.assertTrue(worker.close())
