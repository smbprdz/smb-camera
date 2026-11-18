"""Own GPU YUV/grading/alpha renderer. SDL owns only the window/context wrapper.

Input remains CPU-visible YUV from PyAV, uploaded once; this is not zero-copy.
No CPU full-resolution RGB conversion, blend or grading. Readback is opt-in.
"""
import ctypes as C
from pathlib import Path
from .sdl_preview import native_path,Event
from .color import ColorState

class GLPreview:
    def __init__(self,width,height,title='Universal Camera Studio',window_width=1280,window_height=720,hidden=False,hwnd=None):
        import moderngl
        self.mgl=moderngl;self.width=width;self.height=height;self.hidden=hidden;self.hwnd=hwnd
        self.window=self.context=self.gl=None;self.planes=[];self.mask=self.background=None
        self.foreground=self.fbo=self.grade=self.compose=self.grade_vao=self.compose_vao=self.lut=None
        self.mask_size=None;self.background_key=None;self.lut_key=None;self.color_key=None;self.alpha_gain=None
        self.motion=None;self.motion_frame=None;self.motion_error=''
        self.format_key=None;self.frame=None;self.canvas=(width,height);self.preview_size=(window_width,window_height)
        self.output_program=self.output_vao=self.output_texture=self.output_fbo=None
        self.output_size=None;self.output_format=None;self.last_scene=None;self.output_reads=0
        self.default_color=ColorState().get();self.dll=C.CDLL(str(native_path()));s=self.dll
        p=C.c_void_p;i=C.c_int;u=C.c_uint;char=C.c_char_p
        for name,args,result in (
            ('SDL_SetMainReady',[],None),('SDL_InitSubSystem',[u],i),('SDL_QuitSubSystem',[u],None),
            ('SDL_SetHint',[char,char],i),('SDL_GL_SetAttribute',[i,i],i),
            ('SDL_CreateWindow',[char,i,i,i,i,u],p),('SDL_CreateWindowFrom',[p],p),
            ('SDL_GL_CreateContext',[p],p),('SDL_GL_MakeCurrent',[p,p],i),('SDL_GL_DeleteContext',[p],None),
            ('SDL_GL_SetSwapInterval',[i],i),('SDL_GL_SwapWindow',[p],None),
            ('SDL_GL_GetDrawableSize',[p,C.POINTER(i),C.POINTER(i)],None),
            ('SDL_SetWindowSize',[p,i,i],None),('SDL_SetWindowTitle',[p,char],None),
            ('SDL_DestroyWindow',[p],None),('SDL_PollEvent',[C.POINTER(Event)],i),('SDL_GetError',[],char)):
            fn=getattr(s,name);fn.argtypes=args;fn.restype=result
        s.SDL_SetMainReady();self.check(s.SDL_InitSubSystem(0x20))
        try:
            for attr,value in ((17,3),(18,3),(21,1),(5,1),(6,0)):self.check(s.SDL_GL_SetAttribute(attr,value))
            if hwnd:
                s.SDL_SetHint(b'SDL_VIDEO_FOREIGN_WINDOW_OPENGL',b'1')
                self.window=s.SDL_CreateWindowFrom(C.c_void_p(hwnd))
            else:self.window=s.SDL_CreateWindow(title.encode(),0x2fff0000,0x2fff0000,window_width,window_height,2|32|8192|(8 if hidden else 4))
            if not self.window:raise RuntimeError(self.error())
            self.context=s.SDL_GL_CreateContext(self.window)
            if not self.context:raise RuntimeError(self.error())
            self.check(s.SDL_GL_MakeCurrent(self.window,self.context));s.SDL_GL_SetSwapInterval(0)
            self.gl=moderngl.create_context(require=330);g=self.gl
            name=g.info.get('GL_RENDERER','')
            if any(x in name.lower() for x in ('llvmpipe','softpipe','gdi generic','software')):raise RuntimeError('Renderer GPU indisponivel.')
            self.info={'name':'OpenGL','renderer':name,'vendor':g.info.get('GL_VENDOR'),
                'version':g.version_code,'accelerated':True,'embedded':bool(hwnd)}
            shaders=Path(__file__).with_name('shaders');vertex=(shaders/'fullscreen.vert').read_text(encoding='utf-8')
            self.grade=g.program(vertex_shader=vertex,fragment_shader=(shaders/'grade.frag').read_text(encoding='utf-8'))
            self.compose=g.program(vertex_shader=vertex,fragment_shader=(shaders/'compose.frag').read_text(encoding='utf-8'))
            self.grade_vao=g.vertex_array(self.grade,[]);self.compose_vao=g.vertex_array(self.compose,[])
            for name,unit in [('plane_y',0),('plane_u',1),('plane_v',2),('alpha_mask',3),('grade_lut',4)]:self.grade[name]=unit
            self.compose['foreground']=0;self.compose['background_image']=1
            self.grade['source_size']=(width,height)
            self.foreground=g.texture((width,height),4,dtype='f1');self.configure(self.foreground)
            self.fbo=g.framebuffer([self.foreground])
            self.background=g.texture((1,1),4,bytes([0,0,0,255]));self.configure(self.background)
            self.mask=g.texture((1,1),1,b'\x00');self.configure(self.mask);self.mask_size=(1,1)
            self._set_color(self.default_color)
        except Exception:self.close();raise
    def error(self):return 'GPU: '+self.dll.SDL_GetError().decode(errors='replace')
    def check(self,code):
        if code<0:raise RuntimeError(self.error())
    def configure(self,texture):
        texture.filter=(self.mgl.LINEAR,self.mgl.LINEAR);texture.repeat_x=False;texture.repeat_y=False
    def upload(self,frame):
        self.last_scene=None
        if (frame.width,frame.height)!=(self.width,self.height):raise ValueError('Frame dimensions changed')
        name=frame.format.name
        if name not in ('nv12','yuv420p','yuvj420p'):raise ValueError('GPU requires 8-bit YUV420/NV12')
        components=[1,2] if name=='nv12' else [1,1,1]
        sizes=[(p.line_size//n,p.buffer_size//p.line_size) for p,n in zip(frame.planes,components)]
        key=(name,tuple(sizes))
        if key!=self.format_key:
            for texture in self.planes:texture.release()
            self.planes=[self.gl.texture(size,n,dtype='f1') for size,n in zip(sizes,components)]
            for texture in self.planes:self.configure(texture)
            self.format_key=key
        for texture,plane in zip(self.planes,frame.planes):texture.write(memoryview(plane),alignment=1)
        self.grade['nv12']=name=='nv12';self.grade['full_range']=int(frame.color_range)==2 or name=='yuvj420p'
        self.frame=frame
    def _set_color(self,color):
        from .color import PARAMETERS
        color=color or self.default_color;lut=color['lut']
        lut_key=lut.digest if lut else None
        if self.lut is None or lut_key!=self.lut_key:
            if self.lut:self.lut.release()
            self.lut=self.gl.texture3d((lut.size,)*3,3,lut.data,dtype='f4') if lut else self.gl.texture3d((2,2,2),3,b'\x00'*(8*3*4),dtype='f4')
            self.configure(self.lut);self.lut.repeat_z=False;self.lut_key=lut_key
        key=(color['active'],tuple(color[k] for k in PARAMETERS),lut_key)
        if key!=self.color_key:
            p=self.grade;p['apply_color']=color['active']
            p['basic']=(color['exposure'],color['contrast']/100,color['saturation']/100,color['vibrance']/100)
            p['tones']=tuple(color[k]/100 for k in ('shadows','highlights','blacks','whites'))
            p['balance']=(color['temperature']/100,color['tint']/100,color['gamma'])
            p['rgb_gain']=tuple(color[k] for k in ('red','green','blue'))
            p['domain_min']=lut.minimum if lut else (0,0,0);p['domain_max']=lut.maximum if lut else (1,1,1)
            p['lut_size']=float(lut.size if lut else 2);p['lut_strength']=color['lut_strength']/100 if lut else 0.
            self.color_key=key
    def _set_mask(self,alpha):
        import numpy as np
        if alpha is None:size=(1,1);data=b'\x00'
        else:
            if not isinstance(alpha,np.ndarray) or alpha.dtype!=np.uint8 or alpha.ndim!=2 or not all(0<n<=1024 for n in alpha.shape):raise ValueError('Invalid alpha mask')
            size=(alpha.shape[1],alpha.shape[0]);data=np.ascontiguousarray(alpha).tobytes()
        if size!=self.mask_size:
            self.mask.release();self.mask=self.gl.texture(size,1,dtype='f1');self.configure(self.mask);self.mask_size=size
        self.mask.write(data,alignment=1)
    def suspend_background_motion(self):
        if self.motion is not None:
            self.motion.select(None)
            self.motion_frame=None

    def _set_background(self,background):
        mode=background.get('mode','off');path=background.get('image')
        if mode=='motion' and path:
            if self.motion is None:
                from .background_motion import BackgroundMotion
                self.motion=BackgroundMotion()
            self.motion.select(path)
            pixels, self.motion_error=self.motion.snapshot()
            if pixels is not None:
                if pixels is not self.motion_frame:
                    size, components, data=pixels
                    if self.background_key!=('motion',size,components):
                        texture=self.gl.texture(size,components,data)
                        self.configure(texture)
                        self.background.release();self.background=texture
                        self.background_key=('motion',size,components)
                    else:
                        self.background.write(data,alignment=1)
                    self.motion_frame=pixels
                return 2
            mode='transparent'
        else:
            self.suspend_background_motion()
            self.motion_error=''
        if mode!='image' or not path:
            if self.background_key is not None:
                self.background.release();self.background=self.gl.texture((1,1),4,bytes([0,0,0,255]))
                self.configure(self.background);self.background_key=None
            return 1 if mode!='off' else 0
        key=(path,background.get('generation'))
        if key!=self.background_key:
            from PIL import Image,ImageOps
            with Image.open(path) as image:
                if image.width*image.height>50_000_000:raise ValueError('Background image too large')
                image=ImageOps.exif_transpose(image).convert('RGBA');image.thumbnail((3840,2160))
                texture=self.gl.texture(image.size,4,image.tobytes());self.configure(texture)
            self.background.release();self.background=texture;self.background_key=key
        return 2
    def draw(self,angle=0,mirror=False,output_format='landscape',pan_x=0.,pan_y=0.,alpha=None,background=None,color=None,preview=True):
        if self.frame is None:raise RuntimeError('No source frame')
        from .view_transform import crop_geometry
        geometry=crop_geometry(self.width,self.height,angle,output_format,pan_x,pan_y)
        canvas=geometry['canvas']
        if canvas!=self.canvas:
            self.canvas=canvas
            if not self.hidden and not self.hwnd:
                scale=min(self.preview_size[0]/canvas[0],self.preview_size[1]/canvas[1])
                self.dll.SDL_SetWindowSize(self.window,round(canvas[0]*scale),round(canvas[1]*scale))
                self.dll.SDL_SetWindowTitle(self.window,f'Universal Camera Studio - GPU {canvas[0]}x{canvas[1]}'.encode())
        background=background or {'mode':'off'};mode=self._set_background(background)
        solidity=background.get('solidity',0.)
        if type(solidity) not in (int,float) or not 0<=solidity<=100:raise ValueError('Invalid foreground solidity')
        gain=1./(1.-.0075*solidity)
        if gain!=self.alpha_gain:self.grade['alpha_gain']=gain;self.alpha_gain=gain
        self._set_color(color);self._set_mask(alpha if mode else None)
        self.grade['use_alpha']=bool(mode)
        self.fbo.use();self.gl.viewport=(0,0,self.width,self.height)
        self.planes[0].use(0);self.planes[1].use(1);self.planes[2 if len(self.planes)>2 else 0].use(2)
        self.mask.use(3);self.lut.use(4);self.grade_vao.render(vertices=3)
        x,y,cw,ch=geometry['source']
        self.last_scene={'crop':(x/self.width,y/self.height,cw/self.width,ch/self.height),'angle':angle,'mirror':mirror,
                         'canvas_size':canvas,'background_mode':mode,'background_size':self.background.size}
        if not preview:return
        w=C.c_int();h=C.c_int();self.dll.SDL_GL_GetDrawableSize(self.window,C.byref(w),C.byref(h))
        self.gl.screen.use();self.gl.screen.clear(0,0,0,1)
        scale=min(w.value/canvas[0],h.value/canvas[1]);vw=max(1,round(canvas[0]*scale));vh=max(1,round(canvas[1]*scale))
        self.gl.viewport=((w.value-vw)//2,(h.value-vh)//2,vw,vh)
        for name,value in self.last_scene.items():self.compose[name]=value
        self.foreground.use(0);self.background.use(1);self.compose_vao.render(vertices=3)
    def _prepare_output(self,pixel_format):
        if self.last_scene is None:raise RuntimeError('No composed frame available')
        size=self.last_scene['canvas_size']
        if pixel_format not in (1,2,3) or (pixel_format==1 and (size[0]%2 or size[1]%2)):raise ValueError('Unsupported output pixel format or dimensions')
        if self.output_format!=pixel_format and self.output_program is not None:
            self.output_vao.release();self.output_program.release();self.output_vao=self.output_program=None
        if self.output_program is None:
            shaders=Path(__file__).with_name('shaders')
            fragment=(shaders/{1:'output_nv12.frag',2:'output.frag',3:'output_rgba.frag'}[pixel_format]).read_text(encoding='utf-8')
            fragment=fragment.replace('#include "output_common.glsl"',(shaders/'output_common.glsl').read_text(encoding='utf-8'))
            self.output_program=self.gl.program(vertex_shader=(shaders/'fullscreen.vert').read_text(encoding='utf-8'),
                fragment_shader=fragment)
            self.output_vao=self.gl.vertex_array(self.output_program,[])
            self.output_program['foreground']=0;self.output_program['background_image']=1
        self.output_format=pixel_format
        return size
    def render_output(self,target,pixel_format=3):
        """Draw to an owned target or a locked shared GPU target; no readback."""
        size=self._prepare_output(pixel_format)
        storage=(size[0],size[1]*3//2) if pixel_format==1 else size
        if target.size!=storage:raise ValueError('Output target dimensions differ from canvas')
        viewport=self.gl.viewport
        try:
            target.use();self.gl.viewport=(0,0,*storage)
            for name,value in self.last_scene.items():self.output_program[name]=value
            self.foreground.use(0);self.background.use(1);self.output_vao.render(vertices=3)
        finally:self.gl.screen.use();self.gl.viewport=viewport
    def capture_output(self,pixel_format=2):
        """Opt-in opaque BGRA/NV12 or premultiplied RGBA. Call on GL thread."""
        size=self._prepare_output(pixel_format)
        components=1 if pixel_format==1 else 4
        storage=(size[0],size[1]*3//2) if pixel_format==1 else size
        if (storage,pixel_format)!=self.output_size:
            if self.output_fbo:self.output_fbo.release();self.output_texture.release()
            self.output_texture=self.gl.texture(storage,components,dtype='f1');self.configure(self.output_texture)
            self.output_fbo=self.gl.framebuffer([self.output_texture]);self.output_size=(storage,pixel_format)
        self.render_output(self.output_fbo,pixel_format)
        data=self.output_fbo.read(components=components,alignment=1);self.output_reads+=1
        return size[0],size[1],data
    def present(self):self.dll.SDL_GL_SwapWindow(self.window)
    def poll(self):
        event=Event()
        while self.dll.SDL_PollEvent(C.byref(event)):
            if event.type==0x100:return False
            if event.type==0x200 and event.padding[12]==14:return False
        return True
    def pixels(self):
        import numpy as np
        w=C.c_int();h=C.c_int();self.dll.SDL_GL_GetDrawableSize(self.window,C.byref(w),C.byref(h))
        return np.frombuffer(self.gl.screen.read(components=4,alignment=1),np.uint8).reshape(h.value,w.value,4)[::-1].copy()
    def alpha_pixels(self):
        import numpy as np
        return np.frombuffer(self.fbo.read(components=4,alignment=1),np.uint8).reshape(self.height,self.width,4)[::-1].copy()
    def clear(self):
        self.last_scene=None
        self.gl.screen.use();self.gl.screen.clear(0,0,0,1)

    def close(self):
        if self.motion is not None:
            self.motion.close();self.motion=None;self.motion_frame=None
        if self.gl:
            if self.hwnd:
                try:self.gl.screen.use();self.gl.screen.clear(0,0,0,1);self.present()
                except Exception:pass
            for resource in [self.output_fbo,self.output_texture,self.output_vao,self.output_program,*self.planes,self.mask,self.background,self.fbo,self.foreground,self.lut,self.grade_vao,self.compose_vao,self.grade,self.compose]:
                if resource:resource.release()
            self.gl.release();self.gl=None
        if self.context:self.dll.SDL_GL_DeleteContext(self.context);self.context=None
        if self.window:self.dll.SDL_DestroyWindow(self.window);self.window=None
        self.dll.SDL_QuitSubSystem(0x20)
