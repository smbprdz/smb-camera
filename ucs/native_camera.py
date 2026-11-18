"""Optional installed webcam lifecycle. Native code is never loaded in Python."""
import json,os,subprocess,threading,time
from . import camera_runtime
from .process_job import ProcessJob

class NativeCamera:
    def __init__(self,publisher):
        self.publisher=publisher;self.lock=threading.Lock();self.stop_event=threading.Event();self.worker=None
        self.process=None;self.job=None;self.mode=None;self.state='off';self.detail='';self.closed=False
        self.directory=camera_runtime.installed_directory();self.last_installation_check=time.monotonic()
    def refresh_installation(self):
        if time.monotonic()-self.last_installation_check<5:return
        with self.lock:idle=self.state in ('off','error')
        if idle:
            directory=camera_runtime.installed_directory()
            with self.lock:self.directory=directory;self.last_installation_check=time.monotonic()
    def snapshot(self):
        with self.lock:return {'available':self.directory is not None,'state':self.state,'detail':self.detail,'mode':self.mode}
    def start(self,fps):
        with self.lock:
            if self.closed or self.state in ('starting','running','stopping'):return False
            if self.directory is None:self.detail='Componente Windows ainda não instalado.';return False
            if self.publisher.canvas is None:self.detail='Ative a câmera do iPhone primeiro.';return False
            self.mode=(*self.publisher.canvas,fps);self.state='starting';self.detail='Ativando webcam Windows...';self.stop_event.clear()
            self.worker=threading.Thread(target=self._run,args=(fps,),daemon=True);self.worker.start();return True
    def _run(self,fps):
        own_publisher=not self.publisher.enabled;timer=None;failure=False
        try:
            self.publisher.enable();endpoint=self.publisher.endpoint()
            directory=camera_runtime.installed_directory(endpoint['owner_sid'])
            if directory is None:raise RuntimeError('Installed native component belongs to another account')
            camera_runtime.write_endpoint(endpoint,fps)
            process=subprocess.Popen([str(directory/'SMBCameraHost.exe'),'--run'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            with self.lock:self.process=process
            self.job=ProcessJob(process)
            timer=threading.Timer(8,self._startup_timeout);timer.daemon=True;timer.start()
            line=process.stdout.readline(4097)
            if len(line)>4096 or not line or json.loads(line).get('status')!='ready':raise RuntimeError('Native webcam did not start')
            timer.cancel()
            if hasattr(self.publisher,'mark_camera_registered'):self.publisher.mark_camera_registered(True)
            with self.lock:self.state='running';self.detail='Webcam Windows ativa: SMB Camera.'
            while not self.stop_event.wait(.1):
                if process.poll() is not None:raise RuntimeError('Native webcam process exited')
        except Exception:
            failure=True
            with self.lock:self.detail='O Windows não iniciou ou interrompeu a webcam. Verifique a instalação e a assinatura do componente.'
        finally:
            if timer:timer.cancel()
            self._shutdown()
            if hasattr(self.publisher,'mark_camera_registered'):self.publisher.mark_camera_registered(False)
            camera_runtime.remove_endpoint(os.getpid(),self.publisher.epoch)
            if own_publisher:self.publisher.disable()
            with self.lock:
                self.state='error' if failure else 'off'
                if not failure and self.detail.startswith(('Ativando','Webcam')):self.detail='Webcam Windows desativada.'
    def _startup_timeout(self):
        with self.lock:starting=self.state in ('starting','stopping');job=self.job
        if starting and job:job.terminate()
    def _shutdown(self):
        process=self.process
        if process:
            try:
                if process.poll() is None:
                    try:process.stdin.write(b'stop\n');process.stdin.flush()
                    except (OSError,ValueError):pass
                    try:process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        if self.job:self.job.terminate()
                        else:process.terminate()
                        process.wait(timeout=2)
            finally:
                for stream in (process.stdin,process.stdout):
                    if stream:stream.close()
        if self.job:self.job.close()
        with self.lock:self.process=None;self.job=None
    def stop(self,reason=None):
        with self.lock:
            if reason:self.detail=reason
            if self.state in ('starting','running'):self.state='stopping'
        self.stop_event.set()
        # Also end a blocked native startup promptly; no UI-thread wait.
        if self.process and self.state=='stopping' and self.job:
            try:self.process.stdin.write(b'stop\n');self.process.stdin.flush()
            except (OSError,ValueError):pass
    def observe(self,canvas,fps):
        with self.lock:mode=self.mode;active=self.state in ('starting','running')
        if active and (canvas is None or (*canvas,fps)!=mode):self.stop('O formato mudou. Reative a webcam para aplicar o novo formato.')
    def close(self):
        self.closed=True;self.stop()
        worker=self.worker
        if worker and worker is not threading.current_thread():worker.join(timeout=10)
        if worker and worker.is_alive():
            if self.job:self.job.terminate()
            worker.join(timeout=2)
