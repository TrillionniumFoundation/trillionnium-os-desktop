#!/usr/bin/env python3
"""Local owned-file controls only: never open the actual worker jobs directory."""
from pathlib import Path
import hashlib
import json
import os
import tempfile
import time
import types

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'read_requests.py'
APPROVED = Path('/workspace/scratch/94990735b266/native-recovery-20261105-02/factory-snapshot-nofollow-run-bound01/exact-request.json')
module = types.ModuleType('owned_reconciliation_reader_controls')
exec(compile(SOURCE.read_bytes(), str(SOURCE), 'exec'), module.__dict__)
assert module.JOBS == '/home/alex/.local/state/hepta-runtime-mac-worker/jobs'
assert module.EXPECTED_UID == 1000
module.EXPECTED_UID = os.getuid()  # Test process ownership only; frozen source stays UID1000.
target, = module.TARGETS
raw_request = APPROVED.read_bytes()
assert hashlib.sha256(raw_request).hexdigest() == '407b5a345263ecdf8a8b6e7582edf4484fa898053cfe930abc23c3498ca3cd8e'
body = json.loads(raw_request)['stdin'].encode()
assert len(body) == target['stdin_bytes'] == 138246
assert hashlib.sha256(body).hexdigest() == target['stdin_sha256']
results = []


def record(name, condition):
    assert condition, name
    results.append({'case': name, 'passed': True})


def state():
    return {'deadline': time.monotonic() + 10, 'read_bytes': 0, 'entries_seen': 0,
            'requests_read': 0, 'nonmatching_requests': 0, 'unrecognized_names': 0,
            'execution_tuple_candidates': 0, 'different_stdin_size_candidates': 0,
            'candidate_stdin_reads': 0, 'different_stdin_hash_candidates': 0,
            'unreadable_or_rejected_counts': {}, 'matches': [], 'close_errors': [],
            'enumeration_exhausted': False}


execution = target['execution']
record('single_external_request_and_stdin_bound', target['approved_request_sha256'] == hashlib.sha256(raw_request).hexdigest())
record('exact_execution_tuple_matches', module.tuple_matches(execution, execution))
owner = dict(execution, cpu_quota_percent=100, memory_max_bytes=536870912, nice=10, timeout_seconds=240)
record('Owner14_shared_argv_different_resources_rejected', not module.tuple_matches(owner, execution))
for field in ('cpu_quota_percent', 'memory_max_bytes', 'nice', 'timeout_seconds'):
    record(field + '_boolean_rejected', not module.tuple_matches(dict(execution, **{field: True}), execution))
record('all_scan_limits_exact', (module.ENTRY_LIMIT, module.REQUEST_LIMIT, module.TOTAL_READ_LIMIT,
                               module.SECONDS, module.MATCH_LIMIT, module.OUTPUT_LIMIT) ==
       (4096, 131072, 33554432, 10, 8, 65536))

before_fds = len(os.listdir('/proc/self/fd'))
with tempfile.TemporaryDirectory(prefix='owned-reconcile04-', dir=HERE.parent) as root:
    parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        Path(root, 'stdin.bin').write_bytes(body)
        s = state()
        got, pin = module.read_regular(parent, 'stdin.bin', 138246, s, allowed_sizes={138246})
        record('actual_138246_byte_read_spans_original_65536_chunks', got == body and s['read_bytes'] == 138246 and not s['close_errors'])
        record('actual_large_stdin_pin_matches', module.stdin_matches(target, pin))

        Path(root, 'short.bin').write_bytes(b'x')
        s = state()
        try:
            module.read_regular(parent, 'short.bin', 138246, s, allowed_sizes={138246})
            raise AssertionError('wrong size admitted')
        except module.NotTargetStdin:
            record('different_size_reads_zero_body_bytes', s['read_bytes'] == 0 and not s['close_errors'])

        altered = bytes([body[0] ^ 1]) + body[1:]
        Path(root, 'changed.bin').write_bytes(altered)
        s = state()
        _, pin = module.read_regular(parent, 'changed.bin', 138246, s, allowed_sizes={138246})
        record('same_size_different_hash_is_not_target', not module.stdin_matches(target, pin) and s['read_bytes'] == 138246)

        s = state()
        s['read_bytes'] = module.TOTAL_READ_LIMIT - 138246 + 1
        initial = s['read_bytes']
        try:
            module.read_regular(parent, 'stdin.bin', 138246, s, allowed_sizes={138246})
            raise AssertionError('total bound admitted')
        except module.BoundError as error:
            record('existing_total_budget_rejects_before_body_read', str(error) == 'total_read_bound' and s['read_bytes'] == initial and not s['close_errors'])

        s = state()
        try:
            module.read_regular(parent, 'stdin.bin', module.REQUEST_LIMIT, s)
            raise AssertionError('metadata bound weakened')
        except module.BoundError as error:
            record('metadata_limit_still_rejects_138246', str(error) == 'single_file_bound' and s['read_bytes'] == 0 and not s['close_errors'])
    finally:
        os.close(parent)

with tempfile.TemporaryDirectory(prefix='owned-reconcile04-scan-', dir=HERE.parent) as root:
    module.JOBS = root  # Only the owned temporary tree is scanned in these controls.
    metadata_bytes = 0
    cases = [('1a1abcd0000-fc05-1', execution, body),
             ('1a1abcd0000-fc05-22', execution, b'wrong-size-never-read'),
             ('1a1abcd0000-fc05-333', owner, b'unmatched-tuple-never-read')]
    for job, fields, content in cases:
        directory = Path(root, job)
        directory.mkdir()
        metadata = dict(fields, job_id=job, job_dir=str(directory),
                        stdin_path=str(directory / 'stdin.bin'),
                        request_digest='a' * 64, request_fingerprint='a' * 64)
        raw = json.dumps(metadata, separators=(',', ':')).encode()
        metadata_bytes += len(raw)
        (directory / 'request.json').write_bytes(raw)
        (directory / 'stdin.bin').write_bytes(content)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    s = state()
    try:
        module.scan(fd, s)
    finally:
        os.close(fd)
    record('owned_scan_exact_single_target_only', len(s['matches']) == 1 and s['matches'][0]['job_id'] == cases[0][0] and s['matches'][0]['target_label'] == target['label'])
    record('owned_scan_does_not_read_excluded_stdin', s['read_bytes'] == metadata_bytes + 138246 and s['candidate_stdin_reads'] == 1 and s['different_stdin_size_candidates'] == 1 and s['nonmatching_requests'] == 1)
    record('owned_scan_exhausted_without_errors_or_close_failures', s['enumeration_exhausted'] and s['entries_seen'] == 3 and not s['close_errors'] and not s['unreadable_or_rejected_counts'])

record('all_owned_FDs_and_temporary_directories_released', len(os.listdir('/proc/self/fd')) == before_fds)
result = {'schema': 1, 'success': True, 'passed': len(results), 'controls': results,
          'scope': 'actual local owned files and synthetic metadata only',
          'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
          'source_expected_UID': 1000, 'test_module_UID_seam': os.getuid(),
          'actual_worker_jobs_directory_opened': False,
          'actual_reconciliation_reader_main_executed': False,
          'approved_runtime_executed': False, 'Hepta_called': False,
          'real_submission_or_execution_state_proved': False}
raw = (json.dumps(result, indent=2) + '\n').encode()
with (HERE / 'checks.json').open('xb') as output:
    output.write(raw)
print(json.dumps({'passed': len(results), 'checks_bytes': len(raw),
                  'checks_sha256': hashlib.sha256(raw).hexdigest()}))
