import pathlib,os,json,subprocess,hashlib,time,signal
B=pathlib.Path('/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1');BASE=B/'recipe-signature-team-r1';OUT=B/'native-tradefed-helper-be1746a-r1';SRC=OUT/'source';LOG=OUT/'qualification';PIN='fb55abd62b661b4c028f5a8fdf213f29b4f1ad8b'
os.umask(0o077);os.sched_setaffinity(0,{10,11})
def need(ok,msg):
 if not ok:raise RuntimeError(msg)
def sha(p):
 raw=p.read_bytes();return {'path':str(p),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def readcmd(args):
 r=subprocess.run(args,text=True,capture_output=True,timeout=30);need(r.returncode==0,'read command failed '+r.stderr[:500]);return r.stdout.strip()
need(not LOG.exists(),'qualification exists; reconcile original key');LOG.mkdir(mode=0o700)
report={'schema':'native-tradefed-helper-normal-qualification-v1','state':'STARTED','started_ns':time.time_ns(),'base_commit':PIN,'commands':[],'errors':[],'profile':'dev','shared_aosp_mutated':False,'source_reconcile_invocations':0,'full_aosp_builds_started':0,'runtime_qualified':False}
env=os.environ.copy();TB=OUT/'rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu/bin';env.update({'CARGO_HOME':str(OUT/'cargo-home'),'RUSTUP_HOME':str(OUT/'rustup'),'RUSTUP_TOOLCHAIN':'1.93.0','CARGO_TARGET_DIR':str(OUT/'target'),'CARGO_BUILD_JOBS':'1','RUSTC':str(TB/'rustc'),'RUSTDOC':str(TB/'rustdoc'),'PATH':str(TB)+':/usr/bin:/bin'})
def resource():
 rel=pathlib.Path('/proc/self/cgroup').read_text().strip().split(':',2)[2].lstrip('/');cg=pathlib.Path('/sys/fs/cgroup')/rel
 return {'cgroup':str(cg),'affinity':sorted(os.sched_getaffinity(0)),**{n:(cg/n).read_text().strip() for n in ['cpu.max','memory.max','memory.peak','memory.events','memory.swap.current','cgroup.procs']}}
def run(name,args,timeout=1200):
 a=LOG/(name+'.stdout');z=LOG/(name+'.stderr');start=time.time_ns();print(json.dumps({'phase':name,'state':'starting'}),flush=True);timed=False
 with a.open('wb') as so,z.open('wb') as se:
  p=subprocess.Popen(args,cwd=SRC,env=env,stdout=so,stderr=se,start_new_session=True)
  try:rc=p.wait(timeout=timeout)
  except BaseException:
   timed=True
   try:os.killpg(p.pid,signal.SIGTERM)
   except ProcessLookupError:pass
   try:p.wait(timeout=10)
   except subprocess.TimeoutExpired:
    try:os.killpg(p.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    p.wait(timeout=10)
   rc=p.returncode
  try:os.killpg(p.pid,0);group_retired=False
  except ProcessLookupError:group_retired=True
 row={'phase':name,'argv':args,'started_ns':start,'finished_ns':time.time_ns(),'pid':p.pid,'returncode':rc,'timeout_or_interruption':timed,'child_reaped':True,'process_group_retired':group_retired,'stdout':sha(a),'stderr':sha(z)};report['commands'].append(row);print(json.dumps({'phase':name,'returncode':rc,'process_group_retired':group_retired}),flush=True);need(rc==0 and not timed and group_retired,'phase failed '+name);return row
try:
 report['resources_before']=resource();need(report['resources_before']['memory.max']=='4294967296' and report['resources_before']['cpu.max']=='200000 100000','resource budget differs')
 need(not any('tradefed' in p.name and p.name!=OUT.name for p in B.iterdir()),'owner has another Tradefed successor; avoid duplicate compiler')
 need(readcmd(['/usr/bin/git','-C',str(BASE),'rev-parse','HEAD'])==PIN and readcmd(['/usr/bin/git','-C',str(BASE),'status','--porcelain=v1'])=='','base changed')
 setup=json.loads((OUT/'SETUP.json').read_text());need(setup['state']=='ISOLATED_SOURCE_READY_LOCKED_TOOLCHAIN_AVAILABLE','setup not complete');report['setup']=sha(OUT/'SETUP.json')
 run('normal-native-pair-tests',[str(TB/'cargo'),'test','--locked','-j','1','-p','droidloom-update','native_generation_pair_build::tests','--','--test-threads=1'],timeout=1200)
 run('normal-source-tests',[str(TB/'cargo'),'test','--locked','--offline','-j','1','-p','droidloom-source','--lib','--','--test-threads=1'],timeout=600)
 run('normal-tools-build',[str(TB/'cargo'),'build','--locked','--offline','-j','1','-p','droidloom-update','-p','droidloom-source'],timeout=600)
 for name in ['droidloom-source','droidloom-update']:
  bin=OUT/'target/debug'/name;run(name+'-help',[str(bin),'--help'],timeout=30)
 report['binaries']={name:sha(OUT/'target/debug'/name) for name in ['droidloom-source','droidloom-update']}
 run('git-diff-check',['/usr/bin/git','diff','--check'],timeout=30)
 expected={'android/native-generation-pair/source-lock.json':'02fd330466357ecf744d85f27d23b03fabde46f31fae3ef69a5f6634e66e8837','tools/droidloom-update/src/native_generation_pair_build.rs':'52d7dabf9b34b9625f92fc7ecdf36cdc3dd575690a8990f778712995c4067cab'}
 report['source_files']={k:sha(SRC/k) for k in expected};need(all(report['source_files'][k]['sha256']==v for k,v in expected.items()),'candidate changed during normal build');need(set(readcmd(['/usr/bin/git','-C',str(SRC),'diff','--name-only']).splitlines())==set(expected),'unexpected source diff')
 run('git-add',['/usr/bin/git','add','--']+list(expected),timeout=30)
 run('git-commit',['/usr/bin/git','-c','user.name=Codex','-c','user.email=codex@openai.com','commit','-m','fix(android): retain original Tradefed test provider sources'],timeout=30)
 report['commit']=readcmd(['/usr/bin/git','-C',str(SRC),'rev-parse','HEAD']);report['tree']=readcmd(['/usr/bin/git','-C',str(SRC),'rev-parse','HEAD^{tree}']);report['candidate_clean']=readcmd(['/usr/bin/git','-C',str(SRC),'status','--porcelain=v1'])==''
 report['base_after']={'head':readcmd(['/usr/bin/git','-C',str(BASE),'rev-parse','HEAD']),'status':readcmd(['/usr/bin/git','-C',str(BASE),'status','--porcelain=v1'])};need(report['base_after']=={'head':PIN,'status':''},'original recipe changed during qualification');need(report['candidate_clean'],'candidate not clean after commit')
 report['state']='NORMAL_RUST193_TESTS_AND_DEV_TOOLS_QUALIFIED_SOURCE600_RECONCILE_PENDING'
except BaseException as e:report['errors'].append({'type':type(e).__name__,'message':str(e)});report['state']='FAILED'
try:report['resources_after']=resource()
except BaseException as e:report['errors'].append({'type':type(e).__name__,'message':str(e),'phase':'resources'})
report['finished_ns']=time.time_ns();(OUT/'QUALIFICATION.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps({'state':report['state'],'result':sha(OUT/'QUALIFICATION.json'),'errors':report['errors'],'commit':report.get('commit'),'binaries':report.get('binaries')}),flush=True)
raise SystemExit(0 if report['state'].startswith('NORMAL_RUST193_') else 1)
