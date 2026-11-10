import os,stat,fcntl,hashlib,json,subprocess,time
from pathlib import Path
assert os.getuid()==os.geteuid()==0
fd=os.open('/home/alex/work/pocket4-android-final/.qpr1-kernel-control-8b88.lock',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
ls=os.fstat(fd)
assert stat.S_ISREG(ls.st_mode) and ls.st_uid==0 and ls.st_nlink==1 and ls.st_size==0
assert ls.st_ino==41719533 and stat.S_IMODE(ls.st_mode)==0o600
fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
os.initgroups('alex',1000);os.setgid(1000);os.setuid(1000)
assert os.getuid()==os.geteuid()==1000
os.environ.clear()
os.environ.update(HOME='/home/alex',PATH='/usr/sbin:/usr/bin:/sbin:/bin',LANG='C.UTF-8',XDG_RUNTIME_DIR='/run/user/1000',DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/1000/bus')
os.umask(0o077)
B=Path('/home/alex/work/p4-context-provider-runtime-8764-r1')
def pin(p,expected=None):
 p=Path(p); assert p.is_relative_to(B)
 s=p.lstat();assert stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_size<=64*1024**2
 f=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  assert (os.fstat(f).st_dev,os.fstat(f).st_ino)==(s.st_dev,s.st_ino)
  with os.fdopen(os.dup(f),'rb') as stream: b=stream.read()
  z=p.lstat();assert (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)==(z.st_dev,z.st_ino,z.st_size,z.st_mtime_ns,z.st_ctime_ns)
 finally:os.close(f)
 r={'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'dev':s.st_dev,'ino':s.st_ino}
 if expected:assert (r['bytes'],r['sha256'])==expected
 return r,b
host={'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'kernel':os.uname().release,'active_lsm':Path('/sys/kernel/security/lsm').read_text().strip()}
R={'schema':'p4ctx3-independent-runtime-retirement-v1','started_ns':time.time_ns(),'host':host,'lock_inode':ls.st_ino,'original_lock_reacquired':True,'records':[],'Android_started':False,'host_installations':0,'host_reboots':0,'host_policy_loads':0,'host_module_loads':0}
cgroups=set();old=[]
for name,size,digest,count,failed in (
 ('baseline',27254,'f66494a0fa7c2338877e90db29e4dfb9c1cea51a60396d8a48fbed41e937cc50',47,6),
 ('previous',27423,'e4c174ebfdf5c2430f42a4c2cca270d0af8e2c2040db733d7485252b7f78c76e',47,2),
 ('candidate',29657,'bd65f7335a6ee7685812a3efa199019a869cd5db13191295faed3af26893c616',47,0),
 ('inactive',15678,'4159aa71cbed6b90a8f3cc06848cd12c11a20eaa5e2caaa0f1c899a826feafe8',12,0)):
 result,b=pin(B/(name+'-vm-r5')/'result.json',(size,digest));d=json.loads(b)
 assert d['passed'] and d['actual_qemu_exited'] and d['owned_unit_retired'] and d['cgroup_retired']
 assert d['inputs_unchanged'] and d['host_identity_unchanged'] and not d['after_qemu'] and d['memory_events_clean']
 assert d['host_before']==d['host_after']==host and d['lock_inode']==ls.st_ino
 assert len(d['guest_summary'])==1 and d['guest_summary'][0]['cases']==count and d['guest_summary'][0]['failed']==failed and d['guest_summary'][0]['setup_error']==0
 assert d['guest_disks']==d['guest_network_devices']==d['host_installations']==d['host_policy_loads']==d['host_module_loads']==d['host_reboots']==0
 assert not d['Android_started'] and not d['production_acceptance']
 for item in d['inputs'].values():
  actual,_=pin(item['path'])
  assert actual==item
 unit='p4-context-runtime-8764-'+name+'-r5.service'
 p=subprocess.run(['/usr/bin/systemctl','--user','show',unit,'--property=LoadState,ActiveState,SubState,MainPID,ControlGroup,InvocationID'],capture_output=True,text=True,timeout=15)
 state=dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line)
 assert state.get('ActiveState') in ('inactive','failed') and state.get('MainPID')=='0' and not state.get('ControlGroup')
 rows=[s for s in d['samples'] if s.get('ControlGroup')]
 assert rows and all(s['InvocationID']==d['actual_process']['invocation'] and s['MemoryMax']=='1610612736' and s['MemorySwapMax']=='0' and s['CPUQuotaPerSecUSec']=='2s' and s['CPUAffinity']=='20-21' and s['KillMode']=='control-group' for s in rows)
 for s in rows:
  cgroups.add(s['ControlGroup']);assert not Path('/sys/fs/cgroup'+s['ControlGroup']).exists()
 assert all(all(e.get(k)=='0' for k in ('oom','oom_kill','oom_group_kill')) for e in d['memory_events_observed'])
 actual=d['actual_process'];alive=False
 try:alive=Path('/proc/%d/stat'%actual['pid']).read_text().rsplit(') ',1)[1].split()[19]==actual['starttime']
 except FileNotFoundError:pass
 assert not alive
 old.append({'pid':actual['pid'],'starttime':actual['starttime'],'same_process_alive':alive})
 R['records'].append({'arm':name,'result':result,'summary':d['guest_summary'][0],'kernel':d['guest_boot'][0]['kernel'],'unit':state,'invocation_id':actual['invocation'],'affinity':actual['affinity'],'input_count_verified':len(d['inputs']),'memory_events':d['memory_events_observed']})
remaining=[];qemu=[]
for p in Path('/proc').glob('[0-9]*'):
 try:
  if p.stat().st_uid!=1000:continue
  groups=[line.split('::',1)[-1] for line in (p/'cgroup').read_text().splitlines()]
  if any(g==cg or g.startswith(cg+'/') for g in groups for cg in cgroups):remaining.append(int(p.name))
  a=(p/'cmdline').read_bytes().split(b'\0')
  if a and os.path.basename(a[0].decode()).startswith('qemu-system'):qemu.append(int(p.name))
 except FileNotFoundError:pass
assert not remaining and not qemu
R.update(old_processes=old,remaining_pids=remaining,remaining_qemu_pids=qemu,cgroups_absent=sorted(cgroups),passed=True,finished_ns=time.time_ns())
target=B/'control/runtime-independent-retirement-r5.json'
data=(json.dumps(R,indent=2,sort_keys=True)+'\n').encode()
out=os.open(target,os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_WRONLY,0o600)
with os.fdopen(out,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
result,_=pin(target)
fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
print(json.dumps({'result':result,'passed':True,'original_lock_inode':ls.st_ino,'old_processes':old,'remaining_pids':remaining,'remaining_qemu_pids':qemu}))
