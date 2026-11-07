#!/usr/bin/env python3
"""One fixed TasksMax restoration. Default PLAN has no device side effects.

The action flock excludes cooperating QA, not arbitrary privileged writers.
The 90 file is modified through its already held original inode, never by a
path replacement. A partial write is a retained failure, not a retry request.
"""
import argparse
import base64
import fcntl
import hashlib
import json
import os
import re
import select
import selectors
import signal
import stat
import subprocess
import time

ROOT = '/home/alex/work/pocket4-main-tasksmax-restore-01'
KEY = 'pocket4-main-tasksmax-restore-01-20261105'
NONCE = '7fec81044748ffad41b9f2c589fb0ccf'
LOCK = '/run/lock/android-digitalis-actions.lock'
CONFIG50 = '/etc/systemd/system.control/droidloomd.service.d/50-TasksMax.conf'
CONFIG90 = '/etc/systemd/system/droidloomd.service.d/90-digitalis-validation-resources.conf'
NAME90 = '90-digitalis-validation-resources.conf'
SYSTEMCTL = '/usr/bin/systemctl'
SERVICE = 'droidloomd.service'
TOOL_SHA = '639bce3ce5c06b605079ea56f74e3f08216ddffcfa76e11f62073aa775180082'
IDENTITY_SOURCE_SHA = '4b955afce019418e98282aa4af549ab1089afc040a5c8990b7713be5f8b4585e'
PRIOR_SHA = '5b05db0897b2eb85dbd4e71df77bbbb24ff481d78a8965492c0729bcd9e4de99'
OLD90 = (b'[Service]\nCPUQuota=200%\nMemoryHigh=5G\nMemoryMax=6G\nTasksMax=6144\n'
         b'ExecStartPre=/opt/android-digitalis-validation/check-kernel-compat\n')
NEW90 = OLD90.replace(b'TasksMax=6144\n', b'TasksMax=12288\n')
OLD50 = (b'# This is a drop-in unit file extension, created via "systemctl set-property"\n'
         b'# or an equivalent operation. Do not edit.\n[Service]\nTasksMax=12288\n')
EXPECTED_LIMITS = {'cpu.max': '200000 100000', 'memory.high': '5368709120',
                   'memory.max': '6442450944', 'memory.swap.max': 'max', 'pids.max': '12288'}
FIELDS = ('device', 'inode', 'mode', 'uid', 'gid', 'nlink')
PROPERTIES = ('Id', 'ActiveState', 'SubState', 'MainPID', 'InvocationID', 'ControlGroup',
              'TasksMax', 'TasksCurrent', 'FragmentPath', 'DropInPaths', 'UnitFileState', 'NRestarts')
SHOW = [SYSTEMCTL, '--system', 'show', '--no-pager'] + [
    '--property=' + name for name in PROPERTIES] + [SERVICE]
SET = [SYSTEMCTL, '--system', '--no-pager', '--no-ask-password',
       'set-property', SERVICE, 'TasksMax=12288']
STREAM_MAX = 16384
TRANSACTION_SECONDS = 60.0
COMMAND_SECONDS = 5.0
RESULT_MAX = 1024 * 1024


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fail(phase, error):
    return dict(phase=phase, type=type(error).__name__, message=str(error),
                errno=getattr(error, 'errno', None))


class ToolFailure(RuntimeError):
    def __init__(self, record):
        super().__init__(str(record.get('error')))
        self.record = record


def remember(result, phase, error):
    item = error.record['error'] if isinstance(error, ToolFailure) else fail(phase, error)
    if result['error'] is None:
        result['error'] = item
    else:
        result['secondary_errors'].append(item)
    if isinstance(error, ToolFailure):
        result['secondary_errors'].extend(error.record['secondary_errors'])


def check_time(deadline):
    require(time.monotonic() < deadline, 'TRANSACTION_DEADLINE')


def metadata(fd):
    s = os.fstat(fd)
    return dict(device=s.st_dev, inode=s.st_ino, mode=s.st_mode, uid=s.st_uid,
                gid=s.st_gid, nlink=s.st_nlink, size=s.st_size,
                mtime_ns=s.st_mtime_ns, ctime_ns=s.st_ctime_ns)


def same_identity(left, right):
    return all(left[key] == right[key] for key in FIELDS)


def pread_bound(fd, maximum, deadline):
    data = bytearray()
    while len(data) <= maximum:
        check_time(deadline)
        block = os.pread(fd, min(65536, maximum + 1 - len(data)), len(data))
        if not block:
            return bytes(data)
        data.extend(block)
    raise RuntimeError('READ_BOUND')


