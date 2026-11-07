from pathlib import Path
import base64,datetime,difflib,hashlib,json,os,re,stat,subprocess,tarfile,traceback
ROOT=Path('/home/alex/work/pocket4-supervisor-lmkd-lifecycle-r11-work-01')
C=ROOT/'candidate';OUT=ROOT/'integration-producer-build-05';SNAP=ROOT/'integration-producer-review-04'
CFG=__PAYLOAD__
def sha(b):return hashlib.sha256(b).hexdigest()
def need(v,m):
 if not v:raise RuntimeError(m)
def put(p,b):
 p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
 with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
def inputs():
 return {n:{'bytes':(C/n).stat().st_size,'sha256':sha((C/n).read_bytes())} for n in sorted(set(CFG['old'])|set(CFG['files']))}
def all_source():
 out=[]
 for p in sorted(C.rglob('*')):
  m=p.lstat();n=p.relative_to(C).as_posix()
  if stat.S_ISDIR(m.st_mode):continue
  if stat.S_ISREG(m.st_mode):out.append({'path':n,'bytes':m.st_size,'sha256':sha(p.read_bytes())})
  elif stat.S_ISLNK(m.st_mode):out.append({'path':n,'symlink':os.readlink(p)})
  else:raise RuntimeError('unexpected non-source inode '+n)
 return (json.dumps(out,indent=2,sort_keys=True)+'\n').encode()
os.umask(0o077);OUT.mkdir(mode=0o700)
report={'schema':1,'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'success':False,
 'commands':[],'candidate':str(C),'runtime_started':False,'Android_constructor_executed':False,
 'cgroup_namespace_mount_network_or_pressure_effects':False,'installed_files_changed':False,
 'local_opt_in_source_wired':True,'default_policy_remains_legacy_none':True,
 'runtime_qualified':False,'new_source_under_host_validation':True}
env=dict(os.environ);env.update(CARGO_BUILD_JOBS='1',CARGO_INCREMENTAL='0',CARGO_PROFILE_DEV_DEBUG='0',
 CARGO_PROFILE_TEST_DEBUG='0',RUST_TEST_THREADS='1',CARGO_TARGET_DIR=str(ROOT/'integration-core-build-01/target'))
def run(argv,timeout=240):
 i=len(report['commands'])
 try:p=subprocess.run(argv,cwd=C,env=env,capture_output=True,timeout=timeout)
 except subprocess.TimeoutExpired as e:
  stdout=e.stdout or b'';stderr=e.stderr or b''
  put(OUT/('command-%02d.stdout'%i),stdout);put(OUT/('command-%02d.stderr'%i),stderr)
  report['commands'].append({'argv':argv,'returncode':None,'timed_out':True,
   'stdout':stdout.decode(errors='replace'),'stderr':stderr.decode(errors='replace'),
   'stdout_sha256':sha(stdout),'stderr_sha256':sha(stderr)})
  raise
 put(OUT/('command-%02d.stdout'%i),p.stdout);put(OUT/('command-%02d.stderr'%i),p.stderr)
 report['commands'].append({'argv':argv,'returncode':p.returncode,'stdout':p.stdout.decode(),'stderr':p.stderr.decode(),
  'stdout_sha256':sha(p.stdout),'stderr_sha256':sha(p.stderr)})
 return p
