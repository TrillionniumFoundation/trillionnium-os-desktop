"""Pure typed joins; callers first pin complete bodies and all original F9 fields.

Cross-host copies remain separate refs. These gates never accept the failed B
as a successful prior phase, and do not by themselves grant C/D permission.
"""
import base64
import hashlib
import json
import pathlib
import stat
from recovery_core import encoded, require, sha

LEAVES = {'reuse-index.sqlite', 'DESTINATION-OBSERVED.ndjson', 'REUSE-AND-GAP-PLAN.ndjson'}
FALSE_RECORD_FLAGS = ('original_B_passed', 'original_storage_functional_passed',
                      'recovery_plan_accepted', 'current_destination_F9_rechecked',
                      'C_D_admitted', 'production_ready')


def terminal_binding(raw, expected_sha, value, result_ref, unit, boot,
                     host='desktop', retirement_event=False):
    """Bind the original complete H read text; never reconstruct its large ints."""
    sha(expected_sha)
    require(type(raw) is bytes and len(raw) <= 65536 and
            hashlib.sha256(raw).hexdigest() == expected_sha,
            'bounded complete original H read raw bytes and exact SHA')
    h = json.loads(raw)
    status = h['status']
    body = bytes.fromhex(h['bytes_hex'])
    require(host in ('desktop', 'pocket4') and h['host'] == host and h['offset'] == 0 and
            h['output_complete'] is True and h['truncated_before_offset'] is False and
            status['state'] == 'exited' and status['exit_code'] == 0 and
            status['capture_error'] is None and status['output_complete'] is True and status['boot'] == boot,
            'actual original zero complete terminal on the same fixed host boot')
    require(len(body) == h['next_offset'] == h['available_end'] == status['bytes_seen'] == status['bytes_stored'] and
            hashlib.sha256(body).hexdigest() == h['chunk_sha256'],
            'complete captured stdout bytes, offsets and SHA')
    native = value['native']
    require(native['unit'] == unit and native['boot'] == boot and
            type(native['pid']) is int and native['pid'] > 1 and
            type(native['start_ticks']) in (str, int) and int(native['start_ticks']) > 0 and
            type(native['InvocationID']) is str and len(native['InvocationID']) == 32 and
            all(c in '0123456789abcdef' for c in native['InvocationID']),
            'actual original report native unit, boot and generation')
    events = [json.loads(line) for line in body.decode('utf-8').splitlines() if line.startswith('{')]
    event_fields = {'passed', 'native', 'result'}
    if retirement_event: event_fields.add('functional_result_passed')
    require(events and set(events[-1]) == event_fields and
            events[-1]['passed'] is True and encoded(events[-1]['native']) == encoded(native) and
            encoded(events[-1]['result']) == encoded(result_ref),
            'last original H JSON event binds the exact complete report and native')
    if retirement_event:
        require(events[-1]['functional_result_passed'] is True,
                'offline successful functional outcome remains explicit in retirement event')
    require(type(h['session_id']) is str and h['session_id'].startswith('dpty-') and
            all(type(status[k]) is int and status[k] > 1 for k in ('pid', 'owner_pid')),
            'actual terminal identity, without inventing unavailable outer start ticks')
    return {'terminal_session_id': h['session_id'], 'raw_sha256': expected_sha,
            'output_sha256': h['chunk_sha256'], 'native': native,
            'original_pids': [native['pid'], status['pid'], status['owner_pid']],
            'outer_start_identity_independently_captured': False, 'result': result_ref}

def full_ref(value):
    require(type(value) is dict and set(value) == {'path', 'bytes', 'sha256', 'identity'},
            'exact full original ref without copy/host substitutions')
    p = value['path']
    require(type(p) is str and p.startswith('/') and pathlib.PurePosixPath(p).as_posix() == p and
            all(part not in ('.', '..', '') for part in p.split('/')[1:]) and '\0' not in p,
            'exact absolute original reference path')
    f = value['identity']
    require(type(f) is list and len(f) == 9 and all(type(x) is int for x in f) and
            f[0] > 0 and f[1] > 0 and stat.S_ISREG(f[2]) and f[5] == 1 and
            type(value['bytes']) is int and 0 <= value['bytes'] == f[6],
            'full nine-field single-link identity and byte length')
    sha(value['sha256'])
    return value

