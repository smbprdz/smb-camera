"""Own UI + real loopback TLS/H.264/hardware decode/GPU preview. No phone/OBS.

Only synthetic video and disposable identity; no camera, accounts, microphone,
discovery announcement or USB monitor. Keeps product settings separate.
"""
import argparse,json,queue,subprocess,sys,threading,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tkinter as tk
from ucs.desktop import Desktop
from ucs.receiver import run
from ucs.synthetic import access_units,connect
from ucs.protocol import *
from ucs import studio_ui

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=int,default=15)
    parser.add_argument('--resolution',choices=['720','1080','4k'],default='720')
    parser.add_argument('--diagnostics',action='store_true')
    parser.add_argument('--exposure-controls',action='store_true',help='Generated phone advertises physical exposure control')
    parser.add_argument('--visibility-cycle',action='store_true',help='Generated visible/hidden/consumer/resume phases; needs at least16 seconds')
    parser.add_argument('--start-hidden',action='store_true',help='Start visibility cycle without ever creating a preview renderer')
    parser.add_argument('--matting',action='store_true',help='Exercise licensed local NVIDIA runtime with generated video only')
    parser.add_argument('--sender-fps',type=float,default=30,help='Generated frame cadence, independent of negotiated30fps')
    parser.add_argument('--motion-background', type=Path, help='Local GIF/video fixture behind the generated matte')
    parser.add_argument('--assert-mask-hold',action='store_true',help='Generated solid mask; reject redraws that remove alpha during short gaps')
    parser.add_argument('--frame-format',choices=['bgra','nv12','rgba'],default='bgra')
    parser.add_argument('--solidity',type=float,default=0,help='Generated UI probe for foreground alpha boost')
    parser.add_argument('--frame-output',action='store_true',help='Exercise composed BGRA/NV12 packet output using generated video only')
    parser.add_argument('--gpu-output',action='store_true',help='Enable own GPU broker; external generated OBS consumer performs validation')
    parser.add_argument('--gpu-view-cycle',action='store_true',help='Generated GPU output changes canvas then returns')
    parser.add_argument('--gpu-reject-adapter',action='store_true',help='Fault injection: advertise a wrong LUID to the own OBS source')
    parser.add_argument('--pressure', action='store_true', help='Generated GPU pipe delay/age fixture')
    parser.add_argument('--soak-events', action='store_true', help='Repeat generated pause and canvas events per soak barrier')
    parser.add_argument('--consumer-ready-file',type=Path,default=None,help='Generated probe barrier: schedule pause/view changes after consumer attachment')
    parser.add_argument('--stall-seconds',type=float,default=0,help='Pause synthetic video while heartbeats continue, then resume')
    parser.add_argument('--hidden',action='store_true');args=parser.parse_args()
    if args.soak_events and not (args.gpu_output and args.stall_seconds and args.consumer_ready_file):
        parser.error('Soak events require GPU output, a stall duration and a private fixture barrier')
    if args.stall_seconds and not 1.3<=args.stall_seconds<=3.5:parser.error('stall must be between 1.3 and 3.5 seconds')
    if args.stall_seconds and args.seconds<9:parser.error('stall probe needs at least 9 seconds')
    if args.visibility_cycle and (args.seconds<16 or not args.frame_output):parser.error('visibility cycle needs16 seconds and --frame-output')
    if args.start_hidden and not args.visibility_cycle:parser.error('--start-hidden requires --visibility-cycle')
    if not 0<=args.solidity<=100:parser.error('solidity must be within0..100')
    if args.frame_format=='rgba' and not (args.frame_output and args.assert_mask_hold):parser.error('RGBA probe requires --frame-output and --assert-mask-hold')
    if args.gpu_output and args.frame_output:parser.error('select GPU or RAM output')
    if args.gpu_view_cycle and (not args.gpu_output or args.seconds<12):parser.error('GPU view cycle requires GPU output and12seconds')
    if args.gpu_reject_adapter and not args.gpu_output:parser.error('adapter fault requires GPU output')
    if not .5<=args.sender_fps<=30:parser.error('generated sender cadence must be between0.5 and30fps')
    width,height={'720':(1280,720),'1080':(1920,1080),'4k':(3840,2160)}[args.resolution]
    folder=Path('output')/('studio-smoke-'+str(time.time_ns()));folder.mkdir(parents=True)
    fixture=folder/'synthetic.h264'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i',f'testsrc2=size={width}x{height}:rate=30',
        '-frames:v','30','-c:v','libx264','-preset','ultrafast','-tune','zerolatency','-pix_fmt','yuv420p',
        '-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709',
        '-x264-params','aud=1:keyint=30:repeat-headers=1',str(fixture)],check=True)
    ports=queue.Queue();reports=[];errors=[];sent=[];applied=[];stall=[];stall_interval=[];cleared_at=[];resumed_at=[]
    visibility_phase=['visible'];visibility_samples=[];consumer_allowed=threading.Event()
    if not args.visibility_cycle:consumer_allowed.set()
    from ucs import gl_preview
    original_gl=gl_preview.GLPreview
    alpha_redraws=[];mask_patch=None
    if args.assert_mask_hold:
        import numpy as np
        from unittest.mock import patch
        class GeneratedMask:
            def __init__(self,*args):pass
            def infer(self,frame,angle=0,mirror=False):
                mask=np.full((36,64),255,np.uint8)
                if args.frame_format=='rgba' or args.gpu_output:mask[:,:21]=0;mask[:,21:43]=128
                return mask
            def reset(self):pass
            def close(self):pass
        mask_patch=patch('ucs.matting.IsolatedPortraitModel',GeneratedMask);mask_patch.start()
    if args.stall_seconds:
        class StallPreview(original_gl):
            def clear(self):
                if self.frame is not None:cleared_at.append(time.perf_counter())
                super().clear()
            def upload(self,frame):
                super().upload(frame)
                if stall_interval and not resumed_at:resumed_at.append(time.perf_counter())
        gl_preview.GLPreview=StallPreview
    if args.assert_mask_hold:
        base=gl_preview.GLPreview
        class MaskHoldPreview(base):
            def draw(self,*args,**kwargs):
                if kwargs.get('background',{}).get('mode')!='off' and kwargs.get('alpha') is None:alpha_redraws.append(time.perf_counter())
                return super().draw(*args,**kwargs)
        gl_preview.GLPreview=MaskHoldPreview
    class LocalStudio(Desktop):
        grade_observed=False
        def event(self,value):
            if args.visibility_cycle and value.get('event')=='metrics':visibility_samples.append(dict(value,visibility_phase=visibility_phase[0]))
            if value.get('event')=='metrics' and value.get('color_exposure_ev')==.35:self.grade_observed=True
            super().event(value)
        def _run(self):
            try:reports.extend(run('127.0.0.1',0,self.identity,self.output,preview=True,max_sessions=1,ready=ports.put,
                stop_event=self.stop,disconnect_event=self.disconnect,on_event=self.event,decoder='d3d11va',
                renderer='gl',preview_transform=self.preview_transform,control_bus=self.controls,
                background_state=self.background,matting_backend='nvidia',color_state=self.colors,preview_target=self.preview_hwnd,
                metrics_provider=self.diagnostics.snapshot,frame_output=getattr(self,'frame_output',None),preview_visibility=self.preview_visibility))
            except Exception as exc:errors.append(type(exc).__name__);self.stop.set()
        def poll(self):
            super().poll()
            if not self.closing:self.status.configure(text='Teste sintético local, sem câmera')
    # Pairing intent must be a private address; the test listener remains loopback.
    options={'suspend_hidden_preview':False}
    if args.diagnostics:options['diagnostics']=True
    if args.frame_output:options['alpha_output' if args.frame_format=='rgba' else 'frame_output']=True
    if args.gpu_output:options['gpu_output']=True
    root=tk.Tk();controller=LocalStudio(root,'192.168.1.2',folder/'identity',folder/'sessions','Teste local',
                                     renderer='gl',settings_path=folder/'settings.json',**options)
    # LocalStudio replaces the network-ready callback to keep USB/discovery out
    # of this generated experiment, so explicitly enable its alpha test endpoint.
    if args.frame_output and args.frame_format=='rgba':controller.frame_output.enable()
    if args.gpu_output:controller.frame_output.enable()
    if args.pressure:
        if not args.soak_events:
            parser.error('Pressure fixture needs the private soak barrier')
        from ucs.frame_output import REPLY
        pending = ['late', 'expired']
        original_request = controller.frame_output.request
        def delayed_request(data):
            reply = original_request(data)
            if pending and len(reply) == 96:
                fault = pending[0]
                path = args.consumer_ready_file.parent / (fault + '.ready')
                if path.is_file():
                    pending.pop(0)
                    if fault == 'late':
                        time.sleep(.18)
                    else:
                        fields = list(REPLY.unpack(reply[:32]))
                        fields[-2] -= 300
                        reply = REPLY.pack(*fields) + reply[32:]
                    path.with_suffix('.done').touch()
            return reply
        controller.frame_output.request = delayed_request
    if args.gpu_reject_adapter:
        from ucs.gpu_output import GPU_DESCRIPTOR
        original_request=controller.frame_output.request
        def wrong_adapter(data):
            reply=original_request(data)
            if len(reply)==96:
                values=list(GPU_DESCRIPTOR.unpack(reply[32:]));values[8]^=1
                return reply[:32]+GPU_DESCRIPTOR.pack(*values)
            return reply
        controller.frame_output.request=wrong_adapter
    controller.solidity_scale.set(args.solidity)
    root.title('UCS: validação da interface');root.geometry(f'{min(1280,root.winfo_screenwidth()-60)}x{min(820,root.winfo_screenheight()-100)}+20+20')
    if args.hidden:root.withdraw()
    controller.tabs.select(1);controller.colors.set(exposure=.35,contrast=12,saturation=110,shadows=15);studio_ui.sync_widgets(controller)
    if args.matting or args.assert_mask_hold:controller.background.set(mode='transparent')
    if args.motion_background:
        from tkinter import filedialog
        from unittest.mock import patch
        controller.background_mode.set('GIF ou vídeo')
        with patch.object(filedialog, 'askopenfilename', return_value=str(args.motion_background)):
            controller.change_background()
        if controller.background.get()['mode'] != 'motion':
            raise RuntimeError('The background picker did not activate the animation')
    if args.start_hidden:visibility_phase[0]='hidden_idle';controller.preview_visibility.set_visible(False)
    def sender():
        try:
            port=ports.get(timeout=10)
            with connect('127.0.0.1',port,(controller.identity/'fingerprint.txt').read_text()) as sock:
                sock.settimeout(5)
                hello=dict(token=(controller.identity/'token.txt').read_text().strip(),codec='h264',width=width,height=height,fps=30,pixel_format='yuv420p',color='bt709-sdr',controls=1)
                if args.stall_seconds:hello['timing']=1
                sock.sendall(encode(json_message(HELLO,hello)));accepted=read_json(receive(sock));session=accepted['session']
                state={'zoom':1.,'focus':.5,'focus_mode':'auto'}
                caps=dict(session=session,revision=1,active='fixture',cameras=[dict(id='fixture',label='Fonte sintética',available=True)],
                    zoom_min=1,zoom_max=3,focus_auto_supported=True,focus_manual_supported=True,state=state)
                if args.exposure_controls:
                    caps['exposure_bias']={'min':-2,'max':2};state.update(exposure_bias=0,sensor_iso=100,sensor_exposure_us=16666.7)
                sock.sendall(encode(json_message(CAPS,caps)))
                def heartbeat(seq):
                    payload=b'{}'
                    if args.stall_seconds:
                        # Both synthetic endpoints share perf_counter; no clock synchronization claim for a phone.
                        payload=b'{"clock_offset_us":0,"clock_uncertainty_us":1}'
                    sock.sendall(encode(Message(PING,payload,seq=seq,pts_us=seq)))
                    while True:
                        msg=receive(sock)
                        if msg.kind==PONG:break
                        if msg.kind==CONTROL:
                            command=read_json(msg);name=command['control'];applied.append(name)
                            if name=='zoom':state['zoom']=command['value']
                            elif name=='focus':state.update(focus=.5 if command['value']=='auto' else command['value'],focus_mode='auto' if command['value']=='auto' else 'manual')
                            elif name=='exposure_bias' and args.exposure_controls:state['exposure_bias']=command['value']
                            sock.sendall(encode(json_message(RESULT,dict(session=session,request=command['request'],revision=1,status='applied',state=state))))
                units=access_units(fixture.read_bytes());units=list(units);start=time.perf_counter();seq=0;ready_seq=None
                cycle = 0
                while not controller.stop.is_set():
                    for frame,key in units:
                        if controller.stop.is_set():break
                        if args.consumer_ready_file and ready_seq is None and args.consumer_ready_file.is_file():ready_seq=seq
                        if args.soak_events and seq % 3 == 0 and (args.consumer_ready_file.parent / f'cycle-{cycle}.ready').exists():
                            ready_seq = seq
                            cycle += 1
                        stall_at=60 if args.consumer_ready_file is None else (ready_seq+60 if ready_seq is not None else None)
                        if args.stall_seconds and seq==stall_at:
                            began=time.perf_counter()
                            while time.perf_counter()-began<args.stall_seconds and not controller.stop.is_set():
                                heartbeat(seq);time.sleep(.1)
                            elapsed=time.perf_counter()-began;start+=elapsed;stall.append(elapsed)
                            stall_interval.extend((began,time.perf_counter()))
                        time.sleep(max(0,start+seq/args.sender_fps-time.perf_counter()))
                        pts=round(time.perf_counter()*1e6) if args.stall_seconds else round(seq*1e6/args.sender_fps)
                        sock.sendall(encode(Message(VIDEO,frame,seq,pts,int(key))))
                        heartbeat(seq)
                        seq+=1
                sent.append(seq)
                try:sock.sendall(encode(Message(STOP)))
                except OSError:pass
        except Exception as exc:
            if not controller.stop.is_set():errors.append(type(exc).__name__)
    client=threading.Thread(target=sender,daemon=True);client.start()
    output_ids=set();output_errors=[];output_consumer=None;output_alpha_levels=set()
    if args.frame_output:
        def consume_output():
            from ucs.frame_output import REQUEST,REPLY,DESCRIPTOR
            try:
                pixel_format={'nv12':1,'bgra':2,'rgba':3}[args.frame_format]
                payload=width*height*3//2 if pixel_format==1 else width*height*4
                request=REQUEST.pack(0x51534355,1,24,pixel_format,width,height,0)
                while not controller.stop.is_set():
                    if not consumer_allowed.is_set():time.sleep(.02);continue
                    packet=controller.frame_output.request(request)
                    if len(packet)>32:
                        envelope=REPLY.unpack(packet[:32]);frame=DESCRIPTOR.unpack(packet[32:96])
                        if envelope[0]!=0x52534355 or frame[3:6]!=(pixel_format,width,height) or len(packet)!=96+payload or (pixel_format==2 and packet[-1]!=255):
                            raise ValueError('Invalid processed output packet')
                        if pixel_format==3:
                            if frame[-1]!=1:raise ValueError('RGBA packet lost premultiplied alpha flag')
                            output_alpha_levels.update(packet[99::256])
                        output_ids.add(frame[10])
                    time.sleep(1/30)
            except Exception as error:output_errors.append(type(error).__name__)
        output_consumer=threading.Thread(target=consume_output,daemon=True);output_consumer.start()
    root.after(3500,lambda:controller.zoom.set(1.5))
    root.after(4500,controller.focus_auto.invoke)
    root.after(5500,lambda:controller.focus.set(.2))
    if args.soak_events:
        def schedule_cycle(cycle=0):
            if controller.closing:
                return
            if (args.consumer_ready_file.parent / f'cycle-{cycle}.ready').exists():
                root.after(6000, lambda: controller.preview_transform.set(output_format='portrait'))
                root.after(10000, lambda: controller.preview_transform.set(output_format='landscape'))
                cycle += 1
            root.after(100, schedule_cycle, cycle)
        schedule_cycle()
    if args.gpu_view_cycle:
        def schedule_views():
            if args.consumer_ready_file and not args.consumer_ready_file.is_file():
                if not controller.closing:root.after(50,schedule_views)
                return
            root.after(4000,lambda:controller.preview_transform.set(output_format='portrait'))
            root.after(7000,lambda:controller.preview_transform.set(output_format='landscape'))
        schedule_views()
    if args.exposure_controls:root.after(7000,lambda:controller.exposure_bias.set(1.25))
    if args.visibility_cycle:
        def phase(name,visible,consume):
            visibility_phase[0]=name;controller.preview_visibility.set_visible(visible)
            if consume:consumer_allowed.set()
            else:consumer_allowed.clear()
        if args.start_hidden:root.after(4000,lambda:phase('hidden_output',False,True))
        else:
            root.after(4000,lambda:phase('hidden_idle',False,False))
            root.after(7000,lambda:phase('hidden_output',False,True))
        root.after(10000,lambda:phase('restored',True,True))
        root.after(13000,lambda:phase('visible_no_output',True,False))
    root.after(args.seconds*1000,controller.close)
    print(json.dumps({'ui_test_folder':str(folder),'process':__import__('os').getpid()}),flush=True)
    try:
        root.mainloop();client.join(5);controller.worker.join(5)
        if output_consumer:output_consumer.join(2)
        if getattr(controller,'frame_output',None) is not None:controller.frame_output.close()
    finally:
        gl_preview.GLPreview=original_gl
        if mask_patch:mask_patch.stop()
    summary={'errors':errors,'reports':reports,'frames_sent':sent,'controls_applied':applied,
             'video_pause_seconds':stall,
             'processed_output_unique_ids':len(output_ids),'processed_output_errors':output_errors,
             'processed_output_format':args.frame_format,'processed_output_alpha_levels':sorted(output_alpha_levels),
             'foreground_solidity':controller.background.get()['solidity'],
             'visibility_samples':visibility_samples,
             'mask_removed_redraws':len(alpha_redraws),'generated_sender_fps':args.sender_fps,
             'pause_interval_monotonic_s':stall_interval,'preview_clear_monotonic_s':cleared_at,'preview_resumed_monotonic_s':resumed_at,
             'scope':'real loopback TLS, synthetic H.264, hardware decode, embedded GPU color/UI, no device capture'}
    (folder/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    if errors or not reports or not controller.grade_observed or reports[0].get('render_backend')!='gl' or not {'zoom','focus'}<=set(applied):raise SystemExit('Studio integration failed')
    if args.diagnostics and 'ui_diagnostics' not in reports[0]:raise SystemExit('UI diagnostics were not delivered to the session report')
    if args.frame_output and (len(output_ids)<20 or output_errors or reports[0].get('frame_output_published',0)<20):raise SystemExit('Processed frame output failed')
    if args.gpu_output:
        if reports[0].get('gpu_output_cpu_readbacks')!=0:raise SystemExit('GPU sender read back pixels')
        if args.gpu_reject_adapter:
            if not reports[0].get('gpu_output_consumer_error'):raise SystemExit('Mismatched OBS adapter was not reported')
        elif reports[0].get('frame_output_published',0)<20:raise SystemExit('External GPU output consumer did not receive frames')
    expected_alpha=min(255,round(128/(1-.0075*args.solidity)))
    if args.frame_format=='rgba' and not {0,expected_alpha,255}<=output_alpha_levels:raise SystemExit('RGBA output lost generated transparency levels')
    if controller.background.get()['solidity']!=args.solidity:raise SystemExit('Solidity UI control did not update state')
    if args.exposure_controls and 'exposure_bias' not in applied:raise SystemExit('Physical exposure control was not delivered')
    if args.assert_mask_hold and alpha_redraws:raise SystemExit('A short frame gap removed the matched alpha mask')
    if args.visibility_cycle:
        def last_two(name):
            rows=[r for r in visibility_samples if r['visibility_phase']==name]
            if len(rows)<2:raise SystemExit('Missing visibility phase samples: '+name)
            return rows[-2:]
        idle_a,idle_b=last_two('hidden_idle');out_a,out_b=last_two('hidden_output');restored_a,restored_b=last_two('restored');quiet_a,quiet_b=last_two('visible_no_output')
        if idle_b['decoded_frames']<=idle_a['decoded_frames'] or idle_b['processed_render_frames']!=idle_a['processed_render_frames'] or idle_b['display_submitted_frames']!=idle_a['display_submitted_frames'] or idle_b['preview_hidden_skipped_frames']<=idle_a['preview_hidden_skipped_frames']:raise SystemExit('Hidden idle kept rendering or stopped decoding')
        if out_b['processed_render_frames']<=out_a['processed_render_frames'] or out_b['frame_output_published']<=out_a['frame_output_published'] or out_b['display_submitted_frames']!=out_a['display_submitted_frames']:raise SystemExit('Hidden consumer did not receive independently from presentation')
        if restored_b['display_submitted_frames']<=restored_a['display_submitted_frames']:raise SystemExit('Presentation did not resume')
        if quiet_b['frame_output_published']!=quiet_a['frame_output_published'] or quiet_b['display_submitted_frames']<=quiet_a['display_submitted_frames']:raise SystemExit('Output did not become idle independently')
        if args.matting and (idle_b.get('matting_frames',0)!=idle_a.get('matting_frames',0) or out_b.get('matting_frames',0)<=out_a.get('matting_frames',0)):raise SystemExit('Matting failed suspend/resume')
        if args.start_hidden and (idle_b['processed_render_frames'] or idle_b['renderer_info'] or idle_b.get('matting_frames',0)):raise SystemExit('Initially hidden stream allocated/rendered before demand')
    if args.stall_seconds:
        report=reports[0]
        clears_during_pause=[t for t in cleared_at if stall_interval and stall_interval[0]<=t<stall_interval[1]]
        if not stall or len(clears_during_pause)!=1 or not resumed_at or report.get('preview_stale_blank'):
            raise SystemExit('Stale preview did not clear once and resume')
        if report['received_frames']!=report['decoded_frames'] or report['received_frames']<=90:
            raise SystemExit('Reference frames were lost or video did not resume')
        if report.get('capture_to_receive_p95_ms') is None:raise SystemExit('Timing summary missing')
    print('Studio integration PASS',folder/'summary.json',flush=True)

if __name__=='__main__':main()
