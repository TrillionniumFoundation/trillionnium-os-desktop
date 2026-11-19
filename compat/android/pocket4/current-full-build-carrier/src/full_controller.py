"""Fixed Production651 user vendor build and owned source restoration."""
import contextlib,importlib.util,json,os,signal,stat,sys,time,traceback
from pathlib import Path
entry=sys.modules.get('p4_storage_entry')
assert entry is not None and entry.proof['role'] in ('vendor_inner','wm_inner')
_binding_spec=importlib.util.spec_from_file_location('latest_full_producer_contract',Path(__file__).with_name('producer_contract.py'))
producer=importlib.util.module_from_spec(_binding_spec);_binding_spec.loader.exec_module(producer)
producer.require_new_execution_binding()
PHASE=entry.proof['role'].split('_')[0]
ROOT=Path('/data/p4-production651-nbd-e6ac-r1/mount/source-production651')
WORK=ROOT/'work';SOURCE=WORK/'aosp-source';T=ROOT/'tools-production-latest-r1'
RECIPE=T/'recipe';TOOLS=T/'bin'
CONTROL=Path('/data/p4-production651-full-source-e6ac-r2');STATE=CONTROL/'operation'/PHASE
RESULT=ROOT/'qualification'/('full-production651-user-'+PHASE+'-e6ac-r2')
OUTPUT_ROOT=Path('/data/p4-production651-nbd-e6ac-r1/mount/build-production651')
OUT=OUTPUT_ROOT/('out-production651-user-'+PHASE+'-e6ac-r2')
TEMPORARY=WORK/('compiler-tmp-production651-user-'+PHASE+'-e6ac-r2')
UNIT='p4-production651-'+PHASE+'-inner-desktop-e6ac-r3.service'
TARGETS=producer.targets(PHASE)
SUBCOMMAND='vendor-image-build' if PHASE=='vendor' else 'framework-security-build'
INPUT_RECEIPT='droidloom-production-full651-inputs.json' if PHASE=='vendor' else 'droidloom-framework-asb-security-inputs.json'
INPUT_SCHEMA='droidloom-production-full651-inputs-v1' if PHASE=='vendor' else 'droidloom-framework-asb-security-inputs-v1'
ARGV=[str(TOOLS/'droidloom-update'),'--source',str(RECIPE),'--jobs','2',SUBCOMMAND,'--work',str(WORK),'--out',str(OUT)]
spec=importlib.util.spec_from_file_location('full651_support',CONTROL/'ai395_build_support.py')
s=importlib.util.module_from_spec(spec);sys.modules[spec.name]=s;spec.loader.exec_module(s)
all_config,CONFIG_REF=s.read_json(CONTROL/'FULL-CONFIG.json',16*1024**2)
config=all_config['phases'][PHASE]
profile=s.load_module(CONTROL/'current_full_profile.py');BINDING=profile.configure(s,config['resource_plan'])
witness=s.load_module(CONTROL/'process_command_witness.py')
alloc=s.load_module(CONTROL/'owned_allocation.py')
observer=s.load_module(CONTROL/('production651_'+PHASE+'_observation.py'))
projection=s.load_module(CONTROL/'production651_projection.py')
checks=s.load_module(CONTROL/'carrier_checks.py')
receipts=s.load_module(CONTROL/'build_receipts.py')
elf_closure=s.load_module(CONTROL/'elf_closure.py')
original=s.load_module(CONTROL/'projection_baseline_admission.py')
v2=s.load_module(CONTROL/'projection_v2_admission.py')
def environment():
 return {'HOME':'/home/qian-qi','PATH':str(TOOLS)+':/usr/bin:/bin:/usr/sbin:/sbin','LANG':'C.UTF-8',
 'GIT_NO_LAZY_FETCH':'1','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_OPTIONAL_LOCKS':'0',
 'GIT_CONFIG_COUNT':'2','GIT_CONFIG_KEY_0':'maintenance.auto','GIT_CONFIG_VALUE_0':'false',
 'GIT_CONFIG_KEY_1':'gc.auto','GIT_CONFIG_VALUE_1':'0',
 'DROIDLOOM_NATIVE_BRIDGE_SOURCE':str(ROOT/'inputs/engine-working'),'DROIDLOOM_COMPILER_CPUS_RESERVED':'1',
 'GOMAXPROCS':'2','GOMEMLIMIT':'5GiB','GOGC':'50','GODEBUG':'gctrace=1',
 'NINJA_ARGS':'-d keeprsp -d keepdepfile','PYTHONDONTWRITEBYTECODE':'1',
 'TMPDIR':str(TEMPORARY),'GOTMPDIR':str(TEMPORARY),
 'ALLOW_MISSING_DEPENDENCIES':'false','SELINUX_IGNORE_NEVERALLOWS':'false'}
