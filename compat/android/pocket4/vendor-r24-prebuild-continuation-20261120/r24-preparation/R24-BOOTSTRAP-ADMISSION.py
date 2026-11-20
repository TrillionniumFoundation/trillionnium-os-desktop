# Appended to the exact actually frozen R23 prefix before its unchanged main.
# All earlier source/contract/bootstrap code retains its original bytes/names.
R24_CONTRACT_PATH = ROOT / 'control/vendor-build-20261120-9907-r24/inputs/CONTRACT.json'
R24_CONTRACT_PIN = None
R24 = None
PREBUILD23 = None
R24_R23_PINS = dict(PINS)
R24_UNMATERIALIZED_LOCK = ROOT / 'producer-build-r23-9907/android/manifest/production-full-apex-tests-source-lock.json'
R24_UNMATERIALIZED_ROOTS = ('producer-build-r23-9907', 'out-build-r23-9907', 'tmp-build-r23-9907')
R24_EXTRA_TARGETS = [
    {'scope': 'user', 'unit': 'p4-cp3a-vendor-supervisor-20261120-9907-r23.service', 'pids': []},
    {'scope': 'user', 'unit': 'p4-cp3a-vendor-20261120-9907-r23.service', 'pids': []},
    {'scope': 'user', 'unit': 'p4-cp3a-vendor-20261120-9907-r23-recovery.service', 'pids': []},
    {'scope': 'user', 'unit': 'p4-r23-resource-view-20261120-3b9d-r1.service', 'pids': []},
    {'scope': 'user', 'unit': 'p4-r23-resource-stability-20261120-3b9d-r1.service', 'pids': []},
    {'scope': 'user', 'unit': 'p4-r24-resource-preflight-20261120-3b9d-r1.service', 'pids': []},
]
R24_CLIENTS = (
    ('r23-controller-stage', 'dpty-b89809e41cb901a245fe6013f91127c424c48dce4218317551df9599906f8647', 0),
    ('r23-input-freeze', 'dpty-53971af9e52fcec6420cbb9844a17ebee7cdbe09ec920328b2758f66db2f4054', 0),
    ('r23-original-supervisor', 'dpty-4b559da7e3cf112676f930f890b7262bafd2e4c230f6e8d459f06154abc7e4cc', 1),
    ('r23-resource-view-direct', 'dpty-e59704d903ae55b808d44a4958f3561834188af6f16069f984dbd2dd3c5c9ec4', 0),
    ('r23-resource-view-service', 'dpty-a84df6a9ab050331674763e5b3bff3a2aed21ae506f24903f4ae46c7349c9836', 0),
    ('r23-resource-stability', 'dpty-9c13917a5733cd6fa850017c983d72c17a29130325f4496cda1c0689c059c161', 0),
)


def r24_failure_inputs():
    inputs = {name: r23_raw(reference) for name, reference in R24['r23_inputs'].items()}
    inputs['r22_helper'] = r23_raw(R23['prebuild_helper'])
    inputs['r22'] = {name: r23_raw(reference) for name, reference in R23['r22_inputs'].items()}
    inputs['r22']['preparation_outputs'] = {
        client['session_id']: r23_raw(client['stdout']) for client in R22['preparation_clients']}
    inputs['preparation_outputs'] = {
        client['session_id']: r23_raw(client['stdout']) for client in R23['preparation_clients']}
    return PREBUILD23.validate_r23_prebuild(inputs, r23_current_baseline())


