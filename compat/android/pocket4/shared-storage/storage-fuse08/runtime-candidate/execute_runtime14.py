from pathlib import Path
import hashlib,json,os,stat,subprocess,sys

assert os.geteuid()==0
root=Path('/home/alex/work/pocket4-storage-session-candidate-20261105-r12')
frozen=root/'frozen13';out=root/'build13'
expected={'build_runtime13.py':'757dc7cd0c04ee1d7ddb6f4fa05457867b410e6f4c4ce30f5656eb590b25c5a8',
 'smali_equivalence.py':'a895a4e3963f958ea6a6ff45b9d0c51f6239118b3a10fddff6d0f17e22e25f9f',
 'StorageSessionController.smali':'9c7070a802038cb1eaa4a18ebb3db12785aad1d7e96d37c50d5c62e92abe6e61'}
for p,uid in ((root,0),(frozen,0),(out,1000)):
    st=p.lstat()
    assert stat.S_ISDIR(st.st_mode) and st.st_uid==uid and st.st_gid==1000
assert not list(out.iterdir()),'PREVIOUS_BUILDER_MAY_HAVE_RUN'
assert {p.name for p in frozen.iterdir()}==set(expected)
before={}
for name,sha in expected.items():
    p=frozen/name;st=p.lstat()
    assert stat.S_ISREG(st.st_mode) and st.st_uid==0 and st.st_gid==1000 and st.st_nlink==1
    assert hashlib.sha256(p.read_bytes()).hexdigest()==sha
    before[name]=oct(stat.S_IMODE(st.st_mode))
before['directory']=oct(stat.S_IMODE(frozen.stat().st_mode))
for name in expected:os.chmod(frozen/name,0o440)
os.chmod(frozen,0o750)
for name,sha in expected.items():
    assert stat.S_IMODE((frozen/name).stat().st_mode)==0o440
    assert hashlib.sha256((frozen/name).read_bytes()).hexdigest()==sha
assert stat.S_IMODE(frozen.stat().st_mode)==0o750
print(json.dumps({'permission_correction':'isolated frozen13 only','before_modes':before,
 'after_directory_mode':'0o750','after_file_modes':'0o440','all_source_hashes_unchanged':True}),flush=True)
command=['/usr/bin/systemd-run','--quiet','--wait','--pipe','--collect',
 '--unit=pocket4-storage-assemble14-r12','--service-type=exec',
 '--property=User=alex','--property=Group=alex','--property=MemoryMax=2G',
 '--property=MemorySwapMax=0','--property=CPUQuota=200%','--property=AllowedCPUs=20,21',
 '--property=RuntimeMaxSec=320','--property=TimeoutStopSec=10',
 '--property=NoNewPrivileges=yes','--property=UMask=0077',
 '/usr/bin/python3','-I',str(frozen/'build_runtime13.py')]
p=subprocess.run(command,check=False)
sys.exit(p.returncode)
