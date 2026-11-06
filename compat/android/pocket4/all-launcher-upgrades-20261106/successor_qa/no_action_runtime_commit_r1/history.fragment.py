def actual_host_gate(base, host, partial):
    raw = base.pinned(HOST_STDOUT); terminal_raw = base.pinned(HOST_TERMINAL)
    partial.original_terminal(partial.document(terminal_raw), HOST_JOB, len(raw))
    value = partial.document(raw)
    need(value.get('schema') == 'pocket4-task878-failed-case-host-diagnostic-v1' and
         value.get('flow') == FLOW and value.get('step') == CASE_STEP and value.get('task') == TASK and
         value.get('historical_job') == FAILED_JOB and value.get('source_sha256') == READER_SOURCE['sha256'] and
         value.get('private_bundle') == HISTORY_BUNDLE and value.get('files') == 101 and
         value.get('step_file_count') == 90 and value.get('original_bytes') == 782840 and
         value.get('diagnosis_error') is None and
         all(value.get(k) is True for k in ('ok', 'collection_completed', 'diagnosis_completed',
             'original_file_bytes_and_stat_unchanged', 'whole_process_fd_identities_unchanged')) and
         value.get('process_fds_before') == value.get('process_fds_after') and
         all(value.get(k) is False for k in ('old_UNKNOWN_modified', 'original_case_success',
             'originals_modified', 'current_action_authority', 'reconciliation_published',
             'production_ready', 'automatic_retry', 'private_UI_content_in_stdout')) and
         all(type(value.get(k)) is int and value[k] == 0 for k in ('Main_commands', 'Main_locks_or_guards',
             'UI_actions', 'installs', 'namespace_entries', 'permission_changes', 'signals')),
         'ACTUAL_HOST_READER_COMPLETE_NOT_RECONCILIATION_OR_MAIN_AUTHORITY')
    diagnosis = value['diagnosis']
    need(diagnosis['all_recorded_commands_normal_zero_joined'] is True and
         diagnosis['all_recorded_transports_verified'] is True and
         len(diagnosis['commands']) == 10 and len(diagnosis['transports']) == 13 and
         diagnosis['failure_remains_unknown'] is True and diagnosis['new_action_authority'] is False and
         diagnosis['no_declared_postcondition_completed'] is True,
         'ACTUAL_DIAGNOSIS_IS_COMPLETE_AND_STILL_FAILED')
    return {'job_id': HOST_JOB, 'stdout': HOST_STDOUT, 'terminal': HOST_TERMINAL,
            'reader_source': READER_SOURCE, 'original_failed_job': FAILED_JOB,
            'private_original_bundle': HISTORY_BUNDLE, 'independent_later_observer_available': False}


def original_directory_identity(path):
    path = Path(path)
    need(str(path.resolve()) == str(path), 'ORIGINAL_FAILED_STEP_CANONICAL_PATH')
    value = os.stat(path, follow_symlinks=False)
    need(stat.S_ISDIR(value.st_mode) and value.st_uid == 0 and stat.S_IMODE(value.st_mode) == 0o700,
         'ORIGINAL_FAILED_STEP_ROOT_PRIVATE_DIRECTORY')
    return {key: getattr(value, key) for key in base_stat_fields()}


