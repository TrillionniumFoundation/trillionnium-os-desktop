import os,json,hashlib,stat,subprocess,select,signal,time,traceback,importlib.util
from pathlib import Path
R=Path('/data/pocket4-runtime-d7-unified538-20261113-e2a3-r1');repo=R/'source'
source=repo/'.work/aosp-m2-source/external/minigbm';Q=R/'tools-dma334-r1';Q.mkdir();(Q/'tmp').mkdir();os.umask(0o077)
commit='ce79bbee67b3e2ea7abb110e1415e9ceceaa6471';tree='95c2eb6837a39a6ef62ae454c5d9767cf2066c53'
cg=next(x.split(':',2)[2] for x in Path('/proc/self/cgroup').read_text().splitlines() if x.startswith('0::'));cgp=Path('/sys/fs/cgroup')/cg.lstrip('/')
assert cg.endswith('/p4-runtime-d7-tools334-dma-layout-e2a3-r1.service') and os.sched_getaffinity(0)=={8,9}
assert (cgp/'memory.max').read_text().strip()=='4294967296' and (cgp/'memory.swap.max').read_text().strip()=='0'
report={'schema':'runtime-d7-exact1595-tools334-original-minigbm-actual-dma-layout-v1','reader_pid':os.getpid(),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'cgroup':str(cgp),'release_binaries_rebuilt':0,'runtime_tests_repeated':0,'state':'RUNNING','commands':[],'errors':[],'shared_AOSP_reads_or_writes':0,'runtime_qualified':False,'production_ready':False,'started_ns':time.time_ns()}
env=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',GIT_TERMINAL_PROMPT='0',GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_NOSYSTEM='1',LC_ALL='C',TMPDIR=str(Q/'tmp'))
def f9(s):return [getattr(s,k) for k in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')]
def ref(p):
 p=Path(p);assert p.resolve()==p;s=p.lstat();assert stat.S_ISREG(s.st_mode)
 b=p.read_bytes();assert f9(s)==f9(p.lstat());return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'identity':f9(s)}
def run(name,args,cwd=repo,limit=120):
 op=Q/(name+'.stdout');ep=Q/(name+'.stderr');timed_out=False
 with op.open('xb') as out,ep.open('xb') as err:
  p=subprocess.Popen(args,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True,umask=0o022);fd=os.pidfd_open(p.pid)
  try:
   try:code=p.wait(timeout=limit)
   except subprocess.TimeoutExpired:
    timed_out=True;os.killpg(p.pid,signal.SIGTERM)
    try:code=p.wait(timeout=5)
    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);code=p.wait(timeout=5)
   poll=select.poll();poll.register(fd,select.POLLIN);assert poll.poll(0)
  finally:os.close(fd)
 report['commands'].append({'name':name,'argv':args,'pid':p.pid,'original_pidfd_retired':True,'exit_code':code,'timed_out':timed_out,'stdout':ref(op),'stderr':ref(ep)})
 print(json.dumps({'event':'command_complete','name':name,'exit_code':code}),flush=True)
 assert code==0 and not timed_out,(name,code,ep.read_text()[-1500:]);return op.read_bytes()
def source_snapshot(raw):
 rows=[]
 for entry in raw.split(b'\0'):
  if not entry:continue
  meta,relative=entry.split(b'\t',1);mode,kind,blob=meta.decode().split();p=source/relative.decode();assert kind=='blob' and mode in ('100644','100755')
  r=ref(p);b=p.read_bytes();assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==blob
  assert stat.S_IMODE(r['identity'][2])==int(mode,8)&0o777 and r['identity'][5]==1
  rows.append(dict(r,git_blob=blob,git_mode=mode,relative=relative.decode()))
 return rows
