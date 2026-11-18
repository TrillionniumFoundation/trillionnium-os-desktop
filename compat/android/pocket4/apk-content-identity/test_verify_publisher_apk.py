"""V4 negative controls. SDK calls are mocked; these tests grant no real APK credit."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import struct
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_publisher_apk as gate


def sha(data):
    return hashlib.sha256(data).hexdigest()


def archive(entries):
    output = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as z:
            for name, data in entries:
                z.writestr(name, data)
    return output.getvalue()


def elf_header():
    data = bytearray(64)
    data[:7] = b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HHI', data, 16, 3, 183, 1)
    return bytes(data)


def pin(data, path, package='org.example.fixture', kind='embedded_zip_v1'):
    observed = gate.inspect_payload(data, path, package, kind)
    return {'path': path, 'format': kind, 'bytes': len(data), 'sha256': sha(data),
            'observation_sha256': gate.observation_sha256(observed)}


class PublisherGateControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='publisher-controls-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.apk, self.cpath, self.receipt = (self.root / name for name in ('input.apk', 'candidate.json', 'receipt.json'))
        self.manifest = b'AXML parser fixture; deliberately not a real binary manifest'
        self.plugin_name = 'lib/arm64-v8a/libplugin.so'
        self.plugin = archive([('classes.dex', b'inert test member')])
        self.entries = [('AndroidManifest.xml', self.manifest),
                        ('lib/arm64-v8a/libregular.so', elf_header()),
                        (self.plugin_name, self.plugin)]
        self.candidate = {'schema': gate.SCHEMA, 'package': 'org.example.fixture',
                          'version_name': '1.0', 'version_code': 1, 'version_code_major': 0,
                          'min_sdk_version': 23, 'target_sdk_version': 35,
                          'native_abis': ['arm64-v8a'], 'signer_certificate_sha256': ['a' * 64],
                          'publisher_payloads': [pin(self.plugin, self.plugin_name)],
                          'source': {'apk_url': 'https://mirror.example/input.apk',
                                     'version_metadata_url': 'https://mirror.example/current',
                                     'signer_reference_url': 'https://publisher.example/signer',
                                     'signer_reference_kind': 'public_historical_candidate',
                                     'version_metadata_kind': 'signed_apk_android_manifest',
                                     'distribution': 'public_mirror',
                                     'observed_utc': '2026-11-18T12:00:00+00:00',
                                     'observed_stable_version': '1.0',
                                     'sha256_kind': 'observed_whole_file_digest'}}
        self.write_apk()
        self.raw_overrides = {}
        self.enterContext(patch.object(gate, 'manifest_observation', side_effect=self.raw_manifest))
        self.sdk = self.enterContext(patch.object(gate.single, 'verify', side_effect=self.sdk_result))

    def write_apk(self):
        self.apk.write_bytes(archive(self.entries))
        self.candidate['apk'] = {'name': 'base.apk', 'bytes': self.apk.stat().st_size,
                                 'sha256': gate.single.digest(self.apk)}
        self.identity = {key: copy.deepcopy(self.candidate[key]) for key in (
            'package', 'version_name', 'version_code', 'version_code_major',
            'native_abis', 'signer_certificate_sha256')}
        self.identity.update(bytes=self.candidate['apk']['bytes'], sha256=self.candidate['apk']['sha256'],
                             long_version_code=self.candidate['version_code'], split_name=None,
                             uses_splits=[], config_for_split=None, manifest_split_fields=[],
                             signature_verified=True, manifest_binary_sha256=sha(self.manifest),
                             tool_exits={'badging': 0, 'manifest': 0, 'signature': 0})

    def write_candidate(self):
        raw = (json.dumps(self.candidate, sort_keys=True) + '\n').encode()
        self.cpath.write_bytes(raw)
        return sha(raw)

    def raw_manifest(self, manifest):
        self.assertEqual(manifest, self.manifest)
        raw = {key: self.candidate[key] for key in ('package', 'version_name', 'version_code', 'version_code_major')}
        raw.update(min_sdk_version=str(self.candidate['min_sdk_version']),
                   target_sdk_version=str(self.candidate['target_sdk_version']), split_name=None,
                   uses_split=None, config_for_split=None, is_feature_split=False,
                   is_split_required=False, isolated_splits=False, required_split_types=[], split_types=[])
        raw.update(self.raw_overrides)
        return raw

    def sdk_result(self, path, tools, package, signers):
        self.assertNotEqual(path, self.apk)
        self.assertEqual(path.name, 'base.apk')
        self.assertEqual(package, self.candidate['package'])
        self.assertEqual(signers, self.candidate['signer_certificate_sha256'])
        self.assertEqual(gate.single.digest(path), self.identity['sha256'])
        return copy.deepcopy(self.identity)

    def run_gate(self, expected=None):
        return gate.verify_candidate(self.apk, self.root / 'tools', self.cpath,
                                     expected or self.write_candidate(), self.receipt)

    def reject(self, pattern='.'):
        with self.assertRaisesRegex((ValueError, zipfile.BadZipFile, OSError), pattern):
            self.run_gate()
        self.assertFalse(self.receipt.exists())

    def test_exact_source_receipt_with_no_runtime_abi_or_production_credit(self):
        result = self.run_gate()
        stored = json.loads(self.receipt.read_bytes())
        self.assertEqual(stored['candidate_schema'], gate.SCHEMA)
        self.assertEqual(stored['source_observation']['distribution'], 'public_mirror')
        self.assertEqual(result['application']['expected_input']['apks'], [self.candidate['apk']])
        self.assertEqual(result['application']['expected_input']['source_receipt']['sha256'], sha(self.receipt.read_bytes()))
        self.assertTrue(stored['binary_metadata']['outer_zip_all_member_crc_verified'])
        self.assertEqual(stored['binary_metadata']['publisher_payloads'][0]['sha256'], sha(self.plugin))
        for obj in (result, stored, stored['binary_metadata']):
            for key in gate._NO_CREDIT:
                self.assertIs(obj[key], False)
        self.sdk.assert_called_once()
        self.assertFalse(self.sdk.call_args.args[0].exists())

    def test_external_candidate_pin_and_complete_apk_pin_precede_sdk(self):
        self.write_candidate()
        with self.assertRaisesRegex(ValueError, 'External candidate'):
            self.run_gate('0' * 64)
        self.sdk.assert_not_called()
        self.candidate['apk']['sha256'] = '0' * 64
        self.reject('external pin')
        self.sdk.assert_not_called()

    def test_failed_sdk_and_false_signature_cannot_publish(self):
        self.identity['signature_verified'] = False
        self.reject('SDK signature')
        self.identity['signature_verified'] = True
        self.identity['tool_exits']['signature'] = 1
        self.reject('SDK signature')
        self.sdk.side_effect = ValueError('real signature failure')
        self.reject('real signature failure')

    def test_signed_identity_mismatch_cannot_publish(self):
        original = copy.deepcopy(self.identity)
        for key, value in [('package', 'org.example.wrong'), ('version_name', '2.0'),
                           ('version_code', 2), ('version_code_major', 1),
                           ('native_abis', ['x86_64']), ('signer_certificate_sha256', ['b' * 64])]:
            with self.subTest(key=key):
                self.identity = copy.deepcopy(original)
                self.identity[key] = value
                self.reject('differs from candidate')

    def test_literal_payload_hash_layout_format_and_missing_pin(self):
        original = copy.deepcopy(self.candidate['publisher_payloads'][0])
        for key, value in [('sha256', '0' * 64), ('bytes', len(self.plugin) + 1),
                           ('observation_sha256', '0' * 64), ('format', 'dex035_layout_v1'),
                           ('path', 'lib/arm64-v8a/libmissing.so')]:
            with self.subTest(key=key):
                self.candidate['publisher_payloads'][0] = copy.deepcopy(original)
                self.candidate['publisher_payloads'][0][key] = value
                self.reject('pin|Unpinned|differs')

    def test_unknown_payload_and_missing_actual_elf_remain_failures(self):
        self.entries.append(('lib/arm64-v8a/libopaque.so', b'unknown data'))
        self.write_apk()
        self.reject('Unpinned')
        self.entries.pop()
        self.entries = [row for row in self.entries if row[0] != 'lib/arm64-v8a/libregular.so']
        self.write_apk()
        self.reject('actual ELF')

    def test_split_requirements_are_not_standalone_equivalents(self):
        for key, value in [('split_name', 'config.arm64_v8a'), ('uses_split', 'feature'),
                           ('config_for_split', 'feature'), ('is_feature_split', True),
                           ('is_split_required', True), ('isolated_splits', True),
                           ('required_split_types', ['base__abi']), ('split_types', ['base__abi'])]:
            with self.subTest(key=key):
                self.raw_overrides = {key: value}
                self.reject('standalone')

    def test_text_mentions_of_split_are_not_binary_manifest_declarations(self):
        self.identity['manifest_split_fields'] = [
            'A: android:name="com.alibaba.android.split.service.SplitInstallService"',
            'A: android:name="com.alibaba.android.split.core.splitinstall.BIND_SPLIT_INSTALL_SERVICE"']
        self.run_gate()
        self.assertTrue(json.loads(self.receipt.read_bytes())['binary_metadata']['standalone_manifest_verified'])

    def test_binary_manifest_version_sdk_and_hash_are_bound(self):
        for key, value in [('version_name', 'different'), ('version_code', 2),
                           ('min_sdk_version', '24'), ('target_sdk_version', '34')]:
            with self.subTest(key=key):
                self.raw_overrides = {key: value}
                self.reject('Binary manifest')
        self.raw_overrides = {}
        self.identity['manifest_binary_sha256'] = '0' * 64
        self.reject('Manifest changed')

    def test_outer_zip_links_duplicates_aliases_and_crc_are_rejected(self):
        original = list(self.entries)
        link = zipfile.ZipInfo('assets/link')
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        for extra in [[('../escape', b'x')], [('assets', b'x'), ('assets/file', b'y')],
                      [(self.plugin_name, self.plugin)], [(link, b'../target')]]:
            with self.subTest(extra=str(extra)[:80]):
                self.entries = original + extra
                self.write_apk()
                self.reject('ZIP')
        self.entries = original + [('assets/unique-text', b'known CRC test data')]
        self.write_apk()
        broken = self.apk.read_bytes().replace(b'known CRC test data', b'wrong CRC test data')
        self.apk.write_bytes(broken)
        self.candidate['apk'].update(bytes=len(broken), sha256=sha(broken))
        self.identity.update(bytes=len(broken), sha256=sha(broken))
        self.reject('CRC')

    def test_source_mutation_symlink_hardlink_and_existing_receipt_publish_nothing(self):
        def changed(*args):
            result = self.sdk_result(*args)
            self.apk.write_bytes(b'changed source')
            return result
        self.sdk.side_effect = changed
        self.reject('changed during')
        self.sdk.side_effect = self.sdk_result
        self.write_apk()
        link = self.root / 'hardlink.apk'
        os.link(self.apk, link)
        self.reject('single-link')
        link.unlink()
        self.apk.rename(link)
        self.apk.symlink_to(link)
        self.reject('symbolic|Too many')
        self.apk.unlink()
        link.rename(self.apk)
        self.receipt.write_bytes(b'keep this receipt')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.run_gate()
        self.assertEqual(self.receipt.read_bytes(), b'keep this receipt')

    def test_v4_schema_does_not_relax_old_v3_or_allow_opaque_catch_all(self):
        self.candidate['publisher_payloads'] = [dict(self.candidate['publisher_payloads'][0],
            path=f'lib/arm64-v8a/libplugin{i}.so') for i in range(9)]
        self.assertEqual(len(gate.load_candidate(self.cpath, self.write_candidate())[0]['publisher_payloads']), 9)
        with self.assertRaisesRegex(ValueError, 'Unsupported candidate schema'):
            gate.single.load_candidate(self.cpath, sha(self.cpath.read_bytes()))
        with self.assertRaisesRegex(ValueError, 'at most eight'):
            gate.single._native_layout_pins({'native_layout_exceptions': [{}] * 9})
        self.candidate['publisher_payloads'][0]['format'] = 'opaque_data'
        self.reject('Unknown publisher')

    def test_identical_candidate_replacement_is_not_the_original_file_identity(self):
        original = gate.load_candidate
        def replace_after_read(*args):
            result = original(*args)
            replacement = self.root / 'replacement.json'
            replacement.write_bytes(self.cpath.read_bytes())
            os.replace(replacement, self.cpath)
            return result
        with patch.object(gate, 'load_candidate', side_effect=replace_after_read):
            self.reject('Candidate file identity changed')
        self.sdk.assert_not_called()

    def test_receipt_bound_matches_the_actual_runtime_consumer(self):
        self.assertEqual(gate.RECEIPT_LIMIT, 8 * 1024 * 1024)
        with patch.object(gate, 'RECEIPT_LIMIT', 1):
            self.reject('receipt exceeds')

    def test_candidate_duplicate_unknown_fields_booleans_and_provenance_rejected(self):
        original = copy.deepcopy(self.candidate)
        for key, value in [('version_code', True), ('target_sdk_version', 0),
                           ('schema', 'pocket4-official-apk-candidate-v3'), ('unknown', 'ignored')]:
            with self.subTest(key=key):
                self.candidate = copy.deepcopy(original)
                self.candidate[key] = value
                self.reject()
        self.candidate = copy.deepcopy(original)
        self.candidate['source']['distribution'] = 'implicitly_official'
        self.reject('provenance')
        self.candidate = copy.deepcopy(original)
        self.write_candidate()
        raw = self.cpath.read_bytes().replace(b'{', b'{"schema":"duplicate",', 1)
        self.cpath.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.run_gate(sha(raw))

    def test_target_below_min_is_independently_bounded(self):
        self.candidate.update(min_sdk_version=37, target_sdk_version=30)
        result, _ = gate.load_candidate(self.cpath, self.write_candidate())
        self.assertEqual((result['min_sdk_version'], result['target_sdk_version']), (37, 30))


def cso_fixture():
    prefix = 'lib/arm64-v8a/'
    token = bytes.fromhex('01020304')
    packed = b'CSOP' + bytes(8) + token + bytes.fromhex('28b52ffd2003190000') + b'abc'
    stub = b'CSOS' + token + struct.pack('<I', 9) + b'arm64-v8a'
    records = [(3, 1, 'libsample.so'), (64, 0, 'libregular.so')]
    cursor = 4 + len(records) * 4
    offsets, body = [], []
    for size, flag, name in records:
        chunk = struct.pack('<QII', size, flag, 0) + name.encode() + b'\0'
        offsets.append(cursor + 16)
        body.append(chunk)
        cursor += len(chunk)
    meta = struct.pack('<I', len(records)) + struct.pack('<2I', *offsets) + b''.join(body)
    payloads = {}
    for name, data, kind in [('libsample.$cso.so', packed, 'wechat_csop_zstd_v1'),
                              ('libsample.so', stub, 'wechat_csos_stub_v1'),
                              ('libcso.meta.so', meta, 'wechat_cso_offset_table_v1')]:
        path = prefix + name
        payloads[path] = gate.inspect_payload(data, path, 'com.tencent.mm', kind)
    natives = {name: {'kind': 'publisher_payload', 'bytes': value['bytes'], 'sha256': value['sha256']}
               for name, value in payloads.items()}
    natives[prefix + 'libregular.so'] = {'kind': 'elf_header', 'bytes': 64, 'sha256': sha(elf_header())}
    natives[prefix + 'libcso.so'] = {'kind': 'elf_header', 'bytes': 64, 'sha256': sha(elf_header())}
    candidate = {'package': 'com.tencent.mm', 'native_abis': ['arm64-v8a']}
    return candidate, natives, payloads


class PublisherRelationshipControls(unittest.TestCase):
    def test_exact_cso_pairing_keeps_all_loader_and_dependency_claims_false(self):
        result = gate._cso_relationships(*cso_fixture())
        self.assertEqual(result[0]['record_count'], 2)
        self.assertEqual(len(result[0]['pairs']), 1)
        self.assertEqual(result[0]['pairs'][0]['declared_content_bytes'], 3)
        self.assertFalse(result[0]['loader_semantics_verified'])
        self.assertFalse(result[0]['dependency_resolution_verified'])

    def test_cso_metadata_absence_and_missing_or_extra_native_entries_fail(self):
        prefix = 'lib/arm64-v8a/'
        for change in ('meta', 'packed', 'ordinary', 'extra'):
            candidate, natives, observations = cso_fixture()
            if change in ('meta', 'packed'):
                observations.pop(prefix + ('libcso.meta.so' if change == 'meta' else 'libsample.$cso.so'))
            elif change == 'ordinary':
                natives.pop(prefix + 'libregular.so')
            else:
                natives[prefix + 'libextra.so'] = {'kind': 'elf_header', 'bytes': 64}
            with self.subTest(change=change), self.assertRaises(ValueError):
                gate._cso_relationships(candidate, natives, observations)

    def test_cso_token_abi_size_and_raw_record_relations_are_not_waived_by_local_hashes(self):
        prefix = 'lib/arm64-v8a/'
        for change in ('token', 'abi', 'declared_size', 'ordinary_size', 'ordinary_kind', 'package'):
            candidate, natives, observations = cso_fixture()
            if change == 'token':
                observations[prefix + 'libsample.so']['observed_token_hex'] = 'deadbeef'
            elif change == 'abi':
                observations[prefix + 'libsample.so']['abi_label'] = 'x86_64'
            elif change == 'declared_size':
                observations[prefix + 'libsample.$cso.so']['zstd']['declared_content_bytes'] = 4
            elif change == 'ordinary_size':
                natives[prefix + 'libregular.so']['bytes'] = 65
            elif change == 'ordinary_kind':
                natives[prefix + 'libregular.so']['kind'] = 'publisher_payload'
            else:
                candidate['package'] = 'org.example.other'
            with self.subTest(change=change), self.assertRaises(ValueError):
                gate._cso_relationships(candidate, natives, observations)

    def test_only_three_named_bounded_meituan_header_observations_exist(self):
        package = 'com.sankuai.meituan.takeoutnew'
        for name, version, size in [('libmtguard_1.so', '1.1.4', 28736),
                                     ('libmtguard_2.so', '1.1.8', 29632),
                                     ('libmtguard_3.so', '1.1.1', 5216)]:
            data = version.encode().ljust(16, b'\0') + bytes(size - 16)
            path = 'lib/arm64-v8a/' + name
            result = gate.inspect_mtguard_observation(data, path, package)
            self.assertEqual(result['header_hex'], data[:16].hex())
            self.assertEqual(result['body_sha256'], sha(data[16:]))
            for claim in ('body_format_verified', 'decryption_performed', 'native_execution_verified',
                          'abi_compatibility_verified', 'inner_code_executed'):
                self.assertIs(result[claim], False)
            for invalid, entry, app in [(data[:-1], path, package), (data + bytes(16), path, package),
                                         (b'2' + data[1:], path, package),
                                         (data, 'lib/arm64-v8a/libmtguard_4.so', package),
                                         (data, path.replace('arm64-v8a', 'x86_64'), package),
                                         (data, path, 'org.example.other')]:
                with self.subTest(name=name, entry=entry, app=app), self.assertRaises(ValueError):
                    gate.inspect_mtguard_observation(invalid, entry, app)
            with self.assertRaisesRegex(ValueError, 'Unknown native-directory'):
                gate.inspect_native_publisher_payload(data, path)


if __name__ == '__main__':
    unittest.main()
