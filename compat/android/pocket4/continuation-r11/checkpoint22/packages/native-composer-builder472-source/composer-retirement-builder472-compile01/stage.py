import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
ROOT=Path("/home/alex/work/pocket4-native-builder472-composer-retirement-entry-compile-01-20261106")
TRANSFERRED={"compile_builder.py":{"bytes":90451,"sha256":"a1e24b06b89c96c4d818d62b0394653c56e10fed6e3793c88ce11af19d6bd907"},"expected-builder472-manifest.json":{"bytes":99523,"sha256":"fcbf72b891d9a9bbbcd015777e50cc3ade436f25732a603b51de261eab9cb27a"},"composer-entry-proof.json":{"bytes":11586,"sha256":"3bc022c9924dc13f7e2ad8d6ed85a079af1dec61733433b88c2c76d0df0c60da"},"build-scope.json":{"bytes":6535,"sha256":"f43cd778b75e484d53899eab543680e6b32ae5e54d6eca373b34223dcfcc8af9"},"delta/tools/droidloom-update/src/android.rs":{"bytes":321919,"sha256":"0be2c4d9607c719a8e2bec337d0f23caced603381b0823659559844f77eea996"},"delta/tools/droidloom-update/src/main.rs":{"bytes":24381,"sha256":"f6be56d7f64144c0be40b3c6c519a966b9d733ef3e5f857d8140bef1be3a8ace"}}
REUSED_AUTHORITY={"go-control-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/go-control-result.json","bytes":44083,"sha256":"391ed7920bdc8a0a7ff3797237a8425d51aaa88cd37f29214baca6a7061d8674","mode":256},"image-tools-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/image-tools-result.json","bytes":34633,"sha256":"b7129a849481537bd9a6e8124ab43c639d22712b0ce732488f132186ee1b7292","mode":256},"prior-compile01-failure.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/prior-compile01-failure.json","bytes":7681,"sha256":"44da2c2f9f2df67bc1c32fe25f003442378b19e341da4add8869b77488e7fee3","mode":256},"registry-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/registry-result.json","bytes":211021,"sha256":"b7f723a9898e6db5abd181cafb02afc3d9a6e2e2c2ec0119b7c20c82ebd62993","mode":256},"rust193-tools-recheck-read03-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/rust193-tools-recheck-read03-result.json","bytes":31452,"sha256":"60f543d7a5fc552add6824160794c2c2e8b1a5f908401aab9b176a0a737789fb","mode":256},"selected-build.stdout":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/selected-build.stdout","bytes":2121,"sha256":"82ad8aefece0dedb3a992db45b5de4097ebbb2c0fd02ed00ffe50c401bd4dd0d","mode":256},"selection-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/selection-result.json","bytes":14132,"sha256":"185fce9a8eba4c8edb9879da1eef282404e890ec013a8c4c41c61ccbea7023bf","mode":256},"typed-lock-derivation.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/typed-lock-derivation.json","bytes":6051,"sha256":"c5cd3f0efd5519b8e724a42b7fc27850e20dc5a5ea55fff868366e902b56c3e0","mode":256},"typed-root-trees-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/control-source/typed-root-trees-result.json","bytes":51842,"sha256":"0088aaea045f1c0e048db1a65184e536495f3d0d8a9721cd668bdfa0016b43e8","mode":256},"compiled-parent470-manifest.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder470-published-lock-alignment-compile-01-20261106/attempt01/copied-builder-source-manifest.json","bytes":99327,"sha256":"d87ab919c015a8739011a83add768db28c7f7296a7be9683a0516b28808c1057","mode":384},"compiled-parent470-result.json":{"path":"/home/alex/work/pocket4-native-typed-ingress-builder470-published-lock-alignment-compile-01-20261106/attempt01/result.json","bytes":172040,"sha256":"f4e78f21dec485f59ff2149cb12298c070142dbad4e29b00a776729a376eea4c","mode":384},"delta/graphics/droidloom-composer-service/src/main.rs":{"path":"/home/alex/work/p4-retirement-wayland-check03-20261106/control-source/candidate-composer-main.rs","bytes":19202,"sha256":"567c60fd293f35e2e0957db6f38bc967cc0c3fa90354b98491d461a7decdb4ce","mode":256},"delta/graphics/droidloom-composer-service/src/control.rs":{"path":"/home/alex/work/p4-retirement-wayland-check03-20261106/control-source/candidate-control.rs","bytes":42491,"sha256":"d3d9f4b763a6e80b6549119e42b4d6c3c6ab7368359f3cc71d2e090f05a881ca","mode":256},"delta/graphics/droidloom-composer/src/denial.rs":{"path":"/home/alex/work/p4-retirement-wayland-check03-20261106/control-source/candidate-core-denial.rs","bytes":25541,"sha256":"ed0080cd33a3a4fa67b3a0c2e95bc274ab38e992ec073ab01d87b910bf2db3c8","mode":256},"delta/graphics/droidloom-denial-endpoint/src/lib.rs":{"path":"/home/alex/work/p4-retirement-wayland-check03-20261106/control-source/candidate-endpoint.rs","bytes":63752,"sha256":"062b65857160eb6e3aeba2a78c4ce3d8503c02572f24353f8c944d950e52308c","mode":256},"delta/graphics/droidloom-wayland/src/retirement.rs":{"path":"/home/alex/work/p4-retirement-wayland-check03-20261106/control-source/candidate-engine-retirement.rs","bytes":11118,"sha256":"383f4c6f7490c8568f1853af6e9449fdb35bdb088348de4a9856d75f97306873","mode":256},"delta/graphics/droidloom-denial-protocol/src/lib.rs":{"path":"/home/alex/work/p4-retirement-wayland-check03-20261106/control-source/candidate-protocol.rs","bytes":105464,"sha256":"6c7f8df133f2a9e55bd375da4b39dcba5b00d0c4c3ba6531a6b8be329ebce41c","mode":256},"delta/graphics/droidloom-composer-aidl/src/denial.rs":{"path":"/home/alex/work/p4-retirement-wayland-check03-20261106/control-source/candidate-provider.rs","bytes":50513,"sha256":"d6f13720da4267ff46f369617faecbb8c6446eca2c624e381c1ff51ddaebbf09","mode":256},"delta/graphics/droidloom-wayland/src/layers.rs":{"path":"/home/alex/work/p4-retirement-wayland-check03-20261106/control-source/candidate-wayland-layers.rs","bytes":35990,"sha256":"d0a81ce5339c5020496e9b73e007d52ee206449827269b272e4ef6ef43df5ecc","mode":256},"delta/graphics/droidloom-wayland/src/main.rs":{"path":"/home/alex/work/p4-retirement-wayland-check03-20261106/control-source/candidate-wayland-main.rs","bytes":110131,"sha256":"0f56264e971db9f246d8db34d7fd5de157fd389a97bfb34492a6f53376d27459","mode":256},"actual-wayland03-result.json":{"path":"/home/alex/work/p4-retirement-wayland-check03-20261106/attempt01/result.json","bytes":81805,"sha256":"57546b6c6c2d4e05aea6099097944cdbe6746bbcc0124768a314414ec5663abd","mode":384}}
EXPECTED={"compile_builder.py":{"bytes":90451,"sha256":"a1e24b06b89c96c4d818d62b0394653c56e10fed6e3793c88ce11af19d6bd907"},"expected-builder472-manifest.json":{"bytes":99523,"sha256":"fcbf72b891d9a9bbbcd015777e50cc3ade436f25732a603b51de261eab9cb27a"},"composer-entry-proof.json":{"bytes":11586,"sha256":"3bc022c9924dc13f7e2ad8d6ed85a079af1dec61733433b88c2c76d0df0c60da"},"build-scope.json":{"bytes":6535,"sha256":"f43cd778b75e484d53899eab543680e6b32ae5e54d6eca373b34223dcfcc8af9"},"delta/tools/droidloom-update/src/android.rs":{"bytes":321919,"sha256":"0be2c4d9607c719a8e2bec337d0f23caced603381b0823659559844f77eea996"},"delta/tools/droidloom-update/src/main.rs":{"bytes":24381,"sha256":"f6be56d7f64144c0be40b3c6c519a966b9d733ef3e5f857d8140bef1be3a8ace"},"go-control-result.json":{"bytes":44083,"sha256":"391ed7920bdc8a0a7ff3797237a8425d51aaa88cd37f29214baca6a7061d8674"},"image-tools-result.json":{"bytes":34633,"sha256":"b7129a849481537bd9a6e8124ab43c639d22712b0ce732488f132186ee1b7292"},"prior-compile01-failure.json":{"bytes":7681,"sha256":"44da2c2f9f2df67bc1c32fe25f003442378b19e341da4add8869b77488e7fee3"},"registry-result.json":{"bytes":211021,"sha256":"b7f723a9898e6db5abd181cafb02afc3d9a6e2e2c2ec0119b7c20c82ebd62993"},"rust193-tools-recheck-read03-result.json":{"bytes":31452,"sha256":"60f543d7a5fc552add6824160794c2c2e8b1a5f908401aab9b176a0a737789fb"},"selected-build.stdout":{"bytes":2121,"sha256":"82ad8aefece0dedb3a992db45b5de4097ebbb2c0fd02ed00ffe50c401bd4dd0d"},"selection-result.json":{"bytes":14132,"sha256":"185fce9a8eba4c8edb9879da1eef282404e890ec013a8c4c41c61ccbea7023bf"},"typed-lock-derivation.json":{"bytes":6051,"sha256":"c5cd3f0efd5519b8e724a42b7fc27850e20dc5a5ea55fff868366e902b56c3e0"},"typed-root-trees-result.json":{"bytes":51842,"sha256":"0088aaea045f1c0e048db1a65184e536495f3d0d8a9721cd668bdfa0016b43e8"},"compiled-parent470-manifest.json":{"bytes":99327,"sha256":"d87ab919c015a8739011a83add768db28c7f7296a7be9683a0516b28808c1057"},"compiled-parent470-result.json":{"bytes":172040,"sha256":"f4e78f21dec485f59ff2149cb12298c070142dbad4e29b00a776729a376eea4c"},"delta/graphics/droidloom-composer-service/src/main.rs":{"bytes":19202,"sha256":"567c60fd293f35e2e0957db6f38bc967cc0c3fa90354b98491d461a7decdb4ce"},"delta/graphics/droidloom-composer-service/src/control.rs":{"bytes":42491,"sha256":"d3d9f4b763a6e80b6549119e42b4d6c3c6ab7368359f3cc71d2e090f05a881ca"},"delta/graphics/droidloom-composer/src/denial.rs":{"bytes":25541,"sha256":"ed0080cd33a3a4fa67b3a0c2e95bc274ab38e992ec073ab01d87b910bf2db3c8"},"delta/graphics/droidloom-denial-endpoint/src/lib.rs":{"bytes":63752,"sha256":"062b65857160eb6e3aeba2a78c4ce3d8503c02572f24353f8c944d950e52308c"},"delta/graphics/droidloom-wayland/src/retirement.rs":{"bytes":11118,"sha256":"383f4c6f7490c8568f1853af6e9449fdb35bdb088348de4a9856d75f97306873"},"delta/graphics/droidloom-denial-protocol/src/lib.rs":{"bytes":105464,"sha256":"6c7f8df133f2a9e55bd375da4b39dcba5b00d0c4c3ba6531a6b8be329ebce41c"},"delta/graphics/droidloom-composer-aidl/src/denial.rs":{"bytes":50513,"sha256":"d6f13720da4267ff46f369617faecbb8c6446eca2c624e381c1ff51ddaebbf09"},"delta/graphics/droidloom-wayland/src/layers.rs":{"bytes":35990,"sha256":"d0a81ce5339c5020496e9b73e007d52ee206449827269b272e4ef6ef43df5ecc"},"delta/graphics/droidloom-wayland/src/main.rs":{"bytes":110131,"sha256":"0f56264e971db9f246d8db34d7fd5de157fd389a97bfb34492a6f53376d27459"},"actual-wayland03-result.json":{"bytes":81805,"sha256":"57546b6c6c2d4e05aea6099097944cdbe6746bbcc0124768a314414ec5663abd"}}
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
    require(len(TRANSFERRED)==6 and len(REUSED_AUTHORITY)==21 and len(EXPECTED)==27 and
            not set(TRANSFERRED)&set(REUSED_AUTHORITY),'fixed source member partition differs')
    for name,text in packet.items():
        path=PurePosixPath(name)
        require(type(text) is str and name and not path.is_absolute() and '..' not in path.parts and str(path)==name,
                'noncanonical transferred source path/type')
        raw=text.encode('utf-8')
        require(len(raw)==TRANSFERRED[name]['bytes'] and hashlib.sha256(raw).hexdigest()==TRANSFERRED[name]['sha256'],
                'transferred source pin mismatch: '+name)
    complete=dict(packet);observations={}
    # All twenty-one fixed actual/source inputs are re-read before creating ROOT.
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
