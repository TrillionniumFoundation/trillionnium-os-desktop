#!/usr/bin/env python3
"""Fixed read-only Main snapshot. Root helper; no Android or service actions."""
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import stat
import time
import types

EPOCH_MODULE = Path('/home/alex/work/pocket4-framework-epoch-20261104-r10/framework_epoch.py')
EPOCH_SOURCE_SHA = 'f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288'
ACTIVATION = Path('/home/alex/work/pocket4-app-production-20261104-r10/deployment-preparation/activation-after-01.json')
ACTIVATION_SHA = '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
EPOCH_SHA = '48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'
INIT_PID = 3588093
CG = Path('/sys/fs/cgroup/system.slice/droidloomd.service')
CELL = Path('/etc/droidloom/cell.json')
CELL_SHA = 'f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc'
ENGINE_SHA = 'c8b9bae4466d4f66525fdef6bcec140b29612581efeb6ceb621f96e17277d26d'
PRESENTER_SHA = '47f34d5f68783a372283cb63a42034d5899e270524cca40122bf28fd5e903f24'


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_regular(path):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'unsafe fixed input')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(1024 * 1024 + 1)
        require(len(raw) <= 1024 * 1024, 'fixed input too large')
        return raw
    finally:
        os.close(fd)


def parse_counters(text):
    rows = {}
    for line in text.splitlines():
        key, value = line.split()
        require(key not in rows and value.isdecimal(), 'counter format changed')
        rows[key] = int(value)
    return rows


def capture():
    require(os.getuid() == 0 and os.geteuid() == 0, 'read-only helper requires root')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.alarm(15)  # Self-only watchdog; this helper never launches children.
    start = time.monotonic_ns()
    raw = read_regular(ACTIVATION)
    require(sha(raw) == ACTIVATION_SHA, 'activation receipt changed')
    activation = json.loads(raw)
    require(activation['main_deployed'] is True and
            activation['engine_sha256'] == ENGINE_SHA and
            activation['presenter_sha256'] == PRESENTER_SHA, 'wrong recorded activation')
    epoch_raw = read_regular(EPOCH_MODULE)
    require(sha(epoch_raw) == EPOCH_SOURCE_SHA, 'epoch module changed')
    epoch = types.ModuleType('pinned_readonly_framework_epoch')
    epoch.__file__ = str(EPOCH_MODULE)
    exec(compile(epoch_raw, str(EPOCH_MODULE), 'exec'), epoch.__dict__)
    bound = activation['framework_epoch']
    require(bound['sha256'] == EPOCH_SHA and
            bound['binding']['processes']['init']['host_pid'] == INIT_PID, 'wrong activation epoch')
    epoch.require_unchanged(bound)
    require(sha(read_regular(CELL)) == CELL_SHA, 'Main config changed')
    hosts = {}
    for field in ('daemon_process', 'launcher_process', 'presenter_process'):
        expected = activation[field]
        actual = epoch.process_identity(expected['host_pid'])
        require(actual == expected, 'host process changed: ' + field)
        hosts[field] = {'host_pid': actual['host_pid'], 'start_ticks': actual['start_ticks'],
                        'identity_sha256': sha(json.dumps(actual, sort_keys=True, separators=(',', ':')).encode())}
    cg_fd = os.open(CG, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        cg_info = os.fstat(cg_fd)
        def cg_read(name):
            require(name and '/' not in name and name not in ('.', '..'), 'unsafe cgroup filename')
            fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=cg_fd)
            try:
                with os.fdopen(fd, 'rb', closefd=False) as stream:
                    value = stream.read(65537)
                require(len(value) <= 65536, 'cgroup field too large')
                return value.decode('ascii').strip()
            finally:
                os.close(fd)
        expected_limits = activation['limits']
        require(isinstance(expected_limits, dict) and expected_limits, 'activation lacks limits')
        limits = {name: cg_read(name) for name in expected_limits}
        require(limits == expected_limits, 'Main resource limits changed')
        current_epoch = epoch.capture_android(INIT_PID)
        require(current_epoch['sha256'] == EPOCH_SHA and current_epoch['binding'] == bound['binding'],
                'framework discovery changed')
        events = parse_counters(cg_read('memory.events'))
        require({'oom', 'oom_kill', 'oom_group_kill'} <= events.keys(), 'OOM counters incomplete')
        current = {name: int(cg_read(name)) for name in
                   ('memory.current', 'memory.swap.current', 'pids.current')}
        cpu = parse_counters(cg_read('cpu.stat'))
        pressure = cg_read('memory.pressure')
        require({name: cg_read(name) for name in expected_limits} == limits,
                'Main limits changed during read')
        cg_identity = {'device': cg_info.st_dev, 'inode': cg_info.st_ino}
    finally:
        os.close(cg_fd)
    epoch.require_unchanged(bound)
    require(sha(read_regular(ACTIVATION)) == ACTIVATION_SHA and
            sha(read_regular(CELL)) == CELL_SHA and
            sha(read_regular(EPOCH_MODULE)) == EPOCH_SOURCE_SHA, 'snapshot inputs changed during read')
    result = {'schema': 1, 'ok': True, 'activation_sha256': ACTIVATION_SHA,
              'epoch_source_sha256': EPOCH_SOURCE_SHA, 'framework_epoch_sha256': EPOCH_SHA,
              'cell_sha256': CELL_SHA, 'host_processes': hosts, 'limits': limits,
              'main_cgroup': str(CG), 'main_cgroup_identity': cg_identity,
              'memory_events': events, 'current_resources': current, 'cpu_stat': cpu,
              'memory_pressure': pressure, 'started_monotonic_ns': start,
              'finished_monotonic_ns': time.monotonic_ns(), 'Main_actions': 0,
              'installed_engine_hash_observed': False,
              'scope': 'Activation pin, current framework and host process identity, config, service-root cgroup limits and counters; not continuous sampling.'}
    signal.alarm(0)
    return result


if __name__ == '__main__':
    try:
        print(json.dumps(capture(), separators=(',', ':')), flush=True)
    except Exception as error:
        print(json.dumps({'schema': 1, 'ok': False, 'error': repr(error),
                          'Main_actions': 0, 'framework_epoch_sha256': EPOCH_SHA}), flush=True)
        raise SystemExit(1)
