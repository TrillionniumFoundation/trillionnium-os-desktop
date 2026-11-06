import hashlib,os,stat,sys
from pathlib import Path
if sys.argv[1:] != ['--execute-once']:raise SystemExit('PLAN_ONLY: compiler not invoked')
p=Path('/home/alex/work/pocket4-native-typed-ingress-builder470-systemui-provider-compile-02-20261106/compile_builder470.py')
for q in [p.parent,*p.parent.parents]:
 if not stat.S_ISDIR(q.lstat().st_mode):raise RuntimeError('compile source parent differs')
fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
try:
 before=os.fstat(fd)
 if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_size!=32863:raise RuntimeError('compile source type/bound differs')
 with os.fdopen(fd,'rb',closefd=False) as f:raw=f.read(32864)
 identity=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
 if identity(before)!=identity(os.fstat(fd)) or identity(before)!=identity(p.lstat()) or len(raw)!=32863 or hashlib.sha256(raw).hexdigest()!='5d66d26127cfb01ec09a83536ff4f4fdfb0782500cbcbfb2ec0a7b0288ea89d7':raise RuntimeError('compile source changed')
finally:os.close(fd)
scope={'__name__':'__main__','__file__':str(p)};exec(compile(raw,str(p),'exec'),scope,scope)
