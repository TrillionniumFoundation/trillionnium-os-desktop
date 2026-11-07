#!/usr/bin/env python3
"""Freeze one offline Rust build-only request for the actual-lock-bound route."""
import ast
import base64
import difflib
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zlib

BASE = Path('/workspace/scratch/94990735b266/native-recovery-20261105-02')
OLD = BASE / 'paired-builder462-compile01'
TRANSPORT = BASE / 'paired-builder462-compile01-transport02'
SOURCE = BASE / 'typed-ingress-builder-source02'
LOCK = BASE / 'typed-ingress-source-lock-freeze02'
DEST = BASE / 'typed-ingress-builder465-compile01'
ACTUAL = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence/paired-builder462-compile01-transport02/result.json')
OLD_REMOTE = '/home/alex/work/pocket4-native-generation-builder462-compile-01-20261105'
REMOTE = '/home/alex/work/pocket4-native-typed-ingress-builder465-compile-01-20261105'
KEY = 'pocket4-native-typed-ingress-builder465-matching-compile-01-20261105'


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def exact(source, before, after):
    assert source.count(before) == 1, before[:160]
    return source.replace(before, after)


def definitions(source):
    return {node.name: ast.dump(node, include_attributes=False)
            for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)}


def assignment(source, name, replacement):
    nodes = [node for node in ast.parse(source).body
             if isinstance(node, ast.Assign) and len(node.targets) == 1
             and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name]
    assert len(nodes) == 1, name
    return exact(source, ast.get_source_segment(source, nodes[0]), name + ' = ' + repr(replacement))


