def save(name, body):
    need(name in ('badging.stdout', 'badging.stderr', 'permissions.stdout',
                  'permissions.stderr', 'result.json'), 'CLOSED_EVIDENCE_NAME')
    with (ROOT / name).open('xb') as stream:
        stream.write(body); stream.flush(); os.fsync(stream.fileno())
    return {'path': str(ROOT / name), 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}


def quoted_attributes(value):
    attributes, at = {}, 0
    while at < len(value):
        match = re.match(r"\s*([A-Za-z][A-Za-z0-9_:-]*)='([^']*)'(?:\s+|$)", value[at:])
        need(match is not None and match[1] not in attributes, 'UNPARSED_OR_DUPLICATE_PERMISSION_ATTRIBUTE')
        attributes[match[1]] = match[2]
        at += match.end()
    return attributes


def permissions_dump(raw):
    """Decode recognized aapt permission rows without discarding duplicates or raw attributes."""
    text = raw.decode('utf-8', 'strict')
    lines = text.splitlines()
    need(len(lines) <= 4096, 'PERMISSIONS_LINE_COUNT_BOUND')
    packages, entries, unparsed = [], [], []
    tags = {'uses-permission', 'uses-permission-sdk-23', 'uses-permission-sdk-m',
            'permission', 'permission-group', 'permission-tree'}
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        if line.startswith('package: '):
            value = line[len('package: '):]
            if value.startswith("name='"):
                attributes = quoted_attributes(value)
                packages.append({'name': attributes.get('name'), 'attributes': attributes, 'raw': line})
            else:
                need(value and not any(character.isspace() for character in value) and
                     "'" not in value and '"' not in value, 'UNPARSED_PERMISSION_PACKAGE')
                packages.append({'name': value, 'attributes': {}, 'raw': line})
            continue
        tag, separator, value = line.partition(': ')
        if separator and tag in tags:
            entry = {'tag': tag, 'name': None, 'attributes': {}, 'raw_line': line, 'line_number': number}
            try:
                if value.startswith("name='"):
                    entry['attributes'] = quoted_attributes(value)
                    entry['name'] = entry['attributes'].get('name')
                else:
                    need(value and not any(character.isspace() for character in value) and
                         "'" not in value and '"' not in value, 'UNPARSED_BARE_PERMISSION_NAME')
                    entry['name'] = value
                    entry['name_form'] = 'bare_aapt_name'
                need(isinstance(entry['name'], str) and 0 < len(entry['name']) <= 1024,
                     'EMPTY_OR_UNBOUNDED_PERMISSION_NAME')
            except (RuntimeError, UnicodeError, ValueError) as error:
                entry['decode_error'] = {'type': type(error).__name__, 'reason': str(error)}
            entries.append(entry)
            need(len(entries) <= 2048, 'PERMISSION_ENTRY_BOUND')
        else:
            unparsed.append({'line_number': number, 'raw_line': line})
    need(len(packages) == 1 and packages[0]['name'] == 'com.szzc', 'UNIQUE_CANDIDATE_PERMISSION_PACKAGE')
    return {'package': packages[0]['name'], 'package_row': packages[0], 'entries': entries,
        'entry_count': len(entries), 'duplicates_preserved': True, 'unparsed_lines': unparsed,
        'all_names_decoded': all(row['name'] is not None and 'decode_error' not in row for row in entries),
        'declared_manifest_only': True, 'effective_permission_grants': 'UNKNOWN_NOT_QUERIED',
        'permission_coverage': 'aapt_dump_permissions_recognized_rows; raw output is authoritative'}


