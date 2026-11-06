def save(name, body):
    need(name in ('apksigner.stdout', 'apksigner.stderr', 'badging.stdout', 'badging.stderr',
                  'permissions.stdout', 'permissions.stderr', 'result.json'), 'CLOSED_EVIDENCE_NAME')
    with (ROOT / name).open('xb') as stream:
        stream.write(body); stream.flush(); os.fsync(stream.fileno())
    return {'path': str(ROOT / name), 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}


def qualify_vendor_signature(signature):
    need(signature['cryptographic_verification_performed'] is True and
         signature['verified'] is True and signature['API_minimum_override_used'] is False and
         signature['integrity_check_bypassed'] is False, 'NORMAL_FULL_SIGNATURE_REQUIRED')
    need(signature['signer_certificate_sha256'] == [SAVED_PM_SIGNER],
         'VALID_SIGNATURE_WITH_DIFFERENT_VENDOR_IS_NOT_AN_UPDATE')
    schemes = signature['schemes']
    need(schemes.get('v2 scheme (APK Signature Scheme v2)') is True or
         schemes.get('v3 scheme (APK Signature Scheme v3)') is True,
         'WHOLE_APK_V2_OR_V3_VERIFICATION_REQUIRED')


def observe_command(kind, argv, af, result, deadline):
    command = {'name': kind, 'purpose': 'read only the exact held complete S41 APK',
               'execution_uid': 1000}
    result['commands'].append(command)
    remaining = deadline - time.monotonic()
    command['remaining_budget_before_spawn_seconds'] = remaining
    command['minimum_budget_before_spawn_seconds'] = 5
    need(remaining > 5, 'VERIFICATION_DEADLINE_BEFORE_SPAWN:' + kind)
    outputs = run_tool(argv, (af,), command, deadline)
    for stream, raw in outputs.items():
        command[stream] = save(kind + '.' + stream, raw)
        if len(raw) <= 32768:
            try:
                command[stream + '_original_utf8'] = raw.decode('utf-8', 'strict')
            except UnicodeError as error:
                command[stream + '_decode_error'] = str(error)
        else:
            command[stream + '_original_inline_state'] = 'FULL_RAW_FILE_SAVED; exceeds_inline_32768B'
    need(normal_child_retired(command), 'COMPLETE_NORMAL_CHILD_RETIREMENT_REQUIRED:' + kind)
    return command, outputs


