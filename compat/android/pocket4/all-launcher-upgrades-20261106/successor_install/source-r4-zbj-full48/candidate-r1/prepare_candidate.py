#!/usr/bin/env python3
"""Derive the full48 ZBJ revision from the unchanged, actually staged r3 source.

This local preparation only reads archived evidence and executes pure controls.
It does not stage, claim, install, enter Android, or acquire any Main lease.
"""
import ast
import copy
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PARENT = 'successor_install/source-r3-zbj/candidate-r2'
SOURCE_ROOT = '/home/alex/work/pocket4-successor-install-source-20261106-r4-zbj-full48-r1'
INPUT_ROOT = '/home/alex/work/pocket4-successor-install-input-20261106-zbj-s43-full48-r4-01'
OUTPUT_ROOT = '/home/alex/work/pocket4-successor-native-install-20261106-zbj-s43-full48-r4-01'
SCOPE_LOCAL = 'successor_audit_requests/explicit48_scope_r1/actual-readback/app-scope.private.json'
SCOPE_REF = {'path': '/home/alex/work/pocket4-current-explicit-48-app-observation-20261106-r1/app-scope.private.json',
             'bytes': 59957, 'sha256': 'b184299ce0a39a998752ed980a43192b396099f780bcf60bcfe53d0edf92ffe4'}
SOURCE_KEY = 'pocket4-zbj-successor-installer-full48-r4-source-stage-01-20261106'
INSTALL_KEY = 'pocket4-successor-zbj-s43-signed-full48-r4-upgrade-01-20261106'
NDK = 'com.example.ndk_tests'
HELPER = 'org.droidloom.qa.successor.p8f89f253350ba2fa.r1'
INPUTS = []


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + '\n').encode()


def pin(path, raw):
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def read(path, expected=None):
    raw = (ROOT / path).read_bytes()
    row = pin(path, raw)
    if expected is not None:
        assert (row['bytes'], row['sha256']) == expected, path
    if row not in INPUTS:
        INPUTS.append(row)
    return raw


def put(name, raw):
    if isinstance(raw, str):
        raw = raw.encode()
    path = HERE / name
    if path.exists():
        assert path.read_bytes() == raw, 'refuse to replace differing artifact: ' + name
    else:
        with path.open('xb') as stream:
            stream.write(raw)
    return pin(name, raw)


def replace_once(text, old, new):
    assert text.count(old) == 1, old[:160]
    return text.replace(old, new, 1)


def definitions(source):
    lines = source.splitlines(keepends=True)
    return {node.name: ''.join(lines[node.lineno - 1:node.end_lineno])
            for node in ast.parse(source).body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}


