"""Typed review authority from completed new F9, never a fabricated successful B.

Pure validation only. No caller gains C/D execution permission from this return value.
The accepted observed epoch is historical. A separate, actually admitted storage
transition is mandatory before any future C/D actor can consume the plan.
"""
import hashlib
import json

from f9_authority import full_ref
from f9_contract import canonical_binding
from f9_result import completed_result, verify_retirement_terminal
from recovery_core import encoded, require

SOURCE = 'd84a90d376beded3c3f9dfc5124dd522c882316a6ccdf1a696294ea8f7e6992e'
NONCE = 'ad8546f4bb7e18728839f877b3800cf4d48825ec8f39e33078c4a1961f7f142f'
ADMISSION_SHA = '751e6c1dfd3ef7d79f2351e250e05d96af5f88bb10ef2db9a43643596ffe236a'
PAGED_CLOSE_SOURCE = 'e40a1c40fb76e153d131722c00b0497c280b4d8d9411e8376af8f8f6e6ed3b7d'
PAGED_CLOSE_DECODER = 'e382b4e074a5dfcee4ef34b7e1b63f9a35739d4d1dbf89f6829a000a2130f12a'
PAGED_CLOSE_UNIT = 'p4-production651-final-f9-paged-close-e6ac-r2.service'
DOCUMENTS = {'source_manifest', 'contract', 'admission', 'dispatch', 'entry', 'result',
             'independent', 'close', 'root_acceptance', 'old_B_result', 'old_B_retirement'}
FALSE_FLAGS = ('original_B_passed', 'original_storage_functional_passed',
               'recovery_plan_accepted', 'C_D_admitted', 'production_ready')


def same(left, right, why):
    require(encoded(left) == encoded(right), why)


def structure_sha(value):
    """Explicit canonical-structure digest, never mislabelled a file-body digest."""
    return hashlib.sha256(encoded(value)).hexdigest()


def native_identity(value):
    require(type(value['pid']) is int and value['pid'] > 1 and
            type(value['start_ticks']) is str and value['start_ticks'].isdigit() and
            int(value['start_ticks']) > 0 and type(value['InvocationID']) is str and
            len(value['InvocationID']) == 32 and
            all(c in '0123456789abcdef' for c in value['InvocationID']), 'actual original native generation')
    return {k:value[k] for k in ('unit', 'pid', 'start_ticks', 'InvocationID', 'cgroup')}


def original_terminal(raw, expected_sha, boot):
    require(type(raw) is bytes and 0 < len(raw) <= 65536 and
            hashlib.sha256(raw).hexdigest() == expected_sha, 'complete bounded original small H JSON')
    h = json.loads(raw); status = h['status']; output = bytes.fromhex(h['bytes_hex'])
    require(h['host'] == 'desktop' and h['offset'] == 0 and h['truncated_before_offset'] is False and
            h['output_complete'] is True and status['state'] == 'exited' and status['exit_code'] == 0 and
            type(status['exit_code']) is int and status['capture_error'] is None and
            status['output_complete'] is True and status['boot'] == boot and
            len(output) == h['next_offset'] == h['available_end'] == status['bytes_seen'] == status['bytes_stored'] and
            hashlib.sha256(output).hexdigest() == h['chunk_sha256'], 'whole actual successful small terminal')
    require(type(h['session_id']) is str and len(h['session_id']) == 69 and h['session_id'].startswith('dpty-') and
            all(type(status[k]) is int and status[k] > 1 for k in ('pid', 'owner_pid')),
            'actual H identity; no fabricated original outer birth')
    events = [json.loads(line) for line in output.decode().splitlines() if line.startswith('{')]
    require(events, 'actual JSON event in whole original output')
    return h, events[-1]


def accepted_plan(result, contract):
    audit = contract['accepted_audit_ancestor']
    return {'schema':'p4-c-d-exact-reviewed-plan-v1',
        'authenticated_source_manifest':{'original':audit['authenticated_manifest'],
                                         'final_f9_copy':result['authenticated_source_manifest']},
        'exact_recovery_plan':result['exact_recovery_plan'], 'observed_manifest':result['observed_manifest'],
        'counts':result['counts'], 'members':audit['members'], 'payload_bytes':audit['payload_bytes'],
        'missing_or_partial_payload_bytes':result['missing_or_partial_payload_bytes'],
        'preserved_partial_bytes':result['preserved_partial_bytes'],
        'synthetic_parents':result['synthetic_parents'],
        'preserved_old_coherent_structure_sha256':structure_sha(result['preserved_old_coherent']),
        'current_namespace_structure_sha256':structure_sha(result['current_namespace_after'])}


