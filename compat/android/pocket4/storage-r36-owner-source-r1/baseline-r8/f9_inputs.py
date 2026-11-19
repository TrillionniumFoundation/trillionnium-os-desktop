"""Read the fixed small proof copies; never open the image or target tree."""
import hashlib
import json
import pathlib
import stat

from common import pin
from f9_authority import full_ref, record_chain, offline_chain
from recovery_core import encoded, require

P = pathlib.Path
SMALL_LIMIT = 2 * 1024 ** 2
TOTAL_SMALL_LIMIT = 16 * 1024 ** 2


def root_json(path, expected=None, limit=SMALL_LIMIT):
    ref, raw = pin(path, expected, limit=limit)
    full_ref(ref)
    require(ref['identity'][3:6] == [0, 0, 1] and
            stat.S_IMODE(ref['identity'][2]) == 0o444,
            'exact root-sealed single-link small input')
    return ref, json.loads(raw)


def root_acceptances(contract, records, offline, values):
    """The two functional successes do not promote any original failed actor."""
    record_root = values['records.root']
    require(record_root['schema'] == 'p4-failed-b-first-pass-record-chain-root-acceptance-v1' and
            record_root['accepted'] is True and
            encoded(record_root['originals']) == encoded(records['phase_refs']) and
            encoded(record_root['accepted_A']) == encoded(contract['accepted_audit_ancestor']) and
            encoded(record_root['sealed_copies']) == encoded(records['sealed_copies']) and
            encoded(record_root['validation']) == encoded(records['validation']) and
            encoded(record_root['source_manifest']) == encoded(contract['proof_inputs']['record_source_manifest']),
            'actual ROOT record acceptance joins complete original reports, copies and A')
    require(all(record_root[key] is False for key in
                ('original_B_passed', 'original_storage_functional_passed', 'recovery_plan_accepted',
                 'current_destination_F9_rechecked', 'current_namespace_or_retained_closure_qualified',
                 'C_D_admitted', 'production_ready', 'new_storage_or_image_actions_admitted')),
            'record ROOT scope remains independent first-pass records only')
    checked = record_root['root_verification']
    require(checked['four_actual_H_full_zero'] is True and
            checked['four_units_both_scopes_not_found'] is True and checked['four_exact_cgroups_missing'] is True,
            'record ROOT actual terminal and final observer retirement evidence')
    for mode, terminal in records['terminals'].items():
        row = record_root['terminals'][mode]
        require(row['session_id'] == terminal['terminal_session_id'] and
                row['original_raw_sha256'] == terminal['raw_sha256'] and
                row['stdout_sha256'] == terminal['output_sha256'] and row['exit_code'] == 0 and
                row['output_complete'] is True and encoded(row['native']) == encoded(terminal['native']) and
                row['original_pids'] == terminal['original_pids'] and
                set(row['original_pids']) <= set(checked['retired_original_pids']),
                'actual ROOT independently consumed and retired this exact record terminal')
    offline_root = values['offline.root']
    require(offline_root['schema'] == 'p4-root-new-offline-qualification-acceptance-v1' and
            offline_root['accepted'] is True and
            encoded(offline_root['originals']) == encoded([offline['phase_refs'][k]
                    for k in ('main', 'independent', 'close')]) and
            encoded(offline_root['whole_image']) == encoded(offline['whole_image']) and
            offline_root['e2fsck_exit_code'] == 0 and
            offline_root['original_alloc_lock_independently_released'] is True and
            offline_root['three_cgroups_absent'] is True and
            offline_root['three_units_both_scopes_absent'] is True,
            'actual new offline ROOT acceptance joins stable image and full retired chain')
    require(all(offline_root[k] is False for k in ('original_B_passed', 'original_desktop_passed',
            'original_server_passed', 'whole_storage_lifecycle_passed', 'final_F9_successor_passed',
            'production_ready', 'new_storage_or_Android_actions_admitted')),
            'offline ROOT acceptance retains every previous functional failure')
    require(len(offline_root['full_terminal_digests']) == 3, 'exact three ROOT offline terminal digests')
    for mode, row in zip(('main', 'independent', 'close'), offline_root['full_terminal_digests']):
        actual = offline['terminals'][mode]
        require(row['session_id'] == actual['terminal_session_id'] and row['exit_code'] == 0 and
                row['sha256'] == actual['output_sha256'] and
                set(actual['original_pids']) <= set(offline_root['fresh_subject_pids_absent']),
                'actual offline terminal and final retirement independently covered by ROOT')
    detached = values['detachment.root']
    require(detached['schema'] == 'p4-b5-storage-failed-functional-detachment-root-acceptance-v1' and
            detached['retirement_passed'] is True and
            all(detached[k] is False for k in ('original_B_passed', 'original_desktop_passed',
                    'original_server_passed', 'whole_storage_lifecycle_passed', 'production_ready')),
            'original failed storage detached only, never reclassified as successful')
    return {'record_root': contract['proof_inputs']['record_root_acceptance'],
            'offline_root': contract['proof_inputs']['offline_root_acceptance'],
            'detachment_root': contract['proof_inputs']['storage_detachment_root_acceptance']}


