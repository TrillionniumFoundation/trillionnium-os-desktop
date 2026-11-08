"""One explicitly authorized fresh Camera video case in its real parent worker.

The finite case owns Binder task claims separately from the parent's acoustic
processes. All local contexts close before the cancellation/terminal commit.
Unknown start/stop/VIEW/removal or host retirement is never retried or promoted.
"""
from datetime import datetime, timezone
import os
import signal

class CaseInterrupted(BaseException):
    pass

def stamp():
    return datetime.now(timezone.utc).isoformat()

def execute(c, base_ref, components, acoustic):
    c.need(os.getuid() == os.geteuid() == 0, 'ROOT_NEW_CAMERA_VIDEO_WORKER')
    base = c.parse(c.read_ref(base_ref)); plan = components['camera_plan.py']; runtime = components['camera_runtime.py']
    host = components['app_runtime.py']; _, support = c.support(base['support_manifest'])
    baseline = support['business_baseline.py'].BusinessBaseline(base['baseline'], base['qualification'])
    plan.validate(c, base, baseline); acoustic.verify()
    root = c.private_dir(base['case_root']); c.write_new(root / 'execute-once.json', {
        'plan': base_ref, 'operator': host.process(c, os.getpid()), 'started_utc': stamp(), 'automatic_retry': False})
    evidence = c.private_dir(root / 'evidence', create=True)
    result = {'schema': 'pocket4-current-camera-video-case-result-v1', 'state': 'FAILED',
        'plan': base_ref, 'source_preparation': base['source_preparation'], 'kind': 'camera_video',
        'started_utc': stamp(), 'case_business_success_verified': False, 'runtime_qualified': False,
        'whole_app_business_accepted': False, 'camera_recovery_qualified': False,
        'common_six_gates_complete': False, 'automatic_retry': False, 'secondary_errors': [],
        'acoustic_results': {}, 'acoustic_channel_closed': False}
    session = driver = lock = witness = None; first = None; retiring = False; signals = []
    def cancelled(number, frame):
        nonlocal retiring
        if len(signals) < 32: signals.append(number)
        if not retiring:
            retiring = True; raise CaseInterrupted('CAMERA_VIDEO_WORKER_CANCELLED')
    def remember(stage, error):
        nonlocal first
        row = {'stage': stage, 'type': type(error).__name__, 'message': str(error)}
        if first is None: first = error; result['error'] = row
        else: result['secondary_errors'].append(row)
    for number in (signal.SIGINT, signal.SIGTERM): signal.signal(number, cancelled)
    try:
        lock = runtime.ActionLock(c, host, root)
        lease = runtime.create_lease(c, host, base_ref, base)
        active_ref, scopes = plan.activate(c, base_ref, lease, lock.ref)
        active = c.parse(c.read_ref(active_ref)); phase = runtime.phase(c, host, active_ref, active, 'business')
        witness = c.EvidenceWitness([base_ref, active_ref, lease, lock.ref, *scopes, acoustic.parent_ref])
        cls = components['camera_session.py'].make_session(components['camera_base_session.py'])
        session = cls(c, active_ref, active, scopes, phase, lock, components, evidence, acoustic)
        acoustic.attach(session)
        driver = components['camera_video_driver.py'].Driver(session, result)
        result.update(active_plan=active_ref, recorder_scopes=scopes, actual_business_phase=phase)
        try:
            driver.run()
        except BaseException as error:
            if isinstance(error, components['camera_decode.py'].DecodeOutcomeUnknown): driver.host_unknown = True
            remember('current_camera_video_business', error)
        finally:
            retiring = True
            try:
                trigger = c.write_new(root / 'cleanup-trigger.json', {'actual_business_error': result.get('error'),
                    'case_run_completed': driver.run_completed, 'automatic_retry': False, 'started_utc': stamp()})
                result['actual_cleanup_phase'] = session.begin_cleanup(trigger); driver.finish()
            except BaseException as error: remember('camera_video_cleanup_readback', error)
    except BaseException as error: remember('camera_video_admission_or_construction', error)
    finally:
        retiring = True
        if driver is not None:
            try: driver.close_local(); result['owned_decoder_descriptor_closed'] = True
            except BaseException as error: remember('owned_local_video_descriptor_close', error)
        for context, label in ((session, 'current_Main_APIs'), (lock, 'whole_case_OFD'),
                (witness, 'evidence_witness'), (acoustic, 'acoustic_channel')):
            if context is not None:
                try: context.close(); result[label + '_closed'] = True
                except BaseException as error: remember(label + '_close', error)
        result['acoustic_results'] = {role: acoustic.results[role + '_finish']
            for role in ('emit', 'listen') if role + '_finish' in acoustic.results}
        result['acoustic_pending'] = acoustic.pending
        try:
            result['independent_Main_after'] = baseline.guard(); plan.validate(c, base, baseline)
            result['final_source_and_identity_chain_unchanged'] = True
        except BaseException as error: remember('independent_final_Main_source_guard', error)
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        pending_signals = sorted(signal.sigpending() & {signal.SIGINT, signal.SIGTERM})
        if signals or pending_signals:
            remember('cancelled_before_terminal_commit', CaseInterrupted('CAMERA_VIDEO_CANCELLED_BEFORE_COMMIT'))
        unknown = acoustic.pending is not None or result['acoustic_channel_closed'] is not True
        if driver is not None:
            unknown = bool(unknown or driver.host_unknown or driver.pending is not None
                or driver.close_pending is not None or driver.owned is not None
                or driver.recording is not None and driver.recording.pending is not None
                or driver.decoder is not None and driver.decoder.unknown)
            result.update(native_launches=driver.launches, exact_normal_closes=driver.closes,
                pending_business_action=driver.pending, pending_owned_task_remove=driver.close_pending,
                owned_task_remaining=driver.owned,
                recording_pending=None if driver.recording is None else driver.recording.pending,
                owned_task_cleanup_verified=driver.cleanup_verified)
        success = bool(driver is not None and driver.run_completed and driver.cleanup_verified
            and first is None and not signals and not pending_signals and not result['secondary_errors'] and not unknown
            and all(result.get(k) is True for k in ('current_Main_APIs_closed', 'whole_case_OFD_closed',
                'evidence_witness_closed', 'acoustic_channel_closed', 'owned_decoder_descriptor_closed',
                'final_source_and_identity_chain_unchanged')))
        result.update(state='CURRENT_CAMERA_VIDEO_SCOPE_VERIFIED_CLEAN' if success else 'FAILED_OR_UNKNOWN_RETAINED',
            case_business_success_verified=success, outcome_unknown=unknown,
            cancellation_commit={'received_signals': signals, 'pending_at_commit': pending_signals,
                'decision_after_all_context_close': True}, finished_utc=stamp(),
            automated_rollback=False, Binder_UID_cleanup_verified=False,
            whole_app_business_accepted=False, runtime_qualified=False)
        ref = c.write_new(root / 'result.json', result)
    return ref, result
