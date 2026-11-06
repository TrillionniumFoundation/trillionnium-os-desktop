#!/usr/bin/env python3
"""Read only exact action-lock FD metadata in one bounded visible PID scan."""
import argparse
import errno
import hashlib
import json
import os
import re
import select
import stat
import sys
import time

LOCK = '/run/lock/android-digitalis-actions.lock'
LOCK_DEV, LOCK_INO = 28, 8312
LOCK_MODE = stat.S_IFREG | 0o600
PRIOR_SHA = '13179fb6aa36a1fde53892cc6287994ae269e492199a94eb12eeafe83fe290cc'
PRIOR_BYTES = 6053
PRIOR_NONCE = 'c398efeb8c07781670825f5ad68e13af'
PRIOR_SOURCE = '16f371bda457b830b11536f977a11f8dcce3347eded286605400a9162ba079a8'
VISIBLE_PID_MAX = 4096
PROC_ROOT_ENTRY_MAX = 8192
STAT_MAX = 16384
STATUS_MAX = 32768
CGROUP_MAX = 4096
LINK_MAX = 4096
FDINFO_MAX = 16384
MOUNTINFO_MAX = 524288
FD_PER_PROCESS_MAX = 4096
FD_TOTAL_MAX = 131072
MATCH_FD_MAX = 64
LOCK_ROWS_MAX = 32
DEADLINE_SECONDS = 15.0
OUTPUT_MAX = 2097152


def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def error_record(phase, error):
    # No rejected /proc/locks line or unrelated process data enters errors.
    return dict(phase=phase, type=type(error).__name__, errno=getattr(error, 'errno', None),
                message=str(error)[:512],
                close_notes=[str(note)[:160] for note in getattr(error, '_lock_close_notes', ())[:8]])

def parse_proc_stat(raw, expected_pid):
    need(type(raw) is bytes and 0 < len(raw) <= STAT_MAX and b'\0' not in raw, 'PID_STAT_BOUND')
    left, right = raw.find(b'('), raw.rfind(b')')
    need(left > 0 and right > left and raw[:left].strip() == str(expected_pid).encode(),
         'EXACT_PID_STAT_HEADER')
    fields = raw[right + 1:].split()
    need(len(fields) >= 20 and len(fields[0]) == 1 and fields[1].isdigit() and fields[19].isdigit(),
         'PID_STAT_REQUIRED_FIELDS')
    start = int(fields[19])
    need(start > 0, 'PID_BIRTH_TICKS_REQUIRED')
    return dict(pid=expected_pid, comm=raw[left + 1:right].decode('utf-8', 'replace'),
                state=fields[0].decode('ascii'), parent_pid=int(fields[1]), start_ticks=start)

def identity_key(metadata):
    return (metadata['device'], metadata['inode'])

