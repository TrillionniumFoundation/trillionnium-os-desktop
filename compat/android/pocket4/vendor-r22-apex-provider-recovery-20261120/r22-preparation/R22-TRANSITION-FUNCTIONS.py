"""R22 source transition/recovery functions; ROOT must integrate and review.

This fragment has no import-time action. It requires ROOT's frozen R22,
TRANSITION22, PARTIAL22 and r22_current_baseline, plus the original strict
r20_check/r20_json, ADMISSION20 reference/reaped gates, three source locks,
owned runner, durable source stages and unchanged build/recover budgets.
Only r20_recovery_retirement keeps its legacy entry-point name because the
unchanged generic recover() calls it. No controller or Android action is run.
"""


def source_contracts():
    evidence = r20_json(R22['plan_evidence'])
    need(evidence['schema'] == 'p4-r22-current-release-normal-plan-evidence-v1'
         and evidence['passed'] is True and evidence['all_original_children_reaped'] is True
         and evidence['inputs_before'] == evidence['inputs_after']
         and evidence['network_operations'] is False and evidence['materialize_or_reconcile'] is False
         and len(evidence['commands']) == 2, 'actual current normal read-only profile plans')
    result = {}
    for i, (key, profile, sha) in enumerate((('old', 'production-full-lint', TRANSITION22.OLD_LOCK_SHA),
                                            ('new', 'production-full-apex-tests', TRANSITION22.NEW_LOCK_SHA))):
        entry = R22['profiles'][key]
        lock, plan_ref = r20_check(entry['lock']), r20_check(entry['plan'])
        need(lock['sha256'] == sha and Path(lock['path']).is_relative_to(CANONICAL_SOURCE),
             'new-release canonical old and new profile lock inputs')
        command = evidence['commands'][i]
        ADMISSION20.command_reaped(command)
        need(command['name'] == 'plan-' + profile
             and command['argv'] == [str(SOURCE_TOOL), '--profile', profile, 'plan', '--lock', lock['path']]
             and ADMISSION20.reference(command['stdout']) == plan_ref,
             'actual exact current normal plan argv and complete output')
        r20_check(command['stderr'])
        for item in (R22['current_binaries']['droidloom-source'], entry['lock']):
            observed = [x for x in evidence['inputs_before'] if x['path'] == item['path']]
            need(len(observed) == 1 and ADMISSION20.reference(observed[0]) == r20_check(item),
                 'actual plan process used this current ELF and exact lock inode')
        plan = BOOKENDS.normalized_plan(r20_json(entry['plan']))
        result[key] = {'schema_version': 1, 'source_lock_sha256': sha, 'plan': plan}
    old, new = TRANSITION22.validate_profiles(BOOKENDS, result['old'], result['new'])
    recovery = r20_json(R22['predecessor']['recovery'])
    need(recovery['schema'] == 'p4-cp3a-normal-vendor-build-r21-v1'
         and recovery['source_recovery_complete'] is True
         and recovery['new_lint652_source_state_verified'] is True
         and recovery['errors'] == []
         and recovery['final_normal_manifest']['original'] == R22['baseline']['manifest'],
         'actual complete R21 recovery retains this exact old manifest baseline')
    need(BOOKENDS.normalized_manifest(r20_json(recovery['final_normal_manifest']['copy'])) == old,
         'old actual normal plan exactly matches R21 final published lint652 manifest')
    return {'old': old, 'new': new}


