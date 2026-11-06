def entry(mode):
    global SELF, REQUEST
    need(os.getuid() == os.geteuid() == 0 and len(sys.argv) == 10 and sys.argv[1] == mode and
         sys.argv[2] == '--source-sha256' and re.fullmatch('[0-9a-f]{64}', sys.argv[3]) and
         sys.argv[4] == '--source-bytes' and sys.argv[5].isdigit() and
         0 < int(sys.argv[5]) <= 131072 and sys.argv[6] == '--request-sha256' and
         re.fullmatch('[0-9a-f]{64}', sys.argv[7]) and sys.argv[8] == '--request-bytes' and
         sys.argv[9].isdigit() and 0 < int(sys.argv[9]) <= 16384, 'EXACT_NEW_RUNTIME_ONCE_ENTRY')
    need(str(Path(__file__).resolve()) == ROOT + '/runtime_stage_a_once.py', 'REAL_NEW_STAGE_A_SOURCE_LOCATION')
    SELF = {'path': str(Path(__file__).resolve()), 'bytes': int(sys.argv[5]), 'sha256': sys.argv[3]}
    REQUEST = {'path': ROOT + '/request.json', 'bytes': int(sys.argv[9]), 'sha256': sys.argv[7]}
    os.umask(0o077)
    base = load_base(); base.pinned(SELF)
    return base


def request_value(raw, partial):
    value = partial.document(raw)
    need(value == FIXED_REQUEST and raw == canonical(value) + b'\n',
         'CLOSED_STAGE_A_ONLY_REQUEST_NO_ARBITRARY_COMMAND_OR_COMMIT')
    return value


def actual_host_gate(base, host, partial):
    raw = base.pinned(HOST_STDOUT)
    terminal = partial.document(base.pinned(HOST_TERMINAL))
    host.original_terminal(terminal, HOST_JOB, len(raw))
    lines = raw.splitlines()
    need(len(lines) == 2 and raw.endswith(b'\n'), 'EXACT_ACTUAL_HOST_STAGE_AND_RESULT')
    stage, value = [partial.document(line) for line in lines]
    need(stage == HOST_STAGE, 'EXACT_ACTUAL_HOST_SOURCE_CLOSURE_STAGE')
    need(value.get('schema') == 'pocket4-task878-partial-case-host-verification-v1' and
         all(value.get(key) is True for key in ('ok', 'host_historical_verification_completed',
             'historical_case_remains_failed_unknown', 'original_bytes_and_stat_unchanged',
             'whole_process_fd_identities_unchanged',
             'acceptance_requires_original_stdout_and_authoritative_durable_terminal')) and
         value.get('proof') == HOST_PROOF and value.get('private_observer_archive') == OBSERVER_ARCHIVE and
         value.get('verified_case_commands') == 29 and value.get('verified_case_transports') == 38 and
         value.get('verified_observer_commands') == 9 and value.get('verified_observer_transports') == 12 and
         value.get('process_fds_before') == value.get('process_fds_after') and
         set(value['process_fds_before']) == {'0', '1', '2'} and
         all(type(value.get(key)) is int and value[key] == 0 for key in ('Main_commands',
             'Main_locks_or_guards', 'namespace_entries', 'UI_actions', 'instrumentation_calls',
             'installs', 'permission_changes', 'signals')) and
         all(value.get(key) is False for key in ('private_UI_raw_or_nodes_in_stdout',
             'reconciliation_published', 'current_action_authority', 'production_ready', 'automatic_retry')),
         'ACTUAL_COMPLETE_HOST_HISTORY_PROOF_NOT_CURRENT_AUTHORITY')
    return {'job_id': HOST_JOB, 'stdout': HOST_STDOUT, 'terminal': HOST_TERMINAL,
            'historical_proof': HOST_PROOF, 'private_observer_archive': OBSERVER_ARCHIVE}


def no_publication_or_replay():
    need(not os.path.lexists(Path(FLOW) / 'reconciliations' / (CASE_STEP + '.json')),
         'STAGE_A_CANNOT_ACCEPT_OR_CREATE_RECONCILIATION')
    need(not os.path.lexists(Path(FLOW) / 'cleanup-attempted.json'),
         'CURRENT_OWNED_TASK_CLEANUP_NOT_ALREADY_ATTEMPTED')


def read_exact(base, pin, maximum=3 * 1024 * 1024):
    raw, metadata = base.read(pin['path'], maximum=maximum)
    need(len(raw) == pin['bytes'] and sha(raw) == pin['sha256'], 'EXACT_HISTORICAL_FILE_PIN')
    return raw, metadata


