#!/usr/bin/env python3
"""Prepare, and only on a later explicit --launch, cancel a real paused ktest VM.

Native QEMU executes the production ELF/serial argv with only test-added -S.
This never represents Rust-entry, test execution, or a complete boot pass.
"""
import argparse
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import socket
import stat
import subprocess
import sys
import time

MANIFEST_HASH = '1ff39174c39411f8b9a7fd328f762268e62d88521b43ebbde384d03d7d9a9f9f'
REAL_QEMU = Path('/usr/bin/qemu-system-x86_64')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def record(path):
    path = Path(path)
    with path.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    info = path.stat()
    return {'path': str(path), 'size': info.st_size, 'sha256': digest}


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def exited(descriptor, timeout=0):
    return bool(select.select([descriptor], [], [], timeout)[0])


def wait_json(path, owner, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            require(owner.poll() is None, f'ktest CLI exited {owner.returncode} before {path}')
            time.sleep(.05)
    raise TimeoutError(str(path))


def make_qemu_shim(path, root):
    source = '''#!/usr/bin/env python3
import hashlib,json,os,sys,time
from pathlib import Path
root=Path(ROOT_VALUE)
real=Path(REAL_VALUE)
args=sys.argv[1:]
if args==['--version']:
 os.execv(str(real),[str(real),*args])
if args.count('-kernel')!=1 or '-S' in args:
 raise SystemExit('expected one real ktest kernel and no preexisting -S')
index=args.index('-kernel')+1
kernel=Path(args[index]).resolve()
actual=[str(real),*args,'-S']
receipt={'kind':'test_only_native_qemu_minus_S_hold','pid':os.getpid(),'group':os.getpgrp(),'requested_argv':sys.argv,'actual_argv':actual,'real_qemu':str(real),'real_qemu_sha256':hashlib.sha256(real.read_bytes()).hexdigest(),'kernel':{'path':str(kernel),'size':kernel.stat().st_size,'sha256':hashlib.sha256(kernel.read_bytes()).hexdigest()},'adaptation':'only append -S; no source, ELF, serial, device or machine change','rust_entry_or_boot_pass':False,'time_ns':time.time_ns()}
for number in range(1,100):
 destination=root/('qemu-launch-%03d.json'%number)
 try:
  with destination.open('x') as output:json.dump(receipt,output,indent=2)
  break
 except FileExistsError:continue
else:raise SystemExit('launch receipt allocation exhausted')
os.execv(str(real),actual)
'''.replace('ROOT_VALUE', repr(str(root))).replace('REAL_VALUE', repr(str(REAL_QEMU)))
    path.write_text(source)
    path.chmod(0o755)
    compile(source, str(path), 'exec')


def launch_under_stable_lock(work, command, env, console, preserved):
    manifest = work / 'kernel/asterinas/kernel/OSDK.toml'
    lock = work / 'support/build/out-kernel.lock'
    preserved.parent.mkdir(parents=True, exist_ok=True)
    require(not os.path.lexists(preserved), 'preservation path is not new')
    with lock.open('a') as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        info = os.fstat(held.fileno())
        receipt = {'lock_path': str(lock), 'device': info.st_dev, 'inode': info.st_ino,
                   'manifest_present': os.path.lexists(manifest), 'writer_cause': 'unknown'}
        if os.path.lexists(manifest):
            fd = os.open(manifest, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as source:
                before = os.fstat(source.fileno())
                require(stat.S_ISREG(before.st_mode), 'manifest is not a regular file')
                digest = hashlib.file_digest(source, 'sha256').hexdigest()
                require(digest == MANIFEST_HASH, 'manifest differs from fixed minimal profile; preserved in place')
                current = manifest.lstat()
                require((current.st_dev, current.st_ino) == (before.st_dev, before.st_ino), 'manifest changed before rename')
                os.rename(manifest, preserved)
                after = preserved.stat()
                require((after.st_dev, after.st_ino) == (before.st_dev, before.st_ino), 'manifest changed during rename')
                require(record(preserved)['sha256'] == MANIFEST_HASH, 'preserved bytes changed')
                receipt['preserved'] = record(preserved)
    # The ktest CLI takes this flock immediately. Release our preservation
    # lease before Popen so it cannot fail its own nonblocking acquisition.
    # Root serializes kernel activity; the child still enforces the same lock.
    owner = subprocess.Popen(command, cwd=work, env=env, stdout=console, stderr=subprocess.STDOUT)
    receipt['cli_pid'] = owner.pid
    receipt['preservation_lock_released_before_cli_launch'] = True
    return owner, receipt


def cleanup_receipts(value, path='$'):
    found = []
    if isinstance(value, dict):
        if 'leader_reaped' in value or 'reaped' in value:
            reaped = value.get('leader_reaped', value.get('reaped'))
            found.append({'path': path, 'reaped': reaped,
                          'external_reap': value.get('external_reap_disarmed', value.get('external_reap', False)),
                          'record': value})
        for key, child in value.items():
            found.extend(cleanup_receipts(child, path + '/' + key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(cleanup_receipts(child, path + '/' + str(index)))
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launch', action='store_true', help='use only after root explicitly authorizes this actual VM')
    parser.add_argument('--worktree', type=Path, default=Path('/workspace/scratch/ae1a8cf05419/a01-next6-build'))
    parser.add_argument('--output', type=Path, default=Path('/workspace/scratch/ae1a8cf05419/next7-real-ktest-cancel-controller-01'))
    parser.add_argument('--expected-tree', help='exact final published source tree, required for launch')
    parser.add_argument('--published-commit', help='exact final published source SHA, required for launch')
    parser.add_argument('--ready-timeout', type=float, default=900)
    args = parser.parse_args()
    if not args.launch:
        free = os.statvfs('/workspace/scratch/ae1a8cf05419')
        print(json.dumps({'prepared_only': True, 'Cargo_invoked': False, 'QEMU_invoked': False,
                          'worktree_created_or_changed': False, 'planned_worktree': str(args.worktree),
                          'planned_cli': 'python3 -I support/build/ktest/run.py --crate ostd --skip-osdk-install --output NEW_DIR',
                          'test_adapter': 'PATH qemu shim delegates --version and execs real QEMU with only -S appended',
                          'disk_free_bytes_now': free.f_bavail * free.f_frsize,
                          'authorization': 'root launch approval and final published source/tree still required'}, indent=2))
        return 0
    require(args.expected_tree and args.published_commit, 'launch requires final source/tree identity')
    work = args.worktree.resolve()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    out = work / 'support/build/out/next7-real-ktest-cancel-01'
    require(not out.exists(), 'production ktest output must be new')
    git = lambda *arguments: subprocess.check_output(['git', '-C', str(work), *arguments], text=True).strip()
    require(git('rev-parse', 'HEAD^{tree}') == args.expected_tree, 'runtime tree differs from approved published tree')
    tools = root / 'tools'
    tools.mkdir()
    shim = tools / 'qemu-system-x86_64'
    make_qemu_shim(shim, root)
    base = json.loads(Path('/workspace/scratch/ae1a8cf05419/next6-clean-debug-invocation.json').read_text())['environment']
    env = os.environ.copy()
    env.update(base)
    env['CARGO_TARGET_DIR'] = str(work / 'kernel/asterinas/target')
    env['PATH'] = str(tools) + os.pathsep + '/workspace/scratch/ae1a8cf05419/toolchains/cargo/bin:/workspace/scratch/ae1a8cf05419/a01-host-tools-next-e5ae/root/usr/bin:' + env.get('PATH', '')
    command = [sys.executable, '-I', str(work / 'support/build/ktest/run.py'), '--crate', 'ostd',
               '--skip-osdk-install', '--output', str(out)]
    sources = ['support/build/ktest/run.py', 'support/build/ktest/record-qemu.py', 'support/build/ktest/check.py',
               'support/build/ktest/locks/ostd.Cargo.lock', 'support/build/verify-source.py']
    invocation = {'argv': command, 'cwd': str(work), 'git_head': git('rev-parse', 'HEAD'),
                  'git_tree': args.expected_tree, 'git_status': git('status', '--short'),
                  'published_equivalent_commit': args.published_commit,
                  'selected_environment': {key: env.get(key) for key in [*base, 'PATH']},
                  'complete_environment_saved': False, 'source': {p: record(work / p) for p in sources},
                  'shim': record(shim), 'controller': record(Path(__file__)), 'real_qemu': record(REAL_QEMU),
                  'cache_reuse': 'root full two-crate run target reused explicitly; no fresh compile claim'}
    write(root / 'invocation.json', invocation)
    owner, descriptors = None, {}
    result = {'kind': 'actual_ktest_cli_cancellation_with_native_qemu_paused_before_execution',
              'passed': False, 'boot_pass': False, 'rust_entry_verified': False, 'guest_tests_executed': False}
    started = time.monotonic()
    try:
        with (root / 'console.log').open('wb') as console:
            owner, preservation = launch_under_stable_lock(work, command, env, console,
                work / 'support/build/out/next7-manifest-preserved/pre-ktest-cancel-01.toml')
            write(root / 'manifest-preservation.json', preservation)
            descriptors['ktest_cli'] = os.pidfd_open(owner.pid)
            launch = wait_json(root / 'qemu-launch-001.json', owner, args.ready_timeout)
            descriptors['native_qemu'] = os.pidfd_open(launch['pid'])
            guest_path = out / 'ostd/guests/guest-001/qemu.json'
            guest = wait_json(guest_path, owner, 3)
            require(guest['raw_exit_code'] is None and guest['timed_out'] is False, 'native guest already ended')
            require(guest['qemu_sha256'] == invocation['shim']['sha256'], 'recorder did not identify the test adapter')
            require(launch['real_qemu_sha256'] == invocation['real_qemu']['sha256'], 'adapter did not select expected native binary')
            require(launch['kernel']['sha256'] == guest['artifacts']['-kernel']['sha256'], 'native and production ELF identities disagree')
            time.sleep(.2)  # An exec/configuration failure must not count as a live paused VM.
            before = {name: not exited(fd) for name, fd in descriptors.items()}
            require(all(before.values()), 'CLI/native QEMU was not alive before cancellation')
            lock = work / 'support/build/out-kernel.lock'
            with lock.open('a') as held:
                try:
                    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    raise RuntimeError('ktest CLI did not hold the shared workspace lock')
                except BlockingIOError:
                    pass
            kernel = Path(launch['kernel']['path']).read_bytes()
            require(hashlib.sha256(kernel).hexdigest() == launch['kernel']['sha256'], 'live launch ELF changed')
            (root / 'kernel.elf.gz').write_bytes(gzip.compress(kernel, mtime=0))
            result.update(native_launch=launch, production_start_record=guest, before_signal_alive=before)
            signal.pidfd_send_signal(descriptors['ktest_cli'], signal.SIGTERM)
            owner.wait(timeout=15)
        ended = {name: exited(fd, 3) for name, fd in descriptors.items()}
        require(owner.returncode == 143, 'ktest CLI must report cancellation143')
        require(all(ended.values()), 'owned native QEMU survived CLI cancellation')
        with (work / 'support/build/out-kernel.lock').open('a') as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            info = os.fstat(held.fileno())
            require((info.st_dev, info.st_ino) == (preservation['device'], preservation['inode']), 'lock inode changed')
        final = json.loads((out / 'result.json').read_text())
        require(final.get('passed') is False and final.get('interrupted_by') == 'SIGTERM'
                and final.get('exit_code') == 143, 'final result falsely accepts cancellation or loses signal')
        require(final.get('runner_sha256') == invocation['source']['support/build/ktest/run.py']['sha256'],
                'aggregate result does not identify the frozen runner source')
        command_path = out / 'ostd/osdk-test.log.command.json'
        cancelled_command = json.loads(command_path.read_text())
        require(cancelled_command.get('exit_code') == 143
                and cancelled_command.get('interrupted_by') == 'SIGTERM', 'cancelled Cargo command lost effective status143')
        command_group = cancelled_command.get('group_cleanup', {})
        require(command_group.get('leader_reaped') is True
                and command_group.get('external_reap_disarmed') is False, 'Cargo leader cleanup receipt missing or disarmed')
        require(cancelled_command.get('raw_exit_code') == command_group.get('leader_exit_code'),
                'command raw status differs from actual reaped leader status')
        require(type(cancelled_command.get('raw_exit_code')) is int, 'live Cargo command has no actual raw status')
        require('WNOWAIT' in command_group.get('identity_anchor', ''), 'leader identity anchor is not retained')
        lifecycle = []
        command_paths = sorted(out.rglob('*.command.json'))
        require(sorted(final.get('command_receipts', [])) == sorted(str(path.relative_to(out)) for path in command_paths),
                'aggregate command receipt list is incomplete')
        for path in command_paths:
            lifecycle.extend(cleanup_receipts(json.loads(path.read_text()), str(path)))
        require(lifecycle and all(item['reaped'] is True and not item['external_reap'] for item in lifecycle),
                'direct-command reaping receipts are missing or failed')
        launches = sorted(root.glob('qemu-launch-*.json'))
        require(len(launches) == 1, 'a second VM was launched after the first was paused/cancelled')
        source_after = {p: record(work / p) for p in sources}
        require(source_after == invocation['source'], 'production source changed during experiment')
        result.update(passed=True, cli_returncode=owner.returncode, after_signal_pidfd_exited=ended,
                      stable_lock_reacquired=True, ktest_result=final, cancelled_command=cancelled_command, owned_cleanup=lifecycle,
                      queued_second_launch=False, source_after=source_after,
                      recorder_finalization='rawnull is expected if the wrapper was terminated before rewriting its launch record')
    except BaseException as error:
        result.update(passed=False, error_type=type(error).__name__, error=str(error))
    finally:
        if owner is not None and owner.poll() is None:
            signal.pidfd_send_signal(descriptors['ktest_cli'], signal.SIGTERM)
            try:owner.wait(timeout=15)
            except subprocess.TimeoutExpired:pass
        cleanup = []
        for name, descriptor in descriptors.items():
            alive = not exited(descriptor)
            if alive:
                try:signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                except ProcessLookupError:pass
            cleanup.append({'process': name, 'was_alive': alive, 'pidfd_exited': exited(descriptor, 3)})
            os.close(descriptor)
        if owner is not None:
            owner.wait(timeout=5)
            result['actual_cli_returncode'] = owner.returncode
        result['controller_cleanup'] = cleanup
        result['duration_seconds'] = round(time.monotonic() - started, 3)
        result['production_output'] = str(out)
        write(root / 'result.json', result)
    return int(not result['passed'])


if __name__ == '__main__':
    raise SystemExit(main())
