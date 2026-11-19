"""Pure r7 immediate-predecessor proof with a separate, unchanged r6 ancestor.

This module reads no files, starts no actor, and issues no storage permission.
Its complete inputs are already pinned by the caller. The r6 image hash and
read-only fsck remain ancestor facts; r7 contributes actual image metadata
bookends, the original failed controller and the two known retirements only.
"""
from recovery_core import require, encoded
from f9_authority import full_ref
from failed_storage_authority import (DOCUMENTS as ANCESTOR_DOCUMENTS,
    qualified_failed_storage, whole_document, same, integer, zero_exit, observed_ref_join)

IMMEDIATE_PREDECESSOR = {
    'source_manifest_sha256': '9aa8b8685c9682ce6e0b3d3c319cf95c27172d21878bf556f8e859dc836ea383',
    'admission_sha256': 'c23b850ce75955ec335d8dee495c2c2c3ac0ff16f95efd0d48e9225378d91ffc',
    'nonce': '046f051d71c6863654c12575eceebee89005c40385591a5cbcb3ea306b1fc7dd'}
OFFLINE_ANCESTOR = {
    'source_manifest_sha256': 'b9c8805f82f628a8f67fcd17a73193b6141be7ee5a9c04b67ff270b9762b708d',
    'admission_sha256': '37d06a61be3bfc74595a57dfb59c9966da919903d0e5793f6b64666030ca57e0',
    'nonce': '07fcf25dedaae64ee1f9fafb4d1ffc052f4f32175544b8d7be05b62abbfdba50'}

FROZEN_PREDECESSOR_ORIGINALS = {'r7.controller.result': {'bytes': 11039,
                          'identity': [2067,
                                       17564660,
                                       33060,
                                       0,
                                       0,
                                       1,
                                       11039,
                                       1794893025402956754,
                                       1794893025402956754],
                          'path': '/data/p4-production651-nbd-e6ac-r7/DESKTOP-RESULT.json',
                          'sha256': '515e79797b642cce0b79ff69fc21a10ea305dc7be4c3f93b111c8461cebb465c'},
 'r7.controller.retirement': {'bytes': 16305,
                              'identity': [2067,
                                           41175491,
                                           33060,
                                           0,
                                           0,
                                           1,
                                           16305,
                                           1794894091740425291,
                                           1794894091740425291],
                              'path': '/data/p4-production651-nbd-storage-source-e6ac-r7/controller-INDEPENDENT-RETIREMENT.json',
                              'sha256': 'ee708d8713a49b2fe262f1babcbad87da5da293fc7f3f0841ffe37abac31e667'},
 'r7.controller.root': {'bytes': 63374,
                        'identity': [66306,
                                     31392960,
                                     33152,
                                     1000,
                                     1000,
                                     1,
                                     63374,
                                     1794894282965151956,
                                     1794894282968238247],
                        'path': '/home/alex/work/p4-storage-r7-controller-retirement-ROOT-actual-acceptance-e6ac-r1.json',
                        'sha256': '38228ca78dcf8e2c8bd93db16d7e026f727656593c46fed67bd1c5ea271df168'},
 'r7.public.root': {'bytes': 27488,
                    'identity': [66306,
                                 31392970,
                                 33152,
                                 1000,
                                 1000,
                                 1,
                                 27488,
                                 1794895115016265192,
                                 1794895115019410019],
                    'path': '/home/alex/work/p4-r7-public-leaf-ROOT-actual-acceptance-e6ac-r2.json',
                    'sha256': '21b3da06e4d97304044765deaffe05b12280413fa272e66f867561d980fc1561'},
 'r7.server.result': {'bytes': 22417,
                      'identity': [66306,
                                   62550532,
                                   33060,
                                   1000,
                                   1000,
                                   1,
                                   22417,
                                   1794894333045371181,
                                   1794894333045371181],
                      'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-r1/storage-r7/SERVER-RESULT.json',
                      'sha256': '4da774fc45c0383785b7dfbc13e8a8a3b7b5915f81fc9bc574d611e06ba9d13d'},
 'r7.server.retirement': {'bytes': 16119,
                          'identity': [66306,
                                       51296513,
                                       33060,
                                       0,
                                       0,
                                       1,
                                       16119,
                                       1794894333308369306,
                                       1794894333308369306],
                          'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r7/server-INDEPENDENT-RETIREMENT.json',
                          'sha256': '37a450b2ba22915441500fd76ea7264d9fd3098b3bb29a84710aa563da8b0c83'},
 'r7.server.root': {'bytes': 59663,
                    'identity': [66306,
                                 31392968,
                                 33152,
                                 1000,
                                 1000,
                                 1,
                                 59663,
                                 1794895057736857633,
                                 1794895057738570064],
                    'path': '/home/alex/work/p4-storage-r7-server-retirement-ROOT-actual-acceptance-e6ac-r1.json',
                    'sha256': '354d1eaa4e3676f96c1e9a4e987c5c8e97c9e869fe5e781256d76237b355a6cb'}}
