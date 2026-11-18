"""Native D3D11 YUV preview via a pinned SDL2 build. No CPU YUV->BGR conversion.

PyAV currently returns CPU-visible frames after D3D11 decode (readback). SDL uploads
the YUV planes; this bridge is not an end-to-end zero-copy native decoder engine.
"""
import ctypes as C
import hashlib
import json
from pathlib import Path

NV12=int.from_bytes(b'NV12','little')
IYUV=int.from_bytes(b'IYUV','little')
RGBA32=0x16762004 # SDL_PIXELFORMAT_ABGR8888 on little-endian Windows.

class RendererInfo(C.Structure):
    _fields_=[('name',C.c_char_p),('flags',C.c_uint32),('count',C.c_uint32),
              ('formats',C.c_uint32*16),('max_width',C.c_int),('max_height',C.c_int)]
class Rect(C.Structure):
    _fields_=[('x',C.c_int),('y',C.c_int),('w',C.c_int),('h',C.c_int)]
class Event(C.Union):
    _fields_=[('type',C.c_uint32),('padding',C.c_uint8*56),('alignment',C.c_uint64)]

def native_path():
    root=Path(__file__).resolve().parents[1]
    info=json.loads((root/'docs/NATIVE.lock.json').read_text())['SDL2']
    path=root/'runtime/native'/('SDL2-'+info['version'])/'SDL2.dll'
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=info['dll_sha256']:
        raise RuntimeError('Pinned SDL2 runtime missing or changed; run tools/install_sdl.py')
    return path

