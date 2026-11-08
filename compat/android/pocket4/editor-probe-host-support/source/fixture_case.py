"""Original two-round business bodies under fresh bounded case ownership."""
from datetime import datetime, timezone
import os
from pathlib import Path
import signal

class CaseInterrupted(BaseException):
    pass

def stamp():
    return datetime.now(timezone.utc).isoformat()

def business(session, adapter, result):
    c = session.c; flow = adapter.flow; uid = session.active['target_profile']['uid']
    result['identity_before'] = adapter.identity(session)
    before = adapter.diagnostics.trial.diagnostics('before', uid)
    adapter.diagnostics.exit_events(before['exits'])
    flow.run()
    after = adapter.diagnostics.trial.diagnostics('after', uid)
    result['diagnostics'] = adapter.diagnostics.fresh_crashes(before, after, uid, before['guest_seconds'])
    c.need(result['diagnostics']['clear'], 'ORIGINAL_FRESH_FIXTURE_CRASH_ANR_OR_EXIT_GATE')
    result['identity_after'] = adapter.identity(session)
    c.need(result['identity_before'] == result['identity_after'], 'ORIGINAL_IDENTITY_OR_PERMISSIONS_CHANGED')
    c.need(len(flow.closed) == len(set(flow.owned)) == 2 and flow.closed == flow.owned
        and flow.c.pending is None, 'ORIGINAL_TWO_DISTINCT_OWNED_LIFECYCLES_REQUIRED')
    if session.kind == 'qa_probe03':
        c.need(flow.c.actions == flow.number == 14 and len(result['rounds']) == 2
            and result['functional_flow_verified'], 'COMPLETE_ORIGINAL_14_PROBE_ACTIONS')
    else:
        c.need(flow.intent_calls == 2 and flow.actions <= 20 and len(result['rounds']) == 2
            and len(flow.evidence) == 2 and all(ev.cleaned and ev.final is not None for ev in flow.evidence),
            'COMPLETE_ORIGINAL_EDITOR_NONCE_KEY_AND_OWNED_FILE_CLEANUP')
    result['business_scope_completed'] = True