SUCCESSOR_DOCUMENTS = frozenset(FROZEN_PREDECESSOR_ORIGINALS)
DOCUMENTS = ANCESTOR_DOCUMENTS | SUCCESSOR_DOCUMENTS


def controller_root_proof_join(observed, original):
    """Only this fixed ROOT view's 24 F9 refs have string ns; originals stay native."""
    require(type(observed) is dict and set(observed) == set(original), 'exact controller ROOT proof shape')
    changed = {'original', 'result', 'commands', 'whole_fsynced_native_logs'}
    same({k: v for k, v in observed.items() if k not in changed},
         {k: v for k, v in original.items() if k not in changed},
         'all controller ROOT proof non-reference values and types are identical')
    for key in ('original', 'result'):
        observed_ref_join(observed[key], original[key], 'controller ROOT exact ' + key)
    require(type(observed['commands']) is list and len(observed['commands']) == len(original['commands']) == 6 and
            type(observed['whole_fsynced_native_logs']) is list and
            len(observed['whole_fsynced_native_logs']) == len(original['whole_fsynced_native_logs']) == 10,
            'exact six commands and ten dispatch log refs; no recursive coercion')
    for left, right in zip(observed['commands'], original['commands']):
        require(type(left) is dict and set(left) == set(right), 'exact recorded command fields')
        same({k: v for k, v in left.items() if k not in ('stdout', 'stderr')},
             {k: v for k, v in right.items() if k not in ('stdout', 'stderr')},
             'all actual command lifecycle fields remain identically typed')
        for key in ('stdout', 'stderr'):
            observed_ref_join(left[key], right[key], 'controller ROOT command ' + key)
    for left, right in zip(observed['whole_fsynced_native_logs'], original['whole_fsynced_native_logs']):
        observed_ref_join(left, right, 'controller ROOT original dispatch log')


def retired_r7_role(proof, role, result, result_ref):
    require(proof['schema'] == 'p4-production651-nbd-independent-retirement-v1' and
            proof['role'] == role and proof['retirement_passed'] is True and
            proof['cgroup_absent'] is True and proof['source_and_tools_unchanged'] is True and
            proof['host_kernel_and_MAC_unchanged'] is True and proof['stop_ack_error'] is None,
            'actual original r7 role retirement, not a new observation or reuse')
    for body in (proof, result):
        same({key: body[key] for key in IMMEDIATE_PREDECESSOR}, IMMEDIATE_PREDECESSOR,
             'same exact immediate r7 source, admission and nonce')
        require(integer(body['Android_starts']) == 0 and body['production_ready'] is False,
                'original component report carries no Android or production acceptance')
    same(full_ref(proof['result']), result_ref, 'retirement names the complete original result')
    full_ref(proof['original'])
    native = result['native']; terminal = proof['actual_terminal']; after = proof['actual_after']
    unit = 'p4-production651-nbd-' + role + '-e6ac-r7.service'
    require(native['unit'] == terminal['Id'] == after['Id'] == unit and
            native['InvocationID'] == terminal['InvocationID'] and
            str(integer(native['pid'], 1)) == terminal['ExecMainPID'] and
            terminal['MainPID'] == '0' and terminal['ExecMainCode'] == '1' and
            terminal['ExecMainStatus'] == ('1' if role == 'controller' else '0'),
            'same original PID/invocation and actual terminal exit, not a launch acknowledgement')
    require(after['LoadState'] == 'not-found' and after['MainPID'] == '0' and
            after['ActiveState'] == 'inactive' and after['SubState'] == 'dead' and
            after['InvocationID'] == after['ControlGroup'] == '',
            'the named original unit is released after terminal capture')
    require(type(proof['commands']) is list and 1 <= len(proof['commands']) <= 16,
            'bounded complete recorded original retirement commands')
    for command in proof['commands']:
        zero_exit(command)
    require(type(proof['whole_fsynced_native_logs']) is list and
            len(proof['whole_fsynced_native_logs']) == 10,
            'original dispatch log references retained without substituting their bodies')
    for ref in proof['whole_fsynced_native_logs']:
        full_ref(ref)


