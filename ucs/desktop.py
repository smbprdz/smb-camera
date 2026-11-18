"""Local desktop controller: initial QR, LAN discovery and one receiver lifecycle."""
import argparse
from pathlib import Path
import socket
import threading
import time
import tkinter as tk
from tkinter import ttk
from .identity import create
from .pairing import Pairing, Advertisement
from .receiver import run
from .usbmux import TunnelRegistry,monitor
from .view_transform import ViewTransform
from .controls import ControlBus
from .matting import BackgroundState
from .color import ColorState
from . import studio_state
from .ui_diagnostics import UIDiagnostics,measure_poll
from .stream_health import connection_view

def local_address():
    # UDP connect selects a local route; no data is sent to this TEST-NET address.
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.connect(('192.0.2.1',9))
        return sock.getsockname()[0]

class Desktop:
    def __init__(self, root, host, identity, output, name, decoder='cpu',renderer='gl',matting_backend='directml',settings_path='runtime/studio-settings.json',diagnostics=False,frame_output=False,suspend_hidden_preview=True,alpha_output=False,gpu_output=False):
        from .original_recording import OriginalRecording
        self.recording = OriginalRecording()
        self.root = root
        from .preview_visibility import PreviewVisibility
        self.preview_visibility=PreviewVisibility();self.suspend_hidden_preview=suspend_hidden_preview
        self.identity = Path(identity)
        if not (self.identity/'token.txt').exists(): create(self.identity)
        self.pairing = Pairing(host,name,(self.identity/'fingerprint.txt').read_text().strip(),
                              (self.identity/'token.txt').read_text().strip()).validate()
        self.output = Path(output)
        self.decoder = decoder
        self.renderer = renderer
        self.preview_transform=ViewTransform()
        self.controls=ControlBus()
        self.background=BackgroundState();self.matting_backend=matting_backend
        self.colors=ColorState();self.settings_path=Path(settings_path);self.preview_hwnd=None
        self.controls_revision=None
        self.applying_controls=False
        self.pending_zoom=self.pending_focus=self.pending_exposure_bias=None;self.slider_values={}
        self.stop = threading.Event()
        self.usb_registry=TunnelRegistry()
        self.usb_worker=None
        self.disconnect = threading.Event()
        self.lock = threading.Lock()
        self.state = {'state':'starting','metrics':{},'detail':''}
        self.advertisement = None
        self.qr_visible = True
        self.closing = False
        self.widget_properties={};self.last_detail=None
        self.diagnostics=UIDiagnostics(diagnostics)
        self.frame_output=None
        self.native_camera=None
        self.alpha_output=bool(alpha_output or gpu_output)
        if (frame_output or alpha_output or gpu_output) and renderer!='gl':raise ValueError('Frame output requires GL')
        if sum(bool(x) for x in (frame_output,alpha_output,gpu_output))>1:raise ValueError('Select one output endpoint')
        if renderer=='gl':
            import os
            from .frame_output import FramePublisher
            filename='alpha-output.json' if self.alpha_output else f'frame-output-{os.getpid()}.json'
            if gpu_output:
                from .gpu_output import GPUFramePublisher
                self.frame_output=GPUFramePublisher(metadata=Path('runtime')/filename)
            else:self.frame_output=FramePublisher(metadata=Path('runtime')/filename,formats=(3,) if alpha_output else (1,2),enabled=frame_output)
            if not self.alpha_output:
                from .native_camera import NativeCamera
                self.native_camera=NativeCamera(self.frame_output)
        from .studio_ui import build_ui
        build_ui(self)
        self.worker=threading.Thread(target=self._run,daemon=True)
        self.worker.start();root.after(200,self.poll)
        if diagnostics:
            self.heartbeat_expected=self.diagnostics.clock()+.1;root.after(100,self.heartbeat)

    def event(self, value):
        with self.lock:
            if value['event']=='connected': self.state.update(state='connected',metrics={},transport=value['transport'],config=value['config'])
            elif value['event']=='metrics': self.state.update(metrics=value,metrics_at=time.perf_counter())
            elif value['event']=='disconnected': self.state.update(state='waiting',metrics={})
            elif value['event']=='usb_status' and self.state['state']!='connected':self.state['detail']=value['detail']
            elif value['event']=='usb_bytes':print('USB tunnel summary:',value,flush=True)

    def _ready(self, port):
        # Publish the stable alpha endpoint only after binding the receiver.
        # A second failing desktop must not replace the active connection file.
        if self.alpha_output:self.frame_output.enable()
        self.usb_worker=threading.Thread(target=monitor,args=(self.pairing.host,port,self.stop,self.usb_registry,self.event),daemon=True)
        self.usb_worker.start()
        try: self.advertisement=Advertisement(self.pairing,port)
        except Exception:
            with self.lock: self.state['detail']='Descoberta indisponivel; o QR ainda permite conectar pela rede local.'
        with self.lock: self.state['state']='waiting'

    def _run(self):
        try:
            run(self.pairing.host,49200,self.identity,self.output,preview=True,ready=self._ready,
                stop_event=self.stop,disconnect_event=self.disconnect,on_event=self.event,decoder=self.decoder,
                transport_resolver=self.usb_registry.resolve,renderer=self.renderer,preview_transform=self.preview_transform,control_bus=self.controls,
                background_state=self.background,matting_backend=self.matting_backend,
                color_state=self.colors,preview_target=self.preview_hwnd if self.renderer=='gl' else None,
                metrics_provider=self.diagnostics.snapshot,frame_output=self.frame_output,preview_visibility=self.preview_visibility,recording=self.recording)
        except Exception as exc:
            # Log the exception type only; never include pairing values in a diagnostic.
            print('Desktop receiver failure:',type(exc).__name__,flush=True)
            with self.lock: self.state.update(state='error',detail='Nao foi possivel iniciar o receptor. Verifique se outra janela ja esta aberta e as dependencias locais.')
        finally:
            self.stop.set()
            if self.native_camera is not None:self.native_camera.close()
            if self.frame_output is not None:self.frame_output.close()
            if self.usb_worker:self.usb_worker.join(timeout=4)
            if self.advertisement: self.advertisement.close()

    def toggle_qr(self):
        from .studio_ui import toggle_qr
        toggle_qr(self)

    def update_widget(self,widget,**properties):
        # Track individual properties: a range+state update must invalidate a
        # subsequent state-only request. Identical polls do no Tcl/config work.
        known=self.widget_properties.setdefault(widget,{})
        changed={key:value for key,value in properties.items() if key not in known or known[key]!=value}
        if changed:widget.configure(**changed);known.update(changed)

    def check_matting_runtime(self):
        if self.matting_backend != 'nvidia':
            return True
        from .nvidia_vfx import runtime_error
        message = runtime_error()
        self.update_widget(self.recorte_dependency, text=message)
        return not message

    def select_matting_runtime(self):
        from tkinter import filedialog, messagebox
        from .nvidia_vfx import select_runtime
        path = filedialog.askdirectory(parent=self.root, title='Pasta do runtime NVIDIA 0.7.6')
        if not path:
            return
        try:
            select_runtime(path)
        except (ValueError, OSError, RuntimeError) as error:
            messagebox.showerror('Runtime NVIDIA', str(error), parent=self.root)
            return
        self.check_matting_runtime()
        self.background.set(mode=self.background.get()['mode'])

    def change_background(self, _=None):
        from .background_motion import MOTION_SUFFIXES
        mode={'Original':'off','Transparente':'transparent','Imagem':'image','GIF ou vídeo':'motion'}[self.background_mode.get()]
        if mode != 'off' and not self.check_matting_runtime():
            self.refresh_background_picker()
            return
        current=self.background.get()
        path=current['image']
        matches_file=path and ((Path(path).suffix.lower() in MOTION_SUFFIXES) == (mode=='motion'))
        if mode in ('image','motion') and not matches_file:
            self.choose_background()
        else:
            self.background.set(mode=mode)
            self.refresh_background_picker()

    def refresh_background_picker(self):
        state=self.background.get()
        labels={'off':'Original','transparent':'Transparente','image':'Imagem','motion':'GIF ou vídeo'}
        self.background_mode.set(labels[state['mode']])
        self.update_widget(self.background_button,
                           text='Escolher GIF ou vídeo' if state['mode']=='motion' else 'Escolher imagem de fundo')
        media=Path(state['image']).name if state['mode'] in ('image','motion') and state['image'] else ''
        self.update_widget(self.background_file_label, text=media)

    def choose_background(self):
        if not self.check_matting_runtime():
            return
        from tkinter import filedialog
        from .background_motion import verify_motion
        motion=self.background_mode.get()=='GIF ou vídeo'
        filetypes=[('GIF e vídeo','*.gif *.mp4 *.mov *.webm *.mkv')] if motion else [('Imagens','*.png *.jpg *.jpeg *.webp')]
        path=filedialog.askopenfilename(parent=self.root,title='Escolha seu fundo',filetypes=filetypes)
        if path:
            try:
                if motion:
                    verify_motion(path)
                else:
                    from PIL import Image
                    with Image.open(path) as image:
                        if image.format not in ('PNG','JPEG','WEBP') or image.width*image.height>50_000_000:
                            raise ValueError('Imagem incompatível')
                        image.verify()
                self.background.set(mode='motion' if motion else 'image',image=path)
            except Exception:
                self.note.configure(text='Não foi possível abrir o fundo escolhido. Verifique o formato e o tamanho do arquivo.')
        self.refresh_background_picker()

    def zoom_changed(self,value):
        if not self.applying_controls:self.queue_slider('zoom',float(value))

    def focus_changed(self,value):
        if not self.applying_controls:self.queue_slider('focus',float(value))

    def exposure_bias_changed(self,value):
        if not self.applying_controls:self.queue_slider('exposure_bias',float(value))

    def queue_slider(self,control,value):
        if self.closing:return
        self.slider_values[control]=value
        if getattr(self,'pending_'+control) is None:self.send_slider(control)

    def send_slider(self,control):
        setattr(self,'pending_'+control,None)
        value=self.slider_values.pop(control,None)
        if self.closing or value is None:return
        try:self.controls.enqueue(control,value)
        except ValueError:pass
        # Leading update now; trailing updates take the latest intent every100ms.
        # ControlBus still permits only one in-flight command and coalesces values.
        setattr(self,'pending_'+control,self.root.after(100,lambda:self.send_slider(control)))

    def focus_mode_changed(self):
        if not self.applying_controls:
            if self.pending_focus:self.root.after_cancel(self.pending_focus);self.pending_focus=None
            self.slider_values.pop('focus',None)
            self.controls.enqueue('focus','auto' if self.auto_focus.get() else float(self.focus.get()))

    def toggle_native_camera(self):
        if self.native_camera is None:return
        if self.native_camera.snapshot()['state'] in ('starting','running','stopping'):self.native_camera.stop();return
        with self.lock:state=dict(self.state)
        if state['state']=='connected':self.native_camera.start(state.get('config',{}).get('fps',30))

    def refresh_native_camera(self,state):
        if self.native_camera is not None:self.native_camera.refresh_installation()
        native=self.native_camera.snapshot() if self.native_camera is not None else {'available':False,'state':'off','detail':''}
        if self.native_camera is not None:
            if state['state']!='connected':self.native_camera.stop()
            else:self.native_camera.observe(self.frame_output.canvas,state.get('config',{}).get('fps',30))
        active=native['state'] in ('starting','running','stopping')
        self.update_widget(self.native_button,text='Desativar webcam' if active else 'Ativar webcam',state='normal' if native['available'] and (active or state['state']=='connected') else 'disabled')
        detail=native['detail'] or ('Ative a câmera do iPhone e depois a webcam.' if native['available'] else 'O componente de webcam do Windows ainda não está instalado. O pacote de desenvolvimento aguarda assinatura para este notebook.')
        self.update_widget(self.native_status,text=detail)

    def refresh_controls(self):
        snapshot=self.controls.snapshot();caps=snapshot['caps']
        self.update_widget(self.control_status,text=snapshot['status'])
        if not caps:
            for pending in ('pending_zoom','pending_focus','pending_exposure_bias'):
                callback=getattr(self,pending)
                if callback:self.root.after_cancel(callback);setattr(self,pending,None)
            self.slider_values.clear()
            self.lens.set_capabilities(None)
            for widget in (self.zoom,self.focus,self.focus_auto,self.exposure_bias):self.update_widget(widget,state='disabled')
            self.update_widget(self.exposure_label,text='Conecte o iPhone para ajustar a exposição.')
            self.update_widget(self.sensor_label,text='')
            self.controls_revision=None;return
        self.lens.set_capabilities(caps)
        revision=(caps['session'],caps['revision'])
        if self.controls_revision!=revision:
            for pending in ('pending_zoom','pending_focus','pending_exposure_bias'):
                callback=getattr(self,pending)
                if callback:self.root.after_cancel(callback);setattr(self,pending,None)
            self.slider_values.clear()
            self.applying_controls=True
            try:
                self.update_widget(self.zoom,from_=caps['zoom_min'],to=caps['zoom_max'],state='normal' if caps['zoom_max']>caps['zoom_min'] else 'disabled')
                self.zoom.set(caps['state']['zoom']);self.focus.set(caps['state']['focus'])
                self.auto_focus.set(caps['state']['focus_mode']=='auto')
                exposure=caps.get('exposure_bias')
                if exposure is not None:
                    self.update_widget(self.exposure_bias,from_=exposure['min'],to=exposure['max'],state='normal' if exposure['max']>exposure['min'] else 'disabled')
                    self.exposure_bias.set(caps['state']['exposure_bias'])
                else:self.update_widget(self.exposure_bias,state='disabled')
                self.controls_revision=revision
            finally:self.applying_controls=False
        state=caps['state']
        if not snapshot['busy'] and self.pending_zoom is None and self.pending_focus is None and self.pending_exposure_bias is None:
            self.applying_controls=True
            try:
                if abs(self.zoom.get()-state['zoom'])>1e-6:self.zoom.set(state['zoom'])
                if abs(self.focus.get()-state['focus'])>1e-6:self.focus.set(state['focus'])
                automatic=state['focus_mode']=='auto'
                if self.auto_focus.get()!=automatic:self.auto_focus.set(automatic)
                if caps.get('exposure_bias') is not None and abs(self.exposure_bias.get()-state['exposure_bias'])>1e-6:self.exposure_bias.set(state['exposure_bias'])
            finally:self.applying_controls=False
        self.update_widget(self.zoom_label,text=f"Zoom aplicado: {state['zoom']:.2f}x")
        self.update_widget(self.focus_label,text=f"Foco aplicado: {state['focus']:.2f}" if caps['focus_manual_supported'] else 'Foco fixo nesta lente')
        self.update_widget(self.focus_auto,state='normal' if caps['focus_auto_supported'] and caps['focus_manual_supported'] else 'disabled')
        self.update_widget(self.focus,state='normal' if caps['focus_manual_supported'] and not self.auto_focus.get() else 'disabled')
        exposure=caps.get('exposure_bias')
        self.update_widget(self.exposure_bias,state='normal' if exposure is not None and exposure['max']>exposure['min'] else 'disabled')
        self.update_widget(self.exposure_label,text=f"Compensação confirmada: {state['exposure_bias']:+.2f} EV" if exposure is not None else 'Requer app iPhone 0.8 e uma lente compatível.')
        iso=state.get('sensor_iso');duration=state.get('sensor_exposure_us')
        self.update_widget(self.sensor_label,text=f'Última leitura: ISO {iso:.0f} · {duration/1000:.2f} ms' if iso is not None and duration is not None else '')

    def toggle_recording(self):
        from tkinter import filedialog, messagebox
        session, mic, active, stopping, _ = self.recording.snapshot()
        if active:
            self.recording.stop()
            return
        if not session:
            return
        directory = filedialog.askdirectory(parent=self.root, title='Pasta para o vídeo original')
        if directory:
            try:
                self.recording.start(directory, session, mic and self.record_mic.get())
            except ValueError as exc:
                messagebox.showinfo('Gravação original', str(exc), parent=self.root)

    def open_recording_folder(self):
        import os
        from tkinter import messagebox
        path = self.recording.progress().file
        if path is not None:
            try:
                os.startfile(str(path.parent))
            except OSError:
                messagebox.showinfo('Gravação original', 'A pasta da gravação está indisponível.', parent=self.root)

    def refresh_recording(self):
        take = self.recording.progress()
        busy = take.phase in ('starting', 'recording', 'finishing')
        seconds = take.duration_us // 1_000_000
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        duration = f'{hours}:{minutes:02}:{seconds:02}' if hours else f'{minutes:02}:{seconds:02}'
        button = {
            'starting': '■  Cancelar início',
            'recording': '■  Parar gravação',
            'finishing': 'Finalizando…',
        }.get(take.phase, '●  Gravar original')
        state = {
            'starting': 'Aguardando microfone' if take.waiting_audio else 'Aguardando quadro-chave',
            'recording': f'GRAVANDO  {duration}',
            'finishing': f'Finalizando  {duration}',
            'saved': f'Salvo  {duration}',
            'error': 'Gravação interrompida',
        }.get(take.phase, 'Pronto para gravar' if take.available else 'Aguardando iPhone')
        if self.sidebar_collapsed:
            button = '…' if take.phase == 'finishing' else ('■' if busy else '●')
            state = duration if busy else ''
        enabled = not self.closing and take.phase != 'finishing' and (busy or take.available)
        self.update_widget(self.record_button, text=button,
                           state='normal' if enabled else 'disabled',
                           style='RecordActive.TButton' if busy else 'RecordReady.TButton')
        self.update_widget(self.record_state, text=state,
                           style='RecordingLive.TLabel' if take.phase == 'recording' else 'RecordingState.TLabel')
        self.update_widget(self.mic_check, state='normal' if take.mic_available and not busy else 'disabled')
        size = take.video_format
        self.update_widget(self.record_format, text=f'MOV · {size[0]}×{size[1]} · {size[2]} fps' if size else 'MOV · H.264 original')
        self.update_widget(self.record_frames, text=f'Quadros gravados  {take.frames}')
        self.update_widget(self.record_gaps, text=f'Saltos na origem  {take.source_gaps}',
                           foreground='#ffb089' if take.source_gaps else '')
        if busy or take.phase in ('saved', 'error'):
            if take.audio_samples:
                audio = f'Áudio gravado · {take.audio_rate/1000:g} kHz'
            elif take.with_audio:
                audio = 'Mic · aguardando áudio' if busy else 'Áudio ausente'
            else:
                audio = 'Sem áudio'
        elif take.mic_available:
            audio = 'Com microfone' if self.record_mic.get() else 'Sem áudio · mic disponível'
        else:
            audio = 'Mic indisponível' if take.available else ''
        self.update_widget(self.record_audio, text=audio)

        result = take.detail
        if take.file:
            result = f'{result}\nArquivo parcial' if result else take.file.name
        self.update_widget(self.record_result, text=result)
        if result:
            if not self.record_result.winfo_manager():
                self.record_result.pack(anchor='w',pady=(5,0),before=self.record_folder if self.record_folder.winfo_manager() else None)
        else:
            self.record_result.pack_forget()
        if take.file:
            if not self.record_folder.winfo_manager():
                self.record_folder.pack(fill='x',pady=(5,0))
        else:
            self.record_folder.pack_forget()

    def open_obs_module(self):
        import os
        os.startfile(str(Path(__file__).resolve().parents[1]/'integrations/obs'))

    def refresh_obs_output(self,state):
        publisher=self.frame_output
        if publisher is None or not self.alpha_output:
            self.update_widget(self.obs_output_status,text='Saída para OBS não está ativa nesta janela.')
            self.update_widget(self.obs_output_mode,text='A captura e a prévia continuam disponíveis.');return
        info=publisher.snapshot();gpu=getattr(publisher,'gpu',False)
        error=info.get('gpu_output_consumer_error') or info.get('frame_output_error')
        if error:text=error
        elif state['state']!='connected':text='Ative a câmera do iPhone para enviar a imagem.'
        elif publisher.wanted():text='A fonte OBS está solicitando a imagem tratada.'
        else:text='Saída pronta. Aguardando a fonte SMB Camera no OBS.'
        self.update_widget(self.obs_output_status,text=text)
        self.update_widget(self.obs_output_mode,text=('GPU experimental: imagem compartilhada, um leitor por janela.' if gpu else 'Compatibilidade: imagem transferida por memória.')+
                           '\nEscolha Transparente em Fundo e recorte para preservar o recorte.')

    def heartbeat(self):
        if self.closing:return
        now=self.diagnostics.clock();self.diagnostics.record('heartbeat',(now-self.heartbeat_expected)*1000)
        self.heartbeat_expected=now+.1;self.root.after(100,self.heartbeat)

    @measure_poll
    def poll(self):
        if self.suspend_hidden_preview:self.preview_visibility.set_visible(self.root.state() not in ('iconic','withdrawn'))
        self.refresh_controls()
        with self.lock: state=dict(self.state)
        self.refresh_native_camera(state)
        self.refresh_obs_output(state)
        self.refresh_recording()
        if self.closing:
            self.update_widget(self.status,text='Encerrando camera...')
            if not self.worker.is_alive(): self.root.destroy();return
        else:
            labels={'starting':'Preparando receptor...','waiting':'PC pronto. Aguardando iPhone.',
                    'connected':'iPhone conectado','error':'Receptor indisponivel'}
            self.update_widget(self.status,text=labels[state['state']]+(' por USB' if state.get('transport','').startswith('USB') and state['state']=='connected' else ''))
            self.update_widget(self.stop_button,state='normal' if state['state']=='connected' else 'disabled')
            self.update_widget(self.pair_button,state='disabled' if state['state']=='connected' else 'normal')
            if state['state']=='connected' and self.qr_visible: self.toggle_qr()
            metrics=state['metrics']
            video_status,connection_values=connection_view(state,time.perf_counter())
            self.update_widget(self.video_status,text='●  '+video_status.upper())
            for name,value in connection_values.items():self.update_widget(self.connection_labels[name],text=value)
            if self.background.get()['mode']!='off':
                matte_status=metrics.get('matting_status','loading')
                text={'loading':'Preparando recorte na GPU...','ready':'Recorte experimental ativo. Confira cabelo e movimento.',
                      'late':'O recorte excedeu o atraso permitido; reduza a carga ou volte ao original.',
                      'error':metrics.get('matting_error','Recorte indisponivel.'),'off':'Recorte aguardando imagem.'}.get(matte_status,'Preparando recorte...')
                if self.background.get()['mode']=='motion':
                    text = (metrics.get('background_media_error') or text) if self.renderer=='gl' else 'Fundo animado requer OpenGL.'
                self.update_widget(self.matting_status,text=text)
            else:self.update_widget(self.matting_status,text='Recorte desligado.')
            self.preview_surface.status(state['state']=='connected' and self.renderer=='gl')
            transport='USB (cabo)' if state.get('transport','').startswith('USB') else 'Wi-Fi/LAN'
            config=state.get('config',{})
            self.update_widget(self.metrics,text=(f"{transport} | {config.get('width','?')}x{config.get('height','?')}\n"
                                         f"Previa: {metrics.get('preview_submit_fps',0):.1f} FPS | {metrics.get('receive_mbps',0):.1f} Mbps"
                                         if metrics else 'Ative a camera pelo iPhone.'))
            if state['detail'] and state['detail']!=self.last_detail:
                self.note.configure(text=state['detail']);self.last_detail=state['detail']
        self.root.after(200,self.poll)

    def close(self):
        try:studio_state.write(self.settings_path,studio_state.snapshot(self.colors,self.preview_transform,self.background))
        except Exception as exc:print('Studio settings save failed:',type(exc).__name__,flush=True)
        self.recording.stop()
        self.closing=True;self.stop.set();self.disconnect.set()
        self.update_widget(self.stop_button,state='disabled')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',default=None)
    parser.add_argument('--identity',default='runtime/identity')
    parser.add_argument('--output',default='output/device-sessions-v03')
    parser.add_argument('--name',default=socket.gethostname())
    parser.add_argument('--decoder',choices=['cpu','d3d11va'],default='cpu')
    parser.add_argument('--renderer',choices=['opencv','sdl','gl'],default='gl')
    parser.add_argument('--settings',default='runtime/studio-settings.json')
    parser.add_argument('--diagnostics',action='store_true',help='Local numeric UI timings only')
    outputs=parser.add_mutually_exclusive_group()
    outputs.add_argument('--frame-output',action='store_true',help='Experimental local opaque frame publisher; does not install/register a webcam')
    outputs.add_argument('--alpha-output',action='store_true',help='Experimental own RGBA/alpha endpoint; no OBS module installed or activated')
    outputs.add_argument('--gpu-output',action='store_true',help='Experimental own keyed GPU alpha endpoint, one OBS reader; no plugin installed')
    parser.add_argument('--matting-backend',choices=['directml','cuda','nvidia'],default='directml')
    args=parser.parse_args()
    root=tk.Tk();controller=Desktop(root,args.host or local_address(),args.identity,args.output,args.name,args.decoder,args.renderer,args.matting_backend,args.settings,args.diagnostics,args.frame_output,alpha_output=args.alpha_output,gpu_output=args.gpu_output)
    try: root.mainloop()
    except KeyboardInterrupt: pass
    finally:
        controller.stop.set();controller.disconnect.set();controller.worker.join(timeout=8)

if __name__=='__main__': main()
