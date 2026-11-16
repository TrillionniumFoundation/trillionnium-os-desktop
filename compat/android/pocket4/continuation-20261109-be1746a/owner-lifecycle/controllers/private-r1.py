import os,stat,pathlib,hashlib,json,subprocess,time,datetime
source=pathlib.Path('/home/alex/work/pocket4-owner-lifecycle-integration-20261109-be1746a-r2/target/debug/deps/droidloom_supervisor-63ac7238d3bd685e')
expected='118f78a02234c9eca71f5c0f5aa20922c0b88b6b0f9dea2d657212b1ebcc3a9d'
stage=pathlib.Path('/var/lib/droidloom-owner-lifecycle-r2-private-20261109-be1746a-r1')
env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'}
def identity(s):return [s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
def pin(p):
 b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def protected():
 data=[pathlib.Path('/var/lib/droidloom/users/1000/data/data.img'),pathlib.Path('/var/lib/droidloom/users/1000/data/metadata.img')]
 pub=[pathlib.Path('/etc')/n for n in ['passwd','group','subuid','subgid','nsswitch.conf']]
 return {'data_metadata_only':[{'path':str(p),'identity':identity(p.lstat())} for p in data],
 'public_authority':[{'path':str(p),'identity':identity(p.lstat()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in pub],
 'boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'host_kernel':os.uname().release,
 'parent_namespaces':{n:[os.stat('/proc/self/ns/'+n).st_dev,os.stat('/proc/self/ns/'+n).st_ino] for n in ['user','pid','mnt','ipc','net','cgroup','uts']}}
assert os.geteuid()==0
fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
try:
 meta=os.fstat(fd);assert stat.S_ISREG(meta.st_mode) and meta.st_nlink==1 and meta.st_size==42320208
 chunks=[]
 while True:
  b=os.read(fd,1024*1024)
  if not b:break
  chunks.append(b)
 raw=b''.join(chunks)
 assert len(raw)==meta.st_size and hashlib.sha256(raw).hexdigest()==expected
 assert identity(meta)==identity(os.fstat(fd))==identity(source.lstat())
finally:os.close(fd)
stage.mkdir(mode=0o700)
binary=stage/'test-binary'
with binary.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
os.chmod(binary,0o500)
assert binary.lstat().st_uid==0 and binary.lstat().st_nlink==1
before=protected()
result={'schema':'pocket4-owner-lifecycle-r2-fixed-private-v1','started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'test_binary':pin(binary),'source_binary':pin(source),'before':before,'controls':[],'passed':False,'production_admission':False,'Android_starts':0,'original_data_body_opened':False,'host_accounts_or_grants_changed':False}
cases=[
 ('userns','production_namespace::tests::privileged_private_userns_mapping_controls','mapped supplementary groups set/read/cleared'),
 ('pid1','production_namespace::tree::tests::privileged_private_pid1_namespace_controls','actual direct-parent pidfd/proc and six namespace ownership verified')
]
try:
 for name,test,marker in cases:
  unit='pocket4-owner-lifecycle-r2-'+name+'-20261109-be1746a-r1.service'
  out=stage/name;out.mkdir(mode=0o700)
  argv=['/usr/bin/systemd-run','--quiet','--wait','--pipe','--unit',unit,
   '-p','User=root','-p','Group=root','-p','CPUQuota=100%','-p','CPUAffinity=0','-p','MemoryMax=4G',
   '-p','MemorySwapMax=0','-p','TasksMax=64','-p','RuntimeMaxSec=35','-p','TimeoutStopSec=5',
   '-p','KillMode=control-group','-p','PrivateTmp=yes','-p','PrivateDevices=yes','-p','PrivateNetwork=yes',
   '-p','ProtectSystem=strict','-p','ProtectHome=read-only','-p','ProtectKernelTunables=yes',
   '-p','ProtectKernelModules=yes','-p','ProtectControlGroups=yes','-p','NoNewPrivileges=yes',
   '-p','AmbientCapabilities=CAP_SETUID','-p','RestrictAddressFamilies=AF_UNIX',
   '-p','CapabilityBoundingSet=CAP_SYS_ADMIN CAP_SETUID CAP_SETGID CAP_SYS_PTRACE CAP_DAC_READ_SEARCH CAP_KILL',
   '--setenv=LC_ALL=C','--',str(binary),'--exact',test,'--ignored','--nocapture','--test-threads=1']
  (out/'intent.json').write_text(json.dumps({'argv':argv,'test_binary':pin(binary),'scope':'exact existing private fixed owned-child fixture; no HostAdmission or Android'},indent=2)+'\n')
  start=time.monotonic();p=subprocess.run(argv,env=env,capture_output=True,timeout=50)
  (out/'normal.stdout').write_bytes(p.stdout);(out/'normal.stderr').write_bytes(p.stderr)
  show=subprocess.run(['/usr/bin/systemctl','show',unit,'--property=LoadState,ActiveState,SubState,MainPID,Result,ExecMainCode,ExecMainStatus,ControlGroup,InvocationID'],env=env,capture_output=True,timeout=10)
  (out/'unit-show.stdout').write_bytes(show.stdout);(out/'unit-show.stderr').write_bytes(show.stderr)
  fields=dict(line.split('=',1) for line in show.stdout.decode().splitlines() if '=' in line)
  cg=fields.get('ControlGroup','')
  absent=not cg or not (pathlib.Path('/sys/fs/cgroup')/cg.lstrip('/')).exists()
  terminal=fields.get('MainPID')=='0' and absent and fields.get('ActiveState')=='inactive'
  if fields.get('LoadState')=='not-found':terminal=terminal and not (pathlib.Path('/sys/fs/cgroup/system.slice')/unit).exists()
  else:terminal=terminal and fields.get('LoadState')=='loaded' and fields.get('Result')=='success' and fields.get('ExecMainCode')=='1' and fields.get('ExecMainStatus')=='0'
  passed=p.returncode==0 and b'1 passed; 0 failed; 0 ignored' in p.stdout and marker.encode() in p.stdout and show.returncode==0 and not show.stderr and terminal
  rec={'name':name,'test':test,'argv':argv,'returncode':p.returncode,'elapsed_seconds':time.monotonic()-start,'stdout':pin(out/'normal.stdout'),'stderr':pin(out/'normal.stderr'),'unit':unit,'unit_fields':fields,'owned_unit_terminal':terminal,'owned_cgroup_absent':absent,'passed':passed}
  result['controls'].append(rec);(out/'result.json').write_text(json.dumps(rec,indent=2)+'\n')
  print(json.dumps({'name':name,'returncode':p.returncode,'passed':passed,'stdout':p.stdout.decode(),'stderr':p.stderr.decode(),'unit_fields':fields}),flush=True)
  assert passed,name
 result['after']=protected();result['protected_unchanged']=result['before']==result['after'];assert result['protected_unchanged']
 assert pin(source)['sha256']==expected==pin(binary)['sha256']
 result['passed']=True
except Exception as e:
 result['error']={'type':type(e).__name__,'message':str(e)}
 result['after']=protected();result['protected_unchanged']=result['before']==result['after']
finally:
 result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
 (stage/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'result':pin(stage/'result.json'),'passed':result['passed'],'controls_executed':len(result['controls']),'protected_unchanged':result['protected_unchanged'],'production_admission':False,'Android_starts':0}),flush=True)
raise SystemExit(0 if result['passed'] else 1)
