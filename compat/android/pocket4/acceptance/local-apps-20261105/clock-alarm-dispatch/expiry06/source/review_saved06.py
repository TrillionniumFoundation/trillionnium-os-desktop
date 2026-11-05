#!/usr/bin/env python3
"""Offline, Clock-only classification of the exact expiry06 saved journal."""
from pathlib import Path
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent
RESULT_SHA = '6b584428d4145416d26c72400ab966b9be8df185aec35655177ad799f62ea86e'
EXPORT_SHA = '41a9ffd9b73efc62efa48c533c543363b7baab35083241ff3f2416dfd9c596e6'
APK_SHA = '433ff501b92a21bb9265c896add220b52bc16fc4124662eaf45310da99243a0d'
KEY = '0|com.android.deskclock|2147483644|null|10063'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(name, pin):
    raw = (HERE / name).read_bytes()
    assert sha(raw) == pin
    return json.loads(raw)


def classify_scheduler(item, phase, expected_count, due):
    raw = item['raw'].encode()
    assert sha(raw) == item['sha256'] and len(raw) == item['bytes']
    lines = item['raw'].splitlines()
    headers = [line for line in lines if re.fullmatch(r'  Pending alarms per uid: \[.*\]', line)]
    assert len(headers) == 1
    counts = re.findall(r'\bu0a63:(\d+)\b', headers[0])
    assert len(counts) <= 1
    uid_count = int(counts[0]) if counts else 0
    current, current_lines = [], set()
    for index, line in enumerate(lines):
        match = re.fullmatch(r'    ELAPSED_WAKEUP #\d+: Alarm\{\w+ type 2 origWhen (\d+) whenElapsed (\d+) com\.android\.deskclock\}', line)
        if not match:
            continue
        preceding = [v for v in lines[:index] if v.strip() and len(v) - len(v.lstrip()) <= 2]
        assert preceding and re.fullmatch(r'  \d+ pending alarms: ', preceding[-1])
        block = [line]
        current_lines.add(index)
        for following in range(index + 1, len(lines)):
            value = lines[following]
            if value.strip() and len(value) - len(value.lstrip()) <= 4:
                break
            block.append(value)
            current_lines.add(following)
        operations = [v for v in block if 'operation=PendingIntent{' in v]
        assert block[1].strip() == 'tag=*walarm*:com.android.deskclock.action.TIMER_EXPIRED'
        assert len(operations) == 1 and 'com.android.deskclock startForegroundService' in operations[0]
        assert int(match[1]) == int(match[2]) == due
        current.append({'source_line_number': index + 1, 'type': 'ELAPSED_WAKEUP',
            'operation_type': 'startForegroundService',
            'action': 'com.android.deskclock.action.TIMER_EXPIRED', 'due_uptime_ms': due,
            'exact_owned_timer_deadline_match': True, 'record_sha256': sha(('\n'.join(block) + '\n').encode())})
    historical = [line for index, line in enumerate(lines)
                  if 'com.android.deskclock.action.TIMER_EXPIRED' in line and index not in current_lines]
    assert len(current) == uid_count == expected_count
    return {'phase': phase, 'raw_bytes': len(raw), 'raw_sha256': sha(raw),
        'observed_utc': item['observed_utc'], 'uptime_ms': item['uptime_ms'],
        'clock_UID_current_pending_count': uid_count, 'current_records': current,
        'historical_timer_tags_excluded': len(historical),
        'raw_global_UID_header_sha256': sha(headers[0].encode()),
        'other_application_records_published': False}


def active_notifications(item):
    raw = item['raw'].encode()
    assert sha(raw) == item['sha256'] and len(raw) == item['bytes']
    lines = item['raw'].splitlines()
    assert lines[0] == "Current Notification Manager state (filtered to 'com.android.deskclock'):"
    starts = [i for i, line in enumerate(lines) if line == '  Notification List:']
    assert len(starts) == 1
    body = []
    for line in lines[starts[0] + 1:]:
        if line.strip() and not line.startswith('    '):
            break
        body.append(line)
    if not '\n'.join(body).strip():
        return []
    blocks = re.split(r'(?=^    NotificationRecord\()', '\n'.join(body), flags=re.M)
    assert not blocks[0].strip()
    result = []
    for block in blocks[1:]:
        assert re.search(r'\bpkg=com\.android\.deskclock\b', block.splitlines()[0])
        assert 'user=UserHandle{0}' in block and re.search(r'\buid=10063\b', block)
        keys = set(re.findall(r'\bkey=(0\|com\.android\.deskclock\|[0-9]+\|null\|10063)\b', block))
        assert keys == {KEY}
        assert re.search(r'\bchannel=TimerModelNotification\b', block) or "mId='TimerModelNotification'" in block
        result.append({'key': KEY, 'uid': 10063, 'android_user': 0, 'channel': 'TimerModelNotification',
            'record_sha256': sha(block.encode()),
            'full_screen_pending_intent_present': bool(re.search(r'\bfullscreenIntent=PendingIntent\{', block)),
            'desktop_popup_or_sound_observed': False})
    return result


