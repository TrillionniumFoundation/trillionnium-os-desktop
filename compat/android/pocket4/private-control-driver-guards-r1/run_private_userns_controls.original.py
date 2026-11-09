#!/usr/bin/python3
"""Run only the reviewed private syscall control; not a production admission API."""
import hashlib,json,os,stat,subprocess,sys,time
from pathlib import Path
ROOT=Path("/home/alex/work/pocket4-android-final/qualification/production-namespace-broker-source-20261109-8b88-r2")
OUT=Path("/home/alex/work/pocket4-android-final/qualification/production-namespace-broker-private-controls-20261109-8b88-r2")
UNIT="pocket4-namespace-broker-private-controls-20261109-8b88-r2.service"
E={"PATH":"/usr/sbin:/usr/bin:/sbin:/bin","LC_ALL":"C","PYTHONDONTWRITEBYTECODE":"1"}
def identity(s):return [s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
def exact(ref,limit=67108864):
 p=Path(ref["path"]);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  b=os.fstat(fd);assert stat.S_ISREG(b.st_mode) and b.st_uid==0 and b.st_nlink==1 and not b.st_mode&0o022
  assert b.st_size==ref["bytes"] and b.st_size<=limit
  raw=bytearray()
  while len(raw)<=b.st_size:
   q=os.read(fd,min(1048576,b.st_size+1-len(raw)))
   if not q:break
   raw.extend(q)
  assert len(raw)==b.st_size and hashlib.sha256(raw).hexdigest()==ref["sha256"]
  assert identity(os.fstat(fd))==identity(b)==identity(os.lstat(p))
  return bytes(raw)
 finally:os.close(fd)
def pin(p):
 b=p.read_bytes();return {"path":str(p),"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
def write(name,body):
 p=OUT/name
 with p.open("xb") as f:f.write(body);f.flush();os.fsync(f.fileno())
 return pin(p)
def protected():
 p=[Path("/var/lib/droidloom/users/1000/data/data.img"),Path("/var/lib/droidloom/users/1000/data/metadata.img")]
 files=[Path("/etc/passwd"),Path("/etc/group"),Path("/etc/subuid"),Path("/etc/subgid"),Path("/etc/nsswitch.conf")]
 return {"data_metadata_only":[{"path":str(x),"identity":identity(os.lstat(x))} for x in p],
         "public_authority":[{"path":str(x),"identity":identity(os.lstat(x)),"sha256":hashlib.sha256(x.read_bytes()).hexdigest()} for x in files],
         "boot_id":Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
         "host_kernel":os.uname().release,
         "parent_ns":[{"kind":n,"dev":os.stat("/proc/self/ns/"+n).st_dev,"ino":os.stat("/proc/self/ns/"+n).st_ino} for n in ["user","pid","mnt","ipc","net","cgroup","uts"]]}
def main():
 assert os.geteuid()==0 and sys.argv[1:]==["--run"],"only explicit reviewed --run is supported"
 manifest=json.loads((ROOT/"manifest.json").read_text())
 assert manifest["schema"]=="pocket4-owned-userns-source-custody-v1"
 for r in manifest["members"]:exact(r)
 assert not OUT.exists();OUT.mkdir(mode=0o700)
 before=protected()
 binary=manifest["test_binary"];exact(binary)
 argv=["/usr/bin/systemd-run","--quiet","--wait","--pipe","--unit",UNIT,
  "-p","User=root","-p","Group=root","-p","CPUQuota=100%","-p","MemoryMax=4G",
  "-p","MemorySwapMax=0","-p","TasksMax=64","-p","RuntimeMaxSec=35",
  "-p","TimeoutStopSec=5","-p","KillMode=control-group","-p","PrivateTmp=yes",
  "-p","PrivateDevices=yes","-p","PrivateNetwork=yes","-p","ProtectSystem=strict",
  "-p","ProtectHome=read-only","-p","ProtectKernelTunables=yes","-p","ProtectKernelModules=yes",
  "-p","ProtectControlGroups=yes","-p","NoNewPrivileges=yes","-p","RestrictAddressFamilies=AF_UNIX",
  "-p","CapabilityBoundingSet=CAP_SYS_ADMIN CAP_SETUID CAP_SETGID CAP_SYS_PTRACE CAP_DAC_READ_SEARCH CAP_KILL",
  "--setenv=LC_ALL=C","--",binary["path"],
  "--exact","production_namespace::tests::privileged_private_userns_mapping_controls",
  "--ignored","--nocapture","--test-threads=1"]
 write("intent.json",(json.dumps({"argv":argv,"source_manifest":pin(ROOT/"manifest.json"),"before":before,"production_admission":False,"android":0},sort_keys=True,indent=2)+"\n").encode())
 start=time.monotonic();p=subprocess.run(argv,env=E,capture_output=True,timeout=50)
 stdout=write("normal.stdout",p.stdout);stderr=write("normal.stderr",p.stderr)
 show=subprocess.run(["/usr/bin/systemctl","show",UNIT,"--property=ActiveState,SubState,MainPID,Result,ExecMainCode,ExecMainStatus,ControlGroup,InvocationID"],env=E,capture_output=True,timeout=10)
 showref=write("unit-show.stdout",show.stdout);write("unit-show.stderr",show.stderr)
 fields=dict(line.split("=",1) for line in show.stdout.decode().splitlines() if "=" in line)
 after=protected()
 result={"schema":1,"scope":"private fixed owned-child syscall control only; no HostAdmission token",
  "argv":argv,"returncode":p.returncode,"elapsed_seconds":time.monotonic()-start,"stdout":stdout,"stderr":stderr,
  "unit":UNIT,"unit_show":showref,"unit_fields":fields,"before":before,"after":after,
  "production_admission":False,"android":0,"host_accounts_or_grants_changed":False,"original_data_body_opened":False}
 # Always preserve actual outcomes before qualification predicates.
 ref=write("result.json",(json.dumps(result,sort_keys=True,indent=2)+"\n").encode())
 assert p.returncode==0,(ref,p.returncode)
 assert b"1 passed; 0 failed; 0 ignored" in p.stdout
 assert b"mapped supplementary groups set/read/cleared" in p.stdout
 assert show.returncode==0 and not show.stderr
 assert fields.get("ActiveState")=="inactive" and fields.get("MainPID")=="0"
 assert fields.get("Result")=="success" and fields.get("ExecMainCode")=="1" and fields.get("ExecMainStatus")=="0"
 assert not fields.get("ControlGroup") or not (Path("/sys/fs/cgroup")/fields["ControlGroup"].lstrip("/")).exists()
 assert before==after,"protected host metadata or public authority changed"
 for r in manifest["members"]:exact(r)
 print(json.dumps({"result":ref,"actual_private_control_passed":True,"production_admission":False,"android":0},sort_keys=True))
main()
