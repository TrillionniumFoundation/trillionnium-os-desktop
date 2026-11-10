import hashlib,os,sys
from pathlib import Path
raw=sys.stdin.buffer.read(131073)
assert len(raw)<=131072 and hashlib.sha256(raw).hexdigest()=='ad93287b86624ea8444ebf37300c8b51ed899ac5511d904b81bc2283adcaf398'
root=Path('/home/alex/work/pocket4-clock-art-context-tools-20261105-r12-05')
assert os.geteuid()==0 and not os.path.lexists(root)
os.umask(0o077);root.mkdir(mode=0o750);os.chown(root,0,1000);os.chmod(root,0o750)
p=root/'read_context05.py'
fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o640)
with os.fdopen(fd,'wb') as f:
 f.write(raw);f.flush();os.fsync(f.fileno());os.fchown(f.fileno(),0,1000);os.fchmod(f.fileno(),0o640)
os.execv('/usr/bin/systemd-run',['/usr/bin/systemd-run','--quiet','--wait','--pipe','--collect',
 '--unit=p4-clock-art-context-20261105-r12-05','--property=Type=exec','--property=CPUQuota=100%',
 '--property=MemoryMax=536870912','--property=MemorySwapMax=0','--property=TasksMax=48',
 '--property=RuntimeMaxSec=90','--property=AllowedCPUs=20','--property=LimitCORE=0',
 '--property=LimitFSIZE=2097152','--property=TimeoutStopSec=5','--property=KillMode=control-group',
 '/usr/bin/python3','-I',str(p),'--execute'])
