"""Exact live stage composition functions; external qualification runs separately."""
import copy

import hashlib

from pathlib import Path

import re

import stat

FINAL = Path('/home/alex/work/pocket4-android-final')

DEPLOY = FINAL / 'deployment'

PREFIX = Path('/usr/lib/droidloom/runtime/pocket4')

BASE_PINS = {
    'deployment/manifest.json': '8df3d0fe6a40b9509155290e201c13afa96781e6e0425b1e0e78e6cf893e682c',
    'deployment/transaction-plan.json': 'bc3383d304a12cdd9046da403f00a26ccc59a017e6fb154603ae8efa9cb25277',
    'deployment/cell.candidate.json': 'd5e9184dc6078e46acf1f0ce3124a727ccfc9fbe2ee3258b18d490f5e00b80cb',
    'deployment/qualification-config.json': '288d228f72d7274f5e067c39a2ba14e362e0c1cfb05bb9c5a5d4f91fc7540d3d',
    'qualification/plan.json': '1558939f681b2a0ba15134a32a124ad2c7c417b3fd8d3c72b7944372de6c36c4',
    'deployment/SHA256SUMS': '3eb000180a19a2c5be4d7003763e6b90ac16d89078282cd49fc5a19dd01c1ff5',
    'deployment/verification.json': 'c013dd2db258492e950d9f50c41696ee655f03677d256b9290d4c21ab96e4a16',
    'camera/runtime-entry.json': '8d4b36e48fcd7b567cf3314474a014f14b34183aa243665ed12d26a32fb6d719',
}

RUNNER_SHA = '1ebd5406c5cf37d84e9b16b6caa5783554918e624537bddcd0ed64e044049de0'

QUALIFIER_SHA = '914ba73aa6f68a5cf685a73cba01cb2ee04543d8c30bd02f3e02cc58076abeba'

SERVICES_SHA = 'f1acb56e23cd9082a77ef686f2e840a736e7769dd8843830e53e56b1ac31566f'

GUEST = {
    'engine': '/system/lib64/libberberis_arm64.so',
    'art_apex': '/system/apex/com.android.art.apex',
    'libart': '/apex/com.android.art/lib64/libart.so',
    'libnativebridge': '/apex/com.android.art/lib64/libnativebridge.so',
    'owner': '/system/bin/droidloom-proc-maps-owner',
    'factory': '/system/bin/droidloom-proc-maps-factory-v2',
    'readiness': '/system/bin/droidloom-proc-maps-readiness',
    'pair': '/system/etc/droidloom-native-generation-pair.json',
    'bridge_profile': '/system/etc/droidloom-native-bridge.json',
    'sensor': '/system/lib64/libsensorservice.so',
}

CHANGED_ROLES = ('engine', 'bridge_profile', 'art_apex', 'pair')

REPLACED_ROLES = ('engine', 'bridge_profile')

audio = None

EXTENSION_SOURCES = {}

EXTENSION_CONTENTS = {}

def payload_relative(role):
    return 'deployment/payload/' + str(PREFIX / GUEST[role].lstrip('/')).lstrip('/')

def stage_allowlist():
    if audio is None:
        raise RuntimeError('AUDIO_COMPOSITION_SOURCE_NOT_LOADED')
    return set(BASE_PINS) | {payload_relative(role) for role in CHANGED_ROLES} | audio.allowlist()