def aapt_diagnostics(kind, raw, stderr):
    """Nonempty stderr or an unrecognized stdout line prevents a healthy-parser claim."""
    text = raw.decode('utf-8', 'strict')
    diagnostic = []
    for number, line in enumerate(text.splitlines(), 1):
        if re.match(r'^\s*(?:[EWFDI]/|(?:warning|warn|error|fatal|exception|note)\b|ResourceType\b)', line, re.I):
            diagnostic.append({'line_number': number, 'raw_line': line})
    unexpected = []
    if kind == 'badging':
        allowed = {
            'package', 'sdkVersion', 'targetSdkVersion', 'maxSdkVersion', 'application',
            'application-debuggable', 'application-testOnly', 'launchable-activity', 'leanback-launchable-activity',
            'uses-permission', 'uses-permission-sdk-23', 'uses-permission-sdk-m', 'uses-implied-permission',
            'permission', 'permission-group', 'permission-tree', 'uses-feature', 'uses-feature-not-required',
            'uses-implied-feature', 'uses-gl-es', 'uses-library', 'uses-library-not-required',
            'uses-static-library', 'uses-sdk-library', 'provides-library', 'uses-package',
            'feature-group', 'uses-configuration', 'supports-screens', 'compatible-screens',
            'supports-any-density', 'supports-input', 'locales', 'densities', 'native-code',
            'alt-native-code', 'other-activities', 'other-receivers', 'other-services',
        }
        for number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            key = line.split(':', 1)[0]
            if key not in allowed and not re.fullmatch(r'application-(?:label|icon)(?:-[A-Za-z0-9_-]+)?', key):
                unexpected.append({'line_number': number, 'raw_line': line})
    return {'stderr_nonempty': bool(stderr), 'stdout_diagnostic_lines': diagnostic,
            'unrecognized_badging_lines': unexpected,
            'healthy_output_shape': not stderr and not diagnostic and not unexpected,
            'stderr_and_diagnostic_rows_never_removed': True}


def normal_child_retired(command):
    return (type(command.get('returncode')) is int and command.get('joined') is True and
        command.get('pipes_closed') is True and command.get('output_capture_complete') is True and
        command.get('timed_out') is False and command.get('own_group_kill_requested') is False and
        not command.get('error') and not command.get('retirement_error') and not command.get('output_truncated'))


