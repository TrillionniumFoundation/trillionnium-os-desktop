"""Qualification gates with synthetic file/certificate metadata; no Android."""

import hashlib
import os
from pathlib import Path
import tempfile
import types
import unittest
import zipfile
from unittest.mock import patch

from support.android.receiver import qualify_receiver as qualification


class QualificationTests(unittest.TestCase):
    def test_unsigned_repack_preserves_binary_manifest_and_resources_exactly(self):
        with tempfile.TemporaryDirectory() as scratch:
            source, dex, output = [Path(scratch) / name for name in ('original.apk', 'classes.dex', 'unsigned.apk')]
            entries = {'AndroidManifest.xml': b'\x03\x00\x08\x00binary fixture manifest',
                       'classes.dex': b'dex\n035\0old fixture code',
                       'assets/data.bin': b'\0unchanged\xff', 'META-INF/LICENSE': b'preserve license',
                       'META-INF/CERT.SF': b'old signature', 'META-INF/CERT.RSA': b'old certificate',
                       'META-INF/MANIFEST.MF': b'old manifest digests'}
            with zipfile.ZipFile(source, 'x') as archive:
                for name, content in entries.items():
                    archive.writestr(name, content)
            replacement = b'dex\n035\0new fixture code'
            dex.write_bytes(replacement)
            with patch.object(qualification.build_receiver, 'ORIGINAL_APK_SHA256', qualification.build_receiver.sha(source)):
                report = qualification.build_receiver.repack_original_apk(source, dex, output)
            with zipfile.ZipFile(output) as result:
                self.assertEqual(set(result.namelist()), {'AndroidManifest.xml', 'classes.dex', 'assets/data.bin', 'META-INF/LICENSE'})
                for name in ('AndroidManifest.xml', 'assets/data.bin', 'META-INF/LICENSE'):
                    self.assertEqual(result.read(name), entries[name])
                self.assertEqual(result.read('classes.dex'), replacement)
            self.assertFalse(report['old_signatures_retained'])
            self.assertFalse(qualification.build_receiver.signing_block_present(output))

    def test_unpinned_apk_and_invalid_replacement_do_not_produce_a_candidate(self):
        with tempfile.TemporaryDirectory() as scratch:
            source, dex, output = [Path(scratch) / name for name in ('original.apk', 'classes.dex', 'unsigned.apk')]
            source.write_bytes(b'not the original package')
            dex.write_bytes(b'dex\n035\0fixture')
            with self.assertRaisesRegex(ValueError, 'original APK pin mismatch'):
                qualification.build_receiver.repack_original_apk(source, dex, output)
            self.assertFalse(output.exists())
            dex.write_bytes(b'not dex')
            with patch.object(qualification.build_receiver, 'ORIGINAL_APK_SHA256', qualification.build_receiver.sha(source)):
                with self.assertRaisesRegex(ValueError, 'invalid replacement dex'):
                    qualification.build_receiver.repack_original_apk(source, dex, output)
            self.assertFalse(output.exists())

    def test_candidate_with_different_original_signer_cannot_qualify(self):
        with patch.object(qualification.build_receiver, 'sha', return_value=qualification.build_receiver.ORIGINAL_APK_SHA256), \
                patch.object(qualification.build_receiver, 'certificates', side_effect=[['a' * 64], ['b' * 64]]), \
                patch.object(qualification.build_receiver, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'ORIGINAL_SIGNER_IDENTITY_MISMATCH'):
                qualification.check_apks('/sdk', '/original.apk', '/candidate.apk')
        run.assert_not_called()

    def test_added_permission_or_component_fails_manifest_gate(self):
        base = "package: name='local.pocket4.actions.v2' versionCode='2'\n"
        cases = [(base + "uses-permission: name='android.permission.INTERNET'", '.ActionRunner'),
                 (base, '.ActionRunner\n  E: service (line=1)')]
        for badging, manifest in cases:
            with self.subTest(manifest=manifest), \
                    patch.object(qualification.build_receiver, 'sha', return_value=qualification.build_receiver.ORIGINAL_APK_SHA256), \
                    patch.object(qualification.build_receiver, 'certificates', return_value=['a' * 64]), \
                    patch.object(qualification.build_receiver, 'run', side_effect=[badging, manifest]):
                with self.assertRaises(ValueError):
                    qualification.check_apks('/sdk', '/original.apk', '/candidate.apk')

    def test_installed_probe_never_elevates_when_original_capability_is_absent(self):
        with patch.object(qualification.os, 'geteuid', return_value=1000), \
                patch.object(qualification, 'check_apks') as check:
            with self.assertRaisesRegex(ValueError, 'ORIGINAL_ROOT_INSPECTION_CAPABILITY_REQUIRED'):
                qualification.installed(types.SimpleNamespace())
        check.assert_not_called()

    def test_file_pin_rejects_drift_wrong_owner_and_symlink(self):
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / 'helper'
            raw = b'reviewed fixture bytes'
            path.write_bytes(raw)
            path.chmod(0o755)
            digest = hashlib.sha256(raw).hexdigest()
            self.assertEqual(qualification.pinned_file(path, digest, os.geteuid()), raw)
            with self.assertRaises(ValueError):
                qualification.pinned_file(path, digest, os.geteuid() + 1)
            path.write_bytes(b'changed bytes')
            with self.assertRaisesRegex(ValueError, 'TOOL_PIN_MISMATCH'):
                qualification.pinned_file(path, digest, os.geteuid())
            alias = Path(scratch) / 'alias'
            alias.symlink_to(path)
            with self.assertRaises(OSError):
                qualification.pinned_file(alias, digest, os.geteuid())


if __name__ == '__main__':
    unittest.main()
