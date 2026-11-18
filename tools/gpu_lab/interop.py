"""Own generated-only GPU experiment. Documented D3D11/DXGI/WGL APIs.

No SDK from Spout, no camera/OBS settings, no new native executable.
COM slots below verified against Windows SDK 10.0.26100 public headers.
"""
import ctypes as C
import uuid

P = C.c_void_p
U = C.c_uint32
I = C.c_int32
SHARED_KEYEDMUTEX = 0x100  # D3D11_RESOURCE_MISC_SHARED_KEYEDMUTEX, public SDK.


class GUID(C.Structure):
    _fields_ = [('a', U), ('b', C.c_uint16), ('c', C.c_uint16), ('d', C.c_ubyte*8)]


def guid(value):
    return GUID.from_buffer_copy(uuid.UUID(value).bytes_le)


def method(pointer, slot, result, *types):
    address = C.cast(pointer, C.POINTER(C.POINTER(P))).contents[slot]
    return C.WINFUNCTYPE(result, P, *types)(address)


def check(code, operation):
    if code < 0:
        raise RuntimeError(operation+': '+hex(code & 0xffffffff))


def release(pointer):
    if pointer:
        method(pointer, 2, U)(pointer)


def query(pointer, iid):
    value, ident = P(), guid(iid)
    check(method(pointer, 0, I, C.POINTER(GUID), C.POINTER(P))(
        pointer, C.byref(ident), C.byref(value)), 'QueryInterface')
    return value


class AbandonedTexture(RuntimeError):
    """The resource must be recreated, not reused after an owner crash."""


def mutex_status(code):
    # WAIT_TIMEOUT/WAIT_ABANDONED are positive DWORD values, not failed HRESULTs.
    if code == 0:return True
    if code == 0x102:return False
    if code == 0x80:raise AbandonedTexture('Recreate abandoned GPU resource')
    raise RuntimeError('Keyed mutex failure: '+hex(code & 0xffffffff))


class KeyedAccess:
    def __init__(self,texture):
        self.pointer=query(texture,'9d8e1289-d7b3-465f-8126-250e349af85d')
        self.held=False

    def acquire(self,key,timeout_ms=0):
        if type(key) is not int or not 0<=key<2**64 or type(timeout_ms) is not int or not 0<=timeout_ms<=50:
            raise ValueError('Bounded keyed mutex request required')
        if not self.pointer or self.held:raise RuntimeError('Invalid keyed resource ownership')
        acquired=mutex_status(method(self.pointer,8,I,C.c_uint64,U)(self.pointer,key,timeout_ms))
        self.held=acquired
        return acquired

    def publish(self,next_key):
        if type(next_key) is not int or not 0<=next_key<2**64:raise ValueError('Invalid release key')
        if not self.pointer or not self.held:raise RuntimeError('Keyed resource not owned')
        code=method(self.pointer,9,I,C.c_uint64)(self.pointer,next_key)
        if code!=0:raise RuntimeError('Keyed release failure: '+hex(code & 0xffffffff))
        self.held=False

    def close(self):
        release(self.pointer);self.pointer=None


class LUID(C.Structure):
    _fields_ = [('low', U), ('high', I)]


class AdapterDesc(C.Structure):
    _fields_ = [('name', C.c_wchar*128), ('vendor', U), ('device', U),
                ('subsystem', U), ('revision', U), ('video_memory', C.c_size_t),
                ('system_memory', C.c_size_t), ('shared_memory', C.c_size_t),
                ('luid', LUID), ('flags', U)]


class TextureDesc(C.Structure):
    _fields_ = [(name, U) for name in ('width', 'height', 'mips', 'arrays', 'format',
                'sample_count', 'sample_quality', 'usage', 'bind', 'cpu_access', 'misc')]


class Mapped(C.Structure):
    _fields_ = [('data', P), ('row_pitch', U), ('depth_pitch', U)]


