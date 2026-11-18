"""Experimental local portrait matting; one frame in flight, no camera recording.

Result carries its source frame. Never paste an older matte onto a newer frame.
NVIDIA maintains per-stream temporal state; MODNet is the stateless baseline.
Neither FPS nor successful inference certifies quality on moving hair/hands.
"""
from collections import deque
import hashlib,json,math,threading,time
from pathlib import Path

class BackgroundState:
    def __init__(self):
        self.lock=threading.Lock();self.mode='off';self.image=None;self.generation=0;self.quality='quality';self.solidity=0.
    def set(self,mode=None,image=None,quality=None,solidity=None):
        if solidity is not None and (type(solidity) not in (int,float) or not math.isfinite(solidity) or not 0<=solidity<=100):
            raise ValueError('Invalid foreground solidity')
        with self.lock:
            if mode is not None:
                if mode not in ('off','transparent','image','motion'):raise ValueError('Invalid background mode')
                self.mode=mode
            if image is not None:self.image=str(Path(image).resolve())
            if quality is not None:
                if quality not in ('quality','performance'):raise ValueError('Invalid quality profile')
                self.quality=quality
            if self.mode in ('image','motion') and self.image is None:self.mode='transparent'
            if solidity is not None:self.solidity=float(solidity)
            # A post-processing control must not reset the temporal AI model or
            # discard its in-flight result. Preserve existing core transitions.
            if solidity is None or mode is not None or image is not None or quality is not None:self.generation+=1
    def get(self):
        with self.lock:return {'mode':self.mode,'image':self.image,'generation':self.generation,'quality':self.quality,'solidity':self.solidity}

