#!/usr/bin/env python3
"""Prepare one ordinary-UID, two-command S36 APK manifest observation; do not submit."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent.parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pinned(relative, size, digest):
    raw = (BASE / relative).read_bytes()
    assert len(raw) == size and sha(raw) == digest, relative
    return raw


def definition(raw, name):
    text = raw.decode()
    node = next(item for item in ast.parse(raw).body if isinstance(item, ast.FunctionDef) and item.name == name)
    return ast.get_source_segment(text, node) + '\n\n'


def constant(raw, name):
    for node in ast.parse(raw).body:
        if isinstance(node, ast.Assign) and any(isinstance(value, ast.Name) and value.id == name for value in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(name)


def once(name, body):
    with (HERE / name).open('xb') as stream:
        stream.write(body)


def main():
    old = pinned('official_source_scripts/s38_szzc_operator_signature/observe_signature_as_owner.py',
                 21026, '5a223fd2fc4baa5ce3e2b80615e400f11adac27d48365fa67de2b821c275abf3')
    runner = pinned('successor_audit_requests/reference/audit_successor_apks.py',
                    29242, 'faff199c1f6218b3c01d87e44be610d6fa211de396b5e8c862c188dec59d284a')
    actual_raw = pinned('official_source_scripts/s38_szzc_operator_signature/actual/stdout.original.json',
                        25448, '3ba6894d1d084f8d95b4ebfb342a3710990ce3b0aadf0e17710e9f608f8228a6')
    terminal_raw = pinned('official_source_scripts/s38_szzc_operator_signature/actual/status-1.original.txt',
                          733, '2974cb7304f993a0120ed8052cc6ff99837ad01e690d2c0f61f21c4d710ca904')
    batch_raw = pinned('successor_audit_requests/actual/batches-final-r1/batch-04/artifact.original.json',
                       132796, 'd2df2ac82742d7cbc69b43df878af8372e2df617113492e2e8ab25c69bbc0605')
    actual, terminal, batch = json.loads(actual_raw), json.loads(terminal_raw), json.loads(batch_raw)
    assert terminal['job_id'] == '1a1b25b668d-fc05-7dae' and terminal['state'] == 'succeeded' and terminal['exit_code'] == 0
    assert all(terminal[key] is True for key in ['output_complete', 'output_durable', 'terminal_publication_confirmed'])
    assert all(terminal[key] is False for key in ['timed_out', 'cancelled', 'automatic_retry'])
    for name, count in [('stdout', len(actual_raw)), ('stderr', 0)]:
        assert terminal['log_bytes'][name] == {'seen': count, 'stored': count}
        assert terminal['log_errors'][name] is None and terminal['log_truncated'][name] is False and terminal['log_synced'][name] is True
    assert actual['ok'] is True and actual['signature_verified'] is True and actual['errors'] == []
    assert actual['actual_uid'] == actual['actual_euid'] == 1000 and actual['root_execution'] is False
    assert actual['held_files'] == {'acquired': 13, 'closed': 13, 'errors': []}
    assert actual['original_descriptor_identities_restored'] is True and actual['all_held_files_full_identity_and_hash_unchanged'] is True
    apk_pin, apk_identity = constant(old, 'APK_PIN'), constant(old, 'APK_IDENTITY')
    assert actual['candidate']['sha256'] == apk_pin['sha256'] and actual['candidate']['identity'] == apk_identity
    bindings = constant(old, 'TOOL_BINDINGS')
    current_names = {row['name']: row for row in actual['held_input_bindings']}
    assert set(current_names) == set(bindings) | {'complete_s36_APK'}
    for name, row in bindings.items():
        assert current_names[name]['identity'] == {key: str(value) for key, value in row['observed']['file'].items()}
        assert current_names[name]['sha256'] == row['pin']['sha256'] and current_names[name]['bytes'] == row['pin']['bytes']
    signature_stdout = actual['commands'][0]['stdout_original_utf8']
    assert "Verified using v1 scheme (JAR signing): true\n" in signature_stdout
    assert "Verified using v2 scheme (APK Signature Scheme v2): true\n" in signature_stdout
    installed = next(row for row in batch['apps'] if row['package'] == 'com.szzc')
    assert len(installed['apks']) == 1
    installed_apk = installed['apks'][0]
    assert actual['signer_certificate_sha256'] == installed['PM_certificate_sha256']
    signature_reference = {
        'kind': 'prior actual S38 signature success for the exact same held candidate; not rerun in S39',
        'job_id': terminal['job_id'], 'result_bytes': len(actual_raw), 'result_sha256': sha(actual_raw),
        'terminal_bytes': len(terminal_raw), 'terminal_sha256': sha(terminal_raw),
        'signature_stdout': actual['commands'][0]['stdout'],
        'signature_stderr': actual['commands'][0]['stderr'],
        'candidate_sha256': apk_pin['sha256'], 'candidate_identity': apk_identity,
        'signer_certificate_sha256': actual['signer_certificate_sha256'],
        'v1_verified': True, 'v2_verified': True, 'original_warning_rows_removed': False,
        'original_all_warning_bytes_preserved_in_S38_stdout': True,
    }
    historical = {'kind': 'saved successful batch04 manifest/signature observation only; never a fresh current claim',
        'artifact_bytes': len(batch_raw), 'artifact_sha256': sha(batch_raw), 'observed_utc': batch['ended_utc'],
        'package': 'com.szzc', 'bytes': installed_apk['bytes'], 'sha256': installed_apk['sha256'],
        'manifest': installed_apk['manifest'], 'PM_version_code': installed['PM_version_code'],
        'signer_certificate_sha256': installed['PM_certificate_sha256'],
        'permission_tag_names': [{'tag': row['tag'], 'name': row['name']} for row in installed_apk['declared_permissions']['entries']],
        'full_original_permission_attributes_retained_in_batch04': True, 'current_runtime_observed': False}
    prefix = old.decode().split('\ndef need(', 1)[0]
    prefix = prefix.replace('Observe one downloaded APK signature as the existing ordinary tool owner.',
                            'Observe one exact candidate APK manifest and permission dump as its ordinary tool owner.')
    prefix = prefix.replace('/home/alex/work/pocket4-szzc-operator-signature-20261106-s38-r2',
                            '/home/alex/work/pocket4-szzc-operator-manifest-20261106-s39')
    source = prefix + '\nSIGNATURE_REFERENCE = ' + repr(signature_reference)
    source += '\nHISTORICAL_INSTALLED = ' + repr(historical) + '\n\n'
    inherited_names = ['need', 'ident', 'digest_fd', 'census', 'now', 'run_tool', 'hold_exact', 'recheck_exact']
    source += ''.join(definition(old, name) for name in inherited_names)
    source += definition(runner, 'badging_manifest')
    source += (HERE / 'body.py').read_text()
    raw = source.encode()
    compile(raw, 'observe_manifest_as_owner.py', 'exec')
    for name in inherited_names:
        assert definition(raw, name) == definition(old, name)
    assert definition(raw, 'badging_manifest') == definition(runner, 'badging_manifest')
    assert definition(raw, 'run_tool') == definition(runner, 'run_tool')
    request = {'host': 'pocket4', 'executable': '/usr/bin/python3',
        'args': ['-I', '-B', '-c', source, '--observe-candidate-manifest-as-existing-owner-once'],
        'idempotency_key': 'pocket4-szzc-operator-manifest-s39-20261106',
        'timeout_seconds': 210, 'memory_max_bytes': 536870912, 'cpu_quota_percent': 100, 'nice': 10}
    encoded = (json.dumps(request, sort_keys=True, indent=2) + '\n').encode()
    once('observe_manifest_as_owner.py', raw)
    once('process-request.json', encoded)
    once('against-actual-S38.diff', ''.join(difflib.unified_diff(old.decode().splitlines(True), source.splitlines(True),
        fromfile='S38_actual/observe_signature_as_owner.py', tofile='S39_candidate/observe_manifest_as_owner.py')).encode())
    pins = {'schema': 'pocket4-szzc-operator-manifest-source-pins-v1', 'state': 'PREPARED_NOT_SUBMITTED',
        'source_bytes': len(raw), 'source_sha256': sha(raw), 'request_bytes': len(encoded), 'request_sha256': sha(encoded),
        'parent_actual_source_bytes': len(old), 'parent_actual_source_sha256': sha(old),
        'actual_S38_result_bytes': len(actual_raw), 'actual_S38_result_sha256': sha(actual_raw),
        'actual_S38_terminal_bytes': len(terminal_raw), 'actual_S38_terminal_sha256': sha(terminal_raw),
        'copied_S38_function_bodies_unchanged': inherited_names,
        'copied_faff_function_bodies_unchanged': ['now', 'run_tool', 'badging_manifest'],
        'actual_uid_required': 1000, 'root_execution': False, 'Main_operations': 0,
        'tool_identity_policy': 'All12 original full stat and SHA pins, including real observed owner/mode, unchanged before/after; no wildcard.',
        'fixed_candidate': apk_pin, 'fixed_candidate_identity': apk_identity,
        'only_commands': [['/usr/lib/android-sdk/build-tools/debian/aapt', 'dump', 'badging', '<held candidate FD>'],
                          ['/usr/lib/android-sdk/build-tools/debian/aapt', 'dump', 'permissions', '<same held candidate FD>']],
        'per_spawn_deadline_checked': True, 'total_internal_deadline_seconds': 170,
        'all_stderr_and_stdout_saved_without_suppression': True,
        'nonempty_stderr_or_unrecognized_stdout_never_healthy': True,
        'effective_permissions_and_runtime_compatibility': 'UNKNOWN_NOT_QUERIED',
        'signature_verification_not_repeated_or_changed': True,
        'historical_installed_reference_is_fresh_current': False,
        'production_ready': False, 'cleanup_eligible': False, 'no_actual_execution': True}
    once('SOURCE_PINS.json', (json.dumps(pins, indent=2, sort_keys=True) + '\n').encode())
    once('historical-reference.json', (json.dumps(historical, indent=2, sort_keys=True) + '\n').encode())
    print(json.dumps({'source_bytes': len(raw), 'source_sha256': sha(raw),
                      'request_bytes': len(encoded), 'request_sha256': sha(encoded)}, sort_keys=True))


if __name__ == '__main__':
    main()