def open_lock_metadata(support, deadline):
    """O_PATH only: never reads lock contents and never asks for a lock."""
    owned = []
    try:
        current = os.open('/', os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
        owned.append(current)
        parts = LOCK[1:].split('/')
        for part in parts[:-1]:
            support.check_time(deadline)
            child = os.open(part, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=current)
            owned.append(child)
            parent = current
            current = child
            # Transfer child ownership before the parent's close can raise.
            # Each close is attempted once: retrying a failed close can hit a
            # reused descriptor. An error prevents any complete/closed claim.
            owned.remove(parent)
            os.close(parent)
        support.check_time(deadline)
        fd = os.open(parts[-1], os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=current)
        owned.append(fd)
        m = support.metadata(fd)
        need((m['device'], m['inode'], m['mode'], m['uid'], m['gid'], m['nlink']) ==
             (LOCK_DEV, LOCK_INO, LOCK_MODE, 0, 0, 1), 'EXACT_ROOT0600_SINGLE_LOCK_INODE')
        # Keep the leaf owned until the last parent close has succeeded.
        owned.remove(current)
        os.close(current)
        owned.remove(fd)
        return fd, m
    except BaseException as error:
        notes = []
        for fd in reversed(owned):
            try:
                os.close(fd)
            except OSError as close_error:
                notes.append('temporary FD close failed: ' + type(close_error).__name__ +
                             ' errno=' + str(close_error.errno))
        if notes:
            error._lock_close_notes = tuple(notes)
        raise


class OwnedFDs:
    """Register ownership before any later operation can fail; close once."""
    def __init__(self):
        self.values = []
        self.close_errors = []

    def take(self, fd):
        need(type(fd) is int and fd >= 0 and fd not in self.values, 'NEW_OWNED_FD')
        self.values.append(fd)
        return fd

    def close(self, fd):
        need(fd in self.values, 'CLOSE_ONLY_OWNED_FD')
        self.values.remove(fd)
        primary = sys.exc_info()[1]
        try:
            os.close(fd)
        except OSError as error:
            # Do not retry an ambiguous close; the numeric FD may be reused.
            self.close_errors.append(error_record('owned_fd_close', error))
            if primary is None:
                raise
            primary._lock_close_notes = tuple(getattr(primary, '_lock_close_notes', ())) + (
                'owned FD close: ' + type(error).__name__ + ' errno=' + str(error.errno),)

    def finish(self):
        for fd in list(reversed(self.values)):
            try:
                self.close(fd)
            except OSError:
                pass


def metadata_from_stat(s):
    return dict(device=s.st_dev, inode=s.st_ino, mode=s.st_mode,
                uid=s.st_uid, gid=s.st_gid, nlink=s.st_nlink, size=s.st_size,
                mtime_ns=s.st_mtime_ns, ctime_ns=s.st_ctime_ns)


def open_fixed(fds, support, path, flags, deadline):
    """No-follow component walk; all temporary FDs belong to the outer scope."""
    need(type(path) is str and path.startswith('/') and '//' not in path, 'FIXED_ABSOLUTE_PATH')
    parts = path[1:].split('/')
    need(parts and all(p not in ('', '.', '..') for p in parts), 'FIXED_PATH_COMPONENT')
    current = fds.take(os.open('/', os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC))
    for part in parts[:-1]:
        support.check_time(deadline)
        child = fds.take(os.open(part, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                                 dir_fd=current))
        parent, current = current, child
        fds.close(parent)
    support.check_time(deadline)
    leaf = fds.take(os.open(parts[-1], flags | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=current))
    fds.close(current)
    return leaf


def read_input(fds, support, path, digest, length, deadline, anchor=None):
    fd = open_fixed(fds, support, path, os.O_RDONLY | os.O_NONBLOCK, deadline)
    try:
        before = support.metadata(fd)
        need(stat.S_ISREG(before['mode']) and before['nlink'] == 1 and
             0 < before['size'] <= support.INPUT_MAX, 'ORIGINAL_INPUT_SHAPE_BOUND')
        if anchor is not None:
            need(before == support.metadata(anchor['fd']) == anchor['metadata'], 'INPUT_NAMED_HELD_CHANGED')
        raw = support.read_bounded(fd, support.INPUT_MAX, deadline)
        after = support.metadata(fd)
        need(before == after and len(raw) == before['size'], 'ORIGINAL_INPUT_CHANGED')
        need((length is None or len(raw) == length) and sha(raw) == digest, 'ORIGINAL_INPUT_SIZE_SHA')
        return raw, dict(path=path, bytes=len(raw), sha256=sha(raw), before=before, after=after)
    finally:
        fds.close(fd)


def read_relative(fds, support, parent, name, maximum, deadline):
    need(type(name) is str and re.fullmatch(r'[A-Za-z0-9_]+', name), 'ONE_FIXED_PROC_COMPONENT')
    support.check_time(deadline)
    fd = fds.take(os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
                          dir_fd=parent))
    try:
        before = support.metadata(fd)
        need(stat.S_ISREG(before['mode']) and before['device'] == os.fstat(parent).st_dev,
             'SAME_PROC_REGULAR_FILE')
        raw = support.read_bounded(fd, maximum, deadline)
        need(raw and before == support.metadata(fd), 'PROC_FILE_EMPTY_OR_CHANGED')
        return raw
    finally:
        fds.close(fd)


def read_boot(fds, support, deadline):
    fd = open_fixed(fds, support, support.BOOT_ID, os.O_RDONLY | os.O_NONBLOCK, deadline)
    try:
        before = support.metadata(fd)
        need(stat.S_ISREG(before['mode']), 'BOOT_REGULAR_PROC_FILE')
        raw = support.read_bounded(fd, support.PSEUDO_MAX, deadline)
        need(raw and before == support.metadata(fd), 'BOOT_FILE_CHANGED')
        return dict(value=raw.decode('ascii').strip(), bytes=len(raw), sha256=sha(raw), metadata=before)
    finally:
        fds.close(fd)


def validate_prior(raw):
    need(type(raw) is bytes and len(raw) == PRIOR_BYTES and sha(raw) == PRIOR_SHA, 'EXACT_TICKET_LAUNCH')
    value = json.loads(raw)
    need(value['nonce'] == PRIOR_NONCE and value['source_manifest_sha256'] == PRIOR_SOURCE and
         value['package'] == 'com.MobileTicket' and value['uid'] == 10121 and
         value['helper_uid'] == 10190 and value['phase'] == 'launch', 'TICKET_FAILURE_SCOPE')
    lock = value['action_lock_admission']
    need(lock['path'] == LOCK and lock['opened_identity'] ==
         dict(device=LOCK_DEV, inode=LOCK_INO, mode=LOCK_MODE, uid=0, gid=0, nlink=1), 'TICKET_LOCK_IDENTITY')
    need(lock['acquired'] is False and lock['errno'] == 11 and lock['fd_closed_on_error'] is True and
         lock['attempts'] == lock['busy_attempts'] == 100 and lock['wait_limit_seconds'] == 5.0 and
         value['error']['phase'] == 'action_lock' and value['error']['errno'] == 11 and
         value['action_attempted'] is False and value['outcome_unknown'] is False and
         value['flow_lock_released'] is True and value['Main_before_lock'] == value['Main_after'],
         'ORIGINAL_TICKET_ZERO_ACTION_FAILURE')
    return value




def pidfd_alive(pidfd):
    poller = select.poll()
    poller.register(pidfd, select.POLLIN | select.POLLHUP | select.POLLERR | select.POLLNVAL)
    events = poller.poll(0)
    need(events == [], 'FIXED_PROCESS_PIDFD_NO_LONGER_LIVE')
    return []


