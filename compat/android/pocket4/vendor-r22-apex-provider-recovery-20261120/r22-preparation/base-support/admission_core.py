#!/usr/bin/python3
"""R20's explicit predecessor and actual-current-release admission predicates.

No launcher, writer, permission change, runtime credit or historical pin rewrite.
The worker supplies full pinned JSON and observes live state separately.
"""
from pathlib import PurePosixPath
import hashlib
import re
import stat

CURRENT = {'tree': '4d78aae1aba2ec9952c37153069cca85c5a87953',
           'files': 2359, 'bytes': 44737433}
CI_SCHEMA = 'p4-current2359-fresh-ordinary-and-release-ci-v1'
CI_STATE = 'ALL1555_ORDINARY_AND19_NORMAL_RELEASE_BUILDS_PASSED'
BINARIES = tuple(sorted(('droidloom-applications', 'droidloom-classpath-wrapper',
    'droidloom-dmabuf-probe', 'droidloom-doctor', 'droidloom-gapps', 'droidloom-host-mac',
    'droidloom-image', 'droidloom-mesa', 'droidloom-package', 'droidloom-package-helper',
    'droidloom-runtime-inputs', 'droidloom-source', 'droidloom-supervisor',
    'droidloom-task-launcher', 'droidloom-translation-bench', 'droidloom-update',
    'droidloom-wayland', 'droidloomctl', 'droidloomd')))
R19 = '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor-build-20261120-9907-r19'
SOURCE = '/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/work/aosp-source'
MANIFEST = {'path': SOURCE + '/.droidloom-source-manifest.json', 'bytes': 441786,
    'sha256': 'e05ea8ffb8b6f1b140027cf2842adbf18d5623a0cf6edb3edf5cfd0565c3e487',
    'identity': [66306, 61099405, 33152, 1000, 1000, 1, 441786,
                 1795156737617805221, 1795156737628804821]}
LOCKS = [
    {'path': '/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/native-full.serial.lock',
     'bytes': 0, 'sha256': hashlib.sha256(b'').hexdigest(), 'body_hex': '',
     'identity': [66306, 60857531, 33152, 1000, 1000, 1, 0,
                  1794183129522871360, 1794183129522871360]},
    *[{'path': str(PurePosixPath(SOURCE).parent / name), 'bytes': 8,
       'sha256': 'c128e753e81869c5a458bbd2381dfaa39cd115365f5d7b7f54c3ee1e73cf7f29',
       'body_hex': b'3693135\n'.hex(),
       'identity': [66306, inode, 33152, 1000, 1000, 1, 8,
                    1795157377961046959, 1795157377961046959]}
      for name, inode in [('package-build.lock', 60857480),
                          ('aosp-source-update.lock', 60857481)]]]
HISTORY = {
    'worker': (224029, '61a3f49bf0a00075a3335eaccc0157217983c7ee1563e77acd80be0bd7912b74'),
    'bundle': (22228, 'ad40ce56fbb0c9c9e3f90cebcdc8fae0dfb606c95784d5a862783ab5d24c5ca6'),
    'outer': (311463, 'ea3e09187045bd56c9a3f3a4dc665baed20a40354e586cd8b653037736726717'),
    'build': (141892, '5453b4cedef4a2b5669319d25a6495062420fdd1436af4a1e82f7ce5cc701549'),
    'recovery': (8344, '8b4b1619b25cce75563350e2489928bacd2cb5228c1e15cbecb403c95caaaa16'),
    'retirement': (7899, '603a3e2605c479cf5b88fc27942bc10f618673d4209415d10274b63226715881'),
}


def need(value, message):
    if not value:
        raise RuntimeError(message)


def content_reference(value):
    """Original CI command logs record content refs, not Linux inode custody."""
    need(type(value) is dict and type(value.get('bytes')) is int and value['bytes'] >= 0
         and type(value.get('sha256')) is str
         and re.fullmatch('[0-9a-f]{64}', value['sha256']) is not None,
         'complete recorded command output size/hash')
    path = value.get('path')
    need(type(path) is str and path.startswith('/') and '..' not in PurePosixPath(path).parts,
         'actual original absolute command log path')
    return {k: value[k] for k in ('path', 'bytes', 'sha256')}


def reference(value):
    need(type(value) is dict, 'whole exact file reference')
    identity = value.get('identity', value.get('f9'))
    need(type(identity) is list and len(identity) == 9
         and all(type(x) is int for x in identity), 'whole integer F9 required')
    need(type(value.get('bytes')) is int and value['bytes'] == identity[6]
         and type(value.get('sha256')) is str
         and re.fullmatch('[0-9a-f]{64}', value['sha256']) is not None,
         'whole bytes/hash identity')
    path = value.get('path')
    need(type(path) is str and path.startswith('/') and '..' not in PurePosixPath(path).parts,
         'exact absolute reference path')
    return {'path': path, 'bytes': value['bytes'], 'sha256': value['sha256'], 'identity': identity}


