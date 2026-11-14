import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import owned_allocation as a


class CompleteAllocationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.left = self.root / 'source'; self.left.mkdir()
        self.right = self.root / 'output'; self.right.mkdir()
        (self.left / 'original').write_bytes(b'a' * 8193)
        os.link(self.left / 'original', self.right / 'same-inode')
        (self.right / 'generated').write_bytes(b'b' * 4097)
        outside = self.root / 'outside'; outside.mkdir()
        (outside / 'not-owned').write_bytes(b'x' * 65536)
        (self.left / 'external-link').symlink_to(outside)
        self.checkpoints = 0

    def tearDown(self):
        self.temp.cleanup()

    def checkpoint(self):
        self.checkpoints += 1

    def observer(self, name='evidence', checkpoint=None):
        observer = a.AllocationObserver((self.left, self.right), self.root / name,
                                        checkpoint or self.checkpoint)
        self.addCleanup(observer.close)
        return observer

    def test_real_du_two_complete_roots_hardlinks_and_no_external_symlink_walk(self):
        expected = subprocess.run(['/usr/bin/du', '-sx', '--block-size=1', str(self.left), str(self.right)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        expected_bytes = sum(int(x.split()[0]) for x in expected.stdout.splitlines())
        observer = self.observer()
        count, ref = observer.observe()
        result = json.loads(Path(ref['path']).read_bytes())
        self.assertEqual(count, expected_bytes)
        self.assertEqual(result['allocated_bytes'], expected_bytes)
        self.assertTrue(result['complete'])
        self.assertFalse(result['partial_output_accepted'])
        self.assertEqual(result['attempts'][0]['returncode'], 0)
        self.assertTrue(result['attempts'][0]['child_reaped'])
        self.assertTrue(result['attempts'][0]['pidfd_closed'])
        self.assertGreater(self.checkpoints, 2)
        self.assertEqual(a.reference(ref['path']), ref)

    def test_decode_rejects_partial_duplicate_extra_negative_and_unterminated(self):
        valid = b'12\t/proc/self/fd/7\0' + b'13\t/proc/self/fd/8\0'
        operands = ['/proc/self/fd/7', '/proc/self/fd/8']
        self.assertEqual(a.decode_complete(valid, operands), [12, 13])
        for bad in (valid[:-1], valid.split(b'\0')[0] + b'\0',
                    valid.replace(b'/fd/8', b'/fd/7'), valid + b'1\tother\0',
                    valid.replace(b'12\t', b'-1\t'), valid.replace(b'13\t', b'true\t')):
            with self.subTest(bad=bad), self.assertRaises(RuntimeError):
                a.decode_complete(bad, operands)

    def test_exact_real_gnu_disappearance_diagnostic_only_allows_retry(self):
        missing = self.left / 'missing'
        result = subprocess.run(['/usr/bin/du', '--summarize', '--', str(missing)],
                                env={'LC_ALL': 'C'}, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 1)
        self.assertTrue(a.retryable_disappearance(result.returncode, result.stderr))
        for code, raw in ((True, result.stderr), (0, result.stderr), (2, result.stderr),
                          (-9, result.stderr), (1, b''),
                          (1, result.stderr + b'/usr/bin/du: Permission denied\n')):
            self.assertFalse(a.retryable_disappearance(code, raw))

    def test_actual_failed_leaf_retains_stderr_argv_and_reap_evidence(self):
        fd = os.open('/usr/bin/du', os.O_RDONLY | os.O_CLOEXEC)
        try:
            args = ['/usr/bin/du', '--summarize', str(self.left / 'missing')]
            row = a.run_leaf(args, fd, (), self.root / 'failed-leaf', time.monotonic() + 5, self.checkpoint)
        finally:
            os.close(fd)
        self.assertEqual(row['argv'], args)
        self.assertEqual(row['returncode'], 1)
        self.assertFalse(row['timed_out'])
        self.assertTrue(row['child_reaped'] and row['pidfd_closed'])
        self.assertIn(b'No such file or directory', Path(row['stderr']['path']).read_bytes())
        self.assertEqual(json.loads(Path(row['record']['path']).read_bytes())['returncode'], 1)

    def test_disappearance_retry_still_requires_actual_complete_success(self):
        observer = self.observer()
        original = a.run_leaf; calls = []
        def first_fails(argv, exe, fds, directory, deadline, checkpoint):
            calls.append(True)
            if len(calls) == 1:
                # The first failure is a real GNU du ENOENT. It must not be accepted.
                return original(['/usr/bin/du', str(self.left / 'missing')], exe, fds,
                                directory, deadline, checkpoint)
            return original(argv, exe, fds, directory, deadline, checkpoint)
        with mock.patch.object(a, 'run_leaf', side_effect=first_fails):
            _, ref = observer.observe()
        result = json.loads(Path(ref['path']).read_bytes())
        self.assertEqual([x['returncode'] for x in result['attempts']], [1, 0])
        self.assertTrue(result['complete'])
        self.assertFalse(result['partial_output_accepted'])

    def test_repeated_real_missing_paths_fail_after_exact_attempt_bound(self):
        observer = self.observer(); original = a.run_leaf
        def missing(argv, exe, fds, directory, deadline, checkpoint):
            return original(['/usr/bin/du', str(self.left / 'missing')], exe, fds,
                            directory, deadline, checkpoint)
        with mock.patch.object(a, 'run_leaf', side_effect=missing), self.assertRaises(RuntimeError):
            observer.observe()
        row = json.loads(Path(observer.records[0]['path']).read_bytes())
        self.assertEqual(len(row['attempts']), 3)
        self.assertFalse(row['complete'])
        self.assertNotIn('allocated_bytes', row)
        self.assertTrue(all(x['child_reaped'] and x['pidfd_closed'] for x in row['attempts']))

    def test_unchanged_root_fd_does_not_excuse_replaced_named_root(self):
        observer = self.observer()
        self.left.rename(self.root / 'moved-source'); self.left.mkdir()
        with self.assertRaises(RuntimeError):
            observer.observe()
        row = json.loads(Path(observer.records[0]['path']).read_bytes())
        self.assertFalse(row['complete']); self.assertEqual(row['attempts'], [])
        self.assertTrue((self.root / 'moved-source/original').is_file())

    def test_symlink_root_and_nested_roots_rejected(self):
        link = self.root / 'source-link'; link.symlink_to(self.left)
        with self.assertRaises(OSError):
            a.AllocationObserver((link, self.right), self.root / 'link-evidence', self.checkpoint)
        with self.assertRaises(RuntimeError):
            a.AllocationObserver((self.root, self.left), self.root / 'nested-evidence', self.checkpoint)

    def test_real_timeout_kills_and_reaps_only_owned_leaf_and_records_timeout(self):
        fd = os.open(sys.executable, os.O_RDONLY | os.O_CLOEXEC)
        try:
            argv = [sys.executable, '-c', 'import time; time.sleep(20)']
            start = time.monotonic()
            row = a.run_leaf(argv, fd, (), self.root / 'timeout-leaf', start + 0.3, self.checkpoint)
        finally:
            os.close(fd)
        self.assertTrue(row['timed_out'])
        self.assertEqual(row['returncode'], -signal.SIGKILL)
        self.assertTrue(row['child_reaped'] and row['pidfd_closed'])
        self.assertLess(time.monotonic() - start, 5)
        with self.assertRaises(ChildProcessError):
            os.waitpid(row['pid'], os.WNOHANG)

    def test_real_checkpoint_failure_during_scan_retires_child_and_preserves_failure(self):
        calls = 0
        def failed_checkpoint():
            nonlocal calls
            calls += 1
            if calls >= 3:
                raise RuntimeError('actual strict reserve predicate rejected fixture')
        fd = os.open(sys.executable, os.O_RDONLY | os.O_CLOEXEC)
        try:
            row = a.run_leaf([sys.executable, '-c', 'import time; time.sleep(20)'], fd, (),
                             self.root / 'reserve-failure', time.monotonic() + 5, failed_checkpoint)
        finally:
            os.close(fd)
        self.assertTrue(row['child_reaped'] and row['pidfd_closed'])
        self.assertEqual(row['returncode'], -signal.SIGKILL)
        self.assertIn('reserve predicate', row['errors'][0]['message'])

    def test_nontransient_nonzero_error_is_not_retried_or_accepted(self):
        observer = self.observer(); original = a.run_leaf
        def bad_command(argv, exe, fds, directory, deadline, checkpoint):
            # An actual GNU du usage error is non-transient and terminal.
            return original(['/usr/bin/du', '--not-a-du-option'], exe, fds, directory, deadline, checkpoint)
        with mock.patch.object(a, 'run_leaf', side_effect=bad_command), self.assertRaises(RuntimeError):
            observer.observe()
        row = json.loads(Path(observer.records[0]['path']).read_bytes())
        self.assertEqual(len(row['attempts']), 1)
        self.assertFalse(row['complete']); self.assertNotIn('allocated_bytes', row)

    def test_deadline_and_root_input_bounds(self):
        for deadline in (True, 0, -1, 31, float('inf'), float('nan')):
            with self.subTest(deadline=deadline), self.assertRaises(RuntimeError):
                a.AllocationObserver((self.left, self.right), self.root / 'invalid',
                                     self.checkpoint, deadline_seconds=deadline)

    def test_reaped_log_cannot_escape_the_final_byte_bound(self):
        fd = os.open(sys.executable, os.O_RDONLY | os.O_CLOEXEC)
        try:
            row = a.run_leaf([sys.executable, '-c', 'import os; os.write(1,b"x"*(5*1024**2))'],
                             fd, (), self.root / 'oversized-output', time.monotonic() + 5, self.checkpoint)
        finally:
            os.close(fd)
        self.assertTrue(row['child_reaped'] and row['pidfd_closed'])
        self.assertTrue(row['errors'])
        self.assertGreater(row['stdout']['bytes'], a.LOG_LIMIT_BYTES)
        self.assertFalse(row['stdout']['qualified_reference'])
        with self.assertRaises(RuntimeError):
            a.reference(row['stdout']['path'])

    def test_same_path_replacement_cannot_match_the_held_executable_bytes(self):
        path = self.root / 'executable-fixture'; path.write_bytes(b'first')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            expected = a.held_reference(fd, path, 1024)
            path.rename(self.root / 'old-executable'); path.write_bytes(b'first')
            with self.assertRaises(RuntimeError):
                a.held_reference(fd, path, 1024)
            self.assertEqual(expected['sha256'], a.reference(path)['sha256'])
        finally:
            os.close(fd)


if __name__ == '__main__':
    unittest.main(verbosity=2)
