"""Fixed retired Owner08 kernel-window read. No child, write, clear or replay."""
import base64
import errno
import gzip
import hashlib
import json
import os
import re
import stat
import time
import traceback

CFG = None  # Filled once from the externally pinned actual runtime/preparation.
MAX_SCAN_BYTES = 16 * 1024 * 1024
MAX_SCAN_RECORDS = 65536
MAX_READ_SECONDS = 10
MAX_SELECTED_BYTES = 256 * 1024
MAX_SELECTED_RECORDS = 256
MAX_RECORD_BYTES = 65536


def need(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(body):
    return hashlib.sha256(body).hexdigest()


def stamp(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_gid, value.st_nlink, value.st_rdev, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns]


def device_identity(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_gid, value.st_nlink, value.st_rdev]


def directory(name, parent=None):
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                 **({} if parent is None else {'dir_fd': parent}))
    try:
        value = os.fstat(fd)
        need(stat.S_ISDIR(value.st_mode) and value.st_uid == value.st_gid == 0
             and not value.st_mode & 0o022, 'fixed ancestor is not protected/root-owned')
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_runtime(root):
    fd = os.open('runtime-result.json', os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
                 dir_fd=root)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == before.st_gid == 0
             and before.st_nlink == 1 and not before.st_mode & 0o6022
             and before.st_size == CFG['runtime_bytes'], 'fixed original runtime metadata differs')
        raw = bytearray()
        while len(raw) <= CFG['runtime_bytes']:
            part = os.read(fd, min(32768, CFG['runtime_bytes'] + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
        need(len(raw) == CFG['runtime_bytes'] and sha(raw) == CFG['runtime_sha256']
             and stamp(before) == stamp(os.fstat(fd))
             == stamp(os.stat('runtime-result.json', dir_fd=root, follow_symlinks=False)),
             'fixed original runtime changed or external digest differs')
        actual = json.loads(raw)
        need(actual['attempt_nonce'] == CFG['attempt_nonce']
             and actual['prepared_sha256'] == CFG['prepared_sha256']
             and actual['first_unit']['InvocationID'] == actual['terminal']['InvocationID'] == CFG['invocation']
             and actual['first_unit']['ExecMainPID'] == actual['terminal']['ExecMainPID'] == str(CFG['actor_pid'])
             and actual['started_monotonic_ns'] == CFG['start_ns']
             and actual['finished_monotonic_ns'] == CFG['end_ns'], 'fixed original attempt/time binding differs')
        cleanup = actual['exact_unit_cleanup']
        need(cleanup['invocation'] == CFG['invocation'] and cleanup['unit'] == CFG['unit']
             and all(cleanup[key] is True for key in ('unit_not_found', 'cgroup_absent', 'original_actor_dead')),
             'original exact cleanup was not established')
        return {'bytes': len(raw), 'sha256': sha(raw), 'identity': stamp(before)}
    finally:
        os.close(fd)


def boot_id():
    fd = os.open('/proc/sys/kernel/random/boot_id', os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == before.st_gid == 0,
             'boot identity source type/owner differs')
        body = os.read(fd, 129)
        need(len(body) <= 128 and stamp(before) == stamp(os.fstat(fd)), 'boot identity source changed')
        value = body.decode('ascii').strip()
        need(re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', value) is not None,
             'malformed boot identity')
        need(value == CFG['boot_id'], 'host boot differs from the fixed actual attempt')
        return value
    finally:
        os.close(fd)


def parse_record(raw):
    header, separator, message = raw.partition(b';')
    fields = header.split(b',')
    need(separator == b';' and 4 <= len(fields) <= 12, 'malformed kernel record header')
    need(all(1 <= len(value) <= 20 and value.isdigit() for value in fields[:3]),
         'malformed kernel record numeric fields')
    priority, sequence, timestamp = map(int, fields[:3])
    need(priority <= 191 and timestamp > 0 and sequence < 2**64, 'kernel record values outside bounds')
    header_text = header.decode('ascii', 'strict')
    need(len(header_text) <= 1024, 'kernel record header exceeds bound')
    caller = None
    for field in fields[4:]:
        match = re.fullmatch(b'caller=T([1-9][0-9]{0,9})', field)
        if match:
            need(caller is None, 'duplicate kernel caller field')
            caller = int(match.group(1))
    return {'sequence': sequence, 'timestamp_us': timestamp, 'priority': priority,
            'header': header_text, 'caller_host_pid': caller, 'message_raw': message}


def selected(record):
    if not CFG['window_start_us'] <= record['timestamp_us'] <= CFG['window_end_us']:
        return False
    lower = record['message_raw'].lower()
    return record['caller_host_pid'] in CFG['owned_pids'] or any(marker in lower for marker in
        (b'init:', b'init[', b'init(', b'ueventd:', b'apexd:', b'reboot:', b'rebooting'))


def empty_scan():
    return {'records_read': 0, 'bytes_read': 0, 'selected_bytes': 0, 'selected_records': [],
              'overrun_errors': 0, 'sequence_gaps': 0, 'ring_end_observed': False,
              'oldest_observed_timestamp_us': None, 'newest_observed_timestamp_us': None,
              'window_timestamp_bounds_covered': False, 'window_evidence_complete': False}


def scan(fd, report):
    previous = None
    began = time.monotonic()
    while True:
        need(time.monotonic() - began <= MAX_READ_SECONDS, 'kernel read time bound reached')
        need(report['records_read'] < MAX_SCAN_RECORDS and report['bytes_read'] < MAX_SCAN_BYTES,
             'kernel scan record/byte bound reached')
        try:
            raw = os.read(fd, MAX_RECORD_BYTES)
        except BlockingIOError:
            report['ring_end_observed'] = True
            break
        except OSError as error:
            if error.errno == errno.EINTR:
                continue
            if error.errno == errno.EPIPE:
                report['overrun_errors'] += 1
                continue
            raise
        need(raw and len(raw) <= MAX_RECORD_BYTES, 'unexpected empty/oversized kernel read')
        report['bytes_read'] += len(raw)
        need(report['bytes_read'] <= MAX_SCAN_BYTES, 'kernel scan byte bound exceeded')
        record = parse_record(raw)
        report['records_read'] += 1
        if previous is not None and record['sequence'] != previous + 1:
            report['sequence_gaps'] += 1
        previous = record['sequence']
        timestamp = record['timestamp_us']
        low, high = report['oldest_observed_timestamp_us'], report['newest_observed_timestamp_us']
        report['oldest_observed_timestamp_us'] = timestamp if low is None else min(low, timestamp)
        report['newest_observed_timestamp_us'] = timestamp if high is None else max(high, timestamp)
        if selected(record):
            need(len(report['selected_records']) < MAX_SELECTED_RECORDS
                 and report['selected_bytes'] + len(raw) <= MAX_SELECTED_BYTES,
                 'selected kernel evidence bound reached')
            body = record.pop('message_raw')
            try:
                record['message'] = body.decode('utf-8', 'strict')
                record['message_utf8_exact'] = True
            except UnicodeDecodeError:
                record['message'] = body.decode('utf-8', 'replace')
                record['message_utf8_exact'] = False
            record.update({'raw_bytes': len(raw), 'raw_sha256': sha(raw),
                'raw_base64': base64.b64encode(raw).decode('ascii'),
                'caller_matches_recorded_owned_pid': record['caller_host_pid'] in CFG['owned_pids'],
                'attribution': 'TIME_WINDOW_AND_TEXT_OR_RECORDED_PID_CANDIDATE; NOT_A_RUNTIME_VERDICT'})
            report['selected_records'].append(record)
            report['selected_bytes'] += len(raw)
    low, high = report['oldest_observed_timestamp_us'], report['newest_observed_timestamp_us']
    report['window_timestamp_bounds_covered'] = (low is not None and high is not None
        and low <= CFG['window_start_us'] and high >= CFG['window_end_us'])
    report['window_evidence_complete'] = (report['ring_end_observed']
        and report['window_timestamp_bounds_covered'] and report['overrun_errors'] == 0
        and report['sequence_gaps'] == 0)
    report['elapsed_seconds'] = time.monotonic() - began
    return report


def main():
    result = {'schema': 1, 'kind': 'owner08-normal01-fixed-kernel-window-read01',
              'collection_complete': False, 'qualification': False, 'mutations': False,
              'child_or_runtime_executed': False, 'config': CFG, 'errors': []}
    fds = []
    try:
        need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0, 'original root read required')
        need(CFG['start_ns'] < CFG['end_ns'] and CFG['end_ns'] - CFG['start_ns'] < 10_000_000_000,
             'fixed actual window outside ten-second limit')
        slash = directory('/'); fds.append(slash)
        opt = directory('opt', slash); fds.append(opt)
        root = directory(CFG['state_leaf'], opt); fds.append(root)
        identity = os.fstat(root)
        need([identity.st_dev, identity.st_ino] == CFG['state_identity'], 'held actual state identity differs')
        root_stamp = stamp(identity)
        result['runtime_before'] = read_runtime(root)
        result['boot_before'] = boot_id()
        dev = directory('dev', slash); fds.append(dev)
        fd = os.open('kmsg', os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=dev)
        fds.append(fd)
        before = os.fstat(fd)
        need(stat.S_ISCHR(before.st_mode) and before.st_uid == before.st_gid == 0
             and os.major(before.st_rdev) == 1 and os.minor(before.st_rdev) == 11
             and not before.st_mode & 0o022, 'fixed kmsg character device metadata differs')
        result['kmsg_identity'] = device_identity(before)
        result['scan'] = empty_scan()
        began = time.monotonic()
        try:
            scan(fd, result['scan'])
        finally:
            result['scan']['elapsed_seconds'] = time.monotonic() - began
        need(device_identity(before) == device_identity(os.fstat(fd))
             == device_identity(os.stat('kmsg', dir_fd=dev, follow_symlinks=False)),
             'held kmsg identity changed')
        result['boot_after'] = boot_id()
        result['runtime_after'] = read_runtime(root)
        need(result['runtime_before'] == result['runtime_after'] and root_stamp == stamp(os.fstat(root))
             == stamp(os.stat(CFG['state_leaf'], dir_fd=opt, follow_symlinks=False)),
             'fixed actual evidence directory changed')
        result['collection_complete'] = True
    except BaseException as error:
        result['errors'].append({'error': repr(error), 'traceback': traceback.format_exc()})
    finally:
        for fd in reversed(fds):
            try:
                os.close(fd)
            except OSError as error:
                result['errors'].append({'close_error': repr(error)})
    result['collection_complete'] = result['collection_complete'] and not result['errors']
    raw = (json.dumps(result, sort_keys=True, separators=(',', ':')) + '\n').encode()
    need(len(raw) <= 2 * 1024 * 1024, 'diagnostic envelope bound exceeded')
    packed = gzip.compress(raw, mtime=0)
    print(json.dumps({'collection_complete': result['collection_complete'], 'qualification': False,
        'bytes': len(raw), 'sha256': sha(raw), 'gzip_bytes': len(packed), 'gzip_sha256': sha(packed),
        'gzip_base64': base64.b64encode(packed).decode()}, sort_keys=True))
    return 0 if result['collection_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