def r22_require_R21_bodies(summary, contracts):
    recovery = r20_json(R22['predecessor']['recovery'])
    need(recovery['schema'] == 'p4-cp3a-normal-vendor-build-r21-v1'
         and recovery['source_recovery_complete'] is True
         and recovery['new_lint652_source_state_verified'] is True
         and recovery['all_original_inputs_and_source_files_unchanged'] is True
         and recovery['native_source_926_members_and_git_provenance_unchanged'] is True
         and recovery['complete_cmake_members_preserved'] == 3915
         and recovery['final_normal_manifest']['original'] == R22['baseline']['manifest']
         and recovery['errors'] == [], 'actual final R21 recovery required as the original source baseline')
    original = r20_json(recovery['content_bookends']['lint652-content-after-recovery'])
    keys = ('project', 'tree', 'tracked_entries', 'materialized_entries',
            'materialized_bytes', 'sparse_absent_entries', 'body_sha256')
    totals = ('content_sha256', 'materialized_entries', 'materialized_bytes', 'sparse_absent_entries')
    need(original['schema'] == summary['schema'] == 'pocket4-original-materialized-source-content-bookend-v1'
         and original['all_actual_Git_blob_reads_verified'] is True
         and summary['all_actual_Git_blob_reads_verified'] is True
         and original['source_mutations'] is summary['source_mutations'] is False
         and original['project_count'] == summary['project_count'] == 652
         and [x['project'] for x in original['projects']] == contracts['old']['plan']['projects']
         and [x['project'] for x in summary['projects']] == contracts['old']['plan']['projects']
         and sum(p['tracked_entries'] for p in original['projects']) == TRANSITION22.TRACKED_MEMBERS
         and sum(p['tracked_entries'] for p in summary['projects']) == TRANSITION22.TRACKED_MEMBERS
         and [{k: p[k] for k in keys} for p in summary['projects']]
             == [{k: p[k] for k in keys} for p in original['projects']]
         and {k: summary[k] for k in totals} == {k: original[k] for k in totals},
         'all actual R21 lint652 tuples, raw bodies, representation and complete CMake are unchanged')


def r22_compare(before, after, contracts, *, partial=False):
    if not partial:
        return TRANSITION22.compare_complete(BOOKENDS, contracts['old'], contracts['new'], before, after,
                                             DEADLINE, resource_guard)
    a = TRANSITION22.VerifiedInventory(BOOKENDS, before, contracts['old']['plan']['projects'],
                                      DEADLINE, resource_guard)
    b = TRANSITION22.VerifiedPartialInventory(BOOKENDS, after, contracts['old'], contracts['new'],
                                             DEADLINE, resource_guard)
    result = TRANSITION22.compare_rows(a, b, allow_partial=True,
                                      expected_count=TRANSITION22.TRACKED_MEMBERS)
    need(a.completed and b.completed, 'both full original and partial source streams completed')
    return result


def r22_candidate_rules(name):
    directory = CONTROL / (name + '-queries')
    result = PARTIAL22.candidate_checkout_rules(BOOKENDS, TRANSITION22,
        SOURCE, directory, DEADLINE, resource_guard, R22['git_conversion_admission'])
    need(result['schema'] == 'p4-r22-four-original-apex-provider-checkout-rules-v1'
         and result['candidate_count'] == 4 and set(result['providers']) == set(TRANSITION22.PROVIDERS)
         and result['all_five_attributes_unspecified'] is True
         and result['committed_effective_equal'] is True
         and result['custom_filters_executed'] is False and result['source_mutations'] is False,
         'four original raw-only APEX provider checkout rules from both actual projects')
    path = CONTROL / (name + '.json')
    with path.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True); stream.write('\n')
    return digest(path)


