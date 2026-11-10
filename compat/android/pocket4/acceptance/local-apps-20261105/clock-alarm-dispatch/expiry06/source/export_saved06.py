#!/usr/bin/python3 -I
"""Export only the already terminal expiry06 journal; no live Android reads."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import gzip
import hashlib
import json
import os
import re
import stat
import time

ROOT = Path('/home/alex/work/pocket4-clock-timer-expiry-20261105-r12-06')
TOOLS = Path('/home/alex/work/pocket4-clock-expiry-tools-20261105-r12-06')
OUT = Path('/home/alex/work/pocket4-clock-expiry06-saved-20261105-r12-01')
RESULT_SHA = '6b584428d4145416d26c72400ab966b9be8df185aec35655177ad799f62ea86e'
SOURCE_PINS = {'timer_expiry06.py': 'fba956b1b2a681d5181b60ab5fccad55964a46029b89970ad1c9ad646a0776fc',
              'timer_core04.py': '59598a298f768bd63f535efb5216233f916383bc4411e7d98531e3d078a6b69b',
              'read_clock_expired_text02.py': '4eae2c4540ce0710f225c875b025fad48d9e8a14bbc5b81f99aa1e0cb26c0905'}


def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(value):
    return tuple(getattr(value, key) for key in ('st_dev', 'st_ino', 'st_mode', 'st_uid',
                 'st_gid', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def read(directory, name, deadline, pin=None, maximum=2 * 1024 * 1024):
    need('/' not in name and name not in ('.', '..') and time.monotonic() < deadline,
         'BOUNDED_EXACT_SAVED_NAME_REQUIRED')
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NOATIME, dir_fd=directory)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1
             and 0 <= before.st_size <= maximum, 'EXACT_OWNED_REGULAR_SAVED_FILE_REQUIRED')
        chunks, offset = [], 0
        while offset < before.st_size:
            need(time.monotonic() < deadline, 'SAVED_EXPORT_READ_DEADLINE')
            chunk = os.pread(fd, min(65536, before.st_size - offset), offset)
            need(chunk, 'SAVED_FILE_SHORT_READ')
            chunks.append(chunk)
            offset += len(chunk)
        raw = b''.join(chunks)
        need(identity(before) == identity(os.fstat(fd)), 'SAVED_FILE_CHANGED_DURING_READ')
        need(pin is None or sha(raw) == pin, 'SAVED_FILE_PIN_CHANGED')
        return raw
    finally:
        os.close(fd)


def write(name, raw):
    fd = os.open(OUT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640)
    try:
        os.fchown(fd, 0, 1000)
        os.fchmod(fd, 0o640)
        with os.fdopen(os.dup(fd), 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)
    return {'path': str(OUT / name), 'bytes': len(raw), 'sha256': sha(raw)}


def main():
    need(os.geteuid() == 0, 'ROOT_REQUIRED_TO_READ_OWNED_PRIVATE_JOURNAL')
    os.sched_setaffinity(0, {20})
    deadline = time.monotonic() + 45
    directory = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    tool_fd = os.open(TOOLS, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        birth = os.fstat(directory)
        need(birth.st_uid == 0 and stat.S_IMODE(birth.st_mode) == 0o700, 'OWNED_JOURNAL_DIRECTORY_CHANGED')
        original = read(directory, 'result.json', deadline, RESULT_SHA, 64 * 1024)
        result = json.loads(original)
        need(len(original) == 38001 and result['state'] == 'CURRENT_CLOCK_TIMER_EXPIRY_STOP_DELETE_VERIFIED_CLEAN'
             and result['business_success_verified'] is True and result['owned_timer_id'] == 0
             and result['owned_tasks'] == result['closed_tasks'] == [1003, 1004]
             and all(result[key] is None for key in ('pending_effect', 'pending_timer_effect',
                     'close_pending', 'owned_task_remaining', 'remaining_timer_id'))
             and result['actual_install_binding']['apk_sha256'] == '433ff501b92a21bb9265c896add220b52bc16fc4124662eaf45310da99243a0d',
             'EXACT_TERMINAL_EXPIRY06_REQUIRED')
        for name, pin in SOURCE_PINS.items():
            read(tool_fd, name, deadline, pin, 64 * 1024)
        report = {'schema': 'pocket4-expiry06-saved-only-export/v1',
            'exported_utc': datetime.now(timezone.utc).isoformat(),
            'source_result': {'bytes': len(original), 'sha256': RESULT_SHA},
            'source_pins': SOURCE_PINS, 'new_Android_commands': 0, 'new_UI_actions': 0,
            'live_process_or_environment_reads': 0, 'original_files_modified': False,
            'contains_private_global_alarm_dumps': True, 'original_scheduler_cancellation_verified':
                result['scheduler_cancellation_verified'], 'scheduler': {}, 'notifications': {}, 'receipts': {}}
        need(set(result['scheduler_observations']) == {'before', 'created-running', 'actual-expired', 'final-deleted'},
             'EXACT_FOUR_SAVED_SCHEDULER_PHASES_REQUIRED')
        for phase, item in result['scheduler_observations'].items():
            name = phase + '-alarm-private.txt'
            raw = read(directory, name, deadline, item['sha256'])
            need(len(raw) == item['bytes'], 'SCHEDULER_SAVED_LENGTH_CHANGED')
            report['scheduler'][phase] = {'source_name': name, 'bytes': len(raw), 'sha256': sha(raw),
                'observed_utc': item['observed_utc'], 'uptime_ms': item['uptime_ms'],
                'raw': raw.decode('utf-8', 'strict')}
        need(set(result['notifications']) == {'before', 'actual-expired', 'deleted'}, 'EXACT_THREE_SAVED_NMS_PHASES')
        for phase, item in result['notifications'].items():
            name = phase + '-notifications-private.txt'
            raw = read(directory, name, deadline, item['sha256'], 128 * 1024)
            need(len(raw) == item['bytes'] and raw.startswith(
                b"Current Notification Manager state (filtered to 'com.android.deskclock'):\n"),
                'EXACT_SAVED_CLOCK_FILTER_REQUIRED')
            report['notifications'][phase] = {'source_name': name, 'bytes': len(raw), 'sha256': sha(raw),
                'observed_uptime_ms': item['observed_uptime_ms'], 'raw': raw.decode('utf-8', 'strict')}
        names = os.listdir(directory)
        need(len(names) <= 2048, 'SAVED_JOURNAL_ENTRY_BOUND')
        labels = ('owned-timer-created', 'actual-expired-owned-timer',
            'expiry-stop-intent-e05-stop-expired', 'expiry-stop-native-ack-e05-stop-expired',
            'timer-effect-complete-e05-stop-expired', 'timer-effect-complete-t06-delete', 'final-task-set')
        for label in labels:
            matches = [name for name in names if re.fullmatch(r'[0-9]{3,5}-' + re.escape(label) + r'\.json', name)]
            need(len(matches) == 1, 'ONE_SAVED_RECEIPT_REQUIRED_' + label)
            raw = read(directory, matches[0], deadline, maximum=128 * 1024)
            value = json.loads(raw)
            if label == 'timer-effect-complete-e05-stop-expired':
                need(value['intent']['operation'] == 'reset' and value['intent']['timer_id'] == 0
                     and value['exact_readback'] == result['phases']['stopped-reset'], 'EXACT_STOP_READBACK_CHANGED')
            if label == 'final-task-set':
                need(value['task_ids'] == [851], 'FINAL_SAVED_TASK_SET_CHANGED')
            report['receipts'][label] = {'source_name': matches[0], 'bytes': len(raw),
                'sha256': sha(raw), 'raw': raw.decode('utf-8', 'strict')}
        need(read(directory, 'result.json', deadline, RESULT_SHA, 64 * 1024) == original
             and identity(os.fstat(directory)) == identity(birth), 'ORIGINAL_JOURNAL_CHANGED')
        for name, pin in SOURCE_PINS.items():
            read(tool_fd, name, deadline, pin, 64 * 1024)
    finally:
        os.close(tool_fd)
        os.close(directory)
    raw = (json.dumps(report, sort_keys=True, indent=2) + '\n').encode()
    need(len(raw) <= 8 * 1024 * 1024, 'SAVED_EXPORT_TOTAL_BOUND')
    OUT.mkdir(mode=0o750)
    os.chown(OUT, 0, 1000)
    os.chmod(OUT, 0o750)
    receipt = write('private-saved-evidence06.json.gz', gzip.compress(raw, mtime=0))
    receipt.update(uncompressed_bytes=len(raw), uncompressed_sha256=sha(raw),
        source_result_sha256=RESULT_SHA, saved_scheduler_files=4, saved_notification_files=3,
        saved_receipt_files=7, new_Android_commands=0, new_UI_actions=0,
        private_global_alarm_dumps_not_for_publication=True)
    write('result.json', (json.dumps(receipt, indent=2, sort_keys=True) + '\n').encode())
    print(json.dumps(receipt, sort_keys=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect', action='store_true')
    if parser.parse_args().collect:
        main()
    else:
        print(json.dumps({'state': 'PLAN_ONLY', 'Android_commands': 0, 'UI_actions': 0}))
