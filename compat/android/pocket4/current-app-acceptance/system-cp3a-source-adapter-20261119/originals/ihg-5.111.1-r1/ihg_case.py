"""Original IHG public London case, newly bound workers and coordinator.

Only actual current helper install/build/identity receipts can construct this
case. Original two clicks, one London input, 39 distinct nonces, restoration,
phase counts and exact owned leaf cleanup remain explicit. No bookings/login.
"""
import copy
import json
import os
from pathlib import Path
import signal
import time
import types


def remember(result, phase, error):
    row = {'phase': phase, 'type': type(error).__name__, 'message': str(error),
           'details': getattr(error, 'details', None)}
    if result['error'] is None:
        result['error'] = row
    else:
        result['secondary_errors'].append(row)
    result['ok'] = False


def phase_counts(common, flow, phase, result, plans):
    if phase == 'launch':
        common.need(flow.policy.counts == {'target_uid': 2, 'target_path': 2, 'helper_uid': 2,
            'helper_path': 2, 'resolve': 1, 'stacks': 2} and flow.command_index == 12
            and flow.launch_claimed is True, 'EXACT_ORIGINAL_IHG_LAUNCH_COUNTS')
    if phase == 'inspect' and result['error'] is None:
        count = result.get('search_readiness_count')
        common.need(type(count) is int and 3 <= count <= 8 and result.get('search_readiness_qualified') is True
            and len(result['search_readiness_observations']) == count, 'EXACT_ORIGINAL_READINESS_COUNT')
        used = {nonce for plan in plans['readiness'][:count] for nonce in plan['nonces'].values()}
        used |= {nonce for key in ('search', 'destination', 'input', 'post') for nonce in plans[key]['nonces'].values()}
        common.need(flow.policy.counts == {'target_uid': 2, 'target_path': 2, 'helper_uid': 10 + 2 * count,
            'helper_path': 10 + 2 * count, 'stacks': 8 + 2 * count, 'instrument': 15 + 3 * count,
            'foreground': 12 + 3 * count, 'click': 2, 'set_text': 1}
            and flow.command_index == 47 + 9 * count and flow.policy.used_nonces == used
            and flow.action_attempted is True and result.get('destination_click_and_observation_completed') is True
            and result.get('explicit_search_then_destination_completed') is True
            and result.get('public_london_input_and_readback_completed') is True,
            'EXACT_ORIGINAL_TWO_CLICKS_ONE_LONDON_AND_RESTORATION_COUNTS')


