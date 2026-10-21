#!/usr/bin/env python3
"""Preserve the unexpected manifest under the native workspace lock."""
import datetime,fcntl,hashlib,json,os,pathlib,stat
repo=pathlib.Path('/workspace/scratch/d7da9e7650f0/a01-mainf9')
out=repo/'support/build/out/2026-10-19-mainf9/failures/post-boot-manifest'
out.mkdir(parents=True,exist_ok=False)
source=repo/'kernel/asterinas/kernel/OSDK.toml'
destination=out/'unexpected-OSDK.toml'
def digest(b):return hashlib.sha256(b).hexdigest()
def info(s):return {k:getattr(s,k) for k in ('st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns')}
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
with (repo/'support/build/out-kernel.lock').open('a+b') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW)
 try:
  before=os.fstat(fd);named=os.lstat(source)
  assert stat.S_ISREG(before.st_mode) and info(before)==info(named)
  assert before.st_ino==19777 and before.st_size==1019
  raw=os.read(fd,before.st_size+1)
  assert digest(raw)=='1ff39174c39411f8b9a7fd328f762268e62d88521b43ebbde384d03d7d9a9f9f'
  assert info(before)==info(os.fstat(fd))==info(os.lstat(source))
  assert not destination.exists()
  record={'started_at':now(),'reason':'entry reappeared after successful boot, observed before and after passing ktests; preserve it without modifying any build guard','source':str(source),'destination':str(destination),'before':info(before),'sha256':digest(raw),'lock_path':str(repo/'support/build/out-kernel.lock'),'lock_inode':os.fstat(lock.fileno()).st_ino,'exclusive_nonblocking_lock':True,'operation':'os.rename into exclusive new evidence directory; no unlink or overwrite','writer_identified':False}
  (out/'quarantine.json').write_text(json.dumps(record,indent=2)+'\n')
  os.rename(source,destination)
  after=os.lstat(destination)
  assert (before.st_dev,before.st_ino)==(after.st_dev,after.st_ino)
  assert destination.read_bytes()==raw
  record.update(finished_at=now(),after=info(after),source_absent_after=not source.exists(),bytes_equal=True)
  (out/'quarantine.json').write_text(json.dumps(record,indent=2)+'\n')
  print(json.dumps(record,indent=2))
 finally:os.close(fd)
