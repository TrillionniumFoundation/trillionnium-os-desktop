"""Negative cases for authority selection and false signature success."""
import unittest
import collect_identities01 as c


GOOD = (b'Verifies\nVerified using v1 scheme (JAR signing): false\n'
        b'Verified using v2 scheme (APK Signature Scheme v2): true\n'
        b'Verified using v3 scheme (APK Signature Scheme v3): true\n'
        b'Number of signers: 1\nSigner #1 certificate SHA-256 digest: ' + b'a' * 64 + b'\n')


class ParserBoundaries(unittest.TestCase):
    def test_nonzero_exit_cannot_be_verified_by_stdout(self):
        self.assertTrue(c.signature(GOOD, 0)['verified'])
        for rc in (1, 2, -9, -15):
            self.assertFalse(c.signature(GOOD, rc)['verified'])

    def test_unknown_or_missing_scheme_cannot_pass(self):
        for raw in (b'', b'Verifies\n', b'Permission Denial\n',
                    GOOD.replace(b': true', b': false'), GOOD.replace(b'Verifies\n', b'')):
            self.assertFalse(c.signature(raw, 0)['verified'])

    def test_duplicate_or_missing_signer_cannot_pass(self):
        extra = b'Signer #1 certificate SHA-256 digest: ' + b'b' * 64 + b'\n'
        self.assertFalse(c.signature(GOOD + extra, 0)['verified'])
        self.assertFalse(c.signature(GOOD.replace(b'Number of signers: 1', b'Number of signers: 2'), 0)['verified'])

    def test_active_package_does_not_select_hidden_factory_copy(self):
        raw = b'''Packages:
  Package [com.android.camera2] (abc):
    appId=10062
    codePath=/data/app/owned
    versionCode=20002000 minSdk=37 targetSdk=1000
    versionName=2.0
    primaryCpuAbi=null
    secondaryCpuAbi=null
    User 0: ceDataInode=1 deDataInode=2 installed=true hidden=false suspended=false stopped=false enabled=0
Hidden system packages:
  Package [com.android.camera2] (def):
    appId=10062
    codePath=/system/app/Camera2
    versionCode=1 minSdk=1 targetSdk=1
'''
        v = c.active_identity(raw, 'com.android.camera2')
        self.assertEqual((v['uid'], v['version_code'], v['code_path']), (10062, 20002000, '/data/app/owned'))
        with self.assertRaises(RuntimeError):
            c.active_identity(raw.replace(b'  Package [com.android.camera2]', b'  Package [other.package]', 1), 'com.android.camera2')

    def test_package_and_path_duplicates_rejected(self):
        with self.assertRaises(RuntimeError):
            c.packages(b'package:example.app versionCode:1 uid:10100\n' * 2)
        with self.assertRaises(RuntimeError):
            c.paths(b'package:/data/app/x/base.apk\n' * 2)
        with self.assertRaises(RuntimeError):
            c.paths(b'Error: unknown package\n')

    def test_split_identity_and_abi_are_only_manifest_observations(self):
        row = c.badging(b"package: name='example.app' versionCode='7' versionName='1' split='config.arm64_v8a'\n"
                        b"sdkVersion:'23'\ntargetSdkVersion:'35'\nnative-code: 'arm64-v8a'\n")
        self.assertEqual(row['split_name'], 'config.arm64_v8a')
        self.assertEqual(row['embedded_native_abis'], ['arm64-v8a'])
        self.assertNotIn('engine', row)

    def test_fresh_launcher_unknown_or_missing_rows_rejected(self):
        raw = (b'1 activities found:\n  Activity #0:\n'
               b'    priority=0 preferredOrder=0 match=0x108000 specificIndex=-1 isDefault=false\n'
               b'    example.app/.Main\n')
        self.assertEqual(c.launchers(raw), ['example.app/.Main'])
        for bad in (raw.replace(b'#0', b'#1'), raw.replace(b'isDefault=false', b'unknown=false'), raw.splitlines(keepends=True)[0]):
            with self.assertRaises(RuntimeError):
                c.launchers(bad)


if __name__ == '__main__':
    unittest.main()
