"""TLS receiver: direct packet preview or bounded FFmpeg/hash laboratory verifier."""
import argparse
import hmac
import json
from pathlib import Path
import queue
import re
import shutil
import socket
import ssl
import subprocess
import threading
import time
import uuid
from .protocol import *
from .timing import pong_timestamps,phone_metrics
from .stream_health import StreamWindow

class DecodeSink:
    def __init__(self, folder, decoder='cpu', fps=30):
        if not shutil.which('ffmpeg'):
            raise FileNotFoundError('Install FFmpeg or add it to PATH')
        self.output = open(folder/'decoded.framemd5', 'wb')
        self.errors = open(folder/'decoder.log', 'wb')
        accel = ['-hwaccel', 'd3d11va'] if decoder == 'd3d11va' else []
        self.proc = subprocess.Popen(['ffmpeg', '-hide_banner', '-loglevel', 'verbose',
            '-flags', 'low_delay', '-threads', '1',
            '-xerror', *accel, '-probesize', '32768', '-analyzeduration', '0',
            '-f', 'h264', '-framerate', str(fps), '-i', 'pipe:0', '-map', '0:v:0',
            '-fps_mode', 'passthrough', '-pix_fmt', 'yuv420p', '-f', 'framemd5', 'pipe:1'],
            stdin=subprocess.PIPE, stdout=self.output, stderr=self.errors)
        self.q = queue.Queue(maxsize=8)
        self.failure = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        try:
            while True:
                data = self.q.get()
                if data is None:
                    break
                self.proc.stdin.write(data)
                self.proc.stdin.flush()
        except (OSError, ValueError) as exc:
            self.failure = str(exc)
        finally:
            try: self.proc.stdin.close()
            except OSError: pass

    def put(self, data):
        if self.failure:
            raise ProtocolError('decoder failed')
        try: self.q.put_nowait(data)
        except queue.Full as exc:
            # Do not silently drop reference frames and corrupt the GOP.
            raise ProtocolError('decoder backlog: restart stream at IDR') from exc

    def close(self):
        try: self.q.put(None, timeout=3)
        except queue.Full: self.proc.kill()
        self.thread.join(timeout=8)
        if self.thread.is_alive():
            self.proc.kill()
            self.thread.join(timeout=2)
        try: code = self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill(); code = self.proc.wait()
        self.output.close()
        self.errors.close()
        return code

