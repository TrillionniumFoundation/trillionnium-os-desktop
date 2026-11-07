"""Read exactly three public Rust sources from the completed owned builder469.

No source execution, Git, subprocess, directory enumeration, network, writes,
Main access, or inferred remote Destroy completion. All explicit read FDs are
held through the final named/held check and closed once before output.
"""
import hashlib
import json
import os
import stat
import sys
import time

ROOT = "/home/alex/work/pocket4-native-typed-ingress-builder469-hal-provider-closure-compile-01-20261106"
SOURCE = ROOT + '/builder-source'
PINS = [{"path":"graphics/droidloom-denial-protocol/src/lib.rs","bytes":97476,"kind":"file","mode":436,"sha256":"abac4785ca16eccd330da0f5d928e5a6a1a11d9f5ac4306bc7c63121c4a84a27"},{"path":"graphics/droidloom-denial-ipc/src/lib.rs","bytes":42737,"kind":"file","mode":436,"sha256":"7724a0778185bfec08c8e2fe23a3168a757a62413ac5403e369a747c59b26a8f"},{"path":"graphics/droidloom-denial-endpoint/src/lib.rs","bytes":44175,"kind":"file","mode":436,"sha256":"4d79ae81810aab3784c0e265fd861cb9fcbacab9160854553d56584b2751ebe6"}]
AUTHORITIES = [{"role":"manifest","path":"/home/alex/work/pocket4-native-typed-ingress-builder469-hal-provider-closure-compile-01-20261106/attempt01/copied-builder-source-manifest.json","bytes":99327,"sha256":"88dc3c8020c436009862800ffdc5af97f50f6ae7efff832562c2784d66794701","mode":384},{"role":"producer","path":"/home/alex/work/pocket4-native-typed-ingress-builder469-hal-provider-closure-compile-01-20261106/attempt01/result.json","bytes":170316,"sha256":"3636057b9a20fc895657064da3fb66d8ded7e69ebfa5a5b92072a51b33f29fd5","mode":384}]
MAX_FDS = 40
OUTPUT_BYTES = 2 * 1024 * 1024
STARTED = time.monotonic_ns()
DEADLINE = STARTED + 8_000_000_000
FDS = {}
ORDER = []
ERRORS = []
RESULT = {
    'schema': 1, 'scope': 'exact-builder469-three-public-Denial-sources-readonly01',
    'source_root': SOURCE, 'started_monotonic_ns': STARTED,
    'deadline_monotonic_ns': DEADLINE, 'authority_qualified': False,
    'files': [], 'authorities': [], 'errors': ERRORS,
    'collection_complete': False, 'all_explicit_read_fds_closed': False,
    'source_executed': False, 'children_started': 0,
    'network_operations': 0, 'filesystem_writes': 0,
    'Main_accessed': False, 'installed_Main_same_source_qualified': False,
    'remote_Destroy_completion_qualified': False,
}

def need(value, code):
    if not value:
        raise RuntimeError(code)

def check():
    need(time.monotonic_ns() < DEADLINE, 'READ_DEADLINE')

def metadata(s):
    return {'device': s.st_dev, 'inode': s.st_ino, 'mode': s.st_mode,
            'uid': s.st_uid, 'gid': s.st_gid, 'nlink': s.st_nlink,
            'bytes': s.st_size, 'mtime_ns': s.st_mtime_ns, 'ctime_ns': s.st_ctime_ns}

def same_binding(left, right, directory):
    # A sibling creation may change parent size/link-count/timestamps without
    # replacing this held directory. Keep full observations but bind directory
    # inode/type/owner/access mode; every selected leaf retains full equality.
    if directory:
        fields = ('device', 'inode', 'mode', 'uid', 'gid')
        return all(left[key] == right[key] for key in fields)
    return left == right

def error(stage, exc, path=None):
    row = {'stage': stage, 'type': type(exc).__name__,
           'errno': getattr(exc, 'errno', None), 'error': repr(exc)[:512]}
    if path is not None:
        row['path'] = path
    ERRORS.append(row)

