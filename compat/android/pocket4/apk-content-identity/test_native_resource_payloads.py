"""Ordinary parser tests; optional real inputs remain external to the source tree.

Run with python3 -I -B test_native_resource_payloads.py. To add the two actual
12306 byte-parser cases, also pass --real-apk and --expect-apk-sha256. This does
not repeat APK signature verification or grant candidate/runtime admission.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest
import zipfile
import zlib

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import native_resource_payloads as payloads


def sha(body):
    return hashlib.sha256(body).hexdigest()


def archive(packed=b'invented packed bytes', next_header=b'\x01\x00'):
    start = struct.pack('<QQI', len(packed), len(next_header), zlib.crc32(next_header) & 0xffffffff)
    return b'7z\xbc\xaf\x27\x1c\x00\x03' + struct.pack('<I', zlib.crc32(start) & 0xffffffff) + start + packed + next_header


def archive_range(body, offset=None, size=None):
    value = bytearray(body)
    if offset is not None:
        struct.pack_into('<Q', value, 12, offset)
    if size is not None:
        struct.pack_into('<Q', value, 20, size)
    struct.pack_into('<I', value, 8, zlib.crc32(value[12:32]) & 0xffffffff)
    return bytes(value)


def elf(soname=b'libfixture.so', needed=None, interpreter=b'/system/bin/linker\0',
        interpreters=1, dynamics=1, duplicate_load=False, entry=0, machine=40,
        flags1=1, extra_tags=None):
    needed = [b'libc.so'] if needed is None else needed
    strings = bytearray(b'\0' + soname + b'\0')
    offsets = []
    for value in needed:
        offsets.append(len(strings))
        strings += value + b'\0'
    tags = [(5, 0x1800), (10, len(strings)), (14, 1)]
    tags += [(1, offset) for offset in offsets]
    tags += [(30, 8), (0x6ffffffb, flags1)] + (extra_tags or []) + [(0, 0)]
    dynamic = b''.join(struct.pack('<iI', tag, value) for tag, value in tags)
    body = bytearray(4096)
    programs = [(3, 256 + i * 32, 0x1100 + i * 32, 0x1100 + i * 32,
                 len(interpreter), len(interpreter), 4, 1) for i in range(interpreters)]
    load = (1, 0, 0x1000, 0x1000, len(body), len(body), 5, 4096)
    programs += [load] * (2 if duplicate_load else 1)
    programs += [(2, 512, 0x1200, 0x1200, len(dynamic), len(dynamic), 6, 4)] * dynamics
    body[:16] = b'\x7fELF\x01\x01\x01' + b'\0' * 9
    struct.pack_into('<HHIIIIIHHHHHH', body, 16, 3, machine, 1, entry, 52, 0, 0,
                     52, 32, len(programs), 0, 0, 0)
    for i, program in enumerate(programs):
        struct.pack_into('<8I', body, 52 + i * 32, *program)
    for i in range(interpreters):
        body[256 + i * 32:256 + i * 32 + len(interpreter)] = interpreter
    body[512:512 + len(dynamic)] = dynamic
    body[2048:2048 + len(strings)] = strings
    return bytes(body)


def u32(body, offset, value):
    changed = bytearray(body)
    struct.pack_into('<I', changed, offset, value)
    return bytes(changed)


def dyn(body, wanted, replacement):
    changed = bytearray(body)
    for position in range(512, 2048, 8):
        tag, unused = struct.unpack_from('<iI', changed, position)
        if tag == wanted:
            struct.pack_into('<I', changed, position + 4, replacement)
            return bytes(changed)
        if tag == 0:
            break
    raise AssertionError('Fixture dynamic tag missing')


class ResultChecks:
    def common(self, result, body):
        self.assertEqual(result['bytes'], len(body))
        self.assertEqual(result['sha256'], sha(body))
        canonical = json.dumps(result['layout'], sort_keys=True, separators=(',', ':'),
                               ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.assertEqual(result['layout_sha256'], sha(canonical))
        self.assertTrue(result['source_only'])
        for name in ('candidate_admission_issued', 'loaded', 'installed',
                     'native_compatibility_qualified', 'dispatch_runtime_observed',
                     'native_runtime_qualified', 'runtime_qualified', 'production_ready',
                     'counted_as_directory_native_library'):
            self.assertIs(result[name], False, name)


class ArchiveTests(ResultChecks, unittest.TestCase):
    def test_complete_header_and_payload_are_bound_without_decoding(self):
        body = archive()
        result = payloads.inspect_embedded_7z(body)
        self.common(result, body)
        self.assertEqual(result['kind'], 'embedded_7z_archive')
        self.assertFalse(result['native_elf'])
        self.assertFalse(result['archive_contents_decoded'])
        self.assertFalse(result['archive_contents_verified'])
        self.assertEqual(result['layout']['next_header']['end'], len(body))
        changed = archive(packed=b'altered packed bytes')
        self.assertNotEqual(result['layout_sha256'], payloads.inspect_embedded_7z(changed)['layout_sha256'])
        self.assertEqual(result, payloads.inspect_embedded_7z(body))

    def test_only_immutable_bounded_bytes_are_accepted(self):
        for body in (None, '7z', bytearray(archive()), memoryview(archive()), b'', b'0' * 32):
            with self.subTest(kind=type(body).__name__), self.assertRaises(ValueError):
                payloads.inspect_embedded_7z(body)

    def test_exact_version_and_magic_are_required(self):
        for offset in (0, 5, 6, 7):
            body = bytearray(archive()); body[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                payloads.inspect_embedded_7z(bytes(body))

    def test_start_and_next_header_crc_failures_are_distinct(self):
        first = bytearray(archive()); first[12] ^= 1
        with self.assertRaisesRegex(ValueError, 'start-header CRC'):
            payloads.inspect_embedded_7z(bytes(first))
        second = bytearray(archive()); second[-1] ^= 1
        with self.assertRaisesRegex(ValueError, 'next-header CRC'):
            payloads.inspect_embedded_7z(bytes(second))

    def test_ranges_reject_zero_huge_offset_and_size(self):
        for body in (archive_range(archive(), size=0), archive_range(archive(), size=65537),
                     archive_range(archive(), offset=2**64 - 1), archive_range(archive(), size=2**64 - 1)):
            with self.assertRaises(ValueError):
                payloads.inspect_embedded_7z(body)

    def test_truncation_trailing_bytes_and_non_EOF_header_are_rejected(self):
        for body in (archive()[:-1], archive() + b'extra', archive_range(archive(), offset=0)):
            with self.assertRaises(ValueError):
                payloads.inspect_embedded_7z(body)

    def test_next_header_limit_has_a_valid_boundary(self):
        self.common(payloads.inspect_embedded_7z(archive(next_header=b'a' * 65536)),
                    archive(next_header=b'a' * 65536))
        with self.assertRaises(ValueError):
            payloads.inspect_embedded_7z(archive(next_header=b'a' * 65537))

    def test_archive_whole_body_limit_is_enforced(self):
        body = archive(packed=b'x' * (64 * 1024 * 1024))
        with self.assertRaisesRegex(ValueError, 'bounded 7z'):
            payloads.inspect_embedded_7z(body)


class InterpreterTests(ResultChecks, unittest.TestCase):
    def test_literal_interpreter_and_complete_dynamic_identity(self):
        body = elf()
        result = payloads.inspect_interpreter_tagged_et_dyn(body)
        self.common(result, body)
        self.assertEqual((result['elf_class'], result['elf_machine'], result['elf_type'], result['entry_point']),
                         (1, 40, 3, 0))
        self.assertEqual(result['interpreter'], '/system/bin/linker')
        self.assertEqual(result['soname'], 'libfixture.so')
        self.assertEqual(result['dynamic_needed'], ['libc.so'])
        self.assertTrue(result['has_interpreter'])
        self.assertFalse(result['standalone_executable_role_established'])
        self.assertEqual(result, payloads.inspect_interpreter_tagged_et_dyn(body))

    def test_mutable_and_oversized_elf_input_is_rejected(self):
        for body in (None, bytearray(elf()), memoryview(elf()), b''):
            with self.assertRaises(ValueError):
                payloads.inspect_interpreter_tagged_et_dyn(body)
        with self.assertRaises(ValueError):
            payloads.inspect_interpreter_tagged_et_dyn(elf() + b'\0' * (16 * 1024 * 1024 - 4096 + 1))

    def test_only_actual_ARM32_zero_entry_form_is_supported(self):
        for body in (elf(machine=3), elf(machine=183), elf(entry=0x1100), elf(entry=0xffffffff),
                     elf()[:4] + b'\x02' + elf()[5:]):
            with self.assertRaises(ValueError):
                payloads.inspect_interpreter_tagged_et_dyn(body)

    def test_missing_duplicate_and_nonliteral_interpreters_are_rejected(self):
        variants = [elf(interpreters=0), elf(interpreters=2)]
        variants += [elf(interpreter=value) for value in (
            b'/system/bin/linker64\0', b'system/bin/linker\0', b'/tmp/linker\0',
            b'/system/bin/linker', b'/system/bin/linker\0extra\0')]
        for body in variants:
            with self.assertRaises(ValueError):
                payloads.inspect_interpreter_tagged_et_dyn(body)

    def test_interpreter_must_precede_loadable_segments(self):
        body = bytearray(elf())
        body[52:84], body[84:116] = body[84:116], body[52:84]
        with self.assertRaisesRegex(ValueError, 'precede'):
            payloads.inspect_interpreter_tagged_et_dyn(bytes(body))

    def test_program_table_and_segment_file_bounds(self):
        wrapped = u32(elf(), 84 + 8, 0xfffff700)
        wrapped = u32(wrapped, 116 + 8, 0xfffff900)
        wrapped = dyn(wrapped, 5, 0xffffff00)
        for body in (u32(elf(), 28, 0xfffffff0), u32(elf(), 84 + 16, 4097),
                     u32(elf(), 84 + 20, 4095), u32(elf(), 116 + 4, 4090), wrapped):
            with self.assertRaises(ValueError):
                payloads.inspect_interpreter_tagged_et_dyn(body)

    def test_dynamic_table_must_be_unique_integral_and_mapped(self):
        variants = [elf(dynamics=0), elf(dynamics=2), elf(duplicate_load=True),
                    u32(elf(), 116 + 8, 0x1204), u32(elf(), 116 + 16, 55)]
        for body in variants:
            with self.assertRaises(ValueError):
                payloads.inspect_interpreter_tagged_et_dyn(body)

    def test_missing_null_and_duplicate_identity_tags_are_rejected(self):
        body = bytearray(elf())
        tag, offset = None, 512
        while tag != 0:
            tag = struct.unpack_from('<i', body, offset)[0]
            if tag == 0:
                struct.pack_into('<i', body, offset, 21)
                break
            offset += 8
        with self.assertRaisesRegex(ValueError, 'DT_NULL'):
            payloads.inspect_interpreter_tagged_et_dyn(bytes(body))
        for extra in ((5, 0x1800), (10, 20), (14, 1), (30, 8), (0x6ffffffb, 1)):
            with self.subTest(tag=extra[0]), self.assertRaisesRegex(ValueError, 'Duplicate'):
                payloads.inspect_interpreter_tagged_et_dyn(elf(extra_tags=[extra]))

    def test_missing_identity_and_outside_string_mapping_are_rejected(self):
        body = bytearray(elf()); struct.pack_into('<i', body, 512 + 16, 21)
        for changed in (bytes(body), dyn(elf(), 5, 0x9000), dyn(elf(), 10, 1024 * 1024 + 1),
                        dyn(elf(), 10, 0), dyn(elf(), 14, 4096)):
            with self.assertRaises(ValueError):
                payloads.inspect_interpreter_tagged_et_dyn(changed)

    def test_PIE_and_excessive_needed_lists_are_rejected(self):
        for body in (elf(flags1=0x08000001), elf(needed=[b'libc.so'] * 65)):
            with self.assertRaises(ValueError):
                payloads.inspect_interpreter_tagged_et_dyn(body)

    def test_dynamic_strings_require_bounded_terminated_UTF8(self):
        for body in (elf(soname=b'a' * 257), elf(soname=b'\xff'), elf(needed=[b'b' * 257]),
                     dyn(elf(), 1, 4096)):
            with self.assertRaises(ValueError):
                payloads.inspect_interpreter_tagged_et_dyn(body)
        body = bytearray(elf())
        size = struct.unpack_from('<I', body, 512 + 12)[0]
        body[2048 + size - 1] = 65
        with self.assertRaises(ValueError):
            payloads.inspect_interpreter_tagged_et_dyn(bytes(body))

    def test_canonical_layout_uses_unescaped_UTF8_and_binds_unused_bytes(self):
        body = elf(soname='libé.so'.encode(), needed=['lib依赖.so'.encode()])
        result = payloads.inspect_interpreter_tagged_et_dyn(body)
        self.common(result, body)
        escaped = json.dumps(result['layout'], sort_keys=True, separators=(',', ':'),
                             ensure_ascii=True, allow_nan=False).encode()
        self.assertNotEqual(result['layout_sha256'], sha(escaped))
        changed = bytearray(body); changed[-1] = 1
        self.assertNotEqual(result['layout_sha256'],
                            payloads.inspect_interpreter_tagged_et_dyn(bytes(changed))['layout_sha256'])


def real_case(apk_path, expected_sha, observed):
    class ActualPayloadTests(ResultChecks, unittest.TestCase):
        @classmethod
        def setUpClass(cls):
            cls.before = apk_path.stat()
            def whole_sha():
                digest = hashlib.sha256()
                with apk_path.open('rb') as stream:
                    for raw in iter(lambda: stream.read(1024 * 1024), b''):
                        digest.update(raw)
                return digest.hexdigest()
            cls.whole_sha = staticmethod(whole_sha)
            assert whole_sha() == expected_sha == 'c7e56101e5753002bba220ce40d07b00d4bc822e1eeef12bbe36ec9e2f8e272d'

        @classmethod
        def tearDownClass(cls):
            after = apk_path.stat()
            for field in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'):
                assert getattr(cls.before, field) == getattr(after, field)
            assert cls.whole_sha() == expected_sha

        def member(self, name, length, digest):
            with zipfile.ZipFile(apk_path) as archive_file:
                self.assertEqual(archive_file.getinfo(name).file_size, length)
                with archive_file.open(name) as stream:
                    body = stream.read(length + 1)
            self.assertEqual(len(body), length)
            self.assertEqual(sha(body), digest)
            return body

        def test_actual_7z_bytes_parse_without_decoding(self):
            body = self.member('lib/arm64-v8a/libWebViewCore_3.22.2.72.240709175818_7z_uc.so',
                               13999047, 'fb2588ecfbfd0e8ae55c1454551098f24ab0308f88329b625d27e6b05c809c4e')
            result = payloads.inspect_embedded_7z(body)
            self.common(result, body)
            self.assertEqual(result['layout']['start_header']['crc32'], 0xec19ea22)
            self.assertEqual(result['layout']['next_header']['crc32'], 0xa250b709)
            self.assertEqual(result['layout']['next_header']['bytes'], 37)
            observed['embedded_7z_archive'] = result

        def test_actual_interpreter_ET_DYN_remains_unqualified(self):
            body = self.member('lib/arm64-v8a/libwb.so', 2208920,
                               'cd177d09ed8a9a0b902c42b1138895d958ffb185c6b47b6fa52b9149b8849a99')
            result = payloads.inspect_interpreter_tagged_et_dyn(body)
            self.common(result, body)
            self.assertEqual(result['soname'], 'libwb.so')
            self.assertEqual(result['dynamic_needed'],
                             ['libz.so', 'liblog.so', 'libstdc++.so', 'libm.so', 'libc.so', 'libdl.so'])
            self.assertEqual(result['layout']['program_table']['count'], 8)
            observed['interpreter_tagged_et_dyn'] = result
    return ActualPayloadTests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--real-apk', type=Path)
    parser.add_argument('--expect-apk-sha256')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if bool(args.real_apk) != bool(args.expect_apk_sha256):
        parser.error('Real APK and its external SHA-256 are required together')
    suite = unittest.TestSuite()
    for case in (ArchiveTests, InterpreterTests):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    synthetic_count = suite.countTestCases()
    observed = {}
    if args.real_apk:
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(
            real_case(args.real_apk, args.expect_apk_sha256, observed)))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = (result.wasSuccessful() and not result.skipped and not result.expectedFailures
              and not result.unexpectedSuccesses and result.testsRun == synthetic_count + (2 if args.real_apk else 0))
    report = {'schema': 'native-resource-byte-parser-tests-v1', 'source_only': True,
              'tests_run': result.testsRun, 'synthetic_cases': synthetic_count,
              'real_cases': 2 if args.real_apk else 0, 'passed': bool(passed),
              'tests_skipped': len(result.skipped), 'real_payloads': observed,
              'candidate_admission_issued': False, 'loaded': False,
              'native_runtime_qualified': False, 'installed': False, 'production_ready': False}
    if args.report:
        with args.report.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write('\n')
    print(json.dumps({key: report[key] for key in ('tests_run', 'synthetic_cases', 'real_cases', 'passed', 'tests_skipped')}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
