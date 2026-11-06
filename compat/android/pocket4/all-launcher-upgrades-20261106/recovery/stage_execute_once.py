#!/usr/bin/env python3
"""Stage a new coordinated drain, then request the reviewed native restart once.

This is an EXECUTION entry, not a preflight. The caller must first settle every
known runtime worker and review the actual new QA source/staging receipts.
No historic qualification is edited and no operation is automatically replayed.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time

ROOT = Path('/home/alex/work/pocket4-cell-recovery-execute-20261106-r1')
PRE = Path('/home/alex/work/pocket4-cell-recovery-preflight-20261106-r1')
MANIFEST_SHA = 'b97002660594ad0ef6e7b453927b8c5b19cba49a5873bc133199d790019b1f9f'
PLAN_SHA = 'eb9f47bcce9d8b5dbbd103b7d7ae19c4f11714e82ed192e2d036f844907816bc'
SUCCESSOR = '/home/alex/work/pocket4-cell-successor-20261106-r1'
STAT = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode() + b'\n'


def read(path, maximum, expected=None):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path, 'CANONICAL_IMMUTABLE_INPUT')
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1
             and 0 < before.st_size <= maximum, 'BOUNDED_ROOT_INPUT')
        out, end = bytearray(), time.monotonic() + 10
        while len(out) <= maximum:
            need(time.monotonic() < end, 'INPUT_READ_DEADLINE')
            block = os.read(fd, min(65536, maximum + 1 - len(out)))
            if not block:
                break
            out.extend(block)
        after = os.fstat(fd)
        current = path.lstat()
        need(len(out) == before.st_size and all(getattr(before, key) == getattr(after, key) == getattr(current, key)
             for key in STAT), 'INPUT_CHANGED')
        need(expected is None or digest(out) == expected, 'INPUT_HASH_CHANGED')
        return bytes(out)
    finally:
        os.close(fd)


def write_new(name, raw):
    need(re.fullmatch(r'[A-Za-z0-9_.-]{1,120}', name) and name not in ('.', '..'), 'NEW_FILENAME')
    path = ROOT / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o400)
    try:
        remaining = memoryview(raw)
        while remaining:
            n = os.write(fd, remaining)
            need(n > 0, 'DURABLE_WRITE_PROGRESS')
            remaining = remaining[n:]
        os.fsync(fd)
    finally:
        os.close(fd)
    need(read(path, len(raw), digest(raw)) == raw, 'NEW_FILE_READBACK')
    return {'path': str(path), 'bytes': len(raw), 'sha256': digest(raw)}


def main():
    need(os.getuid() == os.geteuid() == 0, 'EXISTING_ROOT_AUTHORITY_REQUIRED')
    os.umask(0o077)
    raw = sys.stdin.buffer.read(900001)
    need(len(raw) <= 900000, 'PACKET_BOUND')
    packet = json.loads(raw)
    need(set(packet) == {'schema', 'terminals', 'flow_directories', 'reviewed_source_receipts', 'coordination'}, 'CLOSED_EXECUTION_PACKET')
    need(packet['schema'] == 'pocket4-native-cell-single-execution-packet-v1', 'PACKET_SCHEMA')
    need(packet['coordination'] == {
        'known_runtime_workers_settled': True,
        'unresolved_start_attempts': [],
        'new_qa_candidate_second_reviewed': True,
        'new_qa_source_staging_and_host_controls_settled': True,
        'all_agents_notified_no_new_runtime_jobs_until_recovery_settles': True,
        'source': 'root-coordinator-review-of-actual-terminal-results-not-proc-discovery'}, 'ACTUAL_COORDINATOR_REVIEW_REQUIRED')
    need(not Path(SUCCESSOR).exists(), 'PRIOR_EXECUTION_OUTPUT_PRESENT_NO_RETRY')
    need(ROOT.parent.resolve() == ROOT.parent, 'CANONICAL_NEW_STAGE_PARENT')
    manifest_raw = read(PRE / 'source/SOURCE_PINS.json', 65536, MANIFEST_SHA)
    manifest = json.loads(manifest_raw)
    need(len(manifest['files']) == 6, 'EXACT_FROZEN_RECOVERY_CLOSURE')
    for name, pin in manifest['files'].items():
        need('/' not in name and name.endswith('.py'), 'FROZEN_SOURCE_NAME')
        value = read(PRE / 'source' / name, 131072, pin['sha256'])
        need(len(value) == pin['bytes'], 'FROZEN_SOURCE_LENGTH')
    plan = json.loads(read(PRE / 'plan.json', 65536, PLAN_SHA))
    preflight = json.loads(read(PRE / 'preflight.stdout', 65536))
    need(preflight['ok'] is True and preflight['restart_attempted'] is False and preflight['errors'] == [], 'ACTUAL_READONLY_PREFLIGHT_REQUIRED')
    for section in ('observation_fds', 'lease_fds'):
        need(preflight[section]['acquired'] == preflight[section]['closed'] and not preflight[section]['errors'], 'PREFLIGHT_FDS_NOT_SETTLED')
    need(10 <= len(packet['terminals']) <= 64 and 3 <= len(packet['flow_directories']) <= 16, 'EXPLICIT_KNOWN_JOB_AND_FLOW_BOUNDS')
    roots = packet['flow_directories']
    need(len(roots) == len(set(roots)), 'DUPLICATE_FLOW_DIRECTORY')
    ROOT.mkdir(mode=0o700)
    receipts = []
    for job, supplied in sorted(packet['terminals'].items()):
        need(re.fullmatch('[0-9a-f]+-[0-9a-f]+-[0-9a-f]+', job), 'EXACT_DURABLE_JOB_ID')
        body = supplied['text'].encode()
        need(set(supplied) == {'text', 'bytes', 'sha256'} and len(body) == supplied['bytes'] and digest(body) == supplied['sha256'], 'EXACT_TERMINAL_TEXT')
        value = json.loads(body)
        need(value['job_id'] == job and value['state'] in ('succeeded', 'failed') and value['output_complete'] is True
             and value['output_durable'] is True and value['terminal_publication_confirmed'] is True,
             'AUTHORITATIVE_TERMINAL_REQUIRED')
        receipts.append(write_new('terminal-' + job + '.json', body))
    for pin in packet['reviewed_source_receipts'] + plan['unknown_evidence']:
        need(set(pin) <= {'path', 'bytes', 'sha256'} and {'path', 'sha256'} <= set(pin), 'CLOSED_REVIEWED_RECEIPT')
        body = read(pin['path'], 1048576, pin['sha256'])
        need('bytes' not in pin or len(body) == pin['bytes'], 'REVIEWED_RECEIPT_LENGTH')
        receipts.append({'path': pin['path'], 'bytes': len(body), 'sha256': pin['sha256']})
    locks = []
    for directory in roots:
        need(directory.startswith('/home/alex/work/pocket4-') and '..' not in Path(directory).parts and Path(directory).resolve() == Path(directory), 'OWNED_FLOW_DIRECTORY')
        path = Path(directory) / 'flow.lock'
        value = path.lstat()
        need(stat.S_ISREG(value.st_mode) and value.st_uid == 0 and value.st_nlink == 1, 'EXISTING_OWNED_LOCK')
        locks.append({'path': str(path), 'identity': {'st_dev': value.st_dev, 'st_ino': value.st_ino}})
    drain = {'schema': 'pocket4-owned-worker-drain-v1',
        'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'reviewed_monotonic_ns': time.monotonic_ns(), 'unresolved_start_attempts': [],
        'workers': [], 'flow_locks': locks, 'source_receipts': receipts,
        'review_scope': 'all-known-pocket4-UI-install-observer-restart-jobs'}
    plan['drain'] = write_new('drain.json', encoded(drain))
    need(plan['output_root'] == SUCCESSOR, 'EXACT_SINGLE_REVIEWED_SUCCESSOR_DESTINATION')
    plan_pin = write_new('plan.json', encoded(plan))
    write_new('coordinator-review.json', encoded({'coordination': packet['coordination'],
        'terminal_jobs': sorted(packet['terminals']), 'original_readonly_preflight_job': '1a1b0802b05-fc05-70f1',
        'terminal_artifacts': receipts, 'flow_locks': locks, 'restart_count_requested': 1,
        'new_qa_runtime_qualification_inherited': False, 'production_ready': False}))
    fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    print(json.dumps({'stage': str(ROOT), 'plan': plan_pin, 'known_terminal_jobs': len(packet['terminals']),
        'source_manifest_sha256': MANIFEST_SHA, 'next_operation': 'one-existing-native-cell-restart-with-fresh-preflight',
        'automatic_retry': False, 'UI_actions': 0, 'installs': 0}), flush=True)
    argv = ['/usr/bin/python3', '-B', '-I', str(PRE / 'source/successor_runtime.py'),
        'execute-native-cell-restart', '--plan', str(ROOT / 'plan.json'),
        '--plan-sha256', plan_pin['sha256'], '--source-manifest-sha256', MANIFEST_SHA]
    os.execve(argv[0], argv, {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'})


if __name__ == '__main__':
    main()
