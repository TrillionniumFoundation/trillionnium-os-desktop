import hashlib,json,os,stat,sys
from pathlib import Path
raw=sys.stdin.buffer.read()
assert len(raw)==365563 and hashlib.sha256(raw).hexdigest()=='f4766fa1c74d04c53512013da819e0899ba469266712eaad8be1c1ccb62a76df'
packet=json.loads(raw)
assert set(packet)=={'run_control.py','preimage-runtime.cc','candidate-runtime.cc','bridge-full.cc','art-interface-full.cc','lifecycle_fixture.cc'}
for name,row in packet.items():
 assert set(row)=={'bytes','sha256','text'} and '/' not in name
 data=row['text'].encode()
 assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
root=Path('/home/alex/work/pocket4-art-prefork-quiesce-order-control-01-20261105')
for parent in root.parents:
 assert stat.S_ISDIR(parent.lstat().st_mode)
assert not root.exists() and not root.is_symlink()
os.umask(0o077)
root.mkdir(mode=0o700)
source=root/'source';source.mkdir(mode=0o700)
for name,row in packet.items():
 fd=os.open(source/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as stream:
  stream.write(row['text'].encode());stream.flush();os.fsync(stream.fileno())
sys.argv=[str(source/'run_control.py'),'--execute-once']
scope={'__name__':'__main__','__file__':str(source/'run_control.py')}
exec(compile(packet['run_control.py']['text'],str(source/'run_control.py'),'exec'),scope,scope)
