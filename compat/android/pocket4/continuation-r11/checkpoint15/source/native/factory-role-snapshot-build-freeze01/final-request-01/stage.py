import hashlib,json,os,stat
from pathlib import Path
ROOT=Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/role-authorized-snapshot-host-build-01-20261105')
EXPECTED={'snapshot-source-pins.json': {'bytes': 4422, 'sha256': '53e90ef34ab51ae8b9700f93419c3c050665fb0ea5a50482417b48aa860497e1'}, 'controls/snapshot_controls.cc': {'bytes': 14854, 'sha256': 'fb15f8f56474f445caaa7da7e9b96d7623a4f0ce18eb00862be3867ecc6fd760'}, 'include/berberis/kernel_api/proc_maps_factory_protocol.h': {'bytes': 5051, 'sha256': 'b942f4c76fc34d8a124ecc8bb1af8503e4bc93a58f87b654771b3793072f2df9'}, 'include/berberis/kernel_api/proc_maps_kernel_statfs.h': {'bytes': 2480, 'sha256': '77f72e71bb8e5f9239287cfb4899fc4d83c38b61f3cd78cd93909da792d751a0'}, 'include/berberis/kernel_api/proc_maps_linux_compat.h': {'bytes': 2072, 'sha256': '131d1eef8d9f789876c965fa2d827b21a59fc64ab7886fa1f78d95623114370c'}, 'references/factory_main.v2.cc': {'bytes': 28588, 'sha256': '18d8134ed6c2077088104d9b5dc22ccfe1c93f73a87ee880595a9eb89821e2b9'}, 'references/registry_controls.cc': {'bytes': 33258, 'sha256': '5ea30aeb58eebeb09542e9ee68c07e1be7ff92fedcc3141f4d336490458e1a94'}, 'source/factory_context.cc': {'bytes': 5377, 'sha256': 'afd7ed0688ac5d4ea5cfc5611c7a7f17572184547c2628f1fe888d491ee1479a'}, 'source/factory_context.h': {'bytes': 954, 'sha256': 'b27148d779b5626a1677f7b2e10333645de90c68b67716b851104eab7ad6c7d1'}, 'source/proc_maps_factory_wire.cc': {'bytes': 8661, 'sha256': '4a39b504188c5eaf56320f4e10d48285ea8954d816a98a2d5b7b684d38c48608'}, 'source/role_authorization.cc': {'bytes': 38998, 'sha256': '5d9a43b4f9d51ddfe7896de563353c96f75856171d39c1af9a5816394247a03c'}, 'source/role_authorization.h': {'bytes': 5539, 'sha256': '320933ecda593fdb98b16b7bcd506d48ab81e15c0bd5903b38fe4dde49404d8c'}, 'source/role_snapshot.cc': {'bytes': 9965, 'sha256': 'c2c14486d21e852a971835abd0f36631b4eb37b0a53fbcd5697cf4c11c8e4994'}, 'source/role_snapshot.h': {'bytes': 1243, 'sha256': '24ca056261cf6928bcd0be38f9669290287ac5529629cc77901313060af97bd4'}, 'build_snapshot.py': {'bytes': 24468, 'sha256': '15e7f8ab241a89e71fae1135dcf5429f198253fb1515347aac1449046a3af77d'}}
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
    os.execve('/usr/bin/python3',['/usr/bin/python3','-I','-B',str(source/'build_snapshot.py'),'--execute-once'],
              {'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'})
