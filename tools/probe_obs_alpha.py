"""Isolated official OBS engine + own Lua source, generated pixels only.

Does not start obs64.exe, load user profiles/scenes, install a script/plugin,
open audio/cameras, or create a recording/output. Uses the existing signed OBS
libraries through their public APIs in this disposable diagnostic process.
"""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
import threading
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ucs.frame_output import FramePublisher


class VideoInfo(C.Structure):
    # OBS 32.2.2 libobs/obs.h, obs_video_info. Refuse other ABIs below.
    _fields_ = [('graphics_module', C.c_char_p)] + [(name, C.c_uint32) for name in (
        'fps_num', 'fps_den', 'base_width', 'base_height', 'output_width', 'output_height',
        'output_format', 'adapter')] + [('gpu_conversion', C.c_bool)] + [
        (name, C.c_int) for name in ('colorspace', 'range', 'scale_type')]


class VideoData(C.Structure):
    _fields_ = [('data', C.POINTER(C.c_uint8)*8), ('linesize', C.c_uint32*8),
                ('timestamp', C.c_uint64)]


def bind(library, name, args, result):
    function = getattr(library, name)
    function.argtypes, function.restype = args, result
    return function


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--obs', type=Path, default=Path('C:/Program Files/obs-studio'))
    parser.add_argument('--motion-background', type=Path, help='Red/green GIF or video fixture for the generated studio')
    parser.add_argument('--seconds', type=int, default=8)
    parser.add_argument('--resolution', choices=['64', '1080', '4k'], default='64')
    parser.add_argument('--generated-studio', action='store_true',
                        help='Own generated H264/TLS/GPU studio -> IPC -> Lua -> OBS, no phone')
    parser.add_argument('--gpu-studio',action='store_true',help='Exercise app integrated GPU broker instead of RAM')
    parser.add_argument('--gpu-view-cycle',action='store_true',help='Verify generated GPU canvas changes')
    parser.add_argument('--gpu-reject-adapter',action='store_true',help='Verify wrong-GPU rejection without fallback')
    parser.add_argument('--gpu-visibility-cycle',action='store_true',help='Hide and show the generated OBS source to verify release/reconnect')
    parser.add_argument('--soak-cycles', type=int, choices=range(1, 26), help=argparse.SUPPRESS)
    parser.add_argument('--steady-seconds', type=int, choices=range(0, 601, 10), default=0, help=argparse.SUPPRESS)
    parser.add_argument('--pressure', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    soak = None
    if args.soak_cycles:
        from gpu_soak import CYCLE_SECONDS, OUTPUT, Observer, exercise, steady_state
        if not args.gpu_studio or args.resolution != '1080':
            parser.error('Soak requires generated GPU studio at 1080p')
        soak = Observer()
    if os.name != 'nt' or not 4 <= args.seconds <= 15:
        raise ValueError('Bounded Windows-only experiment')
    if args.generated_studio and args.resolution == '64':
        raise ValueError('Generated studio probe requires 1080 or 4k')
    if args.gpu_studio and not args.generated_studio:raise ValueError('GPU studio probe requires generated input')
    if args.gpu_view_cycle and not args.gpu_studio:raise ValueError('GPU view cycle requires GPU studio')
    if args.gpu_reject_adapter and not args.gpu_studio:raise ValueError('GPU rejection probe requires GPU studio')
    if args.gpu_visibility_cycle and not args.gpu_studio:raise ValueError('GPU visibility cycle requires GPU studio')
    if args.motion_background:
        if not args.generated_studio or soak:
            parser.error('Motion background requires the short generated studio probe')
        args.motion_background = args.motion_background.resolve()
    args.obs = args.obs.resolve()
    root = Path(__file__).resolve().parents[1]
    folder = (Path('output')/('obs-alpha-generated-'+str(time.time_ns()))).resolve()
    folder.mkdir(parents=True)
    binary = args.obs/'bin/64bit'
    previous_directory = Path.cwd()
    # OBS's script-module lookup is relative to its normal bin/64bit directory.
    # Only this disposable process changes cwd; all writable paths are absolute.
    os.chdir(binary)
    directory = os.add_dll_directory(str(binary.resolve()))
    obs = C.CDLL(str((binary/'obs.dll').resolve()))
    scripting = C.CDLL(str((binary/'obs-scripting.dll').resolve()))
    p, u, b, s = C.c_void_p, C.c_uint32, C.c_bool, C.c_char_p
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
    version = obs.obs_get_version_string().decode()
    if version != '32.2.2':
        raise RuntimeError('Probe ABI pinned to OBS 32.2.2')
    report = dict(scope='existing official OBS engine and own Lua source; generated pixels only',
                  obs_version=version, personal_media_captured=False, audio_opened=False,
                  recording_created=False, obs_ui_started=False, user_installation_modified=False,
                  source_loaded=False, frame_samples=0, distinct_hashes=0, alpha_levels=[],
                  hash_scope='middle row of generated OBS output',
                  full_product_performance_validated=False,
                  input_pipeline=('generated H264/TLS/D3D11VA/GL/own keyed GPU broker' if args.gpu_studio else 'generated H264/TLS/D3D11VA/GL/own IPC') if args.generated_studio else 'generated RGBA fixture')
    active = scripts = connected = False
    script = source = settings = publisher = video = None
    finish = threading.Event()
    feeder = None
    studio = studio_log = None
    consumer_ready=folder/'consumer-ready.flag'
    samples, errors = [], []
    phase = ['active']
    feed_enabled = threading.Event()
    feed_enabled.set()
    width, height = {'64': (64, 64), '1080': (1920, 1080), '4k': (3840, 2160)}[args.resolution]
    out_width, out_height = OUTPUT if soak else (width, height)
    third = width//3
    # Three vertical bands: invisible, half-alpha, opaque. Distinct RGB confirms
    # that transparency came through the source, not a black/empty replacement.

    def receive(param, pointer):
        try:
            if soak:
                soak.receive(pointer)
                return
            frame = pointer.contents
            if not frame.data[0] or frame.linesize[0] < width*4:
                return
            data = C.string_at(C.cast(frame.data[0], p).value+(height//2)*frame.linesize[0], width*4)
            if len(samples) < 600:
                bands = [list(data[x*4:x*4+4]) for x in (width//8, width//2, width*7//8)]
                # Explicit BGRA raw-video output, normalized to RGBA in the
                # numeric proof only. The actual source texture stays RGBA.
                bands = [[pixel[2], pixel[1], pixel[0], pixel[3]] for pixel in bands]
                samples.append((int(frame.timestamp), hashlib.sha256(data).hexdigest(), bands, phase[0]))
        except Exception as error:
            errors.append(type(error).__name__)

    callback = callback_type(receive)
    try:
        metadata = folder/'alpha-endpoint.json'
        if args.generated_studio:
            metadata = folder/'runtime/alpha-output.json'
            studio_log = (folder/'generated-studio.log').open('wb')
            command=[sys.executable, str(root/'tools/smoke_studio.py'),
                '--hidden', '--resolution', args.resolution, '--diagnostics',
                '--assert-mask-hold',
                '--stall-seconds', '1.5', '--seconds', str(args.seconds+5)]
            if soak:
                command[-1] = str(CYCLE_SECONDS * args.soak_cycles + args.steady_seconds
                                  + (20 if args.steady_seconds else 0) + (10 if args.pressure else 0) + 6)
                command.append('--soak-events')
                if args.pressure:
                    command.append('--pressure')
            command+=['--gpu-output'] if args.gpu_studio else ['--frame-output','--frame-format','rgba']
            command+=['--consumer-ready-file',str(consumer_ready)]
            if args.motion_background:command+=['--motion-background',str(args.motion_background)]
            if args.gpu_view_cycle:command+=['--gpu-view-cycle']
            if args.gpu_reject_adapter:command+=['--gpu-reject-adapter']
            studio = subprocess.Popen(command,cwd=folder, stdout=studio_log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW)
            deadline = time.monotonic()+8
            while time.monotonic() < deadline:
                if studio.poll() is not None:
                    raise RuntimeError('Generated studio exited before producing its endpoint')
                if metadata.is_file():
                    endpoint = json.loads(metadata.read_text())
                    if endpoint.get('canvas') == [width, height]:
                        break
                time.sleep(.03)
            else:
                raise RuntimeError('Generated studio did not publish its canvas')
        active = bool(obs.obs_startup(b'en-US', str(folder.resolve()/'module-config').encode(), None))
        if not active:
            raise RuntimeError('Isolated OBS startup failed')
        obs.obs_add_data_path(((args.obs/'data/libobs').resolve().as_posix()+'/').encode())
        info = VideoInfo(b'libobs-d3d11', 30, 1, width, height, out_width, out_height, 7, 0, False, 0, 2, 0)
        code = obs.obs_reset_video(C.byref(info))
        report['video_init'] = code
        if code != 0:
            raise RuntimeError('Isolated OBS video initialization failed')
        scripts = bool(scripting.obs_scripting_load())
        if not scripts:
            raise RuntimeError('OBS scripting unavailable')
        module = root/'integrations/obs/smb-camera.lua'
        if soak:
            import shutil
            fixture_module = folder / 'obs-module'
            fixture_module.mkdir()
            for name in ('smb-camera.lua', 'alpha_transport.lua', 'gpu_transport.lua', 'gpu_graphics.lua'):
                shutil.copyfile(module.parent / name, fixture_module / name)
            module = fixture_module / 'soak_obs_counters.lua'
            shutil.copyfile(root / 'tools' / module.name, module)
        script = scripting.obs_script_create(module.as_posix().encode(), None)
        if not script or not scripting.obs_script_loaded(script):
            raise RuntimeError('Own OBS script did not load')
        report['source_loaded'] = True
        if not args.generated_studio:
            publisher = FramePublisher(metadata=metadata, formats=(3,))
            publisher.set_canvas(width, height)

        def feed():
            index = 0
            next_frame = time.perf_counter()
            while not finish.wait(max(0, next_frame-time.perf_counter())):
                next_frame = max(next_frame+1/30, time.perf_counter())
                if feed_enabled.is_set() and publisher.wanted():
                    row = (bytes([0, 0, 0, 0])*third + bytes([40, 64, 80, 128])*(width-2*third)
                           + bytes([64+index % 64, 128, 160, 255])*third)
                    pixels = row*height
                    publisher.publish(width, height, pixels, time.perf_counter(), 3)
                    index += 1

        if publisher:
            feeder = threading.Thread(target=feed)
            feeder.start()
        settings = obs.obs_data_create_from_json(json.dumps(
            {'endpoint': str(metadata.resolve())}).encode())
        source = obs.obs_source_create(b'smb_camera_alpha_v1', b'SMB generated alpha only', settings, None)
        if not source:
            raise RuntimeError('Own OBS source not created')
        obs.obs_set_output_source(0, source)
        obs.obs_add_raw_video_callback(None, callback, None)
        connected = True
        if soak:
            def visible(show):
                obs.obs_set_output_source(0, source if show else None)

            def recreate():
                nonlocal source
                visible(False)
                obs.obs_source_release(source)
                source = obs.obs_source_create(b'smb_camera_alpha_v1', b'SMB soak', settings, None)
                if not source:
                    raise RuntimeError('OBS source recreation failed')
                visible(True)

            def dimensions():
                return obs.obs_source_get_width(source), obs.obs_source_get_height(source)

            report['observer_output'] = [out_width, out_height]
            report['soak_cycles'] = args.soak_cycles
            report['native_obs_alpha_validated'] = exercise(
                args.soak_cycles, folder, soak, dimensions, visible, recreate)
            if args.pressure:
                for fault in ('late', 'expired'):
                    soak.reset()
                    (folder / (fault + '.ready')).touch()
                    time.sleep(5)
                    sample = soak.snapshot()
                    report[fault] = sample
                    report['native_obs_alpha_validated'] &= (sample['blank'] == 0 and sample['changed'] >= 40
                                                              and (folder / (fault + '.done')).is_file())
            if args.steady_seconds:
                report['native_obs_alpha_validated'] &= steady_state(
                    args.steady_seconds, folder, soak, visible)
            report['callback_errors'] = soak.errors
            report['observation_logs'] = ['cycles.jsonl'] + (['steady.jsonl'] if args.steady_seconds else [])
            for short_probe_field in ('frame_samples', 'distinct_hashes', 'alpha_levels', 'hash_scope'):
                report.pop(short_probe_field)
        else:
            if args.generated_studio:consumer_ready.write_bytes(b'')
            if args.generated_studio:
                if args.gpu_visibility_cycle:
                    time.sleep(1.);obs.obs_set_output_source(0,None)
                    time.sleep(1.2);obs.obs_set_output_source(0,source)
                    time.sleep(args.seconds-2.2)
                    report['source_hidden_and_restored']=True
                elif args.gpu_view_cycle:
                    history=set();deadline=time.monotonic()+args.seconds
                    while time.monotonic()<deadline:
                        history.add((obs.obs_source_get_width(source),obs.obs_source_get_height(source)))
                        time.sleep(.05)
                    report['observed_source_canvases']=[list(x) for x in sorted(history)]
                else:time.sleep(args.seconds)
            else:
                time.sleep(args.seconds/2)
                phase[0] = 'paused'
                feed_enabled.clear()
                time.sleep(1.5)
                phase[0] = 'resumed'
                feed_enabled.set()
                time.sleep(args.seconds/2-1.5)
            report['source_dimensions'] = [obs.obs_source_get_width(source), obs.obs_source_get_height(source)]
            report['frame_samples'] = len(samples)
            report['distinct_hashes'] = len({sample[1] for sample in samples})
            report['changed_generated_rows'] = sum(a[1] != b[1] for a, b in zip(samples, samples[1:]))
            report['observed_band_rgba'] = samples[-1][2] if samples else []
            report['alpha_levels'] = sorted({band[3] for _, _, bands, _ in samples for band in bands})
            report['callback_errors'] = errors
            report['publisher_frames'] = publisher.published if publisher else None
            report['raw_output_format'] = 'BGRA'
            valid = [row for row in samples if [band[3] for band in row[2]] == [0, 128, 255]]
            if args.generated_studio:
                colors = bool(valid) and all(bands[0] == [0, 0, 0, 0]
                    and all(value <= 128 for value in bands[1][:3])
                    for _, _, bands, _ in valid)
            else:
                colors = bool(valid) and all(
                    bands[0] == [0, 0, 0, 0] and bands[1] == [40, 64, 80, 128]
                    and 64 <= bands[2][0] <= 127 and bands[2][1:] == [128, 160, 255]
                    for _, _, bands, _ in valid)
            report['generated_color_and_premultiplication_match'] = colors
            report['loss_became_transparent'] = any(
                state == 'paused' and all(band == [0, 0, 0, 0] for band in bands)
                for _, _, bands, state in samples)
            report['resumed_with_alpha'] = any(state == 'resumed' for _, _, _, state in valid)
            if args.generated_studio:
                seen = blank = resumed = False
                for _, _, bands, _ in samples:
                    if [band[3] for band in bands] == [0, 128, 255]:
                        if blank: resumed = True
                        seen = True
                    elif seen and all(band == [0, 0, 0, 0] for band in bands):
                        blank = True
                report['loss_became_transparent'] = blank
                report['resumed_with_alpha'] = resumed
            report['native_obs_alpha_validated'] = (len(valid) >= 60 and not errors
                and report['distinct_hashes'] >= 20 and colors
                and report['loss_became_transparent'] and report['resumed_with_alpha'])
            if args.motion_background:
                colors = []
                for _, _, bands, _ in samples:
                    red, green, blue, alpha = bands[0]
                    if [band[3] for band in bands] == [255, 255, 255]:
                        if red > 200 and max(green, blue) < 30:
                            colors.append('red')
                        if green > 200 and max(red, blue) < 30:
                            colors.append('green')
                counts = {name: colors.count(name) for name in ('red', 'green')}
                transitions = sum(a != b for a, b in zip(colors, colors[1:]))
                report['motion_background'] = dict(samples=counts, transitions=transitions)
                report['native_obs_alpha_validated'] = not errors and min(counts.values()) >= 15 and transitions >= 4
            if args.gpu_view_cycle:
                report['native_obs_alpha_validated']=report['native_obs_alpha_validated'] and [height,width] in report['observed_source_canvases']
    except Exception as error:
        report['failure'] = type(error).__name__ + ': ' + str(error)
        report['native_obs_alpha_validated'] = False
    finally:
        if connected:
            obs.obs_remove_raw_video_callback(callback, None)
        if source:
            obs.obs_set_output_source(0, None)
            obs.obs_source_release(source)
        if settings:
            obs.obs_data_release(settings)
        finish.set()
        if feeder:
            feeder.join(2)
        if publisher:
            publisher.close()
        if script:
            scripting.obs_script_destroy(script)
        if scripts:
            scripting.obs_scripting_unload()
        if active:
            obs.obs_shutdown()
        if studio:
            try:
                studio_code = studio.wait(timeout=12)
            except subprocess.TimeoutExpired:
                studio.kill()
                studio_code = studio.wait(timeout=3)
            report['generated_studio_exit'] = studio_code
            report['native_obs_alpha_validated'] = report.get('native_obs_alpha_validated', False) and studio_code == 0
            if args.gpu_studio:
                summaries=list(folder.glob('output/studio-smoke-*/summary.json'))
                if len(summaries)==1:
                    generated=json.loads(summaries[0].read_text())
                    metrics=generated.get('reports',[{}])[0]
                    report['gpu_sender']={key:metrics.get(key) for key in ('frame_output_published','gpu_output_cpu_readbacks','gpu_output_resource_generations','gpu_output_busy_skips','gpu_output_consumer_error','frame_output_error','frame_output_submit_p95_ms')}
                    if soak:
                        report['native_obs_alpha_validated'] &= (
                            metrics.get('gpu_output_resource_generations', 0) >= 3 * args.soak_cycles
                            and metrics.get('gpu_output_cpu_readbacks') == 0
                            and not metrics.get('gpu_output_consumer_error') and not metrics.get('frame_output_error'))
                    if args.gpu_reject_adapter:
                        report['adapter_rejection_validated']=(studio_code==0 and report['frame_samples']>=60
                            and report['alpha_levels']==[0] and bool(metrics.get('gpu_output_consumer_error')))
                elif soak:
                    report['native_obs_alpha_validated'] = False
        if soak:
            counts = folder / 'obs-module/observed-copies.txt'
            try:
                copies, ids, epochs = map(int, counts.read_text().split())
            except (ValueError, OSError):
                copies = ids = epochs = 0
            report['gpu_consumer'] = dict(copies=copies, distinct_descriptor_ids_at_copy=ids,
                                          observed_resource_epochs=epochs)
            report['native_obs_alpha_validated'] &= copies >= ids >= 20 and epochs >= 3 * args.soak_cycles
        if studio_log:
            studio_log.close()
        directory.close()
        os.chdir(previous_directory)
        (folder/'summary.json').write_bytes((json.dumps(report, indent=2)+'\n').encode())
    print(json.dumps(dict(report, proof_folder=str(folder))))
    return 0 if (report.get('adapter_rejection_validated') if args.gpu_reject_adapter else report.get('native_obs_alpha_validated')) else 1


if __name__ == '__main__':
    raise SystemExit(main())
