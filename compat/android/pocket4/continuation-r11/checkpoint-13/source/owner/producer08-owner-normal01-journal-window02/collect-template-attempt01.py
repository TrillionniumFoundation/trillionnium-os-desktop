"""Fixed retired Owner08 journal diagnostic; no runtime or namespace mutation."""
import base64
import errno
import gzip
import hashlib
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import time
import traceback

CFG = None  # Fixed only from already verified original evidence.
MAX_READ_SECONDS = 10
MAX_STDOUT_BYTES = 8 * 1024 * 1024
MAX_STDERR_BYTES = 65536
MAX_LINE_BYTES = 65536
MAX_SELECTED_BYTES = 256 * 1024
MAX_SELECTED_RECORDS = 256

def need(ok, message):
    if not ok:
        raise RuntimeError(message)

def sha(body):
    return hashlib.sha256(body).hexdigest()

def stamp(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_gid, value.st_nlink, value.st_rdev, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns]

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


def journal_record(raw):
    item = json.loads(raw)
    need(isinstance(item, dict), 'journal record is not an object')
    boot = item.get('_BOOT_ID')
    transport = item.get('_TRANSPORT')
    tick = item.get('__MONOTONIC_TIMESTAMP')
    need(boot == CFG['boot_id'].replace('-', '') and transport == 'kernel'
         and isinstance(tick, str) and 1 <= len(tick) <= 20 and tick.isdigit(),
         'journal boot/transport/monotonic field differs from fixed query')
    tick = int(tick)
    need(tick < 2**64, 'journal monotonic timestamp outside bounds')
    message = item.get('MESSAGE', '')
    if isinstance(message, list):
        need(all(type(x) is int and 0 <= x <= 255 for x in message), 'invalid journal binary message')
        message_bytes = bytes(message)
        message = message_bytes.decode('utf-8', 'replace')
    else:
        need(isinstance(message, str), 'invalid journal message type')
        message_bytes = message.encode('utf-8')
    caller = item.get('SYSLOG_PID')
    identifier = item.get('SYSLOG_IDENTIFIER')
    matched_pid = isinstance(caller, str) and caller.isdigit() and int(caller) in CFG['owned_pids']
    within = CFG['window_start_us'] <= tick <= CFG['window_end_us']
    lower = message_bytes.lower()
    # Limit this second read to service/cgroup failure context, not all init traffic.
    service_failure = any(word in lower for word in
        (b'bootstrap-apexd-failed', b'apexd-bootstrap', b'reboot_on_failure',
         b'shutdown_command', b'reboot start', b'rebooting'))
    cgroup_failure = any(word in lower for word in (b'cgroup', b'processgroup')) and any(
        word in lower for word in (b'failed', b'error', b'cannot', b'no such', b'permission', b'busy'))
    startup = lower == b'init second stage started!'
    named = identifier in ('init', 'libprocessgroup', 'processgroup', 'apexd', 'apexd-bootstrap')
    keep = within and (matched_pid or named and (service_failure or cgroup_failure or startup))
    source_tick = item.get('_SOURCE_MONOTONIC_TIMESTAMP')
    source_boot = item.get('_SOURCE_BOOTTIME_TIMESTAMP')
    for value in (source_tick, source_boot):
        need(value is None or isinstance(value, str) and 1 <= len(value) <= 20 and value.isdigit(),
             'invalid optional source timestamp')
    return tick, keep, {
        'journal_received_monotonic_us': tick,
        'source_monotonic_us': None if source_tick is None else int(source_tick),
        'source_boottime_us': None if source_boot is None else int(source_boot),
        'message': message, 'syslog_pid': caller, 'syslog_identifier': identifier,
        'syslog_pid_matches_recorded_host_pid_number': matched_pid,
        'attribution': 'RECEIVE_TIME_AND_NARROW_TEXT_OR_PID_NUMBER_CANDIDATE; NO_BIRTH_ASSOCIATION',
        'raw_bytes': len(raw), 'raw_sha256': sha(raw),
        'raw_base64': base64.b64encode(raw).decode('ascii')}



