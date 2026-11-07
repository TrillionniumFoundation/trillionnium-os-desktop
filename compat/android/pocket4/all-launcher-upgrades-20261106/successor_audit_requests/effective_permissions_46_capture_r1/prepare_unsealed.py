#!/usr/bin/env python3
"""Prepare non-executable permission capture templates. No device or claim API."""
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
OLD = PROJECT / 'successor_audit_requests/effective_permissions_45_capture_r1'
MICROG = PROJECT / 'successor_audit_requests/revisions/permissions-microg-b02-correction-r1'
DISCOVERY = PROJECT / 'successor_audit_requests/native46_discovery_r1/actual'
PINS = {
    'original_partition': ('successor_audit_requests/final-upgrades-r1/REQUEST_MANIFEST.json', 17548, 'd288affedc2eae8d28f2d7083df4c89d756e51ba8e5ebfb2264f9d3c6d783139'),
    'old_plan': ('successor_audit_requests/effective_permissions_45_capture_r1/CAPTURE_PLAN.json', 47161, '802c9616b99c0c753c7a31188ab7b594e5baba39d6940d963c2c1b9bd2cdb749'),
    'worker': ('successor_audit_requests/effective_permissions_45_capture_r1/batch-01/observe_current_services.py', 46457, 'c261aa5e00dd1980a2154053fdd25ee72881f6963b584fa1761e3410425ceab5'),
    'transport': ('successor_audit_requests/effective_permissions_45_capture_r1/batch-01/readonly_services_transport.py', 16116, 'bb2c347f3a208175a9db8b31aa8462d862bf732954adf726c795eb1c4fa20b3e'),
    'owner': ('successor_audit_requests/effective_permissions_45_capture_r1/batch-01/owned_readonly_lifetime.py', 19964, '0db1088ebd9a2d19d0f6a9ef2e5bbe2dd7415d7827d9c1c6c1d66c14d4d82cfa'),
    'microg_worker': ('successor_audit_requests/revisions/permissions-microg-b02-correction-r1/observe_current_services.py', 56665, 'a968ecab4f8b1837bd7f153c6c76517625b5f2ec89d5a157b19e494a5ab5f641'),
    'discovery': ('successor_audit_requests/native46_discovery_r1/actual/artifact.original.json', 112546, '69482778466e03dceff2defc85fb8f68880c360a3f112e129561a8fd5e6e5400'),
    'discovery_terminal': ('successor_audit_requests/native46_discovery_r1/actual/status-01.original.json', 733, 'f16d1da55f8afa0da6f91f37186fff39dc50ba12a22e54b048290e723dc797bd'),
    'discovery_root_review': ('successor_audit_requests/native46_discovery_r1/actual/root-validation.actual.json', 5903, '0a9c6e397790adce9e064aa445b13929f44bddbfc616820eee8693df70bc11cc'),
    'prior_scope48': ('successor_install/source-r4-zbj-full48/candidate-r1/post_install_scope_readback_r1/actual/app-scope-after.private.json', 59259, '9aeb555bbc287e168d1bb8f1df09e33f8fd37777ee01a58fe2c563e2725cf01a'),
    'old_b03_artifact': ('successor_audit_requests/actual/permissions-fixed45-r1/batch-03/artifact.original.json', 12181, 'f5ff1b1758803a9537bd84023146fa62ac72d8587b1dc94605868413dd2ffc08'),
    'old_b03_terminal': ('successor_audit_requests/actual/permissions-fixed45-r1/batch-03/terminal.original.json', 730, '4a95cb262ac9b2d8d4a0437c53fde9e82ea47b4529e6fd0e79fa87b32ef24552'),
    'old_b03_stop': ('successor_audit_requests/actual/permissions-fixed45-r1/batch-03/gate-status.stdout.original.json', 7906, '90f6e488fd3493c4597e01ab38f622f317d1f2c126df1546884eb3b0e498f6e1'),
}


def need(test, message):
    if not test:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(raw):
    return {'bytes': len(raw), 'sha256': sha(raw)}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2).encode('ascii') + b'\n'


def source(key):
    rel, length, digest = PINS[key]
    raw = (PROJECT / rel).read_bytes()
    need(pin(raw) == {'bytes': length, 'sha256': digest}, 'FIXED_INPUT_CHANGED:' + key)
    return raw


