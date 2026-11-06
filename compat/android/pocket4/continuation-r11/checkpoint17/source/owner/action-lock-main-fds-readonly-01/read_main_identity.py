#!/usr/bin/env python3
"""Observe the original Main identity contract around its unchanged guard."""
import argparse
import hashlib
import json
import os
import stat
import time
import traceback
import types

ACTIVATION = '/home/alex/work/pocket4-app-production-20261104-r10/deployment-preparation/activation-after-01.json'
VERIFIED = '/home/alex/work/pocket4-app-production-20261104-r10/deployment-preparation/activation-verified-01.json'
CELL = '/etc/droidloom/cell.json'
REFERENCE = '/home/alex/work/pocket4-owned-amazon-qa-r1-install-state-01/source/references/readonly_r3_coordinator.py'
EPOCH_SOURCE = '/home/alex/work/pocket4-framework-epoch-20261104-r10/framework_epoch.py'
CGROUP = '/sys/fs/cgroup/system.slice/droidloomd.service'
CGROUP_DEV, CGROUP_INO = 30, 26651611
BOOT_ID = '/proc/sys/kernel/random/boot_id'
EPOCH_SHA = '48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'
INPUTS = (
    ('activation', ACTIVATION, '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615', 63675),
    ('verified', VERIFIED, '2d6f2ef7953b98109044f823da56694111bd9f8ff14fff5e746afb7bd42b0387', None),
    ('cell', CELL, 'f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc', None),
    ('reference_source', REFERENCE, 'e2769eeeae2d620456a67959dfaff3b07545f2352cd9a60692450451004c39fd', 16900),
    ('epoch_source', EPOCH_SOURCE, 'f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288', None),
)
FRAMEWORK_ROLES = ('init', 'surfaceflinger', 'system_server', 'zygote64')
HOST_ROLES = ('daemon_process', 'launcher_process', 'presenter_process')
LIMIT_NAMES = ('cpu.max', 'memory.high', 'memory.max', 'memory.swap.max', 'pids.max')
INPUT_MAX = 1024 * 1024
PSEUDO_MAX = 4096
OUTPUT_MAX = 1024 * 1024
DEADLINE_SECONDS = 20.0


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


def failure(phase, error):
    return dict(phase=phase, type=type(error).__name__, message=str(error),
                errno=getattr(error, 'errno', None))


def read_regular(path, expected_sha, expected_bytes, deadline, anchor=None):
    fd = open_fixed(path, False, deadline)
    try:
        before = metadata(fd)
        require(stat.S_ISREG(before['mode']) and before['nlink'] == 1 and
                0 < before['size'] <= INPUT_MAX, 'FIXED_INPUT_REGULAR_SINGLE_LINK_BOUND')
        if anchor is not None:
            require(before == metadata(anchor['fd']) == anchor['metadata'], 'INPUT_NAMED_OR_HELD_CHANGED')
        raw = read_bounded(fd, INPUT_MAX, deadline)
        after = metadata(fd)
        require(before == after and len(raw) == before['size'], 'INPUT_HELD_READ_CHANGED')
        require(expected_bytes is None or len(raw) == expected_bytes, 'FIXED_INPUT_BYTE_LENGTH')
        digest = hashlib.sha256(raw).hexdigest()
        require(digest == expected_sha, 'FIXED_INPUT_SHA256:' + path)
        record = dict(path=path, bytes=len(raw), sha256=digest, before=before, after=after)
        return raw, record
    finally:
        os.close(fd)


def load_exact_source(raw, path, name):
    module = types.ModuleType(name)
    module.__file__ = path
    exec(compile(raw, path, 'exec'), module.__dict__)
    return module