def worker(common, scope_ref, phase):
    common.need(os.getuid() == os.geteuid() == 0 and phase in ('launch', 'inspect', 'cleanup'),
                'EXACT_ROOT_IHG_PHASE_WORKER_REQUIRED')
    scope = common.parse(common.read_ref(scope_ref)); active_ref = scope['phase_plan']
    active = common.parse(common.read_ref(active_ref))
    def source(name):
        return common.packet_module(scope, name)
    runtime = source('app_runtime.py'); plan_module = source('app_plan.py')
    scope_module, modules = common.support(scope['support_manifest'])
    baseline = modules['business_baseline.py'].BusinessBaseline(active['baseline'], active['qualification'])
    plan_module.validate(common, active, baseline, scope)
    common.need(active['kind'] == 'ihg_london' and len(active['flows']) == 1, 'ONE_NEW_IHG_FLOW_ONLY')
    phase_ref = runtime.create_phase(common, active_ref, active, phase)
    phase_lease = common.parse(common.read_ref(phase_ref)); deadline = phase_lease['deadline_monotonic_ns'] / 1000000000
    root = common.private_dir(scope['flow_root']); step = root / 'steps' / (phase + '-01')
    plans = copy.deepcopy(active['input_plans'])
    qa = source('qa_contract.py'); policy = source('ihg_policy.py'); adapter = source('ihg_session.py')
    public = source('ihg_public.py'); assessment = source('ihg_assessment.py'); original_artifacts = source('ihg_artifacts.py')
    guard_module = source('ihg_guard.py'); flow_module = source('app_flow.py')
    build = common.parse(common.read_ref(active['helper_build'])); installed = common.parse(common.read_ref(active['helper_install']))
    helper_uid = active['helper_profile']['uid']; expected_helper = installed['installed_after_state']
    target_identity = common.parse(common.read_ref(active['target_identity']))
    target_expected = {'target': target_identity['metadata'], 'artifacts': [
        {'path': row['guest_path'], 'sha256': row['sha256'], 'held_file': row['stat_file']}
        for row in target_identity['artifacts']]}
    result = {'schema': 'pocket4-final-ihg-phase-result-v1', 'ok': False, 'error': None,
        'secondary_errors': [], 'phase': phase, 'scope': scope_ref, 'active_plan': active_ref,
        'phase_lease': phase_ref, 'package': qa.PACKAGE, 'uid': qa.UID, 'helper_package': qa.SELF,
        'helper_uid': helper_uid, 'actual_install': active['helper_install'], 'actual_resolution': active['target_identity'],
        'build': active['helper_build'], 'automatic_retry': False, 'old_Flow_instantiated': False,
        'maximum_click_actions': 2, 'maximum_no_action_search_readiness_sequences': 8, 'maximum_text_actions': 1,
        'screenshots': 0, 'audio_actions': 0, 'permission_grants': 0, 'settings_writes': 0,
        'raw_UI_tree_private_only': True, 'whole_app_business_accepted': False,
        'business_success_verified': False, 'host_foreground_display_independently_verified': False,
        'required_helper_display': 0, 'Binder_UID_cleanup_verified': False}
    flow = artifacts = session = flow_lock = action_lock = None
    current = 'phase_admission'; started = time.monotonic()
    try:
        common.need(not os.path.lexists(step), 'FRESH_ORIGINAL_IHG_PHASE_STEP_REQUIRED')
        flow_lock = common.locked(root / 'flow.lock', wait_seconds=5); flow_lock.__enter__()
        result['Main_before_lock'] = baseline.guard()
        if phase != 'cleanup':
            action_lock = common.locked(flow_module.ACTION_LOCK, wait_seconds=5); action_lock.__enter__()
            baseline.guard()
        else:
            result['action_lock_owner'] = 'original exact cleanup section'
        current = 'held_Main_context'
        flow = flow_module.Flow(common, scope_ref, phase, phase + '-01', deadline, guard_module,
            lambda f: policy.Policy(phase, qa, original_artifacts.RESOLVE, plans, f.step,
                lambda path, maximum=1048576: common.regular(path, maximum)[0], f.selected_task),
            private_context={'phase_lease': phase_ref})
        artifact_context = types.SimpleNamespace(android=flow.android, target=flow.view.target,
            deadline=deadline, artifacts=None)
        artifacts = original_artifacts.ArtifactSet(artifact_context, target_expected, original_artifacts)
        current = 'target_before'; result['target_before'] = artifacts.before()
        flow.commercial_artifacts = artifacts
        session = (public.make_session(adapter, flow, flow.recorder, qa, build, helper_uid,
            plans['search'], plans['destination'], plans['input'], plans['post'], plans['readiness'])
            if phase == 'inspect' else adapter.Session(flow, flow.recorder, qa, build, helper_uid))
        current = 'helper_before'; result['helper_before'] = session.installed()
        common.need(result['helper_before'] == expected_helper, 'ACTUAL_INSTALLED_NEW_HELPER_CHANGED')
        if phase == 'launch':
            current = 'current_component'
            raw = flow.android(original_artifacts.RESOLVE, 15)
            result['current_launcher'] = original_artifacts.component(raw)
            common.need(result['current_launcher']['component'] == scope['component'], 'CURRENT_IHG_LAUNCHER_CHANGED')
            current = 'one_native_launch'; result['launch'] = flow.launch_locked()
            common.need(result['launch']['native_launch_acknowledged'] is True and result['launch']['cleanup_allowed'] is True,
                        'EXACT_NEW_IHG_NATIVE_TASK_REQUIRED')
            result['owned_task'] = flow.selected_task()
        elif phase == 'inspect':
            current = 'explicit_public_search_destination_london'
            public.run_sequences(qa, session, expected_helper, plans['search'], plans['destination'], plans['input'],
                plans['post'], plans['readiness'], result,
                lambda sequence, plan: assessment.assessment_summary(common, qa, helper_uid, step, sequence, plan),
                lambda label, error: remember(result, label, error))
        else:
            current = 'exact_owned_cleanup'; selected = flow.selected_task(); result['owned_task'] = selected
            completed = flow.cleanup(); result['cleanup'] = completed
            absent = completed.get('new_task_already_absent') is True and completed.get('removal_attempted') is False
            removed = completed.get('new_leaf_removed_and_verified') is True and completed.get('other_tasks_preserved') is True
            common.need(absent or removed, 'EXACT_OWNED_IHG_CLEANUP_COMPLETION_REQUIRED')
            after = completed['task_ids_after']
            common.need(after == selected['prelaunch_task_ids'] and selected['task'] not in after,
                        'ORIGINAL_PREEXISTING_TASK_SET_PRESERVED')
            result['task_ids_after'] = after; result['owned_task_absent'] = True
        current = 'helper_after'; result['helper_after'] = session.installed()
        common.need(result['helper_after'] == result['helper_before'], 'HELPER_CHANGED_DURING_PHASE')
        current = 'target_after'; result['target_after'] = artifacts.after()
        common.need(result['target_after'] == result['target_before'], 'TARGET_APKS_CHANGED_DURING_PHASE')
        phase_counts(common, flow, phase, result, plans)
        result['ok'] = result['error'] is None and not result['secondary_errors']
    except BaseException as error:
        if session is not None and hasattr(session, 'sequence_observation'):
            result['failed_sequence_observation'] = session.sequence_observation
        remember(result, current, error)
    finally:
        if artifacts is not None:
            try:
                if len(artifacts.records) == 1 and 'target_after' not in result:
                    result['failed_scope_files_revalidated'] = artifacts.revalidate_files()
            except BaseException as error:
                remember(result, 'failed_scope_files_revalidation', error)
            if flow is not None:
                flow.commercial_artifacts = None
            try:
                result['target_FD_cleanup'] = artifacts.close()
            except BaseException as error:
                remember(result, 'target_FD_cleanup', error)
        if flow is not None:
            result['command_counts'] = dict(flow.policy.counts); result['durable_command_count'] = flow.command_index
            try:
                flow.artifacts.revalidate(); flow.guard(attempted=flow.action_attempted)
                result['final_Main_guard_passed'] = True
            except BaseException as error:
                remember(result, 'final_Main_guard', error)
            try:
                flow.close(); result['held_binding_released'] = True
            except BaseException as error:
                remember(result, 'held_binding_release', error)
        try:
            result['Main_after'] = baseline.guard()
            common.need(result['Main_after'] == result.get('Main_before_lock'), 'PHASE_MAIN_CHANGED')
            plan_module.validate(common, active, baseline, scope)
            result['source_and_artifact_unchanged'] = True
        except BaseException as error:
            remember(result, 'independent_final_Main_and_sources', error)
        for lock, label in ((action_lock, 'action_lock'), (flow_lock, 'flow_lock')):
            if lock is not None:
                try:
                    lock.__exit__(None, None, None); result[label + '_released'] = True
                except BaseException as error:
                    remember(result, label + '_release', error)
        result['action_attempted'] = bool(flow is not None and flow.action_attempted)
        result['outcome_unknown'] = bool(result['action_attempted'] and (phase == 'inspect' or not result['ok']))
        admitted = set() if session is None else getattr(session, 'action_requests_admitted', set())
        result['click_requests_admitted'] = len(admitted & {'search', 'destination'})
        result['text_requests_admitted'] = int('input' in admitted)
        result['seconds'] = time.monotonic() - started
        common.need(step.is_dir(), 'PHASE_SETUP_FAILURE_HAS_NO_REUSABLE_STEP')
        ref = common.write_new(step / 'result.json', result)
    return ref, result


