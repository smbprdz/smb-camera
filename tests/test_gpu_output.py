import os
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch
from ucs.gpu_output import GPUFramePublisher,GPU_DESCRIPTOR,validate_request
from ucs.frame_output import REQUEST,REPLY


def request(width=4,height=2,operation=0):return REQUEST.pack(0x51534355,2,24,4,width,height,operation)


class GPUOutputTests(unittest.TestCase):
    def publisher(self):
        clock=[5.]
        out=GPUFramePublisher(clock=lambda:clock[0]);out.enabled=True
        out.set_canvas(4,2);out.request(request())
        return out,clock

    def test_control_request_and_single_reader_lazy_endpoint(self):
        out=GPUFramePublisher()
        self.assertIsNone(out.server);self.assertIsNone(out.device)
        self.assertEqual(out.pipe_instances,1);self.assertFalse(out.allow_frame_services)
        self.assertFalse(out.wanted());self.assertEqual(len(out.request(request())),32)
        for payload in (b'',REQUEST.pack(0x51534355,1,24,4,4,2,0),request(operation=3),request(16384,16384)):
            with self.assertRaises(ValueError):validate_request(payload)
        out.close()

    def test_consumer_errors_stop_demand_without_stopping_camera_or_assuming_success(self):
        out,clock=self.publisher()
        out.request(request(operation=1));self.assertFalse(out.wanted())
        self.assertIn('GPU',out.snapshot()['gpu_output_consumer_error'])
        out.request(request());self.assertTrue(out.wanted())
        self.assertEqual(out.snapshot()['gpu_output_consumer_error'],'')
        clock[0]+=.7;self.assertFalse(out.wanted());out.close()

    def test_render_publishes_only_descriptor_and_releases_device_after_idle(self):
        class Device:
            def __init__(self,*args):self.info={'luid':[0x1234,-1]};self.closed=False
            def close(self):self.closed=True
        class Surface:
            def __init__(self,*args,**kwargs):self.texture=object();self.handle=17;self.closed=False
            def render(self,callback):callback(object())
            def close(self):self.closed=True
        class Access:
            def __init__(self,*args):self.held=False
            def acquire(self,key):self.held=True;return True
            def publish(self,key):self.held=False
            def close(self):pass
        class Renderer:
            canvas=(4,2);output_reads=0;info={'renderer':'fixture'}
            def render_output(self,target,format):self.asserted_format=format
        out,clock=self.publisher();renderer=Renderer()
        with patch('ucs.gpu_device.Device',Device),patch('ucs.gpu_device.Interop',Surface),patch('ucs.gpu_device.KeyedAccess',Access):
            self.assertTrue(out.publish_render(renderer,5.))
            packet=out.request(request());header=REPLY.unpack(packet[:32]);frame=GPU_DESCRIPTOR.unpack(packet[32:])
            self.assertEqual(len(packet),96);self.assertEqual(header[:5],(0x52534355,2,1,64,0))
            self.assertEqual(frame[:12],(0x47534355,1,64,3,4,2,28,1,0x1234,-1,0,17))
            self.assertEqual(frame[12],1);self.assertEqual(renderer.output_reads,0)
            device,surface=out.device,out.surface
            clock[0]+=.251;self.assertEqual(len(out.request(request())),32)
            out.disconnect();out.idle(renderer)
            self.assertTrue(device.closed);self.assertTrue(surface.closed)
            self.assertIsNone(out.device);self.assertIsNone(out.surface)
        out.close()

    def test_failed_shared_surface_creation_does_not_keep_a_device_after_output_fails(self):
        class Device:
            def __init__(self,*args):self.closed=False
            def close(self):self.closed=True
        class Renderer:
            canvas=(4,2);info={'renderer':'fixture'}
        out,clock=self.publisher();renderer=Renderer()
        with patch('ucs.gpu_device.Device',Device),patch('ucs.gpu_device.Interop',side_effect=RuntimeError('fixture creation failure')):
            with self.assertRaises(RuntimeError):out.publish_render(renderer,5.)
            device=out.device;self.assertIsNotNone(device)
            out.fail();out.idle(renderer)
            self.assertTrue(device.closed);self.assertIsNone(out.device)
        out.close()


