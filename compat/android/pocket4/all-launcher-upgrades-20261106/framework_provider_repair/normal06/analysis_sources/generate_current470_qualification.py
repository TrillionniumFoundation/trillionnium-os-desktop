"""Assemble a local, reviewable qualification candidate; never execute its host code."""
import ast
import copy
import hashlib
import json
import pathlib
import pprint
import re

P = pathlib.Path
BASE = P(__file__).resolve().parents[1]
DEST = BASE / 'builder470-current-qualification-r1/source-r1'
REF = BASE / 'builder470-current-qualification-r1/reference'
ACTIVE = '/home/alex/work/pocket4-native-typed-ingress-builder470-systemui-provider-compile-02-20261106'
LEGACY469 = '/home/alex/work/pocket4-native-typed-ingress-builder469-native-provider-compile-01-20261106'
LEGACY468 = '/home/alex/work/pocket4-native-typed-ingress-builder468-provider-closure-compile-03-20261106'
ROOT = '/home/alex/work/pocket4-builder470-explicit-current-qualification-01-20261106'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path.relative_to(BASE)), 'bytes': len(raw), 'sha256': sha(raw)}


def original(rel, expected):
    path = BASE / rel
    raw = path.read_bytes()
    assert sha(raw) == expected, rel
    return raw


def funcs(raw):
    text = raw.decode()
    return {node.name: ast.get_source_segment(text, node) for node in ast.parse(text).body
            if isinstance(node, ast.FunctionDef)}


