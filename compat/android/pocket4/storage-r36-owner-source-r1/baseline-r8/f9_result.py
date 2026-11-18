"""Pure result gates for the new completed pass; not a C/D acceptance bridge."""
from recovery_core import encoded, require


def retirement_terminal_code(action, functional_passed):
    require(action in ('normal-retire', 'stop') and type(functional_passed) is bool,
            'actual requested retirement action and explicit functional outcome')
    return 1 if action == 'normal-retire' and not functional_passed else 0


def verify_retirement_terminal(prior, actual_exit_code):
    require(prior['retirement_passed'] is True and type(actual_exit_code) is int and
            actual_exit_code == retirement_terminal_code(prior['requested_action'], prior['functional_passed']),
            'real independent terminal agrees with its requested action without promoting function')


def completed_result(value, contract, admitted):
    require(value['schema'] == 'p4-production651-final-f9-result-v1' and value['phase'] == 'final_f9' and
            value['passed'] is True and value['nonce'] == contract['nonce'] and
            value['source_manifest_sha256'] == admitted['source_manifest_sha256'] and
            value['source_lock_sha256'] == contract['source_lock_sha256'] and
            value['new_final_F9_complete'] is True and value['recovery_plan_eligible_for_root_review'] is True and
            value['root_plan_review_required'] is True and value['namespace_observation_is_new'] is True,
            'only a complete actual independently admitted new final-F9 result')
    require(all(value[k] is False for k in ('original_B_passed', 'original_storage_functional_passed',
            'old_partial_cursor_reused', 'recovery_plan_accepted', 'C_D_admitted', 'production_ready')) and
            all(type(value[k]) is int and value[k] == 0 for k in
                ('source_writes', 'destination_writes', 'selected_file_body_bytes_rehashed', 'Android_builds')),
            'no prior failure promotion, new file hash claim, destination write or later-phase authority')
    authority = admitted['fixed_proof_validation']
    records = authority['records']; validation = records['validation']
    require(encoded(value['fixed_proof_validation']) == encoded(authority) and
            encoded(value['record_inputs']) == encoded(records) and
            encoded(value['counts']) == encoded(validation['counts']) and value['counts']['conflict'] == 0 and
            encoded(value['exact_recovery_plan']) == encoded(records['sealed_copies']['REUSE-AND-GAP-PLAN.ndjson']) and
            encoded(value['observed_manifest']) == encoded(records['sealed_copies']['DESTINATION-OBSERVED.ndjson']) and
            encoded(value['authenticated_source_manifest']) == encoded(contract['authenticated_manifest']['copy']),
            'same actually sealed full first-pass evidence and historical A')
    revalidated = value['record_revalidation']
    require(revalidated['schema'] == 'p4-final-f9-record-revalidation-v1' and
            encoded(revalidated['validation']) == encoded(validation) and
            revalidated['all_before_after_SHA_F9_equal'] is True and revalidated['SQLite_changes'] == 0 and
            revalidated['new_index_or_journal_copies'] == 0 and revalidated['original_B_passed'] is False,
            'full records and original A remained byte/F9 equal around the new full pass')
    totals = validation['totals']; current = value['current_complete_F9']; coverage = current['coverage']
    mapping = {'source_members': 'source_members', 'observed_members': 'observed_members',
               'files': 'files', 'directories': 'directories', 'symlinks': 'symlinks',
               'file_sizes_from_metadata': 'observed_file_bytes'}
    require(coverage['schema'] == 'p4-final-f9-complete-observed-coverage-v1' and
            all(type(coverage[k]) is int and coverage[k] == totals[v] for k, v in mapping.items()) and
            coverage['all_original_observed_ordinals_rechecked'] is True and
            coverage['all_nine_F9_fields_compared'] is True and coverage['SQLite_changes'] == 0 and
            coverage['selected_file_body_bytes_rehashed'] == 0 and
            coverage['original_B_passed'] is False and coverage['old_partial_cursor_reused'] is False,
            'full ordinal bitmap and every original F9 field, no partial cursor')
    metrics = current['walk_metrics']
    require(metrics['traversal_completed'] is True and metrics['body_hash'] is False and
            metrics['body_sha_bytes'] == 0 and metrics['worker_threads_started'] == 0 and
            metrics['worker_threads_joined'] is True and
            encoded(value['current_namespace_before']) == encoded(current['namespace']) ==
            encoded(value['current_namespace_after']) and
            value['preserved_old_coherent']['evidence_only_not_latest_producer'] is True,
            'completed held walk and the newly checked complete retained/synthetic namespace')
    return {'new_complete_final_F9_verified': True, 'original_B_passed': False,
            'recovery_plan_accepted': False, 'C_D_admitted': False}
