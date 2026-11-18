"""Finite independent R36-source storage after actual r7 retirement and the separate r6 offline ancestor.

The pure qualification preserves unknown historical lifetimes and all failures.
It grants no new storage, namespace, full-B, C/D or build permission. Runtime
callers separately enforce original ownership, resources and actual identities.
"""
for _name in ('recovery_core.py', 'f9_authority.py', 'failed_storage_authority.py', 'successor_storage_authority.py', 'owner_acquisition_v2.py'):
    _raw = (C / _name).read_bytes()
    need(len(_raw) == manifest['files'][_name]['bytes'] and
         hashlib.sha256(_raw).hexdigest() == manifest['files'][_name]['sha256'],
         'sealed pure failed-epoch proof module body')
sys.path.insert(0, str(C))
from recovery_core import encoded
from f9_authority import full_ref
from failed_storage_authority import (OLD_MANIFEST as OLD_STORAGE_SHA,
    OLD_ADMISSION as OLD_ADMISSION_SHA, OLD_NONCE)
from successor_storage_authority import (DOCUMENTS, qualified_successor_storage,
    IMMEDIATE_PREDECESSOR, OFFLINE_ANCESTOR)
from owner_acquisition_v2 import validate_storage_owner_v2, FROZEN_R8_NONCE


def rotation_schedule(contract):
    import datetime
    expected = {'setup_upper_seconds': 600, 'fresh_full_B_whole_envelope_seconds': 36900,
                'gap_receive_and_peer_retirement_upper_seconds': 21300,
                'verification_and_retirement_upper_seconds': 14100,
                'vendor_native_and_stop_upper_seconds': 28800, 'vendor_independent_upper_seconds': 4500,
                'wm_native_and_stop_upper_seconds': 28800, 'wm_independent_upper_seconds': 4500,
                'storage_cleanup_reserve_seconds': 1200}
    immediate = {
        'source_manifest_sha256': '9aa8b8685c9682ce6e0b3d3c319cf95c27172d21878bf556f8e859dc836ea383',
        'admission_sha256': 'c23b850ce75955ec335d8dee495c2c2c3ac0ff16f95efd0d48e9225378d91ffc',
        'nonce': '046f051d71c6863654c12575eceebee89005c40385591a5cbcb3ea306b1fc7dd'}
    ancestor = {
        'source_manifest_sha256': 'b9c8805f82f628a8f67fcd17a73193b6141be7ee5a9c04b67ff270b9762b708d',
        'admission_sha256': '37d06a61be3bfc74595a57dfb59c9966da919903d0e5793f6b64666030ca57e0',
        'nonce': '07fcf25dedaae64ee1f9fafb4d1ffc052f4f32175544b8d7be05b62abbfdba50'}
    need(contract['schema'] == 'p4-production651-successor-storage-contract-v2' and
         contract['generation'] == 'e6ac-storage-r8-r36-v2-r1' and
         encoded(contract['rotation_schedule']) == encoded(expected) and
         encoded([contract['storage_work_seconds'], contract['storage_runtime_max_seconds'],
                  contract['storage_stop_seconds']]) == encoded([144000, 145200, 1200]) and
         sum(expected.values()) < contract['storage_work_seconds'] and
         contract['fresh_full_B_required_before_C_D'] is True and
         contract['new_mount_complete_F9_required_before_C_D'] is True and
         contract['new_mount_F9_qualified'] is False and
         type(contract['minimum_current_lease_seconds']) is int and
         contract['minimum_current_lease_seconds'] == 21600 and
         type(contract['initial_ready_fresh_seconds']) is int and contract['initial_ready_fresh_seconds'] == 300,
         'new finite R36-source storage; unchanged full-B replacement, freshness and lifetime budgets')
    need(encoded(contract['immediate_predecessor']) == encoded(immediate) and
         encoded(contract['offline_ancestor']) == encoded(ancestor) and
         encoded([contract[k] for k in ('previous_storage_source_manifest_sha256',
             'previous_storage_admission_sha256', 'previous_storage_nonce')]) ==
         encoded([immediate['source_manifest_sha256'], immediate['admission_sha256'], immediate['nonce']]),
         'r7 immediate predecessor and original r6 offline ancestor are separate exact identities')
    need(encoded([contract[k] for k in ('p4_fresh_disk_minimum', 'p4_live_disk_reserve',
          'p4_fresh_memory_minimum', 'p4_live_memory_reserve', 'desktop_fresh_memory_minimum',
          'desktop_live_memory_reserve', 'desktop_local_disk_minimum', 'volume_prebuild_free_minimum')]) ==
         encoded([276 * 1024**3, 256 * 1024**3, 6 * 1024**3, 5 * 1024**3,
                  28 * 1024**3, 12 * 1024**3, 8 * 1024**3, 248 * 1024**3]),
         'unchanged original fresh/live disk, volume and memory reserve gates')
    validate_storage_owner_v2(contract)
    return {'total_seconds': sum(expected.values()), 'owner_work_seconds': contract['storage_work_seconds'],
            'fresh_full_B_required_before_C_D': True,
            'new_mount_complete_F9_required_before_C_D': True,
            'later_phases_are_proposals': True, 'C_D_admitted': False}


