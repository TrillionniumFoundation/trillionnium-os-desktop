import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
ROOT=Path("/home/alex/work/pocket4-native-status-lifecycle-readiness-compile-01-20261106")
TRANSFERRED={"compile_status.py":{"bytes":84470,"sha256":"66757ecc000a401f0f3ba690982945301d330a54fc84ab855923dbb236abe025"},"expected-status-manifest.json":{"bytes":99958,"sha256":"d8f6213f73726bd3766645e7decb5ebfac852f49852c49545e511a54b689d16e"},"build-scope.json":{"bytes":4272,"sha256":"554d3eee89100697b69336ccad6b97ca983aed064a75a000bf1cfa175709437b"},"delta/runtime/droidloom-supervisor/src/control.rs":{"bytes":71588,"sha256":"50d7bc3abd94f83233ef7d461f93cb714f843cacb3fd5c0e929d06671a95f89b"},"delta/runtime/droidloom-supervisor/src/development.rs":{"bytes":101645,"sha256":"37645978b33d443313694609625a97ac9dd7f6e14053664a48d02ff6d8daea90"},"delta/runtime/droidloom-supervisor/src/bin/droidloomctl.rs":{"bytes":20606,"sha256":"3733dd7586ebf534aef3d4a5d176a76b8822dd0c6a6b8b39fb64adf8e70cd484"},"delta/runtime/droidloom-supervisor/tests/cli_lifecycle.rs":{"bytes":11717,"sha256":"5310bfdb21b006ae1432b584c03fbbfb4c1f3a7cbd3ce226b54770ff4bbca317"},"delta/runtime/droidloom-supervisor/src/control_status_tests.rs":{"bytes":11843,"sha256":"0bafad33112df280c73ceedf675305236275bb043d0909fc4a71f6366c0a6727"}}
REUSED_AUTHORITY={"compiled-parent474-manifest.json":{"path":"/home/alex/work/pocket4-native-builder474-composer-audiocontrol-projection-compile-01-20261106/attempt01/copied-builder-source-manifest.json","bytes":99750,"sha256":"e18fe837795e9c3bd684592f3c91228604b2b21ca9d918ac56cebdb4b40754dd","mode":384},"compiled-parent474-result.json":{"path":"/home/alex/work/pocket4-native-builder474-composer-audiocontrol-projection-compile-01-20261106/attempt01/result.json","bytes":197750,"sha256":"d3b0264441b2af0684c9f147bbb32e274a6d42f96fd83c19f0f24ba6937ad294","mode":384},"prior-compile01-failure.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/prior-compile01-failure.json","bytes":7681,"sha256":"44da2c2f9f2df67bc1c32fe25f003442378b19e341da4add8869b77488e7fee3","mode":256},"registry-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/registry-result.json","bytes":211021,"sha256":"b7f723a9898e6db5abd181cafb02afc3d9a6e2e2c2ec0119b7c20c82ebd62993","mode":256},"rust193-tools-recheck-read03-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/rust193-tools-recheck-read03-result.json","bytes":31452,"sha256":"60f543d7a5fc552add6824160794c2c2e8b1a5f908401aab9b176a0a737789fb","mode":256}}
EXPECTED={"compile_status.py":{"bytes":84470,"sha256":"66757ecc000a401f0f3ba690982945301d330a54fc84ab855923dbb236abe025"},"expected-status-manifest.json":{"bytes":99958,"sha256":"d8f6213f73726bd3766645e7decb5ebfac852f49852c49545e511a54b689d16e"},"build-scope.json":{"bytes":4272,"sha256":"554d3eee89100697b69336ccad6b97ca983aed064a75a000bf1cfa175709437b"},"delta/runtime/droidloom-supervisor/src/control.rs":{"bytes":71588,"sha256":"50d7bc3abd94f83233ef7d461f93cb714f843cacb3fd5c0e929d06671a95f89b"},"delta/runtime/droidloom-supervisor/src/development.rs":{"bytes":101645,"sha256":"37645978b33d443313694609625a97ac9dd7f6e14053664a48d02ff6d8daea90"},"delta/runtime/droidloom-supervisor/src/bin/droidloomctl.rs":{"bytes":20606,"sha256":"3733dd7586ebf534aef3d4a5d176a76b8822dd0c6a6b8b39fb64adf8e70cd484"},"delta/runtime/droidloom-supervisor/tests/cli_lifecycle.rs":{"bytes":11717,"sha256":"5310bfdb21b006ae1432b584c03fbbfb4c1f3a7cbd3ce226b54770ff4bbca317"},"delta/runtime/droidloom-supervisor/src/control_status_tests.rs":{"bytes":11843,"sha256":"0bafad33112df280c73ceedf675305236275bb043d0909fc4a71f6366c0a6727"},"compiled-parent474-manifest.json":{"bytes":99750,"sha256":"e18fe837795e9c3bd684592f3c91228604b2b21ca9d918ac56cebdb4b40754dd"},"compiled-parent474-result.json":{"bytes":197750,"sha256":"d3b0264441b2af0684c9f147bbb32e274a6d42f96fd83c19f0f24ba6937ad294"},"prior-compile01-failure.json":{"bytes":7681,"sha256":"44da2c2f9f2df67bc1c32fe25f003442378b19e341da4add8869b77488e7fee3"},"registry-result.json":{"bytes":211021,"sha256":"b7f723a9898e6db5abd181cafb02afc3d9a6e2e2c2ec0119b7c20c82ebd62993"},"rust193-tools-recheck-read03-result.json":{"bytes":31452,"sha256":"60f543d7a5fc552add6824160794c2c2e8b1a5f908401aab9b176a0a737789fb"}}
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
    require(len(TRANSFERRED)==8 and len(REUSED_AUTHORITY)==5 and len(EXPECTED)==13 and
            not set(TRANSFERRED)&set(REUSED_AUTHORITY),'fixed source member partition differs')
    for name,text in packet.items():
        path=PurePosixPath(name)
        require(type(text) is str and name and not path.is_absolute() and '..' not in path.parts and str(path)==name,
                'noncanonical transferred source path/type')
        raw=text.encode('utf-8')
        require(len(raw)==TRANSFERRED[name]['bytes'] and hashlib.sha256(raw).hexdigest()==TRANSFERRED[name]['sha256'],
                'transferred source pin mismatch: '+name)
    complete=dict(packet);observations={}
    # All five fixed actual/source inputs are re-read before creating ROOT.
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
    os.execve('/usr/bin/python3',['/usr/bin/python3','-I','-B',str(source/'compile_status.py'),'--execute-once'],
              {'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'})