def inode_identity(metadata):
    # nsfs timestamps and proc-directory link counts are observations, not identity.
    return {key: metadata[key] for key in ('device', 'inode', 'mode', 'uid', 'gid')}


def namespace_identity(namespaces):
    return {name: dict(label=row['label'], identity=inode_identity(row['metadata']))
            for name, row in namespaces.items()}


def namespace_metadata(fds, support, procfd, deadline):
    support.check_time(deadline)
    nsfd = fds.take(os.open('ns', os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=procfd))
    try:
        result = {}
        for name in ('pid', 'mnt'):
            support.check_time(deadline)
            label = os.readlink(name, dir_fd=nsfd)
            need(re.fullmatch(name + r':\[[0-9]{1,20}\]', label), 'FIXED_NAMESPACE_LINK_SHAPE')
            before = metadata_from_stat(os.stat(name, dir_fd=nsfd, follow_symlinks=True))
            after = metadata_from_stat(os.stat(name, dir_fd=nsfd, follow_symlinks=True))
            need(inode_identity(before) == inode_identity(after) and stat.S_ISREG(before['mode']) and
                 label == os.readlink(name, dir_fd=nsfd) and
                 before['inode'] == int(label.split('[')[1][:-1]), 'NAMESPACE_IDENTITY_CHANGED')
            # Labels are never followed as external paths; times remain raw evidence.
            result[name] = dict(label=label, metadata=before, named_after_metadata=after)
        return result
    finally:
        fds.close(nsfd)


def process_sample(fds, support, procfd, pidfd, pid, deadline):
    """Read process details only after an exact lock-inode FD was observed."""
    pidfd_alive(pidfd)
    first = parse_proc_stat(read_relative(fds, support, procfd, 'stat', STAT_MAX, deadline), pid)
    need(first['state'] not in ('Z', 'X', 'x'), 'MATCHED_PROCESS_NOT_LIVE')
    raw = read_relative(fds, support, procfd, 'status', STATUS_MAX, deadline)
    fields = {}
    for line in raw.decode('ascii', 'strict').splitlines():
        if ':' in line:
            key, value = line.split(':', 1)
            if key in ('Uid', 'NSpid'):
                need(key not in fields and value.split() and all(p.isdigit() for p in value.split()),
                     'MATCHED_PROCESS_STATUS_FORMAT')
                fields[key] = [int(p) for p in value.split()]
    need(len(fields.get('Uid', [])) == 4 and 1 <= len(fields.get('NSpid', [])) <= 32 and
         fields['NSpid'][0] == pid, 'MATCHED_PROCESS_UID_AND_NAMESPACE_PID_SHAPE')
    ns = namespace_metadata(fds, support, procfd, deadline)
    cgroup = read_relative(fds, support, procfd, 'cgroup', CGROUP_MAX, deadline).decode('ascii').splitlines()
    need(cgroup and len(cgroup) <= 64, 'MATCHED_PROCESS_CGROUP_BOUND')
    link = os.readlink('exe', dir_fd=procfd)
    need(link.startswith('/') and len(os.fsencode(link)) <= LINK_MAX, 'MATCHED_PROCESS_EXECUTABLE_SHAPE')
    exe = fds.take(os.open('exe', os.O_PATH | os.O_CLOEXEC, dir_fd=procfd))
    try:
        executable = support.metadata(exe)
        named = metadata_from_stat(os.stat('exe', dir_fd=procfd, follow_symlinks=True))
        need(stat.S_ISREG(executable['mode']) and executable == support.metadata(exe) == named and
             link == os.readlink('exe', dir_fd=procfd), 'MATCHED_PROCESS_EXE_METADATA_CHANGED')
    finally:
        fds.close(exe)
    last = parse_proc_stat(read_relative(fds, support, procfd, 'stat', STAT_MAX, deadline), pid)
    need(last['state'] not in ('Z', 'X', 'x') and all(first[k] == last[k]
         for k in ('pid', 'comm', 'parent_pid', 'start_ticks')), 'MATCHED_PROCESS_STAT_CHANGED_DURING_SAMPLE')
    pidfd_alive(pidfd)
    return dict(stat=last, uids=fields['Uid'], namespace_pids=fields['NSpid'], namespaces=ns,
                executable=dict(path=link, metadata=executable), cgroup=cgroup,
                process_directory=support.metadata(procfd), pidfd_events=[],
                observed_monotonic_ns=time.monotonic_ns())


def stable_process_part(value):
    return dict(uids=value['uids'], namespace_pids=value['namespace_pids'],
                namespaces=namespace_identity(value['namespaces']), executable=value['executable'],
                cgroup=value['cgroup'], process_directory=inode_identity(value['process_directory']),
                stat={key: value['stat'][key] for key in ('pid', 'parent_pid', 'start_ticks', 'comm')})


def parse_fd_name(name):
    need(type(name) is str and re.fullmatch(r'0|[1-9][0-9]{0,9}', name) is not None and
         int(name) <= 2147483647, 'PROC_FD_NUMERIC_NAME')
    return int(name)