def history_context(base, host, partial, core):
    gate = actual_host_gate(base, host, partial)
    proof, archive, originals = host.collect_and_verify(base, HOST_SOURCE)
    archive_raw = canonical(archive) + b'\n'
    actual_archive, archive_stat = read_exact(base, OBSERVER_ARCHIVE)
    need(archive_raw == actual_archive, 'COMPLETE_LATER_PRIVATE_ARCHIVE_STILL_EXACT')
    proof.update(complete_later_observer_private_archive=OBSERVER_ARCHIVE,
                 verifier_source=HOST_SOURCE, verifier_inputs=host.INPUTS_PIN)
    proof_raw = canonical(proof) + b'\n'
    actual_proof, proof_stat = read_exact(base, HOST_PROOF)
    need(proof_raw == actual_proof, 'REPARSED_HISTORY_MUST_EQUAL_REAL_HOST_PROOF_BYTES')
    originals[OBSERVER_ARCHIVE['path']] = (actual_archive, archive_stat)
    originals[HOST_PROOF['path']] = (actual_proof, proof_stat)
    for pin in (HOST_STDOUT, HOST_TERMINAL, HOST_SOURCE, PARTIAL_SOURCE, BASE, SELF, REQUEST):
        raw, metadata = read_exact(base, pin)
        originals[pin['path']] = (raw, metadata)
    def original(name):
        need(name in originals, 'ACTUAL_HOST_VERIFIER_MUST_HAVE_READ_REQUIRED_ORIGINAL')
        return partial.document(originals[name][0])
    failed = FLOW + '/steps/' + CASE_STEP + '/'
    later = FLOW + '/steps/' + OBSERVATION_STEP + '/'
    observation = original(later + 'result.json')
    case_intent = original(failed + 'intent.json')
    scope = original(FLOW + '/scope.json')
    launch = original(FLOW + '/launch-scope.json')
    core.fixed_scope(scope); partial.fixed_launch(launch, core)
    need(observation['foreground_before'] == observation['foreground_after'],
         'ACTUAL_LATER_OBSERVER_STABLE_FULL_FOREGROUND')
    return {'gate': gate, 'proof_raw': proof_raw, 'originals': originals,
            'scope': scope, 'launch': launch, 'build': case_intent['request']['build'],
            'installed': observation['installed_before'], 'foreground': observation['foreground_before'],
            'case_binding': original(failed + 'held-main-binding.json'),
            'observer_binding': original(later + 'held-main-binding.json'),
            'historical_hashes': {'case': proof['case_file_hashes'],
                                  'observer': proof['observation_file_hashes']}}


def recheck_history(base, context, deadline):
    for path, (raw, metadata) in context['originals'].items():
        need(time.monotonic() < deadline, 'ALL_HISTORICAL_ORIGINALS_RECHECK_DEADLINE')
        again, current = base.read(path, maximum=3 * 1024 * 1024)
        need(again == raw and current == metadata, 'ORIGINAL_BYTES_OR_FULL_FILE_IDENTITY_CHANGED')
    for kind, step in (('case', CASE_STEP), ('observer', OBSERVATION_STEP)):
        need(sorted(os.listdir(Path(FLOW) / 'steps' / step)) == sorted(context['historical_hashes'][kind]),
             'ORIGINAL_STEP_FILE_SET_CHANGED')
    no_publication_or_replay()


def qualified_current_build(adapter, manifest, builder, core, context):
    args = types.SimpleNamespace(build_receipt=Path(BUILD_PATH), build_receipt_sha256=core.BUILD_RECEIPT,
        source_manifest_sha256=core.HELPER_MANIFEST, apk_sha256=APK_SHA,
        signer_certificate_sha256=core.SIGNER_SHA)
    before = os.stat(BUILD_PATH, follow_symlinks=False)
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == before.st_gid == 1000 and
         stat.S_IMODE(before.st_mode) == 0o600 and
         f'{before.st_dev}:{before.st_ino}:{before.st_size}:{before.st_mtime_ns}:{before.st_ctime_ns}' == BUILD_FILE_VERSION and
         str(Path(BUILD_PATH).resolve()) == BUILD_PATH,
         'ACTUAL_UID1000_BUILD_IDENTITY_NOT_A_ROOT_OWNED_FICTION')
    proof = adapter.qualified_build(args, manifest, builder)
    after = os.stat(BUILD_PATH, follow_symlinks=False)
    need(all(getattr(before, key) == getattr(after, key) for key in base_stat_fields()) and
         proof == context['build'] and proof['APK']['bytes'] == 37008 and proof['APK']['sha256'] == APK_SHA,
         'UNCHANGED_ACTUAL_BUILD_AND_ORIGINAL_CASE_APK_PROOF')
    return proof, {key: getattr(before, key) for key in base_stat_fields()}


def base_stat_fields():
    return ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_rdev',
            'st_size', 'st_mtime_ns', 'st_ctime_ns')


