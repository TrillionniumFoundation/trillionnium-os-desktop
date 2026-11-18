"""V4 source-only composition controls; no signed APK or runtime claims."""
import copy
import hashlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_publisher_apk as gate
from test_verify_publisher_apk import archive, elf_header, pin
from test_seven_zip04_payload import fixture as sevenzip
from test_native_resource_payloads import elf as interpreter_elf
from test_dual_dynamic_elf import sample as dual_elf


class MixedPublisherControls(unittest.TestCase):
    def setUp(self):
        self.manifest = b'explicit inert mock manifest'
        self.interpreter_path = 'lib/arm64-v8a/libwb.so'
        self.dual_path = 'lib/arm64-v8a/libDexHelper-x86.so'
        self.archive_path = 'lib/arm64-v8a/libarchive_7z.so'
        self.interpreter_kind = 'interpreter_tagged_et_dyn_source_v1'
        self.dual_kind = 'dual_dynamic_shared_library_source_v1'
        self.sevenzip_kind = 'seven_zip04_single_lzma2_v1'
        self.interpreter = interpreter_elf()
        self.dual = dual_elf()[0]
        self.sevenzip = sevenzip()
        self.entries = [('AndroidManifest.xml', self.manifest),
                        ('lib/arm64-v8a/libordinary.so', elf_header()),
                        (self.interpreter_path, self.interpreter),
                        (self.dual_path, self.dual), (self.archive_path, self.sevenzip)]
        self.candidate = {'package': 'org.example.fixture', 'version_name': '1',
                          'version_code': 1, 'version_code_major': 0,
                          'min_sdk_version': 23, 'target_sdk_version': 35,
                          'native_abis': ['arm64-v8a'],
                          'publisher_payloads': sorted([
                              pin(self.interpreter, self.interpreter_path, kind=self.interpreter_kind),
                              pin(self.dual, self.dual_path, kind=self.dual_kind),
                              pin(self.sevenzip, self.archive_path, kind=self.sevenzip_kind)],
                              key=lambda row: row['path'])}
        self.identity = {'manifest_binary_sha256': hashlib.sha256(self.manifest).hexdigest()}
        manifest = {key: self.candidate[key] for key in ('package', 'version_name', 'version_code',
                                                        'version_code_major')}
        manifest.update(min_sdk_version='23', target_sdk_version='35', split_name=None,
                        uses_split=None, config_for_split=None, is_feature_split=False,
                        is_split_required=False, isolated_splits=False,
                        required_split_types=[], split_types=[])
        self.enterContext(patch.object(gate, 'manifest_observation', return_value=manifest))

    def observe(self):
        return gate.binary_observation(io.BytesIO(archive(self.entries)), self.identity, self.candidate)

    def reject(self, pattern='.'):
        with self.assertRaisesRegex((ValueError, zipfile.BadZipFile), pattern):
            self.observe()

    def test_mixed_architectures_are_literal_source_payloads_only(self):
        result = self.observe()
        self.assertEqual(result['mixed_isa_source_payloads'], sorted([self.interpreter_path, self.dual_path]))
        self.assertEqual([row['path'] for row in result['native_libraries']],
                         ['lib/arm64-v8a/libordinary.so'])
        observed = {row['entry_name']: row for row in result['publisher_payloads']}
        self.assertEqual((observed[self.interpreter_path]['actual_elf_class'],
                          observed[self.interpreter_path]['actual_elf_machine']), (1, 40))
        self.assertEqual((observed[self.dual_path]['actual_elf_class'],
                          observed[self.dual_path]['actual_elf_machine']), (2, 62))
        for path in result['mixed_isa_source_payloads']:
            item = observed[path]
            self.assertIs(item['crosses_directory_abi'], True)
            self.assertIs(item['counted_as_directory_native_library'], False)
            for key in gate._NO_CREDIT:
                self.assertIs(item[key], False)
        self.assertTrue(observed[self.archive_path]['archive_contents_verified'])
        for key in gate._NO_CREDIT:
            self.assertIs(result[key], False)

    def test_mixed_entries_cannot_supply_the_only_arm64_witness(self):
        self.entries = [item for item in self.entries if item[0] != 'lib/arm64-v8a/libordinary.so']
        self.reject('lacks an actual ELF header')

    def test_unpinned_cross_isa_entries_still_fail(self):
        for path in (self.interpreter_path, self.dual_path, self.archive_path):
            saved = copy.deepcopy(self.candidate['publisher_payloads'])
            self.candidate['publisher_payloads'] = [row for row in saved if row['path'] != path]
            with self.subTest(path=path):
                self.reject('Unpinned')
            self.candidate['publisher_payloads'] = saved

    def test_literal_content_observation_and_kind_are_required(self):
        original = copy.deepcopy(self.candidate['publisher_payloads'])
        for key, value in (('sha256', '0' * 64), ('observation_sha256', '0' * 64),
                           ('bytes', len(self.dual) + 1), ('format', self.interpreter_kind)):
            self.candidate['publisher_payloads'] = copy.deepcopy(original)
            row = next(row for row in self.candidate['publisher_payloads'] if row['path'] == self.dual_path)
            row[key] = value
            with self.subTest(field=key):
                self.reject('pin|Expected bounded ELF32')

    def test_same_isa_reclassification_is_not_a_mixed_payload(self):
        for data, path, kind in ((self.interpreter, 'lib/armeabi-v7a/libwb.so', self.interpreter_kind),
                                 (self.dual, 'lib/x86_64/libDexHelper-x86.so', self.dual_kind)):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'matches its directory ABI'):
                gate.inspect_payload(data, path, 'org.example.fixture', kind)

    def test_old_precise_interpreter_and_dual_view_rejections_survive_composition(self):
        for data in (interpreter_elf(entry=4), interpreter_elf(interpreter=b'/wrong/linker\0'),
                     interpreter_elf(interpreters=2), interpreter_elf(machine=3)):
            with self.subTest(kind='interpreter'), self.assertRaises(ValueError):
                gate.inspect_payload(data, self.interpreter_path, 'org.example.fixture', self.interpreter_kind)
        for data in (self.dual[:64], self.dual[:1000], elf_header()):
            with self.subTest(kind='dual'), self.assertRaises(ValueError):
                gate.inspect_payload(data, self.dual_path, 'org.example.fixture', self.dual_kind)

    def test_new_archive_pin_does_not_accept_old_or_corrupt_format(self):
        for data in (self.sevenzip[:7] + b'\x03' + self.sevenzip[8:], self.sevenzip[:-1]):
            self.entries = [(path, data if path == self.archive_path else body)
                            for path, body in self.entries]
            row = next(row for row in self.candidate['publisher_payloads'] if row['path'] == self.archive_path)
            row['bytes'], row['sha256'] = len(data), hashlib.sha256(data).hexdigest()
            with self.subTest(size=len(data)):
                self.reject('0.4|range|EOF')


if __name__ == '__main__':
    unittest.main()
