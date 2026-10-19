#!/usr/bin/env python3
"""Record one narrow existing-repository validation command and source identity."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

BASE = Path('/workspace/scratch/499c7902de8e')
SOURCE = BASE / 'r10-fleet-fixture-fix'
EVIDENCE = BASE / 'r10-evidence/fleet-fixture-fix'
TOOLS = BASE / 'r10-fleet-fixture-tools'
RUST = BASE / 'r10-cargo-deny-tools/rustup-home/toolchains/1.95.0-x86_64-unknown-linux-gnu'
TARGET = BASE / 'r10-fleet-fixture-target'
FILES = ['codex-rs/hepta-fleet/src/authority_port.rs', 'codex-rs/Cargo.lock',
         'codex-rs/Cargo.toml', 'codex-rs/deny.toml', 'codex-rs/clippy.toml', '.bazelrc']


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(['git', '-C', str(SOURCE), *args], text=True).strip()


def state():
    files = []
    for name in FILES:
        b = (SOURCE / name).read_bytes()
        files.append({'path': name, 'bytes': len(b), 'sha256': digest(b)})
    return {'commit': git('rev-parse', 'HEAD'), 'tree': git('rev-parse', 'HEAD^{tree}'),
            'status_porcelain': git('status', '--porcelain=v1', '--untracked-files=all'),
            'diff_sha256': digest(subprocess.check_output(['git', '-C', str(SOURCE), 'diff', 'HEAD'])),
            'files': files}


name, *argv = sys.argv[1:]
out = EVIDENCE / name
out.mkdir()
cache = TOOLS / 'cargo-home'
cache.mkdir(exist_ok=True)
for part in ['registry', 'git']:
    path = cache / part
    if not path.exists():
        path.symlink_to(BASE / 'r10-cargo-deny-tools/cargo-home' / part, target_is_directory=True)
env = os.environ.copy()
overrides = {'PATH': str(TOOLS / 'bin') + ':' + env.get('PATH', ''),
             'RUSTC': str(RUST / 'bin/rustc'), 'RUSTDOC': str(RUST / 'bin/rustdoc'),
             'CARGO_HOME': str(cache), 'CARGO_TARGET_DIR': str(TARGET),
             'CARGO_INCREMENTAL': '0', 'CARGO_BUILD_JOBS': '1',
             'CARGO_NET_OFFLINE': 'true', 'CARGO_TERM_COLOR': 'never',
             'NEXTEST_TEST_THREADS': '1'}
env.update(overrides)
before = state()
receipt = {'schema': 1, 'name': name, 'argv': argv, 'cwd': str(SOURCE / 'codex-rs'),
           'started_at': now(), 'environment_overrides': overrides, 'source_before': before,
           'cache_reuse': 'Previously fetched registry/git content is reused through the isolated Cargo home; all Cargo commands are offline and use an independent target.',
           'scope': 'codex-hepta-fleet only, except just fmt limits itself to the exact changed source diff'}
with (out / 'command.log').open('wb') as log:
    process = subprocess.run(argv, cwd=SOURCE / 'codex-rs', env=env, stdout=log, stderr=subprocess.STDOUT)
receipt['exit_code'] = process.returncode
receipt['completed_at'] = now()
receipt['source_after'] = state()
receipt['source_unchanged'] = before == receipt['source_after']
data = (out / 'command.log').read_bytes()
receipt['log'] = {'path': 'command.log', 'bytes': len(data), 'sha256': digest(data)}
(out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps({'name': name, 'exit_code': process.returncode, 'started_at': receipt['started_at'],
                  'completed_at': receipt['completed_at'], 'source_unchanged': receipt['source_unchanged'],
                  'receipt': str(out / 'receipt.json'), 'tail': data.decode(errors='replace').splitlines()[-12:]}, indent=2))
raise SystemExit(process.returncode)