def audit_and_failure(contract, values, main):
    a = contract['accepted_audit_ancestor']
    result, retired = values['A.result'], values['A.retirement']
    require(result['schema'] == 'p4-production651-recovery-result-v1' and
            retired['schema'] == 'p4-production651-recovery-retirement-v1' and
            result['phase'] == retired['phase'] == 'audit' and
            result['passed'] is True and retired['retirement_passed'] is True and
            retired['functional_passed'] is True and encoded(retired['result']) == encoded(a['result']) and
            result['source_manifest_sha256'] == retired['source_manifest_sha256'] == a['source_manifest_sha256'] and
            result['nonce'] == retired['nonce'] == a['nonce'] and a['nonce'] != contract['nonce'] and
            result['source_lock_sha256'] == retired['source_lock_sha256'] == contract['source_lock_sha256'] and
            result['source_writes'] == 0 and result['own_source_locks_closed'] is True and
            encoded(result['authenticated_source_manifest']) == encoded(a['authenticated_manifest']) and
            result['members'] == a['members'] and result['payload_bytes'] == a['payload_bytes'],
            'complete unchanged accepted A remains the sole historical audit ancestor')
    b, retirement = values['B.result'], values['B.retirement']
    require(b['schema'] == 'p4-production651-recovery-result-v1' and b['phase'] == 'reuse' and
            b['passed'] is False and b['source_manifest_sha256'] == contract['historical_old_B_source_sha256'] and
            b['nonce'] == '50e61f3b9db070a26e5841a273cf9bcf340a2a6617f35b0d1499645b8f0a7c22' and
            b['source_lock_sha256'] == contract['source_lock_sha256'] and b['source_writes'] == 0 and
            'destination_writes' not in b and
            retirement['schema'] == 'p4-production651-recovery-retirement-v1' and
            retirement['phase'] == 'reuse' and retirement['retirement_passed'] is True and
            retirement['functional_passed'] is False and retirement['cgroup_absent'] is True and
            retirement['source_manifest_sha256'] == b['source_manifest_sha256'] and
            retirement['nonce'] == b['nonce'] and
            encoded(retirement['result']) == encoded(contract['original_B_result']),
            'the exact EIO predecessor remains failed and actually retired')
    metrics = b['read_only_scan_metrics']
    require(type(metrics) is list and len(metrics) == 2 and metrics[0]['body_hash'] is True and
            metrics[0]['traversal_completed'] is True and metrics[0]['worker_threads_joined'] is True and
            metrics[1]['body_hash'] is False and metrics[1]['traversal_completed'] is False and
            encoded(main['first_pass_metrics']) == encoded(metrics[0]),
            'only the complete first pass is sealed; failed second pass is not a cursor')
    return metrics[0]


def expected_small_refs(contract):
    proofs = contract['proof_inputs']
    result = {family + '.' + mode: row['original']
              for family in ('records', 'offline') for mode, row in proofs[family].items()}
    result.update({'records.root': proofs['record_root_acceptance'],
                   'offline.root': proofs['offline_root_acceptance'],
                   'detachment.root': proofs['storage_detachment_root_acceptance'],
                   'B.result': contract['original_B_result'],
                   'B.retirement': contract['original_B_retirement']})
    for key in ('result', 'retirement', 'root_acceptance', 'source_manifest', 'source_contract'):
        result['A.' + key] = contract['accepted_audit_ancestor'][key]
    return result


