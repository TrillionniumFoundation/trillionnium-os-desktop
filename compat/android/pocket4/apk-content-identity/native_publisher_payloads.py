"""Bounded identities for publisher payloads stored under APK lib/ directories.

These results describe bytes and container layouts. They do not establish that
payloads load, execute, translate, or are compatible with any Android runtime.
ZIP members are read for CRC/hash validation but are never extracted or executed.
Zstandard content is not decompressed; its frame/block boundaries are checked.

Format references:
https://www.rfc-editor.org/rfc/rfc8878.html#section-3.1.1
https://source.android.com/docs/core/runtime/dex-format
https://source.android.com/docs/security/features/apksigning/v2
CSOP/CSOS and libcso.meta layouts below are observations from the signed WeChat
8.0.80 input. Unknown header fields retain raw names, without invented semantics.
"""

import hashlib
import re
import stat
import struct
import unicodedata
import zlib


MAX_ZIP_BYTES = 64 * 1024 * 1024
MAX_ZIP_EXPANDED = 64 * 1024 * 1024
MAX_ZIP_MEMBERS = 4096
MAX_CSOP_BYTES = 128 * 1024 * 1024
MAX_ZSTD_CONTENT_BYTES = 256 * 1024 * 1024
MAX_ZSTD_BLOCKS = 4096
MAX_META_BYTES = 4 * 1024 * 1024
MAX_META_RECORDS = 4096
MAX_DEX_BYTES = 64 * 1024 * 1024
ABIS = frozenset(('arm64-v8a', 'armeabi-v7a', 'armeabi', 'x86', 'x86_64'))
_BASENAME = re.compile(r'lib[A-Za-z0-9_.$+\-]+\.so\Z')


def _fail(message):
    raise ValueError(message)


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _bounded(data, limit, minimum=1):
    if not isinstance(data, bytes) or not minimum <= len(data) <= limit:
        _fail('Payload byte-size/type bound')


def _span(data, start, size):
    if start < 0 or size < 0 or start > len(data) or size > len(data) - start:
        _fail('Payload field exceeds byte boundary')
    return data[start:start + size]


def _result(kind, data, **fields):
    return {'format': kind, 'bytes': len(data), 'sha256': _hash(data),
            'native_execution_verified': False, 'abi_compatibility_verified': False,
            **fields}


def _zip_name(raw, flags):
    if not raw or len(raw) > 1024 or b'\0' in raw:
        _fail('ZIP empty, overlong, or NUL path')
    try:
        name = raw.decode('utf-8' if flags & 0x800 else 'cp437')
    except UnicodeDecodeError as error:
        raise ValueError('ZIP invalid filename encoding') from error
    if (name != unicodedata.normalize('NFC', name) or '\\' in name or ':' in name
            or name.startswith('/') or any(ord(c) < 32 or ord(c) == 127 for c in name)):
        _fail('ZIP noncanonical/absolute path')
    normalized = name[:-1] if name.endswith('/') else name
    if not normalized or any(p in ('', '.', '..') for p in normalized.split('/')):
        _fail('ZIP traversal or path alias')
    # Android ZIP/JAR paths are case sensitive (obfuscated resources can have
    # both res/AR.xml and res/Ar.xml). NFC/path normalization aliases still fail.
    return name, normalized


def _zip_extra(extra):
    cursor = 0
    while cursor < len(extra):
        # zipalign may reserve a zero-filled tail; it has no filename semantics.
        if not any(extra[cursor:]):
            return
        if cursor + 4 > len(extra):
            _fail('ZIP malformed extra-field header')
        kind, size = struct.unpack_from('<HH', extra, cursor)
        cursor += 4
        if cursor + size > len(extra):
            _fail('ZIP malformed extra-field size')
        if kind in (1, 0x7075):
            _fail('ZIP64 or alternate Unicode filename extra is unsupported')
        cursor += size


