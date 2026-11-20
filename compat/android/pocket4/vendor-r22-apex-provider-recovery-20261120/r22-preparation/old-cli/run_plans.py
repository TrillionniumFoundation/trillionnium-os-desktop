#!/usr/bin/python3
"""Run only two bound, ordinary read-only source plan commands; never materialize."""
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import signal
import stat
import time

ROOT = Path('/home/qq/work/current2359-cli-preparation-20261120-9907-r1')
CONTRACT_SHA256 = 'c9d7acb26e8e52b1eaf33e0088dbfdcb5e638041a6875ce1d2ccff6a25b49a84'
HELPER_SHA256 = 'c045a56847ff90d8a72b0d72dbb1ee312a02d2a21e14b62ab213ce8a9f3e1d82'
CURRENT = {'tree': '4d78aae1aba2ec9952c37153069cca85c5a87953', 'files': 2359, 'bytes': 44737433}


def need(ok, message):
    if not ok:
        raise RuntimeError(message)


def f9(s):
    return [s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def read(path, maximum=8 * 1024 * 1024):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path, 'canonical ordinary input required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
             and 0 <= before.st_size <= maximum, 'bounded regular single-link input required')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(before.st_size + 1)
        need(len(raw) == before.st_size and f9(before) == f9(os.fstat(fd)) == f9(path.lstat()),
             'whole input changed during read')
        return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                'identity': f9(before)}, raw
    finally:
        os.close(fd)


def check(expected):
    actual, _ = read(expected['path'])
    need(actual == expected, 'frozen actual input reference changed: ' + expected['path'])
    return actual


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def save_new(path, value):
    raw = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return read(path)[0]


def main():
    need(os.getuid() == os.geteuid() == os.getgid() == 1000, 'ordinary target account required')
    need(os.uname().machine == 'x86_64', 'expected x86_64 preparation host')
    need(len(CONTRACT_SHA256) == len(HELPER_SHA256) == 64, 'actual preparation contract is not frozen')
    contract_ref, raw = read(ROOT / 'PLAN-CONTRACT.json')
    need(contract_ref['sha256'] == CONTRACT_SHA256, 'whole actual plan contract differs')
    contract = decode(raw)
    need(contract['schema'] == 'p4-current2359-readonly-plan-contract-v1'
         and contract['host'] == 'ai395' and contract['source'] == CURRENT,
         'exact newly qualified source and execution host required')
    helper_ref, raw = read(ROOT / 'owned_process.py')
    need(helper_ref['sha256'] == HELPER_SHA256, 'unchanged process owner helper required')
    spec = importlib.util.spec_from_file_location('current2359_owned_process', ROOT / 'owned_process.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    need(read(ROOT / 'owned_process.py')[0] == helper_ref, 'process helper changed across import')
    tool = ROOT / 'bin/droidloom-source'
    profiles = ('production-full-cmake', 'production-full-lint')
    locks = [ROOT / 'producer/android/manifest' / (name + '-source-lock.json') for name in profiles]
    expected = contract['inputs']
    need([x['path'] for x in expected] == [str(tool), *map(str, locks)], 'exact three frozen ordinary inputs')
    need(expected[0]['identity'][2] == stat.S_IFREG | 0o755
         and all(x['identity'][3:6] == [1000, 1000, 1] for x in expected), 'exact ordinary deployed input ownership')
    cpus = sorted(os.sched_getaffinity(0))
    need(len(cpus) >= 3, 'leave at least two logical CPUs unused')
    os.sched_setaffinity(0, {cpus[0]})
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024**2, 2 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    need(ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0, 'owned child subreaper required')
    need(not helper.owned_children(), 'no inherited children may enter the preparation scope')
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM):
        signal.signal(signum, helper.interrupted)
    signal.alarm(120)
    outdir = ROOT / 'plans'
    outdir.mkdir(mode=0o700)
    result = {'schema': 'p4-r20-current-release-normal-plan-evidence-v1', 'host': 'ai395',
        'hostname_observed': os.uname().nodename, 'source': CURRENT, 'passed': False,
        'started_ns': time.time_ns(), 'controller_pid': os.getpid(), 'controller_uid': os.getuid(),
        'affinity': [cpus[0]], 'reserved_cpus': cpus[1:],
        'contract': contract_ref, 'process_helper': helper_ref,
        'inputs_before': [], 'inputs_after': [], 'commands': [], 'errors': [],
        'network_operations': False, 'materialize_or_reconcile': False, 'source_locks_acquired': False,
        'all_original_children_reaped': False, 'runtime_qualified': False, 'production_ready': False,
        'Android_builds': 0, 'Android_starts': 0}
    try:
        result['inputs_before'] = [check(item) for item in expected]
        for profile, lock in zip(profiles, locks):
            name = 'plan-' + profile
            argv = [str(tool), '--profile', profile, 'plan', '--lock', str(lock)]
            out, err = outdir / (name + '.stdout'), outdir / (name + '.stderr')
            started = time.time_ns()
            with out.open('xb') as stdout, err.open('xb') as stderr:
                observed = helper.execute_child(argv, ROOT,
                    {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'TZ': 'UTC', 'GIT_OPTIONAL_LOCKS': '0'},
                    stdout, stderr, 20)
            row = {'name': name, 'argv': argv, 'cwd': str(ROOT), 'started_ns': started,
                   'finished_ns': time.time_ns(), **observed, 'stdout': read(out)[0], 'stderr': read(err)[0]}
            result['commands'].append(row)
            save_new(outdir / (name + '.command.json'), row)
            need(row['exit_code'] == 0 and row['actual_child_reaped']
                 and row['original_pidfd_held_until_reaped'] and not row['error'] and not row['timed_out']
                 and not row['cleanup_errors'] and not row['owned_descendants_remaining']
                 and not row['retired_descendants'], 'original plan command or retirement failed')
            decode(read(out)[1])
            need([check(item) for item in expected] == result['inputs_before'], 'input changed across actual plan')
        result['inputs_after'] = [check(item) for item in expected]
        need(result['inputs_before'] == result['inputs_after'], 'whole plan input bookend differs')
        need(read(ROOT / 'PLAN-CONTRACT.json')[0] == contract_ref
             and read(ROOT / 'owned_process.py')[0] == helper_ref, 'prepared controller input changed')
        need(not helper.owned_children(), 'owned child remains after both actual plans')
        result['all_original_children_reaped'] = True
        result['passed'] = True
    except BaseException as failure:
        result['errors'].append({'type': type(failure).__name__, 'message': str(failure)})
    finally:
        signal.alarm(0)
        try:
            retired = helper.reap_descendants()
            result['final_retirement'] = retired
            if retired or helper.owned_children():
                result['passed'] = result['all_original_children_reaped'] = False
                result['errors'].append({'type': 'RetirementError', 'message': 'unexpected child required final retirement'})
        except BaseException as failure:
            result['passed'] = result['all_original_children_reaped'] = False
            result['errors'].append({'type': type(failure).__name__, 'message': str(failure)})
        result['finished_ns'] = time.time_ns()
        report_ref = save_new(outdir / 'PLAN-EVIDENCE.json', result)
    print(json.dumps({'passed': result['passed'], 'report': report_ref, 'errors': result['errors']}, sort_keys=True))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
