#!/usr/bin/env python3
"""One exact retired Owner19 preload ELF read: no process, namespace, mount, or write."""
import errno
import hashlib
import json
import os
import re
import stat
import struct
import sys
import time
import traceback

STATE_NAME = 'p4-owner19-normal-20261105-01-state'
NONCE = '08eae45fbb6c6c42c38bd67a6bdcc20b1a6fbe915a3e0fa0ce182a51b58029ed'
UNIT = 'p4-owner19-normal-20261105-01.service'
INVOCATION = '0c03d2ff679f4cfc9e70717280f93075'
ACTOR_PID = 3956131
SPEC_SHA256 = '0e0e3e9b67f4d43a9d66b12ba28e9953941926487e58bd4010f678f36d04a320'
STATE_ID = {'device': 66306, 'inode': 45663385}
IMAGE_ID = {'device': 66306, 'inode': 39237163}
IMAGE_BYTES = 742322176
IMAGE_PACKAGE = 'p4-media-composer-diagnostic-20261102-chat2-r5'
IMAGE_SHA256 = '358a7f008bbfbcd09fb9655d4ed1ff5f07071f89349735aabf7dd381d738b2cf'
RECORDS = {
    'prepared.json': (55273, 'e6b02798bb03598310905852664eec5cbe2329b990571b0d02e71f43d15aa163'),
    'runtime-result.json': (708698, '6e489440223b2515301d56125a19c9357a4ae211ea960b4a41bf96d0ffe9fce5'),
}



PRELOAD_RELATIVE = 'payload/29/libdroidloom_selinux_compat.so'
PRELOAD_PATH = '/opt/' + IMAGE_PACKAGE + '/' + PRELOAD_RELATIVE
FIXED_BASE_FILES = {PRELOAD_RELATIVE: {
    'identity': {'device': 66306, 'inode': 39736818},
    'bytes': 35336, 'mode': 0o555,
    'sha256': 'b4da6c85703e5f0dac88c039438d8836a4123c97655d14130e68828295d3fb50'}}
PROPERTY_SYMBOLS = ('__system_property_get', '__system_property_find',
    '__system_property_read', '__system_property_read_callback', '__system_property_foreach',
    '__system_property_area_init', '__system_property_set', '__system_property_add',
    '__system_property_update', '__system_property_serial', 'android_get_device_api_level')
RECORD_LIMIT = 1048576
ELF_LIMIT = 65536
OUTPUT_LIMIT = 262144
WIRE_LIMIT = 131072
DEADLINE_SECONDS = 35

def need(value, message):
    if not value:
        raise RuntimeError(message)

def remember(report, phase, error):
    row = {'phase': phase, 'error': repr(error)[:2048],
           'traceback': traceback.format_exc()[-4096:]}
    if report['first_error'] is None:
        report['first_error'] = row
    report['errors'].append(row)

def check_time(deadline):
    need(time.monotonic() <= deadline, 'metadata collection deadline exceeded')

def identity(value):
    return {'device': value.st_dev, 'inode': value.st_ino}

def stamp(value):
    return {'device': value.st_dev, 'inode': value.st_ino,
            'bytes': value.st_size, 'type': stat.S_IFMT(value.st_mode),
            'mode': stat.S_IMODE(value.st_mode), 'uid': value.st_uid,
            'gid': value.st_gid, 'nlink': value.st_nlink,
            'mtime_ns': value.st_mtime_ns, 'ctime_ns': value.st_ctime_ns}

def directory_stamp(value):
    return {key: stamp(value)[key] for key in ('device', 'inode', 'type', 'mode', 'uid', 'gid')}

def recheck(held):
    for row in held:
        need(row['before'] is not None, 'an opened input did not complete qualification')
        describe = directory_stamp if row['directory'] else stamp
        current = describe(os.fstat(row['fd']))
        named = os.stat(row['name'], follow_symlinks=False,
                        **({} if row['parent'] is None else {'dir_fd': row['parent']}))
        need(current == row['before'] == describe(named), 'fixed input changed: ' + row['name'])

def read_exact(fd, size, deadline):
    body = bytearray()
    while len(body) < size:
        check_time(deadline)
        chunk = os.pread(fd, min(65536, size - len(body)), len(body))
        need(bool(chunk), 'short fixed file read')
        body.extend(chunk)
    need(not os.pread(fd, 1, size), 'fixed file grew past expected size')
    return bytes(body)

