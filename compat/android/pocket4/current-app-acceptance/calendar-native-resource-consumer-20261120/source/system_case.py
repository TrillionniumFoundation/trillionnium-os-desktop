"""Original reminder22 natural-delivery / exact UI-delete case on a fresh Main.

The prior reminder source was prepared, not executed. This coordinator has no
inherited runtime or whole-app credit. It retains the original finite work,
cleanup, resource, task, account, data, notification and no-replay predicates.
"""
import copy
from datetime import datetime, timezone
import os
from pathlib import Path
import signal
import time


class CaseInterrupted(BaseException):
    pass


def stamp():
    return datetime.now(timezone.utc).isoformat()


def calendar(s, f, result):
    m=s.components; p=m['system_profiles.py']; doc=m['calendar_identity.py']
    result['native_actions_before']=doc.identity(s,p.NATIVE_HELPER['package'],
        p.NATIVE_HELPER['apks'][0]['sha256'],10125,2)
    f.setup()
    f.diag_chain.start(f.before_diag)
    f.diag_chain.checkpoint('after-initial-launch',force=True)
    m['calendar_driver.py'].run(f,s.model)


def calendar_final(s, f, result):
    c=s.c; m=s.components; p=m['system_profiles.py']; doc=m['calendar_identity.py']
    f.cleanup_deadline=s.deadline
    if f.sampler is not None:
        try:
            f.arm_cleanup_remaining()
            f.sampler.phase_changed('before-final-normal-close')
            result['runtime_evidence']=f.sampler.stop()
            result['runtime_evidence_review_required']=True
        except BaseException as error:
            result['runtime_stop_error']=type(error).__name__+': '+str(error)
        finally:
            f.sampler.close()
    try:
        f.arm_cleanup_remaining()
        if f.diag_chain.first is not None:
            f.diag_chain.checkpoint('before-cleanup',force=True)
    except BaseException as error:
        result['diagnostic_checkpoint_error']=type(error).__name__+': '+str(error)
    result['cleanup']=f.cleanup()
    f.arm_cleanup_remaining()
    result['calendar_after']=f.calendar_identity()
    c.need(result['calendar_after']==result['calendar_before'],'ORIGINAL_CALENDAR_IDENTITY_CHANGED')
    result['provider_after']=doc.identity(s,p.CALENDAR_PROVIDER['package'],
        p.CALENDAR_PROVIDER['apks'][0]['sha256'],10017,37)
    c.need(result['provider_after']==result['provider_before'],'ORIGINAL_PROVIDER_IDENTITY_CHANGED')
    result['native_actions_after']=doc.identity(s,p.NATIVE_HELPER['package'],
        p.NATIVE_HELPER['apks'][0]['sha256'],10125,2)
    c.need(result['native_actions_after']==result['native_actions_before'],'ORIGINAL_NATIVE_HELPER_IDENTITY_CHANGED')
    f.arm_cleanup_remaining()
    result['calendar_uid_census_after']=m['calendar_audit.py'].uid_census(s,f.record,'runtime-uid-after')
    c.need(result['calendar_uid_census_after']['same_uid_packages']==
        result['calendar_uid_census_before']['same_uid_packages'],'CALENDAR_UID_MEMBERSHIP_CHANGED')
    result['system_timezone_after']=s.android(['/system/bin/getprop','persist.sys.timezone'],8).decode().strip()
    c.need(result['system_timezone_after']==result['system_timezone_before'],'DEVICE_TIMEZONE_CHANGED')
    result['final_counts']=f.counts('final')
    c.need(not any(result['final_counts'].values()),'ORIGINAL_PROVIDER_BASELINE_NOT_RESTORED')
    result['notifications_after']=f.nms.read('final')
    c.need(result['notifications_after']['active_calendar_count']==0,'CALENDAR_NOTIFICATION_REMAINS')
    _,tasks=f.ui.check_tasks('final')
    result['task_set_restored']=not f.ui.owned and tasks==f.ui.baseline
    c.need(result['task_set_restored'],'ORIGINAL_TASK_SET_NOT_RESTORED')
    f.arm_cleanup_remaining()
    after=f.diagnostics.diagnostics('after',10061)
    result['diagnostics']=f.diag_chain.finish(after)
    c.need(result['diagnostics']['clear'],'ORIGINAL_FRESH_CALENDAR_CRASH_OR_ANR_GATE')
    s.caller_status('calendar-reminder-final')
    result['guard_after']=s.guard()
    result['cleanup_budget_seconds_remaining']=max(0,f.cleanup_deadline-time.monotonic())


