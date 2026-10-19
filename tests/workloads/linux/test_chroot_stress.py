"""Selection / evidence-guard tests only; actual full chroot stress is separate."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('a04_chroot_stress',HERE/'chroot_stress.py')
stress=importlib.util.module_from_spec(spec)
spec.loader.exec_module(stress)


class AppStressGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ref=json.loads((HERE/'baselines/linux-debian13-x86_64.json').read_text())

    def test_required_actual_workloads_not_only_syscall_count(self):
        items=stress.selected_cases(self.ref)
        self.assertEqual(len(items),18)
        self.assertEqual(len(set(x[0] for x in items)),18)
        self.assertTrue(any(x[0]=='sqlite_dynamic.sqlite_wal_elf' for x in items))
        self.assertTrue(any(x[0]=='static.robust_owner_death' for x in items))
        self.assertTrue(any(x[0]=='dynamic.uds_peercred' for x in items))

    def test_missing_or_unverified_reference_fails_closed(self):
        for case in ('sqlite_static.sqlite_wal_elf','static.threads_futex','dynamic.uds_peercred'):
            ref=copy.deepcopy(self.ref)
            ref['cases'][case]['status']='not_run'
            with self.assertRaises(ValueError):
                stress.selected_cases(ref)
            ref=copy.deepcopy(self.ref)
            del ref['cases'][case]
            with self.assertRaises(ValueError):
                stress.selected_cases(ref)

    def test_run_case_delegates_bounded_descendant_cleanup(self):
        sentinel = {'exit_code': 0, 'stdout': '{"ok":true}\n', 'stderr': '',
                    'timed_out': False, 'cleanup_incomplete': False}
        with patch.object(stress.chroot, 'bounded_run', return_value=sentinel) as mock:
            actual = stress.run_case(['/usr/local/bin/a04/probe_static', 'smoke'],
                                     root=Path('/discarded'), scratch='/tmp/a04/test', timeout=2)
        self.assertEqual(actual, sentinel)
        self.assertEqual(mock.call_count, 1)
        self.assertEqual(mock.call_args.kwargs['timeout'], 2)

    def test_round_and_timeout_bounds(self):
        with self.assertRaises(ValueError):
            stress.run(Path('/tmp/none'),Path('/tmp/none'),self.ref,rounds=0)
        with self.assertRaises(ValueError):
            stress.run(Path('/tmp/none'),Path('/tmp/none'),self.ref,rounds=41)
        with self.assertRaises(ValueError):
            stress.run(Path('/tmp/none'),Path('/tmp/none'),self.ref,timeout=31)


if __name__=='__main__':
    unittest.main()
