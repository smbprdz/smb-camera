"""User-initiated MOV recording. Preserve compressed H.264 and phone capture time."""
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
import io
from pathlib import Path
import threading
import time
import uuid

from .protocol import AUDIO, VIDEO, pcm_format

MICROSECOND = Fraction(1, 1_000_000)
START_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class RecordingProgress:
    available: bool = False
    mic_available: bool = False
    phase: str = 'idle'
    video_format: tuple = ()
    duration_us: int = 0
    frames: int = 0
    source_gaps: int = 0
    audio_samples: int = 0
    audio_rate: int = 0
    with_audio: bool = False
    waiting_audio: bool = False
    detail: str = ''
    file: Path | None = None


class OriginalRecording:
    def __init__(self):
        self.condition = threading.Condition()
        self.pending = deque()
        self.queued_bytes = 0
        self.session = None
        self.token = None
        self.active = False
        self.stopping = False
        self.failure = ''
        self.status = ''
        self.with_audio = False
        self.waiting_audio = False
        self.worker = None
        self.video_format = ()
        self.duration_us = 0
        self.frames = self.source_gaps = 0
        self.audio_samples = self.audio_rate = 0
        self.file = None
        self.outcome = 'idle'
        self.detail = ''

    def connect(self, fps, mic):
        with self.condition:
            self.session = (fps, mic)
            self.token = object()

    def disconnect(self):
        with self.condition:
            self.session = self.token = None
            self.stop()

    def snapshot(self):
        with self.condition:
            return self.token, bool(self.session and self.session[1]), self.active, self.stopping, self.status

    def progress(self):
        with self.condition:
            phase = self.outcome
            if self.active:
                phase = 'finishing' if self.stopping else ('recording' if self.frames else 'starting')
            return RecordingProgress(
                available=self.token is not None, mic_available=bool(self.session and self.session[1]),
                phase=phase, video_format=self.video_format, duration_us=self.duration_us,
                frames=self.frames, source_gaps=self.source_gaps, audio_samples=self.audio_samples,
                audio_rate=self.audio_rate, with_audio=self.with_audio, waiting_audio=self.waiting_audio,
                detail=self.detail, file=self.file)

    def start(self, directory, token, with_audio):
        with self.condition:
            if self.active or not self.session or self.token is not token:
                raise ValueError('A conexão mudou. Escolha a gravação novamente.')
            fps, mic = self.session
            if with_audio and not mic:
                raise ValueError('Microfone indisponível nesta conexão.')
            name = datetime.now().strftime('SMB Camera %Y-%m-%d %H-%M-%S') + ' ' + uuid.uuid4().hex[:8]
            path = Path(directory) / (name + '.mov')
            self.pending.clear()
            self.queued_bytes = 0
            self.active, self.stopping, self.with_audio = True, False, with_audio
            self.waiting_audio = with_audio
            self.failure = ''
            self.video_format = ()
            self.duration_us = 0
            self.frames = self.source_gaps = 0
            self.audio_samples = self.audio_rate = 0
            self.file = None
            self.outcome = 'idle'
            self.detail = ''
            self.status = 'Aguardando microfone e quadro-chave…' if with_audio else 'Aguardando quadro-chave…'
            self.worker = threading.Thread(target=self._write, args=(path, fps, with_audio), name='original-mov')
            self.worker.start()
            return path

    def wants_audio(self):
        with self.condition:
            return self.active and self.with_audio and not self.stopping

    def stop(self, reason=''):
        with self.condition:
            if self.active:
                self.stopping = True
                if reason:
                    self.failure = reason
                self.condition.notify_all()

    def offer(self, message):
        with self.condition:
            if not self.active or self.stopping or (message.kind == AUDIO and not self.with_audio):
                return
            size = len(message.payload)
            if self.queued_bytes + size > 16 * 1024**2 or len(self.pending) >= 96:
                self.stop('Disco atrasado. Gravação interrompida.')
                return
            self.pending.append(message)
            self.queued_bytes += size
            self.condition.notify()

    def _write(self, path, fps, with_audio):
        partial = path.with_suffix('.partial.mov')
        container = handle = None
        base = audio_format = None
        audio_packets = 0
        last_video_seq = None
        last_audio_end = None
        last_audio_pts = None
        first_deadline = time.monotonic() + START_TIMEOUT_SECONDS
        video_seen = keyframe_seen = False
        error = ''
        try:
            while True:
                with self.condition:
                    if not self.pending:
                        if self.stopping:
                            break
                        self.condition.wait(.2)
                    message = self.pending.popleft() if self.pending else None
                    if message:
                        self.queued_bytes -= len(message.payload)
                if message is not None and message.kind == AUDIO:
                    fmt = pcm_format(message.payload)
                    if audio_format is not None and fmt != audio_format:
                        raise ValueError('O formato do microfone mudou.')
                    if audio_format is None:
                        with self.condition:
                            self.waiting_audio = False
                    audio_format = fmt
                if base is None:
                    if message is not None and message.kind == VIDEO:
                        video_seen = True
                        keyframe_seen = keyframe_seen or bool(message.flags)
                    ready = (message is not None and message.kind == VIDEO and message.flags
                             and (not with_audio or audio_format))
                    if not ready and time.monotonic() >= first_deadline:
                        if with_audio and audio_format is None:
                            if keyframe_seen:
                                raise ValueError('O vídeo chegou, mas o iPhone não enviou o áudio do microfone.')
                            raise ValueError('O iPhone não enviou áudio nem quadro-chave a tempo.')
                        if video_seen:
                            raise ValueError('Aguardamos um quadro-chave do iPhone, mas ele não chegou.')
                        raise ValueError('O iPhone não enviou vídeo a tempo.')
                    if not ready:
                        continue
                    import av
                    base = message.pts_us
                    handle = partial.open('xb')
                    container = av.open(handle, 'w', format='mov')
                    # Learn SPS/PPS and codec parameters from the first access unit.
                    with av.open(io.BytesIO(message.payload), format='h264') as first:
                        source = first.streams.video[0]
                        video = container.add_stream_from_template(source)
                        video_format = (source.width, source.height, fps)
                    video.time_base = MICROSECOND
                    if with_audio:
                        rate, channels = audio_format
                        audio = container.add_stream('pcm_s16le', rate=rate)
                        audio.layout = 'mono' if channels == 1 else 'stereo'
                        audio.time_base = Fraction(1, rate)
                if message is None or message.pts_us < base:
                    continue
                if message.kind == VIDEO:
                    if with_audio and message.pts_us - (base if last_audio_pts is None else last_audio_pts) > 2_000_000:
                        raise ValueError('O microfone parou de enviar áudio.')
                    packet = av.Packet(message.payload)
                    packet.stream = video
                    packet.pts = packet.dts = message.pts_us - base
                    packet.time_base = MICROSECOND
                    packet.duration = round(1_000_000 / fps)
                    packet.is_keyframe = bool(message.flags)
                else:
                    packet = av.Packet(message.payload[6:])
                    packet.stream = audio
                    sample = round((message.pts_us - base) * rate / 1_000_000)
                    if last_audio_end is not None and abs(sample - last_audio_end) > 2:
                        raise ValueError('Descontinuidade no áudio. Gravação interrompida.')
                    packet.pts = packet.dts = sample if last_audio_end is None else last_audio_end
                    packet.time_base = Fraction(1, rate)
                    packet.duration = packet.size // (2 * channels)
                    last_audio_end = packet.pts + packet.duration
                    audio_packets += 1
                    last_audio_pts = message.pts_us
                duration = packet.duration
                container.mux(packet)
                with self.condition:
                    if message.kind == VIDEO:
                        if last_video_seq is None:
                            self.video_format = video_format
                            self.status = 'Gravando original com microfone' if with_audio else 'Gravando original sem áudio'
                        else:
                            self.source_gaps += max(0, message.seq - last_video_seq - 1)
                        last_video_seq = message.seq
                        self.frames += 1
                        self.duration_us = message.pts_us - base + duration
                    else:
                        self.audio_samples += duration
                        self.audio_rate = rate
        except Exception as exc:
            error = str(exc) if type(exc) is ValueError else 'Falha ao escrever o arquivo de gravação.'
        finally:
            try:
                if container:
                    container.close()
            except Exception:
                error = 'Falha ao finalizar o MOV.'
            try:
                if handle:
                    handle.close()
                with self.condition:
                    error = self.failure or error
                if base is None:
                    error = error or 'Nenhum quadro-chave gravado.'
                if with_audio and not audio_packets:
                    error = error or 'Nenhuma amostra de áudio gravada.'
                if not error:
                    partial.rename(path)
            except OSError:
                error = 'Falha ao salvar o arquivo final.'
            with self.condition:
                self.status = error or ('Salvo em ' + str(path))
                self.outcome = 'error' if error else 'saved'
                self.detail = error
                self.file = (partial if partial.is_file() else None) if error else path
                if error and self.file:
                    self.status += ' Arquivo parcial em ' + str(self.file)
                self.pending.clear()
                self.queued_bytes = 0
                self.active = self.stopping = False
                self.condition.notify_all()
