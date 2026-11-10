#!/usr/bin/env python3
"""Independently classify exact saved Timer04 current alarms, without device access."""
from pathlib import Path
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent
CORE_SHA = 'bc3fd55145039228f27f7ef0a23e48f899cc4b1a64d0f8fb06cdc9e4545feebb'
EXPORT_SHA = '81b12baa291b0d93cf30cb0933949129478fa12448aec6852c7f1b9c5f13af18'
APK = '433ff501b92a21bb9265c896add220b52bc16fc4124662eaf45310da99243a0d'


def read(path, pin):
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == pin
    return json.loads(raw)


def main():
    core = read(HERE / 'result04-original.json', CORE_SHA)
    export = read(HERE.parent / 'alarm-route04/selected-route04.json', EXPORT_SHA)
    saved = export['timer_scheduler']
    assert saved['original_result_sha256'] == CORE_SHA and saved['original_result_modified'] is False
    assert core['business_success_verified'] is True and core['identity_before'] == core['identity_after']
    assert core['identity_after']['apk_sha256'] == APK
    assert core['scheduler_cancellation_verified'] is False
    assert core['timer_final'] == {'ids': [], 'stopwatch': {}, 'timers': [], 'values': {}}
    expected = {'before': 0, 'created-running': 1, 'paused': 0,
                'resumed': 1, 'paused-after-resume': 0, 'deleted': 0}
    assert set(saved['observations']) == set(expected)
    phases = []
    for phase, wanted in expected.items():
        obs = saved['observations'][phase]
        original = core['scheduler_observations'][phase]
        assert obs['raw_sha256'] == original['sha256'] and obs['raw_bytes'] == original['bytes']
        assert obs['observed_utc'] == original['observed_utc']
        assert len(obs['current_clock_records']) == obs['clock_uid_current_pending_count'] == wanted
        assert obs['historical_Clock_tags_not_current']
        records = []
        for record in obs['current_clock_records']:
            assert re.fullmatch(r'  \d+ pending alarms: ', record['section'])
            lines = record['owned_record_lines']
            header = re.fullmatch(r'    ELAPSED_WAKEUP #\d+: Alarm\{\w+ type 2 origWhen (\d+) whenElapsed (\d+) com\.android\.deskclock\}', lines[0])
            assert header and header[1] == header[2]
            assert lines[1].strip() == 'tag=*walarm*:com.android.deskclock.action.TIMER_EXPIRED'
            operations = [x for x in lines if 'operation=PendingIntent{' in x]
            assert len(operations) == 1 and 'com.android.deskclock startForegroundService' in operations[0]
            own = core['phases'][phase]['timers']
            assert len(own) == 1 and own[0]['id'] == core['owned_timer_id'] == 0 and own[0]['state'] == 1
            due = own[0]['last_start_ms'] + own[0]['remaining_ms']
            assert int(header[2]) == due
            records.append({'type': 'ELAPSED_WAKEUP', 'operation_type': 'startForegroundService',
                'action': 'com.android.deskclock.action.TIMER_EXPIRED', 'due_uptime_ms': due,
                'exact_owned_timer_ID_and_deadline_match': True, 'source_line_number': record['source_line_number'],
                'original_owned_record_sha256': hashlib.sha256(('\n'.join(lines) + '\n').encode()).hexdigest()})
        phases.append({'phase': phase, 'observed_utc': obs['observed_utc'],
            'original_raw_bytes': obs['raw_bytes'], 'original_raw_sha256': obs['raw_sha256'],
            'clock_UID_pending_count': obs['clock_uid_current_pending_count'],
            'current_pending_records': records,
            'historical_timer_tag_count_excluded': len(obs['historical_Clock_tags_not_current'])})
    result = {'schema': 'clock-timer04-independent-saved-scheduler-review/v1',
        'state': 'CURRENT_APK_SCHEDULE_PAUSE_RESUME_AND_CANCEL_VERIFIED',
        'package': 'com.android.deskclock', 'uid': 10063, 'android_user': 0,
        'apk_sha256': APK, 'framework_epoch_sha256': core['epoch_sha256'],
        'original_result_sha256': CORE_SHA, 'saved_export_sha256': EXPORT_SHA,
        'original_started_utc': core['started_utc'], 'original_finished_utc': core['finished_utc'],
        'original_result_modified': False, 'original_scheduler_cancellation_verified': False,
        'independent_saved_scheduler_cancellation_verified': True,
        'phases': phases, 'new_Android_or_UI_calls': 0,
        'historical_string_presence_not_equated_to_current_pending': True,
        'limits': ['This is a review of saved observations, not a fresh runtime query.',
            'Only the exact one Timer04 fixture and UID10063 records are classified.',
            'Completion on current APK, real notification interaction, timezone behavior and physical audio remain unverified here.'],
        'clock_timer_complete_gate_passed': False, 'whole_app_production_ready': False}
    raw = (json.dumps(result, indent=2, sort_keys=True) + '\n').encode()
    with (HERE / 'SCHEDULER_INDEPENDENT_REVIEW04.json').open('xb') as stream:
        stream.write(raw)
    print(len(raw), hashlib.sha256(raw).hexdigest())


if __name__ == '__main__':
    main()