def definition(text, name, parent=None):
    nodes = ast.parse(text).body
    if parent:
        nodes = next(node.body for node in nodes if isinstance(node, ast.FunctionDef) and node.name == parent)
    matches = [node for node in nodes if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name]
    need(len(matches) == 1, 'EXACT_DEFINITION:' + name)
    node = matches[0]
    return ''.join(text.splitlines(keepends=True)[node.lineno - 1:node.end_lineno])


def assignment(text, name, value):
    nodes = [node for node in ast.parse(text).body if isinstance(node, ast.Assign) and
             any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    need(len(nodes) == 1, 'EXACT_ASSIGNMENT:' + name)
    lines = text.splitlines(keepends=True); node = nodes[0]
    lines[node.lineno - 1:node.end_lineno] = [name + ' = ' + repr(value) + '\n']
    return ''.join(lines)


def literal(text, name):
    nodes = [node for node in ast.parse(text).body if isinstance(node, ast.Assign) and
             any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    need(len(nodes) == 1, 'EXACT_LITERAL:' + name)
    return ast.literal_eval(nodes[0].value)


def once(text, old, new):
    need(text.count(old) == 1, 'EXACT_SOURCE_FRAGMENT:' + old[:80])
    return text.replace(old, new, 1)


def write_new(name, raw):
    path = HERE / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        offset = 0
        while offset < len(raw):
            count = os.write(fd, raw[offset:]); need(count > 0, 'LOCAL_WRITE_PROGRESS'); offset += count
        os.fsync(fd)
    finally:
        os.close(fd)
    need(path.read_bytes() == raw, 'LOCAL_READBACK_CHANGED')


def command_list(targets):
    commands = [['/system/bin/cmd', 'package', 'help']]
    for package in targets:
        commands += [['/system/bin/cmd', 'package', 'dump-package', package],
                     ['/system/bin/cmd', 'appops', 'get', '--user', '0', package]]
    return commands


def make_normal_template(original, components):
    text = original
    launchers = sorted(component.split('/', 1)[0] for component in components)
    for name, value in [('LAUNCHERS', tuple(launchers)), ('PACKAGES', None), ('TARGET_PACKAGES', None),
                        ('BATCH_NUMBER', None), ('ACTUAL45_COMPONENTS', components), ('APP_SCOPE', None),
                        ('STAGE', None), ('OUTPUT', None), ('TRANSPORT', None), ('APP_OPS_HELP', None)]:
        text = assignment(text, name, value)
    text = once(text, 'TARGET_USER = 0\n', 'TARGET_USER = 0\nSOURCE_SEALED = False\nNEW_HELPER = None\n')
    text = text.replace('ACTUAL45_COMPONENTS', 'ACTUAL46_COMPONENTS')
    text = text.replace('pocket4-fixed-launcher-permission-capture-request-v1', 'pocket4-fixed46-launcher-permission-capture-request-v1')
    text = text.replace('pocket4-fixed-launcher-permission-raw-capture-v1', 'pocket4-fixed46-launcher-permission-raw-capture-v1')
    text = text.replace('pocket4-fixed-launcher-permission-entry-rejection-v1', 'pocket4-fixed46-launcher-permission-entry-rejection-v1')
    text = once(text, 'def validate_request(request):\n', '''def validate_request(request):
    need(SOURCE_SEALED is True and type(APP_SCOPE) is dict and type(PACKAGES) is list and
         type(NEW_HELPER) is str and len(PACKAGES) == len(set(PACKAGES)) == 49 and
         PACKAGES == sorted((*LAUNCHERS, ACTIONS, HELPER, NEW_HELPER)) and
         type(TARGET_PACKAGES) is list and 1 <= len(TARGET_PACKAGES) <= 4 and
         len(TARGET_PACKAGES) == len(set(TARGET_PACKAGES)) and set(TARGET_PACKAGES) <= set(LAUNCHERS) and
         type(BATCH_NUMBER) is int and 1 <= BATCH_NUMBER <= 14,
         "ACTUAL_SCOPE49_AND_EXACT_BATCH_NOT_BOUND")
''')
    text = once(text, '"ACTUAL_47_REFERENCE_REQUIRED"', '"ACTUAL_49_REFERENCE_REQUIRED"')
    text = once(text, '"actual_framework_resolver_reference_job": "1a1b22e95d0-fc05-7cd4"',
                '"actual_framework_resolver_reference_job": "1a1b307f521-fc05-807a"')
    text = once(text, '"expected_count": 45, "observed_count": len(current_components)',
                '"expected_count": 46, "observed_count": len(current_components)')
    text = once(text, 'len(current_components) == len(set(current_components)) == 45',
                'len(current_components) == len(set(current_components)) == 46')
    text = text.replace('EXACT_ACTUAL45_NATIVE_COMPONENT_REFERENCE_CHANGED', 'EXACT_ACTUAL46_NATIVE_COMPONENT_REFERENCE_CHANGED')
    text = text.replace('native_catalog_matches_actual45_component_reference', 'native_catalog_matches_actual46_component_reference')
    text = once(text, 'current_scope_47_unchanged=True', 'current_scope_49_unchanged=True')
    text = once(text, 'if __name__ == "__main__":\n',
                'if __name__ == "__main__":\n    need(SOURCE_SEALED is True, "UNSEALED_TEMPLATE_NOT_AN_EXECUTABLE_REQUEST")\n')
    return text


def make_microg_template(normal, actual_microg):
    text = normal
    for name in ('held_bounded_child',):
        text = once(text, definition(text, name), definition(actual_microg, name))
    text = once(text, definition(text, 'runner', 'run'), definition(actual_microg, 'runner', 'run'))
    extra = 'CORRECTION_COMMANDS = ' + repr(literal(actual_microg, 'CORRECTION_COMMANDS')) + '\n'
    extra += 'CAPTURE_POLICY = ' + repr(literal(actual_microg, 'CAPTURE_POLICY')) + '\n'
    extra += '\n' + definition(actual_microg, 'capture_limits_for') + '\n'
    text = once(text, 'def write_empty_raw_stream(', extra + '\ndef write_empty_raw_stream(')
    text = once(text, 'def validate_request(request):\n',
                'def validate_request(request):\n    need(BATCH_NUMBER == 2 and TARGET_PACKAGES == ["com.google.android.gms"], "ONLY_FIXED_MICROG_BATCH_MAY_USE_EXCEPTION")\n')
    text = once(text, '"service_output_capture_complete": False,',
                '"service_output_capture_complete": False, "capture_policy": CAPTURE_POLICY,')
    return text


def main():
    raw_inputs = {name: source(name) for name in PINS}
    oldplan = json.loads(raw_inputs['old_plan']); discovery = json.loads(raw_inputs['discovery'])
    original_partition = json.loads(raw_inputs['original_partition'])
    scope48 = json.loads(raw_inputs['prior_scope48'])
    old_failure = json.loads(raw_inputs['old_b03_artifact']); old_stop = json.loads(raw_inputs['old_b03_stop'])
    need(discovery['ok'] is True and discovery['errors'] == [] and discovery['enumeration_samples_equal'] is True,
         'ACTUAL_DISCOVERY_MUST_BE_COMPLETE')
    components = sorted(row['component'] for row in discovery['MAIN_LAUNCHER_components'])
    launcher_packages = sorted(row['package'] for row in discovery['MAIN_LAUNCHER_components'])
    need(len(components) == len(set(components)) == len(launcher_packages) == len(set(launcher_packages)) == 46,
         'EXACT_REAL_46_COMPONENTS_AND_PACKAGES')
    need(all(component.split('/', 1)[0] == package for component, package in
             zip(sorted(components), sorted(launcher_packages))), 'EXACT_COMPONENT_PACKAGE_RELATION')
    need(old_stop['state'] == 'STOP_FAILED_OR_UNVERIFIED_BATCH' and old_stop['batch'] == 3 and
         old_failure['ok'] is False and old_failure['Android_namespace_commands'] == 0,
         'PRESERVE_REAL_OLD_STOP3')
    rows = [{'batch': row['batch'], 'original_partition_batch': row['batch'], 'targets': row['targets']}
            for row in oldplan['batches']]
    need(len(rows) == 13 and [row['batch'] for row in rows] == list(range(1, 14)), 'ORIGINAL_13_BATCH_ORDER')
    need(len(original_partition['batches']) == 13 and all(
         row['batch'] == prior['batch'] and row['targets'] == prior['packages']
         for row, prior in zip(rows, original_partition['batches'])), 'EXACT_ORIGINAL_PARTITION_SOURCE')
    old_targets = [package for row in rows for package in row['targets']]
    need(len(old_targets) == len(set(old_targets)) == 45 and
         set(launcher_packages) - set(old_targets) == {'com.example.ndk_tests'} and
         not set(old_targets) - set(launcher_packages), 'ONLY_ACTUAL_NDK_MEMBERSHIP_ADDITION')
    rows.append({'batch': 14, 'original_partition_batch': None, 'targets': ['com.example.ndk_tests']})
    need(len(scope48['apps']) == 48 and set(launcher_packages) <= set(scope48['apps']), 'PREINSTALL_48_REFERENCE_ONLY')
    for row in rows:
        row['Android_commands'] = command_list(row['targets'])
        row['stream_limits'] = [{'stdout': 262144, 'stderr': 262144} for command in row['Android_commands']]
        if row['batch'] == 2:
            need(row['targets'] == ['com.google.android.gms'], 'EXACT_MICROG_PARTITION')
            row['stream_limits'][1]['stdout'] = 2097152
        row.update(target_identities=None, app_scope=None, source_root=None, output_root=None,
                   idempotency_key=None, process_request=None, actual_results='UNKNOWN_NOT_RUN')
    normal = make_normal_template(raw_inputs['worker'].decode(), components)
    microg = make_microg_template(normal, raw_inputs['microg_worker'].decode())
    transport = assignment(raw_inputs['transport'].decode(), 'READ_ONLY_COMMANDS', None)
    for name, text in [('worker.normal.template.py', normal), ('worker.microg.template.py', microg), ('transport.template.py', transport)]:
        compile(text, name, 'exec')
    old_defs = oldplan['preserved_worker_definitions']
    exact_normal = {name: sha(definition(normal, name).encode()) for name in old_defs
                    if definition(normal, name) == definition(raw_inputs['worker'].decode(), name)}
    need(set(exact_normal) == set(old_defs), 'UNCHANGED_NORMAL_21_WORKER_DEFINITIONS')
    exact_microg = {name: sha(definition(microg, name).encode()) for name in old_defs if name != 'held_bounded_child'
                    and definition(microg, name) == definition(raw_inputs['worker'].decode(), name)}
    need(set(exact_microg) == set(old_defs) - {'held_bounded_child'}, 'UNCHANGED_MICROG_20_COMMON_DEFINITIONS')
    for name, parent in [('held_bounded_child', None), ('capture_limits_for', None), ('runner', 'run')]:
        need(definition(microg, name, parent) == definition(raw_inputs['microg_worker'].decode(), name, parent),
             'ACTUAL_MICROG_LIMIT_AND_RETIREMENT_ALGORITHM_UNCHANGED')
    plan = {'schema': 'pocket4-fixed46-permission-unsealed-plan-v1', 'state': 'WAITING_FOR_ACTUAL_NEW_HELPER_AND_SCOPE49',
        'service_target_packages': 46, 'expected_future_identity_context_packages': 49, 'actual_bound_scope': None,
        'current_new_helper_UID': None, 'current_new_helper_APK': None, 'actual_new_helper_install_job': None,
        'actual_scope49_observation_job': None, 'actual_scope49_readback': None,
        'guard': oldplan['guard'], 'runtime_epoch_sha256': oldplan['runtime_epoch_sha256'],
        'resolver_reference': {'file': PINS['discovery'][0], 'bytes': PINS['discovery'][1], 'sha256': PINS['discovery'][2],
                               'job_id': '1a1b307f521-fc05-807a'},
        'actual_46_components': components, 'target_packages': [p for row in rows for p in row['targets']],
        'batches': rows, 'total_Android_readonly_commands': sum(len(row['Android_commands']) for row in rows),
        'total_native_readonly_commands': 42, 'native_operations_per_batch': ['status', 'applications', 'status'],
        'per_command_seconds': 30, 'Android_timeout_seconds': 25, 'worker_deadline_seconds': 900,
        'owned_child_seconds': 1000, 'outer_process_seconds': 1100,
        'default_per_stream_bytes': 262144, 'microg_dump_stdout_only_bytes': 2097152,
        'old45_STOP3_preserved': True, 'new_ledger_proposed_relative_path': 'successor_audit_requests/actual/permissions-fixed46-r1',
        'old_ledger_advanced_or_reclassified': False, 'fresh_framework_resolver_requeried_by_capture_worker': False,
        'native_component_difference_stops_before_service_queries': True,
        'raw_capture_is_semantic_grant_proof': False, 'roles': 'UNKNOWN_NOT_QUERIED',
        'private_PM_AppOps_body_in_Git': False, 'automatic_retry': False, 'claims_created': 0,
        'packets_sealed': 0, 'remote_jobs_submitted': 0, 'production_ready_apps': 0, 'cleanup_actions': 0}
    need(plan['total_Android_readonly_commands'] == 106, 'EXACT_106_READONLY_COMMANDS')
    contract = {'schema': 'pocket4-scope49-future-input-contract-v1', 'state': 'MISSING_ACTUAL_INPUTS_FAIL_CLOSED',
        'new_helper_package_from_actual_build_and_install': None, 'new_helper_actual_UID': None,
        'new_helper_actual_APK_identity': None, 'actual_installer_stdout': None, 'actual_installer_terminal': None,
        'actual_installer_joint': None, 'actual_scope49_original_bytes': None, 'actual_scope49_remote_path': None,
        'actual_scope49_observer_stdout': None, 'actual_scope49_observer_terminal': None,
        'actual_scope49_complete_readback_receipt': None,
        'required_original48_reference': {'file': PINS['prior_scope48'][0], 'bytes': PINS['prior_scope48'][1], 'sha256': PINS['prior_scope48'][2]},
        'required_relation': 'same runtime; all prior 48 package rows unchanged; exactly one actually installed new helper row; exact 49 keys',
        'current_scope48_is_not_a_substitute': True,
        'final_installer_and_scope_observer_joint_gate_adapter_required_before_sealing': True,
        'may_create_claim_or_process_request_now': False}
    inheritance = {'schema': 'pocket4-fixed46-unsealed-source-inheritance-v1', 'state': 'UNSEALED_NOT_EXECUTABLE',
        'actual_inputs': {key: {'file': row[0], 'bytes': row[1], 'sha256': row[2]} for key, row in PINS.items()},
        'normal_21_worker_definitions_exact': exact_normal, 'microg_20_common_definitions_exact': exact_microg,
        'microg_runner_budget_function_and_owned_retirement_from_actual_correction_exact': True,
        'transport_all_definitions_exact': {name: sha(definition(transport, name).encode())
              for name in oldplan['preserved_transport_definitions']
              if definition(transport, name) == definition(raw_inputs['transport'].decode(), name)},
        'new_owner_and_serial_gate_not_sealed': True, 'old_gate_and_all_frozen_source_modified': False,
        'source_templates_have_explicit_pre_IO_unsealed_refusal': True}
    need(len(inheritance['transport_all_definitions_exact']) == 8, 'ORIGINAL_EIGHT_TRANSPORT_DEFINITIONS')
    files = {'PLAN.unsealed.json': canonical(plan), 'INPUTS.required.json': canonical(contract),
        'SOURCE_INHERITANCE.unsealed.json': canonical(inheritance),
        'worker.normal.template.py': normal.encode(), 'worker.microg.template.py': microg.encode(),
        'transport.template.py': transport.encode(),
        'normal-worker-against-original-b01.diff': ''.join(difflib.unified_diff(raw_inputs['worker'].decode().splitlines(True), normal.splitlines(True),
            fromfile='actual-original45/batch-01/worker.py', tofile='unsealed46/worker.normal.template.py')).encode(),
        'microg-worker-against-normal-template.diff': ''.join(difflib.unified_diff(normal.splitlines(True), microg.splitlines(True),
            fromfile='unsealed46/worker.normal.template.py', tofile='unsealed46/worker.microg.template.py')).encode(),
        'transport-against-original-b01.diff': ''.join(difflib.unified_diff(raw_inputs['transport'].decode().splitlines(True), transport.splitlines(True),
            fromfile='actual-original45/batch-01/transport.py', tofile='unsealed46/transport.template.py')).encode()}
    need(not any((HERE / name).exists() for name in files), 'ONLY_NEW_LOCAL_PREPARATION_OUTPUTS')
    for name, raw in files.items():
        write_new(name, raw)
    for key, raw in raw_inputs.items():
        need(source(key) == raw, 'ORIGINAL_INPUT_CHANGED_DURING_PREPARATION')
    print(json.dumps({'state': plan['state'], 'files': {name: pin(raw) for name, raw in files.items()},
        'actual_launcher_packages': 46, 'expected_future_scope_packages': 49, 'batch_count': 14,
        'Android_commands_planned': 106, 'packets': 0, 'claims': 0, 'remote_or_Main_actions': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
