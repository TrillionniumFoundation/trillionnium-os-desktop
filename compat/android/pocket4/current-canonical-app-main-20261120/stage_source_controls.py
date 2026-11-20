"""Create one pinned host source-control stage and run its private namespace."""
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import zlib

STAGE=Path('/home/alex/work/p4-canonical-source-validation-20261120-3b9d-r1')
PACKET=Path('/home/alex/work/p4-canonical-source-control-packet-20261120-3b9d-r1.z')
COMPRESSED_SHA='f4061d04bf0e80cb48bb1fa454dbe555965fc8bdc409fb47e05fbde8949df37e'
PACKET_SHA='71c2ee722fc26ec4a76f5c537ef654fff1f4501f78e81a83e6ca79b8d8d9d928'
MANIFEST_SHA='fabbfbcb2ea9a461ba0e15ec236a6a0e66a951442b4832e0a144a10d51d714e8'
CURRENT=Path('/home/alex/work/pocket4-android-final/CONTINUATION_CURRENT.json')
FIELDS=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')

def f9(value):return [getattr(value,k) for k in FIELDS]
def read(path,maximum):
    assert path.is_absolute() and path.resolve()==path
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=os.fstat(fd)
        assert stat.S_ISREG(before.st_mode) and before.st_nlink==1 and 0<before.st_size<=maximum
        with os.fdopen(os.dup(fd),'rb') as stream:raw=stream.read(maximum+1)
        assert len(raw)==before.st_size and f9(before)==f9(os.fstat(fd))==f9(path.lstat())
        return raw,f9(before)
    finally:os.close(fd)

def pin(path,raw):return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def write(path,raw,mode=0o444):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    assert path.stat().st_nlink==1 and path.stat().st_uid==path.stat().st_gid==0

assert os.getuid()==os.geteuid()==0
raw,current_f9=read(CURRENT,2*1024*1024)
assert hashlib.sha256(raw).hexdigest()=='091f53bb8ad9623c9825c5e94a91e7226157ba90205fa1bddf06eb362aa0875b'
compressed,packet_f9=read(PACKET,3*1024*1024)
assert hashlib.sha256(compressed).hexdigest()==COMPRESSED_SHA
decoded=zlib.decompress(compressed)
assert len(decoded)==9547328 and hashlib.sha256(decoded).hexdigest()==PACKET_SHA
rows=json.loads(decoded);assert len(rows)==476
STAGE.mkdir(mode=0o700)
seen=set()
for row in rows:
    relative=Path(row['path']);assert not relative.is_absolute() and '..' not in relative.parts
    assert row['path'] not in seen;seen.add(row['path'])
    body=base64.b64decode(row['base64'],validate=True)
    assert len(body)==row['bytes'] and hashlib.sha256(body).hexdigest()==row['sha256']
    write(STAGE/relative,body)
assert read(STAGE/'BUNDLE-MANIFEST.json',1024*1024)[0] and hashlib.sha256((STAGE/'BUNDLE-MANIFEST.json').read_bytes()).hexdigest()==MANIFEST_SHA
before_ns=os.stat('/proc/self/ns/mnt').st_ino
before_libexec=f9(Path('/usr/libexec').lstat())
argv=['/usr/bin/unshare','--mount','--propagation','private','--','/usr/bin/python3','-I','-B',
      str(STAGE/'validate_source_private_namespace.py'),'--stage',str(STAGE),
      '--expect-manifest-sha256',MANIFEST_SHA,'--original-mount-inode',str(before_ns)]
# The private inspector owns/reaps each bounded command using the unchanged
# source recorder. This parent waits for that exact unshare child normally.
child=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                     close_fds=True,check=False)
write(STAGE/'private-source.stdout',child.stdout,0o400)
write(STAGE/'private-source.stderr',child.stderr,0o400)
current_after,after_f9=read(CURRENT,2*1024*1024)
assert current_after==raw and current_f9==after_f9
assert os.stat('/proc/self/ns/mnt').st_ino==before_ns and f9(Path('/usr/libexec').lstat())==before_libexec
assert not (Path('/proc/self/task')/str(os.getpid())/'children').read_text().strip()
report={'schema':'pocket4-canonical-source-control-parent-v1','exit_code':child.returncode,
        'stage':str(STAGE),'source_manifest_sha256':MANIFEST_SHA,
        'source_stdout':pin(STAGE/'private-source.stdout',child.stdout),
        'source_stderr':pin(STAGE/'private-source.stderr',child.stderr),
        'current_before_and_after_f9':current_f9,'CURRENT_unchanged':True,
        'host_mount_namespace_before_and_after':before_ns,'host_libexec_before_and_after_f9':before_libexec,
        'remaining_owned_children':[],'Android_actions':0,'CURRENT_writes':0,'image_opens':0,
        'host_canonical_path_writes':0,'runtime_qualified':False,'Main_readonly_entry_passed':False}
body=(json.dumps(report,sort_keys=True,indent=2)+'\n').encode();write(STAGE/'PARENT-RESULT.json',body,0o400)
print(json.dumps({'result':pin(STAGE/'PARENT-RESULT.json',body),'exit_code':child.returncode,
                  'child_stdout':child.stdout.decode(),'child_stderr':child.stderr.decode()}),flush=True)
raise SystemExit(child.returncode)
