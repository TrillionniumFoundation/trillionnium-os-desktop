"""Publisher-delivery provenance controls: real ZIP/AXML bytes, mocked SDK crypto only.

These tests do not grant real signature, transport, install, native, or runtime credit.
Existing 146 controls run separately without source changes.
"""
from pathlib import Path
from unittest.mock import patch
import base64
import copy
import hashlib
import io
import json
import os
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_publisher_delivery as gate
from test_apk_set import manifest, axml
from axml_metadata import ANDROID


def sha(body):
    return hashlib.sha256(body).hexdigest()


def elf(cls=2, machine=183):
    body = bytearray(64)
    body[:7] = b'\x7fELF' + bytes([cls, 1, 1])
    struct.pack_into('<HHI', body, 16, 3, machine, 1)
    return bytes(body)


def apk(binary, extra=None):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_STORED) as archive:
        archive.writestr('AndroidManifest.xml', binary)
        for name, body in (extra or {}).items():
            archive.writestr(name, body)
    return out.getvalue()


def corrupt_resource(body, name):
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        item = archive.getinfo(name)
        offset = item.header_offset
    result = bytearray(body)
    n, extra = struct.unpack_from('<HH', result, offset + 26)
    result[offset + 30 + n + extra] ^= 1
    return bytes(result)