def storage_binding(contract, accepted, rotation_sha):
    rotation_schedule(contract)
    need(type(contract['nonce']) is str and len(contract['nonce']) == 64 and
         all(c in '0123456789abcdef' for c in contract['nonce']) and
         contract['nonce'] not in (contract['immediate_predecessor']['nonce'], contract['offline_ancestor']['nonce'], FROZEN_R8_NONCE) and
         all(type(x) is str and len(x) == 64 and all(c in '0123456789abcdef' for c in x)
             for x in (accepted, rotation_sha)),
         'actual new source/nonce and sealed input SHA, never executable placeholders')
    owner = contract['owner_acquisition']['owner']
    return {'schema': 'p4-production651-successor-storage-canonical-binding-v2',
            'source_manifest_sha256': accepted, 'nonce': contract['nonce'],
            'rotation_inputs_sha256': rotation_sha,
            'immediate_predecessor': contract['immediate_predecessor'],
            'offline_ancestor': contract['offline_ancestor'],
            'previous_storage_source_manifest_sha256': contract['previous_storage_source_manifest_sha256'],
            'previous_storage_admission_sha256': contract['previous_storage_admission_sha256'],
            'previous_storage_nonce': contract['previous_storage_nonce'],
            'r7_controller_retirement_root_sha256': contract['transition_originals']['r7.controller.root']['original']['sha256'],
            'r7_server_retirement_root_sha256': contract['transition_originals']['r7.server.root']['original']['sha256'],
            'r7_public_originals_root_sha256': contract['transition_originals']['r7.public.root']['original']['sha256'],
            'offline_ancestor_root_sha256': contract['transition_originals']['offline.root']['original']['sha256'],
            'owner_acquisition_id': owner['acquisition_id'], 'foreground_owner': owner['name'],
            'lease_until_utc': owner['active_until_utc'],
            'owner_acquisition_current': contract['owner_acquisition']['current'],
            'owner_acquisition_root': contract['owner_acquisition']['root_acceptance'],
            'mount_target': contract['mount_target'], 'new_storage_work_seconds': contract['storage_work_seconds'],
            'schedule': contract['rotation_schedule'], 'fresh_full_B_required_before_C_D': True,
            'new_mount_complete_F9_required_before_C_D': True,
            'permits_build_without_separate_role_admission': False, 'old_owner_deadline_extended': False,
            'old_storage_READY_reusable': False, 'old_plan_or_SQLite_resume_accepted': False,
            'complete_old_storage_retirement': False, 'unknown_progress_reader_retired': False,
            'original_B_passed': False, 'original_storage_lifecycle_success': False,
            'new_mount_F9_qualified': False, 'C_D_admitted': False}


def proof_copy(bundle, host, expected, label, contract):
    need(type(bundle) is dict and set(bundle) == {'host', 'original', 'copies'} and
         type(expected) is dict and set(expected) == {'host', 'original'} and
         bundle['host'] == expected['host'] and host in ('desktop', 'pocket4') and
         expected['host'] in ('desktop', 'pocket4') and
         encoded(bundle['original']) == encoded(expected['original']) and
         type(bundle['copies']) is dict and set(bundle['copies']) == {'desktop', 'pocket4'} and
         label in DOCUMENTS, 'one exact failed-epoch original and two distinct copies')
    original = full_ref(bundle['original']); limit = 2 * 1024**2
    for target_host, source_key in (('desktop', 'desktop_source'), ('pocket4', 'p4_source')):
        copied = full_ref(bundle['copies'][target_host])
        need(copied['path'] == str(P(contract[source_key]) / 'inputs' / (label + '.json')) and
             copied['identity'][3:6] == [0, 0, 1] and stat.S_IMODE(copied['identity'][2]) == 0o444 and
             copied['bytes'] <= limit and copied['identity'][:2] != original['identity'][:2] and
             (copied['bytes'], copied['sha256']) == (original['bytes'], original['sha256']),
             'root-sealed whole copy keeps its own actual F9 and fixed source-host path')
    copy = full_ref(bundle['copies'][host])
    need(copy['path'] == str(C / 'inputs' / (label + '.json')), 'local sealed source root')
    if host == expected['host']:
        original_actual, _ = pin(original['path'], original, limit=limit)
        need(encoded(original_actual) == encoded(original), 'complete source-host original remains unchanged')
    actual, body = pin(copy['path'], copy, limit=limit)
    need(encoded(actual) == encoded(copy), 'whole copied original and all nine local identity fields')
    return {'original_host': expected['host'], 'original': original, 'local': actual,
            'raw': body, 'body': json.loads(body)}


