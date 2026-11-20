#!/usr/bin/python3
"""Bounded external observation only; never grants R24 build admission.

The fixed user service is p4-r24-resource-preflight-20261120-3b9d-r1.service.
Its complete actual terminal is separate post-freeze scheduling evidence.
No worker, source lock, systemctl, child process, build or retry is invoked.
"""
from pathlib import Path
import hashlib
import json
import os
import resource
import signal
import stat
import time

ROOT = Path('/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1')
STAGE = Path('/home/qq/work/p4-r24-controller-preparation-20261120-3b9d-r1')
REPORT = STAGE / 'RESOURCE-PREFLIGHT.json'
UNIT = 'p4-r24-resource-preflight-20261120-3b9d-r1.service'
REQUIRED_MEMORY = 44 * 1024**3
WINDOW_NS = 60 * 10**9
TOTAL_NS = 600 * 10**9
MAX_SAMPLE_GAP_NS = 2 * 10**9


def need(value, message):
    if not value:
        raise RuntimeError(message)


def next_window(start, previous, now, available):
    need(type(now) is int and type(available) is int and available >= 0,
         'actual monotonic time and memory are native integers')
    need(previous is None or type(previous) is int and previous <= now,
         'monotonic ordered observations')
    if available < REQUIRED_MEMORY:
        return None
    if start is None or previous is None or now - previous > MAX_SAMPLE_GAP_NS:
        return now
    need(type(start) is int and start <= previous, 'actual window origin')
    return start


def observe():
    values = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        need(key not in values, 'unique actual meminfo field')
        values[key] = value.strip().split()
    row = {'observed_ns': time.time_ns(), 'monotonic_ns': time.monotonic_ns()}
    for name in ('MemAvailable', 'MemFree', 'Cached', 'Shmem'):
        words = values[name]
        need(len(words) == 2 and words[0].isascii() and words[0].isdigit()
             and words[1] == 'kB', 'actual kernel memory unit')
        row[name] = int(words[0]) * 1024
    disk = os.statvfs(ROOT)
    row['disk_available_bytes'] = disk.f_bavail * disk.f_frsize
    return row


def identity():
    names = ('cgroup', 'ipc', 'mnt', 'net', 'pid', 'time', 'user', 'uts')
    result = {'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              'namespaces': {}, 'uid': os.getuid(), 'euid': os.geteuid(), 'gid': os.getgid()}
    for name in names:
        info = os.stat('/proc/self/ns/' + name)
        result['namespaces'][name] = [info.st_dev, info.st_ino]
    return result


def save(value):
    need(STAGE.resolve() == STAGE, 'canonical fixed external observation directory')
    parent = STAGE.stat()
    need(stat.S_ISDIR(parent.st_mode) and parent.st_uid == parent.st_gid == 1000
         and not parent.st_mode & 0o022, 'original owner-controlled observation directory')
    raw = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    fd = os.open(REPORT, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    return {'path': str(REPORT), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def main():
    need(os.getuid() == os.geteuid() == os.getgid() == 1000, 'ordinary original ai395 owner')
    need(18 in os.sched_getaffinity(0), 'reserved light observation CPU18')
    os.sched_setaffinity(0, {18})
    resource.setrlimit(resource.RLIMIT_AS, (64 * 1024**2, 64 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024**2, 1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    signal.alarm(610)
    need(not os.path.lexists(REPORT), 'create-only external observation report')
    before = identity()
    started = time.monotonic_ns(); deadline = started + TOTAL_NS
    samples = []; window = None; previous = None; satisfied = False
    while True:
        now = time.monotonic_ns()
        if now > deadline:
            break
        row = observe(); now = row['monotonic_ns']
        if now > deadline:
            break
        window = next_window(window, previous, now, row['MemAvailable'])
        row['window_started_monotonic_ns'] = window
        samples.append(row); previous = now
        if len(samples) == 1 or len(samples) % 10 == 0:
            print(json.dumps({'sample': len(samples), **row, 'build_admission_granted': False}), flush=True)
        if window is not None and now - window >= WINDOW_NS:
            satisfied = True
            break
        remaining_ns = deadline - time.monotonic_ns()
        if remaining_ns <= 0:
            break
        time.sleep(min(10**9, remaining_ns) / 10**9)
    after = identity()
    need(before == after, 'same host boot and namespace view throughout observation')
    result = {'schema': 'p4-r24-external-readonly-resource-preflight-v1',
        'unit': UNIT, 'identity_before': before, 'identity_after': after,
        'required_memory_bytes': REQUIRED_MEMORY, 'required_observed_window_ns': WINDOW_NS,
        'total_observation_budget_ns': TOTAL_NS, 'maximum_accepted_sample_gap_ns': MAX_SAMPLE_GAP_NS,
        'started_monotonic_ns': started, 'finished_monotonic_ns': time.monotonic_ns(),
        'sampled_window_satisfied': satisfied, 'samples': samples,
        'source_mutations': 0, 'source_locks_acquired': False, 'children_started': 0,
        'build_started': False, 'build_retry_requested': False, 'build_admission_granted': False,
        'original_worker_fresh_42_GiB_and_144_GiB_gate_still_required': True,
        'original_150_second_retirement_gate_still_required': True,
        'runtime_qualified': False, 'production_ready': False}
    reference = save(result)
    print(json.dumps({'sampled_window_satisfied': satisfied, 'report': reference,
        'build_admission_granted': False, 'build_started': False,
        'runtime_qualified': False, 'production_ready': False}), flush=True)
    raise SystemExit(0 if satisfied else 1)


if __name__ == '__main__':
    main()
