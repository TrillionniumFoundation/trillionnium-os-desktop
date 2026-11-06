def authorization_pin(recorded):
    """Normalize the two existing receipt formats without losing nanoseconds."""
    row = {key: recorded[key] for key in ('path', 'bytes', 'sha256', 'identity')}
    value = row['identity']
    if len(value) == 5:
        require(all(type(item) is int for item in value[:3]) and
                all(type(item) is str and item.isdecimal() for item in value[3:]),
                'current qualification five-field identity differs')
        require(recorded.get('resolved_path', recorded['path']) == recorded['path'],
                'current qualification resolved path differs')
        row['identity'] = value[:3] + [recorded['bytes'], int(value[3]), int(value[4])]
    require(len(row['identity']) == 6 and all(type(item) is int for item in row['identity']) and
            row['identity'][3] == row['bytes'], 'current qualification full identity differs')
    return row


def qualify_authorization_observation(row, observed_owner, wanted, owner=None):
    require(row == wanted and observed_owner['identity'] == row['identity'] and
            observed_owner['path'] == row['path'] and
            observed_owner['uid'] == observed_owner['gid'] == 1000 and not row['identity'][2] & 0o6002,
            'current authorization input full identity, owner or bytes changed')
    if owner is None:
        require(observed_owner['nlink'] == 1, 'current authorization single-link receipt differs')
    else:
        require(observed_owner == owner, 'current authorization recorded owner changed')


def authorized_held(recorded, observations, owner=None, include_bytes=False):
    wanted = authorization_pin(recorded)
    row, raw = held_file(wanted['path'], wanted['bytes'], include_bytes)
    info = P(wanted['path']).lstat()
    observed_owner = {'path': row['path'], 'uid': info.st_uid, 'gid': info.st_gid,
                      'nlink': info.st_nlink, 'identity': identity(info)}
    qualify_authorization_observation(row, observed_owner, wanted, owner)
    observation = {'pin': row, 'owner': observed_owner}
    if observation not in observations:
        observations.append(observation)
    return raw


def authorization_staged(name, size, checksum, observations):
    row, raw = held_file(HERE / name, size, True)
    require(row['bytes'] == size and row['sha256'] == checksum,
            'current authorization staged original bytes changed: ' + name)
    authorized_held(row, observations)
    return raw


def durable_current470_terminal(terminal, stdout):
    require(terminal['job_id'] == '1a1b26092d9-fc05-7dc7' and
            terminal['launch_nonce'] == '7da8162ba5cb9469071b73c7fc9edb2f' and
            terminal['state'] == 'succeeded' and terminal['exit_code'] == 0 and
            terminal['audit_recorded'] is True and terminal['output_complete'] is True and
            terminal['output_durable'] is True and terminal['terminal_publication_confirmed'] is True and
            terminal['terminal_publication_protocol'] == 1 and
            terminal['timed_out'] is False and terminal['cancelled'] is False and
            terminal['automatic_retry'] is False and
            terminal['log_bytes'] == {'stderr': {'seen': 0, 'stored': 0},
                'stdout': {'seen': len(stdout), 'stored': len(stdout)}} and
            terminal['log_errors'] == {'stderr': None, 'stdout': None} and
            terminal['log_synced'] == {'stderr': True, 'stdout': True} and
            terminal['log_truncated'] == {'stderr': False, 'stdout': False},
            'actual current470 authoritative terminal is incomplete or failed')


