#!/usr/bin/env python3
"""Wrap an already frozen readback, preserving its entire original closure."""
import datetime,gzip,hashlib,io,json,os,stat,tarfile
from pathlib import Path
BASE=Path('/workspace/scratch/ae1a8cf05419')
SOURCE=BASE/'final-owner-readback'
DEST=BASE/'trillionnium-os-desktop/support/build/evidence/2026-10-17-owner-final-refresh'
ORIGINAL_SUM='3416ac3789de0a29bed99483d89dc91dff4d4c7d45447e2878eedfddf04d3e8f'
def sha(data):return hashlib.sha256(data).hexdigest()
def write(name,obj):(DEST/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
payloads={}
for p in sorted(SOURCE.rglob('*')):
 if p.is_symlink():raise ValueError('symlink in frozen input')
 if p.is_dir():continue
 before=p.stat(follow_symlinks=False)
 fd=os.open(p,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  a=os.fstat(fd)
  if not stat.S_ISREG(a.st_mode) or a!=before:raise ValueError('nonregular/changed source')
  with os.fdopen(fd,'rb',closefd=False) as s:raw=s.read()
  z=os.fstat(fd)
  if z!=a or p.stat(follow_symlinks=False)!=a:raise ValueError('source changed during capture')
 finally:os.close(fd)
 payloads[p.relative_to(SOURCE).as_posix()]=raw
if len(payloads)!=39 or sum(map(len,payloads.values()))!=357755:raise ValueError('frozen inventory differs')
if sha(payloads['SHA256SUMS'])!=ORIGINAL_SUM:raise ValueError('original checksum manifest differs')
expected={}
for line in payloads['SHA256SUMS'].decode().splitlines():
 h,name=line.split('  ',1)
 if name in expected:raise ValueError('duplicate original checksum')
 expected[name]=h
if set(expected)!=set(payloads)-{'SHA256SUMS'}:raise ValueError('original closure incomplete')
for name,h in expected.items():
 if sha(payloads[name])!=h:raise ValueError('original content hash differs: '+name)
DEST.mkdir(mode=0o700,exist_ok=False)
archive=DEST/'raw-readback.tar.gz'
with archive.open('xb') as output:
 with gzip.GzipFile(fileobj=output,mode='wb',filename='',mtime=0,compresslevel=9) as zipped:
  with tarfile.open(fileobj=zipped,mode='w',format=tarfile.USTAR_FORMAT) as tar:
   for name,raw in payloads.items():
    info=tarfile.TarInfo(name);info.size=len(raw);info.mode=0o644;info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0
    tar.addfile(info,io.BytesIO(raw))
if archive.stat().st_size>2*1024*1024:raise ValueError('archive exceeds requested chunk bound')
members=[{'path':name,'bytes':len(raw),'sha256':sha(raw),'mode':0o644} for name,raw in payloads.items()]
write('archive.json',{'schema':1,'path':archive.name,'bytes':archive.stat().st_size,'sha256':sha(archive.read_bytes()),
 'members':39,'original_total_bytes':357755,'original_sha256sums_sha256':ORIGINAL_SUM,
 'container':'USTAR sorted regular members; uid/gid0; empty owner names; mode0644; mtime0; gzip mtime0/empty filename',
 'raw_scope':'Entire original frozen readback, including its unchanged SHA256SUMS, 18 request metadata/results and old local docs/lock.'})
write('members.json',members)
original=json.loads(payloads['review-report.json']);index=json.loads(payloads['local-readback-index.json'])
write('source-bindings.json',{'schema':1,'kind':'Captured readback source bytes, not a new Git checkout or a claim that the current repository equals these historical bytes.',
 'original_directory':str(SOURCE),'original_sha256sums_sha256':ORIGINAL_SUM,
 'source_inventory':index['files'],'source_capture_utc':index['captured_utc'],
 'remote_A01_head_observed':original['remote']['a01_head'],'main_as_PR22_base_observed':original['remote']['main_as_PR22_base'],
 'remote_scope':'Connector-normalized metadata. Run/job status and steps only; no fresh completed-job checkout source binding was established by this last readback.',
 'original_summary_path':'review-report.json','original_summary_sha256':sha(payloads['review-report.json'])})
requests=json.loads(payloads['requests.json'])['requests']
write('summary.json',{'schema':1,'packaged_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'original_readback_window_utc':original['remote_readback_window_utc'],'raw_files':39,'raw_bytes':357755,'requests':len(requests),
 'original_snapshot_not_current_status':True,'later_results_outside_this_package':True,
 'temporal_context':'Original01:52-01:53 reports correctly said the pair/final full22 had no completed frozen result at that observation time. Root subsequently reported actual pair exit0 at01:56 and final22/22, retained in separate later phases. Those are not new executions or verified results of this packaging phase; old pending text must not be presented as the final current aggregate.',
 'remote_at_original_window':original['remote'],
 'package_acceptance':'Original raw closure, source bindings, request timings and bounded historical API/CI facts only. No compiler, installer, Cargo, QEMU, GDB, kernel, owner test or new GitHub query is run.'})
(DEST/'REPORT.md').write_text('''# Final owner readback — bounded historical snapshot

This phase preserves the complete original **39-file /357,755-byte** scratch final-owner-readback. The original SHA256SUMS remains byte-identical, SHA256 `3416ac3789de0a29bed99483d89dc91dff4d4c7d45447e2878eedfddf04d3e8f`. All38 files in that inner checksum closure and the original checksum file are retained in raw-readback.tar.gz. No original raw field, document, report, timestamp or checksum was updated.

The remote observation window is **2026-10-17 01:52:52.607–01:53:47.412 UTC**. Requests.json inside the archive is explicitly a posthoc literal transcription of the18 actual read-only tool names/arguments, using the original captured per-request start/end fields. The connector returned normalized structured data; this is not raw HTTP transport capture. Captured old docs, upstream-lock and frozen phase reports remain historical source bytes. Source-bindings.json does not invent a Git commit for them or claim the final repository still equals them.

At that window A01 PR22 head was d879a9d2 and its host-evidence run38992415807/job117277478013 was queued with null conclusion. A05 PR87/25cbffe6, A06 PR18/57b23ede and A04 PR8/da4107f8 remained open Draft. Issue63 was open with0 comments. Both limited A07 title/head queries returned zero; this is not proof that an external owner or every possible branch is absent. Associated A05 host-contracts success and A06 G0 failure remain host CI metadata. Empty status/run arrays are never interpreted as acceptance.

**Temporal boundary:** the original reports correctly said the final cross-path pair and snapshot full22 lacked completed frozen evidence at that time. Root later reported an actual pair exit0 at01:56 and the final22/22 matrix, with their separate later evidence. This package neither reexecutes nor validates those newer runs. Its old pending statements must not be used as the current final aggregate. Root's consolidated report uses the later pair/matrix receipts. AF_UNIX/KVM/cross-host/immutable-environment and A05/A06/A04/A07 owner boundaries likewise retain their precise source/time scopes, not a blanket claim that all blockers closed.

The archive uses sorted regular USTAR members, mode0644, uid/gid0, empty owner names and mtime0; gzip uses mtime0 and an empty filename. This normalizes container metadata without changing any member payload. It is below2MiB. Members.json binds every original path/size/SHA256; archive.json binds the compressed storage and unchanged original checksum manifest. No executable tool or native payload is installed or run by this wrapper.

Offline verification from the repository root:

```sh
python3 -I support/build/evidence/2026-10-17-owner-final-refresh/verify.py
python3 -I -O support/build/evidence/2026-10-17-owner-final-refresh/verify.py
```

The verifier uses explicit checks, not Python assert. It verifies the full outer checksum inventory, compressed archive/member identities, the exact39-file/38-entry original closure, all18 requests and original timings,15 local document/frozen-report bindings and the bounded PR/issue/A07/CI observations. It performs no extraction, network request, compiler, tool installation, owner test or VM. Later root outcomes are contextual statements outside its acceptance scope.
''')
(DEST/'package-evidence.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps({'destination':str(DEST),'archive_bytes':archive.stat().st_size,'original_files':len(payloads),'requests':len(requests)},indent=2))