def command_reaped(row, expected_code=0):
    need(type(row) is dict and row['actual_child_reaped'] is True
         and row['original_pidfd_held_until_reaped'] is True
         and type(row['exit_code']) is int and row['exit_code'] == expected_code
         and row.get('owned_descendants_remaining', 0) == 0
         and row.get('error') is None and not row.get('timed_out', False)
         and row.get('cleanup_errors', []) == [], 'actual original command success and retirement')


def validate_host_abi_custody(value, inputs):
    """Bind the same eight resolved providers to the report and live checks."""
    reported, libraries = value['host_abi_inputs'], value['libraries']
    need(type(inputs) is list and type(reported) is list and type(libraries) is list
         and len(inputs) == len(reported) == len(libraries) == 8,
         'exact eight actual host ABI provider references')
    sonames = [row['soname'] for row in libraries]
    need(all(type(name) is str and name and '/' not in name and '\x00' not in name for name in sonames)
         and len(set(sonames)) == 8, 'eight distinct actual ABI library sonames')
    def normalized(rows):
        result = sorted((reference(row) for row in rows), key=lambda row: row['path'])
        need(len({row['path'] for row in result}) == 8, 'eight unique resolved host library paths')
        return result
    declared = normalized(inputs)
    need(declared == normalized(reported) == normalized([row['provider'] for row in libraries]),
         'contract, actual ABI report and inspected providers must have identical full references')
    return declared


def validate_current_release(value, binary_refs):
    need(value['schema'] == CI_SCHEMA and value['state'] == CI_STATE
         and {k: value['source_' + k] for k in ('tree', 'files', 'bytes')} == CURRENT,
         'actual complete new 2359 release cohort; old leaf CI is insufficient')
    need(value['errors'] == [] and value['all_input_packet_bookends_equal'] is True
         and value['all_source_bookends_equal'] is True
         and value['final_descendant_retirement'] == [], 'actual whole CI inputs and retirement')
    need(value['fresh_ordinary_passed'] == 1555 and value['fresh_test_targets'] == 49
         and value['fresh_example_tests_passed'] == 9 and value['fresh_doc_tests_passed'] == 0
         and len(value['doc_targets_checked']) == 20 and len(value['ignored_not_executed']) == 30
         and value['doc_test_commands_executed'] is True and value['doc_tests_executed'] is False
         and value['example_mains_executed'] is False
         and value['jobs'] == value['test_threads'] == 1,
         'current ordinary/example/doc counts and original bounded CI scope')
    # Original runner records the whole sorted sched_getaffinity set as these
    # two lossless slices. The actual runner may expose more than four CPUs.
    selected, reserved = value['affinity'], value['reserved_cpus']
    need(type(selected) is list and type(reserved) is list
         and len(selected) == 2 and len(reserved) >= 2
         and all(type(x) is int and x >= 0 for x in selected + reserved)
         and selected + reserved == sorted(set(selected + reserved)),
         'original first-two-CPUs selection and complete remaining reservation')
    for key in ('historical_ELFs_reused', 'positive_hardware_branches_inferred',
                'production_ready', 'runtime_qualified', 'full_workspace_qualified'):
        need(value[key] is False, 'CI must not claim unsupported runtime or historical credit')
    need(value['historical_tests_counted_as_fresh'] == 0
         and value['Android_builds'] == value['Android_starts'] == 0,
         'ordinary CI is not Android execution')
    commands = value['commands']
    need(len(commands) == 243 and len({x['name'] for x in commands}) == 243,
         'complete fixed current cohort command roster')
    for row in commands:
        command_reaped(row)
        need(row['started_ns'] < row['finished_ns'] <= value['finished_ns'], 'actual CI command time order')
        content_reference(row['stdout']); content_reference(row['stderr'])
    batches = [r for r in commands if r['name'] in ('normal-release-updater', 'normal-release-remaining27')]
    need([r['name'] for r in batches] == ['normal-release-updater', 'normal-release-remaining27'],
         'both original normal release batches executed')
    need(tuple(sorted(value['fresh_release_binaries'])) == tuple(sorted(binary_refs)) == BINARIES,
         'all original nineteen current normal binaries, exact scope')
    parents = set()
    for name in BINARIES:
        ci, live = reference(value['fresh_release_binaries'][name]), reference(binary_refs[name])
        need(PurePosixPath(live['path']).name == name and live['bytes'] == ci['bytes']
             and live['sha256'] == ci['sha256'] and live['identity'][2] == (stat.S_IFREG | 0o755)
             and live['identity'][3:6] == [1000, 1000, 1],
             'exact ordinary deployed current ELF bytes and inode scope')
        parents.add(str(PurePosixPath(live['path']).parent))
    need(len(parents) == 1, 'single current release directory')
    return {'schema': 'p4-r20-actual-current-release-ci-consumed-v1', **CURRENT,
            'actual_ordinary_passed': 1555, 'actual_release_binaries': 19,
            'actual_commands_reaped': len(commands), 'runtime_qualified': False,
            'production_ready': False, 'Vendor_build_credit': False}


