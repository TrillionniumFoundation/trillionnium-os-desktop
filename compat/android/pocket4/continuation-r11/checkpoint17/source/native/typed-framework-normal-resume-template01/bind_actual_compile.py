#!/usr/bin/env python3
"""Generate one normal resume request only from the actual successful compile output."""
import argparse
import ast
import base64
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zlib

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'typed-framework-normal-build-freeze01'
DEST = HERE.parent / 'typed-framework-normal-resume-bound01'
REMOTE = '/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-resume-build-01-20261106'
COMPILE_REMOTE = '/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-02-20261105'
KEY = 'pocket4-native-typed-ingress-framework-strict-two-target-resume-build-01-20261106'


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=True) + '\n').encode()


def assignment(source, name, value):
    nodes = [n for n in ast.parse(source).body if isinstance(n, ast.Assign) and len(n.targets) == 1
             and isinstance(n.targets[0], ast.Name) and n.targets[0].id == name]
    require(len(nodes) == 1, 'one fixed binding assignment is required: ' + name)
    before = ast.get_source_segment(source, nodes[0])
    require(source.count(before) == 1, 'binding assignment is ambiguous')
    return source.replace(before, name + ' = ' + repr(value))


def literal(source, name):
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.Assign) and len(n.targets) == 1
                and isinstance(n.targets[0], ast.Name) and n.targets[0].id == name)
    return ast.literal_eval(node.value)


def definitions(source):
    return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)}


