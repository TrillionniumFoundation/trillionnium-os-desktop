#!/usr/bin/env python3
"""Adversarial tests of the permission evidence verdict; these do not boot a kernel."""
import copy
import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('permission_runner', Path(__file__).with_name('run_permission_guest.py'))
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def observation(name):
    policy = runner.SPECS[name]
    actor = policy['actor']
    row = {'name': name, 'ruid': runner.OWNER if policy['fsuid_owner'] else actor,
           'euid': actor, 'suid': runner.OWNER if policy['fsuid_owner'] else actor,
           'fsuid': runner.OWNER if policy['fsuid_owner'] else actor,
           'rgid': actor, 'egid': actor, 'sgid': actor, 'fsgid': actor,
           'groups_count': int(policy['member']), 'group': runner.MEMBER if policy['member'] else -1,
           'effective': policy['caps'], 'permitted': policy['caps'], 'inheritable': 0,
           'rc': -1 if policy['errno'] else 0, 'errno': policy['errno']}
    for prefix in ('before', 'after'):
        values = policy[prefix] if policy['mount'] is None else (0, 0, 0o755)
        row.update({prefix + '_' + key: value for key, value in zip(('uid', 'gid', 'mode'), values)})
        row.update({prefix + '_ino': 17, prefix + '_dev': 1,
                    prefix + '_ctime_sec': 1700000000, prefix + '_ctime_nsec': 123})
    if policy.get('ctime_advance'):
        row['after_ctime_sec'] += 1
    if policy['mount'] is None:
        row.update(marker_before=-1, marker_after=-1)
    else:
        before = 0 if policy['mount'] == 'umount' else 1
        row.update(marker_before=before,
                   marker_after=before if policy['errno'] else (1 if policy['mount'] == 'umount' else 0))
    return row


def encode_observation(row):
    return 'PERMISSION_OBSERVATION ' + ' '.join(f'{key}={row[key]}' for key in runner.OBS_KEYS)


def valid_lines():
    lines = []
    for name in runner.CASE_ORDER:
        lines.extend((encode_observation(observation(name)), f'PERMISSION_CASE name={name} result=PASS line=0'))
    return lines + [runner.COMPLETE]


def raw(lines, guest=False):
    if guest:
        lines = ['kernel startup'] + lines + [runner.PROCESS_EXIT, runner.BOOT_MARKER]
    return ('\n'.join(lines) + '\n').encode()


