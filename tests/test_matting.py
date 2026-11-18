import time,threading,unittest
from ucs.matting import BackgroundState,MatteWorker,frame_tensor,restore_alpha,small_rgb

class MattingTests(unittest.TestCase):
    def test_letterbox_preserves_capture_aspect(self):
        import av,numpy as np
        frame=av.VideoFrame(1920,1080,'rgb24')
        tensor,region=frame_tensor(frame)
        self.assertEqual(tensor.shape,(1,3,256,256));self.assertEqual(region,(0,56,256,144))
        self.assertEqual(tensor.dtype,np.float32)
    def test_disabled_does_not_load_model(self):
        calls=[];state=BackgroundState();worker=MatteWorker(state,factory=lambda:calls.append(1))
        worker.submit((object(),1,time.perf_counter()),state.get()['generation']);time.sleep(.12);worker.close()
        self.assertFalse(calls)
    def test_result_keeps_exact_source_and_discards_old_generation(self):
        import numpy as np
        entered=threading.Event();release=threading.Event()
        class Fake:
            def infer(self,frame,angle=0,mirror=False):entered.set();release.wait(.15);return np.ones((2,2),np.uint8)*128
        state=BackgroundState();state.set(mode='transparent');worker=MatteWorker(state,factory=Fake)
        try:
            old=object();worker.submit((old,1,time.perf_counter()),state.get()['generation']);self.assertTrue(entered.wait(1))
            state.set(mode='off');release.set();time.sleep(.03);self.assertIsNone(worker.take())
            state.set(mode='transparent');new=object();worker.submit((new,2,time.perf_counter()),state.get()['generation'])
            deadline=time.monotonic()+1;result=None
            while result is None and time.monotonic()<deadline:result=worker.take();time.sleep(.005)
            self.assertIsNotNone(result);self.assertIs(result[0],new);self.assertEqual(result[1],2)
        finally:release.set();worker.close()
    def test_initialization_never_emits_stale_camera_frame(self):
        import numpy as np
        class Fake:
            def infer(self,frame,angle=0,mirror=False):return np.zeros((2,2),np.uint8)
        def delayed_factory():time.sleep(.28);return Fake()
        state=BackgroundState();state.set(mode='transparent');worker=MatteWorker(state,factory=delayed_factory)
        try:
            worker.submit((object(),0,time.perf_counter()),state.get()['generation']);time.sleep(.34)
            self.assertIsNone(worker.take());self.assertGreaterEqual(worker.snapshot()['matting_stale_discarded'],1)
        finally:worker.close()
    def test_shutdown_cancels_an_inflight_isolated_inference(self):
        entered=threading.Event();release=threading.Event();closed=threading.Event()
        class Fake:
            def infer(self,frame,angle=0,mirror=False):entered.set();release.wait(5);raise RuntimeError('cancelled')
            def cancel(self):release.set()
            def close(self):closed.set()
        state=BackgroundState();state.set(mode='transparent');worker=MatteWorker(state,factory=Fake)
        worker.submit((object(),1,time.perf_counter()),state.get()['generation'])
        self.assertTrue(entered.wait(1));self.assertTrue(worker.close());self.assertTrue(closed.is_set())
        self.assertIsNone(worker.take())
    def test_ready_mask_is_dropped_if_the_consumer_stalls(self):
        state=BackgroundState();worker=MatteWorker(state,factory=lambda:None)
        try:
            worker.results.put((object(),1,time.perf_counter()-.3,None,state.get()['generation']))
            self.assertIsNone(worker.take());self.assertEqual(worker.snapshot()['matting_stale_discarded'],1)
        finally:worker.close()
    def test_portrait_input_and_inverse_mask_follow_preview_rotation(self):
        import av,numpy as np
        pixels=np.zeros((32,64,3),np.uint8);pixels[:,:32,0]=255
        tensor,region=frame_tensor(av.VideoFrame.from_ndarray(pixels,format='rgb24'),angle=90)
        self.assertEqual(region,(64,0,128,256))
        # The red left side becomes the top side when rotated clockwise.
        self.assertGreater(float(tensor[0,0,20,128]),.9);self.assertLess(float(tensor[0,0,220,128]),-.9)
        alpha=np.zeros((256,256),np.uint8);alpha[:128,64:192]=255
        restored=restore_alpha(alpha,region,90)
        self.assertEqual(restored.shape,(128,256));self.assertTrue((restored[:,:128]==255).all())
        self.assertTrue((restored[:,128:]==0).all())
    def test_temporal_state_resets_on_lens_revision_and_rotation(self):
        import numpy as np
        calls=[]
        class Fake:
            def infer(self,frame,angle=0,mirror=False):return np.zeros((2,2),np.uint8)
            def reset(self):calls.append('reset')
        state=BackgroundState();state.set(mode='transparent');worker=MatteWorker(state,factory=Fake)
        try:
            for seq,(angle,revision,mirror) in enumerate([(0,1,False),(0,1,False),(0,2,False),(90,2,False),(90,2,True)]):
                worker.submit((object(),seq,time.perf_counter()),state.get()['generation'],angle,revision,mirror)
                deadline=time.monotonic()+1;result=None
                while result is None and time.monotonic()<deadline:result=worker.take();time.sleep(.002)
                self.assertIsNotNone(result)
            self.assertEqual(calls,['reset','reset','reset'])
        finally:worker.close()
    def test_model_input_and_restored_mask_match_preview_in_all_eight_views(self):
        import av,numpy as np
        pixels=np.zeros((32,64,3),np.uint8)
        pixels[:16,:32]=[255,0,0];pixels[:16,32:]=[0,255,0]
        pixels[16:,:32]=[0,0,255];pixels[16:,32:]=[255,255,255]
        source_alpha=np.zeros((32,64),np.uint8);source_alpha[:16,:32]=255
        frame=av.VideoFrame.from_ndarray(pixels,format='rgb24')
        for angle in (0,90,180,270):
            for mirror in (False,True):
                canvas,region=small_rgb(frame,64,64,angle,mirror)
                left,top,w,h=region
                expected=np.rot90(pixels[:,::-1] if mirror else pixels,-angle//90)
                np.testing.assert_array_equal(canvas[top:top+h,left:left+w],expected)
                alpha=np.zeros((64,64),np.uint8)
                alpha[top:top+h,left:left+w]=np.rot90(source_alpha[:,::-1] if mirror else source_alpha,-angle//90)
                np.testing.assert_array_equal(restore_alpha(alpha,region,angle,mirror),source_alpha)
    def test_a_result_from_before_mirror_change_cannot_be_presented(self):
        import numpy as np
        class Fake:
            def infer(self,frame,angle=0,mirror=False):return np.ones((2,2),np.uint8)
        state=BackgroundState();state.set(mode='transparent');worker=MatteWorker(state,factory=Fake)
        try:
            generation=state.get()['generation'];worker.submit((object(),0,time.perf_counter()),generation,90,0,False)
            deadline=time.monotonic()+1
            while worker.snapshot()['matting_frames']==0 and time.monotonic()<deadline:time.sleep(.002)
            self.assertEqual(worker.snapshot()['matting_frames'],1)
            self.assertIsNone(worker.take((generation,90,True,0)))
        finally:worker.close()

if __name__=='__main__':unittest.main()