def serve_session(sock, token, output, preview=False, decoder='cpu', stop_event=None, disconnect_event=None, on_event=None,
                  transport='Wi-Fi/LAN TCP/TLS',renderer='opencv',preview_transform=None,control_bus=None,
                  background_state=None,matting_backend='directml',color_state=None,preview_target=None,metrics_provider=None,frame_output=None,preview_visibility=None,recording=None):
    sock.settimeout(5)
    msg = receive(sock)
    if msg.kind != HELLO:
        raise ProtocolError('HELLO required')
    hello = read_json(msg)
    timing_enabled = type(hello.get('timing')) is int and hello['timing']==1
    mic = recording is not None and hello.get('mic') == 'pcm-s16le-v1'
    mic_requested = False
    mic_packet_seen = False
    controls_enabled=control_bus is not None and type(hello.get('controls')) is int and hello['controls']==1
    control_session=uuid.uuid4().hex if controls_enabled else None
    supplied = hello.get('token')
    if not isinstance(supplied, str) or not hmac.compare_digest(supplied.encode(), token.encode()):
        raise ProtocolError('authentication failed')
    config = validate_stream(hello)
    folder = Path(output)/uuid.uuid4().hex
    folder.mkdir(parents=True)
    if preview:
        from .live_preview import LivePreviewSink
        sink = LivePreviewSink(folder, config, decoder,renderer,preview_transform,background_state,matting_backend,color_state,preview_target,frame_output,preview_visibility)
    else:
        sink = DecodeSink(folder, decoder, config['fps'])
    count = missing = byte_count = 0
    last_seq = last_pts = first_pts = None
    first_arrival = last_arrival = None
    status, error = 'disconnected', None
    start = time.perf_counter()
    last_stats_time, last_stats_count = start, 0
    offset_floor = None
    delay_variation = 0
    sender_metrics={}
    health=StreamWindow()
    last_stats_bytes=0
    last_stats_display=0
    try:
        accepted={'version':1,'stream':config}
        if recording is not None:
            recording.connect(config['fps'], mic)
        if mic: accepted['mic'] = 'pcm-s16le-v1'
        if timing_enabled:accepted['timing']=1
        if controls_enabled:
            control_bus.begin(control_session)
            accepted.update(controls=1,session=control_session)
        sock.sendall(encode(json_message(ACCEPT,accepted)))
        if on_event: on_event({'event':'connected','config':config,'transport':transport})
        while True:
            if (stop_event and stop_event.is_set()) or (disconnect_event and disconnect_event.is_set()):
                status = 'stopped'; break
            if mic:
                want_mic = recording.wants_audio()
                if want_mic != mic_requested:
                    mic_requested = want_mic
                    sock.sendall(encode(Message(MIC, bytes([mic_requested]))))
                    mic_packet_seen = False
                    print(json.dumps({'event':'record_mic_request','enabled':mic_requested}), flush=True)
            if controls_enabled:
                command=control_bus.next_message()
                if command:sock.sendall(encode(command))
            msg = receive(sock)
            if mic and msg.kind in (AUDIO, MIC_ERROR):
                if mic_requested:
                    if msg.kind == MIC_ERROR:
                        print(json.dumps({'event':'record_mic_error'}), flush=True)
                        recording.stop('Microfone indisponível. Confira a permissão no iPhone.')
                    else:
                        try:
                            pcm_format(msg.payload)
                        except ProtocolError:
                            recording.stop('Formato de áudio incompatível.')
                        else:
                            if not mic_packet_seen:
                                print(json.dumps({'event':'record_mic_first_packet'}), flush=True)
                                mic_packet_seen = True
                            recording.offer(msg)
                continue
            if msg.kind == STOP:
                status = 'stopped'; break
            if msg.kind == PING:
                receive_us=round(time.perf_counter()*1e6)
                if timing_enabled:
                    sender_metrics=phone_metrics(read_json(msg))
                    health.phone_sample(sender_metrics,receive_us/1e6)
                    payload=pong_timestamps(receive_us,round(time.perf_counter()*1e6))
                else:payload=msg.payload
                sock.sendall(encode(Message(PONG, payload, msg.seq, msg.pts_us)))
                continue
            if msg.kind in (CAPS,RESULT):
                if not controls_enabled:raise ProtocolError('unnegotiated camera control message')
                if msg.kind==CAPS:
                    control_bus.update(read_json(msg))
                    if preview:sink.camera_revision+=1
                else:control_bus.result(read_json(msg))
                continue
            if msg.kind != VIDEO:
                raise ProtocolError('unexpected message in streaming state')
            if last_seq is not None and (msg.seq <= last_seq or msg.pts_us <= last_pts):
                raise ProtocolError('non-monotonic frame sequence or timestamp')
            if count == 0 and not msg.flags & 1:
                raise ProtocolError('first frame must be IDR with SPS/PPS')
            if not msg.payload.startswith((b'\0\0\0\1', b'\0\0\1')):
                raise ProtocolError('Annex B required')
            if count == 0:
                types={msg.payload[m.end()] & 31 for m in re.finditer(b'\x00\x00(?:\x00)?\x01',msg.payload) if m.end()<len(msg.payload)}
                if not {5,7,8}.issubset(types):
                    raise ProtocolError('first access unit lacks IDR/SPS/PPS')
            if last_seq is not None: missing += msg.seq-last_seq-1
            now = time.perf_counter()
            first_arrival = now if first_arrival is None else first_arrival
            last_arrival = now
            health.video(now,msg.pts_us)
            first_pts = msg.pts_us if first_pts is None else first_pts
            if preview:
                sink.put(msg.payload, msg.pts_us, msg.seq, now)
            else:
                sink.put(msg.payload)
            if recording is not None:
                recording.offer(msg)
            last_seq, last_pts = msg.seq, msg.pts_us
            count += 1
            byte_count += len(msg.payload)
            offset = now*1_000_000-msg.pts_us
            offset_floor = offset if offset_floor is None else min(offset_floor, offset)
            delay_variation = (offset-offset_floor)/1000
            if now-last_stats_time >= 1:
                stats = {'received_frames':count, 'sequence_gaps':missing,
                         'receive_fps':round((count-last_stats_count)/(now-last_stats_time),2),
                         'receive_mbps':round((byte_count-last_stats_bytes)*8/(now-last_stats_time)/1e6,2),
                         'transport':transport,
                         'arrival_delay_variation_ms':round(delay_variation,2)}
                if preview:
                    stats.update(sink.snapshot())
                    if metrics_provider:stats.update(metrics_provider())
                    stats['preview_submit_fps']=round((stats['display_submitted_frames']-last_stats_display)/(now-last_stats_time),2)
                    last_stats_display=stats['display_submitted_frames']
                stats.update({'phone_'+key:value for key,value in sender_metrics.items() if not key.startswith('clock_')})
                stats.update(health.snapshot(now))
                print(json.dumps(stats), flush=True)
                if on_event: on_event(dict(stats,event='metrics'))
                last_stats_time, last_stats_count = now, count
                last_stats_bytes=byte_count
    except EOFError as exc:
        error = str(exc)
        status = 'disconnected'
    except (OSError, ProtocolError, RuntimeError, ValueError) as exc:
        error = str(exc)
        status = 'failed'
    finally:
        if recording is not None: recording.disconnect()
        if controls_enabled:control_bus.close()
        code = sink.close()
        if preview:
            extra = sink.snapshot()
            if metrics_provider:extra.update(metrics_provider())
            decoded, actual_size = extra['decoded_frames'], extra['decoded_dimensions']
        else:
            extra = {}
            decoded_text = (folder/'decoded.framemd5').read_text()
            decoded = sum(1 for line in decoded_text.splitlines() if line and not line.startswith('#'))
            dimensions = re.search(r'#dimensions\s+0:\s+(\d+)x(\d+)',decoded_text)
            actual_size = [int(n) for n in dimensions.groups()] if dimensions else None
        report = {'status': status, 'error': error, 'config':config,
            'received_frames':count, 'decoded_frames':decoded, 'sequence_gaps':missing,
            'compressed_bytes':byte_count, 'decoder_exit':code,
            'elapsed_s':time.perf_counter()-start,
            'decoder_requested':decoder,
            'decoded_dimensions':actual_size,
            'source_fps':(count-1)*1e6/(last_pts-first_pts) if count>1 else None,
            'receive_fps':(count-1)/(last_arrival-first_arrival) if count>1 and last_arrival>first_arrival else None,
            'capture_to_display_latency_ms':None, 'transport':transport,
            'validation':'synthetic or device origin must be established externally', **extra}
        report['sender_metrics']=sender_metrics
        report.update(health.snapshot(time.perf_counter()))
        if code or not count or decoded != count or sink.failure or actual_size != [config['width'],config['height']]:
            report['status'] = 'failed'
        (folder/'report.json').write_text(json.dumps(report,indent=2), encoding='utf-8')
        if on_event: on_event({'event':'disconnected','status':report['status']})
    return report