def main():
    need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 1000 and
         sys.argv[1:] == ['--observe-candidate-manifest-as-existing-owner-once'],
         'EXACT_UNPRIVILEGED_EXISTING_TOOL_OWNER_ENTRY')
    need(ROOT.parent.resolve() == ROOT.parent, 'FIXED_PRIVATE_PARENT')
    os.umask(0o077); before = census(); ROOT.mkdir(mode=0o700)
    held, deadline = [], time.monotonic() + 170
    result = {'schema': 'pocket4-szzc-operator-manifest-observation-v1', 'ok': False, 'errors': [],
        'actual_uid': os.getuid(), 'actual_euid': os.geteuid(), 'root_execution': False,
        'Android_commands': 0, 'Main_actions': 0, 'installs': 0, 'UI_actions': 0, 'permission_changes': 0,
        'automatic_retry': False, 'production_ready': False, 'cleanup_eligible': False,
        'root_private_dependency_files_opened': False, 'old_files_modified_or_deleted': False,
        'current_manifest_verified': False, 'candidate_manifest_verified': False,
        'candidate_permission_dump_verified': False, 'newer_version_claimed': False,
        'signature_reverified_in_this_run': False, 'signature_integrity_checks_changed': False,
        'commands': [], 'tool_identity_basis': TOOL_EVIDENCE, 'runner_source_basis': RUNNER_EVIDENCE,
        'prior_actual_signature_reference': SIGNATURE_REFERENCE,
        'historical_installed_reference': HISTORICAL_INSTALLED,
        'historical_installed_reference_is_fresh_current': False,
        'effective_permission_grants': 'UNKNOWN_NOT_QUERIED',
        'candidate_runtime_compatibility': 'UNKNOWN_NOT_EXECUTED',
        'update_eligibility': 'NOT_ASSESSED_WITHOUT_CURRENT_SCOPE_AND_OFFICIAL_LATEST_PROOF'}
    try:
        need(len(TOOL_BINDINGS) == 12 and set(TOOL_BINDINGS) == EXPECTED_TOOL_NAMES,
             'EXACT_PRIOR_TWELVE_TOOL_INPUTS')
        for name, row in TOOL_BINDINGS.items():
            hold_exact(name, row['pin'], row['observed']['file'], held, deadline)
        af = hold_exact('complete_s36_APK', APK_PIN, APK_IDENTITY, held, deadline)
        result['candidate'] = {key: value for key, value in held[-1].items() if key != 'fd'}
        need(SIGNATURE_REFERENCE['candidate_sha256'] == APK_PIN['sha256'] and
             SIGNATURE_REFERENCE['candidate_identity'] == APK_IDENTITY,
             'CANDIDATE_DIFFERS_FROM_ACTUAL_S38_SIGNATURE_ARTIFACT')
        command_health = []
        for kind in ('badging', 'permissions'):
            recheck_exact(held, deadline)
            command = {'name': kind, 'purpose': 'read only the exact held candidate APK', 'execution_uid': 1000}
            result['commands'].append(command)
            remaining = deadline - time.monotonic()
            command['remaining_budget_before_spawn_seconds'] = remaining
            command['minimum_budget_before_spawn_seconds'] = 5
            need(remaining > 5, 'MANIFEST_DEADLINE_BEFORE_SPAWN:' + kind)
            argv = [TOOL_BINDINGS['aapt']['pin']['resolved_path'], 'dump', kind, '/proc/self/fd/' + str(af)]
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
            health = {'name': kind, 'normal_exit_zero': command['returncode'] == 0,
                      'parsed': False, 'healthy': False, 'parse_errors': []}
            try:
                health['diagnostics'] = aapt_diagnostics(kind, outputs['stdout'], outputs['stderr'])
                if kind == 'badging':
                    manifest = badging_manifest(outputs['stdout'])
                    manifest['native_abi_source'] = 'aapt_dump_badging_exact_S36_candidate_APK'
                    result['candidate_manifest_observation'] = manifest
                    need(manifest['package'] == 'com.szzc' and manifest['version_code'] >= 0 and
                         isinstance(manifest['version_name'], str) and bool(manifest['version_name']) and
                         all(isinstance(manifest[key], str) and manifest[key].isdigit()
                             for key in ('min_sdk', 'target_sdk')), 'COMPLETE_CANDIDATE_PACKAGE_VERSION_SDK_FIELDS')
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
        result['all_raw_command_observations_complete'] = len(result['commands']) == 2
        if 'candidate_manifest_observation' in result:
            candidate = result['candidate_manifest_observation']
            fields = ('package', 'version_code', 'version_code_major', 'long_version_code', 'version_name',
                      'min_sdk', 'target_sdk', 'max_sdk', 'native_abis')
            result['historical_comparison'] = {
                'scope': 'saved batch04 reference only; no fresh current Android observation',
                'candidate_bytes_equal_historical_bytes': APK_PIN['bytes'] == HISTORICAL_INSTALLED['bytes'],
                'candidate_sha256_equal_historical_sha256': APK_PIN['sha256'] == HISTORICAL_INSTALLED['sha256'],
                'field_equality': {key: candidate.get(key) == HISTORICAL_INSTALLED['manifest'].get(key) for key in fields},
                'candidate_minus_historical_long_version_code': candidate['long_version_code'] - HISTORICAL_INSTALLED['manifest']['long_version_code'],
                'comparison_is_not_current_upgrade_or_runtime_compatibility_qualification': True}
            if 'candidate_declared_permissions_observation' in result:
                entries = result['candidate_declared_permissions_observation']['entries']
                result['historical_comparison']['permission_tag_and_name_sequence_equal'] = (
                    [{'tag': row['tag'], 'name': row['name']} for row in entries] == HISTORICAL_INSTALLED['permission_tag_names'])
                result['historical_comparison']['permission_attribute_equivalence'] = 'NOT_CLAIMED_DIFFERENT_DUMP_FORMATS'
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
                    result['held_files'] == {'acquired': 13, 'closed': 13, 'errors': []})
    result['status'] = 'CANDIDATE_MANIFEST_AND_PERMISSION_DUMP_OBSERVED_NOT_INSTALLED' if result['ok'] else 'CANDIDATE_MANIFEST_OBSERVATION_FAILED'
    raw = (json.dumps(result, sort_keys=True) + '\n').encode()
    save('result.json', raw)
    need(census() == before, 'FINAL_OUTPUT_PUBLICATION_DESCRIPTOR_SET_CHANGED')
    print(raw.decode(), end='', flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
