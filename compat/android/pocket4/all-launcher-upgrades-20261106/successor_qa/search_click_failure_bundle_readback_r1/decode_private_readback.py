#!/usr/bin/env python3
"""After durable readback success, restore the exact bundle only outside Git."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import zlib

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(RuntimeError('NONFINITE_JSON')))


def read(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        first = os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and 0 < first.st_size <= limit, 'BOUNDED_LOCAL_FILE')
        raw = bytearray()
        while len(raw) <= limit:
            part = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
        after, path_now = os.fstat(fd), path.stat(follow_symlinks=False)
        keys = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        need(len(raw) == first.st_size and all(getattr(first, key) == getattr(after, key) == getattr(path_now, key)
             for key in keys), 'LOCAL_FILE_CHANGED')
        return bytes(raw)
    finally:
        os.close(fd)


def decode_exact(compressed, expected):
    decoder = zlib.decompressobj()
    raw = decoder.decompress(compressed, expected['bytes'] + 1)
    need(decoder.eof and not decoder.unconsumed_tail and not decoder.unused_data and
         len(raw) == expected['bytes'] and sha(raw) == expected['sha256'], 'COMPLETE_FIXED_ORIGINAL_BUNDLE_REQUIRED')
    return raw


def write_new(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            need(count > 0, 'PRIVATE_WRITE_PROGRESS')
            view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    need(read(path, len(raw)) == raw, 'NEW_PRIVATE_READBACK')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-sha256', required=True)
    args = parser.parse_args()
    plan_raw = read(HERE / 'READBACK_PLAN.json', 32768)
    need(sha(plan_raw) == args.plan_sha256, 'EXACT_REVIEWED_PLAN')
    plan = parse(plan_raw)
    private = PROJECT.parent / 'p4_private_ui/beike-search-click-failure-bundle-r1'
    public = HERE / 'actual-public'
    need(plan['schema'] == 'pocket4-fixed-failed-search-private-bundle-readback-plan-v1' and
         plan['private_directory'] == str(private) and plan['public_actual_directory'] == str(public) and
         plan['maximum_stdout_bytes'] == 2097152 and plan['maximum_compressed_bytes'] == plan['fixed_bundle']['bytes'] + 65536,
         'FIXED_PRIVATE_DESTINATION_AND_BUDGET')
    for folder in (private, public):
        need(folder.is_dir() and not folder.is_symlink(), 'EXISTING_REGULAR_DIRECTORY')
    packet_raw = read(HERE / 'process-request.review-only.json', 32768)
    reader = read(HERE / 'read_one_fixed_bundle.py', 16384)
    need(len(packet_raw) == plan['process_request']['bytes'] and sha(packet_raw) == plan['process_request']['sha256'] and
         len(reader) == plan['reader']['bytes'] and sha(reader) == plan['reader']['sha256'], 'REVIEWED_REQUEST_SOURCE_PINS')
    packet = parse(packet_raw)
    need(packet['args'][-1] == reader.decode(), 'REQUEST_EMBEDS_EXACT_READER')
    start = parse(read(public / 'start.original.json', 65536))
    job = start['job']
    need(all(job[key] == packet[key] for key in ('host', 'executable', 'args', 'cwd', 'idempotency_key')) and
         job['launch_state'] == 'launched' and job['launch_error'] is None and start['launch']['ok'] is True,
         'ACTUAL_FIXED_READBACK_START')
    terminal_raw = read(public / 'terminal.original.json', 16384)
    terminal = parse(terminal_raw)
    stdout = read(private / 'stdout.original.jsonl', plan['maximum_stdout_bytes'])
    need(terminal['job_id'] == job['id'] and terminal['state'] == 'succeeded' and type(terminal['exit_code']) is int and
         terminal['exit_code'] == 0 and all(terminal[key] is True for key in ('output_complete', 'output_durable', 'terminal_publication_confirmed')) and
         all(terminal[key] is False for key in ('timed_out', 'cancelled', 'automatic_retry')) and
         terminal['log_errors'] == {'stdout': None, 'stderr': None} and terminal['log_truncated'] == {'stdout': False, 'stderr': False} and
         terminal['log_bytes'] == {'stdout': {'seen': len(stdout), 'stored': len(stdout)}, 'stderr': {'seen': 0, 'stored': 0}},
         'DURABLE_COMPLETE_ZERO_READER_REQUIRED')
    need(len(stdout.splitlines()) == 1, 'ONE_COMPLETE_ENVELOPE')
    envelope = parse(stdout)
    need(envelope['schema'] == 'pocket4-one-fixed-private-bundle-zlib-readback-v1' and envelope['ok'] is True and
         envelope['encoding'] == 'zlib-base64' and envelope['bundle'] == plan['fixed_bundle'] and
         envelope['capture_binding'] == plan['capture_binding'] and
         envelope['process_fds_before'] == envelope['process_fds_after'] and
         len(envelope['process_fds_before']) >= 3 and
         all(envelope[key] is True for key in ('whole_process_fd_identities_unchanged', 'original_file_bytes_and_stat_unchanged',
                                             'raw_output_may_contain_private_state')) and
         all(type(envelope[key]) is int and envelope[key] == 0 for key in ('Main_reads', 'Main_commands', 'namespace_entries',
                           'Main_locks_or_guards', 'UI_actions', 'installs', 'permission_changes', 'signals')) and
         all(envelope[key] is False for key in ('raw_output_repository_publication_admitted', 'originals_modified', 'automatic_retry',
                           'reconciliation_published', 'old_UNKNOWN_modified', 'production_ready')),
         'COMPLETE_UNMODIFIED_READONLY_BUNDLE_RESULT')
    info = envelope['bundle_stat']
    need(stat.S_ISREG(info['st_mode']) and not info['st_mode'] & 0o077 and info['st_uid'] == 0 and
         info['st_nlink'] == 1 and info['st_size'] == plan['fixed_bundle']['bytes'], 'ACTUAL_ROOT_PRIVATE_BUNDLE_IDENTITY')
    compressed = base64.b64decode(envelope['data'], validate=True)
    need(type(envelope['compressed_bytes']) is int and 0 < len(compressed) == envelope['compressed_bytes'] <= plan['maximum_compressed_bytes'] and
         sha(compressed) == envelope['compressed_sha256'], 'COMPLETE_COMPRESSED_BYTES_PIN')
    raw = decode_exact(compressed, plan['fixed_bundle'])
    bundle = parse(raw)
    need(bundle['schema'] == 'pocket4-task878-failed-case-private-original-bytes-v1' and
         bundle['actual_job'] == plan['capture_binding']['original_failed_job'] and
         bundle['step'] == plan['capture_binding']['original_failed_step'] and
         bundle['full_original_bytes'] is True and bundle['contains_private_UI_evidence'] is True and
         bundle['approved_for_Git'] is False and len(bundle['files']) == plan['capture_binding']['files'], 'EXACT_PRIVATE_BUNDLE_SCHEMA')
    total = 0
    for row in bundle['files'].values():
        body = base64.b64decode(row['base64'], validate=True)
        need(type(row['bytes']) is int and len(body) == row['bytes'] and sha(body) == row['sha256'], 'EVERY_ORIGINAL_RECORD_PIN')
        total += len(body)
    need(total == plan['capture_binding']['original_bytes'], 'ALL_ORIGINAL_RECORD_BYTES')
    write_new(private / 'bundle.private.original.json', raw)
    receipt = {'schema': 'pocket4-single-private-bundle-readback-receipt-v1', 'ok': True, 'readback_job': job['id'],
               'capture_binding': plan['capture_binding'], 'bundle': plan['fixed_bundle'], 'bundle_stat': info,
               'stdout_bytes': len(stdout), 'stdout_sha256': sha(stdout), 'terminal_sha256': sha(terminal_raw),
               'compressed_bytes': len(compressed), 'compressed_sha256': sha(compressed),
               'whole_process_fd_identities_unchanged': True, 'all_101_original_record_hashes_verified': True,
               'original_bytes': total, 'private_raw_published': False, 'original_failed_case_reclassified': False,
               'specific_rejected_tree_difference': 'UNKNOWN', 'production_ready': False}
    write_new(public / 'READBACK_RECEIPT.derived.json', (json.dumps(receipt, indent=2, sort_keys=True) + '\n').encode())
    print(json.dumps(receipt, sort_keys=True))


if __name__ == '__main__':
    main()
