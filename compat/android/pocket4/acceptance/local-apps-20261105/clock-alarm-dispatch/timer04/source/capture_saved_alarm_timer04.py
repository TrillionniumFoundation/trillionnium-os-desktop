#!/usr/bin/python3 -I
"""Export exact saved Alarm04 route, Timer04 schedule records and built classes only."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import gzip
import hashlib
import json
import os
import re
import stat

SAVED = Path('/home/alex/work/pocket4-clock-alarm-accept-20261105-r12-04')
BUILD = Path('/home/alex/work/pocket4-clock-alarm-dispatch-20261105-r12-04/build')
OUT = Path('/home/alex/work/pocket4-clock-alarm-timer-saved-20261105-r12-04')
TIMER = Path('/home/alex/work/pocket4-clock-timer-20261105-r12-04')
TIMER_SHA = 'bc3fd55145039228f27f7ef0a23e48f899cc4b1a64d0f8fb06cdc9e4545feebb'
RESULT_SHA = 'd67ee63b7762adb2a5f4ee66455d15dbd50ab1c41a46683f9172ec8b513b2cec'
PROOF_SHA = '07aef12618bdf82f10c07b58872f41d4684aa5760a6113e9dc418b1179adcc14'
DEX_SHA = 'deff3873f215d97ab47908c7f60cb6ab62d4a6e4f6274dc3f3130023f0630c98'
KEY = '0|com.android.deskclock|2147483640|null|10063'
MARKER = 'Pocket4 QA alarm 67f3c942'


def need(value, why):
    if not value:
        raise RuntimeError(why)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path, pin=None, maximum=4 * 1024 * 1024):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
             and 0 <= before.st_size <= maximum, 'INPUT_BOUND')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(maximum + 1)
        after = os.fstat(fd)
        need(len(raw) == before.st_size and all(getattr(before, k) == getattr(after, k)
            for k in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')), 'INPUT_CHANGED')
    finally:
        os.close(fd)
    need(pin is None or sha(raw) == pin, 'INPUT_PIN_CHANGED')
    return raw


def write(name, raw):
    path = OUT / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640)
    try:
        os.fchown(fd, 0, 1000)
        os.fchmod(fd, 0o640)
        with os.fdopen(os.dup(fd), 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def alarm_block(text, expected):
    lines = text.splitlines()
    need(lines[0] == "Current Notification Manager state (filtered to 'com.android.deskclock'):",
         'EXACT_CLOCK_FILTER_REQUIRED')
    starts = [i for i, line in enumerate(lines) if line == '  Notification List:']
    need(len(starts) == 1, 'NOTIFICATION_SECTION_UNKNOWN')
    active = []
    for line in lines[starts[0] + 1:]:
        if line.strip() and not line.startswith('    '):
            break
        active.append(line)
    blocks = re.split(r'(?=^    NotificationRecord\()', '\n'.join(active), flags=re.M)
    need(not blocks[0].strip(), 'RECORD_GRAMMAR_UNKNOWN')
    records = [b for b in blocks[1:] if re.search(r'\bkey=' + re.escape(KEY) + r'(?:\s|$)', b)]
    need(len(records) == 1 and MARKER in records[0] and sha(records[0].encode()) == expected,
         'EXACT_SAVED_OWNED_RECORD_REQUIRED')
    return records[0]



def saved_timer_scheduler():
    timer_raw = read(TIMER / 'result.json', TIMER_SHA, 128 * 1024)
    timer = json.loads(timer_raw)
    need(timer['state'] == 'OWNED_TIMER_CORE_FLOW_VERIFIED_CLEAN'
         and timer['business_success_verified'] is True
         and timer['identity_before'] == timer['identity_after']
         and timer['identity_after']['apk_sha256'] == '433ff501b92a21bb9265c896add220b52bc16fc4124662eaf45310da99243a0d'
         and timer['owned_tasks'] == timer['closed_tasks'] == [996, 997]
         and all(timer.get(k) is None for k in ('pending_effect', 'pending_timer_effect', 'close_pending')),
         'ACTUAL_TIMER04_TERMINAL_CHANGED')
    expected = {'before': 0, 'created-running': 1, 'paused': 0,
                'resumed': 1, 'paused-after-resume': 0, 'deleted': 0}
    report = {'original_result_sha256': TIMER_SHA, 'original_result_bytes': len(timer_raw),
        'original_scheduler_cancellation_verified': timer['scheduler_cancellation_verified'],
        'original_result_modified': False, 'observations': {}}
    need(set(timer['scheduler_observations']) == set(expected), 'SIX_EXACT_SAVED_SCHEDULER_PHASES')
    for phase, wanted in expected.items():
        evidence = timer['scheduler_observations'][phase]
        raw = read(TIMER / (phase + '-alarm-private.txt'), evidence['sha256'], 512 * 1024)
        need(len(raw) == evidence['bytes'], 'TIMER_DUMP_SIZE_CHANGED')
        lines = raw.decode('utf-8', 'strict').splitlines()
        uid_lines = [line for line in lines if re.fullmatch(r'  Pending alarms per uid: \[.*\]', line)]
        need(len(uid_lines) == 1, 'PENDING_UID_HEADER_UNKNOWN')
        uid_match = re.findall(r'\bu0a63:(\d+)\b', uid_lines[0])
        need(len(uid_match) <= 1, 'CLOCK_UID_COUNT_AMBIGUOUS')
        uid_count = int(uid_match[0]) if uid_match else 0
        # Only exact current pending alarm records enter the positive count.
        starts = [i for i, line in enumerate(lines) if re.fullmatch(
            r'    ELAPSED_WAKEUP #\d+: Alarm\{\w+ type 2 origWhen \d+ whenElapsed \d+ com\.android\.deskclock\}', line)]
        records, active_lines = [], set()
        for i in starts:
            section = [line for line in lines[:i] if line.strip() and len(line)-len(line.lstrip()) <= 2]
            need(section and re.fullmatch(r'  \d+ pending alarms: ', section[-1]), 'CURRENT_PENDING_SECTION_REQUIRED')
            block = [lines[i]]
            active_lines.add(i)
            for n in range(i+1, len(lines)):
                line = lines[n]
                if line.strip() and len(line)-len(line.lstrip()) <= 4:
                    break
                block.append(line)
                active_lines.add(n)
            operations = [line for line in block if 'operation=PendingIntent{' in line]
            need(len(block) > 1 and block[1].strip() == 'tag=*walarm*:com.android.deskclock.action.TIMER_EXPIRED'
                 and len(operations) == 1 and 'com.android.deskclock startForegroundService' in operations[0],
                 'EXACT_CURRENT_FOREGROUND_TIMER_OPERATION_REQUIRED')
            records.append({'source_line_number': i + 1, 'section': section[-1],
                            'owned_record_lines': block})
        historical = [{'source_line_number': i + 1, 'line': line}
                      for i, line in enumerate(lines)
                      if 'com.android.deskclock.action.TIMER_EXPIRED' in line and i not in active_lines]
        need(len(records) == uid_count == wanted and historical, 'ACTUAL_SCHEDULE_CANCEL_SEQUENCE_CHANGED')
        report['observations'][phase] = {'raw_bytes': len(raw), 'raw_sha256': sha(raw),
            'observed_utc': evidence['observed_utc'], 'uptime_ms': evidence['uptime_ms'],
            'pending_uid_header_sha256': sha(uid_lines[0].encode()),
            'clock_uid_current_pending_count': uid_count, 'current_clock_records': records,
            'historical_Clock_tags_not_current': historical}
    need(read(TIMER / 'result.json', TIMER_SHA, 128 * 1024) == timer_raw, 'TIMER_RESULT_CHANGED')
    return report


def main():
    need(os.geteuid() == 0, 'HOST_SAVED_READER_REQUIRES_ROOT')
    os.sched_setaffinity(0, {20})
    result_raw = read(SAVED / 'result.json', RESULT_SHA)
    result = json.loads(result_raw)
    need(result['error'] == 'RuntimeError: ACTUAL_ALARM_ALERT_NOT_ONE_NEW_TASK'
         and result['actual_firing_verified'] is True
         and result['actual_alarm_notification_posted'] is True
         and result['owned_alarm_cleanup_verified'] is True, 'ORIGINAL_SCOPE_CHANGED')
    proof = json.loads(read(BUILD / 'all-class-semantic-proof.json', PROOF_SHA))
    dex = read(BUILD / 'classes.alarm-dispatch.dex', DEX_SHA)
    need(len(dex) == 3023456, 'CURRENT_ARTIFACT_DEX_SIZE')
    report = {'schema': 'clock-alarm-timer04-saved-source-export/v1',
        'exported_utc': datetime.now(timezone.utc).isoformat(),
        'new_Android_commands': 0, 'new_UI_inputs': 0, 'new_current_process_reads': 0,
        'service_or_setting_changes': 0, 'original_files_modified': False,
        'source_result': {'sha256': RESULT_SHA, 'bytes': len(result_raw)},
        'built_dex_sha256': DEX_SHA, 'whole_class_IR_proof_sha256': PROOF_SHA,
        'saved_tasks': {}, 'notifications': {}, 'services': {}, 'classes': {},
        'timer_scheduler': saved_timer_scheduler()}
    for label in ('alarm-baseline-tasks', 'possible-alarm-alert', 'final-owned-alarm-tasks'):
        choices = sorted(p for p in SAVED.iterdir()
                         if re.fullmatch(r'[0-9]{3,5}-' + re.escape(label) + r'\.json', p.name))
        need(len(choices) == 1, 'ONE_SAVED_TASK_OBSERVATION_' + label)
        raw = read(choices[0], maximum=128 * 1024)
        value = json.loads(raw)
        need(set(value) == {'raw_stacks', 'task_ids'}, 'SAVED_TASK_SCHEMA_CHANGED')
        report['saved_tasks'][label] = {'source_name': choices[0].name, 'bytes': len(raw),
            'sha256': sha(raw), 'observation': value}
    for phase in ('fired', 'failure', 'final'):
        evidence = result['runtime_evidence'][phase]
        for kind in ('notifications', 'services'):
            item = evidence['commands'][kind]
            path = Path(item['private_path'])
            need(path == SAVED / (phase + '-' + kind + '-private.txt'), 'EXACT_SAVED_FILENAME_REQUIRED')
            raw = read(path, item['sha256'], 128 * 1024)
            need(len(raw) == item['bytes'], 'SAVED_LENGTH_CHANGED')
            record = {'original_bytes': len(raw), 'original_sha256': sha(raw),
                'observed_utc': evidence['observed_utc']}
            if kind == 'notifications':
                if phase == 'final':
                    need(item['alarm_record']['present'] is False, 'FINAL_NOTIFICATION_NOT_ABSENT')
                    record['owned_record_absent'] = True
                else:
                    record['owned_alarm_record'] = alarm_block(raw.decode(), item['alarm_record']['record_sha256'])
                    record['owned_record_sha256'] = item['alarm_record']['record_sha256']
            else:
                record['saved_clock_filtered_service_dump'] = raw.decode('utf-8', 'strict')
            report[kind][phase] = record
    for name in ('com/android/deskclock/alarms/AlarmNotifications.smali',
                 'com/android/deskclock/alarms/AlarmActivity.smali',
                 'com/android/deskclock/provider/AlarmInstance$Companion.smali'):
        item = proof[name]
        need(item['before_ir_sha256'] == item['after_ir_sha256'], 'NON_TARGET_CLASS_IR_CHANGED')
        raw = read(BUILD / 'roundtrip-smali' / name, item['after_sha256'], 1024 * 1024)
        report['classes'][name] = {'bytes': len(raw), 'sha256': sha(raw),
            'semantic_ir_sha256': item['after_ir_sha256'], 'methods': item['after_method_count'],
            'text': raw.decode('utf-8', 'strict')}
    need(read(SAVED / 'result.json', RESULT_SHA) == result_raw, 'ORIGINAL_CHANGED_DURING_EXPORT')
    OUT.mkdir(mode=0o750)
    os.chown(OUT, 0, 1000)
    os.chmod(OUT, 0o750)
    raw = (json.dumps(report, indent=2, sort_keys=True) + '\n').encode()
    need(len(raw) <= 2 * 1024 * 1024, 'EXPORT_BOUND')
    receipt = write('selected-route04.json.gz', gzip.compress(raw, mtime=0))
    receipt.update(uncompressed_bytes=len(raw), uncompressed_sha256=sha(raw),
                   new_Android_commands=0, new_UI_inputs=0, new_current_process_reads=0)
    write('result.json', (json.dumps(receipt, indent=2, sort_keys=True) + '\n').encode())
    print(json.dumps(receipt, sort_keys=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect', action='store_true')
    if parser.parse_args().collect:
        main()
    else:
        print(json.dumps({'state': 'PLAN_ONLY', 'Android_commands': 0, 'UI_inputs': 0}))
