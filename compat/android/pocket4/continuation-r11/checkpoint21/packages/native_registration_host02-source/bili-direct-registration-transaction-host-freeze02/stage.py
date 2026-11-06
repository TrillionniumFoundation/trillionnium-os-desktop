import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
ROOT=Path("/home/alex/work/pocket4-composer-direct-registration-transaction-host-02-20261106")
TRANSFERRED={"compile_fixture.py":{"bytes":82034,"sha256":"b21d6e05ee67ac138b277dba6b74463fd75088d55dadaa445eee5ec2cd1ce11b"},"candidate-source-manifest.json":{"bytes":99327,"sha256":"3e9992c984a2eadd817b4ebde4f1643070f6c1c9aee3b236bf885c63b70f05e2"},"candidate-control.rs":{"bytes":42483,"sha256":"7375c45596193c3458d9dcbd3b14c41f87930fbece3bae5e7bf2800934676273"},"fixture-lib.rs":{"bytes":9274,"sha256":"84659a797076f73904e7437916f3a885902f06ae87282716c8142b51464df60f"},"transaction_tests.rs":{"bytes":23472,"sha256":"c87d314841ac50f00943ae9181505755e8f262f538144e6979a9b63e15ecf298"},"fixture-Cargo.toml":{"bytes":574,"sha256":"49dad84ffccc546f8c4889b87c85ff68143376d7ebebcf92be08259a4296da97"}}
REUSED_AUTHORITY={"prior-compile01-failure.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/prior-compile01-failure.json","bytes":7681,"sha256":"44da2c2f9f2df67bc1c32fe25f003442378b19e341da4add8869b77488e7fee3","mode":256},"registry-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/registry-result.json","bytes":211021,"sha256":"b7f723a9898e6db5abd181cafb02afc3d9a6e2e2c2ec0119b7c20c82ebd62993","mode":256},"rust193-tools-recheck-read03-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/rust193-tools-recheck-read03-result.json","bytes":31452,"sha256":"60f543d7a5fc552add6824160794c2c2e8b1a5f908401aab9b176a0a737789fb","mode":256},"parent469-manifest.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder469-hal-provider-closure-compile-01-20261106/attempt01/copied-builder-source-manifest.json","bytes":99327,"sha256":"88dc3c8020c436009862800ffdc5af97f50f6ae7efff832562c2784d66794701","mode":384},"parent469-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder469-hal-provider-closure-compile-01-20261106/attempt01/result.json","bytes":170316,"sha256":"3636057b9a20fc895657064da3fb66d8ded7e69ebfa5a5b92072a51b33f29fd5","mode":384}}
EXPECTED={"compile_fixture.py":{"bytes":82034,"sha256":"b21d6e05ee67ac138b277dba6b74463fd75088d55dadaa445eee5ec2cd1ce11b"},"candidate-source-manifest.json":{"bytes":99327,"sha256":"3e9992c984a2eadd817b4ebde4f1643070f6c1c9aee3b236bf885c63b70f05e2"},"candidate-control.rs":{"bytes":42483,"sha256":"7375c45596193c3458d9dcbd3b14c41f87930fbece3bae5e7bf2800934676273"},"fixture-lib.rs":{"bytes":9274,"sha256":"84659a797076f73904e7437916f3a885902f06ae87282716c8142b51464df60f"},"transaction_tests.rs":{"bytes":23472,"sha256":"c87d314841ac50f00943ae9181505755e8f262f538144e6979a9b63e15ecf298"},"fixture-Cargo.toml":{"bytes":574,"sha256":"49dad84ffccc546f8c4889b87c85ff68143376d7ebebcf92be08259a4296da97"},"prior-compile01-failure.json":{"bytes":7681,"sha256":"44da2c2f9f2df67bc1c32fe25f003442378b19e341da4add8869b77488e7fee3"},"registry-result.json":{"bytes":211021,"sha256":"b7f723a9898e6db5abd181cafb02afc3d9a6e2e2c2ec0119b7c20c82ebd62993"},"rust193-tools-recheck-read03-result.json":{"bytes":31452,"sha256":"60f543d7a5fc552add6824160794c2c2e8b1a5f908401aab9b176a0a737789fb"},"parent469-manifest.json":{"bytes":99327,"sha256":"88dc3c8020c436009862800ffdc5af97f50f6ae7efff832562c2784d66794701"},"parent469-result.json":{"bytes":170316,"sha256":"3636057b9a20fc895657064da3fb66d8ded7e69ebfa5a5b92072a51b33f29fd5"}}
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
    require(len(TRANSFERRED)==6 and len(REUSED_AUTHORITY)==5 and len(EXPECTED)==11 and
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
    os.execve('/usr/bin/python3',['/usr/bin/python3','-I','-B',str(source/'compile_fixture.py'),'--execute-once'],
              {'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'})
