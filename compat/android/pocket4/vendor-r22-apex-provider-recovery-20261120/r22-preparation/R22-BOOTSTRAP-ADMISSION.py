# This block is appended to the exact complete R21 source before its main guard.
# The historical bootstrap above remains unchanged and only reads its own pins.
R22_CONTRACT_PATH = ROOT / 'control/vendor-build-20261120-9907-r22/inputs/CONTRACT.json'
R22_CONTRACT_PIN = None  # Freeze only after actual same-cohort CI, ELF/ABI and normal plans.
R22 = None
ADMISSION22 = None
TRANSITION22 = None
PARTIAL22 = None
R22_PRESERVED_PINS = dict(PINS)


def r22_bootstrap():
    global R22, ADMISSION22, TRANSITION22, PARTIAL22, BOOKENDS
    global REPO, CONTROL, OUT, TMP, SELF, UNIT, RECOVERY_UNIT, TREE
    global CANONICAL_SOURCE, CANONICAL_ROWS, CANONICAL_FREEZE, CANONICAL_FILES, CANONICAL_BYTES
    global RELEASE, SOURCE_TOOL, UPDATE_TOOL, LOCK, RECOVERY_LOCK, BOOKEND_PATH
    need(type(R22_CONTRACT_PIN) is tuple and len(R22_CONTRACT_PIN) == 2
         and type(R22_CONTRACT_PIN[0]) is int and R22_CONTRACT_PIN[0] > 0
         and type(R22_CONTRACT_PIN[1]) is str and len(R22_CONTRACT_PIN[1]) == 64,
         'R22 source-only template: actual complete CI, ELF custody, host ABI and normal plans not frozen')
    got = digest(R22_CONTRACT_PATH)
    need((got['bytes'], got['sha256']) == R22_CONTRACT_PIN, 'exact frozen R22 contract')
    R22 = r20_json(got, full=False)
    need(R22['schema'] == 'p4-vendor-r22-operational-input-contract-v1'
         and R22['operational_inputs_frozen'] is True
         and R22['runtime_qualified'] is False and R22['production_ready'] is False,
         'R22 current source input qualification only')
    need(R22['git_conversion_admission'] == R20['git_conversion_admission'],
         'all five original actual Git conversion inputs and scopes unchanged')
    ADMISSION22 = r20_module('p4_r22_admission', R22['support']['admission'])
    TRANSITION22 = r20_module('p4_r22_apex_test_transition', R22['support']['transition'])
    PARTIAL22 = r20_module('p4_r22_partial_apex_test_diagnostic', R22['support']['partial'])
    BOOKEND_PATH = Path(R22['support']['bookends']['path'])
    need((R22['support']['bookends']['bytes'], R22['support']['bookends']['sha256'])
         == (29338, 'bab5c377bf642d4aaa7b50a416319cebad31537022e5179a77e6e8d63827fa88'),
         'unchanged strict original complete representation helper')
    BOOKENDS = r20_module('p4_r22_original_bookends', R22['support']['bookends'])
    current = R22['current_source']
    need({k: current[k] for k in ('tree', 'files', 'bytes')} == ADMISSION22.CURRENT,
         'same full producer and nineteen actual release-binary cohort')
    need(R22['baseline'] == {'manifest': ADMISSION22.MANIFEST, 'locks': ADMISSION22.LOCKS},
         'actual original R21 final manifest and normal-recovery lock writer')
    REPO = ROOT / 'producer-build-r22-9907'
    CONTROL = ROOT / 'control/vendor-build-20261120-9907-r22/actual'
    OUT = ROOT / 'out-build-r22-9907'; TMP = ROOT / 'tmp-build-r22-9907'
    SELF = CONTROL.parent / 'source.py'
    UNIT = 'p4-cp3a-vendor-20261120-9907-r22'; RECOVERY_UNIT = UNIT + '-recovery'
    TREE = current['tree']; CANONICAL_FILES = current['files']; CANONICAL_BYTES = current['bytes']
    CANONICAL_SOURCE = Path(current['path']); CANONICAL_ROWS = Path(current['rows']['path'])
    CANONICAL_FREEZE = Path(current['freeze']['path'])
    release_refs = R22['current_binaries']
    need(tuple(sorted(release_refs)) == ADMISSION22.BINARIES, 'all original nineteen current binaries')
    RELEASE = Path(release_refs['droidloom-source']['path']).parent
    SOURCE_TOOL = RELEASE / 'droidloom-source'; UPDATE_TOOL = RELEASE / 'droidloom-update'
    LOCK = REPO / 'android/manifest/production-full-apex-tests-source-lock.json'
    RECOVERY_LOCK = Path(R22['profiles']['new']['lock']['path'])
    additions = [got, *R22['support'].values(), *release_refs.values(), current['rows'], current['freeze'],
        R22['release_ci'], R22['plan_evidence'], R22['host_direct_abi'],
        *R22['host_abi_inputs'], *R22['predecessor'].values(),
        *[row[k] for row in R22['profiles'].values() for k in ('lock', 'plan')],
        R22['controls']['transition'], R22['controls']['admission'], R22['controls']['real_git'],
        *R22['controls']['source_inputs']]
    for item in additions:
        path = Path(item['path']); pin = (item['bytes'], item['sha256'])
        need(path not in PINS or PINS[path] == pin, 'R22 cannot replace any historical input pin')
        PINS[path] = pin
    PINS[LOCK] = (400720, TRANSITION22.NEW_LOCK_SHA)
    need(all(PINS[path] == pin for path, pin in R22_PRESERVED_PINS.items()),
         'every pre-existing historical pin remains unchanged')
    OBS.update(schema='p4-cp3a-normal-vendor-build-r22-v1', source_tree=TREE,
        actual_updater_release_source_tree=TREE,
        updater_release_and_full_canonical_source_tree_identical=True,
        historical_R21_source_tree=R20['current_source']['tree'])


