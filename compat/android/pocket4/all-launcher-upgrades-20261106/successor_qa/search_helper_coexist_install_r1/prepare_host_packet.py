#!/usr/bin/env python3
"""Local-only sealing of the actual-build/actual-B coexistence installer.

Never connects to Pocket4, executes Android, or submits the resulting requests.
All original candidates and failures remain unchanged.
"""
import ast
import base64
import copy
import difflib
import hashlib
import json
from pathlib import Path
import stat
import textwrap
import types

PROJECT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = HERE / 'host-candidate-r1'
ROOT = '/home/alex/work/pocket4-beike-search-helper-coexist-install-20261106-r1'
FLOW = '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe'
HELPER = PROJECT / 'successor_qa/search_click_same_process_r1/candidate-r2/helper'
BUILD_ACTUAL = HELPER.parent / 'hostprep-r1/actual-build'
B_CANDIDATE = PROJECT / 'successor_qa/no_action_runtime_commit_r1/stage-b-candidate-r1'
STATE_NONCE = '6f1b17628528422dad623e5305c1f776'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def record(path, remote=None):
    raw = path.read_bytes()
    return {'path': remote or str(path.relative_to(PROJECT)), 'bytes': len(raw), 'sha256': sha(raw)}


def require_input(path, size, digest):
    raw = path.read_bytes()
    assert len(raw) == size and sha(raw) == digest, str(path)
    return raw


def definitions(path):
    source = path.read_text(); lines = source.splitlines(keepends=True)
    return {node.name: ''.join(lines[node.lineno - 1:node.end_lineno])
            for node in ast.parse(source).body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}


