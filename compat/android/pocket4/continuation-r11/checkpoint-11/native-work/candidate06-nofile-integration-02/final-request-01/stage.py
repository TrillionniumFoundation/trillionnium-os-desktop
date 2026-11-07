PACKET_SHA='8e6a5797241ae9e92960dbd6e63bf1bccac09a9931609252fbafae1ec8ef1c8f'
REMOTE_ROOT='/home/alex/work/pocket4-candidate06-nofile-composition-source-01-20261105'
EXPECTED_NAMES=['compose.py', 'references/base-source-contract.py', 'references/runtime-coordinator.py', 'proof/android-coordinator-result.json', 'proof/android-build-result.json', 'proof/host-result.json', 'CASE_PLAN.json', 'delta/kernel_api/proc_maps_raw_metadata_owner.cc', 'delta/kernel_api/include/berberis/kernel_api/proc_maps_raw_metadata_owner.h', 'delta/kernel_api/include/berberis/kernel_api/proc_maps_provenance.h']
COMPOSER_SHA='b489e8ac7353c09c90f7c2f65b0b53c10cd0619c13308add7653dec56ba8d642'
import hashlib,json,os,stat,sys
from pathlib import Path,PurePosixPath
raw=sys.stdin.buffer.read(1048577)
assert len(raw)<=1048576 and hashlib.sha256(raw).hexdigest()==PACKET_SHA
packet=json.loads(raw);assert packet['schema']==1
assert os.getuid()==os.geteuid()==1000
root=Path(REMOTE_ROOT)
for path in [root,*root.parents]:
 if path.exists() or path.is_symlink():assert stat.S_ISDIR(path.lstat().st_mode)
assert not root.exists() and [row['path'] for row in packet['files']]==EXPECTED_NAMES
for row in packet['files']:
 relative=PurePosixPath(row['path']);assert relative.parts and not relative.is_absolute() and all(x not in ('','.','..') for x in relative.parts)
 value=row['content'].encode();assert len(value)==row['bytes'] and hashlib.sha256(value).hexdigest()==row['sha256']
assert packet['files'][0]['sha256']==COMPOSER_SHA
os.umask(0o077);root.mkdir(mode=0o700)
for row in packet['files']:
 path=root/row['path'];path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o444)
 with os.fdopen(fd,'wb') as stream:
  value=row['content'].encode();assert stream.write(value)==len(value);stream.flush();os.fsync(stream.fileno())
 assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
os.execv('/usr/bin/python3',['/usr/bin/python3','-I',str(root/'compose.py'),'--execute-once'])
