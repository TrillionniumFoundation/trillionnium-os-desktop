#!/usr/bin/env python3
"""Read fixed Main systemd policy and kernel counters; never change or qualify Main."""
import argparse
import base64
import hashlib
import json
import os
import re
import select
import selectors
import signal
import subprocess
import stat
import time

ACTIVATION = '/home/alex/work/pocket4-app-production-20261104-r10/deployment-preparation/activation-after-01.json'
ACTIVATION_SHA = '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
# Exact original readonly_r3_coordinator.py read() default, not a measured size.
ACTIVATION_MAX = 1024 * 1024
CGROUP = '/sys/fs/cgroup/system.slice/droidloomd.service'
CGROUP_DEV, CGROUP_INO = 30, 26651611
LIMIT_MAX = 4096
OUTPUT_MAX = 2 * 1024 * 1024
DEADLINE_SECONDS = 12.0
IDENTITY_FIELDS = ('device', 'inode', 'mode', 'uid', 'gid', 'nlink')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def check_time(deadline):
    require(time.monotonic() < deadline, 'COLLECTION_DEADLINE')


def metadata(fd):
    s = os.fstat(fd)
    return dict(device=s.st_dev, inode=s.st_ino, mode=s.st_mode,
                uid=s.st_uid, gid=s.st_gid, nlink=s.st_nlink, size=s.st_size,
                mtime_ns=s.st_mtime_ns, ctime_ns=s.st_ctime_ns)


def same_identity(left, right):
    return all(left[name] == right[name] for name in IDENTITY_FIELDS)


