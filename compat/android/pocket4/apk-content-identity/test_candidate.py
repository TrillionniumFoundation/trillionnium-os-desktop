"""Candidate binding controls; real signed-APK verification is a separate local gate."""
from pathlib import Path
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_apk as gate

CURRENT = Path(__file__).resolve().parent.parent / 'current-app-acceptance/firefox-candidate.json'


class CandidateControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='apk-candidate-control-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.apk = self.root / 'input.apk'
        self.apk.write_bytes(b'synthetic input; not an APK signature fixture')
        self.candidate = json.loads(CURRENT.read_bytes())
        self.candidate['apk']['bytes'] = self.apk.stat().st_size
        self.candidate['apk']['sha256'] = gate.digest(self.apk)
        self.candidate_path = self.root / 'candidate.json'
        self.receipt = self.root / 'receipt.json'
        self.verified = {key: copy.deepcopy(self.candidate[key]) for key in (
            'package', 'version_name', 'version_code', 'version_code_major',
            'native_abis', 'signer_certificate_sha256')}
        self.verified.update(self.candidate['apk'])
        self.verified.update(long_version_code=self.candidate['version_code'],
                             split_name=None, uses_splits=[], config_for_split=None,
                             manifest_split_fields=[], signature_verified=True)
        self.verify_mock = self.enterContext(patch.object(gate, 'verify', return_value=self.verified))
        self.enterContext(patch.object(gate, '_candidate_binary_metadata', return_value={}))

    def write_candidate(self):
        raw = (json.dumps(self.candidate) + '\n').encode()
        self.candidate_path.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def run_gate(self, expected_sha=None):
        return gate.verify_candidate(self.apk, self.root / 'tools', self.candidate_path,
                                     expected_sha or self.write_candidate(), self.receipt)

    def assert_no_receipt(self, pattern):
        with self.assertRaisesRegex(ValueError, pattern):
            self.run_gate()
        self.assertFalse(self.receipt.exists())

    def test_native_fragment_and_receipt_are_exactly_bound(self):
        out = self.run_gate()
        application = out['application']
        self.assertEqual(set(application), {'package', 'expected_input'})
        expected = application['expected_input']
        self.assertEqual(set(expected), {'version_code', 'apks', 'source_receipt'})
        self.assertEqual(expected['version_code'], 2016196678)
        self.assertEqual(expected['apks'], [self.candidate['apk']])
        raw = self.receipt.read_bytes()
        self.assertEqual(expected['source_receipt'], {'path': str(self.receipt),
                         'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
        receipt = json.loads(raw)
        self.assertEqual(receipt['identity'], self.verified)
        self.assertEqual(receipt['source_observation'], self.candidate['source'])
        for obj in (out, receipt):
            for key in ('installed', 'runtime_qualified', 'production_ready'):
                self.assertIs(obj[key], False)
        self.verify_mock.assert_called_once_with(self.apk, self.root / 'tools',
            self.candidate['package'], self.candidate['signer_certificate_sha256'])

    def test_wrong_package_version_hash_signer_and_abi_publish_nothing(self):
        changes = [('package', 'org.invalid.example'), ('version_name', '159.0.1'),
                   ('version_code', 2016193998), ('version_code_major', 1),
                   ('sha256', '0' * 64), ('bytes', 1),
                   ('signer_certificate_sha256', ['b' * 64]), ('native_abis', ['arm64-v8a'])]
        before = copy.deepcopy(self.verified)
        for key, value in changes:
            with self.subTest(key=key):
                self.verified.update(before)
                self.verified[key] = value
                self.assert_no_receipt('differs from candidate')

    def test_failed_real_verifier_cannot_publish(self):
        self.verify_mock.side_effect = ValueError('signature verification failed')
        self.assert_no_receipt('signature verification failed')

    def test_split_declarations_cannot_become_one_base_input(self):
        for key, value in [('split_name', 'config.x86_64'), ('uses_splits', ['feature']),
                           ('config_for_split', 'base'), ('manifest_split_fields', ['isSplitRequired=true'])]:
            with self.subTest(key=key):
                old = self.verified[key]
                self.verified[key] = value
                self.assert_no_receipt('standalone base APK')
                self.verified[key] = old

    def test_external_candidate_pin_precedes_apk_verification(self):
        self.write_candidate()
        with self.assertRaisesRegex(ValueError, 'external SHA-256'):
            self.run_gate('0' * 64)
        self.verify_mock.assert_not_called()
        self.assertFalse(self.receipt.exists())

    def test_strict_candidate_schema_rejects_duplicate_keys_and_bad_types(self):
        valid = copy.deepcopy(self.candidate)
        for key, value in [('version_code', True), ('version_code_major', -1),
                           ('native_abis', ['x86_64', 'x86_64']), ('extra', 'ignored')]:
            with self.subTest(key=key):
                self.candidate = copy.deepcopy(valid)
                self.candidate[key] = value
                self.assert_no_receipt('candidate|Candidate')
        self.candidate = valid
        self.write_candidate()
        raw = self.candidate_path.read_bytes().replace(b'{', b'{"schema":"duplicate",', 1)
        self.candidate_path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.run_gate(hashlib.sha256(raw).hexdigest())
        self.verify_mock.assert_not_called()

    def test_existing_receipt_and_changed_source_are_rejected(self):
        self.receipt.write_bytes(b'original receipt')
        self.assert_no_receipt_if_existing()
        self.receipt.unlink()
        def changed(*args):
            self.apk.write_bytes(b'changed after inspection')
            return self.verified
        self.verify_mock.side_effect = changed
        self.assert_no_receipt('changed before receipt')

    def assert_no_receipt_if_existing(self):
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.run_gate()
        self.assertEqual(self.receipt.read_bytes(), b'original receipt')
        self.verify_mock.assert_not_called()

    def test_cli_requires_all_candidate_flags_without_legacy_flags(self):
        command = [sys.executable, '-B', str(Path(gate.__file__)), str(self.apk),
                   '--build-tools', str(self.root / 'tools'), '--candidate', str(CURRENT)]
        for extra in ([], ['--expect-candidate-sha256', 'a' * 64,
                           '--receipt-output', str(self.receipt), '--expected-package', 'legacy.example']):
            with self.subTest(extra=extra):
                result = subprocess.run(command + extra, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 2)
                self.assertIn('together, without legacy', result.stderr)
                self.assertEqual(result.stdout, '')


class BinaryCandidateControls(unittest.TestCase):
    def test_binary_version_sdk_and_actual_elf_abi_must_agree(self):
        candidate = json.loads(CURRENT.read_bytes())
        manifest = b'synthetic binary manifest; parser is mocked here'
        raw = {key: candidate[key] for key in ('package', 'version_name', 'version_code', 'version_code_major')}
        raw.update(min_sdk_version='26', target_sdk_version='37')
        header = bytearray(20)
        header[:7] = b'\x7fELF\x02\x01\x01'
        header[18:20] = (62).to_bytes(2, 'little')
        result = {'manifest_binary_sha256': hashlib.sha256(manifest).hexdigest()}
        with tempfile.TemporaryDirectory(prefix='apk-binary-candidate-') as temporary:
            apk = Path(temporary) / 'synthetic.zip'
            def write():
                with zipfile.ZipFile(apk, 'w') as archive:
                    archive.writestr('AndroidManifest.xml', manifest)
                    archive.writestr('lib/x86_64/test.so', header)
            write()
            with patch.object(gate, 'axml_metadata', return_value=raw):
                observed = gate._candidate_binary_metadata(apk, result, candidate)
                self.assertEqual(observed['native_libraries'][0]['elf_machine'], 62)
                for key, value in [('version_name', '159.0.1'), ('min_sdk_version', '25'),
                                   ('target_sdk_version', '36')]:
                    with self.subTest(key=key):
                        before = raw[key]
                        raw[key] = value
                        with self.assertRaisesRegex(ValueError, 'Binary manifest differs'):
                            gate._candidate_binary_metadata(apk, result, candidate)
                        raw[key] = before
                header[18:20] = (183).to_bytes(2, 'little')
                write()
                with self.assertRaisesRegex(ValueError, 'ELF header'):
                    gate._candidate_binary_metadata(apk, result, candidate)


if __name__ == '__main__':
    unittest.main(verbosity=2)
