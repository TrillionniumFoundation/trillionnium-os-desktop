"""Bound two ELF dynamic views as source metadata; never load or execute them.

The narrow model admits a declared dependency table and a different PT_LOAD
view.  Only their SONAME and ordered NEEDED identities must agree.  It does not
claim that other tags, a particular Android linker, or native execution agree.
"""

import hashlib
import json
import struct


_LIMIT = 16 * 1024 * 1024
_LAYOUT_LIMIT = 64 * 1024
_POINTER_MINIMUM = {
    3: 1, 4: 8, 5: 1, 6: 1, 7: 1, 12: 1, 13: 1, 17: 1, 23: 1,
    25: 1, 26: 1, 32: 1, 36: 1, 0x6ffffef5: 16,
    0x6ffffff0: 2, 0x6ffffffc: 20, 0x6ffffffe: 16,
}
_POINTER_SIZE_TAG = {5: 10, 6: 11, 7: 8, 17: 18, 23: 2,
                     25: 27, 26: 28, 32: 33, 36: 35}
_VALUE_TAGS = {0, 1, 2, 8, 9, 10, 11, 14, 18, 19, 20, 27, 28, 30,
               33, 35, 37, 0x6ffffff9, 0x6ffffffa, 0x6ffffffb,
               0x6ffffffd, 0x6fffffff}