def exact_tree(root,expected,ignore_git=False):
 seen=set()
 for directory,dirs,files in os.walk(root,followlinks=False):
  if ignore_git and Path(directory)==root:dirs[:]=[n for n in dirs if n!='.git']
  for n in list(dirs):
   if (Path(directory)/n).is_symlink():files.append(n);dirs.remove(n)
  for n in files:
   p=Path(directory)/n;relative=p.relative_to(root).as_posix()
   s.need(relative in expected,'unexpected input: '+str(p));row=expected[relative];st=p.lstat()
   s.need(stat.S_IMODE(st.st_mode)==row['mode'],'input mode changed: '+str(p))
   if row['kind']=='file':
    ref=s.file_ref(p);s.need(ref['bytes']==row['bytes'] and ref['sha256']==row['sha256'],'input bytes changed: '+str(p))
   else:s.need(row['kind']=='symlink' and stat.S_ISLNK(st.st_mode) and os.readlink(p)==row['target'],'input link changed')
   seen.add(relative)
 s.need(seen==set(expected),'incomplete input map: '+str(root))
def source_qualification(commands,tag,recovery=False):
 frozen=json.loads(s.pinned(config['frozen_tools'],16*1024**2,contents=True)[1])
 for ref in frozen['normal_tools']:s.pinned(ref)
 producer.validate_frozen(frozen)
 checks.verify_directories(RECIPE,frozen['recipe_directory_refs'],True)
 checks.verify_directories(RECIPE/'.git',frozen['recipe_git_directory_refs'])
 s.need(checks.leaf_names(RECIPE/'.git')==set(frozen['recipe_git_files']),'exact complete recipe Git leaf membership differs')
 exact_tree(RECIPE,frozen['recipe_source_files'],True)
 for ref in list(frozen['recipe_source_refs'].values())+list(frozen['recipe_git_files'].values())+frozen['normal_tools']:
  s.need(s.pinned(ref)['identity']==ref['identity'],'qualified coherent source/tool F9 changed')
 exact_tree(ROOT/'inputs/engine-working',frozen['existing_inputs']['engine_working_files'],True)
 for relative,rows in frozen['existing_inputs']['companion_files'].items():
  s.need(relative in ('mesa-source','python'),'unknown companion input');exact_tree(WORK/relative,rows)
 for ref in frozen['existing_inputs']['fixed_assets']:s.pinned(ref)
 lock=RECIPE/'android/manifest/production-full-source-lock.json'
 prefix=[str(TOOLS/'droidloom-source'),'--profile','production-full']
 commands.run('normal-lock-'+tag,prefix+['verify-lock','--lock',str(lock)],120,cwd=RECIPE,env=environment(),recovery=recovery)
 commands.run('normal-materialized-'+tag,prefix+['verify-materialized','--lock',str(lock),'--output',str(SOURCE)],1200,cwd=RECIPE,env=environment(),recovery=recovery)
 ref=s.pinned(config['materialized_source'],1024**2)
 s.need(ref['path']==str(SOURCE/'.droidloom-source-manifest.json'),'wrong materialized source')
 s.need(not (RECIPE/'.git/objects/info/alternates').exists(),'recipe Git alternates appeared')
 return {'manifest':ref,'recipe_files':producer.TRACKED_FILES,'recipe_tree':frozen['recipe_tree'],'recipe_commit':frozen['recipe_commit'],'normal_tools':frozen['normal_tools']}
def observe_journal(row,baseline,destination):
 s.need(row['lifecycle']['pidfd_closed'] is False,'normal PIDFD must remain held')
 before=s.process_identity(row['driver']['pid'])
 witness.validate_executed_command(row['driver'],before,ARGV,ARGV[0])
 with witness.PinnedExecutable(config['normal_updater']) as held:
  held.verify_running(before['pid'])
  ref,raw=s.file_ref(WORK/'source-projection.json',128*1024**2,contents=True)
  rows=projection.compare(raw,baseline,original.parse_v2,original.original)
  s.need(s.file_ref(WORK/'source-projection.json',128*1024**2)==ref,'journal changed during observation')
  s.create(destination,raw)
  after=s.process_identity(before['pid']);witness.validate_executed_command(row['driver'],after,ARGV,ARGV[0]);held.verify_running(after['pid'])
  return rows,{'reference':ref,'copy':s.file_ref(destination,128*1024**2),'driver':after,'pinned_executable':held.record()}
