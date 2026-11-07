#!/usr/bin/env python3
"""Small local parser/owned-FD controls; never call the fixed collector."""
import contextlib
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
import types
from unittest import mock

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'read_main_lock_fds.py'
RAW = SOURCE.read_bytes()
reader = types.ModuleType('owned_local_reader_control')
reader.__file__ = str(SOURCE)
exec(compile(RAW, str(SOURCE), 'exec'), reader.__dict__)
results = []


def require(value, message):
    if not value:
        raise AssertionError(message)


def rejected(fn, label):
    try:
        fn()
    except (RuntimeError, ValueError, UnicodeError):
        return
    raise AssertionError('accepted invalid input: ' + label)


def closed(fd):
    try:
        os.fstat(fd)
    except OSError as error:
        require(error.errno == errno.EBADF, 'unexpected fstat error')
        return True
    return False


def case(name):
    def invoke(fn):
        fn()
        results.append(dict(name=name, passed=True))
        return fn
    return invoke


def support():
    def check_time(deadline):
        require(time.monotonic() < deadline, 'local control deadline')
    return types.SimpleNamespace(check_time=check_time)


BASE = b'pos:\t0\nflags:\t02000002\nmnt_id:\t87\nino:\t8312\n'


@case('fdinfo_same_inode_flock_zero_pid_ofd_and_waiter')
def fdinfo_positive():
    require(reader.parse_fdinfo(BASE)['lock_records'] == [], 'no-lock shape')
    raw = BASE + b'lock:\t1: FLOCK  ADVISORY  WRITE 0 00:1c:8312 0 EOF\n'
    value = reader.parse_fdinfo(raw)
    require(value['lock_records'][0]['kernel_reported_pid'] == 0, 'retain zero PID')
    require(value['lock_PID_is_not_a_process_birth_or_cleanup_authority'], 'no PID authority')
    raw = BASE + b'lock:\t2: -> OFDLCK ADVISORY READ -1 0:1c:8312 3 90\n'
    value = reader.parse_fdinfo(raw)['lock_records'][0]
    require(value['waiting'] and value['kernel_reported_pid'] == -1, 'retain waiter and -1')


@case('fdinfo_other_inode_unknown_fields_and_bounds_rejected')
def fdinfo_negative():
    line = b'lock:\t1: FLOCK ADVISORY WRITE 1 00:1c:8312 0 EOF\n'
    bad = [BASE.replace(b'8312', b'8313'), BASE + line.replace(b':8312', b':8313'),
           BASE + line.replace(b'00:1c', b'00:1d'), BASE + b'pos:\t0\n',
           BASE + b'other:\tprivate-data\n', BASE + line.replace(b'WRITE', b'EXEC'),
           BASE + line.replace(b'WRITE 1', b'WRITE -2'), BASE + b'\0',
           BASE + line * (reader.LOCK_ROWS_MAX + 1), b'x' * (reader.FDINFO_MAX + 1)]
    for i, raw in enumerate(bad):
        rejected(lambda raw=raw: reader.parse_fdinfo(raw), str(i))


@case('canonical_numeric_fd_names_and_path_rejection')
def fd_names():
    for value in ('0', '7', '2147483647'):
        require(reader.parse_fd_name(value) == int(value), 'valid numeric FD')
    for value in ('', '.', '..', '../7', '7/8', '/7', '07', '-1', '+2', '2147483648', '1\n', 7):
        rejected(lambda value=value: reader.parse_fd_name(value), repr(value))


@case('proc_stat_birth_and_proc_mount_filter_preserved')
def proc_parsers():
    raw = b'55 (owned child) S 1 ' + b'0 ' * 17 + b'12345 0 0\n'
    parsed = reader.parse_proc_stat(raw, 55)
    require(parsed == dict(pid=55, comm='owned child', state='S', parent_pid=1, start_ticks=12345), 'stat fields')
    rejected(lambda: reader.parse_proc_stat(raw, 56), 'wrong stat PID')
    mount = (b'20 1 0:22 / /unrelated-private-path rw - tmpfs tmpfs rw\n'
             b'21 1 0:5 / /proc rw,nosuid - proc proc rw\n')
    value = reader.parse_proc_mount(mount)
    require(value['record']['mount_point'] == '/proc' and value['unrelated_mount_rows_exported'] == 0,
            'exact /proc record')
    require('unrelated-private-path' not in json.dumps(value), 'no unrelated mount export')
    require(value['proc_superblock_pid_namespace_proven'] is False, 'no namespace extrapolation')
    rejected(lambda: reader.parse_proc_mount(mount + mount.splitlines(True)[1]), 'duplicate proc mount')


@case('exact_prior_ticket_failure_pin_and_mutation')
def prior_failure():
    raw = (HERE / 'prior-ticket-launch.json').read_bytes()
    value = reader.validate_prior(raw)
    require(value['action_attempted'] is False and value['outcome_unknown'] is False, 'actual zero action')
    rejected(lambda: reader.validate_prior(raw + b'\n'), 'changed exact prior bytes')


