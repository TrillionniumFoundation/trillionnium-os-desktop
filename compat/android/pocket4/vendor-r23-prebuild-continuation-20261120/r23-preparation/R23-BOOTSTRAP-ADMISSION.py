# Appended to the exact frozen R22 prefix before its unchanged main guard.
# R22's original operational contract and source-transition functions remain
# historical inputs. Only this generation's paths and prebuild admission change.
R23_CONTRACT_PATH = ROOT / 'control/vendor-build-20261120-9907-r23/inputs/CONTRACT.json'
R23_CONTRACT_PIN = None
R23 = None
PREBUILD22 = None
R23_R22_PINS = dict(PINS)
R23_UNMATERIALIZED_LOCK = ROOT / 'producer-build-r22-9907/android/manifest/production-full-apex-tests-source-lock.json'
R23_UNMATERIALIZED_ROOTS = ('producer-build-r22-9907', 'out-build-r22-9907', 'tmp-build-r22-9907')


def r23_raw(reference):
    """Read the actual full historical body under its original complete F9."""
    r20_guard_admission()
    expected = ADMISSION22.reference(reference)
    path = Path(expected['path'])
    need(path.resolve() == path and expected['bytes'] <= 1024 * 1024,
         'canonical bounded R23 historical raw input')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = f9(os.fstat(fd))
        need(before == expected['identity'] and stat.S_ISREG(before[2]) and before[5] == 1,
             'same complete original raw input identity')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            body = stream.read(expected['bytes'] + 1)
        need(len(body) == expected['bytes']
             and hashlib.sha256(body).hexdigest() == expected['sha256']
             and before == f9(os.fstat(fd)) == f9(path.lstat()),
             'whole raw input content and held/path identity bookends')
        r20_guard_admission()
        return {'reference': expected, 'raw': body}
    finally:
        os.close(fd)


def r23_current_baseline():
    r22_current_baseline()
    manifest = digest(SOURCE / '.droidloom-source-manifest.json')
    locks = []
    for original, (path, inode) in zip(ADMISSION22.LOCKS, LOCK_PINS):
        check_lock(path, inode)
        actual = r23_raw(original)
        row = dict(actual['reference'])
        row['body_hex'] = actual['raw'].hex()
        locks.append(row)
    return {'manifest': manifest, 'locks': locks}


def r23_failure_inputs():
    inputs = {name: r23_raw(reference) for name, reference in R23['r22_inputs'].items()}
    inputs['preparation_outputs'] = {
        client['session_id']: r23_raw(client['stdout']) for client in R22['preparation_clients']}
    return PREBUILD22.validate_r22_prebuild(inputs, r23_current_baseline())


