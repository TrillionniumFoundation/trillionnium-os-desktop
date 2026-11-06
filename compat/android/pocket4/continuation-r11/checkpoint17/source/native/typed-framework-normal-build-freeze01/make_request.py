#!/usr/bin/env python3
"""Bind the actual builder/work receipts to the normal strict two-target build."""
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
EVIDENCE = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence')
OLD = BASE / 'full-engine-candidate07-go5-bound-01'
COMPILE = BASE / 'typed-ingress-builder466-go5-compile02'
PREPARE = BASE / 'typed-framework-work-preparation-freeze01'
DEST = BASE / 'typed-framework-normal-build-freeze01'
REMOTE = '/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-build-01-20261105'
KEY = 'pocket4-native-typed-ingress-framework-strict-two-target-build-01-20261105'


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def exact(source, before, after):
    assert source.count(before) == 1, before[:200]
    return source.replace(before, after)


def definitions(source):
    return {node.name: ast.dump(node, include_attributes=False)
            for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)}


def assignment(source, name, replacement):
    nodes = [node for node in ast.parse(source).body if isinstance(node, ast.Assign)
             and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name]
    assert len(nodes) == 1, name
    return exact(source, ast.get_source_segment(source, nodes[0]), name + ' = ' + repr(replacement))


def diff(before, after, name):
    return ''.join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True),
                                      fromfile='a/' + name, tofile='b/' + name)).encode()


