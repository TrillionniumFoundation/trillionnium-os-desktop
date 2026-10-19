#!/usr/bin/env python3
"""Cancel an actual source-built Asterinas debug CLI at its live Rust entry.

Only the debug CLI receives the test SIGTERM. QEMU/GDB identities come from
receipts in this controller's own fork/exec tree; no /proc traversal is used.
The GDB script is explicitly adapted to pause after its live byte verification.
This is cancellation acceptance, never a successful complete boot claim.
"""
import errno
import fcntl
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

ROOT = Path(__file__).resolve().parent
WORK = Path('/workspace/scratch/ae1a8cf05419/a01-next6-build')
OUT = WORK / 'support/build/out/next6-real-debug-cancel-03'
REAL_GDB = Path('/workspace/scratch/ae1a8cf05419/a01-host-tools-next-e5ae/root/usr/bin/gdb')
MANIFEST_HASH = '1ff39174c39411f8b9a7fd328f762268e62d88521b43ebbde384d03d7d9a9f9f'
SHIM = ROOT / 'gdb-live-hold.py'
EVENTS = ROOT / 'events.jsonl'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def identity(path):
    path = Path(path)
    with path.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    info = path.stat()
    return {'path': str(path), 'size': info.st_size, 'sha256': digest}


def event(name, **fields):
    record = {'event': name, 'monotonic': time.monotonic(), 'time_ns': time.time_ns(), **fields}
    with EVENTS.open('a') as output:
        output.write(json.dumps(record) + '\n')
    print(json.dumps(record), flush=True)


def exited(descriptor, timeout=0):
    return bool(select.select([descriptor], [], [], timeout)[0])


