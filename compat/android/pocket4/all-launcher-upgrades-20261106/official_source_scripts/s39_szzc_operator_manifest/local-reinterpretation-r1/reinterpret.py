"""Interpret fixed existing S39 bytes locally; never rerun or relabel S39."""
import ast
import collections
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
S39 = HERE.parent


def need(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fixed(path, size, checksum):
    raw = path.read_bytes()
    need(len(raw) == size and sha(raw) == checksum, 'LOCAL_ORIGINAL_BYTES_CHANGED:' + str(path))
    return raw


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path.relative_to(S39)), 'bytes': len(raw), 'sha256': sha(raw)}


def write_new(name, document):
    with (HERE / name).open('xb') as stream:
        stream.write((json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode())


def main():
    original_source = fixed(S39 / 'observe_manifest_as_owner.py', 38755,
        '73e43862b4f0c6baa840550132901f75a91dcb5fbded25a929d3618e603664b4').decode()
    functions = {node.name: node for node in ast.parse(original_source).body if isinstance(node, ast.FunctionDef)}
    scope = {'need': need, 're': re}
    for name in ['badging_manifest', 'quoted_attributes', 'permissions_dump', 'aapt_diagnostics']:
        exec(compile(ast.Module(body=[functions[name]], type_ignores=[]), '<fixed-original-pure-function>', 'exec'), scope)
    extension_scope = {}
    extension = (HERE / 'diagnostics_extension.py').read_bytes()
    exec(compile(extension, str(HERE / 'diagnostics_extension.py'), 'exec'), extension_scope)
    diagnostic = lambda raw, stderr=b'': extension_scope['feature_group_diagnostics'](
        scope['aapt_diagnostics'], 'badging', raw, stderr)
    actual_raw = fixed(S39 / 'actual/stdout.original.jsonl', 50145,
        'a1ec03e52e30f066b1b01d0507adcdc6d204c5a3ebb1b4772c833e9fc62c26cf')
    actual = json.loads(actual_raw)
    badging = fixed(S39 / 'actual/badging.stdout.original.txt', 11898,
        '8432a270eeee39bdb6f03fc029677565e6870817852451bb9269ced9e160c29c')
    permissions = fixed(S39 / 'actual/permissions.stdout.original.txt', 2770,
        'e9733090c855465db324258cf9db17df515fbfb66b5ed2866174ef3779f19dcd')
    stderr = fixed(S39 / 'actual/badging.stderr.original.txt', 0, sha(b''))
    permission_stderr = fixed(S39 / 'actual/permissions.stderr.original.txt', 0, sha(b''))
    terminal = json.loads((S39 / 'actual/status-1.original.txt').read_bytes())
    need(terminal['job_id'] == '1a1b26844a3-fc05-7ded' and terminal['state'] == 'failed' and
         terminal['exit_code'] == 1 and terminal['output_complete'] is True and
         terminal['output_durable'] is True and terminal['timed_out'] is False and
         terminal['cancelled'] is False and terminal['automatic_retry'] is False, 'ORIGINAL_FAILED_JOB_REQUIRED')
    need(actual['ok'] is False and len(actual['commands']) == 2 and
         all(row['returncode'] == 0 and row['timed_out'] is False and row['joined'] is True and
             row['pipes_closed'] is True and row['output_capture_complete'] is True
             for row in actual['commands']) and
         actual['all_held_files_full_identity_and_hash_unchanged'] is True and
         actual['original_descriptor_identities_restored'] is True, 'ORIGINAL_ACTUAL_OBSERVATIONS_REQUIRED')
    for row, raw, error in [(actual['commands'][0], badging, stderr),
                            (actual['commands'][1], permissions, permission_stderr)]:
        need(row['stdout']['bytes'] == len(raw) and row['stdout']['sha256'] == sha(raw) and
             row['stdout_original_utf8'].encode() == raw and row['stderr_original_utf8'].encode() == error,
             'INLINE_AND_PAGED_COMMAND_ORIGINALS_DIFFER')
    old = scope['aapt_diagnostics']('badging', badging, stderr)
    new = diagnostic(badging, stderr)
    need([row['line_number'] for row in old['unrecognized_badging_lines']] == list(range(207, 228)),
         'EXACT_ORIGINAL_21_LINE_REJECTION_DIFFERED')
    need(new['healthy_output_shape'] is True and
         [row['line_number'] for row in new['recognized_feature_group_extension_rows']] == list(range(207, 228)),
         'EXACT_FEATURE_GROUP_EXTENSION_DID_NOT_PARSE_ALL_ROWS')
    manifest = scope['badging_manifest'](badging)
    permission_rows = scope['permissions_dump'](permissions)
    need(permission_rows['all_names_decoded'] is True and permission_rows['unparsed_lines'] == [] and
         permission_rows['entry_count'] == 45 and
         scope['aapt_diagnostics']('permissions', permissions, permission_stderr)['healthy_output_shape'] is True,
         'PERMISSION_PARSE_DIFFERED')
    controls = [{'name': 'actual_fixed_S39_bytes_interpreted', 'passed': True}]
    negatives = [
        ('three_space_indent_rejected', badging.replace(b'  uses-feature:', b'   uses-feature:', 1), b''),
        ('orphan_indented_feature_rejected', badging.replace(b"feature-group: label=''\n", b'', 1), b''),
        ('extra_feature_attribute_rejected', badging.replace(b"name='android.hardware.camera'\n", b"name='android.hardware.camera' unexpected='1'\n", 1), b''),
        ('unknown_tail_line_rejected', badging + b'future-unknown-token\n', b''),
        ('diagnostic_line_rejected', badging + b'  ERROR: resource parse failed\n', b''),
        ('nonempty_stderr_rejected', badging, b'warning: diagnostic preserved\n'),
    ]
    for name, raw, error in negatives:
        need(diagnostic(raw, error)['healthy_output_shape'] is False, name)
        controls.append({'name': name, 'passed': True, 'synthetic_negative_fixture': True})
    duplicates = collections.Counter(row['name'] for row in permission_rows['entries'])
    historical = actual['historical_installed_reference']
    derived = {'schema': 'pocket4-s39-local-exact-feature-group-reinterpretation-v1',
        'state': 'LOCAL_REINTERPRETATION_COMPLETE',
        'original_job_id': terminal['job_id'], 'original_job_state': 'failed', 'original_exit_code': 1,
        'original_failure_rewritten': False, 'remote_rerun': False, 'new_remote_commands': 0,
        'original_error': actual['errors'], 'original_diagnostics': old, 'new_diagnostics': new,
        'candidate_manifest_from_original_badging': manifest,
        'declared_permissions_from_original_dump': permission_rows,
        'permission_name_duplicates_preserved': {name: count for name, count in sorted(duplicates.items()) if count > 1},
        'historical_installed_reference': historical, 'historical_reference_is_fresh_current': False,
        'same_version_as_historical_reference': manifest['package'] == 'com.szzc' and
            manifest['version_code'] == 327 and manifest['version_name'] == '9.6.1',
        'newer_version_claimed': False, 'current_installed_identity_verified': False,
        'candidate_runtime_compatibility': 'UNKNOWN_NOT_RUN',
        'candidate_effective_grants': 'UNKNOWN_NOT_QUERIED',
        'prior_actual_signature_reference': actual['prior_actual_signature_reference'],
        'signature_reverified_in_local_reinterpretation': False,
        'install_eligible_under_latest_upgrade_task': False,
        'reason': 'Manifest shows the same 9.6.1/code327 as the historical installed reference; current identity, applicable latest version and actual operation remain unverified.',
        'Main_actions': 0, 'Android_commands': 0, 'installs': 0, 'permission_changes': 0,
        'production_ready': False, 'cleanup_eligible': False,
        'inputs': [pin(S39 / name) for name in ['observe_manifest_as_owner.py',
            'actual/stdout.original.jsonl', 'actual/status-1.original.txt', 'actual/badging.stdout.original.txt',
            'actual/badging.stderr.original.txt', 'actual/permissions.stdout.original.txt',
            'actual/permissions.stderr.original.txt']],
        'extension_source': pin(HERE / 'diagnostics_extension.py'),
        'scope': 'Exact bounded feature-group rows and one subsequent bare main marker; no blanket stripping, unknown-token allowance, stderr removal or execution-success reinterpretation.'}
    write_new('derived-result.json', derived)
    write_new('local-controls.json', {'schema': 1, 'state': 'PURE_LOCAL_PARSER_CONTROLS_PASS',
        'passed': len(controls), 'controls': controls, 'Android_actions': 0, 'host_commands': 0,
        'actual_original_job_remains_failed': True})
    write_new('index.json', {'schema': 1, 'files': [pin(HERE / name) for name in
        ['diagnostics_extension.py', 'reinterpret.py', 'derived-result.json', 'local-controls.json']],
        'original_files_modified': False, 'remote_execution': False})
    print(json.dumps({'state': derived['state'], 'manifest': manifest,
        'permissions': permission_rows['entry_count'], 'recognized_extension_rows': 21,
        'controls': len(controls), 'original_job_remains_failed': True}))


if __name__ == '__main__':
    main()