def parse_dual_dynamic_shared_library(body: bytes) -> dict:
    """Return deterministic, fully pinned observations or raise ValueError.

    All reads are bounded by the supplied immutable bytes.  The parser accepts
    no paths and performs no IO.  Unknown dynamic tags are outside this model;
    pointer observations cover the bounded ranges this model actually reads,
    not the correctness of relocations, symbols, or dependencies.
    """
    if (type(body) is not bytes or not 52 <= len(body) <= _LIMIT
            or body[:4] != b'\x7fELF' or body[4] not in (1, 2)
            or body[5:7] != b'\x01\x01'):
        raise ValueError('Invalid dual-dynamic ELF encoding or size')
    elf_class = body[4]
    ehsize, phsize, shsize, dsize, word = ((64, 56, 64, 16, 8)
                                        if elf_class == 2 else (52, 32, 40, 8, 4))
    address_limit = 1 << (word * 8)

    def extent(offset, size):
        if offset < 0 or size < 0 or offset + size > len(body):
            raise ValueError('Dual-dynamic file range is out of bounds')
        return body[offset:offset + size]

    def pin(offset, size):
        return {'offset': offset, 'bytes': size,
                'sha256': hashlib.sha256(extent(offset, size)).hexdigest()}

    def overlaps(left, right):
        return left[0] < right[0] + right[1] and right[0] < left[0] + left[1]

    extent(0, ehsize)
    h = struct.unpack_from('<HHIQQQIHHHHHH' if elf_class == 2
                           else '<HHIIIIIHHHHHH', body, 16)
    kind, machine, version, entry, phoff, shoff, flags, hs, ps, pn, ss, sn, si = h
    if (kind != 3 or version != 1 or hs != ehsize or ps != phsize or ss != shsize
            or (elf_class, machine) not in {(1, 3), (1, 40), (2, 62), (2, 183), (2, 243)}
            or not 1 <= pn <= 128 or not 1 <= sn <= 4096 or not 0 < si < sn
            or min(phoff, shoff) < ehsize or phoff % word or shoff % word):
        raise ValueError('Invalid dual-dynamic ELF header or table shape')
    phpin, shpin = pin(phoff, pn * phsize), pin(shoff, sn * shsize)
    programs = []
    for i in range(pn):
        row = struct.unpack_from('<IIQQQQQQ' if elf_class == 2 else '<IIIIIIII',
                                 body, phoff + i * phsize)
        if elf_class == 2:
            pt, pf, off, va, pa, fs, ms, align = row
        else:
            pt, off, va, pa, fs, ms, pf, align = row
        extent(off, fs)
        if (va + ms > address_limit or pa + ms > address_limit
                or (align > 1 and (align & (align - 1))) or pt == 3
                or (pt == 1 and (fs > ms or (align > 1 and off % align != va % align)))):
            raise ValueError('Invalid dual-dynamic segment or PT_INTERP')
        programs.append({'index': i, 'type': pt, 'flags': pf, 'offset': off,
                         'virtual_address': va, 'physical_address': pa,
                         'file_bytes': fs, 'memory_bytes': ms, 'alignment': align})
    loads = [p for p in programs if p['type'] == 1]
    if not loads:
        raise ValueError('Dual-dynamic ELF needs file-backed loads')
    for i, left in enumerate(loads):
        for right in loads[i + 1:]:
            if (left['memory_bytes'] and right['memory_bytes'] and overlaps(
                    (left['virtual_address'], left['memory_bytes']),
                    (right['virtual_address'], right['memory_bytes']))):
                raise ValueError('Ambiguous overlapping dual-dynamic load ranges')

    def mapped(address, size):
        matches = [p for p in loads if size > 0 and address + size <= address_limit
                   and p['virtual_address'] <= address
                   and address + size <= p['virtual_address'] + p['file_bytes']]
        if len(matches) != 1:
            raise ValueError('Dual-dynamic pointer lacks one file-backed load')
        p = matches[0]
        return p['offset'] + address - p['virtual_address'], p['index']

    if entry:
        _, entry_load = mapped(entry, 1)
        if not programs[entry_load]['flags'] & 1:
            raise ValueError('Dual-dynamic entry is not in an executable load')

    sections = []
    for i in range(sn):
        row = struct.unpack_from('<IIQQQQIIQQ' if elf_class == 2 else '<IIIIIIIIII',
                                 body, shoff + i * shsize)
        name, st, sf, sa, so, sz, link, info, align, entsize = row
        if st != 8:
            extent(so, sz)
        if (so > len(body) or sa + sz > address_limit or (align > 1 and align & (align - 1))
                or (link and link >= sn)):
            raise ValueError('Invalid dual-dynamic section bounds')
        sections.append({'index': i, 'name_index': name, 'type': st, 'flags': sf,
                         'address': sa, 'offset': so, 'bytes': sz, 'link': link,
                         'info': info, 'alignment': align, 'entry_bytes': entsize})
    dynamic = [p for p in programs if p['type'] == 2]
    dynamic_sections = [s for s in sections if s['type'] == 6]
    if len(dynamic) != 1 or len(dynamic_sections) != 1:
        raise ValueError('Dual-dynamic ELF needs one segment and one section')
    dp, ds = dynamic[0], dynamic_sections[0]
    size, declared = dp['file_bytes'], dp['offset']
    if (not 0 < size <= 4096 * dsize or size % dsize or dp['memory_bytes'] != size
            or ds['offset'] != declared or ds['bytes'] != size or ds['entry_bytes'] != dsize):
        raise ValueError('Dual-dynamic section and declared full range differ')
    runtime, dynamic_load = mapped(dp['virtual_address'], size)
    if runtime == declared:
        raise ValueError('Dual-dynamic model requires distinct file views')
    strings_section = sections[ds['link']]
    if strings_section['type'] != 3 or not 0 < strings_section['bytes'] <= 1024 * 1024:
        raise ValueError('Dual-dynamic sh_link must identify a bounded STRTAB')

    def table(offset, declared_view):
        entries, values = [], {}
        for position in range(offset, offset + size, dsize):
            tag, value = struct.unpack_from('<qQ' if elf_class == 2 else '<iI', body, position)
            allowed = {0, 1, 14} if declared_view else _VALUE_TAGS | set(_POINTER_MINIMUM)
            if tag not in allowed or (tag in values and tag != 1):
                raise ValueError('Unsupported or duplicate dual-dynamic tag')
            entries.append([tag, value])
            values.setdefault(tag, []).append(value)
            if tag == 0:
                if value != 0:
                    raise ValueError('Dual-dynamic DT_NULL must have a zero value')
                break
        else:
            raise ValueError('Dual-dynamic table is not terminated')
        if 14 not in values or len(values.get(1, [])) > 64:
            raise ValueError('Dual-dynamic table needs SONAME and bounded NEEDED')
        return {'full': pin(offset, size), 'consumed': pin(offset, len(entries) * dsize),
                'entries': entries}, values

    declared_table, dt = table(declared, True)
    mapped_table, mt = table(runtime, False)
    if not {5, 10, 14} <= set(mt) or mt.get(0x6ffffffb, [0])[0] & 0x08000000:
        raise ValueError('Dual-dynamic mapped table needs STRTAB and no DF_1_PIE')
    string_size = mt[10][0]
    if not 0 < string_size <= 1024 * 1024:
        raise ValueError('Dual-dynamic STRSZ is out of bounds')
    string_offset, string_load = mapped(mt[5][0], string_size)
    if (strings_section['offset'] != string_offset or strings_section['bytes'] != string_size):
        raise ValueError('Dual-dynamic string views do not identify the same bytes')
    strings = extent(string_offset, string_size)

    def string(offset):
        if offset >= len(strings):
            raise ValueError('Dual-dynamic string offset is out of bounds')
        end = strings.find(b'\0', offset, min(len(strings), offset + 257))
        if end <= offset:
            raise ValueError('Dual-dynamic string must be nonempty, bounded and terminated')
        return strings[offset:end].decode('utf-8', 'strict')

    soname = string(dt[14][0])
    needed = [string(n) for n in dt.get(1, [])]
    if soname != string(mt[14][0]) or needed != [string(n) for n in mt.get(1, [])]:
        raise ValueError('Dual-dynamic SONAME or ordered NEEDED differ')
    pointers = []
    for tag in sorted(set(mt) & set(_POINTER_MINIMUM)):
        length = _POINTER_MINIMUM[tag]
        if tag in _POINTER_SIZE_TAG:
            size_tag = _POINTER_SIZE_TAG[tag]
            if size_tag not in mt:
                raise ValueError('Dual-dynamic pointer has no bounded size tag')
            length = mt[size_tag][0]
        if tag == 3:
            length = word
        offset, load = mapped(mt[tag][0], length)
        if tag in {12, 13} and not programs[load]['flags'] & 1:
            raise ValueError('Dual-dynamic init/fini pointer is not executable file-backed data')
        pointers.append({'tag': tag, 'address': mt[tag][0], 'load_index': load,
                         'checked_file_range': pin(offset, length)})

    sht = (shoff, sn * shsize)
    def table_ranges(table):
        return [(table[k]['offset'], table[k]['bytes']) for k in ('full', 'consumed')]
    df, dc = table_ranges(declared_table)
    mf, mc = table_ranges(mapped_table)
    metadata_ranges = [(0, ehsize), (phoff, pn * phsize), sht,
                       (string_offset, string_size)]
    if (overlaps(dc, mc) or any(overlaps(consumed, metadata)
                               for consumed in (dc, mc) for metadata in metadata_ranges)):
        raise ValueError('Consumed dual-dynamic entries overlap metadata or each other')
    layout = {
        'schema': 'dual-dynamic-shared-library-layout-v1',
        'identity_comparison': 'soname-and-ordered-needed-only',
        'shared_identity': {'soname': soname, 'ordered_needed': needed},
        'elf_header': {**pin(0, ehsize), 'class': elf_class, 'machine': machine,
                       'type': kind, 'entry_point': entry, 'flags': flags},
        'program_headers': {**phpin, 'count': pn, 'entries': programs},
        'section_headers': {**shpin, 'count': sn, 'entries': sections},
        'section_name_index': si,
        'section_name_index_type': sections[si]['type'],
        'dynamic_segment_index': dp['index'],
        'dynamic_section_index': ds['index'],
        'dynamic_load_index': dynamic_load,
        'declared_dynamic': declared_table,
        'mapped_dynamic': mapped_table,
        'string_table': {**pin(string_offset, string_size), 'section_index': ds['link'],
                         'virtual_address': mt[5][0], 'load_index': string_load},
        'dynamic_pointer_observations': pointers,
        'tag_differences': [{'tag': tag, 'declared': dt.get(tag), 'mapped': mt.get(tag)}
                            for tag in sorted(set(dt) | set(mt)) if dt.get(tag) != mt.get(tag)],
        'range_overlaps': {'declared_full_section_headers': overlaps(df, sht),
                           'declared_consumed_section_headers': overlaps(dc, sht),
                           'mapped_full_section_headers': overlaps(mf, sht),
                           'mapped_consumed_section_headers': overlaps(mc, sht),
                           'declared_mapped_full': overlaps(df, mf),
                           'declared_mapped_consumed': overlaps(dc, mc),
                           'declared_consumed_mapped_full': overlaps(dc, mf),
                           'mapped_consumed_declared_full': overlaps(mc, df)},
        'load_congruence': [{'index': p['index'],
                             'page_4096': p['offset'] % 4096 == p['virtual_address'] % 4096,
                             'page_16384': p['offset'] % 16384 == p['virtual_address'] % 16384}
                            for p in loads],
        'noncanonical_observations': {
            'section_name_index_is_not_strtab': sections[si]['type'] != 3,
            'dynamic_section_address_differs_from_segment': ds['address'] != dp['virtual_address'],
            'declared_full_overlaps_section_headers': overlaps(df, sht),
        },
    }
    canonical = json.dumps(layout, sort_keys=True, separators=(',', ':'),
                           ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(canonical) > _LAYOUT_LIMIT:
        raise ValueError('Dual-dynamic canonical layout exceeds its output bound')
    return {'elf_class': elf_class, 'elf_machine': machine, 'elf_type': kind,
            'soname': soname, 'entry_point': entry, 'has_interpreter': False,
            'dynamic_needed': needed, 'layout': layout,
            'layout_sha256': hashlib.sha256(canonical).hexdigest()}
