"""Own adapter for documented NvVFX/NvCVImage C APIs, runtime 0.7.6 Ampere.

No OBS code. Vendor descriptors are allocated/destroyed by NvCVImage_Create,
so no private C struct layout is assumed. Runtime/model license is separate.
"""
import ctypes as C
import hashlib,json,os
from pathlib import Path

class NvidiaMatte:
    width=512;height=288
    def __init__(self,mode=2):
        import numpy as np
        if mode not in (0,1,2,3):raise ValueError('Invalid NVIDIA quality mode')
        root=Path(__file__).resolve().parents[1]
        self.folder=root/'runtime/nvidia-vfx-0.7.6'
        record=json.loads((root/'docs/NVIDIA-VFX.lock.json').read_text(encoding='utf-8'))
        for row in record['files']:
            path=self.folder/row['path']
            if not path.is_file() or path.stat().st_size!=row['bytes']:
                raise RuntimeError('Runtime NVIDIA ausente ou diferente do pacote verificado.')
            with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
            if digest!=row['sha256']:raise RuntimeError('Runtime NVIDIA diferente do pacote verificado.')
        self.dll_path=os.add_dll_directory(str(self.folder));self.images=[]
        self.effect=C.c_void_p();self.stream=C.c_void_p();self.state=C.c_void_p()
        self.image=C.CDLL(str(self.folder/'NVCVImage.dll'))
        self.vfx=C.CDLL(str(self.folder/'NVVideoEffects.dll'))
        self.cuda=C.CDLL(str(self.folder/'cudart64_12.dll'))
        p=C.c_void_p;u=C.c_uint;i=C.c_int;s=C.c_char_p
        for dll,name,args,result in [
            (self.image,'NvCVImage_Create',[u,u,i,i,u,u,u,C.POINTER(p)],i),
            (self.image,'NvCVImage_Destroy',[p],None),(self.image,'NvCVImage_Dealloc',[p],None),
            (self.image,'NvCVImage_Init',[p,u,u,i,p,i,i,u,u],i),
            (self.image,'NvCVImage_Transfer',[p,p,C.c_float,p,p],i),
            (self.image,'NvCV_GetErrorStringFromCode',[i],s),
            (self.vfx,'NvVFX_GetVersion',[C.POINTER(u)],i),
            (self.vfx,'NvVFX_CreateEffect',[s,C.POINTER(p)],i),
            (self.vfx,'NvVFX_DestroyEffect',[p],i),
            (self.vfx,'NvVFX_SetString',[p,s,s],i),
            (self.vfx,'NvVFX_SetU32',[p,s,u],i),(self.vfx,'NvVFX_SetImage',[p,s,p],i),
            (self.vfx,'NvVFX_CudaStreamCreate',[C.POINTER(p)],i),
            (self.vfx,'NvVFX_CudaStreamDestroy',[p],i),
            (self.vfx,'NvVFX_SetCudaStream',[p,s,p],i),
            (self.vfx,'NvVFX_Load',[p],i),(self.vfx,'NvVFX_Run',[p,i],i),
            (self.vfx,'NvVFX_AllocateState',[p,C.POINTER(p)],i),
            (self.vfx,'NvVFX_SetStateObjectHandleArray',[p,s,C.POINTER(p)],i),
            (self.vfx,'NvVFX_ResetState',[p,p],i),
            (self.vfx,'NvVFX_DeallocateState',[p,p],i),
            (self.cuda,'cudaStreamSynchronize',[p],i)]:
            function=getattr(dll,name);function.argtypes=args;function.restype=result
        try:
            version=u();self.check(self.vfx.NvVFX_GetVersion(C.byref(version)))
            if version.value!=0x00070600:raise RuntimeError('Unexpected NVIDIA VFX runtime version: '+hex(version.value))
            self.check(self.vfx.NvVFX_CreateEffect(b'GreenScreen',C.byref(self.effect)))
            self.check(self.vfx.NvVFX_CudaStreamCreate(C.byref(self.stream)))
            self.check(self.vfx.NvVFX_SetCudaStream(self.effect,b'CudaStream',self.stream))
            self.check(self.vfx.NvVFX_SetString(self.effect,b'ModelDir',str(self.folder/'models').encode('utf-8')))
            self.check(self.vfx.NvVFX_SetU32(self.effect,b'Mode',mode))
            self.src=self.create(512,288,5,1);self.dst=self.create(512,288,2,1) # BGR and alpha, GPU.
            self.host_in=self.create(1,1,5,0);self.image.NvCVImage_Dealloc(self.host_in)
            self.host_out=self.create(1,1,2,0);self.image.NvCVImage_Dealloc(self.host_out)
            self.alpha=np.empty((288,512),np.uint8)
            self.check(self.image.NvCVImage_Init(self.host_out,512,288,512,C.c_void_p(self.alpha.ctypes.data),2,1,0,0))
            self.check(self.vfx.NvVFX_SetImage(self.effect,b'SrcImage0',self.src))
            self.check(self.vfx.NvVFX_SetImage(self.effect,b'DstImage0',self.dst))
            self.check(self.vfx.NvVFX_Load(self.effect))
            self.check(self.vfx.NvVFX_AllocateState(self.effect,C.byref(self.state)))
            self.check(self.vfx.NvVFX_SetStateObjectHandleArray(self.effect,b'State',C.byref(self.state)))
        except Exception:self.close();raise
    def check(self,code):
        if code:
            message=self.image.NvCV_GetErrorStringFromCode(code)
            raise RuntimeError('NVIDIA VFX '+str(code)+': '+(message.decode(errors='replace') if message else 'unknown error'))
    def create(self,width,height,format,space):
        pointer=C.c_void_p()
        self.check(self.image.NvCVImage_Create(width,height,format,1,0,space,1,C.byref(pointer)))
        self.images.append(pointer);return pointer
    def infer_bgr(self,bgr):
        import numpy as np
        if bgr.shape!=(288,512,3) or bgr.dtype!=np.uint8 or not bgr.flags.c_contiguous:raise ValueError('Invalid NVIDIA BGR input')
        self.check(self.image.NvCVImage_Init(self.host_in,512,288,1536,C.c_void_p(bgr.ctypes.data),5,1,0,0))
        self.check(self.image.NvCVImage_Transfer(self.host_in,self.src,1.0,self.stream,None))
        self.check(self.vfx.NvVFX_Run(self.effect,0))
        self.check(self.image.NvCVImage_Transfer(self.dst,self.host_out,1.0,self.stream,None))
        code=self.cuda.cudaStreamSynchronize(self.stream)
        if code:raise RuntimeError('NVIDIA CUDA stream failed: '+str(code))
        return self.alpha.copy()
    def reset(self):self.check(self.vfx.NvVFX_ResetState(self.effect,self.state))
    def close(self):
        if self.state.value:self.vfx.NvVFX_DeallocateState(self.effect,self.state);self.state=C.c_void_p()
        if self.effect.value:self.vfx.NvVFX_DestroyEffect(self.effect);self.effect=C.c_void_p()
        for image in self.images:self.image.NvCVImage_Destroy(image)
        self.images.clear()
        if self.stream.value:self.vfx.NvVFX_CudaStreamDestroy(self.stream);self.stream=C.c_void_p()
        self.dll_path.close()
