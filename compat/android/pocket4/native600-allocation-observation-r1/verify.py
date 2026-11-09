#!/usr/bin/env python3
"""Reconstruct the exact candidate and test isolated functions, without live I/O."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report-directory', type=Path)
    args = parser.parse_args()
    base = Path(__file__).resolve().parent
    manifest = json.loads((base / 'manifest.json').read_text())
    for name, expected in manifest['files'].items():
        data = (base / name).read_bytes()
        need(len(data) == expected['bytes'] and sha(data) == expected['sha256'],
             'capsule file verification failed: ' + name)
    original = base / 'ai395_native_controller.r4.py'
    need(sha(original.read_bytes()) == manifest['controller_original_sha256'],
         'original controller SHA-256 differs')
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix='native600-observer-verification-') as directory:
        candidate = Path(directory) / 'ai395_native_controller.py'
        shutil.copyfile(original, candidate)
        env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
        env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_OPTIONAL_LOCKS='0',
                   NATIVE_OBSERVER_ORIGINAL=str(original), NATIVE_OBSERVER_CANDIDATE=str(candidate))
        for check in [True, False]:
            command = ['git', 'apply', '--whitespace=error-all']
            if check: command.append('--check')
            command.append(str(base / 'allocation-observer.patch'))
            subprocess.run(command, cwd=directory, env=env, check=True, capture_output=True, timeout=10)
        candidate_raw = candidate.read_bytes()
        need(sha(candidate_raw) == manifest['controller_candidate_sha256'],
             'candidate controller SHA-256 differs')
        compile(candidate_raw, str(candidate), 'exec')
        optimization_flags = ['-' + 'O' * sys.flags.optimize] if sys.flags.optimize else []
        test = subprocess.run([sys.executable, *optimization_flags, '-B', str(base / 'test_allocation_observer.py')],
                              cwd=directory, env=env, capture_output=True, timeout=30)
    log = test.stdout + test.stderr
    match = re.search(rb'Ran (\d+) tests', log)
    count = int(match[1]) if match else 0
    optimization = re.search(rb'^NATIVE_OBSERVER_TEST_OPTIMIZE=(\d+)$', test.stdout, re.M)
    child_optimization = int(optimization[1]) if optimization else None
    passed = (test.returncode == 0 and count == 20 and log.rstrip().endswith(b'OK')
              and child_optimization == sys.flags.optimize)
    report = {'schema': 'native600-allocation-observer-isolated-verification-v1',
              'state': 'PASS' if passed else 'FAIL', 'started_utc': started,
              'finished_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'python': platform.python_version(), 'system': platform.system(),
              'verifier_optimization': sys.flags.optimize,
              'test_child_optimization': child_optimization,
              'controller_original_sha256': manifest['controller_original_sha256'],
              'controller_candidate_sha256': manifest['controller_candidate_sha256'],
              'patch_sha256': manifest['files']['allocation-observer.patch']['sha256'],
              'patch_check_passed': True, 'candidate_hash_verified': True,
              'test_exit_code': test.returncode, 'tests_run': count,
              'test_log_bytes': len(log), 'test_log_sha256': sha(log),
              'live_hosts_modified': False, 'full_builds_started': 0,
              'build_qualified': False, 'runtime_qualified': False}
    if args.report_directory:
        args.report_directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        (args.report_directory / 'tests.log').write_bytes(log)
        (args.report_directory / 'result.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(log.decode('utf-8', errors='backslashreplace'), end='')
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