def _apk_signing_gap(data, absolute_offset):
    if len(data) < 32 or len(data) > 1024 * 1024 or data[-16:] != b'APK Sig Block 42':
        _fail('ZIP unaccounted gap before central directory')
    footer = struct.unpack_from('<Q', data, len(data) - 24)[0]
    padding_size = len(data) - footer - 8
    if (not 0 <= padding_size < 4096 or any(data[:padding_size])
            or (padding_size and (absolute_offset + padding_size) % 4096)):
        _fail('Embedded APK signing-block alignment padding mismatch')
    padding = data[:padding_size]
    data = data[padding_size:]
    if len(data) < 32:
        _fail('Embedded APK signing-block size mismatch')
    size = struct.unpack_from('<Q', data)[0]
    if size != footer or size != len(data) - 8:
        _fail('Embedded APK signing-block size mismatch')
    cursor, end, identifiers, pairs = 8, len(data) - 24, set(), []
    while cursor < end:
        length = struct.unpack('<Q', _span(data, cursor, 8))[0]
        cursor += 8
        if length < 4 or length > end - cursor or len(pairs) >= 64:
            _fail('Embedded APK signing-block pair bound')
        identifier = struct.unpack_from('<I', data, cursor)[0]
        if identifier in identifiers:
            _fail('Embedded APK duplicate signing-block identifier')
        identifiers.add(identifier)
        value = data[cursor + 4:cursor + length]
        pairs.append({'id': f'{identifier:08x}', 'bytes': len(value), 'sha256': _hash(value)})
        cursor += length
    if cursor != end or not pairs:
        _fail('Embedded APK signing-block extent')
    return {'bytes': len(data), 'sha256': _hash(data), 'pairs': pairs,
            'offset': absolute_offset + padding_size,
            'zero_alignment_padding_bytes': padding_size,
            'zero_alignment_padding_sha256': _hash(padding),
            'cryptographic_signature_verified': False}


