import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
ROOT=Path("/home/alex/work/pocket4-native-typed-ingress-builder469-hal-provider-closure-compile-01-20261106")
TRANSFERRED={"compile_builder.py":{"bytes":83194,"sha256":"6e4b18a1116bdc709e5bda2084e79967699be918770731795806d1bc8634bec2"},"expected-builder469-manifest.json":{"bytes":99327,"sha256":"88dc3c8020c436009862800ffdc5af97f50f6ae7efff832562c2784d66794701"},"provider-closure-proof.json":{"bytes":44747,"sha256":"45d47c45524c3f3bbc8bf4c8d5c28fcbbd7ba0acbeea0c4d25fcb37e8de0690c"},"delta/tools/droidloom-update/src/android.rs":{"bytes":294614,"sha256":"eeea9718e16a40692dd4849fdfbc907bb65e5f7c6e205568034f408fe0803d39"},"delta/tools/droidloom-update/src/native_role_ingress.rs":{"bytes":39625,"sha256":"d7b69e7c032a9fe7e184f57eaa2063d6e54c294c94168325aefe99c1b317f869"},"delta/android/manifest/m2-role-ingress-hal-provider-source-lock.json":{"bytes":96934,"sha256":"c7154e445c2bf1a4539418c68a04731538f9ac11050132571b911e706084f8fd"},"delta/android/native-role-ingress/provider-fixtures/car-vhal-client.Android.bp":{"bytes":1705,"sha256":"d27df8040413d7575e066bded28bf04c72a62436dab9659b553eb1ae88819098"},"delta/android/native-role-ingress/provider-fixtures/car-large-parcelable.Android.bp":{"bytes":1355,"sha256":"66b33bf0a2234c0f301dfabed4e5ab7e69562d4bed111cedc6cd81ffa68ecfb8"},"delta/android/native-role-ingress/provider-fixtures/neuralnetworks-root.Android.bp":{"bytes":1726,"sha256":"f408846ebf2fcbf1fc3075a312b2c388888bedd5bd7be96efb07301a9085ad08"},"delta/android/native-role-ingress/provider-fixtures/neuralnetworks-common.Android.bp":{"bytes":13060,"sha256":"4153fd69cfeabb40bcefa51456a6b3747d835e96698150ed4e8bb950eba1f265"},"delta/android/native-role-ingress/provider-fixtures/neuralnetworks-types.Android.bp":{"bytes":3279,"sha256":"f3a14a68f3d0c918f44099b318fc22c8ff0067b4ddbc55b6c8e29177dff6487d"},"delta/android/native-role-ingress/provider-fixtures/hardware-remote-access.Android.bp":{"bytes":3400,"sha256":"fc163b9fd4bf32871e600e2dfea89fd3223b82e4445053a69db316ea6d5683e3"},"delta/android/native-role-ingress/provider-fixtures/hardware-neural-common.Android.bp":{"bytes":1757,"sha256":"03d240c5d70281ce23758c4a87bda16d99138433926778b6493f7d59dafba053"}}
REUSED_AUTHORITY={"go-control-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/go-control-result.json","bytes":44083,"sha256":"391ed7920bdc8a0a7ff3797237a8425d51aaa88cd37f29214baca6a7061d8674","mode":256},"image-tools-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/image-tools-result.json","bytes":34633,"sha256":"b7129a849481537bd9a6e8124ab43c639d22712b0ce732488f132186ee1b7292","mode":256},"prior-compile01-failure.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/prior-compile01-failure.json","bytes":7681,"sha256":"44da2c2f9f2df67bc1c32fe25f003442378b19e341da4add8869b77488e7fee3","mode":256},"registry-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/registry-result.json","bytes":211021,"sha256":"b7f723a9898e6db5abd181cafb02afc3d9a6e2e2c2ec0119b7c20c82ebd62993","mode":256},"rust193-tools-recheck-read03-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/rust193-tools-recheck-read03-result.json","bytes":31452,"sha256":"60f543d7a5fc552add6824160794c2c2e8b1a5f908401aab9b176a0a737789fb","mode":256},"selected-build.stdout":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/selected-build.stdout","bytes":2121,"sha256":"82ad8aefece0dedb3a992db45b5de4097ebbb2c0fd02ed00ffe50c401bd4dd0d","mode":256},"selection-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/selection-result.json","bytes":14132,"sha256":"185fce9a8eba4c8edb9879da1eef282404e890ec013a8c4c41c61ccbea7023bf","mode":256},"typed-lock-derivation.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/typed-lock-derivation.json","bytes":6051,"sha256":"c5cd3f0efd5519b8e724a42b7fc27850e20dc5a5ea55fff868366e902b56c3e0","mode":256},"typed-root-trees-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/typed-root-trees-result.json","bytes":51842,"sha256":"0088aaea045f1c0e048db1a65184e536495f3d0d8a9721cd668bdfa0016b43e8","mode":256},"compiled-parent468-manifest.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder468-provider-closure-compile-03-20261106/attempt01/copied-builder-source-manifest.json","bytes":97525,"sha256":"e06522400f746b62016f82dfd3ec913b39cd9a8f33f9bca4f61a19a2787684ee","mode":384},"compiled-parent468-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder468-provider-closure-compile-03-20261106/attempt01/result.json","bytes":161423,"sha256":"871e78f7ad8f3f3a12c165297e4fe566d96cfe3a2ce64a0d0010cffdb647b6b8","mode":384}}
EXPECTED={"compile_builder.py":{"bytes":83194,"sha256":"6e4b18a1116bdc709e5bda2084e79967699be918770731795806d1bc8634bec2"},"expected-builder469-manifest.json":{"bytes":99327,"sha256":"88dc3c8020c436009862800ffdc5af97f50f6ae7efff832562c2784d66794701"},"provider-closure-proof.json":{"bytes":44747,"sha256":"45d47c45524c3f3bbc8bf4c8d5c28fcbbd7ba0acbeea0c4d25fcb37e8de0690c"},"delta/tools/droidloom-update/src/android.rs":{"bytes":294614,"sha256":"eeea9718e16a40692dd4849fdfbc907bb65e5f7c6e205568034f408fe0803d39"},"delta/tools/droidloom-update/src/native_role_ingress.rs":{"bytes":39625,"sha256":"d7b69e7c032a9fe7e184f57eaa2063d6e54c294c94168325aefe99c1b317f869"},"delta/android/manifest/m2-role-ingress-hal-provider-source-lock.json":{"bytes":96934,"sha256":"c7154e445c2bf1a4539418c68a04731538f9ac11050132571b911e706084f8fd"},"delta/android/native-role-ingress/provider-fixtures/car-vhal-client.Android.bp":{"bytes":1705,"sha256":"d27df8040413d7575e066bded28bf04c72a62436dab9659b553eb1ae88819098"},"delta/android/native-role-ingress/provider-fixtures/car-large-parcelable.Android.bp":{"bytes":1355,"sha256":"66b33bf0a2234c0f301dfabed4e5ab7e69562d4bed111cedc6cd81ffa68ecfb8"},"delta/android/native-role-ingress/provider-fixtures/neuralnetworks-root.Android.bp":{"bytes":1726,"sha256":"f408846ebf2fcbf1fc3075a312b2c388888bedd5bd7be96efb07301a9085ad08"},"delta/android/native-role-ingress/provider-fixtures/neuralnetworks-common.Android.bp":{"bytes":13060,"sha256":"4153fd69cfeabb40bcefa51456a6b3747d835e96698150ed4e8bb950eba1f265"},"delta/android/native-role-ingress/provider-fixtures/neuralnetworks-types.Android.bp":{"bytes":3279,"sha256":"f3a14a68f3d0c918f44099b318fc22c8ff0067b4ddbc55b6c8e29177dff6487d"},"delta/android/native-role-ingress/provider-fixtures/hardware-remote-access.Android.bp":{"bytes":3400,"sha256":"fc163b9fd4bf32871e600e2dfea89fd3223b82e4445053a69db316ea6d5683e3"},"delta/android/native-role-ingress/provider-fixtures/hardware-neural-common.Android.bp":{"bytes":1757,"sha256":"03d240c5d70281ce23758c4a87bda16d99138433926778b6493f7d59dafba053"},"go-control-result.json":{"bytes":44083,"sha256":"391ed7920bdc8a0a7ff3797237a8425d51aaa88cd37f29214baca6a7061d8674"},"image-tools-result.json":{"bytes":34633,"sha256":"b7129a849481537bd9a6e8124ab43c639d22712b0ce732488f132186ee1b7292"},"prior-compile01-failure.json":{"bytes":7681,"sha256":"44da2c2f9f2df67bc1c32fe25f003442378b19e341da4add8869b77488e7fee3"},"registry-result.json":{"bytes":211021,"sha256":"b7f723a9898e6db5abd181cafb02afc3d9a6e2e2c2ec0119b7c20c82ebd62993"},"rust193-tools-recheck-read03-result.json":{"bytes":31452,"sha256":"60f543d7a5fc552add6824160794c2c2e8b1a5f908401aab9b176a0a737789fb"},"selected-build.stdout":{"bytes":2121,"sha256":"82ad8aefece0dedb3a992db45b5de4097ebbb2c0fd02ed00ffe50c401bd4dd0d"},"selection-result.json":{"bytes":14132,"sha256":"185fce9a8eba4c8edb9879da1eef282404e890ec013a8c4c41c61ccbea7023bf"},"typed-lock-derivation.json":{"bytes":6051,"sha256":"c5cd3f0efd5519b8e724a42b7fc27850e20dc5a5ea55fff868366e902b56c3e0"},"typed-root-trees-result.json":{"bytes":51842,"sha256":"0088aaea045f1c0e048db1a65184e536495f3d0d8a9721cd668bdfa0016b43e8"},"compiled-parent468-manifest.json":{"bytes":97525,"sha256":"e06522400f746b62016f82dfd3ec913b39cd9a8f33f9bca4f61a19a2787684ee"},"compiled-parent468-result.json":{"bytes":161423,"sha256":"871e78f7ad8f3f3a12c165297e4fe566d96cfe3a2ce64a0d0010cffdb647b6b8"}}
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
    require(len(TRANSFERRED)==13 and len(REUSED_AUTHORITY)==11 and len(EXPECTED)==24 and
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