def r24_absent_predecessor_roots():
    need(ROOT.resolve() == ROOT, 'original vendor root has no aliases')
    fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = f9(os.fstat(fd))
        need(stat.S_ISDIR(before[2]) and before[:5] == R24['root_authority'] == R23['root_authority']
             and before[3] == before[4] == 1000 and not before[2] & 0o022,
             'same actual original owner-controlled vendor parent directory')
        for name in R24_UNMATERIALIZED_ROOTS:
            try:
                os.stat(name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise RuntimeError('R23 root was materialized or substituted: ' + name)
        need(before == f9(os.fstat(fd)) == f9(ROOT.lstat()),
             'held parent whole identity spans all three no-follow absence observations')
        return {'parent': str(ROOT), 'parent_identity': before,
            'absent_direct_children': list(R24_UNMATERIALIZED_ROOTS),
            'unmaterialized_planned_lock': str(R24_UNMATERIALIZED_LOCK),
            'actual_historical_input_removed': False}
    finally:
        os.close(fd)


def r24_validate_controls():
    result = r20_json(R24['prebuild_controls'])
    need(result['schema'] == 'p4-r24-actual-r23-prebuild-admission-controls-v1'
         and result['passed'] is True and type(result['actual_positive_cases']) is int
         and result['actual_positive_cases'] == 1 and len(result['negative_cases']) == 33
         and result['actual_R22_helper_source_unchanged'] is True
         and result['actual_R22_and_R23_failures_preserved'] is True
         and result['new_host_execution'] is False
         and result['fresh_live_retirement_tested'] is False
         and result['fresh_resource_admission_tested'] is False
         and result['source_locks_acquired'] is False
         and all(type(result[key]) is int and result[key] == 0
                 for key in ('children_started', 'source_mutations', 'Android_builds', 'Android_starts'))
         and result['runtime_qualified'] is result['production_ready'] is False,
         'actual pure nested R23 controls carry no new host/runtime/admission credit')
    need((result['module']['bytes'], result['module']['sha256'])
         == (R24['prebuild_helper']['bytes'], R24['prebuild_helper']['sha256'])
         and result['full_actual_R23_originals'] == result['full_nested_R22_originals'] == 7
         and result['full_actual_R23_preparation_archives'] == 4
         and result['full_nested_R22_preparation_archives'] == 13
         and result['actual_original_status_children_consumed'] == 135,
         'same full helper and all actual original and nested inputs')
    for reference in R24['source_inputs']:
        r20_check(reference)
    return {'control_receipt': R24['prebuild_controls'], 'actual_positive_cases': 1,
            'negative_cases': 33, 'runtime_qualified': False, 'production_ready': False}


def r24_bootstrap():
    global R24, PREBUILD23, REPO, CONTROL, OUT, TMP, SELF, UNIT, RECOVERY_UNIT, LOCK
    need(type(R24_CONTRACT_PIN) is tuple and len(R24_CONTRACT_PIN) == 2
         and type(R24_CONTRACT_PIN[0]) is int and R24_CONTRACT_PIN[0] > 0
         and type(R24_CONTRACT_PIN[1]) is str and len(R24_CONTRACT_PIN[1]) == 64,
         'R24 source-only successor is not frozen from the actual R23 failure')
    contract_ref = digest(R24_CONTRACT_PATH)
    need((contract_ref['bytes'], contract_ref['sha256']) == R24_CONTRACT_PIN,
         'exact frozen R24 continuation contract')
    R24 = r20_json(contract_ref)
    need(R24['schema'] == 'p4-vendor-r24-prebuild-continuation-contract-v1'
         and R24['operational_inputs_frozen'] is True
         and R24['current_source'] == R23['current_source']
         and R24['baseline'] == R23['baseline']
         and R24['current_binaries'] == R23['current_binaries']
         and R24['all_original_constraints_unchanged'] is True
         and R24['runtime_qualified'] is R24['production_ready'] is False,
         'same actually qualified source/release and unchanged original baseline')
    need(set(R24['r23_inputs']) == {'worker', 'outer', 'contract', 'bundle', 'terminal', 'resource', 'serialized'}
         and r20_json(R24['r23_inputs']['contract']) == R23,
         'complete exact actual R23 operational contract remains historical')
    r20_check(R24['prebuild_helper'])
    PREBUILD23 = r20_module('p4_r24_actual_r23_prebuild', R24['prebuild_helper'])
    failure = r24_failure_inputs()
    need(failure['actual_R23_prebuild_failure_consumed'] is True
         and failure['original_status_children_reaped'] == 135
         and failure['R23_uncreated_producer_lock_adopted'] is False,
         'complete original R23 no-build/no-recovery refusal before path transition')
    absence = r24_absent_predecessor_roots()
    need(LOCK == R24_UNMATERIALIZED_LOCK
         and R24_R23_PINS[LOCK] == (400720, TRANSITION22.NEW_LOCK_SHA)
         and R24['unmaterialized_R23_plan'] == {
             'lock_path': str(LOCK), 'lock_bytes': 400720, 'lock_sha256': TRANSITION22.NEW_LOCK_SHA,
             'absent_roots': list(R24_UNMATERIALIZED_ROOTS)},
         'only the original never-created R23 planned producer lock changes classification')
    del PINS[R24_UNMATERIALIZED_LOCK]
    REPO = ROOT / 'producer-build-r24-9907'
    CONTROL = ROOT / 'control/vendor-build-20261120-9907-r24/actual'
    OUT = ROOT / 'out-build-r24-9907'; TMP = ROOT / 'tmp-build-r24-9907'
    SELF = CONTROL.parent / 'source.py'
    UNIT = 'p4-cp3a-vendor-20261120-9907-r24'; RECOVERY_UNIT = UNIT + '-recovery'
    LOCK = REPO / 'android/manifest/production-full-apex-tests-source-lock.json'
    additions = [contract_ref, R24['prebuild_helper'], R24['prebuild_controls'],
        *R24['r23_inputs'].values(), *R24['source_inputs'],
        *[client['stdout'] for client in R24['preparation_clients']]]
    for reference in additions:
        actual = r20_check(reference)
        path = Path(actual['path']); pin = (actual['bytes'], actual['sha256'])
        need(path not in PINS or PINS[path] == pin, 'no actual historical R23 pin replacement')
        PINS[path] = pin
    need(LOCK not in PINS, 'fresh R24 planned producer lock')
    PINS[LOCK] = (400720, TRANSITION22.NEW_LOCK_SHA)
    need(all(PINS[path] == pin for path, pin in R24_R23_PINS.items()
             if path != R24_UNMATERIALIZED_LOCK)
         and set(R24_R23_PINS) - set(PINS) == {R24_UNMATERIALIZED_LOCK},
         'all actual R23 pins remain; only proved unmaterialized declaration is reclassified')
    OBS.update(schema='p4-cp3a-normal-vendor-build-r24-v1',
        actual_R23_prebuild_failure=failure, actual_unmaterialized_R23_plan=absence,
        actual_R23_source_and_release_reused_without_runtime_credit=True,
        R23_failure_record_replaced=False)


def r24_successor_extra_admission():
    need(R20_ADMISSION_DEADLINE is not None, 'original admission owns its single deadline')
    original_deadline = R20_ADMISSION_DEADLINE
    r20_guard_admission()
    failure = r24_failure_inputs()
    absence = r24_absent_predecessor_roots()
    controls = r24_validate_controls()
    need(R24['additional_live_retirement_targets'] == R24_EXTRA_TARGETS,
         'all six exact predecessor/observation/preflight units require fresh original retirement')
    observed = [r20_live_retired(row['unit'], row['pids'], row['scope']) for row in R24_EXTRA_TARGETS]
    clients = R24['preparation_clients']
    need(type(clients) is list and len(clients) == 6
         and all(type(row['expected_exit_code']) is int for row in clients)
         and [(row['name'], row['session_id'], row['expected_exit_code']) for row in clients]
             == list(R24_CLIENTS),
         'all six original completed preparation clients, including failed R23 supervisor')
    for client in clients:
        r20_validate_client(client, client['stdout'], client['expected_exit_code'])
    r23_current_baseline()
    need(R20_ADMISSION_DEADLINE == original_deadline, 'no new or extended admission deadline')
    r20_guard_admission()
    return {'actual_R23_prebuild_failure_and_original_status_retirement': failure,
        'actual_unmaterialized_R23_plan': absence, 'current_prebuild_controls': controls,
        'additional_R23_and_observer_live_retirement_observations': observed,
        'all_actual_R23_input_pins_preserved': True, 'resource_admission_reused': False,
        'external_resource_observation_is_not_admission': True,
        'same_total_admission_budget_seconds': 150, 'observed_ns': time.time_ns()}


# Only the current-generation recovery schema is updated in the copied
# original recovery function below. Earlier R22/R23 records are never renamed.
