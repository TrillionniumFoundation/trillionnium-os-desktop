"""Pure current-image qualification joins; no storage action or inferred ROOT grant.

The historical offline_chain remains unchanged and rejects these new schemas.
This module accepts only the actually introduced r1 main / r2 observers. A
future owner must separately consume a real ROOT acceptance and live admission.
"""
import base64
import hashlib
import json
import os
from recovery_core import require, encoded
from f9_authority import full_ref, terminal_binding
from offline_paged_terminal import decode_main_bundle

NONCE = '78814c8fb718710b94377114e1803382069434756144af0c057258a4f606137e'
BOOT = '97d9600f-e081-465c-9e6e-62651e09806b'
MAIN_SHA = '3228fcb1d869dd8e3ed9a65ba25565f54b3e8d98cbd48de3e87029c0e453b924'
OBSERVER_SHA = 'bb84c1282119efd83ea9c25d789ca97b53be31a2fdcc2855d44134cce40ddc03'
DECODER_SHA = '52a4acf7e8eb04e2fb30e66634376768209e1396881e5b179cdd6bd892a1b59c'
INPUT_SHA = 'c6a230a4a8c3c415397b86549876ec2671322e070449221631557167a6de5ce3'
HELPER_SHA = '396f6dd03685154bf1dde0c3c1a5291b0ec711669a9d85d79a8258210632272e'
R5_SOURCE = '04f63af431b9386d6aaf2e44627f668ccb6861945fdbc83a3546d56c600e0772'
R5_ROOT = '551dd93764f28bb0773d80e2789979ec8c14968610570e3444d9385c9a6f34f5'
UNITS = {'main': 'p4-r5-offline-readonly-e6ac-r1.service',
         'independent': 'p4-r5-offline-readonly-independent-e6ac-r2.service',
         'close': 'p4-r5-offline-readonly-close-e6ac-r2.service'}


def same(a, b, why):
    require(encoded(a) == encoded(b), why)


def whole_document(item):
    require(type(item) is dict and set(item) == {'original', 'raw'}, 'exact original and complete body')
    ref = full_ref(item['original'])
    raw = item['raw']
    require(type(raw) is bytes and len(raw) == ref['bytes'] <= 4 * 1024**2 and
            hashlib.sha256(raw).hexdigest() == ref['sha256'], 'whole original report bytes/SHA')
    return ref, json.loads(raw)


def retired_prior(value, native, h_status):
    retired = value['retired_prior']
    same(retired['native'], native, 'same original native birth')
    state = retired['actual_after']
    require(retired['cgroup_absent'] is True and state['Id'] == native['unit'] and
            state['LoadState'] == 'not-found' and state['ActiveState'] == 'inactive' and
            state['SubState'] == 'dead' and state['MainPID'] == '0' and
            state['InvocationID'] == state['ControlGroup'] == '', 'actual original unit/cgroup retired')
    rows = retired['processes']
    expected = {native['pid']: native['start_ticks'], h_status['pid']: None, h_status['owner_pid']: None}
    require(len(expected) == 3 and type(rows) is list and len(rows) == 3 and
            {r['pid'] for r in rows} == set(expected) and
            retired['outer_start_identity_independently_captured'] is False,
            'same original native and both outer PID identities, unknown births stay unknown')
    for row in rows:
        same(row['original_start'], expected[row['pid']], 'exact recorded original birth type/value')
        require(row['absent'] is True and row['current_start'] is None, 'actual final original subject absence')


