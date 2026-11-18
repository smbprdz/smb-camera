"""Public current-user camera endpoint. No video, token or Apple credentials."""
import os,struct
from pathlib import Path

CLSID='{5D7B959B-7F58-4A09-A390-714583AF4E8B}'
CLASS_KEY='SOFTWARE\\Classes\\CLSID\\'+CLSID
RUNTIME_KEY='Software\\SMB\\Camera\\Runtime'
CONFIG=struct.Struct('<IIIIQ6I256s384s')
assert CONFIG.size==688

def endpoint_bytes(endpoint,fps):
    w,h=endpoint['canvas'];pid=endpoint['producer_pid'];epoch=endpoint['epoch']
    if type(w) is not int or type(h) is not int or w<2 or h<2 or w%2 or h%2 or max(w,h)>16384 or w*h*3//2>64*1024*1024:raise ValueError('Unsupported native canvas')
    if type(fps) is not int or not 1<=fps<=240 or type(pid) is not int or not 1<=pid<2**32 or type(epoch) is not int or not 1<=epoch<2**64:raise ValueError('Invalid native endpoint timing or identity')
    pipe=endpoint['pipe_name'];sid=endpoint['owner_sid'];prefix='\\\\.\\pipe\\UCS.FrameBridge.'
    if not isinstance(pipe,str) or not pipe.startswith(prefix) or len(pipe)!=len(prefix)+36 or any(c not in '0123456789abcdefABCDEF-' for c in pipe[len(prefix):]):raise ValueError('Invalid local pipe')
    if not isinstance(sid,str) or not sid.startswith('S-1-') or len(sid)>=192 or any(c not in 'S-0123456789' for c in sid):raise ValueError('Invalid native owner')
    a=(pipe+'\0').encode('utf-16-le');b=(sid+'\0').encode('utf-16-le')
    if len(a)>256 or len(b)>384:raise ValueError('Endpoint exceeds bound')
    return CONFIG.pack(0x42534355,2,pid,0,epoch,w,h,fps,1,1,0,a,b)

def installed_directory(expected_sid=None):
    if os.name!='nt':return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,CLASS_KEY,0,winreg.KEY_READ|winreg.KEY_WOW64_64KEY) as key:
            sid=winreg.QueryValueEx(key,'UCS.Camera.OwnerSID')[0];directory=Path(winreg.QueryValueEx(key,'UCS.Camera.InstallDirectory')[0])
        expected=Path(os.environ['ProgramFiles'])/'SMB Camera Bridge'
        if directory!=expected or (expected_sid is not None and sid!=expected_sid):return None
        if not (directory/'SMBCameraHost.exe').is_file() or not (directory/'SMBCameraSource.dll').is_file():return None
        return directory
    except (OSError,KeyError,ValueError):return None

def write_endpoint(endpoint,fps):
    if os.name!='nt':raise RuntimeError('Native camera requires Windows')
    import ctypes as C
    from ctypes import wintypes as W
    import winreg
    from .frame_pipe_windows import PipeServer,SECURITY_ATTRIBUTES
    data=endpoint_bytes(endpoint,fps);api=PipeServer(endpoint['pipe_name']);sid=api.owner_sid
    if sid!=endpoint['owner_sid']:raise ValueError('Endpoint owner differs from current account')
    acl=f'O:{sid}D:P(A;;KA;;;{sid})(A;;KA;;;SY)(A;;KR;;;{api.service_sid("NT SERVICE"+chr(92)+"FrameServer")})(A;;KR;;;{api.service_sid("NT SERVICE"+chr(92)+"FrameServerMonitor")})'
    descriptor=W.LPVOID()
    if not api.a.ConvertStringSecurityDescriptorToSecurityDescriptorW(acl,1,C.byref(descriptor),None):raise OSError('Runtime ACL unavailable')
    key=W.HANDLE();disposition=W.DWORD();api.a.RegCreateKeyExW.argtypes=[W.HANDLE,W.LPCWSTR,W.DWORD,W.LPWSTR,W.DWORD,W.DWORD,C.POINTER(SECURITY_ATTRIBUTES),C.POINTER(W.HANDLE),C.POINTER(W.DWORD)];api.a.RegCreateKeyExW.restype=W.LONG
    api.a.RegCloseKey.argtypes=[W.HANDLE]
    try:
        attributes=SECURITY_ATTRIBUTES(C.sizeof(SECURITY_ATTRIBUTES),descriptor,False)
        status=api.a.RegCreateKeyExW(W.HANDLE(0x80000001),RUNTIME_KEY,0,None,0,winreg.KEY_SET_VALUE|winreg.KEY_WOW64_64KEY,C.byref(attributes),C.byref(key),C.byref(disposition))
        if status:raise OSError('Native endpoint key unavailable')
        # An existing key must have the same explicit ACL, not inherit a weaker
        # one from another runtime. Set only its DACL; never alter parent keys.
        get_dacl=api.a.GetSecurityDescriptorDacl;get_dacl.argtypes=[W.LPVOID,C.POINTER(W.BOOL),C.POINTER(W.LPVOID),C.POINTER(W.BOOL)];get_dacl.restype=W.BOOL
        present=W.BOOL();default=W.BOOL();dacl=W.LPVOID()
        if not get_dacl(descriptor,C.byref(present),C.byref(dacl),C.byref(default)):raise OSError('Runtime DACL unavailable')
        api.a.SetSecurityInfo.argtypes=[W.HANDLE,C.c_int,W.DWORD,W.LPVOID,W.LPVOID,W.LPVOID,W.LPVOID];api.a.SetSecurityInfo.restype=W.DWORD
        # Reopen as owner for WRITE_DAC so only this leaf key is hardened.
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,RUNTIME_KEY,0,0x40000|winreg.KEY_SET_VALUE|winreg.KEY_WOW64_64KEY) as owner:
            if api.a.SetSecurityInfo(W.HANDLE(int(owner)),4,4|0x80000000,None,None,dacl,None):raise OSError('Runtime key ACL failed')
            winreg.SetValueEx(owner,'Endpoint',0,winreg.REG_BINARY,data)
    finally:
        if key:api.a.RegCloseKey(key)
        api.k.LocalFree(descriptor)

def remove_endpoint(pid,epoch):
    if os.name!='nt':return
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,RUNTIME_KEY,0,winreg.KEY_QUERY_VALUE|winreg.KEY_SET_VALUE|winreg.KEY_WOW64_64KEY) as key:
            data,kind=winreg.QueryValueEx(key,'Endpoint')
            if kind==winreg.REG_BINARY and len(data)==CONFIG.size:
                values=CONFIG.unpack(data)
                if values[2]==pid and values[4]==epoch:winreg.DeleteValue(key,'Endpoint')
    except OSError:pass