def acquire(path, directory):
    check()
    if path in FDS:
        row = FDS[path]
        need(row['directory'] is directory, 'FIXED_PATH_KIND_CHANGED')
        return row['fd']
    need(path.startswith('/') and '\x00' not in path and
         (path == '/' or all(part not in ('', '.', '..') for part in path[1:].split('/'))),
         'FIXED_ABSOLUTE_PATH_REQUIRED')
    need(len(ORDER) < MAX_FDS, 'EXPLICIT_FD_BOUND')
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    if directory:
        flags |= os.O_DIRECTORY
    if path == '/':
        parent, name, parent_fd = None, None, None
        before = os.stat('/', follow_symlinks=False)
        fd = os.open('/', flags)
    else:
        parent, _, name = path.rpartition('/')
        parent = parent or '/'
        parent_fd = acquire(parent, True)
        need(len(ORDER) < MAX_FDS, 'EXPLICIT_FD_BOUND')
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        fd = os.open(name, flags, dir_fd=parent_fd)
    row = {'path': path, 'directory': directory, 'parent': parent,
           'name': name, 'fd': fd, 'named_before': metadata(before),
           'held_before': None, 'held_final': None, 'named_final': None,
           'close_attempted': False, 'closed': False}
    FDS[path] = row
    ORDER.append(row)
    # Journal the newly acquired descriptor before any operation that can fail.
    held = os.fstat(fd)
    row['held_before'] = metadata(held)
    need(same_binding(row['named_before'], row['held_before'], directory),
         'NAMED_HELD_INITIAL_CHANGED')
    need(stat.S_ISDIR(held.st_mode) if directory else stat.S_ISREG(held.st_mode),
         'FIXED_PATH_TYPE')
    need(not os.get_inheritable(fd), 'READ_FD_INHERITABLE')
    return fd

def read_exact(pin, role, content=False):
    check()
    path = pin['path']
    record = {'role': role, 'path': path, 'expected_bytes': pin['bytes'],
              'expected_sha256': pin['sha256'], 'metadata': None,
              'bytes': None, 'sha256': None, 'eof': False, 'qualified': False}
    target = RESULT['files'] if content else RESULT['authorities']
    target.append(record)
    fd = acquire(path, False)
    before = metadata(os.fstat(fd))
    record['metadata'] = before
    need(before['uid'] == before['gid'] == 1000 and before['nlink'] == 1 and
         stat.S_IMODE(before['mode']) == pin['mode'] and
         before['bytes'] == pin['bytes'], 'FIXED_FILE_METADATA')
    parts = []
    position = 0
    while position < pin['bytes']:
        check()
        part = os.pread(fd, min(65536, pin['bytes'] - position), position)
        need(part, 'FIXED_FILE_TRUNCATED')
        parts.append(part)
        position += len(part)
    check()
    need(os.pread(fd, 1, position) == b'', 'FIXED_FILE_EXTRA_BYTES')
    record['eof'] = True
    raw = b''.join(parts)
    record['bytes'] = len(raw)
    record['sha256'] = hashlib.sha256(raw).hexdigest()
    need(len(raw) == pin['bytes'] and record['sha256'] == pin['sha256'],
         'FIXED_FILE_CONTENT_PIN')
    need(metadata(os.fstat(fd)) == before, 'FIXED_FILE_CHANGED_DURING_READ')
    text = raw.decode('utf-8', 'strict')
    if content:
        record['content'] = text
    record['qualified'] = True
    return text

def unique_object(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'DUPLICATE_AUTHORITY_JSON_KEY')
        result[key] = value
    return result

def parse_authority(raw):
    return json.loads(raw, object_pairs_hook=unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          RuntimeError('NONFINITE_AUTHORITY_JSON')))