def snapshot_effective(row,processes,locks,baseline):
 directory=RESULT/'effective-inputs';directory.mkdir(mode=0o700)
 s.need(row['lifecycle']['pidfd_closed'] is False,'effective observation requires held normal PIDFD')
 with witness.PinnedExecutable(config['normal_updater']) as held:
  before=s.process_identity(row['driver']['pid']);held.verify_running(before['pid'])
  witness.validate_executed_command(row['driver'],before,ARGV,ARGV[0])
  temporary=witness.validate_temporary_environment((Path('/proc')/str(before['pid'])/'environ').read_bytes(),str(TEMPORARY))
  kernel=Path('/proc/locks').read_text();s.need(len(kernel)<=1024**2,'kernel lock observation exceeds bound');observed_locks=[]
  for old in locks:
   ref,raw=s.file_ref(old['path'],4096,contents=True)
   s.need(ref['identity'][:2]==old['identity'][:2] and raw==(str(before['pid'])+'\n').encode(),'normal lock inode/owner differs')
   dev,ino=ref['identity'][:2];key='%02x:%02x:%s'%(os.major(dev),os.minor(dev),ino)
   matches=[line for line in kernel.splitlines() if len(line.split())>=8 and line.split()[1]=='FLOCK' and line.split()[4]==str(before['pid']) and line.split()[5]==key]
   s.need(len(matches)==1,'normal driver lacks its actual kernel work lock');observed_locks.append({'reference':ref,'kernel_flock':matches[0]})
  inputs,inputs_ref=s.read_json(OUT/INPUT_RECEIPT,16*1024**2)
  s.need(inputs['schema']==INPUT_SCHEMA and inputs['source_lock']['sha256']=='30dcc1b5b090530b3fc06aeb3e489a961b0fc7c6368ed9d19eb0a1b2054e3eb4','wrong actual full input receipt')
  s.need(inputs['strict_allow_missing_dependencies']==inputs['selinux_ignore_neverallows']=='false','actual strict source policy differs')
  if PHASE=='vendor':s.need(inputs['source_manifest']['sha256']==config['materialized_source']['sha256'],'actual vendor materialized source differs')
  else:s.need(inputs['original_frameworks_base_pin']=='94b4c163b7dfe5ce3607f7bb8456f9573f7de57d' and inputs['requested_targets']==TARGETS,'actual WindowManager full-provider request differs')
  receipts.base_input(inputs,PHASE)
  security_inputs=receipts.live_inputs(OUT,RECIPE,SOURCE,PHASE)
  files=inputs['effective_projection']['files']
  journal,raw=s.file_ref(WORK/'source-projection.json',128*1024**2,contents=True,copy_to=directory/'projection.json')
  typed=v2.validate(raw,SOURCE,files);rows=projection.compare(raw,baseline,original.parse_v2,original.original);actual=[]
  for i,(relative,digest) in enumerate(sorted(files.items())):
   p=SOURCE/relative;s.need(p.is_relative_to(SOURCE) and '..' not in p.parts and p!=SOURCE,'effective path escapes source')
   if digest is None:s.need(not p.exists() and not p.is_symlink(),'effective absence differs');continue
   ref=s.file_ref(p,64*1024**2,copy_to=directory/('%04d-'%i+p.name));s.need(ref['sha256']==digest,'effective source differs: '+relative);actual.append(ref)
  for ref in actual:s.need(s.file_ref(ref['path'],64*1024**2)==ref,'effective input changed')
  s.need(s.file_ref(WORK/'source-projection.json',128*1024**2)==journal and s.file_ref(inputs_ref['path'],16*1024**2)==inputs_ref,'effective journal/receipt changed')
  after=s.process_identity(before['pid']);witness.validate_executed_command(row['driver'],after,ARGV,ARGV[0]);held.verify_running(after['pid'])
  s.need(temporary==witness.validate_temporary_environment((Path('/proc')/str(after['pid'])/'environ').read_bytes(),str(TEMPORARY)),'normal temporary environment changed')
  value={'schema':'p4-production651-actual-effective-inputs-v1','observed_ns':time.time_ns(),'driver_before':before,'driver_after':after,'normal_argv':ARGV,'pinned_executable':held.record(),'actual_soong_processes':processes,'normal_input_receipt':inputs_ref,'security_inputs':security_inputs,'journal':journal,'typed_v2':typed,'independent_baseline':s.file_ref(RESULT/'projection-baseline.json'),'all_originals_equal_independent_before':True,'files':actual,'work_locks':observed_locks,'source_writes':0,'artifact_qualified':False}
  return rows,s.create(directory/'RESULT.json',value)
