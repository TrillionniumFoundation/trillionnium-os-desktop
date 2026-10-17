#!/usr/bin/env python3
"""Execute fixed A04 C ELF inside a strictly extracted rootfs on ORIGINAL Linux.

Distinct from staged loader execution: chroot resolves PT_INTERP, all DT_NEEDED
libraries and runtime file lookups inside the 17-file captured rootfs. The
child drops to uid/gid 65534; the only writable area is /tmp/a04/CASE.
No mounts, containers, package installs, privileged guest or system disk
changes. chroot is NOT a network/PID/user namespace sandbox, not Asterinas,
not Hepta W1 and not an S1 persistence qualification.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def module(name, source):
    spec = importlib.util.spec_from_file_location(name, source)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


capture = module('a04_chroot_capture', ROOT/'support/rootfs/capture.py')
guest = module('a04_chroot_guest', HERE/'guest.py')


def enter_chroot(root):
    # preexec_fn executes only in forked child, before execve. Parent never chroots.
    os.chroot(root)
    os.chdir('/')
    os.setgroups([])
    os.setgid(65534)
    os.setuid(65534)


def bounded_run(command, *, env, timeout, preexec_fn):
    """Kill the entire disposable process group, not just a timed-out parent.

    A forked descendant can inherit stdout/stderr and keep communicate() open
    after a parent exits. Returning before all pipe owners have died would
    also invalidate file-lock and resource-release observations.
    """
    proc = subprocess.Popen(command, cwd='/', env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True,
                            start_new_session=True, preexec_fn=preexec_fn)
    stdout, stderr, timed_out, cleanup_incomplete = '', '', False, False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
    finally:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if proc.poll() is None:
            proc.kill()
        try:
            # After killing the whole group, all inherited pipes must close.
            proc.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            # A grandchild may have called setsid() and escaped the original
            # process group while retaining a pipe. Never wait forever or
            # claim its cleanup was verified.
            cleanup_incomplete = True
            for pipe in (proc.stdout, proc.stderr):
                if pipe is not None:
                    pipe.close()
            proc.wait(timeout=3)
    return {'exit_code': proc.returncode, 'stdout': stdout, 'stderr': stderr,
            'timed_out': timed_out, 'cleanup_incomplete': cleanup_incomplete}


def exact_observation(execution, reference_case):
    """Fail closed for stderr, extra output, ambiguous JSON and exit drift.

    The same rule must be used by one-shot chroot and repeated chroot stress.
    The guest serial parser independently enforces this contract.
    """
    if execution.get('timed_out'):
        return None, False, 'timeout_descendants_terminated'
    if execution.get('cleanup_incomplete'):
        return None, False, 'incomplete_descendant_cleanup'
    if execution.get('exit_code') != reference_case.get('exit_code'):
        return None, False, 'exit_code_mismatch'
    if execution.get('stderr'):
        return None, False, 'unexpected_stderr'
    stdout = execution.get('stdout')
    if not isinstance(stdout, str) or len(stdout.splitlines()) != 1:
        return None, False, 'unexpected_stdout'
    try:
        facts = guest._json_unique_guest_object(stdout)
    except (json.JSONDecodeError, ValueError):
        return None, False, 'invalid_or_ambiguous_json'
    if not isinstance(facts, dict) or facts != reference_case.get('facts') or facts.get('ok') is not True:
        return facts, False, 'observable_result_mismatch'
    return facts, True, None


def run(tar_path, manifest_path, reference, *, timeout=30):
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise ValueError('x86_64 original Linux required')
    if os.geteuid() != 0:
        raise PermissionError('CAP_SYS_CHROOT/root required in disposable test host')
    if timeout < 1 or timeout > 60:
        raise ValueError('timeout must be in 1..60 seconds')
    with tempfile.TemporaryDirectory(prefix='a04-chroot-replay-') as work:
        root = Path(work)/'root'
        captured_count = capture.extract_verified_tar(tar_path, manifest_path, root)
        # This is a writable ephemeral COPY. The manifest-pinned source tree and
        # read-only file modes are unchanged; no host mount table is altered.
        root.chmod(0o755)
        (root/'tmp').mkdir(mode=0o1777)
        (root/'tmp').chmod(0o1777)
        (root/'tmp/a04').mkdir(mode=0o711)
        (root/'tmp/a04').chmod(0o711)
        manifest = json.loads(Path(manifest_path).read_text())
        pinned = guest.verify_binary_identity(root, manifest, reference,
                                              required_stems=reference['binaries'])
        cases = {}
        for name, stem, case in guest.reference_elf_cases(reference):
            binary = pinned[guest.BINARY_FOR[stem]]
            if binary['sha256'] != reference['binaries'][stem]['sha256']:
                raise ValueError('ELF manifest SHA diverges from Linux reference')
            scratch = '/tmp/a04/' + name
            case_dir = root / scratch.lstrip('/')
            case_dir.mkdir(mode=0o700)
            os.chown(case_dir, 65534, 65534)
            exe = binary['path']
            command = [exe] + ([scratch] if stem.startswith('sqlite_') else [case, scratch])
            # Fixed process environment, NO host LD_LIBRARY_PATH/preloads,
            # credentials, host paths or provider configuration inherited.
            env = {'PATH': '/usr/local/bin/a04', 'LC_ALL': 'C', 'TZ': 'UTC',
                   'HOME': scratch}
            try:
                execution = bounded_run(command, env=env, timeout=timeout,
                                        preexec_fn=lambda: enter_chroot(root))
                facts, success, error = exact_observation(execution, reference['cases'][name])
                cases[name] = {'status': 'pass' if success else 'fail',
                               'exit_code': execution['exit_code'], 'facts': facts,
                               'error': error,
                               'scratch': 'volatile_chroot'}
            except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
                cases[name] = {'status': 'fail', 'exit_code': None, 'facts': None,
                               'error': type(exc).__name__, 'scratch': 'volatile_chroot'}
        for name in reference['cases']:
            if name not in cases:
                cases[name] = {'status': 'not_run', 'reason': 'requires Python or Rust guest runtime'}
        counts = {status: sum(1 for entry in cases.values() if entry['status'] == status)
                  for status in ('pass', 'fail', 'not_run')}
        return {'schema': 1, 'suite': 'a04-host-linux-chroot-elf-only',
                'platform': {'system': platform.system(), 'machine': platform.machine(),
                             'release': platform.release(), 'execution': 'host_linux_chroot_uid65534',
                             'mounts_changed': False, 'network_namespace_isolated': False},
                'binaries': reference['binaries'], 'cases': dict(sorted(cases.items())),
                'counts': counts, 'rootfs_manifest_sha256': capture.sha(manifest_path),
                'rootfs_tar_sha256': capture.sha(tar_path), 'manifest_files_verified': captured_count,
                'rootfs_fully_isolated_from_host_loader': True,
                'kernel_guest_verified': False, 'guest_execution_verified': False,
                'real_hepta_w1_verified': False, 's1_storage_verified': False}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--tar', type=Path, required=True, help='fixed corrected rootfs USTAR')
    ap.add_argument('--manifest', type=Path, required=True)
    ap.add_argument('--reference', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--timeout', type=int, default=30)
    args = ap.parse_args()
    if args.output.exists() or args.output.is_symlink():
        ap.error('refusing to overwrite existing evidence')
    try:
        reference = json.loads(args.reference.read_text())
        result = run(args.tar.resolve(), args.manifest.resolve(),
                     reference, timeout=args.timeout)
    except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError, EOFError) as exc:
        ap.exit(2, 'A04 host chroot baseline blocked: ' + type(exc).__name__ + ': ' + str(exc) + '\n')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'counts': result['counts'], 'rootfs_verified_files': result['manifest_files_verified'],
                      'kernel_guest_verified': False}))
    expected_c = len(guest.reference_elf_cases(reference))
    expected_skipped = len(reference["cases"]) - expected_c
    return 0 if result["counts"] == {"pass": expected_c, "fail": 0,
                                      "not_run": expected_skipped} else 1


if __name__ == '__main__':
    sys.exit(main())
