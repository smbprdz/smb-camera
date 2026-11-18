"""Reference CPU frame publisher. No device registration or video files.

One current BGRA/NV12 opaque or RGBA premultiplied frame, on consumer demand. Separate from
the UCS1 network protocol and does not install a virtual camera.
"""
import json,math,os,secrets,struct,threading,time,uuid
from pathlib import Path

REQUEST=struct.Struct('<IHHIIII')
REPLY=struct.Struct('<IHHIIQQ')
DESCRIPTOR=struct.Struct('<IHHIIIIIIQQqII')
MAX_PAYLOAD=64*1024*1024
assert (REQUEST.size,REPLY.size,DESCRIPTOR.size)==(24,32,64)


class FrameOutput:
    def __init__(self,clock=time.perf_counter,tick_ms=None,epoch=None,formats=(2,)):
        if not isinstance(formats,tuple) or not formats or any(type(f) is not int or f not in (1,2,3) for f in formats) or len(set(formats))!=len(formats):raise ValueError('Invalid output formats')
        self.formats=formats;self.pixel_format=None
        self.clock=clock;self.tick_ms=tick_ms or (lambda:round(time.monotonic()*1000))
        self.epoch=secrets.randbits(63)+1 if epoch is None else epoch
        if type(self.epoch) is not int or not 1<=self.epoch<2**64:raise ValueError('Invalid output epoch')
        self.started=clock();self.last_arrival=float('-inf')
        self.condition=threading.Condition();self.canvas=None;self.mode=None;self.until=0.
        self.latest=None;self.published=0;self.requests=0;self.rejected=0;self.error='';self.stopped=False
    def set_canvas(self,width,height):
        with self.condition:
            value=(width,height)
            if value!=self.canvas:self.canvas=value;self.latest=None
    def wanted(self):
        with self.condition:return not self.stopped and not self.error and self.canvas==self.mode and self.clock()<self.until
    def requested_format(self):
        with self.condition:return self.pixel_format
    def publish(self,width,height,data,arrival,pixel_format=2):
        if type(width) is not int or type(height) is not int or not 2<=width<=16384 or not 2<=height<=16384:raise ValueError('Invalid output dimensions')
        if type(pixel_format) is not int or pixel_format not in self.formats or (pixel_format==1 and (width%2 or height%2)):raise ValueError('Unsupported output format')
        size=width*height*3//2 if pixel_format==1 else width*height*4
        if not isinstance(data,bytes) or len(data)!=size or len(data)>MAX_PAYLOAD:raise ValueError('Invalid frame payload')
        if type(arrival) not in (int,float) or not math.isfinite(arrival):raise ValueError('Invalid output timestamp')
        now=self.clock();age=now-arrival
        with self.condition:
            if self.stopped or self.error or self.pixel_format!=pixel_format or self.mode!=(width,height) or now>=self.until or not 0<=age<=.25 or arrival<=self.last_arrival:
                self.rejected+=1;return False
            self.published+=1;captured=max(0,self.tick_ms()-round(age*1000))
            nv12=pixel_format==1
            descriptor=DESCRIPTOR.pack(0x46534355,1,64,pixel_format,width,height,width if nv12 else width*4,width if nv12 else 0,width*height if nv12 else 0,len(data),self.published,
                max(0,round((arrival-self.started)*1e7)),1 if nv12 else 2,1 if pixel_format==3 else 0)
            header=REPLY.pack(0x52534355,1,1,len(descriptor)+len(data),0,captured,self.epoch)
            self.last_arrival=arrival;self.latest=(arrival,pixel_format,header+descriptor+data);self.condition.notify_all();return True
    def request(self,data,wait=.035):
        if len(data)!=REQUEST.size:raise ValueError('Invalid frame request size')
        magic,version,header,format,width,height,reserved=REQUEST.unpack(data)
        if magic!=0x51534355 or version!=1 or header!=24 or reserved or format not in (1,2,3) or not 2<=width<=16384 or not 2<=height<=16384:
            raise ValueError('Invalid frame request')
        size=width*height*3//2 if format==1 else width*height*4
        if size>MAX_PAYLOAD or (format==1 and (width%2 or height%2)):raise ValueError('Frame request exceeds bounds')
        empty=REPLY.pack(0x52534355,1,0,0,0,0,self.epoch)
        with self.condition:
            self.requests+=1
            if format not in self.formats or self.stopped or self.error:return empty
            if self.pixel_format!=format or self.mode!=(width,height):self.latest=None
            self.pixel_format=format
            self.mode=(width,height);self.until=self.clock()+.2
            if self.canvas is not None and self.canvas!=self.mode:return empty
            deadline=time.monotonic()+max(0,wait)
            while not self.stopped:
                if self.latest and self.latest[1]==format and self.clock()-self.latest[0]<=.25:return self.latest[2]
                remaining=deadline-time.monotonic()
                if remaining<=0:break
                self.condition.wait(remaining)
            return empty
    def disconnect(self):
        with self.condition:self.until=0.;self.mode=None;self.pixel_format=None;self.latest=None;self.condition.notify_all()
    def fail(self):
        with self.condition:self.error='Frame output unavailable';self.latest=None;self.until=0.;self.condition.notify_all()
    def close(self):
        with self.condition:self.stopped=True;self.latest=None;self.until=0.;self.condition.notify_all()
    def snapshot(self):
        with self.condition:return {'frame_output_enabled':True,'frame_output_published':self.published,
            'frame_output_requests':self.requests,'frame_output_rejected':self.rejected,'frame_output_error':self.error,
            'frame_output_canvas':self.canvas,'frame_output_queue_capacity':1,'frame_output_pixel_format':self.pixel_format,'frame_output_formats':self.formats}


