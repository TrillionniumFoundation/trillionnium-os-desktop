#!/usr/bin/python3
"""Execute one actual clean, distinct-source-path normalized kernel build/boot."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

base = Path('/workspace/scratch/ae1a8cf05419')
repo = base / 'trillionnium-os-desktop'
source, case = sys.argv[1:]
if case != 'N1':
    raise SystemExit('case must be N1')
worktree = Path('/tmp/trillionnium-a01-final-normal')
outer = base / 'normal-cloud-final'
outer.mkdir(exist_ok=True)
controller = outer / ('controller-' + case)
controller.mkdir(exist_ok=False)
prefix = base / 'native-tools/root'
env = os.environ.copy()
env.update({
    'CARGO_HOME': str(base / 'toolchains/cargo'),
    'RUSTUP_HOME': str(base / 'toolchains/rustup'),
    'RUSTUP_TOOLCHAIN': 'nightly-2026-07-21',
    'CARGO_BUILD_JOBS': '2', 'CARGO_NET_GIT_FETCH_WITH_CLI': 'true',
    'PATH': ':'.join(map(str, [base / 'toolchains/cargo/bin', prefix / 'usr/bin',
        prefix / 'usr/lib/llvm-18/bin'])) + ':' + env.get('PATH', '/usr/bin:/bin'),
    'LD_LIBRARY_PATH': ':'.join(map(str, [prefix / 'usr/lib/x86_64-linux-gnu',
        prefix / 'lib/x86_64-linux-gnu', prefix / 'usr/lib/llvm-18/lib'])),
    'QEMU_MODULE_DIR': str(prefix / 'usr/lib/x86_64-linux-gnu/qemu'),
    'A01_BUSYBOX': str(prefix / 'usr/bin/busybox'),
    'A01_QEMU_BIOS': str(prefix / 'usr/share/seabios/bios-256k.bin'),
    'A01_QEMU_DATA_DIR': str(prefix / 'usr/share/qemu'),
    'VDSO_LIBRARY_DIR': str(repo / 'support/build/out/linux-vdso'),
    'PKG_CONFIG_LIBDIR': ':'.join(map(str, [prefix / 'usr/lib/x86_64-linux-gnu/pkgconfig',
        prefix / 'usr/share/pkgconfig'])),
    'PKG_CONFIG_SYSROOT_DIR': str(prefix), 'A01_QEMU_TIMEOUT': '300',
})
for key in ('CARGO_INCREMENTAL', 'ASTER_BUILD_TIMESTAMP', 'SOURCE_DATE_EPOCH', 'OSDK_BUILD_USERNAME', 'OSDK_BUILD_HOSTNAME',
            'CARGO_ENCODED_RUSTFLAGS', 'CARGO_TARGET_DIR', 'RUSTFLAGS', 'RUSTC_WRAPPER',
            'RUSTC_WORKSPACE_WRAPPER', 'A01_KERNEL_WORKER', 'A01_REPRO_POLICY',
            'MAKEFLAGS', 'MFLAGS', 'GNUMAKEFLAGS', 'MAKEFILES', 'MAKEOVERRIDES', 'MAKELEVEL'):
    env.pop(key, None)
records = []

def run(name, argv, cwd, timeout=1800):
    log = controller / (name + '.log')
    row = {'name': name, 'argv': argv, 'cwd': str(cwd),
           'start': datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'selected_environment': {k: env[k] for k in env if
             k.startswith(('CARGO_', 'RUSTUP_', 'A01_', 'QEMU_', 'VDSO_', 'PKG_CONFIG_'))
             or k in ('PATH', 'LD_LIBRARY_PATH')}, 'log': str(log)}
    records.append(row)
    (controller / 'commands.json').write_text(json.dumps(records, indent=2) + '\n')
    print(json.dumps({'stage': 'start', 'case': case, 'name': name}), flush=True)
    with log.open('wb') as stream:
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=stream,
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
    (controller / 'commands.json').write_text(json.dumps(records, indent=2) + '\n')
    print(json.dumps({'stage': 'finish', 'case': case, 'name': name, 'returncode': code}), flush=True)
    if code:
        raise SystemExit(code if code > 0 else 1)

run('worktree', ['git', '-C', str(repo), 'worktree', 'add', '--detach', str(worktree), source], repo)
run('source-verification', ['python3', '-I', 'support/build/verify-source.py'], worktree)
env['CARGO_TARGET_DIR'] = str(worktree / 'kernel/asterinas/target')
run('target-absence', ['python3', '-I', '-c',
    "import os,json;from pathlib import Path;p=Path(os.environ['CARGO_TARGET_DIR']);assert not p.exists() and not p.is_symlink();print(json.dumps({'target':str(p),'absent_before_first_build':True}))"], worktree)
env['A01_RUN_DIR'] = str(outer / 'kernel-build')
run('fresh-make-kernel', ['bash', 'support/build/kernel.sh', 'kernel'], worktree)
artifact = worktree / 'kernel/asterinas/target/osdk/asterinas/asterinas-osdk-bin.elf'
freeze = """import hashlib,json,os,stat,sys
from pathlib import Path
source,destination=map(Path,sys.argv[1:])
fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW)
try:
 a=os.fstat(fd)
 if not stat.S_ISREG(a.st_mode):raise ValueError('nonregular produced kernel')
 keys=('st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns')
 identity=lambda x:{k:getattr(x,k) for k in keys}
 if identity(a)!=identity(source.stat()):raise ValueError('source changed before capture')
 digest=hashlib.sha256()
 with destination.open('xb') as out:
  while True:
   chunk=os.read(fd,1048576)
   if not chunk:break
   digest.update(chunk);out.write(chunk)
 if identity(a)!=identity(os.fstat(fd)) or identity(a)!=identity(source.stat()):raise ValueError('source changed during capture')
 destination.chmod(0o400)
 if hashlib.sha256(destination.read_bytes()).hexdigest()!=digest.hexdigest():raise ValueError('copy mismatch')
 print(json.dumps({'source':str(source),'source_stat':identity(a),'copy':str(destination),'size':a.st_size,'sha256':digest.hexdigest()},indent=2))
finally:os.close(fd)
"""
run('freeze-first-produced-kernel', ['python3', '-I', '-c', freeze, str(artifact),
    str(outer / 'first-build-kernel.elf')], worktree)
env['A01_RUN_DIR'] = str(outer / 'kernel-boot')
run('make-run-kernel', ['bash', 'support/build/kernel.sh', 'run_kernel'], worktree)
run('boot-live-recheck', ['python3', '-I', 'support/build/check-boot.py',
    str(outer / 'kernel-boot'), '--live-artifacts'], worktree)
run('post-source-verification', ['python3', '-I', 'support/build/verify-source.py'], worktree)
run('worktree-status', ['git', 'status', '--porcelain=v1'], worktree)
run('installed-components', ['rustup', 'component', 'list', '--installed'], worktree)
run('installed-targets', ['rustup', 'target', 'list', '--installed'], worktree)
print('actual standard make kernel / make run_kernel pipeline completed', flush=True)
