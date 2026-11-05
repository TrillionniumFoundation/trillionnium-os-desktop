#!/usr/bin/env python3
"""Derive a new source-only composer. No remote operations or compiler execution."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE.parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2) + '\n').encode()


def pinned(path, expected):
    raw = path.read_bytes()
    assert sha(raw) == expected, str(path)
    return raw


def put(name, raw):
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        assert stream.write(raw) == len(raw)


def main():
    old = pinned(WORK / 'candidate06-nofile-integration-02/compose.py',
                 'b489e8ac7353c09c90f7c2f65b0b53c10cd0619c13308add7653dec56ba8d642').decode()
    base = pinned(WORK / 'full-engine-candidate06-go5-bound-01/combined_build_streaming.py',
                  'b42ee9229dfac7b62bb04472e39568867fc53d695389b2214c8bbfd9e0f83619')
    before = pinned(WORK / 'candidate06-nofile-integration-02/candidate-06-source-manifest.expected.json',
                    '3c780a398075f77d1f6b1c477c6ceaa35349de17b88e77896aa22820259c0376')
    delta = json.loads((WORK / 'host-glibc-uapi-next01/SOURCE_DELTA.json').read_bytes())
    assert delta['changed_existing'] == 4 and delta['added_files'] == 1
    parent = json.loads(before)
    value = json.loads(before)
    ancestry = 'Host glibc2.17 UAPI declarations; exact five-TU compiler control separately pinned by candidate07 composition'
    changes = {}
    for row in delta['changes']:
        name = 'engine/' + row['path']
        changes[name] = (row['before_sha256'], row['after_sha256'], row['bytes'])
        assert value['files'].get(name) == row['before_sha256']
        if row['before_sha256'] is None:
            assert name not in value['ancestry']
            value['ancestry'][name] = []
        else:
            assert value['ancestry'][name][-1]['sha256'] == row['before_sha256']
        value['files'][name] = row['after_sha256']
        value['ancestry'][name].append({'source': ancestry, 'prior_sha256': row['before_sha256'],
                                        'sha256': row['after_sha256']})
        raw = pinned(WORK / 'host-glibc-uapi-next01/candidate' / row['path'], row['after_sha256'])
        assert len(raw) == row['bytes']
        put('delta/' + row['path'], raw)
    new_manifest = encoded(value)
    assert len(value['files']) == len(value['ancestry']) == 949
    assert sum(name.startswith('engine/') for name in value['files']) == 926
    assert {k: v for k, v in parent['files'].items() if k not in changes} == {
        k: v for k, v in value['files'].items() if k not in changes}
    assert len(parent['files'].keys() - changes.keys()) == 944
    put('references/base-source-contract.py', base)
    put('references/candidate-06-source-manifest.json', before)
    put('candidate-07-source-manifest.expected.json', new_manifest)
    put('expected-engine926.json', encoded({name[7:]: h for name, h in value['files'].items()
                                          if name.startswith('engine/')}))
    constants = '''#!/usr/bin/env python3
"""Create only candidate07 from candidate06 plus four include edits and one private UAPI header."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

HERE = Path('/home/alex/work/pocket4-candidate07-host-uapi-composition-source-01-20261105')
OWNER = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01')
PARENT = OWNER / 'overlay-reconstruction-10/candidate-06'
PARENT_MANIFEST = PARENT.parent / 'candidate-06-source-manifest.json'
PARENT_SHA = '3c780a398075f77d1f6b1c477c6ceaa35349de17b88e77896aa22820259c0376'
PARENT_COMPOSITION_SHA = 'f49173e0527e336f5d5ff5af489a2dfa97ceaba247f0fc3657c9a68ca242922a'
ROOT = OWNER / 'overlay-reconstruction-11'
DESTINATION = ROOT / 'candidate-07'
MANIFEST_SHA = MANIFEST_PLACEHOLDER
BASE_CONTRACT_SHA = 'b42ee9229dfac7b62bb04472e39568867fc53d695389b2214c8bbfd9e0f83619'
GATE_ROOT = Path('/home/alex/work/pocket4-native-host-glibc-uapi-tu-control-01-20261105')
GATE_REPORT = GATE_ROOT / 'attempt01/result.json'
GATE_SHA = '5a09aa094c960a2bcc2d357fa732aac0cdb95203d25d3b690ced62497bb1c1d1'
GATE_CONTROLLER_SHA = 'dc1c91c1c0b84cdd8ca9e487fa7b043da66c0c0c5ce49c4706c55c71c17f48e3'
FAILED_INPUTS_SHA = '8206e05341acd16dccf6d5b0e8e3ad63d83ebc095842f5efbfea1dfdb7105b4d'
ANCESTRY = ANCESTRY_PLACEHOLDER
DELTA = DELTA_PLACEHOLDER