class FramePublisher(FrameOutput):
    def __init__(self,metadata=None,pipe_name=None,epoch=None,formats=(2,),enabled=True,pipe_instances=4,allow_frame_services=True):
        super().__init__(epoch=epoch,formats=formats)
        self.server=None;self.enabled=False;self.camera_registered=False;self.lifecycle_lock=threading.RLock();self.metadata_lock=threading.Lock()
        self.pipe_name=pipe_name or ('\\\\.\\pipe\\UCS.FrameBridge.'+str(uuid.uuid4()))
        self.metadata=Path(metadata) if metadata else None;self.pipe_instances=pipe_instances;self.allow_frame_services=allow_frame_services
        if enabled:self.enable()
    def enable(self):
        from .frame_pipe_windows import PipeServer
        with self.lifecycle_lock:
            if self.enabled:return
            if self.stopped:raise RuntimeError('Frame output already closed')
            self.error='';server=PipeServer(self.pipe_name,self.pipe_instances,self.allow_frame_services)
            try:server.start(self)
            except Exception:server.close();raise
            self.server=server;self.tick_ms=server.tick_ms;self.enabled=True
            if self.metadata:self.metadata.parent.mkdir(parents=True,exist_ok=True);self.write_endpoint()
    def wanted(self):return self.enabled and super().wanted()
    def endpoint(self):
        value={'schema':1,'pipe_name':self.pipe_name,'producer_pid':os.getpid(),'epoch':self.epoch,
               'owner_sid':self.server.owner_sid if self.server else None,'canvas':self.canvas,'formats':self.formats,'camera_registered':self.camera_registered}
        if self.formats==(3,):
            # JSON numbers cannot represent a 64-bit epoch exactly in Lua.
            value.update(epoch_hex=f'{self.epoch:016x}',alpha_mode='premultiplied',
                         width=self.canvas[0] if self.canvas else 0,height=self.canvas[1] if self.canvas else 0)
        return value
    def mark_camera_registered(self,value):
        self.camera_registered=bool(value)
        if self.metadata and self.enabled:self.write_endpoint()
    def set_canvas(self,width,height):
        changed=self.canvas!=(width,height);super().set_canvas(width,height)
        if changed and self.metadata and self.enabled:self.write_endpoint()
    def write_endpoint(self):
        with self.metadata_lock:
            if not self.enabled:return
            temporary=self.metadata.with_name(self.metadata.name+'.tmp')
            temporary.write_text(json.dumps(self.endpoint(),indent=2)+'\n',encoding='utf-8');temporary.replace(self.metadata)
    def remove_endpoint(self):
        with self.metadata_lock:
            if self.metadata and self.metadata.exists():
                try:
                    current=json.loads(self.metadata.read_text(encoding='utf-8'))
                    if current.get('producer_pid')==os.getpid() and current.get('epoch')==self.epoch:self.metadata.unlink()
                except (OSError,ValueError):pass
    def disable(self):
        with self.lifecycle_lock:
            self.enabled=False;super().disconnect()
            if self.server:self.server.close();self.server=None
            self.remove_endpoint()
    def close(self):
        with self.lifecycle_lock:super().close();self.disable()
    def snapshot(self):return dict(super().snapshot(),frame_output_enabled=self.enabled)