def main():
    need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 1000 and
         sys.argv[1:] == ['--verify-complete-zbj-as-existing-owner-once'],
         'EXACT_UNPRIVILEGED_EXISTING_TOOL_OWNER_ENTRY')
    need(ROOT.parent.resolve() == ROOT.parent, 'FIXED_PRIVATE_PARENT')
    os.umask(0o077); before = census(); ROOT.mkdir(mode=0o700)
    held, deadline = [], time.monotonic() + 170
    result = {'schema': 'pocket4-zbj-complete-operator-verification-v1', 'ok': False, 'errors': [],
        'actual_uid': os.getuid(), 'actual_euid': os.geteuid(), 'root_execution': False,
        'Android_commands': 0, 'Main_actions': 0, 'installs': 0, 'UI_actions': 0, 'permission_changes': 0,
        'automatic_retry': False, 'production_ready': False, 'cleanup_eligible': False,
        'root_private_dependency_files_opened': False, 'old_files_modified_or_deleted': False,
        'candidate_signature_verified': False, 'candidate_manifest_verified': False,
        'candidate_permission_dump_verified': False, 'vendor_signer_matches_archived_installed_APK': False,
        'candidate_qualified_for_fresh_install_review': False, 'installable_without_fresh_scope': False,
        'commands': [], 'tool_identity_basis': TOOL_EVIDENCE,
        'prior_actual_tool_execution_basis': TOOL_EXECUTION_EVIDENCE,
        'runner_source_basis': RUNNER_EVIDENCE, 'download_reference': DOWNLOAD_REFERENCE,
        'candidate_file_info_reference': FILE_INFO_REFERENCE,
        'latest_archived_installed_APK_reference': ARCHIVED_INSTALLED,
        'archived_installed_reference_is_fresh_at_this_verification': False,
        'signature_integrity_checks_changed': False, 'API_minimum_override_used': False,
        'effective_permission_grants': 'UNKNOWN_NOT_QUERIED',
        'candidate_runtime_compatibility': 'UNKNOWN_NOT_EXECUTED',
        'original_S39_failure_reclassified': False, 'earlier_download_failures_reclassified': False,
        'update_eligibility': 'PENDING_THIS_VERIFICATION_AND_FRESH_CURRENT_SCOPE_RUNTIME_COMPATIBILITY'}
    try:
        need(len(TOOL_BINDINGS) == 12 and set(TOOL_BINDINGS) == EXPECTED_TOOL_NAMES,
             'EXACT_PRIOR_TWELVE_TOOL_INPUTS')
        for name, row in TOOL_BINDINGS.items():
            hold_exact(name, row['pin'], row['observed']['file'], held, deadline)
        af = hold_exact('complete_s41_APK', APK_PIN, APK_IDENTITY, held, deadline)
        result['candidate'] = {key: value for key, value in held[-1].items() if key != 'fd'}
        recheck_exact(held, deadline)
        argv = [TOOL_BINDINGS['java']['pin']['resolved_path'], '-Xmx256m', '-jar',
                TOOL_BINDINGS['apksigner_jar']['pin']['resolved_path'], 'verify', '--verbose',
                '--print-certs', '/proc/self/fd/' + str(af)]
        command, outputs = observe_command('apksigner', argv, af, result, deadline)
        signature = parse_signature(outputs['stdout'], command)
        result['candidate_signature_observation'] = signature
        result['signature_stderr_nonempty'] = bool(outputs['stderr'])
        result['signature_warning_lines'] = [line for line in outputs['stdout'].decode('utf-8', 'strict').splitlines()
                                             if re.match(r'^\s*(?:WARNING|WARN)\b', line, re.I)]
        result['signature_warning_and_stderr_bytes_preserved'] = True
        qualify_vendor_signature(signature)
        result['candidate_signature_verified'] = True
        result['vendor_signer_matches_archived_installed_APK'] = True
        command_health = []
        for kind in ('badging', 'permissions'):
            recheck_exact(held, deadline)
            argv = [TOOL_BINDINGS['aapt']['pin']['resolved_path'], 'dump', kind, '/proc/self/fd/' + str(af)]
            command, outputs = observe_command(kind, argv, af, result, deadline)
            health = {'name': kind, 'normal_exit_zero': command['returncode'] == 0,
                      'parsed': False, 'healthy': False, 'parse_errors': []}
            try:
                health['diagnostics'] = feature_group_diagnostics(
                    aapt_diagnostics, kind, outputs['stdout'], outputs['stderr'])
                if kind == 'badging':
                    manifest = badging_manifest(outputs['stdout'])
                    manifest['native_abi_source'] = 'aapt_dump_badging_exact_complete_S41_candidate_APK'
                    result['candidate_manifest_observation'] = manifest
                    need(manifest['package'] == PACKAGE and manifest['split_name'] is None and
                         manifest['version_name'] == EXPECTED_VERSION_NAME and
                         manifest['long_version_code'] == EXPECTED_VERSION_CODE and
                         manifest['long_version_code'] > ARCHIVED_INSTALLED['manifest']['long_version_code'] and
                         all(isinstance(manifest[key], str) and manifest[key].isdigit() and int(manifest[key]) > 0
                             for key in ('min_sdk', 'target_sdk')), 'EXACT_CANDIDATE_PACKAGE_VERSION_SDK_FIELDS')
                    need(manifest['max_sdk'] is None or (manifest['max_sdk'].isdigit() and
                         int(manifest['max_sdk']) >= int(manifest['min_sdk'])), 'CANDIDATE_MAX_SDK_INCONSISTENT')
                    need(len(manifest['native_abis']) == len(set(manifest['native_abis'])),
                         'CANDIDATE_ABI_ROWS_DUPLICATED')
                    health['parsed'] = True
                else:
                    permissions = permissions_dump(outputs['stdout'])
                    result['candidate_declared_permissions_observation'] = permissions
                    need(permissions['all_names_decoded'] is True and not permissions['unparsed_lines'],
                         'COMPLETE_RECOGNIZED_DECLARED_PERMISSION_ROWS_REQUIRED')
                    health['parsed'] = True
                health['healthy'] = health['normal_exit_zero'] and health['parsed'] and health['diagnostics']['healthy_output_shape']
            except (RuntimeError, UnicodeError, ValueError, IndexError) as error:
                health['parse_errors'].append({'type': type(error).__name__, 'reason': str(error)[:512]})
            command_health.append(health)
        result['command_parser_health'] = command_health
        result['all_raw_command_observations_complete'] = len(result['commands']) == 3
        if 'candidate_manifest_observation' in result:
            candidate = result['candidate_manifest_observation']
            fields = ('package', 'version_code', 'version_code_major', 'long_version_code', 'version_name',
                      'min_sdk', 'target_sdk', 'max_sdk', 'native_abis')
            result['archived_installed_comparison'] = {
                'scope': 'latest saved batch12 actual APK audit; no new Android observation',
                'candidate_bytes_equal_archived_APK': APK_PIN['bytes'] == ARCHIVED_INSTALLED['bytes'],
                'candidate_sha256_equal_archived_APK': APK_PIN['sha256'] == ARCHIVED_INSTALLED['sha256'],
                'field_equality': {key: candidate.get(key) == ARCHIVED_INSTALLED['manifest'].get(key) for key in fields},
                'candidate_minus_archived_long_version_code': candidate['long_version_code'] - ARCHIVED_INSTALLED['manifest']['long_version_code'],
                'SDK_and_ABI_equality_does_not_prove_runtime_compatibility': True}
            if 'candidate_declared_permissions_observation' in result:
                entries = result['candidate_declared_permissions_observation']['entries']
                result['archived_installed_comparison']['permission_tag_and_name_sequence_equal'] = (
                    [{'tag': row['tag'], 'name': row['name']} for row in entries] == ARCHIVED_INSTALLED['permission_tag_names'])
                result['archived_installed_comparison']['permission_attribute_equivalence'] = 'NOT_CLAIMED_DIFFERENT_DUMP_FORMATS'
        recheck_exact(held, deadline)
        result['all_held_files_full_identity_and_hash_unchanged'] = True
        result['held_input_bindings'] = [{key: value for key, value in row.items() if key != 'fd'} for row in held]
        result['candidate_manifest_verified'] = command_health[0]['healthy']
        result['candidate_permission_dump_verified'] = command_health[1]['healthy']
        result['ok'] = all(row['healthy'] for row in command_health)
        if not result['ok']:
            result['errors'].append({'type': 'AaptObservationIncomplete',
                                    'reason': 'nonzero return, diagnostic bytes, unrecognized output or parse failure; raw evidence preserved'})
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__, 'reason': str(error)[:512]})
    finally:
        close_errors = []
        for row in reversed(held):
            try:
                os.close(row['fd'])
            except OSError as error:
                close_errors.append({'name': row['name'], 'errno': error.errno})
        result['held_files'] = {'acquired': len(held), 'closed': len(held) - len(close_errors), 'errors': close_errors}
        if close_errors:
            result['ok'] = False
    result['original_descriptor_identities_restored'] = census() == before
    result['ok'] = (result['ok'] and not result['errors'] and result['original_descriptor_identities_restored'] and
                    result['held_files'] == {'acquired': 13, 'closed': 13, 'errors': []} and
                    len(result['commands']) == 3 and all(normal_child_retired(x) for x in result['commands']) and
                    result['candidate_signature_verified'] and result['candidate_manifest_verified'] and
                    result['candidate_permission_dump_verified'] and result['vendor_signer_matches_archived_installed_APK'])
    result['candidate_qualified_for_fresh_install_review'] = result['ok']
    result['status'] = 'COMPLETE_CANDIDATE_VERIFIED_PENDING_FRESH_INSTALL_REVIEW' if result['ok'] else 'COMPLETE_CANDIDATE_VERIFICATION_FAILED'
    if result['ok']:
        result['update_eligibility'] = 'HOST_CANDIDATE_QUALIFIED; FRESH_CURRENT_SCOPE_AND_RUNTIME_COMPATIBILITY_STILL_REQUIRED'
    raw = (json.dumps(result, sort_keys=True) + '\n').encode()
    save('result.json', raw)
    need(census() == before, 'FINAL_OUTPUT_PUBLICATION_DESCRIPTOR_SET_CHANGED')
    print(raw.decode(), end='', flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
