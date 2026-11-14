"""Read-only exact native full-build release consumer for candidate staging."""
import hashlib
from pathlib import Path
import re
FINAL = Path('/home/alex/work/pocket4-android-final')


def native_release(io, witness, requested, native_info):
    """Consume the actual 8 GiB full build derived from R11, never source-only or caller predicates.

    All four requested refs are actual create-only output files. Future hashes
    are deliberately not supplied here. The immutable execution binding fixes
    the controller, packet, source generation and output paths. Nonzero or
    unknown adopted-child statuses have no inherited historical exception.
    """
    root = FINAL / 'native'
    run = root / 'attempts/full-build-native597-8gib-hostreserve5-20261108-r1'
    attempt = root / 'attempt-native597-8gib-hostreserve5-20261108-r1'
    fences = root / 'build-fences-native597-8gib-hostreserve5-20261108-r1'
    out = root / 'android-out-native597-8gib-hostreserve5-20261108-r1'
    jobs = Path('/home/alex/.local/state/hepta-runtime-mac-worker/jobs')
    targets = ['libberberis_arm64', 'com.android.art']
    keys = {'runtime_request', 'runtime_exit', 'outer_runtime_admission',
            'parent_work_lease_terminal'}
    io.need(type(requested) is dict and set(requested) == keys,
            'NATIVE_R11_EXACT_COMPLETED_OUTPUT_REFS_REQUIRED')
    proofs = []; conditions = []

    def equal(actual, expected, label):
        io.need(type(actual) is type(expected) and actual == expected
                and (type(actual) is set or io.encode(actual) == io.encode(expected)), 'NATIVE_R11_' + label)

    def read(ref, path, *, json=True, proof=False):
        io.need(type(ref) is dict and {'path', 'bytes', 'sha256'} <= set(ref)
                and ref['path'] == str(path) and type(ref['bytes']) is int
                and ref['bytes'] > 0 and type(ref['sha256']) is str
                and re.fullmatch('[0-9a-f]{64}', ref['sha256']),
                'NATIVE_R11_EXACT_ACTUAL_FILE_REF:' + str(path))
        # The original build held_file records six fields. Qualification and
        # stage_io use nine fields. Compare every original field by its meaning.
        value, pin = witness.read(io.short(ref), json=json)
        io.need(pin['identity'][5] == 1, 'NATIVE_R11_SINGLE_LINK_EVIDENCE')
        if 'identity' in ref:
            expected = ref['identity']
            actual = pin['identity']
            if type(expected) is list and len(expected) == 6:
                actual = [actual[i] for i in (0, 1, 2, 6, 7, 8)]
            equal(actual, expected, 'ORIGINAL_IDENTITY_CHANGED')
        if proof:
            index = len(proofs)
            proofs.append(io.short(pin))
            # The reviewed predicates below validate the complete documents;
            # these fixed, SHA-bound values preserve that decision at maintenance.
            for key in value:
                conditions.append({'proof': index, 'path': [key], 'equals': value[key]})
        return value, pin

    binding, _ = read({'path': str(root / 'manifests/native597-8gib-hostreserve5-normal-execution-binding-20261108-r1.json'),
        'bytes': 75828, 'sha256': 'bc1aa383f812245b45c7e1f76310cadbe95ac89528ac27a5bc8c0c0ff1eaea94'},
        root / 'manifests/native597-8gib-hostreserve5-normal-execution-binding-20261108-r1.json')
    equal(binding['schema'], 'pocket4-native597-normal-execution-binding-v1', 'BINDING_SCHEMA')
    equal(binding['prior_child_attribution_applies_to_new_attempt'], False, 'HISTORICAL_EXCEPTION')
    plan = binding['plan']
    equal(plan['targets'], targets, 'TARGETS')
    equal(plan['dependency_mode'], 'Strict', 'STRICT_DEPENDENCIES')
    equal(plan['builder_source_files'], 515, 'FULL_BUILDER_SOURCE_COUNT')
    equal(plan['out'], str(out), 'OUTPUT_GENERATION')
    equal(plan['resource_profile_id'], 'native597-8gib-hostreserve5-20261108-r1', 'RESOURCE_PROFILE')
    equal(plan['memory_max_bytes'], 8 * 1024**3, 'OWN_HARD_CAP')
    equal(plan['fresh_MemAvailable_min_bytes'], 13 * 1024**3, 'FRESH_HOST_FLOOR')
    equal(plan['admission_difference_bytes'], 5 * 1024**3, 'HOST_RESERVE')
    packet, packet_pin = read(binding['packet'], run / 'build-packet.json')
    for name, filename in (('controller', 'framework_build.py'), ('outer', 'fenced_build.py'),
                           ('launcher', 'launch_build.py')):
        _, pin = read(binding['sources'][name], run / filename, json=False)
        if name != 'launcher':
            equal(hashlib.sha256(packet[name + '_source'].encode()).hexdigest(),
                  pin['sha256'], 'EMBEDDED_SOURCE_' + name)

    request_ref = requested['runtime_request']
    io.need(type(request_ref) is dict and type(request_ref.get('path')) is str,
            'NATIVE_R11_RAW_REQUEST_REF')
    request_path = Path(request_ref['path'])
    job = request_path.parent.name
    io.need(re.fullmatch('[0-9a-f]+-[0-9a-f]+-[0-9a-f]+', job) is not None,
            'NATIVE_R11_ACTUAL_JOB_ID')
    request, request_pin = read(request_ref, jobs / job / 'request.json', proof=True)
    for name, expected in {'job_id': job, 'job_dir': str(jobs / job),
            'unit': 'hepta-runtime-job-' + job, 'execution_mode': 'operator',
            'executable': '/usr/bin/python3', 'args': ['-I', str(run / 'launch_build.py'), packet_pin['sha256']],
            'cwd': str(run), 'timeout_seconds': 23000, 'memory_max_bytes': 8 * 1024**3,
            'cpu_quota_percent': 200, 'nice': 10, 'env': {}, 'terminal_publication_protocol': 1}.items():
        equal(request[name], expected, 'REQUEST_' + name)
    io.need(type(request['launch_nonce']) is str and re.fullmatch('[0-9a-f]{32}', request['launch_nonce']),
            'NATIVE_R11_ACTUAL_LAUNCH_NONCE')
    exited, _ = read(requested['runtime_exit'], jobs / job / 'exit.json', proof=True)
    equal(set(exited), {'at_unix_ms', 'cancelled', 'exit_code', 'job_id', 'launch_nonce',
        'log_bytes', 'log_errors', 'log_synced', 'log_truncated', 'output_complete',
        'output_durable', 'terminal_publication_protocol', 'timed_out'}, 'RAW_H_EXIT_SCHEMA')
    for name, expected in {'job_id': job, 'launch_nonce': request['launch_nonce'], 'exit_code': 0,
            'cancelled': False, 'timed_out': False, 'output_complete': True, 'output_durable': True,
            'terminal_publication_protocol': 1}.items():
        equal(exited[name], expected, 'RAW_H_EXIT_' + name)
    for name, expected in (('log_errors', None), ('log_synced', True), ('log_truncated', False)):
        equal(exited[name], {'stdout': expected, 'stderr': expected}, 'RAW_H_' + name)
    equal(set(exited['log_bytes']), {'stdout', 'stderr'}, 'RAW_H_STREAMS')
    for row in exited['log_bytes'].values():
        io.need(set(row) == {'seen', 'stored'} and type(row['seen']) is int
                and type(row['stored']) is int and row['seen'] == row['stored'] >= 0,
                'NATIVE_R11_COMPLETE_DURABLE_LOGS')
    admission, _ = read(requested['outer_runtime_admission'], run / 'outer-runtime-admission.json', proof=True)
    for name, expected in {'schema': 'pocket4-native597-outer-runtime-admission-v1',
            'state': 'ACTUAL_OUTER_RUNTIME_VERIFIED_BUILD_PENDING', 'job_id': job,
            'actual_request': io.short(request_pin), 'packet': io.short(packet_pin),
            'outer_timeout_seconds': 23000, 'normal_build_timeout_seconds': 21600}.items():
        equal(admission[name], expected, 'ADMISSION_' + name)
    runner_ref = admission['actual_runtime_runner']
    equal(runner_ref, {'path': str(jobs / job / 'runner.py'), 'bytes': 40463,
        'sha256': '65564ce756f3a341def2cf34b2c0d54ef3e75960923c6002c4c56db13564ebf1'}, 'RUNTIME_RUNNER')
    read(runner_ref, jobs / job / 'runner.py', json=False)

    parent, _ = read(requested['parent_work_lease_terminal'], run / 'parent-work-lease-terminal.json', proof=True)
    for name, expected in {'schema': 'native597-full-parent-work-lease-v1', 'errors': [],
            'outer_invoked': True, 'outer_returned': True, 'outer_returncode': 0,
            'owned_retirement_complete': True, 'owned_children_after_outer': [],
            'source_restore_check_completed': True, 'source_projection_restored': True,
            'native_two_locks_free_after_outer': True, 'full_build_success': True,
            'global_admission_granted': False, 'normal_updater_owns_native_two': True}.items():
        equal(parent[name], expected, 'PARENT_' + name)
    inner, _ = read(parent['inner_terminal'], attempt / 'terminal.json', proof=True)
    outer, _ = read(parent['outer_terminal'], fences / 'terminal.json', proof=True)
    for name, expected in {'schema': 1, 'state': 'ORDINARY_PAIR_COMMAND_COMPLETED_QUALIFICATION_PENDING',
            'builder_returncode': 0, 'error': None, 'input_after_qualified': True, 'input_after_error': None,
            'source_projection_journal_present': False, 'strict_targets': targets,
            'builder_sha256': plan['builder_sha256'], 'runtime_authorization_enabled': False,
            'Main_actions': 0, 'Android_actions': 0, 'all_apps_ready': False}.items():
        equal(inner[name], expected, 'INNER_' + name)
    equal(inner.get('observation_errors', []), [], 'INNER_OBSERVATION_ERRORS')
    cleanup = inner['cleanup']
    equal(cleanup['complete'], True, 'OWNED_RETIREMENT_COMPLETE')
    equal(cleanup.get('errors'), [], 'OWNED_RETIREMENT_ERRORS')
    equal(cleanup.get('remaining', []), [], 'OWNED_REMAINING_CHILDREN')
    children = cleanup.get('children')
    io.need(type(children) is list and len(children) <= 4096, 'NATIVE_R11_BOUNDED_CHILDREN')
    seen = set()
    for child in children:
        io.need(type(child) is dict and type(child.get('pid')) is int and child['pid'] > 1
                and child['pid'] not in seen, 'NATIVE_R11_DISTINCT_OWNED_CHILD')
        seen.add(child['pid'])
        equal(child.get('reaped'), True, 'OWNED_CHILD_REAPED')
        equal(child.get('wait_status'), 0, 'OWNED_CHILD_RAW_ZERO_STATUS')
    equal(parent['original_inner_cleanup_summary'], {'complete': True, 'child_record_count': len(children),
        'error_count': 0, 'remaining_count': 0, 'complete_original_in_inner_terminal_reference': True},
        'PARENT_ORIGINAL_CLEANUP')
    equal(parent['original_input_after_qualified'], True, 'PARENT_INPUT_RESTORATION')
    rows = inner['memory_events'].splitlines()
    words = [line.split() for line in rows]
    io.need(words and all(len(x) == 2 and x[1].isdigit() for x in words), 'NATIVE_R11_MEMORY_EVENTS')
    events = {name: int(value) for name, value in words}
    io.need(len(events) == len(words) and all(events.get(name) == 0 for name in ('oom', 'oom_kill', 'oom_group_kill')),
            'NATIVE_R11_NO_OWNED_OOM')
    equal(inner['owned_resource_gate']['pass'], True, 'RESOURCE_GATE')
    equal(inner['owned_resource_gate']['events'], events, 'RESOURCE_RAW_EVENTS')
    for key in ('memory_swap_max', 'memory_swap_current', 'memory_swap_peak'):
        equal(inner[key], '0', 'ZERO_SWAP_' + key)
    equal(inner['owned_budget_before_builder'], {'memory.max': str(8 * 1024**3),
        'cpu.max': '200000 100000', 'memory.swap.max': '0', 'memory.swap.current': '0'}, 'OWNED_BUDGET')
    resource, _ = read(inner['resource_admission_receipt'],
        root / 'resource-admission-native597-8gib-hostreserve5-20261108-r1.json', proof=True)
    for name, expected in {'schema': 1, 'state': 'OBSERVED_BEFORE_RESOURCE_ADMISSION',
            'decision_performed': False, 'historical_sample_used_for_admission': False,
            'Main_actions': 0, 'Android_actions': 0, 'production_ready': False,
            'profile': {'resource_profile_id': plan['resource_profile_id'],
                'memory_max_bytes': 8 * 1024**3, 'memory_swap_max_bytes': 0,
                'minimum_fresh_MemAvailable_bytes': 13 * 1024**3,
                'admission_difference_bytes': 5 * 1024**3, 'global_swap_is_owned_budget': False},
            'owned_observed': inner['owned_budget_before_builder']}.items():
        equal(resource[name], expected, 'ACTUAL_ADMISSION_' + name)
    cgroup = '/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-' + job + '.service'
    equal(resource['owned_cgroup'], '/sys/fs/cgroup' + cgroup, 'ACTUAL_RESOURCE_CGROUP')
    equal(admission['outer_cgroup'], '0::' + cgroup, 'ACTUAL_OUTER_CGROUP')
    meminfo = resource['meminfo']
    equal(meminfo['path'], '/proc/meminfo', 'FRESH_MEMINFO_PATH')
    raw_memory = meminfo['raw_ascii'].encode('ascii', 'strict')
    io.need(0 < len(raw_memory) <= 16384, 'NATIVE_R11_BOUNDED_FRESH_MEMINFO')
    equal(meminfo['bytes'], len(raw_memory), 'FRESH_MEMINFO_BYTES')
    equal(meminfo['sha256'], hashlib.sha256(raw_memory).hexdigest(), 'FRESH_MEMINFO_HASH')
    memory = {}; memory_names = {'MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree', 'SwapCached'}
    for line in raw_memory.decode('ascii').splitlines():
        name, separator, value = line.partition(':')
        if name in memory_names:
            parts = value.split()
            io.need(name not in memory and separator == ':' and len(parts) == 2
                    and parts[0].isdigit() and parts[1] == 'kB', 'NATIVE_R11_FRESH_MEMINFO_UNITS')
            memory[name] = int(parts[0]) * 1024
    io.need(set(memory) == memory_names and 13 * 1024**3 <= memory['MemAvailable'] <= memory['MemTotal']
            and 0 <= memory['SwapFree'] <= memory['SwapTotal'] and memory['SwapCached'] >= 0,
            'NATIVE_R11_ACTUAL_FRESH_13GIB_ADMISSION')
    sample_ns = resource['observed_unix_ns_decimal']
    io.need(type(sample_ns) is str and sample_ns.isdecimal()
            and parent['started_ns'] <= int(sample_ns) <= parent['source_restore_check_completed_ns'],
            'NATIVE_R11_CURRENT_ATTEMPT_RESOURCE_SAMPLE')

    complete = inner['normal_command_completion_gate']
    for name, expected in {'state': 'ORDINARY_PAIR_COMMAND_COMPLETED_ARTIFACT_QUALIFICATION_PENDING',
            'pair': native_info['pair'], 'published_projects': 597, 'published_root_links': 8,
            'targets': targets, 'dependency_mode': 'Strict', 'source_projection_restored': True,
            'runtime_authorization_enabled': False, 'installation_performed': False}.items():
        equal(complete[name], expected, 'ACTUAL_PAIR_' + name)
    equal(set(complete['records']), {'droidloom-native-generation-build-' + name + '.json'
        for name in ('attempt', 'inputs', 'command')}, 'ACTUAL_ORDINARY_RECORD_SET')
    for name in ('attempt', 'inputs', 'command'):
        path = out / ('droidloom-native-generation-build-' + name + '.json')
        _, pin = read(complete['records'][path.name], path)
        equal(io.short(pin), io.short(native_info['ordinary_records'][name]), 'SAME_QUALIFIED_BUILD_' + name)
    for name, role in (('engine', 'engine'), ('whole_ART_APEX', 'art_apex')):
        ref = native_info['sources'][role]
        _, pin = read(complete[name], Path(ref['path']), json=False)
        equal(io.short(pin), io.short(ref), 'SAME_QUALIFIED_PRODUCT_' + role)
    offline, _ = witness.read(native_info['offline'], json=True)
    _, product_pair = read(complete['actual_product_pair'], out / 'target/product/droidloom_x86_64/droidloom-native-generation-pair.json')
    equal(io.short(product_pair), io.short(offline['pair_file']), 'SAME_ORIGINAL_PAIR_RECORD')
    _, manifest = read(complete['actual_published_manifest'], root / 'work/aosp-source/.droidloom-source-manifest.json')
    equal(manifest['sha256'], plan['published_source_manifest_sha256'], 'SAME_597_MANIFEST')

    for name, expected in {'schema': 1, 'state': 'OFFLINE_BUILD_AND_STOPPED_COHORT_FENCES_PASSED',
            'error': None, 'inner_build_called': True, 'inner_returncode': 0,
            'before_observed': True, 'after_observed': True, 'Main_actions': 0, 'Android_actions': 0,
            'installed': False, 'production_ready': False, 'runtime_authorization_enabled': False,
            'restart_requires_new_generation_qualification': True}.items():
        equal(outer[name], expected, 'OUTER_' + name)
    equal(outer['stopped_cohort_fence_assessment'], {'stopped_cohort_fence_pass': True,
        'changed_invariants': [], 'live_Main_fence_pass': False,
        'stopped_generation_absence_checked_before_and_after': True,
        'continuous_absence_or_unobserved_interference_excluded': False,
        'runtime_authorization_enabled': False, 'new_generation_qualification_required_after_restart': True},
        'STOPPED_FENCE')
    controls = outer['capture_lifecycle_controls']
    equal(controls['state'], 'PASS', 'CAPTURE_CONTROLS')
    equal(controls['passed'], 4, 'CAPTURE_CONTROL_COUNT')
    io.need(len(controls['rows']) == 4 and all(row['passed'] is True and row['owned_children_empty'] is True
        for row in controls['rows']), 'NATIVE_R11_CAPTURE_CONTROL_RETIREMENT')
    captures = [row for row in outer['capture_lifecycle_receipts'] if row['phase'] in ('before', 'after')]
    io.need(len(captures) == 2 and {row['phase'] for row in captures} == {'before', 'after'},
            'NATIVE_R11_BOTH_ACTUAL_CAPTURES')
    for capture in captures:
        equal(capture['qualified_success'], True, 'CAPTURE_SUCCESS')
        equal(capture['first_error'], None, 'CAPTURE_ERROR')
        equal(capture['secondary_errors'], [], 'CAPTURE_SECONDARY_ERRORS')
        command = capture['command']
        for key in ('child_reaped', 'owned_tree_cleanup_complete', 'all_acquired_fds_closed',
                    'retirement_within_deadline', 'qualified_success'):
            equal(command[key], True, 'CAPTURE_' + key)
        equal(command['returncode'], 0, 'CAPTURE_RETURN')
        equal(command['remaining_owned_children'], [], 'CAPTURE_REMAINING')
        equal(command['descendants'], [], 'CAPTURE_UNEXPECTED_DESCENDANTS')

    works = (root / 'work', FINAL / 'framework/work',
             Path('/home/alex/work/pocket4-audio-source-build-20261108-r1/work'))
    all_paths = {str(work / name) for work in works for name in ('package-build.lock', 'aosp-source-update.lock')}
    fresh = parent['fresh_six_locks']
    io.need(len(fresh) == 6 and {row['path'] for row in fresh} == all_paths
            and len({tuple(row['identity'][:2]) for row in fresh}) == 6
            and all(row['observed_free'] is True for row in fresh), 'NATIVE_R11_SIX_DISTINCT_ORIGINAL_LOCKS')
    parent_paths = {str(work / name) for work in works[1:] for name in ('package-build.lock', 'aosp-source-update.lock')}
    leased = parent['parent_leases']; release = parent['lease_release']
    io.need(len(leased) == 4 and {row['path'] for row in leased} == parent_paths,
            'NATIVE_R11_FOUR_PARENT_LEASES')
    for name, expected in {'qualified': True, 'all_parent_descriptors_closed': True,
            'remaining_parent_kernel_locks': [], 'errors': []}.items():
        equal(release[name], expected, 'LEASE_RELEASE_' + name)
    io.need(len(release['rows']) == 4 and {row['path'] for row in release['rows']} == parent_paths,
            'NATIVE_R11_ALL_FOUR_RELEASE_ROWS')
    for row in release['rows']:
        prior = next(item for item in leased if item['path'] == row['path'])
        equal({key: row[key] for key in prior}, prior, 'UNCHANGED_PARENT_LEASE')
        equal(row['descriptor_closed'], True, 'PARENT_DESCRIPTOR_CLOSED')
        io.need(prior['acquired_ns'] <= parent['started_ns'] <= parent['source_restore_check_completed_ns']
                <= row['released_ns'] <= parent['finished_ns'], 'NATIVE_R11_RELEASE_AFTER_RESTORATION')
    equal(parent['projection_observations'], [{'path': str(work / 'source-projection.json'), 'absent': True}
        for work in works], 'ALL_THREE_JOURNALS_RESTORED')
    for work in works:
        path = work / 'source-projection.json'
        observed, _ = io.held_read(path, absent=True)
        equal(observed, {'path': str(path), 'absent': True}, 'JOURNAL_REAPPEARED')
        witness.observed[str(path)] = observed
    io.need(type(exited['at_unix_ms']) is int and exited['at_unix_ms'] >= parent['finished_ns'] // 1000000,
            'NATIVE_R11_RAW_EXIT_FOLLOWS_PARENT_RETIREMENT')
    gate = {'proofs': proofs, 'conditions': conditions}
    witness.gate(gate)
    return gate