def read_record(fd, before, name, deadline):
    size, digest = RECORDS[name]
    need(before['bytes'] == size, 'externally pinned record size differs')
    raw = read_exact(fd, size, deadline)
    need(hashlib.sha256(raw).hexdigest() == digest, 'externally pinned record SHA differs')
    return raw, json.loads(raw.decode('utf-8'))

def validate_records(prepared, runtime):
    need(prepared['attempt_nonce'] == runtime['attempt_nonce'] == NONCE,
         'fixed attempt nonce differs')
    need(prepared['success'] is True and prepared['runtime_executed'] is False and
         prepared['errors'] == [] and prepared['state_identity'] == STATE_ID and
         prepared['canonical_spec_sha256'] == SPEC_SHA256, 'prepared contract differs')
    need(prepared['main_before'] == prepared['main_after'] == prepared['main_final'],
         'prepared Main fence differs')
    need(runtime['success'] is False and runtime['production_ready'] is False and
         runtime['installed_owner_qualified'] is False and
         runtime['prepared_sha256'] == RECORDS['prepared.json'][1],
         'original failed runtime binding differs')
    need(runtime['main_before'] == runtime['main_before_gate'] == runtime['main_after'] ==
         prepared['main_before'], 'actual Main before/after fences differ')
    unit = runtime['first_unit']
    need(unit['InvocationID'] == INVOCATION and int(unit['ExecMainPID']) == ACTOR_PID and
         unit['ControlGroup'] == '/system.slice/' + UNIT, 'original unit identity differs')
    cleanup = runtime['exact_unit_cleanup']
    need(cleanup == {'unit': UNIT, 'invocation': INVOCATION, 'original_actor_dead': True,
                     'unit_not_found': True, 'cgroup_absent': True} and
         runtime['cleanup_stop_returncode'] == 0, 'exact original unit cleanup incomplete')
    actor = runtime['actor_result']
    need(actor['attempt_nonce'] == NONCE and actor['actor_pid'] == ACTOR_PID and
         actor['invocation'] == INVOCATION and actor['success'] is False,
         'original actor identity/outcome differs')
    retired = actor['child_retirement']
    need(len(retired) == 4 and {r['role'] for r in retired} == {'daemon', 'presenter', 'sway', 'bus'} and
         all(r['reaped'] is True and r['forced_kill'] is False for r in retired),
         'exact original child retirement incomplete')
    audit = actor['latest_status']['relay_lifecycle']
    need(audit['canonical_spec_sha256'] == SPEC_SHA256 and audit['retirement_failure'] is None and
         audit['cleanup_failure'] is None and audit['recording_error'] is None and
         audit['recording_incomplete'] is False, 'original typed cleanup audit incomplete')
    events = [r['detail']['event'] for r in audit['records']]
    need(events[-6:] == ['broker_retired', 'processes_dead', 'domain_empty', 'retired',
                         'resources_removed', 'claim_released'] and 'active' not in events,
         'original typed terminal sequence differs')
    need(prepared['base_before'] == prepared['base_after'] and len(prepared['base_before']) == 86,
         'actual immutable base inventory differs')
    images = [row for row in prepared['base_before'] if row['relative'] == 'images/system.img']
    need(images == [{'relative': 'images/system.img', 'identity': IMAGE_ID,
                     'bytes': IMAGE_BYTES, 'sha256': IMAGE_SHA256}],
         'fixed base image does not bind exact prepared inventory')
    for relative, expected in FIXED_BASE_FILES.items():
        matching = [row for row in prepared['base_before'] if row['relative'] == relative]
        need(matching == [{'relative': relative, 'identity': expected['identity'],
                           'bytes': expected['bytes'], 'sha256': expected['sha256']}],
             'fixed base ELF/config does not bind exact prepared inventory')
    return {'attempt_nonce': NONCE, 'unit': UNIT, 'invocation': INVOCATION,
            'actor_pid': ACTOR_PID, 'original_runtime_success': False,
            'original_cleanup_bound': True, 'main_before_after_equal': True,
            'continuous_main_claimed': False, 'base_image_identity': IMAGE_ID,
            'prepared_full_image_sha256': IMAGE_SHA256}

def no_capabilities(fd):
    try:
        value = os.getxattr(fd, 'security.capability')
    except OSError as error:
        need(error.errno in (errno.ENODATA, errno.EOPNOTSUPP),
             'cannot establish fixed tool file capabilities')
        value = b''
    need(value == b'', 'fixed tool has file capabilities')

