"""Bounded owned Android R4 smoke. Uses a new private daemon and headless display."""
from pathlib import Path
import datetime,hashlib,json,os,re,stat,subprocess,time,traceback,socket,struct,shutil,fcntl,sys
BASE=Path('/home/alex/work/pocket4-native-private-canary-20261104-r1')
assert len(sys.argv)==2 and sys.argv[1] in ('r14-r4','r15-r2','r16-r2')
HERE=BASE/sys.argv[1]
P=json.loads((HERE/'prepared.json').read_text())
S=Path(P['stage']);Q=Path(P['runtime']);R=Path(P['user_runtime']);SOCK=Q/'control.sock'
NAME=P['name'];NONCE=P['nonce'];SPEC=S/'cell.json';NS=('mnt','pid','uts','ipc','net','cgroup')
PKG='local.pocket4.nativeoraclev8'
PRIVATE_EPOCH=None
GUARD=Path(P['framework_guard']);assert hashlib.sha256(GUARD.read_bytes()).hexdigest()==P['framework_guard_sha256']
EPOCH_GUARD={'__name__':'pinned_epoch_guard'};exec(compile(GUARD.read_bytes(),str(GUARD),'exec'),EPOCH_GUARD)
PARSER={};exec(compile((BASE/'assess-v2.py').read_bytes(),'owned-probe-assessment','exec'),PARSER)
ONCE_PARSER={};exec(compile((BASE/'assess-default-once.py').read_bytes(),'owned-default-once-assessment','exec'),ONCE_PARSER)
CPU_INVENTORY_PATH=BASE/'cpu-inventory-v2.json'
assert hashlib.sha256(CPU_INVENTORY_PATH.read_bytes()).hexdigest()=='590d32e10c5a86934afbd18eebd620d5a07f0e13a4c4af2e4094fac801dc5c62'
CPU_INVENTORY=json.loads(CPU_INVENTORY_PATH.read_text())

ENV={'PATH':'/usr/local/libexec/droidloom-compat:/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8'}
ROWS=[];RESULT={'schema':'pocket4-private-native-v8-three-arm-v2','arm':P['arm'],'started_utc':None,'production_ready':False};INIT=None;LAUNCHER=None
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(name,value):
 raw=value if isinstance(value,bytes) else (json.dumps(value,indent=2,sort_keys=True)+'\n').encode()
 fd=os.open(HERE/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o444)
 with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 os.chmod(HERE/name,0o444)
def event(stage,**kwargs):
 with (HERE/'progress.jsonl').open('a') as f:f.write(json.dumps({'utc':now(),'stage':stage,**kwargs})+'\n');f.flush()
def call(argv,timeout=40,check=True,env=None):
 p=subprocess.run([str(x) for x in argv],capture_output=True,timeout=timeout,env=env or ENV)
 if check and p.returncode:raise RuntimeError(repr(list(map(str,argv[:4])))+' '+p.stderr.decode(errors='replace')[-2000:])
 return p
def props(name):
 p=call(['/usr/bin/systemctl','show',name,'-p','LoadState','-p','ActiveState','-p','MainPID','-p','InvocationID','-p','ControlGroup','-p','Description','-p','ExecStart'],check=False)
 d=dict(x.split('=',1) for x in p.stdout.decode().splitlines() if '=' in x)
 assert p.returncode==0 or d.get('LoadState')=='not-found'
 return d
def proc(pid):
 text=Path(f'/proc/{pid}/stat').read_text();status=dict(x.split(':',1) for x in Path(f'/proc/{pid}/status').read_text().splitlines() if ':' in x)
 return {'pid':pid,'start':text.rsplit(')',1)[1].split()[19],'uid':status['Uid'].split(),'nspid':status.get('NSpid','').split(),'ppid':int(status['PPid']),'ns':{n:os.readlink(f'/proc/{pid}/ns/{n}') for n in NS},'exe':os.readlink(f'/proc/{pid}/exe'),'cgroup':Path(f'/proc/{pid}/cgroup').read_text()}
def main_snapshot():
 guard=EPOCH_GUARD
 import importlib.machinery,importlib.util,sys
 sys.dont_write_bytecode=True
 helper=Path('/usr/local/bin/android-app')
 assert sha(helper)=='eb24b1b0eefb275025d10647ccf218f9395b1f74cf6d912aaabf384210d1aa66'
 loader=importlib.machinery.SourceFileLoader('pinned_android_app_canary',str(helper))
 module=importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name,loader));loader.exec_module(module)
 init,environment,status=module.discover()
 assert init==2773545 and status['host_pid']==2773535
 parent=json.loads((GUARD.parent/'live-capture.json').read_text())
 assert parent['sha256']=='d820db4ea51514fdc7f2258e490a7b7453e03aefd666aab0939ad5a87915842d'
 guard['require_unchanged'](parent)
 current=guard['capture_android'](init);assert current['binding']==parent['binding']
 daemon={k:v for k,v in props('droidloomd.service').items() if k!='Description'};assert daemon['ActiveState']=='active' and daemon['MainPID']=='2773423'
 launcher=guard['process_identity'](status['host_pid'])
 owner=guard['process_identity'](current['binding']['processes']['init']['parent_host_pid'])
 return {'config_sha256':sha('/etc/droidloom/cell.json'),'daemon':daemon,'launcher':launcher,'real_unshare':owner,'framework_binding':current['binding'],'framework_sha256':current['sha256'],'discovery_helper_sha256':sha(helper)}

def unit_launch(role,argv,cpu,memory,user=False,extra=None):
 unit=NAME+'-'+role+'.service';desc=NAME+' '+NONCE+' '+role
 assert props(unit).get('LoadState')=='not-found',unit+' already exists'
 args=['/usr/bin/systemd-run','--unit='+unit,'--property=Type=exec','--property=Description='+desc,'--property=Restart=no','--property=RuntimeMaxSec=900','--property=TimeoutStopSec=25','--property=KillMode=control-group','--property=OOMPolicy=stop','--property=CPUQuota='+str(cpu)+'%','--property=MemoryMax='+memory,'--property=MemorySwapMax=0','--property=TasksMax=4096',('--property=UMask=0022' if role=='daemon' else '--property=UMask=0077')]
 if user:args+=['--property=User=alex','--property=Group=alex','--property=NoNewPrivileges=yes']
 env=dict(ENV)
 if user:
  env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':str(R/'home'),'XDG_RUNTIME_DIR':str(R),'DBUS_SESSION_BUS_ADDRESS':'unix:path='+str(R/'bus'),'XDG_CONFIG_HOME':str(R/'config'),'XDG_STATE_HOME':str(R/'state'),'XDG_CACHE_HOME':str(R/'cache'),'XDG_DATA_HOME':str(R/'data'),'TMPDIR':str(R/'tmp'),'TMP':str(R/'tmp'),'TEMP':str(R/'tmp'),'XDG_SESSION_TYPE':'wayland','OMP_NUM_THREADS':'1'}
 if extra:env.update(extra)
 row={'role':role,'unit':unit,'description':desc};ROWS.append(row)
 try:call(args+['--','/usr/bin/env','-i']+[k+'='+v for k,v in sorted(env.items())]+list(map(str,argv)))
 finally:
  d=props(unit)
  if d.get('Description')==desc and d.get('InvocationID'):row.update(invocation=d['InvocationID'],group=d['ControlGroup'])
 assert row.get('invocation') and d['ActiveState'] in ('active','activating')
 event('unit-started',role=role,unit=unit,invocation=row['invocation'])
 return row
