"""One-shot operator for the six explicitly retired local Audio drafts.

This temporary operator is not a Droidloom runtime tool. It never opens /proc,
operates on a remote host, or traverses any target not in the pinned manifest.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys

ROOT = Path('/workspace/scratch/2840a678aeda/audio-sdk-closeout')
MANIFEST = ROOT / 'r6-cleanup-manifest.json'
MANIFEST_SHA = '05102c3fb05e9b2d8adde56cc68acd165b7a8c75dfa978715c76793b7f32bf8a'
OUT = Path('/workspace/scratch/2840a678aeda/r6-review/local-six-retirement-r3')
TARGETS = (
    'qpr1-audit/stage_audio_vendor_candidate.py',
    'qpr1-audit/test_stage_audio_vendor_candidate.py',
    'qpr1-audit/__pycache__', '__pycache__', 'full-sdk-r1', 'full-sdk-r2',
)


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def ident(s):
    return [s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid,
            s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def inode(s):
    return [s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid]


def read_fd(fd):
    os.lseek(fd, 0, os.SEEK_SET)
    a = os.fstat(fd)
    chunks = []
    while True:
        b = os.read(fd, 1024 * 1024)
        if not b:
            break
        chunks.append(b)
    z = os.fstat(fd)
    assert ident(a) == ident(z), 'file changed while held'
    return b''.join(chunks), z


def read_pin(p, expected):
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        b, s = read_fd(fd)
        assert stat.S_ISREG(s.st_mode)
        assert hashlib.sha256(b).hexdigest() == expected['sha256'], str(p)
        if 'bytes' in expected:
            assert len(b) == expected['bytes'], str(p)
        return {'path': str(p), 'bytes': len(b), 'sha256': expected['sha256'],
                'identity': ident(s)}
    finally:
        os.close(fd)


def write_new(name, value):
    b = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode()
    fd = os.open(OUT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as f:
            f.write(b)
            f.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(outfd)
    return {'path': str(OUT / name), 'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}


assert sys.argv == [sys.argv[0], '--execute'], 'explicit one-shot execution required'
mb = MANIFEST.read_bytes()
assert len(mb) == 21853 and hashlib.sha256(mb).hexdigest() == MANIFEST_SHA
m = json.loads(mb)
assert m['root'] == str(ROOT)
assert tuple(x['relative_path'] for x in m['exact_targets']) == TARGETS
assert len(m['files']) == 17 and len(m['directories']) == 5
files = {x['relative_path']: x for x in m['files']}
dirs = set(m['directories'])
assert len(files) == 17 and len(dirs) == 5
entries = set(files) | dirs
assert len(entries) == 22
for p in entries:
    q = PurePosixPath(p)
    assert not q.is_absolute() and '..' not in q.parts and '.' not in q.parts
    assert any(p == t or p.startswith(t + '/') for t in TARGETS)

# All six original writers have completed; no agent is modifying these targets.
# Source/result/terminal evidence is content-pinned; old inode values are unused.
retained = []
rb = m['retention_boundaries']
pins = m['source_evidence'] + rb['retained_qpr1_files'] + rb['both_frozen_review_indexes']
pins += rb['preserved_old_cleanup_records']
pins += [x['manifest'] for x in rb['protected_publication_and_native_manifests']]
pins += [{'path': rb['native_external_audit']['selected_stock_dex_root'] + '/INDEX.json',
          'sha256': rb['native_external_audit']['selected_stock_dex_index_sha256']}]
for p in pins:
    assert not any(p['path'] == str(ROOT / t) or p['path'].startswith(str(ROOT / t) + '/') for t in TARGETS)
    retained.append(read_pin(p['path'], p))

OUT.mkdir(mode=0o700)
outfd = os.open(OUT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
parentfd = os.open(OUT.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
os.fsync(parentfd)
os.close(parentfd)
held_dirs = {}
held_files = {}
directory_before = {}
file_before = {}
removed = []
result = {'schema': 'pocket4-root-exact-six-local-retirement-r3', 'started_utc': utc(),
          'manifest_sha256': MANIFEST_SHA, 'historical_identity_reused': False,
          'proc_read_attempted': False, 'remote_mutations': 0,
          'all_old_generation_cleanup_complete': False, 'space_reclaimed_claimed': False,
          'independent_absence_pending': True, 'cleanup_complete': False}
journalfd = os.open(OUT / 'JOURNAL.jsonl', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
try:
    held_dirs['.'] = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    directory_before['.'] = ident(os.fstat(held_dirs['.']))
    all_dirs = dirs | {'qpr1-audit'}
    for p in sorted(all_dirs, key=lambda x: (len(PurePosixPath(x).parts), x)):
        q = PurePosixPath(p)
        fd = os.open(q.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                     dir_fd=held_dirs[str(q.parent)])
        s = os.fstat(fd)
        assert s.st_dev == directory_before['.'][0] and s.st_uid == os.geteuid()
        assert ident(s) == ident(os.stat(q.name, dir_fd=held_dirs[str(q.parent)], follow_symlinks=False))
        held_dirs[p] = fd
        directory_before[p] = ident(s)
    for p in sorted(dirs):
        expected = {PurePosixPath(e).name for e in entries if str(PurePosixPath(e).parent) == p}
        assert set(os.listdir(held_dirs[p])) == expected, ('unexpected directory member', p)
    for p, pin in sorted(files.items()):
        q = PurePosixPath(p)
        fd = os.open(q.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                     dir_fd=held_dirs[str(q.parent)])
        b, s = read_fd(fd)
        assert stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_uid == os.geteuid()
        assert s.st_dev == directory_before['.'][0]
        assert len(b) == pin['bytes'] and hashlib.sha256(b).hexdigest() == pin['sha256'], p
        assert ident(s) == ident(os.stat(q.name, dir_fd=held_dirs[str(q.parent)], follow_symlinks=False))
        held_files[p] = fd
        file_before[p] = ident(s)
    result['preflight'] = write_new('PREFLIGHT.json', {
        'observed_utc': utc(), 'manifest_sha256': MANIFEST_SHA,
        'exact_targets': list(TARGETS), 'file_identities': file_before,
        'directory_identities': directory_before, 'retained_before': retained,
        'fresh_membership_size_and_hashes_passed': True,
        'old_deletion_then_reappearance_preserved_as_failure': True,
        'logical_file_bytes': sum(x['bytes'] for x in files.values()),
        'activity_basis': m['own_activity_basis'],
        'current_activity': 'Root, Audio, Native and Apps have frozen all six target paths; full controls use separate owner roots.'})
    # Check all path bindings again immediately before the first mutation.
    for p, s in directory_before.items():
        if p == '.':
            assert ident(os.stat(ROOT, follow_symlinks=False)) == s
        else:
            q = PurePosixPath(p)
            assert ident(os.stat(q.name, dir_fd=held_dirs[str(q.parent)], follow_symlinks=False)) == s
    for p, s in file_before.items():
        q = PurePosixPath(p)
        assert ident(os.fstat(held_files[p])) == s
        assert ident(os.stat(q.name, dir_fd=held_dirs[str(q.parent)], follow_symlinks=False)) == s
    for p in sorted(files):
        q = PurePosixPath(p)
        dfd = held_dirs[str(q.parent)]
        assert ident(os.fstat(held_files[p])) == file_before[p]
        assert ident(os.stat(q.name, dir_fd=dfd, follow_symlinks=False)) == file_before[p]
        os.unlink(q.name, dir_fd=dfd)
        os.fsync(dfd)
        item = {'utc': utc(), 'operation': 'unlink', 'relative_path': p, 'identity': file_before[p]}
        removed.append(item)
        os.write(journalfd, (json.dumps(item, sort_keys=True) + '\n').encode())
        os.fsync(journalfd)
    for p in sorted(dirs, key=lambda x: (-len(PurePosixPath(x).parts), x)):
        q = PurePosixPath(p)
        dfd = held_dirs[str(q.parent)]
        assert inode(os.fstat(held_dirs[p])) == directory_before[p][:5]
        assert inode(os.stat(q.name, dir_fd=dfd, follow_symlinks=False)) == directory_before[p][:5]
        assert not os.listdir(held_dirs[p])
        os.rmdir(q.name, dir_fd=dfd)
        os.fsync(dfd)
        item = {'utc': utc(), 'operation': 'rmdir', 'relative_path': p, 'identity': directory_before[p][:5]}
        removed.append(item)
        os.write(journalfd, (json.dumps(item, sort_keys=True) + '\n').encode())
        os.fsync(journalfd)
    for p in TARGETS:
        q = PurePosixPath(p)
        try:
            os.stat(q.name, dir_fd=held_dirs[str(q.parent)], follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError(('target reappeared during operation', p))
    after = [read_pin(p['path'], p) for p in pins]
    assert after == retained
    result.update(state='SIX_EXACT_PATHS_UNLINKED_INDEPENDENT_ABSENCE_PENDING',
                  same_call_absent_count=6, retained_exactly_unchanged=True,
                  removed_file_names=17, removed_directories=5,
                  logical_file_bytes=379127)
except BaseException as e:
    result.update(state='FAILED_OR_PARTIAL', error=repr(e))
    raise
finally:
    result['ended_utc'] = utc()
    result['removed_entries'] = removed
    receipt = write_new('RESULT.json', result)
    for fd in held_files.values():
        os.close(fd)
    for fd in held_dirs.values():
        os.close(fd)
    os.close(journalfd)
    os.close(outfd)
    print(json.dumps({'result': receipt, 'state': result.get('state'),
                      'removed_entries': len(removed), 'cleanup_complete': False,
                      'independent_absence_pending': True}, sort_keys=True))
