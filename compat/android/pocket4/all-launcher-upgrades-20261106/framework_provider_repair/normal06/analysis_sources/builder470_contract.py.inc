def qualify_builder470_receipt(result):
    # This checks the pinned actual receipt. It does not compile or run tests.
    require(result['state'] == 'RUST_BUILD_AND_19_INDEPENDENT_FOCUSED_TESTS_PASS' and
            result['test_names'] == EXPECTED_TESTS and result['tests_passed'] == 19 and
            result['registered_tests'] == 209 and result['source_files'] == 498 and
            result['new_project_count'] == 242 and
            result['source_manifest_sha256'] == SOURCE_MANIFEST_SHA,
            'actual builder470 result/source/test closure differs')
    require([row['label'] for row in result['commands']] == EXPECTED_COMPILE_LABELS and
            all(row['returncode'] == 0 and row['timed_out'] is False for row in result['commands']) and
            len(result['independent_result_gates']) == 19,
            'actual builder470 command or independent gate closure differs')
    require(all(result[key] is True for key in ['candidate_source_unchanged_after',
                'baseline_source_unchanged_after', 'registry_input_bytes_and_full_identities_unchanged_after',
                'tool_inputs_unchanged_after']) and
            result['cleanup'] == {'complete': True, 'children': [], 'errors': []} and
            result['owned_resource_gate']['pass'] is True and
            all(result['owned_resource_gate']['events'][key] == 0 for key in ['oom', 'oom_kill', 'oom_group_kill']) and
            result['memory_peak'] == '1073741824' and result['owned_resource_gate']['events']['max'] == 657 and
            result['swap_peak'] == '0' and result['Soong_invoked'] is False and
            result['full_Android_Java_JNI_compiled'] is False and
            result['runtime_authorization_enabled'] is False and result['production_ready'] is False and
            result['Main_actions'] == result['Android_actions'] == result['install_actions'] == 0 and
            'HOME' not in result['build_environment'] and
            result['build_environment']['CARGO_NET_OFFLINE'] == 'true' and
            result['build_environment']['CARGO_BUILD_JOBS'] == '1',
            'actual builder470 source/resource/child/scope qualification differs')
    for index, name in enumerate(EXPECTED_TESTS):
        row = result['commands'][index + 4]
        log_path = BUILD_RESULT.parent / ('projection-test-' + str(index) + '.libtest')
        expected_log = ('ok ' + name + '\n').encode()
        gate = {'exact_name': name, 'expected_stdout_runs': 1, 'filtered_out_per_run': 208,
                'outer_results': 1, 'registered_tests': 209, 'summary_and_independent_result_agree': True}
        require(row['argv'] == [result['test_executable']['path'], '--exact', name,
                '--test-threads=1', '--nocapture', '--logfile', str(log_path)] and
                row['focused_result_gate'] == result['independent_result_gates'][index] == gate and
                row['independent_libtest_result']['path'] == str(log_path) and
                row['independent_libtest_result']['bytes'] == len(expected_log) and
                row['independent_libtest_result']['sha256'] == hashlib.sha256(expected_log).hexdigest(),
                'actual builder470 independent exact test differs: ' + name)
    continuity = result['dependency_continuity']
    require(continuity['all_source_bytes_and_full_identities_equal_before'] is True and
            continuity['recorded_files_and_archives'] == 2706 and continuity['selected_packages'] == 49 and
            continuity['registry_packages'] == 45 and continuity['new_dependency_fetches'] == 0 and
            len(continuity['actual_build_packages']) == len(set(continuity['actual_build_packages'])) == 49 and
            continuity['actual_build_packages'] == continuity['actual_test_compile_packages'] and
            result['source_delta'] == EXPECTED_SOURCE_DELTA,
            'actual builder470 dependency or seven-file successor differs')