def validate_prior(prior, binding, expected_pids, original_guard_passed):
    """Verify actual records as well as booleans; this never substitutes a guard."""
    require(prior['collection_complete'] is True and prior['owned_fds_closed'] is True and
            prior['error'] is None and prior['secondary_errors'] == [], 'COMPLETE_IDENTITY_REQUIRED')
    require(prior['expected_limits'] == EXPECTED_LIMITS and
            prior['expected_boot_id'] == binding['expected_boot_id'], 'ORIGINAL_LIMITS_AND_BOOT')
    require(prior['both_identity_observations_match'] is True and
            prior['limits_values_stable_between_samples'] is True, 'STABLE_ORIGINAL_IDENTITIES')
    require(len(prior['phases']) == 2, 'EXACT_TWO_IDENTITY_PHASES')
    require(prior['inputs'] == prior['final_inputs'] == binding['prior_input_metadata'],
            'FIVE_ORIGINAL_INPUTS_AND_METADATA_UNCHANGED')
    for phase in prior['phases']:
        require(phase['complete'] is True and phase['errors'] == [] and
                phase['identity_matches_expected'] is True, 'COMPLETE_IDENTITY_PHASE')
        require(phase['boot']['value'] == binding['expected_boot_id'] and
                phase['boot']['matches_expected'] is True, 'FIXED_BOOT')
        require(phase['framework_epoch_check'] == {'attempted': True, 'passed': True},
                'ORIGINAL_EPOCH_CHECK_REQUIRED')
        require(set(phase['processes']) == set(binding['expected_processes']) and
                len(phase['processes']) == 7, 'EXACT_SEVEN_PROCESSES')
        for role, expected in binding['expected_processes'].items():
            row = phase['processes'][role]
            require(row['complete'] is True and row['matches_expected'] is True and
                    row['expected_host_pid'] == expected['host_pid'] and row['actual'] == expected,
                    'ORIGINAL_PROCESS_IDENTITY:' + role)
        require(phase['inputs'] == {name: binding['prior_input_metadata'][name]
                                   for name in ('activation', 'verified', 'cell')},
                'ORIGINAL_THREE_INPUTS')
        values = {name: row['value'] for name, row in phase['limits'].items()}
        require(values == dict(EXPECTED_LIMITS, **{'pids.max': expected_pids}),
                'ONLY_EXPECTED_PIDS_STATE_ALLOWED')
        require(all(row['matches_expected'] == (name != 'pids.max' or expected_pids == '12288')
                    for name, row in phase['limits'].items()), 'LIMIT_RESULT_CONSISTENCY')
    require(prior['cgroup_before'] == prior['cgroup_after'] == prior['cgroup_named_after'] and
            (prior['cgroup_before']['device'], prior['cgroup_before']['inode']) == (30, 26651611),
            'ORIGINAL_MAIN_CGROUP')
    guard = prior['original_guard']
    require(guard['attempted'] is True and guard['completed'] is True and
            guard['passed'] is original_guard_passed, 'UNCHANGED_ORIGINAL_GUARD_REQUIRED')
    if original_guard_passed:
        value = guard['return_value']
        require(value['Main_epoch_sha256'] == prior['main_epoch_expected'] and
                value['three_host_processes_match'] is True and value['resource_limits_match'] is True,
                'ORIGINAL_GUARD_PASS_FIELDS')
    else:
        require(guard['error']['type'] == 'RuntimeError' and
                guard['error']['message'] == 'Main resource limits differ' and
                'readonly_r3_coordinator.py' in guard['traceback'], 'ORIGINAL_SPECIFIC_GUARD_FAILURE')