def owned(row):
 d=props(row['unit'])
 assert d.get('InvocationID')==row['invocation'] and d.get('Description')==row['description'],'unit identity changed'
 return d
def endpoint(path,row,uid,kind):
 deadline=time.monotonic()+40
 while time.monotonic()<deadline:
  d=owned(row);assert int(d.get('MainPID','0'))>0,'unit exited: '+row['unit']
  try:
   s=path.lstat();assert stat.S_ISSOCK(s.st_mode) and s.st_uid==uid
   with socket.socket(socket.AF_UNIX,kind) as c:
    c.settimeout(2);c.connect(str(path));peer=struct.unpack('3i',c.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
    assert peer[0]==int(d['MainPID']) and peer[1]==uid,'unexpected endpoint owner'
   return path
  except (FileNotFoundError,ConnectionRefusedError):time.sleep(.25)
 raise RuntimeError('endpoint timeout: '+str(path))
def ctl(*args):
 row=[r for r in ROWS if r['role']=='daemon'][0];d=owned(row)
 s=SOCK.lstat();assert stat.S_ISSOCK(s.st_mode) and s.st_uid==0
 assert os.readlink(f"/proc/{d['MainPID']}/exe")==str(S/'bin/droidloomd')
 p=call([S/'bin/droidloomctl-installed-baseline','--socket',SOCK,'--cell','--json',*args],60)
 return json.loads(p.stdout)
def discover_init():
 global INIT,LAUNCHER
 s=ctl('status');assert s.get('ok') and s.get('state')=='running';LAUNCHER=proc(s['host_pid'])
 group=[r['group'] for r in ROWS if r['role']=='daemon'][0]
 found=[];pending=[s['host_pid']];seen=set()
 while pending:
  pid=pending.pop()
  if pid in seen:continue
  seen.add(pid)
  try:
   i=proc(pid)
   if i['nspid'] and i['nspid'][-1]=='1' and i['exe']=='/system/bin/init':found.append(i)
   pending += [int(x) for x in Path(f'/proc/{pid}/task/{pid}/children').read_text().split()]
  except (FileNotFoundError,ProcessLookupError):pass
 assert len(found)==1,found
 INIT=found[0]
 assert all(INIT['ns'][n]!=os.readlink('/proc/self/ns/'+n) for n in NS)
 assert INIT['cgroup'].strip()=='0::'+group or INIT['cgroup'].strip().startswith('0::'+group+'/')
 assert os.readlink(f"/proc/{INIT['pid']}/cwd")=='/'
 mainpid=int(P['main_before']['daemon']['MainPID'])
 assert INIT['pid']!=mainpid and INIT['ns']['mnt']!=os.readlink(f'/proc/{mainpid}/ns/mnt')
 return INIT
def android(args,uid=2000,timeout=35,check=True):
 EPOCH_GUARD['require_unchanged']({'schema':'pocket4-framework-epoch-v1','binding':P['main_before']['framework_binding'],'sha256':P['main_before']['framework_sha256']})
 if PRIVATE_EPOCH is not None:EPOCH_GUARD['require_unchanged'](PRIVATE_EPOCH)
 assert INIT and proc(INIT['pid'])==INIT,'private init generation changed'
 row=[r for r in ROWS if r['role']=='daemon'][0];owned(row)
 env=['PATH=/system/bin:/system/xbin:/apex/com.android.art/bin','ANDROID_ROOT=/system','ANDROID_DATA=/data','ANDROID_ART_ROOT=/apex/com.android.art','ANDROID_I18N_ROOT=/apex/com.android.i18n','ANDROID_TZDATA_ROOT=/apex/com.android.tzdata','EXTERNAL_STORAGE=/sdcard']
 argv=['/usr/bin/nsenter','--target',str(INIT['pid']),'--mount','--pid','--uts','--ipc','--net','--cgroup','--root','--wd','--','/system/bin/env','-i',*env,'/system/bin/timeout','-k','2',str(max(1,timeout-5)),'/system/xbin/su',str(uid),*args]
 return call(argv,timeout,check)
def atext(args,uid=2000,timeout=35):return android(args,uid,timeout).stdout.decode(errors='strict').strip()
def snapshot_app(pid,uid):
 raw=atext(['/system/bin/cat',f'/proc/{pid}/stat'],0);status=atext(['/system/bin/cat',f'/proc/{pid}/status'],0);cmd=atext(['/system/bin/cat',f'/proc/{pid}/cmdline'],0)
 fields=dict(x.split(':',1) for x in status.splitlines() if ':' in x)
 assert fields['Uid'].split()==[str(uid)]*4 and cmd.split('\0')[0]==PKG
 return {'pid':pid,'uid':uid,'start':raw.rsplit(')',1)[1].split()[19],'cmdline':cmd}

def current_guest_epoch():
 return EPOCH_GUARD['capture_android'](INIT['pid'])
def find_app_host(pid,uid):
 found=[]
 for path in Path('/proc').iterdir():
  if not path.name.isdecimal():continue
  try:
   cmd=(path/'cmdline').read_bytes().split(b'\0')[0]
   if cmd!=PKG.encode():continue
   item=EPOCH_GUARD['process_identity'](int(path.name))
   if item['namespace_pids'][-1]==pid and item['namespaces']['pid']==INIT['ns']['pid']:found.append(item)
  except (FileNotFoundError,ProcessLookupError):pass
 assert len(found)==1,('owned process ambiguity',len(found))
 item=found[0];assert item['uids']==[uid]*4
 return item
def engine_loaded(identity):
 pid=identity['host_pid'];assert EPOCH_GUARD['process_identity'](pid)==identity
 p=Path(f'/proc/{pid}/root/system/lib64/libberberis_arm64.so');s=p.stat()
 assert sha(p)==P['engine_sha256']
 rows=[]
 for line in Path(f'/proc/{pid}/maps').read_text().splitlines():
  if 'libberberis_arm64.so' not in line:continue
  m=re.match(r'^([0-9a-f]+)-([0-9a-f]+) (\S+) ([0-9a-f]+) ([0-9a-f]+):([0-9a-f]+) (\d+)\s*(.*)$',line)
  assert m and int(m[7])==s.st_ino and (int(m[5],16),int(m[6],16))==(os.major(s.st_dev),os.minor(s.st_dev))
  rows.append(line)
 assert rows and any('r-xp' in r for r in rows),'candidate engine not actually mapped'
 return {'engine_sha256':P['engine_sha256'],'mapped_inode':s.st_ino,'mapped_device':s.st_dev,'actual_host_maps':rows}
def read_payload(version,nonce,uid,since,pid=None):
 tag='NativeOracleV'+str(version)
 sequence=RESULT.get('raw_log_capture_sequence',0);RESULT['raw_log_capture_sequence']=sequence+1
 observed=android(['/system/bin/logcat','-d','-v','epoch','-v','uid','-s',tag+':I'],0,check=False)
 prefix='raw-attribution-'+str(sequence)
 save(prefix+'.stdout',observed.stdout);save(prefix+'.stderr',observed.stderr)
 save(prefix+'.json',{'tag':tag,'nonce':nonce,'expected_uid':uid,'expected_pid':pid,'earliest_epoch':since,'returncode':observed.returncode})
 assert observed.returncode==0,'raw logcat failed; original output retained before assessment'
 raw=observed.stdout
 payload=[];observed=set()
 for line in raw.decode('utf-8','strict').splitlines():
  if 'run_id='+nonce not in line:continue
  m=re.match(r'^\s*(\d+\.\d+)\s+([A-Za-z0-9_]+)\s+(\d+)\s+(\d+)\s+I\s+'+tag+r'\s*:\s*(.*)$',line)
  assert m,'actual log header mismatch'
  assert float(m[1])>=since and m[2] in (str(uid),'u0_a'+str(uid-10000))
  observed.add(int(m[3]));payload.append(m[5])
 assert len(observed)<=1,'nonce appeared in multiple process IDs'
 if pid is not None:assert observed in (set(),{pid})
 return raw,payload,(next(iter(observed)) if observed else None)
def install_probe(key):
 global PKG
 record=P['apks'][key];PKG=record['package'];assert PKG.startswith('local.pocket4.nativeoraclev')
 existing=atext(['/system/bin/pm','list','packages',PKG],0);assert not existing
 target=Path(f"/proc/{INIT['pid']}/root/data/local/tmp/nativeoracle{key}.apk")
 assert not target.exists();fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
 with os.fdopen(fd,'wb') as f:f.write(Path(record['path']).read_bytes());f.flush();os.fsync(f.fileno())
 assert atext(['/system/bin/pm','install',str('/data/local/tmp/nativeoracle'+key+'.apk')],0,90)=='Success'
 listing=atext(['/system/bin/pm','list','packages','-U','--user','0',PKG],0)
 m=re.fullmatch(r'package:'+re.escape(PKG)+r' uid:(\d+)',listing);assert m
 uid=int(m[1]);assert 10000<=uid<100000
 paths=atext(['/system/bin/pm','path',PKG],0).splitlines();assert len(paths)==1 and paths[0].startswith('package:/data/app/')
 apk=paths[0].removeprefix('package:');assert atext(['/system/bin/sha256sum',apk],0).split()[0]==record['sha256']
 save(key+'-install.json',{'package':PKG,'uid':uid,'APK_SHA256':record['sha256'],'path':apk})
 return uid
def stop_owned(key):
 global PKG
 PKG=P['apks'][key]['package'];atext(['/system/bin/am','force-stop',PKG],2000)
 out=android(['/system/bin/pidof',PKG],0,check=False);assert out.returncode!=0 or not out.stdout.strip()
def normal_probe(key,uid):
 global PKG
 PKG=P['apks'][key]['package'];version=int(key[1:]);nonce=P['nonces'][key if key!='v8' else 'v8-controls']
 since=float(atext(['/system/bin/date','+%s.%N'],0))
 args=['/system/bin/am','start','-W','-n',PKG+'/.MainActivity','--es','run_id',nonce]
 if key=='v8':args+=['--es','mode','controls']
 launch=atext(args,2000,60);save(key+'-launch.txt',launch.encode());assert re.search(r'^Status: ok$',launch,re.M)
 pid=int(atext(['/system/bin/pidof',PKG],0));identity=snapshot_app(pid,uid);host=find_app_host(pid,uid)
 loaded=engine_loaded(host);save(key+'-identity.json',{'guest':identity,'host':host,'loaded':loaded})
 start=time.monotonic();snapshots=[];frozen_payload=None
 for second in (0,2,10):
  while time.monotonic()<start+second:time.sleep(min(.25,start+second-time.monotonic()))
  assert snapshot_app(pid,uid)==identity and EPOCH_GUARD['process_identity'](host['host_pid'])==host
  raw,payload,actual=read_payload(version,nonce,uid,since,pid);save(key+'-log-'+str(second)+'.txt',raw)
  assessed=PARSER['assess'](version,payload,nonce,pid,uid,P['arm'],expected_cpu_count=CPU_INVENTORY['expected_cpuinfo_count'])
  if frozen_payload is None:frozen_payload=payload
  else:assert payload==frozen_payload,'probe automatically replayed or new events appeared'
  EPOCH_GUARD['require_unchanged'](PRIVATE_EPOCH);assert main_snapshot()==P['main_before']
  snapshots.append({'second':second,'assessment':assessed})
 save(key+'-exit-before-owned-stop.txt',atext(['/system/bin/dumpsys','activity','exit-info',PKG],0).encode())
 RESULT[key]={'guest_identity':identity,'host_identity':host,'engine_loaded':loaded,'observations':snapshots,'survived_after_launch_seconds':time.monotonic()-start}
 event('probe-complete',probe=key,classification=snapshots[-1]['assessment']['classification'])
 stop_owned(key)
def capture_default_claim(nonce,parsed,uid,label):
 path='/data/user/0/'+PKG+'/files/default-alarm-'+nonce+'.claim'
 query=android(['/system/bin/cat',path],0,check=False)
 save(label+'.raw',query.stdout);save(label+'.stderr',query.stderr)
 assert query.returncode==0
 expected=('v=1 run_id='+nonce+' mode=default-alarm pid='+str(parsed['owner_pid'])+' uid='+str(uid)+' start_ticks='+str(parsed['owner_start_ticks'])+'\n').encode()
 assert query.stdout==expected,'actual durable claim is not the unique executor identity'
 target=Path(f"/proc/{INIT['pid']}/root")/path.lstrip('/')
 fd=os.open(target,os.O_RDONLY|os.O_NOFOLLOW)
 try:
  meta=os.fstat(fd);body=os.read(fd,513)
  assert stat.S_ISREG(meta.st_mode) and stat.S_IMODE(meta.st_mode)==0o600 and meta.st_uid==uid and meta.st_nlink==1 and meta.st_size==len(expected) and body==expected
 finally:os.close(fd)
 receipt={'path':path,'uid':meta.st_uid,'mode':oct(stat.S_IMODE(meta.st_mode)),'inode':meta.st_ino,'device':meta.st_dev,'nlink':meta.st_nlink,'bytes':len(expected),'sha256':hashlib.sha256(expected).hexdigest(),'owner_pid':parsed['owner_pid'],'owner_start_ticks':parsed['owner_start_ticks']}
 save(label+'.json',receipt);return receipt

def default_alarm_probe(uid):
 global PKG
 PKG=P['apks']['v8']['package'];nonce=P['nonces']['v8-default-alarm']
 since=float(atext(['/system/bin/date','+%s.%N'],0));timezone=atext(['/system/bin/date','+%z'],0)
 assert re.fullmatch(r'[+-]\d{4}',timezone)
 zone=datetime.timezone(datetime.timedelta(minutes=(1 if timezone[0]=='+' else -1)*(int(timezone[1:3])*60+int(timezone[3:]))))
 args=['/system/bin/am','start','-n',PKG+'/.MainActivity','--es','run_id',nonce,'--es','mode','default-alarm']
 save('v8-default-single-launch-command.json',{'argv':args,'earliest_epoch':since,'guest_timezone_offset':timezone,'nonce':nonce,'uid':uid,'host_launch_count':1,'APK_SHA256':P['apks']['v8']['sha256'],'engine_sha256':P['engine_sha256']})
 launch=android(args,2000,60,False)
 save('v8-default-launch.json',{'returncode':launch.returncode,'stdout':launch.stdout.decode(),'stderr':launch.stderr.decode()})
 assert launch.returncode==0
 deadline=time.monotonic()+30;sample=0;data=None;last_payload=None;stable_since=None;r14_identity=None;claim=None
 while time.monotonic()<deadline:
  raw=android(['/system/bin/logcat','-b','all','-d','-v','epoch','-v','uid','-t','5000'],0,check=False)
  exits=android(['/system/bin/dumpsys','activity','exit-info',PKG],0,check=False)
  label='v8-default-observation-'+str(sample);sample+=1
  save(label+'.log',raw.stdout);save(label+'.stderr',raw.stderr);save(label+'.exit-info.txt',exits.stdout);save(label+'.exit-info.stderr',exits.stderr)
  save(label+'.metadata.json',{'utc':now(),'logcat_returncode':raw.returncode,'exit_info_returncode':exits.returncode,'nonce':nonce,'expected_uid':uid,'earliest_epoch':since})
  assert raw.returncode==exits.returncode==0
  collected=ONCE_PARSER['collect'](raw.stdout,nonce,uid,since,PKG)
  parsed=ONCE_PARSER['assess'](collected,nonce,uid,P['arm'],PARSER['assess'])
  save(label+'.attribution.json',{'collected':collected,'assessed':parsed})
  if parsed is None:time.sleep(.2);continue
  if claim is None:claim=capture_default_claim(nonce,parsed,uid,'v8-default-claim')
  pid=parsed['owner_pid']
  exitinfo=exits.stdout.decode('utf-8','strict')
  blocks=re.split(r'ApplicationExitInfo #\d+:',exitinfo)
  found=[b for b in blocks if re.search(r'\bpid='+str(pid)+r'\b',b) and re.search(r'\bprocess='+re.escape(PKG)+r'\b',b)]
  query=android(['/system/bin/pidof',PKG],0,check=False)
  save(label+'.live-pids.json',{'returncode':query.returncode,'stdout':query.stdout.decode(),'stderr':query.stderr.decode()})
  assert query.returncode in (0,1) and not query.stderr
  alive=set(int(x) for x in query.stdout.decode().split())
  assert len(alive)==len(query.stdout.decode().split()) and alive.issubset(set(parsed['all_nonce_pids'])),'unattributed live owned process'
  live=[]
  if P['arm']=='r14':
   assert not found and alive=={pid}
   identity=snapshot_app(pid,uid);host=find_app_host(pid,uid);loaded=engine_loaded(host)
   assert int(identity['start'])==host['start_ticks']==parsed['owner_start_ticks']
   if r14_identity is None:r14_identity=(identity,host)
   else:assert r14_identity==(identity,host)
   data={'assessment':parsed['assessment'],'guest_identity':identity,'host_identity':host,'engine_loaded':loaded,'ignored_alarm_returned_and_survived':True}
  else:
   if not found:time.sleep(.2);continue
   assert len(found)==1 and re.search(r'\brealUid='+str(uid)+r'\b',found[0]) and re.search(r'\bpackageUid='+str(uid)+r'\b',found[0])
   assert re.search(r'\breason=2\s+\(SIGNALED\)',found[0]) and re.search(r'\bstatus=14\b',found[0]),'original default executor did not terminate by SIGALRM'
   timestamp=re.search(r'timestamp=(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3})',found[0]);assert timestamp
   exited=datetime.datetime.strptime(timestamp[1],'%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=zone).timestamp()
   assert since<=exited<=time.time()+2,'default executor exit timestamp is outside this fresh launch'
   assert pid not in alive,'SIGALRM owner unexpectedly still alive'
   refusals={r['pid']:r for r in parsed['relaunch_refused']}
   assert alive.issubset(refusals)
   for refusing_pid,record in refusals.items():
    unexpected=[b for b in blocks if re.search(r'\bpid='+str(refusing_pid)+r'\b',b) and re.search(r'\bprocess='+re.escape(PKG)+r'\b',b)]
    assert not unexpected,'refusing lifecycle process exited before deliberate cleanup'
   for live_pid in sorted(alive):
    identity=snapshot_app(live_pid,uid);host=find_app_host(live_pid,uid)
    assert int(identity['start'])==host['start_ticks']==refusals[live_pid]['start_ticks']
    maps=Path('/proc/'+str(host['host_pid'])+'/maps').read_bytes()
    save(label+'.refused-pid-'+str(live_pid)+'.maps',maps)
    assert b'libnativeoraclev8.so' not in maps,'refusing process unexpectedly mapped the native probe'
    assert EPOCH_GUARD['process_identity'](host['host_pid'])==host
    live.append({'guest_identity':identity,'host_identity':host,'native_probe_not_mapped':True,'maps_sha256':hashlib.sha256(maps).hexdigest()})
   data={'assessment':parsed['assessment'],'logged_guest_pid':pid,'uid':uid,'exit_reason':2,'exit_status':14,'exit_timestamp':timestamp[1],'actual_default_termination':True,'owner_start_ticks_from_durable_claim':parsed['owner_start_ticks'],'owner_start_ticks_not_independently_sampled_due_to_immediate_death':True,'owner_engine_mapping_from_prior_same_arm_live_controls':True}
  save(label+'.live-attribution.json',live)
  if parsed['nonce_payloads']!=last_payload:
   last_payload=parsed['nonce_payloads'];stable_since=time.monotonic()
  elif time.monotonic()-stable_since>=2:
   data.update(at_most_once=parsed,durable_claim=claim,refusing_live_processes=live,observed_stable_seconds=time.monotonic()-stable_since)
   final_claim=capture_default_claim(nonce,parsed,uid,'v8-default-final-claim');assert final_claim==claim
   save('v8-default-log.txt',raw.stdout);save('v8-default-exit-info.txt',exits.stdout);break
  data=None;time.sleep(.2)
 else:raise RuntimeError('owned default signal result or lifecycle stability absent by deadline')
 assert data
 EPOCH_GUARD['require_unchanged'](PRIVATE_EPOCH);assert main_snapshot()==P['main_before']
 save('v8-default-owned-stop-boundary.json',{'utc':now(),'nonce':nonce,'all_nonce_pids':parsed['all_nonce_pids'],'native_executor_pid':parsed['owner_pid'],'reason':'contract captured; explicit cleanup of owned package'})
 stop_owned('v8')
 final_log=android(['/system/bin/logcat','-b','all','-d','-v','epoch','-v','uid','-t','5000'],0,check=False)
 final_exit=android(['/system/bin/dumpsys','activity','exit-info',PKG],0,check=False)
 save('v8-default-after-owned-stop.log',final_log.stdout);save('v8-default-after-owned-stop.stderr',final_log.stderr);save('v8-default-after-owned-stop-exit-info.txt',final_exit.stdout)
 assert final_log.returncode==final_exit.returncode==0
 final_collected=ONCE_PARSER['collect'](final_log.stdout,nonce,uid,since,PKG)
 final_parsed=ONCE_PARSER['assess'](final_collected,nonce,uid,P['arm'],PARSER['assess'])
 assert final_parsed==parsed,'additional lifecycle or native replay appeared after qualification capture'
 RESULT['v8_default']=data
 event('default-alarm-complete',classification=data['assessment']['classification'],signal=data.get('exit_status'),native_executor_pid=parsed['owner_pid'],refusing_pids=[r['pid'] for r in parsed['relaunch_refused']])

BOOTSTRAP_ARTIFACTS={
 'com.android.droidloom.home':{'relative':'runtime-trees/0/DroidloomHome.apk','sha256':'4580d4ba3db94de30204f2a654dbeefae8d52684cdd3d93ba31cb943324b8484','marker':'/data/local/tmp/droidloom-home.sha256'},
 'com.android.droidloom.ime':{'relative':'runtime-trees/0/DroidloomIME.apk','sha256':'1345fb142061e5d8cb3979d1fce3f3a5d125cc9dab2e9287a3ac7db904a8058a','marker':'/data/local/tmp/droidloom-ime.sha256'}}
def package_names(raw):
 lines=raw.decode('utf-8','strict').splitlines();names=[]
 for line in lines:
  match=re.fullmatch(r'package:([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)',line);assert match,('malformed package record',line)
  names.append(match[1])
 assert len(names)==len(set(names)),'duplicate package record'
 return set(names)
def read_package_inventory(label):
 raw=android(['/system/bin/pm','list','packages','--user','0'],0).stdout
 save('packages-'+label+'.txt',raw)  # Commit actual bytes before parsing.
 third=android(['/system/bin/pm','list','packages','-3','--user','0'],0).stdout
 save('packages-'+label+'-third-party.txt',third)
 return package_names(raw),package_names(third)
def bootstrap_ready():
 assert sha(S/'runtime-trees/0/droidloom-home.rc')=='7a1bbd29cdf3266662670eedea52feeb7edcba67ac2c683c8287ebb32b059c85'
 assert sha(S/'runtime-trees/0/home-setup')=='9dcf78ae3141f2e20bd9bdb764e6d863b76bcfe40a954c1bfadeb1472f0ad993'
 assert sha(S/'runtime-trees/0/setup')=='d2a76b0ea356d94b78a20911a0e203838194b90b1791fb778dbd734760338b87'
 for rec in BOOTSTRAP_ARTIFACTS.values():assert sha(S/rec['relative'])==rec['sha256']
 deadline=time.monotonic()+120;observations=[]
 while time.monotonic()<deadline:
  record={'utc':now(),'home_setup_state':atext(['/system/bin/getprop','init.svc.droidloom-home-setup'],0),'ime_setup_state':atext(['/system/bin/getprop','init.svc.droidloom-ime-setup'],0),'packages':{}};ready=record['home_setup_state']=='stopped' and record['ime_setup_state']=='stopped'
  for package,expected in BOOTSTRAP_ARTIFACTS.items():
   query=android(['/system/bin/pm','path','--user','0',package],0,check=False)
   paths=query.stdout.decode('utf-8','strict').strip().splitlines()
   if not paths:ready=False;record['packages'][package]={'installed':False};continue
   assert query.returncode==0 and len(paths)==1 and paths[0].startswith('package:/data/app/')
   path=paths[0].removeprefix('package:')
   digest=atext(['/system/bin/sha256sum',path],0).split()[0]
   assert digest==expected['sha256'],'unexpected bootstrap APK bytes'
   listing=atext(['/system/bin/pm','list','packages','-U','--user','0',package],0)
   match=re.fullmatch(r'package:'+re.escape(package)+r' uid:(\d+)',listing);assert match
   uid=int(match[1]);assert 10000<=uid<100000
   dump=atext(['/system/bin/dumpsys','package',package],0)
   versions=re.findall(r'^\s+versionCode=(\d+)\b',dump,re.M);assert versions and set(versions)=={'1'}
   ids=re.findall(r'^\s+(?:appId|userId)=(\d+)\s*$',dump,re.M);assert ids and set(ids)=={str(uid)}
   marker=android(['/system/bin/cat',expected['marker']],0,check=False)
   marker_text=marker.stdout.decode('utf-8','strict').strip()
   if marker.returncode!=0 or marker_text!=expected['sha256']:ready=False
   record['packages'][package]={'installed':True,'path':path,'sha256':digest,'versionCode':1,'uid':uid,'marker_sha256':marker_text,'marker_returncode':marker.returncode}
  resolve=atext(['/system/bin/cmd','package','resolve-activity','--brief','--user','0','-a','android.intent.action.MAIN','-c','android.intent.category.HOME'],0)
  record['resolved_home']=resolve
  if resolve.splitlines()[-1:] not in [['com.android.droidloom.home/.HomeActivity'],['com.android.droidloom.home/com.android.droidloom.home.HomeActivity']]:ready=False
  disabled=atext(['/system/bin/pm','list','packages','-d','--user','0','com.android.launcher3'],0)
  record['disabled_stock_launcher']=disabled
  if disabled!='package:com.android.launcher3':ready=False
  selected=atext(['/system/bin/cmd','settings','get','secure','default_input_method'],0)
  record['selected_ime']=selected
  if selected!='com.android.droidloom.ime/.HostInputMethod':ready=False
  observations.append(record)
  if ready:
   EPOCH_GUARD['require_unchanged'](PRIVATE_EPOCH)
   save('bootstrap-ready.json',{'deadline_seconds':120,'observations':observations,'complete':True,'source_driven_passive_wait':True})
   event('bootstrap-complete',home_sha256=BOOTSTRAP_ARTIFACTS['com.android.droidloom.home']['sha256']);return
  time.sleep(.5)
 save('bootstrap-not-ready.json',{'deadline_seconds':120,'observations':observations,'complete':False})
 raise RuntimeError('private Home/IME bootstrap deadline exceeded')
def ensure_owned_cleanup(identities,before,third_before):
 uninstall=[]
 for key in ('v8','v4','v5','v6'):
  pkg=P['apks'][key]['package'];q=android(['/system/bin/pm','uninstall',pkg],0,90,False)
  save(key+'-uninstall.json',{'returncode':q.returncode,'stdout':q.stdout.decode(),'stderr':q.stderr.decode()})
  assert q.returncode==0 and q.stdout.strip()==b'Success'
  uninstall.append({'package':pkg,'uid':identities[key],'uninstall_success':True})
 after,third_after=read_package_inventory('after')
 owned={r['package'] for r in P['apks'].values()}
 comparison={'before_count':len(before),'after_count':len(after),'missing':sorted(before-after),'unexpected':sorted(after-before),'third_party_missing':sorted(third_before-third_after),'third_party_unexpected':sorted(third_after-third_before),'owned_still_installed':sorted(after&owned),'uninstall':uninstall}
 save('package-set-comparison.json',comparison)
 assert after==before and third_after==third_before and not after&owned,'package set changed after owned probes'
 uid_raw=android(['/system/bin/pm','list','packages','-U','--user','0'],0).stdout;save('package-uids-after.txt',uid_raw)
 uid_records=[]
 for line in uid_raw.decode('utf-8','strict').splitlines():
  match=re.fullmatch(r'package:([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*) uid:(\d+)',line);assert match,('malformed UID record',line)
  uid_records.append((match[1],int(match[2])))
 assert len(uid_records)==len(set(n for n,u in uid_records))
 assert set(n for n,u in uid_records)==after,'UID package inventory is incomplete'
 assert not any(n in owned or u in identities.values() for n,u in uid_records),'owned package UID still installed'
 root=Path(f"/proc/{INIT['pid']}/root");paths=[]
 for key in ('v8','v4','v5','v6'):
  pkg=P['apks'][key]['package'];installed=json.loads((HERE/(key+'-install.json')).read_text())
  code=Path(installed['path']).parent;assert str(code).startswith('/data/app/') and pkg in code.name
  paths.extend([str(code),'/data/data/'+pkg,'/data/user/0/'+pkg,'/data/user_de/0/'+pkg])
 deadline=time.monotonic()+10;remaining=[]
 while time.monotonic()<deadline:
  EPOCH_GUARD['require_unchanged'](PRIVATE_EPOCH);remaining=[]
  for rel in paths:
   p=root/rel.lstrip('/')
   try:p.lstat();remaining.append(rel)
   except FileNotFoundError:pass
  if not remaining:break
  time.sleep(.25)
 namespace_checks=[]
 for rel in paths:
  q=android(['/system/bin/ls','-ld','--',rel],0,10,False)
  namespace_checks.append({'path':rel,'returncode':q.returncode,'stdout':q.stdout.decode(),'stderr':q.stderr.decode()})
 save('owned-code-data-cleanup.json',{'checked_paths':paths,'remaining':remaining,'owned_uids':identities,'owned_uids_absent_from_package_registry':True,'deadline_seconds':10,'actual_namespace_checks':namespace_checks})
 assert all(q['returncode']!=0 and 'no such file or directory' in q['stderr'].lower() for q in namespace_checks),'owned path absence not confirmed within actual Android namespace'
 assert not remaining,'owned code or data remained'
 RESULT['own_packages_removed']=True
def run_probes():
 global PRIVATE_EPOCH
 PRIVATE_EPOCH=current_guest_epoch();save('private-framework-epoch.json',PRIVATE_EPOCH)
 bootstrap_ready()
 before,third_before=read_package_inventory('before')
 assert set(BOOTSTRAP_ARTIFACTS).issubset(before) and set(BOOTSTRAP_ARTIFACTS).issubset(third_before)
 assert not any(r['package'] in before for r in P['apks'].values())
 identities={}
 for key in ('v8','v4','v5','v6'):
  uid=install_probe(key);identities[key]=uid;normal_probe(key,uid)
 default_alarm_probe(identities['v8'])
 RESULT['all_native_contracts_observed']=True
 ensure_owned_cleanup(identities,before,third_before)
 RESULT['all_owned_contracts_complete']=True
 RESULT['scope']='Owned ALRM, maps offsets, V4-V6 actual translated controls and owned cleanup; no publisher application claim'


MAIN_RESOURCE_EXPECTED={'memory.high':'5368709120','memory.max':'6442450944','cpu.max':'200000 100000','memory.swap.max':'max','pids.max':'12288'}
def main_resources():
 p=Path('/sys/fs/cgroup/system.slice/droidloomd.service')
 actual={n:(p/n).read_text().strip() for n in MAIN_RESOURCE_EXPECTED}
 assert actual==MAIN_RESOURCE_EXPECTED,('Main resource contract changed',actual)
 return actual
def source_contract():
 manifest=BASE/'runner-v5-once-manifest.json';frozen=json.loads(manifest.read_text())
 actual={name:hashlib.sha256((BASE/name).read_bytes()).hexdigest() for name in ('run_arm-v5-once.py','assess-v2.py','assess-default-once.py')}
 assert actual==frozen['files']
 assert hashlib.sha256(CPU_INVENTORY_PATH.read_bytes()).hexdigest()==frozen['inventory_sha256']
 return {'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),'files':actual,'inventory_sha256':frozen['inventory_sha256']}

def run():
 RESULT['started_utc']=now();assert os.geteuid()==0 and os.getegid()==0
 RESULT['source_contract_before']=source_contract();RESULT['main_resources_before']=main_resources()
 cg=Path('/proc/self/cgroup').read_text().strip().split('0::',1)[1];actor=Path('/sys/fs/cgroup'+cg)
 assert (actor/'cpu.max').read_text().strip()=='10000 100000' and (actor/'memory.max').read_text().strip()=='268435456' and (actor/'memory.swap.max').read_text().strip()=='0'
 RESULT['actor_cgroup']=cg
 assert not (HERE/'runtime-result.json').exists()
 before=main_snapshot();assert before==P['main_before'],'Main generation differs from prepared baseline'
 for r in P['copied_records']:assert sha(S/r['relative'])==r['sha256'],r['relative']
 assert sha(SPEC)==P['spec_sha256'] and sha(P['presenter'])==P['presenter_sha256']
 for p in sorted(S.rglob('*'),key=lambda p:len(p.parts),reverse=True):
  if p.is_dir():assert not p.is_symlink();os.chmod(p,0o555)
 os.chmod(S,0o555)
 for p in [Q,R,Path(P['cell_runtime'])]:assert not p.exists() and not p.is_symlink()
 Q.mkdir(mode=0o700);R.mkdir(mode=0o700);os.chown(R,1000,1000)
 for n in ['home','config','state','cache','data','tmp']:
  p=R/n;p.mkdir(mode=0o700);os.chown(p,1000,1000)
 (R/'bus.conf').write_text('<busconfig><type>session</type><listen>unix:path='+str(R/'bus')+'</listen><auth>EXTERNAL</auth><policy context="default"><deny user="*"/><allow user="1000"/><allow own="*"/><allow send_destination="*"/><allow receive_sender="*"/></policy></busconfig>\n')
 (R/'sway.conf').write_text('xwayland disable\noutput HEADLESS-1 mode 1280x800@30Hz scale 1\ndefault_border none\nfocus_follows_mouse no\nmouse_warping none\n')
 for f in ['bus.conf','sway.conf']:os.chown(R/f,1000,1000);os.chmod(R/f,0o600)
 memory=Path('/proc/meminfo').read_text();available=int(re.search(r'^MemAvailable:\s+(\d+)',memory,re.M)[1])*1024
 pressure=Path('/proc/pressure/memory').read_text();full=re.search(r'^full avg10=([0-9.]+)',pressure,re.M)
 assert available>=6*1024**3 and full and float(full[1])<=0.5,('resource preflight',available,pressure)
 save('resource-preflight.json',{'MemAvailable_bytes':available,'memory_pressure':pressure,'required_mem_available_bytes':6*1024**3,'required_memory_full_avg10_max':0.5})
 cgroup=Path('/proc/self/cgroup').read_text().strip().split('0::',1)[1];provider=Path('/sys/fs/cgroup'+cgroup)
 while not (provider/'cpuset.cpus.effective').exists():
  assert provider!=Path('/sys/fs/cgroup');provider=provider.parent
 observed_cpu={'online':Path('/sys/devices/system/cpu/online').read_text().strip(),'present':Path('/sys/devices/system/cpu/present').read_text().strip(),'sysconf_online':os.sysconf('SC_NPROCESSORS_ONLN'),'sysconf_configured':os.sysconf('SC_NPROCESSORS_CONF'),'actor_cpuset_effective':(provider/'cpuset.cpus.effective').read_text().strip(),'actor_affinity':sorted(os.sched_getaffinity(0))}
 assert all(observed_cpu[k]==CPU_INVENTORY[k] for k in observed_cpu),'independent CPU inventory changed'
 save('cpu-inventory-observed.json',{'observed':observed_cpu,'expected_manifest_sha256':sha(CPU_INVENTORY_PATH),'cpuset_provider':str(provider)})
 event('preflight-passed')
 bus=unit_launch('bus',['/usr/bin/dbus-daemon','--nofork','--nopidfile','--config-file='+str(R/'bus.conf')],2,'32M',True);endpoint(R/'bus',bus,1000,socket.SOCK_STREAM)
 sway=unit_launch('sway',['/usr/bin/sway','--config',R/'sway.conf'],8,'256M',True,{'WLR_BACKENDS':'headless','WLR_HEADLESS_OUTPUTS':'1','WLR_RENDERER':'gles2','WLR_RENDER_DRM_DEVICE':'/dev/dri/renderD128'})
 deadline=time.monotonic()+40;wayland=None
 while time.monotonic()<deadline:
  owned(sway)
  candidates=[p for p in R.glob('wayland-*') if stat.S_ISSOCK(p.lstat().st_mode)]
  if len(candidates)==1:wayland=endpoint(candidates[0],sway,1000,socket.SOCK_STREAM);break
  time.sleep(.25)
 assert wayland,'headless Wayland endpoint absent'
 presenter=unit_launch('presenter',[P['presenter']],50,'512M',True,{'WAYLAND_DISPLAY':str(wayland),'DROIDLOOM_MODE':'desktop','DROIDLOOM_HOST_SOCKET':str(R/'droidloom/native-bridge.sock'),'DROIDLOOM_HOST_PEER_UID':'1000','DROIDLOOM_HOST_PEER_GID':'1000','DROIDLOOM_RENDER_NODE':'/dev/dri/renderD128'})
 endpoint(R/'droidloom/native-bridge.sock',presenter,1000,socket.SOCK_SEQPACKET)
 daemon=unit_launch('daemon',[S/'bin/droidloomd','--socket',SOCK,'--supervisor',S/'bin/droidloom-supervisor','--spec-directory',S],130,'4608M')
 endpoint(SOCK,daemon,0,socket.SOCK_STREAM)
 assert ctl('status').get('state')=='stopped'
 started=ctl('start','--no-wait','--spec',str(SPEC));save('start-cell.json',started);assert started.get('ok') and started.get('state')=='running'
 event('cell-started',reply=started)
 deadline=time.monotonic()+120
 while time.monotonic()<deadline:
  try:discover_init();break
  except (AssertionError,FileNotFoundError):time.sleep(1)
 assert INIT
 save('init-identity.json',INIT);event('isolated-init-confirmed',pid=INIT['pid'])
 root=Path(f"/proc/{INIT['pid']}/root")
 observed={}
 for q in ['/','/dev/dri','/dev/binderfs','/etc/cgroups.json','/droidloom','/droidloom/classpath-compat','/data','/dev/socket/logdr']:
  try:
   st=(root/q.lstrip('/')).stat();observed[q]={'mode':oct(st.st_mode),'uid':st.st_uid,'gid':st.st_gid}
  except OSError as e:observed[q]={'error':repr(e)}
 save('early-root-permissions.json',observed)

 boot_start=time.monotonic();deadline=boot_start+360;sample=0;next_sample=0
 while time.monotonic()<deadline:
  p=android(['/system/bin/getprop','sys.boot_completed'],0,check=False)
  if p.returncode==0 and p.stdout.strip()==b'1':break
  if time.monotonic()-boot_start>=next_sample:
   logs=android(['/system/bin/logcat','-b','all','-d','-t','500'],0,20,False);save('boot-log-'+str(sample)+'.txt',logs.stdout);save('boot-observation-'+str(sample)+'.json',{'getprop':{'rc':p.returncode,'stdout':p.stdout.decode(errors='replace'),'stderr':p.stderr.decode(errors='replace')},'logcat':{'rc':logs.returncode,'stderr':logs.stderr.decode(errors='replace')}});event('boot-observation',sample=sample,returncode=logs.returncode,bytes=len(logs.stdout),elapsed=time.monotonic()-boot_start);sample+=1;next_sample+=5
  time.sleep(1)
 else:raise RuntimeError('Android boot deadline exceeded')
 assert atext(['/system/bin/getprop','ro.dalvik.vm.native.bridge'],0)=='libberberis_arm64.so'
 assert atext(['/system/bin/sha256sum','/system/lib64/libberberis_arm64.so'],0).split()[0]==P['engine_sha256']
 RESULT['boot']={'completed':'1','android':atext(['/system/bin/getprop','ro.build.version.release'],0),'sdk':atext(['/system/bin/getprop','ro.build.version.sdk'],0),'system_server_start_count':atext(['/system/bin/getprop','sys.system_server.start_count'],0),'adbd':atext(['/system/bin/getprop','init.svc.adbd'],0),'engine_sha256':P['engine_sha256']}
 assert RESULT['boot']['adbd']=='stopped'
 run_probes()

def cleanup():
 failures=[]
 resources=[]
 for row in ROWS:
  if not row.get('invocation'):continue
  try:
   owned(row)
   q=call(['/usr/bin/systemctl','show',row['unit'],'-p','CPUUsageNSec','-p','MemoryPeak','-p','MemoryCurrent','-p','MemoryMax','-p','MemorySwapMax','-p','CPUQuotaPerSecUSec'],check=False)
   resource_row={'unit':row['unit'],'properties':q.stdout.decode()}
   for name in ('memory.events','memory.pressure','cpu.pressure'):
    p=Path('/sys/fs/cgroup'+row['group'])/name
    if p.exists():resource_row[name]=p.read_text()
   resources.append(resource_row)
  except BaseException as e:resources.append({'unit':row['unit'],'error':repr(e)})
 try:
  actor=Path('/sys/fs/cgroup'+Path('/proc/self/cgroup').read_text().strip().split('0::',1)[1])
  actor_row={'unit':'current-owned-controller-actor','cgroup':str(actor)}
  for name in ('memory.events','memory.pressure','cpu.pressure','memory.peak','memory.max','memory.swap.max','cpu.max'):
   actor_row[name]=(actor/name).read_text().strip()
  resources.append(actor_row)
 except BaseException as e:
  resources.append({'unit':'current-owned-controller-actor','error':repr(e)})
 for item in resources:
  try:
   assert 'error' not in item
   events=dict((k,int(v)) for k,v in (line.split() for line in item['memory.events'].splitlines()))
   assert all(events.get(key)==0 for key in ('oom','oom_kill','oom_group_kill'))
  except BaseException as e:failures.append('owned-memory-events: '+str(item.get('unit'))+': '+repr(e))
 RESULT['owned_memory_events_zero']=not any(x.startswith('owned-memory-events:') for x in failures)
 if INIT:
  try:
   RESULT['adbd_before_cleanup']=atext(['/system/bin/getprop','init.svc.adbd'],0)
   assert RESULT['adbd_before_cleanup']=='stopped'
  except BaseException as e:failures.append('adbd-disabled-contract: '+repr(e))

 save('resources-before-cleanup.json',resources)
 # Private stop uses only our owned daemon's explicit socket, never a default.
 daemon=next((r for r in ROWS if r['role']=='daemon' and r.get('invocation')),None)
 if daemon:
  try:
   d=owned(daemon)
   if int(d.get('MainPID','0'))>0 and SOCK.exists():
    stopped=ctl('stop');save('stop-cell.json',stopped);assert stopped.get('ok') and stopped.get('state')=='stopped'
  except BaseException as e:failures.append('cell-stop: '+repr(e))
 for row in reversed(ROWS):
  if not row.get('invocation'):continue
  try:
   d=owned(row)
   if int(d.get('MainPID','0'))>0:call(['/usr/bin/systemctl','stop',row['unit']],45)
   final=props(row['unit']);assert final.get('MainPID','0')=='0'
   if Path('/sys/fs/cgroup'+row['group']).exists():
    p=Path('/sys/fs/cgroup'+row['group']+'/cgroup.procs');assert not p.exists() or not p.read_text().strip()
   journal=call(['/usr/bin/journalctl','-u',row['unit'],'-b','--no-pager','-n','160'],check=False);save('journal-'+row['role']+'.txt',journal.stdout)
  except BaseException as e:failures.append(row['role']+': '+repr(e))
 if INIT:
  try:assert not Path('/proc/'+str(INIT['pid'])).exists() or proc(INIT['pid'])!=INIT
  except BaseException as e:failures.append('init-liveness: '+repr(e))
 RESULT['cleanup']={'errors':failures,'units':ROWS,'runtime_directories_retained_for_inspection':True}
 try:
  after=main_snapshot();RESULT['main_after']=after;RESULT['main_preserved']=after==P['main_before'];assert RESULT['main_preserved']
  RESULT['main_resources_after']=main_resources();assert RESULT['main_resources_after']==RESULT['main_resources_before']
  RESULT['source_contract_after']=source_contract();RESULT['source_contract_preserved']=RESULT['source_contract_after']==RESULT['source_contract_before'];assert RESULT['source_contract_preserved']
 except BaseException as e:failures.append('Main-preservation: '+repr(e))
 return failures
if __name__=='__main__':
 os.umask(0o077)
 try:run();RESULT['run_returned']=True
 except BaseException as e:RESULT['error']=repr(e);RESULT['traceback']=traceback.format_exc();event('failed',error=repr(e))
 finally:
  cleanup();RESULT['finished_utc']=now();save('runtime-result.json',RESULT)
 print(json.dumps({'arm':P['arm'],'run_returned':RESULT.get('run_returned'),'error':RESULT.get('error'),'boot':RESULT.get('boot'),'all_owned_contracts_complete':RESULT.get('all_owned_contracts_complete'),'main_preserved':RESULT.get('main_preserved'),'cleanup_errors':RESULT.get('cleanup',{}).get('errors'),'finished_utc':RESULT.get('finished_utc')}))

 import sys
 sys.exit(0 if RESULT.get('run_returned') and not RESULT.get('error') and not RESULT.get('cleanup',{}).get('errors') and RESULT.get('main_preserved') and RESULT.get('all_owned_contracts_complete') and RESULT.get('own_packages_removed') and RESULT.get('owned_memory_events_zero') and RESULT.get('adbd_before_cleanup')=='stopped' and RESULT.get('source_contract_preserved') else 1)
