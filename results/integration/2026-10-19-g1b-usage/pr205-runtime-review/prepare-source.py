#!/usr/bin/env python3
"""Read exact Git objects for the independent artifact review; never build/run."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess

HEAD = '4d3011cf9f92e25fc1b0d7371e9cdbbd5a8b7930'
TREE = '8eb809136a402cc54ba049b1e40dd174308c923f'
REPO = Path('/workspace/scratch/499c7902de8e/r11-g1b-usage')
OUT = Path(__file__).resolve().parent
env = dict(os.environ, GIT_NO_LAZY_FETCH='1')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO, env=env)


assert git('rev-parse', HEAD + '^{tree}').decode().strip() == TREE
before = git('rev-parse', 'HEAD').decode().strip()
entries = git('ls-tree', '-r', '-z', HEAD).split(b'\0')
files = {}
child = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=REPO, env=env,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE)
selected = {
    '.github/workflows/a06-kernel.yml',
    'support/build/ktest/run.py', 'support/build/ktest/check.py',
    'support/build/ktest/record-qemu.py',
    'tests/kernel/control/run_queryabi_candidate_guest.py',
    'tests/kernel/control/run_queryabi_guest.py',
    'tests/organ_backend/run_cpu_owner_negative.py',
    'tests/organ_backend/run_cpu_config_settlement.py',
    'tests/organ_backend/run_candidate_matrix.py',
    'tests/organ_backend/run_guest_probe.py',
    'tests/organ_backend/smp2/run_parallel_candidate.py',
    'tests/workloads/linux/run_scm_rights_cloexec_guest.py',
    'tests/workloads/linux/run_rlimit_nofile_guest.py',
    'tests/workloads/linux/run_full_ubuntu_profile.py',
    'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/native/usage_tests.rs',
}
for entry in entries:
    if not entry:
        continue
    meta, raw_path = entry.split(b'\t', 1)
    mode, kind, blob = meta.decode().split()
    assert kind == 'blob' and mode in ('100644', '100755', '120000')
    path = raw_path.decode('utf-8')
    child.stdin.write(blob.encode() + b'\n')
    child.stdin.flush()
    found, found_kind, size = child.stdout.readline().decode().split()
    assert found == blob and found_kind == 'blob'
    size = int(size)
    data = child.stdout.read(size)
    assert len(data) == size and child.stdout.read(1) == b'\n'
    actual_blob = hashlib.sha1(b'blob ' + str(size).encode() + b'\0' + data).hexdigest()
    assert actual_blob == blob
    files[path] = {'mode': mode, 'git_blob': blob, 'size': size, 'sha256': hashlib.sha256(data).hexdigest()}
    if path in selected or (path.startswith('tests/organ_backend/') and path.endswith('_negative.patch')):
        destination = OUT / 'fixed-source' / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
child.stdin.close()
assert child.wait() == 0
after = git('rev-parse', 'HEAD').decode().strip()
delta = git('diff', '--name-status', 'f9669912e2886190429187e14753d62b2060bd5f', HEAD).decode()
assert delta.strip() == 'M\ttests/spec/test_a06_final_accounting_source.py', delta
report = {
    'schema': 1, 'generated_at_utc': datetime.now(timezone.utc).isoformat(),
    'expected_run': 39240728276, 'head': HEAD, 'tree': TREE,
    'basis': 'Exact committed Git blob bytes; not current worktree mutable bytes or PR prose. Every blob SHA-1 is checked while SHA-256 is computed.',
    'repo_head_before': before, 'repo_head_after': after,
    'file_count': len(files), 'total_source_bytes': sum(f['size'] for f in files.values()),
    'delta_from_initial_f966': delta,
    'files': files,
    'scope': 'Read-only preparation, not an artifact pass and not a product/test execution.',
}
destination = OUT / 'source-git-map.json'
encoded = (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode()
destination.write_bytes(encoded)
print(json.dumps({'head': HEAD, 'tree': TREE, 'file_count': len(files),
                  'total_source_bytes': report['total_source_bytes'],
                  'source_map_bytes': len(encoded), 'source_map_sha256': hashlib.sha256(encoded).hexdigest(),
                  'fixed_source_files': len([p for p in (OUT / 'fixed-source').rglob('*') if p.is_file()])}))
