#!/usr/bin/env python3
"""Exercise the actual controller functions without importing host actions."""
import ast
import os
from pathlib import Path
import resource
import stat
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get('NATIVE_OBSERVER_CANDIDATE', BASE / 'candidate/ai395_native_controller.py'))
ORIGINAL = Path(os.environ.get('NATIVE_OBSERVER_ORIGINAL', BASE / 'original/ai395_native_controller.py'))


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def load_functions(path, namespace):
    tree = ast.parse(path.read_text(), filename=str(path))
    wanted = {'parse_owned_allocation', 'allocation_log_limit', 'observe_owned_allocation', 'monitor'}
    nodes = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in wanted]
    for node in nodes:
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
    return tree


class FakeDu:
    def __init__(self, results, advance=None):
        self.results = iter(results)
        self.calls = []
        self.advance = advance

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs['timeout']))
        rc, out, err = next(self.results)
        for stream, data in [(kwargs['stdout'], out), (kwargs['stderr'], err)]:
            if hasattr(stream, 'write'):
                stream.write(data)
                stream.flush()
        if self.advance:
            self.advance()
        if rc == 'timeout':
            raise subprocess.TimeoutExpired(argv, kwargs['timeout'], output=out, stderr=err)
        return subprocess.CompletedProcess(argv, rc, out, err)


class AllocationObserverTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='native-allocation-review-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.roots = (self.base / 'source', self.base / 'build')
        for root in self.roots:
            root.mkdir()
        self.logs = self.roots[0] / 'observations'
        self.logs.mkdir()
        cgroup = self.base / 'cgroup'
        cgroup.mkdir()
        (cgroup / 'cgroup.procs').write_text('')
        self.records = []
        self.result = {'driver': {}, 'owned_allocation_before_bytes': 100, 'build_success': False}
        self.observed = {'next_space_check': float('inf'), 'next_sample': 0,
                         'next_usage_check': 0, 'source_input_observation': None,
                         'samples': [], 'seen': set(), 'work_growth_peak_bytes': 0,
                         'soong_generations': {}}
        self.namespace = {
            'Path': Path, 'os': os, 'stat': stat, 'subprocess': subprocess,
            'time': time, 'resource': resource, 'tempfile': tempfile,
            's': types.SimpleNamespace(need=need, PROFILE={'initial_build_work_budget_bytes': 96 * 1024**3}),
            'RESULT': self.logs, 'ROOT': self.roots[0], 'OUTPUT_ROOT': self.roots[1],
            'OUT': self.roots[1], 'cgroup': cgroup, 'observed': self.observed,
            'result': self.result, 'record_allocation_attempt': self.records.append,
            'allocation_admission': lambda: None,
        }
        self.tree = load_functions(SOURCE, self.namespace)
        self.observe = self.namespace['observe_owned_allocation']
        self.parse = self.namespace['parse_owned_allocation']

    def output(self, a=100, b=200, roots=None):
        roots = roots or self.roots
        return b''.join(str(n).encode() + b'\t' + os.fsencode(root) + b'\0' for n, root in zip((a, b), roots))

    def run_observer(self, responses, admission=lambda: None):
        runner = FakeDu(responses)
        with patch.object(subprocess, 'run', runner):
            value = self.observe(self.roots, self.records.append, admission)
        return value, runner

    def test_real_gnu_du_two_sibling_roots_and_hardlinks(self):
        (self.roots[0] / 'payload').write_bytes(b'x' * 8192)
        os.link(self.roots[0] / 'payload', self.roots[1] / 'same-payload')
        raw = subprocess.run(['/usr/bin/du', '-sx', '--block-size=1', '--null', '--', *map(str, self.roots)],
                             capture_output=True, check=True).stdout
        old_limit = resource.getrlimit(resource.RLIMIT_FSIZE)
        actual = self.observe(self.roots, self.records.append, lambda: None)
        self.assertEqual(actual, self.parse(raw, self.roots))
        self.assertEqual(resource.getrlimit(resource.RLIMIT_FSIZE), old_limit)
        self.assertTrue(self.records[0]['sample_complete'])
        self.assertEqual(bytes.fromhex(self.records[0]['stderr_hex']), b'')

    def test_original_monitor_fails_first_rc_one_without_diagnostics(self):
        ns = dict(self.namespace)
        load_functions(ORIGINAL, ns)
        runner = FakeDu([(1, b'partial', b'du: vanished entry\n')])
        with patch.object(subprocess, 'run', runner), self.assertRaisesRegex(RuntimeError, 'allocation observation failed'):
            ns['monitor']({})
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(self.records, [])

    def test_same_transient_fixture_recovers_only_after_complete_zero_exit(self):
        runner = FakeDu([(1, b'partial', b'du: vanished entry\n'), (0, self.output(), b'')])
        with patch.object(subprocess, 'run', runner):
            self.namespace['monitor']({})
        self.assertEqual(len(runner.calls), 2)
        self.assertEqual([r['sample_complete'] for r in self.records], [False, True])
        self.assertEqual(bytes.fromhex(self.records[0]['stderr_hex']), b'du: vanished entry\n')
        self.assertEqual(self.observed['work_growth_peak_bytes'], 200)
        self.assertFalse(self.result['build_success'])

    def test_three_permission_failures_never_become_a_sample(self):
        runner = FakeDu([(1, self.output(), b'du: Permission denied\n')] * 3)
        with patch.object(subprocess, 'run', runner), self.assertRaisesRegex(RuntimeError, 'bounded resampling'):
            self.observe(self.roots, self.records.append, lambda: None)
        self.assertEqual(len(runner.calls), 3)
        self.assertTrue(all(r['returncode'] == 1 and not r['sample_complete'] for r in self.records))

    def test_non_retryable_exit_two_retains_io_diagnostic(self):
        runner = FakeDu([(2, b'', b'I/O error\xff')])
        with patch.object(subprocess, 'run', runner), self.assertRaises(RuntimeError):
            self.observe(self.roots, self.records.append, lambda: None)
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(bytes.fromhex(self.records[0]['stderr_hex']), b'I/O error\xff')

    def test_timeout_preserves_partial_streams_and_is_not_retried(self):
        runner = FakeDu([('timeout', b'partial stdout', b'partial stderr')])
        with patch.object(subprocess, 'run', runner), self.assertRaisesRegex(RuntimeError, 'timed out'):
            self.observe(self.roots, self.records.append, lambda: None)
        self.assertEqual(len(runner.calls), 1)
        row = self.records[0]
        self.assertTrue(row['timed_out'])
        self.assertIsNone(row['returncode'])
        self.assertFalse(row['sample_complete'])
        self.assertEqual(bytes.fromhex(row['stdout_hex']), b'partial stdout')
        self.assertEqual(bytes.fromhex(row['stderr_hex']), b'partial stderr')

    def test_one_shared_deadline_decreases_each_attempt(self):
        clock = [10.0]
        def advance(): clock[0] += 9
        runner = FakeDu([(1, b'', b'transient'), (1, b'', b'transient'), (0, self.output(), b'')], advance)
        with patch.object(time, 'monotonic', lambda: clock[0]), patch.object(subprocess, 'run', runner):
            self.assertEqual(self.observe(self.roots, self.records.append, lambda: None), 300)
        self.assertEqual([timeout for _, timeout in runner.calls], [30, 21, 12])

    def test_expired_deadline_does_not_launch_another_attempt(self):
        clock = [0.0]
        runner = FakeDu([(1, b'', b'transient')], lambda: clock.__setitem__(0, 30.0))
        with patch.object(time, 'monotonic', lambda: clock[0]), patch.object(subprocess, 'run', runner), self.assertRaises(RuntimeError):
            self.observe(self.roots, self.records.append, lambda: None)
        self.assertEqual(len(runner.calls), 1)

    def test_late_success_before_or_after_recording_is_not_admitted(self):
        for phase in ['du', 'record']:
            with self.subTest(phase=phase):
                clock = [0.0]; records = []
                runner = FakeDu([(0, self.output(), b'')],
                                (lambda: clock.__setitem__(0, 31.0)) if phase == 'du' else None)
                def record(row):
                    records.append(row)
                    if phase == 'record': clock[0] = 31.0
                with patch.object(time, 'monotonic', lambda: clock[0]), patch.object(subprocess, 'run', runner), self.assertRaisesRegex(RuntimeError, 'deadline'):
                    self.observe(self.roots, record, lambda: None)
                self.assertEqual(len(records), 1)
                self.assertTrue(records[0]['sample_complete'])

    def test_success_refreshes_admission_after_recording(self):
        events = []
        runner = FakeDu([(0, self.output(), b'')], lambda: events.append('du'))
        def admission():
            events.append('admission')
            need(events.count('admission') == 1, 'shared reserve changed')
        def record(row):
            events.append('record'); self.records.append(row)
        with patch.object(subprocess, 'run', runner), self.assertRaisesRegex(RuntimeError, 'reserve changed'):
            self.observe(self.roots, record, admission)
        self.assertEqual(events, ['admission', 'du', 'record', 'admission'])
        self.assertTrue(self.records[-1]['sample_complete'])

    def test_admission_elapsed_time_cannot_extend_shared_deadline(self):
        clock = [0.0]; calls = []
        runner = FakeDu([(0, self.output(), b'')])
        def admission():
            calls.append(None)
            if len(calls) == 2: clock[0] = 31.0
        with patch.object(time, 'monotonic', lambda: clock[0]), patch.object(subprocess, 'run', runner), self.assertRaisesRegex(RuntimeError, 'deadline'):
            self.observe(self.roots, self.records.append, admission)
        self.assertEqual(len(calls), 2)

    def test_admission_or_cancellation_is_checked_between_attempts(self):
        calls = []
        def admission():
            calls.append(None)
            need(len(calls) == 1, 'cancelled or reserve crossed')
        runner = FakeDu([(1, b'', b'transient')])
        with patch.object(subprocess, 'run', runner), self.assertRaisesRegex(RuntimeError, 'reserve'):
            self.observe(self.roots, self.records.append, admission)
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(len(self.records), 1)

    def test_invalid_success_outputs_fail_closed(self):
        first = os.fsencode(self.roots[0]); second = os.fsencode(self.roots[1])
        cases = [b'', b'1\t' + first + b'\0', self.output()[:-1],
                 b'1\t' + first + b'\0' + b'2\t' + first + b'\0',
                 b'x\t' + first + b'\0' + b'2\t' + second + b'\0',
                 b'-1\t' + first + b'\0' + b'2\t' + second + b'\0',
                 b'+1\t' + first + b'\0' + b'2\t' + second + b'\0',
                 self.output(roots=(self.roots[0], self.base / 'other')),
                 self.output() + b'3\tother\0', b'1  ' + first + b'\0' + b'2\t' + second + b'\0']
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                self.parse(raw, self.roots)

    def test_zero_exit_with_stderr_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'emitted diagnostics'):
            self.run_observer([(0, self.output(), b'warning')])
        self.assertFalse(self.records[-1]['sample_complete'])

    def test_missing_root_never_launches_du(self):
        self.roots[1].rmdir()
        with patch.object(subprocess, 'run') as run, self.assertRaises(FileNotFoundError):
            self.observe(self.roots, self.records.append, lambda: None)
        run.assert_not_called()

    def test_duplicate_nested_relative_and_symlink_roots_are_rejected(self):
        link = self.base / 'alias'; link.symlink_to(self.roots[0], target_is_directory=True)
        for roots in [(self.roots[0], self.roots[0]), (self.roots[0], self.logs),
                      (Path('relative'), self.roots[1]), (link, self.roots[1])]:
            with self.subTest(roots=roots), patch.object(subprocess, 'run') as run, self.assertRaises(RuntimeError):
                self.observe(roots, self.records.append, lambda: None)
            run.assert_not_called()

    def test_replaced_root_is_rejected_even_with_complete_zero_exit(self):
        runner = FakeDu([(0, self.output(), b'')])
        def replace(argv, **kwargs):
            completed = runner(argv, **kwargs)
            self.roots[1].rename(self.base / 'old-build')
            self.roots[1].mkdir()
            return completed
        with patch.object(subprocess, 'run', replace), self.assertRaisesRegex(RuntimeError, 'identity changed'):
            self.observe(self.roots, self.records.append, lambda: None)
        self.assertFalse(self.records[-1]['sample_complete'])

    def test_log_limit_is_kernel_enforced_and_parent_limit_is_unchanged(self):
        actual_run = subprocess.run
        old_limit = resource.getrlimit(resource.RLIMIT_FSIZE)
        def overflowing_child(argv, **kwargs):
            return actual_run([sys.executable, '-c', 'import os; os.write(2, b"x" * 1048576); os.write(2, b"x")'], **kwargs)
        with patch.object(subprocess, 'run', overflowing_child), self.assertRaisesRegex(RuntimeError, 'log bound'):
            self.observe(self.roots, self.records.append, lambda: None)
        self.assertEqual(resource.getrlimit(resource.RLIMIT_FSIZE), old_limit)
        self.assertEqual(len(self.records), 1)
        self.assertEqual(self.records[0]['stderr_bytes'], 65536)
        self.assertFalse(self.records[0]['sample_complete'])

    def test_actual_monitor_retains_strict_96_gib_boundary(self):
        limit = 96 * 1024**3
        for growth in [limit - 1, limit, limit + 1]:
            with self.subTest(growth=growth):
                self.observed['next_sample'] = 0; self.observed['next_usage_check'] = 0
                runner = FakeDu([(0, self.output(100, growth), b'')])
                with patch.object(subprocess, 'run', runner):
                    if growth < limit:
                        self.namespace['monitor']({})
                    else:
                        with self.assertRaisesRegex(RuntimeError, '96 GiB'):
                            self.namespace['monitor']({})
                self.assertFalse(self.result['build_success'])

    def test_actual_baseline_and_terminal_assignments_use_same_strict_parser(self):
        assignments = [node for node in ast.walk(self.tree) if isinstance(node, ast.Assign)
                       and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
                       and node.value.func.id == 'parse_owned_allocation']
        self.assertEqual(len(assignments), 3)  # helper, before, after
        assignments = [node for node in assignments if node.value.args and isinstance(node.value.args[0], ast.Call)]
        self.assertEqual(len(assignments), 2)
        for node in assignments:
            for raw in [b'', b'7\t' + os.fsencode(self.roots[0]) + b'\0', self.output()]:
                ns = dict(self.namespace, allocation={'stdout': raw}, small_stdout=lambda row: row['stdout'])
                code = compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), 'exec')
                if raw == self.output():
                    exec(code, ns)
                else:
                    with self.assertRaises(RuntimeError): exec(code, ns)


if __name__ == '__main__':
    print('NATIVE_OBSERVER_TEST_OPTIMIZE=' + str(sys.flags.optimize), flush=True)
    unittest.main(verbosity=2)