def validate_predecessor(values, refs):
    need(set(values) == {'bundle', 'outer', 'build', 'recovery', 'retirement'},
         'complete separate original R19 documents')
    need(set(refs) == set(HISTORY), 'all exact R19 original inputs required')
    for name, expected in HISTORY.items():
        item = reference(refs[name])
        need((item['bytes'], item['sha256']) == expected, 'original R19 frozen body changed: ' + name)
    bundle, outer, build, recovery, retired = [values[x] for x in
        ('bundle', 'outer', 'build', 'recovery', 'retirement')]
    need(reference(outer['worker']) == reference(refs['worker'])
         and reference(outer['bundle']) == reference(refs['bundle']), 'actual R19 actor/input binding')
    need(bundle['schema'] == 'pocket4-vendor-r19-launch-bundle-v1'
         and bundle['dispatch_inputs_frozen'] is True
         and bundle['source_tree'] == 'fa0382574f4fc18f59b2b5dd67a30939167d8c3a',
         'historical Vendor source remains correctly labelled')
    need(outer['schema'] == 'pocket4-vendor-r19-supervisor-terminal-v1'
         and outer['passed'] is False and outer['normal_recovery_attempted'] is True
         and outer['normal_recovery_verified'] is True
         and outer['build_attempted'] is True and outer['serial_lock_acquired'] is True
         and outer['all_owned_units_retired'] is True and outer['all_created_children_reaped'] is True
         and outer['serial_held_through_all_source_operations'] is True
         and outer['errors'] == outer['build_retirement_errors'] == outer['final_retirement_errors'] == []
         and outer['fixed_deadline_exceeded'] is False, 'actual failed R19 and successful normal recovery')
    need(len(outer['phases']) == 2 and [x['mode'] for x in outer['phases']] == ['build', 'recover'],
         'exact original two phase order')
    for row, code in zip(outer['phases'], (1, 0)):
        need(row['service_retired'] is True and row['client']['actual_reaped'] is True
             and row['client']['original_pidfd_held_until_reaped'] is True
             and row['client']['exit_code'] == code and row['success'] is (code == 0)
             and row['errors'] == [] and row['forced_service_retirement'] is False
             and row['late_start_unresolved'] is False, 'actual original phase retirement')
    need(len(outer['children']) == 388 and len(outer['original_worker_status_children']) == 106,
         'complete R19 outer child and status roster')
    for row in outer['children']:
        need(row['actual_reaped'] is True and row['original_pidfd_held_until_reaped'] is True,
             'all original outer children actually retired')
    for row in outer['original_worker_status_children']:
        command_reaped(row)
    need(build['schema'] == recovery['schema'] == 'p4-cp3a-normal-vendor-build-r19-v1'
         and len(build['commands']) == 6 and len(recovery['commands']) == 2,
         'actual original R19 build/recovery command scope')
    for row in build['commands'][:-1] + recovery['commands']:
        command_reaped(row)
    failed = build['commands'][-1]
    need(failed['name'] == 'normal-official-gsi-vendor-build'
         and failed['actual_child_reaped'] is True and failed['original_pidfd_held_until_reaped'] is True
         and failed['owned_descendants_remaining'] == 0 and failed['exit_code'] == 1,
         'actual normal Vendor failure remains failed')
    need(len(build['errors']) == 1 and recovery['errors'] == []
         and recovery['source_recovery_complete'] is True
         and recovery['full652_source_verified'] is True
         and recovery['original651_before_after_content_equal'] is True
         and recovery['complete_cmake_matches_independent_original_tree'] is True
         and recovery['prior_cmake_bookend_comparison_performed'] is True
         and recovery['all_original_inputs_and_source_files_unchanged'] is True
         and recovery['native_source_926_members_and_git_provenance_unchanged'] is True,
         'actual old651 plus complete3915 CMake recovery remains distinct from new lint scope')
    admission = build['serialized_heavy_admission']
    for key, expected in {'schema': 'p4-serialized-heavy-build-resource-plan-v1',
        'original_minimum_memory_gib': 42, 'vendor_memory_max_gib': 24,
        'simultaneous_other_heavy_compilers': 0, 'bounded_light_scopes_max_gib': 3.25,
        'host_reserve_gib': 12, 'unallocated_margin_within_minimum_gib': 2.75}.items():
        need(admission[key] == expected, 'original successful serialized historical admission')
    restoration = admission['actual_r18_failure_then_complete_same651_restoration']
    for key in ('actual_original_and_observer_complete_capture_and_retirement_verified',
                'all_2822_actual_checkout_attributes_and_target_controls_consumed',
                'complete_fresh_same651_restoration_consumed'):
        need(restoration[key] is True, 'original actual R4 restoration history retained')
    census = restoration['fresh_census_raw_and_gitlink_comparison_replayed']
    need(census['original_raw_bytes_and_F9_equal'] is True
         and census['original_gitlinks_compared'] == 19
         and census['present_bodies_compared'] == 890095
         and census['raw_bytes_compared'] == 27974799408
         and restoration['exact_catalog_bodies_restored'] == 2822
         and restoration['source_entries_compared'] == 1041385,
         'actual full R4 census and original restoration counts retained')
    need(restoration['historical_failures_replaced'] is False
         and restoration['historical_source_inode_pins_rewritten'] is False,
         'historical failures and pins preserved')
    need(reference(build['full652_reconcile']['new_manifest']['original'])
         == reference(recovery['final_normal_manifest']['original'])
         == reference(retired['source_manifest']) == MANIFEST, 'actual original 652 publication baseline')
    need(retired['read_only'] is True and retired['source_mutations'] is False
         and retired['lock_mutations'] is False and retired['errors'] == []
         and retired['normal_vendor_build_succeeded'] is False
         and retired['source_recovery_complete'] is True
         and retired['source_projection_journal_present'] is False,
         'independent actual R19 retirement and normal source recovery')
    need(reference(retired['terminal']) == reference(refs['outer'])
         and reference(retired['recovery']) == reference(refs['recovery']), 'independent original document binding')
    original = retired['original_locks']
    need(len(original) == 3, 'all original three locks')
    for observed, expected in zip(original, LOCKS):
        need(reference(observed) == reference(expected)
             and observed['body_hex'] == expected['body_hex']
             and observed['actual_lock_records'] == [], 'exact R19 post-recovery original lock transition')
    cmd = recovery['commands'][0]
    need(cmd['name'] == 'normal-source-recovery' and cmd['pid'] == 3693135
         and all(cmd['started_ns'] <= x['identity'][7] <= cmd['finished_ns']
                 and cmd['started_ns'] <= x['identity'][8] <= cmd['finished_ns'] for x in LOCKS[1:]),
         'two original PID-lock times bound to actual normal recovery child')
    for value in (outer, build, recovery, bundle):
        need(value['production_ready'] is False, 'no prior production credit')
    for value in (outer, build, recovery):
        need(value['runtime_qualified'] is False and value['installed'] is False, 'no prior runtime or install credit')
    for key, code in (('original', 1), ('monitor', 0)):
        client = retired['clients'][key]; actual = client['actual_status']
        out = reference(client['stdout'])
        need(actual['state'] == 'exited' and actual['exit_code'] == code
             and actual['output_complete'] is True and actual['capture_error'] is None
             and actual['bytes_seen'] == actual['bytes_stored'] == out['bytes'],
             'actual original client full capture and real exit')
    for item in retired['units']:
        need(item['unit_observation']['properties'] == {'LoadState': 'not-found',
             'ActiveState': 'inactive', 'SubState': 'dead', 'MainPID': '0',
             'ControlGroup': '', 'InvocationID': ''}
             and item['unit_observation']['exit_code'] == 0
             and item['system_cgroup_exists'] is item['user_cgroup_exists'] is False
             and all(p['exists'] is False for p in item['pids']), 'complete original actors retired')
    return {'schema': 'p4-r20-actual-r19-predecessor-consumed-v1',
            'actual_R19_build_exit_code': 1, 'actual_R19_recovery_exit_code': 0,
            'original_outer_children_reaped': 388, 'original_status_children_reaped': 106,
            'new_manifest_baseline': MANIFEST, 'new_lock_baseline': LOCKS,
            'historical_serialized_admission': admission, 'historical_failure_replaced': False,
            'new_lint_scope_credit': False, 'runtime_qualified': False, 'production_ready': False}