def main():
    assert not DEST.exists()
    original = (OLD / 'compile_builder.py').read_bytes()
    assert pin(original) == {'bytes': 64192, 'sha256': '997a1024b3ede93afa4fad33858b00432b95cf73abb6819612b4c096e76e52fc'}
    parent_raw = ACTUAL.read_bytes()
    assert pin(parent_raw) == {'bytes': 136350, 'sha256': 'f9a3dd01d9ebdb60a0e6a34ee99e3b1a2f646a30191eda3643cee5ca36ff544f'}
    parent = json.loads(parent_raw)
    assert parent['state'] == 'PASS' and parent['focused_tests_passed'] == 24
    assert parent['actual_registered_test_count'] == 197
    assert parent['copied_source_unchanged_after'] and parent['original_source_unchanged_after']
    assert parent['owned_resource_gate']['pass'] is True
    assert not parent['cleanup']['errors'] and not parent['cleanup']['remaining']
    assert not parent['cleanup']['forced_cleanup'] and not parent['dependency_changes'] and not parent['tool_changes']
    assert parent['cargo_configs_unchanged_after'] is True
    source_pins = json.loads((SOURCE / 'SOURCE_PINS.json').read_bytes())
    assert pin((SOURCE / 'SOURCE_PINS.json').read_bytes())['sha256'] == '2dccdee62bba2c524089baa1f187ac2eb6cf703694f7baf090f78f70aed8d12f'
    for row in source_pins['files']:
        assert pin((SOURCE / row['path']).read_bytes()) == {key: row[key] for key in ('bytes', 'sha256')}
    old_map_raw = (SOURCE / 'references/parent462-source-manifest.json').read_bytes()
    new_map_raw = (SOURCE / 'expected-builder465-source-manifest.json').read_bytes()
    assert pin(old_map_raw) == {'bytes': 91148, 'sha256': parent['copied_manifest']['sha256']}
    assert pin(new_map_raw) == {'bytes': 91758, 'sha256': '6b15e35c79575f2da99fcaf383a29e1d0ddcfaa34f9bc9bb5ae070fb3367ee10'}
    old_map, new_map = json.loads(old_map_raw), json.loads(new_map_raw)
    changes = sorted(name for name in new_map if new_map[name] != old_map.get(name))
    added = [name for name in changes if name not in old_map]
    edited = [name for name in changes if name in old_map]
    assert len(old_map) == 462 and len(new_map) == 465 and set(old_map) <= set(new_map)
    assert added == ['android/manifest/m2-role-ingress-source-lock.json',
                     'android/native-role-ingress/typed-ingress02-framework.patch',
                     'tools/droidloom-update/src/native_role_ingress.rs']
    assert edited == ['tools/droidloom-update/src/android.rs', 'tools/droidloom-update/src/main.rs']
    assert sum(new_map[name] == row for name, row in old_map.items()) == 460
    for name in changes:
        assert pin((SOURCE / 'candidate' / name).read_bytes()) == {key: new_map[name][key] for key in ('bytes', 'sha256')}
    root_trees = (LOCK / 'references/root-trees-reader-report.json').read_bytes()
    derivation = (LOCK / 'derivation.json').read_bytes()
    assert pin(root_trees) == {'bytes': 51842, 'sha256': '0088aaea045f1c0e048db1a65184e536495f3d0d8a9721cd668bdfa0016b43e8'}
    assert pin(derivation) == {'bytes': 6051, 'sha256': 'c5cd3f0efd5519b8e724a42b7fc27850e20dc5a5ea55fff868366e902b56c3e0'}

    source = original.decode()
    source = assignment(source, 'BASE_SOURCE', None).replace('BASE_SOURCE = None', "BASE_SOURCE = Path(" + repr(OLD_REMOTE + '/builder-source') + ')')
    source = assignment(source, 'ROOT', None).replace('ROOT = None', 'ROOT = Path(' + repr(REMOTE) + ')')
    source = source.replace('MANIFEST_462', 'MANIFEST_465')
    source = assignment(source, 'MANIFEST_PARENT', pin(old_map_raw)['sha256'])
    source = assignment(source, 'MANIFEST_465', pin(new_map_raw)['sha256'])
    source = source.replace('compiled-parent451-manifest.json', 'compiled-parent462-manifest.json')
    source = source.replace('compiled-parent451-result.json', 'compiled-parent462-result.json')
    source = source.replace('expected-builder462-manifest.json', 'expected-builder465-manifest.json')
    source = source.replace('actual_parent451_compile_authority', 'actual_parent462_compile_authority')
    source = source.replace('actual compiled parent451 qualification differs', 'actual compiled parent462 qualification differs')
    source = exact(source, '8c72e771c9ed5bd440b36aa8c7c3379b31ce8acccdc2b222fadad9e64cb28096', pin(parent_raw)['sha256'])
    source = exact(source, '34c04271f1a3095cedb0b57eece7749958622754a864202b17a54abb174e0e3e', parent['builder_elf']['sha256'])
    source = exact(source, "parent['focused_tests_passed']==22", "parent['focused_tests_passed']==24 and parent['actual_registered_test_count']==197")
    source = exact(source, "not parent['tool_changes'] and not parent['cleanup']['errors'] and not parent['cleanup']['remaining'],",
                   "not parent['tool_changes'] and not parent['cleanup']['errors'] and not parent['cleanup']['remaining'] and\n                not parent['cleanup']['forced_cleanup'] and parent['copied_source_unchanged_after'] is True and\n                parent['original_source_unchanged_after'] is True and parent['cargo_configs_unchanged_after'] is True,")
    source = exact(source, 'len(expected)==451 and len(copied_expected)==462', 'len(expected)==462 and len(copied_expected)==465')
    tests = ['native_role_ingress::tests::observed_lock_passes_normal_schema_and_exact_extension_gate',
             'native_role_ingress::tests::structurally_valid_unobserved_root_is_rejected_before_source_actions']
    source = exact(source, 'TESTS = ORIGINAL_TESTS + PAIR_TESTS + ART_PROJECTION_TESTS',
                   'TYPED_INGRESS_TESTS = ' + repr(tests) + '\nTESTS = ORIGINAL_TESTS + PAIR_TESTS + ART_PROJECTION_TESTS + TYPED_INGRESS_TESTS')
    source = source.replace('FIXED_ART_DELTA', 'FIXED_TYPED_DELTA')
    source = assignment(source, 'FIXED_TYPED_DELTA', changes)
    source = exact(source, 'sum(name not in expected for name in changes)==11', 'sum(name not in expected for name in changes)==3')
    source = source.replace('paired462 source delta is not two edits and eleven additions', 'typed465 source delta is not two edits and three additions')
    source = source.replace('actual copied 462 manifest differs', 'actual copied 465 manifest differs')
    source = exact(source, "'unchanged_existing':449", "'unchanged_existing':460")
    source = exact(source, "'ART_source_data_files':10,'ART_sources_executed_or_built':False}",
                   "'ART_source_data_files_changed':0,'ART_sources_executed_or_built':False,\n                                'typed_ingress_framework_patch_files':5,'framework_sources_executed_or_built':False,\n                                'runtime_authorization_enabled':False}")
    authority = """        roots_raw,roots_pin=pinned_packet('typed-root-trees-result.json',
            '0088aaea045f1c0e048db1a65184e536495f3d0d8a9721cd668bdfa0016b43e8')
        roots=json.loads(roots_raw)
        require(roots['state']=='PASS_THREE_FIXED_COMMIT_ROOT_TREES' and
                roots['all_started_children_joined'] is True and roots['first_error'] is None and
                not roots['secondary_errors'] and roots['owned_resource_gate']['pass'] is True and
                roots['source_lock_reference_sha256']==expected['android/manifest/m2-sparse-source-lock.json']['sha256'],
                'actual fixed root-tree input authority differs')
        derivation_raw,derivation_pin=pinned_packet('typed-lock-derivation.json',
            'c5cd3f0efd5519b8e724a42b7fc27850e20dc5a5ea55fff868366e902b56c3e0')
        derivation=json.loads(derivation_raw)
        require(derivation['state']=='DERIVED_THREE_PROJECT_SOURCE_EXTENSION_NOT_COMPILED' and
                derivation['actual_report_sha256']==roots_pin['sha256'] and
                derivation['base_lock_sha256']==roots['source_lock_reference_sha256'] and
                derivation['derived_lock_sha256']==copied_expected['android/manifest/m2-role-ingress-source-lock.json']['sha256'] and
                derivation['derived_lock_bytes']==copied_expected['android/manifest/m2-role-ingress-source-lock.json']['bytes'] and
                derivation['other_lock_fields_unchanged'] is True and derivation['original_lock_modified'] is False,
                'derived lock authority does not bind the exact source delta')
        report['actual_typed_root_tree_authority']=roots_pin
        report['typed_lock_derivation_authority']=derivation_pin
"""
    source = exact(source, "        report['actual_parent462_compile_authority']=parent_pin\n", "        report['actual_parent462_compile_authority']=parent_pin\n" + authority)
    source = exact(source, "b'native-generation-pair' in help_output and b'native-generation-art-build' in help_output,",
                   "b'native-generation-pair' in help_output and b'native-generation-art-build' in help_output and\n                b'native-role-ingress-build' in help_output,")
    source = source.replace('normal builder or explicit paired-record/ART build-only CLI missing', 'normal builder or explicit paired-record/ART/typed-ingress build-only CLI missing')
    source = exact(source, 'len(ART_PROJECTION_TESTS)==2 and len(TESTS)==len(set(TESTS))==24',
                   'len(ART_PROJECTION_TESTS)==2 and len(TYPED_INGRESS_TESTS)==2 and len(TESTS)==len(set(TESTS))==26')
    source = source.replace('original seven, paired fifteen or new ART two exact tests absent/duplicated in actual test executable',
                            'original seven, paired fifteen, ART two or typed-ingress two exact tests absent/duplicated in actual test executable')
    source = exact(source, 'len(listed_names)==197', 'len(listed_names)==199')
    source = exact(source, "report['ART_projection_tests_passed']=len(ART_PROJECTION_TESTS)",
                   "report['ART_projection_tests_passed']=len(ART_PROJECTION_TESTS)\n        report['typed_ingress_lock_tests_passed']=len(TYPED_INGRESS_TESTS)\n        report['framework_Java_and_Android_JNI_compiled']=False\n        report['transitive_framework_closure_qualified']=False\n        report['runtime_authorization_enabled']=False")
    source = source.replace('fresh paired-generation 462-file Rust builder and 24 exact tests; no Android/full-engine/service execution',
                            'fresh typed-ingress 465-file Rust builder and 26 exact tests; no Soong/Java/Android/full-engine/service execution')
    source = source.replace('builder462 and run 24 exact source tests', 'builder465 and run 26 exact source tests')
    source = exact(source, "'source_files':462", "'source_files':465")
    old_defs, new_defs = definitions(original.decode()), definitions(source)
    assert set(old_defs) == set(new_defs)
    assert sorted(name for name in old_defs if old_defs[name] != new_defs[name]) == ['execute']
    before_packet = json.loads((OLD / 'verified-source-packet.json').read_bytes())
    old_stage = (OLD / 'stage.py').read_text()
    expected_node = next(node for node in ast.parse(old_stage).body if isinstance(node, ast.Assign) and node.targets[0].id == 'EXPECTED')
    old_expected = ast.literal_eval(expected_node.value)
    assert set(before_packet) == set(old_expected)
    for name, text in before_packet.items():
        assert pin(text.encode()) == old_expected[name]
    data = {name: text.encode() for name, text in before_packet.items()
            if not name.startswith('delta/') and name not in (
                'compile_builder.py', 'compiled-parent451-manifest.json',
                'compiled-parent451-result.json', 'expected-builder462-manifest.json')}
    inherited = {name: pin(raw) for name, raw in data.items()}
    assert len(inherited) == 6
    data.update({'compile_builder.py': source.encode(),
                 'compiled-parent462-manifest.json': old_map_raw,
                 'compiled-parent462-result.json': parent_raw,
                 'expected-builder465-manifest.json': new_map_raw,
                 'typed-root-trees-result.json': root_trees,
                 'typed-lock-derivation.json': derivation})
    for name in changes:
        data['delta/' + name] = (SOURCE / 'candidate' / name).read_bytes()
    assert len(data) == 17
    stage = old_stage.replace(OLD_REMOTE, REMOTE)
    stage = assignment(stage, 'EXPECTED', {name: pin(raw) for name, raw in data.items()})
    assert definitions(old_stage) == definitions(stage)
    packet = json.dumps({name: raw.decode() for name, raw in data.items()}, ensure_ascii=True, sort_keys=True)
    uncompressed = (stage + '\nPACKET=json.loads(' + repr(packet) + ')\nmain(PACKET)\n').encode()
    ast.parse(uncompressed)
    compressed = gzip.compress(uncompressed, compresslevel=9, mtime=0)
    envelope = (json.dumps({'schema': 1, 'encoding': 'gzip+base64',
                           'compressed': pin(compressed), 'uncompressed': pin(uncompressed),
                           'payload': base64.b64encode(compressed).decode()},
                          sort_keys=True, separators=(',', ':')) + '\n').encode()
    assert len(envelope) < 1024 * 1024
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    restored = decoder.decompress(compressed, len(uncompressed) + 1)
    assert restored == uncompressed and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail
    old_boundary = (TRANSPORT / 'transport-boundary.py').read_text()
    boundary = old_boundary
    for name, raw in [('ENVELOPE', envelope), ('COMPRESSED', compressed), ('UNCOMPRESSED', uncompressed)]:
        boundary = assignment(boundary, name, pin(raw))
    normalized = boundary
    for node in ast.parse(old_boundary).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ('ENVELOPE', 'COMPRESSED', 'UNCOMPRESSED'):
            normalized = assignment(normalized, node.targets[0].id, ast.literal_eval(node.value))
    assert ast.dump(ast.parse(normalized), include_attributes=False) == ast.dump(ast.parse(old_boundary), include_attributes=False)
    request = json.loads((OLD / 'exact-request.json').read_bytes())
    request['args'] = ['-I', '-B', '-c', boundary]
    request['stdin'] = envelope.decode()
    request['idempotency_key'] = KEY
    assert request['host'] == 'pocket4' and request['executable'] == '/usr/bin/python3'
    assert request['cpu_quota_percent'] == 100 and request['memory_max_bytes'] == 1073741824 and request['timeout_seconds'] == 600
    assert 'env' not in request
    artifacts = dict(data)
    artifacts.update({'stage.py': stage.encode(), 'transport-boundary.py': boundary.encode(),
                      'verified-source-packet.json': (packet + '\n').encode(),
                      'exact-request.json': (json.dumps(request, indent=2) + '\n').encode(),
                      'compiler462-to465.patch': ''.join(difflib.unified_diff(original.decode().splitlines(True), source.splitlines(True), fromfile='a/compile_builder.py', tofile='b/compile_builder.py')).encode(),
                      'stage462-to465.patch': ''.join(difflib.unified_diff(old_stage.splitlines(True), stage.splitlines(True), fromfile='a/stage.py', tofile='b/stage.py')).encode(),
                      'transport462-to465.patch': ''.join(difflib.unified_diff(old_boundary.splitlines(True), boundary.splitlines(True), fromfile='a/transport-boundary.py', tofile='b/transport-boundary.py')).encode(),
                      'make_request.py': Path(__file__).read_bytes()})
    checks = {'schema': 1, 'state': 'FROZEN_MATCHING_RUST_BUILD_REQUEST_NOT_SUBMITTED',
              'source_tree': '3fe7867c6fa7ea4824cd57742e60137e60cc01e2',
              'source_prefix': SOURCE.name, 'actual_lock_tree': '04620916e15d0cf64e7b06e69f1730238de2c37d',
              'actual_parent_build_report': pin(parent_raw), 'source_files': 465,
              'source_changed': edited, 'source_added': added, 'source_unchanged': 460,
              'changed_existing_functions': ['execute'],
              'unchanged_functions': sorted(name for name in old_defs if old_defs[name] == new_defs[name]),
              'stage_main_AST_unchanged': True, 'transport_AST_unchanged_except_three_pins': True,
              'inherited_authority_packets': inherited, 'packet_files': len(data),
              'uncompressed_stage': pin(uncompressed), 'compressed_stage': pin(compressed),
              'stdin_envelope': pin(envelope), 'controller': pin(source.encode()),
              'retained_existing_test_names': parent['expected_test_names'],
              'new_test_names': tests, 'expected_registered': 199, 'expected_targeted': 26,
              'Rust_tests_executed_locally': False, 'Rust_compiler_available_locally': False,
              'decoded_stage_executed_locally': False, 'remote_request_submitted': False,
              'Soong_Java_Android_JNI_build_requested': False, 'runtime_authorization_enabled': False,
              'Main_actions': 0, 'parent_failures_and_UNKNOWN_listener_build03_preserved': True}
    artifacts['LOCAL_SOURCE_CHECKS.json'] = (json.dumps(checks, indent=2) + '\n').encode()
    artifacts['README.md'] = b'''# Typed ingress builder465: compile only

This request copies the actual 462-file builder source inventory into a new owned root, verifies every original input, and applies exactly two Rust edits and three additions. The new source lock is derived from the completed three fixed-commit root-tree reader, whose exact raw report and derivation are included. The old source lock and every unrelated source remain unchanged. The old 24 targeted tests retain their order, including the independent libtest log and normal fakeroot-child retirement gate; two production source-lock entry tests are appended, with exactly 199 registered tests expected. These expectations have not been executed for this candidate.

The existing Rust 1.93 offline/locked, selected 49-package and locked 45-archive source checks, held compiler/ELF/library closure, one CPU/1 GiB/600 seconds, owned cgroup observations and cleanup remain. Swap max is observed rather than newly constrained. No Soong command, Java or Android TU compilation, source materialization, service, installation, runtime authorization or Main action is in this request. A successful Rust compile will not qualify the complete framework dependency closure or enabled role lifecycle.

Transport uses the previously reviewed bounded single gzip decoder with only its three size/hash pins changed. It validates the complete exact stage and 17 UTF-8 source packet members before executing. The local round trip does not execute that stage. The original listener build03 remains UNKNOWN and is independent of this new compile-only root and key.
'''
    DEST.mkdir(mode=0o700)
    for name, raw in artifacts.items():
        path = DEST / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(raw)
    plan = subprocess.run([sys.executable, '-I', '-B', str(DEST / 'compile_builder.py')], capture_output=True, check=True)
    assert plan.stderr == b'' and json.loads(plan.stdout)['mode'] == 'PLAN'
    assert not Path(REMOTE).exists()
    with (DEST / 'PLAN.json').open('xb') as stream:
        stream.write(plan.stdout)
    pins = {str(path.relative_to(DEST)): pin(path.read_bytes()) for path in sorted(DEST.rglob('*')) if path.is_file()}
    with (DEST / 'SOURCE_PINS.json').open('xb') as stream:
        stream.write((json.dumps({'schema': 1, 'files': pins}, indent=2, sort_keys=True) + '\n').encode())
    for path in DEST.rglob('*'):
        if path.is_file():
            path.chmod(0o444)
    print(json.dumps({'root': str(DEST), 'files': len(pins) + 1,
                      'controller': pin(source.encode()), 'request': pin((DEST / 'exact-request.json').read_bytes()),
                      'stdin': pin(envelope), 'packet_files': len(data),
                      'patch': pin(artifacts['compiler462-to465.patch']), 'PLAN_exit_code': plan.returncode,
                      'remote_submitted': False}))


if __name__ == '__main__':
    main()
