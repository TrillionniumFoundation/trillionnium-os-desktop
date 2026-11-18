"""Create-only root seal of the dedicated storage capsule and seventeen fixed proofs.

All ordinary inputs are completely read and pinned before the first seal write.
This installs source/proof bytes only; it creates no role root or mountpoint.
"""
import hashlib, io, json, os, pathlib, stat, sys, tarfile


def f9(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
            value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def sha(value):
    assert type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)
    return value


def full_ref(value):
    assert type(value) is dict and set(value) == {'path', 'bytes', 'sha256', 'identity'}
    p = value['path']
    assert type(p) is str and p.startswith('/') and pathlib.PurePosixPath(p).as_posix() == p
    assert all(part not in ('', '.', '..') for part in p.split('/')[1:]) and '\0' not in p
    identity = value['identity']
    assert type(identity) is list and len(identity) == 9 and all(type(n) is int for n in identity)
    assert identity[0] > 0 and identity[1] > 0 and stat.S_ISREG(identity[2]) and identity[5] == 1
    assert type(value['bytes']) is int and 0 <= value['bytes'] == identity[6]
    sha(value['sha256'])
    return value


def read_fixed(path, limit, expected=None, owner_mode=None):
    path = pathlib.Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        assert stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 <= before.st_size <= limit
        assert f9(before) == f9(path.lstat())
        if owner_mode is not None:
            assert (before.st_uid, before.st_gid, stat.S_IMODE(before.st_mode)) == owner_mode
        chunks, size = [], 0
        while True:
            chunk = os.read(fd, min(65536, limit - size + 1))
            assert type(chunk) is bytes
            if not chunk:
                break
            size += len(chunk)
            assert size <= limit
            chunks.append(chunk)
        after = os.fstat(fd)
        assert f9(before) == f9(after) == f9(path.lstat())
        raw = b''.join(chunks)
        assert len(raw) == before.st_size
        ref = {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
               'identity': f9(after)}
        if expected is not None:
            assert ref == full_ref(expected)
        return ref, raw
    finally:
        os.close(fd)


def bookend(refs):
    for ref in refs:
        assert f9(pathlib.Path(ref['path']).lstat()) == full_ref(ref)['identity']


def write_new(path, body):
    path = pathlib.Path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o444)
    with os.fdopen(fd, 'wb') as stream:
        os.fchmod(stream.fileno(), 0o444)
        assert stream.write(body) == len(body)
        stream.flush(); os.fsync(stream.fileno())
        identity = f9(os.fstat(stream.fileno()))
    expected = {'path': str(path), 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(),
                'identity': identity}
    ref, reread = read_fixed(path, len(body), expected, (0, 0, 0o444))
    assert reread == body
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        s = os.fstat(parent)
        assert s.st_uid == s.st_gid == 0 and f9(s) == f9(path.parent.lstat())
        os.fsync(parent)
        assert f9(os.fstat(parent)) == f9(path.parent.lstat())
    finally:
        os.close(parent)
    return ref


assert len(sys.argv) == 5 and sys.argv[1] in ('pocket4', 'desktop')
host, archive_sha, manifest_sha, proof_map_sha = sys.argv[1:]
for expected_sha in (archive_sha, manifest_sha, proof_map_sha):
    sha(expected_sha)
assert os.getresuid() == os.getresgid() == (0, 0, 0)
archives = {'pocket4': '/home/alex/work/p4-production651-nbd-storage-e6ac-r8.tar.xz',
            'desktop': '/data/p4-production651-nbd-storage-e6ac-r8.tar.xz'}
targets = {'pocket4': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r8',
           'desktop': '/data/p4-production651-nbd-storage-source-e6ac-r8'}
bases = {'pocket4': '/home/alex/work', 'desktop': '/data'}
labels = {'desktop.result', 'desktop.retirement', 'desktop.root', 'offline.inputs', 'offline.result',
          'offline.root', 'server.ready', 'server.result', 'server.retirement', 'server.root',
          'r7.controller.result', 'r7.controller.retirement', 'r7.controller.root',
          'r7.server.result', 'r7.server.retirement', 'r7.server.root', 'r7.public.root'}
archive_ref, raw = read_fixed(archives[host], 262143)
assert archive_ref['sha256'] == archive_sha
entries = {}
with tarfile.open(fileobj=io.BytesIO(raw), mode='r:xz') as archive:
    for member in archive:
        assert member.isfile() and '/' not in member.name and not member.name.startswith('.') and member.size < 65536
        assert member.name not in entries
        with archive.extractfile(member) as stream:
            entries[member.name] = stream.read(65536)
        assert len(entries[member.name]) == member.size
assert hashlib.sha256(entries['SOURCE-MANIFEST.json']).hexdigest() == manifest_sha
manifest = json.loads(entries['SOURCE-MANIFEST.json'])
assert set(entries) == set(manifest['files']) | {'SOURCE-MANIFEST.json'}
for name, expected in manifest['files'].items():
    assert type(expected['bytes']) is int and len(entries[name]) == expected['bytes']
    assert hashlib.sha256(entries[name]).hexdigest() == sha(expected['sha256'])
