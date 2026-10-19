#!/usr/bin/env python3
"""Verdict and packaging regressions; these do not claim guest execution."""
import gzip
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    'scm_guest_runner', Path(__file__).with_name('run_scm_rights_cloexec_guest.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class VerdictTests(unittest.TestCase):
    def complete(self):
        return [*(f'SCM_CLOEXEC_CASE name={name} result=PASS line=0' for name in runner.CASE_ORDER),
                runner.COMPLETE, 'SCM_CLOEXEC_PROCESS_EXIT=0', runner.BOOT_MARKER]

    def verdict(self, lines, code=33, timed_out=False):
        return runner.evaluate(('\n'.join(lines) + '\n').encode(), code, timed_out)['passed']

    def test_complete_denominator_and_real_exit_required(self):
        self.assertTrue(self.verdict(self.complete()))
        for code in (0, 1, None, True):
            self.assertFalse(self.verdict(self.complete(), code))
        self.assertFalse(self.verdict(self.complete(), timed_out=True))

    def test_duplicate_missing_and_unknown_cases_rejected(self):
        lines = self.complete()
        self.assertFalse(self.verdict(lines[1:]))
        lines[0] = lines[1]
        self.assertFalse(self.verdict(lines))
        lines[0] = 'SCM_CLOEXEC_CASE name=unknown result=PASS line=0'
        self.assertFalse(self.verdict(lines))

    def test_failed_case_cannot_be_overridden_by_success_summary(self):
        lines = self.complete()
        lines[0] = lines[0].replace('PASS line=0', 'FAIL line=165')
        self.assertFalse(self.verdict(lines))
        self.assertFalse(self.verdict(['SCM_CLOEXEC_ASSERT line=165 expression=x errno=0', *self.complete()]))

    def test_duplicate_and_out_of_order_completion_rejected(self):
        self.assertFalse(self.verdict([*self.complete(), runner.COMPLETE]))
        lines = self.complete()
        lines[0], lines[27] = lines[27], lines[0]
        self.assertFalse(self.verdict(lines))
        lines = self.complete()
        lines[-1], lines[-2] = lines[-2], lines[-1]
        self.assertFalse(self.verdict(lines))

    def test_kernel_failure_and_failed_process_exit_rejected(self):
        self.assertFalse(self.verdict([*self.complete(), 'Kernel panic']))
        self.assertFalse(self.verdict([*self.complete(), 'thread panicked at a source file']))
        lines = self.complete()
        lines[-2] = 'SCM_CLOEXEC_PROCESS_EXIT=1'
        self.assertFalse(self.verdict(lines))


class PackagingTests(unittest.TestCase):
    def test_elf_changed_after_linux_reference_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            elf = Path(directory) / 'probe.elf'
            original = b'fixed Linux reference input'
            elf.write_bytes(original)
            frozen_digest = runner.sha(original)
            self.assertEqual(runner.read_pinned(elf, frozen_digest), original)
            elf.write_bytes(b'different bytes after an intervening build')
            with self.assertRaisesRegex(ValueError, 'SHA256 differs'):
                runner.read_pinned(elf, frozen_digest)

    def initrd(self, init=b'set -eu\necho "TRILLIONNIUM_A01_BOOT_OK"\n'):
        fields = [1, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
        return gzip.compress(runner.pack([('init', fields, init), ('original', fields, b'preserved')]), mtime=0)

    def test_original_entry_preserved_and_probe_status_captured(self):
        original = self.initrd()
        result = runner.build_initramfs(original, b'probe fixture')
        self.assertEqual(result, runner.build_initramfs(original, b'probe fixture'))
        entries = {n: data for n, _, data in runner.unpack(gzip.decompress(result))}
        self.assertEqual(entries['original'], b'preserved')
        self.assertEqual(entries['bin/scm-rights-cloexec-probe'], b'probe fixture')
        self.assertIn(b'scm_probe_exit=$?', entries['init'])
        self.assertIn(b'set -eu', entries['init'])

    def test_ambiguous_missing_or_unchecked_init_rejected(self):
        for init in (b'set -eu\n', b'echo "TRILLIONNIUM_A01_BOOT_OK"\n',
                     b'set -eu\necho "TRILLIONNIUM_A01_BOOT_OK"\necho "TRILLIONNIUM_A01_BOOT_OK"\n'):
            with self.assertRaises(ValueError):
                runner.build_initramfs(self.initrd(init), b'probe fixture')


if __name__ == '__main__':
    unittest.main()