def builder_contract():
    # Preserve the genuine normal05 predecessor contract and all its old
    # authorities. Neither its source nor receipts are rewritten as builder470.
    parent_path = HERE / 'parent-normal05-framework_build.py'
    parent_pin, parent_raw = held_file(parent_path, 65536, True)
    require(parent_pin['bytes'] == 60970 and
            parent_pin['sha256'] == 'f4ab5e09fc22b759811bfa9480c2de555dbc5096bc1258a984dbd33809db734b',
            'original normal05 builder contract changed')
    parent_scope = {'__name__': 'original_normal05_builder_contract', '__file__': str(parent_path)}
    exec(compile(parent_raw, str(parent_path), 'exec'), parent_scope, parent_scope)
    parent_compiled, parent_compiled_pin, parent_map, parent_map_pin, parent_builder = parent_scope['builder_contract']()
    parent_qualification, parent_qualification_pin = json_pin(
        parent_scope['QUALIFICATION_RESULT'], parent_scope['QUALIFICATION_SHA'], 65386)

    result, pin = json_pin(BUILD_RESULT, BUILD_RESULT_SHA, BUILD_RESULT_BYTES)
    staged, _ = json_pin(HERE / 'actual-builder470-result.json', BUILD_RESULT_SHA, BUILD_RESULT_BYTES)
    require(result == staged and result['baseline_compile'] == parent_compiled_pin and
            result['baseline_independent_qualification'] == parent_qualification_pin and
            result['baseline_manifest'] == parent_map_pin,
            'actual builder470 predecessor authority differs')
    qualify_builder470_receipt(result)
    # The inherited normal preflight keeps command and independent-result files
    # identity-bound on the host; no log replay or test execution is performed.
    for row in result['commands']:
        for stream in ('stdout', 'stderr'):
            observed, _ = held_file(row[stream]['path'], 32*1024*1024)
            require(observed == row[stream], 'actual builder470 command output identity changed')
    for index, name in enumerate(EXPECTED_TESTS):
        row = result['commands'][index + 4]
        actual_log, raw_log = held_file(row['independent_libtest_result']['path'], 4096, True)
        require(actual_log == row['independent_libtest_result'] and raw_log == ('ok ' + name + '\n').encode(),
                'actual held builder470 independent libtest log changed: ' + name)

    continuity = result['dependency_continuity']
    dependency_authority, _ = held_file(continuity['authority']['path'], 2*1024*1024)
    expected_packages = sorted(value.replace(str(parent_scope['BUILD_SOURCE']), str(BUILD_SOURCE))
                               for value in parent_compiled['actual_build_packages'])
    require(dependency_authority == continuity['authority'] and
            {key: continuity['authority'][key] for key in ('path', 'bytes', 'sha256')} ==
                parent_compiled['dependency_inputs'] and
            continuity['actual_build_packages'] == expected_packages and
            result['profile_authority'] == parent_qualification['original_compiler03_authority'],
            'actual builder470 original dependency/profile authority differs')
    admission, admission_pin = json_pin(BUILD_PARENT / 'compile01/resource-admission.json',
        '5b4b728f90ee088141d2cd9aaa7e242ef33e58b355c790422ed858930c926031', 2746)
    staged_admission, _ = json_pin(HERE / 'actual-builder470-resource-admission.json',
        '5b4b728f90ee088141d2cd9aaa7e242ef33e58b355c790422ed858930c926031', 2746)
    recorded_admission = result['resource_admission']
    require(admission == staged_admission and
            {key: admission_pin[key] for key in ('path', 'bytes', 'sha256')} ==
                {key: recorded_admission[key] for key in ('path', 'bytes', 'sha256')} and
            admission_pin['identity'] == recorded_admission['identity'][:3] +
                [recorded_admission['bytes']] + [int(value) for value in recorded_admission['identity'][3:]] and
            admission['profile'] == {'memory_max_bytes': 1073741824, 'memory_swap_max_bytes': 0,
                'minimum_fresh_MemAvailable_bytes': 3221225472, 'admission_difference_bytes': 2147483648,
                'global_swap_is_owned_budget': False} and
            admission['owned_observed'] == {'memory.max': '1073741824', 'cpu.max': '100000 100000',
                'memory.swap.max': '0', 'memory.swap.current': '0'} and
            parse_admission_meminfo(admission['meminfo']['raw_ascii'].encode('ascii'))['MemAvailable'] >= 3*1024**3 and
            len(result['cpu_affinity']) == 1,
            'actual builder470 one-GiB Rust resource authority differs')

    source_map, source_pin = json_pin(BUILDER_MANIFEST, SOURCE_MANIFEST_SHA, 99075)
    staged_map, _ = json_pin(HERE / 'expected-builder470-manifest.json', SOURCE_MANIFEST_SHA, 99075)
    changed = sorted(name for name in parent_map if source_map.get(name) != parent_map[name])
    added = sorted(set(source_map) - set(parent_map))
    require(source_map == staged_map and result['candidate_manifest'] == source_pin and
            len(source_map) == 498 and set(parent_map) <= set(source_map) and
            changed == EXPECTED_SOURCE_DELTA['changed_existing'] and added == EXPECTED_SOURCE_DELTA['added'] and
            source_map[GO_PATCH]['sha256'] == GO_PATCH_SHA and
            source_map['android/manifest/m2-role-ingress-source-lock.json']['sha256'] == PREVIOUS_TYPED_LOCK_SHA and
            source_map['android/manifest/m2-role-ingress-provider-source-lock.json']['sha256'] == PREVIOUS_PROVIDER_LOCK_SHA and
            source_map['android/manifest/m2-role-ingress-provider2-source-lock.json']['sha256'] == PREVIOUS_NATIVE_PROVIDER_LOCK_SHA and
            source_map['android/manifest/m2-role-ingress-provider3-source-lock.json']['sha256'] == EXTENDED_LOCK_SHA,
            'full builder470 source manifest is not the exact seven-file successor')
    builder, _ = held_file(BUILDER, 64*1024*1024)
    match_compile_pin(builder, result['builder'])
    require(builder['sha256'] == BUILDER_SHA and builder['bytes'] == BUILDER_BYTES and
            builder['identity'][2] & 0o111,
            'actual builder470 ELF changed')
    return result, pin, source_map, source_pin, builder