def main():
    actual = read('result06-original.json', RESULT_SHA)
    saved = read('private-saved-evidence06.json', EXPORT_SHA)
    assert saved['source_result']['sha256'] == RESULT_SHA
    assert actual['business_success_verified'] and actual['actual_expiry_verified']
    assert actual['identity_before'] == actual['identity_after']
    assert actual['identity_after']['apk_sha256'] == APK_SHA
    assert actual['scheduler_cancellation_verified'] is False
    running = actual['phases']['created-running']['timers']
    assert len(running) == 1 and running[0]['id'] == actual['owned_timer_id'] == 0
    assert running[0]['state'] == 1 and running[0]['length_ms'] == 60000
    due = running[0]['last_start_ms'] + running[0]['remaining_ms']
    assert due == actual['expiry_timing']['expected_due_ms']
    expired = actual['phases']['expired']
    assert expired['ids'] == [0] and len(expired['timers']) == 1
    expired_item = expired['timers'][0]
    assert expired_item['id'] == 0 and expired_item['state'] == 3
    assert expired_item['length_ms'] == 60000 and expired_item['total_length_ms'] == 0
    assert expired_item['remaining_ms'] <= 0
    assert due - 1000 <= expired_item['last_start_ms'] <= actual['expiry_timing']['observed_uptime_ms'] + 10
    assert due - 1000 <= actual['expiry_timing']['observed_uptime_ms'] <= due + 25000
    expected = {'before': 0, 'created-running': 1, 'actual-expired': 0, 'final-deleted': 0}
    assert set(saved['scheduler']) == set(expected)
    phases = []
    for phase, count in expected.items():
        original = actual['scheduler_observations'][phase]
        item = saved['scheduler'][phase]
        assert item['sha256'] == original['sha256'] and item['bytes'] == original['bytes']
        phases.append(classify_scheduler(item, phase, count, due))
    notifications = {}
    for phase, count in {'before': 0, 'actual-expired': 1, 'deleted': 0}.items():
        item = saved['notifications'][phase]
        original = actual['notifications'][phase]
        assert item['sha256'] == original['sha256'] and item['bytes'] == original['bytes']
        records = active_notifications(item)
        assert len(records) == count
        if records:
            assert records[0]['record_sha256'] == original['records'][0]['record_sha256']
        notifications[phase] = {'raw_bytes': item['bytes'], 'raw_sha256': item['sha256'],
            'observed_uptime_ms': item['observed_uptime_ms'], 'owned_active_records': records}
    receipts = {}
    for label, item in saved['receipts'].items():
        raw = item['raw'].encode()
        assert sha(raw) == item['sha256'] and len(raw) == item['bytes']
        receipts[label] = json.loads(raw)
    intent = receipts['expiry-stop-intent-e05-stop-expired']
    ack = receipts['expiry-stop-native-ack-e05-stop-expired']
    request = intent['request']
    assert request['op'] == 'click' and request['method'] == 'accessibility'
    assert request['expected_package'] == 'com.android.deskclock' and request['display'] == 0
    assert intent['focus'] == {'activity': 'com.android.deskclock.DeskClock',
        'focused_activity': '.DeskClock', 'package': 'com.android.deskclock', 'task': 1004,
        'user': 0, 'verified': True, 'window_token': 'a695bef'}
    assert request['selector'] == {
        'class': 'com.google.android.material.floatingactionbutton.FloatingActionButton',
        'clickable': True, 'desc': 'Stop', 'enabled': True,
        'id': 'com.android.deskclock:id/fab', 'package': 'com.android.deskclock'}
    assert intent['effect']['operation'] == 'reset' and intent['effect']['timer_id'] == 0
    assert ack['ok'] is True and ack['performed'] == 'click' and ack.get('outcome_unknown') is not True
    assert ack['accessibility_mode_restoration_verified'] is True
    mapping = {'id': 'resource-id', 'text': 'text', 'desc': 'content-desc', 'class': 'class',
               'package': 'package', 'enabled': 'enabled', 'clickable': 'clickable'}
    assert set(request['selector']) <= set(mapping)
    assert all(ack['actual_target'].get(mapping[k]) == v for k, v in request['selector'].items())
    reset = receipts['timer-effect-complete-e05-stop-expired']
    assert reset['exact_readback'] == actual['phases']['stopped-reset'] and reset['action_replayed'] is False
    item = reset['exact_readback']['timers'][0]
    assert reset['exact_readback']['ids'] == [0] and item['id'] == 0 and item['state'] == 4
    assert item['length_ms'] == item['total_length_ms'] == item['remaining_ms'] == 60000
    assert item['last_start_ms'] == item['last_wall_ms'] == -(1 << 63)
    delete = receipts['timer-effect-complete-t06-delete']
    assert delete['intent']['operation'] == 'delete' and delete['intent']['timer_id'] == 0
    assert delete['exact_readback'] == actual['phases']['final-deleted'] == actual['timer_final']
    assert actual['timer_final'] == {'ids': [], 'timers': [], 'stopwatch': {}, 'values': {}}
    assert receipts['final-task-set']['task_ids'] == [851]
    assert all(actual[k] is None for k in ('pending_effect', 'pending_timer_effect', 'close_pending', 'owned_task_remaining'))
    assert actual['owned_tasks'] == actual['closed_tasks'] == [1003, 1004]
    assert actual['guard_before'] == actual['guard_after'] and actual['native_before'] == actual['native_after']
    assert actual['alarms_before'] == actual['alarms_after']
    assert actual['templates_sha_before'] == actual['templates_sha_after'] == '655c545ee9487dc380100d6300376d0bb82d0d12beddd96f283ab7814ff19fea'
    assert actual['protected_business_and_sound_state_preserved'] is True and actual['task_set_restored'] is True
    result = {'schema': 'pocket4-expiry06-independent-saved-review/v1',
        'state': 'CURRENT_APK_SCHEDULE_EXPIRE_STOP_AND_EMPTY_READBACK_VERIFIED',
        'original_result_sha256': RESULT_SHA, 'saved_export_sha256': EXPORT_SHA,
        'package': 'com.android.deskclock', 'uid': 10063, 'android_user': 0, 'apk_sha256': APK_SHA,
        'epoch_sha256': actual['guard_after']['epoch_sha256'], 'original_result_modified': False,
        'original_scheduler_cancellation_verified': False,
        'scheduler_phases': phases, 'notifications': notifications,
        'owned_timer_id': 0, 'duration_ms': 60000, 'actual_observed_expiry_delay_ms':
            actual['expiry_timing']['observed_uptime_ms'] - due,
        'Stop_native_ACK_and_actual_selector_verified': True,
        'same_ID_reset_before_delete_verified': True, 'timer_and_stopwatch_final_empty': True,
        'final_tasks': [851], 'normal_closed_tasks': actual['closed_tasks'],
        'native_UI_actions': actual['ui_actions'], 'no_pending_effects': True,
        'original_alarm_templates_and_sound_state_preserved': True,
        'new_Android_or_UI_calls': 0, 'raw_private_dumps_published': False,
        'limitations': ['This independent review classifies saved observations; no fresh runtime query was made.',
            'The 60-second alarm naturally left the active scheduler store at expiry. Pause/resume cancellation belongs to the separate current-APK Timer04 evidence.',
            'Timer04 and expiry06 are separate owned fixtures, each created from and cleaned to an empty timer baseline.',
            'Native main-window Stop was used; a new full-screen alert task, desktop popup/action and physical audio were not observed.',
            'Original scheduler_cancellation_verified=false remains unchanged. Registry and whole-App readiness are not modified.']}
    raw = (json.dumps(result, sort_keys=True, indent=2) + '\n').encode()
    with (HERE / 'INDEPENDENT_SAVED_REVIEW06.json').open('xb') as out:
        out.write(raw)
    print(len(raw), sha(raw))


if __name__ == '__main__':
    main()