def directory_names(fd, support, budget, deadline):
    iterator = None
    primary = None
    names = []
    try:
        iterator = os.scandir(fd)
        for entry in iterator:
            support.check_time(deadline)
            number = parse_fd_name(entry.name)
            need(len(names) < FD_PER_PROCESS_MAX and budget['enumerated'] < FD_TOTAL_MAX, 'FD_ENUMERATION_BOUND')
            names.append(number)
            budget['enumerated'] += 1
        need(len(names) == len(set(names)), 'DUPLICATE_PROC_FD_ENTRY')
    except BaseException as error:
        primary = error
    finally:
        if iterator is not None:
            try:
                iterator.close()
            except BaseException as error:
                if primary is None:
                    primary = error
                else:
                    primary._lock_close_notes = tuple(getattr(primary, '_lock_close_notes', ())) + (
                        'directory iterator close: ' + type(error).__name__ + ' errno=' + str(getattr(error, 'errno', None)),)
    if primary is not None:
        raise primary
    return sorted(names)


def parse_fdinfo(raw):
    need(type(raw) is bytes and 0 < len(raw) <= FDINFO_MAX and b'\0' not in raw, 'MATCHED_FDINFO_BOUND')
    values, locks = {}, []
    for line in raw.decode('ascii', 'strict').splitlines():
        need(0 < len(line) <= 2048 and ':' in line, 'MATCHED_FDINFO_LINE')
        key, value = line.split(':', 1)
        value = value.strip()
        if key == 'lock':
            need(len(locks) < LOCK_ROWS_MAX, 'MATCHED_FDINFO_LOCK_ROW_BOUND')
            fields = value.split()
            waiting = len(fields) > 1 and fields[1] == '->'
            if waiting:
                fields.pop(1)
            need(len(fields) == 8 and re.fullmatch(r'[0-9]{1,20}:', fields[0]) and
                 fields[1] in ('FLOCK', 'OFDLCK', 'POSIX') and fields[2] in ('ADVISORY', 'MANDATORY') and
                 fields[3] in ('READ', 'WRITE') and re.fullmatch(r'-?[0-9]{1,10}', fields[4]),
                 'MATCHED_FDINFO_LOCK_SHAPE')
            pid = int(fields[4])
            need(-1 <= pid <= 2147483647, 'MATCHED_FDINFO_PID_BOUND')
            match = re.fullmatch(r'([0-9a-fA-F]{1,16}):([0-9a-fA-F]{1,16}):([0-9]{1,20})', fields[5])
            need(match is not None and (int(match[1], 16), int(match[2], 16), int(match[3])) ==
                 (os.major(LOCK_DEV), os.minor(LOCK_DEV), LOCK_INO), 'MATCHED_FDINFO_EXACT_LOCK_INODE')
            need(re.fullmatch(r'[0-9]{1,20}', fields[6]) and
                 (fields[7] == 'EOF' or re.fullmatch(r'[0-9]{1,20}', fields[7])), 'MATCHED_FDINFO_LOCK_RANGE')
            locks.append(dict(kind=fields[1], mode=fields[2], access=fields[3], waiting=waiting,
                              kernel_reported_pid=pid, range_start=fields[6], range_end=fields[7],
                              raw_matching_line=value))
        else:
            need(key in ('pos', 'flags', 'mnt_id', 'ino') and key not in values, 'MATCHED_REGULAR_FDINFO_KEYS')
            pattern = r'[0-7]{1,24}' if key == 'flags' else r'[0-9]{1,20}'
            need(re.fullmatch(pattern, value), 'MATCHED_FDINFO_SCALAR')
            values[key] = value
    need(set(values) == {'pos', 'flags', 'mnt_id', 'ino'} and int(values['ino']) == LOCK_INO and
         int(values['mnt_id']) > 0, 'MATCHED_FDINFO_REQUIRED_IDENTITY')
    return dict(pos=values['pos'], flags=values['flags'], mnt_id=values['mnt_id'], ino=LOCK_INO,
                lock_records=locks, bytes_read=len(raw), sha256=sha(raw),
                lock_PID_is_not_a_process_birth_or_cleanup_authority=True)


def parse_proc_mount(raw):
    need(type(raw) is bytes and 0 < len(raw) <= MOUNTINFO_MAX and b'\0' not in raw, 'SELF_MOUNTINFO_BOUND')
    matches = []
    for line in raw.decode('ascii', 'strict').splitlines():
        need(0 < len(line) <= 16384, 'SELF_MOUNTINFO_LINE_BOUND')
        fields = line.split()
        need(len(fields) >= 10 and '-' in fields and fields[0].isdigit() and fields[1].isdigit(),
             'SELF_MOUNTINFO_FORMAT')
        if fields[4] != '/proc':
            continue
        split = fields.index('-')
        need(split >= 6 and len(fields) == split + 4 and fields[split + 1] == 'proc' and
             re.fullmatch(r'[0-9]+:[0-9]+', fields[2]), 'EXACT_PROC_MOUNT_ROW')
        matches.append(dict(mount_id=int(fields[0]), parent_id=int(fields[1]), device=fields[2],
                            root=fields[3], mount_point='/proc', filesystem_type='proc'))
    need(len(matches) == 1, 'ONE_EXACT_PROC_MOUNT_OBSERVATION')
    return dict(record=matches[0], source_bytes=len(raw), source_sha256=sha(raw),
                unrelated_mount_rows_exported=0, proc_superblock_pid_namespace_proven=False)


