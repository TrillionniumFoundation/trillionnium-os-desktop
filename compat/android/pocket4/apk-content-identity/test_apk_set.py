"""Complete-set controls with real bounded AXML/ZIP bytes and mocked SDK crypto.

These source tests do not grant any signed-input or Android-runtime credit.
The actual complete Amazon APK set has a separate SDK-37 verification receipt.
"""
from pathlib import Path
import copy
import hashlib
import io
import json
import os
import stat
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_apk_set as gate
from axml_metadata import ANDROID


def sha(body):
    return hashlib.sha256(body).hexdigest()


def axml(root):
    """Build minimal string-typed AXML, independent of the production decoder."""
    strings = []
    def intern(value):
        if value is None:
            return 0xffffffff
        if value not in strings:
            strings.append(value)
        return strings.index(value)
    def qname(value):
        if value.startswith('{'):
            ns, name = value[1:].split('}', 1)
            return intern(ns), intern(name)
        return 0xffffffff, intern(value)
    def visit(node):
        ns, name = qname(node.tag)
        attrs = []
        for key, value in node.attrib.items():
            ans, aname = qname(key)
            idx = intern(value)
            attrs.append(struct.pack('<IIIHBBI', ans, aname, idx, 8, 0, 3, idx))
        payload = struct.pack('<IIHHHHHH', ns, name, 20, 20, len(attrs), 0, 0, 0)
        payload += b''.join(attrs)
        result = struct.pack('<HHIII', 0x102, 16, 16 + len(payload), 1, 0xffffffff) + payload
        for child in node:
            result += visit(child)
        return result + struct.pack('<HHIIIII', 0x103, 16, 24, 1, 0xffffffff, ns, name)
    events = visit(root)
    offsets, encoded = [], b''
    for value in strings:
        body = value.encode()
        assert len(body) < 128 and len(value.encode('utf-16le')) // 2 < 128
        offsets.append(len(encoded))
        encoded += bytes([len(value.encode('utf-16le')) // 2, len(body)]) + body + b'\0'
    encoded += bytes((-len(encoded)) % 4)
    begin = 28 + 4 * len(strings)
    pool = struct.pack('<HHIIIIII', 1, 28, begin + len(encoded), len(strings), 0, 0x100, begin, 0)
    pool += b''.join(struct.pack('<I', offset) for offset in offsets) + encoded
    return struct.pack('<HHI', 3, 8, 8 + len(pool) + len(events)) + pool + events


def manifest(split=None, root_attrs=None, application_attrs=None, uses=None,
             package='org.example.app', version=7, minimum=31, target=37):
    a = lambda key: '{' + ANDROID + '}' + key
    attrs = {'package': package, a('versionCode'): str(version)}
    if split is None:
        attrs[a('versionName')] = '1.0'
    else:
        attrs['split'] = split
    attrs.update(root_attrs or {})
    root = ET.Element('manifest', attrs)
    if minimum is not None:
        ET.SubElement(root, 'uses-sdk', {a('minSdkVersion'): str(minimum),
                                        a('targetSdkVersion'): str(target)})
    if uses is not None:
        ET.SubElement(root, 'uses-split', {a('name'): uses})
    ET.SubElement(root, 'application', application_attrs or {})
    return axml(root)


def apk(binary, extra=None):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('AndroidManifest.xml', binary)
        for name, body in (extra or {}).items():
            archive.writestr(name, body)
    return out.getvalue()


class SetControls(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='apk-set-controls-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.container = self.root / 'input.apks'
        self.path = self.root / 'candidate.json'
        self.receipt = self.root / 'receipt.json'
        a = '{' + ANDROID + '}'
        self.payloads = {
            'original.apk': apk(manifest(root_attrs={a + 'requiredSplitTypes': 'base__abi,base__density'})),
            'config.arm64_v8a.apk': apk(manifest('config.arm64_v8a', minimum=None,
                                               root_attrs={a + 'splitTypes': 'base__abi'})),
            'config.xxhdpi.apk': apk(manifest('config.xxhdpi', minimum=None,
                                            root_attrs={a + 'splitTypes': 'base__density'})),
        }
        self.candidate = {
            'schema': gate.SCHEMA, 'package': 'org.example.app', 'version_name': '1.0',
            'version_code': 7, 'version_code_major': 0, 'min_sdk_version': 31,
            'target_sdk_version': 37, 'signer_certificate_sha256': ['a' * 64],
            'container': {}, 'apks': [], 'source': {
                'archive_url': 'https://example.org/complete.apks',
                'version_metadata_url': 'https://example.org/releases',
                'signer_reference_url': 'https://example.org/cert',
                'signer_reference_kind': 'publisher_certificate',
                'distribution': 'public_mirror', 'observed_utc': '2026-11-18T00:00:00+00:00',
                'observed_stable_version': '1.0', 'sha256_kind': 'observed_whole_file_digest'}}
        self.rebuild()
        self.sdk = self.enterContext(patch.object(gate.single, 'verify', side_effect=self.fake_sdk))

    def fake_sdk(self, path, tools, package, certs):
        with zipfile.ZipFile(path) as archive:
            raw_bytes = archive.read('AndroidManifest.xml')
            raw = gate.manifest_observation(raw_bytes)
            abis = sorted({n.split('/')[1] for n in archive.namelist() if n.startswith('lib/')})
        return {**raw, 'filename': path.name, 'bytes': path.stat().st_size,
                'sha256': gate.single.digest(path), 'manifest_binary_sha256': sha(raw_bytes),
                'native_abis': abis, 'signer_certificate_sha256': certs,
                'long_version_code': (raw['version_code_major'] << 32) | raw['version_code'],
                'signature_verified': True, 'tool_exits': {'mocked': 0}}

    def rebuild(self):
        with zipfile.ZipFile(self.container, 'w', compression=zipfile.ZIP_STORED) as archive:
            for name, body in self.payloads.items():
                archive.writestr(name, body)
        self.candidate['container'] = {'bytes': self.container.stat().st_size,
                                       'sha256': gate.single.digest(self.container)}
        members = []
        for name, body in self.payloads.items():
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                raw = gate.manifest_observation(archive.read('AndroidManifest.xml'))
                abis = sorted({n.split('/')[1] for n in archive.namelist() if n.startswith('lib/')})
            members.append({'member': name, 'split_name': raw['split_name'], 'bytes': len(body),
                            'sha256': sha(body), 'native_abis': abis})
        self.candidate['apks'] = sorted(members, key=lambda p: p['split_name'] or '')

    def write(self):
        body = (json.dumps(self.candidate, sort_keys=True) + '\n').encode()
        self.path.write_bytes(body)
        return sha(body)

    def run_set(self):
        return gate.verify_set(self.container, self.root / 'tools', self.path,
                               self.write(), self.receipt)

    def fail(self, pattern):
        with self.assertRaisesRegex((ValueError, OSError), pattern):
            self.run_set()
        self.assertFalse(self.receipt.exists())

    def test_complete_container_base_and_two_required_splits(self):
        out = self.run_set()
        receipt = json.loads(self.receipt.read_bytes())
        self.assertEqual(self.sdk.call_count, 3)
        self.assertTrue(receipt['all_container_apks_verified'])
        self.assertTrue(receipt['split_closure']['manifest_dependency_closure_verified'])
        self.assertEqual(receipt['split_closure']['required_split_types'], ['base__abi', 'base__density'])
        self.assertEqual([x['name'] for x in out['application']['expected_input']['apks']],
                         ['base.apk', 'split_config.arm64_v8a.apk', 'split_config.xxhdpi.apk'])
        for value in (out, receipt):
            for key in ('installed', 'runtime_qualified', 'production_ready'):
                self.assertIs(value[key], False)
        self.assertIs(receipt['split_closure']['device_configuration_match_qualified'], False)

    def test_missing_declared_split_fails_before_sdk(self):
        self.candidate['apks'].pop()
        self.fail('inventory differs')
        self.sdk.assert_not_called()

    def test_redeclaring_incomplete_set_does_not_satisfy_required_types(self):
        del self.payloads['config.xxhdpi.apk']
        self.rebuild()
        self.fail('missing required split types')

    def test_complete_archive_and_member_hashes_are_independent(self):
        for position in ('container', 'apk'):
            with self.subTest(position=position):
                saved = copy.deepcopy(self.candidate)
                field = self.candidate['container'] if position == 'container' else self.candidate['apks'][1]
                field['sha256'] = '0' * 64
                self.fail('SHA-256|external pin')
                self.candidate = saved

    def test_wrong_package_code_and_split_identity_cannot_join(self):
        valid = copy.deepcopy(self.payloads)
        variants = [{'package': 'org.other.app'}, {'version': 8}, {}]
        for kwargs in variants:
            with self.subTest(kwargs=kwargs):
                self.payloads = copy.deepcopy(valid)
                split = 'other' if not kwargs else 'config.arm64_v8a'
                self.payloads['config.arm64_v8a.apk'] = apk(manifest(split, minimum=None, **kwargs))
                self.rebuild()
                if not kwargs:
                    self.candidate['apks'][2]['split_name'] = 'config.arm64_v8a'
                    self.candidate['apks'].sort(key=lambda p: p['split_name'] or '')
                self.fail('common|identity differs')

    def test_sdk_failure_or_unexpected_signer_publishes_nothing(self):
        self.sdk.side_effect = ValueError('actual SDK signature failed')
        self.fail('signature failed')
        def different(*args):
            result = self.fake_sdk(*args)
            result['signer_certificate_sha256'] = ['b' * 64]
            return result
        self.sdk.side_effect = different
        self.fail('Verified SDK identity differs')

    def test_mutated_candidate_and_container_are_detected(self):
        for what in ('candidate', 'container'):
            with self.subTest(what=what):
                mutated = False
                def change(*args):
                    nonlocal mutated
                    result = self.fake_sdk(*args)
                    if not mutated:
                        p = self.path if what == 'candidate' else self.container
                        with p.open('ab') as output:
                            output.write(b' ')
                        mutated = True
                    return result
                self.sdk.side_effect = change
                self.fail('changed during')
                self.rebuild()

    def test_source_symlink_hardlink_and_existing_receipt_are_rejected(self):
        self.receipt.write_bytes(b'original')
        with self.assertRaisesRegex(ValueError, 'new file'):
            self.run_set()
        self.assertEqual(self.receipt.read_bytes(), b'original')
        self.receipt.unlink()
        alias = self.root / 'alias.apks'
        os.link(self.container, alias)
        self.fail('single-link')
        alias.unlink()
        original = self.root / 'original.apks'
        self.container.rename(original)
        self.container.symlink_to(original)
        self.fail('symbolic links|Too many levels')
        self.sdk.assert_not_called()

    def test_candidate_duplicate_fields_types_and_unknown_keys_are_rejected(self):
        valid = copy.deepcopy(self.candidate)
        for key, value in [('version_code', True), ('min_sdk_version', 38),
                           ('target_sdk_version', 0), ('extra', False), ('apks', [])]:
            with self.subTest(key=key):
                self.candidate = copy.deepcopy(valid)
                self.candidate[key] = value
                self.fail('Invalid|fields|requires')
        self.candidate = valid
        self.write()
        raw = self.path.read_bytes().replace(b'{', b'{"schema":"duplicate",', 1)
        self.path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            gate.load_candidate(self.path, sha(raw))
        self.sdk.assert_not_called()

    def test_valid_lower_target_sdk_is_not_a_reversed_runtime_range(self):
        self.candidate.update(min_sdk_version=37, target_sdk_version=30)
        a = '{' + ANDROID + '}'
        self.payloads['original.apk'] = apk(manifest(minimum=37, target=30,
            root_attrs={a + 'requiredSplitTypes': 'base__abi,base__density'}))
        self.rebuild()
        self.run_set()
        self.assertEqual(self.sdk.call_count, 3)

    def test_wrong_native_elf_is_not_a_publisher_payload_exception(self):
        body = b'\x7fELF\x02\x01\x01' + bytes(9) + struct.pack('<HH', 3, 62)
        self.payloads['config.arm64_v8a.apk'] = apk(manifest('config.arm64_v8a', minimum=None),
                                                 {'lib/arm64-v8a/libtest.so': body})
        self.rebuild()
        self.fail('declared ELF ABI')


class ManifestAndZipControls(unittest.TestCase):
    def test_feature_dependency_missing_config_target_and_cycle(self):
        a = '{' + ANDROID + '}'
        decode = gate.manifest_observation
        base = decode(manifest())
        feature = decode(manifest('feature', root_attrs={a + 'isFeatureSplit': 'true'}))
        config = decode(manifest('config', root_attrs={'configForSplit': 'feature'}))
        self.assertTrue(gate.validate_closure([base, feature, config])['manifest_dependency_closure_verified'])
        with self.assertRaisesRegex(ValueError, 'Missing'):
            gate.validate_closure([base, config])
        left = decode(manifest('left', uses='right', root_attrs={a + 'isFeatureSplit': 'true'}))
        right = decode(manifest('right', uses='left', root_attrs={a + 'isFeatureSplit': 'true'}))
        with self.assertRaisesRegex(ValueError, 'Cycle'):
            gate.validate_closure([base, left, right])

    def test_ambiguous_manifest_flags_and_debuggable_are_rejected(self):
        a = '{' + ANDROID + '}'
        self.assertEqual(gate.manifest_observation(manifest(
            root_attrs={a + 'splitTypes': ''}))['split_types'], [])
        for raw in [manifest(application_attrs={a + 'debuggable': 'true'}),
                    manifest(application_attrs={a + 'testOnly': 'true'}),
                    manifest(root_attrs={a + 'isFeatureSplit': 'maybe'}),
                    manifest(root_attrs={a + 'configForSplit': 'feature'}),
                    manifest(root_attrs={a + 'splitTypes': 'type,type'})]:
            with self.assertRaises(ValueError):
                gate.manifest_observation(raw)

    def test_zip_paths_links_and_duplicates_are_rejected(self):
        import warnings
        variants = [['../base.apk'], ['/base.apk'], ['a//base.apk'], ['a\\base.apk'],
                    ['a', 'a/b.apk'], ['base.apk', 'base.apk']]
        for names in variants:
            with self.subTest(names=names), warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                stream = io.BytesIO()
                with zipfile.ZipFile(stream, 'w') as out:
                    for name in names:
                        out.writestr(name, b'x')
                with zipfile.ZipFile(io.BytesIO(stream.getvalue())) as archive, self.assertRaises(ValueError):
                    gate.safe_members(archive)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as out:
            info = zipfile.ZipInfo('base.apk')
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            out.writestr(info, b'target')
        with zipfile.ZipFile(io.BytesIO(stream.getvalue())) as archive, self.assertRaisesRegex(ValueError, 'link'):
            gate.safe_members(archive)


if __name__ == '__main__':
    unittest.main(verbosity=2)
