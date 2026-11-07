#!/usr/bin/env python3
"""Derive a fresh matching Rust build from the actual 465-file source closure."""
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
OLD = BASE / 'typed-ingress-builder465-compile01'
DEST = BASE / 'typed-ingress-builder466-go5-compile01'
ACTUAL = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence/typed-ingress-builder465-compile01/result.json')
OLD_REMOTE = '/home/alex/work/pocket4-native-typed-ingress-builder465-compile-01-20261105'
REMOTE = '/home/alex/work/pocket4-native-typed-ingress-builder466-go5-compile-01-20261105'
KEY = 'pocket4-native-typed-ingress-builder466-go5-matching-compile-01-20261105'
PATCH_NAME = 'android/apex-compat/0008-soong-leaf-go-memory-budget.patch'


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def exact(source, before, after):
    assert source.count(before) == 1, before[:200]
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


def diff(before, after, name):
    return ''.join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True),
                                      fromfile='a/' + name, tofile='b/' + name)).encode()


def main():
    assert not DEST.exists()
    old_pins = json.loads((OLD / 'SOURCE_PINS.json').read_bytes())['files']
    for name, row in old_pins.items():
        assert pin((OLD / name).read_bytes()) == row, name
    original = (OLD / 'compile_builder.py').read_bytes()
    assert pin(original) == {'bytes': 66298, 'sha256': '2742d19a6de247655a8f3ae067e970b6e753f1cdae0c053de1f0587b088f84e5'}
    parent_raw = ACTUAL.read_bytes()
    assert pin(parent_raw) == {'bytes': 143310, 'sha256': '36158e522a8562b42e2800c89fc4e96a3b8bed8ad8c7e4d0fc8a7b56278028d8'}
    parent = json.loads(parent_raw)
    assert parent['state'] == 'PASS' and parent['focused_tests_passed'] == 26 and parent['actual_registered_test_count'] == 199
    assert len(parent['commands']) == 59 and all(r['returncode'] == 0 and not r['timed_out'] for r in parent['commands'])
    assert parent['copied_source_unchanged_after'] and parent['original_source_unchanged_after']
    assert parent['owned_resource_gate']['pass'] is True and parent['cargo_configs_unchanged_after'] is True
    assert not parent['cleanup']['errors'] and not parent['cleanup']['remaining'] and not parent['cleanup']['forced_cleanup']
    assert not parent['dependency_changes'] and not parent['tool_changes']
    old_map_raw = (OLD / 'expected-builder465-manifest.json').read_bytes()
    assert pin(old_map_raw) == {'bytes': 91758, 'sha256': parent['copied_manifest']['sha256']}
    old_map = json.loads(old_map_raw)
    old_patch = (BASE / 'full-engine-streaming-go5-profile-01/references/0008-soong-go6.preimage.patch').read_bytes()
    new_patch = (BASE / 'full-engine-candidate07-go5-bound-01/0008-soong-leaf-go-memory-budget.patch').read_bytes()
    assert pin(old_patch) == {'bytes': 583, 'sha256': '6aaaf5ec96a75bb6480c202d6483a5b22bdd4963d6d3b66bbfad4d80ee5ed20e'}
    assert pin(new_patch) == {'bytes': 583, 'sha256': '39211a784284ed319b6abbbe4b327a88896931d39c6bdb91fe727a9a7589325f'}
    assert {k: old_map[PATCH_NAME][k] for k in ('bytes', 'sha256')} == pin(old_patch)
    differences = [i for i, (a, b) in enumerate(zip(old_patch, new_patch)) if a != b]
    assert len(old_patch) == len(new_patch) and differences == [468]
    assert old_patch[468] == ord('6') and new_patch[468] == ord('5')
    assert old_patch.count(b'"6GiB"') == 1 and old_patch.replace(b'"6GiB"', b'"5GiB"') == new_patch
    new_map = json.loads(old_map_raw)
    new_map[PATCH_NAME].update(pin(new_patch))
    new_map_raw = (json.dumps(new_map, indent=2, sort_keys=True) + '\n').encode()
    assert len(old_map) == len(new_map) == 465 and set(old_map) == set(new_map)
    assert [n for n in new_map if new_map[n] != old_map[n]] == [PATCH_NAME]

    source = original.decode()
    source = assignment(source, 'BASE_SOURCE', None).replace('BASE_SOURCE = None', 'BASE_SOURCE = Path(' + repr(OLD_REMOTE + '/builder-source') + ')')
    source = assignment(source, 'ROOT', None).replace('ROOT = None', 'ROOT = Path(' + repr(REMOTE) + ')')
    source = source.replace('MANIFEST_465', 'MANIFEST_466')
    source = assignment(source, 'MANIFEST_PARENT', pin(old_map_raw)['sha256'])
    source = assignment(source, 'MANIFEST_466', pin(new_map_raw)['sha256'])
    source = source.replace('compiled-parent462-manifest.json', 'compiled-parent465-manifest.json')
    source = source.replace('compiled-parent462-result.json', 'compiled-parent465-result.json')
    source = source.replace('expected-builder465-manifest.json', 'expected-builder466-manifest.json')
    source = source.replace('actual_parent462_compile_authority', 'actual_parent465_compile_authority')
    source = source.replace('actual compiled parent462 qualification differs', 'actual compiled parent465 qualification differs')
    source = exact(source, 'f9a3dd01d9ebdb60a0e6a34ee99e3b1a2f646a30191eda3643cee5ca36ff544f', pin(parent_raw)['sha256'])
    source = exact(source, '8f19ac0deb472bf8c2a3a6befd689b76d67d619041fd6deb9c31df15c0056c12', parent['builder_elf']['sha256'])
    source = exact(source, "parent['focused_tests_passed']==24 and parent['actual_registered_test_count']==197", "parent['focused_tests_passed']==26 and parent['actual_registered_test_count']==199")
    source = exact(source, 'len(expected)==462 and len(copied_expected)==465', 'len(expected)==465 and len(copied_expected)==465')
    source = exact(source, 'TESTS = ORIGINAL_TESTS + PAIR_TESTS + ART_PROJECTION_TESTS + TYPED_INGRESS_TESTS',
                   'PARENT_TESTS = ORIGINAL_TESTS + PAIR_TESTS + ART_PROJECTION_TESTS + TYPED_INGRESS_TESTS\nTESTS = ORIGINAL_TESTS + TYPED_INGRESS_TESTS')
    source = source.replace('FIXED_TYPED_DELTA', 'FIXED_GO5_DELTA')
    source = assignment(source, 'FIXED_GO5_DELTA', [PATCH_NAME])
    source = exact(source, 'sorted(changes)==wanted and set(expected)<=set(copied_expected) and\n                sum(name not in expected for name in changes)==3 and\n                sum(name in expected for name in changes)==2,',
                   'sorted(changes)==wanted and set(expected)==set(copied_expected) and\n                sum(name not in expected for name in changes)==0 and\n                sum(name in expected for name in changes)==1,')
    source = source.replace('typed465 source delta is not two edits and three additions', 'Go5 source delta is not exactly one existing runtime patch edit')
    source = exact(source, "            target=COPIED/name\n            if name in expected:",
                   "            target=COPIED/name\n            previous,previous_pin=held(target,4*1024*1024)\n            require(previous_pin==copied_before[name] and len(previous)==len(data)==583 and\n                    previous.count(b'\\\"6GiB\\\"')==1 and\n                    previous.replace(b'\\\"6GiB\\\"',b'\\\"5GiB\\\"')==data and\n                    [i for i,(a,b) in enumerate(zip(previous,data)) if a!=b]==[468],\n                    'Go5 runtime data differs from the single observed ASCII replacement')\n            if name in expected:")
    start = source.index("        report['source_delta']={")
    end = source.index('        env.update(', start)
    source = source[:start] + """        report['source_delta']={'changed_existing':wanted,'added':[],
                                'unchanged_existing':464,'actual_source_file_count':465,
                                'builder_revision_name':'466-go5','Go_memory_soft_limit_before':'6GiB',
                                'Go_memory_soft_limit_after':'5GiB','changed_byte_offset':468,
                                'Rust_source_files_changed':0,'engine_source_files_changed':0,
                                'Blueprint_streaming_patch_changed':False,'ART_source_data_files_changed':0,
                                'typed_ingress_framework_patch_changed':False,'source_lock_changed':False,
                                'framework_sources_executed_or_built':False,'runtime_authorization_enabled':False}
""" + source[end:]
    source = exact(source, "len(ART_PROJECTION_TESTS)==2 and len(TYPED_INGRESS_TESTS)==2 and len(TESTS)==len(set(TESTS))==26 and\n                all(test_list.splitlines().count(name+': test')==1 for name in TESTS),",
                   "len(ART_PROJECTION_TESTS)==2 and len(TYPED_INGRESS_TESTS)==2 and len(PARENT_TESTS)==len(set(PARENT_TESTS))==26 and\n                len(TESTS)==len(set(TESTS))==9 and\n                all(test_list.splitlines().count(name+': test')==1 for name in PARENT_TESTS),")
    source = exact(source, "report['pairing_tests_passed']=len(PAIR_TESTS)", "report['pairing_tests_passed']=0")
    source = exact(source, "report['ART_projection_tests_passed']=len(ART_PROJECTION_TESTS)", "report['ART_projection_tests_passed']=0")
    source = exact(source, "report['real_image_test_count']=5", "report['real_image_test_count']=0\n        report['parent_targeted_tests_passed_historically']=26\n        report['parent_only_test_names_not_rerun']=PAIR_TESTS+ART_PROJECTION_TESTS")
    source = source.replace('fresh typed-ingress 465-file Rust builder and 26 exact tests; no Soong/Java/Android/full-engine/service execution',
                            'fresh builder466 Go5 revision, 465 source files and 9 exact projection/CLI/typed-lock tests; no Soong/Java/Android/full-engine/service execution')
    source = source.replace('builder465 and run 26 exact source tests', 'builder466 Go5 revision and run 9 exact projection/CLI/typed-lock tests')
    old_defs, new_defs = definitions(original.decode()), definitions(source)
    assert set(old_defs) == set(new_defs)
    assert sorted(n for n in old_defs if old_defs[n] != new_defs[n]) == ['execute']

    old_packet = json.loads((OLD / 'verified-source-packet.json').read_bytes())
    old_stage = (OLD / 'stage.py').read_text()
    expected_node = next(n for n in ast.parse(old_stage).body if isinstance(n, ast.Assign) and n.targets[0].id == 'EXPECTED')
    old_expected = ast.literal_eval(expected_node.value)
    assert set(old_packet) == set(old_expected)
    for name, text in old_packet.items():
        assert pin(text.encode()) == old_expected[name]
    data = {name: text.encode() for name, text in old_packet.items()
            if not name.startswith('delta/') and name not in ('compile_builder.py',
                'compiled-parent462-manifest.json', 'compiled-parent462-result.json', 'expected-builder465-manifest.json')}
    inherited = {name: pin(raw) for name, raw in data.items()}
    assert len(inherited) == 8
    data.update({'compile_builder.py': source.encode(), 'compiled-parent465-manifest.json': old_map_raw,
                 'compiled-parent465-result.json': parent_raw, 'expected-builder466-manifest.json': new_map_raw,
                 'delta/' + PATCH_NAME: new_patch})
    assert len(data) == 13
    stage = old_stage.replace(OLD_REMOTE, REMOTE)
    stage = assignment(stage, 'EXPECTED', {name: pin(raw) for name, raw in data.items()})
    assert definitions(old_stage) == definitions(stage)
    packet = json.dumps({name: raw.decode() for name, raw in data.items()}, ensure_ascii=True, sort_keys=True)
    uncompressed = (stage + '\nPACKET=json.loads(' + repr(packet) + ')\nmain(PACKET)\n').encode()
    ast.parse(uncompressed)
    compressed = gzip.compress(uncompressed, compresslevel=9, mtime=0)
    envelope = (json.dumps({'schema': 1, 'encoding': 'gzip+base64', 'compressed': pin(compressed),
                           'uncompressed': pin(uncompressed), 'payload': base64.b64encode(compressed).decode()},
                          sort_keys=True, separators=(',', ':')) + '\n').encode()
    assert len(envelope) < 1024 * 1024
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    restored = decoder.decompress(compressed, len(uncompressed) + 1)
    assert restored == uncompressed and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail
    old_boundary = (OLD / 'transport-boundary.py').read_text()
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
                      'compiler465-to466.patch': diff(original, source.encode(), 'compile_builder.py'),
                      'stage465-to466.patch': diff(old_stage.encode(), stage.encode(), 'stage.py'),
                      'transport465-to466.patch': diff(old_boundary.encode(), boundary.encode(), 'transport-boundary.py'),
                      'production-go6-to-go5.patch': diff(old_patch, new_patch, PATCH_NAME),
                      'references/0008-soong-go6.preimage.patch': old_patch,
                      'make_request.py': Path(__file__).read_bytes()})
    checks = {'schema': 1, 'state': 'FROZEN_MATCHING_RUST_BUILD_REQUEST_NOT_SUBMITTED',
              'actual_parent_build_report': pin(parent_raw), 'actual_source_file_count': 465,
              'revision_name': '466-go5', 'source_changed': [PATCH_NAME], 'source_added': [], 'source_unchanged': 464,
              'old_source_manifest': pin(old_map_raw), 'derived_source_manifest': pin(new_map_raw),
              'changed_byte_offsets': differences, 'old_byte': 54, 'new_byte': 53,
              'changed_existing_functions': ['execute'],
              'unchanged_functions': sorted(n for n in old_defs if old_defs[n] == new_defs[n]),
              'stage_main_AST_unchanged': True, 'transport_AST_unchanged_except_three_pins': True,
              'inherited_authority_packets': inherited, 'packet_files': len(data),
              'uncompressed_stage': pin(uncompressed), 'compressed_stage': pin(compressed),
              'stdin_envelope': pin(envelope), 'controller': pin(source.encode()),
              'parent_targeted_tests_passed_historically': 26, 'expected_registered': 199,
              'expected_targeted_this_attempt': 9, 'image_and_ART_targeted_tests_rerun': False,
              'Rust_tests_executed_locally': False, 'decoded_stage_executed_locally': False,
              'remote_request_submitted': False, 'Soong_Java_Android_JNI_build_requested': False,
              'runtime_authorization_enabled': False, 'Main_actions': 0,
              'future_framework_budget_proposal': {'cpu_percent': 200, 'jobs': 1, 'memory_max_GiB': 10,
                  'memory_swap_max_GiB': 1, 'fresh_MemAvailable_min_GiB': 13, 'fresh_SwapFree_min_GiB': 2,
                  'historical_samples_do_not_admit': True, 'framework_build_not_requested_here': True},
              'parent_failures_and_UNKNOWN_listener_build03_preserved': True}
    artifacts['LOCAL_SOURCE_CHECKS.json'] = (json.dumps(checks, indent=2) + '\n').encode()
    artifacts['README.md'] = b'''# Builder466 Go5: a matching Rust build only

The revision name is 466; the complete source inventory still contains 465 files. A create-only copy of the actual successful builder465 source is checked against its complete manifest. Exactly byte 468 of android/apex-compat/0008-soong-leaf-go-memory-budget.patch changes from ASCII 6 to 5, selecting GOMEMLIMIT=5GiB at the normal Soong leaf. All 464 other source files, including every Rust file, the typed framework patch, both source locks and the Blueprint streaming patch, remain byte-identical. The runtime checks the one-byte replacement before modifying its own copied file. Old builder465 source, ELF and receipts are retained.

This request actually recompiles the builder and the complete Rust test executable with Rust 1.93 offline/locked. It retains the selected 49-package/45 locked-archive qualification, source/config/tool/dependency/ELF rechecks, independent libtest result records, and owned resource/child cleanup gates. It lists exactly 199 tests and executes only the existing seven projection/CLI and two typed-lock tests. The parent report's 26 passing targeted tests are historical evidence; this revision does not rerun or claim 15 image/pairing or two ART tests. Image/tool authority checking remains unchanged, but no image-generation test runs.

The compile request remains one CPU, 1GiB and 600 seconds; swap.max remains observed rather than newly constrained. No Soong, Java/JNI, source materialization, service, installation, authorization or Main action is requested. A later framework request will bind the actual new ELF and source receipt and freshly require 13GiB MemAvailable and 2GiB SwapFree for its separate 10GiB RAM/1GiB swap, two-CPU/jobs1 budget. Prior engine success is evidence about that resource choice, not proof that the different framework targets will build. This package does not grant that later request or reuse an old admission sample.

Transport reuses the already reviewed bounded gzip decoder with only three exact size/hash pins changed. It checks the complete stage and thirteen source packet members before execution. Local validation decodes but does not execute the stage. All failed and UNKNOWN attempts remain unchanged.
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
    pins = {str(p.relative_to(DEST)): pin(p.read_bytes()) for p in sorted(DEST.rglob('*')) if p.is_file()}
    with (DEST / 'SOURCE_PINS.json').open('xb') as stream:
        stream.write((json.dumps({'schema': 1, 'files': pins}, indent=2, sort_keys=True) + '\n').encode())
    for path in DEST.rglob('*'):
        if path.is_file(): path.chmod(0o444)
    print(json.dumps({'root': str(DEST), 'files': len(pins) + 1, 'controller': pin(source.encode()),
                      'manifest': pin(new_map_raw), 'request': pin((DEST / 'exact-request.json').read_bytes()),
                      'stdin': pin(envelope), 'packet_files': len(data),
                      'patch': pin(artifacts['compiler465-to466.patch']), 'PLAN_exit_code': plan.returncode,
                      'remote_submitted': False}))


if __name__ == '__main__':
    main()