def inspect_embedded_zip(data):
    """Validate one complete, bounded, conventional ZIP or APK container."""
    _bounded(data, MAX_ZIP_BYTES, 22)
    if not data.startswith(b'PK\x03\x04'):
        _fail('Embedded ZIP must start with its first local header')
    eocd = data.rfind(b'PK\x05\x06', max(0, len(data) - 65557))
    if eocd < 0 or eocd + 22 > len(data):
        _fail('ZIP EOCD missing/truncated')
    end = struct.unpack_from('<I4H2IH', data, eocd)
    _, disk, cd_disk, disk_count, count, cd_size, cd_offset, comment_size = end
    if (disk or cd_disk or disk_count != count or not 1 <= count <= MAX_ZIP_MEMBERS
            or cd_offset + cd_size != eocd or eocd + 22 + comment_size != len(data)):
        _fail('ZIP EOCD/count/disk/extent mismatch')
    cursor, total, aliases, members = cd_offset, 0, {}, []
    for _ in range(count):
        raw = _span(data, cursor, 46)
        values = struct.unpack('<I6H3I5H2I', raw)
        (magic, made, needed, flags, method, _, _, crc, compressed, expanded,
         name_len, extra_len, member_comment, member_disk, _, attrs, local) = values
        if magic != 0x02014b50 or needed > 20 or member_disk:
            _fail('ZIP central-header format unsupported')
        if flags & ~0x080e or method not in (0, 8):
            _fail('ZIP encryption/unsupported flags or compression')
        if compressed > MAX_ZIP_BYTES or expanded > MAX_ZIP_EXPANDED:
            _fail('ZIP member size bound')
        total += expanded
        if total > MAX_ZIP_EXPANDED or expanded > max(1, compressed) * 1024:
            _fail('ZIP decompression bomb bound')
        variable = _span(data, cursor + 46, name_len + extra_len + member_comment)
        name, alias = _zip_name(variable[:name_len], flags)
        if alias in aliases:
            _fail('ZIP duplicate/normalization alias')
        aliases[alias] = name.endswith('/')
        _zip_extra(variable[name_len:name_len + extra_len])
        mode = (attrs >> 16) & 0xffff
        kind = stat.S_IFMT(mode)
        if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or stat.S_ISLNK(mode):
            _fail('ZIP symlink or special member')
        if name.endswith('/') and (expanded or crc or kind == stat.S_IFREG):
            _fail('ZIP directory carries content or file type')
        if not name.endswith('/') and (kind == stat.S_IFDIR or attrs & 0x10):
            _fail('ZIP directory metadata/name mismatch')
        members.append({'name': name, 'raw_name': variable[:name_len], 'flags': flags,
                        'compression': method, 'crc32': crc, 'compressed_bytes': compressed,
                        'bytes': expanded, 'local_header_offset': local})
        cursor += 46 + len(variable)
    if cursor != cd_offset + cd_size:
        _fail('ZIP central-directory extent or count mismatch')
    for name in aliases:
        segments = name.split('/')
        for length in range(1, len(segments)):
            if aliases.get('/'.join(segments[:length])) is False:
                _fail('ZIP file is also a parent directory')
    previous = 0
    for member in sorted(members, key=lambda item: item['local_header_offset']):
        local = member['local_header_offset']
        if local != previous or local + 30 > cd_offset:
            _fail('ZIP local-header gap/overlap/alias')
        header = struct.unpack('<I5H3I2H', _span(data, local, 30))
        magic, needed, flags, method, _, _, crc, compressed, expanded, name_len, extra_len = header
        if (magic != 0x04034b50 or needed > 20 or flags != member['flags']
                or method != member['compression']):
            _fail('ZIP local/central header mismatch')
        raw_name = _span(data, local + 30, name_len)
        if raw_name != member.pop('raw_name'):
            _fail('ZIP local/central filename mismatch')
        _zip_extra(_span(data, local + 30 + name_len, extra_len))
        expected = (member['crc32'], member['compressed_bytes'], member['bytes'])
        if flags & 8:
            if any(actual not in (0, wanted) for actual, wanted in zip((crc, compressed, expanded), expected)):
                _fail('ZIP local descriptor-backed size mismatch')
        elif (crc, compressed, expanded) != expected:
            _fail('ZIP local/central size or CRC mismatch')
        payload_offset = local + 30 + name_len + extra_len
        encoded = _span(data, payload_offset, member['compressed_bytes'])
        previous = payload_offset + len(encoded)
        if previous > cd_offset:
            _fail('ZIP member overlaps central directory')
        if flags & 8:
            signed = data[previous:previous + 4] == b'PK\x07\x08'
            if signed:
                previous += 4
            if struct.unpack('<III', _span(data, previous, 12)) != expected:
                _fail('ZIP data descriptor mismatch')
            previous += 12
        if method == 0:
            decoded = encoded
        else:
            try:
                decoder = zlib.decompressobj(-15)
                decoded = decoder.decompress(encoded, member['bytes'] + 1)
            except zlib.error as error:
                raise ValueError('ZIP invalid deflate stream') from error
            if not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
                _fail('ZIP incomplete/concatenated/overlong deflate stream')
        if len(decoded) != member['bytes'] or (zlib.crc32(decoded) & 0xffffffff) != member['crc32']:
            _fail('ZIP member content size/CRC mismatch')
        member.update(crc32=f'{member["crc32"]:08x}', sha256=_hash(decoded),
                      compressed_sha256=_hash(encoded), payload_offset=payload_offset)
    signing = None
    if previous != cd_offset:
        if previous > cd_offset:
            _fail('ZIP members overlap central directory')
        signing = _apk_signing_gap(data[previous:cd_offset], previous)
    return _result('embedded_zip_v1', data, member_count=count, expanded_bytes=total,
                   central_directory_offset=cd_offset, central_directory_bytes=cd_size,
                   eocd_offset=eocd, comment_sha256=_hash(data[eocd + 22:]),
                   members=sorted(members, key=lambda item: item['name']),
                   apk_signing_block=signing, path_case_sensitive=True,
                   inner_code_executed=False)


def inspect_version_marker(data):
    _bounded(data, 16, 16)
    if not re.fullmatch(rb'[0-9]+(?:\.[0-9]+){2,4} *', data):
        _fail('Version marker must be exactly 16 ASCII bytes with space padding')
    return _result('ascii_version_marker_v1', data, version=data.decode('ascii').rstrip(' '))


