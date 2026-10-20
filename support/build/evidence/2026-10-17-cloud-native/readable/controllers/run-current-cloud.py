#!/usr/bin/python3
"""Retain actual commands/results for the new private-tool full-kernel run."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

base = Path('/workspace/scratch/ae1a8cf05419')
repository = base / 'trillionnium-os-desktop'
worktree = base / 'a01-current-build'
output = base / 'current-cloud'
output.mkdir(exist_ok=False)
source = sys.argv[1]
prefix = base / 'native-tools/root'
env = os.environ.copy()
env.update({
    'CARGO_HOME': str(base / 'toolchains/cargo'),
    'RUSTUP_HOME': str(base / 'toolchains/rustup'),
    'RUSTUP_TOOLCHAIN': 'nightly-2026-07-21',
    'CARGO_BUILD_JOBS': '2',
    'CARGO_NET_GIT_FETCH_WITH_CLI': 'true',
    'PATH': ':'.join(map(str, [base / 'toolchains/cargo/bin', prefix / 'usr/bin',
        prefix / 'usr/lib/llvm-18/bin'])) + ':' + env.get('PATH', '/usr/bin:/bin'),
    'LD_LIBRARY_PATH': ':'.join(map(str, [prefix / 'usr/lib/x86_64-linux-gnu',
        prefix / 'lib/x86_64-linux-gnu', prefix / 'usr/lib/llvm-18/lib'])),
    'QEMU_MODULE_DIR': str(prefix / 'usr/lib/x86_64-linux-gnu/qemu'),
    'A01_BUSYBOX': str(prefix / 'usr/bin/busybox'),
    'A01_QEMU_BIOS': str(prefix / 'usr/share/seabios/bios-256k.bin'),
    'VDSO_LIBRARY_DIR': str(repository / 'support/build/out/linux-vdso'),
    'CARGO_TARGET_DIR': str(worktree / 'kernel/asterinas/target'),
    'PKG_CONFIG_LIBDIR': ':'.join(map(str, [prefix / 'usr/lib/x86_64-linux-gnu/pkgconfig',
        prefix / 'usr/share/pkgconfig'])),
    'PKG_CONFIG_SYSROOT_DIR': str(prefix),
    'A01_QEMU_TIMEOUT': '300',
})
for key in ('CARGO_ENCODED_RUSTFLAGS', 'RUSTFLAGS', 'RUSTC_WRAPPER', 'A01_KERNEL_WORKER',
            'MAKEFLAGS', 'MFLAGS', 'GNUMAKEFLAGS', 'MAKEFILES', 'MAKEOVERRIDES', 'MAKELEVEL'):
    env.pop(key, None)
records = []

def run(name, argv, cwd, extra=None, timeout=1800):
    effective = dict(env)
    if extra:
        effective.update(extra)
    log = output / (name + '.log')
    row = {'name': name, 'argv': argv, 'cwd': str(cwd),
           'start': datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'selected_environment': {k: effective[k] for k in env if
             k.startswith(('CARGO_', 'RUSTUP_', 'A01_', 'QEMU_', 'VDSO_', 'PKG_CONFIG_'))
             or k in ('PATH', 'LD_LIBRARY_PATH')}, 'log': str(log)}
    records.append(row)
    (output / 'commands.json').write_text(json.dumps(records, indent=2) + '\n')
    print(json.dumps({'stage': 'start', 'name': name}), flush=True)
    with log.open('wb') as stream:
        process = subprocess.Popen(argv, cwd=cwd, env=effective, stdout=stream,
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
    row.update(returncode=code, end=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        log_sha256=hashlib.sha256(log.read_bytes()).hexdigest(), log_size=log.stat().st_size)
    (output / 'commands.json').write_text(json.dumps(records, indent=2) + '\n')
    print(json.dumps({'stage': 'finish', 'name': name, 'returncode': code}), flush=True)
    if code:
        raise SystemExit(code if code > 0 else 1)

run('worktree', ['git', '-C', str(repository), 'worktree', 'add', '--detach', str(worktree), source], repository)
run('source-verification', ['python3', '-I', 'support/build/verify-source.py'], worktree)
run('full-kernel-build', ['support/build/kernel.sh', 'kernel'], worktree,
    {'A01_RUN_DIR': str(output / 'build')})
run('full-kernel-boot', ['support/build/kernel.sh', 'run_kernel'], worktree,
    {'A01_RUN_DIR': str(output / 'boot')})
run('boot-live-recheck', ['python3', '-I', 'support/build/check-boot.py', str(output / 'boot'), '--live-artifacts'], worktree)
run('post-source-verification', ['python3', '-I', 'support/build/verify-source.py'], worktree)
run('worktree-status', ['git', 'status', '--porcelain=v1'], worktree)
print('actual clean full-kernel build and boot completed', flush=True)
