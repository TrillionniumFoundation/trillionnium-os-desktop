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
need(proof_pin['path'] == FLOW + '/steps/' + STEP + '/owned-qa-no-action-proof.json' and
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
need(step_result.get('schema') == 'pocket4-owned-qa-no-action-commit-step-result-v1' and
     step_result.get('ok') is True and step_result.get('errors') == [] and
     step_result.get('action_attempted') is False and step_result.get('outcome_unknown') is False and
     step_result.get('publication_attempted') is True and step_result.get('publication_outcome_unknown') is False and
     step_result.get('compatibility_envelope') == committed and step_result.get('typed_proof') == proof_pin and
     step_result.get('reconciliation_published') is True and step_result.get('current_action_authority') is False and
     step_result.get('original_case_ok') is False and step_result.get('original_case_outcome_unknown') is True,
     'ACTUAL_POSTCOMMIT_STEP_RESULT_REQUIRED')