def two_original_rounds(session, expected_installed, expected_task, expected_foreground):
    rounds = []
    for index in (1, 2):
        installed = session.installed()
        task = session.task()
        foreground = session.foreground()
        need(installed == expected_installed and task == expected_task and foreground == expected_foreground,
             'FRESH_ORIGINAL_HELPER_TASK_AND_FULL_FOREGROUND_MUST_MATCH_HISTORY')
        rounds.append({'round': index, 'installed': installed, 'task': task, 'foreground': foreground})
    need({key: value for key, value in rounds[0].items() if key != 'round'} ==
         {key: value for key, value in rounds[1].items() if key != 'round'},
         'TWO_ORIGINAL_READONLY_ROUNDS_DIFFER')
    return rounds


def verify_six_commands(base, flow, binding, partial, core, qa, context, ended):
    names = {'intent.json', 'held-main-binding.json'}
    names |= {'command-%03d%s' % (i, suffix) for i in range(1, 7)
              for suffix in ('.intent.json', '.result.json', '.stdout', '.stderr')}
    names |= {'transport-%03d.%s.json' % (i, suffix) for i in range(1, 9)
              for suffix in ('intent', 'command-result', 'verified-result')}
    need(len(names) == 50 and sorted(os.listdir(flow.step)) == sorted(names),
         'EXACT_SIX_RECORDED_AND_EIGHT_TRANSPORT_FILE_SET')
    files = {name: base.read(flow.step / name)[0] for name in sorted(names)}
    intent = partial.document(files['intent.json'])
    need(intent.get('operation') == OPERATION and intent.get('mutation') is False and
         intent.get('scope') == context['scope'] and intent.get('unknown_step') == CASE_STEP and
         intent.get('observation_step') == OBSERVATION_STEP and intent.get('postcondition') == partial.POSTCONDITION and
         intent.get('automatic_retry') is False and
         intent.get('request') == {'stage_a_only': FIXED_REQUEST, 'producer_source': SELF, 'request_pin': REQUEST},
         'EXPLICIT_NEW_READONLY_PRODUCER_NOT_OLD_UI_RECONCILE')
    need(partial.document(files['held-main-binding.json']) == binding.record,
         'REAL_CURRENT_HELD_BINDING_RECORD_PERSISTED')
    seq = partial.OriginalSequence(files, core=core, qa=qa, transport=binding.transport_module,
        tasks=flow.tasks, binding=binding.record, launch=context['launch'], build=context['build'],
        installed=context['installed'], parent_pid=os.getpid(), started_utc=intent['started_utc'], ended_utc=ended)
    seq.raw('intent.json'); seq.raw('held-main-binding.json')
    for _ in (1, 2):
        seq.packages(); seq.task(); seq.foreground()
    seq.complete(6, 8)
    need(flow.command_index == 6 and flow.action_attempted is False and
         flow._private_backend_transport is False and flow._android_mutation is False,
         'SIX_READONLY_COMMANDS_AND_NO_MUTATION_OR_INSTRUMENTATION')
    return {'recorded_command_count': 6, 'private_foreground_transport_count': 2,
            'transport_count': 8, 'command_proofs': seq.command_proofs,
            'all_commands_normal_joined': True, 'all_transports_post_guard_and_lease_release': True,
            'private_foreground_raw_saved': False,
            'evidence_sha256': {name: sha(raw) for name, raw in sorted(files.items())}}


def checked_lock(probe, fd, path):
    row = probe.descriptor(fd)
    named = os.stat(path, follow_symlinks=False)
    need(row['link'] == str(path) and row['descriptor_flags'] == 1 and
         row['status_flags'] & os.O_ACCMODE == os.O_RDWR and
         stat.S_ISREG(named.st_mode) and named.st_uid == 0 and named.st_nlink == 1 and
         row['fstat'] == {key: getattr(named, key) for key in base_stat_fields()},
         'EXACT_OWNED_ORIGINAL_LOCK_DESCRIPTOR_AND_PATH')
    return row


def final_descriptors(probe, support, frozen, library_fd, library, locks):
    current = probe.census()
    need(set(current) == set(frozen) | set(locks) and set(frozen).isdisjoint(locks) and len(locks) == 2,
         'ONLY_FROZEN_LIBRARY_AND_TWO_ORIGINAL_LOCKS_MAY_REMAIN')
    need(probe.same_descriptors(frozen, {key: current[key] for key in frozen}) and
         all(current[key] == expected for key, expected in locks.items()),
         'FINAL_DESCRIPTOR_IDENTITY_CHANGED_OR_UNKNOWN')
    need(support.stable_library(probe.library_binding(library_fd, current[str(library_fd)])) ==
         support.stable_library(library), 'EXACT_LIBRARY_RESOURCE_RETAINED_UNTIL_NORMAL_OWNER_EXIT')
    return current


