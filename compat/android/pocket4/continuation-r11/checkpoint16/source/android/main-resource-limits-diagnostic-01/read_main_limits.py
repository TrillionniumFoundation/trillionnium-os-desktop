#!/usr/bin/env python3
"""Collect fixed Main resource inputs only; never qualify or change Main."""
import argparse
import base64
import hashlib
import json
import os
import re
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
DEADLINE_SECONDS = 8.0
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


def collect():
    started = time.monotonic()
    deadline = started + DEADLINE_SECONDS
    result = dict(schema=1, collection_complete=False, error=None, secondary_errors=[],
                  activation_path=ACTIVATION, activation_expected_sha256=ACTIVATION_SHA,
                  activation_maximum_bytes=ACTIVATION_MAX,
                  cgroup_path=CGROUP, expected_cgroup_identity=dict(device=CGROUP_DEV, inode=CGROUP_INO),
                  limits_maximum_bytes_each=LIMIT_MAX, deadline_seconds=DEADLINE_SECONDS,
                  device_file_writes=0, subprocesses_started=0, Android_UI_actions=0,
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
        for name in sorted(expected):
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
        result['values_stable_between_samples'] = samples[0]['values'] == samples[1]['values']
        result['each_sample_matches_expected'] = [sample['values'] == expected for sample in samples]
        result['differences'] = [{name: dict(expected=expected[name], current=sample['values'][name])
                                  for name in expected if sample['values'][name] != expected[name]}
                                 for sample in samples]
        result['held_and_named_identities_verified'] = True
        result['collection_complete'] = True
    except Exception as error:
        result['error'] = dict(type=type(error).__name__, message=str(error), errno=getattr(error, 'errno', None))
    finally:
        for fd in reversed(held):
            try:
                os.close(fd)
            except OSError as error:
                result['secondary_errors'].append(dict(phase='close_owned_fd', type=type(error).__name__,
                                                       message=str(error), errno=error.errno))
                result['collection_complete'] = False
        result['owned_fds_closed'] = not result['secondary_errors']
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
                      limit_names='exact five basenames from the SHA-pinned activation only',
                      limits_maximum_bytes_each=LIMIT_MAX, output_maximum_bytes=OUTPUT_MAX,
                      deadline_seconds=DEADLINE_SECONDS, runtime_authorized=False,
                      device_file_writes=0, subprocesses_started=0, Android_UI_actions=0)
    else:
        result = collect()
    output = (json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(',', ':')) + '\n').encode('ascii')
    require(len(output) <= OUTPUT_MAX, 'COMPLETE_OUTPUT_BOUND_NO_TRUNCATION')
    print(output.decode('ascii'), end='', flush=True)
    return 0 if not args.collect_once or result['collection_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
