#!/usr/bin/env python3
"""Derive a strict build-only compiler gate from actual 451 to frozen next03."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import sys

WORK = Path('/workspace/scratch/94990735b266/native-recovery-20261105-02')
OLD = WORK / 'paired-builder451-compile02'
SOURCE = WORK / 'art-normal-projection-next03'
DEST = WORK / 'paired-builder462-compile01'
ACTUAL = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence/paired-builder451-compile02/result.json')
REMOTE = '/home/alex/work/pocket4-native-generation-builder462-compile-01-20261105'
BASE_SOURCE = '/home/alex/work/pocket4-native-generation-builder451-compile-02-20261105/builder-source'


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def write(name, raw):
    path = DEST / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def exact(source, before, after):
    assert source.count(before) == 1, before[:140]
    return source.replace(before, after)


def main():
    actual_raw = ACTUAL.read_bytes()
    assert pin(actual_raw)['sha256'] == '8c72e771c9ed5bd440b36aa8c7c3379b31ce8acccdc2b222fadad9e64cb28096'
    actual = json.loads(actual_raw)
    assert actual['state'] == 'PASS' and actual['focused_tests_passed'] == 22
    old_manifest = (OLD / 'expected-builder451-manifest.json').read_bytes()
    new_manifest = (SOURCE / 'expected-builder462-source-manifest.json').read_bytes()
    assert pin(old_manifest)['sha256'] == actual['copied_manifest']['sha256']
    assert pin(new_manifest)['sha256'] == '7eaf421cc911a8fec13945099f8d3758bada44b2331e4698dbefd472f535c8da'
    parent, expected = json.loads(old_manifest), json.loads(new_manifest)
    changes = sorted(name for name in expected if expected[name] != parent.get(name))
    added = sorted(name for name in changes if name not in parent)
    edited = sorted(name for name in changes if name in parent)
    assert len(parent) == 451 and len(expected) == 462 and len(changes) == 13
    assert len(added) == 11 and len(edited) == 2 and set(parent) <= set(expected)
    assert edited == ['tools/droidloom-update/src/android.rs', 'tools/droidloom-update/src/main.rs']
    assert sorted(str(p.relative_to(SOURCE / 'delta')) for p in (SOURCE / 'delta').rglob('*') if p.is_file()) == changes
    for name in changes:
        raw = (SOURCE / 'delta' / name).read_bytes()
        assert pin(raw) == {key: expected[name][key] for key in ('bytes', 'sha256')}
    before = (OLD / 'compile_builder.py').read_text()
    assert pin(before.encode())['sha256'] == '80cd19aaf18563920b1d7aa02a2ff7a34e0693eefe0d0e8a20c6de478fe7d15b'
    source = before
    source = source.replace('/home/alex/work/pocket4-native-generation-builder451-compile-02-20261105', REMOTE)
    source = source.replace('/home/alex/work/pocket4-blueprint-streaming-builder-450-compile-03-20261105/builder-source', BASE_SOURCE)
    source = source.replace('MANIFEST_451', 'MANIFEST_462')
    source = source.replace("MANIFEST_PARENT = '6834ea57e4d0402bd5c6e6c405728a111af77fb54ea0e0bea407ba9647fa41b4'", "MANIFEST_PARENT = '" + pin(old_manifest)['sha256'] + "'")
    source = source.replace("MANIFEST_462 = 'a5052accd9bb36231a3c59271f8bc35e464e5cf14d702787735feed0d86b7a13'", "MANIFEST_462 = '" + pin(new_manifest)['sha256'] + "'")
    source = source.replace('compiled-parent450-manifest.json', 'compiled-parent451-manifest.json')
    source = source.replace('compiled-parent450-result.json', 'compiled-parent451-result.json')
    source = source.replace('expected-builder451-manifest.json', 'expected-builder462-manifest.json')
    source = source.replace('actual_parent450_compile_authority', 'actual_parent451_compile_authority')
    source = source.replace('actual compiled parent450 qualification differs', 'actual compiled parent451 qualification differs')
    source = source.replace('a1d8fe1e891c876baeff555b18fce9bafe6a895d379d9e55261c6df1981785de', pin(actual_raw)['sha256'])
    source = source.replace('ea80146d5fc47f9927dd16a1ad91b6b48f0b30f0ce043d4eaef53f0e84f482b6', actual['builder_elf']['sha256'])
    source = exact(source, "parent['focused_tests_passed']==7", "parent['focused_tests_passed']==22")
    source = exact(source, "len(expected)==450 and len(copied_expected)==451", "len(expected)==451 and len(copied_expected)==462")
    art_tests = [
        'native_generation_art::tests::output_rejects_source_overlap_alias_and_reuse',
        'native_generation_art::tests::records_are_create_only_and_never_grant_runtime_readiness',
    ]
    source = exact(source, 'TESTS = ORIGINAL_TESTS + PAIR_TESTS',
                   'ART_PROJECTION_TESTS = ' + repr(art_tests) + '\nTESTS = ORIGINAL_TESTS + PAIR_TESTS + ART_PROJECTION_TESTS')
    old_block = """        wanted=['tools/droidloom-update/src/bundle.rs','tools/droidloom-update/src/main.rs',
                'tools/droidloom-update/src/native_bridge.rs','tools/droidloom-update/src/native_generation.rs']
        require(sorted(changes)==wanted and set(expected)<=set(copied_expected) and
                sum(name not in expected for name in changes)==1,'paired451 source delta is not three edits and one new module')"""
    new_block = """        wanted=FIXED_ART_DELTA
        require(sorted(changes)==wanted and set(expected)<=set(copied_expected) and
                sum(name not in expected for name in changes)==11 and
                sum(name in expected for name in changes)==2,
                'paired462 source delta is not two edits and eleven additions')"""
    source = exact(source, old_block, new_block)
    source = exact(source, 'DEADLINE = None', 'FIXED_ART_DELTA = ' + repr(changes) + '\nDEADLINE = None')
    old_block = """        report['source_delta']={'changed_existing':wanted[:3],'added':[wanted[3]],
                                'unchanged_existing':447,'engine_source_files_changed':0,'Go6_patch_changed':False,
                                'Blueprint_streaming_patch_changed':False}"""
    new_block = """        report['source_delta']={'changed_existing':[name for name in wanted if name in expected],
                                'added':[name for name in wanted if name not in expected],
                                'unchanged_existing':449,'engine_source_files_changed':0,'Go6_patch_changed':False,
                                'Blueprint_streaming_patch_changed':False,
                                'ART_source_data_files':10,'ART_sources_executed_or_built':False}"""
    source = exact(source, old_block, new_block)
    source = exact(source, "b'native-generation-pair' in help_output,'normal builder or explicit paired-record CLI missing')",
                   "b'native-generation-pair' in help_output and b'native-generation-art-build' in help_output,\n                'normal builder or explicit paired-record/ART build-only CLI missing')")
    source = exact(source, 'len(PAIR_TESTS)==15 and len(TESTS)==len(set(TESTS))==22',
                   'len(PAIR_TESTS)==15 and len(ART_PROJECTION_TESTS)==2 and len(TESTS)==len(set(TESTS))==24')
    source = source.replace('original seven or new 15 exact tests absent/duplicated in actual test executable',
                            'original seven, paired fifteen or new ART two exact tests absent/duplicated in actual test executable')
    source = exact(source, "require(listed_names and len(listed_names)==len(set(listed_names)) and",
                   "require(len(listed_names)==197 and len(listed_names)==len(set(listed_names)) and")
    source = exact(source, "report['pairing_tests_passed']=len(PAIR_TESTS)",
                   "report['pairing_tests_passed']=len(PAIR_TESTS)\n        report['ART_projection_tests_passed']=len(ART_PROJECTION_TESTS)")
    source = source.replace('451-file Rust builder and 22 exact tests', '462-file Rust builder and 24 exact tests')
    source = source.replace('builder451 and run 22 exact source tests', 'builder462 and run 24 exact source tests')
    source = source.replace('actual copied 451 manifest differs', 'actual copied 462 manifest differs')
    source = source.replace("'source_files':451", "'source_files':462")
    ast.parse(source)
    defs = lambda text: {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}
    before_defs, after_defs = defs(before), defs(source)
    assert set(before_defs) == set(after_defs)
    changed_functions = sorted(name for name in before_defs if before_defs[name] != after_defs[name])
    assert changed_functions == ['execute']
    old_packet = json.loads((OLD / 'verified-source-packet.json').read_bytes())
    data = {name: value.encode() for name, value in old_packet.items()
            if not name.startswith('delta/') and name not in (
                'compile_builder.py', 'compiled-parent450-manifest.json',
                'compiled-parent450-result.json', 'expected-builder451-manifest.json')}
    data.update({'compile_builder.py': source.encode(),
                 'compiled-parent451-manifest.json': old_manifest,
                 'compiled-parent451-result.json': actual_raw,
                 'expected-builder462-manifest.json': new_manifest})
    for name in changes:
        data['delta/' + name] = (SOURCE / 'delta' / name).read_bytes()
    assert len(data) == 23
    old_stage = (OLD / 'stage.py').read_text()
    stage = old_stage.replace('/home/alex/work/pocket4-native-generation-builder451-compile-02-20261105', REMOTE)
    assignment = next(n for n in ast.parse(stage).body if isinstance(n, ast.Assign) and n.targets[0].id == 'EXPECTED')
    stage = exact(stage, ast.get_source_segment(stage, assignment), 'EXPECTED=' + repr({name: pin(raw) for name, raw in data.items()}))
    assert defs(old_stage)['main'] == defs(stage)['main']
    request = json.loads((OLD / 'exact-request.json').read_bytes())
    packet = json.dumps({name: raw.decode() for name, raw in data.items()}, ensure_ascii=True, sort_keys=True)
    request['stdin'] = stage + '\nPACKET=json.loads(' + repr(packet) + ')\nmain(PACKET)\n'
    request['idempotency_key'] = 'pocket4-native-generation-builder462-matching-compile-01-20261105'
    ast.parse(request['stdin'])
    for name, raw in data.items():
        write(name, raw)
    write('stage.py', stage.encode())
    write('verified-source-packet.json', (packet + '\n').encode())
    write('exact-request.json', (json.dumps(request, indent=2) + '\n').encode())
    write('compiler451-to462.patch', ''.join(difflib.unified_diff(before.splitlines(True), source.splitlines(True), fromfile='a/compile_builder.py', tofile='b/compile_builder.py')).encode())
    write('stage451-to462.patch', ''.join(difflib.unified_diff(old_stage.splitlines(True), stage.splitlines(True), fromfile='a/stage.py', tofile='b/stage.py')).encode())
    write('make_request.py', Path(__file__).read_bytes())
    plan = subprocess.run([sys.executable, '-I', '-B', str(DEST / 'compile_builder.py')], capture_output=True, check=True)
    write('PLAN.json', plan.stdout)
    write('LOCAL_SOURCE_CHECKS.json', (json.dumps({
        'schema': 1, 'changed_existing_functions': changed_functions,
        'unchanged_functions': sorted(name for name in before_defs if name not in changed_functions),
        'stage_main_AST_unchanged': True, 'new_source_manifest_files': 462,
        'parent_actual_receipt_sha256': pin(actual_raw)['sha256'],
        'source_delta_changed': edited, 'source_delta_added': added,
        'source_delta_unchanged': 449, 'request_packet_files': 23,
        'local_default_PLAN_returncode': plan.returncode, 'local_Rust_compile': False,
        'ART_APEX_built': False, 'remote_request_submitted': False,
    }, indent=2, sort_keys=True) + '\n').encode())
    write('README.md', b'''# Matching builder462 compile request, next03 scope

This new build-only request starts from the actual PASS builder451 source map and exact compile02 receipt. It applies the already frozen next03 two Rust edits plus eleven additions (one Rust module and ten ART source data files), leaving 449 paths unchanged. It compiles with the same Rust1.93 offline/locked, selected49/cache-archive qualification, held tool/ELF closure, 1 CPU / 1 GiB resource checks and owned-child cleanup as the actual 451 runner. Only the execute function and fixed constants change; the original 22 exact tests stay in their original order, including the same fakeroot index20 retirement gate, and the two new ART projection tests are appended. Independent libtest result files, stdout/registration counts, 197 actual registered tests and all prior failure gates remain required.

The source data is not executed by this request. No Soong build, APEX generation, image staging, namespace, service, Android or Main action is authorized. Next03 still fixes only libart-runtime and libnativebridge targets; full signed ART APEX packaging and the enabled engine/artifact triplet are subsequent gates. Child-zygote role/preload/zero-capability and parent-resume gaps remain open. This request must not be presented as a paired-image qualification.
''')
    pins = {str(path.relative_to(DEST)): pin(path.read_bytes()) for path in sorted(DEST.rglob('*')) if path.is_file()}
    write('SOURCE_PINS.json', (json.dumps({'schema': 1, 'files': pins}, indent=2, sort_keys=True) + '\n').encode())
    print(json.dumps({'root': str(DEST), 'files': len(pins) + 1,
                      'controller': pin(source.encode()), 'request': pin((DEST / 'exact-request.json').read_bytes()),
                      'patch': pin((DEST / 'compiler451-to462.patch').read_bytes())}))


if __name__ == '__main__':
    main()
