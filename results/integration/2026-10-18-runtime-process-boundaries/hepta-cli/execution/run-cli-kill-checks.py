#!/usr/bin/env python3
"""Source-bound R8 CLI subprocess checks; no original owner or kernel launch."""
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

BASE = Path('/workspace/scratch/98f315e377b2/recovery-r7')
REPO = BASE / 'repo'
TOOLCHAIN = BASE / 'rust-1.88/bin'
TARGET = Path('/dev/shm/trill-r9-target-hepta')
CACHE = Path('/dev/shm/trill-r9-cargo')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def snapshot():
    def git(*args):
        return subprocess.check_output(['git', '-C', str(REPO), *args])
    paths = [p.decode() for p in git('ls-files', '-z', '--', 'services/hepta-os').split(b'\0') if p]
    rows = []
    for rel in paths:
        content = (REPO / rel).read_bytes()
        rows.append({'path': rel, 'bytes': len(content), 'sha256': sha(content),
                     'git_blob_of_actual_bytes': hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()})
    return {'head': git('rev-parse', 'HEAD').decode().strip(),
            'base_tree': git('rev-parse', 'HEAD^{tree}').decode().strip(),
            'files': rows,
            'crate_patch_sha256': sha(git('diff', '--binary', '--', 'services/hepta-os'))}


def exec_child():
    expected = int(sys.argv[2])
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'PR_SET_PDEATHSIG')
    if os.getppid() != expected:
        os.kill(os.getpid(), signal.SIGKILL)
    os.execvpe(sys.argv[3], sys.argv[3:], os.environ)