def history_context(base, host, partial, core):
    gate = actual_host_gate(base, host, partial)
    end = time.monotonic() + 180
    originals = {}; total = 0
    def tracked(pin):
        nonlocal total
        need(time.monotonic() < end, 'BOUNDED_NO_ACTION_HISTORY_READ')
        raw, metadata = read_exact(base, pin)
        if pin['path'] in originals:
            need(originals[pin['path']] == (raw, metadata), 'NO_HISTORY_INPUT_CHANGED_DURING_READ')
        else:
            originals[pin['path']] = (raw, metadata); total += len(raw)
            need(total <= 16 * 1024 * 1024, 'BOUNDED_NO_ACTION_HISTORY_TOTAL_BYTES')
        return raw
    def module(pin, name):
        raw = tracked(pin)
        value = types.ModuleType(name); value.__file__ = pin['path']
        exec(compile(raw, pin['path'], 'exec'), value.__dict__)
        return value
    reader = module(READER_SOURCE, 'unchanged_actual_single_click_failure_reader')
    need(reader.FLOW == FLOW and reader.STEP == CASE_STEP and reader.CONFIG['sources']['core'] == base.CORE,
         'FIXED_ACTUAL_READER_SOURCE_CONTRACT')
    bundle_raw = tracked(HISTORY_BUNDLE)
    bundle, archived, files, failed_result, old_lifetime = partial.bundle_originals(bundle_raw, reader, core)
    folder = FLOW + '/steps/' + CASE_STEP
    folder_identity = original_directory_identity(folder)
    need(sorted(os.listdir(folder)) == bundle['step_file_set'], 'EXACT_ORIGINAL_SINGLE_FAILED_STEP_FILE_SET')
    for path, (body, identity) in archived.items():
        again = tracked({'path': path, 'bytes': len(body), 'sha256': sha(body)})
        need(again == body and originals[path][1] == identity, 'ARCHIVED_ORIGINAL_BYTES_AND_FULL_STAT_STILL_IDENTICAL')
    qa = module(reader.CONFIG['sources']['qa'], 'unchanged_wire_contract_for_no_action')
    adapter = module(reader.CONFIG['sources']['adapter'], 'unchanged_adapter_shape_for_no_action')
    transport = module(reader.CONFIG['sources']['transport'], 'unchanged_original_held_transport')
    runner = module(reader.CONFIG['sources']['run_case'], 'unchanged_case_contract_for_no_action')
    tasks = module(TASK_SOURCE, 'unchanged_exact_task_parser')
    closure = {}
    for label, pin in SOURCE_MANIFESTS.items():
        manifest = partial.document(tracked(pin))
        need(type(manifest.get('files')) is dict and len(manifest['files']) == 13,
             'TWO_COMPLETE_ORIGINAL_THIRTEEN_FILE_SOURCE_CLOSURES')
        root = str(Path(pin['path']).parent)
        for relative, row in sorted(manifest['files'].items()):
            need(type(relative) is str and not relative.startswith('/') and '\\' not in relative and
                 all(p not in ('', '.', '..') for p in relative.split('/')) and
                 set(row) == {'bytes', 'sha256'}, 'EXACT_MANIFEST_SOURCE_MEMBER')
            member = {'path': root + '/' + relative, **row}; tracked(member)
            closure[label + '/' + relative] = member
    need(len(closure) == 26, 'ALL_TWENTY_SIX_ORIGINAL_SOURCE_FILES')
    java = tracked(ACTION_SOURCE)
    method = b'    void act(JSONObject request, JSONObject result) throws Exception {'
    need(java.count(method) == 1 and java.rstrip().endswith(b'}\n}'), 'EXACT_FINAL_ORIGINAL_ACT_METHOD')
    method_offset = java.index(method)
    act = java[method_offset:]
    guard = b'"INSPECTED_TREE_OR_WINDOW_CHANGED"'
    mark = b'timeBound(); actionAttempted = true;'
    click = b'current.target.performAction(AccessibilityNodeInfo.ACTION_CLICK)'
    need(act.count(guard) == act.count(mark) == act.count(click) == 1 and
         act.index(guard) < act.index(mark) < act.index(click),
         'FROZEN_COMPILED_SOURCE_REJECTION_PRECEDES_ATTEMPT_MARK_AND_CLICK_DISPATCH')
    prior_raw = tracked(PRIOR_STDOUT); prior_terminal_raw = tracked(PRIOR_TERMINAL)
    installed, prior_ended, prior = partial.prior_installed_identity(prior_raw, prior_terminal_raw, base, core)
    def original(label):
        row = bundle['files']['input/' + label]
        return partial.document(archived[row['path']][0])
    scope, launch, case = (original(label) for label in ('scope', 'launch', 'case'))
    failed = partial.verify_failed_single_case(files, scope, launch, case, failed_result, installed, prior_ended,
        core=core, qa=qa, adapter=adapter, transport=transport, tasks=tasks, runner=runner)
    proof = partial.no_action_public_proof(failed, prior, reader=reader, source_pin=PARTIAL_SOURCE, core=core)
    proof.update(original_source_closures=closure, original_failed_child_lifecycle=old_lifetime,
        action_source_rejection_before_dispatch={'source': ACTION_SOURCE,
            'act_method_byte_offset': method_offset,
            'guard_byte_offset': method_offset + act.index(guard),
            'attempt_mark_byte_offset': method_offset + act.index(mark),
            'performAction_byte_offset': method_offset + act.index(click),
            'source_is_bound_to_actual_qualified_build': True})
    proof_raw = canonical(proof) + b'\n'
    need(len(proof_raw) <= 131072, 'BOUNDED_PUBLIC_NO_ACTION_HISTORY_PROOF')
    for pin in (HOST_STDOUT, HOST_TERMINAL, PARTIAL_SOURCE, BASE, SELF, REQUEST):
        tracked(pin)
    need(original_directory_identity(folder) == folder_identity and
         sorted(os.listdir(folder)) == bundle['step_file_set'], 'ORIGINAL_FAILED_STEP_DIRECTORY_STILL_UNCHANGED')
    return {'gate': gate, 'proof_raw': proof_raw, 'proof': proof, 'originals': originals,
        'scope': scope, 'launch': launch, 'build': failed['build'], 'installed': installed,
        'foreground': failed['rejected']['foreground_scope_from_actual_request'],
        'case_binding': failed['binding'], 'historical_hashes': {'case': proof['case_file_hashes']},
        'failed_step_directory_identity': folder_identity, 'independent_later_observer_available': False}


def recheck_history(base, context, deadline):
    for path, (raw, metadata) in context['originals'].items():
        need(time.monotonic() < deadline, 'ALL_NO_ACTION_ORIGINALS_RECHECK_DEADLINE')
        again, current = base.read(path, maximum=3 * 1024 * 1024)
        need(again == raw and current == metadata, 'ORIGINAL_BYTES_OR_FULL_FILE_IDENTITY_CHANGED')
    folder = FLOW + '/steps/' + CASE_STEP
    need(sorted(os.listdir(folder)) == sorted(context['historical_hashes']['case']) and
         original_directory_identity(folder) == context['failed_step_directory_identity'],
         'ORIGINAL_FAILED_STEP_SET_OR_DIRECTORY_IDENTITY_CHANGED')
    no_publication_or_replay()