def self_context(fds, support, deadline):
    proc = open_fixed(fds, support, '/proc', os.O_PATH | os.O_DIRECTORY, deadline)
    own = None
    try:
        pid = os.getpid()
        own = fds.take(os.open(str(pid), os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                dir_fd=proc))
        sample = parse_proc_stat(read_relative(fds, support, own, 'stat', STAT_MAX, deadline), pid)
        namespaces = namespace_metadata(fds, support, own, deadline)
        mount = parse_proc_mount(read_relative(fds, support, own, 'mountinfo', MOUNTINFO_MAX, deadline))
        need(parse_proc_stat(read_relative(fds, support, own, 'stat', STAT_MAX, deadline), pid)['start_ticks'] ==
             sample['start_ticks'], 'SELF_BIRTH_CHANGED')
        release = os.uname().release
        need(type(release) is str and 0 < len(os.fsencode(release)) <= 256, 'KERNEL_RELEASE_BOUND')
        return dict(pid=pid, parent_pid=sample['parent_pid'], start_ticks=sample['start_ticks'],
                    namespaces=namespaces, proc_root=support.metadata(proc), proc_mount=mount,
                    kernel_release=release, namespace_links_are_never_followed_as_external_paths=True)
    finally:
        if own is not None:
            fds.close(own)
        fds.close(proc)


def stable_self_part(value):
    return dict(pid=value['pid'], parent_pid=value['parent_pid'], start_ticks=value['start_ticks'],
                namespaces=namespace_identity(value['namespaces']), proc_root=inode_identity(value['proc_root']),
                proc_mount=value['proc_mount']['record'], kernel_release=value['kernel_release'])


def numeric_pid_names(procfd, support, deadline):
    iterator = None
    primary = None
    names = []
    entries = 0
    try:
        iterator = os.scandir(procfd)
        for entry in iterator:
            support.check_time(deadline)
            need(entries < PROC_ROOT_ENTRY_MAX, 'PROC_ROOT_DIRECTORY_ENTRY_BOUND')
            entries += 1
            if not entry.name.isascii() or not entry.name.isdigit():
                continue
            pid = parse_fd_name(entry.name)
            need(pid > 0 and len(names) < VISIBLE_PID_MAX, 'VISIBLE_NUMERIC_PID_BOUND')
            names.append(pid)
        need(len(names) == len(set(names)), 'DUPLICATE_VISIBLE_PID_ENTRY')
    except BaseException as error:
        primary = error
    finally:
        if iterator is not None:
            try:
                iterator.close()
            except BaseException as error:
                if primary is None:
                    primary = error
                else:
                    primary._lock_close_notes = tuple(getattr(primary, '_lock_close_notes', ())) + (
                        'proc iterator close: ' + type(error).__name__ + ' errno=' + str(getattr(error, 'errno', None)),)
    if primary is not None:
        raise primary
    return sorted(names), entries


def coverage_gap(coverage, phase, error):
    # No unmatched PID, FD number, name, path or exception message is exported.
    row = next((item for item in coverage['gaps'] if item['phase'] == phase and
                item['errno'] == getattr(error, 'errno', None) and item['type'] == type(error).__name__), None)
    if row is None:
        need(len(coverage['gaps']) < 64, 'AGGREGATE_COVERAGE_ERROR_BOUND')
        row = dict(phase=phase, type=type(error).__name__, errno=getattr(error, 'errno', None), count=0)
        coverage['gaps'].append(row)
    row['count'] += 1


