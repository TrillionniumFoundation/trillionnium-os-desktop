"""Run the original one-photo/persistence case on two fresh current scopes.

This is the photo preparation's execution component. Even a completed result
requires current pixel review, the separate video/audio/playback and recovery
cases, and the common app gates before Camera can be accepted as a whole app.
"""
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


class PhotoCase:
    def __init__(self, session, result):
        self.s = session; self.c = session.c; self.result = result
        self.m = session.components['camera_photo_model.py']
        self.o = session.components['camera_observations.py']
        self.p = session.components['camera_profiles.py']
        self.shutter_seconds = None; self.before = None; self.baseline_diag = None
        self.initial_tasks = None; self.ids_before = None; self.photo = self.row = None
        self.started = False; self.run_completed = False; self.cleanup_verified = False
        trial_type = session.components['camera_photo_trial.py'].make_trial(self.m, session.tx)
        self.trial = trial_type(session, session.tx, session.evidence_root)
        session.case = self; session.trial = self.trial

    def service_state(self, label):
        call = self.s.host_observation(label, ['/usr/bin/systemctl', 'show', self.p.PROVIDER_UNIT,
            '--property=Id,ActiveState,SubState,MainPID,ControlGroup,InvocationID,FragmentPath,ExecStart'], 10)
        rows = call['stdout'].decode('utf-8', 'strict').splitlines()
        self.c.need(rows and all('=' in line for line in rows), 'EXACT_CAMERA_SERVICE_PROPERTIES')
        value = dict(line.split('=', 1) for line in rows)
        self.c.need(len(value) == len(rows) and set(value) == {'Id', 'ActiveState', 'SubState', 'MainPID',
            'ControlGroup', 'InvocationID', 'FragmentPath', 'ExecStart'}
            and value['Id'] == self.p.PROVIDER_UNIT and value['ActiveState'] == 'active'
            and value['SubState'] == 'running' and re.fullmatch('[1-9][0-9]*', value['MainPID'])
            and int(value['MainPID']) > 1 and re.fullmatch('[0-9a-f]{32}', value['InvocationID'])
            and value['ControlGroup'] == '/system.slice/' + self.p.PROVIDER_UNIT
            and value['FragmentPath'] == '/etc/systemd/system/' + self.p.PROVIDER_UNIT
            and '/opt/pocket4-live-camera/manager.py' in value['ExecStart'],
            'ONE_ACTUAL_CURRENT_LIVE_CAMERA_MANAGER')
        return value

    def prepare_provider(self):
        s = self.s; self.result['provider_before'] = self.service_state('provider-before')
        s.provider = self.result['provider_before']
        s.hardware = self.o.physical_identity(); s.owner = self.o.provider_owner()
        self.c.need(s.owner['pid'] == int(s.provider['MainPID']), 'PROVIDER_LOCK_AND_SYSTEMD_MANAGER_MUST_AGREE')
        s.manager_identity = s.host.process(self.c, int(s.provider['MainPID']))
        self.result.update(physical_device=s.hardware, provider_owner=s.owner,
                           provider_manager=s.manager_identity, host_boot_id=s.host.boot())
        provider, _ = s.target.read_file(self.p.MEDIA_PROVIDER_APK, 16777216, single_link=True)
        self.result['media_provider'] = {'path': self.p.MEDIA_PROVIDER_APK,
            'bytes': len(provider), 'sha256': self.c.sha(provider)}
        raw = s.android(['/system/bin/dumpsys', 'media.camera'], 15)
        s.tx.write_new(s.evidence_root / 'camera-service-before.txt', raw)
        text = raw.decode('utf-8', 'strict')
        self.c.need(len(raw) <= 4194304 and re.search(r'^Active Camera Clients:\s*\n\[\]\s*$', text, re.M),
                    'NO_PREEXISTING_ANDROID_CAMERA_CLIENT_TO_DISTURB')

    def physical_after_close(self, cursor, start_us, label):
        basic = self.trial.provider_after_close(cursor)
        rows = self.trial.journal(cursor)
        raw = b'\n'.join(self.c.canonical(row).strip() for row in rows)
        events = self.o.journal_events(raw, self.s.provider['InvocationID'],
            int(self.s.provider['MainPID']), self.result['host_boot_id'])
        end_us = time.monotonic_ns() // 1000
        cycles = self.o.physical_cycles(events, start_us, end_us, expected=1)
        self.c.need(self.o.provider_owner() == self.s.owner and self.o.physical_identity() == self.s.hardware,
                    'SAME_PHYSICAL_CAMERA_AND_MANAGER_THROUGH_THIS_OWNED_SESSION')
        value = {'original_provider_proof': basic, 'actual_fixed_device_cycles': cycles,
            'invocation': self.s.provider['InvocationID'], 'boot_id': self.result['host_boot_id'],
            'manager_pid': int(self.s.provider['MainPID']), 'start_monotonic_us': start_us,
            'end_monotonic_us': end_us, 'historical_frames_used': False}
        self.trial.record(label, value); return value

    def run(self):
        s, t, m, c = self.s, self.trial, self.m, self.c
        self.result['guard_before'] = s.guard()
        self.before = s.snapshot('acceptance-before')
        c.need(self.before['apk']['sha256'] == self.p.CAMERA['apks'][0]['sha256']
            and self.before['apk']['bytes'] == self.p.CAMERA['apks'][0]['bytes'], 'RELEASE08_NOT_CURRENTLY_INSTALLED')
        uid = self.before['identity']['uid']
        self.baseline_diag = t.diagnostics('diagnostics-before', uid); m.exit_events(self.baseline_diag['exits'])
        t.record('photo-mode-before-launch', m.photo_mode_verified(s))
        self.prepare_provider(); self.ids_before = t.ids('media-before')
        self.initial_tasks = t.stacks('all-tasks-before')[1]; self.started = True
        cursor = t.journal(); start_us = time.monotonic_ns() // 1000
        t.launch('open'); t.record('photo-mode-after-launch', m.photo_mode_verified(s))
        self.result['first_preview'] = t.preview('open')
        ready = t.ui('before-shutter', {'op': 'dump', 'package': m.PACKAGE, 'display': 0})
        t.ready(ready); t.record('photo-mode-before-shutter', m.photo_mode_verified(s))
        self.shutter_seconds = time.time()
        t.ui('single-shutter', {'op': 'click', 'package': m.PACKAGE, 'display': 0,
            'method': 'accessibility', 'selector': {'id': m.PACKAGE + ':id/shutter_button',
                                                   'enabled': True, 'clickable': True}})
        deadline = min(time.monotonic() + 25, s.deadline)
        row = None
        while time.monotonic() < deadline:
            image_id = m.new_image_id(self.ids_before, t.ids('media-after-shutter'))
            row = t.row(image_id, self.shutter_seconds) if image_id is not None else None
            if row is not None:
                break
            time.sleep(.4)
        c.need(row is not None, 'ONE_NEW_PHOTO_NOT_PERSISTED')
        self.row = row; self.photo = t.read_photo(row, 'new-photo-decoded', save=True)
        t.close(); self.result['first_provider'] = self.physical_after_close(cursor, start_us, 'first-current-provider')
        c.need(t.row(image_id, self.shutter_seconds) == row, 'PHOTO_ROW_CHANGED_AFTER_CLOSE')
        c.need(t.read_photo(row, 'photo-after-close') == self.photo, 'PHOTO_BYTES_CHANGED_AFTER_CLOSE')
        cursor = t.journal(); start_us = time.monotonic_ns() // 1000
        t.launch('reopen'); t.record('photo-mode-after-reopen', m.photo_mode_verified(s))
        self.result['reopened_preview'] = t.preview('reopen')
        c.need(t.row(image_id, self.shutter_seconds) == row, 'PHOTO_ROW_CHANGED_AFTER_REOPEN')
        c.need(t.read_photo(row, 'photo-after-reopen') == self.photo, 'PHOTO_BYTES_CHANGED_AFTER_REOPEN')
        t.close(); self.result['reopened_provider'] = self.physical_after_close(cursor, start_us, 'reopened-current-provider')
        c.need(t.ids('media-final') == self.ids_before | {image_id}, 'FINAL_MEDIASTORE_DELTA_DIFFERS')
        c.need(t.stacks('all-tasks-final')[1] == self.initial_tasks, 'OTHER_TASKS_NOT_PRESERVED')
        after_diag = t.diagnostics('diagnostics-after', uid)
        self.result['crash_observation'] = m.fresh_crashes(self.baseline_diag, after_diag, uid,
                                                        self.baseline_diag['guest_seconds'])
        c.need(self.result['crash_observation']['clear'], 'NEW_CAMERA_CRASH_OR_ANR')
        after = s.snapshot('acceptance-after'); c.need(after == self.before, 'CAMERA_APK_DATA_IDENTITY_OR_PERMISSIONS_CHANGED')
        self.result['provider_after'] = self.service_state('provider-after')
        c.need(self.result['provider_after'] == self.result['provider_before'], 'CAMERA_MANAGER_RESTARTED_DURING_ORIGINAL_CASE')
        s.guard(); m.require_completed_lifecycle(t)
        self.result.update(photo=self.photo, new_media_row=row, one_new_image=True,
            photo_persisted_after_close=True, photo_persisted_after_reopen=True,
            other_tasks_preserved=True, installed_apk_and_data_identity_preserved=True,
            provider_owner_preserved=True, original_photo_state_machine_completed=True)
        self.run_completed = True

    def finish(self):
        s, t, c = self.s, self.trial, self.c
        # An uncertain shutter is never replayed. The original case explicitly
        # permits one normal removal of its independently owned task on failure.
        # A pending/uncertain removal has already burned ownership and is never
        # repeated. No media file is deleted or adopted from an unknown shutter.
        if t.owned is not None:
            t.close()
        if self.initial_tasks is not None:
            c.need(t.stacks('final-cleanup-taskset')[1] == self.initial_tasks, 'ORIGINAL_CAMERA_TASKSET_NOT_RESTORED')
        if self.ids_before is not None:
            after_ids = t.ids('final-cleanup-media-ids')
            if not t.pending_effects:
                expected = self.ids_before | ({self.row['_id']} if self.row else set())
                c.need(after_ids == expected, 'CAMERA_FINAL_OWNED_MEDIA_DELTA_CHANGED')
        s.caller_status('camera-photo-final'); self.result['guard_after'] = s.guard()
        c.need(self.result['guard_after'] == self.result['guard_before'], 'SAME_ACTUAL_CAMERA_MAIN_AFTER_CASE')
        self.cleanup_verified = t.owned is None and not t.pending_effects


