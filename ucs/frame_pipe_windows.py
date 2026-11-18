"""Windows-only reference pipe server; local, explicit ACL, no secrets."""
import ctypes as C
from ctypes import wintypes as W
import os,threading

class OVERLAPPED(C.Structure):
    _fields_=[('Internal',C.c_size_t),('InternalHigh',C.c_size_t),('Offset',W.DWORD),('OffsetHigh',W.DWORD),('hEvent',W.HANDLE)]
class SECURITY_ATTRIBUTES(C.Structure):
    _fields_=[('nLength',W.DWORD),('lpSecurityDescriptor',W.LPVOID),('bInheritHandle',W.BOOL)]

class PipeServer:
    def __init__(self,name,instances=4,allow_frame_services=True):
        if os.name!='nt':raise RuntimeError('Frame output pipe requires Windows')
        prefix='\\\\.\\pipe\\UCS.FrameBridge.'
        if not name.startswith(prefix) or len(name)!=len(prefix)+36 or any(c not in '0123456789abcdefABCDEF-' for c in name[len(prefix):]):raise ValueError('Invalid local frame endpoint')
        if type(instances) is not int or not 1<=instances<=8:raise ValueError('Invalid pipe instance count')
        self.instances=instances;self.allow_frame_services=bool(allow_frame_services);self.handles=[];self.active=0
        self.name=name;self.k=C.WinDLL('kernel32',use_last_error=True);self.a=C.WinDLL('advapi32',use_last_error=True)
        p=W.LPVOID;u=W.DWORD;h=W.HANDLE;b=W.BOOL;s=W.LPCWSTR
        for dll,n,args,result in [
            (self.k,'CreateNamedPipeW',[s,u,u,u,u,u,u,C.POINTER(SECURITY_ATTRIBUTES)],h),
            (self.k,'ConnectNamedPipe',[h,C.POINTER(OVERLAPPED)],b),(self.k,'DisconnectNamedPipe',[h],b),
            (self.k,'CreateEventW',[p,b,b,s],h),(self.k,'CloseHandle',[h],b),(self.k,'ResetEvent',[h],b),
            (self.k,'WaitForSingleObject',[h,u],u),(self.k,'CancelIoEx',[h,p],b),
            (self.k,'GetOverlappedResult',[h,C.POINTER(OVERLAPPED),C.POINTER(u),b],b),
            (self.k,'ReadFile',[h,p,u,C.POINTER(u),C.POINTER(OVERLAPPED)],b),
            (self.k,'WriteFile',[h,p,u,C.POINTER(u),C.POINTER(OVERLAPPED)],b),
            (self.k,'GetCurrentProcess',[],h),(self.k,'LocalFree',[p],p),(self.k,'GetTickCount64',[],C.c_ulonglong),
            (self.a,'OpenProcessToken',[h,u,C.POINTER(h)],b),(self.a,'GetTokenInformation',[h,C.c_int,p,u,C.POINTER(u)],b),
            (self.a,'ConvertSidToStringSidW',[p,C.POINTER(p)],b),
            (self.a,'LookupAccountNameW',[s,s,p,C.POINTER(u),p,C.POINTER(u),C.POINTER(u)],b),
            (self.a,'ConvertStringSecurityDescriptorToSecurityDescriptorW',[s,u,C.POINTER(p),p],b)]:
            function=getattr(dll,n);function.argtypes=args;function.restype=result
        self.owner_sid=self.user_sid();self.lock=threading.Lock();self.handle=None;self.stop=threading.Event();self.ready=threading.Event();self.startup_error=None
    def tick_ms(self):return self.k.GetTickCount64()
    def sid_text(self,sid):
        text=W.LPVOID()
        if not self.a.ConvertSidToStringSidW(sid,C.byref(text)):raise OSError('SID conversion failed')
        try:return C.wstring_at(text)
        finally:self.k.LocalFree(text)
    def user_sid(self):
        token=W.HANDLE()
        if not self.a.OpenProcessToken(self.k.GetCurrentProcess(),8,C.byref(token)):raise OSError('Frame owner identity unavailable')
        try:
            size=W.DWORD();self.a.GetTokenInformation(token,1,None,0,C.byref(size));buffer=C.create_string_buffer(size.value)
            if not self.a.GetTokenInformation(token,1,buffer,size,C.byref(size)):raise OSError('Frame owner identity failed')
            return self.sid_text(C.cast(buffer,C.POINTER(W.LPVOID))[0])
        finally:self.k.CloseHandle(token)
    def service_sid(self,name):
        size=W.DWORD();chars=W.DWORD();use=W.DWORD()
        self.a.LookupAccountNameW(None,name,None,C.byref(size),None,C.byref(chars),C.byref(use))
        sid=C.create_string_buffer(size.value);domain=C.create_unicode_buffer(chars.value)
        if not self.a.LookupAccountNameW(None,name,sid,C.byref(size),domain,C.byref(chars),C.byref(use)):raise OSError('FrameServer identity unavailable')
        return self.sid_text(sid)
    def start(self,state):
        self.thread=threading.Thread(target=self.run,args=(state,),daemon=True);self.thread.start()
        if not self.ready.wait(3) or self.startup_error:
            self.close();raise RuntimeError('Local frame output could not start')
    def run(self,state):
        workers=[];created=[]
        try:
            acl=f'O:{self.owner_sid}D:P(A;;GA;;;{self.owner_sid})(A;;GA;;;SY)'
            if self.allow_frame_services:
                frame=self.service_sid('NT SERVICE\\FrameServer');monitor=self.service_sid('NT SERVICE\\FrameServerMonitor')
                acl+=f'(A;;0x00120183;;;{frame})(A;;0x00120183;;;{monitor})'
            descriptor=W.LPVOID()
            if not self.a.ConvertStringSecurityDescriptorToSecurityDescriptorW(acl,1,C.byref(descriptor),None):raise OSError('Frame output ACL failed')
            try:
                attributes=SECURITY_ATTRIBUTES(C.sizeof(SECURITY_ATTRIBUTES),descriptor,False)
                for index in range(self.instances):
                    pipe=self.k.CreateNamedPipeW(self.name,3|0x40000000|(0x80000 if index==0 else 0),4|2|8,self.instances,2*1024*1024,4096,1000,C.byref(attributes))
                    if not pipe or pipe==C.c_void_p(-1).value:raise OSError('Frame endpoint unavailable')
                    created.append(pipe)
            finally:self.k.LocalFree(descriptor)
            with self.lock:self.handles=list(created);self.handle=created[0]
            for pipe in created:
                worker=threading.Thread(target=self.serve,args=(pipe,state),daemon=True);worker.start();workers.append(worker)
            self.ready.set()
            for worker in workers:worker.join()
        except Exception as error:
            self.startup_error=type(error).__name__;state.fail();self.stop.set();self.ready.set()
            with self.lock:
                for pipe in self.handles:self.k.CancelIoEx(pipe,None)
            for worker in workers:worker.join()
        finally:
            # Workers never close their handles; the manager owns them until all
            # I/O has completed. close() cancels under the same lifetime lock.
            with self.lock:
                self.handles=[];self.handle=None
                for pipe in created:self.k.CloseHandle(pipe)
    def serve(self,pipe,state):
        event=self.k.CreateEventW(None,True,False,None)
        try:
            if not event:raise OSError('Frame IO event unavailable')
            def io(function,*args,timeout=1000,connect=False):
                self.k.ResetEvent(event);op=OVERLAPPED();op.hEvent=event;count=W.DWORD()
                okay=function(pipe,*args,C.byref(count),C.byref(op)) if not connect else function(pipe,C.byref(op))
                error=C.get_last_error()
                if not okay and connect and error==535:return True,0
                if not okay:
                    if error!=997:return False,0
                    if self.k.WaitForSingleObject(event,timeout)!=0:
                        self.k.CancelIoEx(pipe,C.byref(op));self.k.GetOverlappedResult(pipe,C.byref(op),C.byref(count),True);return False,0
                return bool(self.k.GetOverlappedResult(pipe,C.byref(op),C.byref(count),False)),count.value
            while not self.stop.is_set():
                okay,_=io(self.k.ConnectNamedPipe,connect=True,timeout=250)
                if not okay:self.k.DisconnectNamedPipe(pipe);continue
                with self.lock:self.active+=1
                try:
                    while not self.stop.is_set():
                        request=C.create_string_buffer(24);okay,count=io(self.k.ReadFile,request,24)
                        if not okay or count!=24:break
                        try:packet=state.request(request.raw)
                        except ValueError:break
                        pointer=C.c_char_p(packet);okay,count=io(self.k.WriteFile,C.cast(pointer,W.LPVOID),len(packet),timeout=100)
                        if not okay or count!=len(packet):break
                finally:
                    # A disconnect must not blank another active consumer.
                    with self.lock:
                        self.active-=1
                        if self.active==0:state.disconnect()
                    self.k.DisconnectNamedPipe(pipe)
        except Exception as error:
            self.startup_error=type(error).__name__;state.fail();self.stop.set()
            with self.lock:
                for peer in self.handles:self.k.CancelIoEx(peer,None)
        finally:
            if event:self.k.CloseHandle(event)
    def close(self):
        self.stop.set()
        with self.lock:
            for pipe in self.handles:self.k.CancelIoEx(pipe,None)
        thread=getattr(self,'thread',None)
        if thread and thread is not threading.current_thread():thread.join(timeout=2)
        if thread and thread.is_alive():raise RuntimeError('Frame output did not stop within deadline')
