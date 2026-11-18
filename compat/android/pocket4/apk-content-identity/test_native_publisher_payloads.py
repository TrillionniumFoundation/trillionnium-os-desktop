"""Negative controls for publisher containers; fixtures never execute code."""

import hashlib
import io
import stat
import sys
from pathlib import Path
import struct
import unittest
import warnings
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import native_publisher_payloads as payloads


def archive(entries=(('classes.dex', b'opaque bytecode fixture'),), compression=zipfile.ZIP_DEFLATED):
    buffer = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        with zipfile.ZipFile(buffer, 'w', compression=compression) as target:
            for name, content in entries:
                target.writestr(name, content)
    return buffer.getvalue()


def raw_zstd(content=b'abc', checksum=False):
    if len(content) > 255:
        raise ValueError('Small fixed fixture only')
    return (bytes.fromhex('28b52ffd') + bytes([0x20 | (4 if checksum else 0), len(content)])
            + ((len(content) << 3) | 1).to_bytes(3, 'little') + content
            + (b'\x11\x22\x33\x44' if checksum else b''))


def csop(frame=None):
    return b'CSOP' + bytes(8) + bytes.fromhex('12345678') + (raw_zstd() if frame is None else frame)


def meta_fixture():
    strings = b'libunit.so\0libc.so\0'
    return struct.pack('<IIQII', 1, 24, 4096, 0, 1) + strings


def resign_dex(data):
    data = bytearray(data)
    data[12:32] = hashlib.sha1(data[32:]).digest()
    struct.pack_into('<I', data, 8, zlib.adler32(data[12:]) & 0xffffffff)
    return bytes(data)


def minimal_dex():
    # Independent minimal DEX035: a header and a two-entry self-describing map.
    data = bytearray(140)
    data[:8] = b'dex\n035\0'
    struct.pack_into('<6I', data, 32, 140, 112, 0x12345678, 0, 0, 112)
    struct.pack_into('<II', data, 104, 28, 112)
    struct.pack_into('<I', data, 112, 2)
    struct.pack_into('<HHII', data, 116, 0, 0, 1, 0)
    struct.pack_into('<HHII', data, 128, 0x1000, 0, 1, 112)
    return resign_dex(data)


