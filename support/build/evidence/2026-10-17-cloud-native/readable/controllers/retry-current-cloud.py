#!/usr/bin/python3
"""Retry the retained clean-build kernel with published private QEMU data support."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess

base = Path('/workspace/scratch/ae1a8cf05419')
output = base / 'current-cloud'
worktree = base / 'a01-current-build'
previous = json.loads((output / 'commands.json').read_text())
selected = next(row['selected_environment'] for row in previous if row['name'] == 'full-kernel-build')
env = os.environ.copy()
env.update(selected)
env['A01_QEMU_DATA_DIR'] = str(base / 'native-tools/root/usr/share/qemu')
env['A01_RUN_DIR'] = str(output / 'boot-data-retry')
for key in ('CARGO_ENCODED_RUSTFLAGS', 'RUSTFLAGS', 'RUSTC_WRAPPER', 'A01_KERNEL_WORKER',
            'MAKEFLAGS', 'MFLAGS', 'GNUMAKEFLAGS', 'MAKEFILES', 'MAKEOVERRIDES', 'MAKELEVEL'):
    env.pop(key, None)
records = []

def run(name, argv, timeout=900):
    log = output / ('retry-' + name + '.log')
    row = {'name': name, 'argv': argv, 'cwd': str(worktree), 'selected_environment': selected,
        'overrides': {'A01_QEMU_DATA_DIR': env['A01_QEMU_DATA_DIR'], 'A01_RUN_DIR': env['A01_RUN_DIR']},
        'started': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'log': str(log)}
    records.append(row)
    (output / 'retry-commands.json').write_text(json.dumps(records, indent=2) + '\n')
    with log.open('xb') as stream:
        process = subprocess.Popen(argv, cwd=worktree, env=env, stdout=stream,
            stderr=subprocess.STDOUT, start_new_session=True)
        row['pid'] = process.pid
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            row['controller_timed_out'] = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                code = process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                code = process.wait()
    row.update(returncode=code, ended=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        log_sha256=hashlib.sha256(log.read_bytes()).hexdigest(), log_size=log.stat().st_size)
    (output / 'retry-commands.json').write_text(json.dumps(records, indent=2) + '\n')
    print(json.dumps({'name': name, 'returncode': code}), flush=True)
    if code:
        raise SystemExit(code if code > 0 else 1)

run('initial-status', ['git', 'status', '--porcelain=v1'])
run('kernel-tree-binding', ['git', 'diff', '--exit-code', '0053c98e787391ef566305296ffd2b7c912a1095',
    '31543f71a247add15ce8e026a25385c535746bca', '--', 'kernel/asterinas'])
run('checkout', ['git', 'checkout', '--detach', '31543f71a247add15ce8e026a25385c535746bca'])
run('source-verification', ['python3', '-I', 'support/build/verify-source.py'])
run('boot', ['support/build/kernel.sh', 'run_kernel'])
run('live-recheck', ['python3', '-I', 'support/build/check-boot.py', str(output / 'boot-data-retry'), '--live-artifacts'])
run('post-status', ['git', 'status', '--porcelain=v1'])
run('installed-components', ['rustup', 'component', 'list', '--installed'])
run('installed-targets', ['rustup', 'target', 'list', '--installed'])
