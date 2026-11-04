#!/usr/bin/env python3
"""Execute the separate exact-owner image kernel pipeline with explicit source receipts.

This operational wrapper lives outside either reviewed repository. It emits no
runtime qualification. Its output is checked by the reviewed original validator.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import tomllib

sys.dont_write_bytecode = True

def require(value, message):
    if not value:
        raise ValueError(message)

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

def actual_step(label, argv, cwd, environment, out, report, timeout=7200):
    require(signal.getsignal(signal.SIGCHLD) == signal.SIG_DFL,
            'the wrapper must be the sole wait owner with default SIGCHLD')
    require(hasattr(os, 'WNOWAIT'), 'non-reaping owned-child observation required')
    require(hasattr(signal, 'pthread_sigmask'), 'owned-child cleanup signal mask required')
    record = {'label': label, 'argv': argv, 'cwd': str(cwd),
              'started_at_utc': datetime.now(timezone.utc).isoformat(),
              'timeout_seconds': timeout, 'timed_out': False}
    report['steps'].append(record)
    save(out / 'pipeline.json', report)
    started = time.monotonic()
    with (out / (label + '.log')).open('xb') as log:
        process = subprocess.Popen(argv, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        may_signal_group = True
        failure = None
        try:
            while True:
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    record['timed_out'] = True
                    raise subprocess.TimeoutExpired(argv, timeout)
                try:
                    exited = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                except ChildProcessError:
                    may_signal_group = False
                    record['cleanup_owner_lost'] = True
                    raise RuntimeError('owned-child wait identity was lost') from None
                if exited is not None:
                    break
                time.sleep(min(0.05, remaining))
            # Disarm before wait(), which may reap before an interruption.
            may_signal_group = False
            record['exit_code'] = process.wait()
        except BaseException as error:
            failure = error
            record['error'] = type(error).__name__ + ': ' + str(error)
        finally:
            # A second Ctrl-C must not leave the owned build alive while its
            # exclusive target lease is released. Defer it until after reap.
            previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT})
            try:
                if may_signal_group:
                    # Verify the unreaped owned child before the one signal.
                    try:
                        os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                    except ChildProcessError:
                        may_signal_group = False
                        record['cleanup_owner_lost'] = True
                    if may_signal_group:
                        try:
                            record['cleanup_group_signal'] = 'SIGKILL'
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        finally:
                            may_signal_group = False
                # Keep the build lease through reap, never re-arm a signal.
                while process.returncode is None and not record.get('cleanup_owner_lost'):
                    try:
                        record['exit_code'] = process.wait()
                    except (KeyboardInterrupt, SystemExit) as error:
                        if failure is None:
                            failure = error
                            record['error'] = type(error).__name__ + ': ' + str(error)
                record['exit_code'] = process.returncode
            finally:
                try:
                    signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
                except (KeyboardInterrupt, SystemExit) as error:
                    if failure is None:
                        failure = error
                        record['error'] = type(error).__name__ + ': ' + str(error)
    record.update(elapsed_seconds=round(time.monotonic() - started, 3),
                  finished_at_utc=datetime.now(timezone.utc).isoformat())
    save(out / 'pipeline.json', report)
    if failure is not None:
        raise failure
    require(record['exit_code'] == 0 and not record['timed_out'], label + ' did not succeed')

def execute(args):
    source, hepta, owner_receipt, out = args.source, args.hepta, args.owner_receipt, args.output
    require(not out.exists() and not out.is_symlink(), 'new pipeline output required')
    for path in (source, hepta, args.cargo_home, args.rustup_home, args.vdso, args.target, args.osdk_target):
        require(path.is_absolute() and path.is_dir() and path.resolve(strict=True) == path,
                'canonical existing directory required: ' + str(path))
    require(all(not out.resolve().is_relative_to(path) for path in (source, hepta, owner_receipt.parent)),
            'pipeline output must be outside reviewed inputs')
    require(all(path.is_relative_to(out.parent) for path in (args.cargo_home, args.rustup_home, args.target, args.vdso, args.osdk_target)),
            'Cargo/OSDK installation, Rustup and targets must be private to this task output root')
    sys.path.insert(0, str(source / 'tests/workloads/hepta_cpu_control'))
    inputs = module('original_g2_inputs', source / 'tests/workloads/hepta_cpu_control/native_owner_inputs.py')
    builder = module('original_g2_builder', source / 'tests/workloads/hepta_cpu_control/build_original_entry.py')
    profile = inputs.EXACT_IMAGE_PROFILE
    review = inputs.review_inputs(args.source_review, args.source_review_sha256, profile)
    exact = inputs.image_module(profile)
    owner = owner_receipt.parent / 'packaged/hepta-g2-native-owner'
    shape, ordinary, _ = inputs.original_helpers(source)
    snapshots = inputs.source_snapshots({'desktop': source, 'hepta': hepta}, review, builder)
    _, owner_bytes, _, _ = inputs.owner_build(owner_receipt, args.owner_receipt_sha256, owner, review, snapshots, shape, hepta, profile)
    require(sha(args.vdso / 'vdso_x86_64.so') == '27cd7bf576a92fa48a891c05988f52fac35b7374d5b9650d6b035e477c5d93a3', 'fixed VDSO differs')
    before = ordinary.source_snapshot(source, review['desktop']['head'], review['desktop']['tree'])
    subprocess.run(['/usr/bin/python3', '-I', '-B', str(source / 'support/build/verify-source.py')],
                   cwd=source, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'},
                   capture_output=True, timeout=60, check=True)
    out.mkdir(mode=0o700)
    save(out / 'source-before.json', before)
    (out / 'source-review.json').write_bytes(inputs.read(args.source_review, 1024**2, args.source_review_sha256))
    report = {'passed': False, 'source_inputs_unchanged': False, 'kernel_profile': profile,
              'source_root': str(source), 'source_head': review['desktop']['head'], 'source_tree': review['desktop']['tree'],
              'owner_sha256': sha(owner), 'owner_build_receipt_sha256': args.owner_receipt_sha256,
              'osdk_source_root': str(source / 'kernel/asterinas/osdk'), 'steps': [],
              'osdk_target_directory': str(args.osdk_target), 'osdk_warm_cache': True,
              'started_at_utc': datetime.now(timezone.utc).isoformat(),
              'operational_wrapper_sha256': sha(Path(__file__).resolve()),
              'native_execution_verified': False, 'g2_complete': False, 'production': False,
              'schema': 'hepta.original-owner-image-kernel-pipeline.v1',
              'image_profile_descriptor_sha256': exact.DESCRIPTOR_SHA256,
              'image_profile_descriptor': exact.bind_source_review(review),
              'source_review_sha256': args.source_review_sha256,
              'legacy_static_profile_passed': False, 'legacy_limits_unchanged': True,
              'whole_guest_peak_verified': False, 'global_memory_reserve': False,
              'production_ready': False}
    save(out / 'pipeline.json', report)
    lease = os.open(args.target / '.g2-product-build.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        environment = {'PATH': str(args.cargo_home / 'bin') + ':/usr/bin:/bin:/usr/sbin:/sbin',
                       'HOME': str(Path.home()), 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
                       'CARGO_HOME': str(args.cargo_home), 'RUSTUP_HOME': str(args.rustup_home),
                       'CARGO_NET_OFFLINE': 'true',
                       'VDSO_LIBRARY_DIR': str(args.vdso), 'CARGO_BUILD_JOBS': '1', 'A01_SMP': '1',
                       'PYTHONDONTWRITEBYTECODE': '1', 'GIT_TERMINAL_PROMPT': '0'}
        cargo = args.cargo_home / 'bin/cargo'
        command = [str(cargo), '+nightly-2026-07-21', 'install', '--locked', '--offline', '--force', 'cargo-osdk',
                   '--path', str(source / 'kernel/asterinas/osdk'), '--target-dir', str(args.osdk_target)]
        actual_step('osdk-build', command, source, {**environment, 'OSDK_LOCAL_DEV': '1',
                    'CARGO_TARGET_DIR': str(args.osdk_target)}, out, report)
        osdk = args.cargo_home / 'bin/cargo-osdk'
        require(osdk.is_file() and not osdk.is_symlink(), 'actual source-built OSDK missing')
        shutil.copyfile(osdk, out / 'source-built-cargo-osdk')
        (out / 'source-built-cargo-osdk').chmod(0o444)
        report['osdk_sha256'] = sha(osdk)
        require(sha(out / 'source-built-cargo-osdk') == report['osdk_sha256'], 'OSDK freeze differs')
        command = [str(source / 'support/build/kernel.sh'), 'kernel']
        actual_step('g2-kernel', command, source, {**environment, 'CARGO_TARGET_DIR': str(args.target),
                    'A01_RUN_DIR': str(out / 'kernel-build'), 'HEPTA_G2_ORIGINAL_OWNER_A39_V1': '1',
                    'HEPTA_TRUSTED_INITIAL_ELF': str(owner)}, out, report)
        require(sha(osdk) == report['osdk_sha256'], 'OSDK changed during product build')
        generated = args.target / 'osdk/asterinas-run-base/Cargo.lock'
        locked = generated.read_bytes()
        require(locked == (source / 'support/build/minimal/Cargo.lock').read_bytes()
                and len(tomllib.loads(locked.decode())['package']) == 204, 'actual generated lock differs')
        (out / 'kernel-build/generated.Cargo.lock').write_bytes(locked)
        kernel = args.target / 'osdk/asterinas/asterinas-osdk-bin.elf'
        require(kernel.is_file() and not kernel.is_symlink() and kernel.stat().st_size <= 64 * 1024**2, 'bounded original kernel required')
        shutil.copyfile(kernel, out / 'product-kernel.elf')
        (out / 'product-kernel.elf').chmod(0o444)
        after = ordinary.source_snapshot(source, review['desktop']['head'], review['desktop']['tree'])
        save(out / 'source-after.json', after)
        require(before == after, 'full tracked source inputs changed')
        report.update(passed=True, source_inputs_unchanged=True, kernel_sha256=sha(out / 'product-kernel.elf'),
                      kernel_bytes=(out / 'product-kernel.elf').stat().st_size)
        save(out / 'pipeline.json', report)
        inputs.kernel_build(out, sha(out / 'pipeline.json'), review, owner_bytes, ordinary, profile)
        report['reviewed_original_validator_passed'] = True
    except BaseException as error:
        report.update(passed=False, error=type(error).__name__ + ': ' + str(error))
        if not (out / 'source-after.json').exists():
            try:
                after = ordinary.source_snapshot(source, review['desktop']['head'], review['desktop']['tree'])
                save(out / 'source-after.json', after)
                report['source_inputs_unchanged'] = before == after
            except Exception as snapshot_error:
                report['source_after_error'] = str(snapshot_error)
    finally:
        os.close(lease)
        report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        save(out / 'pipeline.json', report)
    print(json.dumps({k: report[k] for k in ('passed', 'error', 'source_inputs_unchanged', 'kernel_sha256', 'kernel_bytes', 'reviewed_original_validator_passed') if k in report}))
    return 0 if report['passed'] else 1

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'hepta', 'owner-receipt', 'output', 'cargo-home', 'rustup-home', 'vdso', 'target', 'source-review', 'osdk-target'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-review-sha256', required=True)
    parser.add_argument('--owner-receipt-sha256', required=True)
    raise SystemExit(execute(parser.parse_args()))
