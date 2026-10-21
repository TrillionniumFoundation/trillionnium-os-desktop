#!/usr/bin/env python3
"""Exercise unavailable-driver branches without loading modules or touching disks."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock


spec = importlib.util.spec_from_file_location('exfat_support_test', Path(__file__).with_name('exfat_kernel_support.py'))
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)
RELEASE = '6.17.0-1022-azure'
WITHOUT = b'nodev\tsysfs\n\text4\n'
WITH = WITHOUT + b'\texfat\n'
DRIVER = f'/lib/modules/{RELEASE}/kernel/fs/exfat/exfat.ko.zst\n'.encode()
MISSING = (1, b'', b'modinfo: ERROR: Module exfat not found.\n')


class SupportTests(unittest.TestCase):
    def prepare(self, out, report, snapshots, response):
        with mock.patch.object(support.os, 'uname', return_value=types.SimpleNamespace(release=RELEASE)), \
                mock.patch.object(support, 'read_filesystems', side_effect=snapshots), \
                mock.patch.object(support, 'tool', side_effect=lambda name: '/tools/' + name), \
                mock.patch.object(support, 'run', side_effect=response) as execute:
            support.prepare(out, report)
        return execute

    def test_only_one_registered_block_filesystem_counts(self):
        self.assertTrue(support.has_exfat(WITH))
        for raw in (WITHOUT, b'\texfat_other\n', b'nodev\texfat\n', b'exfat\nexfat\n',
                    b'filesystem exfat loaded\n', b'EXFAT_PASS\n'):
            with self.subTest(raw=raw):
                self.assertFalse(support.has_exfat(raw))

    def test_already_registered_driver_requires_no_install_or_module_load(self):
        with tempfile.TemporaryDirectory() as directory:
            out, report = Path(directory), {'passed': False}
            execute = self.prepare(out, report, [WITH, WITH], None)
            execute.assert_not_called()
            self.assertTrue(report['passed'])
            self.assertEqual(report['installed_packages'], [])
            self.assertEqual((out / 'filesystems-before.log').read_bytes(), WITH)
            self.assertEqual((out / 'filesystems-after.log').read_bytes(), WITH)

    def test_available_unloaded_module_is_loaded_without_package_changes(self):
        calls = []
        def response(out, report, name, command, **kwargs):
            calls.append((name, command))
            return (0, DRIVER, b'') if name == 'module-before' else (0, b'', b'')
        with tempfile.TemporaryDirectory() as directory:
            report = {'passed': False}
            self.prepare(Path(directory), report, [WITHOUT, WITH], response)
            self.assertTrue(report['passed'])
            self.assertEqual(calls, [
                ('module-before', ['/tools/modinfo', '--set-version', RELEASE, '--filename', 'exfat']),
                ('module-load', ['/tools/modprobe', '--', 'exfat']),
            ])
            self.assertEqual(report['installed_packages'], [])

    def test_missing_driver_installs_only_available_packages_for_the_running_abi(self):
        calls = []
        version = '6.17.0-1022.22~24.04.1'
        package = 'linux-modules-extra-' + RELEASE + '=' + version
        def response(out, report, name, command, **kwargs):
            calls.append((name, command))
            if name == 'module-before':
                return MISSING
            if name == 'linux-modules-policy':
                return 0, b'  Candidate: (none)\n', b''
            if name == 'linux-modules-extra-policy':
                return 0, ('  Candidate: ' + version + '\n').encode(), b''
            if name == 'module-after-install':
                return 0, DRIVER, b''
            return 0, b'', b''
        with tempfile.TemporaryDirectory() as directory:
            report = {'passed': False}
            self.prepare(Path(directory), report, [WITHOUT, WITH], response)
            self.assertTrue(report['passed'])
            self.assertEqual(report['installed_packages'], [package])
            self.assertEqual(dict(calls)['module-install'],
                             ['/tools/apt-get', 'install', '-y', '--no-install-recommends', '--', package])
            self.assertEqual(dict(calls)['linux-modules-policy'][-1], 'linux-modules-' + RELEASE)
            self.assertEqual(dict(calls)['linux-modules-extra-policy'][-1], 'linux-modules-extra-' + RELEASE)
            self.assertLess([name for name, _ in calls].index('module-after-install'),
                            [name for name, _ in calls].index('module-load'))

    def test_no_matching_package_is_a_failure_not_another_kernel_or_a_skip(self):
        calls = []
        def response(out, report, name, command, **kwargs):
            calls.append(name)
            return MISSING if name == 'module-before' else (0, b'', b'')
        with tempfile.TemporaryDirectory() as directory:
            report = {'passed': False}
            with self.assertRaisesRegex(ValueError, 'no module package candidate'):
                self.prepare(Path(directory), report, [WITHOUT], response)
            self.assertFalse(report['passed'])
            self.assertNotIn('module-install', calls)
            self.assertNotIn('module-load', calls)

    def test_unclassified_module_lookup_error_does_not_guess_a_missing_package(self):
        with tempfile.TemporaryDirectory() as directory:
            report = {'passed': False}
            with self.assertRaisesRegex(ValueError, 'unclassified reason'):
                self.prepare(Path(directory), report, [WITHOUT],
                             lambda *args, **kwargs: (1, b'', b'modinfo: permission denied\n'))
            self.assertFalse(report['passed'])

    def test_successful_modprobe_without_registration_still_fails(self):
        def response(out, report, name, command, **kwargs):
            return (0, DRIVER, b'') if name == 'module-before' else (0, b'', b'')
        with tempfile.TemporaryDirectory() as directory:
            out, report = Path(directory), {'passed': False}
            with self.assertRaisesRegex(ValueError, 'not registered'):
                self.prepare(out, report, [WITHOUT, WITHOUT], response)
            self.assertFalse(report['passed'])
            self.assertFalse(report['registered_after'])
            self.assertEqual((out / 'filesystems-after.log').read_bytes(), WITHOUT)

    def test_module_command_failure_keeps_its_real_output_and_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            out, report = Path(directory), {'passed': False}
            def response(command, **kwargs):
                kwargs['stderr'].write(b'modprobe: operation not permitted\n')
                return types.SimpleNamespace(returncode=1)
            with mock.patch.object(support.subprocess, 'run', side_effect=response), \
                    self.assertRaisesRegex(ValueError, 'exit 1'):
                support.run(out, report, 'module-load', ['/tools/modprobe', '--', 'exfat'])
            self.assertFalse(report['passed'])
            self.assertEqual((out / 'module-load.exit-code.txt').read_text(), '1\n')
            self.assertEqual((out / 'module-load.stderr.log').read_bytes(), b'modprobe: operation not permitted\n')

    def test_candidate_parser_rejects_ambiguous_or_unexpected_versions(self):
        self.assertIsNone(support.package_candidate(b''))
        self.assertIsNone(support.package_candidate(b'  Candidate: (none)\n'))
        for raw in (b'  Candidate: 1\n  Candidate: 2\n', b'  Candidate: --another-kernel\n'):
            with self.assertRaises(ValueError):
                support.package_candidate(raw)

    def test_cli_requires_explicit_disposable_host_and_root_before_mutation(self):
        for args, euid in (([], 0), (['--disposable-ci'], 1000)):
            with self.subTest(args=args, euid=euid), tempfile.TemporaryDirectory() as directory:
                out = Path(directory) / 'new'
                with mock.patch.object(support.os, 'geteuid', return_value=euid), \
                        mock.patch.object(support, 'prepare') as prepare, \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(support.main([*args, '--output', str(out)]), 1)
                prepare.assert_not_called()
                report = json.loads((out / 'result.json').read_text())
                self.assertFalse(report['passed'])
                self.assertFalse(report['linux_reference_passed'])
                self.assertFalse(report['guest_passed'])


if __name__ == '__main__':
    unittest.main()
