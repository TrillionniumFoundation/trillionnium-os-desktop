"""Observe only two fixed, not-yet-qualified Android build inputs."""
import base64, hashlib, json, os, stat, struct, sys, time

PATHS = [('/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/bionic/libc/include/dlfcn.h', 32768, 'header'), ('/home/alex/work/pocket4-lmkd-production-candidate-20261104/android-link-01/deps/libdl.so', 4194304, 'library')]
PRIOR_ACTUAL_147_INPUT_RECEIPT_SHA256 = "718b131c94126d6d7f9df30a2f164e8f85335fc027a2db3101b0e5904c291b64"
MAX_OUTPUT = 65536

def need(value, message):
    if not value: raise RuntimeError(message)

def stamp(s, directory=False):
    result = dict(dev=s.st_dev, ino=s.st_ino, mode=s.st_mode, uid=s.st_uid, gid=s.st_gid)
    if not directory:
        result.update(size=s.st_size, nlink=s.st_nlink, mtime_ns=s.st_mtime_ns, ctime_ns=s.st_ctime_ns)
    return result

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
    need(not interpreters, 'shared library must not have an interpreter')
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
                if symbol in ('dlsym', 'dlerror', 'dladdr'):
                    symbols.append({'name': symbol, 'binding': info >> 4, 'type': info & 15,
                                    'visibility': other & 3, 'section_index': shndx,
                                    'value': value, 'size': size, 'table': name,
                                    'defined': shndx != 0})
    need(dyn_count == sym_count == 1 and len(dynamic) <= 64 and len(symbols) <= 32,
         'unique bounded dynamic tables required')
    return {'elf_machine': machine, 'elf_type': kind, 'interpreter': None,
            'dynamic_strings': dynamic, 'lookup_symbols': symbols,
            'shared_library_definition_read': False, 'call_abi_verified': False,
            'logger_called': False, 'binary_executed': False}


def collect():
    out = dict(schema=1, kind="OWNER16_FIXED_TWO_BUILD_DEPENDENCIES_READONLY", inputs=[],
        prior_147_input_receipt_sha256=PRIOR_ACTUAL_147_INPUT_RECEIPT_SHA256,
        collection_complete=False, expected_new_input_sha256=None,
        build_or_runtime_qualified=False, android_or_ui_action=False,
        files_modified=False, subprocess_started=False, error=None,
        close_errors=[], held_fds_closed=False)
    owned, held = [], []
    deadline = time.monotonic() + 5
    try:
        for path, maximum, kind in PATHS:
            parent = None
            parts = path.split('/')
            for name in ['/'] + parts[1:-1]:
                need(time.monotonic() <= deadline, 'two-input deadline exceeded')
                fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                             **({} if parent is None else {'dir_fd': parent}))
                owned.append(fd)
                meta = os.fstat(fd)
                need(stat.S_ISDIR(meta.st_mode) and meta.st_uid in (0, 1000), 'candidate ancestor identity differs')
                held.append((fd, parent, name, stamp(meta, True), True))
                parent = fd
            leaf = parts[-1]
            fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            owned.append(fd)
            meta = os.fstat(fd)
            need(stat.S_ISREG(meta.st_mode) and meta.st_uid in (0, 1000) and meta.st_nlink == 1
                 and 0 < meta.st_size <= maximum, 'candidate file is not bounded regular single-link input')
            identity = stamp(meta)
            held.append((fd, parent, leaf, identity, False))
            need(stamp(os.stat(leaf, dir_fd=parent, follow_symlinks=False)) == identity, 'initial named input differs')
            raw = bytearray()
            while len(raw) < meta.st_size:
                need(time.monotonic() <= deadline, 'two-input deadline exceeded')
                block = os.pread(fd, min(65536, meta.st_size - len(raw)), len(raw))
                need(block, 'candidate input truncated')
                raw.extend(block)
            need(not os.pread(fd, 1, len(raw)), 'candidate input grew')
            row = dict(path=path, kind=kind, identity=identity, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            if kind == 'header':
                raw.decode('utf-8')
                row['utf8_original_base64'] = base64.b64encode(raw).decode()
            else:
                value = parse(bytes(raw))
                need(value['elf_machine'] == 62 and value['elf_type'] == 3, 'x86_64 DSO required')
                need([v['value'] for v in value['dynamic_strings'] if v['tag'] == 'SONAME'] == ['libdl.so'], 'candidate SONAME differs')
                names = {v['name'] for v in value['lookup_symbols'] if v['defined'] and v['binding'] in (1, 2) and v['type'] == 2 and v['visibility'] == 0}
                need(names == {'dlsym', 'dladdr', 'dlerror'}, 'candidate lookup exports differ')
                row['dynamic_metadata'] = value
            out['inputs'].append(row)
        for fd, parent, name, before, directory in held:
            need(stamp(os.fstat(fd), directory) == before, 'held candidate changed')
            need(stamp(os.stat(name, follow_symlinks=False, **({} if parent is None else {'dir_fd': parent})), directory) == before, 'named candidate changed')
        need(time.monotonic() <= deadline, 'two-input deadline exceeded')
        out['all_named_and_held_unchanged'] = True
    except BaseException as error:
        out['error'] = dict(type=type(error).__name__, message=str(error)[:1024])
    finally:
        for fd in reversed(owned):
            try: os.close(fd)
            except OSError as error: out['close_errors'].append(dict(fd=fd, errno=error.errno))
        out['held_fds_closed'] = not out['close_errors']
    out['collection_complete'] = out['error'] is None and len(out['inputs']) == 2 and out['held_fds_closed']
    encoded = (json.dumps(out, sort_keys=True, separators=(',', ':')) + '\n').encode()
    need(len(encoded) <= MAX_OUTPUT, 'two-input output bound exceeded')
    sys.stdout.buffer.write(encoded)
    return 0 if out['collection_complete'] else 1

if __name__ == '__main__':
    raise SystemExit(collect())