def open_fixed(path, directory, deadline):
    """Walk every component with O_NOFOLLOW; return only the held final FD."""
    require(path.startswith('/') and '//' not in path, 'ABSOLUTE_FIXED_PATH')
    parts = path[1:].split('/')
    require(parts and all(part not in ('', '.', '..') for part in parts), 'PATH_COMPONENT')
    parent = os.open('/', os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in parts[:-1]:
            check_time(deadline)
            child = os.open(part, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                            dir_fd=parent)
            os.close(parent)
            parent = child
        check_time(deadline)
        flags = (os.O_PATH | os.O_DIRECTORY) if directory else (os.O_RDONLY | os.O_NONBLOCK)
        return os.open(parts[-1], flags | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=parent)
    finally:
        os.close(parent)


def read_bounded(fd, maximum, deadline):
    """Read to EOF, including pseudo files whose stat size is zero."""
    data = bytearray()
    while len(data) <= maximum:
        check_time(deadline)
        block = os.read(fd, min(65536, maximum + 1 - len(data)))
        if not block:
            return bytes(data)
        data.extend(block)
    raise RuntimeError('FILE_READ_BOUND')


def names_from_activation(raw):
    activation = json.loads(raw.decode('utf-8'))
    expected = activation['limits']
    require(type(expected) is dict and len(expected) == 5, 'EXACT_FIVE_ACTIVATION_LIMITS')
    for name, value in expected.items():
        require(type(name) is str and len(name) <= 64 and
                re.fullmatch(r'[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+', name),
                'LIMIT_BASENAME_FROM_PINNED_ACTIVATION')
        require(type(value) is str and 0 < len(value.encode('utf-8')) <= LIMIT_MAX and
                value == value.strip(), 'ACTIVATION_LIMIT_STRING')
    return expected


# Embedded verbatim into read_main_service.py; no standalone execution.
SERVICE = 'droidloomd.service'
SYSTEMCTL = '/usr/bin/systemctl'
PROPERTIES = ('Id', 'ActiveState', 'SubState', 'MainPID', 'InvocationID', 'ControlGroup',
              'TasksMax', 'TasksCurrent', 'FragmentPath', 'DropInPaths', 'UnitFileState', 'NRestarts')
EXPECTED_SERVICE = {'Id': SERVICE, 'MainPID': '3588022',
                    'InvocationID': '67cdc2375f394012ad9d7f39b0d77426',
                    'ControlGroup': '/system.slice/droidloomd.service'}
COMMAND_SECONDS = 5.0
STREAM_MAX = 16384
TOOL_MAX = 4 * 1024 * 1024


def systemctl_read(record, deadline):
    """One fixed read-only child, bounded streams, exact-child retirement."""
    argv = [SYSTEMCTL, '--system', 'show', '--no-pager']
    argv += ['--property=' + name for name in PROPERTIES]
    argv += [SERVICE]
    record.update(argv=argv, attempted=False, error=None, secondary_errors=[],
                  command_seconds=COMMAND_SECONDS, stream_maximum_bytes=STREAM_MAX,
                  output_complete=False, child_reaped=False, child_kill_attempted=False, cleanup_errors=[],
                  property_paths_are_metadata_only=True, no_config_file_body_read=True)
    tool = None
    process = None
    pidfd = None
    selector = None
    buffers = {'stdout': bytearray(), 'stderr': bytearray()}
    eof = {'stdout': False, 'stderr': False}

    def remember(phase, error):
        item = dict(phase=phase, type=type(error).__name__, message=str(error),
                    errno=getattr(error, 'errno', None))
        if phase != 'fixed_systemctl_read':
            record['cleanup_errors'].append(item)
        if record['error'] is None:
            record['error'] = item
        else:
            record['secondary_errors'].append(item)

    try:
        tool = open_fixed(SYSTEMCTL, False, deadline)
        first = metadata(tool)
        require(stat.S_ISREG(first['mode']) and first['uid'] == 0 and first['nlink'] == 1 and
                first['mode'] & 0o111 and not first['mode'] & 0o022 and
                0 < first['size'] <= TOOL_MAX, 'FIXED_SYSTEMCTL_METADATA_BOUND')
        body = read_bounded(tool, TOOL_MAX, deadline)
        require(len(body) == first['size'] and metadata(tool) == first, 'SYSTEMCTL_HELD_INPUT_CHANGED')
        record['tool'] = dict(path=SYSTEMCTL, bytes=len(body), sha256=hashlib.sha256(body).hexdigest(),
                              metadata=first, binding='current held root-owned ELF; not an invented prior tool SHA')
        del body
        check_time(deadline)
        command_deadline = min(deadline, time.monotonic() + COMMAND_SECONDS)
        record['attempted'] = True
        process = subprocess.Popen(argv, executable='/proc/self/fd/' + str(tool),
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   cwd='/', env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin',
                                                 'LANG': 'C', 'LC_ALL': 'C', 'SYSTEMD_COLORS': '0'},
                                   close_fds=True, pass_fds=(tool,))
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
        require(record['returncode'] == 0 and record['output_complete'], 'SYSTEMCTL_TERMINAL_REQUIRED')
        text = bytes(buffers['stdout']).decode('utf-8')
        properties = {}
        for line in text.splitlines():
            require('=' in line, 'SYSTEMCTL_PROPERTY_LINE')
            name, value = line.split('=', 1)
            require(name in PROPERTIES and name not in properties, 'SYSTEMCTL_EXACT_UNIQUE_PROPERTIES')
            properties[name] = value
        require(set(properties) == set(PROPERTIES), 'SYSTEMCTL_COMPLETE_PROPERTY_SET')
        record['properties'] = properties
        record['service_identity_fields_match_expected'] = all(properties[k] == v for k, v in EXPECTED_SERVICE.items())
        record['expected_service_identity_fields'] = EXPECTED_SERVICE
    except Exception as error:
        remember('fixed_systemctl_read', error)
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    record['child_kill_attempted'] = True
                    if pidfd is not None:
                        signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                    else:
                        # Popen is this thread's sole unreaped direct child owner.
                        process.kill()
                record['returncode'] = process.wait(timeout=2.0)
                record['child_reaped'] = True
            except Exception as error:
                remember('retire_exact_systemctl_child', error)
        if selector is not None:
            try:
                selector.close()
            except Exception as error:
                remember('close_selector', error)
        # The Popen pipes also exist if pidfd_open or selector registration failed.
        if process is not None:
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except Exception as error:
                        remember('close_owned_pipe', error)
        if pidfd is not None:
            try:
                record['child_pidfd_exit_observed'] = bool(select.select([pidfd], [], [], 0)[0])
                require(record['child_pidfd_exit_observed'], 'EXACT_CHILD_PIDFD_EXIT_REQUIRED')
            except Exception as error:
                remember('observe_owned_child_pidfd_exit', error)
            finally:
                try:
                    os.close(pidfd)
                except Exception as error:
                    remember('close_owned_child_pidfd', error)
        if tool is not None:
            try:
                require(metadata(tool) == record.get('tool', {}).get('metadata'), 'SYSTEMCTL_FINAL_HELD_IDENTITY')
                named = open_fixed(SYSTEMCTL, False, deadline)
                try:
                    require(metadata(named) == metadata(tool), 'SYSTEMCTL_FINAL_NAMED_IDENTITY')
                    data = read_bounded(named, TOOL_MAX, deadline)
                    require(len(data) == record['tool']['bytes'] and
                            hashlib.sha256(data).hexdigest() == record['tool']['sha256'], 'SYSTEMCTL_FINAL_HASH')
                    record['tool_unchanged'] = True
                finally:
                    os.close(named)
            except Exception as error:
                remember('final_systemctl_binding', error)
            finally:
                try:
                    os.close(tool)
                except Exception as error:
                    remember('close_owned_tool_fd', error)
        record['streams'] = {name: dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                                        base64=base64.b64encode(data).decode('ascii'), eof=eof[name],
                                        complete=eof[name] and len(data) <= STREAM_MAX,
                                        retained_prefix_on_failure=not eof[name] or len(data) > STREAM_MAX)
                             for name, data in buffers.items()}
        record['cleanup_complete'] = (process is None or record['child_reaped']) and not record['cleanup_errors']
    return record['error'] is None and not record['secondary_errors'] and record['child_reaped']