def qualify_current470_authorization(result, terminal, stdout):
    durable_current470_terminal(terminal, stdout)
    require(result['schema'] == 'pocket4-builder470-explicit-current-qualification-v1' and
            result['state'] == 'CURRENT470_EXPLICIT_28_TEST_QUALIFICATION_PASS' and
            result['current_builder_qualification_complete'] is True and
            result['errors'] == [] and result['cleanup'] == {'complete': True, 'children': [], 'errors': []} and
            result['expected_gates'] == CURRENT_QUALIFICATION_GATES and
            set(result['gates']) == set(CURRENT_QUALIFICATION_GATES) and
            all(value is True for value in result['gates'].values()) and
            result['command_count'] == 34 and result['tests_passed'] == 28 and
            [row['label'] for row in result['commands']] == CURRENT_QUALIFICATION_LABELS and
            all(row['returncode'] == 0 and row['timed_out'] is False for row in result['commands']),
            'complete current470 34-command and 28-test qualification required')
    require(result['Main_actions'] == result['Android_actions'] == result['install_actions'] == 0 and
            all(result[key] is False for key in ('Soong_invoked', 'runtime_authorization_enabled',
                'full_Android_Java_JNI_compiled', 'production_ready', 'cleanup_eligible',
                'new_authorization_contract_connected', 'historical_originals_rewritten',
                'legacy_binary_paths_written', 'legacy_binary_identities_claimed_current',
                'updater_rebuilt', 'automatic_retry')) and
            result['acceptance_requires_final_stdout_and_authoritative_durable_terminal'] is True and
            result['source_resume_test_compiled_from_current498_source'] is True and
            result['source_resume_test_fixtures_network_disabled_by_exact_cfg_test_source'] is True,
            'actual current qualification scope was widened or history was rewritten')
    require(result['owned_resource_gate']['pass'] is True and
            all(result['owned_resource_gate']['events'][key] == 0 for key in ('max', 'oom', 'oom_kill', 'oom_group_kill')) and
            result['memory_peak'] == '904175616' and result['swap_peak'] == '0' and
            len(result['cpu_affinity']) == 1 and len(result['cpu_affinity_before']) >= 3,
            'actual current qualification resource result differs')
    require(result['qualifier_source'] == CURRENT_QUALIFIER_PIN and
            result['stage_receipt'] == CURRENT_QUALIFICATION_STAGE_PIN and
            result['command_environment'] == CURRENT_QUALIFICATION_ENVIRONMENT,
            'actual current qualifier source, stage or offline command environment differs')
    continuity = result['dependency_continuity']
    require(continuity['recorded_files_and_archives'] == 2706 and continuity['selected_packages'] == 49 and
            continuity['registry_packages'] == 45 and continuity['new_dependency_fetches'] == 0 and
            len(continuity['current_updater_packages']) == 49 and
            len(continuity['expected_source_resume_packages']) == 46 and
            result['actual_source_resume_compile_packages'] == continuity['expected_source_resume_packages'] and
            set(result['actual_source_resume_compile_packages']) <= set(continuity['current_updater_packages']),
            'actual current dependency closure differs')
    for names, offset, registered, artifact, gate_key in [
            (EXPECTED_TESTS, 0, 209, result['current_artifacts']['test'], 'fresh_updater_independent_result_gates'),
            (EXPECTED_SOURCE_TESTS, 100, 20, result['source_resume_test_executable'], 'fresh_source_resume_independent_result_gates')]:
        gates = result[gate_key]
        require(len(gates) == len(names), 'actual current exact test gate count differs')
        for index, name in enumerate(names):
            label = 'projection-test-' + str(index + offset)
            row = next(value for value in result['commands'] if value['label'] == label)
            log = ('ok ' + name + '\n').encode()
            log_path = str(QUALIFICATION_RESULT.parent / (label + '.libtest'))
            gate = {'outer_results': 1, 'expected_stdout_runs': 1, 'registered_tests': registered,
                    'filtered_out_per_run': registered - 1, 'exact_name': name,
                    'summary_and_independent_result_agree': True}
            require(row['argv'] == [artifact['pin']['path'], '--exact', name, '--test-threads=1',
                    '--nocapture', '--logfile', log_path] and row['cwd'] == str(BUILD_SOURCE) and
                    row['focused_result_gate'] == gates[index] == gate and
                    row['independent_libtest_result']['path'] == log_path and
                    row['independent_libtest_result']['bytes'] == len(log) and
                    row['independent_libtest_result']['sha256'] == hashlib.sha256(log).hexdigest(),
                    'actual current exact independent test differs: ' + name)
    rows = [json.loads(line) for line in stdout.splitlines()]
    require(len(rows) == 36 and rows[0] == {'state': 'FRESH_RESOURCE_ADMISSION_OBSERVED',
                'receipt': result['resource_admission']} and
            rows[1:-1] == [{'event': 'FOCUSED_COMMAND_COMPLETED', 'label': label, 'returncode': 0}
                          for label in CURRENT_QUALIFICATION_LABELS],
            'actual current qualification stdout command closure differs')
    require(rows[-1] == {'schema': 'pocket4-current470-qualification-final-summary-v1',
                'state': 'PASS', 'current_builder_qualification_complete': True,
                'result': CURRENT_QUALIFICATION_PIN, 'commands': 34, 'tests_passed': 28,
                'late_error': None, 'Main_actions': 0, 'Soong_invoked': False,
                'new_authorization_contract_connected': False, 'production_ready': False,
                'cleanup_eligible': False, 'authoritative_durable_exit_zero_still_required': True},
            'actual current qualification final stdout is absent or incomplete')
    library = result['explicit_library_resource']
    require(library['path'] == '/usr/lib/x86_64-linux-gnu/libffi.so.8.2.0' and
            library['sha256'] == '1a0dc86f787f73e025a6e521056360afcbe70f2a82cd808132fefc2b4ee95daa' and
            library['bytes'] == 64184 and library['explicit_import_added_FDs'] == ['3'] and
            set(library['inherited_stdio']) == {'0', '1', '2'} and library['manual_close'] is False and
            library['retirement'] == 'authoritative durable normal process exit',
            'actual explicit qualifier library lifetime changed')