try:
 old={}
 for n,pin in CFG['old'].items():
  b=(C/n).read_bytes();need(sha(b)==pin['sha256'] and len(b)==pin['bytes'],'actual producer04 preimage '+n);old[n]=b
 for n,row in CFG['files'].items():
  b=row['text'].encode();need(sha(b)==row['sha256'] and len(b)==row['bytes'],'producer payload '+n)
  if n not in old:need(not (C/n).exists(),'new producer path already exists '+n)
 receipt=(ROOT/'integration-producer-build-04/build-result.json').read_bytes()
 need(sha(receipt)=='0a8db6485bd5352d120365c921a67d8d7332d6205c9609860390b996deb3ba5e','actual producer04 receipt pin')
 baseline_inventory=all_source()
 need(sha(baseline_inventory)=='a7ec8ffb7a1615b5d4f85bcd4dbec19e49042ea4d37fbcd4ac6f5bdd6adab006','full actual producer04 source inventory differs')
 for key in ['manifest','validation']:
  row=CFG['submission_'+key];b=row['text'].encode()
  need(sha(b)==row['sha256'] and len(b)==row['bytes'],'local submission '+key+' pin')
  put(OUT/('submission-'+key+'.json'),b)
 report['submitted_local_manifest_sha256']=CFG['submission_manifest']['sha256']
 SNAP.mkdir(mode=0o700);rows=[]
 put(SNAP/'source-inventory.json',baseline_inventory)
 rows.append({'path':'source-inventory.json','bytes':len(baseline_inventory),'sha256':sha(baseline_inventory)})
 for n,b in old.items():
  put(SNAP/'source'/n,b);rows.append({'path':'source/'+n,'bytes':len(b),'sha256':sha(b)})
 put(SNAP/'host-build-result.json',receipt);rows.append({'path':'host-build-result.json','bytes':len(receipt),'sha256':sha(receipt)})
 note=b'Immutable actual producer04 preimage. Actual 23 relay Rust, 121 supervisor Rust, seven ordinary IPC, worker-origin and compiled entry ABI controls passed. Explicit Some(pressure_relay) is wired only in this uninstalled candidate. Real Android init constructor and receiver execution count is zero. No runtime, namespace, cgroup, mount, network or Main action was run. Source05 changes only the explicit relay startup prefix to direct pinned-path ip and native unshare; legacy None stays unchanged. Its runtime qualification remains open.\n'
 put(SNAP/'REVIEW.txt',note);rows.append({'path':'REVIEW.txt','bytes':len(note),'sha256':sha(note)})
 manifest=(json.dumps({'schema':1,'files':rows,'source_opt_in_wired':True,'installed_entry_enabled':False,'runtime_qualified':False},indent=2,sort_keys=True)+'\n').encode()
 put(SNAP/'manifest.json',manifest)
 with tarfile.open(SNAP/'source-review.tar.gz','x:gz',format=tarfile.PAX_FORMAT) as tar:
  for row in rows:tar.add(SNAP/row['path'],arcname=row['path'],recursive=False)
  tar.add(SNAP/'manifest.json',arcname='manifest.json',recursive=False)
 report['producer04_frozen_snapshot']={'root':str(SNAP),'manifest_sha256':sha(manifest),'archive_sha256':sha((SNAP/'source-review.tar.gz').read_bytes()),'archive_bytes':(SNAP/'source-review.tar.gz').stat().st_size,'files':len(rows)}
 diff=''
 for n,row in CFG['files'].items():
  b=row['text'].encode()
  if n in old:put(OUT/'preimage'/n,old[n]);(C/n).write_bytes(b)
  else:put(C/n,b)
  diff+=''.join(difflib.unified_diff(old.get(n,b'').decode().splitlines(True),b.decode().splitlines(True),fromfile='producer04-actual/'+n,tofile='producer05-submitted/'+n))
 put(OUT/'submitted-delta.diff',diff.encode());report['submitted_delta_sha256']=sha(diff.encode())
 # This one-file submitted overlay is used verbatim; no unrelated formatting.
 report['inputs_before']=inputs(); inventory=all_source();put(OUT/'source-inventory-before.json',inventory)
 report['all_source_inventory_before_sha256']=sha(inventory)
 counts={}
 for package in ['droidloom-pressure-relay','droidloom-supervisor']:
  p=run(['/home/alex/.cargo/bin/cargo','test','--locked','--offline','-j','1','-p',package,'--','--test-threads=1'])
  need(p.returncode==0,'matching tests '+package)
  counts[package]=sum(int(x) for x in re.findall(r'test result: ok\. (\d+) passed;',p.stdout.decode()))
 need(counts=={'droidloom-pressure-relay':23,'droidloom-supervisor':122},'exact 121+1 supervisor / 23 relay control closure')
 need(run(['/home/alex/.cargo/bin/cargo','build','--locked','--offline','-j','1','-p','droidloom-pressure-relay','-p','droidloom-supervisor','--bins']).returncode==0,'matching host binaries')
 for args,minimum in [([],7),(['--worker-context-control'],1)]:
  p=run([str(ROOT/'integration-core-build-01/target/debug/owned-ipc-controls')]+args,45)
  need(p.returncode==0 and len(re.findall(r'^PASS ',p.stdout.decode(),re.M))==minimum,'ordinary IPC/context controls')
 p=run([str(ROOT/'integration-core-build-01/target/debug/droidloom-supervisor'),'relay-entry-abi'],5)
 need(p.returncode==0 and p.stdout==b'droidloom-relay-entry-v1\n','actual compiled entry ABI')
 report['inputs_after']=inputs();need(report['inputs_after']==report['inputs_before'],'source changed during producer controls')
 after=all_source();put(OUT/'source-inventory-after.json',after)
 report['all_source_inventory_after_sha256']=sha(after);need(after==inventory,'complete source tree changed during build')
 report['artifacts']={}
 for name in ['droidloomd','droidloom-supervisor','droidloom-psi-owner','owned-ipc-controls']:
  path=ROOT/'integration-core-build-01/target/debug'/name;b=path.read_bytes()
  need(b.startswith(b'\x7fELF'),'compiled output is not ELF '+name)
  report['artifacts'][name]={'path':str(path),'bytes':len(b),'sha256':sha(b)}
 report.update(success=True,rust_tests_passed=counts,ordinary_ipc_passed=7,worker_context_passed=True,
  actual_compiled_entry_abi_passed=True,production_receiver_Android_executed=False)
except Exception as e:
 report.update(error=type(e).__name__+': '+str(e),traceback=traceback.format_exc())
 try:report['inputs_after_failure']=inputs()
 except Exception as capture:report['source_capture_error']=str(capture)
report['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
raw=(json.dumps(report,indent=2,sort_keys=True)+'\n').encode();put(OUT/'build-result.json',raw)
print(json.dumps({'success':report['success'],'report':str(OUT/'build-result.json'),'sha256':sha(raw),'bytes':len(raw),
 'tests':report.get('rust_tests_passed'),'error':report.get('error'),'producer04_snapshot':report.get('producer04_frozen_snapshot'),
 'submitted_delta_sha256':report.get('submitted_delta_sha256'),'runtime_executed':False}),flush=True)
raise SystemExit(0 if report['success'] else 1)