def record_chain(main, independent, close, refs, expected_source_manifest, accepted_A,
                 terminal_inputs, units, boot):
    require(set(refs) == {'seal', 'independent', 'close'}, 'exact three record-stage refs')
    for ref in refs.values(): full_ref(ref)
    full_ref(expected_source_manifest)
    require(set(terminal_inputs) == set(units) == {'seal', 'independent', 'close'},
            'three original raw H reads and three fixed native units')
    terminals = {}
    for mode, value in (('seal', main), ('independent', independent), ('close', close)):
        require(value['schema'] == 'p4-failed-b-first-pass-' + mode + '-v1' and
                value['mode'] == mode and value['passed'] is True and
                encoded(value['source_manifest']) == encoded(expected_source_manifest),
                'same successful real record source and exact phase ' + mode)
        require(all(value[k] is False for k in FALSE_RECORD_FLAGS) and
                all(type(value[k]) is int and value[k] == 0 for k in
                    ('target_opens', 'target_writes', 'new_storage_actions')),
                'record proof retains failed B and has no target/storage qualification')
        terminals[mode] = terminal_binding(terminal_inputs[mode]['raw'], terminal_inputs[mode]['sha256'],
                                           value, refs[mode], units[mode], boot)
    require(encoded(independent['prior_evidence']['result']) == encoded(refs['seal']) and
            encoded(close['prior_evidence']['result']) == encoded(refs['independent']), 'actual record-phase retirement chain')
    for successor, prior_mode in ((independent, 'seal'), (close, 'independent')):
        proof, actual = successor['prior_evidence'], terminals[prior_mode]
        for key in ('terminal_session_id', 'raw_sha256', 'output_sha256', 'native', 'result',
                    'outer_start_identity_independently_captured'):
            require(encoded(proof[key]) == encoded(actual[key]), 'original H and independently retired report join ' + key)
        require(encoded(proof['original_pids_absent']) == encoded(actual['original_pids']),
                'independent successor covered the original native and both outer PIDs')
    require(encoded(main['accepted_A']) == encoded(independent['accepted_A']) == encoded(accepted_A),
            'same distinct original accepted A ancestor')
    require(main['original_B_destination_writes_field_present'] is False and
            independent['original_B_destination_writes_field_present'] is False,
            'missing old top-level destination_writes stays missing')
    copies = main['sealed_copies']
    require(type(copies) is dict and set(copies) == LEAVES and
            encoded(independent['sealed_copies']) == encoded(close['sealed_copies']) == encoded(copies) and
            encoded(independent['original_records']) == encoded(main['original_records']) and
            set(main['original_records']) == LEAVES, 'same three complete original and copied records')
    for leaf in sorted(LEAVES):
        copied = full_ref(copies[leaf]); original = full_ref(main['original_records'][leaf])
        require(pathlib.PurePosixPath(copied['path']).name == leaf and
                copied['identity'][0] == original['identity'][0] == 2067 and
                copied['identity'][3:6] == [0, 0, 1] and stat.S_IMODE(copied['identity'][2]) == 0o444 and
                original['identity'][3:6] == [1000, 1000, 1] and
                copied['identity'][:2] != original['identity'][:2] and
                (copied['bytes'], copied['sha256']) == (original['bytes'], original['sha256']),
                'original and sealed copy retain distinct complete identities')
    validation = main['validation']
    require(encoded(independent['validation']) == encoded(close['validation']) == encoded(validation) and
            validation['schema'] == 'p4-failed-b-first-pass-record-validation-v1' and
            validation['passed'] is True and validation['conflict_zero_rechecked'] is True and
            validation['counts']['conflict'] == 0 and validation['all_A_rows_and_parents_rechecked'] is True and
            validation['all_actions_recomputed'] is True and validation['SQLite_changes'] == 0,
            'actual complete row/action/conflict-zero validation')
    require(set(validation['counts']) == {'reuse', 'metadata', 'missing', 'partial_file', 'conflict'} and
            all(type(n) is int and n >= 0 for n in validation['counts'].values()) and
            type(validation['SQLite_changes']) is int and
            main['all_original_and_copy_F9_stable'] is True and
            independent['all_original_and_copy_F9_stable'] is True,
            'typed complete counts and both actual stable whole-record observations')
    require(validation['current_destination_F9_rechecked'] is False and
            validation['current_namespace_or_retained_closure_qualified'] is False and
            validation['recovery_plan_accepted'] is False, 'record proof is not final metadata/plan authority')
    require(main['ordinary_prerequisite_H'] == independent['ordinary_prerequisite_H'] and
            main['ordinary_prerequisite'] == independent['ordinary_prerequisite'],
            'same original ordinary H prerequisite independently bound')
    return {'schema': 'p4-final-f9-accepted-record-inputs-v1', 'phase_refs': refs, 'terminals': terminals,
            'sealed_copies': copies, 'original_records': main['original_records'],
            'validation': validation, 'accepted_A': accepted_A,
            'original_B_passed': False, 'recovery_plan_accepted': False}