def safe_failure(error, phase):
    text = str(error)
    return {'phase': phase, 'type': type(error).__name__,
            'code': text if re.fullmatch('[A-Z0-9_]{1,160}', text) else 'STAGE_A_STRICT_REJECTION'}


def child():
    base = entry('--child')
    need(sys.stdin.buffer.read(1) == b'R', 'PARENT_HELD_PIDFD_RELEASE_REQUIRED')
    result = {'schema': CHILD_SCHEMA, 'ok': False, 'errors': [], 'source': SELF, 'request': REQUEST,
        'flow': FLOW, 'task': TASK, 'step': STEP, 'operation': OPERATION,
        'original_case_ok': False, 'original_case_outcome_unknown': True,
        'original_results_rewritten': False, 'old_action_replayed': False,
        'Flow_reconcile_called': False, 'reconciliation_published': False, 'compatibility_envelope_written': False,
        'current_action_authority': False, 'UI_actions': 0, 'instrumentation_calls': 0,
        'installs': 0, 'permission_changes': 0, 'lifecycle_or_activation_actions': 0,
        'business_success_verified': False, 'production_ready': False, 'automatic_retry': False,
        'requires_parent_normal_pidfd_exit_and_durable_terminal': True}
    flow = recorder = None; closed = False; action_lock = None; phase = 'bootstrap'
    probe = support = frozen = library = None; library_fd = None; locks = {}
    deadline = time.monotonic() + 540
    try:
        support = base.load(base.SUPPORT, 'unchanged_explicit_library_bootstrap')
        probe = support.load_module(support.PROBE_SOURCE, 'unchanged_owned_child_probe')
        observed_runtime = support.probe_proof()
        _, frozen, library_fd, library = support.initialize_library(probe, observed_runtime)
        host = base.load(HOST_SOURCE, 'unchanged_actual_host_verifier')
        partial = base.load(PARTIAL_SOURCE, 'unchanged_actual_partial_case_verifier')
        core = base.load(base.CORE, 'unchanged_actual_r5_and_command_contract')
        request = request_value(base.pinned(REQUEST), partial)
        phase = 'historical_reverification'
        context = history_context(base, host, partial, core)
        no_publication_or_replay()
        need(not os.path.lexists(Path(FLOW) / 'steps' / STEP), 'NEW_STAGE_A_STEP_NO_REPLAY')
        ui = base.load(UI_SOURCE, 'unchanged_original_launch_gate_only')
        scope, selected = ui.launch_gate(base, core)
        need(scope == context['scope'] and selected == context['launch'], 'UNCHANGED_ACTUAL_NATIVE_OWNERSHIP')
        adapter = base.load(ui.ADAPTER, 'unchanged_original_adapter')
        manifest = adapter.own_source(core.HELPER_MANIFEST)
        helper_root = Path(ui.ADAPTER['path']).parent
        qa = adapter.load(helper_root / 'qa_contract.py', manifest['files']['qa_contract.py']['sha256'], 'unchanged_qa_scope')
        builder = adapter.load(helper_root / 'build_candidate.py', manifest['files']['build_candidate.py']['sha256'],
                               'unchanged_completed_build_validator')
        build, build_stat = qualified_current_build(adapter, manifest, builder, core, context)
        for name in ('case_binding', 'observer_binding'):
            partial.binding_identity(context[name], core, qa)
        core.installed_identity(context['installed'], build)
        qa.scope(context['foreground'])
        recorder = base.load(base.RECORDER, 'unchanged_original_recorder_flow')
        need(probe.same_descriptors(frozen, probe.census()), 'NO_PRE_MAIN_UNKNOWN_DESCRIPTOR')
        phase = 'original_flow_and_locks'
        fargs = types.SimpleNamespace(operation=OPERATION, adapter_manifest_sha256=core.RECORDER_MANIFEST,
            flow_dir=Path(FLOW), epoch_module=Path(RECORDER_ROOT) / 'references/framework_epoch.py',
            task_source=Path(RECORDER_ROOT) / 'references/task_scope_baseline.py', step=STEP,
            request={'stage_a_only': request, 'producer_source': SELF, 'request_pin': REQUEST},
            unknown_step=CASE_STEP, observation_step=OBSERVATION_STEP, postcondition=partial.POSTCONDITION)
        flow = recorder.Flow(fargs)
        locks[str(flow.lock)] = checked_lock(probe, flow.lock, Path(FLOW) / 'flow.lock')
        action_lock = recorder.lock_file(recorder.ACTION_LOCK)
        locks[str(action_lock)] = checked_lock(probe, action_lock, recorder.ACTION_LOCK)
        need(len(locks) == 2 and set(locks).isdisjoint(frozen), 'TWO_ORIGINAL_DISTINCT_NONBLOCKING_LOCKS')
        flow.begin(fargs, mutation=False)
        no_publication_or_replay()
        need(flow.scope == context['scope'], 'ORIGINAL_CURRENT_FLOW_SCOPE_UNCHANGED')
        for filename in ('baseline.json', 'baseline-qualification.json'):
            path = FLOW + '/' + filename
            context['originals'][path] = base.read(path)
        flow.source.verify_saved_baseline(flow.root)
        phase = 'fresh_held_binding'
        binding = flow.bind(); partial.binding_identity(binding.record, core, qa)
        comparisons = {name: core.compare_held_bindings(context[name], binding.record)
                       for name in ('case_binding', 'observer_binding')}
        phase = 'two_original_session_rounds'
        session = adapter.Session(flow, recorder, qa, build, HELPER_UID)
        rounds = two_original_rounds(session, context['installed'], context['launch'], context['foreground'])
        command_evidence = verify_six_commands(base, flow, binding, partial, core, qa, context, recorder.now())
        phase = 'final_current_and_historical_recheck'
        flow.contract.verify(); flow.guard(attempted=False)
        flow.source.verify_saved_baseline(flow.root)
        recheck_history(base, context, deadline)
        need(qualified_current_build(adapter, manifest, builder, core, context) == (build, build_stat),
             'ACTUAL_BUILD_REPLACED_DURING_CURRENT_OBSERVATION')
        adapter.own_source(core.HELPER_MANIFEST)
        ui.launch_gate(base, core)
        for pin in (SELF, REQUEST, BASE, UI_SOURCE, HOST_SOURCE, PARTIAL_SOURCE, base.RECORDER, base.CORE,
                    base.SUPPORT, support.PROBE_SOURCE):
            base.pinned(pin)
        support.pin_runtime_files(probe, observed_runtime)
        flow.guard(attempted=False)
        phase = 'release_main_authority'
        flow.close(); closed = True
        flow.source.runtime_and_app_guard(flow.current_guard)
        flow.epoch.require_unchanged(flow.activation['framework_epoch'], action_attempted=False)
        for fd, expected in locks.items():
            path = expected['link']
            need(checked_lock(probe, int(fd), path) == expected, 'ORIGINAL_LOCK_PATH_OR_IDENTITY_CHANGED')
        final = final_descriptors(probe, support, frozen, library_fd, library, locks)
        need(time.monotonic() < deadline, 'STAGE_A_TOTAL_DEADLINE')
        phase = 'write_nonauthorizing_candidate'
        candidate = {'schema': CANDIDATE_SCHEMA, 'created_utc': recorder.now(), 'source': SELF, 'request': REQUEST,
            'flow': FLOW, 'step': STEP, 'producer_operation': OPERATION,
            'original_case': CASE_STEP, 'later_observation': OBSERVATION_STEP,
            'historical_controller_and_proof': context['gate'],
            'scope_sha256': partial.SCOPE_SHA, 'framework_epoch_sha256': core.MAIN_EPOCH,
            'runtime_epoch_sha256': core.RUNTIME_EPOCH, 'app_scope_sha256': core.APP_SCOPE,
            'original_case_ok': False, 'original_case_outcome_unknown': True,
            'original_action_outcome': 'unknown_retained', 'original_results_rewritten': False,
            'old_action_replayed': False, 'Flow_reconcile_called': False,
            'current_installed_helper': rounds[0]['installed'], 'current_owned_task': rounds[0]['task'],
            'current_foreground': rounds[0]['foreground'], 'two_original_rounds_equal': True,
            'current_tree_or_node_reobserved': False,
            'original_foreground_predicate_and_full_scope_preserved': True,
            'build': build, 'actual_uid1000_build_file': build_stat,
            'historical_to_current_binding_comparisons': comparisons,
            'current_binding_sha256': command_evidence['evidence_sha256']['held-main-binding.json'],
            'runtime_commands': command_evidence, 'held_Main_authority_closed': True,
            'all_historical_bytes_and_full_stat_unchanged': True,
            'flow_and_action_locks_held_until_process_exit': True,
            'known_library_resource': {'path': library['path'], 'bytes': library['bytes'], 'sha256': library['sha256'],
                'manual_close': False, 'retirement_requires_normal_owned_child_exit': True},
            'unknown_descriptors_closed': 0, 'UI_actions': 0, 'instrumentation_calls': 0, 'permission_changes': 0,
            'installs': 0, 'lifecycle_or_activation_actions': 0,
            'reconciliation_published': False, 'compatibility_envelope_written': False,
            'current_action_authority': False, 'original_unknown_result_kept': True,
            'business_success_verified': False, 'production_ready': False, 'automatic_retry': False,
            'requires_parent_normal_pidfd_exit_and_durable_terminal': True,
            'stage_B_not_sealed_or_executed': True, 'private_UI_raw_or_nodes_included': False}
        copies = {'producer-source.py': base.pinned(SELF), 'producer-request.json': base.pinned(REQUEST),
                  'host-historical-proof.json': context['proof_raw'],
                  'host-controller.stdout.original.jsonl': base.pinned(HOST_STDOUT),
                  'host-controller.terminal.original.json': base.pinned(HOST_TERMINAL)}
        for name, raw in copies.items():
            recorder.write_new(flow.step / name, raw)
        raw = canonical(candidate) + b'\n'
        need(len(raw) <= 131072, 'BOUNDED_PUBLIC_RUNTIME_CANDIDATE')
        recorder.write_new(flow.step / 'runtime-candidate.json', raw)
        candidate_pin = {'path': str(flow.step / 'runtime-candidate.json'), 'bytes': len(raw), 'sha256': sha(raw)}
        need(base.pinned(candidate_pin) == raw, 'RUNTIME_CANDIDATE_FULL_READBACK')
        recheck_history(base, context, deadline)
        flow.source.runtime_and_app_guard(flow.current_guard)
        flow.epoch.require_unchanged(flow.activation['framework_epoch'], action_attempted=False)
        need(final_descriptors(probe, support, frozen, library_fd, library, locks) == final,
             'FINAL_RESOURCES_CHANGED_AFTER_NONAUTHORIZING_WRITE')
        result.update(ok=True, candidate=candidate_pin, runtime_commands=command_evidence,
            original_historical_proof=HOST_PROOF, current_binding_sha256=candidate['current_binding_sha256'],
            held_Main_authority_closed=True, original_foreground_predicate_preserved=True,
            all_historical_originals_unchanged=True, final_descriptors=final,
            normal_process_exit_required_for_locks_and_library=True, unknown_descriptors_closed=0,
            manual_library_close=False, private_UI_raw_or_nodes_in_stdout=False)
    except BaseException as error:
        result['errors'].append(safe_failure(error, phase))
    finally:
        if flow is not None and not closed:
            try:
                flow.close(); closed = True
            except BaseException as error:
                result['ok'] = False
                result['errors'].append(safe_failure(error, 'release_main_authority'))
        if probe is not None and frozen is not None:
            try:
                actual = probe.census()
                result['final_descriptors'] = actual
                need(closed or flow is None, 'MAIN_AUTHORITY_RELEASE_INCOMPLETE')
                if len(locks) == 2:
                    final_descriptors(probe, support, frozen, library_fd, library, locks)
                else:
                    expected = {**frozen, **locks}
                    need(set(actual) == set(expected) and probe.same_descriptors(expected, actual),
                         'FAILED_PRE_MAIN_OR_LOCK_ACQUISITION_LEFT_UNKNOWN_FD')
            except BaseException as error:
                result['ok'] = False
                result['errors'].append(safe_failure(error, 'final_descriptor_gate'))
        if recorder is not None and flow is not None and flow.step is not None:
            try:
                recorder.write_new(flow.step / 'result.json', {
                    'schema': 'pocket4-owned-qa-stage-a-step-result-v1', 'ok': result['ok'],
                    'action_attempted': False, 'outcome_unknown': False, 'errors': result['errors'],
                    'epoch_sha256': flow.scope['epoch_sha256'], 'ended_utc': recorder.now(),
                    'automatic_retry': False, 'business_success_verified': False, 'production_ready': False,
                    'original_case_ok': False, 'original_case_outcome_unknown': True,
                    'original_results_rewritten': False, 'reconciliation_published': False,
                    'current_action_authority': False, 'requires_parent_normal_pidfd_exit_and_durable_terminal': True,
                    'candidate': result.get('candidate')})
                if probe is not None and frozen is not None and len(locks) == 2:
                    final_descriptors(probe, support, frozen, library_fd, library, locks)
            except BaseException as error:
                result['ok'] = False
                result['errors'].append(safe_failure(error, 'new_step_result_write_or_final_FD'))
    raw = canonical(result) + b'\n'
    need(len(raw) <= 131072, 'OWNED_CHILD_PUBLIC_OUTPUT_BOUND')
    sys.stdout.buffer.write(raw); sys.stdout.buffer.flush()
    return 0 if result['ok'] else 1


