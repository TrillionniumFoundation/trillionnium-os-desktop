import os,stat,json,hashlib,gzip,base64,time
from pathlib import Path
assert os.getuid()==os.geteuid()==0
root=Path('/home/alex/work/pocket4-bilibili-owned-inspect-01')
flow=Path('/home/alex/work/pocket4-bilibili-owned-qa-r1-flow-07a6a4bf28a23f7b1f8f2e8be7923646')
specs=[
(root/'result.json',65536,6270,'dbaaa8be658655ff7a4693c4d0da34c72d813768c28cd6082d41382027abf864'),
(root/'stage-result.json',65536,1767,'d87f929cd7c8943e583591bf150e3c3a5452b0ccb80097070ef6df2581021dea'),
(flow/'steps/launch-01/result.json',65536,None,None),
(flow/'steps/inspect-01/result.json',262144,None,None),
(flow/'steps/cleanup-01/result.json',65536,None,None),
(root/'evidence/02-launch.result.json',65536,None,None),
(root/'evidence/03-inspect.result.json',65536,None,None),
(root/'evidence/04-cleanup.result.json',65536,None,None)]
report={'schema':1,'scope':'eight fixed owned launch-inspect01 summary evidence paths only; no raw UI tree or stack','uid':os.geteuid(),'files':[],'source_changes':0,'Android_actions':0,'Main_actions':0,'no_retry':True}
def ident(s):return [s.st_dev,s.st_ino,s.st_mode,s.st_nlink,s.st_uid,s.st_gid,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
for path,limit,size,digest in specs:
 row={'path':str(path),'limit':limit}
 fd=None
 try:
  fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
  before=os.fstat(fd)
  assert stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size<=limit
  parts=[];n=0
  while True:
   part=os.read(fd,min(65536,limit+1-n))
   if not part:break
   parts.append(part);n+=len(part);assert n<=limit
  data=b''.join(parts)
  assert ident(before)==ident(os.fstat(fd))==ident(path.lstat()) and n==before.st_size
  actual=hashlib.sha256(data).hexdigest()
  assert size is None or n==size
  assert digest is None or actual==digest
  row.update(state='HELD_READ_VERIFIED',bytes=n,sha256=actual,identity=ident(before),text=data.decode('utf-8'))
 except Exception as error:
  row.update(state='READ_FAILED',error=type(error).__name__+': '+str(error))
 finally:
  if fd is not None:os.close(fd)
 report['files'].append(row)
encoded=(json.dumps(report,sort_keys=True,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
assert len(encoded)<=1048576
compressed=gzip.compress(encoded,mtime=0)
print(json.dumps({'schema':1,'encoding':'gzip+base64','bytes':len(encoded),'sha256':hashlib.sha256(encoded).hexdigest(),'data':base64.b64encode(compressed).decode('ascii')}),flush=True)
