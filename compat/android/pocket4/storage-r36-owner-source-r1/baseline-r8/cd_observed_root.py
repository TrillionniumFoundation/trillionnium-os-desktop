"""Validate the actual ROOT v2 observed-epoch receipt, without a live-storage grant.

This deliberately has no v1 compatibility branch. Canonical observation hashes
are recomputed from Python's exact integer JSON values, never JS Number values.
"""
import hashlib

from f9_authority import full_ref
from recovery_core import encoded, require

ROOT_SHA = '17197e500d1b7a41d0ef808e4a26fe1bcb4c5475fd5eabb486499f7578e43ad3'
ROOT_PATH = '/data/p4-final-f9-root-observed-epoch-acceptance-e6ac-r2.json'
ROOT_KEYS = {
    'schema', 'ROOT_review_passed', 'new_final_F9_completed_and_retired',
    'recovery_plan_accepted_for_observed_epoch', 'acceptance_scope',
    'source_manifest_sha256', 'nonce', 'source_lock_sha256', 'accepted_A',
    'evidence', 'observed_plan', 'close_protocol', 'retirement',
    'original_storage_epoch', 'current_storage', 'original_B_passed',
    'original_storage_functional_passed', 'old_typed_CD_v1_authority_compatible',
    'new_storage_transition_required_before_any_CD', 'C_D_admitted',
    'full_build_admission_granted', 'Android_builds', 'runtime_qualified',
    'production_ready', 'app_acceptances', 'CURRENT_changed',
}


def same(a, b, message):
    require(encoded(a) == encoded(b), message)