def candidate_gate(value, self_pin, request_pin):
    need(value.get('schema') == CANDIDATE_SCHEMA and value.get('source') == self_pin and
         value.get('request') == request_pin and value.get('flow') == FLOW and value.get('step') == STEP and
         value.get('producer_operation') == OPERATION and value.get('original_case') == CASE_STEP and
         value.get('later_observation') == OBSERVATION_STEP and
         value.get('historical_controller_and_proof', {}).get('job_id') == HOST_JOB and
         value.get('historical_controller_and_proof', {}).get('historical_proof') == HOST_PROOF and
         value.get('original_case_ok') is False and value.get('original_case_outcome_unknown') is True and
         value.get('original_action_outcome') == 'unknown_retained' and
         all(value.get(key) is True for key in ('two_original_rounds_equal',
             'original_foreground_predicate_and_full_scope_preserved', 'held_Main_authority_closed',
             'all_historical_bytes_and_full_stat_unchanged', 'flow_and_action_locks_held_until_process_exit',
             'original_unknown_result_kept', 'requires_parent_normal_pidfd_exit_and_durable_terminal',
             'stage_B_not_sealed_or_executed')) and
         all(value.get(key) is False for key in ('original_results_rewritten', 'old_action_replayed',
             'Flow_reconcile_called', 'current_tree_or_node_reobserved', 'reconciliation_published',
             'compatibility_envelope_written', 'current_action_authority', 'business_success_verified',
             'production_ready', 'automatic_retry', 'private_UI_raw_or_nodes_included')) and
         all(type(value.get(key)) is int and value[key] == 0 for key in ('unknown_descriptors_closed',
             'UI_actions', 'instrumentation_calls', 'permission_changes', 'installs', 'lifecycle_or_activation_actions')),
         'ONLY_CLOSED_NONAUTHORIZING_STAGE_A_CANDIDATE')
    commands = value.get('runtime_commands', {})
    need(commands.get('recorded_command_count') == 6 and commands.get('transport_count') == 8 and
         commands.get('private_foreground_transport_count') == 2 and
         commands.get('all_commands_normal_joined') is True and
         commands.get('all_transports_post_guard_and_lease_release') is True and
         commands.get('private_foreground_raw_saved') is False and len(commands.get('command_proofs', [])) == 6,
         'STAGE_A_EXACT_READONLY_RUNTIME_COMMAND_PROOF')