def execute(c, base_ref, components):
    c.need(os.getuid() == os.geteuid() == 0, 'ROOT_EXPLICIT_NEW_CAMERA_CASE')
    base = c.parse(c.read_ref(base_ref)); plan = components['camera_plan.py']; runtime = components['camera_runtime.py']
    host = components['app_runtime.py']; _, support = c.support(base['support_manifest'])
    baseline = support['business_baseline.py'].BusinessBaseline(base['baseline'], base['qualification'])
    plan.validate(c, base, baseline)
    root = c.private_dir(base['case_root']); c.write_new(root / 'execute-once.json', {
        'plan': base_ref, 'operator': host.process(c, os.getpid()), 'started_utc': stamp(), 'automatic_retry': False})
    evidence = c.private_dir(root / 'evidence', create=True)
    result = {'schema': 'pocket4-final-camera-photo-result-v1', 'state': 'FAILED', 'plan': base_ref,
        'started_utc': stamp(), 'photo_capture_persistence_verified': False,
        'camera_business_gates_complete': False, 'whole_app_business_accepted': False,
        'visual_review_required': True, 'video_audio_playback_qualified': False,
        'camera_recovery_qualified': False, 'automatic_retry': False, 'secondary_errors': []}
    session = case = lock = witness = None; first = None; retiring = False; signals = []
    def interrupted(signum, frame):
        nonlocal retiring
        signals.append(signum)
        if not retiring:
            retiring = True; raise CaseInterrupted('CAMERA_CASE_INTERRUPTED')
    def remember(label, error):
        nonlocal first
        value = {'phase': label, 'type': type(error).__name__, 'message': str(error)}
        if first is None:
            first = error; result['error'] = value
        else:
            result['secondary_errors'].append(value)
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, interrupted)
    try:
        lock = runtime.ActionLock(c, host, root)
        lease = runtime.create_lease(c, host, base_ref, base)
        active_ref, scopes = plan.activate(c, base_ref, lease, lock.ref)
        active = c.parse(c.read_ref(active_ref)); phase = runtime.phase(c, host, active_ref, active, 'business')
        witness = c.EvidenceWitness([base_ref, active_ref, lease, lock.ref, *scopes])
        session = components['camera_session.py'].Session(c, active_ref, active, scopes, phase, lock, components, evidence)
        case = PhotoCase(session, result)
        result.update(active_plan=active_ref, recorder_scopes=scopes, actual_business_phase=phase)
        try:
            case.run()
        except BaseException as error:
            remember('original_photo_business', error)
        finally:
            retiring = True
            try:
                trigger = c.write_new(root / 'cleanup-trigger.json', {'actual_business_error': result.get('error'),
                    'original_photo_completed': case.run_completed, 'automatic_retry': False, 'started_utc': stamp()})
                result['actual_cleanup_phase'] = session.begin_cleanup(trigger)
                case.finish()
            except BaseException as error:
                remember('original_photo_cleanup_and_readback', error)
    except BaseException as error:
        remember('camera_construction_or_admission', error)
    finally:
        retiring = True
        for obj, label in ((session, 'current_Main_APIs'), (lock, 'whole_case_OFD'), (witness, 'evidence_witness')):
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
            remember('cancelled_before_terminal_commit', CaseInterrupted('CAMERA_CANCELLED_BEFORE_TERMINAL_COMMIT'))
        result['cancellation_commit'] = {'observed_before_commit': list(signals),
            'pending_at_commit': pending, 'decision_frozen_after_context_exit': True}
        if case is not None:
            t = case.trial
            result.update(native_launch_calls=t.launch_calls, shutter_calls=t.shutter_calls,
                own_task_remove_calls=t.remove_calls, pending_effects=sorted(t.pending_effects),
                owned_task_remaining=t.owned, outcome_unknown=bool(t.pending_effects),
                own_task_cleanup_verified=case.cleanup_verified)
            result['photo_capture_persistence_verified'] = bool(case.run_completed and case.cleanup_verified
                and first is None and not signals and not pending and not result['secondary_errors'])
        result['state'] = ('PHOTO_CAPTURE_PERSISTENCE_VERIFIED_VISUAL_AND_OTHER_APP_GATES_PENDING'
                           if result['photo_capture_persistence_verified'] else 'FAILED_OR_UNKNOWN_RETAINED')
        result.update(received_signals=signals, finished_utc=stamp(), whole_app_business_accepted=False,
            Binder_UID_cleanup_verified=False, automated_rollback=False, prior_photos_modified_or_deleted=False)
        result_ref = c.write_new(root / 'result.json', result)
    return result_ref, result
