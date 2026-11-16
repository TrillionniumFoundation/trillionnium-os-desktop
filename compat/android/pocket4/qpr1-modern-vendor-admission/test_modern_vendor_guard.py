"""Run the actual shell guard with only its two external command paths replaced.

The getprop fixture supplies observations; the reboot fixture records the exact
failure argv.  The production guard logic is executed by a real POSIX shell.
No Android service, system property, or reboot command is executed by controls.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
EXPECTED = {
    'ro.vndk.version': '',
    'ro.board.api_level': '202604',
    'ro.board.api_frozen': 'true',
    'ro.vendor.api_level': '202604',
    'ro.product.first_api_level': '37',
    'ro.vendor.build.version.sdk': '37',
    'ro.vendor.build.version.sdk_full': '37.0',
    'ro.build.version.sdk': '37',
    'ro.build.version.sdk_full': '37.1',
    'ro.llndk.api_level': '202604',
    'ro.build.id': 'CP3A.260905.010',
    'ro.build.version.incremental': '16176746',
}


class ModernVendorGuardTests(unittest.TestCase):
    def run_guard(self, properties, failed_key=None):
        source = (HERE / 'qpr1-modern-vendor-guard.sh').read_text()
        with tempfile.TemporaryDirectory(prefix='qpr1-vendor-guard-') as directory:
            root = Path(directory)
            getprop, reboot = root / 'getprop', root / 'reboot'
            fixture = root / 'properties.json'
            fixture.write_text(json.dumps(properties))
            # Use the current interpreter only in the command fixtures, never
            # in the Android production script.
            import sys
            getprop.write_text('#!' + sys.executable + '\n'
                'import json, os, sys\n'
                'if sys.argv[1] == os.environ.get("FAILED_PROPERTY"): sys.exit(7)\n'
                'with open(os.environ["PROPERTY_FIXTURE"]) as stream: p=json.load(stream)\n'
                'print(p.get(sys.argv[1], ""))\n')
            reboot.write_text('#!' + sys.executable + '\n'
                'import json, os, sys\n'
                'with open(os.environ["REBOOT_WITNESS"], "x") as stream:\n'
                ' json.dump(sys.argv[1:], stream)\n')
            getprop.chmod(0o700)
            reboot.chmod(0o700)
            self.assertEqual(source.count('/system/bin/getprop'), 1)
            self.assertEqual(source.count('/system/bin/reboot'), 1)
            substituted = source.replace('/system/bin/getprop', str(getprop)).replace(
                '/system/bin/reboot', str(reboot))
            script = root / 'guard.sh'
            script.write_text(substituted)
            env = dict(os.environ, PROPERTY_FIXTURE=str(fixture),
                       REBOOT_WITNESS=str(root / 'reboot.json'))
            if failed_key is not None:
                env['FAILED_PROPERTY'] = failed_key
            result = subprocess.run(['/bin/sh', str(script)], env=env,
                                    capture_output=True, text=True, timeout=10)
            witness = root / 'reboot.json'
            return result, json.loads(witness.read_text()) if witness.exists() else None

    def assert_rejected(self, properties, failed_key=None):
        result, reboot = self.run_guard(properties, failed_key)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(reboot, ['bootloader'])
        self.assertIn('metadata rejected:', result.stderr)
        self.assertNotIn('metadata accepted:', result.stdout)

    def test_observed_current_tuple_is_accepted(self):
        result, reboot = self.run_guard(EXPECTED)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(reboot)
        self.assertIn('metadata accepted:', result.stdout)

    def test_removed_legacy_property_may_be_absent(self):
        properties = dict(EXPECTED)
        del properties['ro.vndk.version']
        result, reboot = self.run_guard(properties)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(reboot)

    def test_every_required_nonempty_property_remains_required(self):
        for key in EXPECTED:
            if key == 'ro.vndk.version':
                continue
            with self.subTest(key=key):
                properties = dict(EXPECTED)
                del properties[key]
                self.assert_rejected(properties)

    def test_every_value_must_match_the_reviewed_pair(self):
        for key in EXPECTED:
            with self.subTest(key=key):
                self.assert_rejected(dict(EXPECTED, **{key: 'unexpected'}))

    def test_legacy_vndk_value_is_not_a_modern_qualification(self):
        for version in ('34', '37', 'current'):
            with self.subTest(version=version):
                self.assert_rejected(dict(EXPECTED, **{'ro.vndk.version': version}))

    def test_future_vendor_api_and_stale_llndk_are_rejected(self):
        self.assert_rejected(dict(EXPECTED, **{'ro.vendor.api_level': '202704'}))
        self.assert_rejected(dict(EXPECTED, **{'ro.llndk.api_level': '202504'}))

    def test_property_read_failure_is_rejected_even_for_expected_empty(self):
        for key in EXPECTED:
            with self.subTest(key=key):
                self.assert_rejected(EXPECTED, failed_key=key)

    def test_shell_metacharacters_are_data(self):
        self.assert_rejected(dict(EXPECTED, **{'ro.board.api_level': '$(exit 0)'}))

    def test_init_action_is_synchronous_and_keeps_failure_selector(self):
        text = (HERE / 'init.vndk-nodef.rc').read_text()
        actions = [line.strip() for line in text.splitlines()
                   if line.strip() and not line.lstrip().startswith('#')]
        self.assertEqual(actions, [
            'on early-init',
            'exec - root -- /system/bin/sh /vendor/etc/qpr1-modern-vendor-guard.sh',
        ])
        source = (HERE / 'qpr1-modern-vendor-guard.sh').read_text()
        self.assertNotIn('setprop', source)
        self.assertEqual(source.count('/system/bin/reboot bootloader'), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