def validate_binding(binding, prior_raw):
    require(binding['schema'] == 1 and
            binding['readiness'] == 'ACTUAL_IDENTITY_BOUND_ROOT_REVIEW_REQUIRED', 'NOT_READY')
    require(binding['root'] == ROOT and binding['stable_key'] == KEY and
            binding['nonce'] == NONCE and re.fullmatch('[0-9a-f]{32}', NONCE), 'FIXED_ATTEMPT')
    require(len(prior_raw) == 23490 and sha(prior_raw) == PRIOR_SHA and
            binding['prior_identity']['sha256'] == PRIOR_SHA, 'ACTUAL_PRIOR_IDENTITY_PIN')
    require(binding['source_identity'] == {'bytes': 18537, 'sha256': IDENTITY_SOURCE_SHA},
            'FROZEN_IDENTITY_SOURCE')
    require(binding['expected_limits'] == EXPECTED_LIMITS, 'ORIGINAL_LIMITS')
    require([row['path'] for row in binding['configs']] == [CONFIG50, CONFIG90], 'EXACT_TWO_CONFIGS')
    for row, body in zip(binding['configs'], (OLD50, OLD90)):
        require(base64.b64decode(row['original_base64'], validate=True) == body and
                row['bytes'] == len(body) and row['sha256'] == sha(body), 'ACTUAL_CONFIG_BODY_PIN')
    require(base64.b64decode(binding['new90']['base64'], validate=True) == NEW90 and
            binding['new90']['bytes'] == 133 and binding['new90']['sha256'] == sha(NEW90),
            'EXACT_SINGLE_LINE_NEW_BODY')
    require(binding['tool']['path'] == SYSTEMCTL and binding['tool']['bytes'] == 302112 and
            binding['tool']['sha256'] == TOOL_SHA, 'ACTUAL_SYSTEMCTL_PIN')
    require(binding['action_lock'] == {'path': LOCK, 'identity': dict(
        device=28, inode=8312, mode=33152, uid=0, gid=0, nlink=1)}, 'EXISTING_ACTION_LOCK')
    require(binding['scope']['target_unit'] == SERVICE and binding['scope']['new_TasksMax'] == '12288' and
            binding['scope']['property_command_maximum'] == 1, 'SINGLE_FIXED_PROPERTY')
    prior = json.loads(prior_raw)
    validate_prior(prior, binding, '6144', False)
    return prior


class Journal:
    """Only one fresh root; each bounded record is create-only and fsynced."""
    def __init__(self, identity, deadline):
        self.identity = identity
        self.fd = None
        path_fd = identity.open_fixed('/home/alex/work', True, deadline)
        try:
            self.parent = os.open('.', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                                  dir_fd=path_fd)
        finally:
            os.close(path_fd)
        self.parent_identity = metadata(self.parent)
        try:
            os.mkdir(ROOT.rsplit('/', 1)[1], 0o700, dir_fd=self.parent)
            self.fd = os.open(ROOT.rsplit('/', 1)[1], os.O_RDONLY | os.O_DIRECTORY |
                              os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=self.parent)
            s = metadata(self.fd)
            require(s['uid'] == os.geteuid() == 0 and stat.S_IMODE(s['mode']) == 0o700,
                    'OWNED_EVIDENCE_DIRECTORY')
            self.directory_identity = s
            os.fsync(self.fd)
            os.fsync(self.parent)
        except Exception as primary:
            for fd in (self.fd, self.parent):
                if fd is not None:
                    try:
                        os.close(fd)
                    except Exception as error:
                        primary.add_note('closing new evidence directory: ' + repr(error))
            raise

    def check(self):
        check_deadline = time.monotonic() + 2.0
        named_parent = self.identity.open_fixed('/home/alex/work', True, check_deadline)
        named = None
        try:
            require(same_identity(metadata(self.parent), self.parent_identity) and
                    metadata(named_parent) == metadata(self.parent), 'EVIDENCE_PARENT_NAMED_IDENTITY')
            named = os.open(ROOT.rsplit('/', 1)[1], os.O_PATH | os.O_DIRECTORY |
                            os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=self.parent)
            require(same_identity(metadata(self.fd), self.directory_identity) and
                    metadata(named) == metadata(self.fd), 'OWNED_EVIDENCE_NAMED_IDENTITY')
        finally:
            if named is not None:
                os.close(named)
            os.close(named_parent)

    def save(self, name, value):
        self.check()
        require(re.fullmatch('[a-z0-9][a-z0-9.-]{0,100}', name), 'EVIDENCE_BASENAME')
        raw = value if isinstance(value, bytes) else (
            json.dumps(value, sort_keys=True, indent=2) + '\n').encode('ascii')
        require(len(raw) <= RESULT_MAX, 'EVIDENCE_BOUND')
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                     0o600, dir_fd=self.fd)
        try:
            offset = 0
            while offset < len(raw):
                count = os.write(fd, raw[offset:])
                require(count > 0, 'OWNED_EVIDENCE_SHORT_WRITE')
                offset += count
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(self.fd)
        self.check()
        return dict(path=ROOT + '/' + name, bytes=len(raw), sha256=sha(raw))

    def close(self):
        first = None
        for fd in (self.fd, self.parent):
            try:
                os.close(fd)
            except Exception as error:
                if first is None:
                    first = error
        if first is not None:
            raise first


