"""Synthetic artifact identity tests; no real APK or Cuttlefish is built."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[3] / 'support/android/run_verified_apks.py'
spec = importlib.util.spec_from_file_location('verified_apks', SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class VerifiedArtifactsTests(unittest.TestCase):
    def build_fixture(self, td):
        td = Path(td)
        out = td / 'aosp/out/target/product/vsoc_x86_64'
        out.mkdir(parents=True)
        artifacts = {}
        for key, (pkg, module) in mod.PKGS.items():
            apk = out / (module + '.apk')
            with zipfile.ZipFile(apk, 'w') as archive:
                archive.writestr('classes.dex', b'dex\n035\0')
                if key == 'x86_64_jni':
                    header = bytearray(64)
                    header[:4] = b'\x7fELF'
                    header[4] = 2
                    header[5] = 1
                    header[18:20] = (62).to_bytes(2, 'little')
                    archive.writestr('lib/x86_64/liba08jni.so', bytes(header))
            artifacts[key] = {'path': str(apk), 'sha256': mod.digest(apk)}
        manifest = td / 'smoke-apk-artifacts.json'
        record = {'status': 'artifacts_verified_NOT_installed_or_executed',
                  'target_kernel': 'Linux Cuttlefish reference, NOT Asterinas',
                  **artifacts}
        manifest.write_text(json.dumps(record))
        aapt2 = td / 'aapt2'
        # Mock host tool accepts the same argv shape, testing identity handling.
        aapt2.write_text(
            '#!/usr/bin/env python3\nimport sys\n'
            'n="org.trillionnium.a08native" if "Native" in sys.argv[-1] '
            'else "org.trillionnium.a08smoke"\n'
            'print(f"package: name=\'{n}\' versionCode=\'1\' versionName=\'1.0\'")\n')
        aapt2.chmod(0o755)
        return manifest, td / 'aosp', aapt2

    def test_positive_fixture_is_only_artifact_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, root, aapt2 = self.build_fixture(td)
            result = mod.validate_artifacts(manifest, root, aapt2)
            self.assertEqual(result['scope'], 'artifact_provenance_only')
            self.assertFalse(result['android_runtime_passed'])
            self.assertFalse(result['asterinas_runtime_passed'])
            self.assertEqual(len(result['artifacts']), 2)

    def test_hash_tamper_fails(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, root, aapt2 = self.build_fixture(td)
            data = json.loads(manifest.read_text())
            Path(data['dex_only']['path']).write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
                mod.validate_artifacts(manifest, root, aapt2)

    def test_wrong_kernel_scope_refused(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, root, aapt2 = self.build_fixture(td)
            data = json.loads(manifest.read_text())
            data['target_kernel'] = 'Asterinas claims'
            manifest.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'kernel scope'):
                mod.validate_artifacts(manifest, root, aapt2)

    def test_swapped_artifacts_rejected_by_package_identity(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, root, aapt2 = self.build_fixture(td)
            data = json.loads(manifest.read_text())
            data['dex_only'], data['x86_64_jni'] = data['x86_64_jni'], data['dex_only']
            manifest.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'DEX-only artifact|package/version mismatch'):
                mod.validate_artifacts(manifest, root, aapt2)

    def test_escape_outside_build_out_is_forbidden(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, root, aapt2 = self.build_fixture(td)
            data = json.loads(manifest.read_text())
            malicious = Path(td) / 'untrusted.apk'
            malicious.write_bytes(b'evil')
            data['dex_only']['path'] = str(malicious)
            data['dex_only']['sha256'] = mod.digest(malicious)
            manifest.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'AOSP out tree'):
                mod.validate_artifacts(manifest, root, aapt2)

    def test_missing_artifact_and_invalid_badging(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, root, aapt2 = self.build_fixture(td)
            data = json.loads(manifest.read_text())
            del data['x86_64_jni']
            manifest.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'missing required artifact'):
                mod.validate_artifacts(manifest, root, aapt2)
            self.assertRaises(ValueError, mod.parse_badging, "package: name='wrong'")

    def test_native_elf_machine_must_be_x86_64(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, root, aapt2 = self.build_fixture(td)
            data = json.loads(manifest.read_text())
            apk = Path(data['x86_64_jni']['path'])
            header = bytearray(64)
            header[:4] = b'\x7fELF'
            header[4] = 2
            header[5] = 1
            header[18:20] = (183).to_bytes(2, 'little')
            with zipfile.ZipFile(apk, 'w') as archive:
                archive.writestr('classes.dex', b'dex\n035\0')
                archive.writestr('lib/x86_64/liba08jni.so', bytes(header))
            data['x86_64_jni']['sha256'] = mod.digest(apk)
            manifest.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'ELF64'):
                mod.validate_artifacts(manifest, root, aapt2)

    def test_dex_only_artifact_cannot_embed_native_lib(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, root, aapt2 = self.build_fixture(td)
            data = json.loads(manifest.read_text())
            apk = Path(data['dex_only']['path'])
            with zipfile.ZipFile(apk, 'w') as archive:
                archive.writestr('classes.dex', b'dex\n035\0')
                archive.writestr('lib/x86_64/unexpected.so', b'\x7fELF')
            data['dex_only']['sha256'] = mod.digest(apk)
            manifest.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'DEX-only artifact'):
                mod.validate_artifacts(manifest, root, aapt2)

    def test_cli_check_only_no_adb(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, root, aapt2 = self.build_fixture(td)
            output = Path(td) / 'evidence'
            rc = mod.main(['--manifest', str(manifest), '--aosp-root', str(root),
                           '--aapt2', str(aapt2), '--check-only', '--out', str(output)])
            self.assertEqual(rc, 0)
            record = json.loads((output / 'result.json').read_text())
            self.assertEqual(record['status'], 'artifacts_verified_no_guest_execution')
            self.assertFalse(record['android_runtime_passed'])

    def test_cli_guest_execution_requires_launch_preflight(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, root, aapt2 = self.build_fixture(td)
            output = Path(td) / 'evidence'
            rc = mod.main(['--manifest', str(manifest), '--aosp-root', str(root),
                           '--aapt2', str(aapt2), '--serial', 'cf-test-only',
                           '--out', str(output)])
            self.assertEqual(rc, 1)
            record = json.loads((output / 'result.json').read_text())
            self.assertEqual(record['status'], 'blocked_or_failed')
            self.assertIn('preflight-evidence', record['error'])
            self.assertFalse((output / 'framework-runner.log').exists())

    def test_cli_forwards_same_preflight_to_both_apk_runners(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, root, aapt2 = self.build_fixture(td)
            output = Path(td) / 'evidence'
            preflight = Path(td) / 'cuttlefish-launch-preflight.json'
            preflight.write_text('{}\n')
            calls = []

            def fake_run(argv, **kwargs):
                calls.append(argv)
                if argv[0] == str(aapt2):
                    package = ('org.trillionnium.a08native'
                               if 'Native' in argv[-1] else 'org.trillionnium.a08smoke')
                    return subprocess.CompletedProcess(
                        argv, 0,
                        stdout=f"package: name='{package}' versionCode='1' versionName='1.0'\n",
                        stderr='')
                return subprocess.CompletedProcess(argv, 0,
                                                   stdout='runner ok\n', stderr='')

            with patch.object(mod.subprocess, 'run', side_effect=fake_run):
                rc = mod.main(['--manifest', str(manifest), '--aosp-root', str(root),
                               '--aapt2', str(aapt2), '--serial', 'cf-test-only',
                               '--preflight-evidence', str(preflight), '--out', str(output)])
            self.assertEqual(rc, 0)
            runner_calls = [call for call in calls if len(call) > 1 and
                            call[1].endswith(('run_apk.py', 'run_native_apk.py'))]
            self.assertEqual(len(runner_calls), 2)
            apk_calls = runner_calls
            for call in apk_calls:
                self.assertIn('--preflight-evidence', call)
                self.assertIn(str(preflight.resolve()), call)


if __name__ == '__main__':
    unittest.main()
