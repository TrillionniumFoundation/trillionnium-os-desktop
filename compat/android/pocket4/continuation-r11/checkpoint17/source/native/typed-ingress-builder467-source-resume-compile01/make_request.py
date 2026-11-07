#!/usr/bin/env python3
"""Freeze builder467 source recovery and a compile-only request; never submit it."""
import ast
import base64
import datetime
import difflib
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zlib

BASE = Path('/workspace/scratch/94990735b266/native-recovery-20261105-02')
WORK = BASE / 'typed-source-resume-work01'
SOURCE = BASE / 'typed-source-resume-freeze01'
OLD = BASE / 'typed-ingress-builder466-go5-compile02'
DEST = BASE / 'typed-ingress-builder467-source-resume-compile01'
NORMAL = BASE / 'typed-framework-normal-build-freeze01'
EVIDENCE = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence')
PARENT_REMOTE = '/home/alex/work/pocket4-native-typed-ingress-builder466-go5-compile-02-20261105'
REMOTE = '/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-01-20261105'
KEY = 'pocket4-native-typed-ingress-builder467-source-resume-compile-01-20261105'
REPLACED = ['tools/droidloom-source/src/lib.rs', 'tools/droidloom-update/src/android.rs',
            'tools/droidloom-update/src/main.rs']
ADDED = ['tools/droidloom-source/src/resume.rs']


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def raw_pin(path, size, digest):
    raw = path.read_bytes()
    assert pin(raw) == {'bytes': size, 'sha256': digest}, str(path)
    return raw


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=True) + '\n').encode()


def exact(source, before, after):
    assert source.count(before) == 1, before[:200]
    return source.replace(before, after)


def assignment(source, name, value):
    nodes = [n for n in ast.parse(source).body if isinstance(n, ast.Assign)
             and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
             and n.targets[0].id == name]
    assert len(nodes) == 1, name
    return exact(source, ast.get_source_segment(source, nodes[0]), name + ' = ' + repr(value))


def functions(source):
    return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(source).body
            if isinstance(n, ast.FunctionDef)}


def diff(before, after, name):
    return ''.join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True),
                                      fromfile='a/' + name, tofile='b/' + name)).encode()


def write_tree(root, artifacts):
    assert not root.exists(), str(root)
    root.mkdir(mode=0o700)
    for name, raw in artifacts.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(raw)
    frozen = {name: pin(raw) for name, raw in sorted(artifacts.items())}
    with (root / 'SOURCE_PINS.json').open('xb') as stream:
        stream.write(encoded({'schema': 1, 'files': frozen}))
    for path in root.rglob('*'):
        if path.is_file():
            path.chmod(0o444)


