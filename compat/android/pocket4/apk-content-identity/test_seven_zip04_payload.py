"""7z profile integrity controls using independent, inert raw-LZMA2 streams.

No external executable, native loading, archive extraction, or SDK is involved.
"""
import hashlib
import json
import lzma
from pathlib import Path
import struct
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seven_zip04_payload as model
from native_resource_payloads import inspect_embedded_7z


CONTENT = (b'Inert archive-content integrity fixture.\n' * 513) + bytes(range(256))


def uint(value):
    for extra in range(8):
        if value < 1 << (7 * (extra + 1)):
            lead = ((0xff << (8 - extra)) & 0xff) if extra else 0
            return bytes([lead | (value >> (8 * extra))]) + value.to_bytes(8, 'little')[:extra]
    return b'\xff' + value.to_bytes(8, 'little')


def property_record(kind, value):
    return bytes([kind]) + uint(len(value)) + value


def standard_properties(name='libfixture.so', attributes=0x81a48020):
    return [(0x11, b'\0' + (name + '\0').encode('utf-16-le')),
            (0x14, b'\x01\0' + struct.pack('<Q', 12345)),
            (0x15, b'\x01\0' + struct.pack('<I', attributes))]


def wrap(packed, header, version=b'\0\x04', offset=None):
    start = struct.pack('<QQI', len(packed) if offset is None else offset,
                        len(header), zlib.crc32(header) & 0xffffffff)
    return b'7z\xbc\xaf\x27\x1c' + version + struct.pack('<I', zlib.crc32(start) & 0xffffffff) + start + packed + header


def fixture(content=CONTENT, packed=None, properties=None, declared_size=None,
            content_crc=None, dictionary_property=0, prefix=b'\x01\x04\x06',
            pack_streams=b'\x01', folder_external=b'\0', coder=b'\x21\x21\x01',
            trailer=b'\0\0', unpack_uint=None):
    if packed is None:
        packed = lzma.compress(content, format=lzma.FORMAT_RAW,
                               filters=[{'id': lzma.FILTER_LZMA2, 'dict_size': 4096}])
    if declared_size is None:
        declared_size = len(content)
    if content_crc is None:
        content_crc = zlib.crc32(content) & 0xffffffff
    if properties is None:
        properties = standard_properties()
    header = (prefix + b'\0' + pack_streams + b'\x09' + uint(len(packed))
              + b'\0\x07\x0b\x01' + folder_external + b'\x01' + coder
              + bytes([dictionary_property]) + b'\x0c'
              + (uint(declared_size) if unpack_uint is None else unpack_uint)
              + b'\0\x08\x0a\x01' + struct.pack('<I', content_crc)
              + b'\0\0\x05\x01'
              + b''.join(property_record(kind, value) for kind, value in properties)
              + trailer)
    return wrap(packed, header)