def read_pseudo(path, deadline):
    fd = open_fixed(path, False, deadline)
    try:
        before = metadata(fd)
        require(stat.S_ISREG(before['mode']), 'FIXED_PSEUDO_REGULAR')
        raw = read_bounded(fd, PSEUDO_MAX, deadline)
        after = metadata(fd)
        require(before == after and raw, 'PSEUDO_IDENTITY_CHANGED_OR_EMPTY')
        return dict(path=path, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                    before=before, after=after, value=raw.decode('ascii').strip())
    finally:
        os.close(fd)


def collect():
    started = time.monotonic()
    deadline = started + DEADLINE_SECONDS
    result = dict(schema=1, collection_complete=False, error=None, secondary_errors=[],
                  inputs={}, phases=[], original_guard=dict(attempted=False, completed=False, passed=False),
                  runtime_authorized=False, Main_mutations=0, Android_UI_actions=0,
                  device_file_writes=0, child_processes_started=0,
                  namespace_entry_performed=False, actor_logs_read=False,
                  guard_source_modified=False, epoch_source_modified=False,
                  original_five_limit_equality_required=True,
                  main_epoch_expected=EPOCH_SHA, deadline_seconds=DEADLINE_SECONDS,
                  scope='original three SHA inputs, boot/four framework/three host process identities and all five limits',
                  observation_scope='sequential before/after reads around one unchanged original guard; not an atomic snapshot',
                  unmeasured_scope=['all application state', 'all runtime artifacts', 'service restart/reload actor',
                                    'new systemd properties or configuration contents'])
    anchors = {}
    held = []
    group_fd = None
    close_failed = False

    def remember(phase, error):
        record = failure(phase, error)
        if result['error'] is None:
            result['error'] = record
        else:
            result['secondary_errors'].append(record)

    try:
        require(os.getuid() == os.geteuid() == 0, 'ROOT_READ_ONLY_COLLECTOR_REQUIRED')
        bodies = {}
        for name, path, digest, length in INPUTS:
            raw, initial = read_regular(path, digest, length, deadline)
            fd = open_fixed(path, False, deadline)
            held.append(fd)
            require(metadata(fd) == initial['before'], 'INITIAL_INPUT_ANCHOR_CHANGED')
            anchors[name] = dict(fd=fd, metadata=initial['before'])
            bodies[name] = raw
            result['inputs'][name] = initial
        activation = json.loads(bodies['activation'].decode('utf-8'))
        require(activation['framework_epoch']['sha256'] == EPOCH_SHA, 'ORIGINAL_EPOCH_PIN')
        expected_framework = activation['framework_epoch']['binding']['processes']
        require(set(expected_framework) == set(FRAMEWORK_ROLES), 'ORIGINAL_FOUR_FRAMEWORK_ROLES')
        require(set(activation['limits']) == set(LIMIT_NAMES), 'ORIGINAL_FIVE_LIMITS')
        expected_boot = activation['framework_epoch']['binding']['boot_id']
        expected_processes = {name: expected_framework[name] for name in FRAMEWORK_ROLES}
        expected_processes.update({name: activation[name] for name in HOST_ROLES})
        for expected in expected_processes.values():
            require(type(expected['host_pid']) is int and expected['host_pid'] > 0, 'ORIGINAL_EXACT_HOST_PID')
        result['expected_limits'] = activation['limits']
        result['expected_boot_id'] = expected_boot
        reference = load_exact_source(bodies['reference_source'], REFERENCE, 'fixed_original_main_reference')
        epoch = load_exact_source(bodies['epoch_source'], EPOCH_SOURCE, 'fixed_original_main_epoch')
        require(str(reference.ACTIVATION) == ACTIVATION and str(reference.VERIFIED) == VERIFIED and
                str(reference.EPOCH_SOURCE) == EPOCH_SOURCE and str(reference.MAIN_CGROUP) == CGROUP and
                reference.EPOCH == EPOCH_SHA and reference.ACTIVATION_SHA == INPUTS[0][2] and
                reference.VERIFIED_SHA == INPUTS[1][2] and reference.CELL_SHA == INPUTS[2][2] and
                reference.EPOCH_SOURCE_SHA == INPUTS[4][2], 'EXACT_REFERENCE_CONSTANTS')
        require(callable(reference.main_guard) and callable(epoch.require_unchanged) and
                callable(epoch.process_identity), 'EXISTING_ORIGINAL_API_REQUIRED')
        group_fd = open_fixed(CGROUP, True, deadline)
        held.append(group_fd)
        group_before = metadata(group_fd)
        require(stat.S_ISDIR(group_before['mode']) and group_before['device'] == CGROUP_DEV and
                group_before['inode'] == CGROUP_INO, 'FIXED_MAIN_CGROUP_IDENTITY')
        result['cgroup_before'] = group_before

        def phase(label):
            nonlocal close_failed
            observed = dict(label=label, complete=False, errors=[], inputs={}, processes={}, limits={},
                            framework_epoch_check=dict(attempted=False, passed=False),
                            elapsed_start_ms=int((time.monotonic() - started) * 1000))
            result['phases'].append(observed)
            for name, path, digest, length in INPUTS[:3]:
                try:
                    _, record = read_regular(path, digest, length, deadline, anchors[name])
                    observed['inputs'][name] = record
                except Exception as error:
                    observed['errors'].append(failure('input:' + name, error))
            try:
                record = read_pseudo(BOOT_ID, deadline)
                record['matches_expected'] = record['value'] == expected_boot
                observed['boot'] = record
            except Exception as error:
                observed['errors'].append(failure('boot_id', error))
            for name, expected in expected_processes.items():
                record = dict(expected_host_pid=expected['host_pid'], complete=False, matches_expected=False)
                observed['processes'][name] = record
                try:
                    check_time(deadline)
                    actual = epoch.process_identity(expected['host_pid'])
                    check_time(deadline)
                    record.update(actual=actual, complete=True, matches_expected=actual == expected)
                except Exception as error:
                    observed['errors'].append(failure('process_identity:' + name, error))
            try:
                check_time(deadline)
                observed['framework_epoch_check']['attempted'] = True
                epoch.require_unchanged(activation['framework_epoch'])
                check_time(deadline)
                observed['framework_epoch_check']['passed'] = True
            except Exception as error:
                observed['framework_epoch_check']['error'] = failure('original_require_unchanged', error)
                observed['errors'].append(observed['framework_epoch_check']['error'])
            for name in LIMIT_NAMES:
                fd = None
                try:
                    check_time(deadline)
                    fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=group_fd)
                    before = metadata(fd)
                    require(stat.S_ISREG(before['mode']) and before['device'] == CGROUP_DEV, 'FIXED_LIMIT_SAME_DEVICE')
                    raw = read_bounded(fd, PSEUDO_MAX, deadline)
                    after = metadata(fd)
                    require(before == after and raw, 'FIXED_LIMIT_IDENTITY_OR_CONTENT')
                    value = raw.decode('ascii').strip()
                    observed['limits'][name] = dict(value=value, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                                                  before=before, after=after,
                                                  expected=activation['limits'][name], matches_expected=value == activation['limits'][name])
                except Exception as error:
                    observed['errors'].append(failure('limit:' + name, error))
                finally:
                    if fd is not None:
                        try:
                            os.close(fd)
                        except OSError as error:
                            close_failed = True
                            observed['errors'].append(failure('close_limit:' + name, error))
            observed['complete'] = (not observed['errors'] and len(observed['inputs']) == 3 and
                                    'boot' in observed and len(observed['processes']) == 7 and
                                    all(record['complete'] for record in observed['processes'].values()) and
                                    len(observed['limits']) == 5 and observed['framework_epoch_check']['passed'])
            observed['identity_matches_expected'] = (observed['complete'] and observed['boot']['matches_expected'] and
                                                     all(record['matches_expected'] for record in observed['processes'].values()))
            observed['all_five_limits_match_expected'] = (len(observed['limits']) == 5 and
                                                         all(record['matches_expected'] for record in observed['limits'].values()))
            observed['elapsed_end_ms'] = int((time.monotonic() - started) * 1000)

        phase('before_original_guard')
        guard = result['original_guard']
        try:
            check_time(deadline)
            guard['attempted'] = True
            # The loaded function and both modules remain byte-exact and unmodified.
            guard['return_value'] = reference.main_guard(activation, epoch)
            guard['passed'] = True
        except Exception as error:
            guard['error'] = failure('unchanged_original_main_guard', error)
            guard['traceback'] = traceback.format_exc()
        finally:
            guard['completed'] = guard['attempted']
        phase('after_original_guard')
        final_inputs = {}
        result['final_inputs'] = final_inputs
        for name, path, digest, length in INPUTS:
            try:
                _, record = read_regular(path, digest, length, deadline, anchors[name])
                final_inputs[name] = record
            except Exception as error:
                remember('final_input:' + name, error)
        named = None
        try:
            named = open_fixed(CGROUP, True, deadline)
            result['cgroup_after'] = metadata(group_fd)
            result['cgroup_named_after'] = metadata(named)
            require(result['cgroup_after'] == group_before == result['cgroup_named_after'], 'CGROUP_FINAL_IDENTITY_CHANGED')
        finally:
            if named is not None:
                os.close(named)
        check_time(deadline)
        result['both_identity_observations_match'] = all(item['identity_matches_expected'] for item in result['phases'])
        result['limits_values_stable_between_samples'] = (
            {name: row['value'] for name, row in result['phases'][0]['limits'].items()} ==
            {name: row['value'] for name, row in result['phases'][1]['limits'].items()})
        result['original_guard_observed_failure'] = guard['attempted'] and not guard['passed']
        result['qualification_failure_preserved'] = guard['completed'] and not guard['passed']
    except Exception as error:
        remember('collect_fixed_identity', error)
    finally:
        for fd in reversed(held):
            try:
                os.close(fd)
            except OSError as error:
                close_failed = True
                remember('close_owned_fd', error)
        result['owned_fds_closed'] = (not close_failed and result['error'] is None and
                                     not result['secondary_errors'] and
                                     all(not item['errors'] for item in result['phases']))
        result['collection_complete'] = (result['error'] is None and not result['secondary_errors'] and
                                         result['owned_fds_closed'] and len(result['phases']) == 2 and
                                         all(item['complete'] for item in result['phases']) and
                                         result['original_guard']['completed'] and len(result.get('final_inputs', {})) == 5)
        result['elapsed_ms'] = int((time.monotonic() - started) * 1000)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect-once', action='store_true')
    args = parser.parse_args(argv)
    if args.collect_once:
        result = collect()
    else:
        result = dict(state='PLAN_ONLY', input_paths_and_sha256=[dict(name=n, path=p, sha256=h, bytes=b) for n,p,h,b in INPUTS],
                      cgroup_path=CGROUP, cgroup_identity=dict(device=CGROUP_DEV, inode=CGROUP_INO),
                      framework_roles=FRAMEWORK_ROLES, host_roles=HOST_ROLES,
                      original_guard_maximum_calls=1, independent_identity_observations=2,
                      deadline_seconds=DEADLINE_SECONDS, output_maximum_bytes=OUTPUT_MAX,
                      child_processes_started=0, device_file_writes=0, Android_UI_actions=0,
                      runtime_authorized=False, original_five_limit_equality_required=True)
    raw = (json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(',', ':')) + '\n').encode('ascii')
    require(len(raw) <= OUTPUT_MAX, 'COMPLETE_OUTPUT_BOUND_NO_TRUNCATION')
    print(raw.decode('ascii'), end='', flush=True)
    return 0 if not args.collect_once or result['collection_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
