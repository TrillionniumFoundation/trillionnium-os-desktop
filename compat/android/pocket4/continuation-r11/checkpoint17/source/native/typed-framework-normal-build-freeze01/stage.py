import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
ROOT = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-build-01-20261105')
EXPECTED = {'framework_build.py': {'bytes': 38463, 'sha256': '12a86ce8fc03b281193a5942a5b7be0c1d7531f7f4e489f1eeca8db9688d1307'}, 'fenced_build.py': {'bytes': 9210, 'sha256': 'a9340df260f62cc8bbcce598c5de03cfc7d0d8c1ecde6b1987941d2c50e33c3b'}, 'main_snapshot.py': {'bytes': 6778, 'sha256': 'f909bdfcaedfef29fcc1ba6a994c49bc21e99850204bac7e0565548bcd7139cb'}, 'frozen-work-inventory.py': {'bytes': 48443, 'sha256': '203dd7f4efdac01891a4c31fd79f2eb3204e3c8c2be5702988f0875307cce9ab'}, 'actual-work-preparation.json': {'bytes': 11091, 'sha256': 'ab286f3939acfeb648a716ca15e5df348fef6b7007eb5651735fe8a7bda96b1c'}, 'actual-builder466-result.json': {'bytes': 98764, 'sha256': '2d6c80a29e957b1e97764d8785257eb47c3d0b899f301e64c9a9c418e96ea0ab'}, 'expected-builder466-manifest.json': {'bytes': 91758, 'sha256': 'f09b908745cf294735f897a64d0d956a207d27f78277781f536d5059bb856d0f'}}
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