'''
    constants = constants.replace('MANIFEST_PLACEHOLDER', repr(sha(new_manifest)))
    constants = constants.replace('ANCESTRY_PLACEHOLDER', repr(ancestry))
    constants = constants.replace('DELTA_PLACEHOLDER', repr(changes))
    common = old[old.index('def need('):old.index('def proof_contract():')]
    proof = '''def proof_contract():
    # The old Android/host 26-case proof is validated by the exact unchanged
    # candidate06 source contract. It does not become a new runtime test here.
    raw = pinned(GATE_REPORT, GATE_SHA, 1048576)
    gate = json.loads(raw)
    pinned(GATE_ROOT / 'source/compile_tus.py', GATE_CONTROLLER_SHA, 65536)
    need(gate['state'] == 'PASS' and gate['baseline_reproduced'] is True and
         gate['full_engine_built'] is False and gate['objects_executed'] is False and
         gate['installed'] is False and gate['Main_actions'] == 0 and
         gate['sources_modified_outside_owned_root'] is False and
         gate['kernel_ABI_compatibility_runtime_not_claimed_by_compilation'] is True and
         not gate['input_changes'] and not gate['observed_signals'] and
         gate['owned_resource_gate']['pass'] is True,
         'actual complete TU proof or resource qualification differs')
    cleanup = gate['cleanup']
    need(not cleanup['forced_cleanup'] and not cleanup['remaining'] and not cleanup['errors'],
         'actual TU control cleanup incomplete')
    tus = ['proc_maps_provenance', 'proc_maps_raw_metadata_owner', 'proc_maps_fd_owner',
           'proc_maps_path', 'proc_maps_factory_wire']
    need([row['name'] for row in gate['compiled_TUs']] == tus and
         all(row['original_warning_target_and_sysroot_flags_preserved'] is True
             for row in gate['compiled_TUs']), 'complete original-flags TU set differs')
    labels = ['compiler-version', 'host-macros', 'preimage-provenance']
    for name in tus:
        labels += [name + '-dependencies', name + '-compile']
    commands = gate['commands']
    need([row['label'] for row in commands] == labels and
         all(not row['timed_out'] for row in commands), 'actual TU command set differs')
    need(commands[2]['returncode'] != 0 and commands[2]['expected_failure'] is True and
         all(row['returncode'] == 0 for i, row in enumerate(commands) if i != 2),
         'original missing-header negative or candidate compiles differ')
    dependencies = gate['actual_system_and_generated_dependencies']
    for name, (before, after, size) in DELTA.items():
        path = str(GATE_ROOT / 'source/candidate' / name[len('engine/'):])
        need(dependencies[path]['sha256'] == after and dependencies[path]['bytes'] == size,
             'new composition input was not an actual compiled input: ' + name)
        pinned(Path(path), after, size)
    return gate


def derive(parent):
    need(set(parent) == {'schema', 'files', 'ancestry'} and parent['schema'] == 1 and
         len(parent['files']) == len(parent['ancestry']) == 948, 'parent manifest schema differs')
    value = json.loads(json.dumps(parent))
    for name, (before, after, size) in DELTA.items():
        if before is None:
            need(name not in value['files'] and name not in value['ancestry'],
                 'new private header already exists in parent')
            value['ancestry'][name] = []
        else:
            need(value['files'][name] == before and value['ancestry'][name][-1]['sha256'] == before,
                 'delta preimage/ancestry differs')
        value['files'][name] = after
        value['ancestry'][name].append({'source': ANCESTRY, 'prior_sha256': before, 'sha256': after})
    raw = (json.dumps(value, indent=2) + '\\n').encode()
    need(sha(raw) == MANIFEST_SHA and len(value['files']) == 949 and
         sum(name.startswith('engine/') for name in value['files']) == 926,
         'derived candidate07 manifest differs')
    return value, raw


