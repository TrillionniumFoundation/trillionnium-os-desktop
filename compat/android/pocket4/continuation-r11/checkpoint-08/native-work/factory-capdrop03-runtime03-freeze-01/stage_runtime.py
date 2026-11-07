import os,sys,hashlib
from pathlib import Path
expected='e76e35332951ba72e68bc59e7d4849ec05c06233c5db95d8d50d74ecfefe0628'
source_path=Path('/home/alex/work/pocket4-factory-v2-host-runtime-source-03/controller.py')
expected_args=['--execute','--out','/home/alex/work/pocket4-factory-v2-host-runtime-03']
if sys.argv[1:] != expected_args: raise RuntimeError('exact owned host-only runtime arguments required')
raw=sys.stdin.buffer.read()
if hashlib.sha256(raw).hexdigest()!=expected: raise RuntimeError('frozen runtime source changed')
compile(raw,str(source_path),'exec')
os.umask(0o077)
source_path.parent.mkdir(mode=0o700)
fd=os.open(source_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o400)
with os.fdopen(fd,'wb') as stream:
 stream.write(raw);stream.flush();os.fsync(stream.fileno())
if source_path.read_bytes()!=raw: raise RuntimeError('new root-owned source differs')
sys.argv=[str(source_path),*expected_args]
scope={'__name__':'__main__','__file__':str(source_path)}
exec(compile(raw,str(source_path),'exec'),scope,scope)
