"""Read one pinned retired-input init ELF's dynamic metadata; never execute it."""
import hashlib
import json
import os
import stat
import struct
import sys
import time

PATH = '/opt/p4-media-composer-diagnostic-20261102-chat2-r5/payload/android-init'
SIZE = 2967000
SHA256 = 'd6905d43a0dad5219b61c9759ab32352262558e1109762eec1a24be153181c73'
MAX_OUTPUT = 32768


def need(value, message):
    if not value:
        raise RuntimeError(message)


def stamp(s, directory=False):
    keys = {'dev': s.st_dev, 'ino': s.st_ino, 'mode': s.st_mode,
            'uid': s.st_uid, 'gid': s.st_gid}
    if not directory:
        keys.update(size=s.st_size, nlink=s.st_nlink,
                    mtime_ns=s.st_mtime_ns, ctime_ns=s.st_ctime_ns)
    return keys


def parse(raw):
    need(raw[:7] == b'\x7fELF\x02\x01\x01', 'ELF64 little-endian version1 required')
    head = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    _, kind, machine, version, _, phoff, shoff, _, ehsize, phsize, phnum, shsize, shnum, shstr = head
    need(kind in (2, 3) and version == 1 and ehsize == 64 and
         phsize == 56 and 0 < phnum <= 128 and shsize == 64 and
         0 < shnum <= 512 and shstr < shnum, 'bounded native ELF table format required')

    def body(offset, size):
        need(0 <= offset <= len(raw) and 0 <= size <= len(raw) - offset,
             'ELF referenced extent exceeds pinned bytes')
        return raw[offset:offset + size]

    def string(table, offset):
        need(0 <= offset < len(table), 'ELF string offset out of range')
        end = table.find(b'\0', offset, min(offset + 1025, len(table)))
        need(end >= offset, 'ELF string is unterminated/overlong')
        return table[offset:end].decode('ascii')

    sections = [struct.unpack_from('<IIQQQQIIQQ', body(shoff + i * 64, 64))
                for i in range(shnum)]
    names = body(sections[shstr][4], sections[shstr][5])
    dynamic = []
    symbols = []
    interpreters = []
    for i in range(phnum):
        p = struct.unpack('<IIQQQQQQ', body(phoff + i * 56, 56))
        if p[0] == 3:
            value = body(p[2], p[5])
            need(1 < len(value) <= 256 and value[-1:] == b'\0' and b'\0' not in value[:-1],
                 'invalid ELF interpreter')
            interpreters.append(value[:-1].decode('ascii'))
    need(len(interpreters) == 1, 'one dynamic ELF interpreter required')
    dyn_count = sym_count = 0
    for index, s in enumerate(sections):
        name = string(names, s[0])
        if s[1] not in (6, 11):
            continue
        need(s[6] < len(sections) and sections[s[6]][1] == 3,
             'dynamic metadata lacks its string table')
        table = body(sections[s[6]][4], sections[s[6]][5])
        if s[1] == 6:
            dyn_count += 1
            need(s[9] == 16 and s[5] % 16 == 0 and s[5] // 16 <= 1024,
                 'invalid dynamic entry bound')
            seen_null = False
            for offset in range(0, s[5], 16):
                tag, value = struct.unpack('<qQ', body(s[4] + offset, 16))
                if tag == 0:
                    seen_null = True
                    break
                if tag in (1, 14, 15, 29):
                    dynamic.append({'tag': {1: 'NEEDED', 14: 'SONAME', 15: 'RPATH', 29: 'RUNPATH'}[tag],
                                    'value': string(table, value)})
            need(seen_null, 'dynamic table has no terminator')
        else:
            sym_count += 1
            need(s[9] == 24 and s[5] % 24 == 0 and s[5] // 24 <= 65536,
                 'invalid dynamic symbol entry bound')
            for offset in range(0, s[5], 24):
                n, info, other, shndx, value, size = struct.unpack('<IBBHQQ', body(s[4] + offset, 24))
                symbol = string(table, n)
                if 'KernelLogger' in symbol or 'InitLogging' in symbol:
                    symbols.append({'name': symbol, 'binding': info >> 4, 'type': info & 15,
                                    'visibility': other & 3, 'section_index': shndx,
                                    'value': value, 'size': size, 'table': name,
                                    'defined': shndx != 0})
    need(dyn_count == sym_count == 1 and len(dynamic) <= 64 and len(symbols) <= 32,
         'unique bounded dynamic tables required')
    return {'elf_machine': machine, 'elf_type': kind, 'interpreter': interpreters[0],
            'dynamic_strings': dynamic, 'logger_symbols': symbols,
            'shared_library_definition_read': False, 'call_abi_verified': False,
            'logger_called': False, 'binary_executed': False}


