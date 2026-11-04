"""Stage three fresh empty-data Android cells. Does not start any service."""
from pathlib import Path
import hashlib,json,os,pwd,grp,stat,subprocess,uuid,time
HERE=Path('/srv/pocket4-native-qualification')
W=Path('/srv/pocket4-native-inputs/probe-preconditions')
OLD=Path('/srv/pocket4-native-inputs/base-runtime')
GUARD=Path('/srv/pocket4-native-inputs/framework-epoch/framework_epoch.py')
GUARD_SHA='f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288'
PRESENTER=Path('/srv/pocket4-native-inputs/presenter/payload/droidloom-wayland')
PRESENTER_SHA='47f34d5f68783a372283cb63a42034d5899e270524cca40122bf28fd5e903f24'
ENGINE={
 'r14':('/srv/pocket4-native-inputs/native-r14/payload/libberberis_arm64.so','a74cba50358ab473b4261e33daee98107fb45fcc78110f71599ad38b63822d2c'),
 'r15':('/srv/pocket4-native-inputs/native-r15/frozen-build-03/target/product/droidloom_x86_64/system/lib64/libberberis_arm64.so','a770eda38e27d072f10568b7dee164a429f9eb05261667f7cb3c6f1c10e0d535'),
 'r16':('/srv/pocket4-native-inputs/native-r16/frozen-build-01/target/product/droidloom_x86_64/system/lib64/libberberis_arm64.so','c8b9bae4466d4f66525fdef6bcec140b29612581efeb6ceb621f96e17277d26d')}
APKS={
 'v4':(W/'native-jni-oracle-v4/build-attempt-1/nativeoraclev4.apk','74c566cefda4877e1b156394a5f8a38e043db95cd33780fd8a45021f9cb6704a'),
 'v5':(W/'native-jni-oracle-v5/build-attempt-1/nativeoraclev5.apk','4cea86be78ba70aba56f5a37bbfe73be9ab10af958cd528a0015fba45f4ced95'),
 'v6':(W/'native-jni-oracle-v6/build-attempt-2/nativeoraclev6.apk','8706242bc7d24bb2f4fc1c0b7358d3c1839b36b8be71470e6f323c5c1b5b43fe'),
 'v8':(HERE/'v8-once-source-r2/build-attempt-1/nativeoraclev8.apk','dc1777871e32681a823253c36dba0a553ef596a464a3c4d7a282d3f9a6bafa67')}
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def command(args,timeout=180):
 q=subprocess.run([str(x) for x in args],capture_output=True,text=True,timeout=timeout)
 assert q.returncode==0,(args[:4],q.stderr[-2000:]);return q.stdout
def put(path,obj,mode=0o444):
 raw=obj if isinstance(obj,bytes) else (json.dumps(obj,indent=2,sort_keys=True)+'\n').encode()
 fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,mode)
 with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 os.chown(path,0,0);os.chmod(path,mode)
def unit(name):
 q=subprocess.run(['/usr/bin/systemctl','show',name,'-p','LoadState','-p','ActiveState','-p','MainPID','-p','InvocationID','-p','ControlGroup','-p','ExecStart'],capture_output=True,text=True,timeout=30)
 d=dict(x.split('=',1) for x in q.stdout.splitlines() if '=' in x)
 assert q.returncode==0 or (q.returncode==4 and d.get('LoadState')=='not-found');return d
def main_snapshot(guard):
 import importlib.machinery,importlib.util,sys
 sys.dont_write_bytecode=True
 helper=Path('/usr/local/bin/android-app')
 assert sha(helper)=='eb24b1b0eefb275025d10647ccf218f9395b1f74cf6d912aaabf384210d1aa66'
 loader=importlib.machinery.SourceFileLoader('pinned_android_app_canary',str(helper))
 module=importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name,loader));loader.exec_module(module)
 init,environment,status=module.discover()
 assert init==int(os.environ['DROIDLOOM_RECORDED_MAIN_INIT_PID']) and status['host_pid']==int(os.environ['DROIDLOOM_RECORDED_MAIN_LAUNCHER_PID'])
 parent=json.loads((GUARD.parent/'live-capture.json').read_text())
 assert parent['sha256']=='d820db4ea51514fdc7f2258e490a7b7453e03aefd666aab0939ad5a87915842d'
 guard['require_unchanged'](parent)
 current=guard['capture_android'](init);assert current['binding']==parent['binding']
 daemon=unit('droidloomd.service');assert daemon['ActiveState']=='active' and daemon['MainPID']==os.environ['DROIDLOOM_RECORDED_MAIN_DAEMON_PID']
 launcher=guard['process_identity'](status['host_pid'])
 owner=guard['process_identity'](current['binding']['processes']['init']['parent_host_pid'])
 return {'config_sha256':sha('/etc/droidloom/cell.json'),'daemon':daemon,'launcher':launcher,'real_unshare':owner,'framework_binding':current['binding'],'framework_sha256':current['sha256'],'discovery_helper_sha256':sha(helper)}

