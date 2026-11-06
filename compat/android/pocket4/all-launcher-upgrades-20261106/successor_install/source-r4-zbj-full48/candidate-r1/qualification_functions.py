def qualify_explicit48_scope(scope, runtime_epoch_sha256):
    """This fixed request covers the observed 48 identities, not a resolver claim."""
    need(type(scope) is dict and scope.get('schema') == 'pocket4-versioned-app-scope-v1'
         and scope.get('runtime_epoch_sha256') == runtime_epoch_sha256
         and type(scope.get('apps')) is dict
         and set(scope['apps']) == set(REVIEWED_EXPLICIT_PACKAGES)
         and len(scope['apps']) == 48 and ZBJ_PACKAGE in scope['apps'] and MEITUAN in scope['apps'],
         'CURRENT_EXACT_EXPLICIT48_APP_SCOPE_REQUIRED')


def require_unchanged_non_target_rows(before, after):
    """Retain the original content gate and additionally reject changed APK stat."""
    need(type(before) is dict and type(after) is dict and len(before) == len(after) == 47
         and ZBJ_PACKAGE not in before and ZBJ_PACKAGE not in after and before == after,
         'NON_TARGET_COMPLETE_APP_IDENTITIES_CHANGED')


def qualify_s43_observation(value, terminal):
    """Qualify one pinned actual S43 result; this pure function performs no I/O."""
    need(type(value) is dict and value.get('schema') == 'pocket4-zbj-complete-operator-verification-v1'
         and value.get('status') == 'COMPLETE_CANDIDATE_VERIFIED_PENDING_FRESH_INSTALL_REVIEW'
         and value.get('ok') is True and value.get('errors') == [], 'ACTUAL_SUCCESSFUL_S43_RESULT_REQUIRED')
    need(terminal == S43_ACTUAL_TERMINAL and terminal['job_id'] == S43_JOB_ID
         and terminal['state'] == 'succeeded' and type(terminal['exit_code']) is int
         and terminal['exit_code'] == 0, 'EXACT_ACTUAL_S43_TERMINAL_REQUIRED')
    need(all(terminal.get(k) is True for k in ('output_complete', 'output_durable', 'terminal_publication_confirmed'))
         and all(terminal.get(k) is False for k in ('automatic_retry', 'cancelled', 'timed_out')),
         'S43_DURABLE_COMPLETION_AND_NO_RETRY_REQUIRED')
    need(value.get('actual_uid') == value.get('actual_euid') == 1000
         and all(value.get(k) is False for k in ('root_execution', 'automatic_retry',
             'root_private_dependency_files_opened', 'old_files_modified_or_deleted',
             'signature_integrity_checks_changed', 'API_minimum_override_used',
             'installable_without_fresh_scope', 'production_ready', 'cleanup_eligible'))
         and all(type(value.get(k)) is int and value[k] == 0 for k in
             ('Android_commands', 'Main_actions', 'UI_actions', 'installs', 'permission_changes')),
         'S43_ORIGINAL_AUTHORITY_BOUNDARY_CHANGED')
    need(all(value.get(k) is True for k in ('candidate_signature_verified', 'candidate_manifest_verified',
             'candidate_permission_dump_verified', 'candidate_qualified_for_fresh_install_review',
             'vendor_signer_matches_archived_installed_APK', 'all_held_files_full_identity_and_hash_unchanged',
             'all_raw_command_observations_complete', 'original_descriptor_identities_restored'))
         and value.get('held_files') == {'acquired': 13, 'closed': 13, 'errors': []},
         'S43_VERIFICATION_OR_OWNED_RESOURCE_CLOSURE_INCOMPLETE')
    need(value.get('held_input_bindings') == S43_HELD_INPUT_BINDINGS,
         'S43_EXACT_TWELVE_TOOLS_AND_ONE_APK_BINDINGS_REQUIRED')
    candidate = value.get('candidate')
    need(candidate == S43_CANDIDATE, 'S43_EXACT_CANDIDATE_IDENTITY_REQUIRED')
    identity = candidate['identity']
    need(type(identity) is dict and set(identity) == set(STAT)
         and all(type(identity[k]) is str and re.fullmatch(r'0|[1-9][0-9]{0,19}', identity[k]) for k in STAT),
         'S43_LOSSLESS_DECIMAL_STAT_REQUIRED')
    converted = {k: int(identity[k]) for k in STAT}
    need(all(str(converted[k]) == identity[k] for k in STAT)
         and stat.S_ISREG(converted['st_mode']) and converted['st_nlink'] == 1
         and converted['st_size'] == candidate['bytes'], 'S43_EXACT_REGULAR_APK_STAT_REQUIRED')
    signature = value.get('candidate_signature_observation', {})
    need(all(signature.get(k) is True for k in ('cryptographic_verification_performed', 'verified'))
         and signature.get('API_minimum_override_used') is False
         and signature.get('integrity_check_bypassed') is False
         and signature.get('signer_certificate_sha256') == [ZBJ_VENDOR_SIGNER]
         and (signature.get('schemes', {}).get('v2 scheme (APK Signature Scheme v2)') is True
              or signature.get('schemes', {}).get('v3 scheme (APK Signature Scheme v3)') is True),
         'NORMAL_WHOLE_APK_SIGNATURE_FROM_SAME_VENDOR_REQUIRED')
    manifest = value.get('candidate_manifest_observation')
    need(manifest == S43_MANIFEST and manifest['package'] == ZBJ_PACKAGE
         and type(manifest['version_code']) is int and manifest['long_version_code'] == manifest['version_code']
         and manifest['version_code_major'] == 0 and manifest['split_name'] is None
         and 0 < int(manifest['min_sdk']) <= 37, 'EXACT_S43_PACKAGE_VERSION_AND_MANIFEST_REQUIRED')
    permissions = value.get('candidate_declared_permissions_observation', {})
    need(permissions.get('all_names_decoded') is True and permissions.get('unparsed_lines') == [],
         'S43_COMPLETE_DECLARED_PERMISSION_OBSERVATION_REQUIRED')
    health = value.get('command_parser_health', [])
    need(type(health) is list and [row.get('name') for row in health] == ['badging', 'permissions'],
         'S43_EXACT_TWO_MANIFEST_OBSERVATIONS_REQUIRED')
    for row in health:
        diagnostics = row.get('diagnostics', {})
        need(all(row.get(k) is True for k in ('normal_exit_zero', 'parsed', 'healthy'))
             and row.get('parse_errors') == [] and diagnostics.get('healthy_output_shape') is True
             and diagnostics.get('stderr_nonempty') is False
             and diagnostics.get('stdout_diagnostic_lines') == []
             and diagnostics.get('unrecognized_badging_lines') == []
             and diagnostics.get('stderr_and_diagnostic_rows_never_removed') is True,
             'S43_MANIFEST_DIAGNOSTIC_OR_UNKNOWN_ROW')
    commands = value.get('commands', [])
    need(type(commands) is list and [cmd.get('name') for cmd in commands] == ['apksigner', 'badging', 'permissions'],
         'EXACT_THREE_S43_COMMANDS_REQUIRED')
    for cmd in commands:
        need(type(cmd.get('returncode')) is int and cmd['returncode'] == 0
             and all(cmd.get(k) is True for k in ('spawned', 'joined', 'pipes_closed', 'output_capture_complete'))
             and all(cmd.get(k) is False for k in ('timed_out', 'own_group_kill_requested', 'automatic_retry'))
             and not any(cmd.get(k) for k in ('error', 'retirement_error', 'output_truncated'))
             and cmd.get('execution_uid') == 1000 and cmd.get('minimum_budget_before_spawn_seconds') == 5
             and type(cmd.get('remaining_budget_before_spawn_seconds')) in (float, int)
             and cmd['remaining_budget_before_spawn_seconds'] > 5
             and cmd.get('argv') == S43_COMMAND_ARGV[cmd['name']], 'S43_NORMAL_CHILD_OR_COMMAND_CHANGED')
        for stream in ('stdout', 'stderr'):
            need(cmd.get(stream) == S43_STREAM_PINS[cmd['name']][stream], 'S43_ORIGINAL_RAW_STREAM_PIN_CHANGED')
    from urllib.parse import urlsplit
    url = value.get('download_reference', {}).get('official_url')
    need(url == ZBJ_OFFICIAL_URL, 'EXACT_REVIEWED_ZBJ_PUBLIC_SOURCE_REQUIRED')
    parsed = urlsplit(url)
    need(parsed.scheme == 'https' and parsed.hostname in ALLOWED[ZBJ_PACKAGE]
         and parsed.username is None and parsed.password is None and parsed.fragment == ''
         and parsed.port in (None, 443), 'NORMAL_HTTPS_ZBJ_SOURCE_REQUIRED')
    return {'schema': 'pocket4-s43-qualified-native-install-input-v1',
            'original_receipt_schema': value['schema'], 'original_actual_result': S43_RESULT_REFERENCE,
            'original_actual_job_id': S43_JOB_ID, 'source_url': url,
            'manifest': dict(manifest), 'signer_certificate_sha256': list(signature['signer_certificate_sha256']),
            'apk': {'path': candidate['path'], 'bytes': candidate['bytes'], 'sha256': candidate['sha256'],
                    'stat': converted},
            'runtime_compatibility': 'NOT_PROVED_BY_HOST_VERIFICATION',
            'effective_permission_grants': 'UNKNOWN_NOT_QUERIED', 'production_ready': False}


def zbj_s43_verifier(core, request):
    """Read exact native S43 artifacts without forging a legacy verifier receipt."""
    need(request == REVIEWED_ZBJ_REQUEST, 'EXACT_REVIEWED_ZBJ_REQUEST_REQUIRED')
    ref = request['official_verifier']
    need(ref == S43_RESULT_REFERENCE, 'EXACT_REVIEWED_S43_RESULT_REFERENCE_REQUIRED')
    value = core.parse(core.pinned_record(ref, 131072))
    terminal = core.parse(core.pinned_record(request['verifier_terminal'], 65536))
    candidate = qualify_s43_observation(value, terminal)
    outputs = []
    for cmd in value['commands']:
        for stream in ('stdout', 'stderr'):
            pin = S43_STREAM_PINS[cmd['name']][stream]
            raw = core.pinned_record(pin, 1024*1024)
            need(raw.decode('utf-8', 'strict') == cmd[stream + '_original_utf8'],
                 'S43_RAW_STREAM_BYTES_DIFFER_FROM_ACTUAL_RECEIPT')
            outputs.append(dict(pin))
    return candidate, outputs
