#!/usr/bin/python3 -I
"""Copy only retained Core13 diagnostics/command receipts; no Android or UI calls."""
from pathlib import Path
import gzip, hashlib, json, os, re, stat

SOURCE = Path('/home/alex/work/pocket4-calendar-accept-core-20261105-r12-13')
OUT = Path('/home/alex/work/pocket4-calendar-core13-saved-diagnostics-20261105-r12-01')
RESULT_SHA = 'fb7f0382a2ae437cb7e74886eb76dce3fc08027a8d47a93b394b7bfdf5025f4c'

def digest(data): return hashlib.sha256(data).hexdigest()

def read(path, maximum):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NOATIME)
    try:
        before = os.fstat(fd)
        assert stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1
        assert 0 < before.st_size <= maximum
        chunks = []
        while True:
            part = os.read(fd, min(65536, maximum + 1 - sum(map(len, chunks))))
            if not part: break
            chunks.append(part)
            assert sum(map(len, chunks)) <= maximum
        raw = b''.join(chunks)
        after = os.fstat(fd)
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        assert all(getattr(before, k) == getattr(after, k) for k in fields)
        assert len(raw) == before.st_size
        return raw, {'bytes':len(raw), 'sha256':digest(raw), 'metadata':{k:getattr(before,k) for k in fields}}
    finally: os.close(fd)

def create(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640)
    try:
        os.fchown(fd, 0, 1000); os.fchmod(fd, 0o640)
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(raw); stream.flush(); os.fsync(fd)
    finally: os.close(fd)

raw, result_meta = read(SOURCE/'result.json', 65536)
assert digest(raw) == RESULT_SHA
result = json.loads(raw)
assert result['state'] == 'FAILED' and result['final_check_error'] == 'Stop:CRASH_OBSERVATION_WINDOW_TRUNCATED'
assert result['business_scope_completed'] and not result['ui_pending'] and result['business_pending'] is None
assert result['task_set_restored'] and not any(result['final_counts'].values())
saved = {}
for name in ('001-before.json', '002-after.json'):
    content, meta = read(SOURCE/'diagnostics'/name, 4*1024*1024)
    saved['diagnostics/'+name] = {'source':meta, 'value':json.loads(content)}
names = sorted((p.name for p in (SOURCE/'commands').iterdir()
               if re.fullmatch(r'[0-9]+-[a-z0-9-]+\.result\.json', p.name)),
               key=lambda name: int(name.split('-', 1)[0]))
assert 8 <= len(names) <= 4096
for name in names[-8:]:
    content, meta = read(SOURCE/'commands'/name, 131072)
    saved['commands/'+name] = {'source':meta, 'value':json.loads(content)}
again, _ = read(SOURCE/'result.json', 65536)
assert again == raw
os.umask(0o077); OUT.mkdir(mode=0o750)
os.chown(OUT, 0, 1000); os.chmod(OUT, 0o750)
payload = json.dumps({'schema':'calendar-core13-retained-diagnostics/v1',
    'original_result':result_meta,'source_root':str(SOURCE), 'files':saved,
    'new_android_commands':0,'ui_inputs':0,'provider_mutations':0,
    'existing_source_files_read_with_noatime':True}, sort_keys=True, indent=2).encode()+b'\n'
compressed = gzip.compress(payload, mtime=0)
create(OUT/'saved.json.gz', compressed)
summary = {'state':'RETAINED_CORE13_DIAGNOSTICS_EXPORTED',
    'path':str(OUT/'saved.json.gz'), 'bytes':len(compressed), 'sha256':digest(compressed),
    'uncompressed_bytes':len(payload),'uncompressed_sha256':digest(payload),
    'source_result_sha256':RESULT_SHA,'new_android_commands':0,'ui_inputs':0,'provider_mutations':0,
    'files':{name:entry['source'] for name,entry in saved.items()}}
create(OUT/'summary.json', json.dumps(summary,sort_keys=True,indent=2).encode()+b'\n')
print(json.dumps(summary,sort_keys=True),flush=True)
