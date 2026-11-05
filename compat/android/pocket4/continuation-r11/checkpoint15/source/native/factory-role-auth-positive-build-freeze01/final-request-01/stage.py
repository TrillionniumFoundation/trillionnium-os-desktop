import hashlib,json,os,stat
from pathlib import Path
ROOT=Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/role-authorization-positive-host-build-01-20261105')
EXPECTED={'role-source-pins.json': {'bytes': 2735, 'sha256': 'd400255a4318ec5856692254cff062280021aeea5bf80662eb939a00d7586aa2'}, 'controls/registry_controls.cc': {'bytes': 33032, 'sha256': '950c5ec5d00f53ec9897dc03219db94c41278b753fae0e5c88a6ea0aa72a8b94'}, 'source/factory_context.cc': {'bytes': 5377, 'sha256': 'afd7ed0688ac5d4ea5cfc5611c7a7f17572184547c2628f1fe888d491ee1479a'}, 'source/factory_context.h': {'bytes': 954, 'sha256': 'b27148d779b5626a1677f7b2e10333645de90c68b67716b851104eab7ad6c7d1'}, 'source/role_authorization.cc': {'bytes': 38998, 'sha256': '5d9a43b4f9d51ddfe7896de563353c96f75856171d39c1af9a5816394247a03c'}, 'source/role_authorization.h': {'bytes': 5539, 'sha256': '320933ecda593fdb98b16b7bcd506d48ab81e15c0bd5903b38fe4dde49404d8c'}, 'build_registry.py': {'bytes': 23221, 'sha256': '52408f9534ad70bad398d5025e468f4b0df40835368f05054542f173a6d343de'}}
def main(packet):
    if os.getuid()!=1000 or os.geteuid()!=1000:raise RuntimeError('operator UID1000 required')
    if set(packet)!=set(EXPECTED):raise RuntimeError('packet members differ')
    for name,text in packet.items():
        raw=text.encode()
        if len(raw)!=EXPECTED[name]['bytes']or hashlib.sha256(raw).hexdigest()!=EXPECTED[name]['sha256']:
            raise RuntimeError('frozen packet differs: '+name)
    for path in [ROOT.parent,*ROOT.parent.parents]:
        if not stat.S_ISDIR(path.lstat().st_mode):raise RuntimeError('parent directory alias')
    parent=os.open(ROOT.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        before=os.fstat(parent);named=ROOT.parent.lstat()
        if (before.st_dev,before.st_ino,before.st_uid,before.st_gid,stat.S_IMODE(before.st_mode))!=(66306,34351895,1000,1000,0o700):
            raise RuntimeError('known private source parent identity differs')
        if (before.st_dev,before.st_ino)!=(named.st_dev,named.st_ino):raise RuntimeError('parent alias changed')
        os.umask(0o077);os.mkdir(ROOT.name,mode=0o700,dir_fd=parent)
        source=ROOT/'source';source.mkdir(mode=0o700)
        for name,text in packet.items():
            path=source/name;path.parent.mkdir(parents=True,exist_ok=True)
            for directory in [path.parent,*path.parent.parents]:
                if not stat.S_ISDIR(directory.lstat().st_mode):raise RuntimeError('source parent alias')
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
            with os.fdopen(fd,'wb')as stream:
                stream.write(text.encode());stream.flush();os.fsync(stream.fileno())
        receipt=(json.dumps({'schema':1,'files':EXPECTED,'registry_positive_executed':False,'Main_actions':0},indent=2)+'\n').encode()
        fd=os.open(ROOT/'stage-receipt.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
        with os.fdopen(fd,'wb')as stream:
            stream.write(receipt);stream.flush();os.fsync(stream.fileno())
        after=os.fstat(parent);named=ROOT.parent.lstat()
        if (after.st_dev,after.st_ino,after.st_uid,after.st_gid,stat.S_IMODE(after.st_mode))!=(66306,34351895,1000,1000,0o700)or (after.st_dev,after.st_ino)!=(named.st_dev,named.st_ino):
            raise RuntimeError('private parent changed during create-only staging')
    finally:os.close(parent)
    os.execve('/usr/bin/python3',['/usr/bin/python3','-I','-B',str(source/'build_registry.py'),'--execute-once'],
              {'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'})