class SevenZip04Controls(unittest.TestCase):
    def reject(self, body, pattern='.'):
        with self.assertRaisesRegex(ValueError, pattern):
            model.inspect_seven_zip04_single_lzma2(body)

    def test_decodes_entire_real_lzma2_stream_and_binds_content(self):
        body = fixture()
        observed = model.inspect_seven_zip04_single_lzma2(body)
        member = observed['layout']['file']
        self.assertEqual(member['bytes'], len(CONTENT))
        self.assertEqual(member['sha256'], hashlib.sha256(CONTENT).hexdigest())
        self.assertEqual(member['crc32'], zlib.crc32(CONTENT) & 0xffffffff)
        self.assertTrue(member['crc_verified'])
        self.assertTrue(member['complete_stream_eof_verified'])
        self.assertTrue(observed['archive_contents_verified'])
        self.assertTrue(observed['archive_contents_decoded'])
        self.assertEqual(observed['sha256'], hashlib.sha256(body).hexdigest())
        canonical = json.dumps(observed['layout'], sort_keys=True, separators=(',', ':'),
                               ensure_ascii=False, allow_nan=False).encode()
        self.assertEqual(observed['layout_sha256'], hashlib.sha256(canonical).hexdigest())
        for field in ('native_execution_verified', 'abi_compatibility_verified',
                      'inner_code_executed', 'runtime_qualified', 'production_ready',
                      'archive_written_to_filesystem'):
            self.assertIs(observed[field], False)
        for field in ('written_to_filesystem', 'loaded', 'executed'):
            self.assertIs(member[field], False)

    def test_chunk_boundary_is_not_an_eof_or_size_shortcut(self):
        content = bytes(range(251)) * 20000
        observed = model.inspect_seven_zip04_single_lzma2(fixture(content))
        self.assertGreater(len(content), 4 * model.CHUNK)
        self.assertEqual(observed['layout']['file']['sha256'], hashlib.sha256(content).hexdigest())

    def test_unknown_and_old_formats_are_not_admitted(self):
        body = fixture()
        self.reject(bytearray(body), 'immutable')
        self.reject(body[:7] + b'\x03' + body[8:], '0.4')
        self.reject(b'not archive', 'bounded')
        with self.assertRaisesRegex(ValueError, '0.3'):
            inspect_embedded_7z(body)
        old = body[:7] + b'\x03' + body[8:]
        observation = inspect_embedded_7z(old)
        self.assertFalse(observation['archive_contents_verified'])
        self.assertFalse(observation['archive_contents_decoded'])

    def test_start_and_next_header_checksums_are_independent(self):
        body = fixture()
        for position, pattern in ((8, 'start-header CRC'), (12, 'start-header CRC'),
                                  (len(body) - 1, 'next-header CRC')):
            changed = bytearray(body)
            changed[position] ^= 1
            with self.subTest(position=position):
                self.reject(bytes(changed), pattern)

    def test_next_header_extent_and_exact_eof(self):
        body = fixture()
        self.reject(body + b'\0', 'range|EOF')
        self.reject(body[:-1], 'range|EOF')
        packed_size, header_size, _ = struct.unpack_from('<QQI', body, 12)
        packed, header = body[32:32 + packed_size], body[-header_size:]
        self.reject(wrap(packed, header, offset=packed_size - 1), 'range|EOF')
        self.reject(wrap(packed, header + b'\0'), 'trailing')
        self.reject(wrap(packed, header + bytes(model.HEADER_LIMIT)), 'range')

    def test_unsupported_stream_folder_and_codec_profiles(self):
        rows = [dict(prefix=b'\x17\x04\x06'), dict(pack_streams=b'\x02'),
                dict(folder_external=b'\x01'), dict(coder=b'\x21\x03\x01'),
                dict(coder=b'\x11\x21\x01'), dict(coder=b'\x21\x21\x02')]
        for params in rows:
            with self.subTest(params=params):
                self.reject(fixture(**params), 'profile|pack stream')

    def test_memory_and_output_limits_precede_decompression(self):
        for params, pattern in ((dict(dictionary_property=27), 'dictionary'),
                                (dict(dictionary_property=40), 'dictionary'),
                                (dict(dictionary_property=41), 'property'),
                                (dict(declared_size=model.UNPACK_LIMIT + 1), 'unpack size'),
                                (dict(declared_size=0), 'unpack size')):
            with self.subTest(params=params):
                self.reject(fixture(**params), pattern)

    def test_canonical_uint_boundary_vectors(self):
        vectors = [('00', 0), ('7f', 127), ('8080', 128), ('bfff', 16383),
                   ('c00040', 16384), ('ffffff000000000000', 0x0000000000ffffff),
                   ('ff0000000000000001', 1 << 56)]
        # The explicitly overlong 0xffffff vector must be rejected, not silently normalized.
        for encoded, wanted in vectors:
            parser = model._Header(bytes.fromhex(encoded))
            if encoded == 'ffffff000000000000':
                with self.assertRaisesRegex(ValueError, 'noncanonical'):
                    parser.uint()
            else:
                self.assertEqual(parser.uint(), wanted)
                self.assertEqual(parser.position, len(bytes.fromhex(encoded)))
        self.reject(fixture(content=b'A', unpack_uint=b'\x80\x01'), 'noncanonical')

    def test_name_and_external_metadata_are_not_filesystem_capabilities(self):
        for name in ('../libx.so', '/libx.so', 'libx/other.so', 'libx\\other.so',
                     'libx\0liby.so', 'libé.so', 'libx.so\0', 'libx.apk'):
            with self.subTest(name=name):
                self.reject(fixture(properties=standard_properties(name=name)), 'name|basename')
        for kind in (0x11, 0x14, 0x15):
            props = standard_properties()
            for index, (pid, value) in enumerate(props):
                if pid == kind:
                    pos = 0 if kind == 0x11 else 1
                    props[index] = (pid, value[:pos] + b'\x01' + value[pos + 1:])
            with self.subTest(external_kind=kind):
                self.reject(fixture(properties=props), 'external|inline')

    def test_only_regular_nonprivileged_member_modes(self):
        for attributes in (0xa1ff8020, 0x41ed8020, 0x89ed8020, 0x81a40020, 0x81808020):
            with self.subTest(attributes=hex(attributes)):
                self.reject(fixture(properties=standard_properties(attributes=attributes)), 'regular')
        self.assertTrue(model.inspect_seven_zip04_single_lzma2(
            fixture(properties=standard_properties(attributes=0x81ed8020)))['archive_contents_verified'])

    def test_missing_duplicate_unknown_properties_and_padding(self):
        props = standard_properties()
        for changed in (props[:-1], props + [props[0]], props + [(0x42, b'')],
                        props + [(0x19, b'X')], props + [(0x19, bytes(9))],
                        props + [(0x19, b'\0')] * 3):
            with self.subTest(props=changed):
                self.reject(fixture(properties=changed), 'missing|duplicate|Unsupported|padding')
        accepted = model.inspect_seven_zip04_single_lzma2(
            fixture(properties=[(0x19, bytes(6))] + props + [(0x19, bytes(2))]))
        self.assertTrue(accepted['archive_contents_verified'])

    def test_invalid_truncated_and_extra_compressed_streams(self):
        packed = lzma.compress(CONTENT, format=lzma.FORMAT_RAW,
                               filters=[{'id': lzma.FILTER_LZMA2, 'dict_size': 4096}])
        for changed in (packed[:-1], packed[:8], b'\xff' + packed[1:],
                        packed + b'\0', packed + packed):
            with self.subTest(length=len(changed)):
                self.reject(fixture(packed=changed), 'invalid|truncated|trailing|stream')

    def test_complete_output_size_and_crc_are_required(self):
        for params, pattern in ((dict(declared_size=len(CONTENT) - 1), 'exceeds'),
                                (dict(declared_size=len(CONTENT) + 1), 'declared size'),
                                (dict(content_crc=(zlib.crc32(CONTENT) ^ 1)), 'CRC')):
            with self.subTest(params=params):
                self.reject(fixture(**params), pattern)


if __name__ == '__main__':
    unittest.main()
