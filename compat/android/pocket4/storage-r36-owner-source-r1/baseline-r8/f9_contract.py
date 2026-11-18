"""One new final-F9 contract; incomplete proposals cannot reach any actor."""
from f9_authority import full_ref
from f9_lease import ROLE, OWNER, FULL_ENVELOPE_SECONDS, MINIMUM_REMAINING_SECONDS
from recovery_core import require, sha, encoded

NONCE = 'ad8546f4bb7e18728839f877b3800cf4d48825ec8f39e33078c4a1961f7f142f'
OLD_B_SOURCE = '3d69d078be546f147307660ff17ff6372c486de2ed47e0fd1e6fc6c6df45eb56'
OLD_B_CONTRACT = '15618c1fb2f39320de6131896589720d09fc3e47a13a5ebb7486e6b259ce0066'
PROTECTED = ('accepted_audit_ancestor', 'selected_roots', 'source_root', 'source_projects',
             'source_lock_sha256', 'fixed_source_inputs', 'original_locks', 'limits',
             'destination', 'mount', 'volume_prebuild_free_minimum', 'desktop_local_reserve',
             'index_bytes_max', 'canonical_path', 'foreground_owner')
ROLE_CONTRACT = {
    'host': 'desktop', 'script': 'final_f9.py',
    'unit': 'p4-production651-final-f9-e6ac-r1.service', 'cpus': [6, 7],
    'memory_max': 2147483648, 'memory_high': 1610612736, 'memory_swap_max': 0,
    'tasks_max': 128, 'work_seconds': 10800, 'runtime_seconds': 12000,
    'stop_seconds': 1200, 'body_hash_workers': 0, 'writes_destination': False,
    'independent_retirement_work_seconds': 4500,
    'independent_retirement_runtime_seconds': 4800,
    'independent_retirement_stop_seconds': 300,
    'close_runtime_seconds': 90, 'close_stop_seconds': 15}
OBSERVERS = {
    'independent': {'unit': 'p4-production651-final-f9-independent-e6ac-r1.service',
        'description': 'Pocket4 Production651 final F9 independent ' + NONCE,
        'cpus': [6, 7], 'memory_max': 536870912, 'memory_high': 402653184, 'memory_swap_max': 0,
        'tasks_max': 32, 'work_seconds': 4500, 'runtime_seconds': 4800, 'stop_seconds': 300},
    'close': {'unit': 'p4-production651-final-f9-close-e6ac-r1.service',
        'description': 'Pocket4 Production651 final F9 close ' + NONCE,
        'cpus': [6, 7], 'memory_max': 268435456, 'memory_high': 201326592, 'memory_swap_max': 0,
        'tasks_max': 32, 'work_seconds': 60, 'runtime_seconds': 90, 'stop_seconds': 15}}


def validate_contract(contract, old):
    require(contract['schema'] == 'p4-production651-final-f9-contract-v1' and
            contract['binding_complete'] is True and contract['nonce'] == NONCE and
            contract['phase'] == ROLE and contract['generation'] == 'e6ac-final-f9-r2' and
            contract['foreground_owner'] == OWNER, 'complete fixed new contract, never a proposal')
    for key in PROTECTED:
        require(encoded(contract[key]) == encoded(old[key]), 'exact inherited original scope: ' + key)
    require(old['schema'] == 'p4-production651-recovery-contract-v1' and
            old['nonce'] == '50e61f3b9db070a26e5841a273cf9bcf340a2a6617f35b0d1499645b8f0a7c22' and
            contract['historical_old_B_contract']['sha256'] == OLD_B_CONTRACT and
            contract['historical_old_B_source_sha256'] == OLD_B_SOURCE,
            'unchanged exact historical failed B contract and source')
    full_ref(contract['historical_old_B_contract'])
    require(encoded(contract['roles']) == encoded({ROLE: ROLE_CONTRACT}) and
            encoded(contract['observers']) == encoded(OBSERVERS) and
            encoded(contract['lease']) == encoded({'P4_storage_measurement_age_max_seconds': 600,
              'capture_age_max_seconds': 60, 'dispatch_window_seconds': 600,
              'full_envelope_seconds': FULL_ENVELOPE_SECONDS,
              'minimum_fresh_remaining_seconds': MINIMUM_REMAINING_SECONDS,
              'no_deadline_extension': True}), 'one fixed finite new read-only role and whole envelope')
    require(contract['canonical_binding_field'] == 'source_import_final_f9_current' and
            contract['original_B_passed'] is False and
            contract['original_storage_functional_passed'] is False and
            contract['C_D_admitted'] is False and contract['production_ready'] is False and
            type(contract['Android_builds']) is int and contract['Android_builds'] == 0,
            'explicit new role never updates original failure or grants later phases')
    require(set(contract['hosts']) == {'desktop', 'pocket4'}, 'two fixed control hosts')
    for host, root, boot in (
        ('desktop', '/data/p4-production651-final-f9-e6ac-r2', '8c55b477-233a-4771-995a-6f666f6299b3'),
        ('pocket4', '/home/alex/work/p4-production651-final-f9-observations-e6ac-r2',
         '97d9600f-e081-465c-9e6e-62651e09806b')):
        value = contract['hosts'][host]
        require(value['root'] == root and value['source'] == root + '/source' and value['boot'] == boot,
                'fixed new host root and actual boot')
    for name in ('original_B_result', 'original_B_retirement', 'original_recovery_serial_lock'):
        full_ref(contract[name])
    require(contract['original_recovery_serial_lock']['path'] ==
            '/data/p4-production651-source-recovery-e6ac-r5/recovery-serial.lock',
            'exact old serial inode is held in addition to the new phase serial')
    return validate_prerequisite_bindings(contract, old)


