def validate_actual_stage_a(raw, terminal, host, partial, base, stage_a):
    host.original_terminal(terminal, STAGE_A_JOB, len(raw))
    lines = raw.splitlines()
    need(len(lines) == 2 and raw.endswith(b'\n'), 'EXACT_ACTUAL_STAGE_A_STAGE_AND_OWNED_OUTPUT')
    stage, outer = [partial.document(line) for line in lines]
    need(stage == ACTUAL_STAGE_A_STAGE, 'ACTUAL_STAGE_A_SOURCE_STAGE_UNCHANGED')
    need(lines[1] == canonical(outer) and outer.get('schema') == stage_a.PARENT_SCHEMA and
         outer.get('source') == STAGE_A_SOURCE and outer.get('request') == STAGE_A_REQUEST and
         outer.get('flow') == FLOW and outer.get('task') == TASK and outer.get('step') == STAGE_A_STEP and
         outer.get('operation') == stage_a.OPERATION and outer.get('candidate') == STAGE_A_CANDIDATE and
         outer.get('step_result') == STAGE_A_RESULT and outer.get('joint_artifact') == STAGE_A_JOINT and
         outer.get('historical_proof') == HOST_PROOF and outer.get('ok') is True and outer.get('errors') == [] and
         outer.get('original_case_ok') is False and outer.get('original_case_outcome_unknown') is True and
         all(outer.get(key) is True for key in ('all_owned_child_resources_retired_by_normal_pidfd_exit',
             'parent_whole_process_FD_identity_restored',
             'explicit_next_stage_requires_new_request_after_this_actual_durable_terminal',
             'acceptance_requires_original_stdout_and_authoritative_durable_terminal', 'stage_B_not_sealed_or_executed')) and
         all(outer.get(key) is False for key in ('old_action_replayed', 'original_results_rewritten',
             'compatibility_envelope_written', 'reconciliation_published', 'current_action_authority',
             'production_ready', 'automatic_retry')) and
         all(type(outer.get(key)) is int and outer[key] == 0 for key in ('UI_actions', 'instrumentation_calls',
             'installs', 'permission_changes', 'lifecycle_or_activation_actions')),
         'ACTUAL_COMPLETE_NONAUTHORIZING_STAGE_A_OWNER_RESULT')
    stderr = outer['child_stderr_original'].encode('utf-8')
    need(stderr == b'' and outer['child_stderr_bytes'] == 0 and outer['child_stderr_sha256'] == sha(b''),
         'ACTUAL_STAGE_A_EMPTY_CHILD_STDERR')
    base.require_owned_exit(outer['child_lifecycle'], stderr)
    need(outer['child_lifecycle']['child_pid'] == 2349898, 'EXACT_ACTUAL_STAGE_A_OWNED_CHILD_ID')
    child_raw = outer['child_stdout_original'].encode('utf-8')
    need(len(child_raw) == outer['child_stdout_bytes'] == 10728 and
         sha(child_raw) == outer['child_stdout_sha256'] == '2650042c12f8bb977b546209b7c65ff2e57020cede3dbf7fab1fb98ed9d5251f',
         'EXACT_ACTUAL_STAGE_A_CHILD_ORIGINAL_BYTES')
    child = partial.document(child_raw)
    need(child.get('schema') == stage_a.CHILD_SCHEMA and child.get('ok') is True and child.get('errors') == [] and
         child.get('source') == STAGE_A_SOURCE and child.get('request') == STAGE_A_REQUEST and
         child.get('flow') == FLOW and child.get('step') == STAGE_A_STEP and child.get('task') == TASK and
         child.get('operation') == stage_a.OPERATION and child.get('candidate') == STAGE_A_CANDIDATE and
         child.get('original_historical_proof') == HOST_PROOF and
         child.get('original_case_ok') is False and child.get('original_case_outcome_unknown') is True and
         all(child.get(key) is True for key in ('held_Main_authority_closed', 'original_foreground_predicate_preserved',
             'all_historical_originals_unchanged', 'requires_parent_normal_pidfd_exit_and_durable_terminal',
             'normal_process_exit_required_for_locks_and_library')) and
         all(child.get(key) is False for key in ('original_results_rewritten', 'old_action_replayed',
             'Flow_reconcile_called', 'reconciliation_published', 'compatibility_envelope_written',
             'current_action_authority', 'business_success_verified', 'production_ready', 'automatic_retry',
             'manual_library_close', 'private_UI_raw_or_nodes_in_stdout')) and
         all(type(child.get(key)) is int and child[key] == 0 for key in ('UI_actions', 'instrumentation_calls',
             'installs', 'permission_changes', 'lifecycle_or_activation_actions', 'unknown_descriptors_closed')),
         'ACTUAL_STAGE_A_CHILD_GATE_COMPLETE_NOT_ONLY_INNER_RENDER')
    return outer, child


