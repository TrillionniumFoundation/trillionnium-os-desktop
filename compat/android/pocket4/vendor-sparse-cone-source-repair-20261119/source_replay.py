#!/usr/bin/env python3
"""Replay the exact sparse-cone repair and run disposable real-Git controls.

No operational AOSP checkout, vendor build, Android process, or app is started.
"""
from pathlib import Path, PurePosixPath
import hashlib
import json
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
ACTUAL = {'recorded/CONTROL-RESULT-local-r1.json': (51448, '841ad38ca4dc7b90e7891cd43bef54f96f3b91a1d9ede7b7d59c99d317ac1090'), 'observations/all-sparse-readonly-diagnosis.json': (296307, '52068005b7095d1afd372816e411903ac3a397e8b2dea18707e44affd2535d73'), 'observations/actual-sparse-observation.jsonl': (35905, 'f8c8c8d3de96b8599d388cfd9ef03c55b847c162bfe43a772e332ad9e1a80db7'), 'observations/two-prebuilt-tree-observation.jsonl': (6300, '318efdb1a52810a2b5c3a244a73e98f932b909485c07e5ec850fa56266c25db2'), 'observations/prebuilt-object-size-observation.jsonl': (1431, 'd3ad4af3b89afe7cbbab23a01b096092e75bb61c0f8fccb52445d5797e88d7ee'), 'observations/prebuilt-allocation-estimate.json': (1521, 'ce1ae1bdafc7d50c7347cb49c627495ca5edbf981c90d6854caca563e1a0ab78'), 'observations/original-rust-verify-functions.json': (2870, '0141ebacbcbf15024071c0f7051b8eb6ce13baa138cf7e403a425de39859e36f'), 'history/outer-terminal.json': (51659, '7004ae364d219b9a835e70b16df552233e7e18d4b78e4d701b552e38942ad82b'), 'history/build-observation.json': (53758, 'c732faef3943ee29743b585f6ab1f785f3cfe3c68ada838de4f573188e3bf16a'), 'history/recovery-observation.json': (7534, '747de3669d663cab07fcc1a7fc271b164323a0f07cb93ac0813a483436679d7e'), 'history/outer-admission.json': (2252, '4c5b9284fc506c80f581fc038d712ab3016c97f5400a4cbe0fe037c94139faac'), 'history/outer-resource-probe.json': (319, 'a5119ce3312f53d0a5b6b2a33f39ea96088a61464f4f132983c06ab058ad461d')}


def need(value, message):
    if not value:
        raise ValueError(message)


def read(name):
    relative = PurePosixPath(name)
    need(not relative.is_absolute() and '..' not in relative.parts and str(relative) == name,
         'canonical relative packet path')
    path = ROOT / name
    info = path.lstat()
    need(path.resolve() == path and stat.S_ISREG(info.st_mode) and info.st_nlink == 1
         and info.st_size <= 2 * 1024 ** 2, 'bounded ordinary packet input')
    return path.read_bytes()


def sha(body):
    return hashlib.sha256(body).hexdigest()


def decoded(body):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            need(key not in value, 'duplicate JSON key')
            value[key] = item
        return value
    def invalid(value):
        raise ValueError('nonfinite JSON value')
    return json.loads(body, object_pairs_hook=unique, parse_constant=invalid)