class VerdictTests(unittest.TestCase):
    def test_full_observations_reference_and_guest_and_real_exit_required(self):
        data = raw(valid_lines())
        self.assertEqual(runner.CASE_COUNT, 32)
        self.assertTrue(runner.evaluate_reference(data, b'', 0, False)['passed'])
        guest = raw(valid_lines(), guest=True)
        self.assertTrue(runner.evaluate_guest(guest, 33, False)['passed'])
        for code in (0, 1, 65, -9, None, True):
            self.assertFalse(runner.evaluate_guest(guest, code, False)['passed'])
        self.assertFalse(runner.evaluate_guest(guest, 33, True)['passed'])
        self.assertFalse(runner.evaluate_reference(data, b'error', 0, False)['passed'])
        self.assertFalse(runner.evaluate_reference(data, b'', 1, False)['passed'])

    def test_pass_labels_cannot_replace_actual_observations(self):
        lines = [line for line in valid_lines() if not line.startswith('PERMISSION_OBSERVATION')]
        self.assertFalse(runner.evaluate_guest(raw(lines, guest=True), 33, False)['passed'])

    def test_actual_uid_fsuid_groups_and_each_capability_set_must_match(self):
        mutations = [('chmod_nonowner_fd', 'euid', 0), ('chmod_nonowner_fd', 'ruid', 0),
                     ('chmod_nonowner_fd', 'suid', 0), ('chmod_fsuid_owner', 'fsuid', runner.OTHER),
                     ('chmod_nonowner_fd', 'effective', runner.CAP_FOWNER),
                     ('chmod_nonowner_fd', 'permitted', runner.CAP_FOWNER),
                     ('chmod_nonowner_fd', 'inheritable', runner.CAP_FOWNER),
                     ('chmod_fowner', 'effective', 0),
                     ('chown_owner_group_member', 'groups_count', 0),
                     ('chown_owner_group_member', 'group', runner.FOREIGN),
                     ('mount_root_without_cap_denied', 'effective', runner.CAP_SYS_ADMIN)]
        for name, key, value in mutations:
            with self.subTest(name=name, key=key):
                lines = valid_lines()
                row = observation(name)
                row[key] = value
                lines[runner.CASE_ORDER.index(name) * 2] = encode_observation(row)
                self.assertFalse(runner.evaluate_guest(raw(lines, guest=True), 33, False)['passed'])

    def test_denial_requires_errno_and_every_recorded_metadata_field_unchanged(self):
        for key in ('uid', 'gid', 'mode', 'ino', 'dev', 'ctime_sec', 'ctime_nsec'):
            row = observation('chmod_nonowner_fd')
            row['after_' + key] += 1
            with self.subTest(key=key):
                self.assertFalse(runner.check_observation(row)['passed'])
        for key, value in (('rc', 0), ('errno', 13)):
            row = observation('chown_owner_uid_denied')
            row[key] = value
            self.assertFalse(runner.check_observation(row)['passed'])
        for name in ('chmod_owner', 'chown_cap'):
            for key in ('ino', 'dev'):
                row = observation(name)
                row['after_' + key] += 1
                self.assertFalse(runner.check_observation(row)['passed'])

    def test_group_sgid_and_chown_setid_positive_semantics_are_independent(self):
        for name, bad_mode in [('chmod_owner_sgid_member', 0o755),
                               ('chmod_owner_sgid_nonmember', 0o2755),
                               ('chmod_owner_sgid_fsetid', 0o755),
                               ('chown_regular_clear_setid', 0o6755),
                               ('chown_directory_keep_setid', 0o775)]:
            row = observation(name)
            row['after_mode'] = bad_mode
            with self.subTest(name=name):
                self.assertFalse(runner.check_observation(row)['passed'])

    def test_nonowner_explicit_same_uid_denied_but_minus_one_noop_succeeds_with_ctime_update(self):
        denied = observation('chown_nonowner_same_uid')
        noop = observation('chown_nonowner_noop')
        self.assertEqual((denied['rc'], denied['errno']), (-1, 1))
        self.assertEqual((noop['rc'], noop['errno']), (0, 0))
        self.assertTrue(runner.check_observation(denied)['passed'])
        self.assertTrue(runner.check_observation(noop)['passed'])
        noop['after_ctime_sec'] = noop['before_ctime_sec']
        self.assertFalse(runner.check_observation(noop)['passed'])
        noop['after_ctime_sec'] -= 1
        self.assertFalse(runner.check_observation(noop)['passed'])

    def test_mount_success_and_denial_require_actual_underlying_marker_visibility(self):
        for name in ('mount_nonroot_denied', 'mount_sysadmin', 'umount_nonroot_denied', 'umount_sysadmin'):
            row = observation(name)
            row['marker_after'] = 1 - row['marker_after']
            with self.subTest(name=name):
                self.assertFalse(runner.check_observation(row)['passed'])

    def test_missing_duplicate_reordered_and_unknown_markers_fail(self):
        original = valid_lines()
        mutations = [original[2:], original + original[:2],
                     original[:2] + original[4:6] + original[2:4] + original[6:],
                     original + ['PERMISSION_SKIP name=mount_sysadmin'],
                     original + [runner.COMPLETE],
                     original + ['PERMISSION_ASSERT name=chmod_owner line=1']]
        for changed in mutations:
            self.assertFalse(runner.evaluate_guest(raw(changed, guest=True), 33, False)['passed'])
        wrong_order = original + [runner.BOOT_MARKER, runner.PROCESS_EXIT]
        self.assertFalse(runner.evaluate_guest(raw(wrong_order), 33, False)['passed'])

    def test_malformed_observation_duplicate_keys_and_out_of_range_data_rejected(self):
        line = encode_observation(observation('chmod_owner'))
        for changed in (line + ' euid=0', line.replace('suid=', 'euid='),
                        line.replace('effective=0', 'effective=True'),
                        line.replace('rc=0', 'rc=0 extra=0')):
            self.assertIsNone(runner.parse_observation(changed))
        for key, value in [('before_ctime_nsec', 1000000000), ('after_dev', -1), ('after_mode', 0o17777)]:
            row = observation('chmod_owner')
            row[key] = value
            self.assertFalse(runner.check_observation(row)['passed'])

    def test_failed_case_signal_timeout_or_kernel_panic_never_passes(self):
        lines = valid_lines()
        lines[1] = f'PERMISSION_CASE name={runner.CASE_ORDER[0]} result=FAIL line=0 signal=14'
        self.assertFalse(runner.evaluate_guest(raw(lines, guest=True), 33, False)['passed'])
        self.assertFalse(runner.evaluate_guest(raw(valid_lines() + ['Kernel panic'], guest=True), 33, False)['passed'])


