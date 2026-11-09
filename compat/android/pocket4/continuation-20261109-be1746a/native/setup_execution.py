import pathlib,os,json,subprocess,hashlib,time,tomllib,shutil,traceback
B=pathlib.Path('/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1'); BASE=B/'recipe-signature-team-r1'; PREP=B/'qualification/tradefed-source-prepared-r1'; OUT=B/'native-tradefed-helper-be1746a-r1'; PIN='fb55abd62b661b4c028f5a8fdf213f29b4f1ad8b'
os.umask(0o077); os.sched_setaffinity(0,{10,11})
def need(ok,msg):
 if not ok:raise RuntimeError(msg)
def sha(p):
 raw=p.read_bytes();return {'path':str(p),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def readcmd(args,cwd=None):
 r=subprocess.run(args,cwd=cwd,text=True,capture_output=True,timeout=30);need(r.returncode==0,'read command failed '+repr(args)+': '+r.stderr[:1000]);return r.stdout.strip()
need(readcmd(['/usr/bin/git','-C',str(BASE),'rev-parse','HEAD'])==PIN,'base head changed');need(readcmd(['/usr/bin/git','-C',str(BASE),'status','--porcelain=v1'])=='','base not clean')
need(not any('tradefed' in p.name and p.name!=OUT.name for p in B.iterdir()),'another owner tradefed successor exists')
need(not OUT.exists(),'unique helper already exists; reconcile previous operation')
OUT.mkdir(mode=0o700);LOG=OUT/'logs';LOG.mkdir(mode=0o700);report={'schema':'native-tradefed-helper-source-setup-v1','state':'STARTED','started_ns':time.time_ns(),'source_base_commit':PIN,'commands':[],'errors':[],'shared_aosp_mutated':False,'full_builds_started':0}
(OUT/'OWNER.json').write_text(json.dumps({'owner':'root/android_state_audit','task':'be1746a native Tradefed normal tool qualification','source_mutation_scope':'isolated recipe only','source_reconcile_allowed':False,'full_aosp_build_allowed':False},indent=2)+'\n')
def run(name,args,cwd=None,env=None,timeout=600):
 s=LOG/(name+'.stdout');e=LOG/(name+'.stderr');start=time.time_ns();print(json.dumps({'phase':name,'state':'starting'}),flush=True)
 with s.open('wb') as a,e.open('wb') as z:r=subprocess.run(args,cwd=cwd,env=env,stdout=a,stderr=z,timeout=timeout)
 row={'name':name,'argv':args,'returncode':r.returncode,'started_ns':start,'finished_ns':time.time_ns(),'stdout':sha(s),'stderr':sha(e),'child_reaped':True};report['commands'].append(row);print(json.dumps({'phase':name,'returncode':r.returncode}),flush=True);need(r.returncode==0,'command failed '+name);return row
try:
 patch=PREP/'native-tradefed-source.patch';need(sha(patch)['sha256']=='3b1b498bd1b2f12623960efe6a9153e943fe17806b397f3dfa9ecdb00e4d4bed','patch changed');report['patch']=sha(patch)
 SRC=OUT/'source';run('clone',['/usr/bin/git','clone','--no-hardlinks','--no-checkout','--',str(BASE),str(SRC)],timeout=120);run('checkout',['/usr/bin/git','-C',str(SRC),'checkout','--detach',PIN]);need(not (SRC/'.git/objects/info/alternates').exists(),'shared git object alternates forbidden')
 run('patch-check',['/usr/bin/git','-C',str(SRC),'apply','--check',str(patch)]);run('patch-apply',['/usr/bin/git','-C',str(SRC),'apply',str(patch)])
 expected={'android/native-generation-pair/source-lock.json':'02fd330466357ecf744d85f27d23b03fabde46f31fae3ef69a5f6634e66e8837','tools/droidloom-update/src/native_generation_pair_build.rs':'52d7dabf9b34b9625f92fc7ecdf36cdc3dd575690a8990f778712995c4067cab'}
 report['candidate_files']={k:sha(SRC/k) for k in expected};need(all(report['candidate_files'][k]['sha256']==v for k,v in expected.items()),'candidate bytes differ')
 need(set(readcmd(['/usr/bin/git','-C',str(SRC),'diff','--name-only']).splitlines())==set(expected),'unexpected source diff')
 run('git-diff-check',['/usr/bin/git','-C',str(SRC),'diff','--check'])
 CARGO=OUT/'cargo-home';CARGO.mkdir(mode=0o700);REG=CARGO/'registry';REG.mkdir(mode=0o700)
 index=pathlib.Path('/home/qq/.cargo/registry/index');run('copy-private-registry-index',['/usr/bin/cp','-a','--reflink=auto','--',str(index),str(REG/'index')],timeout=120)
 pkgs=tomllib.loads((SRC/'Cargo.lock').read_text())['package'];missing=[];copied=[]
 for pkg in pkgs:
  src=pkg.get('source','')
  if not src:continue
  need(src.startswith('registry+'),'unexpected non-registry dependency '+src)
  matches=list(pathlib.Path('/home/qq/.cargo/registry/cache').glob('*/'+pkg['name']+'-'+pkg['version']+'.crate'))
  if not matches:missing.append(pkg['name']+'-'+pkg['version']);continue
  p=matches[0];need(hashlib.sha256(p.read_bytes()).hexdigest()==pkg['checksum'],'cached crate checksum differs '+p.name)
  dest=REG/'cache'/p.parent.name/p.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest);copied.append({'name':pkg['name'],'version':pkg['version'],'sha256':pkg['checksum']})
 report['private_registry']={'copied_crates':len(copied),'missing_crates':missing,'source_cache_mutated':False}
 env=os.environ.copy();env.update({'RUSTUP_HOME':str(OUT/'rustup'),'CARGO_HOME':str(CARGO),'PATH':'/home/qq/.cargo/bin:'+env.get('PATH','/usr/bin:/bin'),'RUSTUP_TOOLCHAIN':'1.93.0','CARGO_TARGET_DIR':str(OUT/'target'),'CARGO_BUILD_JOBS':'1'})
 run('rust-toolchain-install',['/home/qq/.cargo/bin/rustup','toolchain','install','1.93.0','--profile','minimal','--component','clippy','--component','rustfmt','--no-self-update'],env=env,timeout=600)
 run('rustc-version',['/home/qq/.cargo/bin/rustc','--version','--verbose'],cwd=SRC,env=env);run('cargo-version',['/home/qq/.cargo/bin/cargo','--version'],cwd=SRC,env=env)
 report['source_base_after']={'head':readcmd(['/usr/bin/git','-C',str(BASE),'rev-parse','HEAD']),'status':readcmd(['/usr/bin/git','-C',str(BASE),'status','--porcelain=v1'])};need(report['source_base_after']=={'head':PIN,'status':''},'base changed during setup')
 report['state']='ISOLATED_SOURCE_READY_LOCKED_TOOLCHAIN_AVAILABLE'
except BaseException as e:report['errors'].append({'type':type(e).__name__,'message':str(e)});report['state']='FAILED'
report['finished_ns']=time.time_ns();(OUT/'SETUP.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps({'state':report['state'],'result':sha(OUT/'SETUP.json'),'errors':report['errors'],'private_registry':report.get('private_registry')}),flush=True)
raise SystemExit(0 if report['state']=='ISOLATED_SOURCE_READY_LOCKED_TOOLCHAIN_AVAILABLE' else 1)
