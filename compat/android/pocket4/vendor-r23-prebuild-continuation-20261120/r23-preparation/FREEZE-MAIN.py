def complete_clients(path):
    descriptor, raw = pinned(path, SOURCE_INPUT_PINS['CLIENTS-RAW.json'])
    clients = []
    for item in json.loads(raw):
        pages = [decode(value.encode()) for value in item['pages_raw']]
        need(pages and type(item['expected_exit_code']) is int, 'actual client pages and outcome')
        original = pages[0]
        status = original['status']; cursor = 0; body = bytearray()
        need(status['state'] == 'exited' and status['exit_code'] == item['expected_exit_code']
             and type(status['exit_code']) is int and status['output_complete'] is True
             and status['capture_error'] is None, 'actual final client state')
        for page in pages:
            need(page['session_id'] == original['session_id'] and page['status'] == status
                 and page['archive_path'] == original['archive_path'] and page['offset'] == cursor
                 and page['output_complete'] is True and page['utf8_pending'] is False
                 and page['text_is_lossy'] is False and page['truncated_before_offset'] is False,
                 'continuous complete original terminal byte pages')
            chunk = bytes.fromhex(page['bytes_hex'])
            need(len(chunk) == page['next_offset'] - cursor
                 and hashlib.sha256(chunk).hexdigest() == page['chunk_sha256'],
                 'whole actual terminal page body')
            body.extend(chunk); cursor = page['next_offset']
        stdout, actual = read(original['archive_path'])
        need(bytes(body) == actual and cursor == original['available_end']
             == status['bytes_seen'] == status['bytes_stored'] == stdout['bytes'],
             'complete original stdout archive under held F9 bookends')
        clients.append({'name': item['name'], 'session_id': original['session_id'],
            'expected_exit_code': item['expected_exit_code'], 'actual_status': status, 'stdout': stdout})
    need(len(clients) == 4 and len({x['session_id'] for x in clients}) == len(clients),
         'four actually completed original preparation clients')
    return descriptor, clients