def constants(path):
    result = {}
    for node in ast.parse(path.read_bytes()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                result[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    return result


def write(name, raw):
    if isinstance(raw, str):
        raw = raw.encode()
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert path.read_bytes() == raw, 'frozen output differs: ' + str(path)
    else:
        path.write_bytes(raw)
    return path


def json_file(name, value):
    return write(name, json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + '\n')


def module_from(raw, name):
    module = types.ModuleType(name)
    module.__file__ = str(OUT / (name + '.py'))
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module


def main():
    OUT.mkdir(exist_ok=True)
    installer_path = HERE / 'candidate-r1/install_search_helper_full_scope.py'
    installer_raw = require_input(installer_path, 24933, 'a15d1322c1bbf6001d0870307243bf4509e00111484b042038ad583871f101c6')
    require_input(HELPER / 'SOURCE_PINS.json', 3259, '0bd7c10043f46063fdbf46e19a48e40430c02f3373d697ad7a44af8ad64b8489')
    build_raw = require_input(BUILD_ACTUAL / 'build-result.original.json', 39246, '0d6a4e19388358032c9ba4ad4f034e714470d7d194c36599226bd0ba6745330f')
    build_stdout = require_input(BUILD_ACTUAL / 'stdout.original.json', 263, '608d7dec90de0bba10dd8e5e7daf3999a22f984dcd289edb18e7547e4babbc57')
    build_terminal = require_input(BUILD_ACTUAL / 'terminal.original.json', 729, '121ac5733395c1e66d280ff8cb69df38fe7a163f07ff6c99df18aee73ac4ae7b')
    b_stdout = require_input(B_CANDIDATE / 'actual/stdout.original.jsonl', 19805, '3a046f40503768c5e0411daee65c5b233e6245b32c0098c8fd4493a8915a9cbf')
    b_terminal = require_input(B_CANDIDATE / 'actual/terminal.original.json', 733, '29f4241e351442586e8080fa0d252c883075df864934add9657216cecde72ece')
    require_input(B_CANDIDATE / 'commit_stage_b_once.py', 77716, 'f36e146221d43359690b2d73969244dce337a9ac36da038d2bae506a2de981b7')
    require_input(B_CANDIDATE / 'request.json', 2531, 'a2e6b26f52fc0874a5dddac3435df326124558765236e7a1d19d85c3584c6449')
    full48_local = PROJECT / 'successor_install/source-r4-zbj-full48/candidate-r1/post_install_scope_readback_r1/actual/app-scope-after.private.json'
    require_input(full48_local, 59259, '9aeb555bbc287e168d1bb8f1df09e33f8fd37777ee01a58fe2c563e2725cf01a')
    build = json.loads(build_raw); b_lines = [json.loads(x) for x in b_stdout.splitlines()]
    assert len(b_lines) == 2
    b = b_lines[1]; install_constants = constants(installer_path)
    base_path = PROJECT / 'successor_qa/owned_cleanup_r1/cleanup_owned_task_once.py'
    ui_path = PROJECT / 'successor_qa/reusable_owned_ui_r1/owned_ui_request_once.py'
    b_path = B_CANDIDATE / 'commit_stage_b_once.py'
    require_input(base_path, 22233, '559ae3641a5f6e017914102af61c5f8e909605cb92be32d1a045ae7c66a935cf')
    require_input(ui_path, 25377, 'c394598e477f1912378c6c3d582850a196e64f77791d0b7f5c4d498ec9b61e38')
    b_constants = constants(b_path)
    helper_remote = '/home/alex/work/pocket4-successor-qa-build-source-362bdb6f45eeb344b3584aa998cb03e1'
    fixed = {
        'ROOT': ROOT, 'FLOW': FLOW, 'PACKAGE': build['package'],
        'BASE': b_constants['BASE'],
        'INSTALLER': record(installer_path, ROOT + '/install_search_helper_full_scope.py'),
        'ADAPTER': record(HELPER / 'qa_adapter.py', helper_remote + '/qa_adapter.py'),
        'HELPER_MANIFEST': record(HELPER / 'SOURCE_PINS.json', helper_remote + '/SOURCE_PINS.json'),
        'PARENT_SCOPE': install_constants['PARENT_SCOPE'],
        'BUILD_JOB': '1a1b339c056-fc05-8136',
        'BUILD_RESULT': record(BUILD_ACTUAL / 'build-result.original.json', build['APK']['path'].rsplit('/', 1)[0] + '/build-result.json'),
        'BUILD_FILE_VERSION': '66306:35127954:39246:1794008288630404826:1794008288630404826',
        'APK': build['APK'], 'SIGNER_SHA': build['signer_certificate_sha256'],
        'BUILD_STDOUT': record(BUILD_ACTUAL / 'stdout.original.json', ROOT + '/build.stdout.original.json'),
        'BUILD_TERMINAL': record(BUILD_ACTUAL / 'terminal.original.json', ROOT + '/build.terminal.original.json'),
        'RECORDER_ROOT': b_constants['RECORDER_ROOT'], 'NO_ACTION_CORE': b_constants['PARTIAL_SOURCE'],
        'STAGE_B_JOB': '1a1b33fbae4-fc05-8172',
        'STAGE_B_SOURCE': b['source'], 'STAGE_B_REQUEST': b['request'],
        'STAGE_B_STDOUT': record(B_CANDIDATE / 'actual/stdout.original.jsonl', ROOT + '/stage-b.stdout.original.jsonl'),
        'STAGE_B_TERMINAL': record(B_CANDIDATE / 'actual/terminal.original.json', ROOT + '/stage-b.terminal.original.json'),
        'B_ENVELOPE': b['committed'], 'B_PROOF': b['typed_proof'], 'B_STEP_RESULT': b['step_result'], 'B_JOINT': b['joint_artifact'],
        'ACTUAL_STAGE_B_PUBLICATION': b_lines[0],
        'STAT_FIELDS': ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_rdev', 'st_size', 'st_mtime_ns', 'st_ctime_ns'),
    }
    request = {'schema': 'pocket4-fixed-normal-search-helper-coexist-install-request-v1',
        'flow': FLOW, 'step': 'install-search-helper-r2-01', 'state_nonce': STATE_NONCE,
        'package': build['package'], 'installer': fixed['INSTALLER'],
        'helper_source_manifest': fixed['HELPER_MANIFEST'], 'build_result': fixed['BUILD_RESULT'],
        'build_job': fixed['BUILD_JOB'], 'build_APK': fixed['APK'], 'signer_certificate_sha256': fixed['SIGNER_SHA'],
        'completed_no_action_job': fixed['STAGE_B_JOB'], 'completed_no_action_envelope': fixed['B_ENVELOPE'],
        'parent_app_scope': fixed['PARENT_SCOPE'], 'replacement': False, 'old_helper_retained': True,
        'UI_actions': 0, 'permission_grants': 0, 'automatic_retry': False,
        'new_UID_must_come_from_actual_PM': True, 'new_49_scope_must_come_from_actual_observer': True,
        'production_ready': False}
    fixed['FIXED_REQUEST'] = request
    defs = definitions(ui_path)
    b_defs = definitions(b_path)
    body = (HERE / 'owner_body.fragment.py').read_text()
    parent = b_defs['parent']
    start = parent.index('        value = partial.document(raw)')
    end = parent.index("        for pin in (SELF, REQUEST, BASE, UI_SOURCE", start)
    predicates = textwrap.dedent(parent[start:end])
    assert 'run_owned_child' not in predicates and 'write_once' not in predicates and 'entry(' not in predicates
    body = body.replace('__ORIGINAL_COMPLETED_B_PREDICATES__', textwrap.indent(predicates.rstrip(), '    '))
    inherited = ['need', 'sha', 'canonical', 'load_base']
    header = '#!/usr/bin/env python3\n"""Single reviewed normal PM coexistence install; no UI action or replay."""\n'
    header += 'import contextlib\nimport hashlib\nimport io\nimport json\nimport os\nfrom pathlib import Path\nimport re\nimport stat\nimport sys\nimport types\n\nsys.dont_write_bytecode = True\n'
    header += '\n'.join(k + ' = ' + repr(v) for k, v in fixed.items()) + '\nSELF = REQUEST = None\n\n\n'
    owner = header + '\n\n\n'.join(defs[k] for k in inherited) + '\n\n\n' + b_defs['write_once'] + '\n\n\n' + body
    compile(owner, ROOT + '/owned_install_once.py', 'exec')
    write('owned_install_once.py', owner)
    write('install_search_helper_full_scope.py', installer_raw)
    write('request.json', canonical(request) + b'\n')
    for name, raw in [('build.stdout.original.json', build_stdout), ('build.terminal.original.json', build_terminal),
                      ('stage-b.stdout.original.jsonl', b_stdout), ('stage-b.terminal.original.json', b_terminal)]:
        write(name, raw)
    write('OWNER_DIFF.patch', ''.join(difflib.unified_diff(ui_path.read_text().splitlines(True), owner.splitlines(True),
        fromfile=str(ui_path.relative_to(PROJECT)), tofile='host-candidate-r1/owned_install_once.py')))
    write('COMPLETED_B_PREDICATES.original.fragment.py', predicates)
    members = ['owned_install_once.py', 'install_search_helper_full_scope.py', 'request.json',
               'build.stdout.original.json', 'build.terminal.original.json', 'stage-b.stdout.original.jsonl', 'stage-b.terminal.original.json']
    pins = {name: {k: v for k, v in record(OUT / name).items() if k != 'path'} for name in members}
    payload = {'schema': 'pocket4-search-helper-coexist-source-stage-payload-v1', 'root': ROOT,
               'files': {name: dict(pins[name], base64=base64.b64encode((OUT / name).read_bytes()).decode()) for name in members}}
    payload_raw = canonical(payload) + b'\n'
    assert len(payload_raw) <= 524288
    write('stage-input.json', payload_raw)
    stage_parent_path = B_CANDIDATE / 'stage_commit_once.py'
    stage_parent = stage_parent_path.read_text()
    stage_header = stage_parent[:stage_parent.index('ROOT =')]
    stage_header = stage_header.replace('Stage the fixed Stage B owner and already completed Stage A receipts.',
                                         'Publish only the fixed coexistence owner and completed build/B receipts. No Android entry.')
    stage_header += 'ROOT = Path(' + repr(ROOT) + ')\nPINS = ' + repr(pins) + '\nPAYLOAD_SHA = ' + repr(sha(payload_raw)) + '\n'
    stage_header += "FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')\n\n\n"
    stage_defs = definitions(stage_parent_path)
    stage_main = stage_defs['main']
    stage_main = stage_main[:stage_main.index("    entry = ROOT / 'commit_stage_b_once.py'")]
    replacements = {
        'pocket4-stage-b-no-action-commit-stage-payload-v1': 'pocket4-search-helper-coexist-source-stage-payload-v1',
        'pocket4-beike-no-action-commit-20261106-r1': ROOT.rsplit('/', 1)[-1],
        'pocket4-stage-b-no-action-commit-stage-v1': 'pocket4-search-helper-coexist-source-stage-v1',
        'single-no-action-commit-owner-not-yet-invoked': 'source-only-normal-coexist-installer-not-invoked',
    }
    for old, new in replacements.items():
        stage_main = stage_main.replace(old, new)
    stage_source = stage_header + '\n\n\n'.join(stage_defs[n] for n in ('need', 'sha', 'census')) + '\n\n\n' + stage_main + '\n\n\nif __name__ == "__main__":\n    main()\n'
    compile(stage_source, '<source-only-stage>', 'exec')
    write('stage_source_once.py', stage_source)
    write('STAGE_DIFF.patch', ''.join(difflib.unified_diff(stage_parent.splitlines(True), stage_source.splitlines(True),
        fromfile=str(stage_parent_path.relative_to(PROJECT)), tofile='host-candidate-r1/stage_source_once.py')))
    common = {'host': 'pocket4', 'executable': '/usr/bin/sudo', 'cwd': '/home/alex/work', 'nice': 10}
    stage_packet = dict(common, args=['-n', '/usr/bin/python3', '-I', '-B', '-c', stage_source, '--payload-sha256', sha(payload_raw)],
        stdin=payload_raw.decode(), cpu_quota_percent=50, memory_max_bytes=268435456, timeout_seconds=60,
        idempotency_key='pocket4-beike-search-helper-coexist-source-stage-20261106-r1')
    p = pins['owned_install_once.py']; q = pins['request.json']
    install_packet = dict(common, args=['-n', '/usr/bin/python3', '-I', '-B', ROOT + '/owned_install_once.py', '--install-once',
        '--source-sha256', p['sha256'], '--source-bytes', str(p['bytes']), '--request-sha256', q['sha256'], '--request-bytes', str(q['bytes'])],
        cpu_quota_percent=100, memory_max_bytes=1073741824, timeout_seconds=660,
        idempotency_key='pocket4-beike-search-helper-coexist-normal-install-20261106-r1')
    json_file('exact-stage-request.review-only.json', stage_packet)
    json_file('exact-install-request.review-only.json', install_packet)
    inheritance = {'schema': 'pocket4-owned-coexistence-host-source-inheritance-v1',
        'owner_parent': record(ui_path), 'B_predicates_parent': record(b_path), 'stage_parent': record(stage_parent_path),
        'unchanged_owner_functions_from_owned_UI': inherited,
        'unchanged_write_once_from_B': b_defs['write_once'] == definitions(OUT / 'owned_install_once.py')['write_once'],
        'completed_B_original_validation_block_sha256': sha(predicates.encode()),
        'completed_B_block_changes': 'Only outer indentation; local constant bindings select the exact completed B source/request. No entry/parent/child/publication call.',
        'unchanged_installer': record(installer_path), 'unchanged_installer_copy': record(OUT / 'install_search_helper_full_scope.py'),
        'unchanged_stager_functions': ['need', 'sha', 'census'],
        'source_stage_changes': 'Fixed new root, exact seven-member payload and labels; remove all execution of the staged owner.',
        'new_owner_functions': [n for n in definitions(OUT / 'owned_install_once.py') if n not in inherited + ['write_once']],
        'resource_contract': {'source_stage': {'cpu_percent': 50, 'memory_bytes': 268435456, 'timeout_seconds': 60},
            'install': {'cpu_percent': 100, 'memory_bytes': 1073741824, 'owned_child_seconds': 600, 'outer_timeout_seconds': 660,
                        'nice': 10, 'child_stdout_bytes': 131072, 'child_stderr_bytes': 16384, 'parent_stdout_bytes': 262144},
            'references': ['Existing helper normal install 1 GiB/one CPU', 'Existing owned UI case child600/outer660 and unchanged pidfd probe'],
            'full_framework_resource_gates_changed': False}}
    assert all(definitions(OUT / 'owned_install_once.py')[name] == defs[name] for name in inherited)
    assert inheritance['unchanged_write_once_from_B']
    json_file('SOURCE_INHERITANCE.json', inheritance)
    # Limited local checks cover new integration predicates. No runtime or new
    # UID/scope evidence is generated, and the unchanged 7 scope controls remain
    # in candidate-r1 rather than being run repeatedly.
    m = module_from(owner, 'local_owner_definition_checks')
    partial_path = PROJECT / 'successor_qa/no_action_runtime_commit_r1/stage-a-candidate-r1/no_action_core.py'
    partial = module_from(partial_path.read_text(), 'local_original_terminal_predicate')
    base = module_from(base_path.read_text(), 'local_original_normal_exit_predicate')
    checks = []
    def check(name, fn, rejects=False):
        try:
            fn()
        except RuntimeError as error:
            assert rejects, (name, str(error))
            checks.append({'name': name, 'passed': True, 'observed_rejection': str(error)})
        else:
            assert not rejects, 'expected rejection: ' + name
            checks.append({'name': name, 'passed': True})
    check('actual_B_complete_stdout_durable_terminal_and_normal_child_header',
          lambda: m.completed_b_header(base, partial, b_stdout, json.loads(b_terminal)))
    check('actual_build_durable_terminal_and_exact_log_length',
          lambda: partial.original_terminal(json.loads(build_terminal), fixed['BUILD_JOB'], len(build_stdout)))
    bad_terminal = json.loads(b_terminal); bad_terminal['output_durable'] = False
    check('non_durable_B_is_rejected', lambda: m.completed_b_header(base, partial, b_stdout, bad_terminal), True)
    bad_b = copy.deepcopy(b_lines); bad_b[1]['child_lifecycle']['pidfd_closed'] = False
    bad_bytes = b'\n'.join(canonical(x) for x in bad_b) + b'\n'
    bad_term = json.loads(b_terminal); bad_term['log_bytes']['stdout'] = {'seen': len(bad_bytes), 'stored': len(bad_bytes)}
    check('unretired_B_child_is_rejected', lambda: m.completed_b_header(base, partial, bad_bytes, bad_term), True)
    parser = types.SimpleNamespace(document=json.loads)
    check('exact_fixed_install_request', lambda: m.request_value(canonical(request) + b'\n', parser))
    bad_req = dict(request, helper_uid=10158)
    check('preassigned_UID_is_rejected', lambda: m.request_value(canonical(bad_req) + b'\n', parser), True)
    real_stat = types.SimpleNamespace(st_dev=66306, st_ino=35127954, st_size=39246,
        st_mtime_ns=1794008288630404826, st_ctime_ns=1794008288630404826,
        st_mode=stat.S_IFREG | 0o600, st_nlink=1, st_uid=1000, st_gid=1000, st_rdev=0)
    check('actual_file_version_metadata_model', lambda: m.build_identity(real_stat))
    changed = copy.copy(real_stat); changed.st_ino += 1
    check('same_build_bytes_different_inode_not_accepted', lambda: m.build_identity(changed), True)
    changed_owner = copy.copy(real_stat); changed_owner.st_uid = 0
    check('root_owned_build_copy_not_accepted', lambda: m.build_identity(changed_owner), True)
    controls = {'schema': 'pocket4-coexistence-host-integration-local-controls-v1', 'status': 'LOCAL_ONLY_PASS',
        'cases': checks, 'count': len(checks), 'new_Android_or_host_remote_actions': 0,
        'B_evidence_header_uses_actual_originals': True, 'full_211_host_file_gate_executed_here': False,
        'file_identity_negative_cases_are_local_metadata_models': True, 'actual_new_helper_UID': None,
        'actual_new_scope49': None, 'install_performed': False, 'production_ready': False}
    json_file('LOCAL_CONTROLS.json', controls)
    plan = {'schema': 'pocket4-owned-normal-helper-coexistence-execution-plan-v1', 'status': 'SEALED_REVIEW_ONLY_NOT_SUBMITTED',
        'source_root': ROOT, 'fixed_flow': FLOW, 'fixed_install_step': request['step'],
        'actual_build': {'job': fixed['BUILD_JOB'], 'result': fixed['BUILD_RESULT'], 'APK': fixed['APK'], 'signer': fixed['SIGNER_SHA'],
                         'terminal': record(BUILD_ACTUAL / 'terminal.original.json')},
        'actual_B': {'job': fixed['STAGE_B_JOB'], 'terminal': record(B_CANDIDATE / 'actual/terminal.original.json'),
                     'envelope': fixed['B_ENVELOPE'], 'joint': fixed['B_JOINT'], 'original_FAILED_UNKNOWN_retained': True},
        'actual_parent_explicit48': fixed['PARENT_SCOPE'], 'new_UID': None, 'new_scope49': None,
        'normal_install': 'Absent new .r2 only; original PM install -R -t, original signatures/integrity, no -g/downgrade/replacement/uninstall.',
        'scope_transition': 'All48 original full rows stay equal; new UID/APK/cert/CEDE read from normal PM and original observer; complete49/89APKs. New scope cannot be adopted unless original installer, full fences, normal owned child and authoritative controller terminal jointly succeed.',
        'post_scope_consumers': 'Subsequent whole-scope QA/permissions/framework must bind exact actual49 output. Preserve old48/47 and permission failures. No complete PM/launcher enumeration is claimed.',
        'locks': 'Original Flow.begin unresolved-UNKNOWN/flow.lock and actions lock; actions lock covers PM install, state, complete49 observation and durable result. Normal pidfd-owned child exit retires original flow.lock and declared libffi FD.',
        'source_stage': 'Separate host-only seven files; no Main/Android/namespace/lock/library initialization. Does not run owner.',
        'install_owner': 'One fixed marker and one child, no retry. Reads completed B only; no B producer entries. Calls reviewed installer main once. No general UI API.',
        'resources': inheritance['resource_contract'], 'private_UI_body_copied_to_packet': False,
        'permission_grants': 0, 'UI_actions': 0, 'cleanup_bytes': 0, 'production_ready': False,
        'requests': [record(OUT / 'exact-stage-request.review-only.json'), record(OUT / 'exact-install-request.review-only.json')]}
    json_file('EXECUTION_PLAN.json', plan)
    inputs = [Path(__file__), HERE / 'owner_body.fragment.py', installer_path, ui_path, base_path, b_path,
              B_CANDIDATE / 'request.json', B_CANDIDATE / 'stage_commit_once.py', partial_path, full48_local,
              HELPER / 'SOURCE_PINS.json', HELPER / 'qa_adapter.py', HELPER / 'build_candidate.py',
              BUILD_ACTUAL / 'build-result.original.json', BUILD_ACTUAL / 'stdout.original.json',
              BUILD_ACTUAL / 'terminal.original.json', BUILD_ACTUAL / 'root-validation.actual.json',
              B_CANDIDATE / 'actual/stdout.original.jsonl', B_CANDIDATE / 'actual/terminal.original.json',
              B_CANDIDATE / 'actual/root-validation.actual.json', PROJECT / 'recovery/observe_successor_scope.py']
    outputs = [p for p in OUT.iterdir() if p.is_file() and p.name != 'SOURCE_PINS.json']
    index = {'schema': 'pocket4-normal-coexist-install-host-packet-pins-v1', 'inputs': [record(p) for p in inputs],
             'files': [record(p) for p in sorted(outputs)], 'staged_members': pins,
             'source_root': ROOT, 'packet_sealed': True, 'remote_submitted': False,
             'Android_install_or_UI_performed': False, 'private_UI_body_included': False,
             'unknown_new_UID_and_scope_are_not_fabricated': True}
    json_file('SOURCE_PINS.json', index)
    print(json.dumps({'status': 'LOCAL_PACKET_SEALED_NOT_SUBMITTED', 'output': str(OUT),
        'owner': record(OUT / 'owned_install_once.py'), 'source_stage': record(OUT / 'stage_source_once.py'),
        'request': record(OUT / 'request.json'), 'stage_packet': record(OUT / 'exact-stage-request.review-only.json'),
        'install_packet': record(OUT / 'exact-install-request.review-only.json'),
        'manifest': record(OUT / 'SOURCE_PINS.json'), 'input_count': len(inputs), 'output_count': len(outputs),
        'local_controls': len(checks), 'private_UI_body_in_packet': False, 'Android_actions': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
