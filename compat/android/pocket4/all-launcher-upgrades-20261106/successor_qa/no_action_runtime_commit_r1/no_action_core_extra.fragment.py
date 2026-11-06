def bundle_originals(raw, reader, core):
    need(len(raw) == BUNDLE['bytes'] and sha(raw) == BUNDLE['sha256'], 'EXACT_ACTUAL_SINGLE_FAILURE_BUNDLE')
    value = document(raw, maximum=2 * 1024 * 1024)
    need(raw == canonical(value) + b'\n' and set(value) == {
        'actual_job', 'approved_for_Git', 'contains_private_UI_evidence', 'files', 'flow',
        'full_original_bytes', 'original_stdout', 'original_terminal', 'schema', 'step', 'step_file_set'} and
        value['schema'] == 'pocket4-task878-failed-case-private-original-bytes-v1' and
        value['actual_job'] == FAILED_JOB and value['flow'] == FLOW and value['step'] == CASE_STEP and
        value['full_original_bytes'] is True and value['contains_private_UI_evidence'] is True and
        value['approved_for_Git'] is False and type(value['files']) is dict and len(value['files']) == 101,
        'CLOSED_ACTUAL_PRIVATE_ARCHIVE_NOT_NEW_UI_EVIDENCE')
    expected_result, lifetime = reader.validate_actual(core)
    for key, encoded_key, digest_key in (('original_stdout', 'actual_stdout_base64', 'actual_stdout_sha256'),
                                         ('original_terminal', 'terminal_base64', 'terminal_sha256')):
        row = value[key]
        need(type(row) is dict and set(row) == {'base64', 'bytes', 'sha256'}, 'EXACT_ORIGINAL_CONTROLLER_ARCHIVE_ROW')
        body = base64.b64decode(row['base64'], validate=True)
        need(body == base64.b64decode(reader.CONFIG[encoded_key], validate=True) and
             len(body) == row['bytes'] and sha(body) == row['sha256'] == reader.CONFIG[digest_key],
             'ARCHIVE_MATCHES_ORIGINAL_FAILED_CONTROLLER_AND_TERMINAL')
    originals, files = {}, {}
    total = 0
    for key, row in sorted(value['files'].items()):
        need(type(key) is str and type(row) is dict and
             set(row) == {'path', 'bytes', 'sha256', 'stat', 'base64'}, 'CLOSED_ORIGINAL_ARCHIVE_FILE_ROW')
        if key.startswith('source/'):
            label = key[7:]
            need(label in reader.CONFIG['sources'], 'ONLY_FROZEN_READER_SOURCE_MEMBERS')
            expected = reader.CONFIG['sources'][label]
        elif key.startswith('input/'):
            label = key[6:]
            need(label in ('case', 'request', 'scope', 'launch'), 'ONLY_FOUR_ORIGINAL_INPUTS')
            expected = reader.CONFIG[label]
        else:
            need(key.startswith('step/') and '/' not in key[5:] and '\\' not in key[5:] and
                 key[5:] in value['step_file_set'], 'ONE_ORIGINAL_FAILED_STEP_MEMBER')
            expected = {'path': FLOW + '/steps/' + CASE_STEP + '/' + key[5:],
                        'bytes': row['bytes'], 'sha256': row['sha256']}
        need(type(row['bytes']) is int and 0 <= row['bytes'] <= 2 * 1024 * 1024 and
             re.fullmatch('[0-9a-f]{64}', row['sha256']) and
             {k: row[k] for k in ('path', 'bytes', 'sha256')} == expected,
             'ORIGINAL_FILE_PATH_SIZE_AND_HASH_NOT_CALLER_SELECTED')
        body = base64.b64decode(row['base64'], validate=True)
        need(len(body) == row['bytes'] and sha(body) == row['sha256'], 'COMPLETE_ORIGINAL_FILE_BYTES')
        metadata = row['stat']
        need(type(metadata) is dict and set(metadata) == set(STAT_FIELDS) and
             all(type(x) is int and x >= 0 for x in metadata.values()) and
             stat.S_ISREG(metadata['st_mode']) and metadata['st_uid'] == 0 and metadata['st_nlink'] == 1 and
             metadata['st_size'] == len(body), 'ORIGINAL_ROOT_OWNED_REGULAR_FULL_IDENTITY')
        need(row['path'] not in originals, 'ONE_ARCHIVED_ORIGINAL_PATH')
        originals[row['path']] = (body, metadata)
        if key.startswith('step/'):
            files[key[5:]] = body
        total += len(body)
    need(total == 782840 and len(files) == 90 and len(originals) == 101 and
         sorted(files) == value['step_file_set'], 'ALL_101_ORIGINALS_AND_EXACT_90_STEP_FILES')
    return value, originals, files, expected_result, lifetime