def observed_root(root, refs, contract, result, independent, close, terminal, close_h):
    ref = full_ref(refs['root_acceptance'])
    require((ref['path'], ref['bytes'], ref['sha256']) == (ROOT_PATH, 20863, ROOT_SHA),
            'the whole actually published ROOT observed-epoch acceptance')
    require(type(root) is dict and set(root) == ROOT_KEYS and
            root['schema'] == 'p4-final-f9-root-observed-epoch-acceptance-v2' and
            root['ROOT_review_passed'] is True and
            root['new_final_F9_completed_and_retired'] is True and
            root['recovery_plan_accepted_for_observed_epoch'] is True and
            root['source_manifest_sha256'] == result['source_manifest_sha256'] and
            root['nonce'] == contract['nonce'] and
            root['source_lock_sha256'] == contract['source_lock_sha256'],
            'actual v2 ROOT acceptance, not the never-issued v1 proposal')
    require(all(root[k] is False for k in (
        'original_B_passed', 'original_storage_functional_passed',
        'old_typed_CD_v1_authority_compatible', 'C_D_admitted',
        'full_build_admission_granted', 'runtime_qualified', 'production_ready',
        'CURRENT_changed')) and
        root['new_storage_transition_required_before_any_CD'] is True and
        all(type(root[k]) is int and root[k] == 0 for k in ('Android_builds', 'app_acceptances')),
        'historical acceptance does not accept a failed B, current storage, C/D or Android')
    same(root['accepted_A'], contract['accepted_audit_ancestor'], 'same original accepted A')
    evidence = root['evidence']
    require(set(evidence) == {'source_manifest', 'contract', 'admission', 'dispatch',
            'entry', 'main', 'main_logs', 'independent', 'paged_close_r2', 'root_originals'},
            'complete actual ROOT evidence schema')
    for name in ('source_manifest', 'contract', 'admission', 'dispatch', 'entry', 'independent'):
        same(evidence[name], refs[name], 'ROOT exact original ' + name)
    same(evidence['main'], refs['result'], 'actual main original ref, not a relabelled copy')
    same(evidence['paged_close_r2'], refs['close'], 'ROOT actual paged close r2 ref')
    same(evidence['main_logs'], independent['logs'], 'complete original native log references')

    plan = root['observed_plan']
    for key, original in (
        ('authenticated_manifest', result['authenticated_source_manifest']),
        ('observed_manifest', result['observed_manifest']),
        ('plan', result['exact_recovery_plan']), ('sealed_proofs', result['sealed_proofs']),
        ('counts', result['counts']), ('coverage', result['current_complete_F9']['coverage'])):
        same(plan[key], original, 'ROOT accepted the exact observed plan ' + key)
    require(plan['source_members'] == contract['accepted_audit_ancestor']['members'] and
            plan['payload_bytes'] == contract['accepted_audit_ancestor']['payload_bytes'] and
            plan['source_roots'] == len(contract['selected_roots']) == 30 and
            all(plan[k] is True for k in ('namespace_before_after_complete_equal',
                'all_record_F9_SHA_bookends_equal', 'all_actions_and_rows_independently_recomputed')),
            'complete accepted observed membership, actions and record closure')
    for key in ('missing_or_partial_payload_bytes', 'preserved_partial_bytes',
                'selected_file_body_bytes_rehashed', 'source_writes', 'destination_writes'):
        require(type(plan[key]) is int and plan[key] == result[key] == 0,
                'unchanged actual zero count: ' + key)
    canonical = plan['canonical_observations']
    require(set(canonical) == {'current_namespace_before', 'current_namespace_after',
                              'current_complete_F9', 'preserved_old_coherent'},
            'four actual full observations, not selected metadata samples')
    for key, expected in canonical.items():
        raw = encoded(result[key])
        require(set(expected) == {'bytes', 'sha256', 'encoding'} and
                len(raw) == expected['bytes'] and hashlib.sha256(raw).hexdigest() == expected['sha256'] and
                expected['encoding'] == 'original sorted JSON tokens, whitespace removed outside strings, trailing LF; ns integers never converted through JS Number',
                'whole canonical actual observation with all original integer tokens: ' + key)

    protocol = root['close_protocol']
    require(protocol['actual_schema'] == close['schema'] == 'p4-production651-final-f9-paged-close-v2' and
            protocol['original_single_page_r1_not_executed'] is True and
            protocol['ordinary_controls'] == 20 and protocol['ordinary_failures'] == 0,
            'only the actual separately tested r2 close protocol')
    same(protocol['new_control_sources'], close['new_control_sources'], 'exact new close and decoder identities')
    same(protocol['normal_independent_H'], terminal, 'same reconstruction of every actual original H page')
    output = bytes.fromhex(close_h['bytes_hex'])
    same(protocol['paged_close_H'], {'session_id': close_h['session_id'],
         'bytes': len(output), 'sha256': hashlib.sha256(output).hexdigest(),
         'exit_code': close_h['status']['exit_code']}, 'ROOT accepted the actual whole close terminal')
    retired = root['retirement']
    same(retired['main'], result['native'], 'ROOT main generation')
    same(retired['independent'], independent['observer'], 'ROOT independent generation')
    same(retired['paged_close'], close['native'], 'ROOT actual r2 close generation')
    require(all(retired[k] is True for k in (
        'main_retirement_validated_by_original_independent',
        'independent_retirement_validated_by_original_close',
        'both_serial_locks_independently_free', 'all_29_original_source_files_unchanged',
        'ROOT_final_close_and_reader_original_pids_absent',
        'ROOT_final_units_both_scopes_not_found', 'ROOT_final_reader_exact_cgroup_ENOENT')),
        'all actual terminal generations and original source/lock closure are accepted')
    same(root['original_storage_epoch'], contract['new_storage_source_binding'],
         'historical source binding at the actual F9 observation, never a replacement owner')
    current = root['current_storage']
    require(set(current) == {'ready', 'original_server_failed', 'failure_result_sha256',
            'ROOT_failure_triage_sha256', 'historical_whole_image_SHA_not_applied_to_current_modified_image'} and
            current['ready'] is False and current['original_server_failed'] is True and
            current['failure_result_sha256'] == 'f8bced85b2f826738e1e23a585e2f529321125465b35211d5c6e432430a8f9f6' and
            current['historical_whole_image_SHA_not_applied_to_current_modified_image'] is True,
            'old r5 READY and historical offline image hash are explicitly revoked for current use')
    return {'observed_epoch_accepted': True, 'current_storage_ready': False,
            'new_storage_transition_required': True, 'C_D_execution_admitted': False}