class ArchiveTests(unittest.TestCase):
    def original(self):
        data = b'#!/bin/sh\nset -eu\necho "TRILLIONNIUM_A01_BOOT_OK"\n'
        entries = [('init', [1, 0o100755, 0, 0, 1, 0, len(data), 0, 0, 0, 0, 5, 0], data)]
        return gzip.compress(runner.common.pack(entries), mtime=0)

    def test_injection_preserves_entries_and_only_adds_one_static_probe(self):
        original = self.original()
        result = runner.build_initramfs(original, b'probe bytes')
        entries = runner.common.unpack(gzip.decompress(result))
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[-1][0], runner.PROBE_PATH)
        self.assertEqual(entries[-1][2], b'probe bytes')
        init = entries[0][2]
        self.assertIn(b'/bin/permission-probe --work-dir /permission-work', init)
        self.assertLess(init.index(b'PERMISSION_PROCESS_EXIT='), init.index(b'TRILLIONNIUM_A01_BOOT_OK'))
        with self.assertRaises(ValueError):
            runner.build_initramfs(result, b'probe twice')

    def reference(self, root):
        probe = b'fixed probe ELF bytes'
        digest = runner.sha(probe)
        (root / 'probe.elf').write_bytes(probe)
        (root / 'probe.sha256').write_text(f'{digest}  probe.elf\n')
        stdout = raw(valid_lines())
        (root / 'stdout.log').write_bytes(stdout)
        (root / 'stderr.log').write_bytes(b'')
        (root / 'exit-code.txt').write_text('0\n')
        receipt = {'schema': 'a04.permissions-linux.v1', 'passed': True,
                   'probe_inputs_unchanged': True, 'runner_inputs_unchanged': True,
                   'process_group_cleanup_completed': True, 'private_mount_namespace': True,
                   'source_inputs': runner.source_inputs(), 'probe_sha256': digest,
                   'command': ['unshare', '--mount', '--propagation', 'private', '--', 'probe.elf'],
                   'process_exit': 0, 'timed_out': False,
                   'stdout_sha256': runner.sha(stdout), 'stderr_sha256': runner.sha(b'')}
        frozen = json.dumps(receipt).encode()
        (root / 'input.json').write_bytes(frozen)
        receipt['frozen_input_sha256'] = runner.sha(frozen)
        (root / 'result.json').write_text(json.dumps(receipt))
        return probe, digest, receipt

    def test_changed_elf_and_failed_reference_cannot_be_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            probe, digest, receipt = self.reference(root)
            self.assertEqual(runner.load_reference(root, digest)[0], probe)
            (root / 'probe.elf').write_bytes(b'new ELF')
            with self.assertRaises(ValueError):
                runner.load_reference(root, digest)
            self.reference(root)
            for key in ('passed', 'private_mount_namespace', 'probe_inputs_unchanged',
                        'runner_inputs_unchanged', 'process_group_cleanup_completed'):
                changed = copy.deepcopy(receipt)
                changed[key] = False
                (root / 'result.json').write_text(json.dumps(changed))
                with self.subTest(key=key), self.assertRaises(ValueError):
                    runner.load_reference(root, digest)

    def test_rehashed_false_stdout_is_rejudged_instead_of_trusting_passed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, digest, receipt = self.reference(root)
            changed = raw(valid_lines()).replace(b'effective=8 ', b'effective=0 ', 1)
            (root / 'stdout.log').write_bytes(changed)
            receipt['stdout_sha256'] = runner.sha(changed)
            (root / 'result.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, 'raw observations'):
                runner.load_reference(root, digest)

    def test_missing_product_binding_stops_before_qemu(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'source-before.json').write_text(json.dumps({'files': {}}))
            args = type('Args', (), {'product_evidence': root, 'expected_source_head': 'a' * 40,
                                     'expected_source_tree': 'b' * 40})()
            with mock.patch.object(runner.common, 'product_input', return_value=(b'kernel', 'a' * 64)), \
                 mock.patch.object(runner.subprocess, 'run') as launch:
                with self.assertRaisesRegex(ValueError, 'not bound to product snapshot'):
                    runner.run_guest(args, root, {'source_inputs': runner.source_inputs()})
                launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
