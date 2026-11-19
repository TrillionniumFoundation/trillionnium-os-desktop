"""Pure r5 retirement prerequisite: no current whole-image, clean-FS or READY grant."""
import hashlib
import json
from f9_authority import full_ref
from recovery_core import encoded, require

ROOT_PATH = '/home/alex/work/p4-storage-r5-complete-retirement-root-acceptance-e6ac-r1.json'
ROOT_SHA = '551dd93764f28bb0773d80e2789979ec8c14968610570e3444d9385c9a6f34f5'
OLD_SOURCE = '04f63af431b9386d6aaf2e44627f668ccb6861945fdbc83a3546d56c600e0772'
OLD_ADMISSION = 'b9c754e35530394b0ccbf51da5a7259bc9863a11dd264266a98440e436808e20'
OLD_NONCE = 'ec078d295a4ea48154b584f3aa0b7400cbd9c0178075d52baec2d6fbf95eb804'
REPORTS = {'desktop_ROOT_receipt', 'desktop_independent_report',
           'server_independent_report', 'server_original_failure'}


def same(a, b, why):
    require(encoded(a) == encoded(b), why)


def whole_body(ref, raw):
    require(type(ref) is dict and set(ref) in (
            {'path', 'bytes', 'sha256', 'identity'},
            {'path', 'bytes', 'sha256', 'identity', 'version'}),
            'one exact original retirement ref, including any declared version')
    full_ref({k: ref[k] for k in ('path', 'bytes', 'sha256', 'identity')})
    if 'version' in ref:
        require(ref['version'] == ':'.join(str(ref['identity'][i]) for i in (0, 1, 6, 7, 8)),
                'declared original version equals all corresponding F9 integer fields')
    require(type(raw) is bytes and len(raw) == ref['bytes'] <= 1024 ** 2 and
            hashlib.sha256(raw).hexdigest() == ref['sha256'], 'whole original retirement body and F9')
    return json.loads(raw)