def collect():
    started = time.monotonic()
    deadline = started + DEADLINE_SECONDS
    result = dict(schema=1, collection_complete=False, error=None, secondary_errors=[],
                  activation_path=ACTIVATION, activation_expected_sha256=ACTIVATION_SHA,
                  activation_maximum_bytes=ACTIVATION_MAX,
                  cgroup_path=CGROUP, expected_cgroup_identity=dict(device=CGROUP_DEV, inode=CGROUP_INO),
                  limits_maximum_bytes_each=LIMIT_MAX, deadline_seconds=DEADLINE_SECONDS,
                  device_file_writes=0, direct_systemctl_children_owned=0, Android_UI_actions=0,
                  main_guard_called=False, runtime_authorized=False,
                  observation_scope='two sequential complete samples, not an atomic multi-file snapshot')
    held = []
    try:
        require(os.getuid() == os.geteuid() == 0, 'ROOT_READ_ONLY_COLLECTOR_REQUIRED')
        activation_fd = open_fixed(ACTIVATION, False, deadline)
        held.append(activation_fd)
        first = metadata(activation_fd)
        require(stat.S_ISREG(first['mode']) and first['nlink'] == 1 and
                0 < first['size'] <= ACTIVATION_MAX, 'ACTIVATION_REGULAR_SIZE_LINK_BOUND')
        raw = read_bounded(activation_fd, ACTIVATION_MAX, deadline)
        actual_sha = hashlib.sha256(raw).hexdigest()
        require(len(raw) == first['size'] and metadata(activation_fd) == first,
                'ACTIVATION_HELD_INPUT_CHANGED')
        require(actual_sha == ACTIVATION_SHA, 'ACTIVATION_SHA_MISMATCH')
        expected = names_from_activation(raw)
        require(set(expected) == {'cpu.max', 'memory.high', 'memory.max', 'memory.swap.max', 'pids.max'},
                'EXACT_PREVIOUSLY_OBSERVED_FIVE_LIMIT_NAMES')
        result['activation'] = dict(bytes=len(raw), sha256=actual_sha, metadata=first,
                                    encoding='base64-original-bytes', original_base64=base64.b64encode(raw).decode('ascii'))
        result['expected_limits'] = expected
        group_fd = open_fixed(CGROUP, True, deadline)
        held.append(group_fd)
        group_before = metadata(group_fd)
        result['cgroup_before'] = group_before
        require(stat.S_ISDIR(group_before['mode']) and group_before['device'] == CGROUP_DEV and
                group_before['inode'] == CGROUP_INO, 'FIXED_MAIN_CGROUP_IDENTITY')
        files = {}
        for name in sorted(set(expected) | {'pids.current', 'pids.events'}):
            check_time(deadline)
            fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=group_fd)
            held.append(fd)
            first_stat = metadata(fd)
            require(stat.S_ISREG(first_stat['mode']) and first_stat['device'] == CGROUP_DEV,
                    'CGROUP_LIMIT_REGULAR_SAME_DEVICE')
            files[name] = (fd, first_stat)
        samples = []
        result['samples'] = samples
        for index in range(2):
            sample = dict(index=index + 1, elapsed_ms=int((time.monotonic() - started) * 1000),
                          values={}, files={})
            samples.append(sample)
            for name, (anchor, first_stat) in files.items():
                check_time(deadline)
                # A new named descriptor is compared to the original held descriptor
                # for each sample. Neither a path replacement nor a held orphan qualifies.
                fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=group_fd)
                try:
                    before = metadata(fd)
                    require(same_identity(first_stat, metadata(anchor)) and same_identity(first_stat, before),
                            'CGROUP_LIMIT_NAMED_IDENTITY_CHANGED:' + name)
                    content = read_bounded(fd, LIMIT_MAX, deadline)
                    after = metadata(fd)
                    require(same_identity(before, after), 'CGROUP_LIMIT_HELD_IDENTITY_CHANGED:' + name)
                    value = content.decode('ascii').strip()
                    require(bool(value), 'EMPTY_CGROUP_LIMIT:' + name)
                    sample['values'][name] = value
                    sample['files'][name] = dict(bytes=len(content), sha256=hashlib.sha256(content).hexdigest(),
                                                before=before, after=after)
                finally:
                    os.close(fd)
            if index == 0:
                command = {}
                result['systemctl'] = command
                if not systemctl_read(command, deadline):
                    result['error'] = command['error'] or dict(type='RuntimeError', message='SYSTEMCTL_COLLECTION_FAILED', errno=None)
                    result['secondary_errors'].extend(command['secondary_errors'])
                result['direct_systemctl_children_owned'] = int('child_pid' in command)
        # Rewalk both complete paths after all data reads, with all original FDs held.
        named_activation = open_fixed(ACTIVATION, False, deadline)
        try:
            require(metadata(named_activation) == first and metadata(activation_fd) == first,
                    'ACTIVATION_FINAL_NAMED_IDENTITY_CHANGED')
        finally:
            os.close(named_activation)
        named_group = open_fixed(CGROUP, True, deadline)
        try:
            after = metadata(group_fd)
            named_after = metadata(named_group)
            require(same_identity(group_before, after) and same_identity(group_before, named_after),
                    'CGROUP_FINAL_NAMED_IDENTITY_CHANGED')
            result['cgroup_after'] = after
            result['cgroup_named_after'] = named_after
            for name, (anchor, first_stat) in files.items():
                check_time(deadline)
                fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=named_group)
                try:
                    require(same_identity(first_stat, metadata(anchor)) and same_identity(first_stat, metadata(fd)),
                            'CGROUP_FINAL_LIMIT_NAMED_IDENTITY_CHANGED:' + name)
                finally:
                    os.close(fd)
        finally:
            os.close(named_group)
        check_time(deadline)
        limits = [{name: sample['values'][name] for name in expected} for sample in samples]
        result['values_stable_between_samples'] = samples[0]['values'] == samples[1]['values']
        result['limits_stable_between_samples'] = limits[0] == limits[1]
        result['each_sample_matches_expected'] = [values == expected for values in limits]
        result['pids_observations'] = []
        for sample in samples:
            current = sample['values']['pids.current']
            require(current.isascii() and current.isdigit(), 'PIDS_CURRENT_INTEGER')
            events = {}
            for line in sample['values']['pids.events'].splitlines():
                pair = line.split()
                require(len(pair) == 2 and re.fullmatch(r'[a-z_]+', pair[0]) and
                        pair[0] not in events and pair[1].isascii() and pair[1].isdigit(), 'PIDS_EVENTS_COUNTER')
                events[pair[0]] = int(pair[1])
            require('max' in events and len(events) <= 16, 'PIDS_EVENTS_MAX_COUNTER_REQUIRED')
            result['pids_observations'].append(dict(current=int(current), events=events))
        properties = result.get('systemctl', {}).get('properties')
        if properties is not None:
            policy = properties['TasksMax']
            normalized = 'max' if policy == 'infinity' else policy
            require(normalized == 'max' or normalized.isascii() and normalized.isdigit(), 'TASKSMAX_FORMAT')
            result['systemd_tasks_max_matches_kernel_samples'] = [normalized == values['pids.max'] for values in limits]
            result['systemd_tasks_current_raw'] = properties['TasksCurrent']
            result['TasksCurrent_and_pids_current_are_not_an_atomic_observation'] = True
        result['differences'] = [{name: dict(expected=expected[name], current=sample['values'][name])
                                  for name in expected if sample['values'][name] != expected[name]}
                                 for sample in samples]
        result['held_and_named_identities_verified'] = True
        result['collection_complete'] = result['error'] is None and not result['secondary_errors']
    except Exception as error:
        failure = dict(type=type(error).__name__, message=str(error), errno=getattr(error, 'errno', None))
        if result['error'] is None:
            result['error'] = failure
        else:
            result['secondary_errors'].append(failure)
    finally:
        for fd in reversed(held):
            try:
                os.close(fd)
            except OSError as error:
                result['secondary_errors'].append(dict(phase='close_owned_fd', type=type(error).__name__,
                                                       message=str(error), errno=error.errno))
                result['collection_complete'] = False
        result['owned_fds_closed'] = not result['secondary_errors'] and result.get('systemctl', {}).get('cleanup_complete', True)
        result['elapsed_ms'] = int((time.monotonic() - started) * 1000)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect-once', action='store_true')
    args = parser.parse_args(argv)
    if not args.collect_once:
        result = dict(state='PLAN_ONLY', activation_path=ACTIVATION, activation_sha256=ACTIVATION_SHA,
                      activation_maximum_bytes=ACTIVATION_MAX, cgroup_path=CGROUP,
                      expected_cgroup_identity=dict(device=CGROUP_DEV, inode=CGROUP_INO),
                      limit_names='five SHA-pinned activation limits plus fixed pids.current and pids.events',
                      systemctl_properties=PROPERTIES, expected_service_identity_fields=EXPECTED_SERVICE,
                      maximum_command_attempts=1, config_file_bodies_read=0,
                      limits_maximum_bytes_each=LIMIT_MAX, output_maximum_bytes=OUTPUT_MAX,
                      deadline_seconds=DEADLINE_SECONDS, runtime_authorized=False,
                      device_file_writes=0, direct_systemctl_children_owned=0, Android_UI_actions=0)
    else:
        result = collect()
    output = (json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(',', ':')) + '\n').encode('ascii')
    require(len(output) <= OUTPUT_MAX, 'COMPLETE_OUTPUT_BOUND_NO_TRUNCATION')
    print(output.decode('ascii'), end='', flush=True)
    return 0 if not args.collect_once or result['collection_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
