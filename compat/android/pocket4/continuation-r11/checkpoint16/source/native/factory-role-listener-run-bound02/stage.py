import hashlib,json,os,stat
from pathlib import Path
ROOT=Path('/run/pocket4-role-listener-lifetime-host-run-02-20261105')
EXPECTED={'run_listener.py': {'bytes': 31574, 'sha256': 'ad636a738b4b3113c8a10b323ed69d37a354ed6c639c1b7b2faac52760273b11'}, 'actual-build-result.json': {'bytes': 132102, 'sha256': 'e54f6613ecdc546c0a57da4007f330887d32ad04e2fb5f641accffc5001e0c95'}, 'CASE_PLAN.json': {'bytes': 2283, 'sha256': 'b440df29027c3b0516ef09e457346a1577d42545a4e373e69d1b22821f055a9a'}}
def main(packet):
    if (os.getuid(),os.geteuid(),os.getgid(),os.getegid())!=(0,0,0,0):
        raise RuntimeError('exact root staging identity required')
    if set(packet)!=set(EXPECTED):raise RuntimeError('runtime packet members differ')
    for name,text in packet.items():
        raw=text.encode()
        if len(raw)!=EXPECTED[name]['bytes']or hashlib.sha256(raw).hexdigest()!=EXPECTED[name]['sha256']:
            raise RuntimeError('runtime packet pin differs: '+name)
    if ROOT.parent!=Path('/run'):raise RuntimeError('root runtime parent escaped')
    for path in [ROOT.parent,*ROOT.parent.parents]:
        st=path.lstat()
        if not stat.S_ISDIR(st.st_mode)or st.st_uid!=0 or st.st_gid!=0 or stat.S_IMODE(st.st_mode)&0o022:
            raise RuntimeError('root runtime ancestor is not private against nonroot writers')
    parent=os.open(ROOT.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        before=os.fstat(parent);named=ROOT.parent.lstat()
        if (before.st_dev,before.st_ino)!=(named.st_dev,named.st_ino):raise RuntimeError('root parent alias changed')
        os.umask(0o077);os.mkdir(ROOT.name,mode=0o700,dir_fd=parent)
        source=ROOT/'control-source';source.mkdir(mode=0o700)
        for name,text in packet.items():
            if '/'in name or name in ['.','..']:raise RuntimeError('flat runtime packet required')
            fd=os.open(source/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
            with os.fdopen(fd,'wb')as stream:
                stream.write(text.encode());stream.flush();os.fsync(stream.fileno())
        after=os.fstat(parent);named=ROOT.parent.lstat()
        if (before.st_dev,before.st_ino,before.st_uid,before.st_gid,stat.S_IMODE(before.st_mode))!=           (after.st_dev,after.st_ino,after.st_uid,after.st_gid,stat.S_IMODE(after.st_mode))or           (after.st_dev,after.st_ino)!=(named.st_dev,named.st_ino):
            raise RuntimeError('root parent changed during create-only staging')
    finally:os.close(parent)
    os.execve('/usr/bin/python3',['/usr/bin/python3','-I','-B',str(source/'run_listener.py'),'--execute-once'],
              {'PATH':'/usr/bin:/bin','HOME':'/root','LANG':'C','LC_ALL':'C'})
