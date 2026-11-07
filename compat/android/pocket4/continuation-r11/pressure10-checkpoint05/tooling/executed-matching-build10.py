#!/usr/bin/env python3
"""One create-only host build; no Android/namespace/pressure invocation."""
from pathlib import Path, PurePosixPath
import datetime
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import traceback

ARCHIVE = Path('/home/alex/work/pocket4-lmkd-host-pressure-r11-source-10.tar.gz')
ROOT = Path('/home/alex/work/pocket4-lmkd-host-pressure-r11-source-10')
ARCHIVE_SHA = 'b82cdd3818150417525a2b74ba898c66d99987fee859fe20fcc5a62d697bae67'
MANIFEST_SHA = 'bc996fe6c763b0270de97d85c0f7ace71fd3804ca432c49d79f05ec21edec9e5'
PREFIX = 'host-pressure-freeze-10/'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def exclusive(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def events(path):
    return dict((key, int(value)) for key, value in (line.split() for line in path.read_text().splitlines()))


def check_inputs(files):
    observed = {}
    for name, entry in files.items():
        path = ROOT / name
        status = path.lstat()
        require(stat.S_ISREG(status.st_mode) and not path.is_symlink(), 'nonregular source input')
        raw = path.read_bytes()
        require(len(raw) == entry['bytes'] and digest(raw) == entry['sha256'], 'source pin mismatch: ' + name)
        observed[name] = {'bytes': len(raw), 'sha256': digest(raw)}
    require(digest((ROOT / 'source-manifest.json').read_bytes()) == MANIFEST_SHA, 'manifest changed')
    return observed


def main():
    receipt = {'schema': 1, 'started_at': utc(), 'success': False, 'commands': [],
               'archive_sha256': ARCHIVE_SHA, 'source_manifest_sha256': MANIFEST_SHA,
               'root': str(ROOT), 'pressure_executed': False, 'android_started': False,
               'runtime_canary_executed': False, 'installed_files_changed': False}
    created = False
    try:
        membership = Path('/proc/self/cgroup').read_text()
        require(membership.startswith('0::/') and membership.count('\n') == 1, 'unified own job cgroup required')
        own_cgroup = Path('/sys/fs/cgroup') / membership[3:].strip().lstrip('/')
        maximum = (own_cgroup / 'memory.max').read_text().strip()
        cpu = (own_cgroup / 'cpu.max').read_text().split()
        nice = os.getpriority(os.PRIO_PROCESS, 0)
        require(maximum == '536870912' and len(cpu) == 2 and cpu[0].isdigit() and cpu[0] == cpu[1] and nice >= 5,
                'actual 512 MiB/one CPU/nice 5 resource contract missing')
        before_events = events(own_cgroup / 'memory.events')
        receipt['resources'] = {'cgroup': str(own_cgroup), 'memory_max': maximum,
                                'cpu_max': ' '.join(cpu), 'nice': nice,
                                'memory_events_before': before_events}
        source_status = ARCHIVE.lstat()
        require(stat.S_ISREG(source_status.st_mode) and not ARCHIVE.is_symlink(), 'archive must be a held regular path')
        packed = ARCHIVE.read_bytes()
        require(digest(packed) == ARCHIVE_SHA and len(packed) == 130913, 'archive bytes/pin differ')
        with tarfile.open(fileobj=io.BytesIO(packed), mode='r:gz') as archive:
            members = archive.getmembers()
            require(len(members) == 39 and all(member.isfile() for member in members), 'exact text archive shape')
            unpacked = {}
            for member in members:
                require(member.name.startswith(PREFIX), 'archive prefix mismatch')
                name = member.name[len(PREFIX):]
                path = PurePosixPath(name)
                require(name and not path.is_absolute() and '..' not in path.parts and str(path) == name and name not in unpacked,
                        'noncanonical or repeated archive member')
                require(0 < member.size < 1024 * 1024, 'archive member bound')
                raw = archive.extractfile(member).read()
                require(len(raw) == member.size and b'\x00' not in raw and not raw.startswith(b'\x7fELF'), 'only exact UTF8 source payload')
                raw.decode('utf-8', errors='strict')
                unpacked[name] = raw
        require(digest(unpacked['source-manifest.json']) == MANIFEST_SHA, 'inner manifest pin differs')
        manifest = json.loads(unpacked['source-manifest.json'])
        require(manifest['revision'] == 'host-pressure-freeze-10' and manifest['expected_rust_tests'] == 20 and
                manifest['expected_ordinary_ipc_controls'] == 7 and manifest['expected_synthetic_python_controls'] == 28,
                'fixed revision/control count mismatch')
        require(set(unpacked) == set(manifest['files']) | {'source-manifest.json'}, 'archive/manifest set differs')
        for name, entry in manifest['files'].items():
            require(len(unpacked[name]) == entry['bytes'] and digest(unpacked[name]) == entry['sha256'], 'inner source hash differs')
        ROOT.mkdir(mode=0o700)
        created = True
        for name, raw in unpacked.items():
            path = ROOT / name
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            exclusive(path, raw)
        receipt['inputs_before'] = check_inputs(manifest['files'])
        exclusive(ROOT / 'build-start.json', (json.dumps({'started_at': receipt['started_at'], 'archive_sha256': ARCHIVE_SHA,
            'source_manifest_sha256': MANIFEST_SHA, 'runtime': False}, sort_keys=True) + '\n').encode())
        (ROOT / 'build-logs').mkdir(mode=0o700)
        compiler = shutil.which('cargo')
        if compiler is None and Path('/home/alex/.cargo/bin/cargo').is_file():
            compiler = '/home/alex/.cargo/bin/cargo'
        require(compiler is not None, 'existing cargo unavailable; no network installation')
        cxx = shutil.which('g++')
        require(cxx is not None, 'existing C++ compiler unavailable')
        env = os.environ.copy()
        env['CARGO_TARGET_DIR'] = str(ROOT / 'target')
        env['CARGO_BUILD_JOBS'] = '1'
        env['RUST_TEST_THREADS'] = '1'
        commands = [
            ('build', [compiler, 'build', '--locked', '--offline', '-j', '1'], 120),
            ('tests', [compiler, 'test', '--locked', '--offline', '-j', '1'], 120),
            ('ordinary-ipc', [str(ROOT / 'target/debug/owned-ipc-controls')], 20),
            ('actor-build', [cxx, '-std=c++20', '-O1', '-Wall', '-Wextra', '-Werror', '-pthread',
                             'owned-relay/fixture_init.cpp', '-o', 'owned-relay/fixture-init'], 45),
            ('qualifier-controls', ['/usr/bin/python3', '-B', '-m', 'unittest', 'discover', '-s', 'owned-relay',
                                    '-p', 'test_qualify_pressure.py', '-v'], 20),
        ]
        for name, argv, timeout in commands:
            began = time.monotonic()
            completed = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, timeout=timeout)
            stdout_path, stderr_path = ROOT / 'build-logs' / (name + '.stdout'), ROOT / 'build-logs' / (name + '.stderr')
            exclusive(stdout_path, completed.stdout)
            exclusive(stderr_path, completed.stderr)
            require(len(completed.stdout) <= 262144 and len(completed.stderr) <= 262144, 'build/control output exceeded receipt bound')
            stdout, stderr = completed.stdout.decode('utf-8', errors='replace'), completed.stderr.decode('utf-8', errors='replace')
            row = {'name': name, 'argv': argv, 'returncode': completed.returncode,
                   'elapsed_seconds': time.monotonic() - began, 'stdout': stdout, 'stderr': stderr,
                   'stdout_sha256': digest(completed.stdout), 'stderr_sha256': digest(completed.stderr)}
            receipt['commands'].append(row)
            require(completed.returncode == 0, name + ' failed')
            if name == 'tests':
                passed = sum(map(int, re.findall(r'test result: ok\. (\d+) passed;', stdout)))
                require(passed == 20 and not re.search(r'test result: FAILED|[1-9][0-9]* failed;', stdout), 'actual Rust test count/result mismatch')
                receipt['rust_tests_passed'] = passed
            elif name == 'ordinary-ipc':
                passed = sum(line.startswith('PASS ') for line in stdout.splitlines())
                require(passed == 7 and 'RESULT PASS mode=host-negative-controls' in stdout, 'actual ordinary IPC controls mismatch')
                receipt['ordinary_ipc_passed'] = passed
            elif name == 'qualifier-controls':
                require('Ran 28 tests' in stderr and stderr.rstrip().endswith('OK'), 'actual Python test count/result mismatch')
                receipt['synthetic_python_tests_passed'] = 28
        receipt['inputs_after'] = check_inputs(manifest['files'])
        require(receipt['inputs_before'] == receipt['inputs_after'], 'source inputs changed')
        receipt['binaries'] = []
        for relative in ['target/debug/droidloom-psi-owner', 'target/debug/owned-relay-canary',
                         'target/debug/owned-ipc-controls', 'owned-relay/fixture-init']:
            path = ROOT / relative
            require(path.is_file() and not path.is_symlink(), 'matching output missing')
            raw = path.read_bytes()
            receipt['binaries'].append({'path': str(path), 'bytes': len(raw), 'sha256': digest(raw)})
        after_events = events(own_cgroup / 'memory.events')
        receipt['resources']['memory_events_after'] = after_events
        for key in ['max', 'oom', 'oom_kill', 'oom_group_kill']:
            require(after_events[key] == before_events[key], 'own build job memory event changed: ' + key)
        receipt['success'] = True
        receipt['error'] = None
    except Exception as error:
        receipt['error'] = type(error).__name__ + ': ' + str(error)
        receipt['traceback'] = traceback.format_exc()
    finally:
        receipt['finished_at'] = utc()
        raw = (json.dumps(receipt, indent=2, sort_keys=True) + '\n').encode()
        if created:
            exclusive(ROOT / 'build-result.json', raw)
        print(json.dumps({'success': receipt['success'], 'error': receipt.get('error'),
                          'receipt': str(ROOT / 'build-result.json') if created else None,
                          'receipt_sha256': digest(raw) if created else None,
                          'rust_tests_passed': receipt.get('rust_tests_passed'),
                          'ordinary_ipc_passed': receipt.get('ordinary_ipc_passed'),
                          'synthetic_python_tests_passed': receipt.get('synthetic_python_tests_passed'),
                          'runtime_canary_executed': False}, sort_keys=True), flush=True)
    return 0 if receipt['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
