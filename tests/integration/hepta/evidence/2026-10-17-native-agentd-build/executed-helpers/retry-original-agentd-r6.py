#!/usr/bin/env python3
"""Bounded original x86_64 Agentd link build, with immutable R4 inputs copied.

This scoped retry helper proves a source-bound build only. Runtime acceptance is a separate
execution of the reviewed original-library probe and actual desktop Session.
"""
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
base = Path('/workspace/scratch/98f315e377b2')
retained = Path('/dev/shm/trill-hepta-r4-enuzuex9')
source = base / 'next-hepta-source'
desktop = base / 'next-r6-integration'
work = base / 'next-tools/original-r6-build-02'
build_inputs = base / 'next-tools/original-r6-build-01'
work.mkdir(mode=0o700)
owner = json.loads((retained / 'ownership.json').read_text())
assert owner['root'] == str(retained)
assert owner['source_pin'] == 'f8c9419df6ddeb36ff8b522a50219981fb8d9345'
spec = importlib.util.spec_from_file_location('r6_build_gate', desktop / 'tests/integration/hepta/run_original_agentd.py')
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)
record = {
    'started_at_utc': datetime.now(timezone.utc).isoformat(),
    'qualification': 'unchanged_original_agentd_native_x86_64_link_build',
    'original_agentd_runtime': 'not_run',
    'retained_inputs_modified': False,
    'retry_of': str(build_inputs / 'receipt.json'),
    'retry_reason': 'E0460 protoc vendored metadata conflict after copying earlier check target',
    'retained_source_root': str(retained),
    'work_root': str(work),
    'minimum_free_bytes_at_build_start': gate.MIN_FREE_BYTES,
    'minimum_free_bytes_while_building': 700 * 1024**2,
    'maximum_observed_nonreclaimable_bytes': 7 * 1024**3,
    'deadline_seconds': 2400,
    'resource_samples': [],
}
(work / 'ownership.json').write_text(json.dumps({
    'purpose': record['qualification'], 'root': str(work),
    'source_pin': owner['source_pin'], 'created_by': 'current R6 audit task',
}, indent=2) + '\n')
group = None
code = 1
try:
    record['upstream'] = gate.verify_source(source)
    record['desktop_commit'] = gate.git(desktop, 'rev-parse', 'HEAD')
    record['desktop_tree'] = gate.git(desktop, 'rev-parse', 'HEAD^{tree}')
    record['gate_sha256'] = gate.sha256(desktop / 'tests/integration/hepta/run_original_agentd.py')
    previous = json.loads((build_inputs / 'receipt.json').read_text())
    assert previous['status'] == 'failed' and previous['exit_code'] == 101
    assert previous['upstream'] == record['upstream']
    assert previous['source_after'] == record['upstream']
    input_owner = json.loads((build_inputs / 'ownership.json').read_text())
    assert input_owner['root'] == str(build_inputs) and input_owner['source_pin'] == owner['source_pin']
    record['previous_receipt_sha256'] = gate.sha256(build_inputs / 'receipt.json')
    record['reuse_target'] = str(build_inputs / 'target')
    record['free_bytes_at_build_start'] = shutil.disk_usage(work).free
    if record['free_bytes_at_build_start'] < record['minimum_free_bytes_at_build_start']:
        raise RuntimeError('conservative_8_gib_build_preflight_failed')
    env = gate.build_environment(build_inputs / 'target')
    env.update({
        'CARGO_HOME': str(build_inputs / 'cargo'),
        'RUSTUP_HOME': str(retained / 'rustup'),
        'TMPDIR': str(build_inputs / 'tmp'),
        'RUSTUP_NO_UPDATE_CHECK': '1',
        'PATH': str(retained / 'cmake-3.28.3-02/cmake/data/bin') + ':' + str(retained / 'rustup/toolchains/1.95.0-x86_64-unknown-linux-gnu/bin') + ':' + str(base / 'next-tools/cargo/bin') + ':' + env.get('PATH', '/usr/bin:/bin'),
    })
    record['build_environment_paths'] = {key: env[key] for key in ['CARGO_HOME', 'RUSTUP_HOME', 'TMPDIR', 'PATH', 'CARGO_TARGET_DIR', 'CARGO_INCREMENTAL', 'CARGO_BUILD_JOBS']}
    import tomllib
    packages = [item['name'] for item in tomllib.loads((source / 'codex-rs/Cargo.lock').read_text())['package']
                if item['name'].startswith('protoc-bin-vendored')]
    packages.append('codex-code-mode-protocol')
    clean = [str(base / 'next-tools/cargo/bin/rustup'), 'run', '1.95.0', 'cargo',
             'clean', '--locked', '--offline', '--profile', 'dev-small']
    for package in packages:
        clean.extend(['-p', package])
    record['scoped_cache_cleanup'] = {'command': clean, 'packages': packages,
        'target': str(build_inputs / 'target'), 'upstream_or_retained_target_modified': False}
    gate.bounded_command(clean, source / 'codex-rs', env, work / 'scoped-cache-clean.log', 120)
    record['scoped_cache_cleanup']['status'] = 'passed'
    print('Retrying after scoped protobuf package cleanup in the new R6 target only; original source/cache and failed evidence retained.', flush=True)
    command = [str(base / 'next-tools/cargo/bin/rustup'), 'run', '1.95.0', 'cargo',
               'build', '--locked', '--offline', '--profile', 'dev-small',
               '--no-default-features', '-p', 'codex-hepta-agentd', '--bin', 'codex-hepta-agentd', '-j1']
    record['command'] = command
    record['cwd'] = str(source / 'codex-rs')
    if not gate.child_anchor_available():
        raise RuntimeError('waitable_child_anchor_unavailable')
    print('Building and linking unchanged original Agentd with Rust 1.95, offline, one job; runtime not yet started.', flush=True)
    start = time.monotonic()
    with (work / 'cargo-build.log').open('xb') as log:
        process = subprocess.Popen(command, cwd=source / 'codex-rs', env=env,
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        group = gate.ChildGroup(process)
        record['build_pid'] = process.pid
        while True:
            state = group.observe_exit()
            elapsed = time.monotonic() - start
            free = shutil.disk_usage(work).free
            sample = {'elapsed_seconds': round(elapsed, 3), 'free_bytes': free}
            for name in ['memory.current', 'memory.peak', 'memory.events']:
                path = Path('/sys/fs/cgroup') / name
                if path.is_file():
                    sample[name] = path.read_text().strip()
            memory_stat = Path('/sys/fs/cgroup/memory.stat')
            nonreclaimable = 0
            if memory_stat.is_file():
                values = {key: int(value) for key, value in (line.split() for line in memory_stat.read_text().splitlines())}
                nonreclaimable = sum(values.get(key, 0) for key in ['anon', 'shmem', 'kernel_stack', 'pagetables', 'sock', 'slab_unreclaimable', 'file_dirty'])
                sample['observed_nonreclaimable_bytes'] = nonreclaimable
            record['resource_samples'].append(sample)
            if state is not None:
                code = group.reap() if state.si_code == os.CLD_EXITED and state.si_status == 0 else gate.terminate_group(group)
                break
            if free < record['minimum_free_bytes_while_building']:
                record['stop_reason'] = 'temporary_filesystem_reserve_reached'
            elif nonreclaimable > record['maximum_observed_nonreclaimable_bytes']:
                record['stop_reason'] = 'observed_memory_reserve_reached'
            elif elapsed >= record['deadline_seconds']:
                record['stop_reason'] = 'build_deadline_exceeded'
            if 'stop_reason' in record:
                code = gate.terminate_group(group)
                break
            time.sleep(1)
    record['exit_code'] = code
    record['source_after'] = gate.verify_source(source)
    record['status'] = 'passed' if code == 0 and 'stop_reason' not in record else 'failed'
    binary = build_inputs / 'target/dev-small/codex-hepta-agentd'
    if record['status'] == 'passed':
        record['binary'] = {'path': str(binary), 'bytes': binary.stat().st_size, 'sha256': gate.sha256(binary)}
except (gate.GateError, OSError, subprocess.SubprocessError, ValueError, RuntimeError) as error:
    if group is not None and group.armed:
        gate.terminate_group(group)
    record['status'] = 'failed'
    record['error'] = {'type': type(error).__name__, 'detail': str(error)}
    code = 1
finally:
    record['ended_at_utc'] = datetime.now(timezone.utc).isoformat()
    record['free_bytes_after'] = shutil.disk_usage(work).free
    with (work / 'receipt.json').open('x') as output:
        json.dump(record, output, indent=2)
        output.write('\n')
    summary = {key: value for key, value in record.items() if key != 'resource_samples'}
    summary['resource_samples_count'] = len(record['resource_samples'])
    print(json.dumps(summary), flush=True)
sys.exit(code if code else (0 if record['status'] == 'passed' else 1))
