"""Freeze a two-path, read-only new build-input observation; never dispatch."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD = ROOT / 'android-owner15-init-elf-logger-readonly01'
OUT = ROOT / 'android-owner16-log-dependencies-readonly01'
ACTUAL = ROOT / 'root-recovery-20261104-02/evidence/init-cgroup-handoff-build01/build-result.json'
HEADER = '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/bionic/libc/include/dlfcn.h'
LIBRARY = '/home/alex/work/pocket4-lmkd-production-candidate-20261104/android-link-01/deps/libdl.so'


def sha(raw): return hashlib.sha256(raw).hexdigest()
def pretty(value): return json.dumps(value, sort_keys=True, indent=2) + '\n'


def main():
    original = (OLD / 'read_init_elf.py').read_text()
    actual_raw = ACTUAL.read_bytes()
    assert len(actual_raw) == 540269 and sha(actual_raw) == '718b131c94126d6d7f9df30a2f164e8f85335fc027a2db3101b0e5904c291b64'
    actual = json.loads(actual_raw)
    assert actual['success'] and actual['all_inputs_unchanged'] and len(actual['original_inputs_before']) == 147
    rows = actual['original_inputs_before']
    assert HEADER not in rows and LIBRARY not in rows
    assert str(Path(HEADER).with_name('fcntl.h')) in rows
    assert str(Path(LIBRARY).with_name('libc.so')) in rows
    parse = original[original.index('def parse(raw):'):original.index('\n\ndef collect():')]
    parse = parse.replace("need(len(interpreters) == 1, 'one dynamic ELF interpreter required')", "need(not interpreters, 'shared library must not have an interpreter')")
    parse = parse.replace("if 'KernelLogger' in symbol or 'InitLogging' in symbol:", "if symbol in ('dlsym', 'dlerror', 'dladdr'):")
    parse = parse.replace("'interpreter': interpreters[0]", "'interpreter': None")
    parse = parse.replace("'logger_symbols': symbols", "'lookup_symbols': symbols")
    source = '''"""Observe only two fixed, not-yet-qualified Android build inputs."""
import base64, hashlib, json, os, stat, struct, sys, time

PATHS = ''' + repr([(HEADER, 32768, 'header'), (LIBRARY, 4 * 1024 * 1024, 'library')]) + '''
PRIOR_ACTUAL_147_INPUT_RECEIPT_SHA256 = "718b131c94126d6d7f9df30a2f164e8f85335fc027a2db3101b0e5904c291b64"
MAX_OUTPUT = 65536

def need(value, message):
    if not value: raise RuntimeError(message)

def stamp(s, directory=False):
    result = dict(dev=s.st_dev, ino=s.st_ino, mode=s.st_mode, uid=s.st_uid, gid=s.st_gid)
    if not directory:
        result.update(size=s.st_size, nlink=s.st_nlink, mtime_ns=s.st_mtime_ns, ctime_ns=s.st_ctime_ns)
    return result

''' + parse + '''

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
    encoded = (json.dumps(out, sort_keys=True, separators=(',', ':')) + '\\n').encode()
    need(len(encoded) <= MAX_OUTPUT, 'two-input output bound exceeded')
    sys.stdout.buffer.write(encoded)
    return 0 if out['collection_complete'] else 1

if __name__ == '__main__':
    raise SystemExit(collect())
'''
    ast.parse(source)
    request = json.loads((OLD / 'exact-request.json').read_bytes())
    request.update(stdin=source, idempotency_key='p4-owner16-init-log-build-deps-read01-' + sha(source.encode())[:16])
    files = {'read_dependencies.py': source.encode(), 'exact-request.json': pretty(request).encode(),
        'from-init-elf-reader.diff': ''.join(difflib.unified_diff(original.splitlines(True), source.splitlines(True), fromfile='exact-init-reader', tofile='two-fixed-build-inputs')).encode(),
        'prior-input-basis.json': pretty({'prior_receipt_path': str(ACTUAL), 'bytes': len(actual_raw), 'sha256': sha(actual_raw),
            'exact_input_count': 147, 'new_candidate_paths_not_prior_inputs': [HEADER, LIBRARY],
            'observed_sibling_inputs': [rows[str(Path(HEADER).with_name('fcntl.h'))], rows[str(Path(LIBRARY).with_name('libc.so'))]],
            'new_values_unknown_until_collection': True, 'no_library_or_directory_scan': True}).encode(),
        'make_dependency_reader.py': Path(__file__).read_bytes()}
    files['SOURCE_PINS.json'] = pretty({'schema': 1, 'files': {k: {'bytes': len(v), 'sha256': sha(v)} for k, v in sorted(files.items())}}).encode()
    OUT.mkdir()
    for key, data in files.items():
        with (OUT / key).open('xb') as f: f.write(data)
    print(pretty({'root': str(OUT), 'source': {'bytes': len(source.encode()), 'sha256': sha(source.encode())},
        'request': {'bytes': len(files['exact-request.json']), 'sha256': sha(files['exact-request.json'])},
        'manifest_sha256': sha(files['SOURCE_PINS.json']), 'key': request['idempotency_key']}))

if __name__ == '__main__': main()