def baseline(io, witness):
    values = {}; records = {}; raw = {}
    for relative, digest in BASE_PINS.items():
        record, content = io.pinned({'path': str(FINAL / relative), 'sha256': digest}, contents=True, single=True)
        values[relative] = io.parse(content) if relative.endswith('.json') else None
        records[relative] = record; raw[relative] = content
    rows = []
    for line in raw['deployment/SHA256SUMS'].decode('ascii').splitlines():
        io.need(re.fullmatch(r'[0-9a-f]{64}  [A-Za-z0-9._/+\-]+', line) is not None, 'EXACT_OLD_SUMS_LINE')
        digest, relative = line.split('  ', 1)
        io.need(not Path(relative).is_absolute() and '..' not in Path(relative).parts
                and relative != 'SHA256SUMS', 'SEALED_RELATIVE_CANDIDATE_PATH')
        row, _ = io.pinned({'path': str(DEPLOY / relative), 'sha256': digest})
        records['deployment/' + relative] = row
        rows.append((digest, relative))
    io.need(len(rows) == len({r for _, r in rows}) == 43, 'EXACT_CURRENT_43_CHECKSUM_ROWS')
    manifest = values['deployment/manifest.json']; plan = values['deployment/transaction-plan.json']
    io.need(len(manifest['payload']) == len(plan['install_operations']) == 28
            and len(manifest['android_file_overrides']) == 47
            and len(manifest['android_runtime_directories']) == 4
            and manifest['ready_for_apply'] is False and values['qualification/plan.json']['ready'] is False,
            'EXPECTED_UNDEPLOYED_BASELINE_SHAPE')
    io.need(manifest['transaction_runner']['sha256'] == RUNNER_SHA
            and values['deployment/qualification-config.json']['maintenance_gate']['sha256'] == QUALIFIER_SHA,
            'UNCHANGED_QUALIFIED_PUBLIC_TOOLING')
    # SensorService was independently staged and sealed before this consumer.
    # Keep its payload, operation, override, checksum and integration metadata.
    sensor_target = str(PREFIX / GUEST['sensor'].lstrip('/'))
    sensor_payload = [r for r in manifest['payload'] if r['install_target'] == sensor_target]
    sensor_operation = [r for r in plan['install_operations'] if r['target'] == sensor_target]
    sensor_override = [r for r in manifest['android_file_overrides'] if r['guest_target'] == GUEST['sensor']]
    io.need(len(sensor_payload) == len(sensor_operation) == len(sensor_override) == 1,
            'EXACT_EXISTING_SENSOR_ROWS')
    staged_sensor = records[payload_relative('sensor')]
    io.need(staged_sensor['bytes'] == sensor_payload[0]['bytes'] == 482440
            and staged_sensor['sha256'] == sensor_payload[0]['sha256'] == sensor_operation[0]['sha256']
                == '8db6580b97dea3e1e8e1109e29953bd46e4300f113d1a1d738b1dbc7a8057b20'
            and sensor_operation[0]['expected_current'] == {'absent': True}
            and sensor_override[0]['operation'] == 'install_staged'
            and sensor_override[0]['candidate_source'] == sensor_target,
            'EXACT_PREVIOUSLY_QUALIFIED_SENSOR_PAYLOAD')
    io.need(manifest['framework_integration'] == plan['framework_integration']
                == sensor_payload[0]['framework_integration'] == sensor_override[0]['framework_integration']
            and manifest['framework_integration']['sha256']
                == '0832861edd6611ae42d5add4367cdc210ce03f0ccd149264151e66a0d3b19385',
            'EXISTING_FRAMEWORK_STAGE_PROOF_RETAINED')
    for role in (*CHANGED_ROLES, 'sensor'):
        installed = str(PREFIX / GUEST[role].lstrip('/'))
        observed, _ = io.held_read(installed, absent=True, single=True)
        io.need(observed.get('absent') is True, 'ACTUAL_CANONICAL_INSTALL_TARGET_MUST_BE_ABSENT:' + installed)
        witness.observed[installed] = observed
        rel = payload_relative(role)
        if role in ('art_apex', 'pair'):
            current, _ = io.held_read(FINAL / rel, absent=True, single=True)
            io.need(current.get('absent') is True, 'NEW_STAGED_PAYLOAD_ALREADY_EXISTS:' + rel)
            records[rel] = current
    return {'values': values, 'records': records, 'raw': raw, 'sums': rows}