def absent_roots():
    need(ROOT.resolve() == ROOT, 'same original vendor parent path')
    fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = f9(os.fstat(fd))
        need(before[:5] == [66306, 72405100, 16832, 1000, 1000],
             'exact actual original vendor parent inode and authority')
        for name in ('producer-build-r22-9907', 'out-build-r22-9907', 'tmp-build-r22-9907',
                     'producer-build-r23-9907', 'out-build-r23-9907', 'tmp-build-r23-9907'):
            try:
                os.stat(name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise RuntimeError('pre-existing old or new generation root: ' + name)
        need(before == f9(os.fstat(fd)) == f9(ROOT.lstat()), 'held parent whole absence bookend')
        return {'parent': str(ROOT), 'parent_identity': before,
            'R22_roots_absent': ['producer-build-r22-9907','out-build-r22-9907','tmp-build-r22-9907'],
            'R23_roots_absent': ['producer-build-r23-9907','out-build-r23-9907','tmp-build-r23-9907']}
    finally:
        os.close(fd)


def source_conservation(old_raw, new_raw, old_outer, new_outer):
    old = old_raw.decode(); new = new_raw.decode()
    old_ast = ast.parse(old); new_ast = ast.parse(new)
    lines = old.splitlines(keepends=True)
    guards = [x for x in old_ast.body if isinstance(x, ast.If)
              and ast.unparse(x.test) == "__name__ == '__main__'"]
    need(len(guards) == 1, 'single unchanged original main guard')
    guard = guards[0]
    need(new.startswith(''.join(lines[:guard.lineno-1])) and new.endswith(''.join(lines[guard.lineno-1:])),
         'entire exact frozen R22 prefix and original main retained')
    original = {x.name: x for x in old_ast.body if isinstance(x, ast.FunctionDef)}
    successor = {x.name: x for x in new_ast.body if isinstance(x, ast.FunctionDef)}
    changed = [name for name in original
               if ast.dump(original[name], include_attributes=False)
               != ast.dump(successor[name], include_attributes=False)]
    need(sorted(changed) == ['r20_recovery_retirement', 'verify_serialized_retirement'],
         'only two explicitly reviewed existing definitions change')
    def text_of(node, text):
        return ''.join(text.splitlines(keepends=True)[node.lineno-1:node.end_lineno])
    verify = text_of(original['verify_serialized_retirement'], old)
    anchor = "        r22_current_baseline()\n        return {'schema': "
    replacement = "        r22_current_baseline()\n        successor = r23_successor_extra_admission()\n        return {'actual_R22_continuation': successor, 'schema': "
    need(verify.count(anchor) == 1 and text_of(successor['verify_serialized_retirement'], new)
         == verify.replace(anchor, replacement), 'one exact extra call within the original absolute deadline')
    retired = text_of(original['r20_recovery_retirement'], old)
    need(text_of(successor['r20_recovery_retirement'], new) == retired.replace(
        'p4-r22-original-build-retirement-before-recovery-v1',
        'p4-r23-original-build-retirement-before-recovery-v1'), 'only current retirement schema changes')
    need(new_outer == old_outer.replace(
        b"BUNDLE_SHA = 'b97888b0542bace5aa55bcf43dd13b0a699be9a437878372703d8bd6e214b296'",
        b"BUNDLE_SHA = 'UNFROZEN_SOURCE_ONLY'").replace(b'r22', b'r23').replace(b'R22', b'R23'),
        'original complete outer changes only generation literals and the pending bundle pin')
    return {'entire_frozen_R22_prefix_and_main_bytes_retained': True,
        'only_two_existing_definitions_changed': changed,
        'same_original_absolute_admission_deadline': True,
        'original_build_recovery_resource_and_lock_functions_unchanged': True}


def main():
    need(type(INDEPENDENT_FREEZER_REVIEW_PIN) is tuple,
         'actual independent source review must be frozen before preparation')
    need(os.getuid() == os.geteuid() == os.getgid() == 1000, 'ordinary original ai395 owner')
    need(18 in os.sched_getaffinity(0), 'original reserved preparation CPU18')
    os.sched_setaffinity(0, {18})
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8*1024**2, 8*1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0)); signal.alarm(120)
    need(not os.path.lexists(DEST), 'fresh create-only R23 controller directory')
    absence = absent_roots()
    staged = {name: pinned(STAGE/name, pin)[0] for name, pin in SOURCE_INPUT_PINS.items()}
    review_ref, review_raw = pinned(STAGE/'FREEZER-INDEPENDENT-REVIEW.json', INDEPENDENT_FREEZER_REVIEW_PIN)
    review = decode(review_raw)
    need(review.get('passed_source_review') is True and review.get('host_execution') is False,
         'reviewed actual freezer source, without invented runtime credit')
    source_inputs = list(staged.values()) + [review_ref, read(Path(__file__))[0]]
    old_worker, old_raw = pinned(R22/'source.py', (315362,'ab581ee8886af0ad6d64a0694bc8595387e43531e4e4bd8b1a49cd313cbc13cc'))
    old_outer_ref, old_outer = pinned(R22/'outer.py', (35232,'836ff9444ae1968284812da1606820f47d214ad3a95d87c1f27caf5bdd56787e'))
    template_ref, template = pinned(STAGE/'source-r23-template.py', SOURCE_INPUT_PINS['source-r23-template.py'])
    outer_ref, outer_template = pinned(STAGE/'outer-r23-template.py', SOURCE_INPUT_PINS['outer-r23-template.py'])
    conservation = source_conservation(old_raw, template, old_outer, outer_template)
    old = types.ModuleType('r23_exact_frozen_r22'); old.__file__ = old_worker['path']
    exec(compile(old_raw, old.__file__, 'exec'), old.__dict__)
    need(str(old.LOCK) == str(ROOT/'producer-build-r22-9907/android/manifest/production-full-apex-tests-source-lock.json'),
         'exact original never-created R22 planned producer lock')
    helper, helper_ref = module(STAGE/'r22_prebuild_admission.py', SOURCE_INPUT_PINS['r22_prebuild_admission.py'])
    r22_inputs = {}; raw_inputs = {}
    for name, (relative, size, sha, identity) in helper.HISTORY.items():
        reference, raw = pinned(R22/relative, (size,sha))
        need(reference['identity'] == identity, 'same complete original R22 historical file identity')
        r22_inputs[name] = reference; raw_inputs[name] = {'reference': reference, 'raw': raw}
    need(decode(raw_inputs['contract']['raw']) == old.R22, 'same actually executed original operational contract')
    baseline = {'manifest': old.digest(old.SOURCE/'.droidloom-source-manifest.json'), 'locks': []}
    for original in old.ADMISSION22.LOCKS:
        reference, raw = read(original['path'])
        baseline['locks'].append({**reference, 'body_hex': raw.hex()})
    raw_inputs['preparation_outputs'] = {}
    for client in old.R22['preparation_clients']:
        actual, raw = read(client['stdout']['path'])
        need(actual == client['stdout'], 'complete original R22 preparation stdout identity')
        raw_inputs['preparation_outputs'][client['session_id']] = {'reference':actual,'raw':raw}
    failure = helper.validate_r22_prebuild(raw_inputs, baseline)
    old.r22_current_baseline(); old.r22_validate_controls(); old.source_contracts()
    ci = old.r20_json(old.R22['release_ci'])
    for reference in old.R22['current_binaries'].values(): old.r20_check(reference)
    release = old.ADMISSION22.validate_current_release(ci, old.R22['current_binaries'], old.R22['ci_provenance'])
    abi = old.r20_json(old.R22['host_direct_abi'])
    for reference in old.ADMISSION22.validate_host_abi_custody(abi, old.R22['host_abi_inputs']):
        old.r20_check(reference)
    source_ref, source = document(PREP/'SOURCE_FREEZE.json')
    need((source_ref['bytes'],source_ref['sha256']) == (2243323,'2663841a3ff4d3b646bfbb67e4a54189ce23e47b364f08b32abb4efbf9dacba8'),
         'same complete actually prepared source freeze')
    rows_ref, rows = document(PREP/'SOURCE-ROWS.json')
    source_helper, source_helper_ref = module(PREP/'source_helpers.py',
        (27232,'e6a14326b1aa1ccc17d606c60bfc9bdf525f47bb2ccafffc86a054c55dd06219'))
    need(same_source_snapshot(source_helper.source_snapshot(PREP/'producer', rows, CURRENT['tree']),
                              source['source_snapshot']), 'whole original current source remains unchanged')
    materialized = []
    for path, expected in old.PINS.items():
        if path == old.LOCK:
            continue
        actual = old.digest(path)
        need((actual['bytes'],actual['sha256']) == expected, 'every actual historical R22 pin remains unchanged')
        materialized.append(actual)
    need(len(materialized) == len(old.PINS)-1, 'one and only one unmaterialized planned declaration')
    client_descriptor, clients = complete_clients(STAGE/'CLIENTS-RAW.json')
    contract = {'schema':'p4-vendor-r23-prebuild-continuation-contract-v1',
        'operational_inputs_frozen':True, 'runtime_qualified':False, 'production_ready':False,
        'current_source':old.R22['current_source'], 'current_binaries':old.R22['current_binaries'],
        'baseline':old.R22['baseline'], 'r22_inputs':r22_inputs,
        'prebuild_helper':helper_ref, 'prebuild_controls':staged['actual-controls/RESULT.json'],
        'root_authority':absence['parent_identity'][:5], 'actual_predecessor_absence':absence,
        'unmaterialized_R22_plan':{'lock_path':str(old.LOCK),'lock_bytes':400720,
            'lock_sha256':old.TRANSITION22.NEW_LOCK_SHA,'absent_roots':absence['R22_roots_absent']},
        'all_actual_R22_materialized_input_refs':materialized,
        'additional_live_retirement_targets':[
            {'scope':'user','unit':'p4-cp3a-vendor-supervisor-20261120-9907-r22.service','pids':[]},
            {'scope':'user','unit':'p4-cp3a-vendor-20261120-9907-r22.service','pids':[]},
            {'scope':'user','unit':'p4-cp3a-vendor-20261120-9907-r22-recovery.service','pids':[]}],
        'preparation_clients':clients, 'source_inputs':source_inputs,
        'all_original_constraints_unchanged':True, 'source_conservation':conservation}
    # Finish every direct and complete producer bookend before creating DEST.
    direct = [*source_inputs, *r22_inputs.values(), template_ref, outer_ref,
        source_ref, rows_ref, source_helper_ref, client_descriptor,
        *[x['stdout'] for x in clients], baseline['manifest'],
        *[helper.reference(x,('body_hex',)) for x in baseline['locks']]]
    for reference in direct: check(reference)
    for reference in materialized:
        need(old.digest(Path(reference['path'])) == reference, 'complete historical materialized input bookend')
    need(same_source_snapshot(source_helper.source_snapshot(PREP/'producer', rows, CURRENT['tree']),
                              source['source_snapshot']), 'complete actual producer final bookend')
    need(absent_roots() == absence, 'same actual parent and all uncreated generation roots')
    DEST.mkdir(mode=0o700); (DEST/'inputs').mkdir(mode=0o700)
    contract_ref = save(DEST/'inputs/CONTRACT.json', contract)
    anchor = b'R23_CONTRACT_PIN = None'; need(template.count(anchor)==1, 'one exact new contract anchor')
    frozen = template.replace(anchor, ('R23_CONTRACT_PIN = '+repr((contract_ref['bytes'],contract_ref['sha256']))).encode())
    worker_ref = write(DEST/'source.py', frozen)
    worker = types.ModuleType('r23_actual_frozen_worker'); worker.__file__ = worker_ref['path']
    exec(compile(frozen,worker.__file__,'exec'), worker.__dict__)
    need(worker.R23 == contract and worker.R22 == old.R22 and worker.TREE == CURRENT['tree']
         and str(worker.CONTROL) == str(DEST/'actual'), 'actual complete successor imports the same full inputs')
    worker.r23_failure_inputs(); controls = worker.r23_validate_controls(); worker.source_contracts()
    need(set(old.PINS)-set(worker.PINS) == {old.LOCK}
         and all(worker.PINS[p] == pin for p,pin in old.PINS.items() if p != old.LOCK),
         'all actual historical pins retained; only exact never-materialized planned path reclassified')
    bundle = {'schema':'pocket4-vendor-r23-launch-bundle-v1', 'dispatch_inputs_frozen':True,
        'source_tree':CURRENT['tree'], 'current_runtime_source':CURRENT, 'worker':worker_ref,
        'operational_contract':contract_ref, 'actual_current_CI':old.R22['release_ci'],
        'actual_R22_prebuild_failure':r22_inputs, 'original_budgets_unchanged':True,
        'new_vendor_build_not_yet_dispatched':True, 'previous_failed_build_replaced':False,
        'runtime_qualified':False, 'production_ready':False}
    bundle_ref = save(DEST/'inputs/BUNDLE.json', bundle)
    anchor = b"BUNDLE_SHA = 'UNFROZEN_SOURCE_ONLY'"; need(outer_template.count(anchor)==1, 'one exact new bundle anchor')
    frozen_outer = outer_template.replace(anchor, ("BUNDLE_SHA = '"+bundle_ref['sha256']+"'").encode())
    compile(frozen_outer,str(DEST/'outer.py'),'exec')
    outer_ref = write(DEST/'outer.py',frozen_outer)
    receipt = {'schema':'p4-r23-actual-complete-input-freeze-v1', 'contract':contract_ref,
        'worker':worker_ref, 'outer':outer_ref, 'bundle':bundle_ref, 'actual_R22_failure':failure,
        'actual_current_release':release, 'actual_prebuild_controls':controls,
        'historical_actual_inputs_count':len(materialized),
        'all_actual_R22_inputs_bookended_unchanged':True, 'complete_current_source_unchanged':True,
        'explicit_unmaterialized_R22_plan':contract['unmaterialized_R22_plan'],
        'all_preparation_clients_complete':True, 'build_started':False, 'source_mutations':False,
        'source_locks_acquired':False, 'live_retirement_admitted':False,
        'runtime_qualified':False, 'production_ready':False}
    receipt_ref = save(DEST/'PREPARATION.json',receipt)
    print(json.dumps({'passed':True,'preparation':receipt_ref,'worker':worker_ref,'outer':outer_ref,
        'build_started':False,'runtime_qualified':False,'production_ready':False}),flush=True)


if __name__ == '__main__':
    main()