producer_before=None;release_before=None
try:
 normal_ref=ref(R/'tools-normal334-r1/RESULT.json');assert normal_ref['sha256']=='9b0c06c141bfbf4cee4ec765e6a3f437a2bfa7396c6b0276b90b8be4888bd0db'
 normal=json.loads((R/'tools-normal334-r1/RESULT.json').read_bytes());assert normal['actual_distinct_tests_passed']==333 and all(x['exit_code']==0 and x['original_pidfd_retired'] for x in normal['commands'])
 assert json.loads((R/'TOOLS334-NORMAL-r1-RETIREMENT.json').read_text())['cgroup_absent']
 report['prior333_actual_proof']=normal_ref
 assert normal_ref['bytes']==75557 and normal['state']=='D7_333_ACTUAL_TOOL_TESTS_AND_EXISTING_FOUR_RELEASES_PRESERVED_DMA_PENDING'
 assert normal['all_four_original_release_F9_preserved'] and normal['whole1595_F9_preserved_including_failure_boundary']
 for k,v in map(str.split,normal['memory_events'].splitlines()):
  if k in ('oom','oom_kill','oom_group_kill'):assert int(v)==0
 producer_before=json.loads(Path(normal['source_before']['path']).read_bytes());assert ref(normal['source_before']['path'])==normal['source_before'] and len(producer_before)==1595
 release_before=normal['release_binaries_before'];assert len(release_before)==4
 for row in producer_before:assert ref(row['path'])=={k:row[k] for k in ('path','bytes','sha256','identity')}
 for row in release_before.values():assert ref(row['path'])==row
 report['complete_producer_baseline']=normal['source_before'];report['all_four_existing_release_binaries']=release_before
 lock=json.loads((repo/'android/manifest/audio-bridge-source-lock.json').read_bytes());matches=[x for x in lock['projects'] if x['name']=='platform/external/minigbm'];assert len(matches)==1 and matches[0]['commit']==commit
 parent_root=Path('/data/pocket4-audio538-security-normal-20261113-e2a3-r1')
 parent_proof=parent_root/'dma-layout-qualification-r1/RESULT.json';pr=ref(parent_proof)
 assert pr['bytes']==120324 and pr['sha256']=='4e96ff260f32da94988791d09140467d6eaae10fcd07bea51c04bb1f558c731b'
 parent=json.loads(parent_proof.read_bytes());assert parent['actual_distinct_tests_passed']==334 and parent['source_commit']==commit and parent['source_tree']==tree
 parent_source=parent_root/'recipe/.work/aosp-m2-source/external/minigbm'
 parent_rows=parent['private_original_files'];assert len(parent_rows)==parent['private_original_file_count']==103
 parent_before=[]
 for row in parent_rows:
  rr=ref(row['path']);assert all(rr[k]==row[k] for k in ('path','bytes','sha256','identity')) and Path(row['path'])==parent_source/row['relative']
  parent_before.append(rr)
 assert not source.exists();source.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
 run('private-copy-complete-original',['git','clone','--no-local','--no-hardlinks','--depth','1','--',parent_source.as_uri(),str(source)],repo,240)
 for row in parent_before:assert ref(row['path'])==row
 report['same_original_parent_source']=pr;report['parent_private_originals_preserved']=parent_before
 assert run('head',['git','rev-parse','HEAD'],source).decode().strip()==commit
 assert run('tree',['git','rev-parse','HEAD^{tree}'],source).decode().strip()==tree
 assert not (source/'.git/objects/info/alternates').exists()
 raw=run('all-original-files',['git','ls-tree','-rz','HEAD'],source);before=source_snapshot(raw)
 assert len(before)==103 and {r['relative'] for r in before}=={r['relative'] for r in parent_rows}
 expected_members={r['path'] for r in producer_before}|{r['path'] for r in before}
 def members():
  actual=set()
  for p in repo.rglob('*'):
   if p.is_relative_to(repo/'.git') or p.is_relative_to(source/'.git'):continue
   node=p.lstat();assert not stat.S_ISLNK(node.st_mode) and (stat.S_ISREG(node.st_mode) or stat.S_ISDIR(node.st_mode))
   if stat.S_ISREG(node.st_mode):actual.add(str(p))
  return actual
 assert members()==expected_members
 assert not run('original-clean',['git','status','--porcelain'],source)
 assert all((source/p).is_file() for p in ['dma_heap.c','drv.c','drv_helpers.c','drv.h','drv_helpers.h'])
 harness=next(x['artifact'] for x in normal['compiled_harnesses'] if x['name']=='dma_heap_layout');binary=Path(harness['path']);assert ref(binary)==harness
 helper=R/'tools334-test-terminal.py'
 assert hashlib.sha256(helper.read_bytes()).hexdigest()=='5839760e1804f5d4c8f345da8b71b9fc2d48a02e6efd9205535ed3f36787a69b'
 spec=importlib.util.spec_from_file_location('terminal',helper);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 name='dma_heap_video_planes_satisfy_gpu_and_android_layouts'
 assert run('actual-catalog',[str(binary),'--list','--format=terse']).decode()==name+': test\n'
 text=run('actual-original-dma-layout',[str(binary),'--ignored','--test-threads=2','--color','never'],repo,90).decode()
 report['actual_dma_layout']=module.test_terminal(text,{name});assert report['actual_dma_layout']['filtered']==0
 assert source_snapshot(raw)==before and ref(binary)==harness and members()==expected_members
 for row in parent_before:assert ref(row['path'])==row
 assert not run('final-private-source-clean',['git','status','--porcelain'],source)
 assert not run('final-producer-clean',['git','status','--porcelain'],repo)
 assert run('final-producer-head',['git','rev-parse','HEAD'],repo).decode().strip()=='273d1a2b554923b7b53e645560ddbe5999cbde9b'
 report.update({'state':'ALL334_REGISTERED_SOURCE_UPDATER_AND_INTEGRATION_TESTS_ACTUALLY_PASSED','actual_distinct_tests_passed':334,'all_registered_ignored_cases_actually_executed':True,'source_commit':commit,'source_tree':tree,'private_original_files':before,'private_original_files_unchanged':True,'all1595_producer_F9_unchanged':True,'all_four_existing_release_F9_unchanged':True,'only_fixture_outside1595':str(source),'fixture_published_with_producer':False,'private_original_file_count':len(before),'test_binary':harness,'Android_builds':0})
except BaseException as e:report.update(state='FAILED',errors=[{'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()}])
finally:
 try:
  if producer_before is not None:
   for row in producer_before:assert ref(row['path'])=={k:row[k] for k in ('path','bytes','sha256','identity')}
  if release_before is not None:
   for row in release_before.values():assert ref(row['path'])==row
  report['final_original1595_and_four_bins_F9_boundary_passed']=True
 except BaseException as e:report.update(state='FAILED',errors=report['errors']+[{'stage':'original_boundary','message':str(e),'traceback':traceback.format_exc()}])
 report['finished_ns']=time.time_ns();report['memory_peak_bytes']=int((cgp/'memory.peak').read_text());report['memory_events']=(cgp/'memory.events').read_text();p=Q/'RESULT.json'
 with p.open('x') as f:json.dump(report,f,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 print(json.dumps({'state':report['state'],'result':ref(p),'actual_distinct_tests_passed':report.get('actual_distinct_tests_passed'),'errors':report['errors']}),flush=True)
raise SystemExit(0 if report['state']=='ALL334_REGISTERED_SOURCE_UPDATER_AND_INTEGRATION_TESTS_ACTUALLY_PASSED' else 1)