def new_journal_report():
    return {'records_read': 0, 'stdout_bytes': 0, 'stderr_bytes': 0,
            'selected_bytes': 0, 'selected_records': [], 'stderr': '',
            'oldest_observed_timestamp_us': None, 'newest_observed_timestamp_us': None,
            'query_drained': False, 'child_reaped': False, 'forced_child_kill': False,
            'window_timestamp_bounds_covered': False,
            'persistent_journal_completeness_proved': False}


def consume(raw, report):
    need(raw and len(raw) <= MAX_LINE_BYTES, 'journal line empty or exceeds bound')
    tick, keep, candidate = journal_record(raw)
    report['records_read'] += 1
    low, high = report['oldest_observed_timestamp_us'], report['newest_observed_timestamp_us']
    report['oldest_observed_timestamp_us'] = tick if low is None else min(low, tick)
    report['newest_observed_timestamp_us'] = tick if high is None else max(high, tick)
    if keep:
        need(len(report['selected_records']) < MAX_SELECTED_RECORDS
             and report['selected_bytes'] + len(raw) <= MAX_SELECTED_BYTES,
             'selected journal evidence bound reached')
        report['selected_records'].append(candidate)
        report['selected_bytes'] += len(raw)


def run_journal(tool, argv, report):
    child = None
    pidfd = None
    mux = selectors.DefaultSelector()
    stderr = bytearray()
    pending = bytearray()
    began = time.monotonic()
    first = None
    try:
        child = subprocess.Popen(argv, executable='/proc/self/fd/' + str(tool),
            pass_fds=(tool,), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, close_fds=True,
            env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
                 'SYSTEMD_PAGERSECURE': '1', 'SYSTEMD_COLORS': '0'}, cwd='/')
        report['child_pid'] = child.pid
        # Popen owns this unreaped child; its PID cannot have been reused here.
        pidfd = os.pidfd_open(child.pid, 0)
        report['child_pidfd_identity'] = stamp(os.fstat(pidfd))
        for pipe, name in ((child.stdout, 'stdout'), (child.stderr, 'stderr')):
            os.set_blocking(pipe.fileno(), False)
            mux.register(pipe, selectors.EVENT_READ, name)
        while mux.get_map():
            remaining = MAX_READ_SECONDS - (time.monotonic() - began)
            need(remaining > 0, 'journal child read timeout')
            for event, _ in mux.select(min(0.1, remaining)):
                part = os.read(event.fileobj.fileno(), 32768)
                if not part:
                    mux.unregister(event.fileobj)
                    continue
                if event.data == 'stderr':
                    report['stderr_bytes'] += len(part)
                    need(report['stderr_bytes'] <= MAX_STDERR_BYTES, 'journal stderr bound exceeded')
                    stderr.extend(part)
                    continue
                report['stdout_bytes'] += len(part)
                need(report['stdout_bytes'] <= MAX_STDOUT_BYTES, 'journal stdout bound exceeded')
                pending.extend(part)
                while b'\n' in pending:
                    line, _, tail = pending.partition(b'\n')
                    pending[:] = tail
                    consume(bytes(line) + b'\n', report)
                need(len(pending) <= MAX_LINE_BYTES, 'journal unfinished line bound exceeded')
        if pending:
            consume(bytes(pending), report)
        remaining = MAX_READ_SECONDS - (time.monotonic() - began)
        need(remaining > 0, 'journal exit timeout')
        report['returncode'] = child.wait(timeout=remaining)
        report['child_reaped'] = True
        need(report['returncode'] == 0, 'journalctl exited unsuccessfully')
        report['query_drained'] = True
    except BaseException as error:
        first = error
        report['first_error'] = repr(error)
        report['traceback'] = traceback.format_exc()
    finally:
        if child is not None and not report['child_reaped']:
            try:
                if child.poll() is None:
                    report['forced_child_kill'] = True
                    try:
                        if pidfd is not None:
                            signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                        else:
                            # Only this still-unreaped Popen child if pidfd_open failed.
                            child.kill()
                    except ProcessLookupError:
                        # An already-dead exact child must still be joined below.
                        pass
                report['returncode'] = child.wait(timeout=5)
                report['child_reaped'] = True
            except BaseException as error:
                report['cleanup_error'] = repr(error)
                if first is None:
                    first = error
        mux.close()
        if child is not None:
            for pipe in (child.stdout, child.stderr):
                if pipe is not None:
                    pipe.close()
        if pidfd is not None:
            os.close(pidfd)
        report['stderr'] = stderr.decode('utf-8', 'replace')
        report['stderr_sha256'] = sha(stderr)
        report['elapsed_seconds'] = time.monotonic() - began
        low, high = report['oldest_observed_timestamp_us'], report['newest_observed_timestamp_us']
        report['window_timestamp_bounds_covered'] = (low is not None and high is not None
            and low <= CFG['window_start_us'] and high >= CFG['window_end_us'])
    if first is not None:
        raise first


