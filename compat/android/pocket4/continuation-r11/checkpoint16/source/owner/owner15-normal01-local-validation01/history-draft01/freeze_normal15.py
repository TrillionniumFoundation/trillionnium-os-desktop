#!/usr/bin/env python3
"""Local create-only Owner15 binder; never imports or executes the runtime scripts."""
import ast
import base64
import copy
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import stat

WORK = Path(__file__).resolve().parent
BASE = WORK.parent
EVIDENCE = BASE.parent / 'root-recovery-20261104-02/evidence'
OLD = BASE / 'owner14-normal01-freeze-01'
SOURCE = BASE / 'namespace-child-exit-source-freeze-15'
CONTROLLER = BASE / 'producer15-child-exit-controller-freeze-01'
OUT = BASE / 'owner15-normal01-freeze-01'
OLD_PREFIX = 'p4-owner14-normal-20261105-01'
PREFIX = 'p4-owner15-normal-20261105-01'
OLD_KIND = 'owned-real-producer14-normal01-fixture-repair01'
KIND = 'owned-real-producer15-normal01-namespace-child-exit01'
SCOPE = 'REAL_OWNER_ABI3_PINNED_CAUSE_TERMINAL_DRAIN_FIRST_ACTIVE_ORIGINAL_RETIREMENT'
REVISION = 'producer15-namespace-child-exit01'
BUILD_ROOT = '/home/alex/work/pocket4-supervisor-lmkd-child-exit-r11-build-15-01'
SOURCE_NAMES = ('actor.py', 'coordinator.py', 'prepare.py', 'owned.py', 'pinned_support.py', 'qualify.py')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pretty(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def pinned(path, size, digest):
    raw = path.read_bytes()
    assert len(raw) == size and sha(raw) == digest, str(path)
    raw.decode('utf-8')
    return raw, json.loads(raw)


def manifest(root, digest, count):
    raw = (root / 'manifest.json').read_bytes()
    assert sha(raw) == digest, str(root)
    rows = json.loads(raw)['files']
    assert len(rows) == count and len({row['path'] for row in rows}) == count
    for row in rows:
        name = row['path']
        assert not Path(name).is_absolute() and '..' not in Path(name).parts
        body = (root / name).read_bytes()
        assert len(body) == row['bytes'] and sha(body) == row['sha256'], name
        body.decode('utf-8')
    return raw


def file_record(path, raw):
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def resource_gate(report, memory_max):
    health = report['resource_health']
    assert health['held_own_cgroup_gate_passed'] is True
    assert health['expected_cpu_count'] == 1 and health['expected_memory_max'] == memory_max
    assert health['cgroup_files_written'] is False
    assert health['whole_invocation_resource_qualified'] is False
    assert health['swap_zero_claimed'] is False
    assert all(value == 0 for value in health['memory_event_delta'].values())
    before, after = health['before'], health['after']
    for key in ('membership', 'cgroup_identity', 'mount_identity', 'namespaces', 'limits', 'pid'):
        assert before[key] == after[key], key
    for observation in (before, after):
        assert observation['limits']['cpu.max'] == [100000, 100000]
        assert observation['limits']['memory.max'] == memory_max
        assert observation['limits']['memory.swap.max'] == 'max'
        assert observation['memory_swap_current'] == observation['memory_swap_peak'] == 0
        assert observation['memory_peak'] < memory_max
    return {'memory_peak': after['memory_peak'], 'memory_max': memory_max,
            'observed_swap_current_and_peak_zero': True, 'memory_swap_max': 'max',
            'pids_max': after['limits']['pids.max'], 'all_memory_event_deltas_zero': True,
            'whole_invocation_resource_qualified': False}


def identity_observation(report, main, require_limits):
    expected_processes = {**main['retained_processes'], **main['framework_binding']['processes']}
    assert len(expected_processes) == 7 and len(report['phases']) == 2
    assert report['collection_complete'] is True and report['error'] is None
    assert report['secondary_errors'] == [] and report['owned_fds_closed'] is True
    assert report['both_identity_observations_match'] is True
    assert report['expected_boot_id'] == main['framework_binding']['boot_id']
    assert report['main_epoch_expected'] == main['framework_sha256']
    assert report['expected_limits'] == main['resources']
    assert report['inputs'] == report['final_inputs']
    assert report['cgroup_before'] == report['cgroup_after'] == report['cgroup_named_after']
    assert report['runtime_authorized'] is False
    for key in ('Android_UI_actions', 'Main_mutations', 'child_processes_started', 'device_file_writes'):
        assert report[key] == 0, key
    for key in ('namespace_entry_performed', 'guard_source_modified', 'epoch_source_modified'):
        assert report[key] is False, key
    for phase in report['phases']:
        assert phase['complete'] is True and phase['errors'] == []
        assert phase['identity_matches_expected'] is True
        assert set(phase['processes']) == set(expected_processes)
        for role, expected in expected_processes.items():
            row = phase['processes'][role]
            assert row['complete'] is True and row['matches_expected'] is True
            assert row['actual'] == expected and row['expected_host_pid'] == expected['host_pid'], role
        assert phase['boot']['value'] == main['framework_binding']['boot_id']
        assert phase['boot']['matches_expected'] is True
        assert phase['inputs'] == report['inputs']
        assert set(phase['limits']) == set(main['resources'])
        for key, expected in main['resources'].items():
            row = phase['limits'][key]
            assert row['expected'] == expected and row['before'] == row['after']
            actual = expected if require_limits or key != 'pids.max' else '6144'
            assert row['value'] == actual
            assert row['matches_expected'] is (actual == expected)
        assert phase['all_five_limits_match_expected'] is require_limits
    guard = report['original_guard']
    assert guard['attempted'] is True and guard['completed'] is True
    assert guard['passed'] is require_limits
    if require_limits:
        value = guard['return_value']
        assert value['resource_limits_match'] is True and value['three_host_processes_match'] is True
        assert value['Main_epoch_sha256'] == main['framework_sha256']
        assert value['config_sha256'] == main['artifacts']['/etc/droidloom/cell.json']


def fixed_guard(sources, name, message):
    tree = ast.parse(sources[name]['content'])
    matches = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
               and isinstance(node.func, ast.Attribute) and node.func.attr == 'need'
               and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant)
               and node.args[1].value == message]
    assert len(matches) == 1
    return compile(ast.fix_missing_locations(ast.Expression(matches[0].args[0])), '<fixed-source-guard>', 'eval')