def scan_process(fds, support, procroot, pid, lock_metadata, budget, coverage, deadline):
    """Only exact lock-FD matches cause new process-content or fdinfo reads."""
    procfd = fd_dir = info_dir = pidfd = None
    row = None
    enumerated = attempted = 0
    enumeration_complete = False

    def remember(phase, error):
        if row is not None:
            item = error_record(phase, error)
            if row['first_error'] is None:
                row['first_error'] = item
            else:
                row['secondary_errors'].append(item)
        coverage_gap(coverage, phase, error)

    def named_process_check():
        named = fds.take(os.open(str(pid), os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                 dir_fd=procroot))
        try:
            value = support.metadata(named)
            need(inode_identity(value) == inode_identity(support.metadata(procfd)), 'MATCHED_NAMED_PROC_CHANGED')
            pidfd_alive(pidfd)
            return value
        finally:
            fds.close(named)

    try:
        support.check_time(deadline)
        procfd = fds.take(os.open(str(pid), os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                  dir_fd=procroot))
        need(os.fstat(procfd).st_dev == os.fstat(procroot).st_dev, 'VISIBLE_PROC_DIRECTORY_DEVICE')
        fd_dir = fds.take(os.open('fd', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                  dir_fd=procfd))
        need(os.fstat(fd_dir).st_dev == os.fstat(procfd).st_dev, 'VISIBLE_FD_DIRECTORY_DEVICE')
        names = directory_names(fd_dir, support, budget, deadline)
        enumerated = len(names)
        for number in names:
            support.check_time(deadline)
            attempted += 1
            coverage['fd_stat_attempts'] += 1
            try:
                before = metadata_from_stat(os.stat(str(number), dir_fd=fd_dir, follow_symlinks=True))
            except OSError as error:
                coverage_gap(coverage, 'fd_target_stat', error)
                continue
            if identity_key(before) != (LOCK_DEV, LOCK_INO):
                continue
            need(budget['matches'] < MATCH_FD_MAX, 'MATCHING_FD_OUTPUT_BOUND')
            budget['matches'] += 1
            if row is None:
                row = dict(pid=pid, matched_fds=[], first_error=None, secondary_errors=[], complete=False,
                           observation_grants_signal_or_cleanup_authority=False)
            match = dict(fd=number, target_before=before, complete=False, error=None)
            row['matched_fds'].append(match)
            info_fd = None
            try:
                need(before == lock_metadata, 'MATCHED_FD_EXACT_LOCK_METADATA')
                if pidfd is None:
                    pidfd = fds.take(os.pidfd_open(pid, 0))
                    need(not os.get_inheritable(pidfd), 'PIDFD_CLOEXEC_REQUIRED')
                    pidfd_alive(pidfd)
                    row['named_proc_before'] = named_process_check()
                    row['before'] = process_sample(fds, support, procfd, pidfd, pid, deadline)
                    row['named_proc_after_initial_sample'] = named_process_check()
                need('before' in row and 'named_proc_after_initial_sample' in row,
                     'MATCHED_PROCESS_INITIAL_IDENTITY_REQUIRED')
                if info_dir is None:
                    info_dir = fds.take(os.open('fdinfo', os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                                dir_fd=procfd))
                    need(os.fstat(info_dir).st_dev == os.fstat(procfd).st_dev, 'MATCHED_FDINFO_DIRECTORY_DEVICE')
                info_fd = fds.take(os.open(str(number), os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
                                           dir_fd=info_dir))
                info_before = support.metadata(info_fd)
                need(stat.S_ISREG(info_before['mode']) and info_before['device'] == os.fstat(procfd).st_dev,
                     'MATCHED_FDINFO_PROC_DEVICE')
                raw = support.read_bounded(info_fd, FDINFO_MAX, deadline)
                match['fdinfo'] = parse_fdinfo(raw)
                coverage['matched_fdinfo_bytes'] += len(raw)
                need(info_before == support.metadata(info_fd), 'MATCHED_FDINFO_FILE_CHANGED')
                match['target_after'] = metadata_from_stat(os.stat(str(number), dir_fd=fd_dir, follow_symlinks=True))
                need(before == match['target_after'], 'MATCHED_FD_TARGET_CHANGED')
                pidfd_alive(pidfd)
                match.update(complete=True, observed_monotonic_ns=time.monotonic_ns(),
                             same_open_file_description_proven=False, historical_sender_proven=False)
            except Exception as error:
                match['error'] = error_record('matching_fd_sample', error)
                remember('matching_fd_sample', error)
            finally:
                if info_fd is not None:
                    try:
                        fds.close(info_fd)
                    except OSError as error:
                        remember('matching_fdinfo_close', error)
        enumeration_complete = True
        coverage['pid_fd_enumerations_completed'] += 1
    except Exception as error:
        remember('visible_pid_fd_scan', error)
    finally:
        if row is not None and pidfd is not None:
            try:
                row['after'] = process_sample(fds, support, procfd, pidfd, pid, deadline)
                need('before' in row and stable_process_part(row['before']) == stable_process_part(row['after']),
                     'MATCHED_PROCESS_BEFORE_AFTER_CHANGED')
                row['named_proc_after'] = named_process_check()
            except Exception as error:
                remember('matched_process_final_identity', error)
        for fd in (info_dir, fd_dir, pidfd, procfd):
            if fd is not None:
                try:
                    fds.close(fd)
                except OSError as error:
                    remember('visible_process_owned_FD_close', error)
    if row is not None:
        row.update(enumerated_fd_count=enumerated, fd_stat_attempts=attempted,
                   enumeration_complete=enumeration_complete)
        row['complete'] = (enumeration_complete and row['first_error'] is None and
                           not row['secondary_errors'] and 'named_proc_after' in row and
                           all(item['complete'] for item in row['matched_fds']))
    return row


