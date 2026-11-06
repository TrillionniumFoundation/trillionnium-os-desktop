#!/usr/bin/env python3
"""Seal the reviewed exact local packet. No host connection or execution entry."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
INPUT = HERE / 'source-r2-unsealed'
OUTPUT = HERE / 'source-r2'
SCOPE_LOCAL = PROJECT / 'successor_install/actual/douyin-01/app-scope-after.private.json'
SCOPE_PIN = {'path': '/home/alex/work/pocket4-successor-native-install-20261106-douyin-01/app-scope-after.private.json',
             'bytes': 57340, 'sha256': '489129d6e39a5aebc410ebcf74706279a99ff6751a15bd0a6b324ddd007e01a4'}
ORIGINAL_REQUEST = HERE / 'reference/normal04/exact-request.json'
ORIGINAL_REQUEST_SHA = '70e19da34d7ef06c5f4d0eadd90291e07983ead1f074a3fc4a6a1ee8c84f2eb5'
NEW_KEY = 'pocket4-native-typed-ingress-framework-strict-native-provider-two-target-build-05-20261106'
RUNTIME_SHA = 'a7c7091a9e57eb6b373aa8a9225bb2f17b4ec0f1248679b56aaadc78eb0faca9'


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(raw):
    return {'bytes': len(raw), 'sha256': sha(raw)}


def parse(raw):
    def pairs(items):
        row = {}
        for key, value in items:
            need(key not in row, 'DUPLICATE_JSON_KEY')
            row[key] = value
        return row
    def invalid(_):
        raise RuntimeError('NONFINITE_JSON_NUMBER')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def assignment(source, name):
    rows = [row for row in ast.parse(source).body if isinstance(row, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == name for target in row.targets)]
    need(len(rows) == 1, 'EXACT_ASSIGNMENT:' + name)
    return rows[0]


def literal(source, name):
    return ast.literal_eval(assignment(source, name).value)


def set_literal(source, name, value):
    node = assignment(source, name)
    lines = source.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [name + ' = ' + repr(value) + '\n']
    return ''.join(lines)


def qualify_scope_constants(reference, packages, scope):
    need(reference == SCOPE_PIN and scope['schema'] == 'pocket4-versioned-app-scope-v1' and
         scope['runtime_epoch_sha256'] == RUNTIME_SHA, 'FINAL_SCOPE_AUTHORITY_DIFFERS')
    expected = sorted(scope['apps'])
    need(type(packages) is list and packages == expected and len(packages) == 46,
         'EXACT_FINAL_46_MEMBER_SCOPE_REQUIRED')
    return expected


def write_new(name, raw):
    with (OUTPUT / name).open('xb') as stream:
        stream.write(raw)
    return pin(raw)


def main():
    scope_raw = SCOPE_LOCAL.read_bytes()
    need(pin(scope_raw) == {key: SCOPE_PIN[key] for key in ('bytes', 'sha256')}, 'FINAL_SCOPE_BYTES')
    scope = parse(scope_raw)
    original_raw = ORIGINAL_REQUEST.read_bytes()
    need(len(original_raw) == 828024 and sha(original_raw) == ORIGINAL_REQUEST_SHA, 'ORIGINAL_REQUEST_PIN')
    original = parse(original_raw)
    manifest_raw = (INPUT / 'SOURCE_PINS.json').read_bytes()
    manifest = parse(manifest_raw)
    need(manifest['state'] == 'SOURCES_PREPARED_SCOPE_BOUND_EXACT_REQUEST_UNSEALED' and
         manifest['exact_request_sealed'] is False and manifest['remote_submitted'] is False and
         manifest['local_pure_controls'] == 59 and manifest['runtime_epoch_sha256'] == RUNTIME_SHA,
         'BOUND_UNSEALED_SOURCE_MANIFEST_REQUIRED')
    content = {}
    for name, expected in manifest['files'].items():
        raw = (INPUT / name).read_bytes()
        need(pin(raw) == expected, 'SOURCE_INPUT_PIN:' + name)
        content[name] = raw
        if name.endswith('.py'):
            ast.parse(raw, filename=name)
    snapshot = content['main_snapshot.py'].decode()
    packages = qualify_scope_constants(literal(snapshot, 'APP_SCOPE_PIN'), literal(snapshot, 'APP_SCOPE_PACKAGES'), scope)
    need(manifest['final_app_scope_reference'] == SCOPE_PIN and manifest['final_app_scope_packages'] == packages,
         'MANIFEST_SCOPE_DIFFERS_FROM_SOURCE')
    initial_path = PROJECT / 'recovery/independent_repair_r2/actual-execute-01/initial-app-scope.private.json'
    initial_raw = initial_path.read_bytes()
    qualification = parse(content['actual-current-qualification.json'])
    need(pin(initial_raw) == {key: qualification['initial_app_scope'][key] for key in ('bytes', 'sha256')},
         'ACTUAL_INITIAL_SCOPE_AUTHORITY_PIN')
    initial = parse(initial_raw)
    need(set(initial['apps']) == set(scope['apps']) and initial['runtime_epoch_sha256'] == RUNTIME_SHA,
         'ACTUAL_INITIAL_AND_FINAL_MEMBERS_DIFFER')
    checks = ['exact_actual_final_46_members_bound', 'original_qualified_initial_scope_pin_and_full_members_match']
    try:
        qualify_scope_constants(SCOPE_PIN, packages[:-1], scope)
    except RuntimeError as error:
        need(str(error) == 'EXACT_FINAL_46_MEMBER_SCOPE_REQUIRED', 'MISSING_MEMBER_WRONG_FAILURE')
        checks.append('dropping_one_actual_package_rejected_before_sealing')
    else:
        raise RuntimeError('MISSING_PACKAGE_ACCEPTED')
    snapshot_scope = {'__name__': 'normal05_local_scope_binding_only'}
    exec(compile(snapshot, 'main_snapshot.py', 'exec'), snapshot_scope, snapshot_scope)
    snapshot_scope['qualify_scope_reference'](SCOPE_PIN, packages)
    snapshot_scope['qualify_baseline'](parse(content['actual-current-runtime-baseline.json']))
    stage = content['stage.py'].decode()
    expected = literal(stage, 'EXPECTED')
    files = {}
    for name, expected_pin in expected.items():
        need(name in content and pin(content[name]) == expected_pin, 'EXACT_STAGE_MEMBER:' + name)
        files[name] = content[name].decode('utf-8')
    need(len(files) == 21, 'EXACT_CURRENT_STAGE_CLOSURE')
    # This is only serialization of the actual fixed staged sources; no code is run.
    wire = json.dumps({'schema': 1, 'stage': stage, 'files': files}, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode()
    need(len(wire) <= 1024 * 1024, 'TRANSPORT_STDIN_LIMIT')
    boundary = content['transport-boundary.py'].decode()
    need(literal(boundary, 'WIRE_BYTES') is None and literal(boundary, 'WIRE_SHA256') is None, 'INPUT_ALREADY_SEALED')
    need(literal(boundary, 'STAGE_BYTES') == len(content['stage.py']) and
         literal(boundary, 'STAGE_SHA256') == sha(content['stage.py']), 'STAGE_SOURCE_BINDING')
    boundary = set_literal(boundary, 'WIRE_BYTES', len(wire))
    boundary = set_literal(boundary, 'WIRE_SHA256', sha(wire))
    ast.parse(boundary)
    request = copy.deepcopy(original)
    need(set(request) == {'host', 'executable', 'args', 'stdin', 'idempotency_key', 'timeout_seconds', 'cpu_quota_percent', 'memory_max_bytes', 'nice'} and
         request['host'] == 'pocket4' and request['executable'] == '/usr/bin/python3' and
         request['args'][:3] == ['-B', '-I', '-c'] and request['args'][4:] == ['--execute-once'] and
         request['timeout_seconds'] == 6400 and request['cpu_quota_percent'] == 200 and
         request['memory_max_bytes'] == 10737418240 and request['nice'] == 10,
         'ORIGINAL_LAUNCH_ENVELOPE_DIFFERS')
    request['args'][3] = boundary
    request['stdin'] = wire.decode('utf-8')
    request['idempotency_key'] = NEW_KEY
    request_raw = (json.dumps(request, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
    roundtrip = parse(request_raw)
    need(roundtrip['stdin'].encode() == wire and roundtrip['args'][3] == boundary, 'EXACT_REQUEST_ROUNDTRIP')
    parent_controller = (HERE / 'reference/normal04/framework_build.py').read_bytes()
    need(content['framework_build.py'] == parent_controller.replace(
         b"ROOT = OWNER / 'typed-ingress-framework-native-provider-build-04-20261106'",
         b"ROOT = OWNER / 'typed-ingress-framework-native-provider-build-05-20261106'"),
         'CONTROLLER_CHANGED_BEYOND_NEW_ROOT')
    OUTPUT.mkdir(mode=0o700)
    rows = {}
    for name, raw in content.items():
        if name != 'transport-boundary.py':
            rows[name] = write_new(name, raw)
    rows['transport-boundary.py'] = write_new('transport-boundary.py', boundary.encode())
    rows['exact-stdin.json'] = write_new('exact-stdin.json', wire)
    rows['exact-request.json'] = write_new('exact-request.json', request_raw)
    # Exercise only rejection with truncated bytes. The valid source packet is never executed.
    rejected = subprocess.run([sys.executable, '-B', str(OUTPUT / 'transport-boundary.py'), '--execute-once'],
                              input=wire[:-1], capture_output=True, timeout=10)
    need(rejected.returncode == 1 and rejected.stdout == b'' and
         b'normal framework exact source packet changed' in rejected.stderr,
         'TRUNCATED_WIRE_NOT_REJECTED')
    checks.append('sealed_transport_rejects_truncated_wire_before_stage_execution')
    validation = {'schema': 'normal05-exact-request-local-validation-v1', 'state': 'PASS_LOCAL_ONLY',
                  'checks': checks, 'pure_controls_passed': 59, 'actual_main_guard_calls': 0,
                  'actual_app_scope_guard_calls': 0, 'actual_capture_lifecycle_controls_run': 0,
                  'runtime_QA_pass_count': 0, 'remote_submitted': False, 'host_stage_executed': False,
                  'builder_started': False, 'Soong_invoked': False,
                  'rejection_control': {'returncode': rejected.returncode, 'stdout': rejected.stdout.decode(),
                                        'stderr': rejected.stderr.decode(), 'input_bytes': len(wire) - 1},
                  'exact_source_members': len(files), 'final_scope_members': len(packages),
                  'scope_reference': SCOPE_PIN, 'original_launch_envelope_sha256': ORIGINAL_REQUEST_SHA,
                  'request': pin(request_raw), 'wire': pin(wire), 'production_ready': False, 'cleanup_eligible': False}
    rows['local-exact-request-validation.json'] = write_new('local-exact-request-validation.json',
        (json.dumps(validation, indent=2) + '\n').encode())
    sealed = dict(manifest)
    sealed.update({'schema': 'pocket4-normal05-sealed-source-v1', 'state': 'SEALED_FOR_ROOT_REVIEW_NOT_SUBMITTED',
                   'files': rows, 'exact_request_sealed': True, 'remote_submitted': False,
                   'parent_unsealed_source_manifest': pin(manifest_raw),
                   'original_launch_envelope': pin(original_raw), 'sealer': pin(Path(__file__).read_bytes()),
                   'final_scope_count': len(packages), 'parent_review_required_before_dispatch': True,
                   'runtime_capture_lifecycle_controls_pending': 4,
                   'fresh_host_resource_and_current_typedguard_admission_pending': True})
    sealed_pin = write_new('SOURCE_PINS.json', (json.dumps(sealed, indent=2) + '\n').encode())
    print(json.dumps({'state': sealed['state'], 'directory': str(OUTPUT), 'source_manifest': sealed_pin,
                      'request': pin(request_raw), 'stdin': pin(wire), 'stage': pin(content['stage.py']),
                      'snapshot': pin(content['main_snapshot.py']), 'final_scope_members': len(packages),
                      'local_pure_controls_passed': 59, 'sealing_controls_passed': len(checks), 'remote_submitted': False}))


if __name__ == '__main__':
    main()