def current470_qualification_contract():
    observations = []
    raw = authorized_held(CURRENT_QUALIFICATION_PIN, observations, include_bytes=True)
    staged = authorization_staged('actual-current470-qualification-result.json', QUALIFICATION_BYTES,
                                  QUALIFICATION_SHA, observations)
    require(raw == staged, 'actual current qualification and staged original differ')
    result = json.loads(raw)
    terminal_raw = authorization_staged('actual-current470-qualification-terminal.original.json',
        731, '7042c5d094d24aae3eea354d03d9c3d6b94cb647fa0ca23a872814c3753e8e6a', observations)
    stdout = authorization_staged('actual-current470-qualification-stdout.original.jsonl',
        4024, '2854236b0227f6f89e9c6875708fa4863ead70306d02ee4b510d3fe7ddb790ac', observations)
    qualify_current470_authorization(result, json.loads(terminal_raw), stdout)
    authorized_held(result['qualifier_source'], observations)
    stage_raw = authorized_held(result['stage_receipt'], observations, include_bytes=True)
    stage = json.loads(stage_raw)
    require(stage['schema'] == 'pocket4-current470-qualification-stage-v1' and
            stage['state'] == 'SOURCE_STAGED_ONLY' and stage['qualifier_source'] == CURRENT_QUALIFIER_PIN and
            stage['compiler_invoked'] is False and stage['Main_actions'] == 0,
            'actual current qualifier stage binding differs')
    documents = {}
    require(set(result['authority_observations']) == set(CURRENT_AUTHORITY_NAMES),
            'actual eleven authority groups are incomplete')
    for name, row in result['authority_observations'].items():
        documents[name] = json.loads(authorized_held(row['pin'], observations, row['owner'], True))
    for row in [result['current_artifacts']['builder'], result['current_artifacts']['test'],
                result['source_resume_test_executable']]:
        authorized_held(row['pin'], observations, row['owner'])
        require(row['pin']['identity'][2] & 0o111, 'current qualified ELF is not executable')
    compile470 = documents['current470-result']
    require(result['current_compile_authority'] == result['authority_observations']['current470-result'] and
            result['current_artifacts']['builder']['pin'] == compile470['builder'] and
            result['current_artifacts']['test']['pin'] == compile470['test_executable'] and
            result['dependency_continuity']['authority']['pin'] == compile470['dependency_continuity']['authority'] and
            result['dependency_continuity']['current_updater_packages'] ==
                compile470['dependency_continuity']['actual_build_packages'],
            'new qualification is not tied to the same current builder and dependencies')
    for row in result['commands']:
        for stream in ('stdout', 'stderr'):
            authorized_held(row[stream], observations)
        if 'independent_libtest_result' in row:
            actual = authorized_held(row['independent_libtest_result'], observations, include_bytes=True)
            require(actual == ('ok ' + row['focused_result_gate']['exact_name'] + '\n').encode(),
                    'current independent libtest original changed')
    admission = json.loads(authorized_held(result['resource_admission'], observations, include_bytes=True))
    require(admission['profile'] == {'memory_max_bytes': 1073741824, 'memory_swap_max_bytes': 0,
                'minimum_fresh_MemAvailable_bytes': 3221225472, 'admission_difference_bytes': 2147483648,
                'global_swap_is_owned_budget': False} and
            admission['owned_observed'] == {'memory.max': '1073741824', 'cpu.max': '100000 100000',
                'memory.swap.max': '0', 'memory.swap.current': '0'} and
            parse_admission_meminfo(admission['meminfo']['raw_ascii'].encode('ascii'))['MemAvailable'] >= 3*1024**3,
            'actual new current qualification resource admission differs')
    require(verify_source_ancestry(documents['legacy491-manifest'], documents['legacy493-manifest'],
                documents['current498-manifest']) == result['source_ancestry'],
            'actual 491/493/498 provenance differs')
    return result, documents, observations


