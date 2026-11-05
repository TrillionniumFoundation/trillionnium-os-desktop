#!/usr/bin/env python3
"""Read-only reconciliation of one approved, ACK-unknown ordinary14 request."""
import hashlib
import json
import os
import re
import stat
import sys
import time

JOBS = '/home/alex/.local/state/hepta-runtime-mac-worker/jobs'
EXPECTED_UID = 1000
APPROVED_REQUEST_SHA256 = 'd383190cf90e1d752e1fcc3de757c9c9cb9092e1646235ad33e40cd71d535fc6'
APPROVED_STDIN_BYTES = 35263
APPROVED_STDIN_SHA256 = '9eef9bf99c688d128467c9962f7aec8d077a2e65b39042e3a1236f663cbe4ec4'
APPROVED = {
    'executable': '/usr/bin/python3',
    'args': ['-I', '-B', '-', '--compile-sha256',
             'a916592cc708dc76411b482a371214410bca4662f6ff72dccd5083d88872b6a6'],
    'cwd': '/home/alex/work',
    'env': {},
    'cpu_quota_percent': 100,
    'memory_max_bytes': 536870912,
    'nice': 10,
    'timeout_seconds': 180,
}
ENTRY_LIMIT = 4096
REQUEST_LIMIT = 131072
TOTAL_READ_LIMIT = 32 * 1024 * 1024
MATCH_LIMIT = 8
SECONDS = 10
OUTPUT_LIMIT = 65536
JOB_ID = re.compile(r'[0-9a-f]{8,16}-[0-9a-f]{4}-[0-9a-f]{1,4}\Z')
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
IDENTITY_KEYS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid',
                 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
DIR_KEYS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid')


class BoundError(Exception):
    pass


class MetadataError(Exception):
    pass


def identity(value, keys=IDENTITY_KEYS):
    return {key: getattr(value, key) for key in keys}


def tick(state):
    if time.monotonic() >= state['deadline']:
        raise BoundError('monotonic_deadline')


def close_fd(fd, state):
    if fd is not None:
        try:
            os.close(fd)
        except OSError as error:
            state['close_errors'].append(error.errno)


def open_jobs(state):
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for component in JOBS.strip('/').split('/'):
            tick(state)
            next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY |
                              os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            close_fd(fd, state)
            fd = next_fd
        value = os.fstat(fd)
        if not stat.S_ISDIR(value.st_mode) or value.st_uid != EXPECTED_UID:
            raise MetadataError('jobs_directory_identity')
        result, fd = fd, None
        return result
    finally:
        close_fd(fd, state)


def read_regular(parent, name, maximum, state):
    tick(state)
    fd = None
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC |
                     os.O_NONBLOCK, dir_fd=parent)
        first = os.fstat(fd)
        if not stat.S_ISREG(first.st_mode) or first.st_uid != EXPECTED_UID or first.st_nlink != 1:
            raise MetadataError('file_shape_or_owner')
        if not 0 <= first.st_size <= maximum:
            raise BoundError('single_file_bound')
        if state['read_bytes'] + first.st_size > TOTAL_READ_LIMIT:
            raise BoundError('total_read_bound')
        data = bytearray()
        while len(data) <= first.st_size:
            tick(state)
            chunk = os.read(fd, min(65536, first.st_size + 1 - len(data)))
            if not chunk:
                break
            state['read_bytes'] += len(chunk)
            if state['read_bytes'] > TOTAL_READ_LIMIT:
                raise BoundError('total_read_bound')
            data.extend(chunk)
        tick(state)
        last = os.fstat(fd)
        named = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if len(data) != first.st_size or identity(last) != identity(first) or identity(named) != identity(first):
            raise MetadataError('file_changed_during_read')
        raw = bytes(data)
        return raw, {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                     'identity': identity(first)}
    finally:
        close_fd(fd, state)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise MetadataError('duplicate_json_key')
        result[key] = value
    return result