def execute(c, base_ref, components):
    c.need(os.getuid() == os.geteuid() == 0, 'ROOT_EXPLICIT_NEW_SYSTEM_CASE_EXECUTION')
    base = c.parse(c.read_ref(base_ref)); plan = components['system_plan.py']; runtime = components['system_runtime.py']
    host = components['app_runtime.py']; _, support = c.support(base['support_manifest'])
    baseline = support['business_baseline.py'].BusinessBaseline(base['baseline'], base['qualification'])
    plan.validate(c, base, baseline)
    c.need(base['kind']=='calendar_reminder','EXACT_ORIGINAL_REMINDER_KIND')
    root = c.private_dir(base['case_root']); c.write_new(root / 'execute-once.json', {
        'plan': base_ref, 'operator': host.process(c, os.getpid()), 'started_utc': stamp(), 'automatic_retry': False})
    evidence = c.private_dir(root / 'evidence', create=True)
    for name in ('ui', 'diagnostics'):
        c.private_dir(evidence / name, create=True)
    result = {'schema': 'pocket4-final-calendar-reminder22-current-result-v1', 'state': 'FAILED', 'kind': base['kind'],
        'plan': base_ref, 'started_utc': stamp(), 'phases': {}, 'case_business_success_verified': False,
        'whole_app_business_accepted': False, 'automatic_retry': False, 'secondary_errors': [],
        'original_prepared_runtime_credit_transferred':False,'continuous_sampling':False,
        'whole_app_production_ready':False,'engine_identity_automatically_qualified':False,
        'sync_qualified':False,'snooze_qualified':False,'host_notification_actions_qualified':False}
    session = case = lock = witness = None; first = None; retiring = False; signals = []
    saved = {}
    def interrupted(signum, frame):
        nonlocal retiring
        signals.append(signum)
        if not retiring:
            retiring = True
            raise CaseInterrupted('SYSTEM_CASE_INTERRUPTED')
    def remember(label, error):
        nonlocal first
        item = {'phase': label, 'type': type(error).__name__, 'message': str(error)}
        if first is None:
            first = error; result['error'] = item
        else:
            result['secondary_errors'].append(item)
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            saved[signum] = signal.signal(signum, interrupted)
        resources=components['calendar_resources.py']
        result['own_host_resources_before']=resources.own_resources()
        resources.resource_limits(result['own_host_resources_before'])
        lock = runtime.ActionLock(c, host, root)
        lease = runtime.create_lease(c, host, base_ref, base)
        active_ref, scopes = plan.activate(c, base_ref, lease, lock.ref)
        active = c.parse(c.read_ref(active_ref)); phase = runtime.phase(c, host, active_ref, active, 'business')
        witness = c.EvidenceWitness([base_ref, active_ref, lease, lock.ref, *scopes])
        session = components['system_session.py'].Session(c, active_ref, active, scopes, phase, lock, components, evidence)
        emitted = 0
        def emit(value):
            nonlocal emitted
            emitted += 1
            c.write_new(evidence / ('observation-event-%04d.json' % emitted), value)
        case = components['system_factory.py'].construct(session, result, emit)
        if base['kind'] == 'calendar_reminder':
            original = case.result; original.update(result); result = case.result = original
        result.update(active_plan=active_ref, recorder_scopes=scopes, actual_business_phase=phase)
        try:
            calendar(session, case, result)
        except BaseException as error:
            remember('original_business', error)
        finally:
            retiring = True
            try:
                trigger = c.write_new(root / 'cleanup-trigger.json', {'actual_business_error': result.get('error'),
                    'original_scope_completed': result.get('business_scope_completed') is True,
                    'automatic_retry': False, 'started_utc': stamp()})
                result['actual_cleanup_phase'] = session.begin_cleanup(trigger)
                calendar_final(session, case, result)
            except BaseException as error:
                remember('original_final_cleanup_and_readback', error)
    except BaseException as error:
        remember('case_construction_or_admission', error)
    finally:
        retiring = True
        if case is not None and case.sampler is not None:
            try:
                case.sampler.close()
                result['local_synchronous_observer_closed']=True
            except BaseException as error:
                remember('synchronous_observer_close',error)
        for obj, label in ((session, 'actual_Main_and_original_APIs'), (lock, 'whole_case_OFD'), (witness, 'evidence_witness')):
            if obj is not None:
                try:
                    obj.close(); result[label + '_closed'] = True
                except BaseException as error:
                    remember(label + '_close', error)
        try:
            result['independent_Main_after'] = baseline.guard(); plan.validate(c, base, baseline)
            result['final_source_and_identity_chain_unchanged'] = True
        except BaseException as error:
            remember('independent_final_Main_and_source_chain', error)
        if 'own_host_resources_before' in result:
            try:
                resources=components['calendar_resources.py']
                before=result['own_host_resources_before']
                after=result['own_host_resources_after']=resources.own_resources()
                resources.resource_limits(after)
                c.need(before['cgroup']==after['cgroup'],'ORIGINAL_OWN_HOST_CGROUP_CHANGED')
                initial,final=resources.memory_events(before),resources.memory_events(after)
                delta=result['own_memory_event_delta']={k:final[k]-initial[k] for k in final}
                c.need(delta['oom']==delta['oom_kill']==0,'ORIGINAL_OWN_HOST_OOM_OBSERVED')
            except BaseException as error:
                remember('original_host_resource_postcheck',error)
        # This execute path belongs to the dedicated system_entry process. All
        # case contexts and final guards have now finished. Freeze cancellation
        # before terminal serialization, and keep it blocked through entry exit
        # so a later signal cannot split a durable result from its exit status.
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        pending = sorted(signal.sigpending() & {signal.SIGINT, signal.SIGTERM})
        if signals or pending:
            remember('case_cancelled_before_terminal_commit', CaseInterrupted(
                'SYSTEM_CASE_CANCELLED_BEFORE_TERMINAL_COMMIT'))
        result['cancellation_commit'] = {'observed_before_commit': list(signals),
            'pending_at_commit': pending, 'decision_frozen_after_context_exit': True}
        if case is not None:
            result.update(phase=case.phase, ui_actions=case.ui.actions, role_calls=case.roles, ui_pending=case.ui.pending,
                business_pending=case.business_pending, owned_tasks=case.ui.owned, normal_close_calls=case.ui.removals,
                normally_closed_tasks=case.ui.closed, native_launches=case.ui.launches, intent_calls=case.intent_calls,
                empty_calendar_cleanup_calls=case.cleanup_calls, empty_calendar_cleanup_pending=case.cleanup_pending,
                owned_calendar=case.model.calendar, owned_event_id=case.model.event_id)
            cleanup = result.get('cleanup', {})
            succeeded = bool(result.get('business_scope_completed') and set(result.get('gates', {})) == components['calendar_reminder.py'].REQUIRED
                and not cleanup.get('errors', [True]) and cleanup.get('calendar_removed')
                and cleanup.get('provider_baseline_restored') and not result.get('diagnostic_checkpoint_error') and not result.get('runtime_stop_error')
                and not result.get('delivery_error')
                and result.get('runtime_evidence',{}).get('synchronous_observer_closed') is True
                and result.get('runtime_evidence',{}).get('continuous_sampling') is False
                and result.get('guard_after') == result.get('guard_before')
                and case.ui.launches == case.ui.removals == len(case.ui.closed) == 2
                and not case.ui.owned and not case.ui.pending and not case.business_pending and not case.cleanup_pending)
            result['case_business_success_verified'] = bool(succeeded and first is None and not signals and not pending and not result['secondary_errors'])
            result['original_result_preserved'] = True
        result['state'] = 'OWNED_NATURAL_CALENDAR_REMINDER_AND_UI_DELETE_VERIFIED' if result['case_business_success_verified'] else 'FAILED_OR_UNKNOWN_RETAINED'
        result.update(received_signals=signals, finished_utc=stamp(), whole_app_business_accepted=False,
            Binder_UID_cleanup_verified=False, automated_rollback=False)
        result_ref = c.write_new(root / 'result.json', result)
    return result_ref, result