def qualify_authorities(manifest, producer):
    need(type(manifest) is dict and len(manifest) == 499, 'MANIFEST_499_MAP')
    for pin in PINS:
        need(manifest.get(pin['path']) == {
            'kind': 'file', 'bytes': pin['bytes'], 'sha256': pin['sha256'],
            'mode': pin['mode']}, 'MANIFEST_FIXED_LEAF_MISMATCH')
    need(type(producer) is dict and producer['state'] == 'PASS' and
         producer['copied_manifest'] == {
             'path': AUTHORITIES[0]['path'], 'bytes': AUTHORITIES[0]['bytes'],
             'sha256': AUTHORITIES[0]['sha256']} and
         producer['original_source_unchanged_after'] is True and
         producer['copied_source_unchanged_after'] is True and
         producer['source_delta']['actual_source_file_count'] == 499 and
         producer['source_delta']['engine_source_files_changed'] == 0 and
         producer['cleanup']['errors'] == [] and
         producer['cleanup']['remaining'] == [] and
         producer['cleanup']['forced_cleanup'] is False,
         'EXACT_PRODUCER_MANIFEST_OR_CLEANUP')
    RESULT['authority_qualified'] = True

def final_bindings():
    for row in ORDER:
        try:
            held = metadata(os.fstat(row['fd']))
            if row['path'] == '/':
                named = metadata(os.stat('/', follow_symlinks=False))
            else:
                parent = FDS[row['parent']]
                named = metadata(os.stat(row['name'], dir_fd=parent['fd'],
                                         follow_symlinks=False))
            row['held_final'], row['named_final'] = held, named
            need(all(same_binding(row['held_before'], candidate, row['directory'])
                     for candidate in (row['named_before'], held, named)),
                 'HELD_NAMED_FINAL_CHANGED')
        except BaseException as exc:
            error('final_binding', exc, row['path'])

try:
    acquire(ROOT, True)
    acquire(SOURCE, True)
    authorities = [parse_authority(read_exact(pin, pin['role']))
                   for pin in AUTHORITIES]
    qualify_authorities(*authorities)
    for pin in PINS:
        fixed = dict(pin, path=SOURCE + '/' + pin['path'])
        read_exact(fixed, 'public_Rust_source', True)
    check()
except BaseException as exc:
    error('collect', exc)
finally:
    final_bindings()
    for row in reversed(ORDER):
        row['close_attempted'] = True
        try:
            os.close(row['fd'])
            row['closed'] = True
        except BaseException as exc:
            error('close', exc, row['path'])
    RESULT['all_explicit_read_fds_closed'] = all(row['closed'] for row in ORDER)
    RESULT['bindings'] = [{key: value for key, value in row.items() if key != 'fd'}
                          for row in ORDER]
    RESULT['finished_monotonic_ns'] = time.monotonic_ns()
    if RESULT['finished_monotonic_ns'] >= DEADLINE:
        error('final_deadline', RuntimeError('READ_DEADLINE'))
    RESULT['collection_complete'] = (
        RESULT['authority_qualified'] and len(RESULT['files']) == 3 and
        all(row['qualified'] for row in RESULT['files']) and
        RESULT['all_explicit_read_fds_closed'] and not ERRORS)
    RESULT['state'] = 'PASS' if RESULT['collection_complete'] else 'FAIL'

raw = (json.dumps(RESULT, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode('ascii')
if len(raw) > OUTPUT_BYTES:
    RESULT['collection_complete'] = False
    RESULT['state'] = 'FAIL'
    error('output', RuntimeError('OUTPUT_BOUND'))
    for row in RESULT['files']:
        row.pop('content', None)
    raw = (json.dumps(RESULT, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode('ascii')
need(len(raw) <= OUTPUT_BYTES, 'MINIMAL_OUTPUT_BOUND')
sys.stdout.buffer.write(raw)
sys.stdout.buffer.flush()
raise SystemExit(0 if RESULT['collection_complete'] else 1)
