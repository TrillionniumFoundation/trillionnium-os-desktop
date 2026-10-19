#!/usr/bin/env python3
"""Record actual Rust integration checks for the main193 + Runtime tree."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent / 'r9-main-sync-20261019'
RUST = ROOT.parent / 'rust-1.88/bin'
CARGO = str(RUST / 'cargo')


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO).decode().rstrip('\n')


def write(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n')


def snapshot():
    names = git('ls-files', '-z', '--', 'ui', 'services/hepta-os', 'libs/os-abi').split('\0')
    files = {}
    for name in sorted(filter(None, names)):
        path = REPO / name
        if not path.is_file() or path.is_symlink():
            raise RuntimeError('missing or non-regular product input: ' + name)
        data = path.read_bytes()
        files[name] = {'bytes': len(data), 'mode': oct(path.stat().st_mode & 0o777),
                       'sha256': hashlib.sha256(data).hexdigest()}
    canonical = json.dumps(files, sort_keys=True, separators=(',', ':')).encode()
    return {'head': git('rev-parse', 'HEAD'), 'merge_head': git('rev-parse', 'MERGE_HEAD'),
            'files': files, 'canonical_files_sha256': hashlib.sha256(canonical).hexdigest()}


def main():
    out = ROOT / 'rust-01'
    out.mkdir(exist_ok=False)
    before = snapshot()
    write(out / 'source-before.json', before)
    source_names = list(before['files'])
    patch = subprocess.check_output(['git', 'diff', '--binary', 'HEAD', '--', *source_names], cwd=REPO)
    (out / 'source.patch').write_bytes(patch)
    env = os.environ.copy()
    env.update({'PATH': str(RUST) + os.pathsep + env.get('PATH', ''),
                'RUSTC': str(RUST / 'rustc'), 'CARGO_HOME': '/dev/shm/trill-r9-cargo',
                'CARGO_INCREMENTAL': '0', 'CARGO_BUILD_JOBS': '2',
                'CARGO_PROFILE_DEV_DEBUG': '0', 'CARGO_PROFILE_TEST_DEBUG': '0',
                'LC_ALL': 'C.UTF-8', 'TZ': 'UTC'})
    env.pop('RUSTUP_TOOLCHAIN', None)
    commands = [
        ('ui-tests', 'ui', [CARGO, 'test', '--manifest-path', 'ui/Cargo.toml', '--workspace', '--locked', '--offline']),
        ('hepta-all-features-tests', 'hepta', [CARGO, 'test', '--manifest-path', 'services/hepta-os/Cargo.toml', '--all-features', '--locked', '--offline']),
        ('hepta-default-check', 'hepta', [CARGO, 'check', '--manifest-path', 'services/hepta-os/Cargo.toml', '--no-default-features', '--all-targets', '--locked', '--offline']),
        ('ui-clippy', 'ui', [CARGO, 'clippy', '--manifest-path', 'ui/Cargo.toml', '--workspace', '--all-targets', '--locked', '--offline', '--', '-D', 'warnings']),
        ('hepta-all-features-clippy', 'hepta', [CARGO, 'clippy', '--manifest-path', 'services/hepta-os/Cargo.toml', '--all-features', '--all-targets', '--locked', '--offline', '--', '-D', 'warnings']),
        ('ui-fmt', 'ui', [CARGO, 'fmt', '--manifest-path', 'ui/Cargo.toml', '--all', '--', '--check']),
        ('hepta-fmt', 'hepta', [CARGO, 'fmt', '--manifest-path', 'services/hepta-os/Cargo.toml', '--', '--check']),
        ('ui-bins', 'ui', [CARGO, 'build', '--manifest-path', 'ui/Cargo.toml', '--workspace', '--bins', '--locked', '--offline']),
        ('hepta-all-features-bins', 'hepta', [CARGO, 'build', '--manifest-path', 'services/hepta-os/Cargo.toml', '--bins', '--all-features', '--locked', '--offline']),
    ]
    versions = {}
    for label, argv in [('rustc', [str(RUST / 'rustc'), '-Vv']), ('cargo', [CARGO, '-Vv'])]:
        result = subprocess.run(argv, cwd=REPO, env=env, capture_output=True, check=True)
        (out / (label + '-version.stdout.log')).write_bytes(result.stdout)
        (out / (label + '-version.stderr.log')).write_bytes(result.stderr)
        versions[label] = result.stdout.decode()
    receipt = {'schema': 1, 'started_at_utc': stamp(), 'source_before_sha256': before['canonical_files_sha256'],
               'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'source_patch_sha256': hashlib.sha256(patch).hexdigest(), 'versions': versions,
               'environment': {k: env.get(k) for k in ['PATH', 'RUSTC', 'CARGO_HOME', 'CARGO_INCREMENTAL', 'CARGO_BUILD_JOBS', 'CARGO_PROFILE_DEV_DEBUG', 'CARGO_PROFILE_TEST_DEBUG', 'RUSTFLAGS', 'LC_ALL', 'TZ']},
               'commands': [], 'scope': 'Current Rust product and CLI integration on Linux host; no original Agentd, compositor or device execution'}
    write(out / 'receipt.json', receipt)
    for index, (name, target, argv) in enumerate(commands, 1):
        env['CARGO_TARGET_DIR'] = '/dev/shm/trill-r9-target-' + target
        before_command = snapshot()
        stem = f'{index:02d}-{name}'
        item = {'name': name, 'command': argv, 'cwd': str(REPO), 'target_dir': env['CARGO_TARGET_DIR'],
                'started_at_utc': stamp(), 'source_before_sha256': before_command['canonical_files_sha256']}
        print('START', name, flush=True)
        with (out / (stem + '.stdout.log')).open('wb') as stdout, (out / (stem + '.stderr.log')).open('wb') as stderr:
            child = subprocess.Popen(argv, cwd=REPO, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
            item['owned_leader_pid'] = child.pid
            try:
                code = child.wait(timeout=900)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
                code = 124
                item['timeout'] = True
        after_command = snapshot()
        item.update({'exit_code': code, 'completed_at_utc': stamp(),
                     'source_after_sha256': after_command['canonical_files_sha256'],
                     'source_equal': before_command == after_command,
                     'stdout': stem + '.stdout.log', 'stderr': stem + '.stderr.log'})
        receipt['commands'].append(item)
        write(out / 'receipt.json', receipt)
        print('DONE', name, code, 'source_equal', item['source_equal'], flush=True)
    after = snapshot()
    write(out / 'source-after.json', after)
    receipt['source_equal'] = before == after
    receipt['source_after_sha256'] = after['canonical_files_sha256']
    receipt['completed_at_utc'] = stamp()
    receipt['status'] = 'passed' if receipt['source_equal'] and all(x['exit_code'] == 0 and x['source_equal'] for x in receipt['commands']) else 'failed'
    receipt['binaries'] = {}
    binaries = {
        'trill-shell': ('ui', 'trill-shell'), 'trill-session': ('ui', 'trill-session'),
        'trill-ctl': ('ui', 'trill-ctl'), 'trill-app-window': ('ui', 'trill-app-window'),
        'hepta-observe': ('hepta', 'hepta-observe'), 'hepta-submit': ('hepta', 'hepta-submit'),
        'hepta-history': ('hepta', 'hepta-history')}
    for label, (target, name) in binaries.items():
        path = Path('/dev/shm/trill-r9-target-' + target) / 'debug' / name
        if path.is_file():
            data = path.read_bytes()
            receipt['binaries'][label] = {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                                          'elf64_little_endian_x86_64': len(data) >= 64 and data[:7] == b'\x7fELF\x02\x01\x01' and int.from_bytes(data[18:20], 'little') == 62}
    write(out / 'receipt.json', receipt)
    print(json.dumps({'status': receipt['status'], 'source_closure': receipt['source_after_sha256'], 'commands': len(receipt['commands'])}), flush=True)
    return 0 if receipt['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
