"""Bounded root controller for one observed QSB branch; no source result grants Android acceptance."""
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import signal
import time

class CaseInterrupted(BaseException):
    pass

def stamp():
    return datetime.now(timezone.utc).isoformat()

def diagnostic_pair(session, diagnostics, label):
    out = {}
    for profile in (session.active['target_profile'], session.active['browser_profile']):
        package, uid = profile['package'], profile['uid']
        raw_clock = session.android(['/system/bin/date', '+%s'], 8).decode('utf-8', 'strict').strip()
        session.c.need(raw_clock.isdecimal() and abs(time.time() - int(raw_clock)) <= 3, 'REAL_GUEST_DIAGNOSTIC_CLOCK')
        value = {'guest_seconds': int(raw_clock)}
        commands = {
            'exits': ['/system/bin/dumpsys', 'activity', 'exit-info', package],
            'events': ['/system/bin/logcat', '-b', 'events', '-d', '-v', 'epoch', '-t', '2048'],
            'crash': ['/system/bin/logcat', '--uid=' + str(uid), '-b', 'crash', '-d', '-v', 'epoch', '-t', '512'],
        }
        for key, command in commands.items():
            raw = session.android(command, 15)
            session.c.need(len(raw) <= 4 * 1024 * 1024, 'BOUNDED_SYNCHRONOUS_UID_DIAGNOSTIC')
            value[key] = raw.decode('utf-8', 'strict')
        diagnostics.exit_events(value['exits'])
        value['evidence'] = session.record(label + '-' + str(uid), value)
        out[package] = value
    return out

def permission_state(session, label):
    values = {}
    for profile in (session.active['target_profile'], session.active['browser_profile']):
        raw = session.android(['/system/bin/dumpsys', 'package', profile['package']], 20).decode('utf-8', 'strict')
        permissions = sorted(line.strip() for line in raw.splitlines()
            if re.search(r'^\s+[A-Za-z][A-Za-z0-9_.]*: granted=(?:true|false)(?:,|$)', line))
        session.c.need(permissions, 'ACTUAL_ORIGINAL_PACKAGE_PERMISSION_STATE_REQUIRED')
        values[profile['package']] = permissions
        session.record(label + '-permissions-' + str(profile['uid']), {'raw': raw, 'permissions': permissions})
    session.flow.artifacts.revalidate()
    return values

