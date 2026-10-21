from pathlib import Path
import datetime,fcntl,hashlib,json,os,stat,subprocess,tempfile
R=Path('/workspace/scratch/d7da9e7650f0/trillionnium-os-desktop');D=Path('/tmp/a01-main355-publish/late-manifest');src=R/'kernel/asterinas/kernel/OSDK.toml'
observed=json.loads((D/'observation.json').read_text())
record={'started_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'action':'Reversible manual quarantine of a recorded untracked build manifest while holding the shared native-build lock. No unlink, overwrite, kernel source edit or policy change.','source_path':str(src),'ownership_of_late_writer':'unknown','root_cause_fixed':False}
with (R/'support/build/out-kernel.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 record['native_workspace_lock_acquired']=True
 fd=os.open(src,os.O_RDONLY|os.O_NOFOLLOW)
 try:
  s=os.fstat(fd);named=os.lstat(src)
  assert stat.S_ISREG(s.st_mode) and (s.st_dev,s.st_ino)==(named.st_dev,named.st_ino)==(observed['stat']['st_dev'],observed['stat']['st_ino'])
  with os.fdopen(os.dup(fd),'rb') as f:raw=f.read()
  assert hashlib.sha256(raw).hexdigest()==observed['sha256']
  dest_dir=Path(tempfile.mkdtemp(prefix='late-manifest-',dir=R/'support/build/out/2026-10-18-main355-followup'))
  dest=dest_dir/'OSDK.toml'
  os.rename(src,dest)
  moved=dest.stat()
  assert (moved.st_dev,moved.st_ino)==(s.st_dev,s.st_ino)
  assert dest.read_bytes()==raw and not src.exists()
  record.update(destination_path=str(dest),same_inode_preserved=True,same_bytes_preserved=True,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),source_path_absent_after_move=True)
 finally:os.close(fd)
 record['git_status_after_move']=subprocess.check_output(['git','status','--porcelain'],cwd=R,text=True)
 record['finished_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
 record['passed']=not record['git_status_after_move']
(D/'quarantine.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
