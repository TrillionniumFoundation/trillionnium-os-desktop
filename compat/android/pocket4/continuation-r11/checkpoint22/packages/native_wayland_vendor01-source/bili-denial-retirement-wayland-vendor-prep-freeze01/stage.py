import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
ROOT=Path("/home/alex/work/p4-retirement-wayland-vendor-prep01-20261106")
TRANSFERRED={"prepare_vendor.py":{"bytes":53054,"sha256":"1ff10b18860b909b694d62904149d75f98b19cf18559d2d43809566334ff9a75"},"locked-registry-packages.json":{"bytes":43920,"sha256":"a86540f0e046028467072afadccac95565f294c399b43c02764cb86dba23f2b9"}}
REUSED_AUTHORITY={"registry-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/registry-result.json","bytes":211021,"sha256":"b7f723a9898e6db5abd181cafb02afc3d9a6e2e2c2ec0119b7c20c82ebd62993","mode":256},"parent469-manifest.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder469-hal-provider-closure-compile-01-20261106/attempt01/copied-builder-source-manifest.json","bytes":99327,"sha256":"88dc3c8020c436009862800ffdc5af97f50f6ae7efff832562c2784d66794701","mode":384},"parent469-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder469-hal-provider-closure-compile-01-20261106/attempt01/result.json","bytes":170316,"sha256":"3636057b9a20fc895657064da3fb66d8ded7e69ebfa5a5b92072a51b33f29fd5","mode":384},"original-Cargo.lock":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder469-hal-provider-closure-compile-01-20261106/builder-source/Cargo.lock","bytes":51836,"sha256":"c1dfa6f13f789cf40435d0d72973d029d0e264b27bd833eabb5a727492127f62","mode":436},"wayland01-metadata.stderr":{"path":"/home/alex/work/p4-retirement-wayland-check01-20261106/attempt01/command10.stderr","bytes":120,"sha256":"78702e8a0954bbeffd0d1704a8fdbc87719b80009f616d9c2dbd5f1338117200","mode":384}}
EXPECTED={"prepare_vendor.py":{"bytes":53054,"sha256":"1ff10b18860b909b694d62904149d75f98b19cf18559d2d43809566334ff9a75"},"locked-registry-packages.json":{"bytes":43920,"sha256":"a86540f0e046028467072afadccac95565f294c399b43c02764cb86dba23f2b9"},"registry-result.json":{"bytes":211021,"sha256":"b7f723a9898e6db5abd181cafb02afc3d9a6e2e2c2ec0119b7c20c82ebd62993"},"parent469-manifest.json":{"bytes":99327,"sha256":"88dc3c8020c436009862800ffdc5af97f50f6ae7efff832562c2784d66794701"},"parent469-result.json":{"bytes":170316,"sha256":"3636057b9a20fc895657064da3fb66d8ded7e69ebfa5a5b92072a51b33f29fd5"},"original-Cargo.lock":{"bytes":51836,"sha256":"c1dfa6f13f789cf40435d0d72973d029d0e264b27bd833eabb5a727492127f62"},"wayland01-metadata.stderr":{"bytes":120,"sha256":"78702e8a0954bbeffd0d1704a8fdbc87719b80009f616d9c2dbd5f1338117200"}}
def require(ok,message):
    if not ok:raise RuntimeError(message)
def real_directory(path):
    for parent in (path,*path.parents):
        require(stat.S_ISDIR(parent.lstat().st_mode),'authority/stage parent aliases non-directory: '+str(parent))
def identity(value):
    return [value.st_dev,value.st_ino,value.st_mode,value.st_uid,value.st_gid,value.st_nlink,value.st_size,value.st_mtime_ns,value.st_ctime_ns]
