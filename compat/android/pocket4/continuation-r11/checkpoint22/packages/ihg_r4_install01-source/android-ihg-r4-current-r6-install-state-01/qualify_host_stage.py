def qualify_host_stage(value, manifest):
    require(type(value) is dict and
            value.get('schema') == 'pocket4-current-host-source-stage-v2' and
            value.get('ok') is True and value.get('error') is None and
            value.get('secondary_errors') == [] and
            value.get('actual_source_constructor_qualified') is True and
            value.get('all_staged_sources_unchanged') is True and
            value.get('source_root') == str(BASE_HOST_ROOT) and
            value.get('source_manifest_sha256') == RECORDER_MANIFEST,
            'ACTUAL_COMPLETE_R6_HOST_SOURCE_STAGE_REQUIRED')
    require(manifest.get('schema') == 2 and manifest.get('revision') == 6 and
            manifest.get('artifact') == 'pocket4-bilibili-current-recorder-held-r6' and
            len(manifest.get('files', {})) == 14,
            'EXACT_R6_HOST_MANIFEST_REQUIRED')
    expected_sources = {name:{'path':str(BASE_HOST_ROOT/name),**row}
                        for name,row in manifest['files'].items()}
    expected_sources['source-manifest.json'] = {
        'path':str(BASE_HOST_ROOT/'source-manifest.json'),
        'bytes':3757,'sha256':RECORDER_MANIFEST}
    require(value.get('source_pins') == expected_sources,
            'ACTUAL_R6_PUBLISHED_SOURCE_PINS_REQUIRED')
    controls = value.get('controls', {})
    require(controls.get('schema') == 'pocket4-current-host-source-controls-v2' and
            controls.get('all_passed') is True and controls.get('count') == 38 and
            len(controls.get('cases', [])) == 38 and
            len({x.get('name') for x in controls['cases']}) == 38 and
            all(x.get('passed') is True for x in controls['cases']) and
            controls.get('compiled_sources') == sorted(manifest['files']) and
            controls.get('fixture_is_not_baseline_observation') is True and
            all(type(controls.get(k)) is int and controls[k] == 0
                for k in ('Android_commands','UI_actions','children','filesystem_operations')),
            'ACTUAL_38_CURRENT_HOST_CONTROLS_REQUIRED')
    for bucket in ('source_fds','publication_fds'):
        fds = value.get(bucket, {})
        require(fds.get('scope') == 'collector_managed_descriptors' and
                all(type(fds.get(k)) is int for k in ('acquired','close_attempts','closed','remaining')) and
                fds['acquired'] > 0 and
                fds['acquired'] == fds['close_attempts'] == fds['closed'] and
                fds['remaining'] == 0 and fds.get('errors') == [],
                'ACTUAL_CURRENT_HOST_SOURCE_FDS_NOT_RETIRED')
    expected_guard = {'schema':'pocket4-current-main-guard-v2',
        'Main_epoch_sha256':CURRENT_EPOCH, 'current_baseline_sha256':BASELINE_SHA,
        'current_baseline_qualification_sha256':QUALIFICATION_SHA,
        'historical_activation_sha256':'7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615',
        'historical_verified_sha256':'2d6f2ef7953b98109044f823da56694111bd9f8ff14fff5e746afb7bd42b0387',
        'previous_current_baseline_sha256':'163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266',
        'config_sha256':'f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc',
        'seven_processes_match':True, 'three_host_processes_match':True,
        'authenticated_owner_chain_matches':True, 'current_user_namespaces_match':True,
        'resource_limits_match':True, 'current_executable_and_root_backing_match':True,
        'old_helpers_and_tasks_reauthorized':False,
        'framework_exit_cause_resolved':False, 'production_ready':False}
    require(all(value.get(k) == expected_guard for k in ('Main_before','Main_after','Main_final')),
            'CURRENT_HOST_STAGE_MAIN_FENCES_CHANGED')
    require(value.get('source_only') is True and value.get('runtime_admitted') is False and
            value.get('namespace_entry') is False and
            value.get('old_helpers_and_tasks_reauthorized') is False and
            value.get('whole_app_production_ready') is False and
            all(type(value.get(k)) is int and value[k] == 0 for k in
                ('Android_commands','UI_actions','helper_installs','App_launches','children_spawned')),
            'CURRENT_HOST_STAGE_SCOPE_NOT_READONLY_SOURCE')
    durable = {k:v for k,v in value.items() if k not in ('stage_result','publication_fds')}
    raw = (json.dumps(durable,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
    require(value.get('stage_result') == {
                'path':str(BASE_HOST_ROOT/'stage-result.json'),'bytes':len(raw),'sha256':digest(raw)},
            'ACTUAL_R6_DURABLE_STAGE_PIN_REQUIRED')
    return True