def _zstd_frame(data):
    _bounded(data, MAX_CSOP_BYTES, 8)
    if data[:4] != b'\x28\xb5\x2f\xfd':
        _fail('CSOP requires one standard Zstandard frame')
    descriptor = data[4]
    if descriptor & 0x18 or descriptor & 3:
        _fail('Zstandard reserved/unused flags or dictionary are unsupported')
    single = bool(descriptor & 0x20)
    checksum = bool(descriptor & 4)
    size_flag, cursor, window = descriptor >> 6, 5, None
    if not single:
        wd = _span(data, cursor, 1)[0]
        cursor += 1
        exponent, mantissa = wd >> 3, wd & 7
        window_base = 1 << (10 + exponent)
        window = window_base + (window_base >> 3) * mantissa
    field_size = (1 if single else 0, 2, 4, 8)[size_flag]
    if not field_size:
        _fail('CSOP requires a declared Zstandard content size')
    content_size = int.from_bytes(_span(data, cursor, field_size), 'little')
    cursor += field_size
    if field_size == 2:
        content_size += 256
    if single:
        window = content_size
    if not 1 <= content_size <= MAX_ZSTD_CONTENT_BYTES or not 1 <= window <= MAX_ZSTD_CONTENT_BYTES:
        _fail('Zstandard content/window memory bound')
    header_bytes, blocks, known_output, output_bound = cursor, [], 0, 0
    block_max = min(window, 128 * 1024)
    while True:
        if len(blocks) >= MAX_ZSTD_BLOCKS:
            _fail('Zstandard block count bound')
        header_offset = cursor
        header = int.from_bytes(_span(data, cursor, 3), 'little')
        cursor += 3
        last, kind, size = bool(header & 1), (header >> 1) & 3, header >> 3
        if kind == 3 or size > block_max or (kind == 2 and size == 0):
            _fail('Zstandard reserved block or block-size bound')
        encoded_size = 1 if kind == 1 else size
        payload = _span(data, cursor, encoded_size)
        blocks.append({'header_offset': header_offset, 'payload_offset': cursor,
                       'block_type': ('raw', 'rle', 'compressed')[kind],
                       'size_field': size, 'encoded_bytes': encoded_size,
                       'last': last, 'sha256': _hash(payload)})
        cursor += encoded_size
        known_output += size if kind in (0, 1) else 0
        output_bound += size if kind in (0, 1) else block_max
        if last:
            break
    checksum_bytes = _span(data, cursor, 4) if checksum else b''
    cursor += len(checksum_bytes)
    if cursor != len(data):
        _fail('Zstandard trailing/concatenated frames are unsupported')
    if known_output > content_size or output_bound < content_size:
        _fail('Zstandard content size contradicts block output bounds')
    return {'frame_sha256': _hash(data), 'frame_bytes': len(data),
            'header_bytes': header_bytes, 'single_segment': single,
            'declared_content_bytes': content_size, 'window_bytes': window,
            'block_count': len(blocks), 'blocks': blocks,
            'checksum_present': checksum, 'checksum_hex': checksum_bytes.hex(),
            'checksum_verified': False, 'decompression_performed': False,
            'decoded_content_verified': False}


def inspect_csop(data):
    _bounded(data, MAX_CSOP_BYTES, 24)
    if data[:4] != b'CSOP' or data[4:12] != bytes(8):
        _fail('Unknown CSOP header variant')
    return _result('wechat_csop_zstd_v1', data, header_bytes=16,
                   observed_token_hex=data[12:16].hex(), zstd=_zstd_frame(data[16:]))


def inspect_csos(data, expected_abi):
    _bounded(data, 64, 13)
    if expected_abi not in ABIS or data[:4] != b'CSOS':
        _fail('CSOS ABI or magic unsupported')
    size = struct.unpack_from('<I', data, 8)[0]
    if size != len(data) - 12 or data[12:] != expected_abi.encode('ascii'):
        _fail('CSOS declared ABI length or directory ABI mismatch')
    return _result('wechat_csos_stub_v1', data, observed_token_hex=data[4:8].hex(),
                   abi_label=expected_abi, abi_label_bytes=size)


