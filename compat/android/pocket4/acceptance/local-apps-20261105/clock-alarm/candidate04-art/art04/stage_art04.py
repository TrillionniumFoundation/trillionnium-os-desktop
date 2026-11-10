import hashlib,os,sys
from pathlib import Path
raw=sys.stdin.buffer.read(65537)
assert len(raw)<=65536 and hashlib.sha256(raw).hexdigest()=='2ac0b673f1b73b7e36542f961829b78c1b26d5549541a7b55cf4a8656f37797f'
root=Path('/home/alex/work/pocket4-clock-alarm-art-tools-20261105-r12-04')
assert os.geteuid()==0 and not os.path.lexists(root)
os.umask(0o077);root.mkdir(mode=0o750);os.chown(root,0,1000);os.chmod(root,0o750)
p=root/'verify_clock04.py';fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o640)
with os.fdopen(fd,'wb') as f:
 f.write(raw);f.flush();os.fsync(f.fileno());os.fchown(f.fileno(),0,1000);os.fchmod(f.fileno(),0o640)
os.execv('/usr/bin/systemd-run',['/usr/bin/systemd-run','--quiet','--wait','--pipe','--collect',
 '--unit=p4-clock-alarm-art-20261105-r12-04','--property=Type=exec','--property=CPUQuota=200%',
 '--property=MemoryMax=2147483648','--property=MemorySwapMax=0','--property=TasksMax=64',
 '--property=RuntimeMaxSec=240','--property=AllowedCPUs=20,21','--property=LimitCORE=0',
 '--property=LimitFSIZE=268435456','--property=TimeoutStopSec=5','--property=KillMode=control-group',
 '/usr/bin/python3','-I',str(p),'--execute'])