def collect(support, prior_raw):
    prior = validate_prior(prior_raw)
    started = time.monotonic()
    deadline = started + DEADLINE_SECONDS
    result = dict(schema=1, collection_complete=False, scan_completed=False, coverage_complete=False,
                  error=None, secondary_errors=[],
                  scope='one bounded visible numeric-PID FD metadata scan for the exact action-lock inode',
                  prior_failure=dict(bytes=PRIOR_BYTES, sha256=PRIOR_SHA, nonce=PRIOR_NONCE),
                  lock_path=LOCK, expected_lock=dict(device=LOCK_DEV, inode=LOCK_INO, mode=LOCK_MODE, uid=0, gid=0, nlink=1),
                  inputs={}, final_inputs={}, matched_processes=[], main_guard_before=None, main_guard_after=None,
                  original_Main_guard_unchanged=True, output_is_sequential_not_atomic=True,
                  runtime_authorized=False, observation_grants_kill_or_cleanup_authority=False,
                  no_match_proves_no_holder=False, same_open_file_description_proven=False,
                  fdinfo_PID_is_not_birth_or_original_sender=True, historical_sender_proven=False,
                  original_Main_guard_fixed_process_reads_retained=True,
                  visible_PID_limit=VISIBLE_PID_MAX, proc_root_entry_limit=PROC_ROOT_ENTRY_MAX,
                  per_process_fd_limit=FD_PER_PROCESS_MAX, total_fd_limit=FD_TOTAL_MAX,
                  fdinfo_maximum_bytes=FDINFO_MAX, maximum_matching_fds=MATCH_FD_MAX,
                  deadline_seconds=DEADLINE_SECONDS, lock_table_reads=0,
                  only_numeric_proc_root_directories_scanned=True, task_subdirectories_scanned=False,
                  initial_host_PID_namespace_visibility_proven=False,
                  visibility_limits=['one current /proc view', 'numeric leader directories only',
                                     'transient process/FD disappearance stays uncovered',
                                     'nonleader private FD tables and kernel in-flight references not examined'],
                  unmatched_PID_details_exported=0, unmatched_process_content_reads=0,
                  unrelated_fd_content_reads=0, fd_target_readlink_calls=0,
                  pidfd_getfd_calls=0, flock_calls=0, lock_content_reads=0, lock_writes=0,
                  lock_replacement_or_deletion=0, process_signals=0, process_starts=0,
                  namespace_entries=0, SCM_RIGHTS_operations=0, Android_actions=0,
                  owned_fds_closed=False)
    fds = OwnedFDs()
    anchors = {}
    activation = reference = epoch = None
    lockfd = procroot = None
    budget = dict(enumerated=0, matches=0)
    coverage = dict(visible_numeric_PID_count=0, root_directory_entries=0, excluded_collector_PID=None,
                    pid_scans_attempted=0, pid_fd_enumerations_completed=0, fd_stat_attempts=0,
                    matched_fdinfo_bytes=0, gaps=[])

    def remember(phase, error):
        row = error_record(phase, error)
        if result['error'] is None:
            result['error'] = row
        else:
            result['secondary_errors'].append(row)

    def guard(label):
        support.check_time(deadline)
        value = reference.main_guard(activation, epoch)
        support.check_time(deadline)
        need(value == prior['Main_before_lock'], 'ORIGINAL_MAIN_GUARD_RESULT_CHANGED')
        result[label] = value

    try:
        need(os.getuid() == os.geteuid() == 0, 'ROOT_READ_ONLY_REQUIRED')
        bodies = {}
        for name, path, digest, length in support.INPUTS:
            raw, record = read_input(fds, support, path, digest, length, deadline)
            fd = open_fixed(fds, support, path, os.O_RDONLY | os.O_NONBLOCK, deadline)
            need(support.metadata(fd) == record['before'], 'ORIGINAL_INPUT_ANCHOR_CHANGED')
            anchors[name] = dict(fd=fd, metadata=record['before'])
            bodies[name], result['inputs'][name] = raw, record
        activation = json.loads(bodies['activation'])
        need(activation['framework_epoch']['sha256'] == support.EPOCH_SHA, 'ORIGINAL_MAIN_EPOCH')
        reference = support.load_exact_source(bodies['reference_source'], support.REFERENCE, 'original_visible_fd_Main_reference')
        epoch = support.load_exact_source(bodies['epoch_source'], support.EPOCH_SOURCE, 'original_visible_fd_Main_epoch')
        need(str(reference.ACTIVATION) == support.ACTIVATION and str(reference.VERIFIED) == support.VERIFIED and
             str(reference.EPOCH_SOURCE) == support.EPOCH_SOURCE and str(reference.MAIN_CGROUP) == support.CGROUP and
             reference.EPOCH == support.EPOCH_SHA and reference.ACTIVATION_SHA == support.INPUTS[0][2] and
             reference.VERIFIED_SHA == support.INPUTS[1][2] and reference.CELL_SHA == support.INPUTS[2][2] and
             reference.EPOCH_SOURCE_SHA == support.INPUTS[4][2], 'EXACT_ORIGINAL_REFERENCE_CONSTANTS')
        guard('main_guard_before')
        result['boot_before'] = read_boot(fds, support, deadline)
        need(result['boot_before']['value'] == activation['framework_epoch']['binding']['boot_id'], 'ORIGINAL_BOOT_ID')
        lockfd, result['lock_before'] = open_lock_metadata(support, deadline)
        fds.take(lockfd)
        result['self_before'] = self_context(fds, support, deadline)
        procroot = open_fixed(fds, support, '/proc', os.O_RDONLY | os.O_DIRECTORY, deadline)
        result['proc_root_before'] = support.metadata(procroot)
        need(inode_identity(result['proc_root_before']) == inode_identity(result['self_before']['proc_root']),
             'FIXED_PROC_ROOT_IDENTITY')
        pids, entries = numeric_pid_names(procroot, support, deadline)
        own_pid = os.getpid()
        need(own_pid == result['self_before']['pid'] and own_pid in pids, 'COLLECTOR_VISIBLE_PID_CONTEXT')
        coverage.update(visible_numeric_PID_count=len(pids), root_directory_entries=entries,
                        excluded_collector_PID=own_pid)
        for pid in pids:
            support.check_time(deadline)
            if pid == own_pid:
                continue
            coverage['pid_scans_attempted'] += 1
            row = scan_process(fds, support, procroot, pid, result['lock_before'], budget, coverage, deadline)
            if row is not None:
                result['matched_processes'].append(row)
        result['scan_completed'] = True
        result['coverage_complete'] = (not coverage['gaps'] and
            coverage['pid_fd_enumerations_completed'] == coverage['pid_scans_attempted'] == len(pids) - 1 and
            coverage['fd_stat_attempts'] == budget['enumerated'] and
            all(row['complete'] for row in result['matched_processes']))
        if not result['coverage_complete']:
            remember('visible_PID_FD_coverage', RuntimeError('ONE_OR_MORE_VISIBLE_PID_FD_OBSERVATIONS_INCOMPLETE'))
    except Exception as error:
        remember('visible_lock_FD_collection', error)
    finally:
        result['fd_counts'], result['coverage'] = budget, coverage
        if procroot is not None:
            named = None
            try:
                result['proc_root_after'] = support.metadata(procroot)
                named = open_fixed(fds, support, '/proc', os.O_PATH | os.O_DIRECTORY, deadline)
                result['proc_root_named_after'] = support.metadata(named)
                need(inode_identity(result['proc_root_before']) == inode_identity(result['proc_root_after']) ==
                     inode_identity(result['proc_root_named_after']), 'PROC_ROOT_HELD_NAMED_IDENTITY_CHANGED')
            except Exception as error:
                remember('final_proc_root', error)
            finally:
                if named is not None:
                    try:
                        fds.close(named)
                    except OSError as error:
                        remember('final_named_proc_root_close', error)
        if 'self_before' in result:
            try:
                result['self_after'] = self_context(fds, support, deadline)
                need(stable_self_part(result['self_before']) == stable_self_part(result['self_after']),
                     'SELF_OR_PROC_IDENTITY_CHANGED')
            except Exception as error:
                remember('final_self_proc_context', error)
        if lockfd is not None:
            named = None
            try:
                named, result['lock_named_after'] = open_lock_metadata(support, deadline)
                fds.take(named)
                result['lock_after'] = support.metadata(lockfd)
                need(result['lock_before'] == result['lock_after'] == result['lock_named_after'], 'ORIGINAL_LOCK_HELD_NAMED_CHANGED')
            except Exception as error:
                remember('final_lock_identity', error)
            finally:
                if named is not None:
                    try:
                        fds.close(named)
                    except OSError as error:
                        remember('final_named_lock_close', error)
        if activation is not None:
            try:
                result['boot_after'] = read_boot(fds, support, deadline)
                need(result['boot_after']['value'] == activation['framework_epoch']['binding']['boot_id'] ==
                     result.get('boot_before', {}).get('value'), 'ORIGINAL_BOOT_CHANGED_OR_MISSING')
            except Exception as error:
                remember('final_boot', error)
        if reference is not None and epoch is not None:
            try:
                guard('main_guard_after')
            except Exception as error:
                remember('final_original_Main_guard', error)
        for name, path, digest, length in support.INPUTS:
            if name in anchors:
                try:
                    _, result['final_inputs'][name] = read_input(fds, support, path, digest, length, deadline, anchors[name])
                except Exception as error:
                    remember('final_original_input:' + name, error)
        fds.finish()
        if fds.close_errors:
            result['secondary_errors'].extend(fds.close_errors)
        result['owned_fds_closed'] = not fds.values and not fds.close_errors
        result['collection_complete'] = (result['scan_completed'] and result['coverage_complete'] and
            result['error'] is None and not result['secondary_errors'] and result['owned_fds_closed'] and
            len(result['final_inputs']) == 5 and
            result['main_guard_before'] == result['main_guard_after'] == prior['Main_before_lock'])
        result['elapsed_ms'] = int((time.monotonic() - started) * 1000)
    return result


def main(support, prior_raw, argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect-once', action='store_true')
    args = parser.parse_args(argv)
    if args.collect_once:
        result = collect(support, prior_raw)
    else:
        result = dict(state='PLAN_ONLY', visible_numeric_PID_limit=VISIBLE_PID_MAX,
                      proc_root_directory_entry_limit=PROC_ROOT_ENTRY_MAX,
                      lock_path=LOCK, lock_device=LOCK_DEV, lock_inode=LOCK_INO,
                      per_process_fd_limit=FD_PER_PROCESS_MAX, total_fd_limit=FD_TOTAL_MAX,
                      maximum_matching_fds=MATCH_FD_MAX, fdinfo_maximum_bytes=FDINFO_MAX,
                      deadline_seconds=DEADLINE_SECONDS, original_Main_guard_calls=2,
                      collector_own_PID_excluded=True, only_matched_process_details=True,
                      runtime_authorized=False, remote_actions=0)
    raw = (json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(',', ':')) + '\n').encode('ascii')
    need(len(raw) <= OUTPUT_MAX, 'COMPLETE_OUTPUT_BOUND_NO_TRUNCATION')
    print(raw.decode('ascii'), end='', flush=True)
    return 0 if not args.collect_once or result['collection_complete'] else 1