def current_offline_chain(documents, terminals, expected_image, actual_inputs):
    """Reconstruct this new successful phase chain, still without new-owner authority."""
    require(set(documents) == {'main', 'independent', 'close'} and
            set(terminals) == {'main_pagination', 'independent', 'close'}, 'one exact new phase chain')
    refs, bodies = {}, {}
    for name, row in documents.items():
        refs[name], bodies[name] = whole_document(row)
    main, ind, close = (bodies[n] for n in ('main', 'independent', 'close'))
    image_ref = {k: expected_image[k] for k in ('path', 'bytes', 'sha256', 'identity')}
    full_ref(image_ref)
    require(set(expected_image) == {'path', 'bytes', 'sha256', 'identity', 'allocated_bytes'} and
            expected_image['bytes'] == 429496729600 and type(expected_image['allocated_bytes']) is int and
            expected_image['allocated_bytes'] > 0, 'actual full 400GiB current image and observed allocation')
    input_ref, inputs = whole_document(actual_inputs)
    require(input_ref['sha256'] == INPUT_SHA and inputs['nonce'] == NONCE,
            'whole original new-main INPUTS, not a replacement storage contract')
    same({k: expected_image[k] for k in ('path', 'identity', 'allocated_bytes')}, inputs['image'],
         'new measured SHA extends the exact current metadata, never the older image identity')
    for name, schema in (('main', 'p4-r5-new-offline-readonly-result-v1'),
                         ('independent', 'p4-r5-new-offline-independent-v2'),
                         ('close', 'p4-r5-new-offline-close-v2')):
        value = bodies[name]
        require(value['schema'] == schema and value['nonce'] == NONCE and value['passed'] is True and
                value['errors'] == [], 'only actually successful new offline qualification chain')
        same(value['whole_image'], expected_image, 'all phases bind the same actual current whole image')
        same(value['inputs'], input_ref, 'same full original INPUTS reference')
        require(value['source']['sha256'] == (MAIN_SHA if name == 'main' else OBSERVER_SHA) and
                value['prerequisite_source']['sha256'] == HELPER_SHA and
                value['old_source_manifest']['sha256'] == R5_SOURCE,
                'exact actually reviewed new sources and original r5 provenance')
        same(value['old_sources'], main['old_sources'], 'all seventeen original r5 sources stay identical')
        require(all(value[k] is False for k in ('original_B_passed', 'original_desktop_passed',
                'original_server_passed', 'whole_storage_lifecycle_passed', 'final_F9_successor_passed',
                'C_D_admitted', 'production_ready')), 'original failures and future role flags never promoted')
        require(value['NBD_actions'] == value['mount_actions'] == 0, 'no export/mount in qualification')
        require(value['allocation_lock_released'] is True, 'same image allocation lock released by each phase')
        if name != 'main':
            require(value['retirement_passed'] is True and value['functional_result_passed'] is True and
                    value['target_writes'] == 0 and value['allocation_lock_independently_free'] is True and
                    value['pagination_decoder']['sha256'] == DECODER_SHA,
                    'actual typed r2 observer success and explicit function/retirement separation')
            same(value['producer'], main['source'], 'observers bind exact main source fullF9')
    same(ind['source'], close['source'], 'one original r2 observer source, not a later substitute')
    same(ind['pagination_decoder'], close['pagination_decoder'], 'same complete r2 decoder ref')
    same(ind['prior_result'], refs['main'], 'independent exact original main ref')
    same(close['prior_result'], refs['independent'], 'close exact original r2 independent ref')
    same(close['main_result'], refs['main'], 'close retains exact main original')
    for observer, previous in ((ind, 'main'), (close, 'independent')):
        require(base64.b64decode(observer['prior_result_body_base64'], validate=True) == documents[previous]['raw'],
                'original prior report complete bytes preserved')
    page_ref, page_value = whole_document(terminals['main_pagination'])
    main_h, stdout, event, archive_ref = decode_main_bundle(terminals['main_pagination']['raw'], page_ref['sha256'])
    require(main_h['status']['exit_code'] == 0 and event['passed'] is True,
            'actual whole original successful main, explicitly reconstructed from pages')
    same(event['native'], main['native'], 'actual paged main native equals original report')
    same(event['result'], refs['main'], 'actual paged main result equals original ref')
    prior = ind['prior_H']
    require(prior['kind'] == 'explicit_original_main_H_pages_v1' and prior['original_single_page_json'] is False,
            'actual r2 pagination evidence, never a manufactured single-page H')
    same(prior['input'], page_ref, 'same actual pagination-input reference')
    same(prior['terminal'], main_h, 'all original page identities, offsets and full terminal totals')
    same(prior['archive'], archive_ref, 'actual original P4 archive fullF9/SHA')
    require(base64.b64decode(prior['input_body_base64'], validate=True) == terminals['main_pagination']['raw'] and
            prior['stdout_sha256'] == hashlib.sha256(stdout).hexdigest(), 'whole actual pagination input unchanged')
    ordinary_h = {}
    for name in ('independent', 'close'):
        row = terminals[name]
        ordinary_h[name] = terminal_binding(row['raw'], row['sha256'], bodies[name], refs[name],
                                           UNITS[name], BOOT, 'pocket4', True)
    close_h = close['prior_H']; actual_ind_h = json.loads(terminals['independent']['raw'])
    require(close_h['session_id'] == actual_ind_h['session_id'] and close_h['raw_sha256'] == terminals['independent']['sha256'] and
            base64.b64decode(close_h['raw_base64'], validate=True) == terminals['independent']['raw'] and
            close_h['stdout_sha256'] == ordinary_h['independent']['output_sha256'] and
            close_h['exit_code'] == 0 and close_h['output_complete'] is True,
            'close consumed the exact whole actual r2 independent H')
    retired_prior(ind, main['native'], main_h['status'])
    retired_prior(close, ind['native'], actual_ind_h['status'])
    pre = main['preflight']
    raw_pre = base64.b64decode(ind['preflight']['body_base64'], validate=True)
    pre_ref, pre_value = whole_document({'original': pre['report'], 'raw': raw_pre})
    raw_pre_h = base64.b64decode(pre['raw_H_base64'], validate=True)
    terminal_binding(raw_pre_h, pre['raw_H_sha256'], pre_value, pre_ref,
                     inputs['preflight_unit'], BOOT, 'pocket4', False)
    consumed = pre['consumed_monotonic_ns']
    require(all(type(n) is int for n in (consumed, pre_value['writer_observation_started_monotonic_ns'],
            pre_value['writer_observation_finished_monotonic_ns'], pre_value['finished_monotonic_ns'])) and
            pre_value['writer_observation_started_monotonic_ns'] <= pre_value['writer_observation_finished_monotonic_ns'] <=
            pre_value['finished_monotonic_ns'] <= consumed and
            main['started_monotonic_ns'] <= consumed <= main['finished_monotonic_ns'],
            'original actual preflight observation and main consumption ordering')
    age = consumed - pre_value['writer_observation_finished_monotonic_ns']
    require(0 <= age <= 60 * 10**9 and pre['age_at_consumption_ns'] == age and
            inputs['preflight_maximum_age_seconds'] == 60 and pre['prior_phase_is_retired'] is True and
            pre['continuous_global_writer_absence_claimed'] is False,
            'original consumed observation age, never refreshed by copying or later verification')
    same(pre_value['writer_observation'], pre['writer_observation'], 'same actual preflight writer observation')
    require(pre_value['writer_observation']['image_writers'] == pre_value['writer_observation']['unavailable'] == [],
            'preflight writer observation had no matched writers or incomplete subjects')
    same(pre_value['writer_observation']['image'], inputs['image'], 'same current preflight image metadata')
    for observer in (ind, close):
        p = observer['preflight']
        same(p['report'], pre_ref, 'same complete original preflight report in each observer')
        require(base64.b64decode(p['body_base64'], validate=True) == raw_pre and
                p['original_consumption_age_ns'] == age and p['rechecking_old_consumption_does_not_refresh_age'] is True and
                p['cgroup_absent'] is True and all(row['absent'] is True for row in p['retired_subjects']),
                'original preflight fully rechecked and retired without changing freshness')
    same(ind['fresh_offline_writer_observation']['image'], inputs['image'], 'fresh post-main metadata observation')
    require(ind['fresh_offline_writer_observation']['image_writers'] == ind['fresh_offline_writer_observation']['unavailable'] == [],
            'actual independent writer survey completed without matches or unavailable subjects')
    require(main['whole_image_bytes_read'] == expected_image['bytes'] and main['image_writes'] == 0 and
            main['selected_exports'] == main['new_storage_actions'] == 0 and main['elapsed_seconds'] < 13200 and
            main['signals'] == [] and main['passed_scope'] == 'new_readonly_fsck_and_stable_whole_original_image_only',
            'finite successful read-only whole image qualification, never repair or a new storage owner')
    held, fsck = main['held_image_descriptor'], main['e2fsck']
    require(held['access_mode'] == os.O_RDONLY and type(held['fd']) is int and held['fd'] >= 3 and
            held['child_target'] == '/proc/self/fd/' + str(held['fd']) and
            fsck['argv'] == ['/usr/sbin/e2fsck', '-f', '-n', held['child_target']] and fsck['exit_code'] == 0 and
            fsck['PIDFD_HUP'] is True and fsck['original_procdir_absent'] is True and fsck['timed_out'] is False,
            'successful exact read-only fsck on the same held original image fd and reaped child')
    same(held['identity'], expected_image['identity'], 'same image fd throughout fsck and hash')
    same(main['image_final_metadata'], {'held_identity': expected_image['identity'],
         'path_identity': expected_image['identity'], 'allocated_bytes': expected_image['allocated_bytes'],
         'payload_not_read_in_finally': True}, 'stable complete image F9 and allocation')
    require(main['root_detachment_acceptance']['sha256'] == R5_ROOT,
            'same actually accepted retired failed r5, not older detached epoch')
    for value in (ind, close):
        same(value['original_r5_proof_refs'], ind['original_r5_proof_refs'], 'same actual r5 retirement original refs')
    same(ind['original_r5_proof_refs']['root_detachment_acceptance'], main['root_detachment_acceptance'],
         'all current offline phases join actual all-r5 ROOT receipt')
    return {'schema': 'p4-current-offline-chain-ready-for-root-review-v2', 'phase_refs': refs,
            'whole_image': expected_image, 'nonce': NONCE, 'main_original_pages': page_ref,
            'observer_terminals': ordinary_h, 'r5_retirement_root': main['root_detachment_acceptance'],
            'phase_chain_passed': True, 'ROOT_accepted': False, 'new_storage_admitted': False,
            'current_namespace_qualified': False, 'C_D_admitted': False}


def qualified_current_offline(documents, terminals, expected_image, actual_inputs, root_document):
    """Bind the actual new ROOT receipt; future live admission remains separate."""
    chain = current_offline_chain(documents, terminals, expected_image, actual_inputs)
    from current_offline_root import accepted_current_offline
    return accepted_current_offline(chain, documents, terminals, actual_inputs, root_document)
