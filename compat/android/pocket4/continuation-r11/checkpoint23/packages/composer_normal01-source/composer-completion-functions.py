def qualify_composer_records(attempt, inputs, command, manifest_sha, source_map):
    require(set(attempt) == {
        'schema', 'state', 'targets', 'dependency_mode', 'source_lock', 'source_lock_sha256',
        'locked_projects', 'fixed_production_inputs', 'fixed_checkout_declarations',
        'source_projection_journal', 'command_completed', 'tests_executed',
        'Android_Binder_ABI_qualified', 'Wayland_GPU_runtime_qualified',
        'installation_performed', 'service_activation_performed'} and
        set(inputs) == {
            'schema', 'targets', 'dependency_mode', 'ALLOW_MISSING_DEPENDENCIES',
            'source_lock_sha256', 'materialized_manifest_sha256', 'fixed_production_inputs',
            'nine_production_vendor_mirrors_exact', 'fixed_checkout_declarations',
            'effective_vendor_Android_bp_sha256', 'source_projection', 'tests_executed',
            'Android_Binder_ABI_qualified', 'Wayland_GPU_runtime_qualified',
            'installation_performed', 'service_activation_performed'} and
        set(command) == {
            'schema', 'state', 'targets', 'dependency_mode', 'source_projection_restored',
            'tests_executed', 'actual_ELF_AIDL_and_native_link_inputs_qualified',
            'Android_Binder_ABI_qualified', 'Wayland_GPU_runtime_qualified',
            'installation_performed', 'service_activation_performed'},
        'COMPOSER_RECORD_FIELDS')
    for document in [attempt, inputs, command]:
        require(type(document['schema']) is int and document['schema'] == 1 and
                document['targets'] == TARGETS and document['dependency_mode'] == 'Strict' and
                all(document[key] is False for key in [
                    'tests_executed', 'Android_Binder_ABI_qualified',
                    'Wayland_GPU_runtime_qualified', 'installation_performed',
                    'service_activation_performed']), 'COMPOSER_RECORD_SCOPE')
    require(attempt['state'] == 'CLAIMED_BEFORE_FRESH_SOURCE_VERIFICATION_OR_PROJECTION' and
            attempt['source_lock'] == str(BUILD_SOURCE / 'android/manifest/m2-role-ingress-hal-provider-source-lock.json') and
            attempt['source_lock_sha256'] == EXTENDED_LOCK_SHA and
            type(attempt['locked_projects']) is int and attempt['locked_projects'] == 225 and
            attempt['source_projection_journal'] == str(WORK / 'source-projection.json') and
            attempt['command_completed'] is False, 'COMPOSER_ATTEMPT_BINDING')
    for document in [attempt, inputs]:
        require(document['fixed_production_inputs'] == COMPOSER_INPUTS and
                document['fixed_checkout_declarations'] == COMPOSER_DECLARATIONS,
                'COMPOSER_FIXED_INPUTS')
    require(inputs['ALLOW_MISSING_DEPENDENCIES'] is False and
            inputs['source_lock_sha256'] == EXTENDED_LOCK_SHA and
            inputs['materialized_manifest_sha256'] == manifest_sha and
            inputs['nine_production_vendor_mirrors_exact'] is True,
            'COMPOSER_INPUT_BINDING')
    projection = inputs['source_projection']
    require(isinstance(projection, dict) and set(projection) == {'files', 'patches'} and
            isinstance(projection['files'], dict) and isinstance(projection['patches'], dict),
            'COMPOSER_PROJECTION_SHAPE')
    for kind in ['files', 'patches']:
        for relative, value in projection[kind].items():
            require(isinstance(relative, str) and bool(relative) and
                    not pathlib.PurePosixPath(relative).is_absolute() and
                    '..' not in pathlib.PurePosixPath(relative).parts and
                    str(pathlib.PurePosixPath(relative)) == relative and
                    (value is None and kind == 'files' or
                     isinstance(value, str) and len(value) == 64 and
                     all(c in '0123456789abcdef' for c in value)),
                    'COMPOSER_PROJECTION_SHAPE')
    require(all(projection['files'].get(relative) == row['projected_sha256']
                for relative, row in COMPOSER_PROJECTED_BLUEPRINTS.items()),
            'COMPOSER_EXACT_PROJECTION')
    effective = inputs['effective_vendor_Android_bp_sha256']
    # The exact Composer route copies this root Blueprint unchanged. Only the
    # disjoint NativeBridge-only route projects it after the vendor mirror.
    require(effective == COMPOSER_DECLARATIONS['Android.bp']['sha256'] and
            'vendor/droidloom/Android.bp' not in projection['files'],
            'COMPOSER_VENDOR_BLUEPRINT')
    for relative, value in projection['patches'].items():
        require(relative in source_map and source_map[relative]['kind'] == 'file' and
                source_map[relative]['sha256'] == value, 'COMPOSER_PROJECTED_PATCH')
    require(projection['patches'].get(GO_PATCH) == GO_PATCH_SHA and
            projection['patches'].get('android/apex-compat/0009-blueprint-stream-uncached-module-actions.patch') ==
                source_map['android/apex-compat/0009-blueprint-stream-uncached-module-actions.patch']['sha256'] and
            'android/apex-compat/0007-transitive-default-missing-dependencies.patch' not in projection['patches'],
            'COMPOSER_STRICT_PATCH_SCOPE')
    require(command['state'] == 'NORMAL_BUILD_COMMAND_SUCCEEDED' and
            command['source_projection_restored'] is True and
            command['actual_ELF_AIDL_and_native_link_inputs_qualified'] is False,
            'COMPOSER_COMMAND')