@unittest.skipUnless(os.name=='nt' and Path('C:/Program Files/obs-studio/bin/64bit/lua51.dll').is_file(),'Windows LuaJIT and pipe')
class GPUReceiverTests(unittest.TestCase):
    def test_wrong_producer_pid_or_owner_never_reaches_the_gpu_descriptor(self):
        from test_obs_alpha_transport import Lua
        for kind in ('pid','owner'):
            out=GPUFramePublisher(enabled=True);out.set_canvas(4,2)
            endpoint=out.endpoint()
            keys=('schema','transport','alpha_mode','width','height','pipe_name','owner_sid','producer_pid','epoch_hex')
            value={key:endpoint[key] for key in keys}
            if kind=='pid':value['producer_pid']+=1
            else:value['owner_sid']='S-1-5-18'
            runtime=Lua(transport='gpu_transport.lua')
            try:
                runtime.endpoint(value)
                runtime.run('assert(client:poll()==nil);assert(client.error~=nil);assert(not client:fresh())')
                self.assertEqual(out.requests,0)
            finally:runtime.close();out.close()

    def test_gpu_wire_preserves_epochs_and_rejects_wrong_identity_or_layout(self):
        from test_obs_alpha_transport import Lua
        import uuid
        from ucs.frame_pipe_windows import PipeServer
        pipe='\\\\.\\pipe\\UCS.FrameBridge.'+str(uuid.uuid4())
        endpoint=dict(schema=2,transport='d3d11-keyed-v1',alpha_mode='premultiplied',width=4,height=2,
            pipe_name=pipe,owner_sid=PipeServer(pipe).owner_sid,producer_pid=os.getpid(),epoch_hex='fffffffffedcba98')
        # Loading both protocols in one state used to expose incompatible FFI
        # OVERLAPPED declarations. The GPU client must share the exact ABI.
        runtime=Lua()
        try:
            import json
            path=(Path(__file__).resolve().parents[1]/'integrations/obs/gpu_transport.lua').as_posix()
            runtime.run('transport=dofile('+json.dumps(path)+')')
            runtime.endpoint(endpoint)
            desc=GPU_DESCRIPTOR.pack(0x47534355,1,64,3,4,2,28,1,0x1234,-1,0,17,1,0xfeedbeeffedcba98)
            header=REPLY.pack(0x52534355,2,1,64,0,1000,0xfffffffffedcba98)
            runtime.binary('packet_bytes',header+desc)
            runtime.run('ffi.copy(client.buffer,packet_bytes,96); local r=client:validate(96,1100); '
                        'assert(r and r.handle==17 and r.luid_low==4660 and r.luid_high==-1); '
                        'assert(ffi.sizeof(client.buffer)==96); assert(client.gpu)')
            runtime.run('ffi.copy(client.buffer,packet_bytes,96); assert(client:validate(96,1251)==nil);assert(client.error)')
            runtime.run('assert(client.cached_only and not client:fresh()); '
                        'assert(not client.invalidate_private); '
                        'assert(client:validate(96,999)==nil and client.invalidate_private); '
                        'assert(not client.cached_only and not client:fresh())')
        finally:runtime.close()

    def test_gpu_lua_client_reads_real_verified_pipe_using_small_control_messages(self):
        from test_obs_alpha_transport import Lua
        out=GPUFramePublisher(enabled=True)
        out.set_canvas(4,2);endpoint=out.endpoint();runtime=Lua(transport='gpu_transport.lua')
        keys=('schema','transport','alpha_mode','width','height','pipe_name','owner_sid','producer_pid','epoch_hex')
        runtime.endpoint({key:endpoint[key] for key in keys})
        finish=threading.Event()
        def publish_control():
            index=0
            while not finish.wait(.002):
                if out.wanted():
                    with out.condition:
                        index+=1
                        descriptor=GPU_DESCRIPTOR.pack(0x47534355,1,64,3,4,2,28,1,123,0,0,17,index,7)
                        out.latest=(out.clock(),4,REPLY.pack(0x52534355,2,1,64,0,out.tick_ms(),out.epoch)+descriptor)
        worker=threading.Thread(target=publish_control);worker.start()
        try:
            runtime.run('received=0')
            for _ in range(80):
                runtime.run('local r=client:poll();if r then assert(r.handle==17);received=received+1 end')
                time.sleep(.003)
            runtime.run('assert(received>=5);assert(client.error==nil);client:report_error(1)')
            for _ in range(10):runtime.run('client:poll()');time.sleep(.003)
            self.assertTrue(out.consumer_error)
        finally:
            finish.set();worker.join(1);runtime.close();out.close()