def completed_stage_a(base, host, partial, core, context):
    def tracked(pin):
        raw, metadata = read_exact(base, pin)
        if pin['path'] in context['originals']:
            need(context['originals'][pin['path']] == (raw, metadata), 'STAGE_A_INPUT_REPLACED_DURING_REVERIFY')
        context['originals'][pin['path']] = (raw, metadata)
        return raw
    a_source_raw = tracked(STAGE_A_SOURCE)
    stage_a = types.ModuleType('frozen_actually_completed_stage_A_definitions'); stage_a.__file__ = STAGE_A_SOURCE['path']
    exec(compile(a_source_raw, STAGE_A_SOURCE['path'], 'exec'), stage_a.__dict__)
    need(stage_a.FLOW == FLOW and stage_a.STEP == STAGE_A_STEP and stage_a.HOST_PROOF == HOST_PROOF,
         'FIXED_COMPLETED_STAGE_A_PROVENANCE')
    a_request_raw = tracked(STAGE_A_REQUEST)
    stage_a.request_value(a_request_raw, partial)
    raw = tracked(STAGE_A_STDOUT); terminal_raw = tracked(STAGE_A_TERMINAL)
    outer, child = validate_actual_stage_a(raw, partial.document(terminal_raw), host, partial, base, stage_a)
    joint_raw = tracked(STAGE_A_JOINT)
    joint = dict(outer); del joint['joint_artifact']
    need(joint_raw == canonical(joint) + b'\n', 'ACTUAL_STAGE_A_JOINT_EQUALS_DURABLE_STDOUT')
    candidate_raw = tracked(STAGE_A_CANDIDATE); candidate = partial.document(candidate_raw)
    need(candidate_raw == canonical(candidate) + b'\n', 'EXACT_ACTUAL_STAGE_A_CANDIDATE_SERIALIZATION')
    stage_a.candidate_gate(candidate, STAGE_A_SOURCE, STAGE_A_REQUEST)
    need(candidate['runtime_commands'] == child['runtime_commands'] and
         candidate['current_binding_sha256'] == child['current_binding_sha256'] and
         candidate['current_installed_helper'] == context['installed'] and
         candidate['current_owned_task'] == context['launch'] and candidate['current_foreground'] == context['foreground'] and
         candidate['build'] == context['build'], 'ACTUAL_STAGE_A_SAME_TASK_HELPER_SCOPE_AND_HISTORY')
    result_raw = tracked(STAGE_A_RESULT); result = partial.document(result_raw)
    need(result.get('schema') == 'pocket4-owned-qa-stage-a-step-result-v1' and result.get('ok') is True and
         result.get('errors') == [] and result.get('action_attempted') is False and result.get('outcome_unknown') is False and
         result.get('candidate') == STAGE_A_CANDIDATE and result.get('epoch_sha256') == core.MAIN_EPOCH and
         result.get('original_case_ok') is False and result.get('original_case_outcome_unknown') is True and
         result.get('original_results_rewritten') is False and result.get('current_action_authority') is False and
         result.get('reconciliation_published') is False and
         result.get('requires_parent_normal_pidfd_exit_and_durable_terminal') is True,
         'ACTUAL_STAGE_A_STEP_RESULT_NOT_AN_ADMISSION')
    names = {'intent.json', 'held-main-binding.json'}
    names |= {'command-%03d%s' % (i, suffix) for i in range(1, 7)
              for suffix in ('.intent.json', '.result.json', '.stdout', '.stderr')}
    names |= {'transport-%03d.%s.json' % (i, suffix) for i in range(1, 9)
              for suffix in ('intent', 'command-result', 'verified-result')}
    hashes = candidate['runtime_commands']['evidence_sha256']
    need(set(hashes) == names and len(names) == 50, 'EXACT_ACTUAL_STAGE_A_FIFTY_RUNTIME_FILES')
    folder = Path(FLOW) / 'steps' / STAGE_A_STEP
    for name, digest in sorted(hashes.items()):
        need(re.fullmatch('[0-9a-f]{64}', digest), 'EXACT_STAGE_A_MEMBER_DIGEST')
        path = str(folder / name); body, metadata = base.read(path)
        need(sha(body) == digest, 'COMPLETED_STAGE_A_RUNTIME_EVIDENCE_CHANGED')
        context['originals'][path] = (body, metadata)
    copies = {'producer-source.py': a_source_raw, 'producer-request.json': a_request_raw,
              'host-historical-proof.json': context['proof_raw'],
              'host-controller.stdout.original.jsonl': tracked(stage_a.HOST_STDOUT),
              'host-controller.terminal.original.json': tracked(stage_a.HOST_TERMINAL)}
    for name, expected in copies.items():
        path = str(folder / name); body, metadata = base.read(path)
        need(body == expected, 'COMPLETED_STAGE_A_IMMUTABLE_SOURCE_AND_CONTROLLER_COPY_CHANGED')
        context['originals'][path] = (body, metadata)
    names |= set(copies) | {'runtime-candidate.json', 'result.json'}
    need(len(names) == 57 and sorted(os.listdir(folder)) == sorted(names), 'ALL_AND_ONLY_ACTUAL_STAGE_A_FILES')
    context['stage_A_file_set'] = sorted(names)
    binding_raw = context['originals'][str(folder / 'held-main-binding.json')][0]
    need(sha(binding_raw) == candidate['current_binding_sha256'], 'ACTUAL_STAGE_A_BINDING_PIN')
    context['stage_A_binding'] = partial.document(binding_raw)
    context['stage_A_candidate'] = candidate
    context['stage_A_external_copies'] = {'stage-a-controller.stdout.original.jsonl': raw,
        'stage-a-controller.terminal.original.json': terminal_raw, 'stage-a-owned-joint.original.json': joint_raw}
    return {'job_id': STAGE_A_JOB, 'source': STAGE_A_SOURCE, 'request': STAGE_A_REQUEST,
        'stdout': STAGE_A_STDOUT, 'terminal': STAGE_A_TERMINAL, 'joint': STAGE_A_JOINT,
        'runtime_candidate': STAGE_A_CANDIDATE, 'step_result': STAGE_A_RESULT,
        'child_lifecycle': outer['child_lifecycle'], 'owned_child_normal_exit_and_controller_already_completed': True,
        'no_future_stage_B_exit_claimed_here': True, 'original_stage_A_files': 57}