def validate_prerequisite_bindings(contract, old):
    proofs = contract['proof_inputs']
    require(type(proofs) is dict and proofs['schema'] == 'p4-final-f9-fixed-proof-inputs-v1' and
            set(proofs['records']) == {'seal', 'independent', 'close'} and
            set(proofs['offline']) == {'main', 'independent', 'close'},
            'all actual successful prerequisite phases are explicitly bound')
    for family in ('records', 'offline'):
        for row in proofs[family].values():
            require(set(row) == {'original', 'terminal_raw_sha256', 'unit'},
                    'one actual original report, raw terminal digest and native unit')
            full_ref(row['original']); sha(row['terminal_raw_sha256'])
    full_ref(proofs['record_source_manifest'])
    for key in ('record_root_acceptance', 'offline_root_acceptance', 'storage_detachment_root_acceptance'):
        full_ref(proofs[key])
    image = contract['offline_image']
    require(set(image) == {'path', 'bytes', 'sha256', 'identity', 'allocated_bytes'} and
            image['path'] == '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-r1/production651.raw' and
            type(image['bytes']) is int and image['bytes'] == 429496729600 and
            type(image['allocated_bytes']) is int and image['allocated_bytes'] >= image['bytes'],
            'fixed whole offline raw image proof, not a new allocation')
    full_ref({k: image[k] for k in ('path', 'bytes', 'sha256', 'identity')}); sha(contract['offline_nonce'])
    for name in ('authenticated_manifest', 'retained_directory_supplement'):
        pair = contract[name]
        require(set(pair) == {'original', 'copy'}, 'separate original supporting artifact and existing immutable copy')
        for ref in pair.values(): full_ref(ref)
        require((pair['original']['bytes'], pair['original']['sha256']) ==
                (pair['copy']['bytes'], pair['copy']['sha256']) and
                pair['copy']['identity'][3:6] == [0, 0, 1] and
                pair['copy']['path'].startswith('/data/p4-production651-source-recovery-e6ac-r5/inputs/reuse/'),
                'original A and exact directory supplement are read-only reused artifacts')
    full_ref(contract['preserved_coherent_cohort'])
    require(contract['preserved_coherent_cohort']['path'] ==
            contract['destination'] + '/tools-coherent/SOURCE-COHORT.json', 'fixed retained recipe receipt, not latest producer')
    storage = contract['new_storage_source_binding']
    require(type(storage) is dict and storage['schema'] == 'p4-final-f9-new-storage-source-v1' and
            storage['nonce'] not in (NONCE, 'f299dfa890dac924bdc7f392e9429c383cfa18f509fafb7ce7dda3e8aed20a87') and
            storage['mount_target'] == contract['mount'] and
            storage['source_manifest_sha256'] != old['storage_source_manifest_sha256'],
            'separately reviewed new storage source, never an old live owner identity')
    sha(storage['nonce']); sha(storage['source_manifest_sha256'])
    require(encoded({k: storage[k] for k in ('desktop_source', 'desktop_root', 'pocket4_source', 'pocket4_root')}) ==
            encoded({'desktop_source': '/data/p4-production651-nbd-storage-source-e6ac-r5',
                     'desktop_root': '/data/p4-production651-nbd-e6ac-r5',
                     'pocket4_source': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r5',
                     'pocket4_root': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-r1/storage-r5'}),
            'separate create-only storage generation roots, never an old owner alias')
    for key in ('contract', 'source_manifest'):
        require(set(storage[key]) == {'bytes', 'sha256'} and type(storage[key]['bytes']) is int and
                storage[key]['bytes'] > 0, 'fixed new storage source body binding')
        sha(storage[key]['sha256'])
    require(storage['source_manifest']['sha256'] == storage['source_manifest_sha256'] and
            encoded([storage['work_seconds'], storage['runtime_seconds'], storage['stop_seconds']]) ==
            encoded([144000, 145200, 1200]) and storage['final_f9_nonce'] == NONCE,
            'new finite storage capacity and exact final-F9 consumer nonce')
    return contract


def canonical_binding(contract, source_sha):
    sha(source_sha)
    require(contract['binding_complete'] is True and contract['schema'] ==
            'p4-production651-final-f9-contract-v1', 'only a complete reviewed source can be selected')
    return {'schema': 'p4-production651-final-f9-canonical-binding-v1',
            'source_manifest_sha256': source_sha, 'nonce': NONCE, 'phase': ROLE,
            'generation': contract['generation'], 'role': contract['roles'][ROLE],
            'source_lock_sha256': contract['source_lock_sha256'],
            'accepted_audit_ancestor': contract['accepted_audit_ancestor'],
            'failed_B_result': contract['original_B_result'],
            'failed_B_retirement': contract['original_B_retirement'],
            'proof_inputs': contract['proof_inputs'],
            'new_storage_source_binding': contract['new_storage_source_binding'],
            'whole_envelope_seconds': FULL_ENVELOPE_SECONDS,
            'minimum_fresh_remaining_seconds': MINIMUM_REMAINING_SECONDS,
            'original_B_passed': False, 'original_storage_functional_passed': False,
            'C_D_admitted': False, 'production_ready': False}
