"""Actual new-offline ROOT v2 schema, without a live owner or C/D grant."""
import base64
import hashlib
import json
from f9_authority import full_ref
from recovery_core import encoded, require
from offline_paged_terminal import decode_main_bundle

ROOT_REF = {
    'path': '/home/alex/work/p4-r5-new-offline-root-acceptance-e6ac-r1.json',
    'bytes': 15090, 'sha256': '0b5882dbbc9e1e5863f1c1a2db6d1ed3130fb5a9447def0bbf583db5a62f4072',
    'identity': [66306, 31391878, 33152, 1000, 1000, 1, 15090,
                 1794795139472738640, 1794795139474866677],
}


def same(left, right, message):
    require(encoded(left) == encoded(right), message)


def accepted_current_offline(chain, documents, terminals, actual_inputs, root_document):
    from current_offline import whole_document, NONCE
    root_ref, root = whole_document(root_document)
    same(root_ref, ROOT_REF, 'actual complete ROOT original F9 and body, not a published copy identity')
    require(root['schema'] == 'p4-r5-new-offline-root-acceptance-v2' and root['nonce'] == NONCE and
            chain['schema'] == 'p4-current-offline-chain-ready-for-root-review-v2' and
            chain['phase_chain_passed'] is True and chain['ROOT_accepted'] is False,
            'the new v2 current-image phase chain and its actual ROOT acceptance')
    require(all(root[k] is True for k in ('accepted', 'functional_result_passed', 'retirement_passed',
            'all34_original_subjects_absent', 'all4_exact_cgroups_ENOENT', 'all4_units_both_scopes_not_found',
            'allocation_lock_independently_free_and_released', 'stable_image_full_F9_and_allocated_bookends')) and
            all(root[k] is False for k in ('original_B_passed', 'original_desktop_passed', 'original_server_passed',
            'whole_storage_lifecycle_passed', 'old_storage_READY_reusable', 'new_storage_admitted',
            'C_D_admitted', 'production_ready', 'runtime_qualified', 'final_F9_for_new_mount_accepted',
            'continuous_global_writer_absence_claimed')) and
            all(type(root[k]) is int and root[k] == 0 for k in
                ('new_storage_actions', 'Android_starts', 'apps_runtime_accepted', 'whole_payload_reads_by_independent_and_close')),
            'actual completed read-only qualification never admits a new owner, C/D or runtime')
    refs, values = {}, {}
    for name in ('main', 'independent', 'close'):
        refs[name], values[name] = whole_document(documents[name])
        same(refs[name], root[name + '_result'], 'ROOT exact original ' + name + ' result')
        same(refs[name], chain['phase_refs'][name], 'same completely checked phase chain')
    main, ind, close = (values[k] for k in ('main', 'independent', 'close'))
    pre_raw = base64.b64decode(ind['preflight']['body_base64'], validate=True)
    pre_ref, pre = whole_document({'original': main['preflight']['report'], 'raw': pre_raw})
    same(root['preflight_result'], pre_ref, 'ROOT original preflight ref, no refreshed observation')
    same(root['whole_image'], chain['whole_image'], 'ROOT exact newly qualified full image F9/SHA')
    require(root['readonly_fsck_exit_code'] == main['e2fsck']['exit_code'] == 0 and
            type(root['whole_image_bytes_read']) is int and
            root['whole_image_bytes_read'] == main['whole_image_bytes_read'] == 429496729600,
            'actual new successful fsck and exactly one complete 400GiB body hash')
    for root_key, report, report_key in (
        ('producer_source', main, 'source'), ('observer_source', ind, 'source'),
        ('pagination_decoder', ind, 'pagination_decoder'), ('prerequisite_source', main, 'prerequisite_source'),
        ('original_r5_source_manifest', main, 'old_source_manifest'), ('allocation_lock', main, 'allocation_lock'),
        ('original_r5_proof_refs', ind, 'original_r5_proof_refs')):
        same(root[root_key], report[report_key], 'ROOT complete source/lineage reference ' + root_key)
    same(root['inputs'], actual_inputs['original'], 'actual original INPUTS body and original identity')
    for value in (pre, ind, close):
        same(value['allocation_lock'], root['allocation_lock'], 'one unchanged original allocation lock')
    require(root['preflight_consumption_age_ns'] == main['preflight']['age_at_consumption_ns'] and
            0 <= root['preflight_consumption_age_ns'] <= 60 * 10**9,
            'ROOT preserves the originally consumed writer-survey age')

    main_h, main_stdout, _, _ = decode_main_bundle(terminals['main_pagination']['raw'],
                                                 terminals['main_pagination']['original']['sha256'])
    bundle = json.loads(terminals['main_pagination']['raw'])
    envelope = json.loads(base64.b64decode(bundle['pagination_envelope_base64'], validate=True))
    raw_page_statuses = [json.loads(base64.b64decode(p['raw_base64'], validate=True))['status']
                         for p in envelope['original_pages']]
    # The accepted decoder returns only stable identity/status fields. The ROOT
    # receipt preserves the original extra `closed` field too. Read that field
    # from the authenticated original JSON pages; do not invent it in a new H.
    for original_status in raw_page_statuses:
        same(original_status, raw_page_statuses[0], 'all actual original raw main status objects')
        same({key: original_status[key] for key in main_h['status']}, main_h['status'],
             'original page status agrees with the accepted decoder identity projection')
    hs = {'main': main_h, 'preflight': json.loads(base64.b64decode(main['preflight']['raw_H_base64'], validate=True)),
          'independent': json.loads(terminals['independent']['raw']), 'close': json.loads(terminals['close']['raw'])}
    outputs = {k: bytes.fromhex(v['bytes_hex']) for k, v in hs.items() if k != 'main'}
    outputs['main'] = main_stdout
    require(type(root['original_H']) is list and len(root['original_H']) == 4 and
            {x['phase'] for x in root['original_H']} == set(hs), 'four actual ROOT terminal identities')
    for row in root['original_H']:
        phase = row['phase']; h = hs[phase]; stdout = outputs[phase]
        original_status = raw_page_statuses[0] if phase == 'main' else h['status']
        same(row, {'phase': phase, 'session_id': h['session_id'], 'archive_path': h['archive_path'],
                   'bytes': len(stdout), 'sha256': hashlib.sha256(stdout).hexdigest(), 'status': original_status},
             'ROOT whole original terminal and exact original native launcher PID provenance')

    expected_subjects, commands = [], []
    values['preflight'] = pre
    for phase in ('preflight', 'main', 'independent', 'close'):
        value = values[phase]; native = value['native']; h = hs[phase]
        expected_subjects.append({'role': phase, 'pid': native['pid'],
            'start_ticks': str(native['start_ticks']), 'InvocationID': native['InvocationID']})
        expected_subjects += [
            {'role': phase + '-outer-owner', 'pid': h['status']['owner_pid'], 'start_ticks': None},
            {'role': phase + '-outer-child', 'pid': h['status']['pid'], 'start_ticks': None}]
        for command in value['commands']:
            require(command['exit_code'] == 0 and command['PIDFD_HUP'] is True and
                    command['original_procdir_absent'] is True and command['timed_out'] is False,
                    'every actual command completed and was reaped, not only the fsck child')
            expected_subjects.append({'role': phase + '-command', 'pid': command['pid'],
                                      'start_ticks': command['start_ticks']})
            commands.append(command)
    same(root['original_subjects'], expected_subjects, 'all four native, eight outer and twenty-two original command identities')
    require(len(expected_subjects) == len({x['pid'] for x in expected_subjects}) == 34 and len(commands) == 22,
            'exact actual subject and command inventories')
    same(root['complete_original_logs'], {'commands': 22, 'main_original_paged_H_stdout_bytes': len(main_stdout),
          'progress_streams': 1, 'stdout_stderr_streams': 44}, 'ROOT whole command/log coverage')
    log_groups = [pre['full_command_logs'], ind['full_producer_logs'], ind['full_observer_logs'], close['full_observer_logs']]
    logs = {}
    for group in log_groups:
        for path, item in group.items():
            ref = full_ref(item['ref']); raw = base64.b64decode(item['body_base64'], validate=True)
            require(ref['path'] == path and len(raw) == ref['bytes'] and
                    hashlib.sha256(raw).hexdigest() == ref['sha256'], 'complete original command/progress log body')
            if path in logs: same(logs[path], ref, 'same repeated original log reference')
            logs[path] = ref
    require(len(logs) == 45, 'exact unique actual complete log bodies')
    for command in commands:
        for name in ('stdout', 'stderr'):
            same(logs[command[name]['path']], command[name], 'every actual command owns its exact two complete streams')
    return {'schema': 'p4-current-offline-root-qualified-input-v2', 'phase_refs': refs,
            'preflight_result': pre_ref, 'root_acceptance': root_ref, 'whole_image': chain['whole_image'],
            'allocation_lock': root['allocation_lock'], 'original_r5_proof_refs': root['original_r5_proof_refs'],
            'main_original_pages': chain['main_original_pages'], 'nonce': NONCE,
            'phase_chain_passed': True, 'ROOT_accepted': True, 'all_original_actors_retired': True,
            'fresh_image_metadata_and_writer_check_required': True,
            'new_storage_admitted': False, 'current_namespace_qualified': False,
            'final_F9_for_new_mount_accepted': False, 'C_D_admitted': False, 'production_ready': False}