def source_record(observed):
    ident = observed['identity']
    return {'declared_path': observed['path'], 'realpath': observed['path'],
            'bytes': observed['bytes'], 'sha256': observed['sha256'], 'device': ident[0],
            'inode': ident[1], 'mode': stat.S_IMODE(ident[2]), 'uid': ident[3], 'gid': ident[4],
            'nlink': ident[5], 'mtime_ns': ident[7], 'ctime_ns': ident[8]}

def new_ref(path, raw, old=None):
    row = copy.deepcopy(old) if old is not None else {'path': str(path)}
    row.update(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    return row

def build(io, base, known, framework_info, camera_info, native_info, native_gate, proposal_root):
    """Pure planned metadata; source evidence has already been checked by caller."""
    manifest = copy.deepcopy(base['values']['deployment/manifest.json'])
    transaction = copy.deepcopy(base['values']['deployment/transaction-plan.json'])
    cell = copy.deepcopy(base['values']['deployment/cell.candidate.json'])
    qplan = copy.deepcopy(base['values']['qualification/plan.json'])
    config = copy.deepcopy(base['values']['deployment/qualification-config.json'])
    camera_entry = copy.deepcopy(base['values']['camera/runtime-entry.json'])
    sources = dict(native_info['sources'], sensor=framework_info['candidate'])
    payloads = {r['install_target']: r for r in manifest['payload']}
    operations = {r['target']: r for r in transaction['install_operations']}
    overrides = {r['guest_target']: r for r in manifest['android_file_overrides']}
    protected_payloads = copy.deepcopy(payloads)
    protected_overrides = copy.deepcopy(overrides)
    for role in CHANGED_ROLES:
        source = sources[role]; guest = GUEST[role]; installed = str(PREFIX / guest.lstrip('/'))
        staged_relative = payload_relative(role).removeprefix('deployment/')
        if role in REPLACED_ROLES:
            payload = payloads[installed]; operation = operations[installed]; override = overrides[guest]
            io.need(payload.get('must_replace_and_reseal_before_apply') is True
                    and operation['expected_current'] == {'absent': True}, 'ONLY_DECLARED_PLACEHOLDER_REPLACEMENT')
            payload['prior_staged_source'] = copy.deepcopy(payload['source'])
        else:
            io.need(installed not in payloads and installed not in operations and guest not in overrides,
                    'NEW_COMPLETE_ART_PAIR_SENSOR_ROWS_ONLY')
            payload = {'install_target': installed, 'install_owner': {'uid': 0, 'gid': 0},
                'install_mode': 0o644, 'mode': 0o644, 'role': 'android_file_override',
                'path': str(DEPLOY / staged_relative), 'relative_path': staged_relative}
            operation = {'target': installed, 'uid': 0, 'gid': 0, 'mode': 0o644,
                         'expected_current': {'absent': True}, 'staged_relative_path': staged_relative}
            override = {'candidate_source': installed, 'guest_target': guest,
                        'operation': 'install_staged', 'staged_relative_path': staged_relative}
            manifest['payload'].append(payload); transaction['install_operations'].append(operation)
            manifest['android_file_overrides'].append(override)
        payload.update(bytes=source['bytes'], sha256=source['sha256'], source=source_record(source),
                       qualified_source=native_info['contract_value']['files'][role]['qualified_source']
                           if role != 'sensor' else io.short(source))
        operation['sha256'] = source['sha256']
        override['qualified_source'] = copy.deepcopy(payload['qualified_source'])
        for item in (payload, operation, override):
            item.pop('placeholder_for', None); item.pop('must_replace_and_reseal_before_apply', None)
    io.need(len(manifest['payload']) == len(transaction['install_operations']) == 30
            and len(manifest['android_file_overrides']) == 49
            and len(manifest['android_runtime_directories']) == 4, 'EXACT_30_49_4_COMPOSITION')
    for old_guest, old in protected_overrides.items():
        now = next(x for x in manifest['android_file_overrides'] if x['guest_target'] == old_guest)
        io.need(now.get('current_source') == old.get('current_source'), 'ORIGINAL_OVERRIDE_PREIMAGE_CHANGED')
        if old_guest not in {GUEST[r] for r in REPLACED_ROLES}:
            io.need(now == old, 'UNRELATED_OVERRIDE_CHANGED')
    for target, old in protected_payloads.items():
        if target not in {str(PREFIX / GUEST[r].lstrip('/')) for r in REPLACED_ROLES}:
            io.need(next(r for r in manifest['payload'] if r['install_target'] == target) == old,
                    'UNRELATED_PAYLOAD_CHANGED')
    io.need(not any(x['guest_target'] in (GUEST['libart'], GUEST['libnativebridge'])
                    for x in manifest['android_file_overrides']), 'NO_INDIVIDUAL_ART_APEX_MEMBER_OVERLAYS')
    jar = next(r for r in manifest['payload'] if r['install_target'].endswith('/system/framework/services.jar'))
    io.need(jar['sha256'] == SERVICES_SHA, 'ACCEPTED_STORAGE_JAR_IMMUTABLE')
    cell['android_file_overrides'] = [{'source': r['candidate_source'], 'target': r['guest_target']}
                                      for r in manifest['android_file_overrides']]
    old_cell = base['values']['deployment/cell.candidate.json']
    io.need(all(cell[k] == old_cell[k] for k in old_cell if k != 'android_file_overrides'),
            'ALL_OTHER_CELL_SETTINGS_RETAINED')
    qplan['maintenance']['framework_build_complete'] = copy.deepcopy(framework_info['gate'])
    qplan['maintenance']['native_fence_released'] = copy.deepcopy(native_gate)
    qplan['component_inputs']['framework']['abi_report'] = io.short(framework_info['comparison'])
    qplan['component_inputs']['framework']['candidate'] = io.short(framework_info['candidate'])
    qplan['component_inputs']['native']['contract'] = native_info['contract']
    io.need(set(qplan['component_inputs']['camera']) == {'probe', 'consumer_manifest', 'service_manifest', 'service_unit', 'host_cli'},
            'ORIGINAL_CAMERA_EXACT_FIVE_INPUT_KEYS')
    original_camera = copy.deepcopy(qplan['component_runners']['camera'])
    qplan['component_runners']['camera']['program'] = io.short(camera_info['program'])
    qplan['component_runners']['camera']['timeout_seconds'] = 480
    required = qplan['component_runners']['camera']['required']
    io.need(len(required) == 19, 'ORIGINAL_CAMERA_19_REQUIREMENTS_RETAINED')
    additions = [(['schema'], 'pocket4-camera-display-wrapper-v1'), (['success'], True),
        (['ready_revoked'], False), (['errors'], []), (['signals'], []),
        (['subreaper', 'begin_passed'], True), (['subreaper', 'restored'], True),
        (['subreaper', 'final_children_empty'], True),
        (['independent_release_observation', 'inhibitor_removed'], True),
        (['independent_release_observation', 'entry_mode_matches'], True),
        (['independent_release_observation', 'owners_unchanged'], True),
        (['independent_release_observation', 'current', 'locked'], True)]
    required.extend({'path': ['display_lease_wrapper'] + path, 'equals': value} for path, value in additions)
    qplan['references']['camera_display_source_manifest'] = io.short(camera_info['manifest'])
    qplan['references']['camera_display_host_controls'] = io.short(camera_info['host_controls'])
    qplan['references']['native_actual_contract_assembly'] = native_info['assembly']
    qplan['references']['native_full_offline_qualification'] = io.short(native_info['offline'])
    qplan['references']['native_normal_profile_generation'] = io.short(native_info['profile_generation'])
    qplan['ready'] = True; qplan['remaining_inputs'] = []
    camera_entry['entry'] = io.short(camera_info['program'])
    camera_entry['argv'][1] = camera_info['program']['path']
    camera_entry['inner_camera_entry'] = original_camera['program']
    camera_entry['inner_max_operation_budget_seconds'] = 360
    camera_entry['inner_additional_cleanup_budget_seconds'] = 40
    camera_entry['max_operation_budget_seconds'] = 420
    camera_entry['additional_cleanup_budget_seconds'] = 55
    camera_entry['wrapper_budget_seconds'] = 475
    camera_entry['formal_component_seconds'] = 480
    camera_entry['component_inputs.camera'] = copy.deepcopy(qplan['component_inputs']['camera'])
    camera_entry['display_lease_sources'] = camera_info['sources']
    camera_entry['display_lease_manifest'] = io.short(camera_info['manifest'])
    camera_entry['display_lease_host_controls'] = io.short(camera_info['host_controls'])
    camera_entry['exit_codes'] = {'0': 'qualified original Camera and display lease cleanup',
        '1': 'uncaught entry precondition exception; no qualification',
        '2': 'refusal before actor start', '4': 'actor started and failure or UNKNOWN; never automatically retry'}
    camera_entry['live_execution_state'] = 'NOT_RUN'
    camera_tooling = {'schema': 'pocket4-camera-display-wrapper-stage-binding-v1',
        'candidate_sources': camera_info['sources'], 'prepared_source_manifest': camera_info['manifest'],
        'actual_host_controls': camera_info['host_controls'], 'actual_host_cases': 6,
        'inner_camera_source_unchanged': original_camera['program'], 'runtime_qualified': False}
    # The six original source candidates/40 controls remain exactly unchanged;
    # new wrapper evidence is separate, never attributed to the old controls.
    manifest['camera_display_qualification_tooling'] = copy.deepcopy(camera_tooling)
    transaction['camera_display_qualification_tooling'] = copy.deepcopy(camera_tooling)
    qualified = {'native_contract_assembly': native_info['assembly'], 'native_contract': native_info['contract'],
        'native_offline_qualification': io.short(native_info['offline']),
        'native_normal_profile_generation': io.short(native_info['profile_generation']),
        'framework_outer': io.short(framework_info['outer']), 'framework_comparison': io.short(framework_info['comparison']),
        'framework_exact_reconciliation': framework_info['reconciliation'],
        'framework_original_failed_terminal_preserved': framework_info['original_failed_terminal'],
        'runtime_qualified': False, 'candidate_deployed': False}
    manifest['actual_component_source_qualification'] = copy.deepcopy(qualified)
    transaction['actual_component_source_qualification'] = copy.deepcopy(qualified)
    manifest['candidate_integration_pending'] = []
    manifest['ready_for_apply'] = True
    manifest['reason_not_ready'] = None
    transaction['native_framework_candidates_pending'] = []
    io.need(transaction['apply_authorized_by_this_artifact'] is False and manifest['stage_only'] is True,
            'STAGING_DOES_NOT_AUTHORIZE_OR_EXECUTE_DEPLOYMENT')
    output = {'deployment/cell.candidate.json': io.encode(cell), 'qualification/plan.json': io.encode(qplan),
              'camera/runtime-entry.json': io.encode(camera_entry)}
    cell_ref = new_ref(DEPLOY / 'cell.candidate.json', output['deployment/cell.candidate.json'], manifest['candidate_cell'])
    transaction['candidate_cell_sha256'] = transaction['cell_operation']['sha256'] = cell_ref['sha256']
    manifest['candidate_cell'] = cell_ref
    qref = new_ref(FINAL / 'qualification/plan.json', output['qualification/plan.json'])
    for adapter, phase in (('maintenance_gate', 'maintenance'), ('post_start_qualification', 'post')):
        io.need(config[adapter]['program'] == str(FINAL / 'qualification/qualify_final.py')
                and config[adapter]['sha256'] == QUALIFIER_SHA,
                'PUBLIC_QUALIFICATION_ADAPTER_UNCHANGED')
        config[adapter]['args'] = ['--phase', phase, '--plan', qref['path'], '--expect-plan-sha256', qref['sha256']]
    output['deployment/qualification-config.json'] = io.encode(config)
    manifest['qualification_config'] = new_ref(DEPLOY / 'qualification-config.json',
        output['deployment/qualification-config.json'], manifest['qualification_config'])
    camera_ref = new_ref(FINAL / 'camera/runtime-entry.json', output['camera/runtime-entry.json'])
    manifest['camera_runtime_entry'] = camera_ref
    transaction['camera_runtime_entry'] = camera_ref
    output['deployment/transaction-plan.json'] = io.encode(transaction)
    manifest['transaction_plan'] = new_ref(DEPLOY / 'transaction-plan.json',
        output['deployment/transaction-plan.json'], manifest['transaction_plan'])
    output['deployment/manifest.json'] = io.encode(manifest)
    old_verification = base['records']['deployment/verification.json']
    verification = {'status': 'CANDIDATE_SOURCE_VERIFIED_RUNTIME_NOT_RUN',
        'previous_verification': dict(io.short(old_verification),
            path=str(proposal_root / 'stage-attempt/preimages/deployment/verification.json')),
        'manifest_sha256': hashlib.sha256(output['deployment/manifest.json']).hexdigest(),
        'plan_sha256': manifest['transaction_plan']['sha256'], 'candidate_cell_sha256': cell_ref['sha256'],
        'current_cell_sha256': manifest['cell_source']['sha256'],
        'qualified_tool_repair': copy.deepcopy(manifest['qualification_tooling']),
        'camera_display_qualification_tooling': camera_tooling,
        'actual_component_source_qualification': qualified, 'lifecycle_contract': copy.deepcopy(manifest['lifecycle_contract']),
        'actual_post_start_required_checks': ['main', 'storage', 'native', 'framework', 'applications', 'camera'],
        'candidate_counts': {'checksums': 45, 'payload': 30, 'overrides': 49, 'runtime_directories': 4},
        'final_readonly_inspection_result_location': str(proposal_root / 'stage-attempt/result.json'),
        'read_only_inspection': None, 'final_inspection_is_required_before_apply': True,
        'production_changes': False, 'runtime_qualified': False, 'whole_app_business_accepted': False}
    output['deployment/verification.json'] = io.encode(verification)
    digests = {relative.removeprefix('deployment/'): hashlib.sha256(raw).hexdigest()
               for relative, raw in output.items() if relative.startswith('deployment/')}
    for role in CHANGED_ROLES:
        digests[payload_relative(role).removeprefix('deployment/')] = sources[role]['sha256']
    sums = [(digests.get(relative, old_sha), relative) for old_sha, relative in base['sums']]
    for role in CHANGED_ROLES[2:]:
        relative = payload_relative(role).removeprefix('deployment/')
        io.need(relative not in {r for _, r in sums}, 'APPENDED_CHECKSUM_DUPLICATE')
        sums.append((digests[relative], relative))
    io.need(len(sums) == len({r for _, r in sums}) == 45, 'EXACT_FINAL_45_CHECKSUM_ROWS')
    output['deployment/SHA256SUMS'] = ''.join(sha + '  ' + rel + '\n' for sha, rel in sums).encode()
    io.need(set(output) == set(BASE_PINS), 'EXACT_EIGHT_METADATA_TARGETS')
    return {'metadata': output, 'payload_sources': {payload_relative(role): sources[role] for role in CHANGED_ROLES},
            'manifest': manifest, 'transaction': transaction, 'qualification_plan': qplan,
            'final_sums': sums, 'source_qualification': qualified}