def wait_json(path, process, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            require(process.poll() is None, f'debug CLI exited {process.returncode} before {path.name}')
            time.sleep(.05)
    raise TimeoutError(f'timeout awaiting {path}')


def port_bind_released(address, timeout=5):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(tuple(address))
                return {'released': True, 'method': 'fresh AF_INET bind without SO_REUSEADDR'}
            except OSError as error:
                last_error = {'errno': error.errno, 'message': str(error)}
        time.sleep(.05)
    return {'released': False, 'method': 'fresh AF_INET bind without SO_REUSEADDR', 'last_error': last_error}


def make_shim():
    # The original block has already checked PC and 32 live bytes before this
    # inserted hold executes. All other GDB commands and ELF arguments survive.
    code = '''#!/usr/bin/env python3
import hashlib,json,os,sys,time
from pathlib import Path
root=Path(__file__).resolve().parent
real=Path(REAL_GDB_VALUE)
args=sys.argv[1:]
if args==['--version']:
 os.execv(str(real),[str(real),*args])
if args.count('-x')!=1:
 raise SystemExit('expected exactly one original GDB -x script')
index=args.index('-x')+1
original=Path(args[index]).resolve()
if original!=Path(ORIGINAL_SCRIPT_VALUE):
 raise SystemExit('unexpected original GDB script path')
raw=original.read_bytes()
lines=raw.decode().splitlines(keepends=True)
markers=[i for i,line in enumerate(lines) if line.startswith('gdb.write("A01_GDB_RUST_ENTRY_BYTES ')]
if len(markers)!=1 or lines[markers[0]+1].strip()!='end':
 raise SystemExit('expected the original verified live-byte marker immediately before Python end')
hold = """import json, os, time
gdb.flush(gdb.STDOUT)
hold_record = {"kind": "real_native_gdb_hold_after_original_live_entry_validation", "gdb_pid": os.getpid(), "group": os.getpgrp(), "pc": hex(pc), "entry_bytes": observed.hex(), "entry_size": len(observed), "hold_seconds": 60}
with open(READY_VALUE, "x") as hold_output:
    json.dump(hold_record, hold_output, indent=2)
    hold_output.write(chr(10))
gdb.write("A01_REAL_CANCEL_HOLD_READY" + chr(10))
gdb.flush(gdb.STDOUT)
time.sleep(60)
"""
hold=hold.replace('READY_VALUE',repr(str(root/'native-gdb-ready.json')))
adapted=''.join(lines[:markers[0]+1])+hold+''.join(lines[markers[0]+1:])
script=root/'adapted-rust-entry.gdb'
compile(adapted.split('python'+chr(10),1)[1].rsplit(chr(10)+'end'+chr(10),1)[0],str(script),'exec')
with script.open('x') as output: output.write(adapted)
args[index]=str(script)
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
receipt={"scope":"GDB script adaptation only; no source/ELF modification; cancellation case, not boot pass", "shim_pid":os.getpid(), "original_script":str(original), "original_sha256":hashlib.sha256(raw).hexdigest(), "adapted_script":str(script), "adapted_sha256":digest(script), "insertion":"after original PC/32-byte live verification and byte marker, before Python end; write readiness then sleep(60)", "real_gdb":str(real), "real_gdb_sha256":digest(real), "requested_argv":sys.argv, "actual_argv":[str(real),*args]}
(root/'adaptation.json').write_text(json.dumps(receipt,indent=2)+'\\n')
os.execv(str(real),[str(real),*args])
'''
    code = code.replace('REAL_GDB_VALUE', repr(str(REAL_GDB))).replace('ORIGINAL_SCRIPT_VALUE', repr(str(OUT / 'rust-entry.gdb')))
    SHIM.write_text(code)
    SHIM.chmod(0o755)
    compile(code, str(SHIM), 'exec')


def preserve_and_launch(command, env, output):
    lock = WORK / 'support/build/out-kernel.lock'
    preserve = WORK / 'support/build/out/next6-manifest-preserved/pre-cancel-03.toml'
    manifest = WORK / 'kernel/asterinas/kernel/OSDK.toml'
    preserve.parent.mkdir(parents=True, exist_ok=True)
    require(not os.path.lexists(preserve), 'exclusive preserved manifest path already exists')
    with lock.open('a') as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        info = os.fstat(held.fileno())
        record = {'lock_path': str(lock), 'lock_device': info.st_dev, 'lock_inode': info.st_ino,
                  'manifest_present': os.path.lexists(manifest), 'preserved_path': str(preserve),
                  'reason': 'known protective refusal; writer/cause unknown; only matching minimal profile may be renamed'}
        if os.path.lexists(manifest):
            descriptor = os.open(manifest, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, 'rb') as source:
                before = os.fstat(source.fileno())
                require(stat.S_ISREG(before.st_mode), 'manifest is not regular')
                digest = hashlib.file_digest(source, 'sha256').hexdigest()
                require(digest == MANIFEST_HASH, 'refuse to move a nonmatching manifest')
                current = manifest.lstat()
                require((current.st_dev, current.st_ino) == (before.st_dev, before.st_ino), 'manifest changed during check')
                os.rename(manifest, preserve)
                after = preserve.stat()
                require((after.st_dev, after.st_ino) == (before.st_dev, before.st_ino), 'manifest changed during rename')
                require(identity(preserve)['sha256'] == MANIFEST_HASH, 'preserved manifest bytes changed')
                record.update(manifest_sha256=digest, manifest_device=before.st_dev, manifest_inode=before.st_ino,
                              preserved=identity(preserve))
        # All setup precedes the protected move. Launch immediately while the
        # stable lock still identifies this workspace, then release for worker.
        process = subprocess.Popen(command, cwd=WORK, env=env, stdout=output, stderr=subprocess.STDOUT)
        record['debug_cli_pid'] = process.pid
        write_json(ROOT / 'manifest-preservation.json', record)
        return process, (info.st_dev, info.st_ino)


def main():
    started = time.monotonic()
    process = None
    descriptors = {}
    result = {'kind': 'actual_rust_kernel_debug_cancellation', 'passed': False,
              'complete_boot_pass': False, 'qemu_launch_claim': 'pending live receipt',
              'script_adaptation': 'hold after original live PC and 32 instruction-byte verification',
              'scope': 'SIGTERM cancellation of actual debug CLI; not host fixture or complete boot acceptance'}
    make_shim()
    require(not OUT.exists(), 'debug output must be new')
    inherited = json.loads(Path('/workspace/scratch/ae1a8cf05419/next6-clean-debug-invocation.json').read_text())['environment']
    env = os.environ.copy()
    env.update(inherited)
    env['CARGO_TARGET_DIR'] = str(WORK / 'kernel/asterinas/target')
    env['PATH'] = '/workspace/scratch/ae1a8cf05419/toolchains/cargo/bin:/workspace/scratch/ae1a8cf05419/a01-host-tools-next-e5ae/root/usr/bin:' + env.get('PATH', '')
    command = [sys.executable, '-I', str(WORK / 'support/build/debug/run.py'), '--output', str(OUT),
               '--gdb', str(SHIM), '--ready-timeout', '900', '--gdb-timeout', '120', '--boot-timeout', '120']
    git = lambda *args: subprocess.check_output(['git', '-C', str(WORK), *args], text=True).strip()
    source_paths = ['support/build/debug/run.py', 'support/build/debug/test_debug.py', 'support/build/kernel.sh',
                    'support/build/kernel-supervisor.py', 'support/build/record-qemu.py', 'support/build/minimal.mk',
                    'support/build/minimal/OSDK.toml', 'kernel/asterinas/Cargo.lock', 'kernel/asterinas/osdk/Cargo.lock',
                    'kernel/asterinas/rust-toolchain.toml']
    invocation = {'argv': command, 'cwd': str(WORK), 'selected_environment': {key: env.get(key) for key in
                  ['CARGO_HOME','RUSTUP_HOME','RUSTUP_TOOLCHAIN','CARGO_NET_OFFLINE','CARGO_TARGET_DIR','VDSO_LIBRARY_DIR',
                   'CARGO_BUILD_JOBS','LD_LIBRARY_PATH','PATH']}, 'complete_environment_saved': False,
                  'git_head': git('rev-parse','HEAD'), 'git_tree': git('rev-parse','HEAD^{tree}'), 'git_status': git('status','--short'),
                  'published_equivalent_commit': os.environ.get('A01_CANCEL_PUBLISHED_COMMIT', 'not_supplied'), 'real_gdb': identity(REAL_GDB), 'shim': identity(SHIM),
                  'source': {relative: identity(WORK / relative) for relative in source_paths},
                  'controller': identity(Path(__file__))}
    write_json(ROOT / 'invocation.json', invocation)
    event('prepared', source_tree=invocation['git_tree'])
    try:
        with (ROOT / 'console.log').open('wb') as output:
            process, lock_identity = preserve_and_launch(command, env, output)
            descriptors['debug_cli'] = os.pidfd_open(process.pid)
            event('launched', debug_cli_pid=process.pid)
            ready = wait_json(ROOT / 'native-gdb-ready.json', process, 900)
            qemu = wait_json(OUT / 'boot/qemu.json', process, 2)
            debug_ready = wait_json(OUT / 'qemu-ready.json', process, 2)
            adaptation = json.loads((ROOT / 'adaptation.json').read_text())
            require(ready['gdb_pid'] == adaptation['shim_pid'], 'exec did not retain owned native GDB identity')
            require(qemu['qemu_pid'] == debug_ready['qemu_pid'], 'QEMU receipts disagree')
            descriptors['qemu'] = os.pidfd_open(qemu['qemu_pid'])
            descriptors['native_gdb'] = os.pidfd_open(ready['gdb_pid'])
            before = {name: not exited(fd) for name, fd in descriptors.items()}
            require(all(before.values()), 'an expected live process exited before cancellation')
            binding = json.loads((OUT / 'entry-artifact-binding.json').read_text())
            require(ready['entry_size'] == 32 and ready['entry_bytes'] == binding['expected_bytes'], 'live native GDB bytes differ')
            require(ready['pc'] == binding['entry_address'], 'live native GDB PC differs')
            log = (OUT / 'gdb.log').read_text(errors='replace')
            require('A01_GDB_RUST_ENTRY_HIT' in log and 'A01_GDB_RUST_ENTRY_BYTES' in log, 'original native live markers missing')
            address = qemu['gdb_listener']['address']
            require(address[0] == '127.0.0.1', 'GDB listener is not loopback')
            require(not port_bind_released(address, .1)['released'], 'GDB port was not held while QEMU was live')
            lock_path = WORK / 'support/build/out-kernel.lock'
            with lock_path.open('a') as held:
                try:
                    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    raise RuntimeError('kernel workspace lock was not held before cancellation')
                except BlockingIOError:
                    pass
            result.update(before_signal_alive=before, live_gdb=ready, qemu_ready=qemu,
                          original_entry_binding=binding, qemu_launch_claim='actual source-built x86_64 q35/TCG 1CPU 512MiB Rust kernel paused at verified Rust entry')
            event('live_rust_entry_confirmed', qemu_pid=qemu['qemu_pid'], native_gdb_pid=ready['gdb_pid'], pc=ready['pc'], entry_bytes=ready['entry_bytes'])
            signal.pidfd_send_signal(descriptors['debug_cli'], signal.SIGTERM)
            event('sigterm_sent_only_to_debug_cli', debug_cli_pid=process.pid)
            process.wait(timeout=15)
        exited_after = {name: exited(fd, 3) for name, fd in descriptors.items()}
        port = port_bind_released(address)
        with (WORK / 'support/build/out-kernel.lock').open('a') as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            info = os.fstat(held.fileno())
            stable_lock = (info.st_dev, info.st_ino) == lock_identity
        debug_result = json.loads((OUT / 'result.json').read_text())
        require(process.returncode == 143, 'cancelled debug CLI must return 143')
        require(debug_result['passed'] is False and debug_result['interrupted_by'] == 'SIGTERM', 'debug result falsely accepted cancellation')
        require(all(exited_after.values()), 'owned QEMU/GDB or debug CLI remained alive')
        require(port['released'], 'GDB TCP port was not released')
        require(stable_lock, 'workspace lock inode changed')
        cleanup = debug_result['owned_session_cleanup']
        require(all(item.get('reaped') is True and not item.get('external_reap') for item in cleanup), 'a debug-owned direct session was not reaped')
        require(ready['gdb_pid'] in [item['leader_pid'] for item in cleanup], 'native GDB direct owner not in cleanup receipt')
        result.update(passed=True, cli_returncode=process.returncode, debug_result=debug_result,
                      after_signal_pidfd_exited=exited_after, tcp_gdb_port=port, stable_workspace_lock_reacquired=True,
                      source_after={relative: identity(WORK / relative) for relative in source_paths})
        require(result['source_after'] == invocation['source'], 'source changed during cancellation experiment')
        event('cancellation_verified', cli_returncode=process.returncode, pidfd_exited=exited_after, gdb_port_released=port['released'])
    except BaseException as error:
        result.update(passed=False, error_type=type(error).__name__, error=str(error))
        event('failed', error_type=type(error).__name__, error=str(error))
    finally:
        cleanup = []
        # First ask our exact CLI owner to finish its normal cooperative cleanup.
        if process is not None and process.poll() is None:
            signal.pidfd_send_signal(descriptors['debug_cli'], signal.SIGTERM)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                pass
        for name, descriptor in descriptors.items():
            alive = not exited(descriptor)
            if alive:
                try:
                    signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            ended = exited(descriptor, 3)
            cleanup.append({'process': name, 'was_alive_in_final_cleanup': alive, 'pidfd_exited': ended,
                            'signal_if_needed': 'SIGKILL only through retained pidfd'})
            os.close(descriptor)
        if process is not None:
            process.wait(timeout=5)
            result['actual_cli_returncode'] = process.returncode
        result['controller_cleanup'] = cleanup
        result['duration_seconds'] = round(time.monotonic() - started, 3)
        if OUT.exists():
            result['debug_output'] = str(OUT)
            result['actual_debug_result'] = json.loads((OUT/'result.json').read_text()) if (OUT/'result.json').exists() else None
        result['manifest_present_after'] = os.path.lexists(WORK/'kernel/asterinas/kernel/OSDK.toml')
        write_json(ROOT / 'result.json', result)
    return int(not result['passed'])


if __name__ == '__main__':
    raise SystemExit(main())