def main():
    assert not DEST.exists()
    old_raw = (OLD / 'combined_build_streaming.py').read_bytes()
    assert pin(old_raw) == {'bytes': 54249, 'sha256': '702697443b0e1ffa351733a29141be866a81b8be2d2b210b3d36963aa49f5058'}
    old_source = old_raw.decode()
    old_functions = {node.name: ast.get_source_segment(old_source, node) for node in ast.parse(old_source).body
                     if isinstance(node, ast.FunctionDef)}
    common = ['digest', 'utc', 'require', 'save', 'no_alias', 'memory_admission', 'owned_resource_gate',
              'subreaper', 'child_ids', 'cleanup_children']
    new_body = (BASE / 'typed-framework-build-work01/framework_body.py').read_text()
    build = old_functions['build']
    build = exact(build, '    prepared, files, engine, builder_files, baseline, effective = verify_prepared(expected_sha)',
                  '    context = verify_prepared(expected_sha)')
    build = exact(build, 'STARTING_COMBINED07_GO5_STREAMING_FLAG0_COLD_BUILD',
                  'STARTING_TYPED_FRAMEWORK_NORMAL_STRICT_TWO_TARGET_BUILD')
    build = exact(build, '    save(ATTEMPT / "claim.json", claim)',
        '    claim["filesystem_available_before"] = os.statvfs(WORK).f_bavail * os.statvfs(WORK).f_frsize\n'
        '    save(ATTEMPT / "claim.json", claim)\n'
        '    save(ATTEMPT / "input-bindings-before.json", {\n'
        '        "work_preparation": context["prepared_pin"], "actual_builder_compile": context["compiled_pin"],\n'
        '        "actual_builder_manifest": context["builder_map_pin"], "actual_content_manifests": context["manifest_pins"],\n'
        '        "reused_inventory_source": context["inventory_pin"], "observations": context["initial_observations"]})')
    build = exact(build, '    env["DROIDLOOM_NATIVE_BRIDGE_SOURCE"] = str(ENGINE_SOURCE)',
        '    env["DROIDLOOM_NATIVE_BRIDGE_SOURCE"] = str(ENGINE_SOURCE)\n'
        '    env["PATH"] = "/usr/bin:/usr/sbin:/bin:/sbin"\n'
        '    env["PYTHONDONTWRITEBYTECODE"] = "1"')
    build = exact(build, '        artifact = artifact_gate(engine, effective, builder_files)\n'
        '        require(source_contract()[0] == files, "frozen input changed during full build")\n'
        '        require(inventory(BUILD_SOURCE) == builder_files and hashes(ENGINE_SOURCE, True) == engine,\n'
        '                "owned input changed during full build")\n'
        '        require(digest(BUILDER) == BUILDER_SHA, "builder binary changed during full build")',
        '        artifact = completion_gate(context)')
    build = exact(build, '        observation_errors = []',
        '        input_after = None\n'
        '        input_after_error = None\n'
        '        try:\n'
        '            input_after = verify_inputs_after(context)\n'
        '            save(ATTEMPT / "input-bindings-after.json", input_after)\n'
        '        except BaseException as error:\n'
        '            input_after_error = repr(error)\n'
        '            if failure is None:\n'
        '                failure = "post-build input qualification failed: " + repr(error)\n'
        '        observation_errors = []')
    build = exact(build, '"ARTIFACTS_BUILT_QUALIFICATION_PENDING"',
        '"FRAMEWORK_COMMAND_COMPLETED_QUALIFICATION_PENDING"')
    build = exact(build, '                    "artifact_gate": artifact, "Main_actions": 0, "Android_actions": 0,',
        '                    "normal_command_completion_gate": artifact,\n'
        '                    "input_after_qualified": input_after is not None and input_after_error is None,\n'
        '                    "input_after_error": input_after_error,\n'
        '                    "work_preparation_sha256": PREPARATION_SHA, "builder_compile_sha256": BUILD_RESULT_SHA,\n'
        '                    "builder_sha256": BUILDER_SHA, "strict_targets": TARGETS,\n'
        '                    "complete_framework_Java_and_Android_TU_qualified": False,\n'
        '                    "runtime_authorization_enabled": False, "Main_actions": 0, "Android_actions": 0,')
    header = '''#!/usr/bin/env python3
"""Run the normal builder on an independent prepared framework workspace; never deploy."""
import argparse, ctypes, datetime, hashlib, json, os, pathlib, resource, signal, stat, subprocess, time
P = pathlib.Path

'''
    entry = '''def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', action='store_true')
    parser.add_argument('--preparation-sha256')
    args = parser.parse_args(argv)
    if not args.build:
        require(args.preparation_sha256 is None, 'SHA provided without build mode')
        print(json.dumps(plan(), indent=2))
        return 0
    require(args.preparation_sha256 is not None, 'build requires its actual work receipt')
    return build(args.preparation_sha256)

if __name__ == '__main__':
    raise SystemExit(main())
'''
    controller = header + '\n\n'.join(old_functions[name] for name in common) + '\n\n' + new_body + '\n\n' + build + '\n\n' + entry
    source_defs = definitions(controller)
    for name in common:
        assert source_defs[name] == definitions(old_source)[name], name
    snapshot = (OLD / 'main_snapshot.py').read_bytes()
    assert pin(snapshot)['sha256'] == 'f909bdfcaedfef29fcc1ba6a994c49bc21e99850204bac7e0565548bcd7139cb'
    work_raw = (EVIDENCE / 'typed-framework-work-preparation01/result.json').read_bytes()
    assert pin(work_raw) == {'bytes': 11091, 'sha256': 'ab286f3939acfeb648a716ca15e5df348fef6b7007eb5651735fe8a7bda96b1c'}
    work = json.loads(work_raw)
    assert work['state'] == 'PREPARED_INPUTS_NOT_MATERIALIZED_OR_BUILT' and not work['first_error'] and not work['secondary_errors']
    build_raw = (EVIDENCE / 'typed-ingress-builder466-go5-compile02/result.json').read_bytes()
    assert pin(build_raw) == {'bytes': 98764, 'sha256': '2d6c80a29e957b1e97764d8785257eb47c3d0b899f301e64c9a9c418e96ea0ab'}
    actual = json.loads(build_raw)
    assert actual['state'] == 'PASS' and actual['focused_tests_passed'] == 9 and actual['actual_registered_test_count'] == 199
    assert len(actual['commands']) == 41 and all(c['returncode'] == 0 and not c['timed_out'] for c in actual['commands'])
    for c in actual['commands']:
        if c['label'].startswith('projection-test-'):
            value = ('ok ' + c['focused_result_gate']['exact_name'] + '\n').encode()
            assert c['independent_libtest_result']['bytes'] == len(value)
            assert c['independent_libtest_result']['sha256'] == pin(value)['sha256']
    inventory_source = (PREPARE / 'prepare_work.py').read_bytes()
    assert pin(inventory_source) == {'bytes': 48443, 'sha256': '203dd7f4efdac01891a4c31fd79f2eb3204e3c8c2be5702988f0875307cce9ab'}
    builder_map = (COMPILE / 'expected-builder466-manifest.json').read_bytes()
    assert pin(builder_map) == {'bytes': 91758, 'sha256': actual['copied_manifest']['sha256']}
    old_fence = (OLD / 'fenced_build_streaming.template.py').read_text()
    fence = assignment(old_fence, 'CONTROLLER_SHA', pin(controller.encode())['sha256'])
    fence = assignment(fence, 'PREPARATION_SHA', pin(work_raw)['sha256'])
    fence = assignment(fence, 'ROOT', None).replace('ROOT = None', 'ROOT = Path(' + repr(REMOTE) + ')')
    fence = exact(fence, "    require(sha((ROOT / 'preparation.json').read_bytes()) == PREPARATION_SHA, 'actual preparation changed')",
        "    require(sha((ROOT / 'control-source/actual-work-preparation.json').read_bytes()) == PREPARATION_SHA,\n"
        "            'staged actual work preparation changed')")
    main_limits = {'memory.high': '5368709120', 'memory.max': '6442450944', 'memory.swap.max': 'max',
                   'cpu.max': '200000 100000', 'pids.max': '12288'}
    fence = exact(fence, "        before = capture('before', snapshot, packet['snapshot_sha256'])",
        "        before = capture('before', snapshot, packet['snapshot_sha256'])\n"
        "        require(before['limits'] == " + repr(main_limits) + ",\n"
        "                'original activation five-limit contract differs; TasksMax must remain 12288')")
    fence = exact(fence, "            after = capture('after', snapshot, packet['snapshot_sha256'])",
        "            after = capture('after', snapshot, packet['snapshot_sha256'])\n"
        "            require(after['limits'] == " + repr(main_limits) + ",\n"
        "                    'original activation five-limit contract differs after build')")
    assert sorted(n for n in definitions(fence) if definitions(fence)[n] != definitions(old_fence)[n]) == ['run']
    before_main = (EVIDENCE / 'candidate07-go5-build01/originals/build-fences-01/before.json').read_bytes()
    assert pin(before_main) == {'bytes': 2304, 'sha256': 'c16e1ddf15eeda8edefee46fdfd95e85504d5f51bfa202d23595d46dec2b71c8'}
    before_document = json.loads(before_main)
    assert before_document['limits'] == main_limits
    assert before_document['activation_sha256'] == '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
    data = {'framework_build.py': controller.encode(), 'fenced_build.py': fence.encode(),
            'main_snapshot.py': snapshot, 'frozen-work-inventory.py': inventory_source,
            'actual-work-preparation.json': work_raw, 'actual-builder466-result.json': build_raw,
            'expected-builder466-manifest.json': builder_map}
    old_stage = (COMPILE / 'stage.py').read_text()
    stage = assignment(old_stage, 'ROOT', None).replace('ROOT = None', 'ROOT = Path(' + repr(REMOTE) + ')')
    stage = assignment(stage, 'EXPECTED', {name: pin(raw) for name, raw in data.items()})
    stage = exact(stage, '    os.umask(0o077)',
        "    parent=ROOT.parent.lstat()\n"
        "    if [parent.st_dev,parent.st_ino,parent.st_mode,parent.st_uid,parent.st_gid]!=[66306,34351895,16832,1000,1000]:\n"
        "        raise RuntimeError('fixed strict owned parent identity differs')\n"
        "    os.umask(0o077)")
    stage = exact(stage,
        "    os.execve('/usr/bin/python3',['/usr/bin/python3','-I','-B',str(source/'compile_builder.py'),'--execute-once'],{'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'})",
        "    scope={'__name__':'frozen_framework_main_fence','__file__':str(source/'fenced_build.py')}\n"
        "    exec(compile(packet['fenced_build.py'],str(source/'fenced_build.py'),'exec'),scope,scope)\n"
        "    raise SystemExit(scope['run']({'controller_source':packet['framework_build.py'],\n"
        "        'snapshot_source':packet['main_snapshot.py'],\n"
        "        'snapshot_sha256':EXPECTED['main_snapshot.py']['sha256']}))")
    packet = json.dumps({name: raw.decode() for name, raw in data.items()}, sort_keys=True, ensure_ascii=True)
    uncompressed = (stage + '\nPACKET=json.loads(' + repr(packet) + ')\nmain(PACKET)\n').encode()
    ast.parse(uncompressed)
    compressed = gzip.compress(uncompressed, compresslevel=9, mtime=0)
    envelope = (json.dumps({'schema': 1, 'encoding': 'gzip+base64', 'compressed': pin(compressed),
        'uncompressed': pin(uncompressed), 'payload': base64.b64encode(compressed).decode()},
        sort_keys=True, separators=(',', ':')) + '\n').encode()
    assert len(envelope) < 1024*1024
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    assert decoder.decompress(compressed, len(uncompressed)+1) == uncompressed
    assert decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail
    old_boundary = (COMPILE / 'transport-boundary.py').read_text()
    boundary = old_boundary
    for name, raw in [('ENVELOPE', envelope), ('COMPRESSED', compressed), ('UNCOMPRESSED', uncompressed)]:
        boundary = assignment(boundary, name, pin(raw))
    request = json.loads((OLD / 'build-request-01/exact-request.json').read_bytes())
    request['args'] = ['-I', '-B', '-c', boundary]
    request['stdin'] = envelope.decode()
    request['idempotency_key'] = KEY
    assert request['cpu_quota_percent'] == 200 and request['memory_max_bytes'] == 10*1024**3
    assert request['timeout_seconds'] == 6400 and request['nice'] == 10
    artifacts = dict(data)
    artifacts.update({'stage.py': stage.encode(), 'transport-boundary.py': boundary.encode(),
        'exact-request.json': (json.dumps(request, indent=2)+'\n').encode(),
        'verified-source-packet.json': (packet+'\n').encode(),
        'normal-build07-to-framework01.patch': diff(old_functions['build'].encode(), build.encode(), 'build-function.py'),
        'main-fence07-to-framework01.patch': diff(old_fence.encode(), fence.encode(), 'fenced_build.py'),
        'stage-compile02-to-framework01.patch': diff(old_stage.encode(), stage.encode(), 'stage.py'),
        'input-and-completion-bindings.py': new_body.encode(),
        'main-limit-original-before.json': before_main,
        'make_request.py': Path(__file__).read_bytes()})
    checks = {'schema': 1, 'state': 'ACTUAL_INPUT_BOUND_NORMAL_FRAMEWORK_REQUEST_NOT_SUBMITTED',
        'actual_builder_compile': pin(build_raw), 'actual_work_preparation': pin(work_raw),
        'actual_builder_ELF': actual['builder_elf'], 'actual_builder_source_manifest': pin(builder_map),
        'seven_snapshot_inventory_and_authority_packet_members': {name: pin(raw) for name, raw in data.items()},
        'normal07_helpers_AST_identical': common,
        'normal07_builder_wait_resource_swap_cpu_cleanup_logic_retained': True,
        'fence_helpers_AST_identical': sorted(name for name in definitions(fence) if name != 'run'),
        'main_snapshot_bytes_identical': pin(snapshot), 'main_original_five_limits': main_limits,
        'main_original_limits_actual_evidence': pin(before_main),
        'actual_work_manifest_maps_will_be_read_once_locally_on_target_with_original_full_SHA': 5,
        'old_shared_source_modified': False, 'manual_source_manifest_written': False,
        'normal_materialize_reconcile_Strict_two_targets_only': True,
        'fresh_source_and_output_required': True, 'normal_source_projection_restoration_required': True,
        'complete_Java_JNI_artifact_qualification_claimed': False, 'runtime_authorization_enabled': False,
        'new_request_budget_matches_07': {'CPU_percent': 200, 'MemoryMax': 10*1024**3,
            'MemorySwapMax': 1024**3, 'MemAvailable_min': 13*1024**3, 'SwapFree_min': 2*1024**3,
            'jobs': 1, 'timeout_seconds': 6400, 'builder_wait_seconds': 6100},
        'uncompressed_stage': pin(uncompressed), 'compressed_stage': pin(compressed),
        'stdin': pin(envelope), 'controller': pin(controller.encode()), 'fence': pin(fence.encode()),
        'source_materialization_executed_locally': False, 'Soong_executed_locally': False,
        'remote_request_submitted': False, 'Main_actions': 0}
    artifacts['LOCAL_BINDING_CHECKS.json'] = (json.dumps(checks, indent=2)+'\n').encode()
    artifacts['README.md'] = b'''# Normal strict framework build, actual input binding

This request uses the actual builder466 compile02 ELF and its complete 465-file source manifest, and the independently created four-entry work directory from the successful work preparation. It invokes the existing native-role-ingress-build command with only framework-minus-apex and libandroid_runtime in Strict mode. The normal builder performs the fresh 214-project materialization and eight root links, normal package/source locks, exact typed source projection and normal journal recovery/restoration. This wrapper does not create an AOSP source manifest or modify the previous shared AOSP checkout.

The five actual full content-manifest files are read at their fixed receipt-bound paths and hashes in this invocation. Previously reviewed bounded read-only inventory functions verify the complete copied Mesa/Python maps, retained Teto source and full builder source before and after. The twenty copied fixed assets are hashed and matched; no absent Mesa tool is fabricated or given qualification. If the real strict graph needs an unavailable dependency, its error remains a build failure. These observed copied inputs do not prove reproducibility from the original Mesa/Python archives.

The normal07 fresh 13GiB available-memory and 2GiB free-swap admission, two-CPU/jobs1, 10GiB RAM/1GiB own-swap budget, 6100-second builder wait, exact owned process-group cleanup and subreaper logic are retained. Historical memory samples are not admission. Disk availability is recorded, not described as reserved or a proven full-source size bound. The unchanged f909 read-only Main helper binds the original activation 7e490c... and epoch 48cb65... before and after. Its entire original five-limit object is also checked explicitly: memory.high 5368709120, memory.max 6442450944, swap.max max, cpu.max 200000 100000, pids.max 12288. The original successful before snapshot is retained as this binding's source; neither a later 6144 setting nor before-equals-after alone is accepted.

Completion requires the normal attempt/input/command records, exact Strict targets and source-lock hashes, journal restoration and all four original typed source preimages plus absence of the added header after restoration. An exit-zero command is recorded as artifact qualification pending. A framework implementation jar and actual Android JNI compilation/link closure still require their generated artifact evidence; a headers-only jar or host-only library is insufficient. No install, service, Main mutation or runtime role authorization occurs.
'''
    DEST.mkdir(mode=0o700)
    for name, raw in artifacts.items():
        with (DEST/name).open('xb') as stream:
            stream.write(raw)
    planned = subprocess.run([sys.executable, '-I', '-B', str(DEST/'framework_build.py')], capture_output=True, check=True)
    assert not planned.stderr and json.loads(planned.stdout)['targets'] == ['framework-minus-apex', 'libandroid_runtime']
    assert not Path(REMOTE).exists()
    with (DEST/'PLAN.json').open('xb') as stream:
        stream.write(planned.stdout)
    rows = {path.name: pin(path.read_bytes()) for path in sorted(DEST.iterdir()) if path.is_file()}
    (DEST/'SOURCE_PINS.json').write_bytes((json.dumps({'schema': 1, 'files': rows}, indent=2, sort_keys=True)+'\n').encode())
    for path in DEST.iterdir():
        path.chmod(0o444)
    print(json.dumps({'root': str(DEST), 'files': len(rows)+1, 'controller': pin(controller.encode()),
        'fence': pin(fence.encode()), 'request': pin((DEST/'exact-request.json').read_bytes()),
        'stdin': pin(envelope), 'packet_files': len(data), 'reused07_helpers': common,
        'PLAN_exit_code': planned.returncode, 'remote_submitted': False}))


if __name__ == '__main__':
    main()
