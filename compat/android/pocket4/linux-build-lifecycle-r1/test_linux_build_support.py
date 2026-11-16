import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('support_test', HERE / 'linux_build_support.py')
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)


HAVE_LINUX_OWNERSHIP = (sys.platform == 'linux' and hasattr(os, 'pidfd_open')
    and Path('/proc/self/task/' + str(os.getpid()) + '/children').exists())


class DesktopControls(unittest.TestCase):
    def test_new_profile_keeps_distinct_cpu_and_go_budgets(self):
        profile = s.validate_profile(copy.deepcopy(s.PROFILE))
        self.assertEqual(profile['cpu_affinity'], list(range(8)))
        self.assertEqual(profile['go_max_procs'], 2)
        self.assertEqual(profile['fresh_memavailable_minimum_bytes'], 29 * 1024**3)
        self.assertEqual(profile['fresh_disk_minimum_bytes'], 78 * 1024**3)

    def test_resource_integer_fields_reject_boolean_or_float(self):
        for key, value in s.PROFILE.items():
            if type(value) is not int:
                continue
            for bad in (True, float(value)):
                with self.subTest(key=key, bad=bad), self.assertRaises(RuntimeError):
                    row = copy.deepcopy(s.PROFILE); row[key] = bad; s.validate_profile(row)

    def test_cpu_affinity_strict_integer_and_full_profile(self):
        for bad in ([False, 1, 2, 3, 4, 5, 6, 7], list(range(7)), tuple(range(8))):
            with self.subTest(bad=bad), self.assertRaises(RuntimeError):
                row = copy.deepcopy(s.PROFILE); row['cpu_affinity'] = bad; s.validate_profile(row)

    def test_old_profile_cannot_be_relabelled_as_new(self):
        row = copy.deepcopy(s.PROFILE); row['build_memory_max_bytes'] = 8 * 1024**3
        with self.assertRaises(RuntimeError):
            s.validate_profile(row)

    def test_file_witness_rejects_symlink_and_changed_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'data'; p.write_bytes(b'actual')
            ref = s.file_ref(p); s.pinned(ref)
            p.write_bytes(b'changed')
            with self.assertRaises(RuntimeError):
                s.pinned(ref)
            link = Path(directory) / 'alias'; link.symlink_to(p)
            with self.assertRaises(OSError):
                s.file_ref(link)

    def test_evidence_is_create_only(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'result'; s.create(p, {'ok': True})
            with self.assertRaises(FileExistsError):
                s.create(p, {'ok': False})
            self.assertEqual(json.loads(p.read_text()), {'ok': True})

    @unittest.skipUnless(HAVE_LINUX_OWNERSHIP, 'requires real Linux pidfd, waitid, subreaper, and /proc children')
    def test_actual_successful_child_is_observed_before_reap_and_retired(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = s.OwnedCommands(Path(directory) / 'commands', HERE)
            row = runner.run('normal', [sys.executable, '-I', '-B', '-c', "print('complete')"], 5)
            self.assertEqual(row['lifecycle']['returncode'], 0)
            self.assertTrue(row['owned_retirement_complete'])
            self.assertEqual(row['observed_before_reap']['code'], os.CLD_EXITED)
            self.assertTrue(row['reaper']['restored'])
            self.assertTrue(row['lifecycle']['pidfd_closed'])

    @unittest.skipUnless(HAVE_LINUX_OWNERSHIP, 'requires real Linux pidfd, waitid, subreaper, and /proc children')
    def test_actual_failed_child_is_retired_without_success(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = s.OwnedCommands(Path(directory) / 'commands', HERE)
            with self.assertRaises(RuntimeError):
                runner.run('failed', [sys.executable, '-I', '-B', '-c', 'raise SystemExit(7)'], 5)
            row = runner.records[0]
            self.assertEqual(row['lifecycle']['returncode'], 7)
            self.assertTrue(row['owned_retirement_complete'])
            self.assertTrue(row['errors'])

    @unittest.skipUnless(HAVE_LINUX_OWNERSHIP, 'requires real Linux pidfd, waitid, subreaper, and /proc children')
    def test_timeout_retires_actual_owned_process_group(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = s.OwnedCommands(Path(directory) / 'commands', HERE)
            with self.assertRaises(RuntimeError):
                runner.run('deadline', [sys.executable, '-I', '-B', '-c', 'import time; time.sleep(30)'], 1)
            row = runner.records[0]
            self.assertTrue(row['owned_retirement_complete'])
            self.assertEqual(row['lifecycle']['remaining_owned_children'], [])
            self.assertTrue(row['lifecycle']['owned_group_kill_completed'])


if __name__ == '__main__':
    unittest.main()