def opened(name, parent, held, is_directory, maximum=None):
    need(name == '/' if parent is None else name not in ('', '.', '..') and '/' not in name,
         'invalid fixed path component')
    if not is_directory:
        need(name in ('prepared.json', 'runtime-result.json', 'libdroidloom_selinux_compat.so'),
             'outside fixed file allowlist')
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    if is_directory:
        flags |= os.O_DIRECTORY
    fd = os.open(name, flags, **({} if parent is None else {'dir_fd': parent}))
    row = {'fd': fd, 'parent': parent, 'name': name, 'directory': is_directory,
           'before': None}
    # Register before every fallible metadata operation, including fstat.
    held.append(row)
    need(len(held) <= 9, 'fixed held descriptor count exceeded')
    value = os.fstat(fd)
    if is_directory:
        need(stat.S_ISDIR(value.st_mode) and value.st_uid == value.st_gid == 0 and
             not value.st_mode & 0o022, 'fixed directory authority differs')
        describe = directory_stamp
    else:
        need(type(maximum) is int and stat.S_ISREG(value.st_mode) and
             value.st_uid == value.st_gid == 0 and value.st_nlink == 1 and
             not value.st_mode & 0o6022 and 0 < value.st_size <= maximum,
             'fixed file authority/type/nlink/size differs')
        describe = stamp
    row['before'] = describe(value)
    named = os.stat(name, follow_symlinks=False,
                    **({} if parent is None else {'dir_fd': parent}))
    need(describe(named) == row['before'], 'fixed named and held object differ')
    return fd

