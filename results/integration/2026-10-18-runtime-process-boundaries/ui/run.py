#!/usr/bin/env python3
"""Bounded task-owned Rust invocation, with source and raw-output binding."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path('/workspace/scratch/98f315e377b2/recovery-r7/repo')
BASE = Path(__file__).resolve().parent
BIN = Path('/workspace/scratch/98f315e377b2/recovery-r7/rust-1.88/bin')
TARGET = Path('/dev/shm/trill-r9-target-ui')
SCOPES = ['ui', 'services/hepta-os/src', 'services/hepta-os/Cargo.toml',
          'services/hepta-os/Cargo.lock',
          'services/hepta-os/tests/fixtures/agentd_v2_payloads.json']


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


def source():
    names = subprocess.check_output(['git', 'ls-files', '-z', *SCOPES], cwd=ROOT)
    files = {}
    for name in names.decode().strip('\0').split('\0'):
        path = ROOT / name
        if path.is_file():
            data = path.read_bytes()
            files[name] = {'sha256': digest(data), 'bytes': len(data)}
    canonical = json.dumps(files, sort_keys=True, separators=(',', ':')).encode()
    return {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
            'files': files, 'canonical_sources_sha256': digest(canonical)}


def main():
    label = sys.argv[1]
    assert label and all(c.isalnum() or c in '-_' for c in label)
    attempt = BASE / label
    attempt.mkdir()
    before = source()
    write_json(attempt / 'source-before.json', before)
    patch = subprocess.check_output(['git', 'diff', '--', *SCOPES], cwd=ROOT)
    (attempt / 'source.patch').write_bytes(patch)
    for name in ['ui/core/src/hepta.rs', 'ui/session/src/hepta.rs',
                 'ui/shell/src/hepta_panel.rs', 'ui/shell/src/main.rs']:
        copy = attempt / 'source' / name
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes((ROOT / name).read_bytes())
    env_values = {
        'CARGO_HOME': '/dev/shm/trill-r9-cargo',
        'CARGO_TARGET_DIR': str(TARGET),
        'CARGO_PROFILE_DEV_DEBUG': '0',
        'CARGO_PROFILE_TEST_DEBUG': '0',
        'CARGO_INCREMENTAL': '0',
        'CARGO_BUILD_JOBS': '2',
    }
    env = dict(os.environ, **env_values)
    env['PATH'] = str(BIN) + ':' + env['PATH']
    command = [str(BIN / 'cargo'), *sys.argv[2:]]
    started = time.time()
    launch = {'command': command, 'cwd': str(ROOT), 'environment': env_values,
              'path_prefix': str(BIN), 'started_unix': started, 'timeout_seconds': 1200,
              'runner_sha256': digest(Path(__file__).read_bytes()),
              'tools': {name: {'sha256': digest((BIN / name).read_bytes()),
                        'version': subprocess.check_output([str(BIN / name), '--version'], env=env).decode().strip()}
                        for name in ['cargo', 'rustc']}}
    write_json(attempt / 'launch.json', launch)
    timed_out = False
    with (attempt / 'stdout-stderr.log').open('wb') as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(timeout=1200)
        except BaseException:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            code = process.returncode
    after = source()
    write_json(attempt / 'source-after.json', after)
    raw = (attempt / 'stdout-stderr.log').read_bytes()
    executables = {}
    for path in (TARGET / 'debug/deps').glob('trill_shell-*'):
        if path.is_file() and path.read_bytes()[:4] == b'\x7fELF':
            data = path.read_bytes()
            executables[str(path)] = {'sha256': digest(data), 'bytes': len(data)}
    receipt = {'exit_code': code, 'timed_out_or_interrupted': timed_out,
               'source_equal': before == after, 'source_sha256': before['canonical_sources_sha256'],
               'ended_unix': time.time(), 'duration_seconds': time.time() - started,
               'log_sha256': digest(raw), 'log_bytes': len(raw), 'shell_executables': executables}
    write_json(attempt / 'receipt.json', receipt)
    print(json.dumps(receipt, sort_keys=True), flush=True)
    print(raw.decode(errors='replace')[-8000:], flush=True)
    return code if code and 0 < code < 256 else int(code != 0 or before != after)


if __name__ == '__main__':
    sys.exit(main())
