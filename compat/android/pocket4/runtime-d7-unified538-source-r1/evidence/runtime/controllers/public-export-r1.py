import os, json, hashlib, stat, gzip, tarfile, io, time
from pathlib import Path
R = Path('/data/pocket4-runtime-d7-unified538-20261113-e2a3-r1')
Q = R / 'independent-retirement-r1'
os.umask(0o077)
assert os.getuid() == os.getgid() == 1000
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == '14f92beb-43c6-4786-839e-b57307ae8048'
os.sched_setaffinity(0, {8, 9})
def f9(s):
    return [getattr(s, k) for k in ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')]
def read(path, expected=None):
    path = Path(path)
    assert path.is_absolute() and path.resolve() == path
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        s = os.fstat(fd)
        assert stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_size <= 32 * 1024 * 1024
        with os.fdopen(os.dup(fd), 'rb') as stream: raw = stream.read()
        assert len(raw) == s.st_size and f9(s) == f9(os.fstat(fd)) == f9(path.lstat())
        row = {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'identity': f9(s)}
        if expected: assert all(row[k] == value for k, value in expected.items())
        return raw, row
    finally: os.close(fd)
def save(path, obj):
    with path.open('x') as stream:
        json.dump(obj, stream, sort_keys=True, indent=2); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    return read(path)[1]
raw, rr = read(Q / 'RESULT.json', {'bytes': 7360, 'sha256': 'f64c29579d3c4b60a52201a8c8b6e9768119ce29f08e4b16cbdf9df24991ecdd'})
retired = json.loads(raw)
assert retired['state'] == 'ALL289_ACTUAL_ORDINARY_TESTS_FOUR_FRESH_RELEASES_AND_ALL3152_SOURCE_FILES_INDEPENDENTLY_RETIRED' and not retired['errors']
assert retired['all1595_candidate_F9_Gitblobs_modes_preserved'] is True
directory = Path('/home/qian-qi/.local/state/hepta-runtime-mac-worker/jobs/1a1d7446f5d-392-a3a')
docs, refs = {}, {}
for name in ('request', 'started', 'exit'):
    raw, refs[name] = read(directory / (name + '.json')); docs[name] = json.loads(raw)
    assert docs[name]['job_id'] == '1a1d7446f5d-392-a3a' and docs[name]['launch_nonce'] == '3b8023ded059ee202dfb75adc5f31ea1'
assert docs['request']['request_digest'] == '8073bb7665c7a8964fa6cde2d09fe644de7f0bbf18e44c59bd09bcce51f50ea0'
terminal = docs['exit']
assert terminal['exit_code'] == 0 and terminal['at_unix_ms'] == 1794612952590
assert terminal['cancelled'] is False and terminal['timed_out'] is False
assert terminal['output_complete'] is True and terminal['output_durable'] is True
for side, count in [('stdout', 764), ('stderr', 0)]:
    assert terminal['log_bytes'][side] == {'seen': count, 'stored': count}
    assert terminal['log_errors'][side] is None and terminal['log_synced'][side] is True and terminal['log_truncated'][side] is False
pids = {retired['reader_pid'], docs['started']['supervisor_pid']}
for pid in pids:
    try: fd = os.pidfd_open(pid)
    except ProcessLookupError: pass
    else: os.close(fd); raise AssertionError(('reader PID remains', pid))
assert not os.path.lexists(retired['reader_cgroup'])
reader = {'schema': 'runtime-d7-independent-reader-retirement-v1', 'at_ns': time.time_ns(),
          'actual_H_terminal_verified': refs, 'original_PIDs_fresh_ESRCH': sorted(pids),
          'cgroup_absent': retired['reader_cgroup'], 'runtime_qualified': False, 'production_ready': False}
reader_ref = save(Q / 'READER-RETIREMENT.json', reader)
raw, mr = read(Q / 'PUBLIC-PACKET-MANIFEST.json', {'bytes': 28395, 'sha256': '8ee8c1cfe1b94c383a5362bf6821ddd74ffa34d4cb13859b44e92e28a7337950'})
members = json.loads(raw)['members']
members['independent/READER-RETIREMENT.json'] = reader_ref
members['independent/PUBLIC-PACKET-MANIFEST.json'] = mr
for name, value in refs.items(): members['durable/independent-' + name + '.json'] = value
members['controllers/public-export-r1.py'] = read(Path(__file__))[1]
contents = {}
for name, expected in members.items():
    assert not name.startswith('/') and '..' not in Path(name).parts
    contents[name] = read(expected['path'], expected)[0]
export = {'schema': 'runtime-d7-byte-preserving-public-evidence-export-v1', 'member_count': len(members),
          'members': members, 'binary_bodies_included': False, 'source_bodies_included': False,
          'cache_bodies_included': False, 'original_data_body_reads': 0, 'production_ready': False}
er = save(Q / 'EXPORT-MANIFEST.json', export)
contents['EXPORT-MANIFEST.json'] = read(Q / 'EXPORT-MANIFEST.json', er)[0]
archive = Q / 'D7-PUBLIC-EVIDENCE-r1.tar.gz'
with archive.open('xb') as stream:
    with gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0) as compressed:
        with tarfile.open(mode='w', fileobj=compressed, format=tarfile.PAX_FORMAT) as tar:
            for name, raw in sorted(contents.items()):
                info = tarfile.TarInfo(name); info.size = len(raw); info.mode = 0o600; info.mtime = 0
                tar.addfile(info, io.BytesIO(raw))
    stream.flush(); os.fsync(stream.fileno())
for expected in members.values(): read(expected['path'], expected)
result = {'state': 'COMPLETE_PUBLIC_D7_EVIDENCE_EXPORTED', 'archive': read(archive)[1],
          'export_manifest': er, 'reader_retirement': reader_ref, 'archive_members': len(contents),
          'runtime_qualified': False, 'production_ready': False}
result_ref = save(Q / 'EXPORT-RESULT.json', result)
print(json.dumps(dict(result, result=result_ref)), flush=True)
