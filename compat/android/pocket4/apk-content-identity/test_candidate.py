"""Candidate binding controls; real signed-APK verification is a separate local gate."""
from pathlib import Path
import copy
import hashlib
import json
import subprocess
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_apk as gate

CURRENT = Path(__file__).resolve().parent.parent / 'current-app-acceptance/firefox-candidate.json'
SZZC = Path(__file__).resolve().parent.parent / 'current-app-acceptance/szzc-candidate.json'


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

    def test_neutral_digest_description_keeps_the_real_verifier_and_rejects_unknown_kinds(self):
        self.candidate['source']['sha256_kind'] = 'observed_whole_file_digest'
        self.run_gate()
        self.verify_mock.assert_called_once()
        self.receipt.unlink()
        self.verify_mock.reset_mock()
        self.candidate['source']['sha256_kind'] = 'publisher_checksum_is_automatically_trusted'
        self.assert_no_receipt('digest kind')
        self.verify_mock.assert_not_called()

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


def synthetic_shared_elf(elf_class, machine, soname):
    """An inert ELF-format fixture, never a compiled or executable test payload."""
    body = bytearray(1024)
    body[:7] = b'\x7fELF' + bytes((elf_class, 1, 1))
    header_size, program_size = (64, 56) if elf_class == 2 else (52, 32)
    struct.pack_into('<HHIQQQIHHHHHH' if elf_class == 2 else '<HHIIIIIHHHHHH', body, 16,
                     3, machine, 1, 0, header_size, 0, 0, header_size, program_size, 2, 0, 0, 0)
    strings = b'\0' + soname.encode() + b'\0libc.so\0'
    entries = [(5, 512), (10, len(strings)), (14, 1), (1, len(soname) + 2), (0x6ffffffb, 1), (0, 0)]
    stride = 16 if elf_class == 2 else 8
    if elf_class == 2:
        struct.pack_into('<IIQQQQQQ', body, header_size, 1, 5, 0, 0, 0, len(body), len(body), 4096)
        struct.pack_into('<IIQQQQQQ', body, header_size + program_size, 2, 6, 256, 256, 0,
                         len(entries) * stride, len(entries) * stride, 8)
    else:
        struct.pack_into('<IIIIIIII', body, header_size, 1, 0, 0, 0, len(body), len(body), 5, 4096)
        struct.pack_into('<IIIIIIII', body, header_size + program_size, 2, 256, 256, 0,
                         len(entries) * stride, len(entries) * stride, 6, 4)
    for index, row in enumerate(entries):
        struct.pack_into('<qQ' if elf_class == 2 else '<iI', body, 256 + stride * index, *row)
    body[512:512 + len(strings)] = strings
    return bytes(body)


class CrossArchitectureControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='cross-abi-source-controls-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.apk = self.root / 'synthetic.zip'
        self.candidate_path = self.root / 'candidate.json'
        self.receipt = self.root / 'receipt.json'
        self.candidate = json.loads(SZZC.read_bytes())
        self.manifest = b'synthetic manifest; binary parser is mocked for source controls'
        self.payloads = {'AndroidManifest.xml': self.manifest}
        for pin in self.candidate['cross_arch_shared_libraries']:
            body = synthetic_shared_elf(pin['elf_class'], pin['elf_machine'], pin['soname'])
            pin.update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest(), entry_point=0)
            self.payloads[pin['path']] = body
        self.payloads['lib/arm64-v8a/libordinary.so'] = synthetic_shared_elf(2, 183, 'libordinary.so')
        self.payloads['lib/armeabi-v7a/libordinary.so'] = synthetic_shared_elf(1, 40, 'libordinary.so')
        self.actual = {key: copy.deepcopy(self.candidate[key]) for key in (
            'package', 'version_name', 'version_code', 'version_code_major',
            'native_abis', 'signer_certificate_sha256')}
        self.actual.update(long_version_code=329, split_name=None, uses_splits=[], config_for_split=None,
                           manifest_split_fields=[], signature_verified=True,
                           manifest_binary_sha256=hashlib.sha256(self.manifest).hexdigest())
        self.rewrite_apk()
        self.verify_mock = self.enterContext(patch.object(gate, 'verify', return_value=self.actual))
        raw = {key: self.candidate[key] for key in ('package', 'version_name', 'version_code', 'version_code_major')}
        raw.update(min_sdk_version='23', target_sdk_version='33')
        self.enterContext(patch.object(gate, 'axml_metadata', return_value=raw))

    def rewrite_apk(self):
        with zipfile.ZipFile(self.apk, 'w') as archive:
            for name, body in self.payloads.items():
                archive.writestr(name, body)
        pin = {'name': 'base.apk', 'bytes': self.apk.stat().st_size, 'sha256': gate.digest(self.apk)}
        self.candidate['apk'] = pin
        self.actual.update(bytes=pin['bytes'], sha256=pin['sha256'])

    def run_gate(self):
        raw = (json.dumps(self.candidate) + '\n').encode()
        self.candidate_path.write_bytes(raw)
        return gate.verify_candidate(self.apk, self.root / 'not-real-tools', self.candidate_path,
                                     hashlib.sha256(raw).hexdigest(), self.receipt)

    def rejected(self, pattern):
        with self.assertRaisesRegex(ValueError, pattern):
            self.run_gate()
        self.assertFalse(self.receipt.exists())

    def test_complete_four_shared_library_pins_produce_only_bound_source_identity(self):
        out = self.run_gate()
        metadata = json.loads(self.receipt.read_bytes())['binary_metadata']
        self.assertEqual(len(metadata['native_libraries']), 6)
        self.assertEqual(len(metadata['cross_arch_shared_libraries']), 4)
        self.assertEqual([x['path'] for x in metadata['cross_arch_shared_libraries']],
                         [x['path'] for x in self.candidate['cross_arch_shared_libraries']])
        self.assertEqual({x['elf_machine'] for x in metadata['cross_arch_shared_libraries']}, {3, 62})
        self.assertTrue(all(x['dynamic_needed'] == ['libc.so'] for x in metadata['cross_arch_shared_libraries']))
        self.assertIs(metadata['native_compatibility_qualified'], False)
        self.assertIs(metadata['dispatch_runtime_observed'], False)
        for key in ('installed', 'runtime_qualified', 'production_ready'):
            self.assertIs(out[key], False)
        expected = out['application']['expected_input']
        self.assertEqual(set(expected), {'version_code', 'apks', 'source_receipt'})
        self.assertEqual(expected['apks'], [self.candidate['apk']])
        self.assertEqual(expected['source_receipt']['sha256'], gate.digest(self.receipt))
        self.verify_mock.assert_called_once()

    def test_v1_still_rejects_the_same_cross_architecture_layout(self):
        self.candidate['schema'] = gate._CANDIDATE_SCHEMA
        self.candidate.pop('cross_arch_shared_libraries')
        source = self.candidate['source']
        source['publisher_certificate_url'] = source.pop('signer_reference_url')
        source.pop('signer_reference_kind')
        source.pop('version_metadata_kind')
        self.rejected('Native ELF header differs')

    def test_schema_rejects_extra_missing_duplicate_glob_and_executable_declarations(self):
        original = copy.deepcopy(self.candidate)
        mutations = [
            lambda c: c['cross_arch_shared_libraries'].pop(),
            lambda c: c['cross_arch_shared_libraries'].append(copy.deepcopy(c['cross_arch_shared_libraries'][0])),
            lambda c: c['cross_arch_shared_libraries'].__setitem__(1, copy.deepcopy(c['cross_arch_shared_libraries'][0])),
            lambda c: c['cross_arch_shared_libraries'][0].update(path='lib/arm64-v8a/*.so'),
            lambda c: c['cross_arch_shared_libraries'][0].update(kind='executable'),
            lambda c: c['cross_arch_shared_libraries'][0].update(elf_type=2),
            lambda c: c['cross_arch_shared_libraries'][0].update(has_interpreter=True),
            lambda c: c['cross_arch_shared_libraries'][0].update(bytes=True),
            lambda c: c['cross_arch_shared_libraries'][0].update(entry_point=-1),
            lambda c: c['source'].update(signer_reference_kind='publisher_certificate'),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                self.candidate = copy.deepcopy(original)
                mutate(self.candidate)
                self.rejected('Candidate|Cross-architecture|Invalid cross-architecture')
        self.verify_mock.assert_not_called()

    def test_every_payload_sha_and_byte_count_are_bound_before_publication(self):
        original = copy.deepcopy(self.candidate)
        for index in range(4):
            for key, value in (('sha256', '0' * 64), ('bytes', 1025)):
                with self.subTest(index=index, field=key):
                    self.candidate = copy.deepcopy(original)
                    self.candidate['cross_arch_shared_libraries'][index][key] = value
                    self.rejected('pinned bytes|pinned SHA-256')

    def test_actual_class_machine_soname_and_entry_must_match_the_pin(self):
        original = copy.deepcopy(self.candidate)
        for changes in ({'elf_class': 1, 'elf_machine': 3}, {'soname': 'libdifferent.so'}, {'entry_point': 1}):
            with self.subTest(changes=changes):
                self.candidate = copy.deepcopy(original)
                self.candidate['cross_arch_shared_libraries'][0].update(changes)
                self.rejected('differs from its pinned')

    def replace_first_payload(self, body):
        pin = self.candidate['cross_arch_shared_libraries'][0]
        self.payloads[pin['path']] = bytes(body)
        pin.update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
        self.rewrite_apk()

    def test_repinning_executable_type_interpreter_or_pie_cannot_make_a_shared_library(self):
        original = self.payloads[self.candidate['cross_arch_shared_libraries'][0]['path']]
        for field in ('type', 'interpreter', 'pie'):
            with self.subTest(field=field):
                body = bytearray(original)
                if field == 'type':
                    struct.pack_into('<H', body, 16, 2)
                elif field == 'interpreter':
                    struct.pack_into('<I', body, 64 + 56, 3)
                else:
                    struct.pack_into('<Q', body, 256 + 4 * 16 + 8, 0x08000000)
                self.replace_first_payload(body)
                self.rejected('ET_DYN|PT_INTERP|DF_1_PIE')

    def test_program_and_dynamic_tables_are_bounded_even_with_new_whole_file_pins(self):
        original = self.payloads[self.candidate['cross_arch_shared_libraries'][0]['path']]
        for field in ('program_table', 'segment', 'strings', 'duplicate_soname'):
            with self.subTest(field=field):
                body = bytearray(original)
                if field == 'program_table':
                    struct.pack_into('<Q', body, 32, len(body))
                elif field == 'segment':
                    struct.pack_into('<Q', body, 64 + 32, len(body) + 1)
                elif field == 'strings':
                    struct.pack_into('<Q', body, 256 + 8, len(body) + 1)
                else:
                    struct.pack_into('<qQ', body, 256 + 3 * 16, 14, 1)
                self.replace_first_payload(body)
                self.rejected('table|segment|pointer|Duplicate')

    def test_actual_cross_architecture_set_is_exact_and_other_libraries_stay_strict(self):
        original = copy.deepcopy(self.payloads)
        first = self.candidate['cross_arch_shared_libraries'][0]['path']
        for mode in ('missing', 'extra', 'ordinary_changed'):
            with self.subTest(mode=mode):
                self.payloads = copy.deepcopy(original)
                if mode == 'missing':
                    del self.payloads[first]
                elif mode == 'extra':
                    self.payloads['lib/arm64-v8a/libunexpected.so'] = original[first]
                else:
                    self.payloads['lib/arm64-v8a/libordinary.so'] = original[first]
                self.rewrite_apk()
                self.rejected('set is incomplete|Native ELF header differs')


if __name__ == '__main__':
    unittest.main(verbosity=2)