def qualify_settled_build07(terminal, durable, diagnosis, diagnostic_durable):
    for row, job, stdout_bytes in [(durable, '1a1b20bbc0a-fc05-7c2e', 877),
                                  (diagnostic_durable, '1a1b2240691-fc05-7c96', 4320)]:
        require(row['job_id'] == job and row['state'] == 'failed' and row['exit_code'] == 1 and
                row['output_complete'] is True and row['output_durable'] is True and
                row['terminal_publication_confirmed'] is True and row['timed_out'] is False and
                row['cancelled'] is False and row['automatic_retry'] is False and
                row['log_bytes'] == {'stderr': {'seen': 0, 'stored': 0},
                    'stdout': {'seen': stdout_bytes, 'stored': stdout_bytes}} and
                row['log_errors'] == {'stderr': None, 'stdout': None} and
                row['log_synced'] == {'stderr': True, 'stdout': True} and
                row['log_truncated'] == {'stderr': False, 'stdout': False},
                'settled failure durable terminal differs')
    require(terminal['state'] == 'FAILED' and terminal['error'] == "FileNotFoundError(2, 'No such file or directory')" and
            terminal['inner_build_called'] is True and terminal['inner_returncode'] is None and
            terminal['before_observed'] is True and terminal['after_observed'] is True and
            terminal['main_fence_assessment']['main_fence_pass'] is True and
            terminal['main_fence_assessment']['identity_or_limit_changes'] == [] and
            terminal['main_fence_assessment']['main_oom_delta_zero'] is True and
            terminal['capture_lifecycle_controls']['state'] == 'PASS' and
            terminal['capture_lifecycle_controls']['passed'] == 4 and
            terminal['Main_actions'] == terminal['Android_actions'] == 0 and
            terminal['installed'] is False and terminal['production_ready'] is False,
            'build07 failure or observed Main fence was relabeled')
    phases = ['control-root-timeout', 'control-root-escaped', 'control-root-pidfd',
              'control-outer-pidfd', 'before', 'after']
    require([row['phase'] for row in terminal['capture_lifecycle_receipts']] == phases,
            'build07 six outer child receipts differ')
    for row in terminal['capture_lifecycle_receipts']:
        command, reaper = row['command'], row['outer_subreaper']
        is_outer_control = row['phase'] == 'control-outer-pidfd'
        require(row['secondary_errors'] == [] and row['outer_watchdog_disarmed_and_restored'] is True and
                row['within_absolute_outer_deadline'] is True and reaper['begin_passed'] is True and
                reaper['restored'] is True and reaper['final_children_empty'] is True and
                command['returncode'] == (-9 if is_outer_control else 0) and
                command['kill_attempted'] is is_outer_control and command['timed_out'] is False and
                command['child_reaped'] is True and command['pidfd_closed'] is True and
                command['all_acquired_fds_closed'] is True and command['owned_tree_cleanup_complete'] is True and
                command['remaining_owned_children'] == [] and command['secondary_errors'] == [] and
                command['retirement_within_deadline'] is True and
                all(command[key]['closed'] is True for key in ('input', 'stdout', 'stderr')) and
                command['stdout']['complete'] is True and command['stderr']['complete'] is True,
                'build07 actual child, FD, watchdog or subreaper retirement differs')
    require(diagnosis['state'] == 'DIAGNOSIS_FAILED' and diagnosis['diagnosis_completed'] is False and
            diagnosis['observed_failure']['type'] == 'FileNotFoundError' and
            diagnosis['observed_failure']['errno'] == 2 and diagnosis['observed_failure']['filename'] ==
                '/home/alex/work/pocket4-native-typed-ingress-builder468-provider-closure-compile-03-20261106/attempt01/cargo-target/debug/droidloom-update' and
            diagnosis['verify_prepared_called'] is True and diagnosis['verify_prepared_returned'] is False and
            diagnosis['build_entrypoint_called'] is False and diagnosis['compiler_commands'] == 0 and
            diagnosis['Main_commands'] == diagnosis['Android_commands'] == diagnosis['guard_or_lock_calls'] == 0 and
            diagnosis['children_before'] == diagnosis['children_after'] == [] and
            diagnosis['original_failure_rewritten'] is False and
            len(diagnosis['secondary_errors']) == 1 and
            diagnosis['secondary_errors'][0]['phase'] == 'resource_closure' and
            diagnosis['secondary_errors'][0]['error']['repr'] == "RuntimeError('READONLY_DIAGNOSIS_CHANGED_FD_IDENTITIES')",
            'old468 missing-file diagnosis or its separate FD failure was rewritten')


def settled_build07_contract():
    observations = []
    documents = {}
    for name, size, checksum in SETTLED_BUILD07_FILES:
        documents[name] = json.loads(authorization_staged(name, size, checksum, observations))
    remote = OWNER / 'typed-ingress-framework-systemui-provider-build-07-20261106/build-fences-01/terminal.json'
    original, pin = json_pin(remote, '22c315979504854e249d059762a2ef008fc278c93b26c4a2bd65e0ba0a68bc34', 24701)
    authorized_held(pin, observations)
    require(original == documents['settled-build07-fence-terminal.original.json'],
            'actual original build07 terminal differs')
    qualify_settled_build07(original, documents['settled-build07-durable-terminal.original.json'],
        documents['settled-build07-diagnosis-stdout.original.jsonl'],
        documents['settled-build07-diagnosis-terminal.original.json'])
    return observations


def verify_current_authorization_after(context):
    for row in context['current_builder_authorization']['observations']:
        authorized_held(row['pin'], [], row['owner'])