class ConfigAnchor:
    def __init__(self, identity, spec, writable, deadline):
        self.identity, self.spec, self.path = identity, spec, spec['path']
        self.parent_path, self.name = self.path.rsplit('/', 1)
        self.parent = self.fd = None
        try:
            path_fd = identity.open_fixed(self.parent_path, True, deadline)
            try:
                self.parent = os.open('.', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                                      dir_fd=path_fd)
            finally:
                os.close(path_fd)
            self.parent_before = metadata(self.parent)
            require(stat.S_ISDIR(self.parent_before['mode']) and self.parent_before['uid'] == 0 and
                    not self.parent_before['mode'] & 0o022, 'ROOT_OWNED_FIXED_CONFIG_PARENT')
            self.fd = os.open(self.name, (os.O_RDWR if writable else os.O_RDONLY) |
                              os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.parent)
            require(metadata(self.fd) == spec['before'], 'ACTUAL_ORIGINAL_CONFIG_METADATA')
            self.check(spec['before'], base64.b64decode(spec['original_base64'], validate=True), deadline)
        except Exception as primary:
            try:
                self.close()
            except Exception as error:
                primary.add_note('closing failed configuration anchor: ' + repr(error))
            raise

    def parent_check(self, deadline, permit_time_change=False):
        named = self.identity.open_fixed(self.parent_path, True, deadline)
        try:
            held_now, named_now = metadata(self.parent), metadata(named)
            require(same_identity(held_now, self.parent_before) and held_now == named_now,
                    'CONFIG_PARENT_IDENTITY_CHANGED')
            require(permit_time_change or held_now == self.parent_before, 'CONFIG_PARENT_METADATA_CHANGED')
            return dict(before=self.parent_before, held=held_now, named=named_now)
        finally:
            os.close(named)

    def check(self, expected_metadata, body, deadline):
        parent = self.parent_check(deadline)
        first = metadata(self.fd)
        require(first == expected_metadata, 'CONFIG_HELD_METADATA_CHANGED')
        named = os.open(self.name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
                        dir_fd=self.parent)
        try:
            require(metadata(named) == first, 'CONFIG_NAMED_INODE_CHANGED')
            a, b = pread_bound(self.fd, 4096, deadline), pread_bound(named, 4096, deadline)
            require(a == b == body and metadata(self.fd) == metadata(named) == first,
                    'CONFIG_HELD_NAMED_BODY_CHANGED')
            return dict(path=self.path, bytes=len(body), sha256=sha(body), metadata=first, parent=parent)
        finally:
            os.close(named)

    def observe_named50(self, deadline):
        parent = self.parent_check(deadline, True)
        named = os.open(self.name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
                        dir_fd=self.parent)
        try:
            before = metadata(named)
            require(stat.S_ISREG(before['mode']) and before['mode'] == self.spec['before']['mode'] and
                    before['uid'] == before['gid'] == 0 and before['nlink'] == 1 and before['size'] == 146,
                    'EXISTING50_FINAL_TYPE_OWNER_MODE_BOUND')
            body = pread_bound(named, 4096, deadline)
            require(body == OLD50 and before == metadata(named), 'EXISTING50_BODY_MUST_REMAIN_EXACT')
            return dict(path=self.path, metadata=before, original_metadata=self.spec['before'],
                        metadata_changed=before != self.spec['before'], bytes=len(body), sha256=sha(body),
                        parent=parent, original_held_metadata=metadata(self.fd))
        finally:
            os.close(named)

    def close(self):
        errors = []
        for name in ('fd', 'parent'):
            fd = getattr(self, name, None)
            if fd is not None:
                try:
                    os.close(fd)
                except Exception as error:
                    errors.append(error)
                setattr(self, name, None)
        if errors:
            raise errors[0]


