import os,struct,threading,time,unittest
from ucs.frame_output import FrameOutput,FramePublisher,REQUEST,REPLY,DESCRIPTOR

def request(width=4,height=2,format=2):return REQUEST.pack(0x51534355,1,24,format,width,height,0)

class OutputContractTests(unittest.TestCase):
    def test_lazy_publisher_does_not_start_pipe_or_write_metadata_before_activation(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder,patch('ucs.frame_pipe_windows.PipeServer',side_effect=AssertionError('Unrequested pipe startup')):
            path=Path(folder)/'endpoint.json';publisher=FramePublisher(metadata=path,enabled=False)
            publisher.set_canvas(1920,1080);self.assertFalse(publisher.wanted());self.assertFalse(path.exists())
            self.assertFalse(publisher.snapshot()['frame_output_enabled']);publisher.close();self.assertFalse(path.exists())
    def test_nv12_has_exact_planes_color_and_never_returns_cached_bgra_after_mode_switch(self):
        clock=[5.];out=FrameOutput(clock=lambda:clock[0],epoch=7,formats=(1,2));out.set_canvas(4,2)
        out.request(request(),wait=0);self.assertTrue(out.publish(4,2,bytes([1,2,3,255])*8,clock[0]))
        self.assertEqual(len(out.request(request(format=1),wait=0)),32);self.assertEqual(out.requested_format(),1)
        clock[0]+=.01;pixels=bytes([32])*8+bytes([128])*4
        self.assertTrue(out.publish(4,2,pixels,clock[0],1));packet=out.request(request(format=1),wait=0)
        frame=DESCRIPTOR.unpack(packet[32:96]);self.assertEqual(frame[3:10],(1,4,2,4,4,8,12));self.assertEqual(frame[12:],(1,0));self.assertEqual(packet[96:],pixels)
        self.assertEqual(len(out.request(request(),wait=0)),32)
        with self.assertRaises(ValueError):out.publish(3,2,b'123456789',clock[0],1)
        default=FrameOutput();default.set_canvas(4,2);self.assertEqual(len(default.request(request(format=1),wait=0)),32);self.assertFalse(default.wanted())
        for formats in ((0,),(1,1),(True,),(4,),()):
            with self.assertRaises(ValueError):FrameOutput(formats=formats)
    def test_rgba_requires_explicit_negotiation_and_preserves_alpha_flag_pixels_and_ttl(self):
        clock=[5.];out=FrameOutput(clock=lambda:clock[0],epoch=7,formats=(3,));out.set_canvas(4,2)
        self.assertEqual(len(out.request(request(),wait=0)),32);self.assertFalse(out.wanted())
        out.request(request(format=3),wait=0);pixels=bytes([0,0,0,0,32,64,96,128,40,60,80,255,0,0,0,0])*2
        self.assertTrue(out.publish(4,2,pixels,clock[0],3))
        packet=out.request(request(format=3),wait=0);frame=DESCRIPTOR.unpack(packet[32:96])
        self.assertEqual(frame[3:10],(3,4,2,16,0,0,32));self.assertEqual(frame[12:],(2,1));self.assertEqual(packet[96:],pixels)
        clock[0]+=.251;self.assertEqual(len(out.request(request(format=3),wait=0)),32)
        opaque=FrameOutput();opaque.set_canvas(4,2)
        self.assertEqual(len(opaque.request(request(format=3),wait=0)),32);self.assertFalse(opaque.wanted())
        with self.assertRaises(ValueError):opaque.publish(4,2,pixels,time.perf_counter(),3)
    def test_packet_layout_matches_native_and_old_frames_never_become_fresh_by_requesting_again(self):
        clock=[10.];out=FrameOutput(clock=lambda:clock[0],tick_ms=lambda:round(clock[0]*1000),epoch=7);out.set_canvas(4,2)
        self.assertFalse(out.wanted());self.assertEqual(len(out.request(request(),wait=0)),32);self.assertTrue(out.wanted())
        pixels=bytes([4,5,6,255])*8;self.assertTrue(out.publish(4,2,pixels,9.9))
        packet=out.request(request(),wait=0);header=REPLY.unpack(packet[:32]);desc=DESCRIPTOR.unpack(packet[32:96])
        self.assertEqual(header,(0x52534355,1,1,96,0,9900,7));self.assertEqual(desc,(0x46534355,1,64,2,4,2,16,0,0,32,1,0,2,0));self.assertEqual(packet[96:],pixels)
        clock[0]=10.16;self.assertEqual(len(out.request(request(),wait=0)),32)
        self.assertFalse(out.publish(4,2,pixels,9.9));self.assertEqual(out.published,1)
    def test_single_slot_replacement_mode_bounds_and_disconnect(self):
        clock=[5.];out=FrameOutput(clock=lambda:clock[0],epoch=1);out.set_canvas(4,2);out.request(request(),wait=0)
        for n in range(10):
            clock[0]+=.001;self.assertTrue(out.publish(4,2,bytes([n,0,0,255])*8,clock[0]))
        self.assertEqual(out.request(request(),wait=0)[96],9);self.assertEqual(out.snapshot()['frame_output_queue_capacity'],1)
        out.request(request(8,2),wait=0);self.assertFalse(out.wanted())
        out.disconnect();self.assertIsNone(out.latest);self.assertFalse(out.wanted())
        for data in (b'',request()[:-1],REQUEST.pack(0x51534355,1,24,99,4,2,0),request(16384,16384)):
            with self.assertRaises(ValueError):out.request(data,wait=0)
    def test_request_wait_is_woken_by_publish_and_stop(self):
        out=FrameOutput(epoch=1);out.set_canvas(4,2);received=[]
        worker=threading.Thread(target=lambda:received.append(out.request(request(),wait=.5)));worker.start()
        until=time.monotonic()+1
        while not out.wanted() and time.monotonic()<until:time.sleep(.001)
        self.assertTrue(out.publish(4,2,bytes([0,0,0,255])*8,time.perf_counter()));worker.join(1)
        self.assertEqual(len(received[0]),128);out.close();self.assertFalse(out.wanted());self.assertIsNone(out.latest)

@unittest.skipUnless(os.name=='nt','Windows named pipe integration')
class OutputPipeTests(unittest.TestCase):
    def test_bounded_pipe_pool_keeps_second_consumer_alive_when_first_disconnects(self):
        import ctypes as C
        from ctypes import wintypes as W
        from ucs.frame_pipe_windows import OVERLAPPED
        publisher=FramePublisher(epoch=7);server=publisher.server;publisher.set_canvas(4,2)
        k=server.k;k.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,W.LPVOID,W.DWORD,W.DWORD,W.HANDLE];k.CreateFileW.restype=W.HANDLE
        k.SetNamedPipeHandleState.argtypes=[W.HANDLE,C.POINTER(W.DWORD),W.LPVOID,W.LPVOID];k.SetNamedPipeHandleState.restype=W.BOOL
        k.TransactNamedPipe.argtypes=[W.HANDLE,W.LPVOID,W.DWORD,W.LPVOID,W.DWORD,C.POINTER(W.DWORD),C.POINTER(OVERLAPPED)];k.TransactNamedPipe.restype=W.BOOL
        handles=[];events=[];finish=threading.Event()
        def feed():
            while not finish.wait(.005):
                if publisher.wanted():publisher.publish(4,2,bytes([10,20,30,255])*8,time.perf_counter())
        feeder=threading.Thread(target=feed);feeder.start()
        def transact(handle):
            event=k.CreateEventW(None,True,False,None);events.append(event);op=OVERLAPPED();op.hEvent=event
            data=C.create_string_buffer(request());reply=C.create_string_buffer(128);count=W.DWORD()
            okay=k.TransactNamedPipe(handle,data,24,reply,128,C.byref(count),C.byref(op))
            if not okay:self.assertEqual(C.get_last_error(),997);self.assertEqual(k.WaitForSingleObject(event,2000),0)
            self.assertTrue(k.GetOverlappedResult(handle,C.byref(op),C.byref(count),False));self.assertEqual(count.value,128)
        try:
            for _ in range(2):
                handle=k.CreateFileW(server.name,0x120183,0,None,3,0x40000000|0x110000,None)
                self.assertNotEqual(handle,C.c_void_p(-1).value);handles.append(handle);mode=W.DWORD(2)
                self.assertTrue(k.SetNamedPipeHandleState(handle,C.byref(mode),None,None));transact(handle)
            k.CloseHandle(handles.pop(0));time.sleep(.02);transact(handles[0]);self.assertTrue(publisher.wanted())
            self.assertEqual(len(server.handles),4)
        finally:
            for handle in handles:k.CloseHandle(handle)
            finish.set();feeder.join(1)
            for event in events:k.CloseHandle(event)
            publisher.close()
        self.assertFalse(server.thread.is_alive());self.assertEqual(server.handles,[])
    def test_real_local_pipe_serves_generated_frame_and_stops_without_a_camera_or_recording(self):
        self.assert_pipe_payload(2,bytes([1,2,3,255])*8)
    def test_real_local_pipe_nv12_payload(self):
        self.assert_pipe_payload(1,bytes([32])*8+bytes([128])*4)
    def test_real_local_pipe_rgba_preserves_transparent_and_half_alpha(self):
        self.assert_pipe_payload(3,bytes([0,0,0,0,30,40,50,128,40,60,80,255,0,0,0,0])*2)
    def assert_pipe_payload(self,format,pixels):
        import ctypes as C
        from ctypes import wintypes as W
        from ucs.frame_pipe_windows import OVERLAPPED
        publisher=FramePublisher(epoch=7,formats=(format,));server=publisher.server;publisher.set_canvas(4,2);k=C.WinDLL('kernel32',use_last_error=True)
        k.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,W.LPVOID,W.DWORD,W.DWORD,W.HANDLE];k.CreateFileW.restype=W.HANDLE
        k.SetNamedPipeHandleState.argtypes=[W.HANDLE,C.POINTER(W.DWORD),W.LPVOID,W.LPVOID]
        k.CreateEventW.argtypes=[W.LPVOID,W.BOOL,W.BOOL,W.LPCWSTR];k.CreateEventW.restype=W.HANDLE
        k.TransactNamedPipe.argtypes=[W.HANDLE,W.LPVOID,W.DWORD,W.LPVOID,W.DWORD,C.POINTER(W.DWORD),C.POINTER(OVERLAPPED)]
        k.GetOverlappedResult.argtypes=[W.HANDLE,C.POINTER(OVERLAPPED),C.POINTER(W.DWORD),W.BOOL]
        k.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD];k.CloseHandle.argtypes=[W.HANDLE]
        pipe=event=None
        try:
            pipe=k.CreateFileW(publisher.server.name,0x120183,0,None,3,0x40000000|0x110000,None)
            self.assertNotEqual(pipe,C.c_void_p(-1).value)
            mode=W.DWORD(2);self.assertTrue(k.SetNamedPipeHandleState(pipe,C.byref(mode),None,None))
            def feed():
                until=time.monotonic()+1
                while not publisher.wanted() and time.monotonic()<until:time.sleep(.001)
                publisher.publish(4,2,pixels,time.perf_counter(),format)
            worker=threading.Thread(target=feed);worker.start()
            event=k.CreateEventW(None,True,False,None);op=OVERLAPPED();op.hEvent=event;count=W.DWORD();reply=C.create_string_buffer(96+len(pixels));data=C.create_string_buffer(request(format=format))
            okay=k.TransactNamedPipe(pipe,data,24,reply,len(reply),C.byref(count),C.byref(op))
            if not okay:self.assertEqual(C.get_last_error(),997);self.assertEqual(k.WaitForSingleObject(event,2000),0)
            self.assertTrue(k.GetOverlappedResult(pipe,C.byref(op),C.byref(count),False));worker.join(1)
            self.assertEqual(count.value,96+len(pixels));self.assertEqual(reply.raw[96:],pixels)
        finally:
            if pipe and pipe!=C.c_void_p(-1).value:k.CloseHandle(pipe)
            if event:k.CloseHandle(event)
            publisher.close()
        self.assertFalse(server.thread.is_alive());self.assertIsNone(publisher.server)
