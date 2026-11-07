import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
ROOT = Path("/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/composer-retirement-normal-build-01-20261106")
EXPECTED = {"main_snapshot.py":{"bytes":14642,"sha256":"264100ef85e1792c437a4f450050041141288a0f25a4387af5774c52d0dcea06"},"frozen-work-inventory.py":{"bytes":48443,"sha256":"203dd7f4efdac01891a4c31fd79f2eb3204e3c8c2be5702988f0875307cce9ab"},"actual-work-preparation.json":{"bytes":11091,"sha256":"ab286f3939acfeb648a716ca15e5df348fef6b7007eb5651735fe8a7bda96b1c"},"expected-builder474-manifest.json":{"bytes":99750,"sha256":"e18fe837795e9c3bd684592f3c91228604b2b21ca9d918ac56cebdb4b40754dd"},"prior-framework-inner-terminal.json":{"bytes":2898,"sha256":"58a68cae2784bf401315c8016108304576e11d16bf3d5c64552698d4c3a2bb57"},"prior-framework-outer-terminal.json":{"bytes":24714,"sha256":"2e10bdca3a1b88fe8e72f87dde5f38d972f8db41ce087386fa189c40ad231612"},"actual-published-source-manifest.json":{"bytes":108555,"sha256":"afb23d210fda970a09482a14b9b38af1c92b5be505edd0eda2b76ce5ffc6067f"},"actual-native-prebuilt-Android.bp":{"bytes":1017,"sha256":"d1eca99403572ee9d481e777febac8d4e062f44fd8844285ffc452b17beb531a"},"actual-hal-provider-source-lock.json":{"bytes":96957,"sha256":"72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d"},"framework_build.py":{"bytes":77645,"sha256":"22a6f09f5a119217f78e6ae23cd6ebb23d1abc8c8c97f2d06371ca53a0674d5d"},"fenced_build.py":{"bytes":25501,"sha256":"468cc4b97f46d5ff83540f066ac1510f7da854d0aaffcdd3e6f88cb33d642ff2"},"pure_controls.py":{"bytes":15427,"sha256":"57cebcaf1adb8b67bfad3f43416b7cb4e7fae20fb4e184d8ede27b8532bb05f0"},"capture_lifecycle.py":{"bytes":25240,"sha256":"2dcf44609e6ef53e91b2d8e3a07c192fe65a7d44601f218dc8990272285d4dfe"},"root_snapshot_supervisor.py":{"bytes":12041,"sha256":"903ae227d9231a361c61fad6fd584c97a548bb5a41b09a4e5fa8824e13e02350"},"prior-normal02-outer-terminal.json":{"bytes":24722,"sha256":"42b2d7b8749047df9e1d40ddf9b70b3f3e187c39ce6a15dd0f5721610e814c00"},"actual-resource-observation01.json":{"bytes":399,"sha256":"feb95f82087d7c68a8c8c42b54cf267b8f9c343ce41e49bb8193e96f49f050da"},"actual-current225-source-manifest.json":{"bytes":109252,"sha256":"5ae96f8d2bc32986fdbf8fea12f54dbcb02b1ed1601894b2b23998f61aba0d7d"},"actual-builder474-result.json":{"bytes":197750,"sha256":"d3b0264441b2af0684c9f147bbb32e274a6d42f96fd83c19f0f24ba6937ad294"},"prior-normal09-outer-terminal.json":{"bytes":24759,"sha256":"873a8c03dc51a62e69aaeab28e7929ef2b8b48019d9d1ca949e23ce07d3f3d1a"},"prior-normal09-resource-admission.json":{"bytes":2749,"sha256":"62bc5109a8ed50722560b6374caa1b0581d53abaa0d300e510adbeb85acfb2cd"}}
def main(packet):
    if os.getuid()!=1000 or os.geteuid()!=1000:raise RuntimeError('operator UID1000 required')
    if set(packet)!=set(EXPECTED):raise RuntimeError('staged source member set differs')
    for name,text in packet.items():
        path=PurePosixPath(name)
        if not name or path.is_absolute() or '..' in path.parts or str(path)!=name:raise RuntimeError('noncanonical staged source path')
        raw=text.encode('utf-8')
        if len(raw)!=EXPECTED[name]['bytes'] or hashlib.sha256(raw).hexdigest()!=EXPECTED[name]['sha256']:
            raise RuntimeError('staged source pin mismatch: '+name)
    for name,text in packet.items():
        if name.endswith('.py'):
            compile(text,'<staged-'+name+'>','exec')
    controls_scope={'__name__':'frozen_host_build_pure_controls','__file__':'<frozen-pure-controls>'}
    exec(compile(packet['pure_controls.py'],'pure_controls.py','exec'),controls_scope,controls_scope)
    controls=controls_scope['run'](packet)
    if controls['state']!='PASS' or controls['passed']!=56:
        raise RuntimeError('new host-only pure controls incomplete')
    for parent in [ROOT.parent,*ROOT.parent.parents]:
        if not stat.S_ISDIR(parent.lstat().st_mode):raise RuntimeError('owned root parent aliases non-directory')
    parent=ROOT.parent.lstat()
    if [parent.st_dev,parent.st_ino,parent.st_mode,parent.st_uid,parent.st_gid]!=[66306,34351895,16832,1000,1000]:
        raise RuntimeError('fixed strict owned parent identity differs')
    os.umask(0o077)
    ROOT.mkdir(mode=0o700)
    source=ROOT/'control-source';source.mkdir(mode=0o700)
    for name,text in packet.items():
        path=source/name
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        for parent in [path.parent,*path.parent.parents]:
            if not stat.S_ISDIR(parent.lstat().st_mode):raise RuntimeError('staged parent is not a real directory')
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
        with os.fdopen(fd,'wb') as stream:
            stream.write(text.encode('utf-8'));stream.flush();os.fsync(stream.fileno())
    raw=(json.dumps({'schema':1,'files':EXPECTED,'pure_controls':controls,'capture_lifecycle_controls_expected':4,'capture_lifecycle_controls_executed':False,'Main_actions':0,'Android_actions':0,'old_QA_epoch_invalid':True,'new_QA_epoch_qualified':False,'only_owned_root_written':True},indent=2)+'\n').encode()
    fd=os.open(ROOT/'stage-receipt.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    scope={'__name__':'frozen_framework_main_fence','__file__':str(source/'fenced_build.py')}
    exec(compile(packet['fenced_build.py'],str(source/'fenced_build.py'),'exec'),scope,scope)
    raise SystemExit(scope['run']({'controller_source':packet['framework_build.py'],
        'snapshot_source':packet['main_snapshot.py'],
        'snapshot_sha256':EXPECTED['main_snapshot.py']['sha256'],
        'lifecycle_source':packet['capture_lifecycle.py'],
        'root_supervisor_source':packet['root_snapshot_supervisor.py']}))