def write90(anchor, record, journal, deadline):
    """Single pwrite through the original FD. No rename, truncation or retry."""
    record.update(attempted=False, full_write=False, fsynced=False, new_claim=None)
    record['before'] = anchor.check(anchor.spec['before'], OLD90, deadline)
    journal.save('write90-intent.json', dict(path=CONFIG90, original=record['before'],
                 new_bytes=len(NEW90), new_sha256=sha(NEW90), mutation='one held-inode pwrite at offset zero'))
    check_time(deadline)
    anchor.check(anchor.spec['before'], OLD90, deadline)
    record['attempted'] = True
    count = os.pwrite(anchor.fd, NEW90, 0)
    record['returned_bytes'] = count
    require(count == len(NEW90), 'MAIN_CONFIG_PARTIAL_WRITE_NO_RETRY')
    record['full_write'] = True
    os.fsync(anchor.fd)
    os.fsync(anchor.parent)
    record['fsynced'] = True
    after = metadata(anchor.fd)
    require(same_identity(after, anchor.spec['before']) and after['size'] == 133,
            'ORIGINAL90_INODE_MUST_BE_PRESERVED')
    record['after'] = anchor.check(after, NEW90, deadline)
    record['new_claim'] = after
    journal.save('write90-result.json', record)


def rollback90(anchor, write_record, record, journal, deadline, property_attempted):
    """Only a pre-property, still exact transaction-owned new body is eligible."""
    record.update(attempted=False, restored=False, eligible=False, reason=None)
    if property_attempted:
        record['reason'] = 'PROPERTY_ATTEMPTED_NO_AUTOMATIC_CONFIGURATION_OR_KERNEL_ROLLBACK'
        return
    claim = write_record.get('new_claim')
    if claim is None:
        record['reason'] = 'NO_COMPLETE_EXACT_NEW_WRITE_CLAIM_PARTIAL_OR_UNKNOWN_RETAINED'
        return
    anchor.check(claim, NEW90, deadline)
    record['eligible'] = True
    journal.save('rollback90-intent.json', dict(path=CONFIG90, claim=claim,
                                              new_sha256=sha(NEW90), restore_sha256=sha(OLD90)))
    anchor.check(claim, NEW90, deadline)
    record['attempted'] = True
    count = os.pwrite(anchor.fd, OLD90, 0)
    record['returned_bytes'] = count
    require(count == len(OLD90), 'ROLLBACK_PARTIAL_WRITE_NO_RETRY')
    os.ftruncate(anchor.fd, len(OLD90))
    os.fsync(anchor.fd)
    os.fsync(anchor.parent)
    restored = metadata(anchor.fd)
    require(same_identity(restored, anchor.spec['before']), 'ROLLBACK_ORIGINAL_INODE_REQUIRED')
    record['after'] = anchor.check(restored, OLD90, deadline)
    record['restored'] = True
    journal.save('rollback90-result.json', record)


def check_tool(identity, fd, binding, deadline):
    expected = binding['tool']
    require(metadata(fd) == expected['metadata'], 'SYSTEMCTL_HELD_METADATA')
    named = identity.open_fixed(SYSTEMCTL, False, deadline)
    try:
        require(metadata(named) == metadata(fd), 'SYSTEMCTL_NAMED_IDENTITY')
        body = pread_bound(fd, 4 * 1024 * 1024, deadline)
        require(body.startswith(b'\x7fELF') and len(body) == expected['bytes'] and
                sha(body) == TOOL_SHA and metadata(named) == metadata(fd) == expected['metadata'],
                'SYSTEMCTL_ORIGINAL_HELD_ELF_HASH')
    finally:
        os.close(named)


