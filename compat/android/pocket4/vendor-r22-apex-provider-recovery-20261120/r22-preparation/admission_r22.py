#!/usr/bin/python3
"""R22 pure admission of the actual R21 failure/recovery and a new CI cohort.

No command, source writer, lock acquisition, launcher or retry is exposed.
The worker must independently recheck every full reference and live retirement.
"""
from pathlib import PurePosixPath
import hashlib
import re
import stat

CURRENT = {'bytes': 45262277, 'files': 2367, 'tree': 'fd0ef624e436d1eb5c8d2c4083335088811a6a42'}
CI_SCHEMA = 'p4-native-leaf-complete-source-and-release-ci-v1'
CI_STATE = 'ALL_CURRENT_ORDINARY_AND19_NORMAL_RELEASE_BUILDS_PASSED'
BINARIES = tuple(sorted(('droidloom-applications', 'droidloom-classpath-wrapper',
    'droidloom-dmabuf-probe', 'droidloom-doctor', 'droidloom-gapps', 'droidloom-host-mac',
    'droidloom-image', 'droidloom-mesa', 'droidloom-package', 'droidloom-package-helper',
    'droidloom-runtime-inputs', 'droidloom-source', 'droidloom-supervisor',
    'droidloom-task-launcher', 'droidloom-translation-bench', 'droidloom-update',
    'droidloom-wayland', 'droidloomctl', 'droidloomd')))