class DeliveryControls(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='publisher-delivery-controls-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.path = self.root / 'candidate.json'
        self.receipt = self.root / 'receipt.json'
        self.container = self.root / 'input.apks'
        self.metadata_path = self.root / 'metadata.json'
        self.delivery_path = self.root / 'delivery.json'
        self.transaction_path = self.root / 'transaction.json'
        self.time = '2026-11-18T12:00:00+00:00'
        self.cert = 'a' * 64
        self.candidate = {
            'schema': gate.SET_SCHEMA, 'package': 'org.example.app', 'version_name': '1.0',
            'version_code': 7, 'version_code_major': 0, 'min_sdk_version': 31,
            'target_sdk_version': 37, 'signer_certificate_sha256': [self.cert],
            'selected_abi': 'arm64-v8a', 'container': None, 'apks': [],
            'source': {
                'distribution': 'google_play_publisher_delivery',
                'signer_reference_kind': 'current_get_items_certificate_set',
                'container_origin': gate.ORIGIN_SET, 'publisher_archive_obtained': False,
                'observed_utc': self.time, 'metadata': {}, 'delivery': {}, 'transaction': {}}}
        b64 = lambda body: base64.urlsafe_b64encode(body).decode().rstrip('=')
        self.metadata = {
            'package': 'org.example.app', 'version_name': '1.0', 'version_code': 7,
            'source': 'GET_ITEMS', 'restriction': 'AVAILABLE', 'restriction_code': 1,
            'is_free': True, 'offer_type': 1,
            'certificate_sets': [{'sha1_base64url': b64(b'\xbb' * 20),
                                  'sha256_base64url': b64(bytes.fromhex(self.cert))}],
            'certificate_sha1_base64url': []}
        a = '{' + ANDROID + '}'
        self.payloads = [
            (None, apk(manifest(root_attrs={
                a + 'requiredSplitTypes': 'base__abi,base__density'}),
                {'assets/resource.bin': b'real resource bytes'})),
            ('config.arm64_v8a', apk(manifest('config.arm64_v8a', minimum=None,
                root_attrs={a + 'splitTypes': 'base__abi'}),
                {'lib/arm64-v8a/libexample.so': elf()})),
            ('config.xxhdpi', apk(manifest('config.xxhdpi', minimum=None,
                root_attrs={a + 'splitTypes': 'base__density'})))]
        self.rebuild()
        self.sdk = self.enterContext(patch.object(gate.single, 'verify', side_effect=self.fake_sdk))

    def fake_sdk(self, path, tools, package, certs):
        with zipfile.ZipFile(path) as archive:
            binary = archive.read('AndroidManifest.xml')
            raw = gate.sets.manifest_observation(binary)
            abis = sorted({x.filename.split('/')[1] for x in archive.infolist()
                           if not x.is_dir() and x.filename.startswith('lib/')})
        return {**raw, 'filename': path.name, 'bytes': path.stat().st_size,
                'sha256': gate.single.digest(path), 'manifest_binary_sha256': sha(binary),
                'native_abis': abis, 'signer_certificate_sha256': certs,
                'long_version_code': (raw['version_code_major'] << 32) | raw['version_code'],
                'signature_verified': True, 'tool_exits': {'mocked_crypto_only': 0}}

    def evidence(self):
        for key, path, value in [('metadata', self.metadata_path, self.metadata),
                                 ('delivery', self.delivery_path, self.delivery),
                                 ('transaction', self.transaction_path, self.transaction)]:
            body = (json.dumps(value, sort_keys=True) + '\n').encode()
            path.write_bytes(body)
            self.candidate['source'][key] = {'path': str(path), 'bytes': len(body), 'sha256': sha(body)}

    def rebuild(self):
        members, files = [], []
        for index, (split, body) in enumerate(self.payloads):
            path = self.root / ('part-%04d.apk' % index)
            path.write_bytes(body)
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                abis = sorted({x.filename.split('/')[1] for x in archive.infolist()
                               if not x.is_dir() and x.filename.startswith('lib/')})
            pin = {'member': gate.sets.normalized_name(split), 'split_name': split,
                   'bytes': len(body), 'sha256': sha(body),
                   'sha1': hashlib.sha1(body).hexdigest(), 'native_abis': abis,
                   'delivery_path': str(path)}
            members.append(pin)
            files.append({'path': str(path), 'role': 'BASE' if split is None else 'SPLIT',
                          'bytes': pin['bytes'], 'sha256': pin['sha256'], 'sha1': pin['sha1'],
                          'delivery_sha256': pin['sha256'], 'delivery_sha1': pin['sha1'],
                          'source_host': 'rr1---example.gvt1.com', 'redirect_count': 1})
        self.candidate['apks'] = sorted(members, key=lambda x: x['split_name'] or '')
        self.delivery = {'package': 'org.example.app', 'version_name': '1.0', 'version_code': 7,
                         'status': 'transport_complete_requires_apk_gate',
                         'official_signer_certificate_sha256': [self.cert], 'files': files,
                         **gate.NO_CREDIT}
        self.transaction = {
            'schema': 'pocket4-aurora-official-client-result-v1', 'finished_utc': self.time,
            'results': [copy.deepcopy(self.delivery)],
            'transport': {'stopped': None}, 'auth_requests': 0, 'purchase_requests': 0,
            'android_starts': 0, 'installed_apps': 0, 'production_ready': False}
        self.evidence()
        if self.container.exists():
            self.container.unlink()
        if self.candidate['schema'] == gate.SET_SCHEMA:
            self.candidate['container'] = gate.assemble_local_set(
                self.candidate['apks'], self.container)
            self.input = self.container
        else:
            self.candidate['container'] = None
            self.input = Path(self.candidate['apks'][0]['delivery_path'])

    def standalone(self, legacy=None, only_legacy=False, attrs=None):
        self.candidate['schema'] = gate.SINGLE_SCHEMA
        self.candidate['source']['container_origin'] = gate.ORIGIN_SINGLE
        natives = {} if only_legacy else {'lib/arm64-v8a/libexample.so': elf()}
        if legacy is not None:
            natives['lib/armeabi/liblegacy.so'] = legacy
        self.payloads = [(None, apk(manifest(root_attrs=attrs), natives))]
        self.rebuild()

    def write(self):
        body = (json.dumps(self.candidate, sort_keys=True) + '\n').encode()
        self.path.write_bytes(body)
        return sha(body)

    def run_gate(self):
        return gate.verify_delivery(self.input, self.root / 'tools', self.path,
                                    self.write(), self.receipt)

    def assert_rejected(self, pattern):
        with self.assertRaisesRegex((ValueError, OSError, zipfile.BadZipFile), pattern):
            self.run_gate()
        self.assertFalse(self.receipt.exists())

    def mutate_container(self, action):
        body = self.container.read_bytes()
        self.container.write_bytes(action(body))
        self.candidate['container'] = {'bytes': self.container.stat().st_size,
                                       'sha256': gate.single.digest(self.container)}

    def test_complete_real_axml_set_with_external_metadata(self):
        result = self.run_gate()
        receipt = json.loads(self.receipt.read_bytes())
        self.assertEqual(self.sdk.call_count, 3)
        self.assertEqual(receipt['schema'], gate.RECEIPT_SCHEMA)
        self.assertFalse(receipt['publisher_archive_obtained'])
        self.assertEqual(receipt['source_observation']['container_origin'], gate.ORIGIN_SET)
        self.assertEqual([x['name'] for x in result['application']['expected_input']['apks']],
                         ['base.apk', 'split_config.arm64_v8a.apk', 'split_config.xxhdpi.apk'])
        self.assertTrue(receipt['split_closure']['manifest_dependency_closure_verified'])
        self.assertEqual(len(receipt['selected_abi_native_members']), 1)
        self.assertEqual(receipt['selected_abi_native_members'][0]['sha256'], sha(elf()))
        self.assertTrue(all(x['all_member_crc_verified'] for x in receipt['complete_zip_integrity']))
        for observed in (result, receipt):
            for key in gate.NO_CREDIT:
                self.assertIs(observed[key], False)
        for key in ('native_compatibility_qualified', 'device_profile_match_qualified',
                    'legacy_armeabi_execution_supported'):
            self.assertIs(receipt[key], False)

    def test_standalone_observes_all_legacy_bytes_but_selects_only_arm64(self):
        self.standalone(elf(1, 40))
        self.run_gate()
        receipt = json.loads(self.receipt.read_bytes())
        self.assertIsNone(receipt['local_container'])
        self.assertEqual(receipt['source_observation']['container_origin'], gate.ORIGIN_SINGLE)
        self.assertEqual(len(receipt['complete_zip_integrity'][0]['native_members']), 2)
        self.assertEqual(len(receipt['selected_abi_native_members']), 1)
        legacy = [x for x in receipt['binary_metadata'][0]['native_libraries']
                  if x['legacy_armeabi_observation_only']]
        self.assertEqual(len(legacy), 1)
        self.assertFalse(legacy[0]['selected_for_input'])
        self.assertFalse(receipt['legacy_armeabi_execution_supported'])

    def test_old_set_schema_and_legacy_abi_rejection_remain(self):
        digest = self.write()
        with self.assertRaisesRegex(ValueError, 'fields differ'):
            gate.sets.load_candidate(self.path, digest)
        self.assertNotIn('armeabi', gate.single._ABI_ELF)
        self.assertEqual(gate.sets.SCHEMA, 'pocket4-apk-set-candidate-v1')

    def test_publisher_archive_claim_cannot_describe_local_zip(self):
        self.candidate['source']['publisher_archive_obtained'] = True
        self.assert_rejected('provenance')
        self.sdk.assert_not_called()

    def test_historical_signer_label_is_not_accepted_for_current_metadata(self):
        self.candidate['source']['signer_reference_kind'] = 'public_historical_candidate'
        self.assert_rejected('provenance')

    def test_source_unknown_field_is_rejected(self):
        self.candidate['source']['archive_url'] = 'https://example.org/not-obtained.apks'
        self.assert_rejected('fields differ')

    def test_external_metadata_version_mismatch_rejected(self):
        self.metadata['version_code'] += 1
        self.evidence()
        self.assert_rejected('External metadata package/version')
        self.sdk.assert_not_called()

    def test_external_metadata_certificate_is_not_inferred_from_apk(self):
        self.metadata['certificate_sets'][0]['sha256_base64url'] = (
            base64.urlsafe_b64encode(b'\xcc' * 32).decode().rstrip('='))
        self.evidence()
        self.assert_rejected('External metadata signer')
        self.sdk.assert_not_called()

    def test_external_certificate_noncanonical_padding_rejected(self):
        self.metadata['certificate_sets'][0]['sha256_base64url'] += '='
        self.evidence()
        self.assert_rejected('certificate encoding')

    def test_duplicate_external_certificate_rejected(self):
        self.metadata['certificate_sets'] *= 2
        self.evidence()
        self.assert_rejected('External metadata signer')

    def test_region_unavailable_metadata_is_not_free_delivery(self):
        self.metadata['restriction'] = 'NOT_AVAILABLE_IN_COUNTRY'
        self.metadata['restriction_code'] = 4
        self.evidence()
        self.assert_rejected('does not authorize')
        self.sdk.assert_not_called()

    def test_paid_metadata_is_rejected(self):
        self.metadata['is_free'] = False
        self.evidence()
        self.assert_rejected('does not authorize')

    def test_provider_stop_transaction_is_rejected(self):
        self.transaction['transport']['stopped'] = 'provider rejected'
        self.evidence()
        self.assert_rejected('provider boundary')

    def test_per_package_record_must_equal_original_transaction(self):
        self.transaction['results'][0]['files'][0]['redirect_count'] += 1
        self.evidence()
        self.assert_rejected('transaction and per-package')

    def test_candidate_cannot_omit_original_density_member(self):
        self.candidate['apks'].pop()
        self.assert_rejected('original delivery inventory')
        self.sdk.assert_not_called()

    def test_redeclared_delivery_still_must_close_signed_split_dependencies(self):
        self.payloads.pop()
        self.rebuild()
        self.assert_rejected('missing required split types')

    def test_duplicate_original_delivery_member_rejected(self):
        self.delivery['files'][1] = copy.deepcopy(self.delivery['files'][0])
        self.transaction['results'] = [copy.deepcopy(self.delivery)]
        self.evidence()
        self.assert_rejected('Duplicate or invalid original delivery')

    def test_delivery_digest_disagreement_rejected(self):
        self.delivery['files'][0]['delivery_sha256'] = '0' * 64
        self.transaction['results'] = [copy.deepcopy(self.delivery)]
        self.evidence()
        self.assert_rejected('delivery digest')

    def test_real_original_sha1_is_checked_independently(self):
        self.candidate['apks'][0]['sha1'] = '0' * 40
        self.delivery['files'][0]['sha1'] = '0' * 40
        self.delivery['files'][0]['delivery_sha1'] = '0' * 40
        self.transaction['results'] = [copy.deepcopy(self.delivery)]
        self.evidence()
        self.assert_rejected('Actual original delivery SHA-1')
        self.sdk.assert_not_called()

    def test_metadata_bytes_must_match_external_pin(self):
        self.metadata_path.write_bytes(self.metadata_path.read_bytes() + b' ')
        self.assert_rejected('Source bytes or SHA-256')
        self.sdk.assert_not_called()

    def test_sdk_signer_disagreement_rejected(self):
        def wrong(*args):
            result = self.fake_sdk(*args)
            result['signer_certificate_sha256'] = ['b' * 64]
            return result
        self.sdk.side_effect = wrong
        self.assert_rejected('Verified SDK identity')

    def test_signature_failure_rejected(self):
        def wrong(*args):
            result = self.fake_sdk(*args)
            result['signature_verified'] = False
            return result
        self.sdk.side_effect = wrong
        self.assert_rejected('Verified SDK identity')

    def test_candidate_cannot_replace_signed_package_identity(self):
        self.candidate['package'] = self.metadata['package'] = 'org.example.other'
        self.delivery['package'] = 'org.example.other'
        self.transaction['results'] = [copy.deepcopy(self.delivery)]
        self.evidence()
        self.assert_rejected('differs from common package')

    def test_set_actual_arm64_machine_mismatch_rejected(self):
        a = '{' + ANDROID + '}'
        self.payloads[1] = ('config.arm64_v8a', apk(
            manifest('config.arm64_v8a', minimum=None, root_attrs={a + 'splitTypes': 'base__abi'}),
            {'lib/arm64-v8a/libexample.so': elf(2, 62)}))
        self.rebuild()
        self.assert_rejected('declared ELF ABI')

    def test_standalone_legacy_only_cannot_become_arm64_input(self):
        self.standalone(elf(1, 40), only_legacy=True)
        self.assert_rejected('Selected ARM64 payload is absent')
        self.sdk.assert_not_called()

    def test_standalone_legacy_elf_class_mismatch_rejected(self):
        self.standalone(elf(2, 40))
        self.assert_rejected('ELF class/machine/type')

    def test_standalone_legacy_elf_machine_mismatch_rejected(self):
        self.standalone(elf(1, 3))
        self.assert_rejected('ELF class/machine/type')

    def test_standalone_split_requirement_rejected(self):
        self.standalone(elf(1, 40), attrs={'{' + ANDROID + '}isSplitRequired': 'true'})
        self.assert_rejected('Standalone has a split dependency')

    def test_standalone_original_path_cannot_be_replaced_by_copy(self):
        self.standalone(elf(1, 40))
        path = self.root / 'same-copy.apk'
        path.write_bytes(self.input.read_bytes())
        self.input = path
        self.assert_rejected('not the original delivery path')

    def test_local_container_undeclared_trailing_bytes_rejected(self):
        self.mutate_container(lambda body: body + b'undeclared')
        self.assert_rejected('boundary or trailer')
        self.sdk.assert_not_called()

    def test_local_container_recompression_is_not_claimed_deterministic_assembly(self):
        with zipfile.ZipFile(self.container, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for pin in self.candidate['apks']:
                archive.writestr(pin['member'], Path(pin['delivery_path']).read_bytes())
        self.candidate['container'] = {'bytes': self.container.stat().st_size,
                                       'sha256': gate.single.digest(self.container)}
        self.assert_rejected('deterministic assembly')
        self.sdk.assert_not_called()

    def test_local_central_version_cannot_disagree_with_local_header(self):
        with zipfile.ZipFile(self.container) as archive:
            offset = archive.start_dir
        def alter(body):
            result = bytearray(body)
            struct.pack_into('<H', result, offset + 6, 20)
            return bytes(result)
        self.mutate_container(alter)
        self.assert_rejected('deterministic assembly')
        self.sdk.assert_not_called()

    def test_full_resource_crc_is_checked_not_only_manifest_and_elf(self):
        split, body = self.payloads[0]
        self.payloads[0] = (split, corrupt_resource(body, 'assets/resource.bin'))
        self.rebuild()
        self.assert_rejected('CRC')

    def test_candidate_same_bytes_new_inode_during_sdk_rejected(self):
        invoked = False
        def replacement(*args):
            nonlocal invoked
            if not invoked:
                invoked = True
                replacement_path = self.root / 'candidate-replacement.json'
                replacement_path.write_bytes(self.path.read_bytes())
                os.replace(replacement_path, self.path)
            return self.fake_sdk(*args)
        self.sdk.side_effect = replacement
        self.assert_rejected('Original source changed')

    def test_metadata_same_bytes_new_inode_during_sdk_rejected(self):
        invoked = False
        def replacement(*args):
            nonlocal invoked
            if not invoked:
                invoked = True
                path = self.root / 'metadata-replacement.json'
                path.write_bytes(self.metadata_path.read_bytes())
                os.replace(path, self.metadata_path)
            return self.fake_sdk(*args)
        self.sdk.side_effect = replacement
        self.assert_rejected('Original source changed')

    def test_original_apk_same_bytes_new_inode_during_sdk_rejected(self):
        invoked = False
        def replacement(*args):
            nonlocal invoked
            if not invoked:
                invoked = True
                original = Path(self.candidate['apks'][0]['delivery_path'])
                path = self.root / 'apk-replacement.apk'
                path.write_bytes(original.read_bytes())
                os.replace(path, original)
            return self.fake_sdk(*args)
        self.sdk.side_effect = replacement
        self.assert_rejected('Original source changed')

    def test_receipt_never_overwrites_existing_output(self):
        self.receipt.write_bytes(b'existing receipt')
        with self.assertRaisesRegex(ValueError, 'new absolute file'):
            self.run_gate()
        self.assertEqual(self.receipt.read_bytes(), b'existing receipt')
        self.sdk.assert_not_called()

    def test_receipt_size_bound_prevents_publication(self):
        with patch.object(gate.sets, 'RECEIPT_LIMIT', 32):
            self.assert_rejected('receipt exceeds consumer bound')

    def test_candidate_boolean_version_is_not_integer(self):
        self.candidate['version_code'] = True
        self.assert_rejected('Invalid version_code')


if __name__ == '__main__':
    unittest.main(verbosity=2)
