import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
ROOT = Path("/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-native-provider-build-04-20261106")
EXPECTED = {'framework_build.py': {'bytes': 60970, 'sha256': '16e1e03e466c946dcb4c72f5fc900f2552bba919fdcf49ba136c41d0e544cdc1'}, 'fenced_build.py': {'bytes': 25488, 'sha256': '7d7ae7e05b6446a56dc4a38ee23d194d4e159dadaf682e59d7a8dfe5215f8887'}, 'pure_controls.py': {'bytes': 10969, 'sha256': '359adbeee68c536f6f2925503ff1c237683985dfab327fde0ad1ff1e6bd41a9a'}, 'parent-normal03-framework_build.py': {'bytes': 59292, 'sha256': '03f0b4aecba20149ad7f1301ea823eb5e7e5ba1efa00d08c92c4fa7ecf482132'}, 'main_snapshot.py': {'bytes': 14294, 'sha256': '1fd614b6e7b4900feff1a114c0cd221a1fb00fc0cea9878db1f3ae5672d561cf'}, 'capture_lifecycle.py': {'bytes': 25227, 'sha256': '4ffc5a7d6a54ad2cd4351ef30f90a12143614206953e97219f3d6cf5c6e1fc28'}, 'root_snapshot_supervisor.py': {'bytes': 12041, 'sha256': 'f493a324cb5694f618d0fed3d5ed17ff90aa64924b671ea99550622f6090b5b7'}, 'frozen-work-inventory.py': {'bytes': 48443, 'sha256': '203dd7f4efdac01891a4c31fd79f2eb3204e3c8c2be5702988f0875307cce9ab'}, 'actual-work-preparation.json': {'bytes': 11091, 'sha256': 'ab286f3939acfeb648a716ca15e5df348fef6b7007eb5651735fe8a7bda96b1c'}, 'actual-native-prebuilt-Android.bp': {'bytes': 1017, 'sha256': 'd1eca99403572ee9d481e777febac8d4e062f44fd8844285ffc452b17beb531a'}, 'actual-builder469-result.json': {'bytes': 37384, 'sha256': 'a14dde5d3a2e85fe44d90c651527c8c8402d341403ef84a7bc92b93252de72b9'}, 'actual-builder469-qualification.json': {'bytes': 65386, 'sha256': 'f31bb31d29967bacdb0842eea99dae65f8b67425f26f10063c3d84099367fd64'}, 'expected-builder469-manifest.json': {'bytes': 97964, 'sha256': 'd9340351c9653b10dfd0882afbff5ff4fc11dafaa6083191ed2a8fdb5c8dd934'}, 'prior-framework-inner-terminal.json': {'bytes': 5239, 'sha256': '6a525b9838f43579bc41b1106891f2f734a0c2d92b0c5cc355f7ab02b39eb2a8'}, 'prior-framework-outer-terminal.json': {'bytes': 24689, 'sha256': '273ba8a236253ee3873074a26f568144397044ebcfdd6f153ab8712b29ff70cf'}, 'actual-published-source-manifest.json': {'bytes': 108555, 'sha256': 'afb23d210fda970a09482a14b9b38af1c92b5be505edd0eda2b76ce5ffc6067f'}, 'actual-provider-source-lock.json': {'bytes': 96957, 'sha256': '72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d'}}
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
    if controls['state']!='PASS' or controls['passed']!=45:
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
