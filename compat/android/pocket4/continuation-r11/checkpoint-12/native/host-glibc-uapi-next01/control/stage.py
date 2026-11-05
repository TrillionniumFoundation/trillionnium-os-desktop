import hashlib,json,os,stat,sys
from pathlib import Path
raw=sys.stdin.buffer.read()
assert len(raw)==715057 and hashlib.sha256(raw).hexdigest()=='dbd75f1e884b5bb89c64f7c7b6e8e91687f4c4fce9fdba051963716d334f0f44'
packet=json.loads(raw)
assert len(packet)==28 and 'compile_tus.py' in packet and 'INPUT_PINS.json' in packet
for name,row in packet.items():
 path=Path(name)
 assert not path.is_absolute() and '..' not in path.parts and str(path)==name
 assert set(row)=={'bytes','sha256','text'}
 data=row['text'].encode()
 assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
root=Path('/home/alex/work/pocket4-native-host-glibc-uapi-tu-control-01-20261105')
for parent in root.parents:assert stat.S_ISDIR(parent.lstat().st_mode)
assert not root.exists() and not root.is_symlink()
os.umask(0o077);root.mkdir(mode=0o700)
source=root/'source';source.mkdir(mode=0o700)
for name,row in packet.items():
 destination=source/name;destination.parent.mkdir(parents=True,exist_ok=True)
 fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as stream:
  stream.write(row['text'].encode());stream.flush();os.fsync(stream.fileno())
sys.argv=[str(source/'compile_tus.py'),'--execute-once']
scope={'__name__':'__main__','__file__':str(source/'compile_tus.py')}
exec(compile(packet['compile_tus.py']['text'],str(source/'compile_tus.py'),'exec'),scope,scope)
