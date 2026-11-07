#!/usr/bin/python3 -I
"""Read-only diagnosis of a frozen runtime guard mismatch. Never enters Android.

Writes only a new, private evidence directory. Does not change any guard,
activation, cgroup, namespace, service, process, package, or Android state.
"""
from pathlib import Path
import datetime
import hashlib
import json
import os
import re
import stat
import time

ROOT = Path('/home/alex/work/pocket4-main-runtime-boundary-20261105-r12-01')
TX = Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
TX_SHA = 'b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
ACTIVATION = Path('/home/alex/work/pocket4-app-production-20261104-r10/deployment-preparation/activation-after-01.json')
ACTIVATION_SHA = '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
EPOCH = Path('/home/alex/work/pocket4-framework-epoch-20261104-r10/framework_epoch.py')
EPOCH_SHA = 'f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288'
CELL_SHA = 'f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc'
CGROUP = Path('/sys/fs/cgroup/system.slice/droidloomd.service')
GALLERY = Path('/home/alex/work/pocket4-gallery-video-flow-20261105-r12-02/result.json')

def require(value, reason):
    if not value:
        raise RuntimeError(reason)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def ordinary(path, expected=None, maximum=1048576):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 <= before.st_size <= maximum, 'INPUT_SCOPE')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(maximum + 1)
        after = os.fstat(fd)
        require(len(raw) == before.st_size and all(getattr(before, key) == getattr(after, key) for key in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')), 'INPUT_CHANGED')
        require(expected is None or digest(raw) == expected, 'INPUT_PIN_CHANGED')
        return raw
    finally:
        os.close(fd)

def kernel_text(path, maximum=65536):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), 'KERNEL_FILE_REQUIRED')
        raw = os.read(fd, maximum + 1)
        require(len(raw) <= maximum, 'KERNEL_READ_BOUND')
        return raw.decode('utf-8').strip()
    finally:
        os.close(fd)

def write_new(name, raw):
    fd = os.open(ROOT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o640)
    try:
        os.fchown(fd, 0, 1000)
        os.fchmod(fd, 0o640)
        with os.fdopen(os.dup(fd), 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)
    return {'file': name, 'bytes': len(raw), 'sha256': digest(raw)}

def process(pid):
    require(isinstance(pid, int) and 1 <= pid <= 4194304, 'FIXED_PID_REQUIRED')
    base = Path('/proc') / str(pid)
    raw = kernel_text(base / 'stat', 16384)
    fields = raw[raw.rfind(')') + 2:].split()
    require(len(fields) >= 20, 'PROC_STAT_TRUNCATED')
    status = kernel_text(base / 'status')
    uid = re.findall(r'^Uid:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)$', status, re.M)
    require(len(uid) == 1, 'PROC_UID_REQUIRED')
    return {'host_pid': pid, 'start_ticks': int(fields[19]), 'uids': list(uid[0]),
            'namespaces': {key: os.readlink(base / 'ns' / key) for key in ('mnt', 'pid', 'net', 'uts', 'ipc', 'user')},
            'exe': os.readlink(base / 'exe'), 'cgroup': kernel_text(base / 'cgroup', 4096)}

def observe(keys, pids):
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return {'utc': stamp, 'monotonic_ns': str(time.monotonic_ns()),
            'limits': {key: kernel_text(CGROUP / key, 4096) for key in keys},
            'processes': {key: process(pid) for key, pid in pids.items()}}

def main():
    require(os.geteuid() == 0, 'READ_ONLY_ROOT_REQUIRED')
    ordinary(TX, TX_SHA)
    activation_raw = ordinary(ACTIVATION, ACTIVATION_SHA)
    activation = json.loads(activation_raw)
    epoch_raw = ordinary(EPOCH, EPOCH_SHA)
    expected = activation['limits']
    require(isinstance(expected, dict) and 0 < len(expected) <= 32 and all(re.fullmatch(r'[a-z][a-z0-9_.]*', key) and isinstance(value, str) for key, value in expected.items()), 'EXPECTED_LIMITS_SCOPE')
    pids = {'main_host': 3588089, 'main_init': 3588093, 'presenter': 3588024}
    for key in ('daemon_process', 'launcher_process', 'presenter_process'):
        pids[key] = activation[key]['host_pid']
    before = observe(expected, pids)
    self_cgroup = kernel_text(Path('/proc/self/cgroup'), 4096)
    cell = ordinary('/etc/droidloom/cell.json')
    counters = {key: kernel_text(CGROUP / key, 16384) for key in ('memory.current', 'memory.events', 'memory.peak', 'cpu.stat', 'pids.current') if (CGROUP / key).exists()}
    gallery = ordinary(GALLERY, maximum=65536)
    gallery_json = json.loads(gallery)
    after = observe(expected, pids)
    ordinary(TX, TX_SHA)
    ordinary(ACTIVATION, ACTIVATION_SHA)
    ordinary(EPOCH, EPOCH_SHA)
    cell_after = ordinary('/etc/droidloom/cell.json')
    result = {'schema': 'pocket4-main-limits-readonly-diagnostic/v1',
              'scope': {'android_commands': 0, 'ui_actions': 0, 'package_actions': 0, 'cgroup_writes': 0, 'process_signals': 0, 'namespace_entries': 0, 'service_actions': 0, 'guard_changes': 0, 'fresh_main_selection': False},
              'pins': {'transaction_sha256': TX_SHA, 'activation_sha256': ACTIVATION_SHA, 'epoch_source_sha256': EPOCH_SHA},
              'expected_limits': expected, 'before': before, 'after': after,
              'differences': {key: {'expected': expected[key], 'before': before['limits'][key], 'after': after['limits'][key]} for key in expected if expected[key] != before['limits'][key] or expected[key] != after['limits'][key]},
              'limits_stable_across_read': before['limits'] == after['limits'],
              'processes_stable_across_read': before['processes'] == after['processes'],
              'expected_host_processes': {key: activation[key] for key in ('daemon_process', 'launcher_process', 'presenter_process')},
              'expected_framework_epoch_sha256': activation['framework_epoch']['sha256'],
              'expected_framework_processes': activation['framework_epoch']['binding']['processes'],
              'cell_sha256': digest(cell), 'cell_pin_matches': digest(cell) == CELL_SHA, 'cell_unchanged': cell == cell_after,
              'own_job_cgroup': self_cgroup, 'main_cgroup_counters_observed': counters,
              'gallery02_original': {'bytes': len(gallery), 'sha256': digest(gallery), 'value': gallery_json},
              'qualification': 'Diagnosis only; no runtime rebaseline, repair, or App qualification.'}
    ROOT.mkdir(mode=0o750)
    os.chown(ROOT, 0, 1000)
    os.chmod(ROOT, 0o750)
    result['exports'] = [write_new('epoch-source-original.py', epoch_raw), write_new('gallery02-result-original.json', gallery)]
    raw = (json.dumps(result, indent=2, sort_keys=True) + '\n').encode()
    record = write_new('result.json', raw)
    print(json.dumps({'state': 'READ_ONLY_DIAGNOSIS_COMPLETE', 'result': record, 'differences': result['differences'], 'limits_stable': result['limits_stable_across_read'], 'processes_stable': result['processes_stable_across_read']}), flush=True)

if __name__ == '__main__':
    main()
