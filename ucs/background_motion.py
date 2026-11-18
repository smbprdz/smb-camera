"""Local animated backgrounds. Decode on one worker and retain only the latest frame."""
from contextlib import closing
from pathlib import Path
import math
import threading
import time

CONTAINERS = {'.mp4': 'mov', '.mov': 'mov', '.webm': 'matroska', '.mkv': 'matroska'}
MOTION_SUFFIXES = {'.gif', *CONTAINERS}


def check_size(width, height):
    if not (0 < width <= 4096 and 0 < height <= 4096 and width * height <= 3840 * 2160):
        raise ValueError('O fundo animado deve ter até 8,3 megapixels e 4096 px por lado.')


def timed_frames(path):
    if str(path).startswith(('\\\\', '//')):
        raise ValueError('O fundo animado precisa estar em um arquivo local.')
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in MOTION_SUFFIXES:
        raise ValueError('Escolha um GIF, MP4, MOV, WebM ou MKV local.')
    if not path.is_file() or path.stat().st_size > 1024**3:
        raise ValueError('O fundo animado precisa de um arquivo local de até 1 GB.')
    if suffix == '.gif':
        from PIL import Image
        with Image.open(path, formats=['GIF']) as image:
            check_size(*image.size)
            offset = 0.
            index = 0
            while True:
                try:
                    image.seek(index)
                except EOFError:
                    break
                duration = max(.02, image.info.get('duration', 100) / 1000)
                yield offset, duration, image
                offset += duration
                index += 1
        return
    import av
    with path.open('rb') as source, av.open(source, format=CONTAINERS[suffix]) as media:
        if not media.streams.video:
            raise ValueError('O arquivo não tem uma trilha de vídeo.')
        stream = media.streams.video[0]
        check_size(stream.width, stream.height)
        stream.codec_context.thread_count = 1
        default_duration = 1 / max(1., min(240., float(stream.average_rate or 30)))
        origin = None
        previous = None
        duration = default_duration
        for frame in media.decode(stream):
            check_size(frame.width, frame.height)
            stamp = frame.time
            if origin is None and stamp is not None and math.isfinite(stamp):
                origin = stamp if previous is None else stamp - previous - duration
            offset = stamp - origin if origin is not None and stamp is not None and math.isfinite(stamp) else None
            if offset is None or offset < 0 or (previous is not None and offset <= previous):
                offset = 0. if previous is None else previous + duration
            duration = float(frame.duration * frame.time_base) if frame.duration and frame.time_base else default_duration
            duration = duration if math.isfinite(duration) and duration > 0 else default_duration
            yield offset, duration, frame
            previous = offset


def frame_pixels(frame):
    from PIL import Image
    if isinstance(frame, Image.Image):
        image = frame.convert('RGBA')
        image.thumbnail((1920, 1080) if image.width >= image.height else (1080, 1920))
    else:
        rotation = getattr(frame, 'rotation', 0) % 360
        width, height = frame.width, frame.height
        portrait = (width < height) != (rotation in (90, 270))
        limit_w, limit_h = (1080, 1920) if portrait else (1920, 1080)
        if rotation in (90, 270):
            limit_w, limit_h = limit_h, limit_w
        scale = min(1., limit_w / width, limit_h / height)
        rgb = frame.to_ndarray(format='rgb24', width=max(1, round(width * scale)),
                               height=max(1, round(height * scale)))
        image = Image.fromarray(rgb).rotate(rotation, expand=True).convert('RGBA') if rotation else None
        if image is None:
            return (rgb.shape[1], rgb.shape[0]), 3, rgb.tobytes()
    return image.size, 4, image.tobytes()


def verify_motion(path):
    with closing(timed_frames(path)) as frames:
        first = next(frames, None)
        if first is None:
            raise ValueError('O fundo animado não contém quadros.')
        frame_pixels(first[2])


class BackgroundMotion:
    def __init__(self):
        self.condition = threading.Condition()
        self.request = (None, 0)
        self.latest = None
        self.error = ''
        self.closed = False
        self.worker = threading.Thread(target=self._work, name='background-motion', daemon=True)
        self.worker.start()

    def select(self, path):
        with self.condition:
            if path != self.request[0]:
                self.request = (path, self.request[1] + 1)
                self.latest = None
                self.error = ''
                self.condition.notify_all()

    def snapshot(self):
        with self.condition:
            return self.latest, self.error

    def close(self):
        with self.condition:
            self.closed = True
            self.latest = None
            self.condition.notify_all()
        self.worker.join(timeout=1)

    def _changed(self, request):
        return self.closed or request != self.request

    def _wait_until(self, request, deadline):
        with self.condition:
            if self.condition.wait_for(lambda: self._changed(request), max(0, deadline - time.monotonic())):
                return False
            return True

    def _work(self):
        request = None
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self._changed(request))
                if self.closed:
                    return
                request = self.request
            if request[0] is None:
                continue
            try:
                self._play(request)
            except Exception:
                with self.condition:
                    if not self._changed(request):
                        self.latest = None
                        self.error = 'Falha ao ler o fundo animado. Escolha outro arquivo.'

    def _play(self, request):
        last_due = -math.inf
        cycle_start = time.monotonic()
        while True:
            end = None
            with closing(timed_frames(request[0])) as frames:
                for offset, duration, frame in frames:
                    due = cycle_start + offset
                    if not self._wait_until(request, due):
                        return
                    end = due + duration
                    now = time.monotonic()
                    if due - last_due < 1 / 30 - .0005 or (now - due > .12 and end < now):
                        continue
                    pixels = frame_pixels(frame)
                    with self.condition:
                        if self._changed(request):
                            return
                        self.latest = pixels
                    last_due = due
            if end is None:
                raise ValueError('O fundo animado não contém quadros.')
            if not self._wait_until(request, end):
                return
            cycle_start = max(end, time.monotonic())
