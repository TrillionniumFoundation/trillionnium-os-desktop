#!/usr/bin/env python3
"""Check that interleaved kernel output cannot hide a missing or failed test."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    'cpu_owner_negative', Path(__file__).with_name('run_cpu_owner_negative.py'))
NEGATIVE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NEGATIVE)

SERIAL = b'''[ktest runner] running 552 tests in 16 crates\r
running 3 tests in crate "aster-core"\r
test aster_core::one ... \x1b[32mok\x1b[39m\r
test aster_core::two ...ERROR: expected device read failure\r
ERROR: expected device read failure\r
 \x1b[32mok\x1b[39m\r
test aster_core::three ... \x1b[31mFAILED\x1b[39m\r
\r
test result: \x1b[31mFAILED\x1b[39m. 2 passed; 1 failed; 0 filtered out.\r
\r
failures:\r
---- example.rs:1:1 - three ----\r
[caught panic] assertion failed\r
'''


class SerialContract(unittest.TestCase):
    def test_interleaved_output_preserves_every_name_and_outcome(self):
        self.assertEqual(NEGATIVE.test_results(SERIAL), (
            'FAILED', {'aster_core::one': 'ok', 'aster_core::two': 'ok',
                       'aster_core::three': 'FAILED'}))

    def test_green_output_has_the_same_complete_names(self):
        green = SERIAL.replace(b'FAILED', b'ok').replace(
            b'2 passed; 1 failed;', b'3 passed; 0 failed;') + b'[ktest runner] All crates tested.\r\n'
        self.assertEqual(NEGATIVE.test_results(green)[1], {
            'aster_core::one': 'ok', 'aster_core::two': 'ok', 'aster_core::three': 'ok'})

    def test_missing_repeated_and_wrong_crate_names_fail(self):
        for bad in (
            SERIAL.replace(b'test aster_core::one ... \x1b[32mok\x1b[39m\r\n', b''),
            SERIAL.replace(b'aster_core::two', b'aster_core::one'),
            SERIAL.replace(b'aster_core::two', b'ostd::two'),
        ):
            with self.subTest(serial=bad), self.assertRaises(ValueError):
                NEGATIVE.test_results(bad)

    def test_missing_and_ambiguous_outcomes_fail(self):
        for bad in (
            SERIAL.replace(b' \x1b[31mFAILED\x1b[39m\r\n', b'\r\n', 1),
            SERIAL.replace(b'ERROR: expected device read failure\r\n', b' ok\r\n', 1),
            SERIAL.replace(b'test aster_core::two', b'unterminated log\r\ntest aster_core::two'),
        ):
            with self.subTest(serial=bad), self.assertRaises(ValueError):
                NEGATIVE.test_results(bad)

    def test_counts_filter_and_status_cannot_override_real_outcomes(self):
        for bad in (
            SERIAL.replace(b'2 passed; 1 failed;', b'3 passed; 0 failed;'),
            SERIAL.replace(b'0 filtered out.', b'1 filtered out.'),
            SERIAL.replace(b'test result: \x1b[31mFAILED', b'test result: \x1b[31mok'),
        ):
            with self.subTest(serial=bad), self.assertRaises(ValueError):
                NEGATIVE.test_results(bad)

    def test_incomplete_fatal_or_skipped_runs_fail(self):
        for bad in (
            SERIAL.replace(b'[ktest runner] running 552 tests in 16 crates', b''),
            SERIAL + b'\n[ktest runner] All crates tested.\n',
            SERIAL.replace(b'running 3 tests', b'running 4 tests'),
            SERIAL + b'\nrunning 1 tests in crate "ostd"\n',
            SERIAL.replace(b'assertion failed', b'An uncaught panic occurred:'),
            SERIAL.replace(b'assertion failed', b'[skipped: unavailable]'),
        ):
            with self.subTest(serial=bad), self.assertRaises(ValueError):
                NEGATIVE.test_results(bad)


class CheckoutContract(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git('init', '-q', '-b', 'candidate')
        self.git('config', 'user.name', 'Checkout regression')
        self.git('config', 'user.email', 'checkout@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')
        (self.root / 'cpu.rs').write_text('original owner\n')
        self.git('add', 'cpu.rs')
        self.git('commit', '-qm', 'candidate')
        self.head = self.git('rev-parse', 'HEAD')
        self.git('checkout', '--detach', '-q')
        (self.root / 'cpu.rs').write_text('negative owner\n')
        self.git('commit', '-qam', 'negative')
        self.negative = self.git('rev-parse', 'HEAD')
        self.git('checkout', '-q', 'candidate')

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root,
                                       stderr=subprocess.DEVNULL).decode().strip()

    def test_failure_restores_the_original_branch_and_exact_bytes(self):
        with self.assertRaisesRegex(RuntimeError, 'original gate failed'):
            with NEGATIVE.identified_checkout(self.root, self.head, self.negative):
                self.assertEqual(self.git('rev-parse', 'HEAD'), self.negative)
                self.assertEqual((self.root / 'cpu.rs').read_text(), 'negative owner\n')
                raise RuntimeError('original gate failed')
        self.assertEqual(self.git('symbolic-ref', '--short', 'HEAD'), 'candidate')
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.head)
        self.assertEqual((self.root / 'cpu.rs').read_text(), 'original owner\n')
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_detached_candidate_restores_without_moving_a_branch(self):
        self.git('checkout', '--detach', '-q', self.head)
        with NEGATIVE.identified_checkout(self.root, self.head, self.negative):
            self.assertEqual(self.git('rev-parse', 'HEAD'), self.negative)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.head)
        self.assertEqual(self.git('rev-parse', 'candidate'), self.head)
        result = subprocess.run(['git', 'symbolic-ref', '--quiet', 'HEAD'], cwd=self.root)
        self.assertEqual(result.returncode, 1)

    def test_dirty_candidate_is_rejected_without_discarding_work(self):
        (self.root / 'cpu.rs').write_text('unexpected edit\n')
        with self.assertRaises(ValueError):
            with NEGATIVE.identified_checkout(self.root, self.head, self.negative):
                self.fail('dirty checkout was accepted')
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.head)
        self.assertEqual((self.root / 'cpu.rs').read_text(), 'unexpected edit\n')


class OriginalGreenElfContract(unittest.TestCase):
    def test_shared_target_rebuild_requires_the_verified_original_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            target, retained = Path(directory) / 'target.elf', Path(directory) / 'green.elf'
            original = b'original successful kernel bytes'
            target.write_bytes(original)
            record = {'artifacts': {'-kernel': {'path': str(target), 'size': len(original),
                                               'sha256': NEGATIVE.sha(original)}}}
            self.assertEqual(NEGATIVE.checked_green_kernel(record), original)
            retained.write_bytes(NEGATIVE.checked_green_kernel(record))
            target.write_bytes(b'negative kernel rebuilt in the same original OSDK target')
            with self.assertRaises(ValueError):
                NEGATIVE.checked_green_kernel(record)
            self.assertEqual(NEGATIVE.checked_green_kernel(record, retained), original)
            retained.write_bytes(target.read_bytes())
            with self.assertRaises(ValueError):
                NEGATIVE.checked_green_kernel(record, retained)

    def test_wrong_length_and_missing_backup_cannot_reauthorize_the_original_elf(self):
        with tempfile.TemporaryDirectory() as directory:
            retained = Path(directory) / 'green.elf'
            data = b'original successful kernel bytes'
            retained.write_bytes(data)
            record = {'artifacts': {'-kernel': {'path': str(retained), 'size': len(data) + 1,
                                               'sha256': NEGATIVE.sha(data)}}}
            with self.assertRaises(ValueError):
                NEGATIVE.checked_green_kernel(record, retained)
            retained.unlink()
            with self.assertRaises(FileNotFoundError):
                NEGATIVE.checked_green_kernel(record, retained)


class RuntimeMutationRecipeContract(unittest.TestCase):
    def test_all_three_recipes_apply_to_the_current_runtime_and_only_the_declared_path(self):
        # A production refactor must update its explicitly named mutation before
        # the expensive green/negative guest sequence. This applies no patch and
        # makes no claim that an applicable mutation is behaviorally detected.
        controls = (
            "handoff-drop-tail-runtime-v2",
            "handoff-eligibility-first-runtime-v2",
            "dequeue-drop-owner-switch-v2",
        )
        for control in controls:
            name, expected_sha, declared, _, minimum = NEGATIVE.CONTROLS[control]
            patch = NEGATIVE.ROOT / "tests/organ_backend" / name
            with self.subTest(control=control):
                self.assertTrue(patch.is_file())
                self.assertFalse(patch.is_symlink())
                self.assertEqual(NEGATIVE.sha(patch.read_bytes()), expected_sha)
                self.assertGreaterEqual(minimum, 396)
                checked = subprocess.run(
                    ["git", "apply", "--check", str(patch)], cwd=NEGATIVE.ROOT,
                    capture_output=True,
                )
                self.assertEqual(checked.returncode, 0, checked.stderr.decode())
                stats = subprocess.check_output(
                    ["git", "apply", "--numstat", str(patch)], cwd=NEGATIVE.ROOT,
                    text=True,
                ).splitlines()
                self.assertEqual(len(stats), 1)
                self.assertEqual(stats[0].split("\t")[-1], declared)


if __name__ == '__main__':
    unittest.main()