def execute(c, base_ref, components):
    c.need(os.getuid() == os.geteuid() == 0, 'ROOT_EXPLICIT_SOURCE_BOUND_SEARCH_EXECUTION')
    base = c.parse(c.read_ref(base_ref)); plan = components['search_plan.py']; runtime = components['search_runtime.py']
    host = components['app_runtime.py']; _, support = c.support(base['support_manifest'])
    baseline = support['business_baseline.py'].BusinessBaseline(base['baseline'], base['qualification'])
    plan.validate(c, base, baseline)
    root = c.private_dir(base['case_root'])
    c.write_new(root / 'execute-once.json', {'plan': base_ref, 'operator': host.process(c, os.getpid()),
        'started_utc': stamp(), 'automatic_retry': False})
    evidence = c.private_dir(root / 'evidence', create=True)
    result = {'schema': 'pocket4-final-quicksearch-branch-result-v1', 'state': 'FAILED', 'kind': base['kind'],
        'plan': base_ref, 'started_utc': stamp(), 'branch_business_success_verified': False,
        'original_search_failure_gate_complete': False, 'whole_app_business_accepted': False,
        'automatic_retry': False, 'secondary_errors': [], 'network_configuration_writes': 0,
        'permission_writes': 0, 'account_operations': 0, 'package_mutations': 0,
        'source_only_branch_facts_are_not_runtime_credit': True,
        'diagnostic_scope': 'synchronous original bounded package/UID crash and exit observations',
        'continuous_sampling_or_soak_credit': False, 'original_full_app_gates_unchanged': True}
    session = driver = lock = witness = None; first = None; retiring = False; signals = []
    def interrupted(signum, frame):
        nonlocal retiring
        signals.append(signum)
        if not retiring:
            retiring = True
            raise CaseInterrupted('SEARCH_CASE_CANCELLED_NO_INPUT_REPLAY')
    def remember(phase, error):
        nonlocal first
        item = {'phase': phase, 'type': type(error).__name__, 'message': str(error)}
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
        session = components['search_session.py'].Session(c, active_ref, active, scopes, phase, lock, components, evidence)
        driver = components['search_driver.py'].Driver(session, result)
        result.update(active_plan=active_ref, recorder_scopes=scopes, actual_business_phase=phase)
        diagnostics = components['search_diagnostics.py']
        try:
            permissions_before = permission_state(session, 'before')
            before = diagnostic_pair(session, diagnostics, 'before')
            driver.run()
            after = diagnostic_pair(session, diagnostics, 'after')
            result['diagnostics'] = {}
            for profile in (active['target_profile'], active['browser_profile']):
                package = profile['package']
                check = diagnostics.fresh_crashes(before[package], after[package], profile['uid'],
                    before[package]['guest_seconds'], package)
                result['diagnostics'][package] = check
                c.need(check['clear'], 'FRESH_SEARCH_OR_BROWSER_CRASH_ANR_OR_EXIT')
            permissions_after = permission_state(session, 'after')
            c.need(permissions_before == permissions_after, 'SEARCH_OR_BROWSER_PERMISSIONS_CHANGED')
            result['actual_permissions_unchanged'] = True
        except BaseException as error:
            remember('actual_search_branch', error)
        finally:
            retiring = True
            try:
                trigger = c.write_new(root / 'cleanup-trigger.json', {'error': result.get('error'),
                    'branch_scope_completed': result.get('branch_scope_completed') is True,
                    'started_utc': stamp(), 'automatic_retry': False})
                result['actual_cleanup_phase'] = session.begin_cleanup(trigger)
                driver.cleanup()
                roots, tasks, task_ref = session.stacks('final-task-set')
                c.need(tasks == session.baseline_tasks and roots == session.baseline_roots, 'ALL_PREEXISTING_TASKS_PRESERVED')
                result['final_tasks'] = task_ref; result['guard_after'] = session.guard()
            except BaseException as error:
                remember('bounded_known_owned_task_cleanup', error)
    except BaseException as error:
        remember('case_admission_or_construction', error)
    finally:
        retiring = True
        for obj, label in ((session, 'actual_Main_and_UI'), (lock, 'whole_case_OFD'), (witness, 'evidence_witness')):
            if obj is not None:
                try:
                    obj.close(); result[label + '_closed'] = True
                except BaseException as error:
                    remember(label + '_close', error)
        try:
            result['independent_Main_after'] = baseline.guard(); plan.validate(c, base, baseline)
            result['final_source_and_identity_chain_unchanged'] = True
        except BaseException as error:
            remember('independent_final_Main_or_source_chain', error)
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        pending = sorted(signal.sigpending() & {signal.SIGINT, signal.SIGTERM})
        if signals or pending:
            remember('cancelled_before_terminal_commit', CaseInterrupted('SEARCH_CANCELLED_BEFORE_TERMINAL_COMMIT'))
        result['cancellation_commit'] = {'observed_before_commit': list(signals), 'pending_at_commit': pending,
            'decision_frozen_after_context_exit': True}
        if driver is not None:
            result.update(UI_actions=driver.actions, pending_input=driver.pending, native_launch_calls=session.native_launches,
                native_tasks=session.native_tasks, closed_native_tasks=session.closed_native_tasks,
                implicit_browser_tasks=session.companion_tasks, closed_browser_tasks=session.closed_companion_tasks,
                native_browser_launch_calls=0, back_inputs=driver.back_inputs, known_owned_remove_calls=session.remove_calls,
                query_preimages_restored=sorted(driver.restored), owned_primary_remaining=session.primary_task,
                owned_browser_remaining=session.handoff, unknown_input_not_resolved_by_task_cleanup=driver.pending is not None)
            result['branch_business_success_verified'] = bool(result.get('branch_scope_completed')
                and result.get('actual_permissions_unchanged') and result.get('guard_after')
                and driver.pending is None and session.native_tasks == session.closed_native_tasks
                and len(set(session.native_tasks)) == 2 and driver.restored == {0, 1}
                and session.companion_tasks == session.closed_companion_tasks
                and session.primary_task is None and session.handoff is None
                and first is None and not result['secondary_errors'] and not signals and not pending)
        result['state'] = 'ACTUAL_SEARCH_BRANCH_VERIFIED_CLEAN' if result['branch_business_success_verified'] else 'FAILED_OR_UNKNOWN_RETAINED'
        result.update(finished_utc=stamp(), received_signals=signals, original_search_failure_gate_complete=False,
            whole_app_business_accepted=False, Binder_UID_cleanup_verified=False, automated_rollback=False)
        ref = c.write_new(root / 'result.json', result)
    return ref, result
