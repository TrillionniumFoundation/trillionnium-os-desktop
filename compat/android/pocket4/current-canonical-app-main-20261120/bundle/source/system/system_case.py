"""Original Contacts search03 / Calendar core21 coordinators, new Main only."""
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


def contacts(s, f, result):
    c = s.c; m = s.components; verifier = m['contacts_model.py']; mouse = m['contacts_mouse.py']; trial = s.trial
    result['guard_before'] = s.guard()
    verifier.identity(s); result['native_actions_before'] = mouse.native_identity(s)
    result['account_topology_before'] = verifier.unchanged_account_topology(s)
    roots, tasks = trial.stacks('initial-coordinated-taskset')
    result['actual_new_task_baseline'] = {'roots': copy.deepcopy(roots), 'tasks': sorted(tasks)}
    result['contacts_before'] = verifier.current_state(s); verifier.validate_before(result['contacts_before'])
    result['empty_baseline_verified'] = True
    f.run(); result['business_scope_completed'] = True


def contacts_final(s, f, result, failure):
    c = s.c; m = s.components; verifier = m['contacts_model.py']; mouse = m['contacts_mouse.py']; trial = s.trial
    if failure:
        f.deadline = s.deadline - 15
        try:
            f.cleanup_fixture_on_failure()
        except BaseException as error:
            result['fixture_cleanup_error'] = type(error).__name__ + ': ' + str(error)
    if f.c.pending is None and f.close_pending is None and f.effect_pending is None:
        f.close()
    else:
        result['unknown_retained_without_further_mutation'] = True
    result['contacts_after'] = verifier.current_state(s)
    if f.created is None:
        verifier.validate_before(result['contacts_after'])
    else:
        result['deleted_final_proof'] = verifier.validate_deleted(result['contacts_after'], f.created)
    result['account_topology_after'] = verifier.unchanged_account_topology(s)
    verifier.identity(s); result['native_actions_after'] = mouse.native_identity(s)
    c.need(result['native_actions_after'] == result['native_actions_before'], 'ORIGINAL_NATIVE_HELPER_IDENTITY_CHANGED')
    roots, tasks = trial.stacks('final-coordinated-taskset')
    expected = result['actual_new_task_baseline']
    c.need(tasks == set(expected['tasks']) and roots == expected['roots'], 'ORIGINAL_COMPLETE_TASK_BASELINE_NOT_RESTORED')
    s.caller_status('contacts-search-final'); result['guard_after'] = s.guard()
    c.need(result['guard_after'] == result['guard_before'], 'ACTUAL_NEW_MAIN_CHANGED')
    result['cleanup_verified'] = f.c.pending is None and f.close_pending is None and f.effect_pending is None and trial.owned is None


def calendar(s, f, result):
    m = s.components; p = m['system_profiles.py']; doc = m['calendar_identity.py']
    result['native_actions_before'] = doc.identity(s, p.NATIVE_HELPER['package'], p.NATIVE_HELPER['apks'][0]['sha256'], 10125, 2)
    f.setup(); f.diag_chain.start(f.before_diag); f.diag_chain.checkpoint('after-initial-launch', force=True)
    m['calendar_driver.py'].run(f, m['calendar_model.py'])


def calendar_final(s, f, result):
    c = s.c; m = s.components; p = m['system_profiles.py']; doc = m['calendar_identity.py']
    try:
        if f.diag_chain.first is not None:
            f.diag_chain.checkpoint('before-cleanup', force=True)
    except BaseException as error:
        result['diagnostic_checkpoint_error'] = type(error).__name__ + ': ' + str(error)
    result['cleanup'] = f.cleanup()
    result['calendar_after'] = f.calendar_identity()
    c.need(result['calendar_after'] == result['calendar_before'], 'ORIGINAL_CALENDAR_IDENTITY_CHANGED')
    result['provider_after'] = doc.identity(s, p.CALENDAR_PROVIDER['package'], p.CALENDAR_PROVIDER['apks'][0]['sha256'], 10017, 37)
    c.need(result['provider_after'] == result['provider_before'], 'ORIGINAL_PROVIDER_IDENTITY_CHANGED')
    result['native_actions_after'] = doc.identity(s, p.NATIVE_HELPER['package'], p.NATIVE_HELPER['apks'][0]['sha256'], 10125, 2)
    c.need(result['native_actions_after'] == result['native_actions_before'], 'ORIGINAL_NATIVE_HELPER_IDENTITY_CHANGED')
    result['final_counts'] = f.counts('final'); c.need(not any(result['final_counts'].values()), 'ORIGINAL_PROVIDER_BASELINE_NOT_RESTORED')
    _, tasks = f.ui.check_tasks('final'); result['task_set_restored'] = not f.ui.owned and tasks == f.ui.baseline
    c.need(result['task_set_restored'], 'ORIGINAL_TASK_SET_NOT_RESTORED')
    after = f.diagnostics.diagnostics('after', 10061); result['diagnostics'] = f.diag_chain.finish(after)
    c.need(result['diagnostics']['clear'], 'ORIGINAL_FRESH_CALENDAR_CRASH_OR_ANR_GATE')
    s.caller_status('calendar-core-final'); result['guard_after'] = s.guard()


