"""Actual Linux ptrace observations + negative evidence-format tests."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("a04_ptrace_probe", HERE / "ptrace_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class TraceEvidence(unittest.TestCase):
    def test_nonexistent_or_empty_trace_never_qualifies(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "raw.jsonl"
            with self.assertRaises(ValueError):
                probe.inspect_trace(target)
            target.write_text("")
            with self.assertRaises(ValueError):
                probe.inspect_trace(target)

    def test_parse_numeric_syscalls_and_internal_restart_separately(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "raw.jsonl"
            rows = [
                {"kind":"syscall","tid":42,"nr":202,"errno":11,"internal_restart":0},
                {"kind":"syscall","tid":42,"nr":61,"errno":0,"internal_restart":512},
                {"kind":"exit","tid":42,"code":0},
            ]
            target.write_text("\n".join(json.dumps(x) for x in rows)+"\n")
            report = probe.inspect_trace(target)
            self.assertEqual(report["syscall_events"], 2)
            self.assertEqual(report["syscall_errno"][(202, 11)], 1)
            self.assertEqual(report["internal_restarts"][(61, 512)], 1)
            self.assertNotIn((61, 512), report["syscall_errno"])
            self.assertEqual(report["process_or_thread_exits"], 1)

    def test_invalid_trace_or_fake_errno_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "raw.jsonl"
            fixtures = [
                [{"kind":"syscall","tid":1,"nr":1,"errno":0}],
                [{"kind":"syscall","tid":1,"nr":1,"errno":512},
                 {"kind":"exit","tid":1,"code":0}],
                [{"kind":"syscall","tid":1,"nr":1,"errno":11,"internal_restart":512},
                 {"kind":"exit","tid":1,"code":0}],
                [{"kind":"syscall","tid":1,"nr":1,"errno":0,"internal_restart":999},
                 {"kind":"exit","tid":1,"code":0}],
                [{"kind":"exit","tid":1,"code":0}],
                [{"kind":"syscall","tid":"forged","nr":1,"errno":0},
                 {"kind":"exit","tid":1,"code":0}],
                [{"kind":"garbage","tid":1}],
            ]
            for rows in fixtures:
                with self.subTest(rows=rows):
                    target.write_text("\n".join(json.dumps(x) for x in rows)+"\n")
                    with self.assertRaises(ValueError):
                        probe.inspect_trace(target)

    def test_actual_ptrace_child_syscalls_if_kernel_allows_it(self):
        with tempfile.TemporaryDirectory() as td:
            exe, raw = Path(td)/"a04-ptrace", Path(td)/"raw.jsonl"
            try:
                sha = probe.compile_tracer(exe)
            except (FileNotFoundError, RuntimeError) as exc:
                self.skipTest("GCC not available: "+str(exc))
            self.assertEqual(len(sha), 64)
            result = subprocess.run([exe, raw, "--", "/bin/true"], timeout=10,
                                    capture_output=True, text=True)
            if result.returncode != 0 and ("PTRACE_" in result.stderr or
                                           "Operation not permitted" in result.stderr or
                                           "initial PTRACE stop" in result.stderr):
                self.skipTest("kernel ptrace policy denies tracing")
            self.assertEqual(result.returncode, 0, result.stderr)
            report = probe.inspect_trace(raw)
            self.assertGreater(report["syscall_events"], 10)
            self.assertEqual(report["process_or_thread_exits"], 1)
            self.assertIn(12, report["syscalls"])  # brk ELF runtime on x86_64


    def test_real_sigtrap_handler_is_not_swallowed_by_tracer(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src, exe = root / "sigtrap.c", root / "sigtrap"
            src.write_text("""#include <signal.h>
static volatile sig_atomic_t got;
static void ontrap(int signum) { (void)signum; got=1; }
int main(void) { struct sigaction a={0}; a.sa_handler=ontrap;
  if (sigaction(SIGTRAP,&a,0)!=0) return 9;
  raise(SIGTRAP); return got ? 0 : 7; }
""")
            compile_result = subprocess.run(["gcc", "-std=c11", "-D_POSIX_C_SOURCE=200809L",
                                             "-Wall", "-Wextra", "-Werror", str(src),
                                             "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            tracer = root / "trace-exe"
            probe.compile_tracer(tracer)
            result = subprocess.run([tracer, root / "trace.jsonl", "--", exe],
                                    timeout=10, capture_output=True, text=True)
            if result.returncode != 0 and ("PTRACE_" in result.stderr or
                                           "Operation not permitted" in result.stderr or
                                           "initial PTRACE stop" in result.stderr):
                self.skipTest("kernel ptrace policy denies tracing")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertGreater(probe.inspect_trace(root / "trace.jsonl")["syscall_events"], 10)


if __name__ == "__main__":
    unittest.main()
