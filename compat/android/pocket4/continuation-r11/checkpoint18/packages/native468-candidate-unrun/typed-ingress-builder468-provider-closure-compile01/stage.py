import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
ROOT=Path("/home/alex/work/pocket4-native-typed-ingress-builder468-provider-closure-compile-01-20261106")
TRANSFERRED={"compile_builder.py":{"bytes":81620,"sha256":"6c4c4c30497e54ebc79d171d854ca8aa5de79ce85ef77e33d45179ad96f34c55"},"expected-builder468-manifest.json":{"bytes":92800,"sha256":"256532b032ea0732b7833774e4417f78ba469ce485b110c24dcde8c4358b6026"},"provider-closure-proof.json":{"bytes":13365,"sha256":"33249911bfd62c4e0b1a22b3a40b97e12a2c0f8624c46998e160abb6c6e305b4"},"delta/tools/droidloom-update/src/android.rs":{"bytes":274422,"sha256":"7d555524e080284948980731540d40e0ea63070a80a63b2ea320cf935740dafe"},"delta/tools/droidloom-update/src/native_role_ingress.rs":{"bytes":26755,"sha256":"04088760f0f08eda0aad5c2c067ed4cff1d5d3b615c58d93f7dd895d73b4b214"},"delta/android/manifest/m2-role-ingress-provider-source-lock.json":{"bytes":87139,"sha256":"3150cba593f2fb9117244d4ebc92d046abaa3f2c5a4f4ae7e45ba2455b2f1e91"},"delta/android/native-role-ingress/provider-fixtures/SystemUI.Android.bp":{"bytes":49535,"sha256":"fa1aaf330d580d6cefb74dc0ef1b52fcebbdd9b6bced5497a3bd29f9fb3647a3"},"delta/android/native-role-ingress/provider-fixtures/motion.Android.bp":{"bytes":2098,"sha256":"a29bc25117f71e6acac6722f98950831a16a00f382c3ee0f9e991a36ecba5440"},"delta/android/native-role-ingress/provider-fixtures/screenshot.Android.bp":{"bytes":2403,"sha256":"53ba33c12075d68266d9c90620b2a0e04934e7d0b9eb73c1faf6c06cde689032"}}
REUSED_AUTHORITY={"go-control-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/go-control-result.json","bytes":44083,"sha256":"391ed7920bdc8a0a7ff3797237a8425d51aaa88cd37f29214baca6a7061d8674","mode":256},"image-tools-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/image-tools-result.json","bytes":34633,"sha256":"b7129a849481537bd9a6e8124ab43c639d22712b0ce732488f132186ee1b7292","mode":256},"prior-compile01-failure.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/prior-compile01-failure.json","bytes":7681,"sha256":"44da2c2f9f2df67bc1c32fe25f003442378b19e341da4add8869b77488e7fee3","mode":256},"registry-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/registry-result.json","bytes":211021,"sha256":"b7f723a9898e6db5abd181cafb02afc3d9a6e2e2c2ec0119b7c20c82ebd62993","mode":256},"rust193-tools-recheck-read03-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/rust193-tools-recheck-read03-result.json","bytes":31452,"sha256":"60f543d7a5fc552add6824160794c2c2e8b1a5f908401aab9b176a0a737789fb","mode":256},"selected-build.stdout":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/selected-build.stdout","bytes":2121,"sha256":"82ad8aefece0dedb3a992db45b5de4097ebbb2c0fd02ed00ffe50c401bd4dd0d","mode":256},"selection-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/selection-result.json","bytes":14132,"sha256":"185fce9a8eba4c8edb9879da1eef282404e890ec013a8c4c41c61ccbea7023bf","mode":256},"typed-lock-derivation.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/typed-lock-derivation.json","bytes":6051,"sha256":"c5cd3f0efd5519b8e724a42b7fc27850e20dc5a5ea55fff868366e902b56c3e0","mode":256},"typed-root-trees-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/typed-root-trees-result.json","bytes":51842,"sha256":"0088aaea045f1c0e048db1a65184e536495f3d0d8a9721cd668bdfa0016b43e8","mode":256},"compiled-parent467-manifest.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/attempt01/copied-builder-source-manifest.json","bytes":91945,"sha256":"71768da388021a870ef5f5516cc3efbfd956288a8fa74cb9b176b312f68d7605","mode":384},"compiled-parent467-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/attempt01/result.json","bytes":140163,"sha256":"cd9f61ca21dd83210299f24dd50b68f5aa7aeba7eab94ac9cada71271d660e28","mode":384}}
EXPECTED={"compile_builder.py":{"bytes":81620,"sha256":"6c4c4c30497e54ebc79d171d854ca8aa5de79ce85ef77e33d45179ad96f34c55"},"expected-builder468-manifest.json":{"bytes":92800,"sha256":"256532b032ea0732b7833774e4417f78ba469ce485b110c24dcde8c4358b6026"},"provider-closure-proof.json":{"bytes":13365,"sha256":"33249911bfd62c4e0b1a22b3a40b97e12a2c0f8624c46998e160abb6c6e305b4"},"delta/tools/droidloom-update/src/android.rs":{"bytes":274422,"sha256":"7d555524e080284948980731540d40e0ea63070a80a63b2ea320cf935740dafe"},"delta/tools/droidloom-update/src/native_role_ingress.rs":{"bytes":26755,"sha256":"04088760f0f08eda0aad5c2c067ed4cff1d5d3b615c58d93f7dd895d73b4b214"},"delta/android/manifest/m2-role-ingress-provider-source-lock.json":{"bytes":87139,"sha256":"3150cba593f2fb9117244d4ebc92d046abaa3f2c5a4f4ae7e45ba2455b2f1e91"},"delta/android/native-role-ingress/provider-fixtures/SystemUI.Android.bp":{"bytes":49535,"sha256":"fa1aaf330d580d6cefb74dc0ef1b52fcebbdd9b6bced5497a3bd29f9fb3647a3"},"delta/android/native-role-ingress/provider-fixtures/motion.Android.bp":{"bytes":2098,"sha256":"a29bc25117f71e6acac6722f98950831a16a00f382c3ee0f9e991a36ecba5440"},"delta/android/native-role-ingress/provider-fixtures/screenshot.Android.bp":{"bytes":2403,"sha256":"53ba33c12075d68266d9c90620b2a0e04934e7d0b9eb73c1faf6c06cde689032"},"go-control-result.json":{"bytes":44083,"sha256":"391ed7920bdc8a0a7ff3797237a8425d51aaa88cd37f29214baca6a7061d8674"},"image-tools-result.json":{"bytes":34633,"sha256":"b7129a849481537bd9a6e8124ab43c639d22712b0ce732488f132186ee1b7292"},"prior-compile01-failure.json":{"bytes":7681,"sha256":"44da2c2f9f2df67bc1c32fe25f003442378b19e341da4add8869b77488e7fee3"},"registry-result.json":{"bytes":211021,"sha256":"b7f723a9898e6db5abd181cafb02afc3d9a6e2e2c2ec0119b7c20c82ebd62993"},"rust193-tools-recheck-read03-result.json":{"bytes":31452,"sha256":"60f543d7a5fc552add6824160794c2c2e8b1a5f908401aab9b176a0a737789fb"},"selected-build.stdout":{"bytes":2121,"sha256":"82ad8aefece0dedb3a992db45b5de4097ebbb2c0fd02ed00ffe50c401bd4dd0d"},"selection-result.json":{"bytes":14132,"sha256":"185fce9a8eba4c8edb9879da1eef282404e890ec013a8c4c41c61ccbea7023bf"},"typed-lock-derivation.json":{"bytes":6051,"sha256":"c5cd3f0efd5519b8e724a42b7fc27850e20dc5a5ea55fff868366e902b56c3e0"},"typed-root-trees-result.json":{"bytes":51842,"sha256":"0088aaea045f1c0e048db1a65184e536495f3d0d8a9721cd668bdfa0016b43e8"},"compiled-parent467-manifest.json":{"bytes":91945,"sha256":"71768da388021a870ef5f5516cc3efbfd956288a8fa74cb9b176b312f68d7605"},"compiled-parent467-result.json":{"bytes":140163,"sha256":"cd9f61ca21dd83210299f24dd50b68f5aa7aeba7eab94ac9cada71271d660e28"}}
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
    require(len(TRANSFERRED)==9 and len(REUSED_AUTHORITY)==11 and len(EXPECTED)==20 and
            not set(TRANSFERRED)&set(REUSED_AUTHORITY),'fixed source member partition differs')
    for name,text in packet.items():
        path=PurePosixPath(name)
        require(type(text) is str and name and not path.is_absolute() and '..' not in path.parts and str(path)==name,
                'noncanonical transferred source path/type')
        raw=text.encode('utf-8')
        require(len(raw)==TRANSFERRED[name]['bytes'] and hashlib.sha256(raw).hexdigest()==TRANSFERRED[name]['sha256'],
                'transferred source pin mismatch: '+name)
    complete=dict(packet);observations={}
    # All eleven immutable actual inputs are re-read before creating ROOT.
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
    os.execve('/usr/bin/python3',['/usr/bin/python3','-I','-B',str(source/'compile_builder.py'),'--execute-once'],
              {'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'})