def interrupted_journal(commands,baseline,destination):
 s.need(all(r['owned_retirement_complete'] for r in commands.records),'journal recovery requires retired owned children')
 ref,raw=s.file_ref(WORK/'source-projection.json',128*1024**2,contents=True,copy_to=destination)
 rows=projection.compare(raw,baseline,original.parse_v2,original.original)
 return rows,{'journal':ref,'copy':s.file_ref(destination,128*1024**2),'owned_commands_retired':True}

def vendor_completion(observed, primary_observed):
 security=receipts.security_completion(OUT,RECIPE,SOURCE,'vendor',observed)
 security.pop('values')
 value,ref=s.read_json(OUT/'droidloom-production-full651-vendor-normal-result.json',16*1024**2)
 s.need(value['schema']=='droidloom-production-full651-vendor-normal-result-v1' and value['requested_targets']==['vendorimage','secilc'],'actual vendor receipt scope differs')
 s.need(value['normal_command_returned_success'] is True and value['source_projection_restored'] is True and value['source_release']=='cp2a' and value['build_variant']=='user','normal vendor receipt did not finish strict user build')
 input_ref=checks.exact_file(value['inputs'],OUT/'droidloom-production-full651-inputs.json',16*1024**2)
 s.need(input_ref==primary_observed,'actual live-observed full651 input receipt F9/SHA changed')
 receipts.false_fields(value,['QPR1_source_identity_claim','selected_CP3A_system_policy_qualified','production_signing_qualified','whole_security_bulletin_qualified','Audio_runtime_qualified','runtime_qualified','production_ready'])
 product=OUT/'target/product/droidloom_x86_64';files={}
 expected={'vendor_image':product/'vendor.img','vendor_build_prop':product/'vendor/build.prop','vendor_sepolicy_cil':product/'vendor/etc/selinux/vendor_sepolicy.cil','plat_pub_versioned_cil':product/'vendor/etc/selinux/plat_pub_versioned.cil','vendor_manifest':product/'vendor/etc/vintf/manifest.xml','vendor_compatibility_matrix':product/'vendor/etc/vintf/compatibility_matrix.xml','normal_host_secilc':OUT/'host/linux-x86/bin/secilc'}
 for key,path in expected.items():
  item=value[key];s.need(item['path']==str(path) and item['bytes']>0,'vendor output location or emptiness differs: '+key)
  files[key]=s.pinned(item,32*1024**3 if key=='vendor_image' else 256*1024**2)
 properties=s.pinned(value['vendor_build_prop'],4*1024**2,contents=True)[1].decode()
 observed=dict(line.split('=',1) for line in properties.splitlines() if not line.startswith('#') and '=' in line)
 s.need(observed==value['observed_vendor_properties'] and observed.get('ro.vendor.build.type')=='user','actual full vendor properties differ')
 inventories={}
 for key in ('complete_vendor_selinux_inventory','complete_vendor_vintf_inventory','odm_actual_output'):
  row=value[key];root=Path(row['path']);s.need(root.is_relative_to(product) and '..' not in root.parts,'vendor inventory escaped owned product')
  s.need(root.exists()==row['exists'],'vendor inventory existence differs');seen=[]
  if root.exists():
   for d,dirs,names in os.walk(root,followlinks=False):
    for n in list(dirs):
     if (Path(d)/n).is_symlink():names.append(n);dirs.remove(n)
    for n in names:seen.append(str(Path(d)/n))
  s.need(set(seen)=={x['path'] for x in row['files']},'vendor inventory not complete')
  for item in row['files']:
   p=Path(item['path']);s.need(p.is_relative_to(root),'vendor inventory file escaped root')
   if item.get('kind')=='symlink':s.need(p.is_symlink() and os.readlink(p)==item['target'],'vendor output link differs')
   else:s.pinned(item,256*1024**2)
  inventories[key]={'root':str(root),'exists':row['exists'],'files':len(seen)}
 s.need(value['odm_image_present']==(product/'odm.img').exists(),'ODM image actual presence differs')
 s.need(value['host_runtime_outputs_to_retain']==[str(OUT/'host/linux-x86/bin/secilc'),str(OUT/'host/linux-x86/lib'),str(OUT/'host/linux-x86/lib64')],'host tool retention paths differ')
 closure=elf_closure.capture(files['normal_host_secilc'],OUT,config.get('secilc_external_inputs',()),config.get('secilc_interpreter_binding'))
 closure_ref=s.create(RESULT/'secilc-static-dependency-closure.json',closure)
 return {'normal_receipt':ref,'normal_input_receipt':input_ref,'normal_security_receipts':security,'normal_secilc_static_dependency_closure':closure_ref,'nonempty_whole_hashed_outputs':files,'inventory_checks':inventories,'observed_vendor_properties':observed,'odm_image_present':value['odm_image_present'],'host_tool_runtime_outputs_retained':value['host_runtime_outputs_to_retain'],'actual_ELF_static_dependency_closure_complete':True,'actual_loader_execution_qualification_pending':True,'selected_CP3A_system_policy_qualified':False,'runtime_qualified':False,'production_ready':False}