def run(host, port, identity, output, preview=False, max_sessions=0, ready=None, decoder='cpu',
        stop_event=None, disconnect_event=None, on_event=None,transport_resolver=None,renderer='opencv',preview_transform=None,control_bus=None,
        background_state=None,matting_backend='directml',color_state=None,preview_target=None,metrics_provider=None,frame_output=None,preview_visibility=None,recording=None):
    if preview:
        import importlib.util
        if not importlib.util.find_spec('av'):
            raise RuntimeError('Install requirements-preview.txt and run with that Python environment')
        if renderer=='opencv':
            import cv2
            if not cv2.currentUIFramework():
                raise RuntimeError('OpenCV has no window support; install the pinned non-headless preview requirements')
        elif renderer in ('sdl','gl'):
            from .sdl_preview import native_path
            native_path()
            if renderer=='gl' and not importlib.util.find_spec('moderngl'):
                raise RuntimeError('Install requirements-color.txt inside the isolated environment.')
        else:raise ValueError('Unsupported preview renderer')
    identity = Path(identity)
    token = (identity/'token.txt').read_text().strip()
    if len(token) != 64:
        raise ValueError('expected 256-bit hex token')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(identity/'cert.pem', identity/'key.pem')
    reports=[]
    with socket.socket() as listener:
        listener.bind((host,port)); listener.listen(4)
        listener.settimeout(.5 if stop_event else (30 if max_sessions else None))
        if ready: ready(listener.getsockname()[1])
        print('UCS receiver listening on', listener.getsockname(), flush=True)
        while not max_sessions or len(reports)<max_sessions:
            if stop_event and stop_event.is_set(): break
            try: raw, _ = listener.accept()
            except socket.timeout:
                if stop_event: continue
                raise
            raw.settimeout(5)
            raw.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
            try:
                with context.wrap_socket(raw,server_side=True) as sock:
                    transport=transport_resolver(sock.getpeername()) if transport_resolver else 'Wi-Fi/LAN TCP/TLS'
                    report = serve_session(sock,token,output,preview,decoder,stop_event,disconnect_event,on_event,transport,renderer,preview_transform,control_bus,
                        background_state,matting_backend,color_state,preview_target,metrics_provider,frame_output,preview_visibility,recording)
                    if max_sessions: reports.append(report)
            except (OSError, EOFError, ProtocolError) as exc:
                raw.close()
                # No payloads, tokens, device names or remote addresses in logs.
                print('Session rejected:', type(exc).__name__, flush=True)
            finally:
                if disconnect_event: disconnect_event.clear()
    return reports

if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--host',default='127.0.0.1')
    p.add_argument('--port',type=int,default=49200)
    p.add_argument('--identity',default='runtime/identity')
    p.add_argument('--output',default='output/sessions')
    p.add_argument('--preview',action='store_true')
    p.add_argument('--decoder',choices=['cpu','d3d11va'],default='cpu')
    a=p.parse_args()
    try: run(a.host,a.port,a.identity,a.output,a.preview,decoder=a.decoder)
    except KeyboardInterrupt: pass