class SDLPreview:
    def __init__(self,width,height,title='Universal Camera Studio',window_width=1280,window_height=720,hidden=False):
        self.dll=C.CDLL(str(native_path()))
        self.window=self.renderer=self.texture=None
        self.mask_texture=self.foreground_texture=self.background_texture=None
        self.mask_size=None;self.background_key=None
        self.width=width;self.height=height;self.pixel_format=None;self.frame_format=None
        self.colour_mode=None;self.hidden=hidden
        self.canvas=(width,height);self.preview_size=(window_width,window_height)
        self._bind()
        s=self.dll
        s.SDL_SetMainReady()
        s.SDL_SetHint(b'SDL_RENDER_SCALE_QUALITY',b'linear')
        self._check(s.SDL_InitSubSystem(0x20),'video init')
        try:
            self.window=s.SDL_CreateWindow(title.encode(),0x2fff0000,0x2fff0000,window_width,window_height,
                (0x8 if hidden else 0x4)|0x2000)
            if not self.window:raise RuntimeError(self.error('window'))
            driver=None
            for index in range(s.SDL_GetNumRenderDrivers()):
                info=RendererInfo()
                self._check(s.SDL_GetRenderDriverInfo(index,C.byref(info)),'driver info')
                if info.name==b'direct3d11':driver=index;break
            if driver is None:raise RuntimeError('Native D3D11 SDL renderer unavailable')
            self.renderer=s.SDL_CreateRenderer(self.window,driver,0x2) # Accelerated; no mandatory vsync wait.
            if not self.renderer:raise RuntimeError(self.error('renderer'))
            info=RendererInfo();self._check(s.SDL_GetRendererInfo(self.renderer,C.byref(info)),'renderer info')
            if info.name!=b'direct3d11' or not info.flags&0x2:
                raise RuntimeError('Renderer did not activate D3D11 acceleration')
            self.info={'name':info.name.decode(),'accelerated':bool(info.flags&2),
                       'max_texture_width':info.max_width,'max_texture_height':info.max_height,
                       'supported_formats':list(info.formats[:info.count])}
            self._check(s.SDL_RenderSetLogicalSize(self.renderer,width,height),'logical size')
            self._check(s.SDL_SetRenderDrawColor(self.renderer,0,0,0,255),'clear colour')
        except Exception:self.close();raise

    def _bind(self):
        p=C.c_void_p;i=C.c_int;u=C.c_uint32;char=C.c_char_p
        functions={
            'SDL_SetMainReady':([],None),'SDL_InitSubSystem':([u],i),'SDL_QuitSubSystem':([u],None),
            'SDL_SetHint':([char,char],i),'SDL_GetError':([],char),
            'SDL_CreateWindow':([char,i,i,i,i,u],p),'SDL_DestroyWindow':([p],None),
            'SDL_SetWindowSize':([p,i,i],None),'SDL_SetWindowTitle':([p,char],None),
            'SDL_GetNumRenderDrivers':([],i),'SDL_GetRenderDriverInfo':([i,C.POINTER(RendererInfo)],i),
            'SDL_CreateRenderer':([p,i,u],p),'SDL_DestroyRenderer':([p],None),
            'SDL_GetRendererInfo':([p,C.POINTER(RendererInfo)],i),
            'SDL_CreateTexture':([p,u,i,i,i],p),'SDL_DestroyTexture':([p],None),
            'SDL_UpdateTexture':([p,p,p,i],i),'SDL_SetTextureBlendMode':([p,i],i),
            'SDL_ComposeCustomBlendMode':([i,i,i,i,i,i],i),
            'SDL_SetRenderTarget':([p,p],i),'SDL_GetRenderTarget':([p],p),
            'SDL_UpdateNVTexture':([p,p,p,i,p,i],i),
            'SDL_UpdateYUVTexture':([p,p,p,i,p,i,p,i],i),
            'SDL_SetYUVConversionMode':([i],None),
            'SDL_RenderSetLogicalSize':([p,i,i],i),
            'SDL_SetRenderDrawColor':([p,C.c_uint8,C.c_uint8,C.c_uint8,C.c_uint8],i),
            'SDL_RenderClear':([p],i),'SDL_RenderCopy':([p,p,p,p],i),
            'SDL_RenderCopyEx':([p,p,p,p,C.c_double,p,i],i),
            'SDL_RenderPresent':([p],None),'SDL_PollEvent':([C.POINTER(Event)],i),
            'SDL_RenderReadPixels':([p,p,u,p,i],i),'SDL_GetRendererOutputSize':([p,C.POINTER(i),C.POINTER(i)],i)}
        functions['SDL_RenderGetViewport']=([p,C.POINTER(Rect)],None)
        functions['SDL_RenderSetViewport']=([p,C.POINTER(Rect)],i)
        for name,(args,result) in functions.items():
            fn=getattr(self.dll,name);fn.argtypes=args;fn.restype=result

    def error(self,stage):
        value=self.dll.SDL_GetError()
        return 'D3D11 preview '+stage+': '+(value.decode(errors='replace') if value else 'unknown')

    def _check(self,value,stage):
        if value<0:raise RuntimeError(self.error(stage))

    def upload(self,frame):
        if (frame.width,frame.height)!=(self.width,self.height):raise ValueError('Frame dimensions changed')
        name=frame.format.name
        pixel_format=NV12 if name=='nv12' else IYUV if name in ('yuv420p','yuvj420p') else None
        if pixel_format is None:raise ValueError('Native YUV preview requires NV12 or planar 8-bit YUV420')
        # Only negotiated BT.709 SDR is supported by the current capture protocol.
        colour_mode=0 if int(frame.color_range)==2 or name=='yuvj420p' else 2
        if colour_mode!=self.colour_mode:
            self.dll.SDL_SetYUVConversionMode(colour_mode)
            self.colour_mode=colour_mode
        if self.pixel_format!=pixel_format:
            if self.texture:self.dll.SDL_DestroyTexture(self.texture)
            self.texture=self.dll.SDL_CreateTexture(self.renderer,pixel_format,1,self.width,self.height)
            if not self.texture:raise RuntimeError(self.error('YUV texture'))
            self.pixel_format=pixel_format;self.frame_format=name
        planes=frame.planes
        if pixel_format==NV12:
            code=self.dll.SDL_UpdateNVTexture(self.texture,None,C.c_void_p(planes[0].buffer_ptr),planes[0].line_size,
                C.c_void_p(planes[1].buffer_ptr),planes[1].line_size)
        else:
            code=self.dll.SDL_UpdateYUVTexture(self.texture,None,C.c_void_p(planes[0].buffer_ptr),planes[0].line_size,
                C.c_void_p(planes[1].buffer_ptr),planes[1].line_size,C.c_void_p(planes[2].buffer_ptr),planes[2].line_size)
        self._check(code,'plane upload')

    def _rgba_texture(self,pixels):
        import numpy as np
        pixels=np.ascontiguousarray(pixels,dtype=np.uint8)
        h,w,_=pixels.shape
        texture=self.dll.SDL_CreateTexture(self.renderer,RGBA32,0,w,h)
        if not texture:raise RuntimeError(self.error('background texture'))
        try:self._check(self.dll.SDL_UpdateTexture(texture,None,C.c_void_p(pixels.ctypes.data),pixels.strides[0]),'image upload')
        except Exception:self.dll.SDL_DestroyTexture(texture);raise
        return texture

    def _background(self,mode,path,out_w,out_h):
        """Image decoded/uploaded once per choice, checker is a transparency preview only."""
        import numpy as np
        key=('image',path,out_w,out_h) if mode=='image' and path else ('checker',)
        if key!=self.background_key:
            if self.background_texture:self.dll.SDL_DestroyTexture(self.background_texture);self.background_texture=None
            if key[0]=='image':
                from PIL import Image,ImageOps
                with Image.open(path) as image:
                    if image.width*image.height>50_000_000:raise ValueError('Background image is too large')
                    image=ImageOps.exif_transpose(image).convert('RGBA')
                    # Only a preview background; no repeated disk load or full-frame CPU blend.
                    scale=min(1,1920/out_w,1080/out_h)
                    pixels=np.asarray(ImageOps.fit(image,(max(1,round(out_w*scale)),max(1,round(out_h*scale)))))
            else:
                yy,xx=np.indices((128,128));tone=np.where(((xx//16+yy//16)%2)==0,72,104).astype(np.uint8)
                pixels=np.empty((128,128,4),np.uint8);pixels[:,:,:3]=tone[:,:,None];pixels[:,:,3]=255
            self.background_texture=self._rgba_texture(pixels);self.background_key=key
        self._check(self.dll.SDL_RenderCopy(self.renderer,self.background_texture,None,None),'background draw')

    def _matte_foreground(self,alpha):
        import numpy as np
        if not isinstance(alpha,np.ndarray) or alpha.dtype!=np.uint8 or alpha.ndim!=2 or not all(0<n<=1024 for n in alpha.shape):
            raise ValueError('Invalid alpha mask')
        h,w=alpha.shape
        if self.mask_size!=(w,h):
            if self.mask_texture:self.dll.SDL_DestroyTexture(self.mask_texture)
            self.mask_texture=self.dll.SDL_CreateTexture(self.renderer,RGBA32,1,w,h)
            if not self.mask_texture:raise RuntimeError(self.error('mask texture'))
            # destination RGB and alpha *= source alpha, producing a premultiplied matte.
            mode=self.dll.SDL_ComposeCustomBlendMode(1,5,1,1,5,1)
            self._check(self.dll.SDL_SetTextureBlendMode(self.mask_texture,mode),'mask blend')
            self.mask_size=(w,h)
        rgba=np.full((h,w,4),255,np.uint8);rgba[:,:,3]=alpha
        self._check(self.dll.SDL_UpdateTexture(self.mask_texture,None,C.c_void_p(rgba.ctypes.data),rgba.strides[0]),'mask upload')
        if not self.foreground_texture:
            self.foreground_texture=self.dll.SDL_CreateTexture(self.renderer,RGBA32,2,self.width,self.height)
            if not self.foreground_texture:raise RuntimeError(self.error('alpha render target'))
            # Premultiplied foreground over the chosen background.
            mode=self.dll.SDL_ComposeCustomBlendMode(2,6,1,2,6,1)
            self._check(self.dll.SDL_SetTextureBlendMode(self.foreground_texture,mode),'foreground blend')
        previous=self.dll.SDL_GetRenderTarget(self.renderer)
        self._check(self.dll.SDL_SetRenderTarget(self.renderer,self.foreground_texture),'foreground target')
        try:
            self._check(self.dll.SDL_RenderSetLogicalSize(self.renderer,self.width,self.height),'foreground logical size')
            self._check(self.dll.SDL_RenderClear(self.renderer),'foreground clear')
            self._check(self.dll.SDL_RenderCopy(self.renderer,self.texture,None,None),'foreground colour')
            self._check(self.dll.SDL_RenderCopy(self.renderer,self.mask_texture,None,None),'foreground alpha')
        finally:
            self._check(self.dll.SDL_SetRenderTarget(self.renderer,previous),'restore window target')
            self._check(self.dll.SDL_RenderSetLogicalSize(self.renderer,*self.canvas),'restore window size')
        return self.foreground_texture

    def draw(self,angle=0,mirror=False,output_format='landscape',pan_x=0.,pan_y=0.,alpha=None,background=None):
        from .view_transform import crop_geometry
        geometry=crop_geometry(self.width,self.height,angle,output_format,pan_x,pan_y)
        out_w,out_h=geometry['canvas']
        if self.canvas!=(out_w,out_h):
            self._check(self.dll.SDL_RenderSetLogicalSize(self.renderer,out_w,out_h),'rotated logical size')
            self.canvas=(out_w,out_h)
            if not self.hidden:
                # Match the window to the selected canvas; no portrait image inside a horizontal frame.
                scale=min(self.preview_size[0]/out_w,self.preview_size[1]/out_h)
                self.dll.SDL_SetWindowSize(self.window,max(1,round(out_w*scale)),max(1,round(out_h*scale)))
                self.dll.SDL_SetWindowTitle(self.window,f'Universal Camera Studio - GPU {out_w}x{out_h}'.encode())
        self._check(self.dll.SDL_RenderClear(self.renderer),'clear')
        if not background or background.get('mode')=='off':self.release_effect()
        texture=self.texture
        if background and background.get('mode')!='off':
            self._background(background['mode'],background.get('image'),out_w,out_h)
            if alpha is None:return # Pending/error: keep source background hidden, no stale mask.
            texture=self._matte_foreground(alpha)
        source=Rect(*geometry['source']);rect=Rect(*geometry['destination'])
        self._check(self.dll.SDL_RenderCopyEx(self.renderer,texture,C.byref(source),C.byref(rect),float(angle),None,1 if mirror else 0),'draw')

    def clear(self):
        self._check(self.dll.SDL_SetRenderDrawColor(self.renderer,0,0,0,255),'clear color')
        self._check(self.dll.SDL_RenderClear(self.renderer),'clear stale preview')

    def present(self):self.dll.SDL_RenderPresent(self.renderer)

    def poll(self):
        event=Event()
        while self.dll.SDL_PollEvent(C.byref(event)):
            if event.type==0x100:return False
            if event.type==0x200 and event.padding[12]==14:return False
            if event.type==0x300 and int.from_bytes(bytes(event.padding[20:24]),'little',signed=True) in (27,113):return False
        return True

    def pixels(self):
        """Validation-only readback; never used in live rendering."""
        w=C.c_int();h=C.c_int();self._check(self.dll.SDL_GetRendererOutputSize(self.renderer,C.byref(w),C.byref(h)),'output size')
        import numpy as np
        pixels=np.empty((h.value,w.value,4),dtype=np.uint8)
        viewport=Rect();self.dll.SDL_RenderGetViewport(self.renderer,C.byref(viewport))
        self._check(self.dll.SDL_RenderSetViewport(self.renderer,None),'test full viewport')
        try:self._check(self.dll.SDL_RenderReadPixels(self.renderer,None,RGBA32,C.c_void_p(pixels.ctypes.data),w.value*4),'test readback')
        finally:self.dll.SDL_RenderSetViewport(self.renderer,C.byref(viewport))
        return pixels

    def alpha_pixels(self):
        """Validation-only RGBA foreground readback. Not an OBS output or live export."""
        if not self.foreground_texture:raise RuntimeError('No matte render target')
        import numpy as np
        previous=self.dll.SDL_GetRenderTarget(self.renderer)
        self._check(self.dll.SDL_SetRenderTarget(self.renderer,self.foreground_texture),'test alpha target')
        pixels=np.empty((self.height,self.width,4),np.uint8)
        try:
            self.dll.SDL_RenderSetLogicalSize(self.renderer,self.width,self.height)
            self.dll.SDL_RenderSetViewport(self.renderer,None)
            self._check(self.dll.SDL_RenderReadPixels(self.renderer,None,RGBA32,C.c_void_p(pixels.ctypes.data),self.width*4),'test alpha readback')
        finally:
            self.dll.SDL_SetRenderTarget(self.renderer,previous);self.dll.SDL_RenderSetLogicalSize(self.renderer,*self.canvas)
        return pixels

    def release_effect(self):
        for name in ('mask_texture','foreground_texture','background_texture'):
            texture=getattr(self,name)
            if texture:self.dll.SDL_DestroyTexture(texture);setattr(self,name,None)
        self.mask_size=None;self.background_key=None

    def close(self):
        self.release_effect()
        if self.texture:self.dll.SDL_DestroyTexture(self.texture);self.texture=None
        if self.renderer:self.dll.SDL_DestroyRenderer(self.renderer);self.renderer=None
        if self.window:self.dll.SDL_DestroyWindow(self.window);self.window=None
        self.dll.SDL_QuitSubSystem(0x20)