def actual_compile(args, template):
    wire = args.compile_stdout.read_bytes()
    require(pin(wire) == {'bytes': args.compile_stdout_bytes, 'sha256': args.compile_stdout_sha256},
            'actual compile stdout does not match its independently supplied observed pin')
    require(0 < len(wire) <= 65536, 'actual compile stdout exceeds its fixed metadata bound')
    terminal = json.loads(wire)
    require(terminal['state'] == 'PASS' and terminal['Main_actions'] == 0 and
            terminal['full_engine_build'] is False and
            terminal['result']['path'] == COMPILE_REMOTE + '/attempt01/result.json',
            'actual compile stdout is not the fixed successful compile terminal')
    raw = args.compile_result.read_bytes()
    require(0 < len(raw) <= 4*1024*1024 and pin(raw) ==
            {key: terminal['result'][key] for key in ('bytes', 'sha256')},
            'actual full compile result does not match the actual stdout carrier pin')
    value = json.loads(raw)
    expected_tests = literal(template, 'EXPECTED_TESTS')
    source_tests = literal(template, 'EXPECTED_SOURCE_TESTS')
    labels = literal(template, 'EXPECTED_COMPILE_LABELS')
    require(value['state'] == 'PASS' and value['focused_tests_passed'] == 18 and
            value['updater_focused_tests_passed'] == 9 and value['source_resume_tests_passed'] == 9 and
            value['actual_registered_test_count'] == 199 and value['source_actual_registered_test_count'] == 20 and
            value['expected_test_names'] == expected_tests and value['expected_source_resume_test_names'] == source_tests,
            'actual updater and source-resume test results are not all qualified')
    commands = value['commands']
    require(len(commands) == len(labels) == 56 and {row['label'] for row in commands} == set(labels) and
            all(row['returncode'] == 0 and row['timed_out'] is False for row in commands),
            'actual complete compiler command closure differs')
    for offset, names, count, elf_key, gates_key in [
        (0, expected_tests, 199, 'test_elf', 'focused_result_gates'),
        (9, source_tests, 20, 'source_test_elf', 'source_resume_result_gates')]:
        require(len(value[gates_key]) == len(names), 'independent test gate count differs')
        for position, name in enumerate(names):
            label = 'projection-test-' + str(offset + position)
            command = next(row for row in commands if row['label'] == label)
            log_path = COMPILE_REMOTE + '/attempt01/' + label + '.libtest'
            gate = {'exact_name': name, 'expected_stdout_runs': 1, 'filtered_out_per_run': count-1,
                    'outer_results': 1, 'registered_tests': count, 'summary_and_independent_result_agree': True}
            log = ('ok ' + name + '\n').encode()
            require(command['argv'] == [value[elf_key]['path'], '--exact', name,
                    '--test-threads=1', '--nocapture', '--logfile', log_path] and
                    command['focused_result_gate'] == gate and value[gates_key][position] == gate and
                    command['independent_libtest_result']['path'] == log_path and
                    {key:command['independent_libtest_result'][key] for key in ('bytes','sha256')} == pin(log),
                    'actual independent exact test result differs: ' + name)
    require(value['actual_build_packages'] == value['actual_test_compile_packages'] and
            len(set(value['actual_build_packages'])) == 49 and
            sum(name.startswith('registry+') for name in value['actual_build_packages']) == 45 and
            value['actual_source_test_compile_packages'] and
            set(value['actual_source_test_compile_packages']).issubset(value['actual_build_packages']) and
            all(value[key] is True for key in ['copied_source_unchanged_after','original_source_unchanged_after',
                'cargo_configs_unchanged_after','source_test_fixtures_network_disabled']) and
            not value['dependency_changes'] and not value['tool_changes'] and not value['observed_signals'],
            'actual source/tool/config/dependency stability was not established')
    require(value['cleanup'] == {'errors':[],'forced_cleanup':False,'initial_owned_children':[],
                'reaped':[],'remaining':[]} and value['owned_resource_gate']['pass'] is True and
            all(value['owned_memory_events_delta'][key] == 0 for key in ('oom','oom_kill','oom_group_kill')),
            'actual compile cleanup or resource gate failed')
    manifest = (HERE / 'expected-builder467-manifest.json').read_bytes()
    require(pin(manifest) == {key:value['copied_manifest'][key] for key in ('bytes','sha256')} and
            value['copied_manifest']['path'] == COMPILE_REMOTE + '/attempt01/copied-builder-source-manifest.json',
            'actual compile does not bind the frozen 466-file builder467 source manifest')
    delta = value['source_delta']
    require(delta['changed_existing'] == ['tools/droidloom-source/src/lib.rs',
                'tools/droidloom-update/src/android.rs','tools/droidloom-update/src/main.rs'] and
            delta['added'] == ['tools/droidloom-source/src/resume.rs'] and delta['unchanged_existing'] == 462 and
            delta['actual_source_file_count'] == 466 and delta['builder_revision_name'] == '467-source-resume' and
            all(delta[key] is False for key in ('Cargo_lock_or_dependency_manifest_changed',
                'Go5_or_Blueprint_patch_changed','source_lock_changed','real_source_staging_accessed')) and
            value['actual_device_staging_reuse_qualified'] is False and
            value['runtime_authorization_enabled'] is False and
            value['framework_Java_and_Android_JNI_compiled'] is False and
            value['transitive_framework_closure_qualified'] is False and
            value['actual_toolchain']['rustup_proxy_executed'] is False and
            value['actual_toolchain']['rustup_proxy_changed_bytes_approved_for_execution'] is False,
            'actual compiler source or authorization scope differs')
    elf = value['builder_elf']
    require(elf == terminal['builder_elf'] and
            elf['path'] == COMPILE_REMOTE + '/attempt01/cargo-target/debug/droidloom-update' and
            0 < elf['bytes'] <= 64*1024*1024 and len(elf['sha256']) == 64 and
            all(c in '0123456789abcdef' for c in elf['sha256']) and elf['identity'][2] & 0o111,
            'actual builder ELF is missing or differs from the producer terminal')
    return raw, value, wire


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compile-result', type=Path, required=True)
    parser.add_argument('--compile-stdout', type=Path, required=True)
    parser.add_argument('--compile-stdout-bytes', type=int, required=True)
    parser.add_argument('--compile-stdout-sha256', required=True)
    args = parser.parse_args()
    require(not DEST.exists(), 'new normal-resume freeze already exists; never overwrite or retry its key')
    for name, wanted in json.loads((HERE / 'SOURCE_PINS.json').read_bytes())['files'].items():
        require(pin((HERE / name).read_bytes()) == wanted, 'frozen template member changed: ' + name)
    template = (HERE / 'framework_build.template.py').read_text()
    actual_raw, actual, actual_stdout = actual_compile(args, template)
    source = template
    for name, value in [('BUILDER_SHA',actual['builder_elf']['sha256']),
                        ('BUILDER_BYTES',actual['builder_elf']['bytes']),
                        ('BUILD_RESULT_SHA',pin(actual_raw)['sha256']),
                        ('BUILD_RESULT_BYTES',len(actual_raw))]:
        require(literal(source,name) is None, 'future actual compile field was already bound: ' + name)
        source = assignment(source,name,value)
    require(definitions(source) == definitions(template), 'binding changed a reviewed controller function')
    fence_template = (HERE / 'fenced_build.template.py').read_text()
    require(literal(fence_template,'CONTROLLER_SHA') is None, 'future controller pin was already bound')
    fence = assignment(fence_template,'CONTROLLER_SHA',pin(source.encode())['sha256'])
    require(definitions(fence) == definitions(fence_template), 'binding changed a fence function')
    data = {name:(HERE/name).read_bytes() for name in ['main_snapshot.py','frozen-work-inventory.py',
        'actual-work-preparation.json','expected-builder467-manifest.json','prior-framework-inner-terminal.json',
        'prior-framework-outer-terminal.json','actual-staging-read03.json']}
    data.update({'framework_build.py':source.encode(),'fenced_build.py':fence.encode(),
                 'actual-builder467-result.json':actual_raw})
    require(len(data) == 10, 'normal-resume packet member set differs')
    stage_template = (HERE/'stage.template.py').read_text()
    require(literal(stage_template,'EXPECTED') is None, 'future staged members were already bound')
    stage = assignment(stage_template,'EXPECTED',{name:pin(raw) for name,raw in data.items()})
    require(definitions(stage) == definitions(stage_template), 'binding changed the original stage function')
    packet = json.dumps({name:raw.decode() for name,raw in data.items()},sort_keys=True,ensure_ascii=True)
    decoded = (stage+'\nPACKET=json.loads('+repr(packet)+')\nmain(PACKET)\n').encode()
    ast.parse(decoded)
    compressed = gzip.compress(decoded,compresslevel=9,mtime=0)
    envelope = (json.dumps({'schema':1,'encoding':'gzip+base64','compressed':pin(compressed),
        'uncompressed':pin(decoded),'payload':base64.b64encode(compressed).decode()},
        sort_keys=True,separators=(',',':'))+'\n').encode()
    require(len(envelope)<1024*1024, 'normal-resume envelope exceeds the original transport bound')
    inflater = zlib.decompressobj(16+zlib.MAX_WBITS)
    require(inflater.decompress(compressed,len(decoded)+1)==decoded and inflater.eof and
            not inflater.unused_data and not inflater.unconsumed_tail, 'fixed single-member gzip verification failed')
    boundary = (HERE/'transport-boundary.template.py').read_text()
    for name,raw in [('ENVELOPE',envelope),('COMPRESSED',compressed),('UNCOMPRESSED',decoded)]:
        require(literal(boundary,name) is None, 'future transport pin was already bound: ' + name)
        boundary = assignment(boundary,name,pin(raw))
    request = json.loads((OLD/'exact-request.json').read_bytes())
    request['args']=['-I','-B','-c',boundary]
    request['stdin']=envelope.decode()
    request['idempotency_key']=KEY
    require(request['host']=='pocket4' and request['executable']=='/usr/bin/python3' and
            request['cpu_quota_percent']==200 and request['memory_max_bytes']==10*1024**3 and
            request['timeout_seconds']==6400 and request['nice']==10 and 'env' not in request,
            'original normal resource or launch boundary changed')
    plan = subprocess.run([sys.executable,'-I','-B','-c',source],capture_output=True,check=True)
    require(plan.stderr==b'' and json.loads(plan.stdout)['state']=='PLAN_NORMAL_STRICT_FRAMEWORK_RESUME',
            'bound local PLAN-only mode failed')
    require(not Path(REMOTE).exists(), 'local generation unexpectedly created a remote execution root')
    artifacts=dict(data)
    artifacts.update({'stage.py':stage.encode(),'transport-boundary.py':boundary.encode(),
        'verified-source-packet.json':(packet+'\n').encode(),'exact-request.json':encoded(request),
        'actual-builder467-compile.stdout':actual_stdout,'PLAN.json':plan.stdout,
        'make_request.py':Path(__file__).read_bytes()})
    binding={'schema':1,'state':'ACTUAL_COMPILE_BOUND_NORMAL_RESUME_REQUEST_NOT_SUBMITTED',
        'actual_compile_stdout':pin(actual_stdout),'actual_compile_result':pin(actual_raw),
        'actual_builder_elf':actual['builder_elf'],'source_template':pin(template.encode()),
        'controller':pin(source.encode()),'changed_controller_function_ASTs':[],
        'prior_failed_framework_inner':pin(data['prior-framework-inner-terminal.json']),
        'prior_failed_framework_outer':pin(data['prior-framework-outer-terminal.json']),
        'actual_staging_observation':pin(data['actual-staging-read03.json']),
        'historical_145_candidates_and_project146_not_reuse_qualified':True,
        'future_per_project_qualification_requires_real_builder_under_normal_locks':True,
        'packet_files':10,'stdin':pin(envelope),'compressed':pin(compressed),'uncompressed':pin(decoded),
        'new_key':KEY,'Main_actions':0,'remote_submitted':False,'runtime_authorization_enabled':False}
    artifacts['ACTUAL_BINDING.json']=encoded(binding)
    DEST.mkdir(mode=0o700)
    for name,raw in artifacts.items():
        with (DEST/name).open('xb') as stream:stream.write(raw)
    (DEST/'SOURCE_PINS.json').write_bytes(encoded({'schema':1,'files':{name:pin(raw) for name,raw in sorted(artifacts.items())}}))
    for path in DEST.iterdir():path.chmod(0o444)
    print(json.dumps({'root':str(DEST),'request':pin(artifacts['exact-request.json']),
        'stdin':pin(envelope),'controller':pin(source.encode()),'packet_files':10,
        'new_key':KEY,'remote_submitted':False},indent=2))


if __name__ == '__main__':
    main()