def normal_reconcile_and_verify(env):
    contracts = source_contracts()
    with original_source_locks():
        r22_current_baseline()
        run('verify-lint652-before', [str(SOURCE_TOOL), '--profile', 'production-full-lint',
            'verify-materialized', '--lock', R22['profiles']['old']['lock']['path'], '--output', str(SOURCE)],
            env, min(1200, max(1, DEADLINE - time.monotonic())), True)
        old, old_pin = manifest_observation('manifest-lint652-before')
        need(BOOKENDS.normalized_manifest(old) == contracts['old']
             and old_pin['original'] == R22['baseline']['manifest'], 'whole original R21 lint652 manifest before mutation')
        before = content_bookend('original-lint652-content-before', contracts['old']['plan']['projects'])
        r22_require_R21_bodies(before, contracts)
        # Fully validate every original row and prove the four original S-absent
        # entries without using a new partial state as the budget/baseline.
        a = TRANSITION22.VerifiedInventory(BOOKENDS, before, contracts['old']['plan']['projects'], DEADLINE, resource_guard)
        b = TRANSITION22.VerifiedInventory(BOOKENDS, before, contracts['old']['plan']['projects'], DEADLINE, resource_guard)
        initial = TRANSITION22.compare_rows(a, b, allow_partial=True, expected_count=TRANSITION22.TRACKED_MEMBERS)
        need(initial['provider_materialized'] == 0 and initial['provider_remaining_absent'] == 4
             and initial['provider_raw_bytes_materialized'] == 0 and a.completed and b.completed,
             'all four original APEX provider inputs absent')
        rules = r22_candidate_rules('apex-tests-checkout-rules-before')
        intent_pin = write_source_stage('source-reconcile-intent', {
            'old_manifest': old_pin, 'before_content': OBS['content_bookends']['original-lint652-content-before'],
            'expected_new_manifest_sha256': hashlib.sha256(BOOKENDS.encoded(contracts['new'])).hexdigest(),
            'original_four_apex_provider_members_absent': True, 'candidate_checkout_rules': rules,
            'source_lock_before': TRANSITION22.OLD_LOCK_SHA, 'source_lock_after': TRANSITION22.NEW_LOCK_SHA})
        run('normal-reconcile-apex-tests652', [str(SOURCE_TOOL), '--profile', 'production-full-apex-tests',
            'reconcile', '--lock', str(LOCK), '--output', str(SOURCE)],
            env, max(1, DEADLINE - time.monotonic()), True)
        write_source_stage('source-reconcile-returned', {'intent': intent_pin, 'command': OBS['commands'][-1]})
        run('verify-apex-tests652-before', [str(SOURCE_TOOL), '--profile', 'production-full-apex-tests',
            'verify-materialized', '--lock', str(LOCK), '--output', str(SOURCE)],
            env, min(1200, max(1, DEADLINE - time.monotonic())), True)
        new, new_pin = manifest_observation('manifest-apex-tests652-after-reconcile')
        need(BOOKENDS.normalized_manifest(new) == contracts['new'], 'exact normal APEX provider atomic publication')
        after = content_bookend('apex-tests652-content-after-reconcile', contracts['new']['plan']['projects'])
        comparison = r22_compare(before, after, contracts)
        tool_pins, versions = [], []
        for name in ('cmake', 'ctest'):
            path = CMAKE_PROJECT / 'bin' / name; pin = digest(path)
            with path.open('rb') as stream:
                header = stream.read(20)
            need(header[:6] == b'\x7fELF\x02\x01' and header[18:20] == b'\x3e\x00'
                 and pin['identity'][2] & 0o111, 'original x86_64 executable CMake tool')
            output = run('original-cmake-provider-' + name + '-version', [str(path), '--version'], env, 30, True)
            need(digest(path) == pin, 'original tool unchanged during execution')
            first = output.read_text().splitlines()[0]
            need(first.startswith(name + ' version '), 'original provider actual version')
            versions.append(first.split(' version ', 1)[1]); tool_pins.append(pin)
        need(versions[0] == versions[1], 'original CMake/CTest versions agree')
        OBS['full_apex_tests652_reconcile'] = {'normal_cli_completed': True, 'old_manifest': old_pin,
            'new_manifest': new_pin, 'comparison': comparison, 'original_complete_cmake_members': 3915,
            'full_provider_tool_pins': tool_pins, 'actual_tool_version': versions[0],
            'materialization_only': True, 'vendor_build_credit': False}
        write_source_stage('source-transition-complete', {'intent': intent_pin, 'new_manifest': new_pin,
            'full_apex_tests652_after': OBS['content_bookends']['apex-tests652-content-after-reconcile'], 'comparison': comparison})
        save()
    native_before = json.loads((CONTROL / 'native-source-before.json').read_text())
    need(native_snapshot() == native_before, 'normal APEX provider reconciliation changed independent native926 input')


def r22_verify_reconcile_return(record, intent_pin, name):
    payload, pin = record; command = payload['command']
    need(set(payload) == {'intent', 'command'} and payload['intent'] == intent_pin
         and command['name'] == name and command['argv'] == [str(SOURCE_TOOL), '--profile', 'production-full-apex-tests',
             'reconcile', '--lock', str(LOCK if name == 'normal-reconcile-apex-tests652' else RECOVERY_LOCK),
             '--output', str(SOURCE)], 'same normal APEX provider source command and original intent')
    ADMISSION20.command_reaped(command)
    r20_check(command['stdout']); r20_check(command['stderr'])


