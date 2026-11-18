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


class NativeLayoutControls(unittest.TestCase):
    """V3 source controls use inert ZIP/ELF bytes; SDK signature checks are mocked."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='native-layout-source-controls-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.apk = self.root / 'synthetic.zip'
        self.candidate_path = self.root / 'candidate.json'
        self.receipt = self.root / 'receipt.json'
        self.candidate = json.loads(SZZC.read_bytes())
        foreign = self.candidate.pop('cross_arch_shared_libraries')[0]
        self.candidate.update(schema=gate._LAYOUT_SCHEMA, native_abis=['arm64-v8a'])
        self.manifest = b'synthetic manifest; never a signed Android application'
        body = synthetic_shared_elf(2, 62, foreign['soname'])
        foreign.update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest(), entry_point=0)
        self.foreign_path = foreign['path']
        self.empty_path = 'lib/arm64-v8a/libunused_a.so'
        placeholders = [{'path': name, 'kind': 'empty_placeholder', 'bytes': 0,
                         'sha256': hashlib.sha256(b'').hexdigest()}
                        for name in (self.empty_path, 'lib/arm64-v8a/libunused_b.so')]
        self.candidate['native_layout_exceptions'] = sorted([foreign] + placeholders,
                                                           key=lambda item: item['path'])
        self.payloads = {'AndroidManifest.xml': self.manifest, self.foreign_path: body,
                         'lib/arm64-v8a/libordinary.so': synthetic_shared_elf(2, 183, 'libordinary.so')}
        self.payloads.update({pin['path']: b'' for pin in placeholders})
        self.actual = {key: copy.deepcopy(self.candidate[key]) for key in (
            'package', 'version_name', 'version_code', 'version_code_major',
            'native_abis', 'signer_certificate_sha256')}
        self.actual.update(long_version_code=self.candidate['version_code'], split_name=None,
                           uses_splits=[], config_for_split=None, manifest_split_fields=[],
                           signature_verified=True, manifest_binary_sha256=hashlib.sha256(self.manifest).hexdigest())
        self.rewrite_apk()
        self.verify_mock = self.enterContext(patch.object(gate, 'verify', return_value=self.actual))
        self.raw = {key: self.candidate[key] for key in ('package', 'version_name', 'version_code', 'version_code_major')}
        self.raw.update(min_sdk_version='23', target_sdk_version='33')
        self.enterContext(patch.object(gate, 'axml_metadata', return_value=self.raw))

    def rewrite_apk(self):
        with zipfile.ZipFile(self.apk, 'w') as archive:
            for name, body in self.payloads.items():
                archive.writestr(name, body)
        self.candidate['apk'] = {'name': 'base.apk', 'bytes': self.apk.stat().st_size,
                                 'sha256': gate.digest(self.apk)}
        self.actual.update(bytes=self.candidate['apk']['bytes'], sha256=self.candidate['apk']['sha256'])

    def run_gate(self, expected_sha=None):
        raw = (json.dumps(self.candidate) + '\n').encode()
        self.candidate_path.write_bytes(raw)
        return gate.verify_candidate(self.apk, self.root / 'not-real-tools', self.candidate_path,
                                     expected_sha or hashlib.sha256(raw).hexdigest(), self.receipt)

    def rejected(self, pattern):
        with self.assertRaisesRegex(ValueError, pattern):
            self.run_gate()
        self.assertFalse(self.receipt.exists())

    def test_zero_exceptions_bind_plain_elf_without_upgrading_source_or_runtime_trust(self):
        self.candidate['native_layout_exceptions'] = []
        self.payloads = {name: body for name, body in self.payloads.items()
                         if name in ('AndroidManifest.xml', 'lib/arm64-v8a/libordinary.so')}
        self.rewrite_apk()
        out = self.run_gate()
        receipt = json.loads(self.receipt.read_bytes())
        metadata = receipt['binary_metadata']
        self.assertEqual(len(metadata['native_libraries']), 1)
        self.assertEqual(metadata['cross_arch_shared_libraries'], [])
        self.assertEqual(metadata['empty_placeholders'], [])
        self.assertIs(metadata['native_compatibility_qualified'], False)
        self.assertIs(metadata['dispatch_runtime_observed'], False)
        self.assertEqual(receipt['source_observation']['signer_reference_kind'], 'public_historical_candidate')
        self.assertNotIn('publisher_certificate_url', receipt['source_observation'])
        expected = out['application']['expected_input']
        self.assertEqual(set(expected), {'version_code', 'apks', 'source_receipt'})
        self.assertEqual(expected['apks'], [self.candidate['apk']])
        self.assertEqual(expected['source_receipt']['sha256'], gate.digest(self.receipt))
        for obj in (out, receipt):
            for key in ('installed', 'runtime_qualified', 'production_ready'):
                self.assertIs(obj[key], False)

    def test_mixed_layout_counts_only_actual_elf_and_records_every_empty_placeholder(self):
        self.run_gate()
        metadata = json.loads(self.receipt.read_bytes())['binary_metadata']
        self.assertEqual(len(metadata['native_libraries']), 2)
        self.assertEqual(len(metadata['cross_arch_shared_libraries']), 1)
        self.assertEqual(len(metadata['empty_placeholders']), 2)
        empty_paths = {pin['path'] for pin in metadata['empty_placeholders']}
        self.assertFalse(empty_paths & {pin['path'] for pin in metadata['native_libraries']})
        seen = empty_paths | {pin['path'] for pin in metadata['cross_arch_shared_libraries']}
        self.assertEqual(seen, {pin['path'] for pin in self.candidate['native_layout_exceptions']})
        self.assertTrue(all(pin['bytes'] == 0 and pin['sha256'] == gate._EMPTY_SHA256
                            for pin in metadata['empty_placeholders']))
        self.assertIs(metadata['native_compatibility_qualified'], False)
        self.assertIs(metadata['dispatch_runtime_observed'], False)

    def test_missing_extra_and_unlisted_changed_libraries_never_publish(self):
        original = copy.deepcopy(self.payloads)
        for mode in ('missing_foreign', 'missing_empty', 'extra_foreign', 'extra_empty', 'ordinary_changed'):
            with self.subTest(mode=mode):
                self.payloads = copy.deepcopy(original)
                if mode == 'missing_foreign':
                    del self.payloads[self.foreign_path]
                elif mode == 'missing_empty':
                    del self.payloads[self.empty_path]
                elif mode == 'extra_foreign':
                    self.payloads['lib/arm64-v8a/libunlisted.so'] = original[self.foreign_path]
                elif mode == 'extra_empty':
                    self.payloads['lib/arm64-v8a/libunlisted.so'] = b''
                else:
                    self.payloads['lib/arm64-v8a/libordinary.so'] = original[self.foreign_path]
                self.rewrite_apk()
                self.rejected('set is incomplete|Native ELF header differs')

    def test_empty_kind_cannot_hide_nonempty_bytes_or_supply_an_abi_witness(self):
        original_candidate, original_payloads = copy.deepcopy(self.candidate), copy.deepcopy(self.payloads)
        for mode in ('nonempty_placeholder', 'foreign_claimed_empty', 'only_placeholders'):
            with self.subTest(mode=mode):
                self.candidate, self.payloads = copy.deepcopy(original_candidate), copy.deepcopy(original_payloads)
                if mode == 'nonempty_placeholder':
                    self.payloads[self.empty_path] = b'not empty'
                elif mode == 'foreign_claimed_empty':
                    self.candidate['native_layout_exceptions'][0] = {
                        'path': self.foreign_path, 'kind': 'empty_placeholder', 'bytes': 0,
                        'sha256': gate._EMPTY_SHA256}
                else:
                    self.candidate['native_layout_exceptions'] = [pin for pin in self.candidate['native_layout_exceptions']
                                                                 if pin['kind'] == 'empty_placeholder']
                    del self.payloads[self.foreign_path]
                    del self.payloads['lib/arm64-v8a/libordinary.so']
                self.rewrite_apk()
                self.rejected('pinned bytes|placeholders are not ELF')

    def test_schema_rejects_nonliteral_duplicate_unknown_kind_and_legacy_field_mixing(self):
        original = copy.deepcopy(self.candidate)
        mutations = [
            lambda c: c['native_layout_exceptions'][0].update(kind='executable'),
            lambda c: c['native_layout_exceptions'][0].update(path='lib/arm64-v8a/*.so'),
            lambda c: c['native_layout_exceptions'][0].update(path='lib/arm64-v8a/../libother.so'),
            lambda c: c['native_layout_exceptions'].__setitem__(1, copy.deepcopy(c['native_layout_exceptions'][0])),
            lambda c: c['native_layout_exceptions'].reverse(),
            lambda c: c['native_layout_exceptions'][1].update(bytes=False),
            lambda c: c['native_layout_exceptions'][1].update(bytes=1),
            lambda c: c['native_layout_exceptions'][1].update(sha256='0' * 64),
            lambda c: c['native_layout_exceptions'][1].update(elf_type=3),
            lambda c: c.update(native_layout_exceptions={}),
            lambda c: c.update(cross_arch_shared_libraries=[]),
            lambda c: c.update(schema=gate._CANDIDATE_SCHEMA),
            lambda c: c.update(schema=gate._CROSS_ARCH_SCHEMA),
            lambda c: c['source'].update(signer_reference_kind='publisher_certificate'),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                self.candidate = copy.deepcopy(original)
                mutate(self.candidate)
                self.rejected('Candidate|Native-layout|Empty placeholder')
        self.verify_mock.assert_not_called()

    def test_eight_exact_pins_are_allowed_and_a_ninth_is_rejected_before_verification(self):
        foreign = copy.deepcopy(self.candidate['native_layout_exceptions'][0])
        placeholders = [{'path': 'lib/arm64-v8a/libunused_' + str(i) + '.so',
                         'kind': 'empty_placeholder', 'bytes': 0, 'sha256': gate._EMPTY_SHA256}
                        for i in range(7)]
        self.candidate['native_layout_exceptions'] = sorted([foreign] + placeholders, key=lambda item: item['path'])
        self.payloads = {name: body for name, body in self.payloads.items() if body}
        self.payloads.update({pin['path']: b'' for pin in placeholders})
        self.rewrite_apk()
        self.run_gate()
        metadata = json.loads(self.receipt.read_bytes())['binary_metadata']
        self.assertEqual(len(metadata['native_libraries']), 2)
        self.assertEqual(len(metadata['empty_placeholders']), 7)
        self.receipt.unlink()
        ninth = {'path': 'lib/arm64-v8a/libunused_8.so', 'kind': 'empty_placeholder',
                 'bytes': 0, 'sha256': gate._EMPTY_SHA256}
        self.candidate['native_layout_exceptions'].append(ninth)
        self.payloads[ninth['path']] = b''
        self.rewrite_apk()
        self.rejected('at most eight')
        self.verify_mock.assert_called_once()

    def test_foreign_bytes_hash_and_real_structural_fields_are_bound(self):
        original = copy.deepcopy(self.candidate)
        for changes in ({'bytes': 1025}, {'sha256': '0' * 64}, {'elf_class': 1, 'elf_machine': 3},
                        {'soname': 'libdifferent.so'}, {'entry_point': 1}):
            with self.subTest(changes=changes):
                self.candidate = copy.deepcopy(original)
                self.candidate['native_layout_exceptions'][0].update(changes)
                self.rejected('pinned bytes|pinned SHA-256|differs from its pinned')

    def test_repinning_invalid_dynamic_interpreter_type_or_pie_keeps_original_elf_rejection(self):
        original = self.payloads[self.foreign_path]
        for field in ('dynamic', 'interpreter', 'type', 'pie'):
            with self.subTest(field=field):
                body = bytearray(original)
                if field == 'dynamic':
                    struct.pack_into('<Q', body, 64 + 56 + 32, 1)
                elif field == 'interpreter':
                    struct.pack_into('<I', body, 64 + 56, 3)
                elif field == 'type':
                    struct.pack_into('<H', body, 16, 2)
                else:
                    struct.pack_into('<Q', body, 256 + 4 * 16 + 8, 0x08000000)
                self.payloads[self.foreign_path] = bytes(body)
                self.candidate['native_layout_exceptions'][0].update(
                    bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
                self.rewrite_apk()
                self.rejected('dynamic segment|PT_INTERP|ET_DYN|DF_1_PIE')

    def test_v3_still_requires_external_pin_real_verifier_and_manifest_identity(self):
        with self.assertRaisesRegex(ValueError, 'external SHA-256'):
            self.run_gate('0' * 64)
        self.verify_mock.assert_not_called()
        self.assertFalse(self.receipt.exists())
        self.verify_mock.side_effect = ValueError('signature verification failed')
        self.rejected('signature verification failed')
        self.verify_mock.side_effect = None
        self.raw['version_name'] = 'different signed manifest version'
        self.rejected('Binary manifest differs')

    def use_dual_dynamic_layout(self):
        from test_dual_dynamic_elf import sample
        from dual_dynamic_elf import parse_dual_dynamic_shared_library
        body, _ = sample()
        actual = parse_dual_dynamic_shared_library(body)
        pin = self.candidate['native_layout_exceptions'][0]
        pin.update(kind='dual_dynamic_shared_library', bytes=len(body),
                   sha256=hashlib.sha256(body).hexdigest(),
                   **{key: actual[key] for key in ('elf_class', 'elf_machine', 'elf_type',
                       'soname', 'entry_point', 'has_interpreter', 'layout_sha256')})
        self.payloads[self.foreign_path] = body
        self.rewrite_apk()
        return actual

    def test_dual_dynamic_kind_retains_actual_views_and_never_claims_runtime_compatibility(self):
        actual = self.use_dual_dynamic_layout()
        self.run_gate()
        metadata = json.loads(self.receipt.read_bytes())['binary_metadata']
        entry = metadata['cross_arch_shared_libraries'][0]
        self.assertEqual(entry['kind'], 'dual_dynamic_shared_library')
        self.assertEqual(entry['layout'], actual['layout'])
        self.assertEqual(entry['layout_sha256'], actual['layout_sha256'])
        self.assertTrue(entry['layout']['range_overlaps']['declared_full_section_headers'])
        self.assertFalse(entry['layout']['range_overlaps']['declared_consumed_section_headers'])
        self.assertEqual(len(metadata['native_libraries']), 2)
        self.assertEqual(len(metadata['empty_placeholders']), 2)
        self.assertIs(metadata['native_compatibility_qualified'], False)
        self.assertIs(metadata['dispatch_runtime_observed'], False)

    def test_dual_external_layout_pin_and_helper_summary_must_match_canonical_bytes(self):
        actual = self.use_dual_dynamic_layout()
        pin = self.candidate['native_layout_exceptions'][0]
        original_sha = pin['layout_sha256']
        pin['layout_sha256'] = '0' * 64
        self.rejected('pinned canonical layout SHA-256')
        pin['layout_sha256'] = original_sha
        for mode in ('stale_summary', 'changed_layout', 'nonfinite_layout'):
            with self.subTest(mode=mode):
                report = copy.deepcopy(actual)
                if mode == 'stale_summary':
                    report['layout_sha256'] = '0' * 64
                elif mode == 'changed_layout':
                    report['layout']['unexpected_text'] = '布局字段改变'
                else:
                    report['layout']['invalid_number'] = float('nan')
                with patch('dual_dynamic_elf.parse_dual_dynamic_shared_library', return_value=report):
                    self.rejected('pinned canonical layout SHA-256|Out of range float')

    def test_dual_view_cannot_be_relabelled_as_an_ordinary_shared_library(self):
        self.use_dual_dynamic_layout()
        pin = self.candidate['native_layout_exceptions'][0]
        pin['kind'] = 'cross_arch_shared_library'
        pin.pop('layout_sha256')
        self.rejected('Invalid cross-architecture dynamic segment')

    def use_resource_layout(self, kind):
        from test_native_resource_payloads import archive, elf
        from native_resource_payloads import inspect_embedded_7z, inspect_interpreter_tagged_et_dyn
        body = archive() if kind == 'embedded_7z_archive' else elf()
        inspect = inspect_embedded_7z if kind == 'embedded_7z_archive' else inspect_interpreter_tagged_et_dyn
        actual = inspect(body)
        pin = {'path': self.foreign_path, 'kind': kind, 'bytes': len(body),
               'sha256': hashlib.sha256(body).hexdigest(), 'layout_sha256': actual['layout_sha256']}
        if kind == 'interpreter_tagged_et_dyn':
            pin.update({key: actual[key] for key in ('elf_class', 'elf_machine', 'elf_type',
                        'soname', 'entry_point', 'has_interpreter', 'interpreter')})
        self.candidate['native_layout_exceptions'][0] = pin
        self.payloads[self.foreign_path] = body
        self.rewrite_apk()
        return actual

    def test_embedded_archive_is_explicit_and_never_counts_as_native_elf(self):
        actual = self.use_resource_layout('embedded_7z_archive')
        self.run_gate()
        metadata = json.loads(self.receipt.read_bytes())['binary_metadata']
        self.assertEqual(len(metadata['native_libraries']), 1)
        self.assertEqual(metadata['cross_arch_shared_libraries'], [])
        self.assertEqual(len(metadata['empty_placeholders']), 2)
        self.assertEqual(len(metadata['embedded_archives']), 1)
        entry = metadata['embedded_archives'][0]
        self.assertEqual(entry['layout'], actual['layout'])
        self.assertEqual(entry['layout_sha256'], actual['layout_sha256'])
        self.assertIs(entry['native_elf'], False)
        self.assertIs(entry['archive_contents_decoded'], False)
        self.assertIs(entry['archive_contents_verified'], False)
        self.assertNotIn(self.foreign_path, {item['path'] for item in metadata['native_libraries']})
        self.assertIs(metadata['native_compatibility_qualified'], False)
        self.assertIs(metadata['dispatch_runtime_observed'], False)

    def test_archive_wrong_hash_layout_empty_kind_and_missing_elf_never_publish(self):
        self.use_resource_layout('embedded_7z_archive')
        original_candidate, original_payloads = copy.deepcopy(self.candidate), copy.deepcopy(self.payloads)
        for mode in ('payload_hash', 'layout_hash', 'claimed_empty', 'no_elf'):
            with self.subTest(mode=mode):
                self.candidate, self.payloads = copy.deepcopy(original_candidate), copy.deepcopy(original_payloads)
                pin = self.candidate['native_layout_exceptions'][0]
                if mode == 'payload_hash':
                    pin['sha256'] = '0' * 64
                elif mode == 'layout_hash':
                    pin['layout_sha256'] = '0' * 64
                elif mode == 'claimed_empty':
                    self.candidate['native_layout_exceptions'][0] = {
                        'path': self.foreign_path, 'kind': 'empty_placeholder', 'bytes': 0,
                        'sha256': gate._EMPTY_SHA256}
                else:
                    del self.payloads['lib/arm64-v8a/libordinary.so']
                self.rewrite_apk()
                self.rejected('pinned SHA-256|pinned canonical layout|pinned bytes|native libraries are missing')

    def test_interpreter_tagged_et_dyn_is_separate_from_plain_shared_libraries(self):
        actual = self.use_resource_layout('interpreter_tagged_et_dyn')
        self.run_gate()
        metadata = json.loads(self.receipt.read_bytes())['binary_metadata']
        self.assertEqual(len(metadata['native_libraries']), 2)
        self.assertEqual(metadata['cross_arch_shared_libraries'], [])
        self.assertEqual(metadata['embedded_archives'], [])
        self.assertEqual(len(metadata['interpreter_tagged_et_dyn']), 1)
        entry = metadata['interpreter_tagged_et_dyn'][0]
        self.assertEqual(entry['layout'], actual['layout'])
        self.assertEqual(entry['layout_sha256'], actual['layout_sha256'])
        self.assertEqual(entry['interpreter'], '/system/bin/linker')
        self.assertEqual((entry['elf_class'], entry['elf_machine'], entry['elf_type'], entry['entry_point']),
                         (1, 40, 3, 0))
        self.assertIs(entry['has_interpreter'], True)
        self.assertIs(entry['standalone_executable_role_established'], False)
        self.assertIs(metadata['native_compatibility_qualified'], False)
        self.assertIs(metadata['dispatch_runtime_observed'], False)

    def test_interpreter_literal_kind_layout_and_helper_identity_cannot_drift(self):
        actual = self.use_resource_layout('interpreter_tagged_et_dyn')
        original = copy.deepcopy(self.candidate)
        for mode in ('layout', 'literal', 'architecture', 'entry', 'plain_shared'):
            with self.subTest(mode=mode):
                self.candidate = copy.deepcopy(original)
                pin = self.candidate['native_layout_exceptions'][0]
                if mode == 'layout':
                    pin['layout_sha256'] = '0' * 64
                elif mode == 'literal':
                    pin['interpreter'] = '/system/bin/linker64'
                elif mode == 'architecture':
                    pin['elf_machine'] = 3
                elif mode == 'entry':
                    pin['entry_point'] = 1
                else:
                    pin.update(kind='cross_arch_shared_library', has_interpreter=False)
                    pin.pop('interpreter')
                    pin.pop('layout_sha256')
                self.rejected('pinned canonical layout|Interpreter-tagged ET_DYN|PT_INTERP')
        self.candidate = original
        for key, value in (('kind', 'cross_arch_shared_library'), ('bytes', 1), ('sha256', '0' * 64)):
            with self.subTest(helper_key=key):
                report = copy.deepcopy(actual)
                report[key] = value
                with patch('native_resource_payloads.inspect_interpreter_tagged_et_dyn', return_value=report):
                    self.rejected('parser identity differs from its complete payload pin')


class NoNativeCandidateControls(unittest.TestCase):
    """Only this new schema observes absent standard lib files; SDK calls are mocked."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='no-native-source-controls-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.apk = self.root / 'synthetic.zip'
        self.candidate_path = self.root / 'candidate.json'
        self.receipt = self.root / 'receipt.json'
        self.candidate = json.loads(SZZC.read_bytes())
        self.candidate.pop('cross_arch_shared_libraries')
        self.candidate.update(schema=gate._NO_NATIVE_SCHEMA, native_abis=[])
        self.manifest = b'synthetic manifest; no APK signing claim'
        self.entries = [('AndroidManifest.xml', self.manifest),
                        ('classes.dex', b'inert synthetic DEX placeholder'),
                        ('assets/library.so', b'\x7fELF outside the standard lib directory')]
        self.actual = {key: copy.deepcopy(self.candidate[key]) for key in (
            'package', 'version_name', 'version_code', 'version_code_major',
            'native_abis', 'signer_certificate_sha256')}
        self.actual.update(long_version_code=self.candidate['version_code'], split_name=None,
                           uses_splits=[], config_for_split=None, manifest_split_fields=[],
                           signature_verified=True,
                           manifest_binary_sha256=hashlib.sha256(self.manifest).hexdigest())
        self.rewrite_apk()
        self.verify_mock = self.enterContext(patch.object(gate, 'verify', return_value=self.actual))
        self.raw = {key: self.candidate[key] for key in (
            'package', 'version_name', 'version_code', 'version_code_major')}
        self.raw.update(min_sdk_version='23', target_sdk_version='33')
        self.enterContext(patch.object(gate, 'axml_metadata', return_value=self.raw))

    def pin_apk(self):
        self.candidate['apk'] = {'name': 'base.apk', 'bytes': self.apk.stat().st_size,
                                 'sha256': gate.digest(self.apk)}
        self.actual.update(bytes=self.candidate['apk']['bytes'], sha256=self.candidate['apk']['sha256'])

    def rewrite_apk(self):
        with zipfile.ZipFile(self.apk, 'w') as archive:
            for entry, body in self.entries:
                archive.writestr(entry, body)
        self.pin_apk()

    def run_gate(self, expected_sha=None):
        raw = (json.dumps(self.candidate) + '\n').encode()
        self.candidate_path.write_bytes(raw)
        return gate.verify_candidate(self.apk, self.root / 'not-real-tools', self.candidate_path,
                                     expected_sha or hashlib.sha256(raw).hexdigest(), self.receipt)

    def rejected(self, pattern):
        with self.assertRaisesRegex(ValueError, pattern):
            self.run_gate()
        self.assertFalse(self.receipt.exists())

    def test_absent_standard_lib_is_bound_without_claiming_native_code_absence(self):
        for placeholders in ([], [('lib/', b''), ('lib/x86_64/', b'')]):
            with self.subTest(directory_placeholders=bool(placeholders)):
                if self.receipt.exists():
                    self.receipt.unlink()
                self.entries = self.entries[:3] + placeholders
                self.rewrite_apk()
                out = self.run_gate()
                receipt = json.loads(self.receipt.read_bytes())
                metadata = receipt['binary_metadata']
                self.assertEqual(metadata['scope'], 'standard_lib_directory_only')
                self.assertEqual(metadata['native_libraries'], [])
                self.assertEqual(metadata['standard_lib_file_count'], 0)
                self.assertEqual(metadata['directory_placeholders'], sorted(p[0] for p in placeholders))
                for key in ('native_code_absence_proved', 'native_compatibility_qualified',
                            'dispatch_runtime_observed'):
                    self.assertIs(metadata[key], False)
                for obj in (out, receipt):
                    for key in ('installed', 'runtime_qualified', 'production_ready'):
                        self.assertIs(obj[key], False)
                expected = out['application']['expected_input']
                self.assertEqual(set(out['application']), {'package', 'expected_input'})
                self.assertEqual(set(expected), {'version_code', 'apks', 'source_receipt'})
                self.assertEqual(expected['apks'], [self.candidate['apk']])
                self.assertEqual(expected['source_receipt']['sha256'], gate.digest(self.receipt))
                self.assertEqual(receipt['identity'], self.actual)
        self.verify_mock.assert_called_with(self.apk, self.root / 'not-real-tools',
            self.candidate['package'], self.candidate['signer_certificate_sha256'])

    def test_legacy_schemas_reject_empty_abi_and_new_schema_keeps_signer_and_exact_fields(self):
        original = copy.deepcopy(self.candidate)
        for schema in (gate._CANDIDATE_SCHEMA, gate._CROSS_ARCH_SCHEMA, gate._LAYOUT_SCHEMA):
            with self.subTest(legacy=schema):
                value = json.loads((CURRENT if schema == gate._CANDIDATE_SCHEMA else SZZC).read_bytes())
                value.update(schema=schema, native_abis=[])
                if schema == gate._LAYOUT_SCHEMA:
                    value.pop('cross_arch_shared_libraries')
                    value['native_layout_exceptions'] = []
                self.candidate = value
                self.rejected('Invalid or duplicate candidate native_abis')
        for key, value in [('native_abis', ['x86_64']), ('native_abis', False),
                           ('signer_certificate_sha256', []), ('signer_certificate_sha256', ['bad']),
                           ('native_layout_exceptions', []), ('cross_arch_shared_libraries', [])]:
            with self.subTest(key=key, value=value):
                self.candidate = copy.deepcopy(original)
                self.candidate[key] = value
                self.rejected('empty native ABI|candidate signer|fields differ')
        self.verify_mock.assert_not_called()

    def test_any_lib_file_and_nonempty_directory_are_rejected(self):
        original = list(self.entries)
        for name, body in [('lib/x86_64/libpresent.so', b'\x7fELF'),
                           ('lib/x86_64/libempty.so', b''), ('lib/x86_64/readme', b'ordinary'),
                           ('lib/unknown/payload', b'opaque'), ('lib', b''),
                           ('lib/', b'directory data'), ('lib/x86_64/', b'directory data'),
                           ('lib/unknown/', b''), ('lib/x86_64/nested/', b'')]:
            with self.subTest(name=name):
                self.entries = original + [(name, body)]
                self.rewrite_apk()
                self.rejected('standard lib directory|directory entry contains|native directory placeholder')

    def test_ambiguous_paths_and_special_zip_members_are_rejected(self):
        original = list(self.entries)
        for name in ('./lib/x.so', '../lib/x.so', '/lib/x.so', 'lib/../assets/x.so',
                     'lib//x.so', 'lib\\x.so', 'C:/lib/x.so', 'assets/control\nname'):
            with self.subTest(path=name):
                self.entries = original + [(name, b'opaque')]
                self.rewrite_apk()
                self.rejected('invalid ZIP path')
        self.entries = original + [('lib!hidden.so', b'opaque')]
        self.rewrite_apk()
        body = self.apk.read_bytes()
        self.assertEqual(body.count(b'lib!hidden.so'), 2)
        self.apk.write_bytes(body.replace(b'lib!hidden.so', b'lib\x00hidden.so'))
        self.pin_apk()
        self.rejected('invalid ZIP path')
        for name, mode in [('assets/link', 0o120777), ('assets/pipe', 0o010600),
                           ('lib/x86_64/', 0o100644), ('assets/not-directory', 0o040755)]:
            with self.subTest(name=name, mode=mode):
                entry = zipfile.ZipInfo(name)
                entry.create_system = 3
                entry.external_attr = mode << 16
                self.entries = original + [(entry, b'')]
                self.rewrite_apk()
                self.rejected('not a regular file or directory')

    def test_duplicate_members_and_file_directory_aliases_are_rejected(self):
        original = list(self.entries)
        self.entries = original + [('classes.dex', b'other bytes')]
        with self.assertWarnsRegex(UserWarning, 'Duplicate name'):
            self.rewrite_apk()
        self.rejected('Duplicate APK ZIP members')
        self.entries = original + [('assets/alias', b''), ('assets/alias/', b'')]
        self.rewrite_apk()
        self.rejected('file and directory paths alias')

    def test_signature_manifest_sdk_and_complete_identity_remain_required(self):
        self.verify_mock.side_effect = ValueError('real signature verifier failed')
        self.rejected('signature verifier failed')
        self.verify_mock.side_effect = None
        original = copy.deepcopy(self.actual)
        for key, value in [('package', 'org.invalid.app'), ('version_name', 'wrong'),
                           ('version_code', 1), ('sha256', '0' * 64), ('bytes', 1),
                           ('signer_certificate_sha256', ['0' * 64]), ('native_abis', ['x86_64']),
                           ('manifest_binary_sha256', '0' * 64)]:
            with self.subTest(key=key):
                self.actual.update(original)
                self.actual[key] = value
                self.rejected('differs from candidate|manifest changed')
        self.actual.update(original)
        original_raw = copy.deepcopy(self.raw)
        for key, value in [('version_name', 'wrong'), ('version_code', 1),
                           ('min_sdk_version', '19'), ('target_sdk_version', '29')]:
            with self.subTest(binary_manifest_key=key):
                self.raw.update(original_raw)
                self.raw[key] = value
                self.rejected('Binary manifest differs')
        self.raw.update(original_raw)
        self.verify_mock.reset_mock()
        with self.assertRaisesRegex(ValueError, 'external SHA-256'):
            self.run_gate('0' * 64)
        self.verify_mock.assert_not_called()
        self.assertFalse(self.receipt.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