def request_object(raw):
    try:
        value = json.loads(raw.decode('utf-8', 'strict'), object_pairs_hook=unique_object)
    except (UnicodeError, ValueError, RecursionError):
        raise MetadataError('invalid_request_json') from None
    if type(value) is not dict:
        raise MetadataError('request_not_object')
    return value


def tuple_matches(value):
    for key, expected in APPROVED.items():
        actual = value.get(key)
        # JSON may encode an identical integral limit as 180 or 180.0.
        # Booleans are never resource numbers; no rounding/coercion is used.
        if type(expected) is int:
            if type(actual) not in (int, float) or actual != expected:
                return False
        elif type(actual) is not type(expected) or actual != expected:
            return False
    return True


def matching_metadata(value, job_id):
    directory = JOBS + '/' + job_id
    if value.get('job_id') != job_id or value.get('job_dir') != directory or value.get('stdin_path') != directory + '/stdin.bin':
        raise MetadataError('matched_job_paths_or_id')
    digest = value.get('request_digest')
    fingerprint = value.get('request_fingerprint')
    if type(digest) is not str or HEX64.fullmatch(digest) is None or fingerprint != digest:
        raise MetadataError('matched_digest_or_fingerprint')
    return digest


def scan(jobs, state):
    first_root = os.fstat(jobs)
    state['jobs_identity'] = identity(first_root, DIR_KEYS)
    exhausted = False
    with os.scandir(jobs) as names:
        while state['entries_seen'] < ENTRY_LIMIT:
            tick(state)
            try:
                name = next(names).name
            except StopIteration:
                exhausted = True
                break
            state['entries_seen'] += 1
            if JOB_ID.fullmatch(name) is None:
                state['unrecognized_names'] += 1
                continue
            job = None
            try:
                job = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW |
                              os.O_CLOEXEC, dir_fd=jobs)
                before = os.fstat(job)
                if before.st_uid != EXPECTED_UID:
                    raise MetadataError('job_directory_owner')
                raw, request_pin = read_regular(job, 'request.json', REQUEST_LIMIT, state)
                state['requests_read'] += 1
                value = request_object(raw)
                if not tuple_matches(value):
                    state['nonmatching_requests'] += 1
                    continue
                digest = matching_metadata(value, name)
                if len(state['matches']) >= MATCH_LIMIT:
                    raise BoundError('matching_entry_bound')
                row = {'job_id': name, 'request_digest': digest,
                       'request_fingerprint': digest, 'request_file': request_pin,
                       'stored_execution_fields_match': True,
                       'stdin_matches': False, 'stdin_file': None, 'errors': []}
                state['matches'].append(row)
                # No nonmatching request can reach this fixed-name read.
                try:
                    stdin, stdin_pin = read_regular(job, 'stdin.bin', APPROVED_STDIN_BYTES, state)
                    row['stdin_file'] = stdin_pin
                    row['stdin_matches'] = (len(stdin) == APPROVED_STDIN_BYTES and
                        stdin_pin['sha256'] == APPROVED_STDIN_SHA256)
                    if not row['stdin_matches']:
                        row['errors'].append({'code': 'matched_stdin_pin_differs'})
                except BoundError:
                    raise
                except (MetadataError, OSError) as error:
                    row['errors'].append(error_summary(error))
                after = os.fstat(job)
                named = os.stat(name, dir_fd=jobs, follow_symlinks=False)
                if identity(before, DIR_KEYS) != identity(after, DIR_KEYS) or identity(before, DIR_KEYS) != identity(named, DIR_KEYS):
                    raise MetadataError('matched_job_directory_changed')
                row['job_directory_identity'] = identity(before, DIR_KEYS)
                row['held_job_directory_stable'] = True
            except BoundError:
                raise
            except (MetadataError, OSError) as error:
                code = error_summary(error)
                key = code['code'] + ':' + str(code.get('errno', ''))
                state['unreadable_or_rejected_counts'][key] = state['unreadable_or_rejected_counts'].get(key, 0) + 1
                # Do not print unmatched job IDs, paths, argv, environment or pins.
            finally:
                close_fd(job, state)
    if not exhausted:
        raise BoundError('entry_bound')
    tick(state)
    if identity(os.fstat(jobs), DIR_KEYS) != state['jobs_identity']:
        raise MetadataError('held_jobs_directory_changed')
    again = None
    try:
        again = open_jobs(state)
        if identity(os.fstat(again), DIR_KEYS) != state['jobs_identity']:
            raise MetadataError('named_jobs_directory_changed')
    finally:
        close_fd(again, state)
    state['enumeration_exhausted'] = True


