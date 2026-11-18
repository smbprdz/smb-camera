"""Optional own GPU alpha output with a bounded local control pipe.

Pixel data stays in a keyed D3D11 texture. Control messages are 32+64 bytes.
One reader in this first cut. All device/GL work belongs to the render thread.
"""
import math
import secrets
import struct
from .frame_output import FramePublisher,REQUEST,REPLY

GPU_DESCRIPTOR=struct.Struct('<IHHIIIIIIiIQQQ')
assert GPU_DESCRIPTOR.size==64
GPU_FORMAT=4


def validate_request(data):
    if len(data)!=24:raise ValueError('Invalid GPU control request size')
    magic,version,size,kind,width,height,operation=REQUEST.unpack(data)
    if (magic!=0x51534355 or version!=2 or size!=24 or kind!=GPU_FORMAT or operation not in (0,1,2)
            or not 2<=width<=16384 or not 2<=height<=16384 or width*height*4>64*1024*1024):
        raise ValueError('Invalid GPU output request')
    return width,height,operation


class GPUFramePublisher(FramePublisher):
    gpu=True
    def __init__(self,metadata=None,enabled=False,clock=None):
        super().__init__(metadata=metadata,formats=(3,),enabled=False,pipe_instances=1,allow_frame_services=False)
        self.formats=(GPU_FORMAT,)
        if clock is not None:self.clock=clock
        self.device=self.surface=self.access=None
        self.surface_size=None;self.resource_epoch=0;self.reset_requested=False
        self.busy_skips=0;self.recreated=0;self.cpu_readbacks=0
        self.consumer_error=''
        if enabled:self.enable()

    def endpoint(self):
        value=super().endpoint()
        value.update(schema=2,transport='d3d11-keyed-v1',alpha_mode='premultiplied',
            epoch_hex=f'{self.epoch:016x}',width=self.canvas[0] if self.canvas else 0,
            height=self.canvas[1] if self.canvas else 0,max_readers=1)
        return value

    def request(self,data,wait=0):
        width,height,operation=validate_request(data)
        with self.condition:
            self.requests+=1
            empty=REPLY.pack(0x52534355,2,0,0,0,0,self.epoch)
            if not self.enabled or self.stopped or self.error:return empty
            if operation:
                self.consumer_error=('O OBS precisa usar a mesma GPU do SMB Camera.' if operation==1
                                     else 'A fonte OBS recusou o recurso GPU. Reative a fonte após conferir a conexão.')
                self.until=0.;self.latest=None;self.reset_requested=True;return empty
            self.consumer_error=''
            self.pixel_format=GPU_FORMAT;self.mode=(width,height);self.until=self.clock()+.6
            if self.canvas!=self.mode:return empty
            if self.latest and 0<=self.clock()-self.latest[0]<=.25:return self.latest[2]
            return empty

    def disconnect(self):
        super().disconnect()
        with self.condition:self.reset_requested=True

    def _release_surface(self):
        # Called only while the producer GL context is current.
        if self.access:self.access.close();self.access=None
        if self.surface:self.surface.close();self.surface=None
        self.surface_size=None
        with self.condition:self.latest=None

    def release_renderer(self,renderer):
        self._release_surface()
        if self.device:self.device.close();self.device=None

    def idle(self,renderer):
        if (self.surface is not None or self.device is not None) and (not self.wanted() or self.reset_requested):
            self.release_renderer(renderer);self.reset_requested=False

    def _create_surface(self,renderer):
        from .gpu_device import Device,Interop,KeyedAccess
        if self.device is None:self.device=Device(renderer.info['renderer'])
        self.surface=Interop(renderer,self.device,*renderer.canvas,keyed=True)
        self.access=KeyedAccess(self.surface.texture);self.surface_size=renderer.canvas
        self.resource_epoch=secrets.randbits(63)+1;self.recreated+=1

    def publish_render(self,renderer,arrival):
        if type(arrival) not in (int,float) or not math.isfinite(arrival):raise ValueError('Invalid GPU arrival')
        now=self.clock()
        if not self.wanted() or not 0<=now-arrival<=.25 or arrival<=self.last_arrival:
            self.rejected+=1;return False
        from .gpu_device import AbandonedTexture
        if self.surface_size!=renderer.canvas or self.reset_requested:
            self._release_surface();self.reset_requested=False
        if self.surface is None:self._create_surface(renderer)
        try:owned=self.access.acquire(0)
        except AbandonedTexture:
            self._release_surface();self._create_surface(renderer);owned=self.access.acquire(0)
        if not owned:
            self.busy_skips += 1
            # A reader can miss key 1, then only receive empty replies once
            # its descriptor expires. Retire our reference on the GL thread;
            # an existing reader still owns its reference to the old surface.
            if now - self.last_arrival >= .5:
                self._release_surface()
            return False
        before=renderer.output_reads
        try:self.surface.render(lambda target:renderer.render_output(target,3))
        except Exception:
            self.access.publish(0)
            raise
        self.access.publish(1)
        if renderer.output_reads!=before:raise RuntimeError('GPU output unexpectedly read pixels')
        now=self.clock();age=now-arrival
        with self.condition:
            if not self.wanted() or not 0<=age<=.25:
                self.rejected+=1;self.reset_requested=True;return False
            self.published+=1;self.last_arrival=arrival
            captured=max(0,self.tick_ms()-round(age*1000));low,high=self.device.info['luid']
            descriptor=GPU_DESCRIPTOR.pack(0x47534355,1,64,3,*renderer.canvas,28,1,low,high,0,
                self.surface.handle,self.published,self.resource_epoch)
            self.latest=(arrival,GPU_FORMAT,REPLY.pack(0x52534355,2,1,64,0,captured,self.epoch)+descriptor)
            self.condition.notify_all();return True

    def snapshot(self):
        return dict(super().snapshot(),frame_output_transport='d3d11-keyed-v1',gpu_output_busy_skips=self.busy_skips,
            gpu_output_resource_generations=self.recreated,gpu_output_cpu_readbacks=self.cpu_readbacks,
            gpu_output_max_readers=1,gpu_output_consumer_error=self.consumer_error)
