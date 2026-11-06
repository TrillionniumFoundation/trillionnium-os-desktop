import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
ROOT = Path("/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-provider-build-03-20261106")
EXPECTED = {"main_snapshot.py":{"bytes":14294,"sha256":"1fd614b6e7b4900feff1a114c0cd221a1fb00fc0cea9878db1f3ae5672d561cf"},"frozen-work-inventory.py":{"bytes":48443,"sha256":"203dd7f4efdac01891a4c31fd79f2eb3204e3c8c2be5702988f0875307cce9ab"},"actual-work-preparation.json":{"bytes":11091,"sha256":"ab286f3939acfeb648a716ca15e5df348fef6b7007eb5651735fe8a7bda96b1c"},"expected-builder468-manifest.json":{"bytes":97525,"sha256":"e06522400f746b62016f82dfd3ec913b39cd9a8f33f9bca4f61a19a2787684ee"},"prior-framework-inner-terminal.json":{"bytes":2246,"sha256":"80f3508bab1884421af6db2f6d87537fd950100be009265b7e2efabc9b97fcdc"},"prior-framework-outer-terminal.json":{"bytes":1150,"sha256":"2c36ab1cc9ff6f181855f195f9c5b7bc0f58e7fb99d9c76e4871e64b143bf059"},"actual-published-source-manifest.json":{"bytes":97784,"sha256":"73a4cc1da8371482164aab2bc149498d03f481f212bb85cb4fda22b6b10c958d"},"actual-native-prebuilt-Android.bp":{"bytes":1017,"sha256":"d1eca99403572ee9d481e777febac8d4e062f44fd8844285ffc452b17beb531a"},"actual-provider-source-lock.json":{"bytes":96322,"sha256":"5c28f77e998cb75fd04de121e43a36fc3d8515c18249930268a2ffb6e5e372f7"},"framework_build.py":{"bytes":59292,"sha256":"03f0b4aecba20149ad7f1301ea823eb5e7e5ba1efa00d08c92c4fa7ecf482132"},"fenced_build.py":{"bytes":25481,"sha256":"ce3c0d1fc221e36055d75837a9bba337ccea33c8c7f89f8101a36defbd09c684"},"actual-builder468-result.json":{"bytes":161423,"sha256":"871e78f7ad8f3f3a12c165297e4fe566d96cfe3a2ce64a0d0010cffdb647b6b8"},"pure_controls.py":{"bytes":10963,"sha256":"5096a8a42c6f7cd1e1b6703ca25c1551a74ee58d55a8db8e68b195994d5a550e"},"capture_lifecycle.py":{"bytes":25227,"sha256":"4ffc5a7d6a54ad2cd4351ef30f90a12143614206953e97219f3d6cf5c6e1fc28"},"root_snapshot_supervisor.py":{"bytes":12041,"sha256":"f493a324cb5694f618d0fed3d5ed17ff90aa64924b671ea99550622f6090b5b7"},"prior-normal02-outer-terminal.json":{"bytes":24722,"sha256":"42b2d7b8749047df9e1d40ddf9b70b3f3e187c39ce6a15dd0f5721610e814c00"},"actual-resource-observation01.json":{"bytes":399,"sha256":"feb95f82087d7c68a8c8c42b54cf267b8f9c343ce41e49bb8193e96f49f050da"}}
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