def inspect_cso_meta(data):
    """Check the observed raw offset-table layout, without claiming loader semantics."""
    _bounded(data, MAX_META_BYTES, 26)
    count = struct.unpack_from('<I', data)[0]
    if not 1 <= count <= MAX_META_RECORDS:
        _fail('CSO meta record-count bound')
    table_end = 4 + count * 4
    offsets = struct.unpack('<' + str(count) + 'I', _span(data, 4, count * 4))
    if offsets[0] != table_end + 16 or list(offsets) != sorted(set(offsets)):
        _fail('CSO meta noncanonical offset table')
    records, names = [], set()
    for index, start in enumerate(offsets):
        finish = offsets[index + 1] - 16 if index + 1 < count else len(data)
        if start > finish or finish > len(data):
            _fail('CSO meta overlapping/out-of-bounds string spans')
        raw_u64, raw_u32_8, raw_u32_12 = struct.unpack('<QII', _span(data, start - 16, 16))
        if (not 1 <= raw_u64 <= MAX_ZSTD_CONTENT_BYTES or raw_u32_8 not in (0, 1)
                or raw_u32_12 > 256):
            _fail('CSO meta unknown header variant or bounded field violation')
        raw_strings = _span(data, start, finish - start)
        parts = raw_strings.split(b'\0')
        if parts[-1] or len(parts) != raw_u32_12 + 2:
            _fail('CSO meta exact string-count/terminator mismatch')
        try:
            strings = [part.decode('ascii') for part in parts[:-1]]
        except UnicodeDecodeError as error:
            raise ValueError('CSO meta non-ASCII basename') from error
        if any(len(name) > 256 or not _BASENAME.fullmatch(name) for name in strings):
            _fail('CSO meta invalid library basename')
        if strings[0] in names or len(strings[1:]) != len(set(strings[1:])):
            _fail('CSO meta duplicate record/dependency name')
        names.add(strings[0])
        records.append({'string_offset': start, 'record_end': finish,
                        'raw_u64_at_0': raw_u64, 'raw_u32_at_8': raw_u32_8,
                        'raw_u32_at_12': raw_u32_12, 'strings': strings,
                        'record_sha256': _hash(data[start - 16:finish])})
    return _result('wechat_cso_offset_table_v1', data, record_count=count,
                   offset_table_sha256=_hash(data[:table_end]), offsets=list(offsets),
                   records=records, field_semantics='observed_raw_layout_only',
                   loader_semantics_verified=False)


