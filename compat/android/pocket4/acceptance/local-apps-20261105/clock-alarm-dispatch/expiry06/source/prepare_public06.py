#!/usr/bin/env python3
"""Make a text-only projection of expiry06; preserve every private original."""
from pathlib import Path
import hashlib
import json
import shutil

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / 'timer-expiry06-public'
RESULT_SHA = '6b584428d4145416d26c72400ab966b9be8df185aec35655177ad799f62ea86e'
REVIEW_SHA = '72f702d90cb2d16a5c680cdf7fa353c370874a0e8222c96f7b3789cc24d35aa5'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path):
    raw = path.read_bytes()
    return {'path': path.name, 'bytes': len(raw), 'sha256': sha(raw)}


def write(name, value):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as out:
        out.write(json.dumps(value, sort_keys=True, indent=2) + '\n')


def packet(name):
    value = json.loads((HERE / name).read_text())
    return value.get('structuredContent') or json.loads(next(c['text'] for c in value['content'] if c['type'] == 'text'))


def main():
    raw = (HERE / 'result06-original.json').read_bytes()
    assert len(raw) == 38001 and sha(raw) == RESULT_SHA
    result = json.loads(raw)
    reviewed_raw = (HERE / 'INDEPENDENT_SAVED_REVIEW06.json').read_bytes()
    assert sha(reviewed_raw) == REVIEW_SHA
    review = json.loads(reviewed_raw)
    status = packet('process-status06-02-original.json')
    assert status['state'] == 'succeeded' and status['exit_code'] == 0
    assert status['output_complete'] and status['output_durable'] and not status['timed_out']
    assert result['business_success_verified'] is True
    assert result['guard_before'] == result['guard_after']
    assert result['identity_before'] == result['identity_after']
    assert result['alarms_before'] == result['alarms_after']
    assert result['templates_sha_before'] == result['templates_sha_after']
    assert result['protected_business_and_sound_state_preserved'] is True
    assert result['scheduler_cancellation_verified'] is False
    assert all(result[key] is None for key in ('pending_effect', 'pending_timer_effect', 'close_pending',
                                             'remaining_timer_id', 'owned_task_remaining'))
    assert review['final_tasks'] == [851]
    OUT.mkdir()
    selected_keys = ('schema', 'state', 'started_utc', 'finished_utc', 'business_scope_completed',
        'business_success_verified', 'actual_expiry_verified', 'actual_expired_notification_posted',
        'actual_expired_main_window_observed', 'new_alert_task_observed', 'full_screen_pending_intent_present',
        'desktop_popup_observed', 'host_notification_action_invoked', 'host_audio_or_speaker_verified',
        'actual_install_binding', 'identity_before', 'identity_after', 'old_binary_expiry_credit_inherited',
        'owned_timer_id', 'remaining_timer_id', 'timer_duration_ms', 'timer_final', 'stop_dispatched',
        'stop_reconciliation', 'owned_tasks', 'closed_tasks', 'normal_remove_calls', 'owned_task_remaining',
        'pending_effect', 'pending_timer_effect', 'close_pending', 'alert_self_finished', 'task_set_restored',
        'ui_actions', 'alarm_writes', 'direct_preference_or_provider_writes', 'timer_mutations_via_UI_only',
        'global_volume_or_ringtone_actions', 'notification_permission_actions', 'automatic_retry',
        'scheduler_cancellation_verified', 'scheduler_requires_saved_review', 'whole_app_production_ready')
    selected = {key: result[key] for key in selected_keys}
    selected.update(original_result=pin(HERE / 'result06-original.json'), original_result_modified=False,
        strict_Main_epoch_sha256=result['guard_after']['epoch_sha256'], strict_Main_before_after_equal=True,
        actual_alarm_templates_before_after_equal=True, original_disabled_alarm_ids=[1, 2],
        original_alarm_instances_before_after=0, protected_business_and_sound_state_preserved=True,
        original_alarm_content_sha256=result['templates_sha_before'], preferences_bytes_equality_not_claimed=True,
        final_saved_tasks=[851], error=result.get('error'), terminal_error=result.get('terminal_error'),
        cleanup_error=result.get('cleanup_error'))
    selected['owned_timer_phases'] = {name: {key: value[key] for key in ('ids', 'timers', 'stopwatch')}
        for name, value in result['phases'].items()}
    selected['expiry_timing'] = {key: result['expiry_timing'][key]
        for key in ('created_start_ms', 'expected_due_ms', 'observed_uptime_ms')}
    selected['expiry_timing']['observation_after_due_ms'] = review['actual_observed_expiry_delay_ms']
    selected['owned_notification_observations'] = review['notifications']
    selected['protected_private_originals'] = {
        name: {'canonical_json_sha256': sha((json.dumps(result[name], sort_keys=True, separators=(',', ':')) + '\n').encode())}
        for name in ('protected_before', 'protected_after')}
    write('EXPIRY06_TERMINAL_SELECTED.json', selected)
    write('TERMINAL_JOB_SELECTED.json', {key: status[key] for key in ('job_id', 'state', 'exit_code',
        'output_complete', 'output_durable', 'timed_out', 'cancelled', 'automatic_retry', 'log_bytes')})
    proposal = {'schema': 'pocket4-current-clock-timer-review-proposal/v1',
        'decision_owner': 'root', 'registry_modified': False, 'frozen_checkpoint11_modified': False,
        'package': 'com.android.deskclock', 'uid': 10063, 'android_user': 0,
        'apk_sha256': result['identity_after']['apk_sha256'],
        'frozen_gate_literal': 'Start/pause/resume an owned timer and observe completion.',
        'suggested_scope': 'clock.timer only, using both current-APK fixtures together',
        'separate_fixtures': [
            {'trial': 'Timer04', 'duration_ms': 900000,
             'original_result_sha256': 'bc3fd55145039228f27f7ef0a23e48f899cc4b1a64d0f8fb06cdc9e4545feebb',
             'public_manifest_sha256': '8281910ffd94acee97292d635bd94f0e76eaea1c959f661ec756a534c0ae58e2',
             'scheduler_review_sha256': '1215cc30cb7d21b29b42f06ef3a5525d7fd93412641e07b342de5beb4c95cb52',
             'actual_scope': 'UI create/start/pause, normal close/reopen preserving paused remaining, resume/pause/reset/delete; independent pending sequence0,1,0,1,0,0.'},
            {'trial': 'Expiry06', 'duration_ms': 60000, 'original_result_sha256': RESULT_SHA,
             'saved_review_sha256': REVIEW_SHA,
             'actual_scope': 'UI create/start, normal close, actual persisted expiry and active own NMS record, native main-window Stop/reset and UI delete; pending sequence0,1,0,0.'}],
        'each_fixture_started_and_ended_empty': True,
        'same_numeric_ID_does_not_mean_same_object_across_trials': True,
        'old_APK_business_credit_inherited': False,
        'original_scheduler_false_fields_preserved': True,
        'not_qualified_by_this_bundle': ['clock.alarm actual user Dismiss',
            'clock.persist alarm/timezone behavior', 'desktop notification Open/Dismiss',
            'physical audio', 'whole Clock production readiness']}
    write('SCOPED_REVIEW_PROPOSAL.json', proposal)
    original_files = ('result06-original.json', 'private-saved-evidence06.json',
        'private-saved-evidence06.json.gz', 'stage-execute-request06.json',
        'export-saved06-request.json', 'result06-binary-01-original.json', 'export-binary06-original.json')
    write('PRIVATE_ORIGINALS_RETAINED.json', {'schema': 'clock-expiry06-projection-omissions/v1',
        'originals_retained_unchanged': True, 'publication_is_text_only': True,
        'omitted_files': [{**pin(HERE / name), 'reason':
            ('Full raw protected snapshots/global scheduler/notification journal remain private; only owned Clock fields are selected.'
             if 'request' not in name else 'Full executable request payload is omitted; exact request hash remains bound.')}
            for name in original_files]})
    copies = {
        'INDEPENDENT_SAVED_REVIEW06.json': 'INDEPENDENT_SAVED_REVIEW06.json',
        'FORMAL_CLEAN_HANDOFF06.json': 'FORMAL_CLEAN_HANDOFF06.json',
        'source/timer_expiry06.py': 'timer_expiry06.py',
        'source/timer_core04.py': 'timer_core04.py',
        'source/read_clock_expired_text02.py': 'read_clock_expired_text02.py',
        'source/test_expiry06_boundaries.py': 'test_expiry06_boundaries.py',
        'source/expiry06-root-review-fixes.patch': 'expiry06-root-review-fixes.patch',
        'source/stage-execute06.py': 'stage-execute06.py',
        'source/export_saved06.py': 'export_saved06.py',
        'source/review_saved06.py': 'review_saved06.py',
        'source/prepare_public06.py': 'prepare_public06.py',
        'reviews/ROOT_ADMISSION_REVIEW.json': 'ROOT_ADMISSION_REVIEW.json',
        'reviews/ROOT_FORMAL_UI_HANDOFF.json': 'ROOT_FORMAL_UI_HANDOFF.json',
        'reviews/DOCS_PEER_REVIEW.json': 'DOCS_PEER_REVIEW.json',
        'reviews/SOURCE_REVIEW.json': 'SOURCE_REVIEW.json',
        'reviews/STAGE_PAYLOAD_REVIEW.json': 'STAGE_PAYLOAD_REVIEW.json',
        'reviews/LOCAL_VALIDATION.json': 'LOCAL_VALIDATION.json',
        'reviews/boundary-tests.stderr': 'boundary-tests.stderr',
        'reviews/execution-source-manifest.json': 'SOURCE_MANIFEST.json',
        'metadata/terminal-status-original.json': 'process-status06-02-original.json',
        'metadata/stdout-original.txt': 'stdout06-original.txt',
        'metadata/saved-export-status-original.json': 'export-status06-original.json'}
    for target, source in copies.items():
        path = OUT / target
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(HERE / source, path)
        assert path.read_bytes() == (HERE / source).read_bytes()
    readme = '''# Current Clock expiry06: actual expiry, Stop and cleanup

The only real trial ran on 2026-11-05 from 22:40:34.602818 to 22:42:42.574016 UTC, using installed Clock APK433ff501 and the original strict Main resource profile. Job5b48 succeeded with complete durable output. Six native UI inputs created one60-second timer, started it, later stopped the expired timer and deleted it. There was no input replay or direct Provider/preferences write.

The same timer0 changed from RUNNING to EXPIRED. The saved observation saw that state1037ms after its exact scheduled deadline. The Clock-owned expiry notification was active. No new full-screen task appeared; a normal native launch reopened Clock, where the actual Stop control was selected in its owned window. Its native ACK matched the full fresh selector, and a separate exact readback proved timer0 reset to60000ms before UI deletion. Final timer/stopwatch state and active Clock notifications were empty. Owned tasks1003 and1004 were normally removed, final saved tasks were851, and all three pending fields were empty. The original two disabled alarms, APK/UID, notification permission, protected data identity, audio settings and strict Main identity were preserved. Equality of all preference-file bytes is not claimed.

The independent offline review hashes all four exact saved scheduler dumps. It distinguishes the active pending sequence0→1→0→0 from historical TIMER_EXPIRED strings and proves the only pending timer operation used startForegroundService at the exact owned deadline. This expiry naturally left the scheduler store; separate current-APK Timer04 evidence covers pause/resume cancellation. Both original scheduler_cancellation_verified=false fields remain unchanged. Timer04 and Expiry06 were separate fixtures, each starting and ending with no timer; reusing numeric ID0 does not join them into one object.

Together with current-APK Timer04, this supports review of the frozen clock.timer start/pause/resume/completion requirement. Root owns any registry decision. This bundle grants no alarm Dismiss, timezone, desktop popup/action, physical audio or whole-App readiness. No old-binary business credit is inherited.

All production controller and review source copies are byte-exact. The14 existing host boundary cases use explicit Android/native/task/clock doubles and retained historical local fixtures; their original output is included, and they are not substituted for the real trial. The private raw originals, all-app alarm dumps, protected snapshots and executable request payloads remain outside this text-only projection. Hashes and omission reasons are explicit. The prior checkpoint11 is unchanged.
'''
    (OUT / 'README.md').write_text(readme)
    files = []
    for path in sorted(OUT.rglob('*')):
        if path.is_file():
            item = pin(path)
            item['path'] = path.relative_to(OUT).as_posix()
            files.append(item)
    manifest = {'schema': 'pocket4-clock-expiry06-public-projection/v1', 'files': files,
        'original_execution_manifest': pin(HERE / 'SOURCE_MANIFEST.json'),
        'original_result_sha256': RESULT_SHA, 'independent_saved_review_sha256': REVIEW_SHA,
        'current_APK_only': True, 'original_receipts_modified': False,
        'private_raw_dump_contents_included': False, 'new_Android_or_UI_calls': 0,
        'registry_or_checkpoint11_modified': False, 'whole_app_production_ready': False}
    write('SOURCE_MANIFEST.json', manifest)
    print(json.dumps({'directory': str(OUT), 'files': len(files), 'manifest': pin(OUT / 'SOURCE_MANIFEST.json')}))


if __name__ == '__main__':
    main()