def main():
    inventory = {}
    for line in read('FILES.sha256').decode('ascii').splitlines():
        digest, name = line.split('  ', 1)
        need(name not in inventory and len(digest) == 64 and sha(read(name)) == digest,
             'unique exact packet member: ' + name)
        inventory[name] = digest
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file()}
    need(actual == set(inventory) | {'FILES.sha256'}, 'complete packet inventory')
    manifest = decoded(read('MANIFEST.json'))
    need(manifest['schema'] == 'pocket4-vendor-sparse-cone-source-repair-v1'
         and manifest['production_ready'] is False and manifest['runtime_qualified'] is False,
         'bounded source-evidence scope')
    need({row['path'] for row in manifest['files']} == actual - {'MANIFEST.json', 'FILES.sha256'}
         and len(manifest['files']) == len(actual) - 2, 'complete manifest members')
    for row in manifest['files']:
        body = read(row['path'])
        need(len(body) == row['bytes'] and sha(body) == row['sha256'], 'manifest member pin')
    for name, (size, digest) in ACTUAL.items():
        body = read(name)
        need(len(body) == size and sha(body) == digest, 'unaltered actual record: ' + name)
    terminal = decoded(read('history/outer-terminal.json'))
    before = decoded(read('history/build-observation.json'))
    after = decoded(read('history/recovery-observation.json'))
    need(terminal['passed'] is False and terminal['all_owned_units_retired'] is True
         and terminal['all_created_children_reaped'] is True
         and terminal['normal_recovery_verified'] is False,
         'original failed R12 remains failed and retired')
    for observation, commands in (
        (before, ['verify-full651-before']),
        (after, ['normal-source-recovery', 'verify-full651-after']),
    ):
        need(len(observation['errors']) == 1
             and observation['errors'][0]['error'] == "RuntimeError('actual sparse cones differ from original plan')"
             and [c['name'] for c in observation['commands']] == commands,
             'exact original R12 failure before reconciliation or compilation')
        need(all(c['exit_code'] == 0 and c['error'] is None
                 and c['actual_child_reaped'] is True
                 and c['original_pidfd_held_until_reaped'] is True
                 and c['owned_descendants_remaining'] == 0 for c in observation['commands']),
             'actual original normal verification and retirement')
        need(observation['production_ready'] is False and observation['runtime_qualified'] is False
             and observation['installed'] is False, 'original runtime scope unchanged')
    diagnosis = decoded(read('observations/all-sparse-readonly-diagnosis.json'))
    need(diagnosis['project_count'] == 651 and diagnosis['sparse_project_count'] == len(diagnosis['rows']) == 446
         and diagnosis['passed'] is False and diagnosis['source_mutations'] is False
         and diagnosis['body_verification_claimed'] is False
         and diagnosis['plan_and_manifest_bytes_unchanged'] is True,
         'exact historical whole sparse-list observation')
    failed = {row['project']: row for row in diagnosis['rows'] if row['passed'] is False}
    need(set(failed) == {'prebuilts/clang/host/linux-x86', 'prebuilts/rust-toolchain/linux-x86'}
         and failed['prebuilts/clang/host/linux-x86']['missing'] == ['clang-r547379', 'clang-r563880c']
         and failed['prebuilts/rust-toolchain/linux-x86']['missing'] == ['1.91.1', '1.92.0']
         and all(row['extra'] == [] for row in failed.values()),
         'real missing toolchain cones are preserved, not treated as redundant')
    cts = next(row for row in diagnosis['rows'] if row['project'] == 'cts')
    need(cts['planned_paths'] == 534 and cts['canonical_paths'] == cts['actual_paths'] == 261
         and cts['passed'] is True, 'observed CTS ancestor pruning')
    recorded = decoded(read('recorded/CONTROL-RESULT-local-r1.json'))
    need(recorded['passed'] is True and recorded['tests_run'] == 13
         and recorded['original_helper_sha256'] == sha(read('source/original/vendor_source_bookends_r12.py'))
         and recorded['successor_helper_sha256'] == sha(read('source/vendor_source_bookends_r13.py')),
         'original finite real-Git controls bind both exact helpers')
    with tempfile.TemporaryDirectory(prefix='p4-cone-packet-controls-') as work:
        output = Path(work) / 'controls.json'
        subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'source/test_sparse_cone_bookends.py'),
                        '--result', str(output)], check=True, timeout=45)
        fresh = decoded(output.read_bytes())
        need(fresh['passed'] is True and fresh['tests_run'] == 13
             and fresh['successor_helper_sha256'] == recorded['successor_helper_sha256']
             and fresh['original_helper_sha256'] == recorded['original_helper_sha256']
             and fresh['operational_source_mutations'] == fresh['compilers_started'] == fresh['VMs_started'] == 0,
             'fresh real-Git controls without operational source execution')
    print(json.dumps({'state': 'PASS_SOURCE_REPLAY_ONLY', 'packet_files': len(actual),
        'fresh_real_git_controls_passed': 13, 'historical_R12_failure_preserved': True,
        'historical_missing_toolchain_cones_preserved': 4,
        'operational_AOSP_reconcile_executed_by_this_command': False,
        'vendor_build_executed_by_this_command': False, 'Android_starts': 0,
        'runtime_qualified': False, 'production_ready': False}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