def main():
    assert not SOURCE.exists() and not DEST.exists()
    parent_manifest_raw = raw_pin(NORMAL / 'expected-builder466-manifest.json', 91758,
        'f09b908745cf294735f897a64d0d956a207d27f78277781f536d5059bb856d0f')
    parent_manifest = json.loads(parent_manifest_raw)
    assert len(parent_manifest) == 465
    parent_result_raw = raw_pin(NORMAL / 'actual-builder466-result.json', 98764,
        '2d6c80a29e957b1e97764d8785257eb47c3d0b899f301e64c9a9c418e96ea0ab')
    parent_result = json.loads(parent_result_raw)
    assert parent_result['state'] == 'PASS' and parent_result['focused_tests_passed'] == 9
    assert parent_result['copied_manifest']['sha256'] == pin(parent_manifest_raw)['sha256']
    assert parent_result['builder_elf']['sha256'] == '309e96393ab482c958a519b78a455a6c75d156a6edb805c840aa6d21f76fa96a'
    old_pins = json.loads((OLD / 'SOURCE_PINS.json').read_bytes())['files']
    for name, wanted in old_pins.items():
        assert pin((OLD / name).read_bytes()) == wanted, name
    old_controller = raw_pin(OLD / 'compile_builder.py', 71226,
        '03c0773f3a35944b2f6aebf5003b143628244096d984e6e44945bc0bece38049')
    candidate = {name: (WORK / 'candidate' / name).read_bytes() for name in REPLACED + ADDED}
    baseline = {name: (WORK / 'baseline' / name).read_bytes() for name in REPLACED}
    for name, raw in baseline.items():
        assert pin(raw) == {key: parent_manifest[name][key] for key in ('bytes', 'sha256')}
        assert candidate[name] != raw
    assert all(name not in parent_manifest for name in ADDED)
    manifest = dict(parent_manifest)
    for name, raw in candidate.items():
        manifest[name] = {'kind': 'file', **pin(raw), 'mode': parent_manifest[name]['mode'] if name in parent_manifest else 0o664}
    assert len(manifest) == 466
    assert [name for name in parent_manifest if manifest[name] != parent_manifest[name]] == [
        name for name in parent_manifest if name in REPLACED]
    assert all(manifest[name] == parent_manifest[name] for name in parent_manifest if name not in REPLACED)
    manifest_raw = encoded(manifest)
    tests = re.findall(r'#\[test\]\s+fn ([a-zA-Z0-9_]+)\(', candidate[ADDED[0]].decode())
    source_tests = ['resume::tests::' + name for name in tests]
    assert len(source_tests) == len(set(source_tests)) == 9
    baseline_tests = ['tests::' + name for name in re.findall(r'#\[test\]\s+fn ([a-zA-Z0-9_]+)\(', baseline[REPLACED[0]].decode())]
    assert len(baseline_tests) == len(set(baseline_tests)) == 11
    assert candidate[REPLACED[0]] == baseline[REPLACED[0]].replace(
        b'use thiserror::Error;\n', b'use thiserror::Error;\n\nmod resume;\npub use resume::materialize_resuming;\n')
    assert candidate[ADDED[0]].count(b'#[cfg(test)]') == 2
    assert b'read_owned(&index_lock, owner, 0)?' in candidate[ADDED[0]]
    assert b'--force' not in candidate[ADDED[0]].replace(b'// No --force:', b'// No forced checkout:')
    staging_raw = raw_pin(EVIDENCE / 'typed-framework-known-staging-read03/stdout.log', 211213,
        'c62f32b7002d043e4813eadd598f33d088a0f20cc9f562ddc19d35c2ccddf664')
    assessment_raw = raw_pin(EVIDENCE / 'typed-framework-known-staging-read03/analysis01/actual-staging-reuse-assessment.json', 7226,
        'b3992232b84de65addb54a87ca6a5f36ea90e5548e321a4774b1a17a60b15354')
    originals = EVIDENCE / 'typed-framework-results-read01/decoded01/originals'
    inner_raw = raw_pin(originals / 'attempt-01/terminal.json', 28758,
        '139163acad47d9db707faa950e4b4dcecaf3e72b655bce8b6b3db089ce542bdf')
    outer_raw = raw_pin(originals / 'build-fences-01/terminal.json', 1177,
        '3626270e88e72c4e46d8beee09b5351e1f7d53bab18043241204ca314855e04d')
    patch = b''.join(diff(baseline.get(name, b''), candidate[name], name) for name in sorted(candidate))
    provenance = {'schema': 1, 'state': 'SOURCE_FROZEN_NOT_COMPILED_OR_DEVICE_REUSE_QUALIFIED',
        'frozen_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'actual_parent_source_manifest': pin(parent_manifest_raw), 'actual_parent_compile': pin(parent_result_raw),
        'actual_parent_revision': '466-go5', 'actual_parent_source_file_count': 465,
        'candidate_revision': '467-source-resume', 'candidate_source_file_count': 466,
        'replaced_existing': {name: {'before': pin(baseline[name]), 'after': pin(candidate[name])} for name in REPLACED},
        'added': {name: pin(candidate[name]) for name in ADDED}, 'unchanged_existing_files': 462,
        'Cargo_lock_and_dependency_manifests_changed': False, 'typed_source_lock_changed': False,
        'Go5_and_framework_patches_changed': False, 'actual_staging_observation': pin(staging_raw),
        'observation_assessment': pin(assessment_raw), 'original_failed_inner_terminal': pin(inner_raw),
        'original_failed_outer_terminal': pin(outer_raw), 'original_timeout_seconds': 6100,
        'original_reaped_children': 296, 'original_failures_preserved': True,
        'staging_observed_candidate_prefix': 145, 'candidate_prefix_reuse_qualified': False,
        'project146': {'path': 'prebuilts/gcc/linux-x86/host/x86_64-linux-glibc2.17-4.8',
            'locked_commit': 'ae37c9849d97a20b97ff5ce93a5b171c6d5d02ab',
            'historical_shape': 'initial symbolic HEAD, exact origin, index ENOENT, index.lock 0 bytes',
            'unobserved_nlink_loose_ref_packed_refs_clean_objects': 'fresh execution gates, never prequalified'},
        'normal_manifest_links_and_verifier_required_before_publication': True,
        'root_lock_owner_retirement_gate_required_for_real_reuse': True,
        'rust_controls': {'declared': source_tests, 'compiled': False, 'executed': False},
        'local_git_mechanism_controls_only': pin((WORK / 'git-mechanism-controls.stdout.json').read_bytes()),
        'local_Rust_toolchain_available': False, 'remote_submitted': False, 'Main_actions': 0,
        'App_or_runtime_readiness_claimed': False}

    source = old_controller.decode()
    source = exact(source, 'fresh paired-generation builder466 Go5 revision and run 9 exact projection/CLI/typed-lock tests',
        'fresh builder467 source-resume revision and run 9 updater plus 9 source-resume controls')
    source = exact(source, "BASE_SOURCE = Path('/home/alex/work/pocket4-native-typed-ingress-builder465-compile-01-20261105/builder-source')",
        'BASE_SOURCE = Path(' + repr(PARENT_REMOTE + '/builder-source') + ')')
    source = exact(source, 'ROOT = Path(' + repr(PARENT_REMOTE) + ')', 'ROOT = Path(' + repr(REMOTE) + ')')
    source = assignment(source, 'MANIFEST_PARENT', pin(parent_manifest_raw)['sha256'])
    source = source.replace('MANIFEST_466', 'MANIFEST_467')
    source = assignment(source, 'MANIFEST_467', pin(manifest_raw)['sha256'])
    source = assignment(source, 'FIXED_GO5_DELTA', sorted(candidate))
    source = source.replace('FIXED_GO5_DELTA', 'FIXED_RESUME_DELTA')
    source = exact(source, 'DEADLINE = None', 'SOURCE_RESUME_TESTS = ' + repr(source_tests) + '\nSOURCE_REGISTERED_TESTS = ' + repr(baseline_tests + source_tests) + '\nDEADLINE = None')
    source = exact(source, "for path in [Path('/usr/bin/git'),Path('/usr/bin/ninja'),Path('/usr/bin/cp'),Path('/usr/bin/ldd')]:",
        "for path in [Path('/usr/bin/git'),Path('/usr/bin/timeout'),Path('/usr/bin/ninja'),Path('/usr/bin/cp'),Path('/usr/bin/ldd')]:")
    source = exact(source, "Path('/usr/bin/git'),Path('/usr/bin/ninja'),selected['rustdoc']]):",
        "Path('/usr/bin/git'),Path('/usr/bin/timeout'),Path('/usr/bin/ninja'),selected['rustdoc']]):")
    source = exact(source, "'scope':'fresh builder466 Go5 revision, 465 source files and 9 exact projection/CLI/typed-lock tests; no Soong/Java/Android/full-engine/service execution'",
        "'scope':'fresh builder467 source-resume revision, 466 source files, 9 exact updater tests and 9 source-resume controls in owned local fixtures; no real staging/Soong/Java/Android/service execution'")
    source = exact(source, "'expected_test_names':TESTS}", "'expected_test_names':TESTS,'expected_source_resume_test_names':SOURCE_RESUME_TESTS}")
    source = exact(source, "pinned_packet('compiled-parent465-manifest.json',MANIFEST_PARENT)",
        "pinned_packet('compiled-parent466-manifest.json',MANIFEST_PARENT)")
    source = exact(source, "pinned_packet('expected-builder466-manifest.json',MANIFEST_467)",
        "pinned_packet('expected-builder467-manifest.json',MANIFEST_467)")
    source = exact(source, "len(expected)==465 and len(copied_expected)==465", "len(expected)==465 and len(copied_expected)==466")
    source = exact(source, "pinned_packet('compiled-parent465-result.json',\n            '36158e522a8562b42e2800c89fc4e96a3b8bed8ad8c7e4d0fc8a7b56278028d8')",
        "pinned_packet('compiled-parent466-result.json',\n            '" + pin(parent_result_raw)['sha256'] + "')")
    source = exact(source, "parent['focused_tests_passed']==26", "parent['focused_tests_passed']==9")
    source = exact(source, "parent['builder_elf']['sha256']=='061a79f701c87b3e2e8227a69398c6ba0333eb1e723a950a3bde028b0a52b135'",
        "parent['builder_elf']['sha256']=='309e96393ab482c958a519b78a455a6c75d156a6edb805c840aa6d21f76fa96a'")
    source = source.replace('compiled parent465', 'compiled parent466').replace('actual_parent465_compile_authority', 'actual_parent466_compile_authority')
    start = source.index('        changes=[name for name in copied_expected')
    stop = source.index('        env.update(', start)
    source = source[:start] + '''        changes=[name for name in copied_expected if copied_expected[name]!=expected.get(name)]
        wanted=FIXED_RESUME_DELTA
        require(sorted(changes)==wanted and set(expected).issubset(copied_expected) and
                sum(name not in expected for name in changes)==1 and
                sum(name in expected for name in changes)==3 and
                set(copied_expected)-set(expected)=={'tools/droidloom-source/src/resume.rs'},
                'source-resume delta is not exactly three replacements and one added module')
        for name in changes:
            wanted_row=copied_expected[name]
            data,pin=pinned_packet('delta/'+name,wanted_row['sha256'])
            require(pin['bytes']==wanted_row['bytes'] and wanted_row['kind']=='file','source-resume delta differs')
            target=COPIED/name
            if name in expected:
                require(hash_held(target)==copied_before[name],
                        'copied parent source differs before source-resume delta')
                fd=os.open(target,os.O_WRONLY|os.O_TRUNC|os.O_CLOEXEC|os.O_NOFOLLOW)
                with os.fdopen(fd,'wb') as stream:
                    require(stream.write(data)==len(data),'short source-resume write')
                    stream.flush();os.fsync(stream.fileno())
            else:
                write_new(target,data)
            os.chmod(target,wanted_row['mode'],follow_symlinks=False)
        candidate_rows=regular_tree(COPIED)
        actual_map=portable(candidate_rows,copied_expected)
        require(json.loads(new_bytes)==actual_map and sha(new_bytes)==MANIFEST_467,
                'actual copied 466-file builder467 manifest differs')
        report['copied_manifest']=write_new(OUT/'copied-builder-source-manifest.json',new_bytes)
        report['source_delta']={'changed_existing':[name for name in wanted if name in expected],
                                'added':[name for name in wanted if name not in expected],
                                'unchanged_existing':462,'actual_source_file_count':466,
                                'builder_revision_name':'467-source-resume','Rust_source_files_changed':4,
                                'Cargo_lock_or_dependency_manifest_changed':False,
                                'Go5_or_Blueprint_patch_changed':False,'engine_source_files_changed':0,
                                'typed_ingress_framework_patch_changed':False,'source_lock_changed':False,
                                'real_source_staging_accessed':False,'framework_sources_executed_or_built':False,
                                'runtime_authorization_enabled':False}
''' + source[stop:]
    source = exact(source,
        "        test_build=command([common[0],'test',*common[1:],'--no-run','--message-format=json-render-diagnostics'],COPIED,env,'builder-test-compile',report['commands'],180)",
        "        resume_help=command([str(builder),'native-role-ingress-build','--help'],COPIED,env,'source-resume-cli-help',report['commands'],10)\n"
        "        require(all(option in resume_help for option in [b'--work',b'--out',b'--resume-source-staging']),\n"
        "                'typed source-resume CLI does not expose the explicit fixed route arguments')\n"
        "        test_build=command([common[0],'test',*common[1:],'--no-run','--message-format=json-render-diagnostics'],COPIED,env,'builder-test-compile',report['commands'],180)")
    insertion = '''        source_packages=[p for p in metadata['packages'] if p['name']=='droidloom-source' and
                         p['manifest_path']==str(COPIED/'tools/droidloom-source/Cargo.toml') and p['source'] is None]
        require(len(source_packages)==1,'source controls do not identify the exact copied library package')
        source_package=source_packages[0]
        source_tree=command([str(tools['cargo']),'tree','--offline','--locked','-p','droidloom-source',
                             '--target','x86_64-unknown-linux-gnu','--edges','normal,build,dev',
                             '--prefix','none','--format','{p}','--color','never'],
                            COPIED,env,'source-resume-selected-test',report['commands'],30)
        selected_source=parse_selected_tree(source_tree,COPIED)
        selected_builder=parse_selected_tree(trees[1],COPIED)
        require(selected_source and all(key in selected_builder and selected_builder[key]==directory
                for key,directory in selected_source.items()),
                'source test dependency closure adds a package outside the already qualified complete builder closure')
        source_build=command([str(tools['cargo']),'test','--offline','--locked','-j','1','-p',
                              'droidloom-source','--lib','--no-run','--message-format=json-render-diagnostics'],
                             COPIED,env,'source-resume-test-compile',report['commands'],90)
        report['actual_source_test_compile_packages']=qualify_compiler_inputs(
            source_build,packages,dependency_rows,candidate_rows)
        source_artifacts=[]
        for line in source_build.decode().splitlines():
            if not line.strip():continue
            item=json.loads(line)
            if item.get('reason')=='compiler-artifact' and item.get('package_id')==source_package['id'] and item.get('executable'):
                require(item['profile']['test'] is True and item['target']['kind']==['lib'] and
                        item['target']['src_path']==str(COPIED/'tools/droidloom-source/src/lib.rs'),
                        'source control artifact is not the exact copied library test target')
                source_artifacts.append(Path(item['executable']))
        require(len(source_artifacts)==1 and source_artifacts[0].is_relative_to(OUT/'cargo-target'),
                'source test executable is ambiguous or escaped the new target')
        source_test_binary=source_artifacts[0]
        source_test_pin=hash_held(source_test_binary)
        require(source_test_binary.lstat().st_mode&0o111,'source test artifact is not executable')
        with source_test_binary.open('rb') as stream:
            require(stream.read(4)==b'\\x7fELF','source test artifact is not ELF')
        source_list=command([str(source_test_binary),'--list'],COPIED,env,'source-resume-test-list',report['commands'],10).decode()
        source_names=[line[:-6] for line in source_list.splitlines() if line.endswith(': test')]
        require(len(source_names)==len(set(source_names))==20 and set(source_names)==set(SOURCE_REGISTERED_TESTS) and
                not any(line.endswith(': benchmark') for line in source_list.splitlines()),
                'source test registrations differ from the eleven baseline and nine new controls')
        source_help=command([str(source_test_binary),'--help'],COPIED,env,'source-resume-test-help',report['commands'],10).decode()
        require(re.search(r'^\\s*--logfile\\s',source_help,re.MULTILINE) is not None and
                'Write logs to the specified file' in source_help,
                'source test executable lacks independent libtest result support')
        report['source_resume_result_gates']=[]
        for index,name in enumerate(SOURCE_RESUME_TESTS,start=len(TESTS)):
            report['source_resume_result_gates'].append(focused_test(
                source_test_binary,name,index,len(source_names),test_env,report['commands']))
        require(hash_held(source_test_binary)==source_test_pin,'source test ELF changed while tested')
        report['source_test_elf']=source_test_pin
        report['source_actual_registered_test_count']=len(source_names)
        report['source_resume_tests_passed']=len(SOURCE_RESUME_TESTS)
        report['source_original_tests_listed_not_rerun']=len(SOURCE_REGISTERED_TESTS)-len(SOURCE_RESUME_TESTS)
        report['source_test_fixtures_network_disabled']=True
        report['actual_device_staging_reuse_qualified']=False
'''
    source = exact(source,
        "        require(hash_held(builder)==builder_pin and hash_held(test_binary)==test_pin,'actual ELF changed while tested')",
        insertion + "        require(hash_held(builder)==builder_pin and hash_held(test_binary)==test_pin,'actual ELF changed while tested')")
    source = exact(source, "report['focused_tests_passed']=len(TESTS)",
        "report['updater_focused_tests_passed']=len(TESTS)\n        report['focused_tests_passed']=len(TESTS)+len(SOURCE_RESUME_TESTS)")
    source = exact(source, "report['parent_targeted_tests_passed_historically']=26", "report['parent_targeted_tests_passed_historically']=9")
    source = exact(source, "'source_files':465", "'source_files':466")
    source = exact(source, "'focused_existing_tests':TESTS}", "'focused_existing_tests':TESTS,'source_resume_tests':SOURCE_RESUME_TESTS}")
    ast.parse(source)
    old_defs, new_defs = functions(old_controller.decode()), functions(source)
    assert set(old_defs) == set(new_defs)
    assert sorted(name for name in old_defs if old_defs[name] != new_defs[name]) == ['execute', 'toolchain']
    unchanged = sorted(name for name in old_defs if old_defs[name] == new_defs[name])

    old_packet = json.loads((OLD / 'verified-source-packet.json').read_bytes())
    omitted = {'compiled-parent465-manifest.json', 'compiled-parent465-result.json',
        'expected-builder466-manifest.json', 'compile_builder.py',
        'delta/android/apex-compat/0008-soong-leaf-go-memory-budget.patch'}
    data = {name: text.encode() for name, text in old_packet.items() if name not in omitted}
    inherited = {name: pin(raw) for name, raw in data.items()}
    data.update({'compiled-parent466-manifest.json': parent_manifest_raw,
        'compiled-parent466-result.json': parent_result_raw,
        'expected-builder467-manifest.json': manifest_raw, 'compile_builder.py': source.encode()})
    data.update({'delta/' + name: raw for name, raw in candidate.items()})
    assert len(data) == 17
    old_stage = (OLD / 'stage.py').read_text()
    stage = exact(old_stage, PARENT_REMOTE, REMOTE)
    stage = assignment(stage, 'EXPECTED', {name: pin(raw) for name, raw in data.items()})
    assert functions(stage) == functions(old_stage)
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
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ('ENVELOPE','COMPRESSED','UNCOMPRESSED'):
            normalized = assignment(normalized, node.targets[0].id, ast.literal_eval(node.value))
    assert ast.dump(ast.parse(normalized), include_attributes=False) == ast.dump(ast.parse(old_boundary), include_attributes=False)
    old_request = json.loads((OLD / 'exact-request.json').read_bytes())
    request = dict(old_request)
    request['args'] = ['-I', '-B', '-c', boundary]
    request['stdin'] = envelope.decode()
    request['idempotency_key'] = KEY
    assert {k: v for k, v in request.items() if k not in ('args','stdin','idempotency_key')} == {
        k: v for k, v in old_request.items() if k not in ('args','stdin','idempotency_key')}
    assert request['host'] == 'pocket4' and request['executable'] == '/usr/bin/python3'
    assert request['cpu_quota_percent'] == 100 and request['memory_max_bytes'] == 1073741824
    assert request['timeout_seconds'] == 600 and request['nice'] == 15 and 'env' not in request
    controller_patch = diff(old_controller, source.encode(), 'compile_builder.py')
    checks = {'schema': 1, 'state': 'FROZEN_BUILDER467_COMPILE_REQUEST_NOT_SUBMITTED',
        'actual_parent_compile': pin(parent_result_raw), 'actual_parent_manifest': pin(parent_manifest_raw),
        'candidate_manifest': pin(manifest_raw), 'candidate_source_paths': sorted(candidate),
        'changed_existing_functions': ['execute','toolchain'], 'unchanged_functions': unchanged,
        'stage_main_AST_unchanged': True, 'transport_AST_unchanged_except_three_pins': True,
        'request_resource_settings_unchanged': True, 'Main_actions': 0, 'real_staging_accessed': False,
        'old_source_or_target_mutated': False, 'candidate_manifest_generated_from_complete_actual_parent': True,
        'inherited_authority_packets': inherited, 'packet_files': len(data),
        'uncompressed_stage': pin(uncompressed), 'compressed_stage': pin(compressed), 'stdin_envelope': pin(envelope),
        'controller': pin(source.encode()), 'expected_updater_registered': 199,
        'expected_updater_targeted': 9, 'expected_source_registered': 20, 'expected_source_targeted': 9,
        'Rust_execution_local': False, 'Rust_control_results_fabricated': False,
        'remote_submitted': False, 'runtime_authorization_enabled': False,
        'original_failed_framework_evidence_preserved': True}
    artifacts = dict(data)
    artifacts.update({'stage.py': stage.encode(), 'transport-boundary.py': boundary.encode(),
        'verified-source-packet.json': (packet + '\n').encode(), 'exact-request.json': encoded(request),
        'compiler466-to467.patch': controller_patch,
        'stage466-to467.patch': diff(old_stage.encode(), stage.encode(), 'stage.py'),
        'transport466-to467.patch': diff(old_boundary.encode(), boundary.encode(), 'transport-boundary.py'),
        'source-resume.patch': patch, 'SOURCE_PROVENANCE.json': encoded(provenance),
        'LOCAL_SOURCE_CHECKS.json': encoded(checks), 'make_request.py': Path(__file__).read_bytes()})
    artifacts['README.md'] = b'''# Builder467 source-resume compile01

This compile-only request copies the complete, actually qualified builder466 Go5 source tree into a fresh root. It replaces three exact Rust files, adds one recovery module, and verifies all 466 resulting files. The other 462 files retain their original bytes and modes. Cargo.lock, dependency manifests, the typed source lock, framework patches, Go5 and Blueprint data are unchanged. The actual builder466 compile receipt and complete manifest are the parent authority; prior failed attempts stay untouched.

The requested build uses the same direct installed Rust 1.93 tools, offline locked dependency closure, owned single CPU, 1GiB limit, nice 15 and 600-second outer budget. The controller keeps the original 550-second internal deadline, subreaper cleanup, tool/source/config/dependency checks, ELF binding and independent libtest-result checks. It adds /usr/bin/timeout to the observed tool closure. The source-library test closure must be a subset of the already qualified builder closure; no new registry inputs are permitted. It compiles the normal builder and updater tests, checks the explicit resume CLI help, runs the nine existing updater controls, compiles the source library test executable, verifies its exact eleven baseline plus nine new registrations, and runs the nine new recovery controls. HTTPS is disabled inside the source unit-test build; fixture object transfer uses only explicitly allowed local file transport.

The source candidate rechecks every selected staging project against its exact locked commit, origin, sparse selection and clean state. Completed projects are reused without fetch/checkout. An initial interrupted checkout is supported only with its unresolved initial branch, absent loose/packed branch and index, exact origin/sparse state, and an absent or empty private single-link index.lock. An observed empty lock is retained under the new attempt with its identity; a nonempty lock stays in place and fails. A locally available exact commit avoids redundant fetch; plain checkout has no force/reset/clean path. Every Git call has a bounded timeout, and progress is create-only and fsynced before continuing. Root links and the complete manifest are produced only after every project passes; the original verifier and atomic final directory publication remain mandatory. The normal caller retains its existing work/source locks. A real resume still requires Root to bind the retired job, fresh staging identity and a new normal build attempt; this compile does not access the actual AOSP staging directory.

The historical normal framework build remains FAILED after its inner 6100-second timeout, with cleanup complete and 296 children reaped. The later observation contains 145 matching HEAD/origin candidates, an initial checkout at project146, and 68 absent projects. Those observations are not reuse, Java, JNI or App readiness qualification. The Rust controls have not been executed when this package is frozen; only a real successful result can establish their outcome. No Hepta request is submitted by this generator.
'''
    source_artifacts = {'candidate/' + name: raw for name, raw in candidate.items()}
    source_artifacts.update({'baseline/' + name: raw for name, raw in baseline.items()})
    source_artifacts.update({'parent466-source-manifest.json': parent_manifest_raw,
        'expected-builder467-manifest.json': manifest_raw, 'source-resume.patch': patch,
        'SOURCE_PROVENANCE.json': encoded(provenance), 'actual-parent466-compile.json': parent_result_raw,
        'actual-staging-read03.stdout.log': staging_raw, 'actual-staging-assessment.json': assessment_raw,
        'original-failed-inner-terminal.json': inner_raw, 'original-failed-outer-terminal.json': outer_raw,
        'git_mechanism_controls.py': (WORK / 'git_mechanism_controls.py').read_bytes(),
        'git-mechanism-controls.stdout.json': (WORK / 'git-mechanism-controls.stdout.json').read_bytes(),
        'git-mechanism-controls.stderr.txt': (WORK / 'git-mechanism-controls.stderr.txt').read_bytes()})
    # PLAN is the controller's existing non-executing mode: it cannot make the
    # remote root, invoke Cargo, or materialize source in this local check.
    plan = subprocess.run([sys.executable, '-I', '-B', '-c', source], capture_output=True, check=True)
    assert plan.stderr == b'' and json.loads(plan.stdout)['mode'] == 'PLAN'
    assert not Path(REMOTE).exists()
    artifacts['PLAN.json'] = plan.stdout
    write_tree(SOURCE, source_artifacts)
    write_tree(DEST, artifacts)
    print(json.dumps({'source_root': str(SOURCE), 'compile_root': str(DEST),
        'source_pins': pin((SOURCE / 'SOURCE_PINS.json').read_bytes()),
        'compile_pins': pin((DEST / 'SOURCE_PINS.json').read_bytes()),
        'request': pin(artifacts['exact-request.json']), 'controller': pin(source.encode()),
        'Rust_patch': pin(patch), 'controller_patch': pin(controller_patch),
        'candidate_manifest': pin(manifest_raw), 'packet_files': len(data),
        'PLAN_exit_code': plan.returncode, 'remote_submitted': False}, indent=2))


if __name__ == '__main__':
    main()
