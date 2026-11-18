"""Packet-boundary decoding and a one-frame preview mailbox.

No demux probing, generated playback clock, frame hashing or second decoder.
This CPU laboratory adapter is not the planned MF/D3D native production engine.
"""
from collections import deque
from fractions import Fraction
import threading
import time
from .stream_health import PreviewFreshness

class LatestFrame:
    def __init__(self):
        self.condition = threading.Condition()
        self.value = None
        self.closed = False
        self.replaced = 0

    def put(self, value):
        with self.condition:
            if self.closed: return
            if self.value is not None: self.replaced += 1
            self.value = value
            self.condition.notify()

    def take(self, timeout=.03):
        with self.condition:
            if self.value is None and not self.closed: self.condition.wait(timeout)
            value, self.value = self.value, None
            return value

    def close(self):
        with self.condition:
            self.closed = True
            self.value = None
            self.condition.notify_all()

class PacketDecoder:
    def __init__(self, config, backend='cpu'):
        import av
        self.av = av
        self.config = config
        if backend not in ('cpu','d3d11va'): raise ValueError('Unsupported preview decoder')
        self.backend = backend
        if backend == 'd3d11va':
            from av.codec.hwaccel import HWAccel
            self.codec = av.CodecContext.create('h264','r',hwaccel=HWAccel('d3d11va',allow_software_fallback=False))
        else: self.codec = av.CodecContext.create('h264', 'r')
        self.codec.thread_count = 1
        self.codec.flags |= av.codec.context.Flags.low_delay
        self.codec.open()
        if backend != 'cpu' and not self.codec.is_hwaccel:
            raise RuntimeError('Requested hardware decoder was not activated')
        self.frames = 0
        self.dimensions = None
        self.times = deque(maxlen=300)

    def decode(self, data, pts_us):
        packet = self.av.Packet(data)
        packet.pts = packet.dts = pts_us
        packet.time_base = Fraction(1, 1_000_000)
        start = time.perf_counter()
        try:
            frames = self.codec.decode(packet)
        except self.av.FFmpegError as exc:
            raise ValueError('H.264 access unit could not be decoded') from exc
        self.times.append((time.perf_counter()-start)*1000)
        for frame in frames:
            self.dimensions = [frame.width, frame.height]
            if self.dimensions != [self.config['width'], self.config['height']]:
                raise ValueError('decoded dimensions differ from negotiated format')
            self.frames += 1
        return frames

    def snapshot(self):
        values = sorted(self.times)
        return {'decoded_frames':self.frames, 'decoded_dimensions':self.dimensions,
                'decoder_backend':self.backend,'decoder_hardware_active':self.codec.is_hwaccel,
                'decode_p50_ms':values[len(values)//2] if values else None,
                'decode_p95_ms':values[int((len(values)-1)*.95)] if values else None}

class LivePreviewSink:
    def __init__(self, folder, config, backend='cpu', renderer='opencv',transform=None,background=None,matting_backend='directml',color=None,preview_target=None,frame_output=None,preview_visibility=None):
        # Import/initialize before ACCEPT so first packets do not queue behind imports.
        if renderer not in ('opencv','sdl','gl'):raise ValueError('Unsupported preview renderer')
        self.renderer_type=renderer
        if frame_output is not None and renderer!='gl':raise ValueError('Frame output requires the GL compositor')
        self.frame_output=frame_output;self.output_times=deque(maxlen=120)
        self.preview_visibility=preview_visibility;self.rendered=0;self.hidden_skipped=0;self.presentation_suspended=False
        from .view_transform import ViewTransform
        self.transform=transform or ViewTransform()
        from .matting import BackgroundState
        self.background=background or BackgroundState()
        from .color import ColorState
        self.colors=color or ColorState();self.preview_target=preview_target
        self.background_media_error=''
        self.matting_backend=matting_backend;self.matte=None;self.last_background_generation=-1;self.camera_revision=0
        if renderer=='opencv':
            import cv2
            cv2.setNumThreads(1)
            self.cv2 = cv2
        else:
            from .sdl_preview import native_path
            native_path()
        self.decoder = PacketDecoder(config,backend)
        self.slot = LatestFrame()
        self.failure = None
        self.submitted = 0
        self.last_submit_time=None;self.submit_gaps=deque(maxlen=300)
        self.freshness=PreviewFreshness()
        self.preview_age = deque(maxlen=300)
        self.convert_times = deque(maxlen=300)
        self.present_times = deque(maxlen=300)
        self.ui_times = deque(maxlen=300)
        self.upload_times = deque(maxlen=300)
        self.renderer_info = {}
        self.thread = threading.Thread(target=self._display, daemon=True)
        self.thread.start()

    def put(self, data, pts_us, seq, arrival):
        if self.failure: raise RuntimeError(self.failure)
        for frame in self.decoder.decode(data, pts_us):
            self.slot.put((frame, seq, arrival))

    def _display(self):
        if self.renderer_type in ('sdl','gl'):
            self._display_sdl();return
        cv = self.cv2
        title = 'Universal Camera Studio - '+str(self.decoder.config['width'])+'x'+str(self.decoder.config['height'])
        created = False
        try:
            while not self.slot.closed:
                item = self.slot.take()
                now=time.perf_counter()
                if created and self.freshness.should_clear(now):
                    import numpy as np
                    cv.imshow(title,np.zeros((self.decoder.config['height'],self.decoder.config['width'],3),dtype=np.uint8))
                if item is not None and not self.freshness.accept(item[2],now):item=None
                if item is not None:
                    frame, _, arrival = item
                    if not created:
                        cv.namedWindow(title, cv.WINDOW_NORMAL)
                        cv.resizeWindow(title,1280,720)
                        created = True
                    convert_start=time.perf_counter()
                    pixels = frame.to_ndarray(format='bgr24')
                    self.convert_times.append((time.perf_counter()-convert_start)*1000)
                    present_start=time.perf_counter()
                    cv.imshow(title, pixels)
                    self.present_times.append((time.perf_counter()-present_start)*1000)
                    self._submitted(arrival)
                if created:
                    ui_start=time.perf_counter()
                    key = cv.waitKey(1)
                    self.ui_times.append((time.perf_counter()-ui_start)*1000)
                    if key in (27, ord('q')) or cv.getWindowProperty(title, cv.WND_PROP_VISIBLE) < 1:
                        self.failure = 'preview closed by user'
                        break
        except Exception as exc:
            self.failure = 'preview: '+str(exc)
        finally:
            if created:
                try: cv.destroyWindow(title)
                except Exception: pass
            self.slot.close()

    def _display_sdl(self):
        from .sdl_preview import SDLPreview
        renderer=None
        previous_visible=True
        try:
            if self.renderer_type=='gl':
                from .gl_preview import GLPreview
            while not self.slot.closed:
                visible=self.preview_visibility is None or self.preview_visibility.is_visible()
                item=self.slot.take(timeout=.008 if visible else .04)
                background=self.background.get();view=self.transform.get();alpha=None
                if self.frame_output is not None and item is not None:
                    from .view_transform import crop_geometry
                    self.frame_output.set_canvas(*crop_geometry(item[0].width,item[0].height,view['angle'],view['output_format'],view['pan_x'],view['pan_y'])['canvas'])
                output_wanted=self.frame_output is not None and self.frame_output.wanted()
                if renderer is not None and getattr(self.frame_output,'gpu',False):self.frame_output.idle(renderer)
                self.presentation_suspended=not visible
                if visible and not previous_visible and renderer is not None:
                    renderer.clear();renderer.present();self.freshness.blank=True
                previous_visible=visible
                if not visible and not output_wanted:
                    if self.matte:self.matte.set_suspended(True)
                    if renderer is not None and self.renderer_type=='gl':
                        renderer.suspend_background_motion()
                    if item is not None:self.hidden_skipped+=1
                    if renderer is not None and not renderer.poll():self.failure='preview closed by user';break
                    continue
                if self.matte:self.matte.set_suspended(False)
                render_options={'color':self.colors.get(),'preview':visible} if self.renderer_type=='gl' else {}
                if background['mode']=='off' and self.matte is not None:self.matte.cancel()
                if background['mode']!='off':
                    if self.matte is None:
                        from .matting import MatteWorker
                        self.matte=MatteWorker(self.background,self.matting_backend)
                    if item is not None:self.matte.submit(item,background['generation'],view['angle'],self.camera_revision,view['mirror'])
                    result=self.matte.take((background['generation'],view['angle'],view['mirror'],self.camera_revision))
                    if result is not None:
                        frame,seq,arrival,alpha,generation=result;item=(frame,seq,arrival)
                    else:item=None
                now=time.perf_counter()
                if visible and renderer is not None and self.freshness.should_clear(now):
                    renderer.clear();renderer.present()
                if visible and renderer is not None and not self.freshness.blank and background['generation']!=self.last_background_generation:
                    renderer.draw(**view,background=background,**render_options)
                    renderer.present();self.last_background_generation=background['generation']
                # Keep the last matched frame/mask through a short input gap.
                # Clearing alpha at250ms made people disappear at <4fps even
                # though the preview frame itself remained valid for1second.
                # PreviewFreshness still clears once at its real frame deadline.
                if item is not None:
                    frame,_,arrival=item
                    if renderer is None:
                        cls=GLPreview if self.renderer_type=='gl' else SDLPreview
                        options={'hwnd':self.preview_target} if self.renderer_type=='gl' else {}
                        renderer=cls(frame.width,frame.height,
                            'Universal Camera Studio - GPU '+str(frame.width)+'x'+str(frame.height),**options)
                        self.renderer_info=renderer.info
                        renderer.clear()
                        if visible:renderer.present()
                    # GPU/context initialization can itself take longer than the
                    # deadline. Recheck afterwards, before displaying this frame.
                    if self.freshness.accept(arrival,time.perf_counter()):
                        start=time.perf_counter();renderer.upload(frame)
                        self.upload_times.append((time.perf_counter()-start)*1000)
                        start=time.perf_counter();renderer.draw(**view,alpha=alpha,background=background,**render_options)
                        self.rendered+=1
                        if visible:renderer.present()
                        self.last_background_generation=background['generation']
                        self.present_times.append((time.perf_counter()-start)*1000)
                        if visible:self._submitted(arrival)
                        if self.frame_output is not None:
                            self.frame_output.set_canvas(*renderer.canvas)
                            if self.frame_output.wanted():
                                try:
                                    pixel_format=self.frame_output.requested_format()
                                    if pixel_format is not None:
                                        export_at=time.perf_counter()
                                        if getattr(self.frame_output,'gpu',False):self.frame_output.publish_render(renderer,arrival)
                                        else:
                                            w,h,data=renderer.capture_output(pixel_format)
                                            self.frame_output.publish(w,h,data,arrival,pixel_format)
                                        self.output_times.append((time.perf_counter()-export_at)*1000)
                                except Exception:self.frame_output.fail()
                if renderer is not None:
                    if self.renderer_type=='gl':
                        self.background_media_error=renderer.motion_error
                    start=time.perf_counter();running=renderer.poll()
                    self.ui_times.append((time.perf_counter()-start)*1000)
                    if not running:
                        self.failure='preview closed by user';break
        except Exception as exc:self.failure='native preview: '+str(exc)
        finally:
            if self.matte:self.matte.close()
            if renderer and getattr(self.frame_output,'gpu',False):self.frame_output.release_renderer(renderer)
            if renderer:renderer.close()
            self.slot.close()

    def _submitted(self,arrival):
        now=time.perf_counter()
        if self.last_submit_time is not None:self.submit_gaps.append((now-self.last_submit_time)*1000)
        self.last_submit_time=now;self.submitted+=1;self.preview_age.append((now-arrival)*1000)

    def snapshot(self):
        values = sorted(self.preview_age)
        def p95(samples):
            values=sorted(samples)
            return values[int((len(values)-1)*.95)] if values else None
        grading=self.colors.get()
        return dict(self.decoder.snapshot(), display_submitted_frames=self.submitted,
                    processed_render_frames=self.rendered,preview_hidden_skipped_frames=self.hidden_skipped,
                    preview_presentation_suspended=self.presentation_suspended,
                    display_replaced_frames=self.slot.replaced,
                    receive_to_preview_submit_p95_ms=values[int((len(values)-1)*.95)] if values else None,
                    preview_queue_capacity=1, decoder_kind='PyAV H.264 '+self.decoder.backend,
                    render_backend=self.renderer_type,renderer_info=self.renderer_info,
                    preview_transform=self.transform.get(),
                    gpu_colour_conversion=self.renderer_type in ('sdl','gl'),upload_p95_ms=p95(self.upload_times),
                    convert_p95_ms=p95(self.convert_times),
                    window_submit_p95_ms=p95(self.present_times),window_pump_p95_ms=p95(self.ui_times),
                    background_mode=self.background.get()['mode'],
                    background_media_error=self.background_media_error,
                    background_solidity=self.background.get()['solidity'],
                    color_active=self.renderer_type=='gl' and grading['active'],
                    color_exposure_ev=grading['exposure'],lut_loaded=grading['lut'] is not None,
                    preview_frame_gap_p95_ms=p95(self.submit_gaps),
                    preview_frame_gap_max_ms=max(self.submit_gaps) if self.submit_gaps else None,
                    preview_stale_blank=self.freshness.blank,
                    preview_stale_clears=self.freshness.clears,
                    preview_expired_frames=self.freshness.expired_frames,
                    preview_last_submit_monotonic_s=self.last_submit_time,
                    frame_output_readback_p95_ms=None if getattr(self.frame_output,'gpu',False) else p95(self.output_times),
                    frame_output_submit_p95_ms=p95(self.output_times),
                    **(self.frame_output.snapshot() if self.frame_output is not None else {'frame_output_enabled':False}),
                    **(self.matte.snapshot() if self.matte else {'matting_status':'off'}))

    def close(self):
        self.slot.close()
        self.thread.join(timeout=3)
        if self.frame_output is not None:self.frame_output.disconnect()
        return 1 if self.failure or self.thread.is_alive() else 0