def collect():
    result = {'schema': 1, 'kind': 'OWNER15_EXACT_INIT_ELF_DYNAMIC_METADATA_ONLY',
              'path': PATH, 'expected_bytes': SIZE, 'expected_sha256': SHA256,
              'collection_complete': False, 'files_modified': False,
              'android_or_ui_action': False, 'main_qualification': False,
              'error': None, 'close_errors': [], 'held_fds_closed': False}
    owned = []
    held = []
    deadline = time.monotonic() + 5
    try:
        parent = None
        for name in ['/', 'opt', 'p4-media-composer-diagnostic-20261102-chat2-r5', 'payload']:
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                         **({} if parent is None else {'dir_fd': parent}))
            owned.append(fd)
            value = os.fstat(fd)
            need(stat.S_ISDIR(value.st_mode) and value.st_uid == value.st_gid == 0 and
                 value.st_mode & 0o22 == 0, 'fixed ancestor authority differs')
            held.append((fd, parent, name, stamp(value, True), True))
            parent = fd
        fd = os.open('android-init', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        owned.append(fd)
        value = os.fstat(fd)
        need(stat.S_ISREG(value.st_mode) and value.st_uid == value.st_gid == 0 and
             value.st_nlink == 1 and stat.S_IMODE(value.st_mode) == 0o555 and
             value.st_size == SIZE, 'actual pinned init metadata differs')
        before = stamp(value)
        held.append((fd, parent, 'android-init', before, False))
        for item, directory_parent, name, original, directory in held:
            need(stamp(os.stat(name, follow_symlinks=False,
                               **({} if directory_parent is None else {'dir_fd': directory_parent})),
                       directory) == original, 'initial named/held identity differs')
        raw = bytearray()
        while len(raw) < SIZE:
            need(time.monotonic() <= deadline, 'fixed ELF deadline exceeded')
            chunk = os.pread(fd, min(65536, SIZE - len(raw)), len(raw))
            need(bool(chunk), 'short pinned ELF')
            raw.extend(chunk)
        need(not os.pread(fd, 1, SIZE), 'pinned ELF grew')
        need(hashlib.sha256(raw).hexdigest() == SHA256, 'pinned init SHA differs')
        result.update(identity=before, actual_bytes=len(raw), actual_sha256=SHA256,
                      dynamic_metadata=parse(bytes(raw)))
        for item, directory_parent, name, original, directory in held:
            need(stamp(os.fstat(item), directory) == original, 'held input changed')
            need(stamp(os.stat(name, follow_symlinks=False,
                               **({} if directory_parent is None else {'dir_fd': directory_parent})),
                       directory) == original, 'named input changed')
        need(time.monotonic() <= deadline, 'fixed ELF deadline exceeded')
        result['named_and_held_unchanged'] = True
    except BaseException as error:
        result['error'] = {'type': type(error).__name__, 'text': str(error)[:1024]}
    finally:
        for fd in reversed(owned):
            try:
                os.close(fd)
            except OSError as error:
                result['close_errors'].append({'fd': fd, 'errno': error.errno})
        result['held_fds_closed'] = not result['close_errors']
    result['collection_complete'] = result['error'] is None and result['held_fds_closed']
    encoded = (json.dumps(result, sort_keys=True, separators=(',', ':')) + '\n').encode()
    need(len(encoded) <= MAX_OUTPUT, 'bounded metadata report exceeded')
    sys.stdout.buffer.write(encoded)
    return 0 if result['collection_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(collect())
