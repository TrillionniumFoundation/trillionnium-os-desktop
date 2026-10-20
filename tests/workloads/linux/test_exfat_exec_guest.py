#!/usr/bin/env python3
"""Reject incomplete ExFAT evidence and require the actual old exec phenotype.

These are parser/acceptance tests with synthetic observations. They neither
mount a disk nor execute a guest, and cannot establish disk qualification.
"""
import importlib.util
import gzip
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('exfat_runner', Path(__file__).with_name('run_exfat_exec_guest.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
HEAD = 'a' * 40
SIZE = 1000000


def fixture(*, old=False, guest=True):
    lines = [] if guest else ['EXFAT_LOOP readonly=1 autoclear=1 inode=111 device=222']
    lines.append('EXFAT_MOUNT type=538032816 flags=5')
    mode = '4095' if old else '511'
    for name, kind, inode in (('root', '16384', '2'), ('subject', '32768', '5'), ('directory', '16384', '8')):
        lines.append(f'EXFAT_METADATA object={name} uid=0 gid=0 mode={mode} type={kind} inode={inode} device=7')
    lines.append('EXFAT_ELF_MATCH source=' + HEAD + ' bytes=1000000')
    for condition in ('plain', 'nnp'):
        for phase in ('before', 'after'):
            elevated = old and condition == 'plain' and phase == 'after'
            effective = '0' if elevated else '65534'
            nnp = '1' if condition == 'nnp' else '0'
            lines.append(f'EXFAT_CREDENTIALS phase={phase} condition={condition} '
                         f'ruid=65534 euid={effective} suid={effective} fsuid={effective} '
                         f'rgid=65534 egid={effective} sgid={effective} fsgid={effective} '
                         'groups=0 effective=0 permitted=0 inheritable=0 bounding=0 ambient=0 '
                         f'nnp={nnp} securebits=0 keepcaps=0')
        lines.append(f'EXFAT_CHILD condition={condition} exit=0 signal=0')
    lines.append('EXFAT_COMPLETE metadata=3 executions=2')
    lines.append('EXFAT_CLEANUP unmounted=1 backing=' + ('virtio detached=0' if guest else 'loop detached=1'))
    if guest:
        lines += ['EXFAT_PROCESS_EXIT=0', 'TRILLIONNIUM_A01_BOOT_OK']
    return ('\n'.join(lines) + '\n').encode()


def verdict(raw, *, old=False, guest=True, code=None, timed_out=False, head=HEAD, size=SIZE):
    return runner.evaluate(raw, (33 if guest else 0) if code is None else code,
                           timed_out, head, size, guest=guest, old=old)['passed']


class ExfatEvidenceOracleTests(unittest.TestCase):
    @staticmethod
    def cpio_helper():
        path = Path(__file__).resolve().parents[2] / 'organ_backend/run_guest_probe.py'
        spec = importlib.util.spec_from_file_location('exfat_newc', path)
        common = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(common)
        return common

    @staticmethod
    def cpio_fixture(common, extra=()):
        fields = [1, 0o100755, 0, 0, 1, 7, 0, 0, 0, 0, 0, 0, 0]
        entries = [('init', fields, b'#!/bin/sh\nset -eu\necho "TRILLIONNIUM_A01_BOOT_OK"\n'),
                   ('bin/original', [2, *fields[1:]], b'\x00original binary\xff'), *extra]
        return gzip.compress(common.pack(entries), mtime=0)

    def test_injected_initramfs_preserves_all_original_bytes_and_metadata(self):
        common = self.cpio_helper()
        original = self.cpio_fixture(common)
        before = common.unpack(gzip.decompress(original))
        built = runner.build_initramfs(original, b'frozen probe', HEAD, common)
        after = common.unpack(gzip.decompress(built))
        self.assertEqual(len(after), len(before) + 1)
        self.assertEqual(after[1], before[1])
        self.assertEqual(after[0][1][:6] + after[0][1][7:], before[0][1][:6] + before[0][1][7:])
        self.assertEqual(after[0][1][6], len(after[0][2]))
        self.assertEqual(after[-1][0], 'bin/exfat-exec-probe')
        self.assertEqual(after[-1][2], b'frozen probe')
        self.assertEqual(after[-1][1][1], 0o100755)
        self.assertEqual(after[0][2].count(b'--guest ' + HEAD.encode()), 1)
        self.assertTrue(after[0][2].endswith(b'echo "TRILLIONNIUM_A01_BOOT_OK"\n'))

    def test_missing_duplicate_init_or_existing_probe_fails_closed(self):
        common = self.cpio_helper()
        fields = [3, 0o100755, 0, 0, 1, 7, 0, 0, 0, 0, 0, 0, 0]
        extra = ('./init', fields, b'#!/bin/sh\nset -eu\necho "TRILLIONNIUM_A01_BOOT_OK"\n')
        for original in (self.cpio_fixture(common, [extra]),
                         self.cpio_fixture(common, [('bin/exfat-exec-probe', fields, b'old')]),
                         gzip.compress(common.pack([('bin/original', fields, b'only')])),
                         gzip.compress(common.pack([('init', fields, b'no boot marker')]))):
            with self.assertRaises(ValueError):
                runner.build_initramfs(original, b'probe', HEAD, common)

    def test_formatter_version_comes_from_successful_format_output(self):
        # The successful cloud format and the separate failed -V both emitted
        # this exfatprogs 1.2.2 version header. Only the real format is required.
        output = (b'exfatprogs version : 1.2.2\n'
                  b'Creating exFAT filesystem(image.raw, cluster size=32768)\n\n'
                  b'exFAT format complete!\n')
        self.assertEqual(runner.formatter_version(output), '1.2.2')
        for malformed in (b'', b'not exfatprogs\n', b'\n' + output,
                          b'error\n' + output, output.replace(b'1.2.2', b'1.2.2 extra')):
            with self.assertRaises(ValueError):
                runner.formatter_version(malformed)

    def test_complete_positive_linux_and_guest(self):
        self.assertTrue(verdict(fixture()))
        self.assertTrue(verdict(fixture(guest=False), guest=False))

    def test_old_requires_mode_and_actual_plain_exec_transition(self):
        raw = fixture(old=True)
        self.assertFalse(verdict(raw))
        self.assertTrue(verdict(raw, old=True))
        self.assertFalse(verdict(fixture(), old=True))

    def test_arbitrary_failure_timeout_and_boolean_exit_are_not_negative(self):
        for code in (0, 1, 65, -9, True):
            with self.subTest(code=code):
                self.assertFalse(verdict(fixture(old=True), old=True, code=code))
        self.assertFalse(verdict(fixture(old=True), old=True, timed_out=True))

    def test_missing_or_duplicate_observation_never_qualifies(self):
        for old in (False, True):
            lines = fixture(old=old).splitlines(keepends=True)
            for index in range(len(lines)):
                with self.subTest(old=old, index=index):
                    self.assertFalse(verdict(b''.join(lines[:index] + lines[index + 1:]), old=old))
                    self.assertFalse(verdict(b''.join(lines[:index] + [lines[index]] + lines[index:]), old=old))

    def test_swapped_cases_or_observations_fail(self):
        lines = fixture().splitlines(keepends=True)
        for first, second in ((1, 2), (5, 6), (7, 10), (11, 12)):
            changed = lines.copy()
            changed[first], changed[second] = changed[second], changed[first]
            self.assertFalse(verdict(b''.join(changed)))

    def test_old_mode_without_privilege_change_is_not_negative(self):
        self.assertFalse(verdict(fixture().replace(b'mode=511', b'mode=4095'), old=True))

    def test_privilege_change_without_old_mode_is_not_negative(self):
        self.assertFalse(verdict(fixture(old=True).replace(b'mode=4095', b'mode=511'), old=True))

    def test_nnp_companion_must_stay_unprivileged(self):
        raw = fixture(old=True).replace(b'phase=after condition=nnp ruid=65534 euid=65534',
                                        b'phase=after condition=nnp ruid=65534 euid=0')
        self.assertFalse(verdict(raw, old=True))

    def test_all_preconditions_are_measured_not_assumed(self):
        changes = ((b'groups=0', b'groups=1'), (b'effective=0', b'effective=1'),
                   (b'permitted=0', b'permitted=1'), (b'inheritable=0', b'inheritable=1'),
                   (b'bounding=0', b'bounding=1'), (b'ambient=0', b'ambient=1'),
                   (b'securebits=0', b'securebits=1'), (b'keepcaps=0', b'keepcaps=1'),
                   (b'nnp=0', b'nnp=1'), (b'fsuid=65534', b'fsuid=0'))
        for before, after in changes:
            with self.subTest(field=before):
                self.assertFalse(verdict(fixture(old=True).replace(before, after, 1), old=True))

    def test_wrong_filesystem_nosuid_or_noexec_cannot_hide_defect(self):
        for replacement in (b'type=16914836 flags=5', b'type=538032816 flags=7',
                            b'type=538032816 flags=13', b'type=538032816 flags=4'):
            self.assertFalse(verdict(fixture().replace(b'type=538032816 flags=5', replacement)))

    def test_boot_sector_signature_is_not_a_filesystem_type(self):
        for guest, old in ((True, False), (True, True), (False, False)):
            raw = fixture(guest=guest, old=old)
            accepted = runner.evaluate(raw, 33 if guest else 0, False, HEAD, SIZE, guest=guest, old=old)
            self.assertTrue(accepted['passed'])
            self.assertTrue(accepted['linux_statfs_type_compatible'])
            rejected = runner.evaluate(raw.replace(b'type=538032816', b'type=43605'),
                                       33 if guest else 0, False, HEAD, SIZE, guest=guest, old=old)
            self.assertFalse(rejected['passed'])
            self.assertFalse(rejected['linux_statfs_type_compatible'])

    def test_wrong_owner_kind_identity_or_duplicate_inode_fails(self):
        for before, after in ((b'uid=0 gid=0', b'uid=1 gid=0'), (b'type=32768', b'type=16384'),
                              (b'inode=5', b'inode=2'), (b'inode=5', b'inode=0'),
                              (b'inode=5 device=7', b'inode=5 device=9')):
            self.assertFalse(verdict(fixture().replace(before, after, 1)))

    def test_wrong_image_source_or_elf_size_fails(self):
        self.assertFalse(verdict(fixture(), head='b' * 40))
        self.assertFalse(verdict(fixture(), size=SIZE + 1))

    def test_failed_or_signaled_exec_child_is_not_qualification(self):
        for replacement in (b'exit=111 signal=0', b'exit=-1 signal=11'):
            self.assertFalse(verdict(fixture(old=True).replace(b'exit=0 signal=0', replacement, 1), old=True))

    def test_crash_assertion_unexpected_record_or_concatenated_marker_fails(self):
        for suffix in (b'kernel panic\n', b'panicked at test\n', b'EXFAT_ERROR setup_failed=1\n',
                       b'EXFAT_SKIPPED count=1\n'):
            self.assertFalse(verdict(fixture(old=True) + suffix, old=True))
        self.assertFalse(verdict(fixture().replace(b'EXFAT_MOUNT', b'Booting from ROM..EXFAT_MOUNT', 1)))

    def test_linux_loop_ownership_cleanup_and_raw_output_are_required(self):
        raw = fixture(guest=False)
        for before, after in ((b'readonly=1', b'readonly=0'), (b'autoclear=1', b'autoclear=0'),
                              (b'detached=1', b'detached=0')):
            self.assertFalse(verdict(raw.replace(before, after), guest=False))
        self.assertFalse(verdict(b'unexpected\n' + raw, guest=False))

    def test_malformed_numeric_and_trailing_fields_fail(self):
        for before, after in ((b'mode=511', b'mode=+511'), (b'mode=511', b'mode=NaN'),
                              (b'bytes=1000000', b'bytes=1000000 extra=1')):
            self.assertFalse(verdict(fixture().replace(before, after, 1)))


if __name__ == '__main__':
    unittest.main()
