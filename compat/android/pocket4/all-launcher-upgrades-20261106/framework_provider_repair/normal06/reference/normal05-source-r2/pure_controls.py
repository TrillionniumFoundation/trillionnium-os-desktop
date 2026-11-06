#!/usr/bin/env python3
"""Pure controls for new host-only gates; no filesystem, process, network or Android operations."""
import copy
import json

def need(value, message):
    if not value:
        raise RuntimeError(message)


def run(packet):
    framework = {'__name__': 'pure_framework_controls', '__file__': '<pure-framework-controls>'}
    snapshot = {'__name__': 'pure_snapshot_controls', '__file__': '<pure-snapshot-controls>'}
    fence = {'__name__': 'pure_fence_controls', '__file__': '<pure-fence-controls>'}
    for name, scope in [('framework_build.py', framework), ('main_snapshot.py', snapshot),
                        ('fenced_build.py', fence)]:
        exec(compile(packet[name], '<pure-' + name + '>', 'exec'), scope, scope)
    passed = []
    def good(name, operation):
        operation()
        passed.append(name)
    def bad(name, operation, expected):
        try:
            operation()
        except RuntimeError as error:
            need(str(error) == expected, 'CONTROL_WRONG_FAILURE:' + name)
        else:
            raise RuntimeError('CONTROL_ACCEPTED_BAD_PATH:' + name)
        passed.append(name)
    def row_for(role):
        value = copy.deepcopy(snapshot['EXPECTED'][role])
        state = {'pid': value['pid'], 'start_ticks': value['start_ticks'], 'state': 'S', 'ppid': value['ppid']}
        return {'pid': value['pid'], 'before': copy.deepcopy(state), 'after': copy.deepcopy(state),
                'status': {'Uid': ' '.join(map(str, value['uids'])),
                           'NSpid': ' '.join(map(str, value['namespace_pids']))},
                'cgroup': value['cgroup'], 'namespaces': value['namespaces'],
                'root_identity': value['root_identity'], 'alive_identity_verified': True}
    for role in snapshot['EXPECTED']:
        good('current_identity_' + role, lambda role=role: snapshot['qualify_process'](role, row_for(role)))
    def changed(path, value):
        row = row_for('zygote64')
        target = row
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        return row
    exact_identity_error = 'FIXED_IDENTITY_DIFFERS_FROM_TYPED_BASELINE'
    for name, path, value in [
        ('wrong_pid', ['pid'], 3588887),
        ('wrong_uid', ['status', 'Uid'], '1000 1000 1000 1000'),
        ('wrong_namespace_pid', ['status', 'NSpid'], '90360 1'),
        ('wrong_cgroup', ['cgroup'], '0::/system.slice/other.service\n'),
        ('wrong_mount_namespace', ['namespaces', 'mnt'], 'mnt:[1]'),
        ('wrong_user_namespace', ['namespaces', 'user'], 'user:[1]'),
        ('wrong_root_inode', ['root_identity', 'inode'], 2),
    ]:
        bad(name, lambda path=path, value=value: snapshot['qualify_process']('zygote64', changed(path, value)),
            exact_identity_error)
    bad('observed_dead_process', lambda: snapshot['qualify_process']('zygote64', changed(['after', 'state'], 'Z')),
        'FIXED_PROCESS_DEAD')
    bad('birth_changed_during_observation',
        lambda: snapshot['qualify_process']('zygote64', changed(['after', 'start_ticks'], 96586438)),
        'FIXED_PROCESS_CHANGED')
    bad('parent_changed_during_observation',
        lambda: snapshot['qualify_process']('zygote64', changed(['after', 'ppid'], 1)),
        'FIXED_PROCESS_CHANGED')
    bad('process_liveness_not_qualified',
        lambda: snapshot['qualify_process']('zygote64', changed(['alive_identity_verified'], False)),
        'FIXED_PROCESS_UNAVAILABLE')
    old = row_for('zygote64')
    old['pid'] = old['before']['pid'] = old['after']['pid'] = 3588887
    old['before']['start_ticks'] = old['after']['start_ticks'] = 80797153
    old['status']['NSpid'] = '3588887 647'
    bad('old_qa_zygote_cannot_qualify', lambda: snapshot['qualify_process']('zygote64', old), exact_identity_error)
    good('clean_fd_completion', lambda: snapshot['qualify_finish'](None, [], True))
    bad('close_error_cannot_emit_ok',
        lambda: snapshot['qualify_finish'](None, [{'errno': 9}], True), 'SNAPSHOT_FD_CLEANUP_FAILED')
    bad('deadline_cannot_emit_ok',
        lambda: snapshot['qualify_finish'](None, [], False), 'SNAPSHOT_DEADLINE')
    primary = RuntimeError('FIRST_FAILURE')
    try:
        snapshot['qualify_finish'](primary, [{'errno': 9}], False)
    except RuntimeError as error:
        need(error is primary, 'CONTROL_PRIMARY_FAILURE_REPLACED')
        passed.append('primary_failure_preserved_over_cleanup_and_deadline')
    else:
        raise RuntimeError('CONTROL_PRIMARY_FAILURE_LOST')
    lock = json.loads(packet['actual-provider-source-lock.json'])
    expected = framework['expected_published_manifest'](lock)
    need(len(lock['projects']) == 225 and len(lock['links']) == 8, 'CONTROL_LOCK_BINDING')
    good('complete_expected_225_project_plan', lambda: framework['qualify_completed_manifest'](expected, lock))
    for name, mutate in [
        ('partial_project_list', lambda d: d['plan']['projects'].pop()),
        ('wrong_commit', lambda d: d['plan']['projects'][0].__setitem__('commit', '0' * 40)),
        ('unlisted_project', lambda d: d['plan']['projects'].append(copy.deepcopy(d['plan']['projects'][0]))),
        ('changed_root_link', lambda d: d['plan']['links'][0].__setitem__('target', 'wrong-target')),
        ('old_source_lock_hash', lambda d: d.__setitem__('source_lock_sha256', framework['PREVIOUS_TYPED_LOCK_SHA'])),
        ('unrestricted_sync', lambda d: d['plan'].__setitem__('unrestricted_repo_sync', True)),
    ]:
        document = copy.deepcopy(expected)
        mutate(document)
        bad(name, lambda document=document: framework['qualify_completed_manifest'](document, lock),
            'normal published manifest is not the exact complete new locked plan')
    bad('actual_provider1_224_manifest_is_not_current_completion',
        lambda: framework['qualify_completed_manifest'](json.loads(packet['actual-published-source-manifest.json']), lock),
        'normal published manifest is not the exact complete new locked plan')
    memory = {'MemAvailable': 15 * 1024**3, 'SwapFree': 0}
    owned = {'memory.max': str(10 * 1024**3), 'cpu.max': '200000 100000',
             'memory.swap.max': '0', 'memory.swap.current': '0'}
    good('zero_swap_exact_minimum_without_global_swap_budget',
         lambda: framework['memory_admission'](memory, owned))
    bad('insufficient_fresh_RAM_no_retry',
        lambda: framework['memory_admission']({**memory, 'MemAvailable': memory['MemAvailable'] - 1}, owned),
        'less than 15 GiB MemAvailable for independent zero-swap profile; no automatic retry')
    bad('configured_owned_swap_nonzero_rejected',
        lambda: framework['memory_admission'](memory, {**owned, 'memory.swap.max': str(1024**3)}),
        'owned swap limit is not zero')
    bad('existing_owned_swap_nonzero_rejected',
        lambda: framework['memory_admission'](memory, {**owned, 'memory.swap.current': '4096'}),
        'existing owned swap is not zero')
    meminfo = (b'MemTotal: 16777216 kB\nMemAvailable: 15728640 kB\n'
               b'SwapTotal: 16777216 kB\nSwapFree: 0 kB\nSwapCached: 0 kB\n')
    good('exact_fixed_meminfo_fields_and_kB_conversion',
         lambda: need(framework['parse_admission_meminfo'](meminfo) == {
             'MemTotal': 16 * 1024**3, 'MemAvailable': 15 * 1024**3,
             'SwapTotal': 16 * 1024**3, 'SwapFree': 0, 'SwapCached': 0},
             'CONTROL_MEMINFO_BYTE_CONVERSION'))
    bad('duplicate_required_meminfo_field_rejected',
        lambda: framework['parse_admission_meminfo'](meminfo + b'MemAvailable: 15728640 kB\n'),
        'duplicate required meminfo field')
    bad('wrong_meminfo_units_rejected',
        lambda: framework['parse_admission_meminfo'](meminfo.replace(b'kB', b'bytes', 1)),
        'required meminfo field units differ')
    bad('missing_required_meminfo_field_rejected',
        lambda: framework['parse_admission_meminfo'](meminfo.replace(b'SwapCached: 0 kB\n', b'')),
        'required meminfo fields incomplete')
    base = {
        'historical_activation_sha256': snapshot['ACTIVATION_SHA'],
        'old_invalid_QA_epoch_sha256': snapshot['OLD_INVALID_EPOCH_SHA'],
        'old_QA_epoch_invalid': True, 'new_QA_epoch_qualified': False,
        'runtime_authorization_enabled': False,
        'protected_boot_id': snapshot['BOOT_ID'],
        'protected_identity_source_sha256': snapshot['IDENTITY_SOURCE_SHA'],
        'current_qualification_sha256': snapshot['CURRENT_QUALIFICATION_SHA'],
        'protected_processes': copy.deepcopy(snapshot['EXPECTED']),
        'runtime_epoch_sha256': snapshot['RUNTIME_EPOCH_SHA'], 'framework_epoch_sha256': snapshot['FRAMEWORK_EPOCH_SHA'],
        'current_guard_source_sha256': snapshot['CURRENT_GUARD_PIN']['sha256'],
        'app_scope_sha256': '1' * 64, 'app_scope_packages': ['synthetic.one', 'synthetic.two'],
        'cell_sha256': snapshot['CELL_SHA'], 'limits': copy.deepcopy(snapshot['LIMITS']),
        'main_cgroup': str(snapshot['CG']), 'main_cgroup_identity': {'device': 30, 'inode': 123},
        'memory_events': {'low': 0, 'high': 10, 'max': 0, 'oom': 0, 'oom_kill': 0, 'oom_group_kill': 0},
        'current_resources': {'memory.current': 3000000000, 'memory.swap.current': 0, 'pids.current': 99},
    }
    need(fence['compare'](base, copy.deepcopy(base))['main_fence_pass'] is True, 'CONTROL_SAME_FENCE_FAILED')
    passed.append('same_current_eight_roles_pass')
    changed_fence = copy.deepcopy(base)
    changed_fence['protected_processes']['zygote64']['pid'] = 3588887
    need(fence['compare'](base, changed_fence)['main_fence_pass'] is False, 'CONTROL_CHANGED_PID_ACCEPTED')
    passed.append('different_current_process_fails_fence')
    oom = copy.deepcopy(base)
    oom['memory_events']['oom'] += 1
    need(fence['compare'](base, oom)['main_fence_pass'] is False, 'CONTROL_OOM_ACCEPTED')
    passed.append('main_oom_delta_fails')
    regressed = copy.deepcopy(base)
    regressed['memory_events']['high'] -= 1
    bad('memory_counter_regression', lambda: fence['compare'](base, regressed), 'Main memory counters regressed')
    pressure = copy.deepcopy(base)
    pressure['memory_events']['high'] += 602
    report = fence['compare'](base, pressure)
    need(report['main_fence_pass'] is True and report['pressure_counter_increases_observed'] == {'high': 602} and
         report['unobserved_transient_effects_excluded'] is False and
         report['causal_attribution_of_counter_changes'] is False, 'CONTROL_PRESSURE_MISREPRESENTED')
    passed.append('pressure_preserved_without_causal_or_continuous_claim')
    widened = copy.deepcopy(base)
    widened['new_QA_epoch_qualified'] = True
    bad('host_snapshot_cannot_qualify_QA', lambda: fence['compare'](base, widened),
        'host build snapshot cannot authorize a QA epoch')
    baseline = json.loads(packet['actual-current-runtime-baseline.json'])
    good('actual_baseline_derives_eight_roles', lambda: snapshot['qualify_baseline'](baseline))
    missing = copy.deepcopy(baseline)
    missing['runtime']['held']['extra'].pop('composer')
    bad('missing_composer_rejected', lambda: snapshot['expected_from_baseline'](missing), 'TYPED_EIGHT_ROLES_REQUIRED')
    stale = copy.deepcopy(baseline)
    stale['runtime_epoch_sha256'] = '0' * 64
    bad('stale_runtime_baseline_rejected', lambda: snapshot['qualify_baseline'](stale), 'TYPED_RUNTIME_BASELINE_CHANGED')
    bad('missing_final_scope_pin_rejected', lambda: snapshot['qualify_scope_reference'](None, None), 'FINAL_APP_SCOPE_PIN_REQUIRED')
    guard_receipt = {
        'schema': 'pocket4-successor-main-guard-v1', 'baseline_sha256': snapshot['IDENTITY_SOURCE_SHA'],
        'runtime_epoch_sha256': snapshot['RUNTIME_EPOCH_SHA'], 'Main_epoch_sha256': snapshot['FRAMEWORK_EPOCH_SHA'],
        'eight_roles_including_composer_match': True, 'complete_paired_classpath_matches': True,
        'resource_limits_match': True, 'runtime_only_app_scopes_checked_separately': True,
        'UI_or_install_runtime_admitted': False, 'production_ready': False,
    }
    for name, key, value in [
        ('wrong_guard_baseline_receipt_rejected', 'baseline_sha256', '0' * 64),
        ('wrong_guard_runtime_receipt_rejected', 'runtime_epoch_sha256', '0' * 64),
        ('guard_cannot_grant_ui', 'UI_or_install_runtime_admitted', True),
    ]:
        bad(name, lambda key=key, value=value: snapshot['qualify_typed_guard']({**guard_receipt, key: value}), 'TYPED_GUARD_RECEIPT_REJECTED')
    # Deliberately synthetic small fixture; never emitted as an actual app scope.
    scope_pin = {'path': '/home/alex/work/pure-control-only/app-scope.json', 'bytes': 1, 'sha256': '1' * 64}
    packages = ['synthetic.one', 'synthetic.two']
    scope_receipt = {
        'schema': 'pocket4-app-scope-guard-v1', 'runtime_epoch_sha256': snapshot['RUNTIME_EPOCH_SHA'],
        'app_scope_sha256': scope_pin['sha256'], 'packages': packages,
        'current_apk_paths_and_file_identities_match': True, 'new_signature_verification_performed': False,
        'UI_or_install_runtime_admitted': False,
    }
    for name, key, value in [
        ('scope_receipt_old_epoch_rejected', 'runtime_epoch_sha256', '0' * 64),
        ('scope_receipt_wrong_apk_scope_rejected', 'app_scope_sha256', '0' * 64),
        ('scope_receipt_missing_package_rejected', 'packages', ['synthetic.one']),
        ('scope_cannot_claim_signature_verification', 'new_signature_verification_performed', True),
    ]:
        bad(name, lambda key=key, value=value: snapshot['qualify_scope_receipt']({**scope_receipt, key: value}, scope_pin, packages),
            'CURRENT_APP_SCOPE_RECEIPT_REJECTED')
    changed_scope = copy.deepcopy(base)
    changed_scope['app_scope_sha256'] = '0' * 64
    need(fence['compare'](base, changed_scope)['main_fence_pass'] is False, 'CONTROL_STALE_SCOPE_FENCE')
    passed.append('stale_scope_fails_outer_fence')
    changed_qualification = copy.deepcopy(base)
    changed_qualification['current_qualification_sha256'] = '0' * 64
    need(fence['compare'](base, changed_qualification)['main_fence_pass'] is False, 'CONTROL_STALE_QUALIFICATION_FENCE')
    passed.append('old_qualification_fails_outer_fence')

    need(len(passed) == len(set(passed)) == 59, 'CONTROL_CASE_COUNT')
    return {'schema': 1, 'state': 'PASS', 'passed': len(passed), 'cases': passed,
            'scope': 'Actual pure Python functions with synthetic identity/resource/failure fixtures and exact staged lock metadata; no device reuse, Main observation, Rust or Soong qualification.',
            'remote_reads': 0, 'subprocesses': 0, 'Main_actions': 0, 'Android_actions': 0,
            'normal_build_executed_by_controls': False}