def prior_installed_identity(raw, terminal_raw, base, core):
    need(len(raw) == PRIOR_STDOUT['bytes'] and sha(raw) == PRIOR_STDOUT['sha256'] and
         len(terminal_raw) == PRIOR_TERMINAL['bytes'] and sha(terminal_raw) == PRIOR_TERMINAL['sha256'],
         'EXACT_PREVIOUS_ACTUAL_INSPECT_IDENTITY_REFERENCE')
    terminal = document(terminal_raw)
    original_terminal(terminal, PRIOR_JOB, len(raw))
    outer = document(raw)
    need(outer['schema'] == 'pocket4-fixed-reusable-owned-ui-result-v1' and outer['ok'] is True and
         outer['errors'] == [] and outer['outcome_unknown'] is False and outer['kind'] == 'plan' and
         outer['step'] == 'inspect-after-partial-commit-01' and outer['flow'] == FLOW and outer['task'] == TASK and
         outer['source'] == UI_SOURCE and outer['all_owned_child_resources_retired_by_normal_pidfd_exit'] is True and
         outer['allows_new_mutation_without_original_Flow_checks'] is False and outer['automatic_retry'] is False and
         outer['original_UNKNOWN_rewritten'] is False and outer['reconciliation_published'] is False,
         'PREVIOUS_INSPECT_COMPLETED_IDENTITY_REFERENCE_NOT_LATER_OBSERVER')
    stderr = outer['child_stderr_original'].encode('utf-8')
    need(stderr == b'' and outer['child_stderr_bytes'] == 0 and outer['child_stderr_sha256'] == sha(b''),
         'PREVIOUS_NORMAL_CHILD_EMPTY_STDERR')
    base.require_owned_exit(outer['child_lifecycle'], stderr)
    need(outer['child_lifecycle']['child_pid'] == 2414622, 'EXACT_PREVIOUS_HELPER_IDENTITY_REFERENCE_CHILD')
    child_raw = outer['child_stdout_original'].encode('utf-8')
    need(len(child_raw) == outer['child_stdout_bytes'] == 10667 and
         sha(child_raw) == outer['child_stdout_sha256'] ==
         '4b0ad68e70e8383c49c11634ac3229b66d438f5a17a9820c1c1ceb3dcad9bc53',
         'PREVIOUS_ACTUAL_OWNED_CHILD_RAW_BYTES')
    child = document(child_raw)
    need(child['schema'] == 'pocket4-fixed-reusable-owned-ui-child-v1' and child['ok'] is True and
         child['errors'] == [] and child['declared_mutation'] is False and child['original_entry_invoked'] is True and
         child['original_returncode'] == 0 and child['outcome_unknown'] is False and child['source'] == UI_SOURCE and
         child['flow'] == FLOW and child['step'] == outer['step'] and child['task'] == TASK and
         child['original_namespace_authority_released'] is True and child['manual_library_close'] is False,
         'PREVIOUS_READONLY_SOURCE_AND_RETIREMENT_QUALIFIED')
    result_raw = child['original_stdout'].encode('utf-8')
    need(len(result_raw) == child['original_stdout_bytes'] == 5752 and
         sha(result_raw) == child['original_stdout_sha256'] ==
         '612ed6e8b154843990feec5ad647727a747e46faa540896c1534f561bd8ebd7d',
         'EXACT_PREVIOUS_ADAPTER_RESULT_IDENTITY_REFERENCE')
    result = document(result_raw)
    need(result['ok'] is True and result['error'] is None and result['secondary_errors'] == [] and
         result['action_attempted'] is False and result['outcome_unknown'] is False and
         result['installed_before'] == result['installed_after'] and result['owned_task'] == fixed_launch(result['owned_task'], core) and
         all(result[k] is True for k in ('restoration_qualified', 'after_state_attempted',
                                        'after_state_completed', 'post_state_matches_before')),
         'PREVIOUS_FULL_INSTALLED_HELPER_REFERENCE_NOT_A_NEW_OBSERVATION')
    build = core.fixed_build(result['build'])
    installed = core.installed_identity(result['installed_before'], build)
    return installed, result['ended_utc'], {'job_id': PRIOR_JOB, 'stdout': PRIOR_STDOUT,
        'terminal': PRIOR_TERMINAL, 'usage': 'previously_qualified_installed_helper_identity_only',
        'is_later_observer_for_failed_click': False, 'no_current_tree_or_action_authority': True}