def r22_current_baseline():
    need(digest(SOURCE / '.droidloom-source-manifest.json') == ADMISSION22.MANIFEST,
         'actual R21 final full lint652 manifest remains the initial source baseline')
    for item, (path, inode) in zip(ADMISSION22.LOCKS, LOCK_PINS):
        need(str(path) == item['path'] and check_lock(path, inode) == item['identity']
             and digest(path) == ADMISSION22.reference(item)
             and path.read_bytes().hex() == item['body_hex'],
             'original lock inode and actual R21 normal recovery body unchanged')
    need(not os.path.lexists(WORK / 'source-projection.json'), 'no interrupted source projection')


def r22_validate_controls():
    controls = R22['controls']
    actual = ADMISSION22.validate_original_git_fixture(r20_json(controls['real_git']))
    admission = r20_json(controls['admission'])
    need(admission['schema'] == 'p4-r22-actual-predecessor-admission-controls-v1'
         and admission['passed'] is True and len(admission['negative_cases']) == 9
         and admission['complete_original_inputs_bookended'] is True
         and admission['actual_new_ci_consumed'] is False
         and all(admission[k] == 0 for k in ('children_started', 'source_mutations', 'Android_builds', 'Android_starts'))
         and admission['production_ready'] is admission['runtime_qualified'] is False
         and ADMISSION22.content_reference(admission['module'])
             == ADMISSION22.content_reference(R22['support']['admission']),
         'actual immutable R21 admission controls are input validation only')
    transition = r20_json(controls['transition'])
    need(transition['schema'] == 'p4-r22-source-transition-pure-controls-v1'
         and type(transition['exit_code']) is int and transition['exit_code'] == 0
         and transition['cases'] == 9 and transition['partial_materialization_masks'] == 16
         and transition['real_fixture_inventory_hash_checked'] is True
         and transition['actual_AOSP_materialization'] is transition['build_started'] is False
         and transition['production_ready'] is transition['runtime_qualified'] is False,
         'actual pure transition controls cannot qualify Android')
    for name, key in (('apex_test_transition.py', 'transition'), ('apex_test_partial.py', 'partial')):
        rows = [row for row in transition['files'] if row['path'] == name]
        need(len(rows) == 1 and all(rows[0][field] == R22['support'][key][field]
             for field in ('bytes', 'sha256')), 'same reviewed complete/partial transition source')
    for reference in controls['source_inputs']:
        r20_check(reference)
    return {'actual_original_Git_fixture': actual,
        'actual_R21_admission_negative_cases': len(admission['negative_cases']),
        'transition_control_receipt': controls['transition'],
        'actual_652_transition_credit': False, 'production_ready': False, 'runtime_qualified': False}


