"""Bounded numeric video health. Clock estimates are not glass-to-glass latency."""
from collections import deque
from .timing import receive_age

WINDOW_SECONDS = 5.
MAX_SAMPLES = 300
TIMING_TTL_SECONDS = 3.
PREVIEW_TTL_SECONDS = 1.


def percentile95(values):
    values = sorted(values)
    return round(values[int((len(values)-1)*.95)], 2) if values else None


class StreamWindow:
    """Written by the receiver thread; sorted only when publishing metrics."""
    def __init__(self):
        self.frames = deque(maxlen=MAX_SAMPLES)
        self.ages = deque(maxlen=MAX_SAMPLES)
        self.phone = {}
        self.phone_at = None
        self.last_arrival = None

    def phone_sample(self, metrics, now):
        old = self.phone.get('clock_offset_us')
        new = metrics.get('clock_offset_us')
        # Do not mix two incompatible clock calibrations into one percentile.
        tolerance = (self.phone.get('clock_uncertainty_us', 0) +
                     metrics.get('clock_uncertainty_us', 0) + 5000)
        if (old is None or new is None or abs(new-old) > tolerance or
                metrics.get('clock_uncertainty_us', 1e9) > 100000 or
                self.phone_at is None or now-self.phone_at > TIMING_TTL_SECONDS):
            self.ages.clear()
        self.phone = dict(metrics)
        self.phone_at = now

    def _timing_valid(self, now):
        return self.phone_at is not None and 0 <= now-self.phone_at <= TIMING_TTL_SECONDS

    def _trim(self, now):
        for values in (self.frames, self.ages):
            while values and now-values[0][0] > WINDOW_SECONDS:
                values.popleft()

    def video(self, now, pts_us):
        gap = (now-self.last_arrival)*1000 if self.last_arrival is not None else None
        self.frames.append((now, gap))
        self.last_arrival = now
        if self._timing_valid(now):
            age = receive_age(now*1e6, pts_us, self.phone)
            if age:
                self.ages.append((now, age['capture_to_receive_estimate_ms']))
        self._trim(now)

    def snapshot(self, now):
        self._trim(now)
        valid = self._timing_valid(now)
        gaps = [value for _, value in self.frames if value is not None]
        uncertainty = self.phone.get('clock_uncertainty_us')
        clock_valid = valid and 'clock_offset_us' in self.phone and uncertainty is not None and uncertainty <= 100000
        ages = [value for _, value in self.ages] if clock_valid else []
        return {
            'last_video_receive_monotonic_s': self.last_arrival,
            'receive_frame_gap_p95_ms': percentile95(gaps),
            'receive_frame_gap_max_ms': round(max(gaps), 2) if gaps else None,
            'capture_to_receive_p95_ms': percentile95(ages),
            'capture_to_receive_estimate_ms': ages[-1] if ages else None,
            'capture_to_receive_samples': len(ages),
            'clock_uncertainty_ms': round(uncertainty/1000, 2) if clock_valid else None,
            'timing_sample_age_ms': round((now-self.phone_at)*1000, 2) if self.phone_at is not None else None,
            'health_window_seconds': WINDOW_SECONDS,
        }


class PreviewFreshness:
    """No extra renderer timer or repeated clear; used on the display thread."""
    def __init__(self, ttl=PREVIEW_TTL_SECONDS):
        self.ttl = ttl
        self.last_arrival = None
        self.blank = True
        self.clears = 0
        self.expired_frames = 0

    def accept(self, arrival, now):
        if not 0 <= now-arrival < self.ttl:
            self.expired_frames += 1
            return False
        self.last_arrival = arrival
        self.blank = False
        return True

    def should_clear(self, now):
        if not self.blank and now-self.last_arrival >= self.ttl:
            self.blank = True
            self.clears += 1
            return True
        return False


def connection_view(state, now):
    """Presentation only, at the UI's existing polling rate. No radio diagnosis."""
    metrics = state.get('metrics', {})
    connected = state.get('state') == 'connected'
    recent = connected and now-state.get('metrics_at', -1e9) <= 3
    last = metrics.get('last_video_receive_monotonic_s')
    age = max(0., (now-last)*1000) if connected and last is not None else None
    status = ('Video recebido' if recent and age is not None and age < 1200 else
              'Sem video recente' if connected else 'Aguardando iPhone')
    def fmt(key, suffix='', digits=1):
        value = metrics.get(key) if recent else None
        return f'{value:.{digits}f}{suffix}' if value is not None else 'Indisponivel'
    transport = ('USB (cabo)' if state.get('transport', '').startswith('USB') else 'Wi-Fi/LAN') if connected else 'Desconectado'
    sample_age = metrics.get('timing_sample_age_ms')
    timing_recent = recent and sample_age is not None and sample_age+max(0,now-state.get('metrics_at',now))*1000 <= TIMING_TTL_SECONDS*1000
    estimate = fmt('capture_to_receive_p95_ms', ' ms') if timing_recent else 'Indisponivel'
    return status, {
        'transport': transport,
        'rates': f"Recebidos: {fmt('receive_fps', ' FPS')}\nPrevia: {fmt('preview_submit_fps', ' FPS')}\nDados: {fmt('receive_mbps', ' Mbps')}",
        'age': f'{age/1000:.1f} s' if age is not None else 'Aguardando quadro',
        'timing': f"Captura ate recepcao, p95: {estimate}\nIncerteza do relogio: {fmt('clock_uncertainty_ms', ' ms') if timing_recent else 'Indisponivel'}",
        'stages': f"Encoder: {fmt('phone_encoder_p95_ms', ' ms')}\nDecoder: {fmt('decode_p95_ms', ' ms')}\nRecepcao ate previa: {fmt('receive_to_preview_submit_p95_ms', ' ms')}",
        'gaps': f"Recepcao: {fmt('receive_frame_gap_p95_ms', ' ms')}\nPrevia: {fmt('preview_frame_gap_p95_ms', ' ms')}",
        'omissions': f"Capturas omitidas no iPhone: {fmt('phone_capture_skipped', digits=0)}\nSaltos de sequencia: {fmt('sequence_gaps', digits=0)}\nSubstituicoes na previa: {fmt('display_replaced_frames', digits=0)}",
    }
