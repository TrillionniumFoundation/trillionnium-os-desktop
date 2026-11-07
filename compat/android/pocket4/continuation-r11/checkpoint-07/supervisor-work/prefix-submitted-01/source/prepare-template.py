from pathlib import Path
import datetime,hashlib,json,os,re,resource,stat,subprocess,sys,traceback

# Instantiated only by the separately reviewed stable-key host-build request.
CFG=__PAYLOAD__
OUT=Path('/home/alex/work/pocket4-relay-prefix-r11-source-05-01')
BASE=Path('/home/alex/work/pocket4-relay-prefix-r11-owned')
SOURCES=('full_prefix_control.py','prefix_coordinator.py','prefix_probe.c',
         'test_prefix_control.py','test_prefix_coordinator.py')
def need(v,m):
 if not v:raise RuntimeError(m)
def sha(b):return hashlib.sha256(b).hexdigest()
def put(p,b,mode=0o600):
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,mode)
 with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
def inventory():
 return {n:{'bytes':(OUT/'source'/n).stat().st_size,'sha256':sha((OUT/'source'/n).read_bytes())} for n in SOURCES}
need(os.getuid()==os.geteuid()==os.getgid()==os.getegid()==0,'exact root builder required for root-owned artifact controls')
need(set(CFG['files'])==set(SOURCES),'complete five-source payload required')
need(os.uname().machine=='x86_64','host prefix probe is x86_64 only')
os.umask(0o077);resource.setrlimit(resource.RLIMIT_CORE,(0,0))
OUT.mkdir(mode=0o700);(OUT/'source').mkdir(mode=0o700);(OUT/'bin').mkdir(mode=0o700)
report={'schema':1,'scope':'matching host compilation and ordinary/pure controls only','success':False,
 'source_freeze_manifest_sha256':CFG['manifest_sha256'],'commands':[],'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'namespace_actions':0,'systemd_unit_actions':0,'network_actions':0,'Android_operations':0,'Main_actions':0,
 'runtime_prefix_qualified':False,'actual_Rust_Owner_executed':False,'production_ready':False}
ENV={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1','TMPDIR':str(OUT/'tmp')}
(OUT/'tmp').mkdir(mode=0o700)
def run(argv,timeout=30,pass_fds=()):
 i=len(report['commands'])
 try:p=subprocess.run(argv,env=ENV,cwd=OUT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,pass_fds=pass_fds)
 except subprocess.TimeoutExpired as e:
  a,b=e.stdout or b'',e.stderr or b''
  put(OUT/('command-%02d.stdout'%i),a);put(OUT/('command-%02d.stderr'%i),b)
  report['commands'].append({'argv':argv,'returncode':None,'timed_out':True,'stdout_sha256':sha(a),'stderr_sha256':sha(b)})
  raise
 put(OUT/('command-%02d.stdout'%i),p.stdout);put(OUT/('command-%02d.stderr'%i),p.stderr)
 report['commands'].append({'argv':argv,'returncode':p.returncode,'stdout':p.stdout.decode(),'stderr':p.stderr.decode(),
  'stdout_sha256':sha(p.stdout),'stderr_sha256':sha(p.stderr)})
 return p
try:
 for n,row in CFG['files'].items():
  b=row['text'].encode();need(len(b)==row['bytes'] and sha(b)==row['sha256'],'payload differs '+n)
  put(OUT/'source'/n,b)
 report['inputs_before']=inventory()
 need(run(['/usr/bin/cc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(OUT/'source/prefix_probe.c'),'-o',str(OUT/'bin/prefix-probe')]).returncode==0,'strict host probe compilation')
 counts={}
 for n,expected in [('test_prefix_control.py',16),('test_prefix_coordinator.py',24)]:
  p=run(['/usr/bin/python3','-I','-B',str(OUT/'source'/n)])
  match=re.search(rb'Ran ([0-9]+) tests',p.stderr)
  need(p.returncode==0 and match and int(match.group(1))==expected,'matching controls failed '+n)
  counts[n]=expected
 report['python_tests_passed']=counts
 binary=OUT/'bin/prefix-probe'
 need(run([str(binary),'--fd-check'],5).returncode==0,'ordinary capability-free exec')
 fd=os.open('/dev/null',os.O_RDONLY|os.O_CLOEXEC)
 try:
  for fixed in (198,199,200,201):
   try:os.fstat(fixed)
   except OSError as e:need(e.errno==9,'fixed slot inspection failed')
   else:raise RuntimeError('fixed capability slot already owned')
   os.dup2(fd,fixed,inheritable=True)
   try:need(run([str(binary),'--fd-check'],5,(fixed,)).returncode==93,'inherited capability not detected')
   finally:os.close(fixed)
 finally:os.close(fd)
 need(run([str(binary),'development-enter','--spec','/not-opened'],5).returncode==97,'ordinary process did not reject before namespace contract')
 report['native_ordinary_controls_passed']=6
 report['inputs_after']=inventory();need(report['inputs_after']==report['inputs_before'],'matching source changed')
 info=binary.stat();b=binary.read_bytes()
 need(info.st_uid==info.st_gid==0 and stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_mode&0o6022==0,'compiled probe metadata differs')
 need(b[:4]==b'\x7fELF' and b[4:6]==b'\x02\x01' and int.from_bytes(b[18:20],'little')==62,'compiled probe is not host x86_64 ELF')
 report['probe']={'path':str(binary),'bytes':len(b),'sha256':sha(b),'device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid,'gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode)}
 if not os.path.lexists(BASE):BASE.mkdir(mode=0o700)
 base=BASE.lstat();need(stat.S_ISDIR(base.st_mode) and base.st_uid==base.st_gid==0 and base.st_mode&0o077==0,'common owned attempt base is not root-private')
 report['owned_attempt_base']={'path':str(BASE),'device':base.st_dev,'inode':base.st_ino,'uid':base.st_uid,'gid':base.st_gid,'mode':stat.S_IMODE(base.st_mode)}
 report['success']=True
except BaseException as e:
 report['error']=repr(e);report['traceback']=traceback.format_exc()
finally:
 report['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
 raw=(json.dumps(report,indent=2,sort_keys=True)+'\n').encode();put(OUT/'build-result.json',raw)
 print(json.dumps({'success':report['success'],'path':str(OUT/'build-result.json'),'bytes':len(raw),'sha256':sha(raw),
  'python_tests_passed':report.get('python_tests_passed'),'native_ordinary_controls_passed':report.get('native_ordinary_controls_passed'),
  'runtime_prefix_qualified':False,'namespace_actions':0}),flush=True)
raise SystemExit(0 if report['success'] else 1)