def verify_serialized_retirement():
    global R20_ADMISSION_DEADLINE
    need(R20_ADMISSION_DEADLINE is None, 'single non-reentrant R22 evidence admission')
    R20_ADMISSION_DEADLINE = time.monotonic() + 150
    try:
        # These two validators keep their original historical globals and F9 pins.
        # Their immutable predecessor reports are never treated as live source state.
        historical_failure = r21_validate_prebuild_failure()
        refs = R20['R19']
        r20_check(refs['worker'])
        historical_values = {k: r20_json(refs[k]) for k in ('bundle', 'outer', 'build', 'recovery', 'retirement')}
        historical_recovery = ADMISSION20.validate_predecessor(historical_values, refs)
        legacy = r20_json(R20['historical_83'])
        need(len(legacy['paths']) == 83 and len({x['path'] for x in legacy['paths']}) == 83,
             'whole unchanged original 83-input roster')
        live_transition = {ADMISSION20.MANIFEST['path'], *[x['path'] for x in ADMISSION20.LOCKS]}
        checked = []
        for item in legacy['paths']:
            if item['path'] in live_transition:
                continue
            got = digest(Path(item['path']))
            need(item['expected_pins'] and all(
                got['bytes'] == x['bytes'] and got['sha256'] == x['sha256']
                and ('f9' not in x or got['identity'] == x['f9']) for x in item['expected_pins']),
                'immutable original historical input: ' + item['path'])
            checked.append(got); r20_guard_admission()
        need(len(checked) == 79, 'only four explicitly bound current identities may transition')
        for path, expected in R20_HISTORICAL_PINS.items():
            got = digest(path)
            need((got['bytes'], got['sha256']) == expected, 'original R19 fixed dependency retained')
            r20_guard_admission()
        for name, item in historical_values['retirement']['clients'].items():
            r20_validate_client(item, item['stdout'], 1 if name == 'original' else 0)
        predecessor = R22['predecessor']
        for reference in predecessor.values():
            r20_check(reference)
        values = {k: r20_json(predecessor[k]) for k in ('contract', 'bundle', 'terminal', 'build', 'recovery')}
        need(values['contract'] == R20, 'exact old R21 operational contract retained')
        previous = ADMISSION22.validate_r21_predecessor(values, predecessor, R22['baseline'])
        for document in (values['build'], values['recovery']):
            for command in document['commands']:
                for channel in ('stdout', 'stderr'):
                    r20_check(command[channel])
        ci = r20_json(R22['release_ci'])
        release = ADMISSION22.validate_current_release(ci, R22['current_binaries'], R22['ci_provenance'])
        for item in R22['current_binaries'].values():
            got = r20_check(item)
            with Path(got['path']).open('rb') as stream:
                header = stream.read(20)
            need(header[:6] == b'\x7fELF\x02\x01' and header[18:20] == b'\x3e\x00',
                 'actual current normal x86_64 ELF header')
            need(digest(Path(got['path'])) == got, 'ELF unchanged across actual header read')
        host = r20_json(R22['host_direct_abi'])
        need(host['schema'] == 'p4-current19-static-direct-import-compatibility-v1'
             and host['host'] == 'ai395' and host['source'] == ADMISSION22.CURRENT
             and host['binary_count'] == 19 and host['passed_direct_symbols_only'] is True
             and host['dynamic_transitive_loading_tested'] is False
             and host['runtime_qualified'] is False and host['production_ready'] is False
             and len(host['binaries']) == 19 and len({x['binary'] for x in host['binaries']}) == 19
             and {x['binary']: x['sha256'] for x in host['binaries']}
                == {name: x['sha256'] for name, x in R22['current_binaries'].items()}
             and all(x['missing_strong'] == [] for x in host['binaries']),
             'actual current direct host symbol evidence, retaining its limits')
        for item in ADMISSION22.validate_host_abi_custody(host, R22['host_abi_inputs']):
            r20_check(item)
        controls = r22_validate_controls()
        targets = R22['live_retirement_targets']
        need(len(targets) == len({(x['scope'], x['unit']) for x in targets})
             and targets[:len(R20['live_retirement_targets'])] == R20['live_retirement_targets'],
             'all original known live retirement targets retained without substitution')
        required = {
            ('user', 'p4-cp3a-vendor-supervisor-20261120-9907-r21.service'),
            ('user', 'p4-cp3a-vendor-20261120-9907-r21.service'),
            ('user', 'p4-cp3a-vendor-20261120-9907-r21-recovery.service'),
            ('user', 'p4-r22-apex-providers-git-fixture-20261120-3b9d-r1.service'),
            ('user', 'p4-r22-apex-providers-git-fixture-20261120-3b9d-r2.service')}
        need(required <= {(x['scope'], x['unit']) for x in targets},
             'actual R21 and both isolated provider fixture units explicitly retired')
        actual_units = [r20_live_retired(x['unit'], x.get('pids', []), x['scope']) for x in targets]
        for item in R20['preparation_clients'] + R22['preparation_clients']:
            r20_validate_client(item, item['stdout'], item.get('expected_exit_code', 0))
        r22_current_baseline()
        return {'schema': 'p4-serialized-heavy-build-resource-plan-v1',
            'original_minimum_memory_gib': 42, 'vendor_memory_max_gib': 24,
            'simultaneous_other_heavy_compilers': 0, 'bounded_light_scopes_max_gib': 3.25,
            'host_reserve_gib': 12, 'unallocated_margin_within_minimum_gib': 2.75,
            'actual_R19_failed_build_and_complete_original_recovery': historical_recovery,
            'actual_R20_prebuild_failure_and_independent_retirement': historical_failure,
            'actual_R21_Soong_failure_and_complete_original_recovery': previous,
            'new_actual_current_release': release, 'historical_83_inputs_preserved': True,
            'historical_79_immutable_inputs_rechecked': checked, 'actual_units': actual_units,
            'new_four_provider_controls': controls, 'new_provider_materialization_credit': False,
            'resource_admission_reused': False, 'production_ready': False, 'runtime_qualified': False,
            'observed_ns': time.time_ns()}
    finally:
        R20_ADMISSION_DEADLINE = None
