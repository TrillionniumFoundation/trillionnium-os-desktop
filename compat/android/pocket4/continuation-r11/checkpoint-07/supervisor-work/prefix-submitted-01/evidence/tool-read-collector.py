from pathlib import Path
import datetime,errno,hashlib,json,os,stat,subprocess
out=Path('/home/alex/work/pocket4-supervisor-lmkd-lifecycle-r11-work-01/integration-prefix-tool-read-01')
out.mkdir(mode=0o700)
result={'schema':1,'scope':'exact readonly host prefix binary metadata','runtime_actions':0,'namespace_actions':0,'Main_actions':0,'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':{}}
def stable(s):return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_nlink)
for name in ('/usr/bin/ip','/usr/bin/unshare','/usr/bin/python3','/usr/bin/systemctl','/usr/bin/systemd-run'):
 p=Path(name);resolved=p.resolve(strict=True);fd=os.open(resolved,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  before=os.fstat(fd)
  if not stat.S_ISREG(before.st_mode) or before.st_size>32*1024*1024:raise RuntimeError('invalid binary bound '+name)
  h=hashlib.sha256()
  while True:
   block=os.read(fd,65536)
   if not block:break
   h.update(block)
  try:cap=os.getxattr(fd,'security.capability').hex()
  except OSError as e:
   if e.errno not in (errno.ENODATA,errno.ENOTSUP):raise
   cap=None
  if stable(before)!=stable(os.fstat(fd)):raise RuntimeError('binary changed while read')
  row={'path':name,'resolved_path':str(resolved),'path_is_symlink':p.is_symlink(),'sha256':h.hexdigest(),'bytes':before.st_size,'device':before.st_dev,'inode':before.st_ino,'mode':stat.S_IMODE(before.st_mode),'uid':before.st_uid,'gid':before.st_gid,'nlink':before.st_nlink,'capability_hex':cap,'set_id':bool(before.st_mode&0o6000)}
  result['files'][name]=row
 finally:os.close(fd)
for path in ('/usr/bin/systemctl','/usr/bin/systemd-run'):
 p=subprocess.run([path,'--version'],env={'PATH':'/usr/bin:/bin','LANG':'C'},capture_output=True,timeout=5)
 if len(p.stdout)+len(p.stderr)>16384:raise RuntimeError('version output bound')
 result['files'][path]['version']={'exit_code':p.returncode,'stdout':p.stdout.decode(),'stderr':p.stderr.decode()}
result['owned_path_census']={}
for name in ('/run/netns','/home/alex/work/pocket4-relay-prefix-r11-owned'):
 try:
  s=Path(name).lstat();result['owned_path_census'][name]={'exists':True,'directory':stat.S_ISDIR(s.st_mode),'symlink':stat.S_ISLNK(s.st_mode),'mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid,'device':s.st_dev,'inode':s.st_ino}
 except FileNotFoundError:result['owned_path_census'][name]={'exists':False}
result['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
raw=(json.dumps(result,indent=2,sort_keys=True)+'\n').encode()
with (out/'read-result.json').open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
print(json.dumps({'path':str(out/'read-result.json'),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'runtime_actions':0}))
