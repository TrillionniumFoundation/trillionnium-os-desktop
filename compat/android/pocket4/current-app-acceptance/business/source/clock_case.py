"""Execute only the original timer15 core on supplied actual new-Main evidence.

Nothing here is called by source publication or host controls. Whole-App,
expiry, audio, desktop-popup and scheduler-cancellation gates remain separate.
"""
from datetime import datetime, timezone
import os
from pathlib import Path
import signal
import time
import types


class Cancelled(BaseException):
    pass


def execute(common, base_ref):
    common.need(os.getuid() == os.geteuid() == 0, 'ROOT_NEW_CLOCK_CASE_REQUIRED')
    base = common.parse(common.read_ref(base_ref)); scope, modules = common.support(base['support_manifest'])
    baseline = modules['business_baseline.py'].BusinessBaseline(base['baseline'], base['qualification'])
    prepared = common.parse(common.read_ref(base['source_preparation']))
    def source(name):
        rows = [r for r in prepared['files'] if Path(r['path']).name == name]
        common.need(len(rows) == 1, 'ONE_REVIEWED_NEW_CASE_SOURCE:' + name)
        return common.module(rows[0], 'clock_case_' + Path(name).stem)
    plan_module = source('app_plan.py'); plan_module.validate(common, base, baseline)
    common.need(base['kind'] == 'clock_timer', 'EXACT_ORIGINAL_TIMER15_CASE_ONLY')
    runtime = source('app_runtime.py'); protection = source('clock_protection.py')
    preservation = source('clock_preservation.py'); timers = source('timer_flow.py')
    selectors = source('clock_selectors.py'); continuation = source('clock_continuation.py')
    trial_module = source('clock_trial.py'); lock_module = source('app_action_lock.py')
    root = common.private_dir(base['case_root'])
    common.write_new(root / 'execution-attempt.json', {'base_plan': base_ref, 'operator': runtime.process(common, os.getpid()),
        'automatic_retry': False, 'original_case': 'DeskClock timer15 core', 'whole_app_business_accepted': False})
    result = {'schema': 'pocket4-final-clock-timer-core-result-v1', 'state': 'FAILED', 'ok': False,
        'error': None, 'secondary_errors': [], 'case_business_success_verified': False,
        'whole_app_business_accepted': False, 'canonical_45_gates_unchanged': True,
        'base_plan': base_ref, 'framework_epoch_sha256': base['framework_epoch_sha256'],
        'phases': {}, 'alarm_write_actions': 0, 'global_volume_or_ringtone_actions': 0,
        'notification_permission_actions': 0, 'timer_expiry_qualification': False,
        'scheduler_cancellation_verified': False, 'scheduler_cancellation_requires_independent_saved_dump_review': True,
        'lease_seconds': 360, 'business_seconds': 350, 'cleanup_budget_seconds': 35, 'timer_duration_ms': 900000,
        'automatic_retry': False, 'Binder_UID_cleanup_verified': False,
        'started_utc': datetime.now(timezone.utc).isoformat()}
    original_handlers = {}; signals = []; retiring = False
    def cancelled(signum, _frame):
        nonlocal retiring
        signals.append(signum)
        if not retiring:
            retiring = True
            raise Cancelled('CASE_CANCELLED_NO_REPLAY')
    for signum in (signal.SIGTERM, signal.SIGINT):
        original_handlers[signum] = signal.signal(signum, cancelled)
    lease_ref = active_ref = phase_ref = None
    action_lock = session = trial = flow = witness = None
    core_completed = False; current = 'initial_main_and_lease'; read_phase = [None]
    def remember(label, error):
        row = {'phase': label, 'type': type(error).__name__, 'message': str(error),
               'details': getattr(error, 'details', None)}
        if result['error'] is None:
            result['error'] = row
        else:
            result['secondary_errors'].append(row)
    def source_guard():
        common.read_ref(base_ref); witness.verify()
        if read_phase[0] is None:
            runtime.validate_lease(common, lease_ref, base_ref, 'clock_timer')
        else:
            runtime.validate_phase(common, read_phase[0], active_ref, active)
        action_lock.verify()
    try:
        result['Main_before'] = baseline.guard()
        lease_ref = runtime.create_lease(common, base_ref, base)
        lease = common.parse(common.read_ref(lease_ref))
        witness = common.EvidenceWitness([base_ref, base['target_identity'], base['helper_identity']])
        current = 'original_whole_case_action_lock'
        action_lock = lock_module.Owner(common, runtime, root, lock_module.ACTION_LOCK)
        lock_module.validate(common, runtime, action_lock.ref)
        current = 'actual_protected_empty_preimage'
        session = protection.Session(common, base, preservation, root / 'protection',
            lease['initial_deadline_monotonic_ns'] / 1000000000, source_guard, runtime.PhaseCommands)
        before = session.snapshot('before')
        result['protected_before'] = common.regular(session.journal_dir / 'before.json', contents=False)
        result['identity_before'] = before['identity']; result['alarms_before'] = before['alarm_state']
        result['templates_sha_before'] = before['alarm_content_sha256']
        active_ref, scopes = plan_module.activate(common, base_ref, lease_ref, result['protected_before'], action_lock.ref)
        active = common.parse(common.read_ref(active_ref))
        phase_ref = runtime.create_phase(common, active_ref, active, 'business')
        read_phase[0] = phase_ref
        trial = trial_module.Trial(common, active_ref, active, scopes, session, phase_ref, action_lock)
        model = types.SimpleNamespace(read=lambda current_session: current_session.timer_read(),
            empty=preservation.empty, owned=preservation.owned, UNUSED=preservation.UNUSED)
        def make_continuation(t, package):
            value = continuation.TypedContinuation(t, package, t.backend, lambda value: None)
            t.continuation = value
            return value
        flow = timers.TimerFlow(trial, selectors, model, result, root, make_continuation)
        # The original 350 s business budget cannot restart after protection
        # work. The outer original 360 s lease remains independently enforced.
        flow.deadline = lease['started_monotonic_ns'] / 1000000000 + 350
        result['active_plan'] = active_ref; result['scopes'] = scopes
        current = 'original_timer_core'
        flow.run(); core_completed = True
    except BaseException as error:
        remember(current, error)
    finally:
        retiring = True
        if flow is not None and trial is not None and session is not None:
            try:
                trigger = common.write_new(root / 'cleanup-trigger.json', {'active_plan': active_ref,
                    'core_completed': core_completed, 'original_failure': result['error'],
                    'pending_input': flow.c.pending, 'pending_timer_effect': flow.effect_pending,
                    'pending_close': flow.close_pending, 'automatic_retry': False}, 0o400)
                cleanup_ref = runtime.create_phase(common, active_ref, active, 'final_cleanup', cleanup_trigger=trigger)
                cleanup = common.parse(common.read_ref(cleanup_ref)); read_phase[0] = cleanup_ref
                cleanup_until = cleanup['deadline_monotonic_ns'] / 1000000000
                trial.begin_final_cleanup(cleanup_ref)
                if not core_completed:
                    try:
                        flow.cleanup(cleanup_until)
                    except BaseException as error:
                        remember('original_failure_cleanup', error)
                common.need(time.monotonic() < cleanup_until, 'ORIGINAL_FINAL_CLEANUP_WINDOW_EXPIRED')
                if flow.c.pending is None and flow.effect_pending is None and flow.close_pending is None:
                    flow.close()
                else:
                    result['final_actions_blocked_by_unknown'] = {'input': flow.c.pending,
                        'timer_effect': flow.effect_pending, 'close': flow.close_pending, 'read_only': True}
                result['identity_after'] = session.identity()
                result['alarms_after'] = session.state()
                result['templates_sha_after'] = session.fingerprint()
                result['timer_final'] = session.timer_read()
                common.need(result['alarms_before'] == result['alarms_after'] and
                    result['templates_sha_before'] == result['templates_sha_after'], 'ORIGINAL_ALARMS_CHANGED')
                if flow.c.pending is None and flow.effect_pending is None and flow.close_pending is None:
                    after = session.snapshot('after')
                    result['protected_after'] = common.regular(session.journal_dir / 'after.json', contents=False)
                    common.need(preservation.preserved(before, after, include_preferences=False),
                                'PROTECTED_CLOCK_SOUND_PERMISSION_OR_DATA_CHANGED')
                    result['protected_business_and_sound_state_preserved'] = True
                session.artifacts.revalidate(); session.guard()
                if core_completed:
                    preservation.empty(result['timer_final'])
                    common.need(flow.owned == flow.closed and len(set(flow.owned)) == 2
                        and flow.c.pending is None and flow.effect_pending is None and flow.close_pending is None
                        and result['identity_before'] == result['identity_after']
                        and result.get('protected_business_and_sound_state_preserved') is True,
                        'ORIGINAL_TIMER_SUCCESS_REQUIRES_TWO_NORMAL_CLOSES_AND_PRESERVATION')
            except BaseException as error:
                remember('original_final_cleanup_and_readback', error)
        for obj, label in ((trial, 'trial_host_FDs'), (session, 'held_Main_FDs'), (action_lock, 'whole_case_action_lock'),
                           (witness, 'evidence_FDs')):
            if obj is not None:
                try:
                    if label == 'trial_host_FDs':
                        obj.release_flow()
                    else:
                        obj.close()
                    result[label + '_released'] = True
                except BaseException as error:
                    remember(label + '_release', error)
        try:
            result['Main_after'] = baseline.guard()
            common.need(result['Main_after'] == result.get('Main_before'), 'INDEPENDENT_FINAL_MAIN_CHANGED')
            plan_module.validate(common, base, baseline)
            result['source_and_identity_chain_unchanged'] = True
        except BaseException as error:
            remember('independent_final_Main_and_sources', error)
        # Dedicated app_entry process: freeze cancellation only after all
        # contexts and final guards. Keep this mask through result/entry exit.
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
        pending_signals = sorted(signal.sigpending() & {signal.SIGTERM, signal.SIGINT})
        if signals or pending_signals:
            remember('case_cancelled_before_terminal_commit', Cancelled('CASE_CANCELLED_BEFORE_TERMINAL_COMMIT'))
        result['cancellation_commit'] = {'observed_before_commit': list(signals),
            'pending_at_commit': pending_signals, 'decision_frozen_after_context_exit': True}
        result.update(ui_actions=flow.c.actions if flow else 0,
            pending_effect=flow.c.pending if flow else None, pending_timer_effect=flow.effect_pending if flow else None,
            close_pending=flow.close_pending if flow else None,
            owned_tasks=flow.owned if flow else [], closed_tasks=flow.closed if flow else [],
            owned_task_remaining=trial.owned if trial else None,
            owned_task_remove_calls=trial.removals if trial else 0, received_signals=signals,
            finished_utc=datetime.now(timezone.utc).isoformat())
        result['ok'] = bool(core_completed and result['error'] is None and not result['secondary_errors']
            and not signals and not pending_signals)
        result['case_business_success_verified'] = result['ok']
        result['state'] = 'ORIGINAL_TIMER_CORE_VERIFIED_CLEAN' if result['ok'] else 'FAILED_OR_UNKNOWN_RETAINED'
        result['whole_app_business_accepted'] = False
        result_ref = common.write_new(root / 'result.json', result)
    return result_ref, result