def elf64_preload_diagnosis(body):
    """Bounded static metadata for one exact historical preload, never dlopen/execute."""
    need(type(body) is bytes and 64 <= len(body) <= ELF_LIMIT, 'ELF body bound differs')
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', body, 0)
    ident, kind, machine, version, entry, phoff, shoff, flags, ehsize, phsize, phnum, shsize, shnum, shstr = header
    need(ident[:7] == b'\x7fELF\x02\x01\x01' and kind == 3 and machine == 62 and
         version == 1 and ehsize == 64 and phsize == 56 and shsize == 64 and
         1 <= phnum <= 128 and 1 <= shnum <= 512 and 0 < shstr < shnum,
         'bounded ELF64 x86_64 shared-object schema differs')

    def bounded(offset, size, why):
        need(type(offset) is int and type(size) is int and
             0 <= offset <= len(body) and 0 <= size <= len(body) - offset, why)
        return body[offset:offset + size]

    def string_at(table, offset):
        need(0 <= offset < len(table), 'ELF string offset outside table')
        boundary = table.find(b'\0', offset, min(len(table), offset + 513))
        need(boundary >= offset, 'ELF string is unterminated or exceeds bound')
        raw = table[offset:boundary]
        need(all(32 <= value < 127 for value in raw), 'ELF symbol/name is not bounded ASCII')
        return raw.decode('ascii')

    bounded(phoff, phnum * phsize, 'program header table outside ELF')
    programs = [struct.unpack_from('<IIQQQQQQ', body, phoff + i * phsize)
                for i in range(phnum)]
    loads = []
    for value in programs:
        ptype, pflags, offset, address, physical, file_size, memory_size, alignment = value
        bounded(offset, file_size, 'program segment outside ELF')
        if ptype == 1:
            need(pflags & ~7 == 0 and file_size <= memory_size and
                 address + memory_size <= 1 << 64, 'load segment flags or range differs')
            loads.append({'offset': offset, 'address': address, 'file_bytes': file_size,
                          'memory_bytes': memory_size, 'flags': pflags, 'alignment': alignment})
    need(1 <= len(loads) <= 16, 'ELF load segment count outside bound')
    bounded(shoff, shnum * shsize, 'section header table outside ELF')
    sections = [struct.unpack_from('<IIQQQQIIQQ', body, shoff + i * shsize)
                for i in range(shnum)]
    names_section = sections[shstr]
    need(names_section[1] == 3, 'section-name table is not a string table')
    names = bounded(names_section[4], names_section[5], 'section-name table outside ELF')
    named_sections = []
    for index, values in enumerate(sections):
        name, stype, sflags, address, offset, size, link, info, alignment, entsize = values
        if stype != 8:
            bounded(offset, size, 'file-backed section outside ELF')
        named_sections.append({'index': index, 'name': string_at(names, name),
            'type': stype, 'flags': sflags, 'address': address, 'offset': offset,
            'bytes': size, 'link': link, 'info': info, 'alignment': alignment,
            'entry_bytes': entsize})
    build_ids = []
    for section in named_sections:
        if section['type'] != 7:
            continue
        note = bounded(section['offset'], section['bytes'], 'note section outside ELF')
        need(len(note) <= 65536, 'note section exceeds bound')
        cursor = count = 0
        while cursor < len(note):
            if len(note) - cursor < 12:
                need(not any(note[cursor:]), 'nonzero partial ELF note')
                break
            name_size, desc_size, note_type = struct.unpack_from('<III', note, cursor)
            cursor += 12
            need(name_size <= 256 and desc_size <= 4096, 'ELF note payload exceeds bound')
            name_end = cursor + name_size
            desc_start = (name_end + 3) & ~3
            desc_end = desc_start + desc_size
            next_cursor = (desc_end + 3) & ~3
            need(next_cursor <= len(note), 'incomplete ELF note payload')
            if note[cursor:name_end] == b'GNU\0' and note_type == 3:
                need(desc_size in (16, 20, 32), 'GNU BuildId size outside fixed supported range')
                build_ids.append(note[desc_start:desc_end].hex())
            cursor = next_cursor
            count += 1
            need(count <= 64, 'ELF note count exceeds bound')

    unique_build_ids = sorted(set(build_ids))
    need(len(unique_build_ids) <= 1, 'ELF multiple different GNU BuildIds')
    result = {'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(),
        'class': 64, 'byte_order': 'little', 'type': 'ET_DYN', 'machine': 'x86_64',
        'build_ids': unique_build_ids, 'source_revision_mapping_proved': False,
        'loaded_process_bytes_read': False, 'runtime_symbol_resolution_proved': False,
        'load_segments': loads, 'dynamic_symbols': [], 'needed': [], 'soname': [],
        'dynamic_loader_flags': [], 'property_entry_points': {},
        'selected_code_windows': [], 'selected_rodata_strings': [],
        'code_windows_are_disassembly': False, 'gnu_debugdata_decoded': False}
    dynamic_tables = [s for s in named_sections if s['type'] == 11]
    need(len(dynamic_tables) == 1, 'exactly one bounded dynamic symbol table required')
    section = dynamic_tables[0]
    need(section['entry_bytes'] == 24 and section['bytes'] % 24 == 0 and
         0 < section['bytes'] // 24 <= 512 and 0 < section['link'] < shnum,
         'dynamic symbol table shape outside bound')
    strings_section = named_sections[section['link']]
    need(strings_section['type'] == 3, 'dynamic symbols need string table')
    strings = bounded(strings_section['offset'], strings_section['bytes'],
                      'dynamic string table outside ELF')
    symbol_table = []
    for index in range(section['bytes'] // 24):
        name, info, other, shindex, value, size = struct.unpack_from(
            '<IBBHQQ', body, section['offset'] + index * 24)
        symbol = {'index': index, 'name': string_at(strings, name),
                  'binding': info >> 4, 'type': info & 15, 'visibility': other & 3,
                  'section_index': shindex, 'value': value, 'bytes': size,
                  'defined': shindex != 0}
        symbol_table.append(symbol)
        if symbol['name']:
            result['dynamic_symbols'].append(symbol)
    dynamic_sections = [s for s in named_sections if s['type'] == 6]
    need(len(dynamic_sections) == 1, 'exactly one bounded dynamic section required')
    dynamic = dynamic_sections[0]
    need(dynamic['entry_bytes'] == 16 and dynamic['bytes'] % 16 == 0 and
         0 < dynamic['bytes'] // 16 <= 512 and dynamic['link'] == section['link'],
         'dynamic section shape or string-table linkage differs')
    terminated = False
    for index in range(dynamic['bytes'] // 16):
        tag, value = struct.unpack_from('<qQ', body, dynamic['offset'] + index * 16)
        if tag == 0:
            terminated = True
            break
        if tag in (1, 14):
            result['needed' if tag == 1 else 'soname'].append(string_at(strings, value))
        elif tag in (15, 29):
            result.setdefault('search_paths', []).append({'tag': tag, 'value': string_at(strings, value)})
        elif tag in (16, 24, 30, 0x6ffffffb):
            result['dynamic_loader_flags'].append({'tag': tag, 'value': value})
    need(terminated and len(result['needed']) <= 32 and len(result['soname']) <= 1 and
         len(result.get('search_paths', [])) <= 2, 'dynamic termination or count bound')
    total_code = 0
    for name in PROPERTY_SYMBOLS:
        rows = [s for s in result['dynamic_symbols'] if s['name'] == name]
        need(len(rows) <= 4, 'bounded named symbol versions required')
        result['property_entry_points'][name] = rows
        for row in rows:
            if not row['defined'] or row['type'] != 2 or row['bytes'] == 0:
                continue
            need(0 < row['bytes'] <= 4096, 'fixed property function code exceeds bound')
            total_code += row['bytes']
            need(total_code <= 8192, 'total selected property function code exceeds bound')
            start, end = row['value'], row['value'] + row['bytes']
            candidates = [p for p in loads if p['flags'] & 1 and
                          p['address'] <= start and end <= p['address'] + p['file_bytes']]
            need(len(candidates) == 1, 'defined property function outside exact executable load')
            segment = candidates[0]
            offset = segment['offset'] + start - segment['address']
            code = bounded(offset, row['bytes'], 'defined property function outside ELF')
            result['selected_code_windows'].append({'symbol': name, 'symbol_index': row['index'],
                'start_vaddr': start, 'end_vaddr': end, 'file_offset': offset, 'bytes': len(code),
                'sha256': hashlib.sha256(code).hexdigest(), 'hex': code.hex()})
    result['dynamic_relocations'] = []
    for relocation in named_sections:
        if relocation['type'] not in (4, 9) or relocation['link'] != dynamic_tables[0]['index']:
            continue
        entry_size = 24 if relocation['type'] == 4 else 16
        need(relocation['entry_bytes'] == entry_size and relocation['bytes'] % entry_size == 0 and
             relocation['bytes'] // entry_size <= 4096, 'bounded linked dynamic relocations required')
        for index in range(relocation['bytes'] // entry_size):
            position = relocation['offset'] + index * entry_size
            offset, info = struct.unpack_from('<QQ', body, position)
            symbol_index, rtype = info >> 32, info & 0xffffffff
            need(symbol_index < len(symbol_table), 'dynamic relocation symbol index outside table')
            if rtype not in (6, 7):
                continue
            result['dynamic_relocations'].append({'table': relocation['name'], 'index': index,
                'offset': offset, 'type': rtype, 'symbol_index': symbol_index,
                'symbol': symbol_table[symbol_index]['name'],
                'addend': struct.unpack_from('<q', body, position + 16)[0]
                          if entry_size == 24 else None})
    need(len(result['dynamic_relocations']) <= 512, 'dynamic relocation output exceeds bound')
    if result['selected_code_windows']:
        plt_bytes = 0
        for section in named_sections:
            if section['name'] not in ('.plt', '.plt.sec', '.plt.got') or not section['bytes']:
                continue
            plt_bytes += section['bytes']
            need(section['flags'] & 4 and plt_bytes <= 8192, 'bounded executable PLT required')
            start, end = section['address'], section['address'] + section['bytes']
            candidates = [p for p in loads if p['flags'] & 1 and
                          p['address'] <= start and end <= p['address'] + p['file_bytes']]
            need(len(candidates) == 1, 'PLT is not in one file-backed executable load')
            offset = candidates[0]['offset'] + start - candidates[0]['address']
            code = bounded(offset, section['bytes'], 'PLT code outside ELF')
            result['selected_code_windows'].append({'symbol': section['name'],
                'start_vaddr': start, 'end_vaddr': end, 'file_offset': offset, 'bytes': len(code),
                'sha256': hashlib.sha256(code).hexdigest(), 'hex': code.hex()})
    selected_bytes = 0
    for section in named_sections:
        if section['name'] != '.rodata' and not section['name'].startswith('.rodata.'):
            continue
        raw = bounded(section['offset'], section['bytes'], 'rodata section outside ELF')
        need(len(raw) <= 65536, 'preload rodata section exceeds bound')
        for match in re.finditer(rb'[\x20-\x7e]{4,256}\x00', raw):
            value = match.group()[:-1]
            if not re.search(rb'property|prop_area|ro\.|sdk|api.level|/dev/__properties__', value, re.IGNORECASE):
                continue
            selected_bytes += len(value)
            need(len(result['selected_rodata_strings']) < 64 and selected_bytes <= 8192,
                 'fixed property rodata selection exceeds bound')
            result['selected_rodata_strings'].append({'section': section['name'],
                'vaddr': section['address'] + match.start(), 'bytes': len(value),
                'text': value.decode('ascii'), 'sha256': hashlib.sha256(value).hexdigest()})
    result['entire_dynamic_symbol_table_parsed'] = True
    result['rodata_filter_complete_stream_claimed'] = False
    return result

def emit(report):
    raw = (json.dumps(report, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
    need(len(raw) <= OUTPUT_LIMIT, 'fixed metadata report exceeds output bound')
    need(len(raw) <= WIRE_LIMIT, 'fixed metadata wire exceeds output bound')
    sys.stdout.buffer.write(raw)

def main():
    report = {'schema': 1, 'kind': 'owner19-fixed-preload-property-ELF-read01',
        'collection_complete': False, 'qualification': False, 'first_error': None, 'errors': [],
        'records': {}, 'commands': [], 'processes_started': 0, 'files_created': False,
        'namespace_or_UID_changes': False, 'Main_or_services_touched': False,
        'live_Main_checked': False, 'image_written': False, 'image_mounted': False,
        'extraction_requested': False, 'raw_runtime_log_exported': False,
        'raw_ELF_binary_exported': False, 'static_fixed_function_code_only': True,
        'owner_failure_cause_proved': False, 'runtime_symbol_resolution_proved': False,
        'held_named_unchanged': False, 'held_fds_closed': False,
        'preload_read_validated_after_final_checks': False}
    held = []
    record_fds = {}
    preload = preload_raw = None
    started = time.monotonic()
    deadline = started + DEADLINE_SECONDS
    try:
        need(os.geteuid() == os.getegid() == 0, 'fixed protected preload read requires root')
        slash = opened('/', None, held, True)
        opt = opened('opt', slash, held, True)
        state = opened(STATE_NAME, opt, held, True)
        need(identity(os.fstat(state)) == STATE_ID, 'original state inode differs')
        records = {}
        for name in RECORDS:
            fd = opened(name, state, held, False, RECORD_LIMIT)
            before_stamp = stamp(os.fstat(fd))
            raw, value = read_record(fd, before_stamp, name, deadline)
            record_fds[name] = (fd, before_stamp, raw)
            records[name] = value
            report['records'][name] = {'bytes': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest(), 'identity': before_stamp}
        report['binding'] = validate_records(records['prepared.json'], records['runtime-result.json'])
        base = opened(IMAGE_PACKAGE, opt, held, True)
        payload = opened('payload', base, held, True)
        parent = opened('29', payload, held, True)
        preload = opened('libdroidloom_selinux_compat.so', parent, held, False, ELF_LIMIT)
        expected = FIXED_BASE_FILES[PRELOAD_RELATIVE]
        observed = stamp(os.fstat(preload))
        need(identity(os.fstat(preload)) == expected['identity'] and
             observed['bytes'] == expected['bytes'] and observed['mode'] == expected['mode'],
             'fixed preload identity or metadata differs')
        no_capabilities(preload)
        preload_raw = read_exact(preload, expected['bytes'], deadline)
        need(hashlib.sha256(preload_raw).hexdigest() == expected['sha256'],
             'fixed preload full hash differs')
        report['preload'] = {'path': PRELOAD_PATH, 'identity': observed,
            'bytes': len(preload_raw), 'sha256': expected['sha256']}
        report['ELF'] = elf64_preload_diagnosis(preload_raw)
    except BaseException as error:
        remember(report, 'fixed_preload_collection', error)
    finally:
        try:
            for name, (fd, original_stamp, original) in record_fds.items():
                raw, _ = read_record(fd, original_stamp, name, deadline)
                need(raw == original, 'original protected record changed')
            if preload_raw is not None:
                need(read_exact(preload, len(preload_raw), deadline) == preload_raw,
                     'fixed preload bytes changed')
                no_capabilities(preload)
            recheck(held)
            report['held_named_unchanged'] = True
        except BaseException as error:
            remember(report, 'final_input_recheck', error)
        closed = True
        for row in reversed(held):
            try:
                os.close(row['fd'])
            except BaseException as error:
                closed = False
                remember(report, 'held_' + row['name'] + '_close', error)
        report['held_fds_closed'] = closed
    report['held_descriptor_count'] = len(held)
    report['elapsed_seconds'] = time.monotonic() - started
    if time.monotonic() > deadline:
        try:
            raise RuntimeError('fixed preload observation exceeded bounded deadline')
        except RuntimeError as error:
            remember(report, 'final_deadline', error)
    report['collection_complete'] = (not report['errors'] and report['held_named_unchanged'] and
        report['held_fds_closed'] and len(held) == 9 and len(record_fds) == 2 and
        'ELF' in report and preload_raw is not None and time.monotonic() <= deadline)
    report['preload_read_validated_after_final_checks'] = report['collection_complete']
    emit(report)
    return 0 if report['collection_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