def load_fixed_inputs(contract, data, checkpoint):
    expected = expected_small_refs(contract)
    require(data['schema'] == 'p4-final-f9-sealed-small-inputs-v1' and data['nonce'] == contract['nonce'] and
            set(data['copies']) == set(expected) and set(data['terminal_copies']) == {'records', 'offline'},
            'one complete root-sealed finite proof set for the new final-F9 phase')
    parent = P(contract['hosts']['desktop']['root']) / 'inputs/final_f9'
    total = 0; seen = set(); refs = {}; values = {}

    def read_copy(ref):
        nonlocal total
        full_ref(ref)
        require(P(ref['path']).parent == parent and ref['path'] not in seen and
                ref['bytes'] <= SMALL_LIMIT and ref['identity'][3:6] == [0, 0, 1] and
                stat.S_IMODE(ref['identity'][2]) == 0o444,
                'one fixed flat root-sealed small proof copy, no target path')
        total += ref['bytes']; require(total <= TOTAL_SMALL_LIMIT, 'bounded total proof bytes')
        seen.add(ref['path']); checkpoint()
        actual, raw = pin(ref['path'], ref, limit=SMALL_LIMIT)
        require(encoded(actual) == encoded(ref), 'exact copied proof path, body and complete F9')
        checkpoint()
        return raw

    for label in sorted(expected):
        spec = data['copies'][label]
        require(set(spec) == {'original', 'copy'} and
                encoded(full_ref(spec['original'])) == encoded(full_ref(expected[label])),
                'exact original provenance, not the identity of an earlier copy')
        raw = read_copy(spec['copy'])
        require((len(raw), hashlib.sha256(raw).hexdigest()) ==
                (spec['original']['bytes'], spec['original']['sha256']),
                'whole copied proof agrees with its independently pinned original')
        refs[label] = spec; values[label] = json.loads(raw)
    inputs = {}
    for family in ('records', 'offline'):
        require(set(data['terminal_copies'][family]) == set(contract['proof_inputs'][family]),
                'all original terminal phases explicitly copied')
        inputs[family] = {}
        for mode, spec in data['terminal_copies'][family].items():
            original_sha = contract['proof_inputs'][family][mode]['terminal_raw_sha256']
            require(set(spec) == {'source_kind', 'sha256', 'copy'} and
                    spec['source_kind'] == 'original-tool-H-read-raw' and spec['sha256'] == original_sha and
                    spec['copy']['sha256'] == original_sha,
                    'raw H bytes remain tool-origin evidence, without invented original file F9')
            inputs[family][mode] = {'raw': read_copy(spec['copy']), 'sha256': original_sha}
    family_refs = {family: {mode: row['original'] for mode, row in contract['proof_inputs'][family].items()}
                   for family in ('records', 'offline')}
    units = {family: {mode: row['unit'] for mode, row in contract['proof_inputs'][family].items()}
             for family in ('records', 'offline')}
    records = record_chain(*(values['records.' + k] for k in ('seal', 'independent', 'close')),
                           family_refs['records'], contract['proof_inputs']['record_source_manifest'],
                           contract['accepted_audit_ancestor'], inputs['records'], units['records'],
                           contract['hosts']['desktop']['boot'])
    offline = offline_chain(*(values['offline.' + k] for k in ('main', 'independent', 'close')),
                            family_refs['offline'], contract['offline_image'], contract['offline_nonce'],
                            inputs['offline'], units['offline'], contract['hosts']['pocket4']['boot'])
    roots = root_acceptances(contract, records, offline, values)
    first = audit_and_failure(contract, values, values['records.seal'])
    checkpoint()
    return {'schema': 'p4-final-f9-fixed-proof-validation-v1', 'records': records, 'offline': offline,
            'root_acceptances': roots, 'small_copy_refs': refs,
            'terminal_copy_refs': data['terminal_copies'], 'small_bytes_read': total,
            'first_pass_metrics': first, 'original_B_passed': False,
            'original_storage_functional_passed': False, 'current_F9_passed': False,
            'recovery_plan_accepted': False, 'C_D_admitted': False, 'target_or_image_opens': 0}