def validate_plan_authority(documents, terminals):
    require(set(documents) == DOCUMENTS and set(terminals) == {'dispatch', 'independent', 'close'},
            'all actual completed proofs are mandatory, not placeholders')
    for family in (documents, terminals):
        for key, record in family.items():
            original = full_ref(record['original']); full_ref(record['copy'])
            raw = record['raw']
            require(type(raw) is bytes and len(raw) == original['bytes'] and
                    hashlib.sha256(raw).hexdigest() == original['sha256'], 'whole original bytes: ' + key)
            if family is documents: same(json.loads(raw), record['body'], 'parsed body preserves exact original values')
    refs = {key:row['original'] for key,row in documents.items()}
    body = {key:row['body'] for key,row in documents.items()}
    contract = body['contract']; admission = body['admission']; result = body['result']
    entry = body['entry']; dispatch = body['dispatch']; ind = body['independent']; close = body['close']
    require(refs['source_manifest']['sha256'] == SOURCE and
            (refs['contract']['bytes'], refs['contract']['sha256']) ==
            (body['source_manifest']['files']['contract.json']['bytes'],
             body['source_manifest']['files']['contract.json']['sha256']), 'exact actually qualified F9 source and contract')
    require(contract['schema'] == 'p4-production651-final-f9-contract-v1' and
            contract['generation'] == 'e6ac-final-f9-r2' and contract['nonce'] == NONCE and
            admission['schema'] == 'p4-production651-final-f9-admission-v1' and
            refs['admission']['sha256'] == ADMISSION_SHA and admission['phase'] == 'final_f9' and
            admission['source_manifest_sha256'] == SOURCE and admission['nonce'] == NONCE,
            'actual F9 generation remains distinct from future C/D source')
    same(admission['canonical_final_f9_binding'], canonical_binding(contract, SOURCE), 'complete accepted F9 source binding')
    same(refs['old_B_result'], contract['original_B_result'], 'original failed B result full ref')
    same(refs['old_B_retirement'], contract['original_B_retirement'], 'original failed B retirement full ref')
    require(body['old_B_result']['passed'] is False and body['old_B_result']['phase'] == 'reuse' and
            body['old_B_result']['source_manifest_sha256'] == contract['historical_old_B_source_sha256'] and
            'destination_writes' not in body['old_B_result'] and
            body['old_B_retirement']['retirement_passed'] is True and
            body['old_B_retirement']['functional_passed'] is False,
            'old failure and absent destination_writes field remain exact historical facts')
    require(body['old_B_retirement']['phase'] == 'reuse' and
            body['old_B_retirement']['source_manifest_sha256'] == body['old_B_result']['source_manifest_sha256'] and
            body['old_B_retirement']['nonce'] == body['old_B_result']['nonce'], 'exact failed original B generation')
    same(body['old_B_retirement']['result'], refs['old_B_result'], 'original failed retirement authenticates its actual result')
    root = contract['hosts']['desktop']['root']; boot = contract['hosts']['desktop']['boot']
    expected_paths = {'source_manifest':'source/SOURCE-MANIFEST.json', 'contract':'source/contract.json',
        'admission':'admissions/final_f9.json', 'dispatch':'dispatch-receipts/final_f9.json',
        'entry':'entry-proofs/final_f9.json', 'result':'operation/final_f9/producer/RESULT.json',
        'independent':'retirements/final_f9.json', 'close':'retirements/final_f9-paged-close-r2.json'}
    for key, suffix in expected_paths.items():
        require(documents[key]['original_host'] == 'desktop' and refs[key]['path'] == root + '/' + suffix,
                'exact original desktop proof path: ' + key)
    for value in (admission, entry, result, ind, close):
        require(value['source_manifest_sha256'] == SOURCE and value['nonce'] == NONCE and
                all(value[k] is False for k in FALSE_FLAGS), 'unchanged failure and permission flags')
    require(entry['schema'] == 'p4-production651-final-f9-entry-v1' and entry['phase'] == 'final_f9' and
            entry['actual_uid'] == entry['actual_gid'] == 1000 and entry['actual_groups'] == [] and
            entry['actual_active_capabilities_zero'] is True, 'actual held ordinary F9 entry')
    same(entry['phase_admission'], refs['admission'], 'actual entry admission')
    same(entry['owner_ready'], admission['storage_epoch']['owner_ready'], 'actual owner epoch without a new deadline')
    same(result['entry'], refs['entry'], 'actual completed result entry')
    same(result['admission'], refs['admission'], 'actual completed result admission')
    require(dispatch['schema'] == 'p4-production651-final-f9-dispatch-v1' and
            dispatch['source_manifest_sha256'] == SOURCE and dispatch['success_not_inferred'] is True,
            'dispatch success never substitutes for final F9 success')
    same(dispatch['admission'], refs['admission'], 'actual dispatch admission')
    original_native = native_identity(dispatch['actual'])
    same(native_identity(result['native']), original_native, 'same completed native generation')
    require(entry['pid'] == original_native['pid'] and entry['start_ticks'] == original_native['start_ticks'] and
            entry['unit']['InvocationID'] == original_native['InvocationID'] and
            entry['unit']['Id'] == original_native['unit'] and
            '/sys/fs/cgroup' + entry['unit']['ControlGroup'] == original_native['cgroup'],
            'original entry and held native identity')
    completed_result(result, contract, admission)
    require(result['implementation_returned_to_actor'] is True, 'new pass actually returned to its actor')
    require(ind['schema'] == 'p4-production651-final-f9-retirement-v1' and ind['phase'] == 'final_f9' and
            ind['requested_action'] == 'normal-retire' and ind['retirement_passed'] is True and
            ind['functional_passed'] is True and ind['cgroup_absent'] is True and
            ind['validation_errors'] == ind['forced_owned_signals'] == [] and
            ind['original_B_serial_lock_independently_free'] is True and
            ind['new_phase_serial_lock_independently_free'] is True,
            'successful normal independent retirement, not a stopped or failed phase')
    same(ind['result'], refs['result'], 'independent binds the whole actual completed F9 result')
    same(ind['entry'], refs['entry'], 'independent binds the actual entry')
    same(ind['admission'], refs['admission'], 'independent binds the actual admission')
    same(native_identity(ind['actual']), original_native, 'independent retired the exact original generation')
    same(ind['independent_record_revalidation'], result['record_revalidation'], 'independent whole record closure')
    require(ind['terminal']['InvocationID'] == original_native['InvocationID'] and
            ind['terminal']['ExecMainPID'] == str(original_native['pid']) and
            ind['terminal']['Result'] == 'success' and ind['terminal']['ExecMainCode'] == '1' and
            ind['terminal']['ExecMainStatus'] == '0' and
            ind['original_process']['pid'] == original_native['pid'] and
            ind['original_process']['original_start_ticks'] == original_native['start_ticks'] and
            ind['original_process']['original_generation_absent'] is True,
            'actual successful main terminal and original birth absent')
    require(ind['observer']['unit'] == contract['observers']['independent']['unit'] and
            ind['observer']['boot'] == boot, 'fixed independent unit and boot')
    require(close['schema'] == 'p4-production651-final-f9-paged-close-v2' and close['passed'] is True and
            close['functional_result_passed'] is True and close['requested_action'] == 'normal-retire' and
            close['original_close_executed'] is False and close['original_single_page_H_claimed'] is False and
            close['final_write_and_stdout_deadline_gate_requires_exit_zero'] is True and
            close['original_29_source_files_unchanged'] is True and
            close['new_final_F9_eligible_for_root_review'] is True and
            set(close['new_control_sources']) == {'close', 'decoder'} and
            close['new_control_sources']['close']['sha256'] == PAGED_CLOSE_SOURCE and
            close['new_control_sources']['close']['path'] == '/data/p4-final-f9-paged-close-e6ac-r2.py' and
            close['new_control_sources']['decoder']['sha256'] == PAGED_CLOSE_DECODER and
            close['new_control_sources']['decoder']['path'] == '/data/p4-final-f9-paged-terminal-e6ac-r2.py' and
            close['native']['unit'] == PAGED_CLOSE_UNIT and close['native']['boot'] == boot and
            close['both_serial_locks_independently_free'] is True,
            'separate paged close program and actual successful retirement')
    for key in ('close', 'decoder'): full_ref(close['new_control_sources'][key])
    same(close['original_source_manifest'], refs['source_manifest'], 'unchanged actual original source manifest')
    require(all(type(close[k]) is int and close[k] == 0 for k in
                ('target_opens', 'image_opens', 'record_opens', 'new_storage_actions')),
            'separate close made no new observation or storage action')
    same(close['prior'], refs['independent'], 'close references exact independent report')
    same(close['admission'], refs['admission'], 'close references exact admission')
    same(close['retired_independent']['native'], ind['observer'], 'close retired the original observer')
    after = close['retired_independent']['actual_after']
    require(close['retired_independent']['original_generation_absent'] is True and
            close['retired_independent']['cgroup_absent'] is True and
            after['LoadState'] == 'not-found' and after['ActiveState'] == 'inactive' and
            after['SubState'] == 'dead' and after['MainPID'] == '0' and
            after['InvocationID'] == after['ControlGroup'] == '', 'actual independent native disappearance')
    for key in terminals:
        require(terminals[key]['original_host'] == 'desktop', 'actual terminal host')
    dispatch_h, dispatch_event = original_terminal(terminals['dispatch']['raw'],
        terminals['dispatch']['original']['sha256'], boot)
    require(set(dispatch_event) == {'dispatch', 'actual', 'new_starts'} and dispatch_event['new_starts'] == 1,
            'the single actual dispatch event')
    same(dispatch_event['dispatch'], refs['dispatch'], 'original dispatch H binds its whole receipt')
    same(dispatch_event['actual'], dispatch['actual'], 'original dispatch H binds the native generation')
    # This decoder consumes an explicit envelope. It cannot manufacture a single-page H.
    from paged_terminal import decode_envelope
    independent_h, output = decode_envelope(terminals['independent']['raw'],
        terminals['independent']['original']['sha256'], boot, close['prior_H_session_id'])
    verify_retirement_terminal(ind, independent_h['status']['exit_code'])
    events = [json.loads(line) for line in output.decode().splitlines() if line.startswith('{')]
    require(events and set(events[-1]) == {'reference', 'body'}, 'actual full independent event across original pages')
    same(events[-1]['reference'], refs['independent'], 'paged event original reference')
    same(events[-1]['body'], ind, 'paged event complete actual independent body')
    same(close['prior_H_pagination_envelope'], terminals['independent']['original'], 'close held this exact envelope')
    same(close['prior_H_terminal'], independent_h, 'same complete original per-page identities and actual stdout')
    require(close['prior_H_pagination_envelope_sha256'] == terminals['independent']['original']['sha256'] and
            close['prior_H_session_id'] == independent_h['session_id'] and
            close['prior_H_exit_code'] == independent_h['status']['exit_code'] == 0 and
            close['prior_H_output_sha256'] == independent_h['stdout_sha256'], 'whole explicit pagination join')
    close_h, close_event = original_terminal(terminals['close']['raw'], terminals['close']['original']['sha256'], boot)
    require(set(close_event) == {'passed', 'native', 'result', 'close_kind'} and close_event['passed'] is True and
            close_event['close_kind'] == 'new_explicit_pagination_r2',
            'actual zero-exit successful close event after final deadline check')
    same(close_event['native'], close['native'], 'close H actual native identity')
    same(close_event['result'], refs['close'], 'close H actual complete report reference')
    native_identity(close['native'])
    observed_outer = close['outer_absence']
    require(type(observed_outer) is list and len(observed_outer) == 2 and
            [row['pid'] for row in observed_outer] ==
            [independent_h['status']['pid'], independent_h['status']['owner_pid']] and
            all(row['pid_name_absent_now'] is True and row['current_start_ticks'] is None and
                row['original_start_ticks'] is None and row['original_birth_independently_captured'] is False
                for row in observed_outer), 'close preserves actual outer absence and unknown original births')
    from cd_observed_root import observed_root
    review = observed_root(body['root_acceptance'], refs, contract, result, ind, close, independent_h, close_h)
    plan = accepted_plan(result, contract)
    return {'schema':'p4-c-d-observed-plan-authority-v2', 'root_acceptance':refs['root_acceptance'],
        'final_f9_source_manifest_sha256':SOURCE, 'final_f9_nonce':NONCE,
        'final_f9_result':refs['result'], 'final_f9_independent':refs['independent'], 'final_f9_close':refs['close'],
        'source_lock_sha256':contract['source_lock_sha256'], 'accepted_A':contract['accepted_audit_ancestor'],
        'accepted_plan':plan, 'preserved_old_coherent':result['preserved_old_coherent'],
        'current_namespace':result['current_namespace_after'],
        'observed_storage_epoch':admission['storage_epoch'],
        'observed_storage_source_binding':contract['new_storage_source_binding'],
        'current_storage_ready':review['current_storage_ready'],
        'new_storage_transition_required':review['new_storage_transition_required'],
        'new_complete_final_F9_accepted':True, 'plan_accepted_for_role_review':True,
        'original_B_passed':False, 'original_B_destination_writes_field_was_present':False,
        'original_storage_functional_passed':False, 'C_D_execution_admitted':False,
        'Android_builds':0, 'production_ready':False}
