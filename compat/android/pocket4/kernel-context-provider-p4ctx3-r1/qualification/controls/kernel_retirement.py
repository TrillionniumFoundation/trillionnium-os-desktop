import os,json,hashlib,stat,fcntl,subprocess,time
from pathlib import Path
B=Path('/home/qq/work/p4-kernel-p4ctx1-scm-8764-r3')
R=B/'control/image/result.json'
raw=R.read_bytes()
assert len(raw)==14996 and hashlib.sha256(raw).hexdigest()=='b38eb0a18281f13206348b48bdf2a3ea9d7d941d6cb2092c00195f7b6626fe30'
r=json.loads(raw)
assert r['passed'] and r['inputs_unchanged'] and r['whole_original_source_unchanged']
assert r['owned_unit']['InvocationID']=='0b2ec6583bc24a25b700fa087fd4848a'
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==r['owner']['boot_id']
q=subprocess.run(['/usr/bin/systemctl','--user','show','p4ctx1-scm-8764-r3-image.service','--property=LoadState,ActiveState,SubState,MainPID,InvocationID,ControlGroup'],capture_output=True,text=True,check=True,timeout=10)
s=dict(x.split('=',1) for x in q.stdout.splitlines() if '=' in x)
assert s.get('ActiveState') in ('inactive','failed') and s.get('MainPID')=='0' and s.get('ControlGroup')==''
assert not Path(r['cgroup']).exists()
cg=r['cgroup'].removeprefix('/sys/fs/cgroup')
left=[]
for p in Path('/proc').glob('[0-9]*'):
 try:
  if p.stat().st_uid!=os.getuid():continue
  if any((v:=x.split('::',1)[-1])==cg or v.startswith(cg+'/') for x in (p/'cgroup').read_text().splitlines()):left.append(int(p.name))
 except FileNotFoundError:pass
assert not left
old=[]
for pid,ticks in [(r['owner']['pid'],r['owner']['stat'].split(') ')[1].split()[19]),*[(x['pid'],x['start_ticks']) for x in r['commands']]]:
 try:alive=Path('/proc/%d/stat'%pid).read_text().split(') ')[1].split()[19]==ticks
 except FileNotFoundError:alive=False
 old.append({'pid':pid,'start_ticks':ticks,'same_process_alive':alive})
assert not any(x['same_process_alive'] for x in old)
p=B/'control/materialize.lock'
f=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
z=os.fstat(f)
assert stat.S_ISREG(z.st_mode) and z.st_ino==55840053 and z.st_uid==os.getuid() and z.st_nlink==1
fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
events=dict(x.split() for x in r['resources_final']['memory.events'].splitlines())
assert all(events.get(k)=='0' for k in ('oom','oom_kill','oom_group_kill'))
pins=[]
for a in [*r['artifacts'],r['complete_modules']['inventory'],r['config_after']]:
 p=Path(a['path']);st=p.lstat();assert stat.S_ISREG(st.st_mode) and st.st_nlink==1
 h=hashlib.sha256()
 with p.open('rb') as stream:
  while chunk:=stream.read(1024*1024):h.update(chunk)
 after=p.lstat()
 assert (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
 assert st.st_size==a['bytes'] and h.hexdigest()==a['sha256']
 pins.append(a)
v={'schema':'p4ctx3-full-independent-retirement-v1','passed':True,'source_generation':str(B),'verified_ns':time.time_ns(),'original_h_job':'1a1c3e0196a-cf39-30','original_result':{'path':str(R),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()},'unit':s,'expected_invocation':r['owned_unit']['InvocationID'],'cgroup_absent':True,'remaining_pids':left,'old_processes':old,'materialize_lock_inode_reacquired':z.st_ino,'memory_events':events,'artifacts_rehashed':pins,'module_count':r['complete_modules']['module_count'],'kernel_release':r['complete_modules']['kernel_release']}
dest=B/'control/image/independent-retirement.json'
data=(json.dumps(v,sort_keys=True,indent=2)+'\n').encode()
fd=os.open(dest,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
fcntl.flock(f,fcntl.LOCK_UN);os.close(f)
print(json.dumps({'result':{'path':str(dest),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()},'passed':True,'unit':s,'remaining_pids':left,'module_count':v['module_count'],'kernel_release':v['kernel_release']}))
