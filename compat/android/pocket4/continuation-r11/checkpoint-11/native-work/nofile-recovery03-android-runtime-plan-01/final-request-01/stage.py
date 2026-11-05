from pathlib import Path
import hashlib,json,os,stat,sys
assert os.geteuid()==0 and os.getegid()==0 and not sys.flags.optimize
raw=PACKET_RAW.encode('utf-8')
assert hashlib.sha256(raw).hexdigest()==PACKET_SHA
files=json.loads(raw)
assert set(files)=={'coordinator.py','entry-review.json','CASE_PLAN.json'}
root=Path(REMOTE_SOURCE)
assert not root.exists() and not root.is_symlink()
for parent in root.parents:
 assert stat.S_ISDIR(parent.lstat().st_mode)
for name,row in files.items():
 value=row['text'].encode('utf-8')
 assert len(value)==row['bytes'] and hashlib.sha256(value).hexdigest()==row['sha256']
compile(files['coordinator.py']['text'],'coordinator.py','exec')
os.umask(0o077);root.mkdir(mode=0o700)
for name,row in files.items():
 fd=os.open(root/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
 with os.fdopen(fd,'wb') as stream:
  stream.write(row['text'].encode('utf-8'));stream.flush();os.fsync(stream.fileno())
os.execv('/usr/bin/python3',['/usr/bin/python3','-I',str(root/'coordinator.py'),'--execute-once'])