def failed_predecessors(rows, contract):
    need(type(rows) is dict and set(rows) == DOCUMENTS, 'seventeen complete r6-ancestor and r7-predecessor documents')
    documents = {name: {'original': rows[name]['original'], 'raw': rows[name]['raw']}
                 for name in DOCUMENTS}
    qualified = qualified_successor_storage(documents)
    need(encoded(qualified['offline_ancestor']['original_failed_epoch']) == encoded(contract['offline_ancestor']) and
         encoded(qualified['immediate_predecessor']) == encoded(contract['immediate_predecessor']) and
         encoded(qualified['whole_image']) == encoded(contract['offline_image']) and
         qualified['allocation_lock']['path'] == contract['allocation_lock_path'] and
         qualified['known_predecessor_lifecycles_retired'] is True and
         all(qualified[key] is False for key in ('complete_old_storage_retirement',
             'unknown_progress_reader_retired', 'old_READY_reusable',
             'old_plan_or_SQLite_resume_accepted', 'new_storage_admitted',
             'current_namespace_qualified', 'C_D_admitted', 'Android_passed', 'production_ready')),
         'exact two-level lineage, retaining all original failures, unknowns and fresh runtime gates')
    return qualified


def validate_rotation_data(contract, host, data):
    rotation_schedule(contract)
    need(type(data) is dict and set(data) == {'schema', 'new_storage_nonce',
         'old_storage_source_manifest_sha256', 'old_storage_admission_sha256',
         'old_storage_nonce', 'offline_ancestor', 'records'} and
         data['schema'] == contract['rotation_input_schema'] == 'p4-production651-successor-storage-inputs-v2' and
         data['new_storage_nonce'] == contract['nonce'] and
         data['old_storage_source_manifest_sha256'] == IMMEDIATE_PREDECESSOR['source_manifest_sha256'] and
         data['old_storage_admission_sha256'] == IMMEDIATE_PREDECESSOR['admission_sha256'] and
         data['old_storage_nonce'] == IMMEDIATE_PREDECESSOR['nonce'] and
         encoded(data['offline_ancestor']) == encoded(OFFLINE_ANCESTOR) and
         type(data['records']) is dict and set(data['records']) == set(contract['transition_originals']) == DOCUMENTS,
         'only actual r7 predecessor and separate r6 offline originals, no old plan or compatibility input')
    rows = {name: proof_copy(data['records'][name], host, contract['transition_originals'][name], name, contract)
            for name in sorted(DOCUMENTS)}
    need(sum(row['local']['bytes'] for row in rows.values()) <= 16 * 1024**2,
         'unchanged finite proof-byte cap; no image, journal or selected payload')
    qualified = failed_predecessors(rows, contract)
    return rows, {**qualified['whole_image'], 'uuid': contract['image_uuid']}


def rotation_inputs(contract, host, expected_sha):
    rotation_schedule(contract)
    need(type(contract['nonce']) is str and len(contract['nonce']) == 64 and
         contract['nonce'] not in (OLD_NONCE, IMMEDIATE_PREDECESSOR['nonce']),
         'new frozen epoch before original inputs are opened')
    ref, raw = pin(C / 'ROTATION-INPUTS.json', limit=256 * 1024)
    need(ref['sha256'] == expected_sha and ref['identity'][3:6] == [0, 0, 1] and
         stat.S_IMODE(ref['identity'][2]) == 0o444, 'root-sealed complete two-host proof binding')
    rows, image = validate_rotation_data(contract, host, json.loads(raw))
    return ref, rows, image


