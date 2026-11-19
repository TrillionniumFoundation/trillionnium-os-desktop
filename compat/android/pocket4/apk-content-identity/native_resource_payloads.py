"""Pure bounded metadata for two literal resource kinds; no runtime permission.

Neither function opens a file, extracts an archive, loads a library, or executes
anything. The existing shared-library parser remains a separate strict policy.
The layout digest covers only ``layout`` using UTF-8 JSON, sorted keys, compact
separators, ensure_ascii=False, allow_nan=False, and no trailing newline.
"""
import hashlib
import json
import struct
import zlib

_ARCHIVE_LIMIT = 64 * 1024 * 1024
_NEXT_HEADER_LIMIT = 64 * 1024
_ELF_LIMIT = 16 * 1024 * 1024
_LINKER = b'/system/bin/linker\0'


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _result(kind, body, layout, **metadata):
    encoded = json.dumps(layout, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False, allow_nan=False).encode('utf-8')
    return {'kind': kind, 'bytes': len(body), 'sha256': _sha(body),
            'layout': layout, 'layout_sha256': _sha(encoded), **metadata,
            'source_only': True, 'candidate_admission_issued': False,
            'loaded': False, 'installed': False,
            'native_compatibility_qualified': False,
            'dispatch_runtime_observed': False, 'native_runtime_qualified': False,
            'runtime_qualified': False, 'production_ready': False}


def inspect_embedded_7z(body):
    """Recognize the observed 7z 0.3 container header without decoding streams."""
    _require(type(body) is bytes and 33 <= len(body) <= _ARCHIVE_LIMIT,
             'Expected immutable bounded 7z bytes')
    _require(body[:8] == b'7z\xbc\xaf\x27\x1c\x00\x03', 'Expected exact 7z 0.3 signature')
    start_crc = struct.unpack_from('<I', body, 8)[0]
    _require(zlib.crc32(body[12:32]) & 0xffffffff == start_crc, 'Invalid 7z start-header CRC')
    offset, size, next_crc = struct.unpack_from('<QQI', body, 12)
    _require(0 < size <= _NEXT_HEADER_LIMIT and offset <= len(body) - 32,
             'Invalid bounded 7z next-header range')
    start = 32 + offset
    _require(size == len(body) - start, '7z next header must end exactly at payload EOF')
    next_header = memoryview(body)[start:]
    _require(zlib.crc32(next_header) & 0xffffffff == next_crc, 'Invalid 7z next-header CRC')
    layout = {
        'schema': 'bounded-native-resource-layout-v1', 'kind': 'embedded_7z_archive',
        'payload': {'bytes': len(body), 'sha256': _sha(body)},
        'archive_version': [0, 3], 'signature_hex': body[:6].hex(),
        'signature_header': {'offset': 0, 'bytes': 32, 'sha256': _sha(body[:32])},
        'start_header': {'offset': 12, 'bytes': 20, 'sha256': _sha(body[12:32]),
                         'crc32': start_crc},
        'packed_range': {'offset': 32, 'bytes': offset,
                         'sha256': _sha(memoryview(body)[32:start])},
        'next_header': {'relative_offset': offset, 'offset': start, 'bytes': size,
                        'end': len(body), 'crc32': next_crc, 'sha256': _sha(next_header)},
    }
    return _result('embedded_7z_archive', body, layout, native_elf=False,
                   archive_contents_decoded=False, archive_contents_verified=False,
                   counted_as_directory_native_library=False)