def inspect_dex035(data):
    """Validate DEX035 identity/header/checksums/map spans, not bytecode semantics."""
    _bounded(data, MAX_DEX_BYTES, 112)
    if data[:8] != b'dex\n035\0':
        _fail('Only the observed DEX035 container version is supported')
    checksum = struct.unpack_from('<I', data, 8)[0]
    if (zlib.adler32(data[12:]) & 0xffffffff) != checksum or hashlib.sha1(data[32:]).digest() != data[12:32]:
        _fail('DEX Adler32/SHA1 mismatch')
    fields = struct.unpack_from('<20I', data, 32)
    file_size, header_size, endian, link_size, link_off, map_off = fields[:6]
    data_size, data_off = fields[-2:]
    if (file_size != len(data) or header_size != 112 or endian != 0x12345678
            or link_size or link_off or data_off < 112 or data_off % 4
            or data_off + data_size != len(data) or map_off < data_off or map_off % 4):
        _fail('DEX header size/endian/link/data/map layout mismatch')
    fixed = {0: 112, 1: 4, 2: 4, 3: 12, 4: 8, 5: 8, 6: 32}
    minimum = {0x1001: 4, 0x1002: 4, 0x1003: 4, 0x2000: 4, 0x2001: 16,
               0x2002: 2, 0x2003: 3, 0x2004: 2, 0x2005: 1, 0x2006: 16}
    counts = {}
    id_end = 112
    for kind in range(1, 7):
        size, offset = fields[6 + (kind - 1) * 2:8 + (kind - 1) * 2]
        if bool(size) != bool(offset) or size > 1000000:
            _fail('DEX identifier-table count/offset mismatch')
        if size:
            finish = offset + size * fixed[kind]
            if offset < id_end or offset % 4 or finish > data_off:
                _fail('DEX overlapping/out-of-range identifier table')
            id_end = finish
        counts[kind] = (size, offset)
    map_count = struct.unpack('<I', _span(data, map_off, 4))[0]
    if not 2 <= map_count <= 64:
        _fail('DEX map count bound')
    _span(data, map_off + 4, map_count * 12)
    maps, seen, previous = [], set(), -1
    for index in range(map_count):
        kind, unused, size, offset = struct.unpack_from('<HHII', data, map_off + 4 + index * 12)
        if (unused or kind in seen or size == 0 or size > 1000000 or offset <= previous
                or offset >= len(data) or kind not in set(fixed) | set(minimum) | {0x1000}):
            _fail('DEX unknown/duplicate/unordered/out-of-range map item')
        if kind in fixed and (offset % 4 or (kind == 0 and (size, offset) != (1, 0))):
            _fail('DEX fixed-map alignment/header mismatch')
        if kind >= 0x1000 and offset < data_off:
            _fail('DEX data map lies outside data section')
        if kind in (0x1000, 0x1001, 0x1002, 0x1003, 0x2001, 0x2006) and offset % 4:
            _fail('DEX data-map alignment mismatch')
        if kind == 0x1000 and (size, offset) != (1, map_off):
            _fail('DEX map self-reference mismatch')
        if kind in counts and (size, offset) != counts[kind]:
            _fail('DEX header/map identifier disagreement')
        seen.add(kind)
        previous = offset
        maps.append({'type': f'{kind:04x}', 'count': size, 'offset': offset})
    if not {0, 0x1000}.issubset(seen) or any(size and kind not in seen for kind, (size, _) in counts.items()):
        _fail('DEX map omits a required header section')
    for index, item in enumerate(maps):
        kind, offset, count = int(item['type'], 16), item['offset'], item['count']
        finish = maps[index + 1]['offset'] if index + 1 < len(maps) else len(data)
        required = (4 + 12 * map_count) if kind == 0x1000 else count * (fixed.get(kind) or minimum[kind])
        if offset + required > finish:
            _fail('DEX map section overlaps next section or EOF')
        item.update(span_end=finish, span_sha256=_hash(data[offset:finish]))
    return _result('dex035_layout_v1', data, dex_version='035', header_bytes=112,
                   adler32=f'{checksum:08x}', dex_sha1=data[12:32].hex(), checksums_verified=True,
                   data_offset=data_off, data_bytes=data_size, map_offset=map_off,
                   map_items=maps, bytecode_semantics_verified=False, inner_code_executed=False)


def inspect_native_publisher_payload(data, entry_name):
    if not isinstance(entry_name, str):
        _fail('Publisher payload entry name must be a string')
    parts = entry_name.split('/')
    if len(parts) != 3 or parts[0] != 'lib' or parts[1] not in ABIS or not _BASENAME.fullmatch(parts[2]):
        _fail('Publisher payload must have one canonical lib/ABI/basename.so path')
    _bounded(data, MAX_CSOP_BYTES)
    abi, name = parts[1:]
    if data.startswith(b'PK\x03\x04'):
        result = inspect_embedded_zip(data)
    elif data.startswith(b'CSOP') and name.endswith('.$cso.so'):
        result = inspect_csop(data)
    elif data.startswith(b'CSOS') and not name.endswith('.$cso.so'):
        result = inspect_csos(data, abi)
    elif name == 'libcso.meta.so':
        result = inspect_cso_meta(data)
    elif name == 'libsgmainso.version.so':
        result = inspect_version_marker(data)
    elif data.startswith(b'dex\n'):
        result = inspect_dex035(data)
    else:
        _fail('Unknown native-directory publisher payload format')
    return {'entry_name': entry_name, 'directory_abi_label': abi, **result}