def error_summary(error):
    if isinstance(error, (MetadataError, BoundError)):
        return {'code': str(error)}
    if isinstance(error, OSError):
        return {'code': 'os_error', 'errno': error.errno}
    return {'code': 'unexpected_' + type(error).__name__}


def main():
    began = time.monotonic()
    state = {'deadline': began + SECONDS, 'read_bytes': 0, 'entries_seen': 0,
             'requests_read': 0, 'nonmatching_requests': 0, 'unrecognized_names': 0,
             'unreadable_or_rejected_counts': {}, 'matches': [], 'close_errors': [],
             'enumeration_exhausted': False}
    error = None
    jobs = None
    try:
        if len(sys.argv) != 1 or os.getuid() != EXPECTED_UID or os.geteuid() != EXPECTED_UID:
            raise MetadataError('fixed_unprivileged_entry_required')
        jobs = open_jobs(state)
        scan(jobs, state)
    except BaseException as caught:
        error = error_summary(caught)
    finally:
        close_fd(jobs, state)
    exact = [row['job_id'] for row in state['matches'] if row['stdin_matches'] and
             row.get('held_job_directory_stable') is True and not row['errors']]
    complete = (error is None and state['enumeration_exhausted'] and
                not state['unreadable_or_rejected_counts'] and not state['unrecognized_names'] and
                not state['close_errors'] and all(not row['errors'] for row in state['matches']))
    result = {
        'schema': 1, 'scope': 'READ_ONLY_APPROVED_ORDINARY14_EXECUTION_METADATA_RECONCILIATION',
        'approved_request_sha256': APPROVED_REQUEST_SHA256,
        'approved_stdin_bytes': APPROVED_STDIN_BYTES,
        'approved_stdin_sha256': APPROVED_STDIN_SHA256,
        'compared_stored_execution_fields': list(APPROVED),
        'idempotency_key_present_or_verified': False,
        'request_digest_recomputed': False,
        'outcome': ('EXACT_MATCH_OBSERVED' if len(exact) == 1 else
                    'MULTIPLE_EXACT_MATCHES_OBSERVED' if len(exact) > 1 else
                    'NOT_FOUND_AT_OBSERVATION'),
        'zero_match_proves_original_call_invalid': False,
        'automatic_retry_or_task_dispatch': False,
        'test_or_runtime_executed': False, 'files_written': False,
        'atomic_inventory_snapshot_claimed': False,
        'collection_complete': complete, 'error': error,
        'limits': {'entries_processed': ENTRY_LIMIT, 'per_request_bytes': REQUEST_LIMIT,
                   'total_read_bytes': TOTAL_READ_LIMIT, 'matching_entries': MATCH_LIMIT,
                   'monotonic_scan_deadline_seconds': SECONDS},
        'summary': {key: state[key] for key in ('read_bytes', 'entries_seen', 'requests_read',
                    'nonmatching_requests', 'unrecognized_names', 'unreadable_or_rejected_counts',
                    'close_errors', 'enumeration_exhausted')},
        'jobs_directory_identity': state.get('jobs_identity'),
        'matched_execution_tuples': state['matches'], 'exact_matching_job_ids': exact,
        'elapsed_seconds': time.monotonic() - began,
    }
    raw = json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(',', ':'))
    if len(raw.encode()) > OUTPUT_LIMIT:
        print('{"collection_complete":false,"error":{"code":"output_bound"},"automatic_retry_or_task_dispatch":false}')
        return 1
    print(raw, flush=True)
    return 0 if complete else 1


if __name__ == '__main__':
    raise SystemExit(main())
