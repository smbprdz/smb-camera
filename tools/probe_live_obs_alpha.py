"""Bounded live-frame validation, no camera start or media recording.

Reads the app's existing local endpoint into our source in an isolated OBS
engine. Reports aggregate numbers only, never pixels, RGB samples or hashes.
Does not open obs64.exe, audio, user profiles/scenes or install an extension.
"""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.probe_obs_alpha import VideoInfo, VideoData, bind


def validate_endpoint(value):
    if type(value) is not dict or type(value.get('schema')) is not int or value['schema'] not in (1,2) or value.get('alpha_mode') != 'premultiplied':
        raise ValueError('Own alpha endpoint required')
    name = value.get('pipe_name')
    prefix = '\\\\.\\pipe\\UCS.FrameBridge.'
    if not isinstance(name, str) or not name.startswith(prefix) or not re.fullmatch(r'[0-9a-fA-F-]{36}', name[len(prefix):]):
        raise ValueError('Local owned pipe required')
    width, height = value.get('width'), value.get('height')
    if (type(width) is not int or type(height) is not int or not 2 <= width <= 16384
            or not 2 <= height <= 16384 or width*height*4 > 64*1024*1024):
        raise ValueError('Invalid alpha canvas')
    gpu=value['schema']==2
    if gpu and (value.get('transport')!='d3d11-keyed-v1' or value.get('max_readers')!=1):raise ValueError('Unsupported GPU transport')
    if value.get('canvas') != [width, height] or value.get('formats') != ([4] if gpu else [3]):
        raise ValueError('Alpha canvas or format mismatch')
    if type(value.get('producer_pid')) is not int or not 1 <= value['producer_pid'] < 2**32:
        raise ValueError('Invalid producer PID')
    if not isinstance(value.get('epoch_hex'), str) or not re.fullmatch(r'[0-9a-fA-F]{16}', value['epoch_hex']) or int(value['epoch_hex'],16)==0:
        raise ValueError('Invalid producer epoch')
    if not isinstance(value.get('owner_sid'),str) or len(value['owner_sid'])>=192 or not re.fullmatch(r'S-1-[0-9][0-9-]+',value['owner_sid']):
        raise ValueError('Invalid producer owner')
    return width, height