def tool_identity(fd):
    before = os.fstat(fd)
    need(stat.S_ISREG(before.st_mode) and before.st_uid == before.st_gid == 0
         and before.st_nlink >= 1 and not before.st_mode & 0o6022
         and before.st_mode & 0o111 and 4096 <= before.st_size <= 4 * 1024 * 1024,
         'journalctl is not a protected bounded root executable')
    try:
        capability = os.getxattr(fd, 'security.capability')
    except OSError as error:
        if error.errno != errno.ENODATA:
            raise
        capability = None
    need(capability is None, 'journalctl has file capabilities')
    body = bytearray()
    while len(body) < before.st_size:
        part = os.pread(fd, min(32768, before.st_size - len(body)), len(body))
        need(part, 'short journalctl read')
        body.extend(part)
    need(body[:4] == b'\x7fELF' and stamp(before) == stamp(os.fstat(fd)), 'journalctl changed/not ELF')
    return {'identity': stamp(before), 'bytes': len(body), 'sha256': sha(body), 'capabilities': None}


def main():
    result = {'schema': 1, 'kind': 'owner08-normal01-fixed-journal-window-read02',
        'collection_complete': False, 'qualification': False, 'runtime_executed': False,
        'runtime_mutations_requested': False, 'config': CFG, 'errors': []}
    fds = []
    try:
        need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0, 'original root read required')
        slash = directory('/'); fds.append(slash)
        opt = directory('opt', slash); fds.append(opt)
        root = directory(CFG['state_leaf'], opt); fds.append(root)
        root_stamp = stamp(os.fstat(root))
        need(root_stamp[:2] == CFG['state_identity'], 'held original state directory differs')
        result['runtime_before'] = read_runtime(root)
        need(result['runtime_before']['identity'][8] == CFG['runtime_mtime_ns'],
             'runtime mtime used for bounded journal search differs')
        result['boot_before'] = boot_id()
        usr = directory('usr', slash); fds.append(usr)
        bin_dir = directory('bin', usr); fds.append(bin_dir)
        tool = os.open('journalctl', os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=bin_dir)
        fds.append(tool)
        result['tool_before'] = tool_identity(tool)
        argv = ['/usr/bin/journalctl', '--no-pager', '--quiet', '--output=json', '--all',
            '--since=@' + str(CFG['query_since_realtime_seconds']),
            '--until=@' + str(CFG['query_until_realtime_seconds']),
            '_BOOT_ID=' + CFG['boot_id'].replace('-', ''), '_TRANSPORT=kernel']
        need(0 < CFG['query_until_realtime_seconds'] - CFG['query_since_realtime_seconds'] <= 45,
             'journal realtime search envelope too broad')
        result['argv'] = argv
        result['journal'] = new_journal_report()
        run_journal(tool, argv, result['journal'])
        result['tool_after'] = tool_identity(tool)
        need(result['tool_before'] == result['tool_after']
             and result['tool_after']['identity'] == stamp(os.stat('journalctl', dir_fd=bin_dir, follow_symlinks=False)),
             'held/named journalctl changed')
        result['boot_after'] = boot_id()
        result['runtime_after'] = read_runtime(root)
        need(result['runtime_before'] == result['runtime_after']
             and root_stamp == stamp(os.fstat(root))
             == stamp(os.stat(CFG['state_leaf'], dir_fd=opt, follow_symlinks=False)),
             'original state/runtime changed')
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

