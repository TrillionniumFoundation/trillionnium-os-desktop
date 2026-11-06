#!/usr/bin/env python3
"""Seal local normal06 review material against the actual explicit-47 scope.

This program does not submit its request, read a host, or run Android/builds.
"""
import ast
import copy
import difflib
import hashlib
import json
from pathlib import Path
import pprint

BASE = Path(__file__).resolve().parents[1]
PROJECT = BASE.parents[1]
PREVIOUS = BASE / 'source-r1b'
OUTPUT = BASE / 'source-r2'
REFERENCE = BASE / 'reference/normal05-source-r2'
SCOPE_LOCAL = PROJECT / 'successor_audit_requests/explicit47_scope_r2/actual-readback/app-scope.private.json'
OBSERVATION = PROJECT / 'successor_audit_requests/explicit47_scope_r2/actual'
SCOPE_PIN = {
    'path': '/home/alex/work/pocket4-current-explicit-47-app-observation-20261106-r2/app-scope.private.json',
    'bytes': 58854,
    'sha256': '44f9ce783000a672c270e98afdaeb74bd79654508bfacae6793316ff4252e52f',
}
HELPER = 'org.droidloom.qa.successor.p8f89f253350ba2fa.r1'


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fixed(path, size, digest):
    raw = path.read_bytes()
    need(len(raw) == size and sha(raw) == digest, 'fixed original changed: ' + str(path))
    return raw


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def put(path, raw):
    if isinstance(raw, str):
        raw = raw.encode('utf-8')
    if path.exists():
        need(path.read_bytes() == raw, 'frozen sealed output differs: ' + str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def replace_nodes(text, replacements):
    lines = text.splitlines(keepends=True)
    spans = []
    found = set()
    for node in ast.parse(text).body:
        for target in getattr(node, 'targets', []):
            if isinstance(target, ast.Name) and target.id in replacements:
                need(target.id not in found, 'duplicate assignment')
                found.add(target.id)
                spans.append((node.lineno - 1, node.end_lineno, replacements[target.id].rstrip() + '\n'))
    need(found == set(replacements), 'assignment set differs')
    for start, end, replacement in sorted(spans, reverse=True):
        lines[start:end] = [replacement]
    return ''.join(lines)


def namespace(source, label):
    scope = {'__name__': label, '__file__': '<' + label + '>'}
    exec(compile(source, '<' + label + '>', 'exec'), scope, scope)
    return scope


def exact_packages(selected, actual, original46):
    need(type(selected) is list and selected == sorted(set(selected)) and
         set(selected) == set(actual) == set(original46) | {HELPER} and
         len(selected) == len(actual) == 47 and len(original46) == 46,
         'EXPLICIT_47_COMPLETE_PACKAGE_SET_REQUIRED')


def main():
    previous_manifest_raw = fixed(PREVIOUS / 'SOURCE_PINS.json', 6655,
        'dcb5917403491b7f2fad4f9006bdb0f0eeceeb06090e8cfd98d34df6658ba15d')
    previous_manifest = json.loads(previous_manifest_raw)
    originals = {name: fixed(PREVIOUS / name, pin['bytes'], pin['sha256']).decode('utf-8')
                 for name, pin in previous_manifest['files'].items()}
    files = {name: originals[name] for name in previous_manifest['staged_members']}
    scope_raw = fixed(SCOPE_LOCAL, SCOPE_PIN['bytes'], SCOPE_PIN['sha256'])
    scope_doc = json.loads(scope_raw)
    worker_raw = fixed(OBSERVATION / 'worker.stdout.original.jsonl', 5905,
        '247d05c5d0526b0975f33b565a1285b1b95aff513c95b6c36215f3a9063ef2c7')
    worker = json.loads(worker_raw)
    stdout_raw = fixed(OBSERVATION / 'stdout.original.jsonl', 17857,
        '2752f58cbc84128beb0a0e3e99882dde5806fd40e291dddc586994e7ec632ecf')
    outer = json.loads(stdout_raw.splitlines()[-1])
    terminal_raw = fixed(OBSERVATION / 'terminal.original.json', 733,
        '95229a6aade31b67f486c0bf1cc10788bbf4b34a4550aa9022fe76854828925e')
    terminal = json.loads(terminal_raw)
    need(terminal['job_id'] == '1a1b1e97bb7-fc05-7b79' and terminal['state'] == 'succeeded' and
         terminal['exit_code'] == 0 and terminal['output_complete'] is True and
         terminal['output_durable'] is True and terminal['terminal_publication_confirmed'] is True and
         terminal['timed_out'] is False and terminal['cancelled'] is False and
         terminal['automatic_retry'] is False and
         terminal['log_errors'] == {'stdout': None, 'stderr': None} and
         terminal['log_truncated'] == {'stdout': False, 'stderr': False},
         'explicit scope authoritative terminal differs')
    lifetime = outer['child_lifecycle']
    need(outer['ok'] is True and outer['errors'] == [] and
         lifetime['errors'] == [] and lifetime['returncode'] == 0 and lifetime['timeout'] is False and
         lifetime['owned_child_sigkill_count'] == 0 and
         all(lifetime[k] is True for k in ['pidfd_acquired', 'pidfd_closed', 'pidfd_exit_observed',
                                         'parent_descriptors_restored']) and
         outer['child_result']['worker_stdout_original'].encode('utf-8') == worker_raw and
         outer['child_result']['ok'] is True and outer['child_result']['errors'] == [] and
         outer['child_result']['worker_returncode'] == 0,
         'actual explicit47 worker lifetime/bytes not qualified')
    original_snapshot = namespace((REFERENCE / 'main_snapshot.py').read_text(), 'original_normal05_scope_reference')
    original46 = original_snapshot['APP_SCOPE_PACKAGES']
    names = sorted(scope_doc['apps'])
    exact_packages(names, scope_doc['apps'], original46)
    need(scope_doc['schema'] == 'pocket4-versioned-app-scope-v1' and
         scope_doc['kind'] == 'explicit-current-app-observation' and
         scope_doc['runtime_epoch_sha256'] == original_snapshot['RUNTIME_EPOCH_SHA'] and
         scope_doc['parent_app_scope'] == original_snapshot['APP_SCOPE_PIN'] and
         scope_doc['UI_or_install_runtime_admitted'] is False and
         scope_doc['fresh_signature_verification_performed'] is False and
         worker['schema'] == 'pocket4-explicit-47-app-scope-observation-v1' and worker['ok'] is True and
         worker['status'] == 'EXPLICIT_47_PACKAGE_SCOPE_OBSERVED' and worker['errors'] == [] and
         worker['package_count'] == 47 and worker['APK_count'] == 87 and worker['packages'] == names and
         worker['framework_MAIN_LAUNCHER_resolver_queried'] is False and
         worker['all_Android_installed_packages_enumerated'] is False and
         worker['original_46_unchanged'] is True and worker['new_helper_matches_actual_install'] is True and
         worker['guard_before'] == worker['guard_after'] and worker['locks_released'] is True and
         worker['process_FDs_before'] == worker['process_FDs_after'] == 5 and
         worker['owned_descriptors_final'] == {'acquired': 31, 'closed': 31, 'errors': [], 'remaining': 0},
         'explicit47 identity/scope observations differ')
    observation = worker['observation']
    need(observation['ok'] is True and observation['app_scope'] == SCOPE_PIN and
         observation['observation_fds'] == {'acquired': 1302, 'closed': 1302, 'errors': [], 'remaining': 0} and
         observation['new_signature_verification_performed'] is False,
         'explicit47 observation authority differs')
    helper = scope_doc['apps'][HELPER]
    need(helper['package'] == HELPER and helper['uid'] == 10157 and helper['version_code'] == 1 and
         len(helper['apks']) == 1 and helper['apks'][0]['bytes'] == 37008 and
         helper['apks'][0]['sha256'] == '006b3bdd64fcd8a03a4ceac0d036b3b99906140feadee61d198756cb6c55c8d9' and
         sum(len(row['apks']) for row in scope_doc['apps'].values()) == 87 and
         all(key == row['package'] for key, row in scope_doc['apps'].items()),
         'current helper identity or complete explicit APK count differs')
    original_snapshot['qualify_typed_guard'](worker['guard_before'])
    original_snapshot['qualify_scope_receipt'](observation['app_scope_guard'], SCOPE_PIN, names)
    try:
        exact_packages(names[:-1], scope_doc['apps'], original46)
    except RuntimeError as error:
        need(str(error) == 'EXPLICIT_47_COMPLETE_PACKAGE_SET_REQUIRED', 'wrong subset rejection')
    else:
        raise RuntimeError('deleted-package subset accepted')
    files['main_snapshot.py'] = replace_nodes(files['main_snapshot.py'], {
        'APP_SCOPE_PIN': 'APP_SCOPE_PIN = ' + pprint.pformat(SCOPE_PIN, sort_dicts=True),
        'APP_SCOPE_PACKAGES': 'APP_SCOPE_PACKAGES = ' + pprint.pformat(names),
    })
    files['fenced_build.py'] = replace_nodes(files['fenced_build.py'], {
        'SNAPSHOT_SHA': 'SNAPSHOT_SHA = ' + repr(sha(files['main_snapshot.py'].encode())),
    })
    staged_pins = {name: {'bytes': len(text.encode()), 'sha256': sha(text.encode())}
                   for name, text in sorted(files.items())}
    stage = replace_nodes(originals['stage.py'], {
        'EXPECTED': 'EXPECTED = ' + pprint.pformat(staged_pins, sort_dicts=True, width=110),
    })
    wire = dump({'schema': 1, 'stage': stage, 'files': files})
    transport = replace_nodes(originals['transport.py'], {
        'WIRE_BYTES': 'WIRE_BYTES = ' + str(len(wire.encode())),
        'WIRE_SHA256': 'WIRE_SHA256 = ' + repr(sha(wire.encode())),
        'STAGE_BYTES': 'STAGE_BYTES = ' + str(len(stage.encode())),
        'STAGE_SHA256': 'STAGE_SHA256 = ' + repr(sha(stage.encode())),
    })
    snapshot_ns = namespace(files['main_snapshot.py'], 'sealed_normal06_snapshot_pure')
    snapshot_ns['qualify_scope_reference'](SCOPE_PIN, names)
    snapshot_ns['qualify_baseline'](json.loads(files['actual-current-runtime-baseline.json']))
    snapshot_ns['qualify_typed_guard'](worker['guard_before'])
    snapshot_ns['qualify_scope_receipt'](observation['app_scope_guard'], SCOPE_PIN, names)
    controls_ns = namespace(files['pure_controls.py'], 'sealed_normal06_controls_pure')
    controls = controls_ns['run'](files)
    need(controls['state'] == 'PASS' and controls['passed'] == 59, 'inherited 59 controls incomplete')
    framework_ns = namespace(files['framework_build.py'], 'sealed_normal06_framework_plan')
    framework_ns['qualify_builder470_receipt'](json.loads(files['actual-builder470-result.json']))
    request = json.loads((PREVIOUS / 'request-template.unsealed.json').read_text())
    request['args'][3] = transport
    request['stdin'] = wire
    parent_request = json.loads((REFERENCE / 'parent-request-without-stdin.json').read_text())
    need({key: value for key, value in request.items() if key not in ['args', 'stdin', 'idempotency_key']} ==
         {key: value for key, value in parent_request.items() if key not in ['args', 'idempotency_key']} and
         request['args'][:3] == parent_request['args'][:3] and request['args'][4:] == parent_request['args'][4:],
         'original process/resource envelope changed')
    materials = {**files, 'stage.py': stage, 'transport.py': transport}
    for name, text in materials.items():
        if name.endswith('.py'):
            compile(text, name, 'exec')
        put(OUTPUT / name, text)
    put(OUTPUT / 'exact-stdin.json', wire)
    request_raw = dump(request)
    put(OUTPUT / 'exact-request.json', request_raw)
    put(OUTPUT / 'pure-controls.actual.json', dump(controls))
    for name in ['builder470-receipt-controls.actual.json', 'local-inheritance-check.json']:
        put(OUTPUT / name, (PREVIOUS / name).read_bytes())
    proof = {'schema': 1, 'state': 'EXACT_EXPLICIT47_LOCAL_SEAL_PASS',
        'scope_authority': SCOPE_PIN, 'scope_local_raw': str(SCOPE_LOCAL),
        'actual_scope_job': '1a1b1e97bb7-fc05-7b79', 'actual_scope_readback_job': '1a1b1ebf1d4-fc05-7b84',
        'scope_readback_extra_out_of_range_page_was_rejected': True,
        'original_scope_bytes_used_without_reconstruction': True,
        'scope_packages': names, 'package_count': 47, 'APK_count': 87,
        'old_46_plus_actual_helper_exactly': True, 'deleted_package_negative_fixture_rejected': True,
        'actual_typed_guard_and_scope_receipts_match': True,
        'framework_MAIN_LAUNCHER_resolver_queried': False,
        'all_Android_installed_packages_enumerated': False,
        'new_runtime_signature_verification_performed_by_sealer': False,
        'Main_or_remote_operations_by_sealer': 0, 'normal06_submitted': False,
        'original_process_resource_envelope_unchanged': True, 'production_ready': False}
    put(OUTPUT / 'scope-binding.actual.json', dump(proof))
    plan = framework_ns['plan']()
    plan.update({'state': 'SEALED_STRICT_TWO_TARGET_REQUEST_REVIEW_REQUIRED',
        'actual_scope_authority': SCOPE_PIN, 'scope_kind': 'explicit47; not a new resolver inventory',
        'actual_scope_package_count': 47, 'actual_scope_APK_count': 87,
        'framework_MAIN_LAUNCHER_resolver_queried': False,
        'all_Android_installed_packages_enumerated': False, 'scope_static_seal_qualified': True,
        'fresh_live_scope_and_typedguard_required_at_execution': True,
        'fresh_15GiB_admission_still_required': True,
        'four_actual_host_capture_lifecycle_controls_still_required': True,
        'framework_build_submitted': False, 'host_window_authorized': False,
        'production_ready': False, 'cleanup_eligible': False})
    put(OUTPUT / 'execution-plan.json', dump(plan))
    for label, olddir in [('unsealed-to-sealed', PREVIOUS), ('normal05-to-normal06-code', REFERENCE)]:
        parts = []
        for name in ['framework_build.py', 'main_snapshot.py', 'fenced_build.py', 'pure_controls.py', 'stage.py', 'transport.py']:
            before = (olddir / name).read_text()
            after = materials[name]
            parts.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                fromfile=olddir.name + '/' + name, tofile='source-r2/' + name))
        put(OUTPUT / (label + '.diff'), ''.join(parts))
    metadata = copy.deepcopy(previous_manifest)
    metadata.update({'schema': 'pocket4-normal06-sealed-source-v2',
        'state': 'SEALED_REVIEW_REQUIRED_NOT_SUBMITTED',
        'files': {name: {'bytes': len(text.encode()), 'sha256': sha(text.encode())}
                  for name, text in sorted(materials.items())},
        'current_scope_pin': SCOPE_PIN, 'current_scope_packages': names, 'current_scope_APK_count': 87,
        'scope_kind': 'explicit-current-app-observation', 'all_launcher_inventory_complete': False,
        'scope_binding_proof_sha256': sha(dump(proof).encode()),
        'exact_stdin': {'bytes': len(wire.encode()), 'sha256': sha(wire.encode())},
        'exact_request': {'bytes': len(request_raw.encode()), 'sha256': sha(request_raw.encode())},
        'host_window_authorized': False,
        'source_r1_schema_error_preserved_and_fixed_before_any_submission': True,
        'source_r1b_manifest': {'bytes': len(previous_manifest_raw), 'sha256': sha(previous_manifest_raw)},
    })
    put(OUTPUT / 'SOURCE_PINS.json', dump(metadata))
    print(json.dumps({'root': str(OUTPUT), 'staged_members': len(files), 'code_and_raw_members': len(materials),
        'exact_request': metadata['exact_request'], 'exact_stdin': metadata['exact_stdin'],
        'source_manifest': {'bytes': len(dump(metadata).encode()), 'sha256': sha(dump(metadata).encode())},
        'scope': SCOPE_PIN, 'package_count': 47, 'APK_count': 87, 'submitted': False}))


if __name__ == '__main__':
    main()
