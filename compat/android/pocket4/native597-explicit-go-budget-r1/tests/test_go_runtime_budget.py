import unittest
import importlib.util
from pathlib import Path

_module_path = Path(__file__).resolve().parents[1] / "source/go_runtime_budget.py"
_spec = importlib.util.spec_from_file_location("native_go_runtime_budget", _module_path)
_module = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_module)
qualify_runtime_budget = _module.qualify_runtime_budget


def marker(phase, pid=41, procs=2, memory=5 * 1024**3, gc=50):
    return ('DROIDLOOM_GO_BUDGET phase=%s pid=%s gomaxprocs=%s gomemlimit_bytes=%s gogc_percent=%s\n'
            % (phase, pid, procs, memory, gc)).encode()


class RuntimeBudgetTests(unittest.TestCase):
    def check(self, lines, pids={41}):
        return qualify_runtime_budget([('stdout', iter(lines)), ('stderr', iter([]))], pids)

    def test_actual_pair_forwarded_by_ninja(self):
        result = self.check([b'[1/2] original Soong\n', marker('enter'), marker('leave')])
        self.assertEqual(result['matching_observed_pids'], [41])
        self.assertFalse(result['continuous_runtime_sampling'])

    def test_environment_is_not_actual_metric(self):
        with self.assertRaises(ValueError): self.check([b'GOMAXPROCS=2 GOMEMLIMIT=5GiB GOGC=50\n'])

    def test_actual_upstream_eight_cpu_override_rejected(self):
        with self.assertRaises(ValueError): self.check([marker('enter', procs=8), marker('leave', procs=8)])

    def test_budget_reset_after_entry_rejected(self):
        with self.assertRaises(ValueError): self.check([marker('enter'), marker('leave', memory=2**63-1)])

    def test_exit_without_entry_rejected(self):
        with self.assertRaises(ValueError): self.check([marker('leave'), marker('enter')])

    def test_incomplete_or_duplicate_entry_rejected(self):
        for lines in ([marker('enter')], [marker('enter'), marker('enter'), marker('leave')]):
            with self.subTest(lines=lines), self.assertRaises(ValueError): self.check(lines)

    def test_unobserved_or_bool_pid_rejected(self):
        for pids in ({42}, {True}):
            with self.subTest(pids=pids), self.assertRaises(ValueError): self.check([marker('enter'), marker('leave')], pids)

    def test_malformed_marker_and_disabled_gc_rejected(self):
        for lines in ([b'prefix ' + marker('enter'), marker('leave')], [marker('enter', gc=2**64-1), marker('leave')]):
            with self.subTest(lines=lines), self.assertRaises(ValueError): self.check(lines)


if __name__ == '__main__':
    unittest.main()