def execute(common, base_ref):
    common.need(os.getuid() == os.geteuid() == 0, 'ROOT_NEW_IHG_COORDINATOR_REQUIRED')
    base = common.parse(common.read_ref(base_ref)); scope_module, modules = common.support(base['support_manifest'])
    baseline = modules['business_baseline.py'].BusinessBaseline(base['baseline'], base['qualification'])
    prepared = common.parse(common.read_ref(base['source_preparation']))
    def source(name):
        rows = [r for r in prepared['files'] if Path(r['path']).name == name]
        common.need(len(rows) == 1, 'ONE_NEW_IHG_COORDINATOR_SOURCE:' + name)
        return common.module(rows[0], 'ihg_coordinator_' + Path(name).stem)
    plans = source('app_plan.py'); plans.validate(common, base, baseline)
    common.need(base['kind'] == 'ihg_london', 'ORIGINAL_IHG_LONDON_CASE_ONLY')
    runtime = source('app_runtime.py'); root = common.private_dir(base['case_root'])
    common.write_new(root / 'execution-attempt.json', {'base_plan': base_ref, 'automatic_retry': False,
        'operator': runtime.process(common, os.getpid()), 'whole_app_business_accepted': False})
    lease_ref = runtime.create_lease(common, base_ref, base)
    active_ref, scopes = plans.activate(common, base_ref, lease_ref)
    common.need(len(scopes) == 1, 'ONE_NEW_IHG_TASK_SCOPE')
    scope_ref = scopes[0]; scope = common.parse(common.read_ref(scope_ref)); active = common.parse(common.read_ref(active_ref))
    flow_root = common.private_dir(scope['flow_root']); evidence = common.private_dir(root / 'workers', create=True)
    packet = common.parse(common.read_ref(active['task_source_manifest']))
    entry_ref = next(r for r in packet['files'] if Path(r['path']).name == 'app_entry.py')
    witness = common.EvidenceWitness([base_ref, active_ref, *scopes])
    owner = types.SimpleNamespace(c=common, deadline=common.parse(common.read_ref(lease_ref))['initial_deadline_monotonic_ns'] / 1000000000)
    commands = runtime.PhaseCommands(modules['business_commands.py'], owner)
    result = {'schema': 'pocket4-final-ihg-public-london-result-v1', 'ok': False, 'error': None,
        'secondary_errors': [], 'base_plan': base_ref, 'active_plan': active_ref, 'scope': scope_ref,
        'package': 'com.ihg.apps.android', 'uid': 10137, 'helper_package': active['helper_profile']['package'],
        'helper_uid': active['helper_profile']['uid'], 'actual_install': active['helper_install'],
        'actual_resolution': active['target_identity'], 'maximum_native_launches': 1,
        'launch_worker_requested': False, 'inspect_worker_requested': False, 'cleanup_requested': False,
        'maximum_click_actions': 2, 'maximum_text_actions': 1, 'fixed_public_input': 'London',
        'screenshots': 0, 'audio_actions': 0, 'package_mutations': 0, 'permission_grants': 0, 'settings_writes': 0,
        'automatic_retry': False, 'business_success_verified': False, 'whole_app_business_accepted': False,
        'Binder_UID_cleanup_verified': False, 'raw_UI_tree_private_only': True, 'canonical_45_gates_unchanged': True}
    def guard(*, action_attempted=False):
        witness.verify(); runtime.validate_lease(common, lease_ref, base_ref, 'ihg_london')
        common.need(not (flow_root / 'hold.json').exists(), 'UNKNOWN_IHG_FLOW_REQUIRES_RECONCILIATION_NO_AUTOMATIC_CLEANUP')
        return baseline.guard(action_attempted=action_attempted)
    def run_phase(phase, timeout):
        common.read_ref(entry_ref)
        argv = ['/usr/bin/python3', '-I', '-B', entry_ref['path'],
            '--preparation', base['source_preparation']['path'], '--expect-preparation-sha256', base['source_preparation']['sha256'],
            'ihg-worker', '--scope', scope_ref['path'], '--expect-scope-sha256', scope_ref['sha256'], '--phase', phase]
        completed = actual = None; durable = False
        try:
            completed = commands.run_recorded(phase, argv, timeout, evidence, guard,
                protected_pids=baseline.protected_pids, mutation=True, check=False, output_bound=1024 * 1024)
            common.need(completed.host_tree_retired and completed.recorder_errors == [] and not completed.host_timed_out,
                        'IHG_WORKER_NOT_FULLY_RETIRED_NO_AUTOMATIC_CLEANUP')
            actual_ref = common.regular(flow_root / 'steps' / (phase + '-01') / 'result.json', contents=False)
            actual = common.parse(common.read_ref(actual_ref)); summary = common.parse(completed.stdout)
            common.need(summary == {'result': actual_ref, 'ok': actual['ok'], 'whole_app_business_accepted': False}
                and actual['schema'] == 'pocket4-final-ihg-phase-result-v1' and actual['scope'] == scope_ref
                and actual['active_plan'] == active_ref and actual['phase'] == phase
                and completed.returncode == (0 if actual['ok'] else 2), 'ACTUAL_DURABLE_IHG_WORKER_RESULT_CHAIN')
            durable = True; result[phase + '_result'] = actual_ref
            common.need(actual['ok'] is True and actual['error'] is None and actual['secondary_errors'] == []
                and actual.get('held_binding_released') is True and actual.get('source_and_artifact_unchanged') is True,
                'ORIGINAL_IHG_PHASE_DID_NOT_QUALIFY')
            return actual
        except BaseException as error:
            if completed is not None:
                error.command_observation = completed.command_observation
            error.worker_outcome_unknown = (not durable or actual.get('held_binding_released') is not True
                or actual.get('source_and_artifact_unchanged') is not True)
            raise
    unretired = False
    try:
        result['Main_before'] = guard()
        result['launch_worker_requested'] = True; launch = run_phase('launch', 190)
        result['owned_task'] = launch['owned_task']
        result['inspect_worker_requested'] = True; inspection = run_phase('inspect', 190)
        for key in ('search_assessments', 'public_search_entry', 'assessments', 'post_assessments',
                    'public_destination_observation', 'input_assessments', 'public_destination_input_observation'):
            result[key] = inspection[key]
        result['search_restoration'] = inspection['search_sequence']['accessibility_restoration']
        result['restoration'] = inspection['sequence']['accessibility_restoration']
        result['post_restoration'] = inspection['post_sequence']['accessibility_restoration']
        result['input_restoration'] = inspection['input_sequence']['accessibility_restoration']
        result['foreground'] = inspection['post_sequence']['foreground_after']
        result['explicit_search_then_destination_completed'] = True
        result['destination_click_and_observation_completed'] = True
        result['public_london_input_and_readback_completed'] = True
        result['business_outcome_unknown'] = True
        result['ok'] = True
    except BaseException as error:
        observation = getattr(error, 'command_observation', None)
        unretired = (getattr(error, 'worker_outcome_unknown', False) or
                     observation is not None and observation.get('host_retirement_proved') is not True)
        remember(result, 'coordinator', error)
    finally:
        if result['launch_worker_requested']:
            try:
                common.need(not unretired and not (flow_root / 'hold.json').exists(),
                            'UNKNOWN_OR_UNRETIRED_FLOW_RETAINED_NO_TASK_REMOVAL')
                if os.path.lexists(flow_root / 'launch-scope.json'):
                    temporary = types.SimpleNamespace(root=flow_root, scope=scope, scope_ref=scope_ref,
                        baseline=baseline, commands=modules['business_commands.py'])
                    claim, claim_ref = scope_module.load_owned_task(temporary)
                    result['owned_scope'] = claim_ref; result['owned_task'] = claim
                    result['cleanup_requested'] = True; clean = run_phase('cleanup', 130)
                    result['owned_task_absent_after_cleanup'] = clean['owned_task_absent'] is True
                    result['task_ids_after'] = clean['task_ids_after']
                else:
                    result['cleanup_not_authorized_without_exact_owned_scope'] = True
                    result['possible_native_launch_outcome_requires_reconciliation'] = os.path.lexists(flow_root / 'launch-attempted.json')
            except BaseException as error:
                remember(result, 'original_exact_owned_task_retirement', error)
        if result['ok'] and result.get('owned_task_absent_after_cleanup') is not True:
            remember(result, 'cleanup_completion', RuntimeError('ACTUAL_OWNED_CLEANUP_MISSING'))
        result['retained_phase_results'] = {}
        for phase in ('launch', 'inspect', 'cleanup'):
            path = flow_root / 'steps' / (phase + '-01') / 'result.json'
            if path.exists():
                result['retained_phase_results'][phase] = common.regular(path, contents=False)
        try:
            result['Main_after'] = baseline.guard()
            common.need(result['Main_after'] == result.get('Main_before'), 'COORDINATOR_MAIN_CHANGED')
            plans.validate(common, active, baseline, scope); witness.verify()
            result['source_and_artifact_unchanged'] = True
        except BaseException as error:
            remember(result, 'final_Main_and_sources', error)
        try:
            witness.close(); result['evidence_FDs_closed'] = True
        except BaseException as error:
            remember(result, 'evidence_FD_close', error)
        result['whole_app_business_accepted'] = False
        ref = common.write_new(root / 'result.json', result)
    return ref, result