class EmbeddedZipTests(unittest.TestCase):
    def test_actual_member_hash_crc_and_no_execution_credit(self):
        result = payloads.inspect_embedded_zip(archive())
        item = result['members'][0]
        self.assertEqual(item['sha256'], hashlib.sha256(b'opaque bytecode fixture').hexdigest())
        self.assertEqual(item['crc32'], f'{zlib.crc32(b"opaque bytecode fixture"):08x}')
        self.assertFalse(result['inner_code_executed'])
        self.assertFalse(result['native_execution_verified'])

    def test_traversal_absolute_backslash_empty_segments_and_aliases(self):
        for name in ('../escape', '/absolute', 'a/../b', 'a\\b', 'a//b', './a', 'C:drive'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                payloads.inspect_embedded_zip(archive(((name, b'x'),)))
        for entries in ((('x', b'1'), ('x', b'2')),
                        (('x', b'1'), ('x/y', b'2'))):
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                payloads.inspect_embedded_zip(archive(entries))

    def test_case_distinct_android_resource_paths_are_distinct_members(self):
        result = payloads.inspect_embedded_zip(archive((('res/AR.xml', b'1'), ('res/Ar.xml', b'2'))))
        self.assertTrue(result['path_case_sensitive'])
        self.assertEqual(result['member_count'], 2)
        self.assertNotEqual(result['members'][0]['sha256'], result['members'][1]['sha256'])
        with self.assertRaisesRegex(ValueError, 'noncanonical'):
            payloads.inspect_embedded_zip(archive((('res/e\u0301.xml', b'1'),)))

    def test_symlink_and_special_file_rejected(self):
        for mode in (stat.S_IFLNK | 0o777, stat.S_IFCHR | 0o600):
            member = zipfile.ZipInfo('liblink.so')
            member.create_system = 3
            member.external_attr = mode << 16
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                payloads.inspect_embedded_zip(archive(((member, b'../target'),)))

    def test_invalid_crc_and_local_filename_are_rejected(self):
        original = archive(compression=zipfile.ZIP_STORED)
        changed = bytearray(original)
        changed[30 + len('classes.dex')] ^= 1
        with self.assertRaisesRegex(ValueError, 'CRC'):
            payloads.inspect_embedded_zip(bytes(changed))
        changed = bytearray(original)
        changed[30] = ord('X')
        with self.assertRaisesRegex(ValueError, 'filename'):
            payloads.inspect_embedded_zip(bytes(changed))

    def test_nul_encryption_unsupported_method_and_zip64_are_rejected(self):
        original = archive()
        central = original.index(b'PK\x01\x02')
        for field in ('nul', 'encrypted', 'method', 'zip64'):
            changed = bytearray(original)
            if field == 'nul':
                changed[30] = changed[central + 46] = 0
            elif field == 'encrypted':
                struct.pack_into('<H', changed, 6, 1)
                struct.pack_into('<H', changed, central + 8, 1)
            elif field == 'method':
                struct.pack_into('<H', changed, 8, 99)
                struct.pack_into('<H', changed, central + 10, 99)
            else:
                struct.pack_into('<H', changed, central + 6, 45)
            with self.subTest(field=field), self.assertRaises(ValueError):
                payloads.inspect_embedded_zip(bytes(changed))

    def test_prefix_trailing_bytes_and_decompression_bomb_rejected(self):
        good = archive()
        for changed in (b'MZ' + good, good + b'trailing', archive((('bomb', bytes(8 * 1024 * 1024)),))):
            with self.subTest(size=len(changed)), self.assertRaises(ValueError):
                payloads.inspect_embedded_zip(changed)

    def test_overlapping_local_header_offsets_are_rejected(self):
        changed = bytearray(archive((('one', b'1'), ('two', b'2'))))
        first = changed.index(b'PK\x01\x02')
        second = changed.index(b'PK\x01\x02', first + 4)
        struct.pack_into('<I', changed, second + 42, 0)
        with self.assertRaisesRegex(ValueError, 'local-header'):
            payloads.inspect_embedded_zip(bytes(changed))

    def test_embedded_signing_block_is_bounded_but_not_cryptographic_credit(self):
        original = archive()
        eocd = original.rindex(b'PK\x05\x06')
        cd = struct.unpack_from('<I', original, eocd + 16)[0]
        pair = struct.pack('<QI', 6, 0x7109871a) + b'ab'
        block_size = len(pair) + 24
        block = struct.pack('<Q', block_size) + pair + struct.pack('<Q', block_size) + b'APK Sig Block 42'
        changed = bytearray(original[:cd] + block + original[cd:])
        struct.pack_into('<I', changed, eocd + len(block) + 16, cd + len(block))
        result = payloads.inspect_embedded_zip(bytes(changed))
        self.assertFalse(result['apk_signing_block']['cryptographic_signature_verified'])
        changed[cd] ^= 1
        with self.assertRaisesRegex(ValueError, 'signing-block'):
            payloads.inspect_embedded_zip(bytes(changed))

    def test_exact_zero_alignment_padding_before_signing_block(self):
        original = archive()
        eocd = original.rindex(b'PK\x05\x06')
        cd = struct.unpack_from('<I', original, eocd + 16)[0]
        pair = struct.pack('<QI', 6, 0x7109871a) + b'ab'
        block_size = len(pair) + 24
        block = struct.pack('<Q', block_size) + pair + struct.pack('<Q', block_size) + b'APK Sig Block 42'
        padding_size = (-cd) % 4096

        def padded(size, nonzero=False):
            padding = bytearray(size)
            if nonzero:
                padding[0] = 1
            extra = padding + block
            changed = bytearray(original[:cd] + extra + original[cd:])
            struct.pack_into('<I', changed, eocd + len(extra) + 16, cd + len(extra))
            return bytes(changed)

        result = payloads.inspect_embedded_zip(padded(padding_size))
        self.assertEqual(result['apk_signing_block']['zero_alignment_padding_bytes'], padding_size)
        self.assertEqual(result['apk_signing_block']['offset'], 4096)
        for changed in (padded(padding_size, True), padded(padding_size + 4096), padded(padding_size - 1)):
            with self.assertRaisesRegex(ValueError, 'alignment padding'):
                payloads.inspect_embedded_zip(changed)


class CsoTests(unittest.TestCase):
    def test_small_standard_zstd_frame(self):
        result = payloads.inspect_csop(csop())
        self.assertEqual(result['observed_token_hex'], '12345678')
        self.assertEqual(result['zstd']['declared_content_bytes'], 3)
        self.assertEqual(result['zstd']['blocks'][0]['block_type'], 'raw')
        self.assertFalse(result['zstd']['decoded_content_verified'])

    def test_checksum_is_accounted_for_without_claiming_verification(self):
        result = payloads.inspect_csop(csop(raw_zstd(checksum=True)))
        self.assertEqual(result['zstd']['checksum_hex'], '11223344')
        self.assertFalse(result['zstd']['checksum_verified'])

    def test_truncation_concatenation_unknown_flags_and_reserved_block(self):
        frame = raw_zstd()
        reserved_block = frame[:6] + bytes([31, 0, 0]) + frame[9:]
        for invalid in (frame[:-1], frame + frame, frame + b'x',
                        frame[:4] + bytes([0x28]) + frame[5:],
                        frame[:4] + bytes([0x21]) + frame[5:], reserved_block,
                        bytes.fromhex('502a4d1800000000')):
            with self.subTest(frame=invalid.hex()), self.assertRaises(ValueError):
                payloads.inspect_csop(csop(invalid))
        with self.assertRaisesRegex(ValueError, 'header'):
            payloads.inspect_csop(b'CSOP' + b'\1' + bytes(7) + bytes(4) + frame)

    def test_output_size_and_window_bombs_rejected(self):
        huge = bytes.fromhex('28b52ffda0') + struct.pack('<I', 0x40000000) + b'\1\0\0'
        unknown = bytes.fromhex('28b52ffd0000') + b'\1\0\0'
        inconsistent = raw_zstd()[:5] + b'\4' + raw_zstd()[6:]
        for invalid in (huge, unknown, inconsistent):
            with self.subTest(frame=invalid.hex()), self.assertRaises(ValueError):
                payloads.inspect_csop(csop(invalid))

    def test_csos_exact_token_and_abi_extent(self):
        stub = b'CSOS' + bytes.fromhex('12345678') + struct.pack('<I', 9) + b'arm64-v8a'
        result = payloads.inspect_csos(stub, 'arm64-v8a')
        self.assertEqual(result['observed_token_hex'], '12345678')
        self.assertFalse(result['abi_compatibility_verified'])
        for invalid, abi in ((stub + b'\0', 'arm64-v8a'), (stub, 'x86_64'), (stub[:11], 'arm64-v8a')):
            with self.subTest(abi=abi, size=len(invalid)), self.assertRaises(ValueError):
                payloads.inspect_csos(invalid, abi)

    def test_meta_raw_layout_and_exact_strings(self):
        result = payloads.inspect_cso_meta(meta_fixture())
        self.assertEqual(result['records'][0]['strings'], ['libunit.so', 'libc.so'])
        self.assertEqual(result['records'][0]['raw_u64_at_0'], 4096)
        self.assertEqual(result['field_semantics'], 'observed_raw_layout_only')
        self.assertFalse(result['loader_semantics_verified'])

    def test_meta_aliases_wrong_offsets_counts_flags_and_trailing_bytes(self):
        original = meta_fixture()
        for offset, value in ((0, 4097), (4, 25), (16, 2), (20, 0)):
            changed = bytearray(original)
            struct.pack_into('<I', changed, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                payloads.inspect_cso_meta(bytes(changed))
        for invalid in (original[:-1], original + b'\0', original.replace(b'libc.so', b'../c.so')):
            with self.subTest(data=invalid), self.assertRaises(ValueError):
                payloads.inspect_cso_meta(invalid)


class DexTests(unittest.TestCase):
    def test_checksums_and_map_spans_without_execution_credit(self):
        result = payloads.inspect_dex035(minimal_dex())
        self.assertTrue(result['checksums_verified'])
        self.assertEqual([item['type'] for item in result['map_items']], ['0000', '1000'])
        self.assertFalse(result['bytecode_semantics_verified'])

    def test_corruption_fails_even_with_well_formed_header(self):
        changed = bytearray(minimal_dex())
        changed[-1] ^= 1
        with self.assertRaisesRegex(ValueError, 'Adler32/SHA1'):
            payloads.inspect_dex035(bytes(changed))

    def test_checksum_valid_malformed_ranges_are_still_rejected(self):
        for offset, value in ((32, 141), (36, 120), (40, 0x78563412),
                              (52, 136), (112, 65), (136, 0), (120, 0), (116, 0xf000)):
            changed = bytearray(minimal_dex())
            struct.pack_into('<I', changed, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                payloads.inspect_dex035(resign_dex(changed))


class DispatchTests(unittest.TestCase):
    def test_marker_is_exact_and_bound_to_named_payload(self):
        marker = b'6.8.260901      '
        result = payloads.inspect_native_publisher_payload(marker, 'lib/arm64-v8a/libsgmainso.version.so')
        self.assertEqual(result['version'], '6.8.260901')
        for data in (marker[:-1], marker.replace(b' ', b'\0'), b'x' * 16):
            with self.subTest(data=data), self.assertRaises(ValueError):
                payloads.inspect_version_marker(data)

    def test_unknown_opaque_elf_and_old_catch_all_styles_are_rejected(self):
        for data, name in ((b'\x7fELF' + bytes(80), 'lib/arm64-v8a/libx.so'),
                           (b'1.1.4' + bytes(11) + bytes(range(32)), 'lib/arm64-v8a/libmtguard_1.so'),
                           (b'opaque native data', 'lib/arm64-v8a/libx.so'),
                           (archive(), '../lib/arm64-v8a/libx.so'),
                           (archive(), 'lib/arm64-v8a/../libx.so'),
                           (archive(), 'lib/not-an-abi/libx.so')):
            with self.subTest(name=name), self.assertRaises(ValueError):
                payloads.inspect_native_publisher_payload(data, name)


if __name__ == '__main__':
    unittest.main()