def inspect_interpreter_tagged_et_dyn(body):
    """Observe ARM32 ET_DYN with one literal Android linker and a zero entry.

All remaining bounds and dynamic-identity conditions of the original shared
parser are retained. PT_INTERP is explicitly represented by this different
resource kind, without changing the original parser's rejection policy.
"""
    _require(type(body) is bytes and 52 <= len(body) <= _ELF_LIMIT and
             body[:7] == b'\x7fELF\x01\x01\x01', 'Expected bounded ELF32 little-endian bytes')
    header = struct.unpack_from('<HHIIIIIHHHHHH', body, 16)
    elf_type, machine, version, entry, phoff, _, _, ehsize, phsize, phnum, _, _, _ = header
    _require(elf_type == 3 and machine == 40 and version == 1 and entry == 0 and
             ehsize == 52 and phsize == 32 and 1 <= phnum <= 128 and
             phoff >= 52 and phnum * phsize <= len(body) - phoff,
             'Expected ARM32 ET_DYN, zero entry and bounded program table')
    programs = []
    interpreters = []
    for index in range(phnum):
        kind, offset, address, physical, file_size, memory_size, flags, alignment = struct.unpack_from(
            '<8I', body, phoff + index * phsize)
        _require(offset <= len(body) and file_size <= len(body) - offset and
                 (kind != 1 or (file_size <= memory_size and address + memory_size <= 2**32)),
                 'ELF segment exceeds its file or ARM32 address space')
        row = {'index': index, 'type': kind, 'flags': flags, 'offset': offset,
               'virtual_address': address, 'physical_address': physical,
               'file_bytes': file_size, 'memory_bytes': memory_size, 'alignment': alignment}
        programs.append(row)
        if kind == 3:
            _require(file_size == len(_LINKER) and body[offset:offset + file_size] == _LINKER,
                     'Expected one literal absolute /system/bin/linker interpreter')
            interpreters.append(row)
    _require(len(interpreters) == 1, 'Expected exactly one PT_INTERP')
    interpreter = interpreters[0]
    loads = [row for row in programs if row['type'] == 1]
    _require(bool(loads), 'ELF needs file-backed loads')
    _require(all(interpreter['index'] < row['index'] for row in loads),
             'PT_INTERP must precede loadable segments')

    mappings = []

    def file_offset(address, size, label):
        matches = [row['offset'] + address - row['virtual_address'] for row in loads
                   if row['virtual_address'] <= address and
                   address + size <= row['virtual_address'] + row['file_bytes']]
        _require(len(matches) == 1, 'Dynamic pointer lacks one file-backed load: ' + label)
        mappings.append({'label': label, 'virtual_address': address, 'bytes': size,
                         'file_offset': matches[0]})
        return matches[0]

    dynamics = [row for row in programs if row['type'] == 2]
    _require(len(dynamics) == 1, 'Expected exactly one PT_DYNAMIC')
    dynamic = dynamics[0]
    _require(0 < dynamic['file_bytes'] <= 4096 * 8 and dynamic['file_bytes'] % 8 == 0,
             'Invalid bounded dynamic-table size')
    _require(file_offset(dynamic['virtual_address'], dynamic['file_bytes'], 'PT_DYNAMIC') ==
             dynamic['offset'], 'Dynamic file and mapped offsets differ')
    tags, needed, entries = {}, [], []
    start, size = dynamic['offset'], dynamic['file_bytes']
    null_end = None
    for position in range(start, start + size, 8):
        tag, value = struct.unpack_from('<iI', body, position)
        entries.append({'offset': position, 'tag': tag, 'value': value})
        if tag == 0:
            null_end = position + 8
            break
        if tag == 1:
            needed.append(value)
        elif tag in (5, 10, 14, 30, 0x6ffffffb):
            _require(tag not in tags, 'Duplicate dynamic identity tag')
            tags[tag] = value
    _require(null_end is not None and {5, 10, 14} <= set(tags) and
             0 < tags[10] <= 1024 * 1024 and len(needed) <= 64 and
             tags.get(0x6ffffffb, 0) & 0x08000000 == 0,
             'Expected bounded DT_NULL, strings, SONAME, NEEDED and no DF_1_PIE')
    string_start = file_offset(tags[5], tags[10], 'DT_STRTAB')
    strings = body[string_start:string_start + tags[10]]

    def dynamic_string(offset):
        _require(offset < len(strings), 'Dynamic string offset is out of bounds')
        end = strings.find(b'\0', offset)
        _require(end >= offset and end - offset <= 256, 'Dynamic string is not bounded and terminated')
        return {'offset': offset, 'bytes_without_null': end - offset,
                'value': strings[offset:end].decode('utf-8', 'strict')}

    soname = dynamic_string(tags[14])
    dependencies = [dynamic_string(offset) for offset in needed]
    dynamic_bytes = memoryview(body)[start:start + size]
    tail = memoryview(body)[null_end:start + size]
    layout = {
        'schema': 'bounded-native-resource-layout-v1', 'kind': 'interpreter_tagged_et_dyn',
        'payload': {'bytes': len(body), 'sha256': _sha(body)},
        'elf_header': {'offset': 0, 'bytes': 52, 'sha256': _sha(body[:52]),
                       'elf_class': 1, 'elf_machine': machine, 'elf_type': elf_type,
                       'version': version, 'entry_point': entry},
        'program_table': {'offset': phoff, 'entry_bytes': phsize, 'count': phnum,
                          'bytes': phnum * phsize,
                          'sha256': _sha(memoryview(body)[phoff:phoff + phnum * phsize]),
                          'entries': programs},
        'interpreter': {'program_index': interpreter['index'], 'offset': interpreter['offset'],
                        'bytes': len(_LINKER), 'sha256': _sha(_LINKER),
                        'literal_path': '/system/bin/linker'},
        'dynamic_table': {'offset': start, 'virtual_address': dynamic['virtual_address'],
                          'bytes': size, 'entry_bytes': 8, 'sha256': _sha(dynamic_bytes),
                          'entries_through_DT_NULL': entries,
                          'tail_after_DT_NULL': {'bytes': len(tail), 'sha256': _sha(tail)},
                          'identity_tags': {str(key): value for key, value in sorted(tags.items())}},
        'string_table': {'offset': string_start, 'virtual_address': tags[5],
                         'bytes': len(strings), 'sha256': _sha(strings),
                         'soname': soname, 'needed': dependencies},
        'pointer_mappings': mappings, 'no_DF_1_PIE': True,
    }
    return _result('interpreter_tagged_et_dyn', body, layout, native_elf=True,
                   counted_as_directory_native_library=False,
                   elf_class=1, elf_machine=machine, elf_type=elf_type,
                   soname=soname['value'], entry_point=entry, has_interpreter=True,
                   interpreter='/system/bin/linker',
                   dynamic_needed=[item['value'] for item in dependencies],
                   standalone_executable_role_established=False)