class Device:
    def __init__(self, renderer):
        self.device = self.context = self.adapter = None
        self.factory = None
        dxgi = C.WinDLL('dxgi')
        dxgi.CreateDXGIFactory1.argtypes = [C.POINTER(GUID), C.POINTER(P)]
        dxgi.CreateDXGIFactory1.restype = I
        factory = P()
        iid = guid('770aae78-f26f-4dba-a829-253c83d1b387')
        check(dxgi.CreateDXGIFactory1(C.byref(iid), C.byref(factory)), 'CreateFactory')
        self.factory = factory
        try:
            for index in range(16):
                adapter = P()
                code = method(factory, 12, I, U, C.POINTER(P))(factory, index, C.byref(adapter))
                if code & 0xffffffff == 0x887a0002:
                    break
                check(code, 'EnumAdapters')
                desc = AdapterDesc()
                check(method(adapter, 10, I, C.POINTER(AdapterDesc))(adapter, C.byref(desc)), 'AdapterDesc')
                if desc.name and desc.name.lower() in renderer.lower():
                    self.adapter = adapter
                    self.info = {'name': desc.name, 'luid': [desc.luid.low, desc.luid.high],
                                 'vendor': desc.vendor}
                    break
                release(adapter)
            if not self.adapter:
                raise RuntimeError('No D3D adapter matching current GL renderer')
            d3d = C.WinDLL('d3d11')
            d3d.D3D11CreateDevice.argtypes = [P, I, P, U, P, U, U, C.POINTER(P), C.POINTER(U), C.POINTER(P)]
            d3d.D3D11CreateDevice.restype = I
            device, context, level = P(), P(), U()
            check(d3d.D3D11CreateDevice(self.adapter, 0, None, 0x20, None, 0, 7,
                C.byref(device), C.byref(level), C.byref(context)), 'CreateD3D11Device')
            self.device, self.context = device, context
            # WGL interop requires a multithread-capable D3D11 device.
            multi = query(context, '9b7e4e00-342c-4106-a19f-4f2704f689f0')
            try:
                method(multi, 5, I, I)(multi, 1)
            finally:
                release(multi)
        except Exception:
            self.close()
            raise

    def texture(self, width, height, staging=False, keyed=False):
        if (type(width) is not int or type(height) is not int or not 2<=width<=16384
                or not 2<=height<=16384 or width*height*4>64*1024*1024 or type(staging) is not bool
                or type(keyed) is not bool or (staging and keyed)):
            raise ValueError('Bounded generated RGBA dimensions required')
        desc = TextureDesc(width, height, 1, 1, 28, 1, 0,
                           3 if staging else 0, 0 if staging else 0x28,
                           0x20000 if staging else 0, 0 if staging else (SHARED_KEYEDMUTEX if keyed else 2))
        result = P()
        check(method(self.device, 5, I, C.POINTER(TextureDesc), P, C.POINTER(P))(
            self.device, C.byref(desc), None, C.byref(result)), 'CreateTexture2D')
        return result

    def shared_handle(self, texture):
        resource = query(texture, '035f3ab4-482e-4e50-b41f-8a7f8bd8960b')
        try:
            handle = P()
            check(method(resource, 8, I, C.POINTER(P))(resource, C.byref(handle)), 'GetSharedHandle')
            return handle.value
        finally:
            release(resource)

    def open(self, handle):
        if type(handle) is not int or not 0<handle<2**32:
            raise ValueError('Expected legacy local shared resource handle')
        result = P()
        iid = guid('6f15aaf2-d208-4e89-9ab4-489535d34f9c')
        check(method(self.device, 28, I, P, C.POINTER(GUID), C.POINTER(P))(
            self.device, P(handle), C.byref(iid), C.byref(result)), 'OpenSharedResource')
        return result

    def read(self, texture, staging, width, height):
        method(self.context, 47, None, P, P)(self.context, staging, texture)
        mapped = Mapped()
        check(method(self.context, 14, I, P, U, U, U, C.POINTER(Mapped))(
            self.context, staging, 0, 1, 0, C.byref(mapped)), 'Map generated proof')
        try:
            return b''.join(C.string_at(mapped.data+y*mapped.row_pitch, width*4) for y in range(height))
        finally:
            method(self.context, 15, None, P, U)(self.context, staging, 0)

    def close(self):
        for name in ('context', 'device', 'adapter', 'factory'):
            pointer = getattr(self, name, None)
            release(pointer)
            setattr(self, name, None)


class Interop:
    def __init__(self, renderer, device, width, height, keyed=False):
        self.dx = self.object = self.texture = self.gl_texture = self.fbo = None
        self.renderer = renderer
        self.gl = C.WinDLL('opengl32')
        sdl = renderer.dll
        sdl.SDL_GL_GetProcAddress.argtypes = [C.c_char_p]
        sdl.SDL_GL_GetProcAddress.restype = P
        for name, args, result in (
            ('wglDXOpenDeviceNV', [P], P), ('wglDXCloseDeviceNV', [P], I),
            ('wglDXRegisterObjectNV', [P, P, U, U, U], P),
            ('wglDXUnregisterObjectNV', [P, P], I),
            ('wglDXLockObjectsNV', [P, I, C.POINTER(P)], I),
            ('wglDXUnlockObjectsNV', [P, I, C.POINTER(P)], I),
        ):
            address = sdl.SDL_GL_GetProcAddress(name.encode())
            if not address:
                raise RuntimeError('Missing WGL interop API')
            setattr(self, name, C.WINFUNCTYPE(result, *args)(address))
        self.gl.glGenTextures.argtypes = [I, C.POINTER(U)]
        self.gl.glDeleteTextures.argtypes = [I, C.POINTER(U)]
        self.name = U()
        try:
            self.texture = device.texture(width, height, keyed=keyed)
            self.handle = device.shared_handle(self.texture)
            self.dx = self.wglDXOpenDeviceNV(device.device)
            if not self.dx:
                raise RuntimeError('WGL device open failed')
            self.gl.glGenTextures(1, C.byref(self.name))
            self.object = self.wglDXRegisterObjectNV(self.dx, self.texture, self.name, 0x0de1, 1)
            if not self.object:
                raise RuntimeError('WGL texture registration failed')
            objects = (P*1)(self.object)
            if not self.wglDXLockObjectsNV(self.dx, 1, objects):
                raise RuntimeError('WGL initial lock failed')
            try:
                self.gl_texture = renderer.gl.external_texture(self.name.value, (width, height), 4, 0, 'f1')
                self.fbo = renderer.gl.framebuffer([self.gl_texture])
            finally:
                self.wglDXUnlockObjectsNV(self.dx, 1, objects)
        except Exception:
            self.close()
            raise

    def render(self, callback):
        objects = (P*1)(self.object)
        if not self.wglDXLockObjectsNV(self.dx, 1, objects):
            raise RuntimeError('WGL render lock failed')
        try:
            callback(self.fbo)
        finally:
            if not self.wglDXUnlockObjectsNV(self.dx, 1, objects):
                raise RuntimeError('WGL render unlock failed')

    def close(self):
        if self.fbo:
            self.fbo.release(); self.fbo = None
        if self.object:
            self.wglDXUnregisterObjectNV(self.dx, self.object); self.object = None
        # external_texture does not own the externally allocated GL name.
        if self.gl_texture:
            self.gl_texture.release(); self.gl_texture = None
        if getattr(self, 'name', None) and self.name.value:
            self.gl.glDeleteTextures(1, C.byref(self.name)); self.name = U()
        if self.dx:
            self.wglDXCloseDeviceNV(self.dx); self.dx = None
        release(self.texture); self.texture = None
