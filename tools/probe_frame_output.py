"""Read-only local frame diagnostics. Never writes video/images or registers devices."""
import argparse,ctypes as C,json,os,sys,time
from ctypes import wintypes as W
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ucs.frame_output import REQUEST,REPLY,DESCRIPTOR,MAX_PAYLOAD
from ucs.frame_pipe_windows import PipeServer,OVERLAPPED


def classify_packet(packet,endpoint,width,height,pixel_format,now):
    """Distinguish a valid but expired frame from a malformed local message."""
    if len(packet)<32:raise ValueError('Truncated frame envelope')
    envelope=REPLY.unpack(packet[:32])
    if envelope[:2]!=(0x52534355,1) or envelope[4] or envelope[6]!=endpoint['epoch'] or envelope[3]!=len(packet)-32:
        raise ValueError('Invalid frame envelope')
    if envelope[2]==0:
        if len(packet)!=32 or envelope[3] or envelope[5]:raise ValueError('Invalid empty frame reply')
        return 'empty',None
    if envelope[2]!=1 or len(packet)<96:raise ValueError('Invalid frame reply status')
    frame=DESCRIPTOR.unpack(packet[32:96])
    payload=width*height*3//2 if pixel_format==1 else width*height*4
    planes=(width,width,width*height) if pixel_format==1 else (width*4,0,0)
    if frame[:3]!=(0x46534355,1,64) or frame[3:6]!=(pixel_format,width,height) or frame[6:9]!=planes or frame[9]!=payload or len(packet)!=96+payload or frame[10]<=0 or frame[11]<0 or frame[12:]!=(1 if pixel_format==1 else 2,1 if pixel_format==3 else 0):
        raise ValueError('Invalid frame descriptor')
    if envelope[5]>now:raise ValueError('Frame timestamp is in the future')
    if now-envelope[5]>250:return 'expired',None
    return 'frame',frame

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--metadata',required=True);parser.add_argument('--seconds',type=float,default=12)
    parser.add_argument('--format',choices=['bgra','nv12','rgba'],default='bgra');args=parser.parse_args()
    if not 1<=args.seconds<=60:raise ValueError('Diagnostic duration out of bounds')
    endpoint=json.loads(Path(args.metadata).read_text(encoding='utf-8'));width,height=endpoint['canvas']
    if type(width) is not int or type(height) is not int or not 2<=width<=16384 or not 2<=height<=16384:raise ValueError('Invalid canvas')
    pixel_format={'nv12':1,'bgra':2,'rgba':3}[args.format]
    if pixel_format not in endpoint.get('formats',[2]) or (pixel_format==1 and (width%2 or height%2)):raise ValueError('Requested format not available')
    payload_size=width*height*3//2 if pixel_format==1 else width*height*4
    if payload_size>MAX_PAYLOAD:raise ValueError('Output exceeds allocation bound')
    # Bind documented Windows APIs only; this object never starts a server.
    api=PipeServer(endpoint['pipe_name']);k=api.k;a=api.a
    for dll,name,types,result in [
        (k,'CreateFileW',[W.LPCWSTR,W.DWORD,W.DWORD,W.LPVOID,W.DWORD,W.DWORD,W.HANDLE],W.HANDLE),
        (k,'SetNamedPipeHandleState',[W.HANDLE,C.POINTER(W.DWORD),W.LPVOID,W.LPVOID],W.BOOL),
        (k,'GetNamedPipeServerProcessId',[W.HANDLE,C.POINTER(W.ULONG)],W.BOOL),
        (k,'TransactNamedPipe',[W.HANDLE,W.LPVOID,W.DWORD,W.LPVOID,W.DWORD,C.POINTER(W.DWORD),C.POINTER(OVERLAPPED)],W.BOOL),
        (a,'GetSecurityInfo',[W.HANDLE,C.c_int,W.DWORD,C.POINTER(W.LPVOID),W.LPVOID,W.LPVOID,W.LPVOID,C.POINTER(W.LPVOID)],W.DWORD),
        (a,'ConvertStringSidToSidW',[W.LPCWSTR,C.POINTER(W.LPVOID)],W.BOOL),(a,'EqualSid',[W.LPVOID,W.LPVOID],W.BOOL)]:
        f=getattr(dll,name);f.argtypes=types;f.restype=result
    pipe=None;event=k.CreateEventW(None,True,False,None);buffer=C.create_string_buffer(96+payload_size)
    request=C.create_string_buffer(REQUEST.pack(0x51534355,1,24,pixel_format,width,height,0));ids=set();samples=empty=expired=0;start=time.perf_counter();first=last=None;timings=[];ages=[];next_at=start;failure=None
    try:
        while time.perf_counter()-start<args.seconds:
            if not pipe:
                pipe=k.CreateFileW(endpoint['pipe_name'],0x120183,0,None,3,0x40000000|0x110000,None)
                if not pipe or pipe==C.c_void_p(-1).value:pipe=None;time.sleep(.03);continue
                pid=W.ULONG();owner=W.LPVOID();descriptor=W.LPVOID();expected=W.LPVOID()
                try:
                    if not k.GetNamedPipeServerProcessId(pipe,C.byref(pid)) or pid.value!=endpoint['producer_pid']:raise ValueError('Unexpected producer PID')
                    if a.GetSecurityInfo(pipe,6,1,C.byref(owner),None,None,None,C.byref(descriptor)) or not a.ConvertStringSidToSidW(endpoint['owner_sid'],C.byref(expected)) or not a.EqualSid(owner,expected):raise ValueError('Unexpected producer identity')
                finally:
                    if descriptor:k.LocalFree(descriptor)
                    if expected:k.LocalFree(expected)
                mode=W.DWORD(2)
                if not k.SetNamedPipeHandleState(pipe,C.byref(mode),None,None):raise OSError('Pipe read mode failed')
            k.ResetEvent(event);op=OVERLAPPED();op.hEvent=event;count=W.DWORD();before=time.perf_counter()
            okay=k.TransactNamedPipe(pipe,request,24,buffer,len(buffer),C.byref(count),C.byref(op))
            if not okay:
                if C.get_last_error()!=997 or k.WaitForSingleObject(event,200)!=0:
                    k.CancelIoEx(pipe,C.byref(op));k.GetOverlappedResult(pipe,C.byref(op),C.byref(count),True);k.CloseHandle(pipe);pipe=None;empty+=1;continue
            if not k.GetOverlappedResult(pipe,C.byref(op),C.byref(count),False):k.CloseHandle(pipe);pipe=None;empty+=1;continue
            if count.value>len(buffer):raise ValueError('Oversized reply')
            packet=C.string_at(buffer,count.value)
            now=k.GetTickCount64();kind,frame=classify_packet(packet,endpoint,width,height,pixel_format,now)
            stamp=time.perf_counter()
            if kind=='frame':
                first=stamp if first is None else first;last=stamp;ids.add(frame[10]);samples+=1;timings.append((stamp-before)*1000);ages.append(now-REPLY.unpack(packet[:32])[5])
            elif kind=='expired':expired+=1
            else:empty+=1
            next_at=max(next_at+1/30,stamp);time.sleep(max(0,next_at-time.perf_counter()))
    except (OSError,ValueError) as error:
        failure=str(error) if isinstance(error,ValueError) else type(error).__name__
    finally:
        if pipe:k.CloseHandle(pipe)
        if event:k.CloseHandle(event)
    timings.sort();ages.sort();print(json.dumps({'scope':'local processed frame packet diagnostics, no camera registration or recorded frames',
        'status':'pass' if len(ids)>=10 and failure is None else 'failed','error':failure,
        'canvas':[width,height],'format':args.format,'samples':samples,'unique_frame_ids':len(ids),'empty_or_timeout':empty,'expired_packets':expired,
        'sample_fps':(samples-1)/(last-first) if samples>1 else None,'request_p95_ms':timings[int((len(timings)-1)*.95)] if timings else None,
        'host_arrival_to_packet_p95_ms':ages[int((len(ages)-1)*.95)] if ages else None,'clock_scope':'host arrival, not sensor or glass-to-glass',
        'personal_media_recorded':False,'consumer_process':os.getpid()},indent=2))
    if failure or len(ids)<10:raise SystemExit('Processed frame diagnostic did not pass')

if __name__=='__main__':main()
