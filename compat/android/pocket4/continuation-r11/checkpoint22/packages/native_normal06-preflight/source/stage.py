import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
ROOT = Path("/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-provider-build-06-20261106")
EXPECTED = {"main_snapshot.py":{"bytes":14642,"sha256":"264100ef85e1792c437a4f450050041141288a0f25a4387af5774c52d0dcea06"},"frozen-work-inventory.py":{"bytes":48443,"sha256":"203dd7f4efdac01891a4c31fd79f2eb3204e3c8c2be5702988f0875307cce9ab"},"actual-work-preparation.json":{"bytes":11091,"sha256":"ab286f3939acfeb648a716ca15e5df348fef6b7007eb5651735fe8a7bda96b1c"},"expected-builder469-manifest.json":{"bytes":99327,"sha256":"88dc3c8020c436009862800ffdc5af97f50f6ae7efff832562c2784d66794701"},"prior-framework-inner-terminal.json":{"bytes":5239,"sha256":"6a525b9838f43579bc41b1106891f2f734a0c2d92b0c5cc355f7ab02b39eb2a8"},"prior-framework-outer-terminal.json":{"bytes":24689,"sha256":"273ba8a236253ee3873074a26f568144397044ebcfdd6f153ab8712b29ff70cf"},"actual-published-source-manifest.json":{"bytes":108555,"sha256":"afb23d210fda970a09482a14b9b38af1c92b5be505edd0eda2b76ce5ffc6067f"},"actual-native-prebuilt-Android.bp":{"bytes":1017,"sha256":"d1eca99403572ee9d481e777febac8d4e062f44fd8844285ffc452b17beb531a"},"actual-hal-provider-source-lock.json":{"bytes":96934,"sha256":"c7154e445c2bf1a4539418c68a04731538f9ac11050132571b911e706084f8fd"},"framework_build.py":{"bytes":62492,"sha256":"07b36baeaea9f6e1586f4adc8e13a5dd21ef1a642123391af0cbc8ed9d546596"},"fenced_build.py":{"bytes":25507,"sha256":"8c166d652af5828739f8c83cd2cf989b7e2d15de90e09b35b678d5d48b79b02b"},"actual-builder469-result.json":{"bytes":170316,"sha256":"3636057b9a20fc895657064da3fb66d8ded7e69ebfa5a5b92072a51b33f29fd5"},"pure_controls.py":{"bytes":10982,"sha256":"19d30bb230d148967d106cd43196baf402465a3c34b906ab25f08827951b7b3f"},"capture_lifecycle.py":{"bytes":25240,"sha256":"2dcf44609e6ef53e91b2d8e3a07c192fe65a7d44601f218dc8990272285d4dfe"},"root_snapshot_supervisor.py":{"bytes":12041,"sha256":"903ae227d9231a361c61fad6fd584c97a548bb5a41b09a4e5fa8824e13e02350"},"prior-normal02-outer-terminal.json":{"bytes":24722,"sha256":"42b2d7b8749047df9e1d40ddf9b70b3f3e187c39ce6a15dd0f5721610e814c00"},"actual-resource-observation01.json":{"bytes":399,"sha256":"feb95f82087d7c68a8c8c42b54cf267b8f9c343ce41e49bb8193e96f49f050da"}}
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
    if controls['state']!='PASS' or controls['passed']!=46:
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