def pinned_authority(name,wanted):
    path=Path(wanted['path'])
    real_directory(path.parent)
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid==1000 and before.st_gid==1000 and
                before.st_nlink==1 and stat.S_IMODE(before.st_mode)==wanted['mode'] and
                before.st_size==wanted['bytes'] and 0<before.st_size<=1024*1024,
                'fixed reused authority type/owner/mode/size differs: '+name)
        chunks=[];total=0
        while total<=wanted['bytes']:
            chunk=os.read(fd,min(65536,wanted['bytes']+1-total))
            if not chunk:break
            chunks.append(chunk);total+=len(chunk)
        raw=b''.join(chunks)
        require(total==wanted['bytes'] and hashlib.sha256(raw).hexdigest()==wanted['sha256'],
                'fixed reused authority bytes/hash differs: '+name)
        real_directory(path.parent)
        require(identity(before)==identity(os.fstat(fd))==identity(path.lstat()),
                'fixed reused authority changed during read: '+name)
        return raw.decode('utf-8'),{'path':str(path),'identity':identity(before),
                                   'bytes':total,'sha256':wanted['sha256']}
    finally:
        os.close(fd)
def main(packet):
    require(os.getuid()==1000 and os.geteuid()==1000,'operator UID1000 required')
    require(type(packet) is dict and set(packet)==set(TRANSFERRED),'transferred member set differs')
    require(len(TRANSFERRED)==2 and len(REUSED_AUTHORITY)==5 and len(EXPECTED)==7 and
            not set(TRANSFERRED)&set(REUSED_AUTHORITY),'fixed source member partition differs')
    for name,text in packet.items():
        path=PurePosixPath(name)
        require(type(text) is str and name and not path.is_absolute() and '..' not in path.parts and str(path)==name,
                'noncanonical transferred source path/type')
        raw=text.encode('utf-8')
        require(len(raw)==TRANSFERRED[name]['bytes'] and hashlib.sha256(raw).hexdigest()==TRANSFERRED[name]['sha256'],
                'transferred source pin mismatch: '+name)
    complete=dict(packet);observations={}
    # All five immutable actual inputs are re-read before creating ROOT.
    # No paths supplied by the incoming packet can select a reused authority.
    for name,wanted in REUSED_AUTHORITY.items():
        text,observation=pinned_authority(name,wanted)
        complete[name]=text;observations[name]=observation
    require(set(complete)==set(EXPECTED),'complete source member set differs')
    for name,row in observations.items():
        path=Path(row['path']);real_directory(path.parent)
        require(identity(path.lstat())==row['identity'],'authority changed before stage creation: '+name)
    for name,text in complete.items():
        raw=text.encode('utf-8')
        require(len(raw)==EXPECTED[name]['bytes'] and hashlib.sha256(raw).hexdigest()==EXPECTED[name]['sha256'],
                'complete source pin mismatch: '+name)
    real_directory(ROOT.parent)
    os.umask(0o077)
    ROOT.mkdir(mode=0o700)
    source=ROOT/'control-source';source.mkdir(mode=0o700)
    for name,text in complete.items():
        path=source/name
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        real_directory(path.parent)
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
        with os.fdopen(fd,'wb') as stream:
            raw=text.encode('utf-8')
            require(stream.write(raw)==len(raw),'short staged source write: '+name)
            stream.flush();os.fsync(stream.fileno())
    raw=(json.dumps({'schema':1,'files':EXPECTED,'reused_authority_observations':observations,
                    'transferred_source_files':len(TRANSFERRED),'reused_fixed_authority_files':len(REUSED_AUTHORITY),
                    'Main_actions':0,'only_owned_root_written':True},indent=2)+'\n').encode()
    fd=os.open(ROOT/'stage-receipt.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,'wb') as stream:
        require(stream.write(raw)==len(raw),'short stage receipt write');stream.flush();os.fsync(stream.fileno())
    os.execve('/usr/bin/python3',['/usr/bin/python3','-I','-B',str(source/'prepare_vendor.py'),'--execute-once'],
              {'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'})