def main():
    os.umask(0o077)
    directory = BASE / 'validation' / 'hepta-cli-kill-01'
    directory.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(REPO / 'tests/integration/hepta'))
    import run_original_agentd as guard
    if not guard.child_anchor_available():
        raise RuntimeError('sole waitable child owner unavailable')
    environment = {key: os.environ[key] for key in (
        'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'SSL_CERT_FILE', 'SSL_CERT_DIR',
    ) if key in os.environ}
    environment.update({
        'PATH': f'{TOOLCHAIN}:/usr/bin:/bin', 'CARGO_HOME': str(CACHE),
        'CARGO_TARGET_DIR': str(TARGET), 'CARGO_INCREMENTAL': '0',
        'CARGO_BUILD_JOBS': '1', 'CARGO_PROFILE_DEV_DEBUG': '0',
        'CARGO_PROFILE_TEST_DEBUG': '0', 'LANG': 'C.UTF-8',
        'RUSTC': str(TOOLCHAIN / 'rustc'), 'RUSTDOC': str(TOOLCHAIN / 'rustdoc'),
    })
    cargo = str(TOOLCHAIN / 'cargo')
    manifest = ['--manifest-path', 'services/hepta-os/Cargo.toml']
    steps = [
        ('fetch', [cargo, 'fetch', *manifest, '--locked'], 600),
        ('focused-kill', [cargo, 'test', *manifest, '--locked', '--offline', '--features', 'objective-transport', '--test', 'objective_cli', 'killed_', '--', '--nocapture'], 300),
        ('full-feature-suite', [cargo, 'test', *manifest, '--locked', '--offline', '--features', 'objective-transport'], 300),
        ('feature-off-check', [cargo, 'check', *manifest, '--locked', '--offline', '--no-default-features', '--all-targets'], 300),
        ('strict-clippy', [cargo, 'clippy', *manifest, '--locked', '--offline', '--features', 'objective-transport', '--all-targets', '--', '-D', 'warnings'], 300),
        ('fmt-check', [cargo, 'fmt', *manifest, '--all', '--', '--check'], 120),
    ]
    before = snapshot()
    write_json(directory / 'source-before.json', before)
    (directory / 'source.patch').write_bytes(subprocess.check_output([
        'git', '-C', str(REPO), 'diff', '--binary', '--', 'services/hepta-os']))
    shutil.copyfile(__file__, directory / 'run-cli-kill-checks.py')
    shutil.copyfile(guard.__file__, directory / 'owned-process-guard.py')
    source = directory / 'source'
    for row in before['files']:
        dst = source / row['path']
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / row['path'], dst)
    versions = {
        name: subprocess.check_output([str(TOOLCHAIN / name), *args], env=environment).decode()
        for name, args in [('cargo', ['--version']), ('rustc', ['--version', '--verbose'])]
    }
    write_json(directory / 'toolchain.json', versions)
    receipt = {'schema': 'r8-cli-kill-execution-v1', 'started_at': now(),
               'source': before, 'profile': {key: environment[key] for key in environment if key not in ('HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY')},
               'target_free_before': shutil.disk_usage(TARGET.parent).free,
               'kernel_or_original_owner_run': False, 'steps': [], 'status': 'running'}
    write_json(directory / 'execution-plan.json', {
        'created_at': now(), 'steps': [{'name': n, 'argv': a, 'timeout_seconds': t} for n, a, t in steps],
        'source_before_sha256': sha((directory / 'source-before.json').read_bytes()),
        'profile': receipt['profile'], 'guard_sha256': sha(Path(guard.__file__).read_bytes()),
        'helper_sha256': sha(Path(__file__).read_bytes()),
        'scope': 'Scripted private UDS fixtures and actual owned hepta-submit subprocesses; no production ledger, original daemon, UI or kernel guest.',
    })
    write_json(directory / 'receipt.json', receipt)
    try:
        for name, argv, deadline_seconds in steps:
            if shutil.disk_usage(TARGET.parent).free < 128 * 1024**2:
                raise RuntimeError('private target memory-filesystem free space below 128 MiB')
            entry = {'name': name, 'argv': argv, 'started_at': now(), 'status': 'running'}
            receipt['steps'].append(entry)
            write_json(directory / 'receipt.json', receipt)
            print(json.dumps({'step': name, 'status': 'started', 'time': now()}), flush=True)
            command = [sys.executable, str(Path(__file__).resolve()), '--exec-child', str(os.getpid()), *argv]
            group = None
            try:
                with (directory / f'{name}.log').open('xb') as log:
                    child = subprocess.Popen(command, cwd=REPO, env=environment, stdin=subprocess.DEVNULL,
                                             stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                    group = guard.ChildGroup(child)
                    deadline = time.monotonic() + deadline_seconds
                    while True:
                        status = group.observe_exit()
                        if status is not None:
                            break
                        if time.monotonic() >= deadline:
                            raise RuntimeError('command deadline elapsed')
                        if shutil.disk_usage(TARGET.parent).free < 128 * 1024**2:
                            raise RuntimeError('private target memory-filesystem free space below 128 MiB')
                        time.sleep(0.05)
                    code = group.reap() if status.si_code == os.CLD_EXITED and status.si_status == 0 else guard.terminate_group(group)
                    entry.update({'exit_code': code, 'guard_disarmed': not group.armed})
                    if code != 0:
                        raise RuntimeError(f'actual command exit {code}')
                entry['status'] = 'passed'
            finally:
                if group is not None and group.armed:
                    entry['cleanup_exit_code'] = guard.terminate_group(group)
                    entry['guard_disarmed'] = not group.armed
                entry['finished_at'] = now()
                log_path = directory / f'{name}.log'
                if log_path.exists():
                    entry.update({'log': log_path.name, 'log_bytes': log_path.stat().st_size,
                                  'log_sha256': sha(log_path.read_bytes())})
                write_json(directory / 'receipt.json', receipt)
            print(json.dumps({'step': name, 'status': entry['status'], 'time': now()}), flush=True)
        receipt['status'] = 'passed'
    except BaseException as error:
        receipt['status'] = 'failed'
        receipt['error'] = str(error)
        if receipt['steps'] and receipt['steps'][-1]['status'] == 'running':
            receipt['steps'][-1]['status'] = 'failed'
        raise
    finally:
        after = snapshot()
        write_json(directory / 'source-after.json', after)
        receipt['source_unchanged'] = after == before
        if after != before:
            receipt['status'] = 'failed'
            receipt['source_failure'] = 'crate input or base identity changed during execution'
        binaries = []
        candidates = list((TARGET / 'debug/deps').glob('objective_cli-*')) + [TARGET / 'debug/hepta-submit']
        for path in candidates:
            if not path.is_file():
                continue
            with path.open('rb') as stream:
                if stream.read(4) != b'\x7fELF':
                    continue
            binaries.append({'path': str(path), 'bytes': path.stat().st_size,
                             'sha256': sha(path.read_bytes())})
        write_json(directory / 'executables.json', binaries)
        receipt.update({'finished_at': now(), 'target_free_after': shutil.disk_usage(TARGET.parent).free})
        write_json(directory / 'receipt.json', receipt)
        print(json.dumps({'status': receipt['status'], 'receipt': str(directory / 'receipt.json')}), flush=True)
    return 0 if receipt['status'] == 'passed' else 1


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--exec-child':
        exec_child()
    else:
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        raise SystemExit(main())
