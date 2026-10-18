#!/usr/bin/env python3
"""Bounded source-pinned RED/GREEN checks in the new copied UI target."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parent
WORKSPACE = BASE.parent.parent
TARGET = BASE / 'target'
PINS = {
    'red': ('next-r6-ui-red', '821841baf5c106b7fc5e4b849ac94636b1b724f7'),
    'green': ('next-r6-ui-fix', 'f0f10dff564037fabc35809a8d8bb174dc5becb9'),
}
EXPECTED_RED = {
    'a_queued_old_observed_response_is_visibly_stale_before_drawing',
    'runtime_sample_and_local_receipt_both_have_exact_seven_second_limits',
    'future_or_missing_observation_cannot_appear_current',
    'missing_or_future_local_receipt_is_unknown_without_rewriting_history',
    'a_later_fresh_session_snapshot_can_restore_the_visible_observation',
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def git(source, *args):
    return subprocess.check_output(['git', '-C', str(source), *args],
        stderr=subprocess.PIPE, timeout=20).decode().strip()


def nonreclaimable_memory():
    path = Path('/sys/fs/cgroup/memory.stat')
    if not path.is_file():
        return None
    values = {key: int(value) for key, value in (line.split() for line in path.read_text().splitlines())}
    return sum(values.get(key, 0) for key in
        ('anon', 'shmem', 'kernel_stack', 'pagetables', 'sock', 'slab_unreclaimable', 'file_dirty'))


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('mode', choices=('red', 'green'))
parser.add_argument('--run-name', required=True)
args = parser.parse_args()
require(re.fullmatch(r'[a-z0-9-]{1,40}', args.run_name), 'bounded new run name required')
name, pin = PINS[args.mode]
source = WORKSPACE / name
require(git(source, 'rev-parse', 'HEAD') == pin, 'source HEAD does not match frozen mode pin')
require(not git(source, 'status', '--porcelain=v1', '--untracked-files=all'), 'source must be clean')
copied = json.loads((BASE / 'copy-receipt.json').read_text())
require(copied['status'] == 'passed' and copied['target'] == str(TARGET), 'verified isolated copy required')
require(TARGET.is_dir() and not TARGET.is_symlink(), 'new owned real target directory required')
output = BASE / args.run_name
output.mkdir(mode=0o700)
(output / 'run-checks-source.py').write_bytes(Path(__file__).read_bytes())
(BASE / 'tmp').mkdir(mode=0o700, exist_ok=True)
guard_path = source / 'tests/integration/hepta/run_original_agentd.py'
(output / 'child-guard-source.py').write_bytes(guard_path.read_bytes())
spec = importlib.util.spec_from_file_location('ui_r6_check_guard', guard_path)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
require(guard.child_anchor_available(), 'waitable process group anchor required')
env = {
    'PATH': str(WORKSPACE / 'next-tools/cargo/bin') + ':/usr/local/bin:/usr/bin:/bin',
    'CARGO_HOME': str(WORKSPACE / 'next-tools/cargo'),
    'RUSTUP_HOME': str(WORKSPACE / 'next-tools/rustup'), 'RUSTUP_TOOLCHAIN': '1.88.0',
    'CARGO_TARGET_DIR': str(TARGET), 'CARGO_INCREMENTAL': '0', 'CARGO_BUILD_JOBS': '1',
    'CARGO_PROFILE_DEV_DEBUG': '0', 'CARGO_PROFILE_TEST_DEBUG': '0',
    'CARGO_TERM_COLOR': 'never', 'RUST_BACKTRACE': '0', 'LANG': 'C.UTF-8',
    'LC_ALL': 'C.UTF-8', 'TZ': 'UTC', 'TMPDIR': str(BASE / 'tmp'),
}
record = {'mode': args.mode, 'status': 'running',
    'started_utc': datetime.now(timezone.utc).isoformat(),
    'source_commit': pin, 'source_tree': git(source, 'rev-parse', 'HEAD^{tree}'),
    'ui_tree': git(source, 'rev-parse', 'HEAD:ui'),
    'target': str(TARGET), 'cache_mode': 'warm_copy_of_retained_R5_target',
    'cwd': str(source), 'package_invalidation': 'trill-shell only in new copied target',
    'source_cache_modified': False, 'copy_receipt_sha256': digest(BASE / 'copy-receipt.json'),
    'helper_sha256': digest(Path(__file__)), 'child_guard_sha256': digest(guard_path),
    'disk_reserve_bytes': 1024**3, 'nonreclaimable_memory_stop_bytes': 7 * 1024**3,
    'per_command_deadline_seconds': 300, 'commands': [], 'samples': []}


def save():
    (output / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')


def run(label, argv):
    item = {'label': label, 'argv': argv, 'started_utc': datetime.now(timezone.utc).isoformat()}
    record['commands'].append(item)
    group = None
    started = time.monotonic()
    try:
        with (output / (label + '.log')).open('xb') as log:
            process = subprocess.Popen(argv, cwd=source, env=env, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            group = guard.ChildGroup(process)
            while group.observe_exit() is None:
                sample = {'command': label, 'elapsed_seconds': round(time.monotonic() - started, 3),
                    'disk_free_bytes': shutil.disk_usage(BASE).free,
                    'nonreclaimable_memory_bytes': nonreclaimable_memory()}
                record['samples'].append(sample)
                require(sample['disk_free_bytes'] >= record['disk_reserve_bytes'], 'owned target disk reserve reached')
                memory = sample['nonreclaimable_memory_bytes']
                require(memory is None or memory < record['nonreclaimable_memory_stop_bytes'], 'shared memory reserve reached')
                require(time.monotonic() - started < record['per_command_deadline_seconds'], 'bounded Cargo command timed out')
                time.sleep(0.2)
            state = group.observe_exit()
            item['exit_code'] = group.reap() if state.si_code == os.CLD_EXITED and state.si_status == 0 else guard.terminate_group(group)
    except BaseException as error:
        item['error'] = str(error)
        if group is not None and group.armed:
            item['exit_code'] = guard.terminate_group(group)
        raise
    finally:
        item['elapsed_seconds'] = round(time.monotonic() - started, 3)
        item['finished_utc'] = datetime.now(timezone.utc).isoformat()
        save()
    return item['exit_code'], (output / (label + '.log')).read_text()


cargo = str(WORKSPACE / 'next-tools/cargo/bin/cargo')
try:
    code, _ = run('compiler-version', [str(WORKSPACE / 'next-tools/cargo/bin/rustc'), '-vV'])
    require(code == 0, 'pinned compiler identity command failed')
    # The package fingerprint and dep-info use workspace-relative source paths.
    # Switching frozen checkouts with older mtimes can otherwise reuse RED's
    # executable. Invalidate only this package in our disposable copied target.
    code, _ = run('clean-shell-package', [cargo, 'clean', '--manifest-path', 'ui/Cargo.toml',
        '-p', 'trill-shell', '--locked', '--offline'])
    require(code == 0, 'owned Shell package artifact invalidation failed')
    command = [cargo, 'test', '--manifest-path', 'ui/Cargo.toml', '-p', 'trill-shell',
        '--locked', '--offline', 'observation_freshness_tests', '--', '--nocapture']
    code, log = run('freshness-tests', command)
    require(re.search(r'Compiling trill-shell [^\n]*' + re.escape(str(source / 'ui/shell')), log),
        'frozen Shell source must actually be recompiled before accepting test evidence')
    test_paths = re.findall(r'Running unittests src/main.rs \(([^\n]+)\)', log)
    require(len(test_paths) == 1, 'one actual executed Shell test binary required')
    test_binary = Path(test_paths[0])
    require(test_binary.parent == TARGET / 'debug/deps' and test_binary.is_file(),
        'executed Shell test escaped the owned target')
    retained_test = output / 'executed-test.elf'
    shutil.copy2(test_binary, retained_test)
    dependency_info = test_binary.with_suffix('.d')
    (output / 'executed-test-dependencies.d').write_bytes(dependency_info.read_bytes())
    record['test_binary'] = {'path': str(test_binary), 'sha256': digest(test_binary),
        'bytes': test_binary.stat().st_size, 'retained_path': str(retained_test),
        'retained_sha256': digest(retained_test), 'dependency_info_sha256': digest(dependency_info),
        'compiled_source_directory': str(source / 'ui/shell'), 'recompilation_observed': True}
    if args.mode == 'red':
        failures = set(re.findall(r'^\s+observation_freshness_tests::([a-z_]+)$', log, re.MULTILINE))
        require(code == 101 and 'running 6 tests' in log
            and '1 passed; 5 failed;' in log and failures == EXPECTED_RED,
            'RED must fail the five intended runtime-state assertions, not compilation or infrastructure')
        record['status'] = 'expected_failure_observed'
        record['red_failures'] = sorted(failures)
        record['product_tests_passed'] = False
    else:
        require(code == 0 and '6 passed; 0 failed;' in log, 'all six actual freshness regressions must pass')
        code, log = run('layout-probe-tests', [cargo, 'test', '--manifest-path', 'ui/Cargo.toml',
            '-p', 'trill-shell', '--locked', '--offline', 'hepta_panel::probe_tests'])
        require(code == 0 and '2 passed; 0 failed;' in log, 'existing one-shot layout predicate regressed')
        code, _ = run('clippy', [cargo, 'clippy', '--manifest-path', 'ui/Cargo.toml',
            '-p', 'trill-shell', '--all-targets', '--locked', '--offline', '--', '-D', 'warnings'])
        require(code == 0, 'focused all-targets Clippy failed')
        code, _ = run('fmt', [cargo, 'fmt', '--manifest-path', 'ui/Cargo.toml', '--all', '--', '--check'])
        require(code == 0, 'workspace format check failed')
        code, _ = run('production-build', [cargo, 'build', '--manifest-path', 'ui/Cargo.toml',
            '--workspace', '--bins', '--locked', '--offline'])
        require(code == 0, 'new source-bound production ELF build failed')
        record['binaries'] = {}
        for name in ('trill-shell', 'trill-session', 'trill-ctl', 'trill-app-window'):
            binary = TARGET / 'debug' / name
            with binary.open('rb') as stream:
                header = stream.read(20)
            require(header[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', header, 18)[0] == 62,
                'new production executable is not x86_64 ELF: ' + name)
            record['binaries'][name] = {'path': str(binary), 'bytes': binary.stat().st_size,
                'sha256': digest(binary), 'elf_machine': 'x86_64'}
        record['status'] = 'passed'
        record['exit_code'] = 0
        record['product_tests_passed'] = True
    require(git(source, 'rev-parse', 'HEAD') == pin
        and not git(source, 'status', '--porcelain=v1', '--untracked-files=all'),
        'frozen source changed during actual check/build')
except BaseException as error:
    record['status'] = 'failed'
    record['error'] = str(error)
    raise
finally:
    record['finished_utc'] = datetime.now(timezone.utc).isoformat()
    record['free_bytes_after'] = shutil.disk_usage(BASE).free
    save()
    print(json.dumps({key: value for key, value in record.items() if key != 'samples'}, indent=2), flush=True)