def rotation_image_input(commands, contract, admission):
    ref, rows, image = rotation_inputs(contract, 'pocket4', admission['rotation_inputs']['sha256'])
    need(encoded(ref) == encoded(admission['rotation_inputs']) and
         encoded(image) == encoded(admission['allocated_image']), 'same admitted readonly offline lineage')
    units = [rows['server.ready']['body']['native']['unit'],
             rows['server.retirement']['body']['native']['unit'],
             rows['offline.result']['body']['native']['unit'],
             rows['offline.root']['body']['release_native']['unit'],
             rows['r7.server.result']['body']['native']['unit'],
             rows['r7.server.root']['body']['independent_review']['units'][1]['unit']]
    need(len(units) == len(set(units)) == 6 and all(type(unit) is str and unit.endswith('.service')
         for unit in units), 'four exact r6 ancestor units and two exact r7 predecessor units')
    states = []
    for unit in units:
        state = show(commands, unit)
        need(state['LoadState'] == 'not-found' and state['MainPID'] == '0' and
             state['ActiveState'] == 'inactive' and state['SubState'] == 'dead' and
             state['InvocationID'] == state['ControlGroup'] == '' and
             not (P('/sys/fs/cgroup/system.slice') / unit).exists(),
             'all six named known original units and their exact cgroups remain retired')
        states.append({'unit': unit, 'state': state, 'cgroup_absent': True})
    return {'schema': 'p4-r36-source-preserved-image-lineage-v2',
            'immediate_predecessor': IMMEDIATE_PREDECESSOR, 'offline_ancestor': OFFLINE_ANCESTOR,
            'offline_result': rows['offline.result']['original'],
            'offline_inputs': rows['offline.inputs']['original'],
            'root_acceptance': rows['offline.root']['original'],
            'desktop_retirement_root': rows['r7.controller.root']['original'],
            'server_retirement_root': rows['r7.server.root']['original'],
            'public_originals_root': rows['r7.public.root']['original'],
            'offline_ancestor_retirement_roots': {name: rows[name]['original']
                for name in ('desktop.root', 'server.root')}, 'known_units': states,
            'old_storage_source_manifest_sha256': IMMEDIATE_PREDECESSOR['source_manifest_sha256'],
            'allocation_performed': False, 'formatting_performed': False,
            'known_server_and_finalizer_units_retired': True, 'complete_storage_retirement': False,
            'unknown_progress_reader_retired': False, 'original_B_passed': False,
            'original_desktop_functional_passed': False, 'whole_storage_lifecycle_passed': False,
            'new_mount_F9_qualified': False, 'fresh_full_B_required_before_C_D': True,
            'new_mount_complete_F9_required_before_C_D': True, 'C_D_admitted': False}


def original_empty_mountpoint(contract, admission, expected=None):
    """Create only in the new owner root, then recheck that same empty inode.

    No operation names or opens the rejected predecessor mountpoint. Evidence
    files legitimately change the new owner directory between these two calls;
    its full named/held F9 is stable within each call and its first five identity
    fields must remain identical across calls. The target itself keeps all nine.
    """
    _, _, image = rotation_inputs(contract, 'desktop', admission['rotation_inputs']['sha256'])
    need(encoded(image) == encoded(admission['allocated_image']), 'same explicitly admitted failed-epoch image')
    target = P(contract['mount_target']); parent = P(contract['desktop_root'])
    need(target == parent / 'mount' and parent == parent.resolve(),
         'only the new generation owner directory, never the rejected old directory')
    pfd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    fd = None
    try:
        parent_before = os.fstat(pfd)
        need(f9(parent_before) == f9(parent.lstat()) and parent_before.st_dev == 2067 and
             stat.S_ISDIR(parent_before.st_mode) and parent_before.st_uid == parent_before.st_gid == 0 and
             stat.S_IMODE(parent_before.st_mode) == 0o711,
             'actual held named new root-owned traversable evidence directory')
        if expected is None:
            os.mkdir('mount', mode=0o700, dir_fd=pfd)
        else:
            need(type(expected) is dict and set(expected) == {'schema', 'path', 'identity', 'parent',
                 'created_new_directory', 'complete_empty_passes', 'mount_observed', 'namespace_qualified', 'C_D_admitted'} and
                 expected['schema'] == 'p4-new-storage-empty-mountpoint-v1' and
                 expected['path'] == str(target) and expected['parent']['path'] == str(parent) and
                 expected['created_new_directory'] is True and expected['complete_empty_passes'] == 2 and
                 expected['mount_observed'] is expected['namespace_qualified'] is expected['C_D_admitted'] is False and
                 encoded(expected['parent']['identity'][:5]) == encoded(f9(parent_before)[:5]),
                 'the same newly created directory identity, not a historical or caller-invented baseline')
        fd = os.open('mount', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=pfd)
        before = os.fstat(fd)
        need(stat.S_ISDIR(before.st_mode) and before.st_dev == parent_before.st_dev == 2067 and
             before.st_uid == before.st_gid == 0 and stat.S_IMODE(before.st_mode) == 0o700 and
             f9(before) == f9(os.stat('mount', dir_fd=pfd, follow_symlinks=False)) == f9(target.lstat()),
             'complete fresh named/held underlying directory F9 on the local evidence filesystem')
        if expected is None:
            os.fsync(fd); os.fsync(pfd)
        else:
            need(encoded(f9(before)) == encoded(expected['identity']),
                 'all nine actual target fields unchanged since this controller created it')
        parent_observed = f9(os.fstat(pfd))
        need(parent_observed == f9(parent.lstat()) and parent_observed[:5] == f9(parent_before)[:5],
             'same parent identity/mode/owner and full named/held F9 after create-only mkdir')
        for _ in range(2):
            os.lseek(fd, 0, os.SEEK_SET)
            need(os.listdir(fd) == [], 'two complete independently rewound empty target enumerations')
        after = os.fstat(fd)
        need(f9(before) == f9(after) == f9(os.stat('mount', dir_fd=pfd, follow_symlinks=False)) == f9(target.lstat()) and
             parent_observed == f9(os.fstat(pfd)) == f9(parent.lstat()),
             'complete new parent and empty target F9 bookends before any mount')
        return {'schema': 'p4-new-storage-empty-mountpoint-v1', 'path': str(target), 'identity': f9(after),
                'parent': {'path': str(parent), 'identity': parent_observed},
                'created_new_directory': expected is None, 'complete_empty_passes': 2,
                'mount_observed': False, 'namespace_qualified': False, 'C_D_admitted': False}
    finally:
        first_error = None
        for observed in (fd, pfd):
            if observed is not None:
                try: os.close(observed)
                except BaseException as error:
                    if first_error is None: first_error = error
        if first_error is not None: raise first_error


