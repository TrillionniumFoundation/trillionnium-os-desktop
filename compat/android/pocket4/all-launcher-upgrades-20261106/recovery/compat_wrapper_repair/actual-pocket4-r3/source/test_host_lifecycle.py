#!/usr/bin/python3 -I
"""Actual isolated host process controls; never accesses an Android cell.

Only this run's children/pidfds receive signals.  Each tree uses a fresh user
and PID namespace, no mount/network namespace or Android command.  No killpg,
process-name signal, or existing namespace entry is used.  Failed controls are
retained and never converted to a namespace-capability PASS.
"""
import argparse
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import select
import selectors
import signal
import stat
import subprocess
import sys
import time
import types

sys.dont_write_bytecode = True
PYTHON = '/usr/bin/python3'
UNSHARE = '/usr/bin/unshare'
LIBC = ctypes.CDLL(None, use_errno=True)
LIBC.prctl.argtypes = (ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                      ctypes.c_ulong, ctypes.c_ulong)
LIBC.prctl.restype = ctypes.c_int


def need(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(pid):
    raw = Path('/proc/' + str(pid) + '/stat').read_text()
    tail = raw[raw.rindex(')') + 2:].split()
    return {'host_pid': pid, 'host_parent': int(tail[1]), 'start_ticks': int(tail[19]),
            'state': tail[0], 'process_group': int(tail[2]),
            'pid_namespace': os.readlink('/proc/' + str(pid) + '/ns/pid')}


def dead(fd):
    poll = select.poll()
    poll.register(fd, select.POLLIN | select.POLLHUP | select.POLLERR)
    events = poll.poll(0)
    need(not any(mask & (select.POLLERR | select.POLLNVAL) for _, mask in events), 'INVALID_CONTROL_PIDFD')
    return bool(events)


class Held:
    def __init__(self):
        self.rows, self.handles = {}, {}
        self.opened = self.closed = 0

    def add(self, name, pid, expected_parent=None, expected_start=None):
        need(name not in self.handles and pid != os.getpid(), 'OWNED_NEW_CONTROL_PROCESS_ONLY')
        before = identity(pid)
        if expected_parent is not None:
            need(before['host_parent'] == expected_parent, 'CONTROL_PARENT_DIFFERS')
        if expected_start is not None:
            need(before['start_ticks'] == expected_start, 'CONTROL_BIRTH_DIFFERS')
        fd = os.pidfd_open(pid, 0)
        self.opened += 1
        self.handles[name], self.rows[name] = fd, before
        after = identity(pid)
        need(all(after[k] == before[k] for k in ('host_pid', 'host_parent', 'start_ticks', 'pid_namespace'))
             and not dead(fd), 'CONTROL_PIDFD_BINDING_CHANGED')
        return before

    def send(self, name, signum):
        signal.pidfd_send_signal(self.handles[name], signum, None, 0)

    def wait_dead(self, names, seconds=5):
        end = time.monotonic() + seconds
        while not all(dead(self.handles[name]) for name in names):
            need(time.monotonic() < end, 'OWNED_DEATH_CHAIN_DID_NOT_COMPLETE')
            time.sleep(.02)

    def cleanup(self):
        errors = []
        for name, fd in list(self.handles.items()):
            try:
                if not dead(fd):
                    signal.pidfd_send_signal(fd, signal.SIGKILL, None, 0)
            except ProcessLookupError:
                pass
            except BaseException as error:
                errors.append({'role': name, 'type': type(error).__name__})
        for name, fd in list(self.handles.items()):
            try:
                end = time.monotonic() + 3
                while not dead(fd) and time.monotonic() < end:
                    time.sleep(.02)
                need(dead(fd), 'TEST_CHILD_NOT_RETIRED')
            except BaseException as error:
                errors.append({'role': name, 'type': type(error).__name__})
            finally:
                os.close(fd)
                self.closed += 1
        self.handles.clear()
        need(not errors and self.opened == self.closed, 'CONTROL_CLEANUP_FAILED:' + json.dumps(errors))


def read_ready(pipe, wrapper):
    data, rows = bytearray(), []
    selector = selectors.DefaultSelector()
    selector.register(pipe, selectors.EVENT_READ)
    end = time.monotonic() + 8
    try:
        while len(rows) < 2:
            need(time.monotonic() < end, 'NAMESPACE_READY_TIMEOUT')
            events = selector.select(.1)
            if not events:
                need(wrapper.poll() is None, 'WRAPPER_EXITED_BEFORE_NAMESPACE_READY')
                continue
            block = os.read(pipe.fileno(), 4096)
            need(block, 'NO_NAMESPACE_FIXTURE_OUTPUT')
            data.extend(block)
            need(len(data) <= 16384, 'CONTROL_OUTPUT_BOUND')
            while b'\n' in data:
                line, _, remainder = data.partition(b'\n')
                data = bytearray(remainder)
                rows.append(json.loads(line))
        need({row['kind'] for row in rows} == {'init_ready', 'leaf_ready'}, 'EXACT_FIXTURE_READY_SET')
        return {row['kind']: row for row in rows}
    finally:
        selector.close()


def subreaper(value=None):
    old = ctypes.c_int()
    address = ctypes.cast(ctypes.byref(old), ctypes.c_void_p).value
    need(LIBC.prctl(37, address, 0, 0, 0) == 0, 'READ_TEST_SUBREAPER_FAILED')
    if value is not None:
        need(LIBC.prctl(36, int(value), 0, 0, 0) == 0, 'SET_TEST_SUBREAPER_FAILED')
    return old.value


def reap_known(rows):
    # waitpid may only reap this test process's own children/adopted descendants.
    for row in rows.values():
        try:
            os.waitpid(row['host_pid'], os.WNOHANG)
        except ChildProcessError:
            pass


def lifecycle_case(candidate, fixture_source, case_dir, mode):
    case_dir.mkdir(mode=0o700)
    held = Held()
    wrapper = sentinel = None
    row = {'name': mode, 'passed': False, 'signals': [], 'new_pid_namespace': None,
           'cleanup_error': None, 'Android_commands': 0, 'existing_namespace_entries': 0}
    stderr = open(case_dir / 'wrapper.stderr', 'xb')
    sentinel_stderr = open(case_dir / 'sentinel.stderr', 'xb')
    try:
        sentinel = subprocess.Popen([PYTHON, '-B', '-I', '-c', 'import time;time.sleep(25)'],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=sentinel_stderr, close_fds=True)
        held.add('sentinel', sentinel.pid, os.getpid())
        argv = [PYTHON, '-B', '-I', str(candidate), '--user', '--map-root-user', '--pid',
                '--fork', '--kill-child=TERM', '--forward-signals', PYTHON, '-B', '-I', '-c', fixture_source]
        wrapper = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=stderr, close_fds=True)
        held.add('wrapper', wrapper.pid, os.getpid())
        ready = read_ready(wrapper.stdout, wrapper)
        init, leaf = ready['init_ready'], ready['leaf_ready']
        need(init['namespace_pid'] == 1 and leaf['namespace_pid'] > 1
             and init['pid_namespace'] == leaf['pid_namespace']
             and init['pid_namespace'] != os.readlink('/proc/self/ns/pid'), 'REAL_NEW_PID_NAMESPACE_REQUIRED')
        native = held.add('native_unshare', init['host_parent'], wrapper.pid)
        held.add('namespace_init', init['host_pid'], native['host_pid'], init['start_ticks'])
        held.add('namespace_leaf', leaf['host_pid'], init['host_pid'], leaf['start_ticks'])
        native_argv = Path('/proc/' + str(native['host_pid']) + '/cmdline').read_bytes().split(b'\0')
        need(b'--kill-child=KILL' in native_argv and b'--forward-signals' not in native_argv,
             'ACTUAL_NATIVE_ARGV_NOT_REPAIRED')
        row.update(new_pid_namespace=init['pid_namespace'], processes=held.rows,
                   actual_native_argv=[x.decode() for x in native_argv if x], ready=ready)
        need(held.rows['wrapper']['process_group'] == held.rows['sentinel']['process_group'] == os.getpgrp(),
             'SAME_PROCESS_GROUP_SENTINEL_REQUIRED')
        if mode == 'TERM_then_supervisor_fallback':
            held.send('wrapper', signal.SIGTERM)
            row['signals'].append({'target': 'owned_wrapper_pidfd', 'signal': 'SIGTERM'})
            time.sleep(.3)
            status = dict(line.split(':', 1) for line in
                          Path('/proc/' + str(native['host_pid']) + '/status').read_text().splitlines() if ':' in line)
            pending = int(status['SigPnd'].strip(), 16) | int(status['ShdPnd'].strip(), 16)
            blocked = int(status['SigBlk'].strip(), 16)
            mask = 1 << (signal.SIGTERM - 1)
            need(pending & mask and blocked & mask, 'ACTUAL_NATIVE_TERM_FORWARDING_NOT_OBSERVED')
            need(all(not dead(held.handles[name]) for name in held.handles), 'PREMATURE_TERM_EXIT')
            row['TERM_forwarded_to_exact_native_child_and_blocked'] = True
            row['existing_native_ten_second_fallback_wait_reproduced'] = False
            row['test_grace_interval_seconds'] = .3
        held.send('wrapper', signal.SIGKILL)
        row['signals'].append({'target': 'owned_wrapper_pidfd', 'signal': 'SIGKILL'})
        owned_tree = ('wrapper', 'native_unshare', 'namespace_init', 'namespace_leaf')
        held.wait_dead(owned_tree)
        need(not dead(held.handles['sentinel']) and identity(sentinel.pid)['start_ticks'] == held.rows['sentinel']['start_ticks'],
             'UNRELATED_SAME_GROUP_SENTINEL_CHANGED')
        wrapper.wait(timeout=2)
        row.update(passed=True, all_four_original_test_pidfds_dead=True,
                   unrelated_same_process_group_sentinel_unchanged=True,
                   wrapper_returncode=wrapper.returncode, native_child_signal_sent_by_test=False,
                   namespace_init_or_leaf_signal_sent_by_test=False)
    except BaseException as error:
        row['error'] = {'type': type(error).__name__, 'code': str(error)[:240]}
    finally:
        try:
            held.cleanup()
        except BaseException as error:
            row['passed'] = False
            row['cleanup_error'] = {'type': type(error).__name__, 'code': str(error)[:240]}
        for child in (wrapper, sentinel):
            if child is not None:
                try:
                    child.wait(timeout=2)
                except BaseException as error:
                    row['passed'] = False
                    row['join_error'] = type(error).__name__
                if child.stdout is not None:
                    child.stdout.close()
        reap_known(held.rows)
        stderr.close()
        sentinel_stderr.close()
        row['pidfds'] = {'acquired': held.opened, 'closed': held.closed}
        row['stderr'] = (case_dir / 'wrapper.stderr').read_text()[:2000]
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--candidate-sha256', required=True)
    parser.add_argument('--result-dir', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    source = args.candidate.read_bytes()
    need(sha(source) == args.candidate_sha256, 'PINNED_WRAPPER_REQUIRED')
    fixture = Path(__file__).resolve().with_name('pidns_fixture.py')
    need(fixture.is_file(), 'EXACT_FIXTURE_SOURCE_REQUIRED')
    fixture_source = fixture.read_bytes()
    need(len(fixture_source) == 1013 and sha(fixture_source) ==
         'da61ecac210799f4626cdc7afa83476049374f4a36e9b87ba0e6a92e664016d1',
         'EXACT_PINNED_FIXTURE_BYTES_REQUIRED')
    compile(fixture_source, str(fixture), 'exec')
    args.result_dir.mkdir(mode=0o700)
    before_fds = len(os.listdir('/proc/self/fd'))
    report = {'schema': 'pocket4-compat-wrapper-real-host-controls-v1', 'ok': False,
              'candidate': {'path': str(args.candidate), 'bytes': len(source), 'sha256': sha(source)},
              'fixture_sha256': sha(fixture_source), 'caller_uid': os.getuid(),
              'test_revision': 'r3-inline-pinned-fixture',
              'fixture_transport': 'pinned_utf8_source_via_python_c',
              'kernel_release': os.uname().release, 'cases': [], 'Android_commands': 0,
              'existing_namespace_entries': 0, 'production_wrapper_deployed': False,
              'Pocket4_runtime_qualified': False, 'errors': []}
    previous_subreaper = subreaper(1)
    try:
        native = Path(UNSHARE)
        meta = native.stat()
        need(stat.S_ISREG(meta.st_mode) and not meta.st_mode & (stat.S_ISUID | stat.S_ISGID),
             'NATIVE_UNSHARE_MUST_NOT_CLEAR_PDEATHSIG_BY_SET_ID_EXEC')
        try:
            capability = os.getxattr(native, 'security.capability')
        except OSError as error:
            need(error.errno == errno.ENODATA, 'NATIVE_CAPABILITY_STATE_UNKNOWN')
            capability = b''
        need(not capability, 'NATIVE_UNSHARE_FILE_CAPABILITIES_WOULD_CLEAR_PDEATHSIG')
        version = subprocess.run([UNSHARE, '--version'], capture_output=True, timeout=3, check=True)
        help_result = subprocess.run([UNSHARE, '--help'], capture_output=True, timeout=3, check=True)
        need(b'--kill-child' in help_result.stdout, 'ACTUAL_NATIVE_CHILD_DEATH_CAPABILITY_REQUIRED')
        report['native_unshare'] = {'path': UNSHARE, 'bytes': meta.st_size, 'sha256': sha(native.read_bytes()),
                                   'uid': meta.st_uid, 'mode': stat.S_IMODE(meta.st_mode),
                                   'version': version.stdout.decode().strip(),
                                   'help_sha256': sha(help_result.stdout), 'file_capabilities_absent': True}
        (args.result_dir / 'native-unshare.help').write_bytes(help_result.stdout)
        loaded = types.ModuleType('actual_wrapper_controls')
        loaded.__file__ = str(args.candidate)
        exec(compile(source, str(args.candidate), 'exec'), loaded.__dict__)
        marker = args.result_dir / 'must-not-exec'
        actual_parent = os.getpid()
        try:
            subprocess.Popen([PYTHON, '-I', '-c', 'from pathlib import Path;Path(' + repr(str(marker)) + ').write_text("wrong")'],
                             preexec_fn=lambda: loaded.arm_owned_child(actual_parent + 1), close_fds=True)
        except subprocess.SubprocessError:
            need(not marker.exists(), 'PARENT_RACE_REACHED_EXEC')
            report['cases'].append({'name': 'actual_fork_parent_mismatch_rejected_before_exec', 'passed': True})
        else:
            raise RuntimeError('PARENT_MISMATCH_WAS_NOT_REJECTED')
        program = 'import json,sys;print(json.dumps(sys.argv[1:]))'
        literal = subprocess.run([PYTHON, '-B', '-I', str(args.candidate), '--fork', '--kill-child=TERM',
                                  PYTHON, '-B', '-I', '-c', program, '--forward-signals', '--kill-child=TERM'],
                                 capture_output=True, timeout=5)
        need(literal.returncode == 0 and json.loads(literal.stdout) == ['--forward-signals', '--kill-child=TERM'],
             'PROGRAM_ARGUMENTS_WERE_REWRITTEN')
        report['cases'].append({'name': 'real_native_command_arguments_preserved', 'passed': True})
        for mode in ('TERM_then_supervisor_fallback', 'wrapper_SIGKILL_without_TERM'):
            report['cases'].append(lifecycle_case(args.candidate, fixture_source.decode('utf-8'), args.result_dir / mode, mode))
        need(all(row['passed'] for row in report['cases']), 'REAL_PROCESS_CONTROL_FAILED')
        need(args.candidate.read_bytes() == source, 'WRAPPER_SOURCE_CHANGED_DURING_TEST')
        need(fixture.read_bytes() == fixture_source, 'FIXTURE_SOURCE_CHANGED_DURING_TEST')
        report['ok'] = True
    except BaseException as error:
        report['errors'].append({'type': type(error).__name__, 'code': str(error)[:240]})
    finally:
        subreaper(previous_subreaper)
        report['FD_count_before'] = before_fds
        report['FD_count_after'] = len(os.listdir('/proc/self/fd'))
        if report['FD_count_after'] != before_fds:
            report['ok'] = False
            report['errors'].append({'code': 'TEST_FD_COUNT_CHANGED'})
    raw = (json.dumps(report, sort_keys=True, indent=2) + '\n').encode()
    (args.result_dir / 'result.json').write_bytes(raw)
    print(json.dumps({'ok': report['ok'], 'result': str(args.result_dir / 'result.json'),
                      'bytes': len(raw), 'sha256': sha(raw), 'case_count': len(report['cases']),
                      'errors': report['errors']}), flush=True)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
