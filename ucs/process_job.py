"""Windows kill-on-close job for the optional inference process and venv launcher."""
import ctypes as C
from ctypes import wintypes as W
import os,threading

class ProcessJob:
    def __init__(self,process):
        self.lock=threading.Lock();self.handle=None
        if os.name!='nt':return
        class Basic(C.Structure):
            _fields_=[('process_time',C.c_longlong),('job_time',C.c_longlong),('flags',W.DWORD),
                ('minimum',C.c_size_t),('maximum',C.c_size_t),('count',W.DWORD),
                ('affinity',C.c_size_t),('priority',W.DWORD),('scheduling',W.DWORD)]
        class Extended(C.Structure):
            _fields_=[('basic',Basic),('io',C.c_ulonglong*6),('process_memory',C.c_size_t),
                ('job_memory',C.c_size_t),('peak_process',C.c_size_t),('peak_job',C.c_size_t)]
        self.api=C.WinDLL('kernel32',use_last_error=True)
        for name,args,result in (
            ('CreateJobObjectW',[C.c_void_p,W.LPCWSTR],W.HANDLE),
            ('SetInformationJobObject',[W.HANDLE,C.c_int,C.c_void_p,W.DWORD],W.BOOL),
            ('AssignProcessToJobObject',[W.HANDLE,W.HANDLE],W.BOOL),
            ('TerminateJobObject',[W.HANDLE,W.UINT],W.BOOL),('CloseHandle',[W.HANDLE],W.BOOL)):
            fn=getattr(self.api,name);fn.argtypes=args;fn.restype=result
        self.handle=self.api.CreateJobObjectW(None,None)
        if not self.handle:raise C.WinError(C.get_last_error())
        limits=Extended();limits.basic.flags=0x2000 # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle,9,C.byref(limits),C.sizeof(limits)) or not self.api.AssignProcessToJobObject(self.handle,int(process._handle)):
            error=C.WinError(C.get_last_error());self.close();raise error
    def terminate(self):
        with self.lock:
            if self.handle:self.api.TerminateJobObject(self.handle,1)
    def close(self):
        with self.lock:
            if self.handle:self.api.CloseHandle(self.handle);self.handle=None
