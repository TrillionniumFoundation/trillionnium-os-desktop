"""Task-local R6 staged build/runtime helpers; not the stock fresh-work gate."""
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
BASE = Path('/workspace/scratch/98f315e377b2')
HOME_DIR = BASE / 'next-tools/r6-original-runtime'
DESKTOP = BASE / 'next-r6-integration'
DEFAULT_COMMIT = '9d2ef72a4183460b1b4f1cdad97c1c013fa9d8dd'
ORIGINAL = BASE / 'next-hepta-source'
ORIGINAL_BUILD = BASE / 'next-tools/original-r6-build-01'
DEFAULT_AGENTD_RECEIPT = BASE / 'next-tools/original-r6-build-03/receipt.json'
RETAINED = Path('/dev/shm/trill-hepta-r4-enuzuex9')
UI_BUILD = BASE / 'next-tools/ui-r5-build-02/receipt.json'
RUSTUP = BASE / 'next-tools/cargo/bin/rustup'


def now():
    return datetime.now(timezone.utc).isoformat()


def load_gate():
    path = DESKTOP / 'tests/integration/hepta/run_original_agentd.py'
    spec = importlib.util.spec_from_file_location('r6_frozen_original_gate', path)
    gate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = gate
    spec.loader.exec_module(gate)
    return gate


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def save_new(path, value):
    with path.open('x', encoding='utf-8') as output:
        json.dump(value, output, indent=2)
        output.write('\n')


def desktop_identity(gate, expected):
    commit = gate.git(DESKTOP, 'rev-parse', 'HEAD')
    require(commit == expected, 'desktop HEAD differs from requested frozen commit')
    require(not gate.git(DESKTOP, 'status', '--porcelain=v1', '--untracked-files=all'),
            'desktop source worktree must be clean')
    require((DESKTOP / 'README.md').stat().st_size == 0, 'root README is not empty')
    paths = [
        'tests/integration/hepta/run_original_agentd.py',
        'tests/integration/hepta/original_agentd_probe.rs',
        'tests/integration/hepta/original_session_probe.rs',
        'services/hepta-os/Cargo.toml', 'services/hepta-os/Cargo.lock',
        'services/hepta-os/UPSTREAM_CONTRACT.json', 'ui/Cargo.toml', 'ui/Cargo.lock',
    ]
    return {
        'commit': commit, 'tree': gate.git(DESKTOP, 'rev-parse', 'HEAD^{tree}'),
        'clean': True,
        'subtrees': {path: gate.git(DESKTOP, 'rev-parse', f'HEAD:{path}')
                     for path in ['services/hepta-os', 'ui']},
        'inputs': {path: gate.sha256(DESKTOP / path) for path in paths},
    }


def binary_identity(gate, path):
    path = path.resolve(strict=True)
    require(path.is_file() and os.access(path, os.X_OK), 'binary is not an executable regular file')
    with path.open('rb') as stream:
        header = stream.read(64)
    require(len(header) == 64 and header[:4] == b'\x7fELF'
            and header[4] == 2 and header[5] == 1,
            'binary must be 64-bit little-endian ELF')
    machine = struct.unpack_from('<H', header, 18)[0]
    require(machine == 62, 'this local qualification requires native x86_64 ELF')
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': gate.sha256(path),
            'elf_class': 64, 'elf_machine': machine, 'architecture': 'x86_64'}


