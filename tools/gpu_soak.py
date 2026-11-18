"""Generated 1080p GPU bridge soak. Run with the diagnostics environment on Windows."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ucs.process_job import ProcessJob

CYCLE_SECONDS = 24
OUTPUT = (160, 90)


class Observer:
    """One middle row and constant-size counters for the current phase."""
    def __init__(self):
        self.lock = threading.Lock()
        self.errors = 0
        self.reset()

    def reset(self):
        with self.lock:
            self.valid = self.changed = self.blank = self.samples = 0
            self.previous = None

    def receive(self, pointer):
        try:
            frame = pointer.contents
            width, height = OUTPUT
            if not frame.data[0] or frame.linesize[0] < width * 4:
                raise ValueError('Invalid BGRA stride')
            start = ctypes.cast(frame.data[0], ctypes.c_void_p).value
            row = ctypes.string_at(start + height // 2 * frame.linesize[0], width * 4)
            alpha = tuple(row[4 * x + 3] for x in (width // 8, width // 2, width * 7 // 8))
            with self.lock:
                self.samples += 1
                self.blank += not any(row)
                if alpha == (0, 128, 255):
                    self.valid += 1
                    self.changed += self.previous is not None and self.previous != row
                    self.previous = row
        except Exception:
            with self.lock:
                self.errors += 1

    def snapshot(self):
        with self.lock:
            return dict(samples=self.samples, valid=self.valid, changed=self.changed, blank=self.blank)


def resources():
    parent = psutil.Process()
    private = handles = cpu = 0
    for process in [parent, *parent.children(recursive=True)]:
        with process.oneshot():
            private += process.memory_info().private
            handles += process.num_handles()
            cpu += sum(process.cpu_times()[:2])
    return dict(private_mib=round(private / 2**20, 1), handles=handles, cpu_seconds=round(cpu, 2))


def exercise(cycles, folder, observer, dimensions, visible, recreate):
    baseline = previous = None
    accepted = True
    for cycle in range(cycles):
        start = time.monotonic()
        observer.reset()
        (folder / f'cycle-{cycle}.ready').touch()

        def observe_until(seconds):
            time.sleep(max(0, start + seconds - time.monotonic()))
            sample = observer.snapshot()
            observer.reset()
            return sample

        initial = observe_until(1.9)
        pause = observe_until(3.95)
        resumed = observe_until(5.8)
        observe_until(8.8)
        portrait = dimensions()
        observe_until(12.5)
        landscape = dimensions()
        visible(False)
        observer.reset()
        hidden = observe_until(15)
        visible(True)
        observer.reset()
        shown = observe_until(18.5)
        recreate()
        observer.reset()
        recreated = observe_until(CYCLE_SECONDS)
        current = resources()
        now = time.monotonic()
        if cycle == 1:
            baseline = current
        passed = (min(initial['changed'], resumed['changed'], shown['changed'], recreated['changed']) >= 5
                  and pause['blank'] >= 2 and hidden['blank'] >= 20
                  and portrait == (1080, 1920) and landscape == (1920, 1080) and observer.errors == 0)
        if baseline:
            passed &= current['private_mib'] - baseline['private_mib'] <= 128
            passed &= current['handles'] - baseline['handles'] <= 64
        row = dict(cycle=cycle + 1, passed=passed, initial=initial, pause=pause, resumed=resumed,
                   portrait=portrait, landscape=landscape, hidden=hidden, shown=shown, recreated=recreated,
                   callback_errors=observer.errors, resources=current)
        if previous:
            row['mean_cpu_cores'] = round((current['cpu_seconds'] - previous[0]) / (now - previous[1]), 2)
        with (folder / 'cycles.jsonl').open('a', encoding='utf-8') as log:
            log.write(json.dumps(row) + '\n')
        previous = current['cpu_seconds'], now
        accepted &= passed
    return accepted


def steady_state(seconds, folder, observer, visible):
    """Compare uninterrupted export with the same live processes and source hidden."""
    baseline = resources()
    previous = baseline
    accepted = True
    for index in range(seconds // 10 + 2):
        exporting = index < seconds // 10
        if index == seconds // 10:
            visible(False)
        observer.reset()
        start = time.monotonic()
        time.sleep(10)
        result = observer.snapshot()
        current = resources()
        elapsed = time.monotonic() - start
        passed = (result['changed'] >= 120 and result['blank'] == 0 if exporting
                  else result['blank'] >= 240)
        passed &= (observer.errors == 0 and current['private_mib'] - baseline['private_mib'] <= 128
                   and current['handles'] - baseline['handles'] <= 64)
        row = dict(window=index + 1, exporting=exporting, passed=passed, **result,
                   resources=current, callback_errors=observer.errors,
                   mean_cpu_cores=round((current['cpu_seconds'] - previous['cpu_seconds']) / elapsed, 2))
        with (folder / 'steady.jsonl').open('a', encoding='utf-8') as log:
            log.write(json.dumps(row) + '\n')
        previous = current
        accepted &= passed
    return accepted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cycles', type=int, choices=range(1, 26), default=8)
    parser.add_argument('--steady-seconds', type=int, choices=range(0, 601, 10), default=0,
                        metavar='0..600', help='Additional uninterrupted export in multiples of 10 s, then 20 s hidden')
    parser.add_argument('--pressure', action='store_true', help='Inject one late pipe response and one stale descriptor')
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('This soak uses Windows D3D11 and Job Objects')
    cycles = args.cycles
    folder = ROOT / 'output' / f'gpu-soak-{time.time_ns()}'
    folder.mkdir(parents=True)
    deadline = CYCLE_SECONDS * cycles + args.steady_seconds + (20 if args.steady_seconds else 0) + (10 if args.pressure else 0) + 45
    print(folder, flush=True)
    command = [sys.executable, str(ROOT / 'tools/probe_obs_alpha.py'), '--resolution', '1080',
               '--generated-studio', '--gpu-studio', '--soak-cycles', str(cycles), '--steady-seconds', str(args.steady_seconds)]
    if args.pressure:
        command.append('--pressure')
    started = time.monotonic()
    receipt = dict(cycles=cycles, steady_seconds=args.steady_seconds, deadline_seconds=deadline, passed=False)
    with (folder / 'worker.log').open('wb') as log:
        worker = subprocess.Popen(command, cwd=folder, stdout=log, stderr=subprocess.STDOUT,
                                  creationflags=subprocess.CREATE_NO_WINDOW | 4)  # CREATE_SUSPENDED
        try:
            job = ProcessJob(worker)
            try:
                psutil.Process(worker.pid).resume()
                code = worker.wait(max(0, deadline - (time.monotonic() - started)))
                receipt.update(worker_exit=code, passed=code == 0)
                return code
            except subprocess.TimeoutExpired:
                receipt['timed_out'] = True
                return 1
            finally:
                job.close()
        finally:
            if worker.poll() is None:
                worker.kill()
                worker.wait(5)
            receipt['elapsed_seconds'] = round(time.monotonic() - started, 3)
            (folder / 'result.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    raise SystemExit(main())