def framework_completion(observed):
 return receipts.framework_completion(OUT,RECIPE,SOURCE,observed)

def run_build():
 result={'schema':'p4-production651-user-vendor-full-v1','state':'STARTED','build_host':'desktop','actual_role':PHASE,'source_projects':651,'source_release':'cp2a','build_variant':'user','requested_targets':TARGETS,'resource_profile':s.PROFILE,'started_ns':time.time_ns(),'build_success':False,'production_ready':False,'runtime_qualified':False,'source_projection_restored':False,'input_after_qualified':False,'owned_retirement_complete':False,'errors':[]}
 RESULT.mkdir(mode=0o700);s.create(RESULT/'STARTED.json',result)
 serial=None;commands=None;cgroup=None;allocation=None;baseline=None;projected={};heavy=False;allocation_recovery=False;locks=None
 def remember(stage,error):result['errors'].append({'stage':stage,'type':type(error).__name__,'message':str(error)})
 try:
  s.need(os.getuid()==os.geteuid()==1000,'ordinary full source owner required')
  s.validate_profile(config['resource_profile']);s.need(config['resource_profile']==s.PROFILE,'full resource profile differs')
  outer,outer_ref=s.read_json(STATE/'outer-execution.json');result['outer_admission']=outer_ref;result['outer_job_id']=outer['outer_job_id']
  s.need(outer['resource_profile']==s.PROFILE and outer['full_unit']==UNIT and outer['controller_source']['sha256']==s.file_ref(__file__)['sha256'] and outer['configuration']['sha256']==CONFIG_REF['sha256'],'actual outer full binding differs')
  result['configuration']=CONFIG_REF;result['resource_plan_before']=profile.configure(s,config['resource_plan'])
  cgroup=s.self_cgroup();s.need(cgroup==Path('/sys/fs/cgroup/system.slice')/UNIT,'wrong actual full cgroup')
  result['budget_before']=s.budget_snapshot(cgroup,inner=True)
  s.need(all(s.event_counts(result['budget_before']['memory.events']).get(k)==0 for k in ('oom','oom_kill','oom_group_kill')),'new full cgroup already has OOM events')
  serial,result['shared_serial_lock']=s.serial_lock();s.need(result['shared_serial_lock']['identity'][:6]==config['original_serial_lock']['identity'][:6],'original full serial inode differs')
  result['boot_id']=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
  reconcile=json.loads(s.pinned(config['source_reconciliation'],1024**2,contents=True)[1]);retired=json.loads(s.pinned(config['source_independent_retirement'],1024**2,contents=True)[1])
  s.need(reconcile['passed'] and reconcile['source_reconciled'] and reconcile['owned_commands_retired'] and retired['passed'] and retired['cgroup_absent'],'current normal651 source or retirement incomplete')
  result['source_reconciliation']=config['source_reconciliation'];result['source_independent_retirement']=config['source_independent_retirement']
  s.need(not OUT.exists() and not OUT.is_symlink() and not (WORK/'source-projection.json').exists(),'fresh output and restored source required')
  locks=s.work_lock_probe(WORK,config['work_locks']);result['work_locks_before']=locks
  TEMPORARY.mkdir(mode=0o700);st=TEMPORARY.lstat();s.need(stat.S_ISDIR(st.st_mode) and st.st_uid==1000 and stat.S_IMODE(st.st_mode)==0o700 and st.st_dev==WORK.stat().st_dev,'temporary compiler files left owned work volume')
  result['temporary_directory']={'path':str(TEMPORARY),'identity':s.identity(st),'included_in_96GiB_growth':True}
  commands=s.OwnedCommands(RESULT/'commands',CONTROL);result['commands']=commands.records
  result['source_before']=source_qualification(commands,'before')
  s.pinned(config['historical_projection_path_scope'],16*1024**2)
  baseline=projection.capture(RECIPE,SOURCE,config['historical_projection_path_scope']['path'],original.physical)
  result['independent_projection_baseline']=s.create(RESULT/'projection-baseline.json',baseline)
  s.pinned(config['go_probe']);probe=commands.run('actual-two-cpu-go-probe',[config['go_probe']['path']],30,env=environment())
  facts=json.loads(s.pinned(probe['stdout'],4*1024**2,contents=True)[1]);result['actual_go_probe']=facts
  for key,value in [('NumCPU',2),('GOMAXPROCS',2),('GOMEMLIMIT',5*s.GIB),('GOGC',50)]:s.need(type(facts[key]) is int and facts[key]==value,'actual Go probe differs: '+key)
  s.need(facts['GoVersion']==config['go_runtime_version'] and facts['GODEBUG']=='gctrace=1' and 'Cpus_allowed_list:\t8-9\n' in facts['proc_status'],'actual Go runtime or affinity differs')
  s.need(facts['TMPDIR']==facts['GOTMPDIR']==facts['TempDir']==str(TEMPORARY),'Go temporary directory differs')
  s.need(b'gc 1 @' in s.pinned(probe['stderr'],1024**2,contents=True)[1],'actual Go GC diagnostic missing')
  def checkpoint():
   s.need(allocation_recovery or not s.CANCELLED,'build cancelled')
   s.need(s.disk_free(ROOT)>=s.PROFILE['shared_disk_reserve_bytes'],'shared disk reserve reached')
   s.need(s.memavailable()>=s.PROFILE['host_reserve_bytes'],'host memory reserve reached')
  allocation=alloc.AllocationObserver((ROOT,OUTPUT_ROOT),RESULT/'allocation-observations',checkpoint)
  s.need(allocation.du_ref==config['actual_allocation_tool']['du_executable'] and allocation.du_alias==config['actual_allocation_tool']['du_package_alias'],'actual allocation tool differs')
  result['allocation_observations']=allocation.records
  result['owned_allocation_before_bytes'],result['owned_allocation_before_observation']=allocation.observe()
  result['admission']=s.admission(ROOT);result['argv']=ARGV;result['work_locks_prelaunch']=s.work_lock_probe(WORK,locks)
  result['state']='RUNNING';s.create(RESULT/'admission.json',result)
  observed={'next_sample':0,'next_usage':0,'next_record':0,'samples':[],'source':None,'journal':None,'seen':set(),'soong':{},'user':{},'roles':set(),'growth_peak':0}
  def monitor(row):
   nonlocal projected
   checkpoint();now=time.monotonic()
   if now<observed['next_sample']:return
   observed['next_sample']=now+2
   if 'driver' not in result:
    result['driver']=row['driver'];s.create(RESULT/'running.json',result)
   receipt=OUT/INPUT_RECEIPT
   if observed['journal'] is None and receipt.exists() and (WORK/'source-projection.json').exists():
    projected,observed['journal']=observe_journal(row,baseline,RESULT/'actual-owned-projection.json')
   pids=(cgroup/'cgroup.procs').read_text().split();s.need(len(pids)<=512,'actual full cgroup process bound exceeded');processes=[]
   for token in pids:
    try:
     proc=s.process_identity(int(token));name=Path(proc['exe']).name
     if name not in ('soong_ui','soong_build','ninja'):continue
     raw=(Path('/proc')/token/'environ').read_bytes();s.need(len(raw)<=2*1024**2,'actual build environment exceeds bound')
     env=dict(x.split(b'=',1) for x in raw.split(b'\0') if b'=' in x)
     proc['affinity']=sorted(os.sched_getaffinity(int(token)))
     proc['environment']={key:env.get(key.encode(),b'').decode() for key in ('ALLOW_MISSING_DEPENDENCIES','SELINUX_IGNORE_NEVERALLOWS','GOMEMLIMIT','GOMAXPROCS','GOGC','GODEBUG','NINJA_ARGS','TMPDIR','GOTMPDIR')}
     s.need(proc['affinity']==s.PROFILE['cpu_affinity'],'actual child CPU affinity differs')
     if name in ('soong_ui','soong_build'):
      s.need(all(proc['environment'][k]==v for k,v in [('GOMEMLIMIT','5GiB'),('GOMAXPROCS','2'),('GOGC','50'),('GODEBUG','gctrace=1')]),'actual Soong Go budget differs')
      s.need(proc['environment']['ALLOW_MISSING_DEPENDENCIES'] in ('false','') and proc['environment']['SELINUX_IGNORE_NEVERALLOWS'] in ('false',''),'actual Soong relaxed dependency/policy flag')
      key=(name,proc['pid'],proc['start_ticks'])
      if key not in observed['user']:
       observed['user'][key]=observer.observe(proc,source=SOURCE,out=OUT,expected_cgroup='0::/system.slice/'+UNIT+'\n',result_directory=RESULT,support=s,witness=witness,profile=s.PROFILE,normal_argv=ARGV,normal_driver=row['driver'],normal_lifecycle=row['lifecycle'],resource_plan=config['resource_plan'])
       observed['roles'].add(name)
     if name=='soong_build':observed['soong'][(proc['pid'],proc['start_ticks'])]=proc
     observed['seen'].add(name);processes.append(proc)
    except (FileNotFoundError,ProcessLookupError):continue
   if processes and observed['source'] is None and receipt.exists() and (WORK/'source-projection.json').exists():
    projected,observed['source']=snapshot_effective(row,processes,locks,baseline)
    print(json.dumps({'state':'ACTUAL_PRODUCTION651_INPUTS_OBSERVED','result':observed['source']}),flush=True)
   if processes and now>=observed['next_record']:
    observed['next_record']=now+30
    sample={'observed_ns':time.time_ns(),'processes':processes,'resources':{key:(cgroup/key).read_text().strip() for key in ('memory.max','memory.high','memory.current','memory.peak','memory.events','memory.stat','memory.swap.current')},'free':s.disk_free(ROOT)}
    observed['samples'].append(s.create(RESULT/('resource-%04d.json'%len(observed['samples'])),sample))
   if now>=observed['next_usage'] and OUT.exists():
    observed['next_usage']=now+60
    total,_=allocation.observe();growth=total-result['owned_allocation_before_bytes'];observed['growth_peak']=max(observed['growth_peak'],growth)
    s.need(growth<s.PROFILE['initial_build_work_budget_bytes'],'owned incremental 96GiB growth reached')
  heavy=True
  try:result['normal_build']=commands.run('normal-full-production651-user-'+PHASE,ARGV,21600,cwd=RECIPE,env=environment(),monitor=monitor)
  finally:
   result['effective_source_input_observation']=observed['source'];result['owned_journal_observation']=observed['journal'];result['resource_observations']=observed['samples']
   result['actual_build_processes_seen']=sorted(observed['seen']);result['observed_work_growth_peak_bytes']=observed['growth_peak']
   result['actual_soong_process_generations']=list(observed['soong'].values());result['actual_production_user_observations']=list(observed['user'].values())
   result['actual_production_user_inputs_qualified']=observed['roles']=={'soong_ui','soong_build'}
  s.need(observed['source'] is not None and 'ninja' in observed['seen'] and result['actual_production_user_inputs_qualified'],'successful build lacks actual source/compile/user observations')
  metrics=s.load_module(CONTROL/'go_runtime_budget.py');refs=[(name,result['normal_build'][name]) for name in ('stdout','stderr')]
  with contextlib.ExitStack() as logs:
   streams=[]
   for name,ref in refs:
    s.pinned(ref);fd=os.open(ref['path'],os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC);stream=logs.enter_context(os.fdopen(fd,'rb'))
    s.need(s.identity(os.fstat(stream.fileno()))==ref['identity'],'normal build log identity differs');streams.append((name,stream))
   actual=metrics.qualify_runtime_budget(streams,{p['pid'] for p in observed['soong'].values()})
   for _,ref in refs:s.pinned(ref)
  actual['normal_build_logs']=dict(refs);actual['actual_soong_process_generations']=list(observed['soong'].values());actual['runtime_observer_source']=s.file_ref(CONTROL/'go_runtime_budget.py')
  result['actual_go_runtime_budget']=s.create(RESULT/'actual-go-runtime-budget.json',actual)
 except BaseException as error:
  remember('execution',error);result['traceback']=traceback.format_exc()
 finally:
  retired=commands is not None and all(r['owned_retirement_complete'] for r in commands.records)
  result['owned_retirement_complete']=bool(retired or not heavy)
  if commands is not None and retired and serial is not None:
   try:
    if (WORK/'source-projection.json').exists():
     # Even an observation error must not suppress the authorized normal recovery.
     try:
      projected,result['interrupted_projection']=interrupted_journal(commands,baseline,RESULT/'interrupted-projection.json')
     except BaseException as error:remember('independent_interrupted_projection',error)
     commands.run('normal-source-recovery',[str(TOOLS/'droidloom-update'),'recover-source','--work',str(WORK)],300,cwd=RECIPE,env=environment(),recovery=True)
    s.need(not (WORK/'source-projection.json').exists(),'normal recovery left source projection')
    result['source_projection_restored']=True
    if baseline is not None:result['independent_original_restoration']=projection.verify_restored(baseline,projected,original.physical,original.original)
    result['source_after']=source_qualification(commands,'after',True)
    result['work_locks_after']=s.work_lock_probe(WORK,locks);result['input_after_qualified']=True
   except BaseException as error:remember('normal_restore_or_verify',error)
  if allocation is not None and 'owned_allocation_before_bytes' in result:
   try:
    allocation_recovery=True;total,ref=allocation.observe();growth=total-result['owned_allocation_before_bytes']
    result.update(owned_allocation_after_bytes=total,owned_allocation_after_observation=ref,owned_work_growth_after_bytes=growth,disk_free_after_bytes=s.disk_free(ROOT))
    s.need(growth<s.PROFILE['initial_build_work_budget_bytes'] and result['disk_free_after_bytes']>=s.PROFILE['shared_disk_reserve_bytes'],'final work growth or shared reserve exceeded')
    result['owned_allocation_after_verified']=True
   except BaseException as error:remember('final_allocation',error)
  if allocation is not None:
   try:allocation.close();result['allocation_root_descriptors_closed']=True
   except BaseException as error:remember('allocation_retirement',error)
  if cgroup is not None:
   try:
    result['budget_after']=s.budget_snapshot(cgroup,inner=True);result['resource_retirement']=s.validate_inner_resource_retirement(result['budget_before'],result['budget_after']);result['resource_gate_passed']=True
   except BaseException as error:remember('resources',error)
  if result.get('normal_build') and result['input_after_qualified']:
   try:
    effective,_=s.read_json(result['effective_source_input_observation']['path'],16*1024**2)
    s.need(s.file_ref(result['effective_source_input_observation']['path'])==result['effective_source_input_observation'],'actual retained-driver observation changed')
    observed_security=effective['security_inputs']
    result['actual_product_completion']=vendor_completion(observed_security,effective['normal_input_receipt']) if PHASE=='vendor' else framework_completion(observed_security)
   except BaseException as error:remember('actual_product_completion',error)
  try:
   result['resource_plan_after']=profile.configure(s,config['resource_plan']);s.need(result['resource_plan_after']==result.get('resource_plan_before'),'resource plan changed')
  except BaseException as error:remember('resource_plan',error)
  result['signals']=list(s.CANCELLED)
  if commands is not None:result['owned_retirement_complete']=all(r['owned_retirement_complete'] for r in commands.records)
  result['build_success']=bool(heavy and result.get('normal_build') and result.get('actual_product_completion') and result['owned_retirement_complete'] and result['input_after_qualified'] and result.get('resource_gate_passed') and result.get('effective_source_input_observation') and result.get('actual_go_runtime_budget') and result.get('owned_allocation_after_verified') and result.get('allocation_root_descriptors_closed') and not result['errors'] and not s.CANCELLED)
  signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT});pending=signal.sigpending() & {signal.SIGTERM,signal.SIGINT}
  if pending:result['pending_signals_at_commit']=sorted(pending);result['build_success']=False
  result['finished_ns']=time.time_ns();result['shared_lock_held_through_restore']=serial is not None
  result['state']='NORMAL_USER_PRODUCT_COMPLETED_SOURCE_RESTORED' if result['build_success'] else 'FAILED'
  ref=s.create(RESULT/'terminal.json',result)
  if serial is not None:os.close(serial)
  print(json.dumps({'state':result['state'],'terminal':ref,'build_success':result['build_success'],'owned_retirement_complete':result['owned_retirement_complete'],'input_after_qualified':result['input_after_qualified'],'errors':result['errors']}),flush=True)
 return 0 if result['build_success'] else 1

if __name__=='__main__':
 s.install_signals()
 fd=os.open(STATE/'inner-progress.jsonl',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
 with os.fdopen(fd,'w',buffering=1) as stream:
  with contextlib.redirect_stdout(stream):status=run_build()
  stream.flush();os.fsync(stream.fileno())
 raise SystemExit(status)