def original_build_identity(gate, receipt_path=DEFAULT_AGENTD_RECEIPT):
    path = Path(receipt_path).resolve(strict=True)
    receipt = json.loads(path.read_text())
    require(receipt.get('status') == 'passed' and receipt.get('exit_code') == 0,
            'original Agentd link build has not passed')
    require(receipt.get('qualification') == 'unchanged_original_agentd_native_x86_64_link_build',
            'wrong original build receipt')
    admission = None
    previous_attempt = None
    recovery = None
    previous_migrations = []
    if receipt.get('fresh_full_gate_preflight_applied') is False:
        require(receipt.get('resume_of_same_target') is True,
                'staged resume must explicitly reuse the same admitted target')
        require(path == BASE / 'next-tools/original-r6-build-03/receipt.json',
                'this reviewed staged-resume contract is specific to attempt 03')
        admission = receipt.get('initial_admission', {})
        initial_path = ORIGINAL_BUILD / 'receipt.json'
        require(admission.get('receipt_path') == str(initial_path)
                and admission.get('receipt_sha256') == gate.sha256(initial_path),
                'staged resume is not bound to the immutable initial admission')
        initial = json.loads(initial_path.read_text())
        require(initial.get('minimum_free_bytes_at_build_start') == gate.MIN_FREE_BYTES
                and initial.get('free_bytes_at_build_start', 0) >= gate.MIN_FREE_BYTES
                and admission.get('minimum_free_bytes') == initial['minimum_free_bytes_at_build_start']
                and admission.get('free_bytes_at_admission') == initial['free_bytes_at_build_start'],
                'the actual original eight-GiB admission was not preserved')
        require(initial.get('upstream') == receipt.get('upstream')
                and initial.get('source_after') == receipt.get('source_after'),
                'staged resume changed the originally admitted source')
        previous_attempt = receipt.get('previous_attempt', {})
        previous_path = BASE / 'next-tools/original-r6-build-02/receipt.json'
        require(previous_attempt.get('receipt_path') == str(previous_path)
                and previous_attempt.get('receipt_sha256') == gate.sha256(previous_path),
                'staged resume is not bound to preserved failed attempt 02')
        previous = json.loads(previous_path.read_text())
        require(previous_attempt.get('status') == previous.get('status') == 'failed'
                and previous_attempt.get('stop_reason') == previous.get('stop_reason') == 'observed_memory_reserve_reached',
                'attempt 02 memory-reserve failure must remain explicit')
        recovery = receipt.get('resource_recovery', {})
        recovery_path = BASE / 'next-tools/r6-retained-cache-migration-03/receipt.json'
        require(recovery.get('receipt_path') == str(recovery_path)
                and recovery.get('receipt_sha256') == gate.sha256(recovery_path),
                'staged resume is not bound to its verified cache migration')
        require(json.loads(recovery_path.read_text()).get('status') == 'passed',
                'cache migration verification did not pass')
        for ordinal in ['01', '02']:
            failed_migration_path = BASE / f'next-tools/r6-retained-cache-migration-{ordinal}/receipt.json'
            failed_migration = json.loads(failed_migration_path.read_text())
            require(failed_migration.get('status') == 'failed',
                    'failed prior migration receipts must remain preserved')
            previous_migrations.append({'receipt_path': str(failed_migration_path),
                                        'receipt_sha256': gate.sha256(failed_migration_path), 'status': 'failed'})
        require(receipt.get('minimum_free_bytes_while_building') == 700 * 1024**2
                and receipt.get('maximum_observed_nonreclaimable_bytes') == 7 * 1024**3,
                'staged resume must retain the active disk and memory guards')
    else:
        require(receipt.get('minimum_free_bytes_at_build_start') == gate.MIN_FREE_BYTES
                and receipt.get('free_bytes_at_build_start', 0) >= gate.MIN_FREE_BYTES,
                'original build receipt did not satisfy the existing eight-GiB admission estimate')
    require(receipt.get('source_after') == gate.verify_source(ORIGINAL)
            and receipt.get('upstream') == receipt['source_after'],
            'fixed original source changed since Agentd build')
    expected_path = ORIGINAL_BUILD / 'target/dev-small/codex-hepta-agentd'
    require(receipt['binary']['path'] == str(expected_path), 'unexpected original Agentd binary path')
    actual = binary_identity(gate, expected_path)
    require(all(actual[key] == receipt['binary'][key] for key in ['path', 'bytes', 'sha256']),
            'original Agentd ELF no longer matches its real build receipt')
    prior = receipt.get('previous_receipt_sha256')
    if prior is not None:
        require(prior == gate.sha256(ORIGINAL_BUILD / 'receipt.json'),
                'retry is not bound to the preserved first-attempt receipt')
    return {'receipt_path': str(path), 'receipt_sha256': gate.sha256(path),
            'original': receipt['source_after'], 'binary': actual,
            'previous_attempt_receipt_sha256': prior,
            'initial_admission': admission, 'previous_attempt': previous_attempt, 'resource_recovery': recovery,
            'previous_failed_migrations': previous_migrations,
            'fresh_full_gate_preflight_applied_at_this_attempt': receipt.get('fresh_full_gate_preflight_applied', True),
            'stock_fresh_work_gate_reexecuted': False,
            'source_build_kind': 'new_R6_target_copied_from_retained_warm_cache'}