def constants(source):
    values = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                values[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    return values


def replace_constant(source, name, value):
    line = next(line for line in source.splitlines() if line.startswith(name + ' = '))
    return replace_once(source, line, name + ' = ' + repr(value))


def durable_success(terminal, job_id, stdout):
    assert terminal['job_id'] == job_id and terminal['state'] == 'succeeded'
    assert type(terminal['exit_code']) is int and terminal['exit_code'] == 0
    assert all(terminal[key] is True for key in ('output_complete', 'output_durable', 'terminal_publication_confirmed'))
    assert all(terminal[key] is False for key in ('automatic_retry', 'cancelled', 'timed_out'))
    assert terminal['log_bytes'] == {'stdout': {'seen': len(stdout), 'stored': len(stdout)},
                                     'stderr': {'seen': 0, 'stored': 0}}
    for stream in ('stdout', 'stderr'):
        assert terminal['log_errors'][stream] is None
        assert terminal['log_truncated'][stream] is False
        assert terminal['log_synced'][stream] is True


def main():
    manifest_raw = read(PARENT + '/SOURCE_PINS.json',
                        (9590, 'fba6aa00c9e7844e7218f95aabb0dc69d098e3f748bfd45b12d7abd6cd17990e'))
    old_manifest = json.loads(manifest_raw)
    archived = {}
    for item in old_manifest['outputs']:
        archived[item['path']] = read(PARENT + '/' + item['path'], (item['bytes'], item['sha256']))
    parent = archived['install_successor_native.py'].decode()
    assert (len(parent.encode()), sha(parent.encode())) == (62335, 'dbb984125844250ff94561aaf9a8a0dd459decc66cf05349151eec961c0ddc7f')
    parent_defs = definitions(parent)
    old_constants = constants(parent)
    old_stage = archived['stage_source.py'].decode()
    old_outer = archived['stage_request_and_invoke_r3_zbj.py'].decode()
    parent_qual = archived['qualification_functions.py'].decode()
    old_test_body = archived['test_body.py'].decode()
    old_scope = json.loads(archived['scope47.original.json'])
    staged_stdout = read(PARENT + '/actual-source-stage/stdout.original.json',
                         (3052, '07c8a8b61afedca6750ccea191a5a8f350dd72021e53bec09b709065745a9e73'))
    staged_terminal = json.loads(read(PARENT + '/actual-source-stage/terminal.original.json',
                                    (731, '0ad75a0bf5352f012df3bf25b5f26c9ed561e980efd8d498f231d2ab31242ce2')))
    durable_success(staged_terminal, '1a1b2defc61-fc05-8011', staged_stdout)
    staged = json.loads(staged_stdout)['result']
    assert staged['ok'] is True and staged['FDs_before'] == staged['FDs_after'] == 4
    assert staged['files']['install_successor_native.py']['sha256'] == sha(parent.encode())
    assert staged['tests'][0]['returncode'] == 0 and staged['tests'][0]['joined'] is True
    read(PARENT + '/root-source-review.actual.json',
         (688, '3dc8d830d5c0c4b7c226fd433a38ede8d509e2a0a560fbdf2de5e0509f9e2149'))
    read(PARENT + '/actual-source-stage/root-validation.actual.json',
         (473, 'fab2ac3826bd0cb9ce2d19e5b6a7d36de6a3c5b631dbb57982352447c950506e'))

    scope_raw = read(SCOPE_LOCAL, (SCOPE_REF['bytes'], SCOPE_REF['sha256']))
    scope = json.loads(scope_raw)
    assert scope['schema'] == old_scope['schema'] == 'pocket4-versioned-app-scope-v1'
    assert scope['runtime_epoch_sha256'] == old_scope['runtime_epoch_sha256']
    assert len(scope['apps']) == 48 and set(scope['apps']) - set(old_scope['apps']) == {NDK}
    assert set(old_scope['apps']) - set(scope['apps']) == set()
    assert all(scope['apps'][package] == value for package, value in old_scope['apps'].items())
    assert HELPER in scope['apps'] and scope['apps']['com.zhubajie.client']['version_code'] == 369
    ndk = scope['apps'][NDK]
    assert ndk['uid'] == 10162 and ndk['version_code'] == 0 and len(ndk['apks']) == 1
    assert ndk['apks'][0]['bytes'] == 1397258
    assert ndk['apks'][0]['sha256'] == 'b3bf438dedbcdd5f3ac871733a273b3cece446db6be308df73f95b08cb46d164'
    assert ndk['fresh_signature_verification'] is False
    scope_proof = json.loads(read('successor_audit_requests/explicit48_scope_r1/actual/root-validation.actual.json',
                       (1330, 'e66b00681144b4ba1049cab4e429c44f33ab5e1e1aa3e8c190776acb71b5f73b')))
    assert scope_proof['scope'] == SCOPE_REF and scope_proof['status'] == 'PASS_IDENTITY_SCOPE_ONLY'
    assert scope_proof['old47_unchanged'] is True and scope_proof['new_package_matches_actual_discovery'] is True
    assert scope_proof['package_count'] == 48 and scope_proof['APK_count'] == 88
    assert scope_proof['new_signature_verification_performed'] is False
    readback_proof = json.loads(read('successor_audit_requests/explicit48_scope_r1/actual-readback/root-validation.actual.json',
                       (740, '9231000ea3bd613f29d75bb86bd94134d1425ad40fb0fb9f8beadb6e1ad85058')))
    assert readback_proof['ok'] is True and readback_proof['scope'] == SCOPE_REF
    assert readback_proof['raw_reconstructed'] is False and readback_proof['signature_audit_claim'] is False
    readback_stdout = read('successor_audit_requests/explicit48_scope_r1/readback-request-r1/actual/stdout.original.json',
                       (65821, 'e5f03b903be3868690b47c5d29105f88a6978732118804ecd378d621e2c575c5'))
    terminal_raw = read('successor_audit_requests/explicit48_scope_r1/readback-request-r1/actual/terminal.original.json',
                       (733, '1bfcfa90b9fef26dc519b9590711720ce4664c9babec7ba3a97d38dbd37016eb'))
    durable_success(json.loads(terminal_raw), '1a1b319fff6-fc05-80a0', readback_stdout)

    request = copy.deepcopy(old_constants['REVIEWED_ZBJ_REQUEST'])
    request['app_scope'] = dict(SCOPE_REF)
    request['verifier_terminal']['path'] = INPUT_ROOT + '/verifier-terminal.raw.json'
    request['output_root'] = OUTPUT_ROOT
    assert request['official_verifier'] == old_constants['S43_RESULT_REFERENCE']
    assert request['guard'] == old_constants['REVIEWED_ZBJ_REQUEST']['guard']
    guard = read('recovery/independent_repair_r2/actual-execute-01/current_baseline_guard.py',
                 (request['guard']['bytes'], request['guard']['sha256']))
    assert constants(guard.decode())['PINS']['baseline']['sha256'] == sha(read(
        'recovery/independent_repair_r2/actual-execute-01/baseline.private.json'))
    qualifier = replace_once(parent_qual, 'qualify_explicit47_scope', 'qualify_explicit48_scope')
    qualifier = replace_once(qualifier, 'observed 47 identities', 'observed 48 identities')
    qualifier = replace_once(qualifier, "len(scope['apps']) == 47", "len(scope['apps']) == 48")
    qualifier = replace_once(qualifier, 'CURRENT_EXACT_EXPLICIT47_APP_SCOPE_REQUIRED', 'CURRENT_EXACT_EXPLICIT48_APP_SCOPE_REQUIRED')
    qualifier = replace_once(qualifier, 'len(before) == len(after) == 46', 'len(before) == len(after) == 47')
    put('qualification_functions.py', qualifier)
    worker = replace_once(parent, parent_qual, qualifier)
    worker = replace_once(worker, "        qualify_explicit47_scope(scope,baseline['runtime_epoch_sha256'])",
                          "        qualify_explicit48_scope(scope,baseline['runtime_epoch_sha256'])")
    worker = replace_constant(worker, 'REVIEWED_EXPLICIT_PACKAGES', tuple(sorted(scope['apps'])))
    worker = replace_constant(worker, 'REVIEWED_ZBJ_REQUEST', request)
    worker = replace_once(worker,
        'Revision 3 admits one exact ZBJ request using actual S43 and explicit47.',
        'Revision 4 admits one exact ZBJ request using unchanged actual S43 and full48.')
    compile(worker, 'install_successor_native.py', 'exec')
    new_defs = definitions(worker)
    changed = [name for name in parent_defs if name in new_defs and parent_defs[name] != new_defs[name]]
    assert changed == ['require_unchanged_non_target_rows', 'run'], changed
    assert set(parent_defs) - set(new_defs) == {'qualify_explicit47_scope'}
    assert set(new_defs) - set(parent_defs) == {'qualify_explicit48_scope'}
    assert new_defs['run'] == parent_defs['run'].replace('qualify_explicit47_scope', 'qualify_explicit48_scope')
    unchanged = [name for name in parent_defs if name in new_defs and parent_defs[name] == new_defs[name]]
    new_constants = constants(worker)
    assert set(new_constants) == set(old_constants)
    assert [name for name in old_constants if new_constants[name] != old_constants[name]] == [
        'REVIEWED_EXPLICIT_PACKAGES', 'REVIEWED_ZBJ_REQUEST']
    worker_pin = put('install_successor_native.py', worker)

    fixtures = {name: archived[name] for name in ('s43-result.original.json', 's43-terminal.original.json',
                                                  's42-failed-result.original.json', 'scope47.original.json')}
    fixtures['scope48.original.json'] = scope_raw
    fixture_pins = {name: {key: value for key, value in put(name, raw).items() if key != 'path'}
                    for name, raw in fixtures.items()}
    test_body = old_test_body.replace('qualify_explicit47_scope', 'qualify_explicit48_scope')
    test_body = replace_once(test_body, "scope = values['scope47.original.json']", "scope = values['scope48.original.json']")
    test_body = replace_once(test_body, 'actual_explicit47_scope_keys_accepted_without_freshness_claim',
                            'actual_explicit48_scope_keys_accepted_without_freshness_claim')
    test_body = replace_once(test_body, 'old46_scope_missing_new_helper_rejected', 'scope48_missing_owned_helper_rejected')
    test_body = replace_once(test_body,
        "    rejects('stale_runtime_epoch_rejected', lambda: worker.qualify_explicit48_scope(scope, '0'*64))\n",
        "    rejects('stale_runtime_epoch_rejected', lambda: worker.qualify_explicit48_scope(scope, '0'*64))\n"
        "    prior = values['scope47.original.json']\n"
        "    assert all(scope['apps'][k] == v for k, v in prior['apps'].items())\n"
        "    assert set(scope['apps']) - set(prior['apps']) == {'com.example.ndk_tests'}\n"
        "    assert scope['apps']['com.example.ndk_tests']['fresh_signature_verification'] is False\n"
        "    rejects('actual_old47_without_NDK_is_not_the_new48_scope',\n"
        "            lambda: worker.qualify_explicit48_scope(prior, scope['runtime_epoch_sha256']))\n")
    test_body = replace_once(test_body,
        "    changed_request = copy.deepcopy(worker.REVIEWED_ZBJ_REQUEST)\n",
        "    changed_ndk = copy.deepcopy(non_target)\n"
        "    changed_ndk['com.example.ndk_tests']['apks'][0]['file']['st_ino'] += 1\n"
        "    rejects('same_NDK_bytes_but_replaced_inode_rejected',\n"
        "            lambda: worker.require_unchanged_non_target_rows(non_target, changed_ndk))\n"
        "    changed_request = copy.deepcopy(worker.REVIEWED_ZBJ_REQUEST)\n")
    test_body = replace_once(test_body, 'pocket4-zbj-r3-local-qualification-controls-v1',
                            'pocket4-zbj-full48-r4-local-qualification-controls-v1')
    put('test_body.py', test_body)
    old_test = archived['test_install_successor_r3_zbj.py'].decode()
    assert old_test.endswith(old_test_body)
    tests = replace_constant(old_test[:-len(old_test_body)], 'FIXTURE_PINS', fixture_pins) + test_body
    test_name = 'test_install_successor_r4_zbj_full48.py'
    put(test_name, tests)
    compile(tests, test_name, 'exec')
    cp = subprocess.run([sys.executable, '-I', '-B', str(HERE / test_name)], stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, timeout=30, check=False)
    put('local-controls.stdout.original.json', cp.stdout)
    put('local-controls.stderr.original.txt', cp.stderr)
    assert cp.returncode == 0, cp.stderr.decode()
    controls = json.loads(cp.stdout)
    assert controls['ok'] is True and all(item['pass'] is True for item in controls['checks'])
    assert controls['runtime_worker_called'] is False and controls['actual_host_child_spawns'] == 0

    names = sorted(['install_successor_native.py', test_name] + list(fixtures))
    stage = replace_once(old_stage, "ROOT='/home/alex/work/pocket4-successor-install-source-20261106-r3-zbj-r2'",
                         'ROOT=' + repr(SOURCE_ROOT))
    names_line = next(line for line in stage.splitlines() if line.startswith('NAMES='))
    stage = replace_once(stage, names_line, 'NAMES={' + ','.join(repr(name) for name in names) + '}')
    stage = replace_once(stage, "for name in ('test_install_successor_r3_zbj.py',):", "for name in ('" + test_name + "',):")
    stage = stage.replace('pocket4-installer-revision3-zbj-source-host-controls-v1',
                          'pocket4-installer-revision4-zbj-full48-source-host-controls-v1')
    stage = stage.replace('pocket4-installer-revision3-zbj-source-prep-v1',
                          'pocket4-installer-revision4-zbj-full48-source-prep-v1')
    assert definitions(stage) == definitions(old_stage)
    compile(stage, 'stage_source.py', 'exec')
    put('stage_source.py', stage)
    host_worker = {**worker_pin, 'path': SOURCE_ROOT + '/install_successor_native.py'}
    outer = replace_constant(old_outer, 'SOURCE', host_worker)
    assert definitions(outer) == definitions(old_outer)
    compile(outer, 'stage_request_and_invoke_r4_zbj_full48.py', 'exec')
    put('stage_request_and_invoke_r4_zbj_full48.py', outer)
    payload = encoded({'files': {name: (HERE / name).read_text() for name in names}, 'stager_source': stage})
    assert len(payload) <= 1048576 and all(0 < len((HERE / name).read_bytes()) <= 100000 for name in names)
    put('stage-payload.json', payload)
    stage_process = {'host': 'pocket4', 'executable': '/usr/bin/sudo',
        'args': ['-n', '/usr/bin/python3', '-I', '-B', '-c', stage], 'cwd': '/home/alex/work', 'stdin': payload.decode(),
        'idempotency_key': SOURCE_KEY, 'timeout_seconds': 180, 'cpu_quota_percent': 100,
        'memory_max_bytes': 536870912, 'nice': 10}
    request_raw = encoded(request)
    put('install-request.json', request_raw)
    install_input = encoded({'input_root': INPUT_ROOT, 'request_text': request_raw.decode(),
                             'terminal_text': fixtures['s43-terminal.original.json'].decode()})
    assert len(install_input) <= 131072
    put('install-input.json', install_input)
    install_process = {'host': 'pocket4', 'executable': '/usr/bin/sudo',
        'args': ['-n', '/usr/bin/python3', '-I', '-B', '-c', outer], 'cwd': '/home/alex/work', 'stdin': install_input.decode(),
        'idempotency_key': INSTALL_KEY, 'timeout_seconds': 900, 'cpu_quota_percent': 100,
        'memory_max_bytes': 1073741824, 'nice': 10}
    stage_pin = put('exact-stage-process-request.review-only.json', encoded(stage_process))
    install_pin = put('exact-install-process-request.review-only.json', encoded(install_process))
    for name, before, after in (
        ('worker-against-actual-r3.diff', parent, worker),
        ('qualification-against-actual-r3.diff', parent_qual, qualifier),
        ('test-body-against-actual-r3.diff', old_test_body, test_body),
        ('source-stage-against-actual-r3.diff', old_stage, stage),
        ('outer-stage-against-actual-r3.diff', old_outer, outer)):
        put(name, ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                             fromfile='actual-staged-r3-explicit47', tofile='review-only-r4-full48')))

    transition = json.loads(read(PARENT + '/scope-transition.json',
        (7278, '8667182e658433dd2829fd0ddea8ac1ce3fe992b89e6acf7411407f1d3dd6321')))
    transition['schema'] = 'pocket4-zbj-full48-scope-transition-review-v1'
    transition['old_scope'] = dict(SCOPE_REF)
    transition['old_scope_local_original'] = pin(SCOPE_LOCAL, scope_raw)
    transition['old_scope_kind'] = 'actual explicit48 identity observation; NDK identity is not fresh signature verification'
    transition['before_install'][0] = 'Root settles and pauses all Main consumers bound to the current 48-scope, including permission capture and Beike QA; no overlapping mutation.'
    transition['before_install'][3] = 'The exact actual48 raw hash, same runtime epoch, all 48 package keys and every current app identity must pass the inherited typed guard before any intent.'
    transition['other_47'] = transition.pop('other_46')
    transition['other_47']['includes'] = [NDK, HELPER]
    transition['other_47']['new_gate_negative_control'] = 'same_NDK_bytes_but_replaced_inode_rejected'
    transition['publication']['actual_future_path'] = OUTPUT_ROOT + '/app-scope-after.private.json'
    transition['publication']['exact_count'] = 48
    transition['publication']['parent_app_scope'] = dict(SCOPE_REF)
    transition['publication']['success_requirements'][6] = 'new scope guard checks all 48 rows successfully'
    transition['consumer_migration'] = [
        {'consumer': 'future QA and current permission series',
         'reference': 'new actual post-install scope pin after successful complete readback',
         'required': 'Use a new explicit source/request binding where the whole-scope contract applies; current 48 requests remain attached to the pre-upgrade scope. No old receipt or failure is rewritten.',
         'prohibited': 'Replay a stale scope or infer effective grants from normal installation.'},
        {'consumer': 'future strict Framework build',
         'reference': 'new actual post-install 48-scope pin in a newly reviewed request',
         'required': 'Keep existing typed runtime, qualified builder, strict targets, fences and fresh RAM gates.',
         'prohibited': 'Edit earlier build source/receipts or treat installation as a framework build success.'},
        {'consumer': 'future inventory and upgrades',
         'reference': 'new actual48 transaction scope, with separate resolver/PM observations for membership claims',
         'required': 'Preserve all 47 non-target rows exactly; scope identity does not supply NDK signature or UI qualification.'}]
    transition['unchanged_old_chain']['old_staged_r3_candidate_preserved_not_installed_by_this_preparation'] = True
    transition['unchanged_old_chain']['old48_b184299c_raw_observation_retained'] = True
    transition['new_NDK_fresh_signature_claim'] = False
    put('scope-transition.json', encoded(transition))
    old_plan = json.loads(archived['execution-plan.json'])
    plan = {
        'schema': 'pocket4-zbj-full48-revision4-review-plan-v1', 'state': 'SEALED_FOR_ROOT_REVIEW_NOT_SUBMITTED',
        'parent_actual_staged_source': {'path': PARENT + '/install_successor_native.py', 'bytes': len(parent.encode()), 'sha256': sha(parent.encode()),
            'source_stage_job': '1a1b2defc61-fc05-8011', 'old_source_unchanged': True, 'old_install_not_claimed': True},
        'package': 'com.zhubajie.client', 'candidate': old_plan['candidate'],
        'historical_installed_reference': old_plan['historical_installed_reference'],
        'scope': {'input': dict(SCOPE_REF), 'count': 48, 'packages': sorted(scope['apps']),
                  'runtime_epoch': scope['runtime_epoch_sha256'], 'original47_rows_exactly_equal': True,
                  'new_package': NDK, 'new_package_fresh_signature_claim': False,
                  'source_generation_is_not_fresh_runtime_qualification': True},
        'only_runtime_source_deltas': ['exact scope constant and 48-package set',
            'scope qualification function name and exact count 48',
            'unchanged non-target full-row comparison count 47', 'new input/output/source paths'],
        'unchanged_gates': old_plan['unchanged_gates'], 'budgets': old_plan['budgets'],
        'fresh_install_is_not_runtime_QA': old_plan['fresh_install_is_not_runtime_QA'],
        'execution_order': ['root reviews full source/diffs/inputs and stable exact keys',
            'one source-only stage; require actual durable success, exact worker and all pure controls',
            'root settles and pauses existing Main consumers; no unresolved installation',
            'one fresh48 guarded normal signed update with original whole lifecycle and old APK retention',
            'success requires actual same UID/CE/DE, code370/same vendor, exact candidate bytes, all 47 other full rows, Meituan projection and Bili evidence unchanged',
            'read back the actual new48 scope raw bytes and pin; migrate scope-bound future requests explicitly'],
        'unknown_outcome_rule': 'No automatic retry or replacement key. Any possibly attempted mutation with incomplete receipt/postcheck/retirement remains UNKNOWN.',
        'artifact_retention': transition['artifact_retention'],
        'permission_boundary_clarification': transition['permission_boundary_clarification'],
        'framework_RAM_observation_or_build': False, 'cleanup_eligible': False, 'production_ready': False,
        'remote_submissions': 0}
    put('execution-plan.json', encoded(plan))
    inherit = {'schema': 'pocket4-zbj-full48-r4-source-inheritance-v1', 'parent': PARENT,
        'parent_immutable_output_pins_checked': len(old_manifest['outputs']),
        'actual_parent_source_stage_job': '1a1b2defc61-fc05-8011',
        'worker_unchanged_definitions': unchanged, 'changed_existing_definitions': changed,
        'renamed_scope_definition': {'from': 'qualify_explicit47_scope', 'to': 'qualify_explicit48_scope'},
        'run_delta_is_only_qualification_function_name': True,
        'changed_constants': ['REVIEWED_EXPLICIT_PACKAGES', 'REVIEWED_ZBJ_REQUEST'],
        'source_stage_helpers_byte_equal': sorted(definitions(stage)),
        'outer_stage_helpers_byte_equal': sorted(definitions(outer)),
        'S43_qualifier_verifier_tools_signer_candidate_and_terminal_unchanged': True,
        'normal_native_install_retirement_and_data_logic_unchanged': True,
        'old47_rows_match_actual48_exactly': True, 'new_NDK_signature_not_claimed': True,
        'local_controls': {'returncode': cp.returncode, 'count': len(controls['checks']),
                           'runtime_worker_called': False, 'fresh_scope_or_install_proved': False},
        'remote_submissions': 0, 'old_failed_unknown_and_gate_receipts_unchanged': True}
    put('source-inheritance.json', encoded(inherit))
    put('REVIEW.md', '''# ZBJ Revision 4 / full48 — review only

This candidate extends only the identity range of the actually staged r3 ZBJ
worker. The exact S43 candidate is still code 370 / 9.5.20, signed by the same
vendor as the installed code 369 / UID10144. The original S43 proof and all
normal PackageManager, byte, data, permission-projection and retirement gates
are retained. The old r3 candidate and old FAILED/UNKNOWN evidence are intact.

The actual 59,957-byte full48 scope includes NDK and the owned helper. Every old
47 app row is exactly unchanged. The new scope proves identities, not NDK
signature verification, permissions, business readiness or a complete PM set.
Runtime preflight still re-observes all 48 rows under the original action lock.
The full-row non-target gate now requires 47 rows, including NDK's exact APK
stat and CE/DE identity. This is not merely a package-count substitution.

Review the five against-actual-r3 diffs, source-inheritance.json and fixed input
pins. The installer run changes only the scope qualifier name. All 26 remaining
existing definitions, including the S43 qualifier, native runner, final UNKNOWN
publication and data checks, are byte-for-byte retained. The two old stage
programs retain every helper function; only fixed paths, closure names, test
name, revision label and the new worker source pin change.

Local controls import this frozen source and interpret original actual fixtures.
They do not call run(), load a runtime guard, access Main or acquire its locks.
They retain the original signature/terminal/unknown-output negatives and add
the actual old47 rejection plus a changed NDK inode rejection. The new source
stage must separately complete these controls on the host. This preparation
does not claim it has been staged or that an installation has occurred.

Root must settle/pause all scope-bound Main consumers before an install. A
successful install creates an actual new full48 scope; old whole-scope requests
must not be reused after it. The exact review-only packets use new stable keys,
no automatic retry, original 700-second worker/260-second install bounds,
900-second outer install timeout and 1 GiB memory profile. No permission grant,
UI, ADB, lifecycle action, integrity override or cleanup is added.
''')
    outputs = [pin(path.name, path.read_bytes()) for path in sorted(HERE.iterdir()) if path.is_file()
               and path.name not in ('SOURCE_PINS.json', 'local-preparation.exec-result.json', 'FINAL_LOCAL_VALIDATION.json')]
    final_manifest = {'schema': 'pocket4-zbj-full48-r4-source-and-evidence-pins-v1',
        'state': 'SEALED_FOR_ROOT_REVIEW_NOT_SUBMITTED', 'inputs': INPUTS, 'outputs': outputs,
        'host_staged_members': names, 'remote_submissions': 0, 'old_sources_and_failures_preserved': True}
    manifest_pin = put('SOURCE_PINS.json', encoded(final_manifest))
    print(json.dumps({'ok': True, 'candidate': str(HERE), 'worker': worker_pin, 'manifest': manifest_pin,
        'stage_request': stage_pin, 'install_request': install_pin, 'pure_controls': len(controls['checks']),
        'unchanged_worker_definitions': len(unchanged), 'scope_packages': 48, 'non_target_exact_rows': 47,
        'remote_submissions': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