def retired_epoch_fields(authority, root, reports):
    require(authority['schema'] == 'p4-c-d-observed-plan-authority-v2' and
            authority['new_complete_final_F9_accepted'] is True and
            authority['plan_accepted_for_role_review'] is True and
            authority['current_storage_ready'] is False and
            authority['new_storage_transition_required'] is True and
            authority['C_D_execution_admitted'] is False, 'historical observed plan only')
    epoch, binding = authority['observed_storage_epoch'], authority['observed_storage_source_binding']
    require(root['schema'] == 'p4-storage-r5-complete-retirement-root-acceptance-v1' and
            root['source_manifest_sha256'] == epoch['source_manifest_sha256'] ==
            binding['source_manifest_sha256'] == OLD_SOURCE and
            root['original_admission_sha256'] == epoch['admission']['sha256'] == OLD_ADMISSION and
            root['original_nonce'] == epoch['nonce'] == binding['nonce'] == OLD_NONCE,
            'the retired owner is exactly the observed F9 epoch')
    require(all(root[k] is True for k in ('accepted', 'retirement_passed',
            'all_original_storage_actors_retired', 'reserve_failure_preserved', 'desktop_EIO_preserved',
            'desktop_ROOT_historical_server_false_preserved',
            'controller_start_from_original_native_proc_identity_not_systemd_timestamp',
            'server_retirement_source_original_unchanged')) and
            all(root[k] is False for k in ('functional_result_passed', 'original_desktop_functional_passed',
            'original_server_functional_passed', 'image_payload_rehashed', 'old_storage_READY_reusable',
            'old_B_passed', 'production_ready', 'runtime_qualified',
            'normal_umount_inferred_from_namespace_disappearance',
            'original_projection_journal_absent_claim_accepted_as_absence')) and
            all(type(root[k]) is int and root[k] == 0 for k in
                ('new_storage_starts', 'C_D_starts', 'Android_starts')),
            'retirement never converts the failed epoch or journal absence into success')
    same(root['original_server_errors'],
         ["RuntimeError('Pocket4 live 5 GiB RAM and 256 GiB disk reserves')"], 'actual reserve error')
    same(root['original_desktop_errors'], ["retirement: OSError(5, 'Input/output error')"], 'actual desktop EIO')
    owner = epoch['owner_native']; original = root['original_subject_generations']['desktop_controller']
    require(original['host'] == 'desktop' and original['boot_id'] == owner['boot'] and
            original['pid'] == owner['pid'] and original['start_ticks'] == owner['start_ticks'] and
            original['invocation'] == owner['InvocationID'] and original['unit'] == owner['unit'] and
            original['cgroup'] == owner['cgroup'], 'actual original held owner birth and invocation')
    desktop, server = reports['desktop_independent_report'], reports['server_independent_report']
    for proof, role in ((desktop, 'controller'), (server, 'server')):
        require(proof['schema'] == 'p4-production651-nbd-independent-retirement-v1' and
                proof['role'] == role and proof['source_manifest_sha256'] == OLD_SOURCE and
                proof['admission_sha256'] == OLD_ADMISSION and proof['nonce'] == OLD_NONCE and
                proof['retirement_passed'] is True and proof['functional_result_passed'] is False and
                proof['cgroup_absent'] is True and proof['source_and_tools_unchanged'] is True and
                proof['actual_after']['LoadState'] == 'not-found' and proof['actual_after']['MainPID'] == '0',
                'complete independent retirements preserve their failed functional results')
    same(desktop['original'], original['original_dispatch_ref'], 'actual original controller dispatch')
    same(desktop['result'], original['origin']['ref'], 'controller birth came from its original native result')
    same(desktop['result'], reports['desktop_ROOT_receipt']['original_records']['desktop_result'],
         'desktop ROOT and original independent refer to the same full result')
    same(server['result'], root['server_original_failure']['original'], 'actual complete server failure')
    failure = reports['server_original_failure']
    require(failure['server_lifecycle_clean'] is False and
            failure['errors'] == root['original_server_errors'] and
            failure['minimum_disk_free'] == 274849148928 and failure['minimum_MemAvailable'] == 12678107136,
            'disk reserve error is preserved independently of sufficient RAM')
    metadata = root['offline_original_image_metadata_only']
    same(metadata, server['offline_original_image'], 'same actual post-retirement descriptor observation')
    same(metadata['image']['identity'], failure['image_after']['identity'], 'same new image F9, not old offline F9')
    require(metadata['whole_image_hash_not_computed_here'] is True and
            metadata['image_writers'] == metadata['unavailable'] == [] and
            metadata['image']['identity'][6] == 429496729600 and
            metadata['image']['identity'][7:] == [1794779583308834355, 1794779583308834355] and
            'sha256' not in metadata['image'], 'metadata-only lineage is not a whole SHA or clean filesystem')
    return metadata


def retired_observed_epoch(authority, root_ref, raw, original_reports):
    require((root_ref['path'], root_ref['bytes'], root_ref['sha256']) == (ROOT_PATH, 87409, ROOT_SHA),
            'actual whole ROOT all-r5 retirement acceptance')
    root = whole_body(root_ref, raw)
    require(set(original_reports) == REPORTS, 'four complete accepted subordinate reports')
    reports = {}
    for key, item in original_reports.items():
        require(set(item) == {'original_host', 'original', 'raw'} and
                item['original_host'] == root[key]['original_host'], 'explicit actual original provenance')
        same(item['original'], root[key]['original'], 'full original F9 and SHA: ' + key)
        reports[key] = whole_body(item['original'], item['raw'])
    metadata = retired_epoch_fields(authority, root, reports)
    return {'schema': 'p4-observed-plan-retired-storage-prerequisite-v1',
            'observed_plan_root': authority['root_acceptance'], 'retirement_root': root_ref,
            'original_storage_source_manifest_sha256': OLD_SOURCE,
            'original_storage_admission_sha256': OLD_ADMISSION, 'original_storage_nonce': OLD_NONCE,
            'revoked_owner_ready': authority['observed_storage_epoch']['owner_ready'],
            'revoked_server_ready': authority['observed_storage_epoch']['server_ready'],
            'offline_metadata_lineage': metadata, 'all_original_actors_retired': True,
            'original_storage_functional_passed': False, 'old_READY_reusable': False,
            'current_image_whole_SHA_qualified': False, 'current_filesystem_clean_qualified': False,
            'new_storage_epoch_admitted': False, 'C_D_execution_admitted': False, 'production_ready': False}
