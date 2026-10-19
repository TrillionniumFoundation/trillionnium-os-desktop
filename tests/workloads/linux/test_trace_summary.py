"""Synthetic trace grammar tests: not a substitute for actual strace evidence."""
import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("a04_trace", HERE.parents[2] / "compat/linux/trace_summary.py")
trace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trace)


class TraceFacts(unittest.TestCase):
    @staticmethod
    def complete_wrapper_evidence(root, status=0):
        # This is a synthetic fixture matching the actual trace-hepta.sh
        # output structure. It never claims that Hepta itself ran here.
        paths = sorted(root.glob('trace.[0-9]*'))
        (root / 'trace-files.sha256').write_text(''.join(
            f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p}\n' for p in paths
        ))
        (root / 'exit-status.txt').write_text(str(status) + '\n')

    def test_empty_trace_does_not_get_reported_as_captured(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                trace.summarize(Path(d))

    def test_empty_pid_log_and_internal_restart_alone_cannot_qualify(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'trace.333').write_text('')
            with self.assertRaisesRegex(ValueError, 'zero completed syscalls'):
                trace.summarize(root)
            (root / 'trace.333').write_text(
                '1771200123.123 futex(0x1000, FUTEX_WAIT_PRIVATE, 0, NULL) = ? ERESTARTSYS (interrupted)\n'
            )
            with self.assertRaisesRegex(ValueError, 'zero completed syscalls'):
                trace.summarize(root)

    def test_errno_per_syscall_and_private_path_split(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "trace.178").write_text(
                '1771200123.123456 openat(AT_FDCWD, "/etc/hosts", O_RDONLY) = 3</etc/hosts>\n'
                '1771200123.123457 openat(AT_FDCWD, "/home/private/config", O_RDONLY) = -1 ENOENT (No such file or directory)\n'
                '1771200123.123458 futex(0x1020, FUTEX_WAKE_PRIVATE, 1) = 0\n'
                '1771200123.123459 execve("/usr/bin/true", ["true"], []) = 0\n'
                '1771200123.123460 +++ exited with 0 +++\n')
            self.complete_wrapper_evidence(root)
            r, paths = trace.summarize(root,include_paths=True)
            self.assertEqual(r['trace_file_count'],1)
            self.assertEqual(r['trace_completeness'], 'complete')
            self.assertEqual(r['trace_files_integrity'], 'verified')
            self.assertEqual(r['strace_wrapper_exit_code'], 0)
            self.assertEqual(r['processes_with_terminal_marker'], 1)
            self.assertEqual(r['processes_missing_terminal_marker'], 0)
            self.assertEqual(r['completed_syscalls'], 4)
            self.assertEqual(r['syscalls']['openat'],2)
            self.assertEqual(r['syscall_errno']['openat:ENOENT'],1)
            self.assertIn('/home/private/config',paths)
            self.assertIn('/etc/hosts',paths)
            self.assertNotIn('/home/private/config',json.dumps(r))
            self.assertFalse(r['hepta_e2e_verified'])
            self.assertFalse(r['tool_execution_verified'])
            safe = root / 'safe.json'
            private = root / 'private.json'
            proc=subprocess.run([sys.executable,str(HERE.parents[2]/'compat/linux/trace_summary.py'),
                                 str(root),'--output',str(safe),'--private-path-output',str(private)],
                                capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertNotIn('/home/private',safe.read_text())
            self.assertIn('/home/private/config',private.read_text())
            self.assertEqual(private.stat().st_mode & 0o777,0o600)
            self.assertEqual(safe.stat().st_mode & 0o777,0o600)
            self.assertNotEqual(subprocess.run([sys.executable,str(HERE.parents[2]/'compat/linux/trace_summary.py'),
                                                str(root),'--output',str(safe)],capture_output=True).returncode,0)


    def test_resumed_errno_path_and_dangling_are_classified_correctly(self):
        # -ff splits by PID and -ttt can split each blocking call into
        # two lines. Count it only when returned, with the *resumed* errno.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "trace.177").write_text(
                '1771200123.100 openat(AT_FDCWD, "/etc/resolv.conf", O_RDONLY <unfinished ...>\n'
                '1771200123.110 <... openat resumed>) = -1 ENOENT (No such file or directory)\n'
                '1771200123.120 futex(0x1000, FUTEX_WAIT_PRIVATE, 0, NULL <unfinished ...>\n'
                '1771200123.130 <... futex resumed>) = ? ERESTARTSYS (To be restarted if SA_RESTART is set)\n'
                '1771200123.140 futex(0x1000, FUTEX_WAIT_PRIVATE, 0, NULL <unfinished ...>\n'
            )
            (root / "trace.178").write_text(
                '1771200124.000 <... poll resumed>) = 0 (Timeout)\n'
                '1771200124.100 close(5) = 0\n'
            )
            report, paths = trace.summarize(root, include_paths=True)
            self.assertEqual(report['syscalls'], {'close': 1, 'openat': 1})
            self.assertEqual(report['syscall_errno'], {'openat:ENOENT': 1})
            self.assertEqual(report['errors'], {'ENOENT': 1})
            self.assertEqual(report['completed_syscalls'], 2)
            self.assertEqual(report['resumed_pairs'], 2)
            self.assertEqual(report['incomplete_syscalls'], 2)
            self.assertEqual(report['orphan_resumptions'], 1)
            self.assertEqual(report['trace_completeness'], 'incomplete')
            self.assertEqual(report['kernel_internal_restarts'], {'futex:ERESTARTSYS': 1})
            self.assertEqual(paths, ['/etc/resolv.conf'])
            self.assertNotIn('/etc/resolv.conf', json.dumps(report))

    def test_pending_mismatch_not_credited_as_completed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'trace.100').write_text(
                '1771200123.100 epoll_wait(3, [], 1, 3000 <unfinished ...>\n'
                '1771200123.110 read(4, "OK", 2) = 2\n'
                '1771200123.120 <... epoll_wait resumed>) = 0 (Timeout)\n'
            )
            report, paths = trace.summarize(root)
            self.assertEqual(report['syscalls'], {'read': 1})
            self.assertEqual(report['incomplete_syscalls'], 1)
            self.assertEqual(report['orphan_resumptions'], 1)
            self.assertEqual(report['trace_completeness'], 'incomplete')
            self.assertFalse(report['hepta_e2e_verified'])


    def test_cli_persists_partial_report_but_returns_failure(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'trace.431').write_text(
                '1771200123.120 openat(AT_FDCWD, "/tmp/scratch", O_RDONLY) = 3\n')
            self.complete_wrapper_evidence(root, status=124)
            output = root/'public-aggregate.json'
            process = subprocess.run([sys.executable, str(HERE.parents[2]/'compat/linux/trace_summary.py'),
                                      str(root), '--output', str(output)],
                                     capture_output=True, text=True, timeout=15)
            self.assertEqual(process.returncode, 3)
            self.assertTrue(output.exists())
            report = json.loads(output.read_text())
            self.assertEqual(report['trace_completeness'], 'incomplete')
            self.assertFalse(report['hepta_e2e_verified'])
            self.assertNotIn('/tmp/scratch', output.read_text())
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    def test_truncated_trace_with_completed_execve_is_incomplete(self):
        # Original parser claimed complete after a single successful execve
        # even though there was no trace of the process ever exiting.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'trace.431').write_text(
                '1771200123.123 execve("/tmp/sandboxed-test", ["test"], []) = 0\n')
            self.complete_wrapper_evidence(root)
            r, _ = trace.summarize(root)
            self.assertEqual(r['syscalls'], {'execve': 1})
            self.assertEqual(r['trace_completeness'], 'incomplete')
            self.assertEqual(r['processes_missing_terminal_marker'], 1)
            self.assertEqual(r['trace_files_integrity'], 'verified')
            self.assertFalse(r['hepta_e2e_verified'])

    def test_missing_tampered_or_duplicate_manifest_never_qualifies(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pid = root / 'trace.431'
            pid.write_text('1771200123.123 close(3) = 0\n'
                           '1771200123.124 +++ exited with 0 +++\n')
            r, _ = trace.summarize(root)
            self.assertEqual(r['trace_files_integrity'], 'missing')
            self.assertEqual(r['trace_completeness'], 'incomplete')
            self.complete_wrapper_evidence(root)
            r, _ = trace.summarize(root)
            self.assertEqual(r['trace_completeness'], 'complete')
            pid.write_text(pid.read_text() + '1771200123.125 write(1, "x", 1) = 1\n')
            r, _ = trace.summarize(root)
            self.assertEqual(r['trace_files_integrity'], 'mismatch')
            self.assertEqual(r['trace_completeness'], 'incomplete')
            self.assertGreater(r['unrecognized_trace_lines'], 0)
            self.complete_wrapper_evidence(root)
            record = (root/'trace-files.sha256').read_text()
            (root/'trace-files.sha256').write_text(record + record)
            r, _ = trace.summarize(root)
            self.assertEqual(r['trace_files_integrity'], 'mismatch')
            self.assertEqual(r['trace_completeness'], 'incomplete')

    def test_timeout_or_killed_pid_marks_partial_session(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pid = root/'trace.921'
            pid.write_text('1771200123.120 futex(0x1, FUTEX_WAKE, 1) = 0\n'
                           '1771200123.130 +++ exited with 0 +++\n')
            self.complete_wrapper_evidence(root, status=124)
            r, _ = trace.summarize(root)
            self.assertEqual(r['strace_wrapper_exit_code'], 124)
            self.assertEqual(r['trace_completeness'], 'incomplete')
            pid.write_text('1771200123.120 futex(0x1, FUTEX_WAKE, 1) = 0\n'
                           '1771200123.130 +++ killed by SIGTERM +++\n')
            self.complete_wrapper_evidence(root, status=0)
            r, _ = trace.summarize(root)
            self.assertEqual(r['process_signal_termination_counts'], {'SIGTERM': 1})
            self.assertEqual(r['trace_completeness'], 'incomplete')

    def test_timestamped_signal_delivery_in_complete_log(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'trace.4').write_text(
                '1771200123.001 rt_sigaction(SIGUSR1, {}, NULL, 8) = 0\n'
                '1771200123.002 --- SIGUSR1 {si_signo=SIGUSR1, si_code=SI_USER} ---\n'
                '1771200123.003 write(1, "ok", 2) = 2\n'
                '1771200123.004 +++ exited with 0 +++\n')
            self.complete_wrapper_evidence(root)
            report, _ = trace.summarize(root)
            self.assertEqual(report['trace_completeness'], 'complete')
            self.assertEqual(report['unrecognized_trace_lines'], 0)
            self.assertEqual(report['completed_syscalls'], 2)

    def test_pid_trace_without_wrapper_exit_status_cannot_be_complete(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'trace.1').write_text('1771200123.001 read(3, "x", 1) = 1\n'
                                        '1771200123.002 +++ exited with 0 +++\n')
            self.complete_wrapper_evidence(root)
            (root/'exit-status.txt').unlink()
            r, _ = trace.summarize(root)
            self.assertIsNone(r['strace_wrapper_exit_code'])
            self.assertEqual(r['trace_completeness'], 'incomplete')


if __name__ == '__main__':
    unittest.main()