def run_tool(identity, fd, binding, kind, record, deadline):
    """Exactly one fixed child; preserve primary error and independently reap."""
    require(kind in ('show_before', 'set_property', 'show_after'), 'FIXED_TOOL_OPERATION')
    argv = SET if kind == 'set_property' else SHOW
    record.update(kind=kind, argv=argv, attempted=False, error=None, secondary_errors=[],
                  child_reaped=False, child_kill_attempted=False, output_complete=False)
    process = pidfd = selector = None
    buffers = {'stdout': bytearray(), 'stderr': bytearray()}
    eof = {'stdout': False, 'stderr': False}
    try:
        check_tool(identity, fd, binding, deadline)
        command_deadline = min(deadline, time.monotonic() + COMMAND_SECONDS)
        check_time(command_deadline)
        record['attempted'] = True
        process = subprocess.Popen(argv, executable='/proc/self/fd/' + str(fd),
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    close_fds=True, pass_fds=(fd,), cwd='/', env={
                        'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
                        'SYSTEMD_COLORS': '0', 'SYSTEMD_PAGER': ''})
        record['child_pid'] = process.pid
        pidfd = os.pidfd_open(process.pid, 0)
        selector = selectors.DefaultSelector()
        for name, stream in (('stdout', process.stdout), ('stderr', process.stderr)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        while selector.get_map() or process.poll() is None:
            require(time.monotonic() < command_deadline, 'SYSTEMCTL_COMMAND_DEADLINE')
            for key, _ in selector.select(min(0.05, max(0.0, command_deadline - time.monotonic()))):
                name = key.data
                try:
                    data = os.read(key.fileobj.fileno(), min(4096, STREAM_MAX + 1 - len(buffers[name])))
                except BlockingIOError:
                    continue
                if not data:
                    eof[name] = True
                    selector.unregister(key.fileobj)
                else:
                    buffers[name].extend(data)
                    require(len(buffers[name]) <= STREAM_MAX, 'SYSTEMCTL_STREAM_BOUND:' + name)
        record['returncode'] = process.wait(timeout=0.2)
        record['child_reaped'] = True
        record['output_complete'] = all(eof.values())
        require(record['returncode'] == 0 and record['output_complete'], 'SYSTEMCTL_COMPLETE_SUCCESS_REQUIRED')
        if kind != 'set_property':
            properties = {}
            for line in bytes(buffers['stdout']).decode('utf-8').splitlines():
                require('=' in line, 'SYSTEMCTL_PROPERTY_LINE')
                key, value = line.split('=', 1)
                require(key in PROPERTIES and key not in properties, 'SYSTEMCTL_UNIQUE_PROPERTY')
                properties[key] = value
            require(set(properties) == set(PROPERTIES), 'SYSTEMCTL_COMPLETE_PROPERTY_SET')
            record['properties'] = properties
    except Exception as error:
        remember(record, 'systemctl_' + kind, error)
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    record['child_kill_attempted'] = True
                    if pidfd is not None:
                        signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                    else:
                        process.kill()  # This sole owner's unreaped direct child.
            except Exception as error:
                remember(record, 'signal_exact_child', error)
            try:
                record['returncode'] = process.wait(timeout=2.0)
                record['child_reaped'] = True
            except Exception as error:
                remember(record, 'independent_wait_exact_child', error)
        if selector is not None:
            try:
                selector.close()
            except Exception as error:
                remember(record, 'close_selector', error)
        if process is not None:
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except Exception as error:
                        remember(record, 'close_child_stream', error)
        if pidfd is not None:
            try:
                record['child_pidfd_exit_observed'] = bool(select.select([pidfd], [], [], 0)[0])
                require(record['child_pidfd_exit_observed'], 'CHILD_PIDFD_EXIT_REQUIRED')
            except Exception as error:
                remember(record, 'observe_child_pidfd_exit', error)
            finally:
                try:
                    os.close(pidfd)
                except Exception as error:
                    remember(record, 'close_child_pidfd', error)
        try:
            check_tool(identity, fd, binding, deadline)
            record['tool_unchanged'] = True
        except Exception as error:
            remember(record, 'final_tool_binding', error)
        record['streams'] = {name: dict(bytes=len(data), sha256=sha(data),
            base64=base64.b64encode(data).decode('ascii'), eof=eof[name],
            complete=eof[name] and len(data) <= STREAM_MAX) for name, data in buffers.items()}
    return record['error'] is None and not record['secondary_errors'] and record['child_reaped']


def service_match(record, binding, tasksmax):
    require(record['error'] is None and record['secondary_errors'] == [] and
            record['returncode'] == 0 and record['child_reaped'] and record['output_complete'],
            'SERVICE_READ_MUST_COMPLETE')
    actual, prior = record['properties'], binding['service_properties_before']
    require(set(actual) == set(PROPERTIES), 'TWELVE_SERVICE_PROPERTIES')
    for key in PROPERTIES:
        if key not in ('TasksMax', 'TasksCurrent'):
            require(actual[key] == prior[key], 'SERVICE_IDENTITY_OR_CONFIGURATION_METADATA:' + key)
    require(actual['TasksMax'] == tasksmax and re.fullmatch('[0-9]+', actual['TasksCurrent']),
            'EXACT_TASKSMAX_AND_VALID_CURRENT')


def lock_check(identity, fd, binding, deadline):
    expected = binding['action_lock']['identity']
    require(all(metadata(fd)[key] == value for key, value in expected.items()), 'ACTION_LOCK_HELD_IDENTITY')
    named = identity.open_fixed(LOCK, False, deadline)
    try:
        require(metadata(named) == metadata(fd), 'ACTION_LOCK_NAMED_IDENTITY')
    finally:
        os.close(named)


def execute_once(identity, binding, prior_raw):
    validate_binding(binding, prior_raw)  # No claim, child or write precedes this.
    require(os.geteuid() == 0, 'ROOT_EXECUTION_REQUIRED')
    started = time.monotonic()
    deadline = started + TRANSACTION_SECONDS
    result = dict(schema=1, key=KEY, nonce=NONCE, root=ROOT, ok=False,
                  state='NOT_COMPLETED', error=None, secondary_errors=[],
                  original_identity_evidence=binding['prior_identity'],
                  deadline_seconds=TRANSACTION_SECONDS, commands={}, write90={}, rollback90={},
                  property_attempted=False, runtime_authorized=False, Android_UI_actions=0,
                  daemon_reload_performed=False, restart_performed=False, extra_dropin_created=False,
                  original_guard_or_baseline_changed=False, main_code_changed=False,
                  side_effects_possible=False, action_lock_acquired=False, action_lock_released=False,
                  held_fds_closed=False, evidence_final_saved=False,
                  atomicity_scope='QA flock plus held inode/name checks; not a global privileged-writer CAS',
                  rollback_scope='before property attempt only, exact new held/named inode and bytes; otherwise retain failure')
    journal = anchor50 = anchor90 = lock = tool = None
    preflight = False
    try:
        journal = Journal(identity, deadline)
        journal.save('claim.json', dict(nonce=NONCE, key=KEY, source_binding=binding))
        journal.save('prior-main-identity-original.json', prior_raw)
        lock = identity.open_fixed(LOCK, False, deadline)
        lock_check(identity, lock, binding, deadline)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result['action_lock_acquired'] = True
        lock_check(identity, lock, binding, deadline)
        tool = identity.open_fixed(SYSTEMCTL, False, deadline)
        check_tool(identity, tool, binding, deadline)
        anchor50 = ConfigAnchor(identity, binding['configs'][0], False, deadline)
        anchor90 = ConfigAnchor(identity, binding['configs'][1], True, deadline)
        journal.save('original-50-TasksMax.conf', OLD50)
        journal.save('original-90-validation.conf', OLD90)
        journal.save('new-90-validation.conf', NEW90)
        before_service = result['commands']['show_before'] = {}
        if not run_tool(identity, tool, binding, 'show_before', before_service, deadline):
            raise ToolFailure(before_service)
        service_match(before_service, binding, '6144')
        result['identity_before'] = identity.collect()
        validate_prior(result['identity_before'], binding, '6144', False)
        journal.save('identity-before.json', result['identity_before'])
        journal.save('service-before.json', before_service)
        result['configs_before'] = [anchor50.check(binding['configs'][0]['before'], OLD50, deadline),
                                    anchor90.check(binding['configs'][1]['before'], OLD90, deadline)]
        lock_check(identity, lock, binding, deadline)
        require(time.monotonic() + 30.0 < deadline, 'POST_OBSERVATION_TIME_MUST_BE_RESERVED')
        preflight = True
        write90(anchor90, result['write90'], journal, deadline)
        result['side_effects_possible'] = True
        anchor50.check(binding['configs'][0]['before'], OLD50, deadline)
        anchor90.check(result['write90']['new_claim'], NEW90, deadline)
        lock_check(identity, lock, binding, deadline)
        journal.save('set-property-intent.json', dict(argv=SET, maximum_attempts=1,
                     original_50_sha256=sha(OLD50), unchanged_original_guard_required_after=True))
        command = result['commands']['set_property'] = {}
        # A launch failure is still an attempted property operation; never retry it.
        result['property_attempted'] = True
        if not run_tool(identity, tool, binding, 'set_property', command, deadline):
            raise ToolFailure(command)
        journal.save('set-property-result.json', command)
    except Exception as error:
        remember(result, 'transaction', error)
    finally:
        result['side_effects_possible'] = bool(result['write90'].get('attempted') or result['property_attempted'])
        if preflight:
            # Every observation is independent: one failed read cannot skip the rest.
            try:
                result['identity_after'] = identity.collect()
                validate_prior(result['identity_after'], binding, '12288', True)
                result['original_main_guard_passed_after'] = True
            except Exception as error:
                remember(result, 'independent_identity_after', error)
            try:
                record = result['commands']['show_after'] = {}
                if not run_tool(identity, tool, binding, 'show_after', record, deadline):
                    raise ToolFailure(record)
                service_match(record, binding, '12288')
                result['systemd_and_kernel_12288_proven'] = result.get('original_main_guard_passed_after', False)
            except Exception as error:
                remember(result, 'independent_service_after', error)
            try:
                result['config50_after'] = anchor50.observe_named50(deadline)
            except Exception as error:
                remember(result, 'independent_config50_after', error)
            try:
                claim = result['write90'].get('new_claim')
                require(claim is not None, 'COMPLETE_NEW90_CLAIM_REQUIRED')
                result['config90_after'] = anchor90.check(claim, NEW90, deadline)
            except Exception as error:
                remember(result, 'independent_config90_after', error)
            try:
                lock_check(identity, lock, binding, deadline)
            except Exception as error:
                remember(result, 'independent_lock_after', error)
            if result['error'] is not None:
                try:
                    rollback90(anchor90, result['write90'], result['rollback90'], journal,
                               deadline, result['property_attempted'])
                except Exception as error:
                    remember(result, 'guarded_config_only_rollback', error)
        # Save a full result before releasing locks/FDs; errors do not prevent release.
        if journal is not None:
            try:
                journal.save('observation-before-release.json', result)
            except Exception as error:
                remember(result, 'save_before_release', error)
        close_errors = []
        for name, anchor in (('config90', anchor90), ('config50', anchor50)):
            if anchor is not None:
                try:
                    anchor.close()
                except Exception as error:
                    close_errors.append(fail('close_' + name, error))
                    remember(result, 'close_' + name, error)
        if tool is not None:
            try:
                os.close(tool)
            except Exception as error:
                close_errors.append(fail('close_tool', error))
                remember(result, 'close_tool', error)
        if lock is not None:
            try:
                os.close(lock)  # Never unlink or replace the shared action lock.
                result['action_lock_released'] = result['action_lock_acquired']
            except Exception as error:
                close_errors.append(fail('close_action_lock', error))
                remember(result, 'close_action_lock', error)
        result['held_fds_closed'] = not close_errors
        conditions_passed = bool(preflight and result['error'] is None and not result['secondary_errors'] and
            result.get('original_main_guard_passed_after') and result.get('systemd_and_kernel_12288_proven') and
            result.get('config50_after') and result.get('config90_after') and result['action_lock_released'])
        result['conditions_passed_before_evidence_close'] = conditions_passed
        result['evidence_fds_closed'] = False
        result['state'] = 'FINAL_EVIDENCE_CLOSE_PENDING' if conditions_passed else 'MAIN_RESTORE_NOT_QUALIFIED'
        result['elapsed_ms'] = int((time.monotonic() - started) * 1000)
        if journal is not None:
            try:
                result['evidence_final_saved'] = True
                result['result_file'] = journal.save('result.json', result)
            except Exception as error:
                result['evidence_final_saved'] = False
                remember(result, 'save_final_result', error)
                result['ok'] = False
                result['state'] = 'MAIN_RESTORE_NOT_QUALIFIED'
            try:
                journal.close()
                result['evidence_fds_closed'] = True
            except Exception as error:
                remember(result, 'close_evidence_directory', error)
                result['ok'] = False
                result['state'] = 'MAIN_RESTORE_NOT_QUALIFIED'
        # The complete stdout envelope is authoritative after evidence FD close.
        # The create-only result.json deliberately never claims the final PASS.
        result['ok'] = bool(conditions_passed and result['evidence_fds_closed'] and
                            result['evidence_final_saved'] and result['error'] is None and
                            not result['secondary_errors'])
        result['state'] = 'ORIGINAL_MAIN_TASKSMAX_RESTORED' if result['ok'] else 'MAIN_RESTORE_NOT_QUALIFIED'
    return result


def plan():
    return dict(state='PLAN_ONLY', root=ROOT, key=KEY, nonce=NONCE,
                binding_required='exact actual complete identity and original inputs; root review required',
                original90=dict(path=CONFIG90, bytes=len(OLD90), sha256=sha(OLD90)),
                new90=dict(bytes=len(NEW90), sha256=sha(NEW90)),
                original50=dict(path=CONFIG50, bytes=len(OLD50), sha256=sha(OLD50)),
                mutation_argv=SET, maximum_property_attempts=1, action_lock=LOCK,
                deadline_seconds=TRANSACTION_SECONDS, per_command_seconds=COMMAND_SECONDS,
                no_daemon_reload=True, no_restart=True, no_extra_dropins=True,
                no_main_guard_or_activation_change=True, runtime_authorized=False,
                partial_failure_retained=True, device_access_performed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(plan(), sort_keys=True, indent=2))
