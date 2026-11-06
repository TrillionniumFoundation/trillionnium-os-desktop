import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
ROOT = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-resume-build-01-20261106')
EXPECTED = {'main_snapshot.py': {'bytes': 6778, 'sha256': 'f909bdfcaedfef29fcc1ba6a994c49bc21e99850204bac7e0565548bcd7139cb'}, 'frozen-work-inventory.py': {'bytes': 48443, 'sha256': '203dd7f4efdac01891a4c31fd79f2eb3204e3c8c2be5702988f0875307cce9ab'}, 'actual-work-preparation.json': {'bytes': 11091, 'sha256': 'ab286f3939acfeb648a716ca15e5df348fef6b7007eb5651735fe8a7bda96b1c'}, 'expected-builder467-manifest.json': {'bytes': 91945, 'sha256': '71768da388021a870ef5f5516cc3efbfd956288a8fa74cb9b176b312f68d7605'}, 'prior-framework-inner-terminal.json': {'bytes': 28758, 'sha256': '139163acad47d9db707faa950e4b4dcecaf3e72b655bce8b6b3db089ce542bdf'}, 'prior-framework-outer-terminal.json': {'bytes': 1177, 'sha256': '3626270e88e72c4e46d8beee09b5351e1f7d53bab18043241204ca314855e04d'}, 'actual-staging-read03.json': {'bytes': 211213, 'sha256': 'c62f32b7002d043e4813eadd598f33d088a0f20cc9f562ddc19d35c2ccddf664'}, 'framework_build.py': {'bytes': 48395, 'sha256': '1d6f63947e5536c22978a6d30c3b35cc348d548409f772903eca1381d206e146'}, 'fenced_build.py': {'bytes': 9217, 'sha256': '624bc3f3feb8aca161cc4a63b5fefe95932a8714a4207ce3d419433b65d0be28'}, 'actual-builder467-result.json': {'bytes': 140163, 'sha256': 'cd9f61ca21dd83210299f24dd50b68f5aa7aeba7eab94ac9cada71271d660e28'}}
def main(packet):
    if os.getuid()!=1000 or os.geteuid()!=1000:raise RuntimeError('operator UID1000 required')
    if set(packet)!=set(EXPECTED):raise RuntimeError('staged source member set differs')
    for name,text in packet.items():
        path=PurePosixPath(name)
        if not name or path.is_absolute() or '..' in path.parts or str(path)!=name:raise RuntimeError('noncanonical staged source path')
        raw=text.encode('utf-8')
        if len(raw)!=EXPECTED[name]['bytes'] or hashlib.sha256(raw).hexdigest()!=EXPECTED[name]['sha256']:
            raise RuntimeError('staged source pin mismatch: '+name)
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
    raw=(json.dumps({'schema':1,'files':EXPECTED,'Main_actions':0,'only_owned_root_written':True},indent=2)+'\n').encode()
    fd=os.open(ROOT/'stage-receipt.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    scope={'__name__':'frozen_framework_main_fence','__file__':str(source/'fenced_build.py')}
    exec(compile(packet['fenced_build.py'],str(source/'fenced_build.py'),'exec'),scope,scope)
    raise SystemExit(scope['run']({'controller_source':packet['framework_build.py'],
        'snapshot_source':packet['main_snapshot.py'],
        'snapshot_sha256':EXPECTED['main_snapshot.py']['sha256']}))
