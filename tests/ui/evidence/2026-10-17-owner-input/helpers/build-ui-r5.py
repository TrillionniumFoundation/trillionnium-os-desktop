#!/usr/bin/env python3
"""Build current native UI sources in the new private dependency target."""
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
desktop = base / 'next-native-ci'
allocation = json.loads((base / 'next-tools/ui-r5-target.json').read_text())
root = Path(allocation['root'])
assert json.loads((root / 'ownership.json').read_text())['root'] == str(root)
evidence = base / 'next-tools/ui-r5-build'
evidence.mkdir(mode=0o700)
spec = importlib.util.spec_from_file_location('ui_r5_process_guard', desktop / 'tests/integration/hepta/run_original_agentd.py')
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)
record = {'started_at_utc': datetime.now(timezone.utc).isoformat(),
          'qualification': 'native_host_ui_build_only', 'source_commit': gate.git(desktop, 'rev-parse', 'HEAD'),
          'source_tree': gate.git(desktop, 'rev-parse', 'HEAD^{tree}'),
          'target': allocation['target'], 'previous_cache_mutated': False,
          'minimum_free_bytes': 48 * 1024**2, 'memory_stop_threshold_bytes': 7 * 1024**3,
          'deadline_seconds': 240, 'samples': []}
assert record['source_commit'] == 'b04a9e5ca7acd78272ddea325e752a7d6b252c9b'
env = os.environ.copy()
env.update({'RUSTUP_HOME': str(base / 'next-tools/rustup'), 'CARGO_HOME': str(base / 'next-tools/cargo'),
            'PATH': str(base / 'next-tools/cargo/bin') + ':' + env.get('PATH', ''),
            'RUSTUP_TOOLCHAIN': '1.88.0', 'CARGO_TARGET_DIR': allocation['target'],
            'CARGO_INCREMENTAL': '0', 'CARGO_PROFILE_DEV_DEBUG': '0', 'CARGO_PROFILE_TEST_DEBUG': '0',
            'CARGO_BUILD_JOBS': '1', 'TMPDIR': str(root)})
command = [str(base / 'next-tools/cargo/bin/cargo'), 'build', '--manifest-path', 'ui/Cargo.toml', '--workspace', '--locked', '--offline']
record['command'] = command
group = None
code = 1
try:
    start = time.monotonic()
    with (evidence / 'cargo-build.log').open('xb') as log:
        process = subprocess.Popen(command, cwd=desktop, env=env, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        group = gate.ChildGroup(process)
        while True:
            state = group.observe_exit()
            sample = {'elapsed_seconds': round(time.monotonic() - start, 3), 'free_bytes': shutil.disk_usage(root).free}
            memory = Path('/sys/fs/cgroup/memory.stat')
            if memory.is_file():
                values = {k: int(v) for k,v in (line.split() for line in memory.read_text().splitlines())}
                sample['shared_cgroup_nonreclaimable_bytes'] = sum(values.get(k,0) for k in ['anon','shmem','kernel_stack','pagetables','sock','slab_unreclaimable','file_dirty'])
            record['samples'].append(sample)
            if state is not None:
                code = group.reap() if state.si_code == os.CLD_EXITED and state.si_status == 0 else gate.terminate_group(group)
                break
            if sample['free_bytes'] < record['minimum_free_bytes']:
                record['stop_reason'] = 'temporary_disk_reserve_reached'
            elif sample.get('shared_cgroup_nonreclaimable_bytes',0) > record['memory_stop_threshold_bytes']:
                record['stop_reason'] = 'shared_memory_reserve_reached'
            elif sample['elapsed_seconds'] >= record['deadline_seconds']:
                record['stop_reason'] = 'build_deadline_reached'
            if 'stop_reason' in record:
                code = gate.terminate_group(group)
                break
            time.sleep(0.2)
    record['exit_code'] = code
    record['status'] = 'passed' if code == 0 and 'stop_reason' not in record else 'failed'
    if record['status'] == 'passed':
        record['binaries'] = {}
        for name in ['trill-shell','trill-session','trill-ctl','trill-app-window']:
            path = Path(allocation['target']) / 'debug' / name
            record['binaries'][name] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': gate.sha256(path)}
finally:
    if group is not None and group.armed:
        gate.terminate_group(group)
    record['ended_at_utc'] = datetime.now(timezone.utc).isoformat()
    record['free_bytes_after'] = shutil.disk_usage(root).free
    with (evidence / 'receipt.json').open('x') as output:
        json.dump(record, output, indent=2)
        output.write('\n')
    summary = {k:v for k,v in record.items() if k != 'samples'}
    summary['sample_count'] = len(record['samples'])
    print(json.dumps(summary), flush=True)
sys.exit(code if code else (0 if record['status'] == 'passed' else 1))