def main():
    assert not OUT.exists(), 'create-only freeze already exists'
    old_manifest = manifest(OLD, '80ba3a2d6caaae90cc11e4997a8fc58c527f25e318b0571bc29d827259981e32', 30)
    source_manifest = manifest(SOURCE, 'a50606bd1352c885fe98a20733d340b565a87849413f579321e86e40fecc2634', 17)
    controller_manifest = manifest(CONTROLLER, 'ebe67de541ba7766944aa19749c687b8a6966bd026a43fcb80e6e358b1b94634', 15)
    old_plan_raw, old_plan = pinned(OLD / 'plan.json', 72481, 'c5529e94a027e161cfd606c10cdcdc852dbaa4e341e20c441eb0168fd5f6f098')
    rb_path = EVIDENCE / 'owner15-compile01/compile-result.json'
    rr_path = EVIDENCE / 'owner15-ordinary01/run-result.json'
    rb_raw, rb = pinned(rb_path, 39999, '3327495b8cc3302dcc18ac72a7495f88d3354788404d2b05d1194d1e6e89ee30')
    rr_raw, rr = pinned(rr_path, 37356, 'ae364c528e0fca047357b13d91814bd461cc539320e78450a096ed64f889c76e')
    cfg_raw = (CONTROLLER / 'payload.json').read_bytes()
    cfg = json.loads(cfg_raw)
    assert cfg['revision'] == REVISION and cfg['source_manifest_sha256'] == sha(source_manifest)
    assert cfg['original_diff_sha256'] == sha((SOURCE / 'source.diff').read_bytes())
    assert len(cfg['preimage']) == 32 and len(cfg['overlays']) == 4
    for relative, row in cfg['overlays'].items():
        raw = (SOURCE / 'candidate' / relative).read_bytes()
        assert row['text'].encode() == raw and row['bytes'] == len(raw) and row['sha256'] == sha(raw)
        before = (SOURCE / 'preimage' / relative).read_bytes()
        assert cfg['preimage'][relative] == {'bytes': len(before), 'sha256': sha(before)}
    expected_inputs = copy.deepcopy(cfg['preimage'])
    expected_inputs.update({path: {key: row[key] for key in ('bytes', 'sha256')}
                            for path, row in cfg['overlays'].items()})
    assert rb['success'] is True and rb['compile_only'] is True and rb['revision'] == REVISION
    assert rb['payload_sha256'] == sha(cfg_raw) and rb['original_source_diff_sha256'] == cfg['original_diff_sha256']
    assert rb['candidate'] == BUILD_ROOT + '/candidate' and rb['target'] == BUILD_ROOT + '/target'
    assert rb['preimage_inputs'] == cfg['preimage']
    assert rb['prior_build_receipt_sha256'] == old_plan['actual_compile_receipt']['sha256']
    assert rb['inputs_before'] == rb['inputs_after'] == expected_inputs
    assert rr['inputs_before'] == rr['inputs_after'] == expected_inputs
    inventory = 'acd7a623dc28f83363d67aec1d4befe64c85cf852fa564312783005abc7a05b8'
    for result in (rb, rr):
        assert result['all_source_inventory_before_sha256'] == result['all_source_inventory_after_sha256'] == inventory
        assert result['installed_files_changed'] is False and result['android_runtime_started'] is False
        assert result['barrier_constructor_executed'] is False and result['full_owner_runtime_qualified'] is False
        assert all(c['returncode'] == 0 and c['timed_out'] is False for c in result['commands'])
    assert len(rb['commands']) == 2 and rb['test_binaries_executed'] is False
    assert '--lib' in rb['commands'][1]['argv'] and '--no-run' in rb['commands'][1]['argv']
    assert len(rb['artifacts']) == 4 and len(rb['compiled_test_artifacts']) == 2
    assert rr['success'] is True and rr['revision'] == REVISION and rr['ordinary_controls_only'] is True
    assert rr['external_compile_sha256'] == sha(rb_raw) and len(rr['commands']) == 7
    assert rr['rust_tests_passed'] == {'droidloom-pressure-relay': 39, 'droidloom-supervisor': 128}
    assert rr['rust_test_binary_counts'] == {'droidloom_pressure_relay:lib': 39, 'droidloom_supervisor:lib': 128}
    assert rr['ordinary_ipc_passed'] == 7 and rr['worker_context_passed'] is True
    assert rr['actual_compiled_entry_abi_passed'] is True and rr['real_broker_generation_qualified'] is False
    targets = rr['targeted_public_retirement_controls']
    assert len(targets) == 2
    for row in targets:
        assert row['passed'] == 1 and row['filtered_out'] == 38
        assert row['failed'] == row['ignored'] == row['measured'] == 0
    test_by_name = {row['target_name']: row for row in rb['compiled_test_artifacts']}
    command_artifacts = [test_by_name['droidloom_pressure_relay']] * 3 + [test_by_name['droidloom_supervisor']]
    command_artifacts += [rb['artifacts']['owned-ipc-controls']] * 2 + [rb['artifacts']['droidloom-supervisor']]
    for command, expected in zip(rr['commands'], command_artifacts):
        assert command['exact_child_pid'] > 0
        assert command['actual_held_elf'] == {key: expected[key] for key in ('path', 'bytes', 'sha256', 'device', 'inode', 'mode')}
    resource_summary = {'compile': resource_gate(rb, 1073741824), 'ordinary': resource_gate(rr, 536870912)}

    # Reuse the unchanged actual ABI3 C image and mechanism evidence from the
    # verified predecessor freeze. No new C build or mechanism run is inferred.
    cb_raw = (OLD / 'evidence/actual-android-build.json').read_bytes(); cb = json.loads(cb_raw)
    mm_raw = (OLD / 'evidence/actual-cgroup-mount-mechanism03.json').read_bytes(); mm = json.loads(mm_raw)
    assert sha(cb_raw) == old_plan['projection_build_receipt_sha256']
    assert cb['success'] is True and cb['errors'] == [] and cb['all_inputs_unchanged'] is True
    assert cb['source_manifest_sha256'] == old_plan['paired_projection_source_manifest_sha256']
    assert cb['Android_actual_MD_equals_preflight'] is True and cb['Android_input_count'] == 140
    assert cb['Android_needed'] == ['libc.so'] and cb['Android_constructor_executed'] is False
    assert len(cb['commands']) == 16 and all(c['returncode'] == 0 and c['child_reaped'] and not c['timed_out'] for c in cb['commands'])
    assert [(c['name'], c['passed']) for c in cb['host_control_results']] == [('protocol', 20), ('protocol-close-errno', 20), ('diagnostic', 7), ('cgroup-view', 8)]
    barrier = {key: cb['Android_artifact'][key] for key in ('path', 'bytes', 'sha256', 'device', 'inode')}
    barrier.update(mode=stat.S_IMODE(cb['Android_artifact']['mode']), destination='lib/libdroidloom_init_relay.so')
    assert barrier == old_plan['artifacts']['init-barrier']
    assert mm['success'] is True and mm['errors'] == []
    assert sha(mm_raw) == old_plan['cgroup_mount_mechanism_evidence']['report_sha256']

    restore_path = EVIDENCE / 'main-tasksmax-restore01/stdout.log'
    post_path = EVIDENCE / 'main-identity-readonly02/stdout.log'
    restore_raw, restore = pinned(restore_path, 60905, '07dac235abe10226316ffc29ba1c716a7cf19a18db39d7eefe19dcf02cc61af1')
    post_raw, post = pinned(post_path, 23171, 'e9344b538fbf6f6f06442b27d81d772be40db0ee3f3805823648a0a733055116')
    assert restore['ok'] is True and restore['error'] is None and restore['state'] == 'ORIGINAL_MAIN_TASKSMAX_RESTORED'
    tx = restore['transaction']
    assert tx['ok'] is True and tx['error'] is None and tx['secondary_errors'] == []
    assert tx['systemd_and_kernel_12288_proven'] is True and tx['original_main_guard_passed_after'] is True
    for key in ('action_lock_released', 'held_fds_closed', 'evidence_fds_closed', 'evidence_final_saved'):
        assert tx[key] is True
    for key in ('restart_performed', 'daemon_reload_performed', 'main_code_changed', 'original_guard_or_baseline_changed'):
        assert tx[key] is False
    assert tx['Android_UI_actions'] == 0 and tx['runtime_authorized'] is False
    assert set(tx['commands']) == {'show_before', 'set_property', 'show_after'}
    for command in tx['commands'].values():
        assert command['returncode'] == 0 and command['child_reaped'] is True and command['child_pidfd_exit_observed'] is True
        assert command['child_kill_attempted'] is False and command['error'] is None and command['secondary_errors'] == []
        assert command['tool_unchanged'] is True and command['output_complete'] is True
        for stream in command['streams'].values():
            raw = base64.b64decode(stream['base64'], validate=True)
            assert len(raw) == stream['bytes'] and sha(raw) == stream['sha256']
            assert stream['complete'] is True and stream['eof'] is True
        assert command['streams']['stderr']['bytes'] == 0
    assert tx['commands']['set_property']['argv'] == ['/usr/bin/systemctl', '--system', '--no-pager', '--no-ask-password', 'set-property', 'droidloomd.service', 'TasksMax=12288']
    identity_observation(tx['identity_before'], old_plan['main'], False)
    identity_observation(tx['identity_after'], old_plan['main'], True)
    identity_observation(post, old_plan['main'], True)
    assert tx['identity_before']['inputs'] == tx['identity_after']['inputs'] == post['inputs']
    assert tx['identity_before']['cgroup_before'] == tx['identity_after']['cgroup_before'] == post['cgroup_before']

    previous_path = EVIDENCE / 'owner14-normal01-runtime-read01/runtime-result.json'
    previous_raw, previous = pinned(previous_path, 57774, '954fa535427e79780cb3764d0eb28e2ab12b4a4af642c4bccf3244a4e1c97fea')
    assert previous['success'] is False and previous['attempt_nonce'] == old_plan['attempt_nonce']
    assert all(previous['exact_unit_cleanup'][key] is True for key in ('cgroup_absent', 'original_actor_dead', 'unit_not_found'))
    assert previous['main_before'] == previous['main_before_gate'] == previous['main_after']
    previous_audit = previous['actor_result']['latest_status']['relay_lifecycle']
    previous_events = [row['detail']['event'] for row in previous_audit['records']]
    assert 'active' not in previous_events and previous_events[-6:] == ['broker_retired', 'processes_dead', 'domain_empty', 'retired', 'resources_removed', 'claim_released']
    assert previous_audit['retirement_failure'] is None and previous_audit['cleanup_failure'] is None
    assert previous_audit['first_failure'] is None and previous_audit['recording_incomplete'] is False
    cause_raw = (SOURCE / 'evidence/owner14-cause-loss-review.json').read_bytes()
    cause = json.loads(cause_raw)
    assert cause['inputs']['runtime']['sha256'] == sha(previous_raw)
    assert cause['original_owner14_success'] is False and cause['guest_boot_first_cause_proved'] is False

    def remap(value):
        if isinstance(value, str): return value.replace(OLD_PREFIX, PREFIX)
        if isinstance(value, list): return [remap(item) for item in value]
        if isinstance(value, dict): return {key: remap(item) for key, item in value.items()}
        return value

    plan = remap(old_plan)
    attempt = os.urandom(32).hex()
    assert attempt != old_plan['attempt_nonce'] and attempt != '0' * 64
    plan.update(kind=KIND, scope=SCOPE, attempt_nonce=attempt, description='Pocket4 Owner15 ABI3 NORMAL01 ' + attempt)
    plan['spec']['host_uid'] = 61287
    plan['spec']['subordinate_uids']['start'] = 21000000
    plan['spec']['subordinate_gids']['start'] = 21000000
    plan['spec']['runtime_dir'] = '/run/droidloom/cells/u61287'
    for role in ('droidloomd', 'droidloom-supervisor', 'droidloom-psi-owner'):
        row = copy.deepcopy(rb['artifacts'][role])
        assert row['path'] == BUILD_ROOT + '/target/debug/' + role
        assert row['bytes'] > 0 and row['inode'] > 0 and row['mode'] & 0o111 and not row['mode'] & 0o6022
        row['destination'] = old_plan['artifacts'][role]['destination']
        plan['artifacts'][role] = row
    relay = plan['spec']['pressure_relay']
    for name, role in (('broker', 'droidloom-psi-owner'), ('entry_supervisor', 'droidloom-supervisor')):
        relay[name]['sha256'] = plan['artifacts'][role]['sha256']
    plan['actual_compile_receipt'] = file_record(rb_path, rb_raw)
    plan['actual_ordinary_receipt_sha256'] = sha(rr_raw)
    plan['earlier_failure_chain'] = {'earlier': copy.deepcopy(old_plan['earlier_failure_chain']), 'previous': copy.deepcopy(old_plan['predecessor_failure'])}
    plan['predecessor_failure'] = {
        'runtime_sha256': sha(previous_raw), 'attempt_nonce': old_plan['attempt_nonce'], 'replayed': False,
        'observed_boundary': 'actual HELLO/PROJECTED/COMMIT/DONE; namespace-owner Child exited SIGHUP before ACTIVE; original retirement and outer exact cleanup completed',
        'old_owner_original_resource_retirement_passed': True, 'outer_exact_cleanup_passed': True,
        'original_latest_status': copy.deepcopy(cause['original_latest_status']),
        'original_first_failure_null_does_not_prove_no_failure': True,
        'specific_relative_name_observed': 'ns/pid_for_children',
        'namespace_open_failure_implies_init_death': False,
        'guest_boot_first_cause_proved': False, 'sighup_sender_proved': False,
        'cause_loss_review_sha256': sha(cause_raw), 'old_failure_not_reclassified': True}
    plan['namespace_child_exit_source_manifest_sha256'] = sha(source_manifest)
    plan['namespace_child_exit_contract'] = {
        'scope': 'preserve exact parent Child ExitStatus before cleanup/cancel; sticky first cause',
        'optional_audit_field': 'namespace_owner_exit',
        'classification_uses_first_observed_stop_intent_and_worker_phase': True,
        'classification_does_not_prove_signal_sender_or_death_order': True,
        'original_exit_zero_behavior_preserved': True,
        'duplicate_observation_cannot_reclassify_or_overwrite_first_cause': True,
        'original_retirement_and_authority_gates_unchanged': True,
        'observation_does_not_qualify_ACTIVE_or_enrollment': True}
    plan['post_error_pidfd_observation_contract'] = {
        'original_snapshot_error_and_errno_preserved': True,
        'same_held_pidfd_zero_timeout_poll_only': True,
        'post_error_observation_is_later_evidence_not_cause_order': True,
        'namespace_retry_fallback_or_identity_grant': False}
    plan['main_budget_restoration_evidence'] = {
        'restoration': file_record(restore_path, restore_raw), 'post_exit_identity': file_record(post_path, post_raw),
        'original_Main_plan_object_unchanged': True, 'original_pids_max': '12288',
        'original_guard_passed_after_and_post_exit': True, 'main_code_deployed_or_restarted': False,
        'live_preparation_and_runtime_fences_still_required': True,
        'historical_blocked_reviews_not_rewritten': True}
    canonical = json.dumps(plan['spec'], ensure_ascii=False, separators=(',', ':')).encode()
    plan['canonical_spec_sha256'] = sha(canonical)
    plan['status'] = 'SOURCE_FROZEN_PREPARE_AND_RUNTIME_NOT_SUBMITTED'
    for key in ('main', 'base', 'presenter', 'tools_fixed_paths', 'tools_sha256', 'outer_limits',
                'runtime_max_seconds', 'controller_timeout_seconds', 'helper_uid', 'helper_gid',
                'mem_available_min_bytes', 'host_memory_full_avg10_max', 'disk_available_min_bytes',
                'data_images', 'control_socket', 'scope', 'init_protocol_abi', 'entry_abi'):
        assert plan[key] == old_plan[key], key
    for role in ('lmkd', 'init-barrier'):
        assert plan['artifacts'][role] == old_plan['artifacts'][role]
    assert plan['spec']['denial_socket'] == old_plan['spec']['denial_socket']
    assert all(plan[key] is False for key in ('production_ready', 'installed_owner_qualified', 'rc_property_reload_qualified', 'pressure_effect_qualified', 'app_qualified'))
    for key in ('memory_max_bytes', 'memory_high_bytes', 'memory_swap_max_bytes', 'cpu_quota_us',
                'cpu_period_us', 'tasks_max', 'entry_timeout_ms', 'bootstrap_timeout_ms', 'lmkd_uid', 'lmkd_gid'):
        assert relay[key] == old_plan['spec']['pressure_relay'][key]
    # Preserve actual Rust serde declaration order, including the artifact maps.
    rust = BASE / 'producer07-audit-freeze-02/source/runtime/droidloom-supervisor/src'
    def fields(path, name, relative):
        raw = path.read_bytes()
        assert expected_inputs[relative] == {'bytes': len(raw), 'sha256': sha(raw)}
        body = re.search(r'pub struct ' + name + r'\s*\{(.*?)^\}', raw.decode(), re.S | re.M)[1]
        return re.findall(r'^\s*pub\s+(\w+)\s*:', body, re.M)
    spec_fields = fields(rust / 'lib.rs', 'CellSpec', 'runtime/droidloom-supervisor/src/lib.rs')
    assert list(plan['spec']) == [key for key in spec_fields if key in plan['spec']]
    policy_path = rust / 'relay_lifecycle/policy.rs'
    policy_relative = 'runtime/droidloom-supervisor/src/relay_lifecycle/policy.rs'
    assert list(relay) == fields(policy_path, 'PressureRelaySpec', policy_relative)
    for name in ('broker', 'entry_supervisor', 'lmkd', 'init_barrier'):
        assert list(relay[name]) == fields(policy_path, 'RelayArtifact', policy_relative)

    replacements = [(OLD_KIND, KIND), (OLD_PREFIX, PREFIX),
                    ('owner14-normal-preparation01', 'owner15-normal-preparation01'),
                    ('owner14-real-normal01', 'owner15-real-normal01'),
                    ('actual producer14 cell', 'actual producer15 cell')]
    sources, source_rows, difference = {}, [], ''
    for name in SOURCE_NAMES:
        old = (OLD / 'source' / name).read_text()
        new = old
        for before, after in replacements: new = new.replace(before, after)
        reverse = new
        for before, after in reversed(replacements): reverse = reverse.replace(after, before)
        assert reverse == old, name
        if name in ('owned.py', 'pinned_support.py', 'qualify.py'): assert new == old
        ast.parse(new); compile(new, name, 'exec')
        raw = new.encode()
        sources[name] = {'bytes': len(raw), 'sha256': sha(raw), 'content': new}
        source_rows.append({'path': name, 'old_sha256': sha(old.encode()), 'new_sha256': sha(raw),
                            'new_bytes': len(raw), 'reverse_fixed_literals_exact': True, 'unchanged': new == old})
        difference += ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile='owner14/source/' + name, tofile='owner15/source/' + name))
    profile_guard = fixed_guard(sources, 'prepare.py', 'wrong fixed profile')
    path_guard = fixed_guard(sources, 'coordinator.py', 'this controller accepts only its fixed fresh unit/package/state')
    cases = [('new_profile', profile_guard, plan, True), ('new_paths', path_guard, plan, True),
             ('old_kind_rejected', profile_guard, {**plan, 'kind': OLD_KIND}, False),
             ('short_nonce_rejected', profile_guard, {**plan, 'attempt_nonce': '12' * 31}, False),
             ('old_scope_rejected', profile_guard, {**plan, 'scope': 'REAL_OWNER_ABI3_RETAINED_CAUSE_FIRST_ACTIVE_ORIGINAL_RETIREMENT'}, False)]
    cases += [('old_' + key + '_rejected', path_guard, {**plan, key: old_plan[key]}, False) for key in ('unit', 'package', 'state')]
    guard_results = []
    for name, code, candidate, expected in cases:
        accepted = eval(code, {'__builtins__': {}, 'len': len}, {'plan': candidate})
        assert accepted is expected, name
        guard_results.append({'case': name, 'accepted': accepted})
    plan_raw = pretty(plan)
    packet = json.dumps({'plan_utf8': plan_raw.decode(), 'sources': sources}, ensure_ascii=False, separators=(',', ':')).encode()
    prepare_template = (OLD / 'requests/prepare-template.py').read_text()
    prepare_stdin = prepare_template.replace('__PACKET_SHA256__', repr(sha(packet))).replace('__PACKET_BASE64__', repr(base64.b64encode(packet).decode()))
    ast.parse(prepare_stdin)
    request = json.loads((OLD / 'requests/prepare-request.json').read_bytes())
    request.update(stdin=prepare_stdin, idempotency_key='p4-owner15-normal01-prepare01-' + sha(prepare_stdin.encode())[:16])
    old_coordinator = (OLD / 'source/coordinator.py').read_bytes()
    assert sources['coordinator.py']['bytes'] == len(old_coordinator)
    runtime = (OLD / 'requests/runtime-stdin-template.py').read_text().replace(OLD_PREFIX, PREFIX)
    runtime = runtime.replace(sha(old_coordinator), sources['coordinator.py']['sha256'])
    ast.parse(runtime)
    assert '__ACTUAL_PREPARED_SHA256__' in runtime and PREFIX in runtime
    runtime_request = json.loads((OLD / 'requests/runtime-request-template.json').read_bytes())
    runtime_request.update(stdin=runtime, idempotency_key='p4-owner15-normal01-runtime01-__ACTUAL_PREPARED_SHA256_PREFIX16__')
    for path, new_request in [('prepare-request.json', request), ('runtime-request-template.json', runtime_request)]:
        old_request = json.loads((OLD / 'requests' / path).read_bytes())
        assert {k: v for k, v in new_request.items() if k not in ('stdin', 'idempotency_key')} == {k: v for k, v in old_request.items() if k not in ('stdin', 'idempotency_key')}
    constants = {node.targets[0].id: ast.literal_eval(node.value) for node in ast.parse(prepare_stdin).body
                 if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ('PACKET_SHA256', 'PACKET_BASE64')}
    decoded = base64.b64decode(constants['PACKET_BASE64'], validate=True)
    assert decoded == packet and constants['PACKET_SHA256'] == sha(decoded)
    decoded_packet = json.loads(decoded)
    assert decoded_packet['plan_utf8'].encode() == plan_raw and decoded_packet['sources'] == sources

    files = {}
    def put(name, raw):
        raw = raw.encode() if isinstance(raw, str) else raw
        raw.decode('utf-8')
        assert name not in files and not Path(name).is_absolute() and '..' not in Path(name).parts
        files[name] = raw
    put('plan.json', plan_raw); put('cell.json', canonical)
    for name, row in sources.items(): put('source/' + name, row['content'])
    put('source.diff', difference)
    put('plan.diff', ''.join(difflib.unified_diff(old_plan_raw.decode().splitlines(True), plan_raw.decode().splitlines(True), fromfile='owner14/plan.json', tofile='owner15/plan.json')))
    put('requests/prepare-template.py', prepare_template); put('requests/prepare-stdin.py', prepare_stdin)
    put('requests/prepare-request.json', pretty(request)); put('requests/runtime-stdin-template.py', runtime)
    put('requests/runtime-request-template.json', pretty(runtime_request))
    put('lineage/owner14-normal-manifest.json', old_manifest)
    put('lineage/producer15-source-manifest.json', source_manifest)
    put('lineage/producer15-controller-manifest.json', controller_manifest)
    put('evidence/actual-rust-compile.json', rb_raw); put('evidence/actual-rust-ordinary.json', rr_raw)
    put('evidence/actual-android-build.json', cb_raw); put('evidence/actual-cgroup-mount-mechanism03.json', mm_raw)
    put('evidence/predecessor-normal14-runtime-failed.json', previous_raw)
    put('evidence/predecessor-normal14-cause-loss-review.json', cause_raw)
    put('evidence/main-tasksmax-restore.stdout.log', restore_raw)
    put('evidence/main-post-exit-identity.stdout.log', post_raw)
    put('freeze_normal15.py', Path(__file__).read_bytes())
    source_review = {'schema': 1, 'scope': 'profile literal substitutions only; no runtime execution',
                     'sources': source_rows, 'fixed_guard_expression_checks': guard_results,
                     'unchanged_sources': ['owned.py', 'pinned_support.py', 'qualify.py'],
                     'no_runtime_module_imported_or_executed': True}
    put('source-profile-review.json', pretty(source_review))
    review = {
        'schema': 1, 'kind': 'owner15_normal01_actual_source_binding', 'prepare_submitted': False, 'runtime_submitted': False,
        'rust_compile': file_record(rb_path, rb_raw), 'rust_ordinary': file_record(rr_path, rr_raw),
        'actual_rust_tests_passed': rr['rust_tests_passed'], 'actual_IPC_passed': rr['ordinary_ipc_passed'],
        'actual_public_retirement_controls': targets, 'candidate_inventory_sha256': inventory,
        'inputs_before_after_match': 32, 'actual_overlays_match': 4, 'actual_run_ELFs_match_compile': 7,
        'ordinary_full_Owner_or_Android_qualification': False, 'resource_summary': resource_summary,
        'source_manifest_sha256': sha(source_manifest), 'controller_manifest_sha256': sha(controller_manifest),
        'unchanged_Android_build_sha256': sha(cb_raw), 'unchanged_mount_mechanism_sha256': sha(mm_raw),
        'main_restoration_sha256': sha(restore_raw), 'main_post_exit_identity_sha256': sha(post_raw),
        'Main_object_equals_original14': True, 'seven_process_identities_and_boot_retained': True,
        'original_Main_pids_max_12288_restored': True, 'Main_guard_never_relaxed': True,
        'fresh_live_Main_and_budget_checks_still_required': True,
        'owner14_failure_preserved': True, 'owner14_retirement_completed_not_boot_PASS': True,
        'Owner11_original_retirement_failure_and_producer13_ordinary_failure_preserved_in_plan_lineage': True,
        'historical_source15_cause_review_Main_blockage_field_is_not_current_admission': True,
        'new_attempt_nonce': attempt, 'namespace_owner_exit_is_optional_evidence_not_success': True,
        'synthetic_uid': 61287, 'subordinate_start': 21000000, 'subordinate_count': 100000,
        'live_UID_subid_absence_not_observed_by_this_binder': True,
        'Rust_field_order_verified_against_actual_unchanged_inputs': True,
        'canonical_spec_sha256': sha(canonical), 'published_plan_sha256': sha(plan_raw),
        'expected_prepared_serialized_plan_sha256': sha((json.dumps(plan, sort_keys=True, indent=2) + '\n').encode()),
        'prepare_packet_bytes': len(packet), 'prepare_packet_sha256': sha(packet),
        'prepare_stdin_bytes': len(prepare_stdin.encode()), 'prepare_stdin_sha256': sha(prepare_stdin.encode()),
        'prepare_request_bytes': len(files['requests/prepare-request.json']),
        'prepare_request_sha256': sha(files['requests/prepare-request.json']), 'idempotency_key': request['idempotency_key'],
        'prepare_template_unchanged': True, 'only_request_stdin_and_key_changed': True,
        'runtime_template_requires_external_actual_prepared_digest': True,
        'no_Hepta_device_Main_or_host_network_action_by_this_binder': True}
    put('ACTUAL-ADMISSION-REVIEW.json', pretty(review))
    put('README.md', '''# Owner15 NORMAL01 preparation candidate

This create-only plan binds the actual Producer15 matching compile and ordinary
receipts: 39 relay and 128 supervisor library tests, two public retirement tests,
7 IPC controls, worker context and entry ABI3. These are host results. A real
Owner15 generation, broker ACTIVE and original Stop retirement have not run.

Source15 preserves the exact namespace-owner Child ExitStatus before cleanup or
cancel, keeps the first recorded cause, and retains the existing exit-zero
behavior. Stop/worker state describes what was already observed; it cannot prove
the signal sender or the order of death. A failed lifecycle identity snapshot
retains its original error and adds only a later zero-time poll of the same held
pidfd. It does not retry namespace reads or grant identity after failure.

The six Python runtime sources keep their existing behavior. Only the fixed
profile/root/result labels change in actor, coordinator and prepare. owned.py,
pinned_support.py and qualify.py are exact predecessor bytes. Optional exit
evidence cannot substitute for typed init HELLO/PROJECTED/COMMIT/DONE, broker
ACTIVE, the original public Stop, exact process death, joined retirement, whole
domain removal and claim release. ABI3 DSO, LMKD r6, base86, original RC and
private presenter remain unchanged. RC/reinit work is excluded.

The actual Main TasksMax repair and a separate post-exit read both passed the
original guard with all seven retained process identities and boot unchanged.
The Main plan object is not rebased or relaxed: pids.max remains 12288. Historical
reviews that recorded the earlier 6144 blockage remain unchanged. Preparation
and runtime must still perform their original fresh Main and resource checks.

UID61287 and subordinate range21000000+100000 are proposed for this new attempt;
live absence is not claimed by a local binder. The original census and absent
unit/path gates remain. Outer5GiB/inner4GiB, zero-swap execution contract, CPU1,
all deadlines, native PSI defaults, one-shot claims, private dbus/sway/network,
Main fences and exact cleanup are unchanged. Actual host compile/ordinary
receipts observed zero swap but had swap.max=max; they do not prove a hard
zero-swap limit or whole-invocation resource qualification.

Owner14 remains failed before ACTIVE. Its original retirement and outer exact
cleanup did complete. Its null first_failure was a loss of cause, not proof of
fault-free boot. The observed ns/pid_for_children ENOENT and SIGHUP do not prove
the guest boot cause or signal sender. Owner11 and Producer13 failures remain
in the inherited evidence chain. No old attempt is retried or reclassified.

Only local JSON/AST/byte binding and fixed-guard-expression validation occurs in
this freeze. Root owns device dispatch. The runtime is only an unbound template
until the unique prepare returns its actual externally verified receipt digest.
No installed Main candidate, host network or account/subid table is modified.
''')
    rows = [{'path': name, 'bytes': len(raw), 'sha256': sha(raw)} for name, raw in sorted(files.items())]
    put('manifest.json', pretty({'schema': 1, 'kind': 'owner15_normal01_frozen', 'prepare_submitted': False,
                                'runtime_executed': False, 'files': rows}))
    OUT.mkdir()
    for name, raw in files.items():
        path = OUT / name; path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream: stream.write(raw)
    print(json.dumps({'root': str(OUT), 'payload_files': len(rows), 'manifest_sha256': sha(files['manifest.json']),
                      'source_diff_bytes': len(files['source.diff']), 'source_diff_sha256': sha(files['source.diff']),
                      'plan_diff_bytes': len(files['plan.diff']), 'plan_diff_sha256': sha(files['plan.diff']),
                      'prepare_request_bytes': review['prepare_request_bytes'], 'prepare_request_sha256': review['prepare_request_sha256'],
                      'prepare_stdin_bytes': review['prepare_stdin_bytes'], 'prepare_stdin_sha256': review['prepare_stdin_sha256'],
                      'key': request['idempotency_key'], 'attempt_nonce': attempt, 'canonical_spec_sha256': sha(canonical)}, indent=2))


if __name__ == '__main__':
    main()
