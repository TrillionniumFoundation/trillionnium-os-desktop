"""Synthetic Asterinas source fixtures; unit results are NOT kernel runtime evidence."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

FILE = Path(__file__).resolve().parents[3] / 'support/android/kernel_contract.py'
spec = importlib.util.spec_from_file_location('kernel_contract', FILE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class KernelContractTests(unittest.TestCase):
    def make_tree(self, directory, *, binder=False, seccomp=False, mac=False):
        root = Path(directory) / 'asterinas'
        lock = Path(directory) / 'upstream-lock.json'
        lock.write_text(json.dumps({'kernel': {'commit': mod.PIN, 'tag': mod.TAG,
                                               'reuse': 'full_kernel_derived'}}))
        src = root / mod.BASE
        sources = ['mod ' + s + ';' for s in mod.ENTRYPOINTS]
        (src / 'syscall').mkdir(parents=True)
        (src / 'syscall/mod.rs').write_text('\n'.join(sources) +
                                            ('\nmod seccomp;' if seccomp else ''))
        for name, rel in mod.ENTRYPOINTS.items():
            path = src / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('pub(super) fn sys_' + name + '() {}\n')
        (src / 'syscall/prctl.rs').write_text('pub(super) fn sys_prctl() {}\n')
        if seccomp:
            (src / 'syscall/seccomp.rs').write_text('pub(super) fn sys_seccomp() {}\n')
        if binder:
            (src / 'device').mkdir()
            (src / 'device/binder.rs').write_text('fn binder_ioctl() { let v = BINDER_WRITE_READ; }\n')
        (src / 'security/lsm/modules').mkdir(parents=True)
        (src / 'security/lsm/modules/mod.rs').write_text(
            'static ALL_MODULES: [&str; 1] = [&selinux::SELINUX_LSM];\n' if mac else
            'static ALL_MODULES: [&str; 1] = [&yama::YAMA_LSM];\n')
        if mac:
            (src / 'security/lsm/modules/selinux.rs').write_text('pub const SELINUX_LSM: u8 = 1;\n')
        (src / 'fs/fs_impls/cgroupfs/controller').mkdir(parents=True)
        (src / 'fs/fs_impls/cgroupfs/controller/memory.rs').write_text('struct MemoryController;')
        return root, lock

    def test_fixed_kernel_sources_report_three_real_blockers(self):
        with tempfile.TemporaryDirectory() as td:
            root, lock = self.make_tree(td)
            result = mod.scan(root, lock)
            self.assertEqual(result['status'], 'source_review_blocked')
            self.assertEqual(result['blocking_requirements'], ['binder', 'seccomp', 'mac'])
            self.assertFalse(result['android_compatible'])
            self.assertFalse(result['runtime_verified'])
            self.assertEqual(result['checks']['futex']['status'], 'source_entrypoint_only')
            self.assertEqual(result['checks']['lmkd_pressure']['status'], 'source_candidates_only')
            self.assertIn('sha256', result['source_files']['kernel/core/src/syscall/futex.rs'])

    def test_candidate_sources_still_not_runtime_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root, lock = self.make_tree(td, binder=True, seccomp=True, mac=True)
            result = mod.scan(root, lock)
            self.assertEqual(result['status'], 'source_candidates_unverified')
            self.assertEqual(result['blocking_requirements'], [])
            self.assertFalse(result['android_compatible'])
            self.assertFalse(result['runtime_verified'])
            self.assertFalse(result['checks']['binder']['transactions_verified'])
            self.assertFalse(result['checks']['seccomp']['tsync_verified'])
            self.assertFalse(result['checks']['mac']['negative_mac_tests_passed'])

    def test_absent_sources_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root, lock = self.make_tree(td)
            (root / mod.BASE / 'syscall/futex.rs').unlink()
            result = mod.scan(root, lock)
            self.assertEqual(result['status'], 'missing_core_sources')
            self.assertIn('source_syscall_coverage', result['blocking_requirements'])
            self.assertIn('kernel/core/src/syscall/futex.rs', result['missing_source_paths'])

    def test_wrong_kernel_pin_fails_before_scan(self):
        with tempfile.TemporaryDirectory() as td:
            root, lock = self.make_tree(td)
            lock.write_text(json.dumps({'kernel': {'tag': mod.TAG, 'commit': '0' * 40,
                                                   'reuse': 'full_kernel_derived'}}))
            result = mod.scan(root, lock)
            self.assertEqual(result['status'], 'lock_mismatch')
            self.assertEqual(result['blocking_requirements'], ['pinned_lock'])

    def test_kernel_lock_absent(self):
        with tempfile.TemporaryDirectory() as td:
            root, lock = self.make_tree(td)
            lock.unlink()
            self.assertEqual(mod.scan(root, lock)['status'], 'lock_unavailable')

    def test_comments_without_implementation_not_success(self):
        with tempfile.TemporaryDirectory() as td:
            root, lock = self.make_tree(td)
            (root / mod.BASE / 'syscall/futex.rs').write_text('// pub fn sys_futex() {}\n')
            result = mod.scan(root, lock)
            self.assertEqual(result['checks']['futex']['status'], 'missing_or_unregistered')

    def test_cli_red_gate_and_json_output(self):
        with tempfile.TemporaryDirectory() as td:
            root, lock = self.make_tree(td)
            output = Path(td) / 'evidence/report.json'
            self.assertEqual(mod.main(['--kernel-root', str(root), '--lock', str(lock),
                                       '--out', str(output)]), 2)
            self.assertEqual(json.loads(output.read_text())['status'], 'source_review_blocked')

    def test_cli_bad_lock_exit_three(self):
        with tempfile.TemporaryDirectory() as td:
            root, lock = self.make_tree(td)
            self.assertEqual(mod.main(['--kernel-root', str(root),
                                       '--lock', str(lock) + '-nope',
                                       '--out', str(Path(td) / 'report.json')]), 3)


if __name__ == '__main__':
    unittest.main()
