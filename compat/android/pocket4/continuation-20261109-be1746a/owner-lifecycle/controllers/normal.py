import os,pathlib,subprocess,json,hashlib,time,datetime,select,signal,re,tomllib
root=pathlib.Path('/home/alex/work/pocket4-owner-lifecycle-integration-20261109-be1746a-r2')
source=root/'source';q=root/'qualification/normal-r1';q.mkdir(parents=True)
os.sched_setaffinity(0,{0})
env=os.environ.copy();env['CARGO_TARGET_DIR']=str(root/'target');env['CARGO_NET_OFFLINE']='true'
cargo='/home/alex/.cargo/bin/cargo';rustfmt='/home/alex/.cargo/bin/rustfmt'
edition=str(tomllib.loads((source/'Cargo.toml').read_text())['workspace']['package']['edition'])
selected=['runtime/droidloom-supervisor/src/'+n for n in ['production_namespace.rs','production_namespace_child.rs','production_namespace_tests.rs']]
owner_ref=json.loads((root/'freeze-manifest.json').read_text())['qualified_owner_normal_result']
owner_raw=pathlib.Path(owner_ref['path']).read_bytes()
assert hashlib.sha256(owner_raw).hexdigest()==owner_ref['sha256']
owner_argv=next(c['argv'] for c in json.loads(owner_raw)['commands'] if c['name']=='production-normal-tests')
assert '--ignored' not in owner_argv
owner_skips=[]
for i,arg in enumerate(owner_argv):
 if arg=='--skip':owner_skips.extend([arg,owner_argv[i+1]])
assert len(owner_skips)>=6

def pin(p):
 b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def hashes():
 return [pin(source/r) for r in selected]
def resources():
 cg=next(l.split('::',1)[1].strip() for l in pathlib.Path('/proc/self/cgroup').read_text().splitlines() if l.startswith('0::'))
 p=pathlib.Path('/sys/fs/cgroup')/cg.lstrip('/')
 return {'path':str(p),'affinity':sorted(os.sched_getaffinity(0)),**{x:(p/x).read_text().strip() for x in ['cpu.max','memory.max','memory.current','memory.peak','memory.events','pids.max'] if (p/x).exists()}}
result={'schema':'pocket4-owner-lifecycle-r2-normal-v1','started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source':str(source),'source_before_format':hashes(),'commands':[],'resources_before':resources(),'Android_starts':0,'production_admission':False,'runtime_qualified':False,'production_ready':False,'private_controls_executed':0,'shared_owner_mutations':0,'passed':False}
def run(name,args,deadline=240):
 start=time.monotonic();out=q/(name+'.stdout');err=q/(name+'.stderr')
 print(json.dumps({'event':'start','command':name,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}),flush=True)
 with out.open('wb') as o,err.open('wb') as e:
  p=subprocess.Popen(args,cwd=source,env=env,stdout=o,stderr=e,start_new_session=True)
  fd=os.pidfd_open(p.pid);poll=select.poll();poll.register(fd,select.POLLIN);timed=False
  if not poll.poll(deadline*1000):
   timed=True
   if not poll.poll(0):os.killpg(p.pid,signal.SIGKILL)
  ready=bool(poll.poll(10000));rc=p.wait(timeout=10);os.close(fd)
 r={'name':name,'argv':args,'pid':p.pid,'returncode':rc,'timed_out':timed,'owned_child_pidfd_exit_observed':ready,'elapsed_seconds':time.monotonic()-start,'stdout':pin(out),'stderr':pin(err)}
 result['commands'].append(r)
 print(json.dumps({'event':'complete','command':name,'returncode':rc,'seconds':r['elapsed_seconds']}),flush=True)
 assert rc==0 and ready and not timed,name
 return r
try:
 run('cargo-version',[cargo,'--version'],15)
 run('rustfmt-version',[rustfmt,'--version'],15)
 run('rustfmt',[rustfmt,'--edition',edition,'--config','skip_children=true',*selected],30)
 result['source_after_format']=hashes()
 run('production-normal-tests',[cargo,'test','--locked','--offline','-j','1','-p','droidloom-supervisor','--lib','production_','--','--test-threads=1','--nocapture',*owner_skips,'--skip','privileged_proc_pid_namespace_view_controls'],360)
 text=(q/'production-normal-tests.stdout').read_text()
 result['test_result_lines']=re.findall(r'test result:.*',text)
 result['creator_barrier_lines']=[l for l in (q/'production-normal-tests.stderr').read_text().splitlines() if 'creator-exit barrier' in l]
 assert '92 passed; 0 failed' in text
 run('normal-both-binaries',[cargo,'build','--locked','--offline','-j','1','-p','droidloom-supervisor','--bin','droidloom-supervisor','--bin','droidloomd'],180)
 result['binaries']=[pin(root/'target/debug'/n) for n in ['droidloom-supervisor','droidloomd']]
 result['source_final']=hashes();assert result['source_after_format']==result['source_final']
 freeze=json.loads((root/'freeze-manifest.json').read_text())
 changed=[]
 for f in freeze['owner_files_before']:
  if f['kind']=='file' and hashlib.sha256((source/f['path']).read_bytes()).hexdigest()!=f['sha256']:changed.append(f['path'])
 result['changed_source_paths']=changed;assert sorted(changed)==sorted(selected)
 result['passed']=True
except Exception as e:result['error']={'type':type(e).__name__,'message':str(e)}
finally:
 result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();result['resources_final']=resources()
 (q/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'result':str(q/'result.json'),'passed':result['passed'],'error':result.get('error'),'test_result_lines':result.get('test_result_lines'),'creator_barrier_lines':result.get('creator_barrier_lines'),'result_sha256':hashlib.sha256((q/'result.json').read_bytes()).hexdigest()}),flush=True)
raise SystemExit(0 if result['passed'] else 1)