def offline_chain(main, independent, close, refs, expected_image, expected_nonce,
                  terminal_inputs, units, boot):
    require(set(refs) == {'main', 'independent', 'close'}, 'exact new offline original phase refs')
    for ref in refs.values(): full_ref(ref)
    require(set(terminal_inputs) == set(units) == {'main', 'independent', 'close'},
            'all three actual offline full terminal reads and fixed units')
    require(set(expected_image) == {'path', 'bytes', 'sha256', 'identity', 'allocated_bytes'} and
            type(expected_image['allocated_bytes']) is int and expected_image['allocated_bytes'] > 0,
            'actual whole raw image reference and separately observed allocation')
    full_ref({k: expected_image[k] for k in ('path', 'bytes', 'sha256', 'identity')})
    for schema, value in (('p4-b5-new-offline-readonly-result-v1', main),
                          ('p4-b5-new-offline-independent-v1', independent),
                          ('p4-b5-new-offline-close-v1', close)):
        require(value['schema'] == schema and value['passed'] is True and
                value['nonce'] == expected_nonce and encoded(value['whole_image']) == encoded(expected_image),
                'same new offline generation and exact stable whole image')
        require(all(value[k] is False for k in ('original_B_passed', 'original_desktop_passed',
                'original_server_passed', 'whole_storage_lifecycle_passed',
                'final_F9_successor_passed', 'C_D_admitted', 'production_ready')),
                'offline qualification preserves original functional failures')
        require(all(type(value[k]) is int and value[k] == 0 for k in ('NBD_actions', 'mount_actions')),
                'offline phase did not export or mount the image')
    terminals = {mode: terminal_binding(terminal_inputs[mode]['raw'], terminal_inputs[mode]['sha256'],
                                        value, refs[mode], units[mode], boot, 'pocket4', mode != 'main')
                 for mode, value in (('main', main), ('independent', independent), ('close', close))}
    require(main['image_writes'] == 0 and main['whole_image_bytes_read'] == expected_image['bytes'] == 429496729600 and
            main['e2fsck']['exit_code'] == 0 and main['e2fsck']['timed_out'] is False,
            'actual read-only whole 400GiB SHA and successful finite fsck')
    require(independent['retirement_passed'] is True and close['retirement_passed'] is True and
            independent['functional_result_passed'] is True and close['functional_result_passed'] is True and
            encoded(independent['prior_result']) == encoded(refs['main']) and
            encoded(close['prior_result']) == encoded(refs['independent']) and
            encoded(close['main_result']) == encoded(refs['main']), 'complete actual offline original result/retirement joins')
    for successor, prior_mode in ((independent, 'main'), (close, 'independent')):
        h, actual = successor['prior_H'], terminals[prior_mode]
        require(h['raw_sha256'] == actual['raw_sha256'] and
                base64.b64decode(h['raw_base64'], validate=True) == terminal_inputs[prior_mode]['raw'] and
                h['session_id'] == actual['terminal_session_id'] and
                h['stdout_sha256'] == actual['output_sha256'] and h['exit_code'] == 0 and
                h['output_complete'] is True, 'actual complete offline H independently consumed unchanged')
        retired = successor['retired_prior']
        state = retired['actual_after']
        require(encoded(retired['native']) == encoded(actual['native']) and retired['cgroup_absent'] is True and
                state['LoadState'] == 'not-found' and state['ActiveState'] == 'inactive' and
                state['SubState'] == 'dead' and state['MainPID'] == '0' and
                state['InvocationID'] == state['ControlGroup'] == '',
                'same offline original generation and actual unit/cgroup retirement')
        rows = retired['processes']
        require(len(rows) == 3 and {r['pid'] for r in rows} == set(actual['original_pids']) and
                all(r['absent'] is True and r['current_start'] is None for r in rows) and
                retired['outer_start_identity_independently_captured'] is False,
                'native and both original outer PIDs absent, without invented outer starts')
        for row in rows:
            expected_start = actual['native']['start_ticks'] if row['pid'] == actual['native']['pid'] else None
            require(encoded(row['original_start']) == encoded(expected_start), 'exact original recorded start identity')
    require(main['allocation_lock_released'] is True and
            independent['allocation_lock_independently_free'] is True and
            close['allocation_lock_independently_free'] is True,
            'actual original image allocation lock independently released')
    return {'schema': 'p4-final-f9-accepted-offline-inputs-v1', 'phase_refs': refs, 'terminals': terminals,
            'whole_image': expected_image, 'offline_nonce': expected_nonce,
            'original_B_passed': False, 'current_namespace_qualified': False}