def literal(raw, name):
    for node in ast.parse(raw.decode()).body:
        if isinstance(node, ast.Assign) and any(isinstance(item, ast.Name) and item.id == name for item in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(name)


def write(name, value):
    target = DEST / name
    raw = value if isinstance(value, bytes) else value.encode()
    target.write_bytes(raw)
    return {'bytes': len(raw), 'sha256': sha(raw)}


def dump(name, value):
    return write(name, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n')


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    parent = original('builder470-hostprep-r2/compile_builder470.py',
                      '5d66d26127cfb01ec09a83536ff4f4fdfb0782500cbcbfb2ec0a7b0288ea89d7')
    framework = original('source-r4/framework_build.py',
                         'c446be88a61f7d07c05aff1e3f3bb967bcf969b7fa3de568eb3de4915e59e7da')
    current_raw = original('builder470-hostprep-r2/root-readback-01/result.original.json',
                           '6599026ebe5071ecdd5f0e2d962eb96cc791041be0dee9fd59a402735a6387d8')
    old_raw = original('old468-recovery-investigation-r1/actual/compiler03-result.original.json',
                       '871e78f7ad8f3f3a12c165297e4fe566d96cfe3a2ce64a0d0010cffdb647b6b8')
    current, old = json.loads(current_raw), json.loads(old_raw)
    tests = literal(parent, 'TESTS')
    source_tests = old['expected_source_resume_test_names']
    assert len(tests) == 19 and len(source_tests) == 9
    helper_names = ['require', 'no_alias', 'read', 'inventory', 'utc', 'save', 'held_file',
        'parse_admission_meminfo', 'memory_admission', 'record_resource_admission', 'owned_resource_gate',
        'subreaper', 'child_ids', 'cleanup_children', 'hash_pin', 'collect_pins', 'checked_tools',
        'identity', 'held', 'hash_held', 'qualify_compiler_inputs', 'validate_focused_result',
        'focused_test', 'sha', 'pinned_json', 'command']
    helpers = funcs(parent)
    assert set(helpers) == set(helper_names)
    expected_delta = literal(framework, 'EXPECTED_SOURCE_DELTA')
    authority_rows = [
        ('current470-result', ACTIVE + '/compile01/result.json', len(current_raw), sha(current_raw)),
        ('current470-tool-inputs', ACTIVE + '/compile01/tool-inputs-before.json', 38712,
            '9c0a2fef8ef04bb26ba65c01354d612d47e16e6e4361e423c007640acef62383'),
        ('current470-resource-admission', ACTIVE + '/compile01/resource-admission.json', 2746,
            '5b4b728f90ee088141d2cd9aaa7e242ef33e58b355c790422ed858930c926031'),
        ('legacy468-result', LEGACY468 + '/attempt01/result.json', len(old_raw), sha(old_raw)),
        ('legacy469-result', LEGACY469 + '/compile02/result.json', 37384,
            'a14dde5d3a2e85fe44d90c651527c8c8402d341403ef84a7bc92b93252de72b9'),
        ('legacy469-qualification', LEGACY469 + '/qualify02/result.json', 65386,
            'f31bb31d29967bacdb0842eea99dae65f8b67425f26f10063c3d84099367fd64'),
        ('legacy491-manifest', LEGACY468 + '/attempt01/copied-builder-source-manifest.json', 97525,
            'e06522400f746b62016f82dfd3ec913b39cd9a8f33f9bca4f61a19a2787684ee'),
        ('legacy493-manifest', LEGACY469 + '/candidate-source-manifest.json', 97964,
            'd9340351c9653b10dfd0882afbff5ff4fc11dafaa6083191ed2a8fdb5c8dd934'),
        ('current498-manifest', ACTIVE + '/candidate-source-manifest.json', 99075,
            'f4a0e6ff82f1ecf9bd786872d99cc0b1608e1d94d0adc37761e87aed449c81bd'),
        ('dependency-inputs', LEGACY468 + '/attempt01/dependency-inputs-before.json', 1376033,
            '34ab55489959d957294dcc25a93083346dffec934c96768c515d584bb91731c7'),
        ('tool-inputs', LEGACY468 + '/attempt01/tool-inputs-before.json', 41106,
            '323f770a9c227f4e3804f38c2211e78ce46a8031565242d34b6e42ed7f7b2433'),
    ]
    authorities = {name: {'path': path, 'bytes': size, 'sha256': digest}
                   for name, path, size, digest in authority_rows}
    authorities['current470-tool-inputs']['identity'] = [66306, 38436520, 33152, 38712,
                                                       1793985117029124108, 1793985117029124108]
    authorities['tool-inputs']['identity'] = [66306, 35833111, 33152, 41106,
                                             1793944381937098438, 1793944381937098438]
    fresh_labels = ['rust-version', 'current-builder-help', 'current-typed-ingress-help', 'updater-test-list']
    fresh_labels += ['projection-test-' + str(index) for index in range(19)]
    fresh_labels += ['source-resume-test-compile', 'source-resume-test-list']
    fresh_labels += ['projection-test-' + str(100 + index) for index in range(9)]
    assert len(fresh_labels) == 34
    extra = (BASE / 'analysis_sources/current470_qualification_extra.py.inc').read_text()
    gates = sorted(set(re.findall(r"result\['gates'\]\['([^']+)'\]", extra)))
    constants = {
        'MEMORY_MAX': 1024**3, 'SWAP_MAX': 0, 'MIN_AVAILABLE': 3 * 1024**3,
        'TESTS': tests, 'EXPECTED_TESTS': tests, 'SOURCE_TESTS': source_tests,
        'EXPECTED_REGISTERED_TESTS': 209, 'EXPECTED_FRESH_LABELS': fresh_labels,
        'EXPECTED_COMPILE_LABELS': literal(framework, 'EXPECTED_COMPILE_LABELS'),
        'EXPECTED_SOURCE_DELTA': expected_delta,
        'SOURCE_MANIFEST_SHA': authorities['current498-manifest']['sha256'],
        'EXPECTED_MANIFEST_SHA': authorities['current498-manifest']['sha256'],
        'FAKEROOT_TEST': literal(parent, 'FAKEROOT_TEST'),
        'EXPLICIT_RUST_TOOLS': [
            ('/bin/cargo', 40753664, '9548937d530bf439ff1ba47a3b2bd26eeb9c3aff1961c20c01798613de922578'),
            ('/bin/rustc', 656704, 'd32249a7c3bfcfc67b471460386e46323accae7125e344567a12d5664d99bb57'),
            ('/bin/rustdoc', 13173040, 'ece7829b8e7448a9d59c88080e2b16253b885c560f792002837901c7f24b7695')],
        'LIBFFI': {'path': '/usr/lib/x86_64-linux-gnu/libffi.so.8.2.0', 'bytes': 64184,
                   'sha256': '1a0dc86f787f73e025a6e521056360afcbe70f2a82cd808132fefc2b4ee95daa',
                   'identity': [66306, 108020388, 33188, 64184, 1774599998000000000, 1791083436303902806]},
        'AUTHORITIES': authorities, 'EXPECTED_GATES': gates,
    }
    declarations = '\n'.join(name + ' = ' + pprint.pformat(value, sort_dicts=True, width=110)
                              for name, value in constants.items())
    header = ('import os,sys,json,hashlib,stat,pathlib,subprocess,time,signal,resource,datetime,re,errno,fcntl\n'
        'P = Path = pathlib.Path\n'
        + 'ROOT = P(' + repr(ROOT) + ')\n'
        + 'ACTIVE = P(' + repr(ACTIVE) + ')\n'
        + 'SOURCE = COPIED = ACTIVE / "builder-source"\n'
        + 'ATTEMPT = OUT = ROOT / "qualify01"\n'
        + 'PROFILE_BASE = P(' + repr(LEGACY468) + ')\n'
        + 'BUILD_RESULT = ACTIVE / "compile01/result.json"\n')
    source = header + declarations + '\n\n' + '\n\n'.join(helpers[name] for name in helper_names)
    source += '\n\n' + funcs(framework)['qualify_builder470_receipt'] + '\n\n' + extra
    compile(source, str(DEST / 'qualify_current470.py'), 'exec')
    source_pin = write('qualify_current470.py', source)
    new_functions = funcs(source.encode())
    assert all(new_functions[name] == helpers[name] for name in helper_names)
    assert new_functions['qualify_builder470_receipt'] == funcs(framework)['qualify_builder470_receipt']

    stage_base = (BASE / 'analysis_sources/current470_qualification_stage.py.inc').read_text()
    stage = stage_base.replace('P = pathlib.Path\n',
        'P = pathlib.Path\nROOT = P(' + repr(ROOT) + ')\nSOURCE_BYTES = ' + str(source_pin['bytes']) +
        '\nSOURCE_SHA = ' + repr(source_pin['sha256']) + '\n')
    compile(stage, str(DEST / 'stage_current470_qualification.py'), 'exec')
    stage_pin = write('stage_current470_qualification.py', stage)
    payload = (json.dumps({'schema': 1, 'stage': stage, 'files': {'qualify_current470.py': source}},
                         ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode()
    payload_pin = write('exact-stage-stdin.json', payload)
    transport = """import hashlib,json,sys
if sys.argv[1:] != ['--stage-only-once']:raise SystemExit('PLAN_ONLY: stage not executed')
raw=sys.stdin.buffer.read(PAYLOAD_BOUND)
if len(raw)!=PAYLOAD_BYTES or hashlib.sha256(raw).hexdigest()!=PAYLOAD_SHA:raise RuntimeError('closed qualification packet differs')
packet=json.loads(raw.decode('utf-8','strict'))
if set(packet)!={'schema','stage','files'} or type(packet['schema']) is not int or packet['schema']!=1:raise RuntimeError('closed qualification packet shape differs')
stage=packet['stage'].encode('utf-8','strict')
if len(stage)!=STAGE_BYTES or hashlib.sha256(stage).hexdigest()!=STAGE_SHA:raise RuntimeError('closed qualifier stager differs')
scope={'__name__':'fixed_current470_qualification_stager','__file__':'<fixed-current470-qualification-stager>'}
exec(compile(stage,'stage_current470_qualification.py','exec'),scope,scope)
scope['main'](packet['files'])
"""
    for token, value in [('PAYLOAD_BOUND', len(payload) + 1), ('PAYLOAD_BYTES', len(payload)),
                         ('PAYLOAD_SHA', sha(payload)), ('STAGE_BYTES', stage_pin['bytes']),
                         ('STAGE_SHA', stage_pin['sha256'])]:
        transport = transport.replace(token, repr(value))
    transport_pin = write('stage_transport.py', transport)
    qualify_transport = """import hashlib,os,stat,sys
from pathlib import Path
if sys.argv[1:] != ['--qualify-once','--source-sha256',SOURCE_SHA]:raise SystemExit('PLAN_ONLY: qualification not executed')
p=Path(SOURCE_PATH)
for parent in [p.parent,*p.parent.parents]:
 if not stat.S_ISDIR(parent.lstat().st_mode):raise RuntimeError('qualifier source parent differs')
fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
try:
 before=os.fstat(fd)
 if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_uid!=1000 or before.st_gid!=1000 or stat.S_IMODE(before.st_mode)!=0o400 or before.st_size!=SOURCE_BYTES:raise RuntimeError('qualifier source owner/type/bound differs')
 with os.fdopen(fd,'rb',closefd=False) as stream:raw=stream.read(SOURCE_BOUND)
 identity=lambda value:(value.st_dev,value.st_ino,value.st_mode,value.st_uid,value.st_gid,value.st_nlink,value.st_size,value.st_mtime_ns,value.st_ctime_ns)
 if identity(before)!=identity(os.fstat(fd)) or identity(before)!=identity(p.lstat()) or len(raw)!=SOURCE_BYTES or hashlib.sha256(raw).hexdigest()!=SOURCE_SHA:raise RuntimeError('exact qualifier source changed')
finally:os.close(fd)
scope={'__name__':'__main__','__file__':str(p)}
exec(compile(raw,str(p),'exec'),scope,scope)
"""
    for token, value in [('SOURCE_PATH', ROOT + '/qualify_current470.py'), ('SOURCE_BOUND', source_pin['bytes'] + 1),
                         ('SOURCE_BYTES', source_pin['bytes']), ('SOURCE_SHA', source_pin['sha256'])]:
        qualify_transport = qualify_transport.replace(token, repr(value))
    qualifier_transport_pin = write('qualification_transport.py', qualify_transport)
    common = {'host': 'pocket4', 'executable': '/usr/bin/python3', 'cpu_quota_percent': 100,
              'memory_max_bytes': 1073741824, 'nice': 10}
    stage_request = {**common, 'args': ['-B', '-I', '-c', transport, '--stage-only-once'],
        'stdin': payload.decode(), 'timeout_seconds': 180,
        'idempotency_key': 'pocket4-builder470-explicit-current-qualification-source-stage-01-20261106'}
    qualify_request = {**common, 'args': ['-B', '-I', '-c', qualify_transport, '--qualify-once',
        '--source-sha256', source_pin['sha256']], 'timeout_seconds': 1500,
        'idempotency_key': 'pocket4-builder470-explicit-current-qualification-01-20261106'}
    assert len(stage_request['stdin'].encode()) <= 1048576
    stage_request_pin = dump('exact-stage-request.json', stage_request)
    qualification_request_pin = dump('exact-qualification-request.json', qualify_request)
    inherited = {'source': pin(BASE / 'builder470-hostprep-r2/compile_builder470.py'),
        'unmodified_function_count': len(helper_names),
        'functions': {name: {'bytes': len(helpers[name].encode()), 'sha256': sha(helpers[name].encode())}
                      for name in helper_names},
        'pure_receipt_validator': {'source': pin(BASE / 'source-r4/framework_build.py'),
            'function': 'qualify_builder470_receipt',
            'sha256': sha(new_functions['qualify_builder470_receipt'].encode())}}
    dump('inherited-functions.json', inherited)
    dump('execution-plan.json', {
        'schema': 'pocket4-current470-explicit-qualification-plan-v1', 'state': 'CANDIDATE_NOT_SUBMITTED',
        'checkpoint_base': '6d67481d0c580bdf74e80358bbadb87ff6293905',
        'purpose': 'Qualify the exact existing current470 artifacts and current498 source; no authorization-contract substitution.',
        'new_root': ROOT, 'source_read_only': ACTIVE + '/builder-source', 'output': ROOT + '/qualify01',
        'existing_builder': current['builder'], 'existing_test_executable': current['test_executable'],
        'original_compile_memory_peak_bytes': 1073741824, 'original_compile_memory_max_events': 657,
        'original_compile_oom_events': 0, 'original_compile_swap_peak_bytes': 0,
        'stage_request': stage_request_pin, 'qualification_request': qualification_request_pin,
        'source': source_pin, 'stage': stage_pin, 'payload': payload_pin,
        'transport': transport_pin, 'qualification_transport': qualifier_transport_pin,
        'authority_files': authorities,
        'current_source_file_count': 498, 'current_source_lock_projects': 242, 'source_lock_links': 8,
        'registry_files_and_archives': 2706, 'current_updater_packages': 49, 'registry_packages': 45,
        'source_resume_compile_packages': 46, 'tools': 70,
        'updater_tests': tests, 'source_resume_tests': source_tests, 'expected_fresh_command_labels': fresh_labels,
        'expected_gate_names': gates,
        'resource_profile': {'fresh_MemAvailable_min_bytes': 3221225472, 'owned_memory_max_bytes': 1073741824,
            'owned_memory_swap_max_bytes': 0, 'owned_cpu_quota_percent': 100, 'jobs': 1,
            'logical_CPUs_left_free_min': 2, 'timeout_seconds': 1500},
        'source_resume_only_compile': True, 'updater_rebuilt': False, 'all_main_android_actions': 0,
        'actual_qualification_complete': False, 'submitted': False, 'production_ready': False,
        'cleanup_eligible': False, 'new_authorization_contract_connected': False,
        'full_framework_resource_gate_unchanged': {'fresh_MemAvailable_min_bytes': 15 * 1024**3,
            'memory_max_bytes': 10 * 1024**3, 'swap_max_bytes': 0, 'CPU_percent': 200, 'jobs': 1},
        'must_stop_on': ['any changed identity, owner, source, dependency, tool or authority',
            'any failed or timed-out command', 'any missing independent test record',
            'any residual owned child, even if cleanup kills/reaps it', 'any OOM or nonzero swap',
            'any descriptor other than original stdio and the explicitly prequalified ctypes library',
            'any changed post-observation input', 'unknown or nonzero durable terminal'],
        'final_acceptance': 'Exact full result + final stdout PASS + authoritative durable exit 0, no cancellation/timeout/log loss; root independently reads pins.',
        'unknown_action': 'Reconcile the original key/job only. Never automatically retry, change keys or reduce resource gates.',
    })
    dump('generation-inputs.json', {'state': 'LOCAL_SOURCE_ASSEMBLY_ONLY', 'remote_processes': 0,
        'inputs': [pin(BASE / path) for path in [
            'builder470-hostprep-r2/compile_builder470.py', 'source-r4/framework_build.py',
            'source-r4/parent-normal03-framework_build.py', 'source-r4/parent-normal05-framework_build.py',
            'builder470-hostprep-r2/root-readback-01/result.original.json',
            'old468-recovery-investigation-r1/actual/compiler03-result.original.json',
            'analysis_sources/current470_qualification_extra.py.inc',
            'analysis_sources/current470_qualification_stage.py.inc']]})
    print(json.dumps({'destination': str(DEST), 'source': source_pin, 'stage_request': stage_request_pin,
                      'qualification_request': qualification_request_pin, 'gates': len(gates)}, indent=2))


if __name__ == '__main__':
    main()
