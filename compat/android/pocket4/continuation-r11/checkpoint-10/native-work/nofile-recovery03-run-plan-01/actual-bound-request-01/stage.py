import hashlib,json,os,stat
from pathlib import Path
ROOT=Path('/home/alex/work/pocket4-nofile-owner-recovery03-host-run-01-20261105')
EXPECTED={'run_nofile.py': {'bytes': 25493, 'sha256': 'bfc9d6b0a7188236a5b436030456e0bbe86ceac4630bc24fc65ff5038242ece0'}, 'actual-build-result.json': {'bytes': 60254, 'sha256': 'bb575a8030aa086e9622dd25c814190821199991461e1f0b094aca44f7e76fdd'}, 'CASE_PLAN.json': {'bytes': 10630, 'sha256': '5ad4e7985eee2d1c9a7dd1322a2c933e74d734a5c98a37d4bb0c5b88e101ee09'}}
def main(packet):
    if os.getuid()!=1000 or os.geteuid()!=1000:raise RuntimeError('ordinary operator UID1000 required')
    if set(packet)!=set(EXPECTED):raise RuntimeError('runtime packet member set differs')
    for name,text in packet.items():
        raw=text.encode()
        if len(raw)!=EXPECTED[name]['bytes'] or hashlib.sha256(raw).hexdigest()!=EXPECTED[name]['sha256']:
            raise RuntimeError('runtime packet pin differs: '+name)
    for parent in [ROOT.parent,*ROOT.parent.parents]:
        if not stat.S_ISDIR(parent.lstat().st_mode):raise RuntimeError('owned runtime root parent aliases directory')
    os.umask(0o077);ROOT.mkdir(mode=0o700);source=ROOT/'control-source';source.mkdir(mode=0o700)
    for name,text in packet.items():
        fd=os.open(source/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
        with os.fdopen(fd,'wb') as stream:
            stream.write(text.encode());stream.flush();os.fsync(stream.fileno())
    os.execve('/usr/bin/python3',['/usr/bin/python3','-I','-B',str(source/'run_nofile.py'),'--execute-once'],
              {'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'})