def r23_absent_predecessor_roots():
    """Observe only the never-created R22 roots, through their held parent."""
    need(ROOT.resolve() == ROOT, 'original vendor root has no aliases')
    fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = f9(os.fstat(fd))
        need(stat.S_ISDIR(before[2]) and before[:5] == R23['root_authority']
             and before[3] == before[4] == 1000 and not before[2] & 0o022,
             'same original owner-controlled vendor parent directory')
        for name in R23_UNMATERIALIZED_ROOTS:
            try:
                os.stat(name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise RuntimeError('R22 root was materialized or substituted: ' + name)
        need(before == f9(os.fstat(fd)) == f9(ROOT.lstat()),
             'held original parent unchanged across all three no-follow absence checks')
        return {'parent': str(ROOT), 'parent_identity': before,
            'absent_direct_children': list(R23_UNMATERIALIZED_ROOTS),
            'unmaterialized_planned_lock': str(R23_UNMATERIALIZED_LOCK),
            'actual_historical_input_removed': False}
    finally:
        os.close(fd)


def r23_validate_controls():
    result = r20_json(R23['prebuild_controls'])
    need(result['schema'] == 'p4-r23-actual-r22-prebuild-admission-controls-v1'
         and result['passed'] is True and result['actual_positive_cases'] == 1
         and result['actual_failure_preserved'] is True and len(result['negative_cases']) == 27
         and result['host_inputs_read_from_actual_files'] is True
         and result['host_metadata_observation_only'] is True
         and result['fresh_live_unit_retirement_tested'] is False
         and result['source_locks_acquired'] is False
         and result['successor_resource_admission_tested'] is False
         and all(result[key] == 0 for key in ('children_started', 'source_mutations', 'Android_builds', 'Android_starts'))
         and result['runtime_qualified'] is result['production_ready'] is False,
         'actual pure prebuild controls preserve their source-only limits')
    need((result['module']['bytes'], result['module']['sha256'])
         == (R23['prebuild_helper']['bytes'], R23['prebuild_helper']['sha256']),
         'same full pure helper source as the actual control run')
    for reference in R23['source_inputs']:
        r20_check(reference)
    return {'control_receipt': R23['prebuild_controls'], 'actual_positive_cases': 1,
            'negative_cases': 27, 'runtime_qualified': False, 'production_ready': False}


def r23_bootstrap():
    global R23, PREBUILD22, REPO, CONTROL, OUT, TMP, SELF, UNIT, RECOVERY_UNIT, LOCK
    need(type(R23_CONTRACT_PIN) is tuple and len(R23_CONTRACT_PIN) == 2
         and type(R23_CONTRACT_PIN[0]) is int and R23_CONTRACT_PIN[0] > 0
         and type(R23_CONTRACT_PIN[1]) is str and len(R23_CONTRACT_PIN[1]) == 64,
         'R23 successor is not frozen from the actual R22 failure')
    contract_ref = digest(R23_CONTRACT_PATH)
    need((contract_ref['bytes'], contract_ref['sha256']) == R23_CONTRACT_PIN,
         'exact frozen R23 continuation contract')
    R23 = r20_json(contract_ref)
    need(R23['schema'] == 'p4-vendor-r23-prebuild-continuation-contract-v1'
         and R23['operational_inputs_frozen'] is True
         and R23['current_source'] == R22['current_source']
         and R23['baseline'] == R22['baseline']
         and R23['current_binaries'] == R22['current_binaries']
         and R23['runtime_qualified'] is R23['production_ready'] is False,
         'same actually qualified source, release and unchanged source baseline')
    need(set(R23['r22_inputs']) == {'worker', 'outer', 'contract', 'bundle', 'terminal', 'resource', 'serialized'}
         and r20_json(R23['r22_inputs']['contract']) == R22,
         'the exact complete R22 historical operational contract is retained')
    r20_check(R23['prebuild_helper'])
    PREBUILD22 = r20_module('p4_r23_actual_r22_prebuild', R23['prebuild_helper'])
    failure = r23_failure_inputs()
    need(failure['actual_R22_prebuild_failure_consumed'] is True
         and failure['original_status_children_reaped'] == 132
         and failure['R22_uncreated_producer_lock_adopted'] is False,
         'complete actual no-build/no-recovery R22 refusal before path transition')
    absence = r23_absent_predecessor_roots()
    need(LOCK == R23_UNMATERIALIZED_LOCK
         and R23_R22_PINS[LOCK] == (400720, TRANSITION22.NEW_LOCK_SHA)
         and R23['unmaterialized_R22_plan'] == {
             'lock_path': str(LOCK), 'lock_bytes': 400720, 'lock_sha256': TRANSITION22.NEW_LOCK_SHA,
             'absent_roots': list(R23_UNMATERIALIZED_ROOTS)},
         'only the original never-created planned producer lock is reclassified')
    # This exact planned path has no file, inode, body or build phase. Retain
    # the declaration and its full absence evidence, but never fabricate it as
    # an existing historical input. Every actual R22 input remains in PINS.
    del PINS[R23_UNMATERIALIZED_LOCK]
    REPO = ROOT / 'producer-build-r23-9907'
    CONTROL = ROOT / 'control/vendor-build-20261120-9907-r23/actual'
    OUT = ROOT / 'out-build-r23-9907'; TMP = ROOT / 'tmp-build-r23-9907'
    SELF = CONTROL.parent / 'source.py'
    UNIT = 'p4-cp3a-vendor-20261120-9907-r23'; RECOVERY_UNIT = UNIT + '-recovery'
    LOCK = REPO / 'android/manifest/production-full-apex-tests-source-lock.json'
    additions = [contract_ref, R23['prebuild_helper'], R23['prebuild_controls'],
        *R23['r22_inputs'].values(), *R23['source_inputs'],
        *[client['stdout'] for client in R23['preparation_clients']]]
    for reference in additions:
        actual = r20_check(reference)
        path = Path(actual['path']); pin = (actual['bytes'], actual['sha256'])
        need(path not in PINS or PINS[path] == pin, 'no historical actual R22 pin replacement')
        PINS[path] = pin
    need(LOCK not in PINS, 'fresh R23 planned producer lock')
    PINS[LOCK] = (400720, TRANSITION22.NEW_LOCK_SHA)
    need(all(PINS[path] == pin for path, pin in R23_R22_PINS.items()
             if path != R23_UNMATERIALIZED_LOCK)
         and set(R23_R22_PINS) - set(PINS) == {R23_UNMATERIALIZED_LOCK},
         'every actual historical pin retained; only proved unmaterialized declaration changes')
    OBS.update(schema='p4-cp3a-normal-vendor-build-r23-v1',
        actual_R22_prebuild_failure=failure, actual_unmaterialized_R22_plan=absence,
        actual_R22_source_and_release_reused_without_runtime_credit=True,
        R22_failure_record_replaced=False)


def r23_successor_extra_admission():
    # Called inside the original R22 function's try/finally. No new deadline
    # is created: every old and new check uses that one absolute 150s bound.
    need(R20_ADMISSION_DEADLINE is not None, 'original admission owns the deadline')
    original_deadline = R20_ADMISSION_DEADLINE
    r20_guard_admission()
    failure = r23_failure_inputs()
    absence = r23_absent_predecessor_roots()
    controls = r23_validate_controls()
    targets = R23['additional_live_retirement_targets']
    need(targets == [
        {'scope': 'user', 'unit': 'p4-cp3a-vendor-supervisor-20261120-9907-r22.service', 'pids': []},
        {'scope': 'user', 'unit': 'p4-cp3a-vendor-20261120-9907-r22.service', 'pids': []},
        {'scope': 'user', 'unit': 'p4-cp3a-vendor-20261120-9907-r22-recovery.service', 'pids': []}],
        'three exact R22 units must receive fresh original live retirement checks')
    observed = [r20_live_retired(row['unit'], row['pids'], row['scope']) for row in targets]
    clients = R23['preparation_clients']
    need(len(clients) >= 3 and len({row['session_id'] for row in clients}) == len(clients),
         'complete original R22 final freeze, supervisor and subsequent preparation clients')
    fixed = {
        'r22-freeze-r2': ('dpty-f70ee7be8e5157c61d3f7d090147804e1da433c8e29decdc44d543452b8ac077', 0),
        'r22-original-supervisor': ('dpty-a2dd1fc97b891e1fc369ec9b2c8fec978a93d6a288e4d21cd5c1209cbdfe0b1c', 1),
        'r22-prebuild-input-capture': ('dpty-807b1e5927cac379fbeb56ad26e3c8fb8d54b64633bb0ab39edee88ca111a91a', 0)}
    need(len({row['name'] for row in clients}) == len(clients)
         and fixed.items() <= {row['name']: (row['session_id'], row['expected_exit_code']) for row in clients}.items(),
         'all actual successful and failed predecessor clients retain exact outcomes')
    for client in clients:
        r20_validate_client(client, client['stdout'], client['expected_exit_code'])
    r23_current_baseline()
    need(R20_ADMISSION_DEADLINE == original_deadline, 'no extension or replacement of the admission deadline')
    r20_guard_admission()
    return {'actual_R22_prebuild_failure_and_original_status_retirement': failure,
        'actual_unmaterialized_R22_plan': absence, 'current_prebuild_controls': controls,
        'additional_R22_live_retirement_observations': observed,
        'all_actual_R22_input_pins_preserved': True, 'resource_admission_reused': False,
        'same_total_admission_budget_seconds': 150, 'observed_ns': time.time_ns()}


# r20_recovery_retirement is copied below with only its current-generation
# schema literal changed to R23. No historical R22 receipt is relabeled.
