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
    exact_identity_error = 'FIXED_IDENTITY_DIFFERS_FROM_ACTUAL_READ02'
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
    need(len(lock['projects']) == 224 and len(lock['links']) == 8, 'CONTROL_LOCK_BINDING')
    good('complete_expected_224_project_plan', lambda: framework['qualify_completed_manifest'](expected, lock))
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
    bad('actual_old_214_manifest_is_not_current_completion',
        lambda: framework['qualify_completed_manifest'](json.loads(packet['actual-published-source-manifest.json']), lock),
        'normal published manifest is not the exact complete new locked plan')
    memory = {'MemAvailable': 13 * 1024**3, 'SwapFree': 2 * 1024**3}
    good('fresh_memory_exact_minimum', lambda: framework['memory_admission'](memory))
    bad('insufficient_memory_no_retry',
        lambda: framework['memory_admission']({**memory, 'MemAvailable': memory['MemAvailable'] - 1}),
        'less than 13 GiB MemAvailable for fresh Go5 streaming profile; no automatic retry')
    bad('insufficient_swap_no_retry',
        lambda: framework['memory_admission']({**memory, 'SwapFree': memory['SwapFree'] - 1}),
        'less than the required 2 GiB free swap; no automatic retry')
    base = {
        'historical_activation_sha256': snapshot['ACTIVATION_SHA'],
        'old_invalid_QA_epoch_sha256': snapshot['OLD_INVALID_EPOCH_SHA'],
        'old_QA_epoch_invalid': True, 'new_QA_epoch_qualified': False,
        'runtime_authorization_enabled': False,
        'protected_boot_id': snapshot['BOOT_ID'],
        'protected_identity_source_sha256': snapshot['IDENTITY_SOURCE_SHA'],
        'actual_read02_stdout_sha256': snapshot['ACTUAL_READ02_STDOUT_SHA'],
        'protected_processes': copy.deepcopy(snapshot['EXPECTED']),
        'cell_sha256': snapshot['CELL_SHA'], 'limits': copy.deepcopy(snapshot['LIMITS']),
        'main_cgroup': str(snapshot['CG']), 'main_cgroup_identity': {'device': 30, 'inode': 123},
        'memory_events': {'low': 0, 'high': 10, 'max': 0, 'oom': 0, 'oom_kill': 0, 'oom_group_kill': 0},
        'current_resources': {'memory.current': 3000000000, 'memory.swap.current': 0, 'pids.current': 99},
    }
    need(fence['compare'](base, copy.deepcopy(base))['main_fence_pass'] is True, 'CONTROL_SAME_FENCE_FAILED')
    passed.append('same_current_seven_roles_pass')
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
    need(len(passed) == len(set(passed)) == 40, 'CONTROL_CASE_COUNT')
    return {'schema': 1, 'state': 'PASS', 'passed': len(passed), 'cases': passed,
            'scope': 'Actual pure Python functions with synthetic identity/resource/failure fixtures and exact staged lock metadata; no device reuse, Main observation, Rust or Soong qualification.',
            'remote_reads': 0, 'subprocesses': 0, 'Main_actions': 0, 'Android_actions': 0,
            'normal_build_executed_by_controls': False}