def execute(c, base_ref, components):
    c.need(os.getuid() == os.geteuid() == 0, 'ROOT_EXPLICIT_NEW_SYSTEM_CASE_EXECUTION')
    base = c.parse(c.read_ref(base_ref)); plan = components['system_plan.py']; runtime = components['system_runtime.py']
    host = components['app_runtime.py']; _, support = c.support(base['support_manifest'])
    baseline = support['business_baseline.py'].BusinessBaseline(base['baseline'], base['qualification'])
    plan.validate(c, base, baseline)
    root = c.private_dir(base['case_root']); c.write_new(root / 'execute-once.json', {
        'plan': base_ref, 'operator': host.process(c, os.getpid()), 'started_utc': stamp(), 'automatic_retry': False})
    evidence = c.private_dir(root / 'evidence', create=True)
    for name in ('ui', 'diagnostics'):
        c.private_dir(evidence / name, create=True)
    result = {'schema': 'pocket4-final-original-system-case-result-v1', 'state': 'FAILED', 'kind': base['kind'],
        'plan': base_ref, 'started_utc': stamp(), 'phases': {}, 'case_business_success_verified': False,
        'whole_app_business_accepted': False, 'automatic_retry': False, 'secondary_errors': []}
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
        if base['kind'] == 'calendar_core':
            original = case.result; original.update(result); result = case.result = original
        result.update(active_plan=active_ref, recorder_scopes=scopes, actual_business_phase=phase)
        try:
            if base['kind'] == 'contacts_search':
                contacts(session, case, result)
            else:
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
                if base['kind'] == 'contacts_search':
                    contacts_final(session, case, result, first is not None)
                else:
                    calendar_final(session, case, result)
            except BaseException as error:
                remember('original_final_cleanup_and_readback', error)
    except BaseException as error:
        remember('case_construction_or_admission', error)
    finally:
        retiring = True
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
            if base['kind'] == 'contacts_search':
                result.update(UI_actions=case.c.actions, pending_input=case.c.pending, pending_close=case.close_pending,
                    pending_database_effect=case.effect_pending, native_launched_tasks=case.owned_tasks,
                    normally_closed_tasks=case.closed_tasks, owned_task_remaining=session.trial.owned,
                    durable_contact_ownership=case.ownership_journal, provider_cleanup_calls=int(case.cleanup_dispatched))
                succeeded = bool(result.get('business_scope_completed') and result.get('cleanup_verified')
                    and result.get('edited_contact_found_by_search_and_reopened') and result.get('UI_delete_verified')
                    and case.owned_tasks == case.closed_tasks and len(case.owned_tasks) == 2
                    and not result.get('fixture_cleanup_error'))
            else:
                result.update(phase=case.phase, ui_actions=case.ui.actions, role_calls=case.roles, ui_pending=case.ui.pending,
                    business_pending=case.business_pending, owned_tasks=case.ui.owned, normal_close_calls=case.ui.removals,
                    normally_closed_tasks=case.ui.closed, native_launches=case.ui.launches, intent_calls=case.intent_calls,
                    empty_calendar_cleanup_calls=case.cleanup_calls, empty_calendar_cleanup_pending=case.cleanup_pending,
                    owned_calendar=case.model.calendar, owned_event_id=case.model.event_id)
                cleanup = result.get('cleanup', {})
                succeeded = bool(result.get('business_scope_completed') and set(result.get('gates', {})) == components['calendar_core.py'].REQUIRED
                    and not cleanup.get('errors', [True]) and cleanup.get('calendar_removed')
                    and cleanup.get('provider_baseline_restored') and not result.get('diagnostic_checkpoint_error')
                    and result.get('guard_after') == result.get('guard_before')
                    and case.ui.launches == case.ui.removals == len(case.ui.closed) == 2
                    and not case.ui.owned and not case.ui.pending and not case.business_pending and not case.cleanup_pending)
            result['case_business_success_verified'] = bool(succeeded and first is None and not signals and not pending and not result['secondary_errors'])
            result['original_result_preserved'] = True
        result['state'] = 'ORIGINAL_CASE_VERIFIED_CLEAN' if result['case_business_success_verified'] else 'FAILED_OR_UNKNOWN_RETAINED'
        result.update(received_signals=signals, finished_utc=stamp(), whole_app_business_accepted=False,
            Binder_UID_cleanup_verified=False, automated_rollback=False)
        result_ref = c.write_new(root / 'result.json', result)
    return result_ref, result
