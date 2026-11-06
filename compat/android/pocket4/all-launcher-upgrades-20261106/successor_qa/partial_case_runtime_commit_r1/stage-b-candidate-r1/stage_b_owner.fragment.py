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
        'requires_parent_normal_pidfd_exit_and_durable_terminal': True,
        'frozen_consumer_checks_controller_terminal': False,
        'coordinator_must_keep_new_actions_frozen_until_actual_terminal': True}
    flow = recorder = None; closed = False; action_lock = None; phase = 'bootstrap'
    probe = support = frozen = library = None; library_fd = None; locks = {}
    publication_attempted = False
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
        phase = 'actual_completed_stage_A_reverification'
        stage_a = completed_stage_a(base, host, partial, core, context)
        no_publication_or_replay()
        need(not os.path.lexists(Path(FLOW) / 'steps' / STEP), 'NEW_STAGE_B_STEP_NO_REPLAY')
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
        for name in ('case_binding', 'observer_binding', 'stage_A_binding'):
            partial.binding_identity(context[name], core, qa)
        core.installed_identity(context['installed'], build)
        qa.scope(context['foreground'])
        recorder = base.load(base.RECORDER, 'unchanged_original_recorder_flow')
        need(probe.same_descriptors(frozen, probe.census()), 'NO_PRE_MAIN_UNKNOWN_DESCRIPTOR')
        phase = 'original_flow_and_locks'
        fargs = types.SimpleNamespace(operation=OPERATION, adapter_manifest_sha256=core.RECORDER_MANIFEST,
            flow_dir=Path(FLOW), epoch_module=Path(RECORDER_ROOT) / 'references/framework_epoch.py',
            task_source=Path(RECORDER_ROOT) / 'references/task_scope_baseline.py', step=STEP,
            request={'stage_b_only': request, 'producer_source': SELF, 'request_pin': REQUEST},
            unknown_step=CASE_STEP, observation_step=OBSERVATION_STEP, postcondition=partial.POSTCONDITION)
        flow = recorder.Flow(fargs)
        locks[str(flow.lock)] = checked_lock(probe, flow.lock, Path(FLOW) / 'flow.lock')
        action_lock = recorder.lock_file(recorder.ACTION_LOCK)
        locks[str(action_lock)] = checked_lock(probe, action_lock, recorder.ACTION_LOCK)
        need(len(locks) == 2 and set(locks).isdisjoint(frozen), 'TWO_ORIGINAL_DISTINCT_NONBLOCKING_LOCKS')
        flow.begin(fargs, mutation=False)
        no_publication_or_replay()
        reconciliation_directory = publication_parent_identity()
        need(flow.scope == context['scope'], 'ORIGINAL_CURRENT_FLOW_SCOPE_UNCHANGED')
        for filename in ('baseline.json', 'baseline-qualification.json'):
            path = FLOW + '/' + filename
            context['originals'][path] = base.read(path)
        flow.source.verify_saved_baseline(flow.root)
        phase = 'fresh_held_binding'
        binding = flow.bind(); partial.binding_identity(binding.record, core, qa)
        comparisons = {name: core.compare_held_bindings(context[name], binding.record)
                       for name in ('case_binding', 'observer_binding', 'stage_A_binding')}
        phase = 'two_original_session_rounds'
        session = adapter.Session(flow, recorder, qa, build, HELPER_UID)
        rounds = two_original_rounds(session, context['installed'], context['launch'], context['foreground'])
        command_evidence = verify_six_commands(base, flow, binding, partial, core, qa, context, recorder.now())
        phase = 'final_current_and_historical_recheck'
        flow.contract.verify(); flow.guard(attempted=False)
        flow.source.verify_saved_baseline(flow.root)
        recheck_completed_inputs(base, context, deadline)
        need(qualified_current_build(adapter, manifest, builder, core, context) == (build, build_stat),
             'ACTUAL_BUILD_REPLACED_DURING_CURRENT_OBSERVATION')
        adapter.own_source(core.HELPER_MANIFEST)
        ui.launch_gate(base, core)
        for pin in (SELF, REQUEST, BASE, UI_SOURCE, HOST_SOURCE, PARTIAL_SOURCE, base.RECORDER, base.CORE,
                    base.SUPPORT, support.PROBE_SOURCE, STAGE_A_SOURCE, STAGE_A_REQUEST, STAGE_A_STDOUT,
                    STAGE_A_TERMINAL, STAGE_A_CANDIDATE, STAGE_A_RESULT, STAGE_A_JOINT):
            base.pinned(pin)
        support.pin_runtime_files(probe, observed_runtime)
        flow.guard(attempted=False)
        phase = 'release_main_authority'
        flow.close(); closed = True
        flow.source.runtime_and_app_guard(flow.current_guard)
        flow.epoch.require_unchanged(flow.activation['framework_epoch'], action_attempted=False)
        for fd, expected in locks.items():
            need(checked_lock(probe, int(fd), expected['link']) == expected, 'ORIGINAL_LOCK_PATH_OR_IDENTITY_CHANGED')
        final = final_descriptors(probe, support, frozen, library_fd, library, locks)
        need(time.monotonic() < deadline, 'STAGE_B_TOTAL_DEADLINE')
        phase = 'write_explicit_partial_case_proof'
        proof = {'schema': PROOF_SCHEMA, 'created_utc': recorder.now(), 'source': SELF, 'request': REQUEST,
            'phase_at_file_creation': 'CURRENT_CHECKS_COMPLETE_BEFORE_NO_REPLACE_PUBLICATION',
            'publication_attempted_at_file_creation': False,
            'this_file_does_not_claim_stage_B_process_exit_or_controller_terminal': True,
            'flow': FLOW, 'step': STEP, 'producer_operation': OPERATION,
            'original_case': CASE_STEP, 'later_observation': OBSERVATION_STEP,
            'historical_controller_and_proof': context['gate'], 'completed_stage_A': stage_a,
            'scope_sha256': partial.SCOPE_SHA, 'framework_epoch_sha256': core.MAIN_EPOCH,
            'runtime_epoch_sha256': core.RUNTIME_EPOCH, 'app_scope_sha256': core.APP_SCOPE,
            'original_case_ok': False, 'original_case_outcome_unknown': True,
            'original_action_outcome': 'unknown_retained', 'original_results_rewritten': False,
            'old_action_replayed': False, 'Flow_reconcile_called': False,
            'evidence_semantics': 'Actual successful prefix plus rejected pre-dispatch suffix and later independent postcondition; original failed case remains failed.',
            'current_installed_helper': rounds[0]['installed'], 'current_owned_task': rounds[0]['task'],
            'current_foreground': rounds[0]['foreground'], 'two_original_rounds_equal': True,
            'current_tree_or_node_reobserved': False, 'current_action_authority': False,
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
            'installs': 0, 'lifecycle_or_activation_actions': 0, 'original_unknown_result_kept': True,
            'business_success_verified': False, 'production_ready': False, 'automatic_retry': False,
            'requires_parent_normal_pidfd_exit_and_durable_terminal': True,
            'frozen_consumer_checks_controller_terminal': False,
            'coordinator_must_keep_new_actions_frozen_until_actual_terminal': True,
            'private_UI_raw_or_nodes_included': False}
        copies = {'producer-source.py': base.pinned(SELF), 'producer-request.json': base.pinned(REQUEST),
                  'host-historical-proof.json': context['proof_raw'],
                  'host-controller.stdout.original.jsonl': base.pinned(HOST_STDOUT),
                  'host-controller.terminal.original.json': base.pinned(HOST_TERMINAL),
                  **context['stage_A_external_copies']}
        for name, raw in copies.items():
            recorder.write_new(flow.step / name, raw)
        raw = canonical(proof) + b'\n'; need(len(raw) <= 131072, 'BOUNDED_EXPLICIT_PARTIAL_CASE_PROOF')
        recorder.write_new(flow.step / 'owned-qa-partial-proof.json', raw)
        proof_pin = {'path': str(flow.step / 'owned-qa-partial-proof.json'), 'bytes': len(raw), 'sha256': sha(raw)}
        need(base.pinned(proof_pin) == raw, 'NEW_TYPED_PROOF_FULL_READBACK')
        hashes = collect_relative_hashes(base, context, flow, deadline)
        recheck_completed_inputs(base, context, deadline)
        flow.source.runtime_and_app_guard(flow.current_guard)
        flow.epoch.require_unchanged(flow.activation['framework_epoch'], action_attempted=False)
        need(final_descriptors(probe, support, frozen, library_fd, library, locks) == final,
             'FINAL_RESOURCES_CHANGED_BEFORE_NO_REPLACE_PUBLICATION')
        envelope = {'schema': 'pocket4-flow-explicit-reconciliation-v1', 'created_utc': recorder.now(),
            'unknown_step': CASE_STEP, 'observation_step': OBSERVATION_STEP,
            'epoch_sha256': core.MAIN_EPOCH, 'scope_sha256': partial.SCOPE_SHA,
            'original_action_outcome': 'unknown_retained', 'allows_new_decisions_only': True,
            'evidence_sha256': hashes, 'postcondition': partial.POSTCONDITION,
            'new_owned_qa_producer': {'schema': PROOF_SCHEMA, 'operation': OPERATION,
                'proof_relative_path': 'steps/' + STEP + '/owned-qa-partial-proof.json',
                'source': SELF, 'request': REQUEST, 'original_Flow_reconcile_called': False,
                'completed_runtime_candidate_job': STAGE_A_JOB,
                'completed_runtime_candidate_terminal': STAGE_A_TERMINAL,
                'completed_runtime_candidate': STAGE_A_CANDIDATE},
            'original_action_result_rewritten': False, 'old_action_replayed': False,
            'business_success_verified': False, 'production_ready': False, 'automatic_retry': False,
            'current_UI_action_authority': False,
            'external_stage_B_owned_exit_and_durable_terminal_still_required': True,
            'frozen_consumer_checks_controller_terminal': False,
            'new_step_result_is_postpublication_and_not_self_referential_evidence': True}
        envelope_raw = canonical(envelope) + b'\n'
        need(len(envelope_raw) <= 131072 and time.monotonic() < deadline, 'BOUNDED_FINAL_COMPATIBILITY_COMMIT')
        phase = 'single_no_replace_compatibility_commit'
        need(publication_parent_identity() == reconciliation_directory, 'PUBLICATION_PARENT_IDENTITY_CHANGED')
        committed = commit_envelope(Path(FLOW) / 'reconciliations' / (CASE_STEP + '.json'), envelope_raw, COMMIT_NONCE)
        publication_attempted = True
        result['committed'] = committed
        result['compatibility_envelope_written'] = True
        need(base.pinned(committed) == envelope_raw, 'NO_REPLACE_COMMIT_READBACK')
        need(publication_parent_identity() == reconciliation_directory, 'PUBLICATION_PARENT_CHANGED_DURING_COMMIT')
        committed_envelope(base, partial, core, committed, proof_pin)
        need(final_descriptors(probe, support, frozen, library_fd, library, locks) == final,
             'FINAL_DESCRIPTOR_IDENTITY_AFTER_COMMIT')
        need(time.monotonic() < deadline, 'STAGE_B_POSTCOMMIT_DEADLINE')
        result.update(ok=True, typed_proof=proof_pin, runtime_commands=command_evidence,
            original_historical_proof=HOST_PROOF, completed_stage_A=stage_a,
            current_binding_sha256=proof['current_binding_sha256'], held_Main_authority_closed=True,
            original_foreground_predicate_preserved=True, all_historical_originals_unchanged=True,
            final_descriptors=final, normal_process_exit_required_for_locks_and_library=True,
            unknown_descriptors_closed=0, manual_library_close=False, private_UI_raw_or_nodes_in_stdout=False,
            reconciliation_published=True, compatibility_envelope_written=True,
            envelope_evidence_count=len(hashes), next_decision_requires_fresh_original_helper_inspection=True)
    except BaseException as error:
        publication_attempted |= bool(getattr(error, 'publication_attempted', False))
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
                actual = probe.census(); result['final_descriptors'] = actual
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
        result['publication_attempted'] = publication_attempted
        result['publication_outcome_unknown'] = publication_attempted and not result['ok']
        if result['publication_outcome_unknown']:
            result['reconciliation_published'] = None
            if 'committed' not in result:
                result['compatibility_envelope_written'] = None
        if recorder is not None and flow is not None and flow.step is not None:
            try:
                recorder.write_new(flow.step / 'result.json', {
                    'schema': 'pocket4-owned-qa-partial-case-commit-step-result-v1', 'ok': result['ok'],
                    'action_attempted': False, 'outcome_unknown': result['publication_outcome_unknown'],
                    'errors': result['errors'], 'epoch_sha256': flow.scope['epoch_sha256'],
                    'ended_utc': recorder.now(), 'automatic_retry': False, 'business_success_verified': False,
                    'production_ready': False, 'original_case_ok': False, 'original_case_outcome_unknown': True,
                    'original_results_rewritten': False, 'publication_attempted': publication_attempted,
                    'publication_outcome_unknown': result['publication_outcome_unknown'],
                    'reconciliation_published': result['reconciliation_published'],
                    'compatibility_envelope': result.get('committed'), 'typed_proof': result.get('typed_proof'),
                    'current_action_authority': False, 'requires_parent_normal_pidfd_exit_and_durable_terminal': True,
                    'coordinator_must_keep_new_actions_frozen_until_actual_terminal': True})
                if probe is not None and frozen is not None and len(locks) == 2:
                    final_descriptors(probe, support, frozen, library_fd, library, locks)
            except BaseException as error:
                result['ok'] = False
                result['publication_outcome_unknown'] = publication_attempted
                if publication_attempted:
                    result['reconciliation_published'] = None
                result['errors'].append(safe_failure(error, 'postpublication_result_write_or_final_FD'))
    raw = canonical(result) + b'\n'; need(len(raw) <= 131072, 'OWNED_CHILD_PUBLIC_OUTPUT_BOUND')
    sys.stdout.buffer.write(raw); sys.stdout.buffer.flush()
    return 0 if result['ok'] else 1