def preserved_volume_anchors(contract, admission):
    # The four historical anchors belong to the separately qualified r6 image.
    # The r7 controller never reached mount; neither old root is current namespace proof.
    _, rows, image = rotation_inputs(contract, 'desktop', admission['rotation_inputs']['sha256'])
    need(encoded(image) == encoded(admission['allocated_image']) and
         rows['desktop.result']['body']['source_manifest_sha256'] ==
         contract['offline_ancestor']['source_manifest_sha256'] and
         rows['desktop.result']['body']['nonce'] == contract['offline_ancestor']['nonce'] and
         rows['desktop.result']['body']['passed'] is False,
         'exact failed-r6 offline ancestor and separately observed r7 immediate predecessor')
    old = rows['desktop.result']['body']['preserved_volume_anchors']
    names = ('.', 'source-production651', 'build-production651', 'delivery')
    need(set(old) == set(names), 'exact four historical persistent anchor identities')
    found = {}; held = []
    try:
        for name in names:
            path = P(contract['mount_target']) if name == '.' else P(contract['mount_target']) / name
            expected = old[name]
            need(type(expected) is list and len(expected) == 9 and
                 all(type(value) is int for value in expected),
                 'native integer historical full F9 is retained without normalization')
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            held.append((name, path, fd))
            value = os.fstat(fd); actual = f9(value)
            need(encoded(actual) == encoded(f9(path.lstat())) and
                 encoded(actual[:5]) == encoded(expected[:5]) and
                 value.st_dev == os.makedev(43, 0) and stat.S_ISDIR(value.st_mode) and
                 value.st_uid == value.st_gid == (0 if name == '.' else 1000),
                 'same actual anchor inode/type/mode/owner and complete named/held current F9')
            found[name] = actual
        for name, path, fd in held:
            need(encoded(found[name]) == encoded(f9(os.fstat(fd))) == encoded(f9(path.lstat())),
                 'all four complete current anchor F9 bookends remain identical')
        # Caller records these as this mount's observations. No old namespace
        # digest, C plan, SQLite resume or current full-tree qualification follows.
        return found
    finally:
        first_error = None
        for _, _, fd in reversed(held):
            try:
                os.close(fd)
            except BaseException as error:
                if first_error is None: first_error = error
        if first_error is not None: raise first_error


def external_consumers_retired(commands, contract):
    results = []
    for unit in contract['external_recovery_units']:
        state = show(commands, unit)
        need(state['LoadState'] == 'not-found' and state['MainPID'] == '0' and
             state['ActiveState'] == 'inactive' and
             not (P('/sys/fs/cgroup/system.slice') / unit).exists(),
             'root must independently retire every external recovery consumer before normal owner stop')
        results.append({'unit': unit, 'state': state, 'cgroup_absent': True})
    return results