R21 = '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor-build-20261120-9907-r21'
MANIFEST = {'bytes': 441804, 'identity': [66306, 61099408, 33152, 1000, 1000, 1, 441804, 1795170689478985442, 1795170689480985365], 'path': '/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/work/aosp-source/.droidloom-source-manifest.json', 'sha256': 'cb140d8937176a4e20fb5059830d3774f930aafb45c3cc7f88423b7b2d16d152'}
LOCKS = [{'actual_lock_records': [], 'body_hex': '', 'bytes': 0, 'identity': [66306, 60857531, 33152, 1000, 1000, 1, 0, 1794183129522871360, 1794183129522871360], 'path': '/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/native-full.serial.lock', 'sha256': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'}, {'actual_lock_records': [], 'body_hex': '333937323134370a', 'bytes': 8, 'identity': [66306, 60857480, 33152, 1000, 1000, 1, 8, 1795171999837515540, 1795171999837515540], 'path': '/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/work/package-build.lock', 'sha256': '700f02ed93978076edd41a3e5102e4dde120d1f808446f07f77d670c9c4f713e'}, {'actual_lock_records': [], 'body_hex': '333937323134370a', 'bytes': 8, 'identity': [66306, 60857481, 33152, 1000, 1000, 1, 8, 1795171999837515540, 1795171999837515540], 'path': '/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/work/aosp-source-update.lock', 'sha256': '700f02ed93978076edd41a3e5102e4dde120d1f808446f07f77d670c9c4f713e'}]
HISTORY = {'worker': (277931, '71e439b91b5363ed9f295589ea7b29f6404de1556b9e61af0d85c6640e4768e9'), 'contract': (83652, 'f88235f91532045e2037a42ce2a44623dc549075e93e041fb955c945d4876d3d'), 'bundle': (3519, '8cdff199f34b0922fd12b23457c17e6162f810d51f199b24b6abe5b9f47dbf47'), 'outer': (35232, '2449e863d9d96435e982ddac4675e97f6a5afd4905076f85179b18fdf1d40247'), 'terminal': (538436, '1272d9ba69e958d8e4bdd3c1b2efbf7663f42a51e29cc760fb146ee5ad06e5bd'), 'build': (330997, '88bf7e778a3d08c830f3c3e51f0e6f64e3b50feaf6a519a60d11dcb426219c1c'), 'recovery': (9720, '057c4958dafb3aaab4b5982ca71e19a701f19c8e675dc4c46c9dbd93eb61f7f1')}


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



def validate_current_release(value, binary_refs, provenance):
    need(value['schema'] == CI_SCHEMA and value['state'] == CI_STATE
         and {k: value['source_' + k] for k in ('tree', 'files', 'bytes')} == CURRENT,
         'actual complete new complete release cohort; old leaf CI is insufficient')
    need(type(provenance) is dict and set(provenance) == {'github_commit', 'github_run_id', 'source_chain'}
         and re.fullmatch('[0-9a-f]{40}', provenance['github_commit']) is not None
         and type(provenance['github_run_id']) is int and provenance['github_run_id'] > 0
         and all(value[k] == provenance[k] for k in provenance),
         'actual checked-out GitHub head/run and complete source chain')
    need(type(value['fresh_example_binaries']) is dict
         and len(value['fresh_example_binaries']) == 3,
         'all three original example binaries built without executing their mains')
    need(value['errors'] == [] and value['all_input_packet_bookends_equal'] is True
         and value['all_source_bookends_equal'] is True
         and value['final_descendant_retirement'] == [], 'actual whole CI inputs and retirement')
    need(value['fresh_ordinary_passed'] == 1588 and value['fresh_test_targets'] == 49
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
    need(len(commands) == 244 and len({x['name'] for x in commands}) == 244,
         'complete fixed current cohort command roster')
    head = commands[0]
    need(head['name'] == 'actual-github-source-head'
         and head['argv'] == ['git', 'rev-parse', 'HEAD']
         and content_reference(head['stdout'])['bytes'] == 41
         and content_reference(head['stdout'])['sha256']
             == hashlib.sha256((provenance['github_commit'] + '\n').encode()).hexdigest(),
         'actual original first Git child observed this complete checkout head')
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
    return {'schema': 'p4-r22-actual-current-release-ci-consumed-v1', **CURRENT,
            'actual_ordinary_passed': 1588, 'actual_release_binaries': 19,
            'actual_commands_reaped': len(commands), 'runtime_qualified': False,
            'production_ready': False, 'Vendor_build_credit': False}



def validate_r21_predecessor(values, refs, baseline):
    need(set(values) == {'contract', 'bundle', 'terminal', 'build', 'recovery'}
         and set(refs) == set(HISTORY), 'all original R21 source and terminal inputs')
    for name, expected in HISTORY.items():
        ref = reference(refs[name])
        need((ref['bytes'], ref['sha256']) == expected, 'immutable actual R21 input: ' + name)
    contract, bundle, terminal, build, recovery = [values[k] for k in
        ('contract', 'bundle', 'terminal', 'build', 'recovery')]
    need(contract['schema'] == 'p4-vendor-r21-operational-input-contract-v1'
         and contract['operational_inputs_frozen'] is True
         and contract['current_source']['tree'] == '4d78aae1aba2ec9952c37153069cca85c5a87953'
         and bundle['schema'] == 'pocket4-vendor-r21-launch-bundle-v1'
         and bundle['dispatch_inputs_frozen'] is True
         and bundle['source_tree'] == contract['current_source']['tree'],
         'R21 historical 2359 cohort remains distinct from the successor')
    need(content_reference(bundle['operational_contract']) == content_reference(refs['contract'])
         and content_reference(bundle['worker']) == content_reference(refs['worker'])
         and reference(terminal['worker']) == reference(refs['worker'])
         and reference(terminal['bundle']) == reference(refs['bundle']),
         'actual original outer used the exact original worker and bundle')
    need(terminal['schema'] == 'pocket4-vendor-r21-supervisor-terminal-v1'
         and terminal['passed'] is False
         and all(terminal[k] is True for k in ('build_attempted', 'serial_lock_acquired',
             'normal_recovery_attempted', 'normal_recovery_verified', 'all_owned_units_retired',
             'all_created_children_reaped', 'serial_held_through_all_source_operations'))
         and terminal['errors'] == terminal['build_retirement_errors'] == terminal['final_retirement_errors'] == []
         and terminal['fixed_deadline_exceeded'] is False,
         'actual R21 failed build and successful bounded original source recovery')
    need(len(terminal['phases']) == 2
         and [p['mode'] for p in terminal['phases']] == ['build', 'recover'],
         'original R21 build then recovery exactly once')
    for phase, code, invocation in zip(terminal['phases'], (1, 0),
            ('d9c82f1887564fdcb02f6ec493fbe912', 'd06a4376421d4ca19eda23359ecf722a')):
        client = phase['client']
        need(phase['service_retired'] is True and phase['success'] is (code == 0)
             and phase['late_start_unresolved'] is False and phase['forced_service_retirement'] is False
             and phase['errors'] == [] and phase['invocation_id'] == invocation
             and client['actual_reaped'] is True and client['original_pidfd_held_until_reaped'] is True
             and type(client['exit_code']) is int and client['exit_code'] == code
             and client['forced'] is False,
             'original phase invocation, failure/success and complete custody retirement')
    need(len(terminal['children']) == 726 and len(terminal['original_worker_status_children']) == 127,
         'whole actual original outer and status child rosters')
    for child in terminal['children']:
        need(child['actual_reaped'] is True and child['original_pidfd_held_until_reaped'] is True,
             'every original R21 outer child is reaped under its PIDFD')
    for child in terminal['original_worker_status_children']:
        command_reaped(child)
    need(build['schema'] == recovery['schema'] == 'p4-cp3a-normal-vendor-build-r21-v1'
         and build['source_tree'] == recovery['source_tree'] == contract['current_source']['tree']
         and len(build['commands']) == 6 and len(recovery['commands']) == 2,
         'exact original historical build/recovery cohort and command scopes')
    expected_build = ['verify-cmake652-before', 'normal-reconcile-lint652', 'verify-lint652-before',
        'original-cmake-provider-cmake-version', 'original-cmake-provider-ctest-version',
        'normal-official-gsi-vendor-build']
    need([c['name'] for c in build['commands']] == expected_build
         and [c['name'] for c in recovery['commands']] == ['normal-source-recovery', 'verify-lint652-after'],
         'original complete source transition, CMake checks, failed Vendor and normal recovery')
    for command, code in zip(build['commands'], (0, 0, 0, 0, 0, 1)):
        command_reaped(command, code)
    for command in recovery['commands']:
        command_reaped(command)
    need(len(build['errors']) == 1
         and build['errors'][0]['error'] == repr(RuntimeError(
             'command or retirement failed: normal-official-gsi-vendor-build'))
         and recovery['errors'] == []
         and all(recovery[k] is True for k in ('source_recovery_complete',
             'all_original_inputs_and_source_files_unchanged', 'new_lint652_source_state_verified',
             'native_source_926_members_and_git_provenance_unchanged',
             'original652_non_lint_tuples_preserved'))
         and recovery['complete_cmake_members_preserved'] == 3915,
         'original failure remains explicit; all original native and source inputs recovered')
    comparison = recovery['complete_original_lint_comparison']
    need(comparison['schema'] == 'p4-r20-six-original-lint-content-comparison-v1'
         and comparison['tracked_members_compared'] == 1045300
         and comparison['lint_materialized'] == comparison['original_lint_members'] == 6
         and comparison['lint_raw_bytes_materialized'] == 19376
         and comparison['lint_remaining_absent'] == 0
         and comparison['all_other_original_tuples_identical'] is True
         and comparison['partial_recovery_admission_only'] is False
         and comparison['Vendor_build_credit'] is False,
         'actual completed R21 six-file transition, not the new four-file transition')
    need(set(baseline) == {'manifest', 'locks'}
         and baseline['manifest'] == MANIFEST and baseline['locks'] == LOCKS
         and reference(recovery['final_normal_manifest']['original']) == MANIFEST,
         'exact current original manifest and separately observed original lock baseline')
    command = recovery['commands'][0]
    need(type(command['pid']) is int and command['pid'] == 3972147,
         'actual original normal source-recovery child')
    need(LOCKS[0]['body_hex'] == '' and LOCKS[0]['bytes'] == 0,
         'original serial body unchanged')
    for lock in LOCKS[1:]:
        raw = bytes.fromhex(lock['body_hex'])
        need(raw == (str(command['pid']) + '\n').encode()
             and len(raw) == lock['bytes'] and hashlib.sha256(raw).hexdigest() == lock['sha256']
             and command['started_ns'] <= lock['identity'][7] <= command['finished_ns']
             and command['started_ns'] <= lock['identity'][8] <= command['finished_ns']
             and lock['actual_lock_records'] == [],
             'each original PID-lock body and timestamp belongs to the actual recovered source')
    for value in (contract, bundle, terminal, build, recovery):
        need(value['production_ready'] is False and value['runtime_qualified'] is False,
             'no predecessor production or runtime credit')
    for value in (terminal, build, recovery):
        need(value['installed'] is False, 'no predecessor installation credit')
    return {'schema': 'p4-r22-actual-r21-failure-and-recovery-consumed-v1',
            'actual_R21_build_exit_code': 1, 'actual_R21_recovery_exit_code': 0,
            'original_outer_children_reaped': 726, 'original_status_children_reaped': 127,
            'new_manifest_baseline': MANIFEST, 'new_lock_baseline': LOCKS,
            'historical_failure_replaced': False, 'four_apex_provider_credit': False,
            'runtime_qualified': False, 'production_ready': False}


def validate_original_git_fixture(result):
    need(result['schema'] == 'p4-r22-real-original-git-object-partial-fixture-v1'
         and result['fixture_passed'] is True and result['errors'] == []
         and result['original_git_metadata_unchanged'] is True
         and result['all_created_git_commands_retired'] is True
         and result['fixture_source_removed'] is True
         and result['only_two_isolated_clone_projects'] is True
         and result['complete_652_production_source_qualification'] is False
         and result['source_mutations_on_original_workspace'] is False
         and result['Android_builds'] == result['Android_starts'] == 0
         and result['runtime_qualified'] is result['production_ready'] is False,
         'actual isolated two-project Git control, without production source credit')
    need(len(result['commands']) == 12
         and [r['label'] for r in result['snapshots']] == ['both-old', 'first-new-second-old',
             'both-new', 'both-new-one-original-skip-absent'],
         'all actual four partial/complete provider source states and twelve Git children')
    for command in result['commands']:
        need(type(command['exit_code']) is int and command['exit_code'] == 0
             and command['actual_reaped'] is True and command['pidfd_held_until_reaped'] is True
             and command['owned_process_group_absent'] is True and command['timed_out'] is False,
             'original fixture child execution and retirement')
    for row, count in zip(result['snapshots'], (0, 2, 4, 3)):
        need(len(row['actual_candidates']) == 4
             and sum(v['present'] is True for v in row['actual_candidates']) == count,
             'actual full original provider membership and materialization count')
    return {'fixture_passed': True, 'isolated_source_states': 4, 'created_git_commands_reaped': 12,
            'complete_652_production_source_qualification': False, 'runtime_qualified': False,
            'production_ready': False}