def verify_failed_single_case(files, scope, launch, case, expected_result, installed, prior_ended,
                              *, core, qa, adapter, transport, tasks, runner):
    core.fixed_scope(scope); fixed_launch(launch, core)
    runner.validate_case(case, adapter, qa)
    need(sha(canonical(case) + b'\n') == CASE_SHA and case['name'] == 'beike-search-click-observe-01' and
         len(case['steps']) == 1 and case['steps'][0]['plan']['operation'] == 'click' and
         case['steps'][0]['post_inspection']['operation'] == 'inspect', 'ONE_ACTUAL_DECLARED_SEARCH_CLICK_ONLY')
    intent, result, binding = (document(files[name]) for name in ('intent.json', 'result.json', 'held-main-binding.json'))
    need(intent.get('operation') == 'owned-qa-case' and intent.get('mutation') is True and
         intent.get('scope') == scope and intent.get('automatic_retry') is False and
         all(intent.get(key) is None for key in ('unknown_step', 'observation_step', 'postcondition')) and
         set(intent['request']) == {'case', 'case_sha256', 'build'} and intent['request']['case'] == case and
         intent['request']['case_sha256'] == CASE_SHA, 'ORIGINAL_SINGLE_CASE_INTENT')
    need(result == expected_result and result['ok'] is False and result['outcome_unknown'] is True and
         result['action_attempted'] is True and result['original_action_outcomes_rewritten'] is False and
         result['production_ready'] is False and result['business_success_verified'] is False and
         result['errors'] == [{'code': 'EXACT_SUCCESSFUL_FINISH_REQUIRED', 'type': 'ProtocolError'}] and
         result['steps'] == [] and 'declared_scoped_sequence_completed' not in result,
         'ORIGINAL_FAILED_UNKNOWN_WITH_NO_COMPLETED_BUSINESS_POSTCONDITION')
    need(core.timestamp(prior_ended) < core.timestamp(intent['started_utc']),
         'PRIOR_HELPER_IDENTITY_REFERENCE_IS_EARLIER_NOT_A_LATER_OBSERVER')
    build = core.fixed_build(intent['request']['build']); binding_identity(binding, core, qa)
    core.installed_identity(installed, build)
    seq = OriginalSequence(files, core=core, qa=qa, transport=transport, tasks=tasks, binding=binding,
        launch=launch, build=build, installed=installed, parent_pid=2441902,
        started_utc=intent['started_utc'], ended_utc=result['ended_utc'])
    for name in ('intent.json', 'result.json', 'held-main-binding.json'):
        seq.raw(name)
    rejected = seq.sequence(case['steps'][0]['plan'], rejected=True)
    need(rejected['inspect']['wire_sha256'] == INSPECTION_WIRE_SHA and
         rejected['middle']['diagnostic']['wire_sha256'] == FAILED_WIRE_SHA,
         'EXACT_ORIGINAL_INSPECT_AND_REJECTING_ACTION_WIRES')
    for nonce in case['steps'][0]['post_inspection']['nonces'].values():
        need(not any(nonce + suffix in files for suffix in ('.request.json', '.assessment.json', '.failed-assessment.json')),
             'UNREQUESTED_POSTCONDITION_NONCES_MUST_REMAIN_ABSENT')
    need('case-00-operation.json' not in files and 'case-00-postcondition.json' not in files,
         'NO_MANUFACTURED_SUCCESSFUL_SEQUENCE_OR_POSTCONDITION')
    seq.complete(10, 13)
    return {'intent': intent, 'result': result, 'binding': binding, 'build': build, 'installed': installed,
            'launch': launch, 'case': case, 'rejected': rejected,
            'command_proofs': seq.command_proofs, 'phase_proofs': seq.phase_proofs,
            'all_files_sha256': {name: sha(body) for name, body in sorted(files.items())}}


def no_action_public_proof(failed, prior, *, reader, source_pin, core):
    rejection = failed['rejected']['failed_helper_retirement']
    need(rejection['helper_action_attempted'] is False and rejection['helper_outcome_unknown'] is False and
         rejection['original_success_parser_rejection_preserved'] is True,
         'ONLY_COMPLETE_PRE_DISPATCH_REJECTION_MAY_PRODUCE_NEW_PROOF')
    return {'schema': 'pocket4-owned-qa-rejected-before-dispatch-history-v1',
        'producer_source': source_pin, 'flow': FLOW, 'task': TASK, 'original_case': CASE_STEP,
        'original_controller_job': FAILED_JOB, 'original_stdout_sha256': reader.CONFIG['actual_stdout_sha256'],
        'original_terminal_sha256': reader.CONFIG['terminal_sha256'], 'private_original_bundle': BUNDLE,
        'case_sha256': CASE_SHA, 'scope_sha256': SCOPE_SHA, 'launch_scope_sha256': LAUNCH_SHA,
        'original_case_ok': False, 'original_case_outcome_unknown': True,
        'original_action_outcome': 'unknown_retained', 'original_results_rewritten': False,
        'helper_requested_click_dispatch_attempted': False, 'helper_claim_persistence_completed': True,
        'claim_deleted_or_reused': False, 'helper_rejection_and_state_retirement': rejection,
        'successful_inspection_state_check': failed['rejected']['successful_inspection_state_check'],
        'original_command_count': 10, 'original_transport_count': 13,
        'original_step_file_count': 90, 'archive_original_file_count': 101,
        'case_file_hashes': failed['all_files_sha256'], 'command_proofs': failed['command_proofs'],
        'phase_proofs': failed['phase_proofs'], 'prior_installed_helper_reference': prior,
        'independent_later_observer_available': False, 'business_postcondition_observed': False,
        'all_declared_postcondition_nonces_unrequested': True, 'app_autonomous_changes_excluded': False,
        'whole_instrumentation_effects_claimed_absent': False,
        'old_action_replayed': False, 'current_action_authority': False,
        'business_success_verified': False, 'production_ready': False, 'automatic_retry': False,
        'private_UI_raw_or_nodes_included': False, 'reconciliation_published': False,
        'original_Flow_reconcile_called': False, 'typed_reason': 'exact_helper_refusal_before_performAction'}