def parent():
    base = entry('--execute-runtime-once')
    result = {'schema': PARENT_SCHEMA, 'ok': False, 'errors': [], 'source': SELF, 'request': REQUEST,
        'flow': FLOW, 'task': TASK, 'step': STEP, 'operation': OPERATION,
        'original_case_ok': False, 'original_case_outcome_unknown': True,
        'original_results_rewritten': False, 'old_action_replayed': False,
        'reconciliation_published': False, 'compatibility_envelope_written': False,
        'current_action_authority': False, 'production_ready': False, 'automatic_retry': False,
        'UI_actions': 0, 'instrumentation_calls': 0, 'installs': 0, 'permission_changes': 0,
        'lifecycle_or_activation_actions': 0, 'stage_B_not_sealed_or_executed': True,
        'acceptance_requires_original_stdout_and_authoritative_durable_terminal': True}
    invoked = False; probe = before = None
    try:
        support = base.load(base.SUPPORT, 'unchanged_explicit_library_functions')
        probe = support.load_module(support.PROBE_SOURCE, 'unchanged_owned_pidfd_lifetime')
        observed = support.probe_proof(); support.pin_runtime_files(probe, observed)
        before = probe.census(); need(set(before) == {'0', '1', '2'}, 'PARENT_INITIAL_STDIO_ONLY')
        partial = base.load(PARTIAL_SOURCE, 'unchanged_original_document_parser')
        host = base.load(HOST_SOURCE, 'unchanged_actual_host_terminal_gate')
        request_value(base.pinned(REQUEST), partial)
        actual_host_gate(base, host, partial)
        no_publication_or_replay()
        need(not os.path.lexists(Path(FLOW) / 'steps' / STEP), 'NO_STAGE_A_REPLAY')
        write_once(base, Path(ROOT) / 'attempt.json', canonical({'source': SELF, 'request': REQUEST,
            'step': STEP, 'child_not_yet_started': True, 'automatic_retry': False}) + b'\n')
        need(probe.same_descriptors(before, probe.census()), 'PARENT_PRE_CHILD_DESCRIPTOR_IDENTITY')
        argv = [sys.executable, '-I', '-B', SELF['path'], '--child', '--source-sha256', SELF['sha256'],
                '--source-bytes', str(SELF['bytes']), '--request-sha256', REQUEST['sha256'],
                '--request-bytes', str(REQUEST['bytes'])]
        invoked = True
        life, raw, stderr = probe.run_owned_child(argv, seconds=600)
        result.update(child_lifecycle=life, child_stdout_original=raw.decode('utf-8', 'strict'),
            child_stdout_bytes=len(raw), child_stdout_sha256=sha(raw),
            child_stderr_original=stderr.decode('utf-8', 'replace'), child_stderr_bytes=len(stderr),
            child_stderr_sha256=sha(stderr))
        base.require_owned_exit(life, stderr)
        value = partial.document(raw)
        need(value.get('schema') == CHILD_SCHEMA and value.get('ok') is True and value.get('errors') == [] and
             value.get('source') == SELF and value.get('request') == REQUEST and value.get('flow') == FLOW and
             value.get('task') == TASK and value.get('step') == STEP and value.get('operation') == OPERATION and
             all(value.get(key) is True for key in ('held_Main_authority_closed',
                 'original_foreground_predicate_preserved', 'all_historical_originals_unchanged',
                 'requires_parent_normal_pidfd_exit_and_durable_terminal')) and
             value.get('original_case_ok') is False and value.get('original_case_outcome_unknown') is True and
             all(value.get(key) is False for key in ('original_results_rewritten', 'old_action_replayed',
                 'Flow_reconcile_called', 'reconciliation_published', 'compatibility_envelope_written',
                 'current_action_authority', 'business_success_verified', 'production_ready', 'automatic_retry',
                 'manual_library_close', 'private_UI_raw_or_nodes_in_stdout')) and
             all(type(value.get(key)) is int and value[key] == 0 for key in ('UI_actions',
                 'instrumentation_calls', 'installs', 'permission_changes', 'lifecycle_or_activation_actions',
                 'unknown_descriptors_closed')), 'COMPLETE_STAGE_A_CHILD_AND_NORMAL_RETIREMENT_JOINTLY_REQUIRED')
        pin = value['candidate']
        need(pin['path'] == FLOW + '/steps/' + STEP + '/runtime-candidate.json', 'EXACT_STAGE_A_CANDIDATE_PATH')
        candidate_raw = base.pinned(pin); candidate = partial.document(candidate_raw)
        need(candidate_raw == canonical(candidate) + b'\n', 'EXACT_CANDIDATE_SERIALIZATION')
        candidate_gate(candidate, SELF, REQUEST)
        need(candidate['runtime_commands'] == value['runtime_commands'], 'SAME_ACTUAL_SIX_COMMAND_EVIDENCE')
        step_result_raw, _ = base.read(Path(FLOW) / 'steps' / STEP / 'result.json')
        step_result = partial.document(step_result_raw)
        need(step_result.get('schema') == 'pocket4-owned-qa-stage-a-step-result-v1' and
             step_result.get('ok') is True and step_result.get('errors') == [] and
             step_result.get('action_attempted') is False and step_result.get('outcome_unknown') is False and
             step_result.get('candidate') == pin and step_result.get('reconciliation_published') is False and
             step_result.get('current_action_authority') is False and
             step_result.get('original_case_ok') is False and step_result.get('original_case_outcome_unknown') is True,
             'NEW_STEP_RESULT_AND_PARENT_JOINT_GATE')
        for pin_to_check in (SELF, REQUEST, BASE, UI_SOURCE, HOST_SOURCE, PARTIAL_SOURCE,
                             HOST_STDOUT, HOST_TERMINAL, HOST_PROOF, base.SUPPORT, support.PROBE_SOURCE):
            base.pinned(pin_to_check)
        support.pin_runtime_files(probe, observed)
        no_publication_or_replay()
        need(probe.same_descriptors(before, probe.census()), 'PARENT_FD_IDENTITIES_RESTORED')
        result.update(ok=True, candidate=pin, step_result={'path': FLOW + '/steps/' + STEP + '/result.json',
            'bytes': len(step_result_raw), 'sha256': sha(step_result_raw)},
            all_owned_child_resources_retired_by_normal_pidfd_exit=True,
            parent_whole_process_FD_identity_restored=True, historical_proof=HOST_PROOF,
            explicit_next_stage_requires_new_request_after_this_actual_durable_terminal=True)
        artifact = write_once(base, Path(ROOT) / 'owned-runtime-candidate-joint.json', canonical(result) + b'\n')
        need(probe.same_descriptors(before, probe.census()), 'PARENT_FD_IDENTITIES_AFTER_JOINT_ARTIFACT')
        result['joint_artifact'] = artifact
    except BaseException as error:
        result['ok'] = False; result['errors'].append(safe_failure(error, 'parent_joint_gate'))
    if not result['ok']:
        result['runtime_candidate_qualification_incomplete'] = True
        result['child_invoked'] = invoked
        result['automatic_retry'] = False
    raw = canonical(result) + b'\n'; need(len(raw) <= 262144, 'BOUNDED_PUBLIC_PARENT_OUTPUT')
    sys.stdout.buffer.write(raw); sys.stdout.buffer.flush()
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    need(sys.argv[1:2] in (['--execute-runtime-once'], ['--child']), 'ONLY_EXPLICIT_STAGE_A_ENTRY')
    raise SystemExit(child() if sys.argv[1] == '--child' else parent())