def r20_recovery_retirement():
    owner = verify_outer()
    record, _ = read_source_json(CONTROL / 'build-retirement-before-recovery.json')
    row = record['build_phase']
    need(record['schema'] == 'p4-r22-original-build-retirement-before-recovery-v1'
         and record['generation'] == owner['generation'] and record['serial_lock'] == owner['serial_lock']
         and record['worker_sha256'] == digest(SELF)['sha256']
         and row['mode'] == 'build' and row['unit'] == UNIT + '.service'
         and row['service_retired'] is True and row['client']['actual_reaped'] is True
         and row['client']['original_pidfd_held_until_reaped'] is True
         and row['late_start_unresolved'] is False
         and all(x['actual_reaped'] is True and x['original_pidfd_held_until_reaped'] is True
                 for x in record['original_outer_children']),
         'original outer retains actual complete build retirement before recovery')
    OBS['actual_build_retirement_before_recovery'] = r20_live_retired(UNIT + '.service')
    need(not RUNNER.owned_children(), 'no inherited unreaped build worker')
    resource_guard(True)


def verify_recovered_source(env):
    contracts = source_contracts()
    with original_source_locks():
        intent = read_source_stage('source-reconcile-intent')
        returned = read_source_stage('source-reconcile-returned')
        complete = read_source_stage('source-transition-complete')
        vendor = read_source_stage('source-vendor-intent')
        resume = read_source_stage('source-resume-intent')
        resume_returned = read_source_stage('source-resume-returned')
        need(intent is not None or all(x is None for x in (returned, complete, vendor, resume, resume_returned)),
             'no later source phase without this original durable transition intent')
        before = None
        if intent is not None:
            payload, intent_pin = intent
            need(set(payload) == {'old_manifest', 'before_content', 'expected_new_manifest_sha256',
                 'original_four_apex_provider_members_absent', 'candidate_checkout_rules', 'source_lock_before', 'source_lock_after'}
                 and payload['original_four_apex_provider_members_absent'] is True
                 and payload['source_lock_before'] == TRANSITION22.OLD_LOCK_SHA
                 and payload['source_lock_after'] == TRANSITION22.NEW_LOCK_SHA
                 and payload['expected_new_manifest_sha256'] == hashlib.sha256(BOOKENDS.encoded(contracts['new'])).hexdigest(),
                 'original four-body APEX provider transition intent')
            old, _ = read_source_json(CONTROL / 'manifest-lint652-before.json', payload['old_manifest']['copy'])
            need(BOOKENDS.normalized_manifest(old) == contracts['old']
                 and payload['old_manifest']['original'] == R22['baseline']['manifest'],
                 'original intent retains actual R21 complete lint manifest')
            before, _ = read_content_bookend('original-lint652-content-before', contracts['old']['plan']['projects'],
                                             payload['before_content'])
            r22_require_R21_bodies(before, contracts)
            r20_check(payload['candidate_checkout_rules'])
            if returned is not None:
                r22_verify_reconcile_return(returned, intent_pin, 'normal-reconcile-apex-tests652')
            if complete is not None:
                c, _ = complete
                need(set(c) == {'intent', 'new_manifest', 'full_apex_tests652_after', 'comparison'}
                     and c['intent'] == intent_pin, 'original exact source completion belongs to intent')
                recorded, _ = read_source_json(CONTROL / 'manifest-apex-tests652-after-reconcile.json', c['new_manifest']['copy'])
                need(BOOKENDS.normalized_manifest(recorded) == contracts['new'], 'original exact new publication')
                prior_after, _ = read_content_bookend('apex-tests652-content-after-reconcile', contracts['new']['plan']['projects'],
                                                     c['full_apex_tests652_after'])
                need(r22_compare(before, prior_after, contracts) == c['comparison'], 'actual original complete four-body provider comparison')
            if vendor is not None:
                need(complete is not None and set(vendor[0]) == {'source_transition_complete'}
                     and vendor[0]['source_transition_complete'] == complete[1], 'Vendor only after original exact complete source')
        actual, state_pin = manifest_observation('manifest-recovery-state-before-verify')
        branch = TRANSITION22.recovery_branch(BOOKENDS, actual, contracts['old'], contracts['new'],
                                              intent is not None, vendor is not None, resume is not None)
        need(resume_returned is None or resume is not None, 'no returned resume without durable intent')
        OBS['source_recovery_branch'] = {'branch': branch, 'observed_manifest': state_pin,
            'original_intent_present': intent is not None, 'original_return_present': returned is not None,
            'complete_present': complete is not None, 'vendor_present': vendor is not None,
            'resume_intent_present': resume is not None, 'original_deadline': DEADLINE}
        save()
        if branch == 'old652-before-reconcile-dispatch':
            run('verify-lint652-after', [str(SOURCE_TOOL), '--profile', 'production-full-lint',
                'verify-materialized', '--lock', R22['profiles']['old']['lock']['path'], '--output', str(SOURCE)],
                env, min(900, max(1, DEADLINE - time.monotonic())), True)
            after = content_bookend('lint652-content-after-recovery', contracts['old']['plan']['projects'])
            r22_require_R21_bodies(after, contracts)
            final, final_pin = manifest_observation('manifest-lint652-after-recovery')
            need(BOOKENDS.normalized_manifest(final) == contracts['old']
                 and final_pin['original'] == R22['baseline']['manifest'], 'original old652 unchanged before source dispatch')
            OBS.update(source_recovery_complete=True, original_lint652_source_state_verified=True,
                       new_apex_tests652_source_state_verified=False, final_normal_manifest=final_pin)
            return
        need(before is not None, 'all mutating or completed APEX provider branches require original full before inventory')
        if branch == 'old652-dispatched-requires-partial-bookend-before-one-normal-resume':
            need(complete is None and vendor is None and returned is None and resume is None
                 and resume_returned is None, 'only a genuinely incomplete original normal reconcile may resume once')
            need(state_pin['original'] == payload['old_manifest']['original'] == R22['baseline']['manifest'],
                 'unpublished normal reconcile retains the original old manifest full F9 and bytes')
            r20_recovery_retirement()
            partial = PARTIAL22.partial_snapshot(BOOKENDS, TRANSITION22, SOURCE,
                contracts['old'], contracts['new'], CONTROL / 'partial-apex-tests652-before-resume.ndjson',
                DEADLINE, resource_guard, R22['git_conversion_admission'], state_pin['original'])
            partial_path = CONTROL / 'partial-apex-tests652-before-resume.json'
            with partial_path.open('x') as stream:
                json.dump(partial, stream, sort_keys=True, indent=2); stream.write('\n')
            comparison = r22_compare(before, partial, contracts, partial=True)
            rules = r22_candidate_rules('apex-tests-checkout-rules-before-resume')
            need(digest(SOURCE / '.droidloom-source-manifest.json') == state_pin['original'],
                 'old manifest unchanged during partial recovery diagnostic')
            resource_guard(True)
            resume_pin = write_source_stage('source-resume-intent', {'original_intent': intent_pin,
                'original_before': payload['before_content'], 'partial_diagnostic': digest(partial_path),
                'partial_comparison': comparison, 'candidate_checkout_rules': rules,
                'fixed_recovery_deadline': DEADLINE, 'budget_baselines': digest(CONTROL / 'budget-baselines.json'),
                'normal_profile': 'production-full-apex-tests', 'retry_number': 0})
            run('normal-resume-apex-tests652-once', [str(SOURCE_TOOL), '--profile', 'production-full-apex-tests',
                'reconcile', '--lock', str(RECOVERY_LOCK), '--output', str(SOURCE)],
                env, max(1, DEADLINE - time.monotonic()), True)
            write_source_stage('source-resume-returned', {'intent': resume_pin, 'command': OBS['commands'][-1]})
            actual, _ = manifest_observation('manifest-apex-tests652-after-resume')
            need(BOOKENDS.normalized_manifest(actual) == contracts['new'], 'single normal resume published exact new manifest')
        elif resume is not None:
            # An existing resume record in a fresh recovery process is not a
            # license for another attempt or credit. This generation has only
            # one recovery phase; unexpected prior records fail closed.
            raise RuntimeError('pre-existing resume record requires a separately reviewed successor; no retry')
        run('verify-apex-tests652-after', [str(SOURCE_TOOL), '--profile', 'production-full-apex-tests',
            'verify-materialized', '--lock', str(RECOVERY_LOCK), '--output', str(SOURCE)],
            env, min(900, max(1, DEADLINE - time.monotonic())), True)
        final, final_pin = manifest_observation('manifest-apex-tests652-after-recovery')
        need(BOOKENDS.normalized_manifest(final) == contracts['new'], 'complete normal APEX provider recovery publication')
        after = content_bookend('apex-tests652-content-after-recovery', contracts['new']['plan']['projects'])
        comparison = r22_compare(before, after, contracts)
        OBS.update(source_recovery_complete=True, new_apex_tests652_source_state_verified=True,
                   original652_non_apex_provider_tuples_preserved=True, complete_cmake_members_preserved=3915,
                   complete_original_apex_provider_comparison=comparison, final_normal_manifest=final_pin)
        save()