def parent():
    base = entry('--publish-once')
    result = {'schema': PARENT_SCHEMA, 'ok': False, 'errors': [], 'source': SELF, 'request': REQUEST,
        'flow': FLOW, 'task': TASK, 'step': STEP, 'operation': OPERATION,
        'original_case_ok': False, 'original_case_outcome_unknown': True,
        'original_results_rewritten': False, 'old_action_replayed': False,
        'reconciliation_published': False, 'compatibility_envelope_written': False,
        'current_action_authority': False, 'production_ready': False, 'automatic_retry': False,
        'UI_actions': 0, 'instrumentation_calls': 0, 'installs': 0, 'permission_changes': 0,
        'lifecycle_or_activation_actions': 0,
        'frozen_consumer_checks_controller_terminal': False,
        'coordinator_must_keep_new_actions_frozen_until_actual_terminal': True,
        'acceptance_requires_original_stdout_and_authoritative_durable_terminal': True}
    invoked = False; probe = before = None
    try:
        support = base.load(base.SUPPORT, 'unchanged_explicit_library_functions')
        probe = support.load_module(support.PROBE_SOURCE, 'unchanged_owned_pidfd_lifetime')
        observed = support.probe_proof(); support.pin_runtime_files(probe, observed)
        before = probe.census(); need(set(before) == {'0', '1', '2'}, 'PARENT_INITIAL_STDIO_ONLY')
        partial = base.load(PARTIAL_SOURCE, 'unchanged_original_document_parser')
        host = base.load(HOST_SOURCE, 'unchanged_actual_host_terminal_gate')
        stage_a_module = base.load(STAGE_A_SOURCE, 'unchanged_actual_completed_stage_a_gate')
        request_value(base.pinned(REQUEST), partial)
        actual_host_gate(base, host, partial)
        validate_actual_stage_a(base.pinned(STAGE_A_STDOUT), partial.document(base.pinned(STAGE_A_TERMINAL)),
                                host, partial, base, stage_a_module)
        no_publication_or_replay()
        need(not os.path.lexists(Path(FLOW) / 'steps' / STEP), 'NO_STAGE_B_REPLAY')
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
                 'requires_parent_normal_pidfd_exit_and_durable_terminal', 'reconciliation_published',
                 'compatibility_envelope_written', 'publication_attempted',
                 'next_decision_requires_fresh_original_helper_inspection')) and
             value.get('original_case_ok') is False and value.get('original_case_outcome_unknown') is True and
             all(value.get(key) is False for key in ('original_results_rewritten', 'old_action_replayed',
                 'Flow_reconcile_called', 'current_action_authority', 'business_success_verified',
                 'production_ready', 'automatic_retry', 'manual_library_close', 'private_UI_raw_or_nodes_in_stdout',
                 'publication_outcome_unknown', 'frozen_consumer_checks_controller_terminal')) and
             all(type(value.get(key)) is int and value[key] == 0 for key in ('UI_actions',
                 'instrumentation_calls', 'installs', 'permission_changes', 'lifecycle_or_activation_actions',
                 'unknown_descriptors_closed')), 'COMPLETE_STAGE_B_COMMIT_AND_NORMAL_RETIREMENT_JOINTLY_REQUIRED')
        core = base.load(base.CORE, 'unchanged_scope_and_hash_contract')
        proof_pin = value['typed_proof']; proof_raw = base.pinned(proof_pin); proof = partial.document(proof_raw)
        need(proof_pin['path'] == FLOW + '/steps/' + STEP + '/owned-qa-partial-proof.json' and
             proof_raw == canonical(proof) + b'\n' and proof.get('schema') == PROOF_SCHEMA and
             proof.get('source') == SELF and proof.get('request') == REQUEST and proof.get('flow') == FLOW and
             proof.get('step') == STEP and proof.get('producer_operation') == OPERATION and
             proof.get('runtime_commands') == value['runtime_commands'] and
             proof.get('completed_stage_A') == value['completed_stage_A'] and
             proof['completed_stage_A']['job_id'] == STAGE_A_JOB and
             proof['completed_stage_A']['runtime_candidate'] == STAGE_A_CANDIDATE and
             proof.get('publication_attempted_at_file_creation') is False and
             proof.get('this_file_does_not_claim_stage_B_process_exit_or_controller_terminal') is True and
             proof.get('original_case_ok') is False and proof.get('original_case_outcome_unknown') is True and
             proof.get('current_action_authority') is False and proof.get('private_UI_raw_or_nodes_included') is False,
             'EXACT_NEW_TYPED_PROOF_AND_ALREADY_COMPLETED_STAGE_A')
        committed = value['committed']
        envelope = committed_envelope(base, partial, core, committed, proof_pin)
        need(value['envelope_evidence_count'] == len(envelope['evidence_sha256']), 'SAME_COMPLETE_FLOW_EVIDENCE_SET')
        old_raw, _ = base.read(Path(FLOW) / 'steps' / CASE_STEP / 'result.json')
        old = partial.document(old_raw)
        need(old.get('ok') is False and old.get('outcome_unknown') is True and
             sha(old_raw) == envelope['evidence_sha256']['steps/' + CASE_STEP + '/result.json'],
             'ORIGINAL_PARTIAL_CASE_STILL_FAILED_UNKNOWN')
        step_result_raw, _ = base.read(Path(FLOW) / 'steps' / STEP / 'result.json')
        step_result = partial.document(step_result_raw)
        need(step_result.get('schema') == 'pocket4-owned-qa-partial-case-commit-step-result-v1' and
             step_result.get('ok') is True and step_result.get('errors') == [] and
             step_result.get('action_attempted') is False and step_result.get('outcome_unknown') is False and
             step_result.get('publication_attempted') is True and step_result.get('publication_outcome_unknown') is False and
             step_result.get('compatibility_envelope') == committed and step_result.get('typed_proof') == proof_pin and
             step_result.get('reconciliation_published') is True and step_result.get('current_action_authority') is False and
             step_result.get('original_case_ok') is False and step_result.get('original_case_outcome_unknown') is True,
             'ACTUAL_POSTCOMMIT_STEP_RESULT_REQUIRED')
        for pin in (SELF, REQUEST, BASE, UI_SOURCE, HOST_SOURCE, PARTIAL_SOURCE, HOST_STDOUT, HOST_TERMINAL,
                    HOST_PROOF, base.SUPPORT, support.PROBE_SOURCE, STAGE_A_SOURCE, STAGE_A_REQUEST,
                    STAGE_A_STDOUT, STAGE_A_TERMINAL, STAGE_A_CANDIDATE, STAGE_A_RESULT, STAGE_A_JOINT):
            base.pinned(pin)
        support.pin_runtime_files(probe, observed)
        need(probe.same_descriptors(before, probe.census()), 'PARENT_FD_IDENTITIES_RESTORED')
        result.update(ok=True, committed=committed, typed_proof=proof_pin, completed_stage_A=value['completed_stage_A'],
            step_result={'path': FLOW + '/steps/' + STEP + '/result.json', 'bytes': len(step_result_raw),
                         'sha256': sha(step_result_raw)},
            reconciliation_published=True, compatibility_envelope_written=True, publication_outcome_unknown=False,
            all_owned_child_resources_retired_by_normal_pidfd_exit=True,
            parent_whole_process_FD_identity_restored=True, historical_proof=HOST_PROOF,
            original_action_outcome='unknown_retained', envelope_evidence_count=len(envelope['evidence_sha256']),
            next_decision_requires_fresh_original_helper_inspection=True)
        artifact = write_once(base, Path(ROOT) / 'owned-partial-reconciliation-joint.json', canonical(result) + b'\n')
        need(probe.same_descriptors(before, probe.census()), 'PARENT_FD_IDENTITIES_AFTER_JOINT_ARTIFACT')
        result['joint_artifact'] = artifact
    except BaseException as error:
        result['ok'] = False; result['errors'].append(safe_failure(error, 'parent_joint_gate'))
    if not result['ok']:
        result['publication_outcome_unknown'] = invoked
        if invoked:
            result['reconciliation_published'] = None
            result['compatibility_envelope_written'] = None
        result['child_invoked'] = invoked
        result['automatic_retry'] = False
        result['no_retry_or_new_UI_decision_before_original_job_reconciliation'] = True
    raw = canonical(result) + b'\n'; need(len(raw) <= 262144, 'BOUNDED_PUBLIC_PARENT_OUTPUT')
    sys.stdout.buffer.write(raw); sys.stdout.buffer.flush()
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    need(sys.argv[1:2] in (['--publish-once'], ['--child']), 'ONLY_EXPLICIT_STAGE_B_ENTRY')
    raise SystemExit(child() if sys.argv[1] == '--child' else parent())