contract = json.loads(entries['contract.json'])
assert contract['schema'] == 'p4-production651-successor-storage-contract-v2'
assert contract['generation'] == 'e6ac-storage-r8'
sha(contract['nonce'])
assert type(contract['owner_acquisition']) is dict and set(contract['owner_acquisition']) == {'owner', 'record', 'current', 'root_acceptance'}
assert all(type(value) is dict for value in contract['owner_acquisition'].values()), 'actual independent owner slots required before seal writes'
assert contract['p4_source'] == targets['pocket4'] and contract['desktop_source'] == targets['desktop']
assert type(contract['transition_originals']) is dict and set(contract['transition_originals']) == labels
assert pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip() == contract['hosts'][host]['boot']

proof_map_path = pathlib.Path(bases[host]) / 'p4-storage-r8-proof-install-map-e6ac-r1.json'
proof_map_ref, proof_map_raw = read_fixed(proof_map_path, 256 * 1024, owner_mode=(1000, 1000, 0o600))
assert proof_map_ref['sha256'] == proof_map_sha
proof_map = json.loads(proof_map_raw)
assert type(proof_map) is dict and set(proof_map) == {'schema', 'host', 'new_storage_nonce', 'records'}
assert proof_map['schema'] == 'p4-storage-r8-proof-install-map-v1'
assert proof_map['host'] == host and proof_map['new_storage_nonce'] == contract['nonce']
assert type(proof_map['records']) is dict and set(proof_map['records']) == labels
proof_bodies, proof_records, ordinary_refs = {}, {}, [archive_ref, proof_map_ref]
proof_bytes = 0
for label in sorted(labels):
    record, wanted = proof_map['records'][label], contract['transition_originals'][label]
    assert type(record) is dict and set(record) == {'original_host', 'original', 'incoming'}
    assert type(wanted) is dict and set(wanted) == {'host', 'original'}
    assert record['original_host'] == wanted['host'] and wanted['host'] in ('pocket4', 'desktop')
    original, incoming = full_ref(record['original']), full_ref(record['incoming'])
    assert original == full_ref(wanted['original']) and 0 < original['bytes'] <= 2 * 1024**2
    incoming_path = pathlib.Path(bases[host]) / ('p4-storage-r8-proof-incoming-e6ac-r1-' + label + '.json')
    assert incoming['path'] == str(incoming_path)
    assert incoming['identity'][3:6] == [1000, 1000, 1] and stat.S_IMODE(incoming['identity'][2]) == 0o600
    assert incoming['identity'][:2] != original['identity'][:2]
    assert (incoming['bytes'], incoming['sha256']) == (original['bytes'], original['sha256'])
    proof_bytes += incoming['bytes']
    assert proof_bytes <= 16 * 1024**2
    actual, proof_bodies[label] = read_fixed(incoming_path, 2 * 1024**2, incoming, (1000, 1000, 0o600))
    ordinary_refs.append(actual)
    proof_records[label] = {'original_host': wanted['host'], 'original': original, 'incoming': actual}
bookend(ordinary_refs)

# No seal directory or file is created until all seventeen exact inputs pass above.
target = pathlib.Path(targets[host]); target.mkdir(mode=0o755); os.chmod(target, 0o755)
inputs = target / 'inputs'; inputs.mkdir(mode=0o700)
inputs_fd = os.open(inputs, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
try:
    before_inputs = os.fstat(inputs_fd)
    assert stat.S_ISDIR(before_inputs.st_mode) and before_inputs.st_uid == before_inputs.st_gid == 0
    assert f9(before_inputs) == f9(inputs.lstat())
    os.fchmod(inputs_fd, 0o711); os.fsync(inputs_fd)
    after_inputs = os.fstat(inputs_fd)
    assert (after_inputs.st_dev, after_inputs.st_ino) == (before_inputs.st_dev, before_inputs.st_ino)
    assert after_inputs.st_uid == after_inputs.st_gid == 0 and stat.S_IMODE(after_inputs.st_mode) == 0o711
    assert f9(after_inputs) == f9(inputs.lstat())
finally:
    os.close(inputs_fd)
refs = {}
for name, body in entries.items():
    sealed = write_new(target / name, body)
    refs[name] = {key: sealed[key] for key in ('bytes', 'sha256', 'identity')}
for label in sorted(labels):
    sealed = write_new(inputs / (label + '.json'), proof_bodies[label])
    assert sealed['identity'][:2] != proof_records[label]['original']['identity'][:2]
    assert sealed['identity'][:2] != proof_records[label]['incoming']['identity'][:2]
    proof_records[label]['sealed'] = sealed
bookend(ordinary_refs)
receipt = {'schema': 'p4-production651-nbd-source-seal-v1', 'host': host, 'archive_sha256': archive_sha,
           'archive': archive_ref, 'source_manifest_sha256': manifest_sha, 'nonce': contract['nonce'], 'files': refs,
           'proof_map': proof_map_ref, 'transition_proofs': proof_records, 'proof_bytes': proof_bytes,
           'ordinary_input_metadata_bookends_unchanged': True,
           'exports': 0, 'module_loads': 0, 'mounts': 0, 'image_allocation_bytes': 0, 'Android_starts': 0,
           'role_root_created': False, 'mountpoint_created': False, 'storage_started': False}
body = (json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
prepared = write_new(target / 'PREPARED.json', body)
bookend(ordinary_refs)
print(json.dumps({**prepared, 'storage_started': False}, sort_keys=True))