'''
    execute = old[old.index('def execute():'):]
    execute = execute.replace('candidate06', 'candidate07').replace('candidate05', 'candidate06')
    execute = execute.replace('candidate-06', 'candidate-07').replace('CANDIDATE06', 'CANDIDATE07')
    execute = execute.replace("    # This exact unchanged function checks candidate06's 948 bytes, 925 engine\n    # inputs, six signal files, actual builder450 and original matching gates.\n", "    # This unchanged full-build contract validates candidate06's full inventory,\n    # exact NOFILE host/Android proof, six signal files and matching builder450.\n")
    execute = execute.replace("    build = proof_contract()\n    tested = verify_11_sources(manifest, build)\n", "    gate = proof_contract()\n")
    execute = execute.replace("'source_files': 948, 'engine_files': 925, 'changed_files': sorted(DELTA),\n                  'unchanged_total_files': 945, 'unchanged_engine_files': 922,", "'source_files': 949, 'engine_files': 926,\n                  'changed_files': sorted(name for name, row in DELTA.items() if row[0] is not None),\n                  'added_files': sorted(name for name, row in DELTA.items() if row[0] is None),\n                  'unchanged_total_files': 944, 'unchanged_engine_files': 921,")
    old_fields = """                  'all_11_tested_production_inputs_exact': True, 'tested_production_input_hashes': tested,
                  'actual_Android_build_sha256': ANDROID_BUILD_SHA,
                  'actual_Android_runtime_sha256': ANDROID_SHA, 'actual_host_runtime_sha256': HOST_SHA,
                  'source_proof_files_root': str(HERE),
                  'original_candidate06_matched_gate_sha256': base['MATCHED_GATE_SHA'],
                  'matched_candidate06_gates_rerun_for06': False,"""
    new_fields = """                  'parent_composition_sha256': PARENT_COMPOSITION_SHA,
                  'parent_NOFILE_host_and_Android_proof_revalidated': True,
                  'actual_complete_TU_gate_sha256': GATE_SHA,
                  'actual_original_missing_header_failure_reproduced': True,
                  'actual_complete_candidate_TUs': len(gate['compiled_TUs']),
                  'original_host_warning_target_and_sysroot_flags_preserved': True,
                  'all_five_composition_inputs_in_actual_compiled_dependencies': True,
                  'source_proof_files_root': str(HERE),
                  'original_candidate05_matched_gate_sha256': base['MATCHED_GATE_SHA'],
                  'matched_candidate05_gates_rerun_for07': False,
                  'NOFILE_Android_runtime_rerun_after_header_delta': False,"""
    assert old_fields in execute
    execute = execute.replace(old_fields, new_fields)
    execute = execute.replace("'source_files': 948, 'engine_files': 925, 'actual_Android_runtime_sha256': ANDROID_SHA,", "'source_files': 949, 'engine_files': 926, 'actual_TU_gate_sha256': GATE_SHA,")
    composer = constants + common + proof + execute
    ast.parse(composer)
    assert 'verify_11_sources' not in composer and 'ANDROID_SHA' not in composer
    put('compose.py', composer.encode())
    put('composer-candidate06-to07.patch', ''.join(difflib.unified_diff(
        old.splitlines(True), composer.splitlines(True), fromfile='candidate06/compose.py',
        tofile='candidate07/compose.py')).encode())
    put('SOURCE_DELTA.json', encoded(delta))
    put('MANIFEST_DERIVATION.json', encoded({
        'schema': 1, 'state': 'LOCAL_DERIVATION_NOT_REMOTE_COMPOSITION',
        'parent_manifest_sha256': sha(before), 'manifest_sha256': sha(new_manifest),
        'parent_source_files': 948, 'candidate_source_files': 949,
        'parent_engine_files': 925, 'candidate_engine_files': 926,
        'changed_existing': 4, 'added_files': 1, 'unchanged_total_files': 944,
        'unchanged_engine_files': 921, 'remote_actions': 0,
        'actual_TU_gate_reported_by_parent_sha256': '5a09aa094c960a2bcc2d357fa732aac0cdb95203d25d3b690ced62497bb1c1d1',
        'actual_TU_complete_receipt_read_by_this_derivation': False,
        'actual_composition': False, 'full_engine_built': False, 'production_ready': False}))
    print(json.dumps({'composer_sha256': sha(composer.encode()), 'manifest_sha256': sha(new_manifest),
                      'source_files': 949, 'engine_files': 926, 'remote_actions': 0}))


if __name__ == '__main__':
    main()
