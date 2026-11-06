#!/usr/bin/env python3
"""Seal the host-only S42 verifier from actual S41/S38 and batch12 originals."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re
import stat
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
BASE = HERE.parent.parent
INPUTS = {}


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(relative, size=None, digest=None):
    raw = (BASE / relative).read_bytes()
    need(size is None or len(raw) == size, 'input size differs: ' + relative)
    need(digest is None or sha(raw) == digest, 'input digest differs: ' + relative)
    INPUTS[relative] = {'path': relative, 'bytes': len(raw), 'sha256': sha(raw)}
    return raw


def load(relative, size=None, digest=None):
    return json.loads(read(relative, size, digest))


def definition(raw, name):
    node = next(x for x in ast.parse(raw).body if isinstance(x, ast.FunctionDef) and x.name == name)
    return ast.get_source_segment(raw.decode(), node) + '\n\n'


def constant(raw, name):
    node = next(x for x in ast.parse(raw).body if isinstance(x, ast.Assign) and
                any(isinstance(t, ast.Name) and t.id == name for t in x.targets))
    return ast.literal_eval(node.value)


def durable(raw, job_id, code, stdout_size):
    t = json.loads(raw)
    need(t['job_id'] == job_id and t['exit_code'] == code and
         t['state'] == ('succeeded' if code == 0 else 'failed'), 'actual terminal differs')
    need(all(t[k] is True for k in ('output_complete', 'output_durable', 'terminal_publication_confirmed')) and
         all(t[k] is False for k in ('timed_out', 'cancelled', 'automatic_retry')), 'terminal not durable or retired')
    for stream, count in (('stdout', stdout_size), ('stderr', 0)):
        need(t['log_bytes'][stream] == {'seen': count, 'stored': count} and
             t['log_errors'][stream] is None and t['log_truncated'][stream] is False and
             t['log_synced'][stream] is True, 'original command log incomplete')
    return t


def main():
    s38rel = 'official_source_scripts/s38_szzc_operator_signature/'
    s39rel = 'official_source_scripts/s39_szzc_operator_manifest/'
    s41rel = 'official_source_scripts/s41_zbj_finite_tail/candidate-r2/'
    s38 = read(s38rel + 'observe_signature_as_owner.py', 21026,
               '5a223fd2fc4baa5ce3e2b80615e400f11adac27d48365fa67de2b821c275abf3')
    s38raw = read(s38rel + 'actual/stdout.original.json', 25448,
                  '3ba6894d1d084f8d95b4ebfb342a3710990ce3b0aadf0e17710e9f608f8228a6')
    s38terminal = read(s38rel + 'actual/status-1.original.txt', 733,
                       '2974cb7304f993a0120ed8052cc6ff99837ad01e690d2c0f61f21c4d710ca904')
    durable(s38terminal, '1a1b25b668d-fc05-7dae', 0, len(s38raw))
    a38 = json.loads(s38raw)
    need(a38['ok'] is True and a38['errors'] == [] and a38['actual_uid'] == a38['actual_euid'] == 1000 and
         a38['held_files'] == {'acquired': 13, 'closed': 13, 'errors': []} and
         a38['original_descriptor_identities_restored'] is True and
         a38['all_held_files_full_identity_and_hash_unchanged'] is True, 'actual S38 tool qualification incomplete')
    bindings = constant(s38, 'TOOL_BINDINGS')
    actual_bindings = {x['name']: x for x in a38['held_input_bindings']}
    need(set(actual_bindings) == set(bindings) | {'complete_s36_APK'}, 'S38 tool scope changed')
    for name, row in bindings.items():
        need(actual_bindings[name]['identity'] == {k: str(v) for k, v in row['observed']['file'].items()} and
             actual_bindings[name]['sha256'] == row['pin']['sha256'] and
             actual_bindings[name]['bytes'] == row['pin']['bytes'], 'S38 full tool identity differs')
    p39 = load(s39rel + 'SOURCE_PINS.json')
    s39 = read(s39rel + 'observe_manifest_as_owner.py', p39['source_bytes'], p39['source_sha256'])
    start39 = load(s39rel + 'actual/start.original.txt')
    need(start39['job']['args'][3].encode() == s39, 'S39 actual source differs')
    raw39 = read(s39rel + 'actual/stdout.original.jsonl', 50145,
                 'a1ec03e52e30f066b1b01d0507adcdc6d204c5a3ebb1b4772c833e9fc62c26cf')
    durable(read(s39rel + 'actual/status-1.original.txt'), '1a1b26844a3-fc05-7ded', 1, len(raw39))
    runner = read('successor_audit_requests/reference/audit_successor_apks.py', 29242,
                  'faff199c1f6218b3c01d87e44be610d6fa211de396b5e8c862c188dec59d284a')
    extension = read(s39rel + 'local-reinterpretation-r1/diagnostics_extension.py', 2689,
                     '09cd2ee86445ce6cde377319a6c2ca92ca2ee57e7c088b6f97e04e2cd54d8ac4')
    extension_index = load(s39rel + 'local-reinterpretation-r1/index.json')
    # The frozen local reinterpretation has a separate index; preserve it as input.
    extension_pin = next(x for x in extension_index['files'] if x['path'] ==
                         'local-reinterpretation-r1/diagnostics_extension.py')
    need(extension_pin['bytes'] == len(extension) and extension_pin['sha256'] == sha(extension),
         'original extension index pin differs')
    need(b"result['new_remote_execution'] = False" in extension, 'exact pure extension metadata differs')

    downloadraw = read(s41rel + 'actual/stdout.original.jsonl', 90411,
                       '87ff7fb49fe8ce2570dbba9c777fd1944c7fcc8fbdf09dc49ecd4a61e7e9cea8')
    terminalraw = read(s41rel + 'actual/terminal.original.json', 733,
                       '8474c03fc5a09313f1d4dfd84a2d680753d6592681562c80f2953fccad5ebf6c')
    durable(terminalraw, '1a1b2aad530-fc05-7f38', 0, len(downloadraw))
    lines = [json.loads(x) for x in downloadraw.splitlines()]
    result, candidate = lines[-1], lines[-1]['candidates'][0]
    need(len(lines) == 40 and result['ok'] is True and result['errors'] == [] and
         result['staged'] == 1 and result['failed'] == 0 and
         result['original_descriptor_identities_restored'] is True and
         result['before_descriptor_identities'] == result['after_descriptor_identities'] and
         candidate['status'] == 'STAGED_PENDING_SIGNATURE_AND_IDENTITY_VERIFICATION' and
         candidate['segment_counts'] == {'COMPLETE': 38, 'FAILED': 0, 'SKIPPED_AFTER_OTHER_RANGE_FAILURE': 0} and
         candidate['owned_curl_processes'] == {'started': 38, 'joined': 38, 'outcome_unknown': False} and
         candidate['prior_file_descriptors'] == {'acquired': 46, 'closed': 46, 'errors': []} and
         candidate['all_prior_sources_unchanged'] is True, 'actual S41 complete download not settled')
    need(candidate['bytes'] == 166873622 and candidate['sha256'] ==
         '1822af13f666fea9814a7e571d50cc7def3aad72426d2e3eaa9101dcd6eaefa0' and
         candidate['package'] == 'com.zhubajie.client' and candidate['channel_version'] == '9.5.20',
         'actual complete candidate differs')
    for index, (progress, receipt) in enumerate(zip(lines[:38], candidate['segment_receipts'])):
        need(progress['segment'] == receipt['index'] == index and
             progress['status'] == receipt['status'] == 'COMPLETE' and
             progress['receipt'] == receipt['receipt'], 'range progress/final receipt mismatch')
    source41 = read(s41rel + 'continue_zbj_s41_once.py', 50714,
                    '9b79c319611295e10d00f141b072a79d39f828549d78f9300572345375fbb2e4')
    info = load(s41rel + 'actual/candidate-file_info.original.txt', 497,
                 '402326c44bdc61524cb5e3e9774e04cdfe903ba349c28e3a3b3523fa80a01dd0')
    need(info['path'] == candidate['local_path'] and info['size'] == candidate['bytes'] and
         info['sha256'] == candidate['sha256'] and info['metadata']['uid'] == info['metadata']['gid'] == 1000 and
         info['metadata']['link_count'] == 1 and info['mode'] == info['metadata']['mode'] == 0o600,
         'candidate file_info identity differs')
    fields = info['version'].split(':')
    need(len(fields) == 5 and all(x.isdecimal() for x in fields) and int(fields[2]) == info['size'],
         'candidate original version tuple malformed')
    apk_identity = {'st_dev': fields[0], 'st_ino': fields[1], 'st_size': fields[2],
                    'st_mtime_ns': fields[3], 'st_ctime_ns': fields[4],
                    'st_uid': str(info['metadata']['uid']), 'st_gid': str(info['metadata']['gid']),
                    'st_nlink': str(info['metadata']['link_count']),
                    'st_mode': str(stat.S_IFREG | info['mode'])}
    apk_pin = {'declared_path': info['path'], 'resolved_path': info['path'],
               'bytes': info['size'], 'sha256': info['sha256']}

    b12rel = 'successor_audit_requests/actual/batches-final-r1/batch-12/'
    batchraw = read(b12rel + 'artifact.original.json', 167063,
                    '29b47ba3639c5964a6b7ee0ac802706ed6dfe4a2aa87dcfcb7e2a20bb1233709')
    batch = json.loads(batchraw)
    b12stdout = read(b12rel + 'stdout.original.jsonl')
    durable(read(b12rel + 'terminal.original.json'), '1a1b2a90ea8-fc05-7f31', 0, len(b12stdout))
    b12outer = json.loads(b12stdout.splitlines()[-1])
    need(b12outer['ok'] is True and b12outer['errors'] == [] and
         b12outer['child_lifecycle']['pidfd_exit_observed'] is True and
         b12outer['child_lifecycle']['pidfd_closed'] is True, 'batch12 outer actual did not pass')
    installed = next(x for x in batch['apps'] if x['package'] == 'com.zhubajie.client')
    need(installed['all_APKs_signature_verified'] is True and
         installed['all_current_signers_equal_PM_records'] is True and
         installed['all_manifests_match_PM_identity'] is True and len(installed['apks']) == 1,
         'latest archived installed APK reference incomplete')
    installed_apk = installed['apks'][0]
    signer = '556246aaaf05f61c8bbb9587dfc0660e01f6c3c6813ec038d18684d3ab378bbe'
    need(installed['PM_certificate_sha256'] == installed_apk['signature']['signer_certificate_sha256'] == [signer] and
         installed_apk['manifest']['long_version_code'] == installed['PM_version_code'] == 369 and
         installed_apk['manifest']['version_name'] == '9.5.11', 'archived package/signer/version differs')
    archived = {'kind': 'latest saved successful batch12 actual APK audit; fresh current observation still required before install',
        'artifact': INPUTS[b12rel + 'artifact.original.json'], 'observed_utc': batch['ended_utc'],
        'job_id': '1a1b2a90ea8-fc05-7f31', 'package': installed['package'], 'uid': installed['uid'],
        'bytes': installed_apk['bytes'], 'sha256': installed_apk['sha256'],
        'manifest': installed_apk['manifest'], 'signer_certificate_sha256': [signer],
        'permission_tag_names': [{'tag': x['tag'], 'name': x['name']}
                                 for x in installed_apk['declared_permissions']['entries']]}
    download_reference = {'job_id': '1a1b2aad530-fc05-7f38',
        'stdout': INPUTS[s41rel + 'actual/stdout.original.jsonl'],
        'terminal': INPUTS[s41rel + 'actual/terminal.original.json'],
        'source': INPUTS[s41rel + 'continue_zbj_s41_once.py'],
        'actual_complete_APK': apk_pin, 'official_url': candidate['url'],
        'public_version_metadata': candidate['channel_version'],
        'computed_MD5': candidate['actual_md5'], 'metadata_MD5': candidate['metadata_md5'],
        'complete_segments': 38, 'owned_curl_joined': 38, 'old_source_FDs_closed': 46,
        'signature_and_manifest_not_previously_verified': True, 'all_prior_failures_preserved': True}
    # Retain the existing import/constants prefix; rebind only the new candidate.
    prefix = s38.decode().split('\ndef need(', 1)[0]
    replacements = {'ROOT': "Path('/home/alex/work/pocket4-zbj-operator-full-verification-20261106-s42')",
                    'SAVED_PM_SIGNER': repr(signer), 'APK_PIN': repr(apk_pin), 'APK_IDENTITY': repr(apk_identity)}
    nodes = ast.parse(prefix).body
    for name, replacement in replacements.items():
        node = next(x for x in nodes if isinstance(x, ast.Assign) and
                    any(isinstance(t, ast.Name) and t.id == name for t in x.targets))
        prefix = prefix.replace(ast.get_source_segment(s38.decode().split('\ndef need(', 1)[0], node),
                                name + ' = ' + replacement, 1)
    prefix = prefix.replace('Observe one downloaded APK signature as the existing ordinary tool owner.',
                            'Verify one complete S41 APK with the actual ordinary-owner S38 tools.')
    additions = {'PACKAGE': 'com.zhubajie.client', 'EXPECTED_VERSION_NAME': '9.5.20', 'EXPECTED_VERSION_CODE': 370,
                 'ARCHIVED_INSTALLED': archived, 'DOWNLOAD_REFERENCE': download_reference,
                 'FILE_INFO_REFERENCE': dict(INPUTS[s41rel + 'actual/candidate-file_info.original.txt'],
                    original_version=info['version'], regular_file_type_required_on_actual_FD=True,
                    file_info_mode_is_permission_bits_not_independent_file_type_observation=True),
                 'TOOL_EXECUTION_EVIDENCE': {'actual_result': INPUTS[s38rel + 'actual/stdout.original.json'],
                    'actual_terminal': INPUTS[s38rel + 'actual/status-1.original.txt'],
                    'same_12_tool_complete_identities_rechecked_before_after': True}}
    source = prefix + '\n' + ''.join(name + ' = ' + repr(value) + '\n' for name, value in additions.items()) + '\n'
    same38 = ['need', 'ident', 'digest_fd', 'census', 'now', 'run_tool', 'hold_exact', 'recheck_exact']
    source += ''.join(definition(s38, name) for name in same38)
    source += ''.join(definition(runner, name) for name in ['badging_manifest', 'parse_signature'])
    source += definition(s39, 'quoted_attributes')
    permissions = definition(s39, 'permissions_dump')
    need(permissions.count("'com.szzc'") == 1, 'permission parser package literal differs')
    source += permissions.replace("'com.szzc'", 'PACKAGE')
    source += definition(s39, 'aapt_diagnostics') + definition(s39, 'normal_child_retired')
    pure_extension = definition(extension, 'feature_group_diagnostics')
    source += pure_extension.replace("result['new_remote_execution'] = False",
                                     "result['parser_itself_executes_no_commands'] = True")
    body = read('official_source_scripts/s42_zbj_operator_verification/body.py')
    source += body.decode()
    raw = source.encode()
    compile(raw, 'verify_complete_zbj_as_owner.py', 'exec')
    for name in same38:
        need(definition(raw, name) == definition(s38, name), 'changed inherited S38 function: ' + name)
    for name in ['badging_manifest', 'parse_signature']:
        need(definition(raw, name) == definition(runner, name), 'changed faff parser: ' + name)
    for name in ['quoted_attributes', 'aapt_diagnostics', 'normal_child_retired']:
        need(definition(raw, name) == definition(s39, name), 'changed S39 function: ' + name)
    need(definition(raw, 'permissions_dump') == permissions.replace("'com.szzc'", 'PACKAGE'),
         'permission parser changed beyond exact package constant')
    need(definition(raw, 'feature_group_diagnostics') == pure_extension.replace(
        "result['new_remote_execution'] = False", "result['parser_itself_executes_no_commands'] = True"),
         'feature-group logic changed beyond execution metadata label')

    # Pure controls only. Do not import or execute the top-level remote worker.
    pure = {'need': need, 're': re, 'SAVED_PM_SIGNER': signer}
    for name in ('aapt_diagnostics', 'feature_group_diagnostics', 'parse_signature', 'qualify_vendor_signature'):
        exec(compile(definition(raw, name), '<pure-local-control>', 'exec'), pure, pure)
    original_badging = read(s39rel + 'actual/badging.stdout.original.txt')
    original_stderr = read(s39rel + 'actual/badging.stderr.original.txt')
    normal = pure['feature_group_diagnostics'](pure['aapt_diagnostics'], 'badging', original_badging, original_stderr)
    need(normal['healthy_output_shape'] is True, 'actual observed feature-group form should decode')
    unknown = pure['feature_group_diagnostics'](pure['aapt_diagnostics'], 'badging',
                                               original_badging + b'UNKNOWN_UNRECOGNIZED_ROW\n', original_stderr)
    need(unknown['healthy_output_shape'] is False and unknown['unrecognized_badging_lines'],
         'unknown stdout must not become healthy')
    wrong = pure['parse_signature'](a38['commands'][0]['stdout_original_utf8'].encode(), a38['commands'][0])
    need(wrong['verified'] is True, 'wrong-vendor control must be a cryptographically valid actual APK')
    try:
        pure['qualify_vendor_signature'](wrong)
    except RuntimeError as error:
        need(str(error) == 'VALID_SIGNATURE_WITH_DIFFERENT_VENDOR_IS_NOT_AN_UPDATE', 'wrong signature gate')
    else:
        raise RuntimeError('valid wrong vendor signer incorrectly accepted')
    v1only = dict(installed_apk['signature'], schemes={'v1 scheme (JAR signing)': True})
    try:
        pure['qualify_vendor_signature'](v1only)
    except RuntimeError as error:
        need(str(error) == 'WHOLE_APK_V2_OR_V3_VERIFICATION_REQUIRED', 'wrong whole-APK gate')
    else:
        raise RuntimeError('v1-only evidence incorrectly accepted')
    calls = []
    deadline_scope = {'need': need, 'time': SimpleNamespace(monotonic=lambda: 10.0),
                      'run_tool': lambda *a: calls.append(a)}
    exec(compile(definition(raw, 'observe_command'), '<pure-budget-control>', 'exec'), deadline_scope)
    try:
        deadline_scope['observe_command']('apksigner', [], 9, {'commands': []}, 10.0)
    except RuntimeError as error:
        need(str(error) == 'VERIFICATION_DEADLINE_BEFORE_SPAWN:apksigner', 'wrong pre-spawn budget gate')
    else:
        raise RuntimeError('expired budget incorrectly admitted')
    need(calls == [], 'expired budget executed a child helper')
    controls = {'schema': 1, 'pure_local_controls_only': True, 'remote_jobs': 0, 'Main_commands': 0,
        'actual_S39_observed_feature_group_decodes': True, 'unknown_line_remains_failure': True,
        'actual_S38_crypto_valid_wrong_vendor_rejected': True, 'v1_only_signature_rejected': True,
        'expired_fresh_budget_zero_child_calls': True, 'original_S39_failure_reclassified': False,
        'candidate_actual_signature_or_manifest_verified': False}

    request = {'host': 'pocket4', 'executable': '/usr/bin/python3',
        'args': ['-I', '-B', '-c', source, '--verify-complete-zbj-as-existing-owner-once'],
        'idempotency_key': 'pocket4-zbj-operator-full-verification-s42-20261106',
        'timeout_seconds': 210, 'memory_max_bytes': 536870912, 'cpu_quota_percent': 100, 'nice': 10}
    plan = {'schema': 'pocket4-S42-full-verification-execution-plan-v1', 'state': 'PREPARED_NOT_SUBMITTED',
        'host_root': '/home/alex/work/pocket4-zbj-operator-full-verification-20261106-s42',
        'idempotency_key': request['idempotency_key'], 'actual_uid_required': 1000,
        'source': {'bytes': len(raw), 'sha256': sha(raw)}, 'candidate': apk_pin,
        'candidate_expected_full_identity': apk_identity, 'candidate_identity_original_version': info['version'],
        'source_only_no_actual_verification': True,
        'S38_functions_copied_unchanged': same38, 'faff_parsers_copied_unchanged': ['badging_manifest', 'parse_signature'],
        'S39_functions_copied_unchanged': ['quoted_attributes', 'aapt_diagnostics', 'normal_child_retired'],
        'S39_permissions_change': 'Only literal com.szzc becomes fixed PACKAGE com.zhubajie.client',
        'feature_group_extension_change': 'Logic unchanged; pure-parser execution label renamed to avoid asserting the new worker never executes tools.',
        'three_commands': ['normal apksigner verify --verbose --print-certs', 'legacy aapt dump badging', 'legacy aapt dump permissions'],
        'SDK_or_integrity_overrides': [], 'root_private_tools_or_files_opened': False,
        'all_stdout_stderr_retained': True, 'AAPT_nonempty_stderr_or_diagnostics_or_unknown_rows_fail_health': True,
        'signature_warning_rows_preserved': True, 'whole_APK_v2_or_v3_and_exact_vendor_required': True,
        'strict_source_and_candidate_stat_SHA_before_after': True, 'held_input_count': 13,
        'per_spawn_fresh_budget_checked': True, 'total_internal_deadline_seconds': 170,
        'fresh_current_install_scope_still_required': True, 'runtime_compatibility': 'UNKNOWN_NOT_EXECUTED',
        'Main_commands': 0, 'Android_commands': 0, 'installs': 0, 'permission_changes': 0,
        'old_failure_results_changed': False, 'production_ready': False, 'cleanup_eligible': False}
    def enc(value):
        return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + '\n').encode()
    outputs = {
        'verify_complete_zbj_as_owner.py': raw, 'process-request.json': enc(request),
        'execution-plan.json': enc(plan), 'local-controls.json': enc(controls),
        'archived-installed-reference.json': enc(archived), 'download-reference.json': enc(download_reference),
        'against-actual-S39.diff': ''.join(difflib.unified_diff(s39.decode().splitlines(True),
            source.splitlines(True), fromfile='S39_actual/observe_manifest_as_owner.py',
            tofile='S42_candidate/verify_complete_zbj_as_owner.py')).encode(),
    }
    manifest = {'schema': 'pocket4-S42-source-pins-v1', 'state': 'PREPARED_NOT_SUBMITTED',
        'files': [{'path': name, 'bytes': len(value), 'sha256': sha(value)} for name, value in outputs.items()],
        'inputs': sorted(INPUTS.values(), key=lambda x: x['path'])}
    for name in ('body.py', 'prepare_packet.py', 'DESIGN.json', 'S41-success-summary.json'):
        local = (HERE / name).read_bytes()
        manifest['files'].append({'path': name, 'bytes': len(local), 'sha256': sha(local)})
    outputs['SOURCE_PINS.json'] = enc(manifest)
    for name in outputs:
        need(not (HERE / name).exists(), 'never overwrite frozen output: ' + name)
    for name, value in outputs.items():
        with (HERE / name).open('xb') as stream:
            stream.write(value)
    print(json.dumps({'source_bytes': len(raw), 'source_sha256': sha(raw),
        'request_bytes': len(outputs['process-request.json']), 'request_sha256': sha(outputs['process-request.json']),
        'manifest_bytes': len(outputs['SOURCE_PINS.json']), 'manifest_sha256': sha(outputs['SOURCE_PINS.json']),
        'pure_controls': controls, 'remote_processes_started': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