def completion_gate(context):
    records = {}
    for name in ['droidloom-composer-retirement-attempt.json',
                 'droidloom-composer-retirement-inputs.json',
                 'droidloom-composer-retirement-command.json']:
        row, raw = held_file(OUT / name, 8*1024*1024, True)
        records[name] = (json.loads(raw), row)
    attempt = records['droidloom-composer-retirement-attempt.json'][0]
    inputs = records['droidloom-composer-retirement-inputs.json'][0]
    command = records['droidloom-composer-retirement-command.json'][0]
    require(not (WORK / 'source-projection.json').exists() and
            not (WORK / 'source-projection.json').is_symlink(),
            'normal source projection did not finish restoration')
    lock, _ = json_pin(BUILD_SOURCE / 'android/manifest/m2-role-ingress-hal-provider-source-lock.json',
                       EXTENDED_LOCK_SHA, 96957)
    manifest_pin, manifest_raw = held_file(PUBLISHED_SOURCE / '.droidloom-source-manifest.json', 1024*1024, True)
    qualify_completed_manifest(json.loads(manifest_raw), lock)
    qualify_composer_records(attempt, inputs, command, manifest_pin['sha256'], context['builder_map'])
    native_bp, _ = held_file(PUBLISHED_SOURCE / 'prebuilts/misc/common/robolectric-native-prebuilt/Android.bp', 65536)
    require(native_bp['bytes'] == NATIVE_PREBUILT_BP_BYTES and native_bp['sha256'] == NATIVE_PREBUILT_BP_SHA,
            'locked native prebuilt provider body differs after the normal build')
    restored = {}
    for relative, expected in COMPOSER_PROJECTED_BLUEPRINTS.items():
        row, _ = held_file(PUBLISHED_SOURCE / relative, 65536)
        require(row['bytes'] == expected['bytes'] and row['sha256'] == expected['sha256'],
                'Composer exact Blueprint original was not restored: ' + relative)
        restored[relative] = row
    vendor_bp, _ = held_file(PUBLISHED_SOURCE / 'vendor/droidloom/Android.bp', 65536)
    require(vendor_bp['bytes'] == COMPOSER_DECLARATIONS['Android.bp']['bytes'] and
            vendor_bp['sha256'] == COMPOSER_DECLARATIONS['Android.bp']['sha256'],
            'Composer vendor Blueprint differs from the exact copied source')
    mirrors = {}
    for relative, expected in COMPOSER_INPUTS.items():
        row, _ = held_file(PUBLISHED_SOURCE / 'vendor/droidloom' / relative, 1024*1024)
        require(row['bytes'] == expected['bytes'] and row['sha256'] == expected['sha256'],
                'Composer fixed production mirror changed after build: ' + relative)
        mirrors[relative] = row
    return {'state': 'COMPOSER_NORMAL_COMMAND_COMPLETED_ARTIFACT_QUALIFICATION_PENDING',
        'records': {name: row for name, (_, row) in records.items()},
        'actual_published_manifest': manifest_pin, 'published_projects': 225, 'published_root_links': 8,
        'actual_locked_native_prebuilt_provider': native_bp,
        'two_exact_Blueprint_originals_restored': restored,
        'exact_vendor_Blueprint_after_build': vendor_bp,
        'nine_production_vendor_mirrors': mirrors,
        'checkout_declarations_verified_by_actual_builder_and_complete_source_map': COMPOSER_DECLARATIONS,
        'targets': TARGETS, 'dependency_mode': 'Strict', 'source_projection_restored': True,
        'actual_ELF_AIDL_and_native_link_inputs_qualified': False,
        'Android_Binder_ABI_qualified': False, 'Wayland_GPU_runtime_qualified': False,
        'tests_executed': False, 'runtime_authorization_enabled': False,
        'installation_performed': False, 'service_activation_performed': False}