def main():
 assert os.geteuid()==os.getegid()==0;os.umask(0o077)
 assert not (HERE/'canary-plan-v5-once.json').exists()
 assert sha(GUARD)==GUARD_SHA and sha(PRESENTER)==PRESENTER_SHA
 guard={'__name__':'frozen_epoch_guard'};exec(compile(GUARD.read_bytes(),str(GUARD),'exec'),guard)
 before=main_snapshot(guard)
 assert sha(HERE/'runner-v5-once-manifest.json')=='72d3151d28485f536b9f28b9575b248da92c6b289998e28066a82a8a2f776f67'
 for path,h in ENGINE.values():assert sha(path)==h and Path(path).is_file()
 for path,h in APKS.values():assert sha(path)==h
 build=json.loads((HERE/'v8-once-source-r2/build-attempt-1/build-result.json').read_text());assert build['state'].startswith('BUILT_')
 for rel,h in build['source_sha256'].items():assert sha(HERE/'v8-once-source-r2'/rel)==h
 old=json.loads((OLD/'cell.json').read_text());manifest=json.loads((OLD/'media-canary-manifest.json').read_text());records=manifest['records']
 assert old['host_uid']==2191 and old['shared_storage_directories']==[] and len(records)==86
 assert len({r['relative'] for r in records})==86
 for rec in records:
  p=Path(rec['frozen']);s=p.lstat();assert p==OLD/rec['relative'] and stat.S_ISREG(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022 and s.st_nlink==1 and s.st_size==rec['bytes']
 assert os.statvfs('/opt').f_bavail*os.statvfs('/opt').f_frsize>12*1024**3
 existing=[]
 for p in [Path('/etc/droidloom/cell.json')]+list(Path('/opt').glob('*/cell.json')):
  try:existing.append((str(p),json.loads(p.read_text())))
  except (OSError,ValueError):pass
 arms=[]
 for index,arm in enumerate(('r14','r15','r16')):
  revision={'r14':4,'r15':2,'r16':2}[arm];name='p4-native-v8-'+arm+'-20261104-r'+str(revision);stage=Path('/opt')/name;data=Path('/var/lib')/name;runtime=Path('/run')/name;user=Path('/run/user/1000')/name;uid=2320+index;sub=12000000+index*100000;cell=Path('/run/droidloom/cells')/('u'+str(uid));directory=HERE/(arm+'-r'+str(revision))
  for p in (stage,data,runtime,user,cell,directory):assert not p.exists() and not p.is_symlink(),str(p)
  try:pwd.getpwuid(uid);raise AssertionError('host UID already named')
  except KeyError:pass
  try:grp.getgrgid(uid);raise AssertionError('host GID already named')
  except KeyError:pass
  for path,cfg in existing:
   assert cfg.get('host_uid')!=uid,('host UID collision',path)
   for key in ('subordinate_uids','subordinate_gids'):
    r=cfg.get(key,{})
    if 'start' in r:assert r['start']+r['count']<=sub or r['start']>=sub+100000,('subordinate overlap',path)
  for name2 in ('subuid','subgid'):
   for line in Path('/etc/'+name2).read_text().splitlines():
    _,start,count=line.split(':');start=int(start);count=int(count)
    assert start+count<=sub or start>=sub+100000,('allocated subordinate overlap',name2)
  stage.mkdir(mode=0o755);data.mkdir(mode=0o700);directory.mkdir(mode=0o700);copied=[]
  for rec in records:
   source=Path(rec['frozen']);target=stage/rec['relative'];target.parent.mkdir(parents=True,exist_ok=True)
   command(['/usr/bin/cp','--reflink=auto','--sparse=always','--no-clobber',source,target])
   os.chown(target,0,0);os.chmod(target,rec['mode']);assert sha(target)==rec['sha256'],str(source)
   copied.append({'relative':rec['relative'],'sha256':rec['sha256'],'bytes':rec['bytes']})
  cfg=json.loads(json.dumps(old));enginepath,enginehash=ENGINE[arm]
  rows=[r for r in cfg['android_file_overrides'] if r['target']=='/system/lib64/libberberis_arm64.so'];assert len(rows)==1
  own_engine=stage/Path(rows[0]['source']).relative_to(OLD);assert own_engine==stage/'payload/39/libberberis_arm64.so'
  own_engine.unlink();command(['/usr/bin/cp','--reflink=auto','--no-clobber',enginepath,own_engine]);os.chown(own_engine,0,0);os.chmod(own_engine,0o444);assert sha(own_engine)==enginehash
  for row in copied:
   if row['relative']=='payload/39/libberberis_arm64.so':row.update(sha256=enginehash,bytes=own_engine.stat().st_size)
  for key in ('android_file_overrides','android_runtime_directories'):
   for row in cfg[key]:row['source']=str(stage/Path(row['source']).relative_to(OLD))
  cfg['android_init']=str(stage/Path(cfg['android_init']).relative_to(OLD))
  cfg.update(host_uid=uid,subordinate_uids={'start':sub,'count':100000},subordinate_gids={'start':sub,'count':100000},runtime_dir=str(cell),data_dir=str(data),denial_socket=str(user/'droidloom/native-bridge.sock'),image_dir=str(stage),vendor_image=str(stage/'images/vendor.raw.img'))
  put(stage/'cell.json',cfg)
  for file,size,label in [('data.img',8*1024**3,'userdata'),('metadata.img',128*1024**2,'metadata')]:
   p=data/file;fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
   with os.fdopen(fd,'wb') as f:f.truncate(size);f.flush();os.fsync(f.fileno())
   command(['/usr/sbin/mkfs.ext4','-F','-m','0','-L',label,'-O','verity,^orphan_file','-E','lazy_itable_init=1,lazy_journal_init=1',p])
  (stage/'tests').mkdir();apks={}
  for key,(apk,h) in APKS.items():
   target=stage/'tests'/('oracle-'+key+'.apk');command(['/usr/bin/cp','--no-clobber',apk,target]);os.chown(target,0,0);os.chmod(target,0o444);assert sha(target)==h
   apks[key]={'path':str(target),'sha256':h,'package':'local.pocket4.nativeoracle'+key}
  nonces={k:uuid.uuid4().hex for k in ('v4','v5','v6','v8-controls','v8-default-alarm')}
  info={'schema':'pocket4-native-private-canary-v1','arm':arm,'nonce':uuid.uuid4().hex,'nonces':nonces,'name':name,'stage':str(stage),'data':str(data),'runtime':str(runtime),'user_runtime':str(user),'cell_runtime':str(cell),'spec_sha256':sha(stage/'cell.json'),'engine_sha256':enginehash,'presenter':str(PRESENTER),'presenter_sha256':PRESENTER_SHA,'apks':apks,'main_before':before,'copied_records':copied,'fresh_empty_data_images':True,'old_userdata_read':False,'services_started':False,'production_ready':False,'base_fixture':str(OLD),'base_fixture_manifest_sha256':sha(OLD/'media-canary-manifest.json'),'framework_guard':str(GUARD),'framework_guard_sha256':GUARD_SHA,'private_cpu_total_percent':200,'private_memory_total_mib':5664,'private_swap_max':0,'serial_arms':True}
  assert main_snapshot(guard)==before,'Main changed during preparation'
  info['runner_contract_sha256']=sha(HERE/'runner-v5-once-manifest.json')
  put(directory/'prepared.json',info);arms.append({'arm':arm,'directory':str(directory),'name':name,'engine_sha256':enginehash,'nonce':info['nonce'],'nonces':nonces})
  print(json.dumps({'prepared':arm,'directory':str(directory),'services_started':False}),flush=True)
 plan={'schema':'pocket4-native-three-arm-plan-v1','arms':arms,'guard_sha256':GUARD_SHA,'main_before':before,'V8_APK_SHA256':APKS['v8'][1],'V8_source_sha256':build['source_sha256'],'fixed_presenter_sha256':PRESENTER_SHA,'services_started':False,'production_ready':False,'scope':'owned ALRM, maps offsets, V4-V6 translated native controls only','failure_action':'stop only identity-matched freshly owned units; preserve evidence; no automatic retry','expected':{'r14':{'maps_status':[32,32,0,0],'handler_control':0,'initial_alarm':1,'default_alarm_returns':True},'r15':{'maps_status':[32,32,0,0],'handler_control':0,'initial_alarm':0,'default_alarm_signal':14},'r16':{'maps_status':[0,0,0,0],'handler_control':0,'initial_alarm':0,'default_alarm_signal':14}}}
 plan['runner_contract_sha256']=sha(HERE/'runner-v5-once-manifest.json')
 put(HERE/'canary-plan-v5-once.json',plan)
 print(json.dumps({'plan':str(HERE/'canary-plan-v5-once.json'),'sha256':sha(HERE/'canary-plan-v5-once.json'),'arms':arms,'main_framework_sha256':before['framework_sha256'],'services_started':False}),flush=True)
if __name__=='__main__':main()