class FrameSummary:
    def __init__(self):
        self.samples = self.content = self.changes = self.partial = self.zero = self.opaque = 0
        self.alpha_min, self.alpha_max = 255, 0
        self.first = self.last = None
        self._previous = None
        self._hashes = set()

    def observe(self, row, now):
        if not row or len(row) % 4:
            raise ValueError('Invalid observed pixel row')
        alpha = row[3::4]
        low, high = min(alpha), max(alpha)
        digest = hashlib.sha256(row).digest()  # ephemeral, never serialized
        self.samples += 1
        self.content += high > 0
        self.zero += low == 0
        self.opaque += high == 255
        self.partial += any(0 < value < 255 for value in alpha)
        self.alpha_min, self.alpha_max = min(self.alpha_min, low), max(self.alpha_max, high)
        if self._previous is not None:
            self.changes += digest != self._previous
        self._previous = digest
        self._hashes.add(digest)
        self.first = now if self.first is None else self.first
        self.last = now

    def report(self):
        return dict(output_samples=self.samples, samples_with_content=self.content,
                    distinct_observed_rows=len(self._hashes), changed_rows=self.changes,
                    alpha_min=self.alpha_min if self.samples else None,
                    alpha_max=self.alpha_max if self.samples else None,
                    samples_with_transparent_pixels=self.zero,
                    samples_with_partial_alpha=self.partial,
                    samples_with_opaque_pixels=self.opaque,
                    output_sample_fps=(self.samples-1)/(self.last-self.first)
                    if self.samples > 1 and self.last > self.first else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--obs', type=Path, default=Path('C:/Program Files/obs-studio'))
    parser.add_argument('--seconds', type=int, default=8)
    args = parser.parse_args()
    if os.name != 'nt' or not 4 <= args.seconds <= 15:
        raise ValueError('Bounded Windows observation required')
    args.obs=args.obs.resolve()
    metadata = args.metadata.resolve()
    if metadata.stat().st_size > 32768:
        raise ValueError('Endpoint metadata exceeds bound')
    endpoint = json.loads(metadata.read_text(encoding='utf-8'))
    width, height = validate_endpoint(endpoint)
    root = Path(__file__).resolve().parents[1]
    folder = (Path('output')/('live-obs-alpha-'+str(time.time_ns()))).resolve()
    folder.mkdir(parents=True)
    previous_directory = Path.cwd()
    binary = args.obs.resolve()/'bin/64bit'
    directory = os.add_dll_directory(str(binary))
    os.chdir(binary)
    obs, scripting = C.CDLL(str(binary/'obs.dll')), C.CDLL(str(binary/'obs-scripting.dll'))
    p, s, b, u = C.c_void_p, C.c_char_p, C.c_bool, C.c_uint32
    callback_type = C.CFUNCTYPE(None, p, C.POINTER(VideoData))
    for name, arguments, result in (
        ('obs_get_version_string', [], s), ('obs_startup', [s, s, p], b),
        ('obs_shutdown', [], None), ('obs_add_data_path', [s], None),
        ('obs_reset_video', [C.POINTER(VideoInfo)], C.c_int),
        ('obs_data_create_from_json', [s], p), ('obs_data_release', [p], None),
        ('obs_source_create', [s, s, p, p], p), ('obs_source_release', [p], None),
        ('obs_source_get_width', [p], u), ('obs_source_get_height', [p], u),
        ('obs_set_output_source', [u, p], None),
        ('obs_add_raw_video_callback', [p, callback_type, p], None),
        ('obs_remove_raw_video_callback', [callback_type, p], None),
    ):
        bind(obs, name, arguments, result)
    for name, arguments, result in (
        ('obs_scripting_load', [], b), ('obs_scripting_unload', [], None),
        ('obs_script_create', [s, p], p), ('obs_script_destroy', [p], None),
        ('obs_script_loaded', [p], b),
    ):
        bind(scripting, name, arguments, result)
    report = dict(scope='live user-started camera through own source in isolated OBS engine',
                  transport=endpoint.get('transport','rgba-memory-v1'),
                  obs_version=obs.obs_get_version_string().decode(),
                  expected_canvas=[width, height], pixel_bytes_saved=False,
                  image_hashes_saved=False, personal_media_recorded=False,
                  audio_opened=False, camera_started_by_probe=False,
                  obs_ui_started=False, user_installation_modified=False,
                  gameplay_and_total_latency_validated=False)
    stats = FrameSummary()
    errors = []
    active = scripts = connected = False
    source = script = settings = None

    def receive(param, pointer):
        try:
            frame = pointer.contents
            if frame.data[0] and frame.linesize[0] >= width*4 and stats.samples < 600:
                address = C.cast(frame.data[0], p).value+(height//2)*frame.linesize[0]
                row = C.string_at(address, width*4)
                stats.observe(row, time.perf_counter())
        except Exception as error:
            if len(errors) < 5:
                errors.append(type(error).__name__)

    callback = callback_type(receive)
    try:
        if report['obs_version'] != '32.2.2':
            raise RuntimeError('Probe ABI requires OBS32.2.2')
        active = bool(obs.obs_startup(b'en-US', str(folder/'module-config').encode(), None))
        if not active:
            raise RuntimeError('Isolated OBS startup failed')
        obs.obs_add_data_path(((args.obs.resolve()/'data/libobs').as_posix()+'/').encode())
        info = VideoInfo(b'libobs-d3d11', 30, 1, width, height, width, height, 7, 0, False, 0, 2, 0)
        if obs.obs_reset_video(C.byref(info)) != 0:
            raise RuntimeError('Isolated graphics setup failed')
        scripts = bool(scripting.obs_scripting_load())
        if not scripts:
            raise RuntimeError('OBS scripting unavailable')
        script = scripting.obs_script_create((root/'integrations/obs/smb-camera.lua').as_posix().encode(), None)
        if not script or not scripting.obs_script_loaded(script):
            raise RuntimeError('Own source module failed to load')
        settings = obs.obs_data_create_from_json(json.dumps({'endpoint': str(metadata)}).encode())
        source = obs.obs_source_create(b'smb_camera_alpha_v1', b'SMB live validation', settings, None)
        if not source:
            raise RuntimeError('Own live source unavailable')
        obs.obs_set_output_source(0, source)
        obs.obs_add_raw_video_callback(None, callback, None)
        connected = True
        time.sleep(args.seconds)
        report['source_canvas'] = [obs.obs_source_get_width(source), obs.obs_source_get_height(source)]
        report.update(stats.report())
        report['callback_errors'] = errors
        report['video_received'] = stats.content >= 60 and not errors
        report['transparency_observed'] = stats.zero > 0 and stats.content >= 60
        report['status'] = 'pass' if report['video_received'] and report['transparency_observed'] and report['source_canvas'] == [width, height] else 'failed'
    except Exception as error:
        report.update(status='failed', failure=type(error).__name__, **stats.report())
    finally:
        if connected: obs.obs_remove_raw_video_callback(callback, None)
        if source:
            obs.obs_set_output_source(0, None)
            obs.obs_source_release(source)
        if settings: obs.obs_data_release(settings)
        if script: scripting.obs_script_destroy(script)
        if scripts: scripting.obs_scripting_unload()
        if active: obs.obs_shutdown()
        directory.close()
        os.chdir(previous_directory)
    (folder/'summary.json').write_bytes((json.dumps(report, indent=2)+'\n').encode())
    print(json.dumps(dict(report, proof_folder=str(folder))))
    return 0 if report.get('status') == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
