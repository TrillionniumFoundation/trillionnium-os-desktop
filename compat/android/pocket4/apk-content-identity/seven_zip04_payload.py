"""Verify a bounded 7z 0.4, one regular file, one LZMA2 stream source payload.

The exact supported profile has an unencoded header, one pack stream at offset
32, one folder/coder/output/substream, and inline file metadata. Unknown coders,
properties, external metadata, encrypted/encoded headers, and extra streams are
rejected. Decompressed bytes are hashed and CRC checked in memory and discarded;
they are never written, loaded, or executed. This grants no ABI/runtime credit.

Primary format references:
https://github.com/ip7z/7zip/blob/main/DOC/7zFormat.txt
https://github.com/ip7z/7zip/blob/main/DOC/Methods.txt
"""
import hashlib
import json
import lzma
import re
import stat
import struct
import zlib


FORMAT = 'seven_zip04_single_lzma2_v1'
ARCHIVE_LIMIT = 64 * 1024 * 1024
HEADER_LIMIT = 4096
UNPACK_LIMIT = 128 * 1024 * 1024
DICTIONARY_LIMIT = 32 * 1024 * 1024
CHUNK = 1024 * 1024


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


class _Header:
    def __init__(self, data):
        self.data, self.position = data, 0

    def take(self, length):
        _need(0 <= length <= len(self.data) - self.position, '7z header read exceeds its extent')
        value = self.data[self.position:self.position + length]
        self.position += length
        return value

    def byte(self):
        return self.take(1)[0]

    def exact(self, data, label):
        _need(self.take(len(data)) == data, '7z profile differs at ' + label)

    def uint(self):
        first, value, mask = self.byte(), 0, 0x80
        for count in range(8):
            if not first & mask:
                value |= (first & (mask - 1)) << (8 * count)
                _need(count == 0 or value >= 1 << (7 * count),
                      '7z integer has a noncanonical long encoding')
                return value
            value |= self.byte() << (8 * count)
            mask >>= 1
        _need(value >= 1 << 56, '7z integer has a noncanonical long encoding')
        return value


