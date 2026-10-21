#!/usr/bin/env python3
"""Adversarial evidence/ownership checks. These tests do not mount or boot an OS."""
import copy
import gzip
import importlib.util
from pathlib import Path
import struct
import subprocess
import tempfile
import types
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('exfat_runner_test', Path(__file__).with_name('run_exfat_mode_guest.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
negative_spec = importlib.util.spec_from_file_location('exfat_negative_test', Path(__file__).with_name('run_exfat_mode_negative.py'))
negative = importlib.util.module_from_spec(negative_spec)
negative_spec.loader.exec_module(negative)


def fixture(*, guest=True, old=False):
    lines = ['EXFAT_FS type=' + str(0xaa55 if guest else 0x2011bab0) + ' flags=0',
             'EXFAT_COPY bytes=800000 reread_equal=1']
    for name, ino, kind, size in (('root_mode', 2, 0o40000, 4096),
                                  ('file_mode', 3, 0o100000, 800000),
                                  ('directory_mode', 4, 0o40000, 4096)):
        lines.append(f'EXFAT_STAT name={name} rc=0 errno=0 mode={4095 if old else 511} type={kind} '
                     f'uid=0 gid=0 ino={ino} dev=17 size={size}')
        lines.append(f'EXFAT_CASE name={name} result={"FAIL" if old else "PASS"} exit={int(old)} signal=0')
    for name, nnp in (('exec_normal', 0), ('exec_nnp', 1)):
        for phase in ('before', 'after'):
            changed = old and not nnp and phase == 'after'
            ident = 0 if changed else 65534
            lines.append(f'EXFAT_CREDENTIALS phase={phase} name={name} ruid=65534 euid={ident} suid={ident} '
                         f'fsuid={ident} rgid=65534 egid={ident} sgid={ident} fsgid={ident} '
                         f'groups=0 nnp={nnp} securebits=0 effective=0 permitted=0 inheritable=0 '
                         f'ambient=0 bounding=0 at_secure={int(changed)}')
        failed = old and not nnp
        lines.append(f'EXFAT_CASE name={name} result={"FAIL" if failed else "PASS"} exit={int(failed)} signal=0')
    lines.append(f'EXFAT_COMPLETE total=5 passed={1 if old else 5} failed={4 if old else 0}')
    if guest:
        lines.extend((f'EXFAT_PROCESS_EXIT={int(old)}', 'TRILLIONNIUM_A01_BOOT_OK'))
    return lines


def evaluate(lines, *, guest=True, old=False, code=None, timeout=False, stderr=b''):
    return runner.oracle.evaluate(('\n'.join(lines) + '\n').encode(), guest=guest, negative=old,
                                   process_exit=(33 if guest else 0) if code is None else code,
                                   timed_out=timeout, probe_bytes=800000, stderr=stderr)


class ObservationTests(unittest.TestCase):
    def test_real_observations_and_process_completion_required_for_all_three_profiles(self):
        self.assertTrue(evaluate(fixture(guest=False), guest=False)['passed'])
        self.assertTrue(evaluate(fixture())['passed'])
        self.assertTrue(evaluate(fixture(old=True), old=True)['passed'])
        self.assertFalse(evaluate(fixture(old=True))['passed'])
        self.assertFalse(evaluate(fixture(), old=True)['passed'])
        for code in (0, 1, 65, -9, True):
            self.assertFalse(evaluate(fixture(), code=code)['passed'])
            self.assertFalse(evaluate(fixture(old=True), old=True, code=code)['passed'])
        self.assertFalse(evaluate(fixture(old=True), old=True, timeout=True)['passed'])
        self.assertFalse(evaluate(fixture(guest=False), guest=False, stderr=b'error')['passed'])

    def test_success_or_failure_labels_cannot_replace_credential_measurement(self):
        for old in (False, True):
            lines = [line for line in fixture(old=old) if not line.startswith('EXFAT_CREDENTIALS')]
            self.assertFalse(evaluate(lines, old=old)['passed'])

    def test_every_identity_and_capability_set_checked_before_and_after_exec(self):
        fields = ('ruid', 'euid', 'suid', 'fsuid', 'rgid', 'egid', 'sgid', 'fsgid', 'groups',
                  'nnp', 'securebits', 'effective', 'permitted', 'inheritable', 'ambient', 'bounding', 'at_secure')
        for old in (False, True):
            original = fixture(old=old)
            for index in (8, 9, 11, 12):
                for field in fields:
                    with self.subTest(old=old, index=index, field=field):
                        lines = original.copy()
                        tokens = lines[index].split()
                        key = next(i for i, part in enumerate(tokens) if part.startswith(field + '='))
                        tokens[key] = field + '=' + str(int(tokens[key].split('=')[1]) + 1)
                        lines[index] = ' '.join(tokens)
                        self.assertFalse(evaluate(lines, old=old)['passed'])

    def test_negative_needs_actual_transition_and_no_new_privileges_companion(self):
        good = fixture(old=True)
        for index, replacement in ((9, fixture()[9]), (12, good[9].replace('exec_normal', 'exec_nnp')),
                                   (10, 'EXFAT_CASE name=exec_normal result=FAIL exit=-1 signal=11')):
            changed = good.copy()
            changed[index] = replacement
            self.assertFalse(evaluate(changed, old=True)['passed'])
        self.assertFalse(evaluate(good + ['Kernel panic'], old=True)['passed'])

    def test_wrong_filesystem_mount_flags_inode_alias_and_copy_identity_fail(self):
        for index, before, after in ((0, 'type=43605', 'type=1'), (0, 'flags=0', 'flags=2'),
                                     (0, 'flags=0', 'flags=8'), (1, '800000', '799999'),
                                     (1, 'reread_equal=1', 'reread_equal=0'),
                                     (4, 'ino=3', 'ino=2'), (4, 'dev=17', 'dev=18'),
                                     (4, 'uid=0', 'uid=65534'), (6, 'mode=511', 'mode=4095')):
            lines = fixture()
            self.assertIn(before, lines[index])
            lines[index] = lines[index].replace(before, after)
            self.assertFalse(evaluate(lines)['passed'])

    def test_missing_duplicate_unknown_reordered_or_malformed_markers_fail(self):
        good = fixture()
        for lines in (good[1:], good + good[:1], good + ['EXFAT_SKIP name=exec_normal'],
                      good[:8] + good[9:10] + good[8:9] + good[10:],
                      good[:-2] + good[-1:] + good[-2:-1],
                      [line.replace('euid=65534', 'euid=65534 euid=0') for line in good],
                      good + ['EXFAT_SETUP errno=1']):
            self.assertFalse(evaluate(lines)['passed'])


class InputOwnershipTests(unittest.TestCase):
    def test_negative_mutation_matches_frozen_patch_on_real_inode_source(self):
        original = (runner.ROOT / negative.INODE).read_bytes()
        patch = (runner.ROOT / negative.PATCH).read_bytes()
        self.assertEqual(runner.sha(patch), negative.PATCH_SHA256)
        with tempfile.TemporaryDirectory(prefix='exfat-frozen-negative-') as directory:
            inode = Path(directory) / negative.INODE
            inode.parent.mkdir(parents=True)
            inode.write_bytes(original)
            subprocess.run(['git', 'apply', '--check', '-'], input=patch, cwd=directory,
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(['git', 'apply', '-'], input=patch, cwd=directory,
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            postimage = inode.read_bytes()
        self.assertNotEqual(postimage, original)
        self.assertEqual(negative.mutation(original), postimage)

    def test_initramfs_retains_original_entries_and_requires_unique_injection(self):
        body = b'#!/bin/sh\nset -eu\necho "TRILLIONNIUM_A01_BOOT_OK"\n'
        entries = [('init', [1, 0o100755, 0, 0, 1, 0, len(body), 0, 0, 0, 0, 5, 0], body)]
        original = gzip.compress(runner.common.pack(entries), mtime=0)
        result = runner.build_initramfs(original, b'fixed ELF bytes')
        after = runner.common.unpack(gzip.decompress(result))
        self.assertEqual(len(after), 2)
        self.assertEqual(after[1][2], b'fixed ELF bytes')
        self.assertIn(b'--device /dev/vda', after[0][2])
        self.assertLess(after[0][2].index(b'EXFAT_PROCESS_EXIT'), after[0][2].index(b'TRILLIONNIUM_A01_BOOT_OK'))
        with self.assertRaises(ValueError):
            runner.build_initramfs(result, b'changed ELF')

    def test_held_loop_descriptor_must_still_name_the_owned_whole_image(self):
        image_stat = types.SimpleNamespace(st_dev=17, st_ino=42)
        def response(fd, op, buf, mutate):
            self.assertEqual((fd, op, mutate), (7, 0x4C05, True))
            struct.pack_into('=QQQQQIIII', buf, 0, *values)
        original = [17, 42, 0, 0, 0, 9, 0, 0, 0]
        values = original.copy()
        with mock.patch.object(runner.fcntl, 'ioctl', side_effect=response):
            self.assertEqual(runner.loop_binding(7, image_stat)['number'], 9)
            for index in (0, 1, 3, 4, 6, 7, 8):
                values = original.copy()
                values[index] += 1
                with self.subTest(field=index), self.assertRaises(ValueError):
                    runner.loop_binding(7, image_stat)

    def test_negative_delta_rejects_changed_tests_or_an_unrelated_postimage(self):
        original = b'prefix\n' + negative.BEFORE + b'suffix\n'
        changed = negative.mutation(original)
        def row(data):
            return {'mode': '100644', 'size': len(data), 'sha256': runner.sha(data)}
        before = {'files': {negative.INODE: row(original), 'tests/test.rs': row(b'original test')}}
        after = {'files': {negative.INODE: row(changed), 'tests/test.rs': row(b'original test')}}
        negative.verify_delta(before, after, original, changed)
        modified = copy.deepcopy(after)
        modified['files']['tests/test.rs'] = row(b'weakened test')
        with self.assertRaises(ValueError):
            negative.verify_delta(before, modified, original, changed)
        with self.assertRaises(ValueError):
            negative.verify_delta(before, after, original, changed + b'extra code')
        with self.assertRaises(ValueError):
            negative.mutation(original + negative.BEFORE)


if __name__ == '__main__':
    unittest.main()