def execute(c, base_ref, components):
    c.need(os.getuid() == os.geteuid() == 0, 'ROOT_EXPLICIT_NEW_FIXTURE_EXECUTION')
    base = c.parse(c.read_ref(base_ref)); plan = components['fixture_plan.py']; runtime = components['fixture_runtime.py']
    host = components['app_runtime.py']; _, support = c.support(base['support_manifest'])
    baseline = support['business_baseline.py'].BusinessBaseline(base['baseline'], base['qualification'])
    plan.validate(c, base, baseline)
    root = c.private_dir(base['case_root']); c.write_new(root / 'execute-once.json', {
        'plan': base_ref, 'operator': host.process(c, os.getpid()), 'started_utc': stamp(), 'automatic_retry': False})
    evidence = c.private_dir(root / 'evidence', create=True)
    for name in ('ui', 'diagnostics'):
        c.private_dir(evidence / name, create=True)
    result = {'schema': 'pocket4-final-original-editor-probe-result-v1', 'state': 'FAILED', 'kind': base['kind'],
        'plan': base_ref, 'started_utc': stamp(), 'case_business_success_verified': False,
        'whole_app_business_accepted': False, 'automatic_retry': False, 'secondary_errors': [], 'rounds': [],
        'diagnostic_scope': 'synchronous before/after original UID crash and process-exit records',
        'continuous_sampling_or_soak_credit': False, 'functional_flow_verified': False,
        'original_full_app_gates_unchanged': True}
    session = adapter = lock = witness = None; first = None; retiring = False; signals = []
    def interrupted(signum, frame):
        nonlocal retiring
        signals.append(signum)
        if not retiring:
            retiring = True
            raise CaseInterrupted('FIXTURE_CASE_INTERRUPTED_NO_INPUT_REPLAY')
    def remember(label, error):
        nonlocal first
        item = {'phase': label, 'type': type(error).__name__, 'message': str(error)}
        if first is None:
            first = error; result['error'] = item
        else:
            result['secondary_errors'].append(item)
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, interrupted)
        lock = runtime.ActionLock(c, host, root)
        lease = runtime.create_lease(c, host, base_ref, base)
        active_ref, scopes = plan.activate(c, base_ref, lease, lock.ref)
        active = c.parse(c.read_ref(active_ref)); phase = runtime.phase(c, host, active_ref, active, 'business')
        witness = c.EvidenceWitness([base_ref, active_ref, lease, lock.ref, *scopes])
        session = components['fixture_session.py'].Session(c, active_ref, active, scopes, phase, lock, components, evidence)
        emitted = 0
        def emit(value):
            nonlocal emitted
            emitted += 1
            c.write_new(evidence / ('observation-event-%04d.json' % emitted), value)
        adapter = components['fixture_factory.py'].construct(session, result, emit)
        result.update(active_plan=active_ref, recorder_scopes=scopes, actual_business_phase=phase)
        try:
            business(session, adapter, result)
        except BaseException as error:
            remember('original_business', error)
        finally:
            retiring = True
            try:
                trigger = c.write_new(root / 'cleanup-trigger.json', {'actual_business_error': result.get('error'),
                    'original_scope_completed': result.get('business_scope_completed') is True,
                    'automatic_retry': False, 'started_utc': stamp()})
                result['actual_cleanup_phase'] = session.begin_cleanup(trigger)
                # Preserve the original independent normal task close. It never
                # retries an uncertain input, nonce route or previous remove.
                adapter.flow.close()
                session.caller_status('editor-final-caller' if base['kind'] == 'editor_ui03' else 'probe-final-caller')
                result['guard_after'] = session.guard()
            except BaseException as error:
                remember('original_final_cleanup_and_readback', error)
    except BaseException as error:
        remember('case_construction_or_admission', error)
    finally:
        retiring = True
        # This is FD retirement only, separate from original data cleanup.
        # Never replay Evidence.cleanup or unlink a record after uncertainty.
        if adapter is not None and base['kind'] == 'editor_ui03':
            for ev in adapter.flow.evidence:
                try:
                    ev.handles.close()
                except BaseException as error:
                    remember('owned_editor_descriptor_close', error)
            result['owned_record_descriptors_closed'] = all(not ev.handles.fds for ev in adapter.flow.evidence)
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
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        pending = sorted(signal.sigpending() & {signal.SIGINT, signal.SIGTERM})
        if signals or pending:
            remember('case_cancelled_before_terminal_commit', CaseInterrupted('FIXTURE_CANCELLED_BEFORE_TERMINAL_COMMIT'))
        result['cancellation_commit'] = {'observed_before_commit': list(signals), 'pending_at_commit': pending,
            'decision_frozen_after_context_exit': True}
        if adapter is not None:
            f = adapter.flow
            result.update(UI_actions=f.c.actions, pending_input=f.c.pending, native_launched_tasks=f.owned,
                normally_closed_tasks=f.closed, native_launch_calls=session.trial.launches,
                normal_remove_calls=session.trial.removals, owned_task_remaining=session.trial.owned,
                unknown_input_not_reconciled_by_normal_task_close=f.c.pending is not None)
            if base['kind'] == 'editor_ui03':
                result.update(all_input_calls=f.actions, nonce_intent_calls=f.intent_calls,
                    owned_nonces_requiring_reconciliation=[ev.run for ev in f.evidence if ev.intent_submitted and not ev.cleaned])
            succeeded = bool(result.get('business_scope_completed') and f.c.pending is None
                and f.owned == f.closed and len(f.owned) == len(set(f.owned)) == 2
                and session.trial.owned is None and session.trial.launches == session.trial.removals == 2
                and result.get('guard_after') and not result.get('owned_nonces_requiring_reconciliation')
                and result.get('owned_record_descriptors_closed', True))
            result['case_business_success_verified'] = bool(succeeded and first is None and not signals and not pending
                and not result['secondary_errors'])
        result['state'] = 'ORIGINAL_CASE_VERIFIED_CLEAN' if result['case_business_success_verified'] else 'FAILED_OR_UNKNOWN_RETAINED'
        result.update(received_signals=signals, finished_utc=stamp(), whole_app_business_accepted=False,
            Binder_UID_cleanup_verified=False, automated_rollback=False)
        ref = c.write_new(root / 'result.json', result)
    return ref, result