def model_path():
    root=Path(__file__).resolve().parents[1]
    record=json.loads((root/'docs/MODELS.lock.json').read_text())['modnet-webcam']
    path=root/'runtime/models/modnet-webcam.onnx'
    if not path.is_file() or path.stat().st_size!=record['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:
        raise RuntimeError('Modelo local ausente ou diferente. Execute tools/install_matting.py.')
    return path

def small_rgb(frame,target_width,target_height,angle=0,mirror=False):
    """Match SDL: source mirror, then rotation. Work on the small image only."""
    import numpy as np
    if angle not in (0,90,180,270):raise ValueError('Invalid input orientation')
    width,height=(frame.height,frame.width) if angle in (90,270) else (frame.width,frame.height)
    scale=min(target_width/width,target_height/height);w=max(1,round(width*scale));h=max(1,round(height*scale))
    raw_w,raw_h=(h,w) if angle in (90,270) else (w,h)
    rgb=frame.to_ndarray(format='rgb24',width=raw_w,height=raw_h,interpolation='FAST_BILINEAR')
    if mirror:rgb=rgb[:,::-1]
    if angle:rgb=np.rot90(rgb,-angle//90)
    left=(target_width-w)//2;top=(target_height-h)//2
    canvas=np.zeros((target_height,target_width,3),dtype=np.uint8)
    canvas[top:top+h,left:left+w]=rgb
    return canvas,(left,top,w,h)

def frame_tensor(frame,size=256,angle=0,mirror=False):
    import numpy as np
    canvas,region=small_rgb(frame,size,size,angle,mirror)
    tensor=np.ascontiguousarray(((canvas.astype(np.float32)/127.5)-1).transpose(2,0,1)[None])
    return tensor,region

def restore_alpha(alpha,region,angle=0,mirror=False):
    import numpy as np
    left,top,w,h=region
    source=np.rot90(alpha[top:top+h,left:left+w],angle//90)
    if mirror:source=source[:,::-1]
    return np.ascontiguousarray(source)

class PortraitModel:
    def __init__(self,backend='directml'):
        import onnxruntime as ort
        if backend not in ('directml','cuda'):raise ValueError('Unsupported matting backend')
        provider='CUDAExecutionProvider' if backend=='cuda' else 'DmlExecutionProvider'
        if provider not in ort.get_available_providers():
            raise RuntimeError('Backend '+backend+' indisponivel neste ambiente. Nenhum fallback CPU foi ativado.')
        if backend=='cuda':
            from .cuda_runtime import prepare
            prepare()
        options=ort.SessionOptions();options.intra_op_num_threads=1;options.inter_op_num_threads=1
        options.enable_mem_pattern=False;options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
        options.add_session_config_entry('session.disable_cpu_ep_fallback','1')
        provider_config=(provider,{'gpu_mem_limit':str(256*1024*1024),'cudnn_conv_algo_search':'HEURISTIC',
            'cudnn_conv_use_max_workspace':'0'}) if backend=='cuda' else provider
        self.session=ort.InferenceSession(str(model_path()),sess_options=options,providers=[provider_config])
        self.session.disable_fallback()
        if self.session.get_providers()[0]!=provider:raise RuntimeError('Requested GPU provider did not activate')
        self.provider=provider;self.name=self.session.get_inputs()[0].name
    def infer(self,frame,angle=0,mirror=False):
        import numpy as np
        tensor,region=frame_tensor(frame,angle=angle,mirror=mirror)
        output=self.session.run(None,{self.name:tensor})[0]
        if output.shape!=(1,1,256,256) or not np.isfinite(output).all():raise ValueError('Invalid alpha prediction')
        return restore_alpha((np.clip(output[0,0],0,1)*255).round().astype(np.uint8),region,angle,mirror)

class IsolatedPortraitModel:
    """Keep CUDA libraries/model out of the desktop and release them on disabling the effect."""
    def __init__(self,backend,quality='quality'):
        import os,subprocess,sys
        root=Path(__file__).resolve().parents[1]
        python=root/'.venv-matting-cuda/Scripts/python.exe' if backend=='cuda' else Path(sys.executable)
        if python.name.lower()=='pythonw.exe':python=python.with_name('python.exe')
        if not python.is_file():raise RuntimeError('Ambiente CUDA isolado nao encontrado.')
        folder=root/'output/matting-runtime';folder.mkdir(parents=True,exist_ok=True)
        self.log=open(folder/(backend+'-worker.stderr.log'),'ab')
        self.process=None;self.job=None
        try:
            self.process=subprocess.Popen([str(python),'-u','-m','ucs.matting_inference','--backend',backend,'--quality',quality],cwd=root,
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            from .process_job import ProcessJob
            self.job=ProcessJob(self.process)
        except Exception:
            if self.process:
                self.process.terminate();self.process.wait(timeout=2)
                self.process.stdin.close();self.process.stdout.close()
            self.log.close();raise
        self.backend=backend;self.ready=False;self.deadline=0;self.watch_stop=threading.Event()
        self.watcher=threading.Thread(target=self._watch,daemon=True);self.watcher.start()
    def _watch(self):
        while not self.watch_stop.wait(.1):
            if self.deadline and time.monotonic()>self.deadline:self.cancel();return
    def _exact(self,n):
        result=bytearray()
        while len(result)<n:
            data=self.process.stdout.read(n-len(result))
            if not data:raise RuntimeError('O processo de recorte encerrou. Volte ao original e tente novamente.')
            result.extend(data)
        return bytes(result)
    def infer(self,frame,angle=0,mirror=False):
        import struct,numpy as np
        # A stalled DLL/model must not keep an orphan GPU process indefinitely.
        self.deadline=time.monotonic()+(20 if not self.ready else 2)
        try:
            if not self.ready:
                reply = self._exact(4)
                if reply == b'FAIL':
                    size = struct.unpack('!I', self._exact(4))[0]
                    if size > 1024:
                        raise RuntimeError('Invalid matting worker error')
                    raise RuntimeError(self._exact(size).decode('utf-8', errors='replace'))
                if reply != b'READ':
                    raise RuntimeError('Invalid matting worker reply')
                self.ready=True
            if self.backend=='nvidia':
                rgb,region=small_rgb(frame,512,288,angle,mirror);data=np.ascontiguousarray(rgb[:,:,::-1]).tobytes()
                shape=(288,512)
            else:
                tensor,region=frame_tensor(frame,angle=angle,mirror=mirror);data=tensor.tobytes();shape=(256,256)
            self.process.stdin.write(struct.pack('!I',len(data))+data);self.process.stdin.flush()
            size=struct.unpack('!I',self._exact(4))[0]
            if size!=shape[0]*shape[1]:raise RuntimeError('Invalid mask reply size')
            alpha=np.frombuffer(self._exact(size),dtype=np.uint8).reshape(shape)
            return restore_alpha(alpha,region,angle,mirror)
        finally:self.deadline=0
    def reset(self):
        if not self.ready:return
        import struct
        self.deadline=time.monotonic()+2
        try:
            self.process.stdin.write(struct.pack('!I',0));self.process.stdin.flush()
            if self._exact(4)!=b'RSET':raise RuntimeError('Invalid state reset reply')
        finally:self.deadline=0
    def cancel(self):
        if self.job:self.job.terminate()
        if self.process.poll() is None:
            try:self.process.terminate()
            except OSError:pass
    def close(self):
        self.watch_stop.set()
        self.cancel()
        try:self.process.wait(timeout=2)
        except Exception:self.process.kill();self.process.wait(timeout=2)
        for stream in (self.process.stdin,self.process.stdout):
            try:stream.close()
            except OSError:pass
        self.log.close()
        if self.job:self.job.close()

class MatteWorker:
    def __init__(self,state,backend='directml',factory=None):
        from .live_preview import LatestFrame
        self.state=state;self.backend=backend;self.factory=factory or (lambda:IsolatedPortraitModel(backend,self.state.get()['quality']))
        self.jobs=LatestFrame();self.results=LatestFrame();self.stop=threading.Event()
        self.lock=threading.Lock();self.status='off';self.error='';self.times=deque(maxlen=120);self.count=0;self.stale=0;self.active_model=None
        self.suspended=False;self.work_epoch=0
        self.thread=threading.Thread(target=self._run,daemon=True);self.thread.start()
    def submit(self,item,generation,angle=0,camera_revision=0,mirror=False):
        with self.lock:
            if self.suspended:return
        self.jobs.put((item,generation,angle,camera_revision,mirror))
    def set_suspended(self,value):
        with self.lock:
            if self.suspended==value:return
            self.suspended=value;self.work_epoch+=1
        if value:self.jobs.take(timeout=0);self.results.take(timeout=0)
    def _run(self):
        model=None;failed_generation=None;context=None;loaded_quality=None
        while not self.stop.is_set():
            job=self.jobs.take(timeout=.1)
            if self.state.get()['mode']=='off':
                if hasattr(model,'close'):model.close()
                self.results.take(timeout=0)
                model=None
                with self.lock:self.status='off';self.error='';self.active_model=None
                continue
            if job is None:continue
            with self.lock:paused=self.suspended;work_epoch=self.work_epoch
            if paused:continue
            item,generation,angle,camera_revision,mirror=job
            if generation!=self.state.get()['generation'] or failed_generation==generation:continue
            try:
                quality=self.state.get()['quality']
                if model is not None and loaded_quality!=quality:
                    if hasattr(model,'close'):model.close()
                    model=None;context=None
                if model is None:
                    with self.lock:self.status='loading'
                    model=self.factory()
                    loaded_quality=quality;context=None
                    with self.lock:self.active_model=model
                frame,seq,arrival=item
                if time.perf_counter()-arrival>.25:
                    with self.lock:self.stale+=1
                    continue
                current_context=(generation,angle,mirror,camera_revision)
                start=time.perf_counter()
                work_context=(*current_context,work_epoch)
                if context is not None and work_context!=context and hasattr(model,'reset'):model.reset()
                context=work_context;alpha=model.infer(frame,angle=angle,mirror=mirror)
                elapsed=(time.perf_counter()-start)*1000
                with self.lock:obsolete=self.suspended or work_epoch!=self.work_epoch
                if obsolete:continue
                if self.stop.is_set() or generation!=self.state.get()['generation']:continue
                if time.perf_counter()-arrival>.25:
                    with self.lock:self.stale+=1;self.status='late'
                    continue
                with self.lock:
                    if self.suspended or work_epoch!=self.work_epoch:continue
                    self.times.append(elapsed);self.count+=1;self.status='ready';self.error=''
                    self.results.put((frame,seq,arrival,alpha,generation,current_context))
            except Exception as exc:
                if hasattr(model,'close'):model.close()
                failed_generation=generation;model=None
                current=self.state.get()
                with self.lock:
                    self.status='off' if current['mode']=='off' else 'error'
                    self.error='' if current['mode']=='off' else str(exc)[:180];self.active_model=None
        if hasattr(model,'close'):model.close()
        model=None
    def take(self,context=None):
        result=self.results.take(timeout=0)
        if result is None or result[4]!=self.state.get()['generation']:return None
        if context is not None and (len(result)<6 or result[5]!=context):return None
        if time.perf_counter()-result[2]>.25:
            with self.lock:self.stale+=1
            return None
        return result[:5]
    def snapshot(self):
        with self.lock:
            values=sorted(self.times)
            return {'matting_status':self.status,'matting_error':self.error,
                    'matting_suspended':self.suspended,
                    'matting_frames':self.count,'matting_backend':self.backend,
                    'matting_p95_ms':values[int((len(values)-1)*.95)] if values else None,
                    'matting_stale_discarded':self.stale,
                    'matting_queue_capacity':1,'matting_job_replaced':self.jobs.replaced}
    def close(self):
        self.stop.set();self.cancel();self.jobs.close();self.results.close();self.thread.join(timeout=2)
        return not self.thread.is_alive()
    def cancel(self):
        with self.lock:model=self.active_model
        if hasattr(model,'cancel'):model.cancel()
