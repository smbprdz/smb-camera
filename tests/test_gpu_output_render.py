"""Real own GPU output, generated pixels only; consumer readback is validation."""
import os
import time
import unittest
from ucs.gpu_output import GPUFramePublisher,GPU_DESCRIPTOR
from ucs.frame_output import REQUEST


@unittest.skipUnless(os.name=='nt' and os.environ.get('UCS_TEST_GPU')=='1','Windows GPU context')
class GPUOutputRenderingTests(unittest.TestCase):
    def test_shared_output_matches_the_existing_rgba_shader_for_every_orientation(self):
        import av
        import numpy as np
        from ucs.gl_preview import GLPreview
        from ucs.gpu_device import Device,KeyedAccess,release
        renderer=GLPreview(64,64,window_width=64,window_height=64,hidden=True)
        publisher=GPUFramePublisher();publisher.enabled=True
        receiver=Device(renderer.info['renderer'])
        frame=av.VideoFrame(64,64,'yuv420p');frame.color_range=1;frame.colorspace=1
        for plane,value in zip(frame.planes,(92,130,170)):plane.update(bytes([value])*plane.buffer_size)
        yy,xx=np.mgrid[:64,:64];mask=((xx*3+yy*5)%256).astype(np.uint8)
        try:
            renderer.upload(frame)
            for angle in (0,90,180,270):
                for mirror in (False,True):
                    for mode in ('landscape','portrait'):
                        renderer.draw(angle=angle,mirror=mirror,output_format=mode,alpha=mask,
                            background={'mode':'transparent','solidity':20},preview=False)
                        width,height=renderer.canvas
                        publisher.set_canvas(width,height)
                        request=REQUEST.pack(0x51534355,2,24,4,width,height,0)
                        publisher.request(request)
                        self.assertTrue(publisher.publish_render(renderer,time.perf_counter()))
                        reads=renderer.output_reads
                        descriptor=GPU_DESCRIPTOR.unpack(publisher.request(request)[32:])
                        self.assertEqual(descriptor[4:6],(width,height))
                        texture=receiver.open(descriptor[11]);access=KeyedAccess(texture)
                        stage=receiver.texture(width,height,True)
                        try:
                            self.assertTrue(access.acquire(1))
                            actual=receiver.read(texture,stage,width,height)
                            access.publish(0)
                        finally:
                            access.close();release(stage);release(texture)
                        self.assertEqual(renderer.output_reads,reads)
                        self.assertEqual(actual,renderer.capture_output(3)[2])
            self.assertEqual(publisher.snapshot()['gpu_output_cpu_readbacks'],0)
        finally:
            publisher.release_renderer(renderer);publisher.close();receiver.close();renderer.close()

    def test_expired_busy_surface_recovers_while_consumer_keeps_requesting(self):
        import av
        from ucs.gl_preview import GLPreview
        from ucs.gpu_device import Device, KeyedAccess, release
        clock = [10.]
        renderer = GLPreview(64, 64, window_width=64, window_height=64, hidden=True)
        publisher = GPUFramePublisher(clock=lambda: clock[0])
        publisher.enabled = True
        receiver = Device(renderer.info['renderer'])
        old_texture = new_texture = access = None
        try:
            renderer.upload(av.VideoFrame(64, 64, 'yuv420p'))
            renderer.draw(preview=False)
            width, height = renderer.canvas
            query = REQUEST.pack(0x51534355, 2, 24, 4, width, height, 0)
            publisher.set_canvas(width, height)
            publisher.request(query)
            self.assertTrue(publisher.publish_render(renderer, clock[0]))
            first = GPU_DESCRIPTOR.unpack(publisher.request(query)[32:])
            old_texture = receiver.open(first[11])
            # Miss the handoff. Key 1 remains pending, yet IPC demand continues.
            for _ in range(12):
                clock[0] += .05
                reply = publisher.request(query)
                if clock[0] - 10. > .25:
                    self.assertEqual(len(reply), 32)
                if publisher.publish_render(renderer, clock[0]):
                    break
            else:
                self.fail('Expired descriptor leaves producer permanently busy')
            current = GPU_DESCRIPTOR.unpack(publisher.request(query)[32:])
            self.assertNotEqual(first[13], current[13])
            self.assertGreater(current[12], first[12])
            new_texture = receiver.open(current[11])
            access = KeyedAccess(new_texture)
            self.assertTrue(access.acquire(1))
            access.publish(0)
            self.assertEqual(renderer.output_reads, 0)
        finally:
            if access: access.close()
            if new_texture: release(new_texture)
            if old_texture: release(old_texture)
            publisher.release_renderer(renderer)
            publisher.close()
            receiver.close()
            renderer.close()
