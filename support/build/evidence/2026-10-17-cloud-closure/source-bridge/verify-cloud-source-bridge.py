#!/usr/bin/python3
"""Compare actual Git inputs consumed by separately executed validations."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--projection-producer', required=True)
parser.add_argument('--normal-producer', required=True)
parser.add_argument('--matrix-producer', required=True)
parser.add_argument('--candidate', required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
repo = Path('/workspace/scratch/ae1a8cf05419/trillionnium-os-desktop')

def git(*arguments):
    return subprocess.check_output(['git', *arguments], cwd=repo)

requested_refs = {
    'projection': args.projection_producer, 'normal': args.normal_producer,
    'matrix': args.matrix_producer, 'candidate': args.candidate,
    'ktest': 'd895dd73a07788f6fc825fb3ca29cca22d93bb07',
    'abi': '8f3bb49ab161104063a6ebea25428c40aa884ac0',
    'control': '40ca002fac0726b366726d3353916637b29adeae',
}
resolved = {key: git('rev-parse', value + '^{commit}').decode().strip()
            for key, value in requested_refs.items()}
candidate = resolved['candidate']

def entry(commit, path):
    raw = git('ls-tree', '-z', commit, '--', path).split(b'\0')
    rows = [row for row in raw if row]
    if len(rows) != 1:
        raise ValueError('missing or ambiguous Git input: ' + commit + ':' + path)
    metadata, actual_path = rows[0].split(b'\t', 1)
    mode, kind, oid = metadata.decode().split()
    if actual_path.decode() != path or kind not in ('blob', 'tree'):
        raise ValueError('unexpected Git input kind or path')
    return {'mode': mode, 'kind': kind, 'git_object': oid}

normal_inputs = [
    'kernel/asterinas', 'support/build/minimal', 'support/build/minimal.mk',
    'support/build/kernel.sh', 'support/build/kernel-supervisor.py',
    'support/build/cleanup-manifest.py', 'support/build/verify-source.py',
    'support/build/record-qemu.py', 'support/build/check-boot.py',
]
projection_inputs = normal_inputs + [
    'support/build/repro/run.py', 'support/build/repro/profile.py',
    'support/build/repro/rustc-wrapper.py',
    'support/build/repro/cargo-metadata-wrapper.py',
]
groups = [
    ('opt-in-path-projected-kernel-build-and-boot', resolved['projection'], projection_inputs),
    ('ordinary-kernel-build-and-boot', resolved['normal'], normal_inputs),
    ('upstream-kernel-mode-regression', resolved['ktest'],
        ['kernel/asterinas', 'support/build/record-qemu.py', 'support/build/verify-source.py',
         'support/build/ktest/run.py', 'support/build/ktest/record-qemu.py',
         'support/build/ktest/check.py', 'support/build/ktest/locks']),
    ('upstream-osdk-matrix', resolved['matrix'],
        ['kernel/asterinas', 'support/build/record-qemu.py',
         'support/build/osdk-integration/run.py', 'support/build/osdk-integration/osdk.py',
         'support/build/osdk-integration/cargo.py', 'support/build/osdk-integration/record-qemu.py',
         'support/build/osdk-integration/capture.py', 'support/build/osdk-integration/archive.py']),
    ('historical-fixed-nightly-abi-host-input-identity', resolved['abi'],
        ['libs/os-abi', 'tests/abi', 'tests/golden']),
    ('historical-fixed-nightly-control-host-input-identity', resolved['control'],
        ['libs/os-control', 'tests/control']),
]
report = {'schema': 'a01-cloud-source-bridge/2', 'candidate': candidate,
          'requested_refs': requested_refs, 'resolved_commits': resolved,
          'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'scope': 'exact Git bytes/modes for listed consumed inputs; whole project trees may differ',
          'validation_executed_here': False,
          'host_scope': 'Historical ABI/control input identity bridges previously executed checks only; no candidate test/Clippy rerun or G0/G1/G2 acceptance is implied.',
          'groups': [], 'pins': []}
passed = True
for name, producer, paths in groups:
    comparisons = []
    for path in paths:
        old, new = entry(producer, path), entry(candidate, path)
        equal = old == new
        comparisons.append({'path': path, 'producer': old, 'candidate': new, 'equal': equal})
        passed &= equal
    report['groups'].append({'name': name, 'producer': producer,
                            'inputs': comparisons, 'all_equal': all(row['equal'] for row in comparisons)})
expected = ('c4b7ed575b7b32773475b194d2ad41fb6d03765b',
            '96605cf64aeae2d34f29b97e85eff9315fe10a8e', 'nightly-2026-07-21')
for commit in dict.fromkeys(resolved.values()):
    lock = json.loads(git('show', commit + ':support/upstream-lock.json'))['kernel']
    pins = tuple(lock[key] for key in ('commit', 'tree', 'toolchain'))
    empty_readme = git('show', commit + ':README.md') == b''
    passed &= pins == expected and empty_readme
    report['pins'].append({'commit': commit, 'upstream': pins[0], 'upstream_tree': pins[1],
                           'toolchain': pins[2], 'fixed_pins_equal': pins == expected,
                           'root_readme_bytes': 0 if empty_readme else len(git('show', commit + ':README.md'))})
report['source_bridge_passed'] = bool(passed)
with args.output.open('x') as stream:
    stream.write(json.dumps(report, indent=2) + '\n')
print(json.dumps({'source_bridge_passed': report['source_bridge_passed'], 'candidate': candidate,
                  'groups': {row['name']: row['all_equal'] for row in report['groups']}}, indent=2))
raise SystemExit(0 if passed else 1)