def ui_inputs(gate, desktop):
    receipt = json.loads(UI_BUILD.read_text())
    require(receipt.get('status') == 'passed' and receipt.get('exit_code') == 0,
            'UI production build receipt did not pass')
    require(receipt['source_commit'] == '35f379101c0863027e971ccb91faf8da71cf929c',
            'unexpected prior UI build source')
    original_ui_tree = gate.git(DESKTOP, 'rev-parse', receipt['source_commit'] + ':ui')
    require(original_ui_tree == desktop['subtrees']['ui'],
            'UI production source differs from the actual R5 ELF build')
    closure = {}
    # Session links this path dependency. Its documentation may advance
    # independently, so compare the executable source and Cargo inputs.
    for path in ['ui', 'services/hepta-os/src', 'services/hepta-os/Cargo.toml', 'services/hepta-os/Cargo.lock']:
        built = gate.git(DESKTOP, 'rev-parse', receipt['source_commit'] + ':' + path)
        current = gate.git(DESKTOP, 'rev-parse', desktop['commit'] + ':' + path)
        require(built == current, f'UI linked source input differs from actual R5 ELF build: {path}')
        closure[path] = {'built_git_object': built, 'current_git_object': current, 'identical': True}
    outputs = {}
    for role, name in [('session', 'trill-session'), ('ctl', 'trill-ctl')]:
        item = receipt['binaries'][name]
        actual = binary_identity(gate, Path(item['path']))
        require(all(actual[key] == item[key] for key in ['path', 'bytes', 'sha256']),
                f'{name} differs from its real production build')
        outputs[role] = actual
    return {'build_receipt_path': str(UI_BUILD), 'build_receipt_sha256': gate.sha256(UI_BUILD),
            'source_commit': receipt['source_commit'], 'source_tree': receipt['source_tree'],
            'current_ui_subtree_matches_build': True, 'linked_source_inputs': closure, 'binaries': outputs}


def environment(gate, target, original=False):
    env = gate.build_environment(target)
    if original:
        env.update({
            'CARGO_HOME': str(ORIGINAL_BUILD / 'cargo'),
            'RUSTUP_HOME': str(RETAINED / 'rustup'),
            'TMPDIR': str(ORIGINAL_BUILD / 'tmp'),
            'PATH': str(RETAINED / 'cmake-3.28.3-02/cmake/data/bin') + ':'
                    + str(RETAINED / 'rustup/toolchains/1.95.0-x86_64-unknown-linux-gnu/bin')
                    + ':' + str(BASE / 'next-tools/cargo/bin') + ':/usr/bin:/bin',
        })
    else:
        env.update({
            'CARGO_HOME': str(BASE / 'next-tools/cargo'),
            'RUSTUP_HOME': str(BASE / 'next-tools/rustup'),
            'PATH': str(BASE / 'next-tools/cargo/bin') + ':/usr/bin:/bin',
        })
    env.update({'CARGO_NET_OFFLINE': 'true', 'RUSTUP_NO_UPDATE_CHECK': '1',
                'CARGO_BUILD_JOBS': '1', 'CARGO_INCREMENTAL': '0'})
    return env


def checked_command(gate, command, cwd, env, log, seconds, record):
    """Use the reviewed waitable-child guard plus explicit resource ceilings."""
    require(gate.child_anchor_available(), 'waitable child anchor unavailable')
    item = {'command': [str(part) for part in command], 'cwd': str(cwd),
            'started_at_utc': now(), 'status': 'running', 'deadline_seconds': seconds,
            'minimum_disk_reserve_bytes': 700 * 1024**2,
            'maximum_nonreclaimable_bytes': 7 * 1024**3, 'resource_samples': []}
    record['steps'].append(item)
    group = None
    try:
        with log.open('xb') as output:
            process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                       stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
            group = gate.ChildGroup(process)
            item['pid'] = process.pid
            started = time.monotonic()
            while True:
                state = group.observe_exit()
                sample = {'elapsed_seconds': round(time.monotonic() - started, 3),
                          'free_bytes': shutil.disk_usage(HOME_DIR).free}
                memory = Path('/sys/fs/cgroup/memory.stat')
                if memory.is_file():
                    values = {k: int(v) for k, v in (line.split() for line in memory.read_text().splitlines())}
                    sample['nonreclaimable_bytes'] = sum(values.get(k, 0) for k in
                        ['anon', 'shmem', 'kernel_stack', 'pagetables', 'sock', 'slab_unreclaimable', 'file_dirty'])
                item['resource_samples'].append(sample)
                if state is not None:
                    code = group.reap() if state.si_code == os.CLD_EXITED and state.si_status == 0 else gate.terminate_group(group)
                    item['exit_code'] = code
                    require(code == 0, f'command failed with exit {code}: {log.name}')
                    break
                require(sample['elapsed_seconds'] < seconds, f'command deadline exceeded: {log.name}')
                require(sample['free_bytes'] >= item['minimum_disk_reserve_bytes'], 'temporary disk reserve reached')
                require(sample.get('nonreclaimable_bytes', 0) <= item['maximum_nonreclaimable_bytes'], 'memory reserve reached')
                time.sleep(1)
        item['status'] = 'passed'
    except BaseException:
        item['status'] = 'failed'
        raise
    finally:
        if group is not None and group.armed:
            gate.terminate_group(group)
        item['ended_at_utc'] = now()
        if log.exists():
            item['log'] = {'path': str(log), 'bytes': log.stat().st_size, 'sha256': gate.sha256(log)}
