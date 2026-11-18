"""No camera, microphone or personal media. Compare generated packets after mux."""
import hashlib
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ucs.original_recording import OriginalRecording
from ucs.protocol import AUDIO, VIDEO, Message
from ucs.synthetic import access_units


@unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required for generated fixture')
class RecordingTests(unittest.TestCase):
    def test_mux_original_video_and_timed_pcm(self):
        import av
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / 'fixture.h264'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                            'testsrc2=size=320x180:rate=30', '-frames:v', '30',
                            '-c:v', 'libx264', '-tune', 'zerolatency', '-x264-params',
                            'aud=1:keyint=30:repeat-headers=1', str(source)], check=True)
            units = list(access_units(source.read_bytes()))
            pcm = struct.pack('<1600h', *(i % 500 for i in range(1600)))
            header = struct.pack('!IH', 48000, 1)
            for mic in (False, True):
                recorder = OriginalRecording()
                recorder.connect(30, mic)
                # Traffic before the explicit start must never create a file.
                recorder.offer(Message(VIDEO, units[0][0], flags=1))
                self.assertFalse(list(base.glob('*.mov')))
                dest = recorder.start(base, recorder.snapshot()[0], mic)
                self.assertEqual(recorder.wants_audio(), mic)
                recorder.offer(Message(VIDEO, units[1][0], pts_us=500000))
                if mic:
                    recorder.offer(Message(AUDIO, header + pcm, pts_us=900000))
                for i, (unit, key) in enumerate(units):
                    pts = 1000000 + round(i * 1000000 / 30)
                    # Inject a sequence gap mid-take to check the sidebar counter.
                    recorder.offer(Message(VIDEO, unit, i + 2 * (i >= 15), pts, int(key)))
                    if mic:
                        recorder.offer(Message(AUDIO, header + pcm, i, pts + 20000))
                recorder.disconnect()
                recorder.worker.join(5)
                self.assertFalse(recorder.worker.is_alive())
                self.assertTrue(dest.is_file(), recorder.status)
                take = recorder.progress()
                self.assertEqual(take.phase, 'saved')
                self.assertEqual(take.file, dest)
                self.assertEqual(take.video_format, (320, 180, 30))
                self.assertEqual(take.frames, 30)
                self.assertEqual(take.source_gaps, 2)
                self.assertAlmostEqual(take.duration_us / 1e6, 1.0, places=5)
                self.assertEqual(take.audio_samples, 48000 if mic else 0)
                def video_hashes(path):
                    with av.open(str(path)) as movie:
                        return [hashlib.sha256(f.to_ndarray(format='yuv420p')).digest()
                                for f in movie.decode(video=0)]
                self.assertEqual(video_hashes(source), video_hashes(dest))
                with av.open(str(dest)) as movie:
                    self.assertEqual(len(movie.streams.audio), int(mic))
                    if mic:
                        audio = movie.streams.audio[0]
                        self.assertEqual(audio.codec_context.name, 'pcm_s16le')
                        self.assertAlmostEqual(float(audio.start_time * audio.time_base), .02, places=3)
                        samples = b''.join(f.to_ndarray().tobytes() for f in movie.decode(audio=0))
                        self.assertEqual(samples, pcm * 30)
                dest.unlink()

    def test_disconnected_session_cannot_rearm_and_empty_take_creates_no_file(self):
        with tempfile.TemporaryDirectory() as folder:
            recorder = OriginalRecording()
            recorder.connect(30, False)
            old = recorder.snapshot()[0]
            recorder.disconnect()
            recorder.connect(30, False)
            with self.assertRaises(ValueError):
                recorder.start(folder, old, False)
            dest = recorder.start(folder, recorder.snapshot()[0], False)
            recorder.stop()
            recorder.worker.join(3)
            take = recorder.progress()
            self.assertEqual(take.phase, 'error')
            self.assertEqual(take.frames, 0)
            self.assertIsNone(take.file)
            self.assertFalse(dest.exists())
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_startup_timeout_reports_whether_mic_or_keyframe_is_missing(self):
        pcm = Message(AUDIO, struct.pack('!IH', 44100, 1) + bytes(882))
        cases = (
            (Message(VIDEO, b'fixture', flags=1), None, 'não enviou o áudio'),
            (Message(VIDEO, b'fixture'), pcm, 'um quadro-chave'),
        )
        with tempfile.TemporaryDirectory() as folder:
            for image, audio, message in cases:
                with self.subTest(message=message), patch('ucs.original_recording.START_TIMEOUT_SECONDS', .4):
                    recorder = OriginalRecording()
                    recorder.connect(30, True)
                    dest = recorder.start(folder, recorder.snapshot()[0], True)
                    recorder.offer(image)
                    if audio is not None:
                        recorder.offer(audio)
                    recorder.worker.join(3)
                    result = recorder.progress()
                    self.assertEqual(result.phase, 'error')
                    self.assertIn(message, result.detail)
                    self.assertIsNone(result.file)
                    self.assertFalse(dest.exists())