def qualified_successor_storage(documents):
    require(type(documents) is dict and set(documents) == DOCUMENTS and len(documents) == 17,
            'the ten original r6 documents plus the seven exact r7 originals')
    ancestor = qualified_failed_storage({name: documents[name] for name in ANCESTOR_DOCUMENTS})
    same(ancestor['original_failed_epoch'], OFFLINE_ANCESTOR,
         'original_failed_epoch stays r6 and is never relabelled r7')
    refs, bodies = {}, {}
    for name in sorted(SUCCESSOR_DOCUMENTS):
        refs[name], bodies[name] = whole_document(documents[name], FROZEN_PREDECESSOR_ORIGINALS[name])
        require(refs[name]['bytes'] <= 2 * 1024**2, 'unchanged per-original proof byte cap')
    cr, cp, croot = (bodies[name] for name in
                    ('r7.controller.result', 'r7.controller.retirement', 'r7.controller.root'))
    sr, sp, sroot = (bodies[name] for name in
                    ('r7.server.result', 'r7.server.retirement', 'r7.server.root'))
    public = bodies['r7.public.root']
    retired_r7_role(cp, 'controller', cr, refs['r7.controller.result'])
    retired_r7_role(sp, 'server', sr, refs['r7.server.result'])
    failure = ["RuntimeError('fresh preserved-volume server export bound to complete offline verification')"]
    require(cr['schema'] == 'p4-production651-nbd-desktop-result-v1' and
            cr['passed'] is False and cr['errors'] == failure and
            cr['original_module_device_mount_state_restored'] is True and
            cr['full_build_started'] is False and integer(cr['full_builds_started_by_owner']) == 0 and
            cp['functional_result_passed'] is False and
            cp['original_module_device_mount_state_restored'] is True and
            cp['offline_original_image'] is cp['detached_recovery'] is cp['socket_retirement'] is None,
            'preserve the actual controller freshness failure and limited restored/retired result')
    require([row['name'] for row in cr['commands']] == ['unit-show', 'storage-lifetime-properties',
            'inspect-existing-ssh-config', 'existing-trusted-peer-boot', 'read-original-server-ready'],
            'the exact complete command sequence stopped before tunnel/client/mount operations')
    for command in cr['commands']:
        zero_exit(command)
    require(croot['schema'] == 'p4-r7-controller-retirement-ROOT-actual-acceptance-v1' and
            croot['retirement_accepted'] is True and croot['original_failure_preserved'] is True and
            croot['functional_controller_success'] is False and
            croot['unknown_old_reader_retired'] is croot['whole_old_storage_retirement'] is False and
            croot['production_ready'] is False and integer(croot['Android_starts']) == 0,
            'independent ROOT accepted known controller retirement with original failure intact')
    controller_root_proof_join(croot['proof'], cp)
    for key in ('public_proof', 'proof_whole'):
        row = croot[key]; ref = refs['r7.controller.retirement']
        same([row['path'], row['bytes'], row['sha256']], [ref['path'], ref['bytes'], ref['sha256']],
             'controller ROOT names the original retirement reference')
        require(row['version'] == ':'.join(str(ref['identity'][i]) for i in (0, 1, 6, 7, 8)),
                'full original controller retirement version with native nanoseconds')
    require(croot['known_retirement']['all_absent'] is croot['known_retirement']['tail_complete'] is True and
            croot['complete_original_H']['complete'] is True and
            integer(croot['complete_original_H']['exit_code']) == 0,
            'known original controller and retirement caller exit with complete H')

    image = ancestor['whole_image']
    full_ref({key: image[key] for key in ('path', 'bytes', 'sha256', 'identity')})
    metadata = {key: image[key] for key in ('path', 'identity', 'allocated_bytes')}
    require(sr['schema'] == 'p4-production651-nbd-server-result-v1' and
            sr['server_lifecycle_clean'] is True and sr['stop_requested'] is True and sr['errors'] == [] and
            sr['fixed_sources_tools_and_admission_unchanged'] is True and sr['full_build_started'] is False and
            sp['functional_result_passed'] is True and sp['original_module_device_mount_state_restored'] is None,
            'actual clean r7 server lifecycle, never a successful controller or whole-storage claim')
    for observed in (sr['image_before'], sr['image_after'], sp['offline_original_image']['image']):
        same(observed, metadata, 'r7 image full F9/allocation equals the unmodified r6 offline image')
    zero_exit(sr['server_retirement'])
    for command in sr['commands']:
        zero_exit(command)
    census = sp['offline_original_image']
    require(census['image_writers'] == census['unavailable'] == [] and
            integer(census['processes_observed'], 1) > 0 and
            integer(census['descriptors_observed'], 1) > 0 and
            census['whole_image_hash_not_computed_here'] is True,
            'recorded complete writer census is historical; no additional hash is claimed')
    for key in ('offline_result', 'offline_inputs', 'root_acceptance'):
        label = {'offline_result': 'offline.result', 'offline_inputs': 'offline.inputs',
                 'root_acceptance': 'offline.root'}[key]
        same(full_ref(sr['preserved_image_lineage'][key]), ancestor['phase_refs'][label],
             'r7 server actually consumed the same original r6 offline qualification')
    require(sr['preserved_image_lineage']['complete_storage_retirement'] is False and
            sr['preserved_image_lineage']['unknown_progress_reader_retired'] is False,
            'the historical lineage keeps unknown-reader and complete-retirement limitations')
    require(sroot['schema'] == 'p4-r7-server-retirement-ROOT-actual-acceptance-v1' and
            sroot['ROOT_acceptance'] is True and
            sroot['status'] == 'ACTUAL_SERVER_RETIREMENT_ACCEPTED_CONTROLLER_ORIGINAL_FAILURE_PRESERVED',
            'independent ROOT accepted the original server result and retirement')
    same(sroot['original_server_result'], sr, 'ROOT full server result equals the original')
    same(sroot['original_public_retirement'], sp, 'ROOT full server retirement equals the original')
    review = sroot['independent_review']
    require(review['all_checks_true'] is True and integer(review['check_count']) == 25 and
            type(review['checks']) is dict and len(review['checks']) == 25 and
            all(flag is True for flag in review['checks'].values()) and
            review['fresh_PID_observation']['all_known_numeric_PIDs_absent'] is True and
            review['fresh_PID_observation']['final_has_more'] is False,
            'complete recorded independent known-subject and native-lifecycle checks')
    same(review['actual_original_refs']['server_result'], refs['r7.server.result'], 'same ROOT server original full9')
    same(review['actual_original_refs']['retirement'], refs['r7.server.retirement'], 'same ROOT retirement original full9')
    same(review['image_metadata'], metadata, 'independent original image metadata')
    same(review['recorded_writer_census'], census, 'same actually recorded writer census')
    require(len(review['units']) == 2 and
            {row['unit'] for row in review['units']} == {
                'p4-production651-nbd-server-e6ac-r7.service',
                'p4-storage-r7-server-retirement-pocket4-e6ac-r1.service'} and
            all(row['system'] == row['user'] == 'not-found' for row in review['units']),
            'the two exact P4 known units had both scopes released')
    require(all(sroot['scope'][key] is False for key in ('all_old_storage_retirement',
            'unknown_old_reader_retired', 'image_payload_read_here', 'B_started', 'C_D_admitted', 'production_ready')) and
            integer(sroot['scope']['Android_starts']) == integer(sroot['scope']['new_START']) == 0,
            'ROOT observation remains limited and did not repeat the offline qualification')
    failure_fact = sroot['controller_actual_failure']
    require(failure_fact['errors'] == failure and failure_fact['functional_passed'] is False and
            failure_fact['image_binding_exact'] is True and
            failure_fact['original_module_device_mount_state_restored'] is True and
            integer(failure_fact['ready_fresh_limit_seconds']) == 300,
            'the existing 300-second failure is retained and is not relaxed for the successor')

    require(public['schema'] == 'p4-r7-public-leaf-ROOT-actual-acceptance-v1' and
            public['ROOT_accepted'] is True and public['prior_generic_tool_EACCES_preserved'] is True and
            public['reconstruction_substituted_for_actual_read'] is False and
            public['full_B_started'] is public['runtime_or_storage_admission'] is public['production_ready'] is False,
            'ordinary actual public reads, not reconstruction or broader permission')
    require(type(public['hosts']) is list and len(public['hosts']) == 2,
            'one original ordinary public-reader result per host')
    hosts = {row['host']: row for row in public['hosts']}
    require(set(hosts) == {'desktop', 'pocket4'}, 'exact two original reader hosts')
    for host, row in hosts.items():
        require(row['scope_complete'] is row['FDs_closed'] is row['H']['complete'] is True and
                integer(row['H']['exit_code']) == 0 and len(row['actual_leaves']) == (2 if host == 'desktop' else 1),
                'complete ordinary bounded reads and closed descriptors')
        for leaf in row['actual_leaves']:
            require(leaf['EOF'] is leaf['complete_read'] is leaf['full9_bookends_equal'] is True,
                    'each original public leaf read was complete with full9 bookends')
            full_ref(leaf['original_ref'])
        sealed = row['actual_leaves'][0]['actual_body']
        require(sealed['schema'] == 'p4-fresh-full-B-runtime-sealed-v1' and sealed['phase'] == 'current' and
                sealed['B_started'] is sealed['C_D_admitted'] is False,
                'historical CURRENT metadata seal is not a runtime or namespace authority')
    leaf = hosts['desktop']['actual_leaves'][1]
    same(leaf['original_ref'], refs['r7.controller.result'], 'ordinary public read of the actual failed controller leaf')
    same(leaf['actual_body'], cr, 'complete ordinary original body, not a reconstructed controller result')
    require(integer(public['independent_known_exits']['checks_passed']) == 20,
            'independent known ordinary reader exits accepted with limited scope')

    return {'schema': 'p4-r7-failed-successor-with-r6-offline-ancestor-qualified-v1',
        'offline_ancestor': ancestor, 'immediate_predecessor': dict(IMMEDIATE_PREDECESSOR),
        'predecessor_refs': refs, 'whole_image': image, 'allocation_lock': ancestor['allocation_lock'],
        'controller_failure': failure, 'controller_original_state_restored': True,
        'server_lifecycle_clean': True, 'known_predecessor_lifecycles_retired': True,
        'ordinary_public_originals_actually_read': True,
        'offline_readonly_qualification_passed': True, 'known_finalizer_lifecycles_retired': True,
        'whole_image_hash_recomputed_for_r7': False, 'offline_fsck_repeated_for_r7': False,
        'complete_old_storage_retirement': False, 'unknown_progress_reader_retired': False,
        'fresh_full_image_F9_and_no_writer_census_required': True,
        'fresh_allocation_lock_EXNB_required': True, 'fresh_current_owner_and_reserve_checks_required': True,
        'new_mount_and_full_B_second_F9_required': True,
        'old_READY_reusable': False, 'old_plan_or_SQLite_resume_accepted': False,
        'new_storage_admitted': False, 'current_namespace_qualified': False,
        'C_D_admitted': False, 'Android_passed': False, 'production_ready': False}
