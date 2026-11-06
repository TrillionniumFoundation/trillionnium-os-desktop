import hashlib,os,stat,sys
from pathlib import Path
if sys.argv[1:] != ['--qualify-once','--source-sha256','f8a4fed5618f05be2db375ddc63d3b2bff2e884d6ed0d9468e46bb138e86f03e']:raise SystemExit('PLAN_ONLY: qualification not executed')
p=Path('/home/alex/work/pocket4-builder470-explicit-current-qualification-01-20261106/qualify_current470.py')
for parent in [p.parent,*p.parent.parents]:
 if not stat.S_ISDIR(parent.lstat().st_mode):raise RuntimeError('qualifier source parent differs')
fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
try:
 before=os.fstat(fd)
 if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_uid!=1000 or before.st_gid!=1000 or stat.S_IMODE(before.st_mode)!=0o400 or before.st_size!=72093:raise RuntimeError('qualifier source owner/type/bound differs')
 with os.fdopen(fd,'rb',closefd=False) as stream:raw=stream.read(72094)
 identity=lambda value:(value.st_dev,value.st_ino,value.st_mode,value.st_uid,value.st_gid,value.st_nlink,value.st_size,value.st_mtime_ns,value.st_ctime_ns)
 if identity(before)!=identity(os.fstat(fd)) or identity(before)!=identity(p.lstat()) or len(raw)!=72093 or hashlib.sha256(raw).hexdigest()!='f8a4fed5618f05be2db375ddc63d3b2bff2e884d6ed0d9468e46bb138e86f03e':raise RuntimeError('exact qualifier source changed')
finally:os.close(fd)
scope={'__name__':'__main__','__file__':str(p)}
exec(compile(raw,str(p),'exec'),scope,scope)
