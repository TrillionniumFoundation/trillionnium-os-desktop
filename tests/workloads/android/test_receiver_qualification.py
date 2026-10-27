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
    @staticmethod
    def apk_inputs(scratch):
        paths = [Path(scratch) / name for name in ('original.apk', 'candidate.apk')]
        for index, path in enumerate(paths):
            with zipfile.ZipFile(path, 'x') as archive:
                archive.writestr('AndroidManifest.xml', b'\x03\x00\x08\x00fixture manifest')
                archive.writestr('classes.dex', b'dex\n035\0fixture code ' + str(index).encode())
        return paths

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
        with tempfile.TemporaryDirectory() as scratch:
            original, candidate = self.apk_inputs(scratch)
            with patch.object(qualification.build_receiver, 'ORIGINAL_APK_SHA256', qualification.build_receiver.sha(original)), \
                    patch.object(qualification.build_receiver, 'certificates', side_effect=[['a' * 64], ['b' * 64]]), \
                    patch.object(qualification.build_receiver, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'ORIGINAL_SIGNER_IDENTITY_MISMATCH'):
                    qualification.check_apks('/sdk', original, candidate)
            run.assert_not_called()

    def test_added_permission_or_component_fails_manifest_gate(self):
        base = "package: name='local.pocket4.actions.v2' versionCode='2'\n"
        cases = [(base + "uses-permission: name='android.permission.INTERNET'", '.ActionRunner'),
                 (base, '.ActionRunner\n  E: service (line=1)')]
        with tempfile.TemporaryDirectory() as scratch:
            original, candidate = self.apk_inputs(scratch)
            for badging, manifest in cases:
                with self.subTest(manifest=manifest), \
                        patch.object(qualification.build_receiver, 'ORIGINAL_APK_SHA256', qualification.build_receiver.sha(original)), \
                        patch.object(qualification.build_receiver, 'certificates', return_value=['a' * 64]), \
                        patch.object(qualification.build_receiver, 'run', side_effect=[badging, manifest]):
                    with self.assertRaises(ValueError):
                        qualification.check_apks('/sdk', original, candidate)

    def test_same_snapshots_are_inspected_and_reported_after_source_replacement(self):
        with tempfile.TemporaryDirectory() as scratch:
            original, candidate = self.apk_inputs(scratch)
            original_raw, candidate_raw = original.read_bytes(), candidate.read_bytes()
            original_inode, candidate_inode = original.stat().st_ino, candidate.stat().st_ino
            snapshots = []

            def certificates(_tool, path):
                snapshots.append(path)
                self.assertNotIn(path, (original, candidate))
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
                expected = original_raw if path.name == 'original.apk' else candidate_raw
                self.assertEqual(path.read_bytes(), expected)
                if path.name == 'original.apk':
                    # A producer modifies one source and atomically replaces
                    # the other after capture, before later inspections/hash.
                    original.write_bytes(b'a different original path now')
                    replacement = Path(scratch) / 'replacement.apk'
                    replacement.write_bytes(b'unverified replacement candidate')
                    os.replace(replacement, candidate)
                return ['a' * 64]

            def inspect(argv):
                self.assertEqual(argv[3], snapshots[1])
                self.assertEqual(Path(argv[3]).read_bytes(), candidate_raw)
                if argv[2] == 'badging':
                    return "package: name='local.pocket4.actions.v2' versionCode='2'\n"
                self.assertEqual(argv[2], 'xmltree')
                return 'local.pocket4.actions.v2.ActionRunner'

            with patch.object(qualification.build_receiver, 'ORIGINAL_APK_SHA256', hashlib.sha256(original_raw).hexdigest()), \
                    patch.object(qualification.build_receiver, 'certificates', side_effect=certificates), \
                    patch.object(qualification.build_receiver, 'run', side_effect=inspect):
                record = qualification.check_apks('/sdk', original, candidate)
            self.assertEqual(record['original_apk_sha256'], hashlib.sha256(original_raw).hexdigest())
            self.assertEqual(record['candidate_apk_sha256'], hashlib.sha256(candidate_raw).hexdigest())
            self.assertNotEqual(record['candidate_apk_sha256'], qualification.build_receiver.sha(candidate))
            binding = record['apk_input_binding']
            self.assertEqual(binding['original']['source_inode'], original_inode)
            self.assertEqual(binding['candidate']['source_inode'], candidate_inode)
            self.assertEqual(binding['candidate']['sha256'], record['candidate_apk_sha256'])
            self.assertIn('installed package', binding['scope'])
            self.assertTrue(all(not path.exists() for path in snapshots))

    def test_snapshot_rejects_aliases_nonregular_inputs_and_size_bounds(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            path = root / 'candidate.apk'
            path.write_bytes(b'bounded fixture')
            alias = root / 'alias.apk'
            alias.symlink_to(path)
            with self.assertRaises(OSError):
                qualification.apk_snapshot(alias)
            alias.unlink()
            os.link(path, alias)
            with self.assertRaisesRegex(ValueError, 'APK_INPUT_NOT_ONE_REGULAR_FILE'):
                qualification.apk_snapshot(path)
            alias.unlink()
            fifo = root / 'fifo'
            os.mkfifo(fifo)
            for nonregular in (root, fifo):
                with self.subTest(path=nonregular), self.assertRaisesRegex(ValueError, 'APK_INPUT_NOT_ONE_REGULAR_FILE'):
                    qualification.apk_snapshot(nonregular)
            with patch.object(qualification, 'APK_MAX_BYTES', 16):
                for raw in (b'', b'x' * 17):
                    path.write_bytes(raw)
                    with self.assertRaisesRegex(ValueError, 'APK_INPUT_SIZE_UNQUALIFIED'):
                        qualification.apk_snapshot(path)
                path.write_bytes(b'x' * 16)
                self.assertEqual(qualification.apk_snapshot(path)[0], b'x' * 16)

    def test_changes_during_held_fd_read_fail_closed(self):
        real_fstat = os.fstat
        for change in ('truncate', 'same-size', 'timestamp', 'replacement'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as scratch:
                path = Path(scratch) / 'candidate.apk'
                path.write_bytes(b'fixture bytes')
                before = path.stat()
                calls = 0

                def fstat(fd):
                    nonlocal calls
                    calls += 1
                    if calls == 2:
                        if change == 'truncate':
                            path.write_bytes(b'x')
                        elif change == 'same-size':
                            path.write_bytes(b'z' * before.st_size)
                            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000))
                        elif change == 'timestamp':
                            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000))
                        else:
                            replacement = Path(scratch) / 'replacement.apk'
                            replacement.write_bytes(b'replacement')
                            os.replace(replacement, path)
                    return real_fstat(fd)

                with patch.object(qualification.os, 'fstat', side_effect=fstat):
                    with self.assertRaisesRegex(ValueError, 'APK_CHANGED_DURING_SNAPSHOT'):
                        qualification.apk_snapshot(path)

    def test_original_pin_failure_precedes_external_inspection(self):
        with tempfile.TemporaryDirectory() as scratch:
            original, candidate = self.apk_inputs(scratch)
            with patch.object(qualification.build_receiver, 'ORIGINAL_APK_SHA256', '0' * 64), \
                    patch.object(qualification.build_receiver, 'certificates') as certificates, \
                    patch.object(qualification.build_receiver, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'ORIGINAL_APK_PIN_MISMATCH'):
                    qualification.check_apks('/sdk', original, candidate)
            certificates.assert_not_called()
            run.assert_not_called()

    def test_failed_signature_verification_cleans_private_snapshots(self):
        with tempfile.TemporaryDirectory() as scratch:
            original, candidate = self.apk_inputs(scratch)
            snapshots = []

            def reject(_tool, path):
                snapshots.append(path)
                raise RuntimeError('actual signature verifier failed')

            with patch.object(qualification.build_receiver, 'ORIGINAL_APK_SHA256', qualification.build_receiver.sha(original)), \
                    patch.object(qualification.build_receiver, 'certificates', side_effect=reject), \
                    patch.object(qualification.build_receiver, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'signature verifier failed'):
                    qualification.check_apks('/sdk', original, candidate)
            run.assert_not_called()
            self.assertEqual(len(snapshots), 1)
            self.assertFalse(snapshots[0].parent.exists())

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
