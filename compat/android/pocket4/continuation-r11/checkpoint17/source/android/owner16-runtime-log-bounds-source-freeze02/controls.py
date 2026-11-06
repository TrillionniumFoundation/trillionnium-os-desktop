#!/usr/bin/env python3
"""Local bounded-consumer controls; synthetic logger/audit, real memfd and owned IO."""
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ACTUAL = ROOT / 'root-recovery-20261104-02/evidence/owner15-normal01-runtime-read01/runtime-result.json'
ACTUAL_SHA = '6d35b126c24604d373175479c9bc69e0246a45c05f2061bb8f8077399f0926d5'
CASES = []


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def rejected(fn, contains):
    try:
        fn()
    except Exception as error:
        check(contains in str(error), 'wrong rejection: ' + repr(error))
        return type(error).__name__
    raise AssertionError('negative was accepted: ' + contains)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def compact(value):
    return (json.dumps(value, separators=(',', ':')) + '\n').encode()


def pretty(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def record_payload(owned, nonce):
    fd = os.memfd_create('owned-init-log-consumer-control', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    writer = -1
    try:
        os.fchmod(fd, 0o600)
        os.ftruncate(fd, owned.INIT_LOG_CAPACITY)
        # Exact Linux UAPI from this host's linux/fcntl.h: F_ADD_SEALS=1033,
        # SEAL_GROW=4, SHRINK=2, SEAL=1. This Python omits their symbolic names.
        check(os.uname().sysname == 'Linux', 'real memfd controls require Linux')
        fcntl.fcntl(fd, 1033, 4 | 2 | 1)
        writer = os.open('/proc/self/fd/' + str(fd), os.O_WRONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        marker = ('<6>droidloom-init-log: P4_INIT_LOG_V1 nonce=' + nonce + '\n' +
                  '<6>droidloom-init-log: P4_INIT_LOG_CACHED_V1 nonce=' + nonce + '\n').encode()
        fixture = marker + b'\xff' * (owned.INIT_LOG_CAPACITY - len(marker))
        check(os.write(writer, fixture) == len(fixture), 'short real fixture write')
        rejected(lambda: os.write(writer, b'x'), 'Operation not permitted')
        raw = os.pread(fd, owned.INIT_LOG_CAPACITY + 1, 0)
        check(raw == fixture and os.lseek(writer, 0, os.SEEK_CUR) == len(raw), 'memfd prefix differs')
        metadata = os.fstat(fd)
        value = {
            'schema': 1, 'nonce': nonce, 'device': metadata.st_dev, 'inode': metadata.st_ino,
            'capacity_bytes': owned.INIT_LOG_CAPACITY, 'marker_verified_after_held_init_hello': True,
            'retirement_proven_before_capture': True, 'observed_writer_offset': len(raw),
            'captured_bytes': len(raw), 'captured_sha256': hashlib.sha256(raw).hexdigest(),
            'captured_hex': raw.hex(), 'capacity_reached': True, 'stream_completeness_claimed': False,
            'exact_writer_per_line_proven': False, 'source_scope': owned.INIT_LOG_SCOPE,
            'first_error': None, 'secondary_errors': [], 'held_fds_closed': True,
        }
        return value
    finally:
        if writer >= 0:
            os.close(writer)
        os.close(fd)






def main():
    check(os.getuid() == os.geteuid() == os.getgid() == 0,
          'controls require existing local root for unchanged record ownership gate')
    before_fds = sorted(os.listdir('/proc/self/fd'))
    load('pinned_support', ROOT / 'lmkd-recovery-20261105-01/owner15-normal01-freeze-01/source/pinned_support.py')
    owned = load('owner16_consumption', HERE / 'candidate/owned.py')
    original = ACTUAL.read_bytes()
    check(hashlib.sha256(original).hexdigest() == ACTUAL_SHA, 'retained original shape differs')
    actual = json.loads(original)
    actor = actual['actor_result']
    first_error = copy.deepcopy(actor['first_error'])
    response = copy.deepcopy(actor['latest_status'])
    record = record_payload(owned, response['relay_lifecycle']['nonce'])
    response['relay_lifecycle']['init_log'] = record
    wire = compact(response)
    check(len(wire) > 256 * 1024 and len(record['captured_hex']) == 512 * 1024, 'full fixture too small')
    check(owned.decode_lifecycle_response(wire) == response, 'full prefix lost')
    check(response['relay_lifecycle']['first_failure'] == actor['latest_status']['relay_lifecycle']['first_failure'],
          'first lifecycle failure replaced')
    CASES.append({'name': 'full_real_memfd_prefix_consumed', 'wire_bytes': len(wire),
                  'captured_bytes': record['captured_bytes'], 'hex_bytes': len(record['captured_hex']),
                  'old_256k_gate_would_reject': True})

    failed = copy.deepcopy(response)
    failed_log = failed['relay_lifecycle']['init_log']
    for key in ('marker_verified_after_held_init_hello', 'retirement_proven_before_capture', 'held_fds_closed'):
        failed_log[key] = False
    failed_log['first_error'] = 'fixture original capture failure'
    failed_log['secondary_errors'] = ['fixture close failure']
    check(owned.decode_lifecycle_response(compact(failed)) == failed, 'failed diagnostic was suppressed')
    CASES.append({'name': 'failed_capture_is_data_not_success', 'success_inferred': False})

    negative_count = 0
    for field, bad in [('nonce', 'f' * 64), ('captured_sha256', '0' * 64),
                       ('captured_hex', record['captured_hex'][:-2]),
                       ('captured_bytes', owned.INIT_LOG_CAPACITY + 1),
                       ('schema', True), ('source_scope', 'unattributed kernel log'),
                       ('stream_completeness_claimed', True), ('first_error', 'x' * 513),
                       ('secondary_errors', ['x'] * 5)]:
        value = copy.deepcopy(response)
        value['relay_lifecycle']['init_log'][field] = bad
        rejected(lambda: owned.decode_lifecycle_response(compact(value)), 'init diagnostic')
        negative_count += 1
    value = copy.deepcopy(response)
    value['relay_lifecycle']['init_log']['unknown'] = 'x'
    rejected(lambda: owned.decode_lifecycle_response(compact(value)), 'schema fields differ')
    CASES.append({'name': 'exact_schema_nonce_hash_bounds_negative', 'rejected': negative_count + 1})

    ordinary = b'{"message":"' + b'x' * (owned.LEGACY_CONTROL_BYTES - 14) + b'"}'
    check(len(ordinary) == owned.LEGACY_CONTROL_BYTES, 'ordinary exact bound fixture differs')
    owned.decode_lifecycle_response(ordinary)
    rejected(lambda: owned.decode_lifecycle_response(ordinary + b' '), 'original bound')
    rejected(lambda: owned.decode_lifecycle_response(wire + b' ' * owned.LEGACY_CONTROL_BYTES), 'original bound')
    rejected(lambda: owned.decode_lifecycle_response(wire + b' ' * owned.INIT_LOG_CONTROL_BYTES), 'paired bound')
    CASES.append({'name': 'ordinary_and_whitespace_do_not_gain_log_allowance', 'original_max': owned.LEGACY_CONTROL_BYTES})

    with tempfile.TemporaryDirectory(prefix='owner16-log-consumer-') as tmp:
        folder = Path(tmp)
        longest = copy.deepcopy(actor)
        for name in owned.INIT_LOG_RESPONSE_FIELDS:
            longest[name] = copy.deepcopy(response)
        raw = pretty(longest)
        check(owned.MAX_RECORD < len(raw) <= owned.INIT_LOG_ACTOR_BYTES, 'six-copy actor bound not exercised')
        path = folder / 'actor-result.json'
        path.write_bytes(raw); path.chmod(0o400)
        rejected(lambda: owned.read_json(path), 'record metadata differs')
        decoded, digest = owned.read_actor_result(path)
        check(decoded == longest and decoded['first_error'] == first_error and
              digest == hashlib.sha256(raw).hexdigest(), 'actor prefix/failure changed')
        full_runtime = copy.deepcopy(actual); full_runtime['actor_result'] = decoded
        full_runtime['actor_result_sha256'] = digest
        runtime_raw = pretty(full_runtime)
        check(len(runtime_raw) <= 5 * 1024 * 1024, 'full coordinator exceeds proposed exact collector bound')
        CASES.append({'name': 'six_longest_prefix_copies_original_writer_and_reader',
                      'actor_bytes': len(raw), 'actor_max': owned.INIT_LOG_ACTOR_BYTES,
                      'runtime_bytes': len(runtime_raw), 'future_exact_runtime_reader_max': 5 * 1024 * 1024,
                      'whole_record_equal': True, 'first_error_preserved': True,
                      'six_slots_are_conservative_fixture_not_runtime_claim': True})
        oversized = copy.deepcopy(actor); oversized['unrelated'] = 'x' * (owned.MAX_RECORD + 1)
        path.chmod(0o600); path.write_bytes(pretty(oversized)); path.chmod(0o400)
        rejected(lambda: owned.read_actor_result(path), 'original record bound')
        path.chmod(0o600); path.write_bytes(raw + b' '); path.chmod(0o400)
        rejected(lambda: owned.read_actor_result(path), 'writer encoding differs')
        path.chmod(0o600); path.write_bytes(b' ' * (owned.INIT_LOG_ACTOR_BYTES + 1)); path.chmod(0o400)
        rejected(lambda: owned.read_actor_result(path), 'record metadata differs')
        CASES.append({'name': 'unrelated_actor_data_noncanonical_or_oversize_rejected'})
        class OwnedFileReceive:
            # Explicit stream seam: real file IO, not socket/peer qualification.
            def __init__(self, fd): self.fd = fd; self.calls = 0
            def recv(self, maximum):
                check(maximum == 65536, 'production receive chunk changed')
                self.calls += 1
                return os.read(self.fd, maximum)
        receive_calls = []
        for body, error in ((wire, None), (ordinary + b' ', 'original bound'),
                            (wire + b' ' * owned.INIT_LOG_CONTROL_BYTES, 'paired bound')):
            target = folder / 'receive-fixture.json'
            target.write_bytes(body)
            fd = os.open(target, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
            try:
                receiver = OwnedFileReceive(fd)
                call = lambda: owned.receive_lifecycle_response(receiver)
                if error is None: check(call() == response, 'stream prefix changed')
                else: rejected(call, error)
                receive_calls.append(receiver.calls)
            finally: os.close(fd)
        CASES.append({'name': 'production_receive_loop_owned_file_stream_seam',
                      'read_calls': receive_calls, 'full_prefix_and_two_rejections': True,
                      'actual_unix_socket_or_peer_qualification': False,
                      'prior_local_pidfd_and_socket_capability_failures_preserved': True})
    check(sorted(os.listdir('/proc/self/fd')) == before_fds, 'local owned FD leak')
    result = {'schema': 1, 'success': True, 'controls': CASES,
              'captured_prefix_bytes': owned.INIT_LOG_CAPACITY,
              'actual_retained_shape_sha256': ACTUAL_SHA,
              'synthetic_logger_and_audit_extension': True,
              'real_memfd_and_regular_io': True, 'receive_stream_adapter_seam': True,
              'unix_socket_and_peer_admission_executed': False,
              'local_only': True, 'android_or_owner_runtime_executed': False,
              'all_owned_children_reaped': True, 'all_owned_fds_closed': True,
              'generic_record_limit_unchanged': owned.MAX_RECORD}
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'success': False, 'completed_controls': CASES,
                          'error': repr(error), 'traceback': traceback.format_exc()}))
        raise
