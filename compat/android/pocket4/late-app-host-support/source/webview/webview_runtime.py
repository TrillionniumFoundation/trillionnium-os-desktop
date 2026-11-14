"""Same-process case owner, original absolute leases and whole-case OFD."""
import fcntl
import os
from pathlib import Path
import stat
import time

ACTION_LOCK = '/run/lock/android-digitalis-actions.lock'


def fd_identity(info):
    return {k: getattr(info, k) for k in ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink')}


class ActionLock:
    def __init__(self, c, host, root, path=ACTION_LOCK):
        self.c, self.host, self.path, self.fd = c, host, path, None
        self.closed = False
        try:
            self.fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
            self.file = fd_identity(os.fstat(self.fd)); self.owner = host.process(c, os.getpid())
            self._check()
            self.ref = c.write_new(Path(root) / 'action-lock.json', {
                'schema': 'pocket4-final-system-same-process-action-lock-v1', 'path': path,
                'file': self.file, 'owner': self.owner, 'boot_id': host.boot(),
                'one_open_file_description': True, 'transferred_descriptors': 0,
                'automatic_retry': False}, 0o400)
        except BaseException:
            if self.fd is not None:
                os.close(self.fd); self.fd = None
            raise

    def _check(self):
        c = self.c
        c.need(not self.closed and self.fd is not None and
            self.host.process(c, os.getpid()) == self.owner, 'SAME_ROOT_CASE_LOCK_OWNER_REQUIRED')
        info = os.fstat(self.fd)
        c.need(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
            and fd_identity(info) == self.file == fd_identity(Path(self.path).lstat())
            and not os.get_inheritable(self.fd), 'ACTUAL_SAME_ACTION_LOCK_OFD_REQUIRED')
        fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def verify(self):
        self._check(); self.c.read_ref(self.ref)

    def close(self):
        if self.fd is not None:
            os.close(self.fd); self.fd = None
        self.closed = True


def create_lease(c, host, base_ref, base):
    now = time.monotonic_ns(); seconds = base['limits']['business_seconds']
    c.need(seconds == {'webview_business10': 630, 'webview_media11': 450}[base['kind']], 'ORIGINAL_WORK_LEASE_REQUIRED')
    value = {'schema': 'pocket4-final-system-case-lease-v1', 'base_plan': base_ref,
        'kind': base['kind'], 'boot_id': host.boot(), 'owner': host.process(c, os.getpid()),
        'started_monotonic_ns': now, 'business_deadline_monotonic_ns': now + seconds * 1000000000,
        'business_seconds': seconds, 'cleanup_seconds': base['limits']['cleanup_seconds'],
        'automatic_retry': False}
    return c.write_new(Path(base['case_root']) / 'lease.json', value, 0o400)


def validate_lease(c, host, ref, base_ref, base, *, cleanup=False):
    value = c.parse(c.read_ref(ref)); fields = {'schema', 'base_plan', 'kind', 'boot_id', 'owner',
        'started_monotonic_ns', 'business_deadline_monotonic_ns', 'business_seconds', 'cleanup_seconds', 'automatic_retry'}
    c.need(set(value) == fields and value['schema'] == 'pocket4-final-system-case-lease-v1'
        and value['base_plan'] == base_ref and value['kind'] == base['kind'] and value['boot_id'] == host.boot()
        and value['business_seconds'] == base['limits']['business_seconds']
        and value['cleanup_seconds'] == base['limits']['cleanup_seconds'] and value['automatic_retry'] is False
        and type(value['started_monotonic_ns']) is type(value['business_deadline_monotonic_ns']) is int
        and value['business_deadline_monotonic_ns'] == value['started_monotonic_ns'] + value['business_seconds'] * 1000000000
        and host.process(c, os.getpid()) == value['owner'], 'EXACT_SAME_PROCESS_ORIGINAL_CASE_LEASE')
    extra = value['cleanup_seconds'] * 1000000000 if cleanup else 0
    c.need(value['started_monotonic_ns'] <= time.monotonic_ns() < value['business_deadline_monotonic_ns'] + extra,
           'ORIGINAL_SYSTEM_LEASE_EXPIRED')
    return value


def phase(c, host, active_ref, active, name, trigger=None):
    c.need(name in ('business', 'final_cleanup') and (trigger is not None) == (name == 'final_cleanup'),
           'ONLY_ORIGINAL_WORK_AND_ONCE_FINAL_CLEANUP_PHASES')
    lease = validate_lease(c, host, active['lease'], active['base_plan'], active, cleanup=name == 'final_cleanup')
    now = time.monotonic_ns()
    if trigger is not None:
        c.read_ref(trigger)
    deadline = lease['business_deadline_monotonic_ns'] if name == 'business' else min(
        now + lease['cleanup_seconds'] * 1000000000,
        lease['business_deadline_monotonic_ns'] + lease['cleanup_seconds'] * 1000000000)
    c.need(now < deadline, 'NO_CASE_PHASE_AFTER_ABSOLUTE_DEADLINE')
    return c.write_new(Path(active['case_root']) / ('phase-' + name + '.json'), {
        'schema': 'pocket4-final-system-phase-lease-v1', 'active_plan': active_ref, 'lease': active['lease'],
        'phase': name, 'owner': lease['owner'], 'started_monotonic_ns': now,
        'deadline_monotonic_ns': deadline, 'trigger': trigger, 'automatic_retry': False}, 0o400)


def validate_phase(c, host, ref, active_ref, active):
    value = c.parse(c.read_ref(ref)); fields = {'schema', 'active_plan', 'lease', 'phase', 'owner',
        'started_monotonic_ns', 'deadline_monotonic_ns', 'trigger', 'automatic_retry'}
    c.need(set(value) == fields and value['schema'] == 'pocket4-final-system-phase-lease-v1'
        and value['active_plan'] == active_ref and value['lease'] == active['lease']
        and value['phase'] in ('business', 'final_cleanup') and value['automatic_retry'] is False,
        'ACTUAL_SOURCE_BOUND_SYSTEM_PHASE_REQUIRED')
    cleanup = value['phase'] == 'final_cleanup'
    lease = validate_lease(c, host, active['lease'], active['base_plan'], active, cleanup=cleanup)
    start, deadline = value['started_monotonic_ns'], value['deadline_monotonic_ns']
    c.need(type(start) is type(deadline) is int and lease['started_monotonic_ns'] <= start <= time.monotonic_ns() < deadline
        and value['owner'] == lease['owner'] and (value['trigger'] is not None) == cleanup,
        'ACTUAL_PHASE_OWNER_TIME_AND_TRIGGER_REQUIRED')
    expected = min(start + lease['cleanup_seconds'] * 1000000000,
        lease['business_deadline_monotonic_ns'] + lease['cleanup_seconds'] * 1000000000) if cleanup else lease['business_deadline_monotonic_ns']
    c.need(deadline == expected, 'ORIGINAL_ABSOLUTE_PHASE_DEADLINE_CHANGED')
    if cleanup:
        c.read_ref(value['trigger'])
    return value
