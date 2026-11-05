#!/usr/bin/env python3
"""Project the completed Timer04 core result; no device calls or registry edits."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / 'timer-regression04-public'
RAW_SHA = 'bc3fd55145039228f27f7ef0a23e48f899cc4b1a64d0f8fb06cdc9e4545feebb'
SCHED_SHA = '1215cc30cb7d21b29b42f06ef3a5525d7fd93412641e07b342de5beb4c95cb52'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def native(path):
    tool = json.loads(path.read_bytes())
    return tool.get('structuredContent') or json.loads(next(b['text'] for b in tool['content'] if b['type'] == 'text'))


def main():
    raw = (HERE / 'result04-original.json').read_bytes()
    assert sha(raw) == RAW_SHA and len(raw) == 37124
    result = json.loads(raw)
    scheduler_raw = (HERE / 'SCHEDULER_INDEPENDENT_REVIEW04.json').read_bytes()
    assert sha(scheduler_raw) == SCHED_SHA
    scheduler = json.loads(scheduler_raw)
    status = native(HERE / 'status04-03-tool-original.json')
    assert status['state'] == 'succeeded' and status['exit_code'] == 0
    assert status['output_complete'] and status['output_durable'] and not status['timed_out']
    assert result['state'] == 'OWNED_TIMER_CORE_FLOW_VERIFIED_CLEAN' and result['business_success_verified']
    assert result['owned_tasks'] == result['closed_tasks'] == [996, 997]
    assert all(result.get(k) is None for k in ('pending_effect', 'pending_timer_effect', 'close_pending',
        'owned_task_remaining', 'error', 'terminal_error', 'cleanup_error'))
    assert result['identity_before'] == result['identity_after']
    assert result['identity_after']['apk_sha256'] == '433ff501b92a21bb9265c896add220b52bc16fc4124662eaf45310da99243a0d'
    assert result['protected_business_and_sound_state_preserved']
    assert result['templates_sha_before'] == result['templates_sha_after']
    assert result['protected_before']['tasks_sha256'] == result['protected_after']['tasks_sha256']
    phases = result['phases']
    assert phases['paused'] == phases['paused-stable'] == phases['after-normal-close'] == phases['after-reopen']
    assert phases['paused']['timers'][0]['remaining_ms'] == 891266
    assert phases['paused-after-resume']['timers'][0]['remaining_ms'] == 881985
    assert phases['reset']['timers'][0]['remaining_ms'] == 900000
    assert result['timer_final'] == {'ids': [], 'stopwatch': {}, 'timers': [], 'values': {}}
    OUT.mkdir()
    manifest = []

    def put(name, value, exact=False):
        data = value if exact else encode(value)
        path = OUT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(data)
        item = {'path': name, 'bytes': len(data), 'sha256': sha(data)}
        manifest.append(item)
        return item

    terminal = {'schema': 'clock-timer04-selected-actual-core-result/v1',
        'original_result': {'bytes': len(raw), 'sha256': RAW_SHA},
        **{k: result[k] for k in ('state', 'started_utc', 'finished_utc', 'business_success_verified',
            'ui_actions', 'owned_timer_id', 'owned_tasks', 'closed_tasks', 'owned_task_remove_calls',
            'owned_task_remaining', 'pending_effect', 'pending_timer_effect', 'close_pending',
            'epoch_sha256', 'actual_install_binding', 'identity_before', 'identity_after',
            'timer_final', 'protected_business_and_sound_state_preserved', 'scheduler_cancellation_verified',
            'timer_expiry_qualification', 'alarm_write_actions', 'global_volume_or_ringtone_actions',
            'notification_permission_actions')},
        'core_phases': {k: {'timer_ids': phases[k]['ids'], 'owned_timers': phases[k]['timers']}
                        for k in ('before', 'created-running', 'paused', 'paused-stable',
                                  'after-normal-close', 'after-reopen', 'resumed', 'paused-after-resume', 'reset', 'deleted')},
        'original_alarm_content_digest_before': result['templates_sha_before'],
        'original_alarm_content_digest_after': result['templates_sha_after'],
        'original_alarm_ids': [1, 2], 'both_original_alarms_disabled_before_after': True,
        'alarm_instance_count_before_after': 0,
        'baseline_task_text_sha256': result['protected_after']['tasks_sha256'],
        'protected_before_canonical_JSON_sha256': sha(encode(result['protected_before'])),
        'protected_after_canonical_JSON_sha256': sha(encode(result['protected_after'])),
        'raw_sound_preferences_and_original_alarm_contents_omitted': True,
        'original_result_modified': False,
        'independent_scheduler_review': 'SCHEDULER_INDEPENDENT_REVIEW04.json',
        'completion_timezone_notification_interaction_and_audio_credit': False,
        'whole_app_production_ready': False}
    put('TIMER04_TERMINAL_SELECTED.json', terminal)
    put('SCHEDULER_INDEPENDENT_REVIEW04.json', scheduler_raw, exact=True)
    put('TERMINAL_JOB_SELECTED.json', {k: status[k] for k in ('job_id', 'state', 'exit_code',
        'output_complete', 'output_durable', 'timed_out', 'automatic_retry', 'log_bytes')})
    sources = ['timer_core04.py', 'read_clock_expired_text02.py', 'timer03-to-timer04-pending-fences.patch',
        'timer04-actual-install-binding.patch', 'timer04-single-cleanup-deadline.patch',
        'validate_pending04.py', 'PENDING_BOUNDARIES_BOUND04.json', 'STAGE_PAYLOAD_REVIEW.json',
        'ROOT_ADMISSION_REVIEW.json', 'FORMAL_HANDOFF_TO_ROOT04.json', 'review_saved_scheduler04.py',
        'prepare_publication04.py']
    for name in sources:
        put('source/' + name, (HERE / name).read_bytes(), exact=True)
    put('source/INDEPENDENT_DEADLINE_PEER.json',
        (HERE.parent / 'timer-regression04-peer-recover/REVIEW_59598.json').read_bytes(), exact=True)
    put('source/capture_saved_alarm_timer04.py',
        (HERE.parent / 'alarm-route04/capture_saved_alarm_timer04.py').read_bytes(), exact=True)
    evidence = [dict(item, path='inputs/clock-timer04/' + item['path']) for item in manifest
                if item['path'] in ('TIMER04_TERMINAL_SELECTED.json', 'SCHEDULER_INDEPENDENT_REVIEW04.json',
                                   'TERMINAL_JOB_SELECTED.json')]
    put('SCOPED_REVIEW_PROPOSAL.json', {'schema': 'clock-timer04-scoped-review-proposal/v1',
        'state': 'PROPOSED_FOR_ROOT_REVIEW_NOT_APPLIED', 'registry_edits': 0,
        'proposed_gate_review': {'id': 'clock_timer04_current433ff_ui_and_lifecycle',
            'package': 'com.android.deskclock', 'uid': 10063, 'android_user': 0, 'version_code': 37,
            'apk_sha256': result['identity_after']['apk_sha256'], 'framework_epoch_sha256': result['epoch_sha256'],
            'observed_at_utc': result['finished_utc'], 'reviewed_at_utc': datetime.now(timezone.utc).isoformat(),
            'reviewer': 'camera_runtime_review_actual_timer04_with_independent_root_result_review',
            'scope': 'scoped', 'checks': {'ui_observation': 'passed', 'lifecycle': 'passed'}, 'evidence': evidence,
            'qualification_scope': 'This exact current APK: real owned timer controls, exact readback, two owned normal task closes and paused-state reopen.',
            'unresolved_findings': [
                'clock.timer explicitly includes completion; this core trial deliberately did not expire.',
                'clock.persist explicitly includes alarm/timezone behavior; timer persistence does not satisfy it.',
                'The original scheduler_cancellation_verified=false is preserved; the separate saved review verifies the current cancellation records.',
                'No stress, audio output, real desktop notification interaction or complete release-scope qualification is granted.',
                'No business qualification from a prior APK is inherited.']},
        'clock_timer_complete_gate_passed': False, 'clock_persist_gate_passed': False,
        'whole_app_production_ready': False})
    put('README.md', (
        '# Clock Timer04 on installed 433ff\n\n'
        'The real trial succeeded on 2026-11-05 from 21:48:44.088668 to 21:50:38.976796 UTC. '
        'Eleven native inputs created one 15-minute timer, paused it, closed and reopened its owned task, '
        'resumed, paused, reset and deleted it. The paused value stayed exactly 891266 ms across normal '
        'close/reopen; the second pause was 881985 ms and reset was 900000 ms. Timer0 was the same object '
        'throughout. Tasks996 and997 were both normally removed. All three pending fields are empty and '
        'the final timer/stopwatch state is empty. The two original disabled alarms and protected sound/permission '
        'state were preserved.\n\n'
        'A separate review of the already saved scheduler dumps proves the current pending sequence '
        '0→1→0→1→0→0. Both active operations were foreground-service timer PendingIntents, with exact '
        'deadlines derived from this timer. Historical TIMER_EXPIRED lines are explicitly excluded. The '
        'original result and its conservative scheduler field are unchanged.\n\n'
        'Only UI observation and lifecycle are proposed. The frozen clock.timer gate also requires completion '
        'on this APK; clock.persist mentions alarm/timezone behavior. Neither full gate is granted here. '
        'Sound, notification interaction, stress and whole-App release are also outside this evidence.\n\n'
        'Full raw protected snapshots, sound/preferences, global alarm dumps and request payload are omitted. '
        'Their hashes and the exact selection source remain recorded; only Clock-owned selected records '
        'and safe controller/review sources are included.\n'
    ).encode(), exact=True)
    omitted = []
    for path, reason in ((HERE / 'result04-original.json', 'Full protected state and raw alarm-line context remain private.'),
                         (HERE.parent / 'alarm-route04/selected-route04.json', 'Only independent Clock scheduler classification is included here; full notification/source export is separate.'),
                         (HERE / 'stage-execute-request04.json', 'Full request payload omitted; exact pin is retained in the payload review.')):
        value = path.read_bytes()
        omitted.append({'name': path.name, 'bytes': len(value), 'sha256': sha(value), 'reason': reason})
    proof = {'schema': 'clock-timer04-public-delta-manifest/v1',
        'publication_prefix_suggestion': 'inputs/clock-timer04', 'files': sorted(manifest, key=lambda x: x['path']),
        'omitted_originals': omitted, 'raw_original_result_modified': False,
        'readiness_registry_modified': False, 'new_Android_or_UI_calls': 0,
        'current_APK_only': True, 'whole_app_production_ready': False}
    data = encode(proof)
    with (OUT / 'SOURCE_MANIFEST.json').open('xb') as stream:
        stream.write(data)
    assert sha((HERE / 'result04-original.json').read_bytes()) == RAW_SHA
    print(json.dumps({'directory': str(OUT), 'files': len(manifest),
        'manifest_bytes': len(data), 'manifest_sha256': sha(data)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    if parser.parse_args().write:
        main()
    else:
        print(json.dumps({'state': 'PLAN_ONLY', 'writes': 0, 'device_calls': 0}))