def _decode(packed, unpack_bytes, dictionary, expected_crc):
    """One decoder, one stream, a bounded output chunk, and no file writes."""
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_RAW,
                                  filters=[{'id': lzma.FILTER_LZMA2,
                                            'dict_size': dictionary}])
    total, crc, digest, prefix = 0, 0, hashlib.sha256(), b''
    incoming = packed
    try:
        for _ in range(UNPACK_LIMIT // CHUNK + 2):
            block = decoder.decompress(incoming, max_length=min(CHUNK, unpack_bytes - total + 1))
            incoming = b''
            total += len(block)
            _need(total <= unpack_bytes, '7z decoded content exceeds its declared size')
            crc = zlib.crc32(block, crc)
            digest.update(block)
            if len(prefix) < 64:
                prefix += block[:64 - len(prefix)]
            if decoder.eof:
                break
            _need(not decoder.needs_input, '7z LZMA2 stream is truncated')
            _need(bool(block), '7z LZMA2 decoder made no progress')
        else:
            raise ValueError('7z LZMA2 output iteration bound exceeded')
    except lzma.LZMAError as exc:
        raise ValueError('7z LZMA2 stream is invalid') from exc
    _need(decoder.eof and not decoder.unused_data, '7z contains trailing bytes or more than one stream')
    _need(total == unpack_bytes, '7z decoded content differs from declared size')
    _need(crc & 0xffffffff == expected_crc, '7z decoded content CRC differs')
    return {'bytes': total, 'sha256': digest.hexdigest(), 'crc32': crc & 0xffffffff,
            'prefix_hex': prefix.hex(), 'crc_verified': True,
            'complete_stream_eof_verified': True, 'written_to_filesystem': False,
            'loaded': False, 'executed': False}


def inspect_seven_zip04_single_lzma2(data):
    _need(type(data) is bytes and 33 <= len(data) <= ARCHIVE_LIMIT,
          'Expected immutable bounded 7z 0.4 bytes')
    _need(data[:8] == b'7z\xbc\xaf\x27\x1c\x00\x04', 'Expected exact 7z 0.4 signature')
    start_crc = struct.unpack_from('<I', data, 8)[0]
    _need(zlib.crc32(data[12:32]) & 0xffffffff == start_crc, '7z start-header CRC differs')
    offset, size, header_crc = struct.unpack_from('<QQI', data, 12)
    _need(0 < offset <= ARCHIVE_LIMIT and 0 < size <= HEADER_LIMIT
          and 32 + offset + size == len(data), '7z next-header range or archive EOF differs')
    next_header = data[32 + offset:]
    _need(zlib.crc32(next_header) & 0xffffffff == header_crc, '7z next-header CRC differs')
    header = _Header(next_header)
    header.exact(b'\x01\x04\x06', 'unencoded header/main streams/pack info')
    _need(header.uint() == 0 and header.uint() == 1, '7z requires one pack stream at offset 32')
    header.exact(b'\x09', 'pack size')
    packed_size = header.uint()
    _need(packed_size == offset, '7z pack extent differs from the entire packed range')
    header.exact(b'\x00\x07\x0b\x01\x00\x01', 'pack end/one inline folder/one coder')
    header.exact(b'\x21\x21\x01', 'one simple LZMA2 coder with one property byte')
    prop = header.byte()
    _need(prop <= 40, '7z LZMA2 property is invalid')
    dictionary = 0xffffffff if prop == 40 else (2 | (prop & 1)) << (prop // 2 + 11)
    _need(dictionary <= DICTIONARY_LIMIT, '7z LZMA2 dictionary exceeds its memory bound')
    header.exact(b'\x0c', 'coder unpack size')
    unpack_size = header.uint()
    _need(0 < unpack_size <= UNPACK_LIMIT, '7z unpack size exceeds its bound')
    header.exact(b'\x00\x08\x0a\x01', 'unpack end/single substream/all-defined CRC')
    unpack_crc = struct.unpack('<I', header.take(4))[0]
    header.exact(b'\x00\x00\x05\x01', 'substreams end/main end/one file')
    properties, semantic, dummy_count = [], {}, 0
    while True:
        nid = header.byte()
        if nid == 0:
            break
        _need(nid in (0x11, 0x14, 0x15, 0x19), 'Unsupported 7z file property')
        length = header.uint()
        _need(length <= 1024, '7z file property exceeds its bound')
        position, value = header.position, header.take(length)
        properties.append({'id': nid, 'relative_offset': position, 'bytes': length,
                           'sha256': _sha(value)})
        if nid == 0x19:
            dummy_count += 1
            _need(dummy_count <= 2 and 1 <= length <= 8 and value == bytes(length),
                  '7z dummy property is not bounded zero padding')
            continue
        _need(nid not in semantic, '7z has a duplicate file property')
        if nid == 0x11:
            _need(5 <= length <= 515 and value[0] == 0 and length % 2 == 1,
                  '7z name is external or has invalid UTF-16 extent')
            name = value[1:].decode('utf-16-le', 'strict')
            _need(name.endswith('\0') and name.count('\0') == 1,
                  '7z requires exactly one terminated file name')
            name = name[:-1]
            _need(re.fullmatch(r'lib[A-Za-z0-9_.$+\-]+\.so', name) is not None,
                  '7z member name is not a safe single library basename')
            semantic[nid] = name
        elif nid == 0x14:
            _need(length == 10 and value[:2] == b'\x01\x00',
                  '7z mtime must be one defined inline FILETIME')
            semantic[nid] = struct.unpack_from('<Q', value, 2)[0]
        else:
            _need(length == 6 and value[:2] == b'\x01\x00',
                  '7z attributes must be one defined inline value')
            attributes = struct.unpack_from('<I', value, 2)[0]
            mode = attributes >> 16
            _need(attributes & 0xffff == 0x8020 and stat.S_ISREG(mode)
                  and mode & 0o7777 in (0o644, 0o755),
                  '7z member is not a regular nonprivileged file with known attributes')
            semantic[nid] = attributes
    header.exact(b'\x00', 'header end')
    _need(header.position == len(next_header), '7z next header contains trailing data')
    _need(set(semantic) == {0x11, 0x14, 0x15}, '7z required inline file metadata is missing')
    decoded = _decode(data[32:32 + offset], unpack_size, dictionary, unpack_crc)
    layout = {'schema': 'seven-zip04-single-lzma2-layout-v1',
              'archive_version': [0, 4],
              'signature_header': {'offset': 0, 'bytes': 32, 'sha256': _sha(data[:32]),
                                   'start_header_crc32': start_crc},
              'packed_stream': {'offset': 32, 'bytes': packed_size,
                                'sha256': _sha(memoryview(data)[32:32 + offset])},
              'next_header': {'offset': 32 + offset, 'bytes': size,
                              'sha256': _sha(next_header), 'crc32': header_crc},
              'codec': {'id_hex': '21', 'name': 'LZMA2', 'property_byte': prop,
                        'dictionary_bytes': dictionary, 'input_stream_count': 1,
                        'output_stream_count': 1, 'encrypted': False},
              'file': {'name': semantic[0x11], 'mtime_filetime': semantic[0x14],
                       'attributes_u32': semantic[0x15], 'posix_mode': semantic[0x15] >> 16,
                       **decoded}, 'file_properties': properties}
    canonical = json.dumps(layout, sort_keys=True, separators=(',', ':'),
                           ensure_ascii=False, allow_nan=False).encode('utf-8')
    return {'format': FORMAT, 'bytes': len(data), 'sha256': _sha(data),
            'layout': layout, 'layout_sha256': _sha(canonical),
            'archive_contents_decoded': True, 'archive_contents_verified': True,
            'member_count': 1, 'archive_written_to_filesystem': False,
            'native_execution_verified': False, 'abi_compatibility_verified': False,
            'inner_code_executed': False, 'runtime_qualified': False, 'production_ready': False}