@case('actual_owned_directory_enumeration_and_total_budget')
def owned_directory():
    with tempfile.TemporaryDirectory(prefix='owned-fd-control-', dir=HERE) as temporary:
        root = Path(temporary)
        for name in ('0', '3', '12'):
            (root / name).write_bytes(b'')
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            budget = dict(enumerated=0)
            require(reader.directory_names(fd, support(), budget, time.monotonic() + 5) == [0, 3, 12], 'actual names')
            require(budget['enumerated'] == 3, 'count actual entries')
        finally:
            os.close(fd)
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            budget = dict(enumerated=reader.FD_TOTAL_MAX - 1)
            rejected(lambda: reader.directory_names(fd, support(), budget, time.monotonic() + 5), 'total entry bound')
            require(budget['enumerated'] == reader.FD_TOTAL_MAX, 'no budget overrun')
        finally:
            os.close(fd)
        require(closed(fd), 'owned directory FD closed')


@case('owned_directory_iterator_primary_error_survives_close_error')
def iterator_failure():
    with tempfile.TemporaryDirectory(prefix='owned-iterator-control-', dir=HERE) as temporary:
        (Path(temporary) / '1').write_bytes(b'')
        fd = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        actual_scandir = os.scandir
        instances = []
        class FailingIterator:
            def __init__(self, number):
                self.actual = actual_scandir(number)
                self.close_calls = 0
                instances.append(self)
            def __iter__(self):
                return self
            def __next__(self):
                raise RuntimeError('ITERATION_SENTINEL')
            def close(self):
                self.close_calls += 1
                self.actual.close()
                raise OSError(errno.EIO, 'ITERATOR_CLOSE_SENTINEL')
        try:
            with mock.patch.object(reader.os, 'scandir', FailingIterator):
                try:
                    reader.directory_names(fd, support(), dict(enumerated=0), time.monotonic() + 5)
                except RuntimeError as error:
                    require(str(error) == 'ITERATION_SENTINEL', 'first error retained')
                    require(len(error._lock_close_notes) == 1, 'close error retained separately')
                else:
                    raise AssertionError('missing iterator error')
            require(len(instances) == 1 and instances[0].close_calls == 1, 'iterator close once')
        finally:
            os.close(fd)
        require(closed(fd), 'owned directory FD closed')


@case('actual_owned_walk_child_and_leaf_survive_parent_close_failure')
def walk_close_failure():
    with tempfile.TemporaryDirectory(prefix='owned-walk-control-', dir=HERE) as temporary:
        target = Path(temporary) / 'leaf'
        target.write_bytes(b'owned')
        parent_closes = len(str(target)[1:].split('/'))
        for fail_at in (1, parent_closes):
            fds = reader.OwnedFDs()
            opened, close_calls = [], []
            real_open, real_close = os.open, os.close
            def traced_open(*args, **kwargs):
                fd = real_open(*args, **kwargs)
                opened.append(fd)
                return fd
            def failed_close(fd):
                close_calls.append(fd)
                real_close(fd)
                if len(close_calls) == fail_at:
                    raise OSError(errno.EIO, 'OWNED_PARENT_CLOSE_SENTINEL')
            try:
                with mock.patch.object(reader.os, 'open', traced_open), mock.patch.object(reader.os, 'close', failed_close):
                    try:
                        reader.open_fixed(fds, support(), str(target), os.O_RDONLY, time.monotonic() + 5)
                    except OSError as error:
                        require(error.errno == errno.EIO, 'actual close error retained')
                    else:
                        raise AssertionError('expected parent close failure')
                    finally:
                        fds.finish()
                require(not fds.values and len(fds.close_errors) == 1, 'no owned FD forgotten; no closed claim')
                require(opened and all(closed(fd) for fd in set(opened)), 'all actual owned descriptors closed')
                require(len(close_calls) == len(opened), 'one close per opened lifetime')
            finally:
                fds.finish()


@case('actual_owned_pipe_primary_failure_not_replaced_by_close')
def primary_close_failure():
    fds = reader.OwnedFDs()
    rfd, wfd = os.pipe2(os.O_CLOEXEC)
    fds.take(rfd); fds.take(wfd)
    real_close = os.close
    count = []
    sentinel = RuntimeError('PRIMARY_SENTINEL')
    def failed_close(fd):
        count.append(fd)
        real_close(fd)
        if fd == rfd:
            raise OSError(errno.EIO, 'PIPE_CLOSE_SENTINEL')
    try:
        with mock.patch.object(reader.os, 'close', failed_close):
            try:
                try:
                    raise sentinel
                finally:
                    fds.close(rfd)
            except RuntimeError as error:
                require(error is sentinel and len(error._lock_close_notes) == 1, 'primary object preserved')
            finally:
                fds.finish()
        require(count.count(rfd) == count.count(wfd) == 1, 'no ambiguous close retry')
        require(closed(rfd) and closed(wfd) and not fds.values and len(fds.close_errors) == 1, 'FD/error final state')
    finally:
        fds.finish()


@case('default_plan_has_no_collector_call')
def plan_only():
    output = io.StringIO()
    with mock.patch.object(reader, 'collect', side_effect=AssertionError('collect forbidden')), contextlib.redirect_stdout(output):
        require(reader.main(None, b'', []) == 0, 'PLAN exit')
    value = json.loads(output.getvalue())
    require(value['state'] == 'PLAN_ONLY' and value['runtime_authorized'] is False and value['remote_actions'] == 0,
            'PLAN-only semantics')


print(json.dumps(dict(schema=1, scope='local parser and actual owned-FD failure controls only',
                      source_bytes=len(RAW), source_sha256=hashlib.sha256(RAW).hexdigest(),
                      count=len(results), results=results, collect_executed=False,
                      proc_or_Main_reads=False, Hepta_executed=False, device_qualification=False),
                 sort_keys=True, indent=2))