def recheck_completed_inputs(base, context, deadline):
    recheck_history(base, context, deadline)
    need(sorted(os.listdir(Path(FLOW) / 'steps' / STAGE_A_STEP)) == context['stage_A_file_set'],
         'COMPLETED_STAGE_A_DIRECTORY_SET_CHANGED')


def publication_parent_identity():
    path = Path(FLOW) / 'reconciliations'
    need(path.resolve() == path, 'CANONICAL_ORIGINAL_RECONCILIATION_DIRECTORY')
    value = os.stat(path, follow_symlinks=False)
    need(stat.S_ISDIR(value.st_mode) and value.st_uid == 0 and stat.S_IMODE(value.st_mode) == 0o700,
         'ORIGINAL_ROOT_PRIVATE_RECONCILIATION_DIRECTORY')
    return {key: getattr(value, key) for key in ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink')}


def collect_relative_hashes(base, context, flow, deadline):
    hashes = {}
    for path, (raw, metadata) in context['originals'].items():
        if not path.startswith(FLOW + '/'):
            continue
        relative = path[len(FLOW) + 1:]
        need(relative and not relative.startswith('reconciliations/') and '\\' not in relative and
             all(part not in ('', '.', '..') for part in relative.split('/')),
             'ONLY_ORIGINAL_FLOW_RELATIVE_EVIDENCE_NO_EXTERNAL_PATH_DISGUISE')
        hashes[relative] = sha(raw)
    expected_prefixes = {'steps/' + CASE_STEP + '/': 257, 'steps/' + OBSERVATION_STEP + '/': 81,
                         'steps/' + STAGE_A_STEP + '/': 57}
    for prefix, count in expected_prefixes.items():
        need(sum(name.startswith(prefix) for name in hashes) == count, 'COMPLETE_HISTORICAL_FLOW_EVIDENCE_SET')
    initial = sorted(os.listdir(flow.step))
    need('result.json' not in initial and 'owned-qa-partial-proof.json' in initial and 55 <= len(initial) <= 65,
         'NEW_TYPED_PROOF_FILES_BEFORE_COMMIT_NO_FUTURE_RESULT_CLAIM')
    for name in initial:
        need(time.monotonic() < deadline and '/' not in name and '\\' not in name and name not in ('', '.', '..'),
             'BOUNDED_NEW_PROOF_FILE_SET')
        raw, _ = base.read(flow.step / name)
        relative = 'steps/' + STEP + '/' + name
        need(relative not in hashes, 'NEW_PROOF_MUST_NOT_REPLACE_ORIGINAL_EVIDENCE')
        hashes[relative] = sha(raw)
    need(sorted(os.listdir(flow.step)) == initial and 450 <= len(hashes) <= 512,
         'COMPLETE_FINITE_RELATIVE_PROOF_CLOSURE')
    return dict(sorted(hashes.items()))


def committed_envelope(base, partial, core, expected_pin, proof_pin=None):
    deadline = time.monotonic() + 60
    need(expected_pin['path'] == FLOW + '/reconciliations/' + CASE_STEP + '.json',
         'ONLY_EXACT_ORIGINAL_UNKNOWN_RECONCILIATION_PATH')
    raw = base.pinned(expected_pin); value = partial.document(raw)
    need(raw == canonical(value) + b'\n' and value.get('schema') == 'pocket4-flow-explicit-reconciliation-v1' and
         value.get('unknown_step') == CASE_STEP and value.get('observation_step') == OBSERVATION_STEP and
         value.get('epoch_sha256') == core.MAIN_EPOCH and value.get('scope_sha256') == partial.SCOPE_SHA and
         value.get('original_action_outcome') == 'unknown_retained' and value.get('allows_new_decisions_only') is True and
         value.get('original_action_result_rewritten') is False and value.get('old_action_replayed') is False and
         value.get('business_success_verified') is False and value.get('production_ready') is False and
         value.get('automatic_retry') is False and value.get('current_UI_action_authority') is False and
         value.get('external_stage_B_owned_exit_and_durable_terminal_still_required') is True and
         value.get('frozen_consumer_checks_controller_terminal') is False,
         'TRUTHFUL_NEW_PRODUCER_COMPATIBILITY_RECORD_NOT_OLD_UI_PROTOCOL')
    producer = value.get('new_owned_qa_producer')
    need(producer == {'schema': PROOF_SCHEMA, 'operation': OPERATION,
        'proof_relative_path': 'steps/' + STEP + '/owned-qa-partial-proof.json',
        'source': SELF, 'request': REQUEST, 'original_Flow_reconcile_called': False,
        'completed_runtime_candidate_job': STAGE_A_JOB, 'completed_runtime_candidate_terminal': STAGE_A_TERMINAL,
        'completed_runtime_candidate': STAGE_A_CANDIDATE}, 'EXACT_NEW_PARTIAL_CASE_PRODUCER_IDENTITY')
    hashes = value.get('evidence_sha256')
    need(type(hashes) is dict and 450 <= len(hashes) <= 512, 'COMPLETE_RELATIVE_RECONCILIATION_CLOSURE')
    total = 0
    for relative, digest in hashes.items():
        need(time.monotonic() < deadline, 'PUBLISHED_PROOF_RECHECK_DEADLINE')
        need(type(relative) is str and not relative.startswith('/') and not relative.startswith('reconciliations/') and
             '\\' not in relative and all(part not in ('', '.', '..') for part in relative.split('/')) and
             re.fullmatch('[0-9a-f]{64}', digest), 'CLOSED_SAFE_RELATIVE_EVIDENCE_MEMBER')
        body, _ = base.read(Path(FLOW) / relative)
        total += len(body)
        need(total <= 24 * 1024 * 1024, 'PUBLISHED_PROOF_TOTAL_BYTE_BOUND')
        need(sha(body) == digest, 'PUBLISHED_COMPATIBILITY_EVIDENCE_CHANGED')
    if proof_pin is not None:
        need(proof_pin['path'] == FLOW + '/steps/' + STEP + '/owned-qa-partial-proof.json' and
             hashes['steps/' + STEP + '/owned-qa-partial-proof.json'] == proof_pin['sha256'] and
             sha(base.pinned(proof_pin)) == proof_pin['sha256'], 'PUBLISHED_NEW_TYPED_PROOF_PIN')
    return value
