#!/usr/bin/env python3
"""Offline transport fault tests; no attached Android device is contacted."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

SUPPORT = Path(__file__).resolve().parents[3] / 'support/android'
sys.path.insert(0, str(SUPPORT))
import run_physical_smoke as gate


class FakeAdb:
    server_version = '0029'

    def __init__(self, digest, *, package_before=False, fingerprint='fixture/android/37',
                 locked=False, user='0', focus=True, replace=False, stale_dump=False):
        self.digest, self.package_before = digest, package_before
        self.fingerprint, self.locked, self.user = fingerprint, locked, user
        self.focus, self.replace, self.stale_dump = focus, replace, stale_dump
        self.calls, self.dumps = [], {}
        self.installed, self.running = False, False
        self.saved, self.input, self.input_focused = 'EMPTY', '', False
        self.launches = 0

    def cmd(self, *parts, timeout=60, allow_failure=False):
        self.calls.append(parts)
        if parts == ('get-state',): return 'device\n'
        if parts == ('get-serialno',): return 'fixture-usb\n'
        if parts[:2] == ('shell', 'getprop'):
            return {'ro.build.fingerprint': self.fingerprint, 'ro.product.model': 'fixture',
                    'ro.product.device': 'fixture', 'ro.product.name': 'fixture',
                    'ro.product.cpu.abi': 'arm64-v8a', 'ro.build.version.release': '17',
                    'ro.build.version.sdk': '37', 'sys.boot_completed': '1'}[parts[2]] + '\n'
        if parts == ('shell', 'am', 'get-current-user'): return self.user + '\n'
        if parts == ('shell', 'dumpsys', 'window', 'policy'):
            return ' showing=' + str(self.locked).lower() + '\n inputRestricted=false\n'
        if parts == ('shell', 'pm', 'list', 'users'): return 'Users:\n UserInfo{0:Owner:13}\n UserInfo{10:Other:10}\n'
        if parts[:5] == ('shell', 'pm', 'list', 'packages', '-u'):
            return 'package:' + gate.PACKAGE + '\n' if self.package_before or self.installed else ''
        if parts[:5] == ('shell', 'pm', 'list', 'packages', '-U'):
            return 'package:' + gate.PACKAGE + ' uid:10123\n'
        if parts == ('shell', 'uname', '-a'): return 'Linux fixture aarch64\n'
        if parts == ('shell', 'getconf', 'PAGESIZE'): return '4096\n'
        if parts == ('shell', 'getenforce'): return 'Enforcing\n'
        if parts[0] == 'install':
            self.installed = True
            return 'Success\n'
        if parts[:3] == ('shell', 'pm', 'path'):
            return 'package:/data/app/fixture/base.apk\n' if self.installed else ''
        if parts[:2] == ('shell', 'sha256sum'):
            return ('f' * 64 if self.replace and self.launches else self.digest) + '  ' + parts[2] + '\n'
        if parts[:4] == ('shell', 'am', 'start', '-W'):
            self.running = True
            self.launches += 1
            return 'Status: ok\nActivity: ' + gate.COMPONENT + '\n'
        if parts == ('shell', 'dumpsys', 'activity', 'activities'):
            return ' mResumedActivity: ActivityRecord{123 u0 ' + gate.COMPONENT + ' t9}\n'
        if parts == ('shell', 'dumpsys', 'window', 'windows'):
            return ' mCurrentFocus=Window{123 u0 ' + (gate.COMPONENT if self.focus else 'other/.Private') + '}\n'
        if parts == ('shell', 'pidof', gate.PACKAGE): return str(1000 + self.launches) + '\n' if self.running else ''
        if parts == ('shell', 'wm', 'size'): return 'Physical size: 1224x2992\n'
        if parts[:3] == ('shell', 'uiautomator', 'dump'):
            if self.stale_dump: return 'ERROR: dump failed\n'
            self.dumps[parts[3]] = self.xml()
            return 'UI hierarchy dumped to: ' + parts[3] + '\n'
        if parts[:2] == ('exec-out', 'cat'): return self.dumps[parts[2]]
        if parts[:3] == ('shell', 'input', 'tap'):
            if int(parts[4]) == 60:
                self.input_focused = True
            elif int(parts[4]) == 110:
                self.saved = self.input
            else:
                raise AssertionError('unexpected bounds-derived tap')
            return ''
        if parts[:3] == ('shell', 'input', 'text'):
            self.input = parts[3]
            return ''
        if parts[:3] == ('shell', 'am', 'force-stop'):
            self.running = False
            return ''
        if parts[0] == 'uninstall':
            self.installed = False
            return 'Success\n'
        if parts[:3] == ('shell', 'rm', '-f'):
            self.dumps.pop(parts[3], None)
            return ''
        raise AssertionError(f'unexpected transport command {parts!r}')

    def xml(self):
        return ('<hierarchy>' + ''.join(
            f'<node package="{gate.PACKAGE}" resource-id="{gate.PACKAGE}:id/{name}" '
            f'text="{text}" enabled="true" focused="{focused}" bounds="{bounds}"/>'
            for name, text, focused, bounds in (
                ('saved_value', 'SAVED:' + self.saved, 'false', '[0,0][100,30]'),
                ('input_value', self.input, str(self.input_focused).lower(), '[0,40][100,80]'),
                ('save_button', 'SAVE', 'false', '[0,90][100,130]'))) + '</hierarchy>')


class PhysicalSmokeTests(unittest.TestCase):
    def run_fixture(self, **options):
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / 'fixture.apk'
            apk.write_bytes(b'FAKE APK: offline transport test only')
            digest = gate.build.checksum(apk)
            args = SimpleNamespace(serial='fixture-usb', user=0,
                expected_fingerprint='fixture/android/37', expected_apk_sha256=digest)
            adb = FakeAdb(digest, **options)
            report = {'android_application_smoke_qualified': False}
            gate.lifecycle(adb, args, apk, report)
            return report, adb

    def test_original_app_lifecycle_and_identity_bound_cleanup(self):
        report, adb = self.run_fixture()
        self.assertEqual(report['status'], 'application_smoke_passed', report)
        self.assertTrue(report['android_application_smoke_qualified'])
        self.assertEqual(report['cleanup'], 'removed_verified_new_install')
        self.assertEqual(adb.launches, 2)
        self.assertEqual(adb.saved, gate.VALUE)
        installs = [call for call in adb.calls if call[0] == 'install']
        self.assertEqual(installs[0][1:3], ('--user', '0'))
        self.assertNotIn('-r', installs[0])
        self.assertFalse(any('clear' in call or 'logcat' in call or 'reboot' in call for call in adb.calls))
        dump_paths = [call[3] for call in adb.calls if call[:3] == ('shell', 'uiautomator', 'dump')]
        self.assertEqual(len(dump_paths), len(set(dump_paths)))
        self.assertFalse(adb.installed)

    def test_wrong_fingerprint_user_locked_or_old_data_prevents_install(self):
        for options in ({'fingerprint': 'different'}, {'user': '10'},
                        {'locked': True}, {'package_before': True}):
            with self.subTest(options=options):
                report, adb = self.run_fixture(**options)
                self.assertEqual(report['status'], 'failed')
                self.assertFalse(any(call[0] in ('install', 'uninstall') or
                                     call[:2] == ('shell', 'input') for call in adb.calls))

    def test_foreign_focus_blocks_any_input_but_cleans_own_new_package(self):
        report, adb = self.run_fixture(focus=False)
        self.assertEqual(report['status'], 'failed')
        self.assertIn('focus', report['error'])
        self.assertFalse(any(call[:2] == ('shell', 'input') for call in adb.calls))
        self.assertEqual(report['cleanup'], 'removed_verified_new_install')

    def test_concurrent_apk_replacement_refuses_effect_and_cleanup(self):
        report, adb = self.run_fixture(replace=True)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['cleanup'], 'refused_or_failed')
        self.assertFalse(any(call[0] == 'uninstall' or call[:2] == ('shell', 'input') for call in adb.calls))

    def test_dump_failure_cannot_replay_old_value_marker(self):
        report, adb = self.run_fixture(stale_dump=True)
        self.assertEqual(report['status'], 'failed')
        self.assertIn('fresh UI dump', report['error'])
        self.assertFalse(any(call[:2] == ('exec-out', 'cat') for call in adb.calls))

    def test_coordinates_require_owned_enabled_resource_inside_screen(self):
        node = ET.fromstring(f'<node package="{gate.PACKAGE}" enabled="true" bounds="[0,40][100,80]"/>')
        self.assertEqual(gate.node_center(node, (1224, 2992)), (50, 60))
        for attr, value in (('bounds', '[0,40][2000,80]'), ('package', 'other.app'),
                            ('enabled', 'false')):
            altered = ET.fromstring(ET.tostring(node))
            altered.set(attr, value)
            with self.assertRaises(gate.Refused):
                gate.node_center(altered, (1224, 2992))

    def test_endpoint_is_explicit_loopback_only(self):
        self.assertEqual(gate.endpoint('tcp:127.0.0.1:5061'), 5061)
        for invalid in ('', '5061', 'tcp:0.0.0.0:5037', 'tcp:localhost:5061',
                        'tcp:127.0.0.1:0', 'tcp:127.0.0.1:65536'):
            with self.assertRaises(gate.Refused): gate.endpoint(invalid)

    def test_unknown_lock_state_is_refused(self):
        with self.assertRaises(gate.Refused): gate.unlocked('inputRestricted=false\n')

    def test_protocol_mismatch_never_contacts_device(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'adb'
            executable.write_bytes(b'fake pinned binary')
            args = SimpleNamespace(adb_endpoint='tcp:127.0.0.1:5061', serial='fixture-usb',
                                   adb=executable, expected_adb_sha256=gate.build.checksum(executable))
            recorder = mock.Mock()
            recorder.run.return_value = 'Android Debug Bridge version 1.0.40\n'
            with mock.patch.object(gate, 'existing_server', return_value='0029'):
                with self.assertRaisesRegex(gate.Refused, 'protocol mismatch'):
                    gate.Adb(args, recorder)
            recorder.run.assert_called_once_with([executable, 'version'])

    def test_default_never_constructs_adb(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / 'adb'
            binary.write_bytes(b'fake adb')
            args = ['--build-manifest', str(root / 'build.json'), '--apk', str(root / 'app.apk'),
                    '--adb', str(binary), '--adb-endpoint', 'tcp:127.0.0.1:5061',
                    '--serial', 'fixture-usb', '--expected-fingerprint', 'fixture/android/37',
                    '--user', '0', '--out', str(root / 'evidence')]
            for name in ('manifest', 'apk', 'source', 'certificate'):
                args += ['--expected-' + name + '-sha256', 'a' * 64]
            args += ['--expected-adb-sha256', gate.build.checksum(binary)]
            with mock.patch.object(gate, 'host_gate', return_value={}), \
                    mock.patch.object(gate, 'Adb', side_effect=AssertionError('must not contact ADB')), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(gate.main(args), 0)
            report = json.loads((root / 'evidence/result.json').read_text())
            self.assertEqual(report['status'], 'host_verified_not_executed')
            for field in ('native_asterinas_qualified', 'production_owner_qualified',
                          'mobile_organ_qualified', 'android_application_smoke_qualified'):
                self.assertFalse(report[field])

    def test_manifest_digest_rejects_before_any_tool_or_device(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / 'build.json'
            manifest.write_text('{}')
            recorder = mock.Mock()
            with self.assertRaisesRegex(gate.Refused, 'manifest digest'):
                gate.host_gate(SimpleNamespace(build_manifest=manifest,
                    expected_manifest_sha256='a' * 64), recorder)
            recorder.run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
