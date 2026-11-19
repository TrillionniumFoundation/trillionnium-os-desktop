import os,sys,json,hashlib,gzip,tarfile,resource,stat
from pathlib import Path
root=Path('/home/qq/work/p4-szzc-current-source-5cd1-20261119-r1');rows=json.loads(sys.argv[1]);assert os.getuid()==1000 and os.sched_getaffinity(0)=={31}
resource.setrlimit(resource.RLIMIT_AS,(96*1024*1024,96*1024*1024));resource.setrlimit(resource.RLIMIT_CPU,(30,30));resource.setrlimit(resource.RLIMIT_FSIZE,(8*1024*1024,8*1024*1024));resource.setrlimit(resource.RLIMIT_CORE,(0,0));os.umask(0o077)
assert len(rows)==8 and {r['name'] for r in rows}=={'source-receipt.json','szzc-badging.stdout','szzc-badging.stderr','szzc-manifest.stdout','szzc-manifest.stderr','szzc-signature.stdout','szzc-signature.stderr','sdk37-preparation-receipt.json'}
def f9(s):return tuple(getattr(s,k) for k in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns'))
held=[]
try:
 for r in rows:
  p=Path(r['path']);assert p.is_relative_to(root/'qualification-r2') and p.resolve()==p
  fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW);s=os.fstat(fd);held.append((fd,p,s,r))
  assert stat.S_ISREG(s.st_mode) and s.st_uid==1000 and s.st_nlink==1 and s.st_size==r['bytes'] and f9(s)==f9(p.lstat())
  b=os.pread(fd,r['bytes']+1,0);assert len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256']
 out=root/'source-evidence-transfer.tar.gz';fd=os.open(out,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as dst:
  with gzip.GzipFile(filename='',fileobj=dst,mode='wb',mtime=0,compresslevel=6) as gz:
   with tarfile.open(fileobj=gz,mode='w|') as tar:
    for source_fd,p,s,r in held:
     info=tarfile.TarInfo(r['name']);info.size=r['bytes'];info.mode=0o600;info.mtime=0
     with os.fdopen(os.dup(source_fd),'rb') as src:src.seek(0);tar.addfile(info,src)
  dst.flush();os.fsync(dst.fileno())
 for source_fd,p,s,r in held:
  assert f9(os.fstat(source_fd))==f9(p.lstat())==f9(s) and hashlib.sha256(os.pread(source_fd,r['bytes']+1,0)).hexdigest()==r['sha256']
 b=out.read_bytes();print(json.dumps({'path':str(out),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'input_count':len(rows),'inputs_unchanged':True,'APK_bytes_read':0}),flush=True)
finally:
 for fd,p,s,r in held:os.close(fd)
