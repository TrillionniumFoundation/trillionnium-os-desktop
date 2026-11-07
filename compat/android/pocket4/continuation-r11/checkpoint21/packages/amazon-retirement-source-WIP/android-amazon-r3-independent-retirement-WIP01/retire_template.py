"""Independent exact Amazon leaf retirement after unknown native launch; no replay or fabricated launch scope."""
import datetime,hashlib,json,math,os,stat,time,types
from pathlib import Path,PurePosixPath
ROOT=Path('/home/alex/work/pocket4-amazon-r3-current-search-entry-01')
SOURCE=ROOT/'source'
FLOW=Path('/home/alex/work/pocket4-amazon-owned-qa-r3-flow-42ee4dd8ab30f563567ba353deff430c')
STEP=FLOW/'steps/native-launch-retirement-01'
POST_STEP=FLOW/'steps/native-launch-retirement-after-01'
MARKER=FLOW/'reconciliations/native-launch-retirement-attempt-01.json'
RECONCILIATION=FLOW/'reconciliations/native-launch-retirement-01.json'
PACKAGE='com.amazon.mShop.android.shopping'
COMPONENT=PACKAGE+'/com.amazon.mShop.home.HomeActivity'
SOURCE_MANIFEST='452b2c85207d60d5e47efbeafc05f49ecae416fabf6988fb7362100d55d6e46c'
ENTRY_PIN={'bytes':40297,'sha256':'7f64037f79317f2e370e0504f75032b945756521984009f0cdc5f068c721bab5'}
WORKER_PIN={'bytes':14255,'sha256':'471fd0060d935a14af74a30206607d58267c96982769cb24e442fa5c92ecf95c'}
SCOPE_FIXED=json.loads("{\"schema\":\"pocket4-current-recorder-scope-v1\",\"current_baseline_schema\":\"pocket4-main-current-baseline-v1\",\"package\":\"com.amazon.mShop.android.shopping\",\"component\":\"com.amazon.mShop.android.shopping/com.amazon.mShop.home.HomeActivity\",\"uid\":10129,\"user\":0,\"nonce\":\"42ee4dd8ab30f563567ba353deff430c\",\"epoch_sha256\":\"734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2\",\"current_baseline_sha256\":\"163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266\",\"current_baseline_qualification_sha256\":\"f37b2eb00db80c398c9a4f9fd895628b6c7ecc827ccf9699c2242fa5ba862ed6\",\"amazon_task_source_manifest_sha256\":\"452b2c85207d60d5e47efbeafc05f49ecae416fabf6988fb7362100d55d6e46c\",\"automatic_retry\":false,\"original_recorder_manifest_sha256\":\"6d99374e1580083fd0f30b7f9b3c520306680760c97ad0d5400798fda427fb6e\",\"actual_resolution_result_sha256\":\"ebeaecf791eba4906502cd3167c08e735d826ffd565f7fdd45d66775c016c534\"}")
INPUTS=__ACTUAL_RETIREMENT_INPUTS__
TASK=INPUTS['task']
STACKS=['/system/bin/cmd','activity','stack','list']
def need(value,code):
 if not value:raise RuntimeError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def pin(raw):return {'bytes':len(raw),'sha256':sha(raw)}
def canon(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
def read_exact(path,expected,maximum=65536):
 need(type(expected) is dict and set(expected)=={'bytes','sha256'} and type(expected['bytes']) is int and
  0<=expected['bytes']<=maximum,'EXACT_FILE_PIN_REQUIRED')
 current=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);fd=None
 try:
  for part in path.parts[1:-1]:
   nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current)
   try:os.close(current)
   except BaseException:
    os.close(nxt);raise
   current=nxt
  fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current)
  first=os.fstat(fd)
  need(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and first.st_uid==0 and first.st_size==expected['bytes'],
   'ROOT_SINGLE_REGULAR_EXACT_INPUT')
  chunks=[];size=0
  while True:
   part=os.read(fd,min(65536,maximum+1-size))
   if not part:break
   size+=len(part);chunks.append(part);need(size<=maximum,'READ_BOUND')
  last=os.fstat(fd)
  fields=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
  need(size==first.st_size and all(getattr(first,k)==getattr(last,k) for k in fields),'EXACT_FILE_CHANGED')
  raw=b''.join(chunks);need(pin(raw)==expected,'EXACT_FILE_SHA');return raw
 finally:
  try:
   if fd is not None:os.close(fd)
  finally:os.close(current)
def task_projection(raw,roots,tasks):
 rows=[]
 for rid,root in sorted(roots.items()):
  children=[]
  for child in root['children']:
   component=child['component'];pub=component==COMPONENT
   children.append({'id':child['id'],'user':child['user'],'target_component_match':pub,
    'component_utf8_bytes':len(component.encode()),'component_sha256':sha(component.encode()),
    'public_target_component':COMPONENT if pub else None})
  rows.append({'id':rid,'display':root['display'],'user':root['user'],'freeform':root['freeform'],
   'children':children,'complete_root_record_sha256':sha(canon(root))})
 return {'raw_pin':pin(raw),'tasks':sorted(tasks),'roots':rows,'complete_parsed_roots_sha256':sha(canon(roots)),
  'unknown_component_names_exported':False,'task_cleanup_authority_created':False}

def safe_error(error):
 value=str(error);out={'type':type(error).__name__,'message_sha256':sha(value.encode('utf-8','replace')),
  'raw_message_exported':False}
 if isinstance(error,RuntimeError) and value.isascii() and value.replace('_','').isalnum() and value.upper()==value and len(value)<=128:
  out['fixed_code']=value
 if type(getattr(error,'errno',None)) is int:out['errno']=error.errno
 if type(getattr(error,'command_observation',None)) is dict:out['command_observation']=error.command_observation
 return out
class ReadOnlyView:
 """Composition only: no replacement of the original Flow, Policy, runner or guard."""
 def __init__(self,flow,task):
  self.flow,self.task=flow,task;self.counts={}
  self.allowed={tuple(task.LIST):('target_uid',15),tuple(task.PATHS):('target_path',15),
   tuple(task.OWN_UID):('helper_uid',8),tuple(task.OWN_PATH):('helper_path',8),tuple(task.STACKS):('stacks',20)}
 @property
 def contract(self):return self.flow.contract
 @property
 def scope(self):return self.flow.scope
 @property
 def _private_backend_transport(self):return self.flow._private_backend_transport
 @property
 def target(self):return self.flow.target
 @property
 def deadline(self):return self.flow.deadline
 @property
 def artifacts(self):return self.flow.artifacts
 @artifacts.setter
 def artifacts(self,value):self.flow.artifacts=value
 def guard(self,attempted=False):
  need(attempted is False and self.flow.action_attempted is False and not self.flow.launch_claimed,'OBSERVATION_ONLY_FLOW')
  return self.flow.guard(attempted=False)
 def bind(self):self.guard();return self.flow.bind()
 def android(self,argv,timeout=20,*,mutation=False):
  need(type(argv) is list and all(type(v) is str for v in argv) and type(mutation) is bool and mutation is False,
   'ONLY_NONMUTATING_OBSERVATION')
  row=self.allowed.get(tuple(argv))
  need(row is not None and type(timeout) is int and timeout==row[1],'ONLY_FIVE_EXACT_READ_COMMANDS')
  key=row[0];count=self.counts.get(key,0);need(count<2,'EXACT_READ_COMMAND_LIMIT')
  self.guard();self.counts[key]=count+1
  # The original Amazon Policy.admit, BoundArun and recorder all still run.
  return self.flow.android(argv,timeout,mutation=False)
def gate_controls(task,qa,plan):
 cases=[]
 class Stub:
  def __init__(self):
   self.policy=task.Policy('launch',qa,['synthetic-resolve'],plan,Path('/synthetic'),lambda *a:None,lambda:None)
   self.action_attempted=False;self.launch_claimed=False;self.closed=False;self.calls=[]
  def guard(self,attempted=False):need(attempted is False,'SYNTHETIC_NO_MUTATION')
  def android(self,argv,timeout,*,mutation=False):
   self.policy.admit(argv,timeout,mutation,False);self.calls.append((list(argv),timeout,mutation));return b''
 def reject(name,fn):
  try:fn()
  except RuntimeError:cases.append({'name':name,'passed':True});return
  raise RuntimeError('READ_GATE_CONTROL_ACCEPTED')
 for name,argv,timeout in (('target_uid',task.LIST,15),('target_path',task.PATHS,15),
  ('helper_uid',task.OWN_UID,8),('helper_path',task.OWN_PATH,8),('stacks',task.STACKS,20)):
  f=Stub();view=ReadOnlyView(f,task)
  view.android(argv,timeout);view.android(argv,timeout)
  need(view.counts=={name:2} and f.policy.counts=={name:2} and len(f.calls)==2,'EXACT_DELEGATED_READ_COUNTS')
  reject(name+'_third_denied',lambda:view.android(argv,timeout))
  need(len(f.calls)==2,'REJECT_BEFORE_UNDERLYING_IO')
 f=Stub();view=ReadOnlyView(f,task)
 reject('mutation_denied',lambda:view.android(task.STACKS,20,mutation=True))
 reject('wrong_timeout_denied',lambda:view.android(task.STACKS,19))
 reject('foreign_package_denied',lambda:view.android(task.OWN_UID[:-1]+['foreign.pkg'],8))
 reject('instrument_denied',lambda:view.android(['/system/bin/am','instrument'],20))
 reject('remove_denied',lambda:view.android(['/system/bin/cmd','activity','stack','remove','123'],20))
 reject('native_launch_denied',lambda:view.android(['/usr/bin/droidloomctl','launch',PACKAGE],20))
 need(f.calls==[] and view.counts=={},'REJECTED_COMMANDS_NEVER_FORWARDED')
 need(len(cases)==11,'EXACT_ELEVEN_READ_GATE_CONTROLS')
 return cases

def qualify_task_set(roots,tasks,baseline_roots,baseline_tasks,task,exact_leaf):
 need(type(task) is int and 0<task<=2147483647,'EXACT_POSITIVE_RECONCILIATION_TASK')
 need(task not in baseline_tasks and task not in baseline_roots,'PREEXISTING_TASK_NEVER_RETIRE')
 need(set(tasks)-{task}==set(baseline_tasks),'OTHER_TASK_SET_CHANGED')
 need(set(roots)-{task}==set(baseline_roots),'OTHER_ROOT_SET_CHANGED')
 need(all(roots.get(k)==v for k,v in baseline_roots.items()),'PREEXISTING_ROOT_CONTENT_CHANGED')
 if task not in tasks and task not in roots:
  return {'status':'already_absent','removal_allowed':False}
 need(task in tasks and task in roots,'INCOMPLETE_TARGET_ROOT_TASK_PAIR')
 need(exact_leaf(roots,task,PACKAGE),'RECONCILIATION_NOT_EXACT_OWNED_LEAF')
 need(roots[task]['children'][0]['component']==COMPONENT,'EXACT_TARGET_COMPONENT_REQUIRED')
 return {'status':'exact_live_leaf','removal_allowed':True}

def task_set_controls(exact_leaf):
 rows=[]
 def passed(name,value):need(value,'TASK_GATE_CONTROL_'+name.upper());rows.append({'name':name,'passed':True})
 def rejected(name,call):
  try:call()
  except RuntimeError:passed(name,True);return
  raise RuntimeError('TASK_GATE_CONTROL_ACCEPTED_'+name.upper())
 base={1:{'display':0,'user':0,'freeform':False,
  'children':[{'id':870,'user':0,'component':'fixture.system/Fixture'}]}}
 target={'display':0,'user':0,'freeform':True,
  'children':[{'id':873,'user':0,'component':COMPONENT}]}
 def qualify(roots,tasks):return qualify_task_set(roots,tasks,base,{870},873,exact_leaf)
 passed('exact_live_leaf',qualify({**base,873:target},{870,873})=={'status':'exact_live_leaf','removal_allowed':True})
 passed('already_absent',qualify(base,{870})=={'status':'already_absent','removal_allowed':False})
 rejected('preserved_task_missing',lambda:qualify({873:target},{873}))
 rejected('unrelated_new_task',lambda:qualify({**base,873:target},{870,873,874}))
 rejected('unrelated_new_root',lambda:qualify({**base,873:target,874:target},{870,873}))
 rejected('foreign_component',lambda:qualify({**base,873:{**target,'children':[{'id':873,'user':0,'component':'other.app/Main'}]}},{870,873}))
 rejected('wrong_same_package_component',lambda:qualify({**base,873:{**target,'children':[{'id':873,'user':0,'component':PACKAGE+'/Other'}]}},{870,873}))
 rejected('wrong_display',lambda:qualify({**base,873:{**target,'display':1}},{870,873}))
 rejected('wrong_user',lambda:qualify({**base,873:{**target,'user':1}},{870,873}))
 rejected('non_leaf',lambda:qualify({**base,873:{**target,'children':target['children']+[{'id':874,'user':0,'component':COMPONENT}]}},{870,873}))
 rejected('task_without_root',lambda:qualify(base,{870,873}))
 rejected('preexisting_target_id',lambda:qualify_task_set(base,{870},base,{870},870,exact_leaf))
 need(len(rows)==12,'TASK_GATE_CONTROL_COUNT')
 return rows


class RetirementAuthority:
 """New failure-reconciliation authority; no successful-launch scope is fabricated."""
 def __init__(self,task_id,baseline_roots,baseline_tasks,scope):
  need(type(task_id) is int and 0<task_id<=2147483647,'EXACT_RECONCILIATION_TASK')
  need(task_id not in baseline_roots and task_id not in baseline_tasks,'PREEXISTING_TASK_NEVER_RETIRE')
  self.task=task_id;self.baseline_roots=baseline_roots;self.baseline_tasks=baseline_tasks
  self.scope=json.loads(canon(scope));self.samples=[];self.claimed=False;self.armed=False
 def observe(self,roots,tasks,exact_leaf):
  need(len(self.samples)<2 and not self.claimed and not self.armed,'ONLY_TWO_PRE_REMOVE_SAMPLES')
  gate=qualify_task_set(roots,tasks,self.baseline_roots,self.baseline_tasks,self.task,exact_leaf)
  self.samples.append({'roots_sha256':sha(canon(roots)),'tasks':sorted(tasks),'qualification':gate})
  return gate
 def arm(self):
  need(len(self.samples)==2 and self.samples[0]==self.samples[1] and
   self.samples[1]['qualification']=={'status':'exact_live_leaf','removal_allowed':True} and not self.claimed,
   'TWO_EQUAL_FRESH_COMPLETE_LEAF_SAMPLES_REQUIRED')
  self.armed=True
 def claim(self,flow):
  need(self.armed and not self.claimed and flow.phase=='cleanup' and flow.scope==self.scope and
   flow.action_attempted is False and not flow.launch_claimed and not flow.poisoned,
   'SINGLE_EXPLICIT_CURRENT_RETIREMENT_ADMISSION')
  self.claimed=True
 def selected(self,flow):
  need(self.armed and self.claimed and flow.phase=='cleanup' and flow.scope==self.scope and
   not flow.launch_claimed,'EXACT_NEW_RECONCILIATION_AUTHORITY_REQUIRED')
  return {'schema':'pocket4-independent-failed-launch-leaf-authority-v1','task':self.task,
   'package':PACKAGE,'component':COMPONENT,'epoch_sha256':self.scope['epoch_sha256'],
   'prelaunch_absent':True,'cleanup_allowed':True,'source':'independent_historical_and_fresh_task_evidence',
   'original_launch_outcome':'unknown_retained','old_launch_scope_created':False,
   'prelaunch_task_ids':sorted(self.baseline_tasks)}

def reconciliation_flow_class(task,authority):
 class ReconciliationFlow(task.Flow):
  def selected_task(self):return authority.selected(self)
  def command(self,*args,**kwargs):raise RuntimeError('NATIVE_LAUNCH_FORBIDDEN_IN_RECONCILIATION')
  def launch_locked(self):raise RuntimeError('NATIVE_LAUNCH_FORBIDDEN_IN_RECONCILIATION')
  def cleanup(self):raise RuntimeError('ONLY_EXPLICIT_ONE_LEAF_RECONCILIATION')
 return ReconciliationFlow

class RetirementView(ReadOnlyView):
 def __init__(self,flow,task,authority):
  super().__init__(flow,task);self.authority=authority
 def guard(self,attempted=False):
  need(attempted is False and not self.flow.launch_claimed,'NO_NATIVE_LAUNCH_DURING_RETIREMENT')
  return self.flow.guard(attempted=self.flow.action_attempted)
 def android(self,argv,timeout=20,*,mutation=False):
  need(type(argv) is list and all(type(v) is str for v in argv) and mutation is False,'ONLY_RETIREMENT_READS_HERE')
  row=self.allowed.get(tuple(argv));need(row is not None,'ONLY_FIVE_RETIREMENT_READ_COMMANDS')
  key,expected=row
  if key=='stacks':
   need(isinstance(timeout,(int,float)) and not isinstance(timeout,bool) and math.isfinite(timeout) and 0<timeout<=20,
    'BOUNDED_COMPLETE_STACK_READ')
   limit=33
  else:
   need(type(timeout) is int and timeout==expected,'EXACT_RETIREMENT_METADATA_TIMEOUT');limit=2
  need(self.counts.get(key,0)<limit,'RETIREMENT_READ_COMMAND_LIMIT')
  self.guard();self.counts[key]=self.counts.get(key,0)+1
  return self.flow.android(argv,timeout,mutation=False)
 def remove_exact_current_leaf(self):
  self.guard();self.authority.claim(self.flow)
  return self.flow.android(['/system/bin/cmd','activity','stack','remove',str(self.authority.task)],20,mutation=True)

def open_reconciliation_context(ref,util,context,source_manifest,source_verify,flow_root,step,
                      transport,result,deadline,phase,qa,inspect_plan,resolve,expected_scope,task,flow_class):
    """Same held Main/classpath primitives as the qualified Amazon install.

    The only newly constructed object is the phase-restricted task Flow above.
    No original Bili Flow/MainBinding or old UI client constructor is called.
    """
    source=util.module(context.INSTALLED_SHARED/'source_contract.py',context.CONTRACT_SHA,
                       'amazon_task_shared_contract')
    contract=source.SourceContract(context.INSTALLED_SHARED/'source-manifest.json',context.SHARED_MANIFEST)
    recorder=contract.load('recorder.py','amazon_task_actual_command')
    held=contract.load('references/held_runtime_r5.py','amazon_task_actual_held_main')
    binding=contract.load('main_binding.py','amazon_task_shared_classpath_only')
    activation=ref.current_baseline()
    own_scope=context.baseline_scope(ref,activation)
    epoch=ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),ref.EPOCH_SOURCE,
                     'amazon_task_fixed_epoch')
    scope_raw=util.read(flow_root/'scope.json',65536)
    scope=json.loads(scope_raw)
    task.current_task_scope(scope,qa,contract)
    need(scope==expected_scope and all(scope[key]==value for key,value in own_scope.items()),
         'EXACT_NEW_CURRENT_AMAZON_FLOW_SCOPE_REQUIRED')
    need(util.read(flow_root/'baseline.json',expected=ref.BASELINE_SHA)==ref.read(ref.BASELINE,expected=ref.BASELINE_SHA)
         and util.read(flow_root/'baseline-qualification.json',expected=ref.QUALIFICATION_SHA)==ref.read(ref.QUALIFICATION,expected=ref.QUALIFICATION_SHA),
         'SAVED_TYPED_CURRENT_BASELINE_CHANGED')
    info=flow_root.lstat()
    need(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and not info.st_mode&0o077,
         'PRIVATE_ROOT_OWNED_NEW_FLOW_REQUIRED')
    target=None
    def guard():
        need(time.monotonic()<deadline,'AMAZON_PHASE_DEADLINE')
        source_verify(source_manifest);contract.verify()
        need(util.read(flow_root/'scope.json',65536)==scope_raw,'AMAZON_SCOPE_CHANGED')
        ref.read(recorder.APP,expected=recorder.APP_SHA)
        util.read(source.HELPER_PATH,source.HELPER_BYTES,source.HELPER_SHA,source.HELPER_BYTES)
        observation=ref.main_guard(activation,epoch)
        if target is not None:context.verify_target_data(target,activation,binding)
        return observation
    result['Main_before']=guard();result['shared_helper']=source.verify_shared_helper()
    expected=activation['framework_epoch']['binding']['processes']['init']
    proc=os.open('/proc/'+str(expected['host_pid']),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:actual=held.proc_identity_at(proc,expected['host_pid'],time.monotonic()+3)
    finally:os.close(proc)
    need(binding.same_epoch_identity(actual,expected),'FIXED_MAIN_INIT_IDENTITY_CHANGED')
    try:
        target=held.HeldTarget(actual,source.HELPER_PATH,source.HELPER_SHA);guard()
        app=util.module(Path(recorder.APP),recorder.APP_SHA,'amazon_task_discovery_only')
        init,discovered,status=app.discover()
        need(init==expected['host_pid'] and status['host_pid']==activation['status']['host_pid'],
             'FIXED_MAIN_DISCOVERY_CHANGED')
        values,classpath=binding.main_classpaths(held,target,activation['framework_epoch'],epoch,guard)
        need(all(discovered.get(k)==v for k,v in values.items()),'CLASSPATH_DISCOVERY_CHANGED')
        environment=transport.environment_values(discovered)
        tasks=recorder.task_functions(context.INSTALLED_SHARED/'references/task_scope_baseline.py')
        flow=flow_class(recorder=recorder,contract=contract,target=target,environment=environment,
            transport=transport,main_guard=guard,root=flow_root,step=step,phase=phase,
            scope=scope,activation=activation,tasks=tasks,qa=qa,inspect_plan=inspect_plan,
            resolve=resolve,read=util.read,deadline=deadline)
        ref.write_new(step/'held-main-binding.json',{'target':target.record,'classpath':classpath,
            'shared_helper':result['shared_helper'],'target_package':PACKAGE,'target_uid':UID,
            'shared_recorder_primitive_manifest':context.SHARED_MANIFEST,
            'amazon_task_runtime_source_manifest':source_manifest,'Bili_Flow_instantiated':False})
        return flow,recorder,lambda:ref.main_guard(activation,epoch)
    except BaseException as primary:
        if target is not None:
            try:target.close()
            except BaseException as secondary:primary.add_note('held target close: '+repr(secondary))
        raise


def retirement_controls(task,qa,adapter,transport,plan,exact_leaf,scope):
 rows=task_set_controls(exact_leaf)
 def passed(name,value=True):
  need(value,'RETIREMENT_CONTROL_'+name.upper());rows.append({'name':name,'passed':True})
 def rejected(name,call):
  try:call()
  except RuntimeError:passed(name);return
  raise RuntimeError('RETIREMENT_CONTROL_ACCEPTED_'+name.upper())
 base={1:{'display':0,'user':0,'freeform':False,
  'children':[{'id':870,'user':0,'component':'fixture.system/Fixture'}]}}
 leaf={'display':0,'user':0,'freeform':True,
  'children':[{'id':873,'user':0,'component':COMPONENT}]}
 roots={**base,873:leaf};tasks={870,873}
 class SyntheticPrivatePath(PurePosixPath):
  def is_dir(self):return True
 def build():
  accesses=[]
  def forbidden(*args,**kwargs):
   accesses.append('FORBIDDEN_IO');raise AssertionError('pure retirement constructor reached I/O')
  authority=RetirementAuthority(873,base,{870},scope)
  cls=reconciliation_flow_class(task,authority)
  root=SyntheticPrivatePath('/synthetic/current-amazon-reconciliation')
  target=types.SimpleNamespace(expected={'pid':42},helper_sha256=transport.HELD_HELPER_SHA256,
   verify=lambda:accesses.append('target'),entry=forbidden,close=forbidden)
  rec=types.SimpleNamespace(write_new=forbidden,Flow=types.SimpleNamespace(command=forbidden))
  flow=cls(recorder=rec,contract=types.SimpleNamespace(sha256=adapter.RECORDER_MANIFEST_SHA),
   target=target,environment={key:'/synthetic/non-authority' for key in transport.REQUIRED_ENV},
   transport=transport,main_guard=lambda:accesses.append('Main'),root=root,step=root/'steps'/'retire',
   phase='cleanup',scope=dict(scope),activation={'framework_epoch':{'binding':{'processes':{'init':{'host_pid':42}}}}},
   tasks=types.SimpleNamespace(exact_leaf=exact_leaf),qa=qa,inspect_plan=plan,resolve=['synthetic-resolve'],
   read=forbidden,deadline=time.monotonic()+60)
  return authority,flow,accesses
 authority,flow,accesses=build()
 need(type(flow.transport) is transport.BoundArun and not accesses,'REAL_CURRENT_CONSTRUCTOR_NO_IO')
 flow.guard()
 passed('real_current_Flow_BoundArun_constructor_and_guard',accesses==['Main','target'])
 rejected('no_selected_authority_before_fresh_tables',flow.selected_task)
 authority.observe(roots,tasks,exact_leaf)
 rejected('one_fresh_table_does_not_arm',authority.arm)
 rejected('original_Policy_rejects_remove_before_arm',
  lambda:flow.policy.admit(['/system/bin/cmd','activity','stack','remove','873'],20,True,False))
 authority.observe(roots,tasks,exact_leaf);authority.arm()
 authority.claim(flow);selected=flow.selected_task()
 passed('new_independent_selected_authority_after_two_equal_samples',
  selected['task']==873 and selected['package']==PACKAGE and selected['prelaunch_task_ids']==[870] and
  selected['old_launch_scope_created'] is False and 'launch_step' not in selected)
 flow.policy.admit(['/system/bin/cmd','activity','stack','remove','873'],20,True,False)
 passed('original_cleanup_Policy_admits_exact_new_authority_once',flow.policy.remove_attempted is True)
 rejected('authority_cannot_be_claimed_twice',lambda:authority.claim(flow))
 rejected('original_cleanup_Policy_cannot_remove_twice',
  lambda:flow.policy.admit(['/system/bin/cmd','activity','stack','remove','873'],20,True,False))
 authority,flow,accesses=build()
 authority.observe(base,{870},exact_leaf);authority.observe(base,{870},exact_leaf)
 rejected('already_absent_does_not_arm_remove',authority.arm)
 authority,flow,accesses=build()
 authority.observe(roots,tasks,exact_leaf)
 authority.samples[0]['roots_sha256']='f'*64
 authority.observe(roots,tasks,exact_leaf)
 rejected('different_complete_samples_do_not_arm',authority.arm)
 authority,flow,accesses=build()
 authority.observe(roots,tasks,exact_leaf);authority.observe(roots,tasks,exact_leaf);authority.arm()
 flow.scope['component']=PACKAGE+'/OtherActivity'
 rejected('scope_changed_after_fresh_observation_forbids_remove',lambda:authority.claim(flow))
 authority,flow,accesses=build()
 authority.observe(roots,tasks,exact_leaf);authority.observe(roots,tasks,exact_leaf);authority.arm();authority.claim(flow)
 rejected('original_Policy_rejects_foreign_task',
  lambda:flow.policy.admit(['/system/bin/cmd','activity','stack','remove','874'],20,True,False))
 rejected('original_Policy_rejects_read_flag_for_remove',
  lambda:flow.policy.admit(['/system/bin/cmd','activity','stack','remove','873'],20,False,False))
 rejected('native_launch_method_forbidden',lambda:flow.command([],70,mutation=True))
 rejected('old_success_scope_cleanup_method_forbidden',flow.cleanup)
 passed('all_new_authority_controls_never_entered_IO','FORBIDDEN_IO' not in accesses)
 authority,flow,accesses=build()
 authority.observe(roots,tasks,exact_leaf);authority.observe(roots,tasks,exact_leaf);authority.arm()
 admitted=[]
 def synthetic_transport(argv,timeout):
  admitted.append((list(argv),timeout,flow._android_mutation));return b''
 # Explicit I/O seam only; actual Flow.android, Policy and new view still run.
 flow.transport=synthetic_transport
 view=RetirementView(flow,task,authority)
 need(view.remove_exact_current_leaf()==b'','NEW_REMOVE_VIEW_RETURN')
 passed('new_view_forwards_once_through_real_Flow_and_Policy',
  admitted==[(['/system/bin/cmd','activity','stack','remove','873'],20,True)] and
  authority.claimed and flow.policy.remove_attempted and not flow._android_mutation)
 rejected('new_view_rejects_second_remove_before_transport',view.remove_exact_current_leaf)
 need(len(admitted)==1,'NO_SECOND_REMOVE_FORWARDED')
 need(len(rows)==30 and len({row['name'] for row in rows})==30,'EXACT_30_RETIREMENT_CONTROLS')
 return rows


def historical_evidence():
 need(INPUTS['actual_native_reader_qualified'] is True and INPUTS['actual_current_two_stack_read_qualified'] is True,
  'ACTUAL_NATIVE_AND_TWO_STACK_RECEIPTS_REQUIRED')
 rows={}
 names=('coordinator','stage','worker','native_intent','native_result','native_stdout','native_stderr',
        'scope','attempted','prelaunch_stacks','prelaunch_result','prelaunch_stdout','prelaunch_transport')
 for name in names:
  expected=INPUTS['historical_observations'][name]
  need(expected['path']==str(HIST.FILES[name]),'EXACT_HISTORICAL_SOURCE_PATH')
  rows[name]=read_exact(HIST.FILES[name],{k:expected[k] for k in ('bytes','sha256')},131072 if name in ('prelaunch_stacks','prelaunch_stdout') else 65536)
 c,s,w=(HIST.strict_json(rows[k]) for k in ('coordinator','stage','worker'))
 original=HIST.qualify_worker(c,s,w)
 intent=HIST.strict_json(rows['native_intent']);native=HIST.strict_json(rows['native_result'])
 HIST.qualify_intent(intent,native,original)
 projected=HIST.classify_native(rows['native_stdout'],rows['native_stderr'])
 need(projected==INPUTS['native_projection'] and projected['whole_error_attribution_qualified'] is False and
  projected['current_installed_source_version_verified'] is False and
  projected['closed_child_matches']==[{'labelled_fields':{'task':TASK},'line_index':1,'shape':'backend_different_registration_ownership'}],
  'EXACT_ACTUAL_NATIVE_CLOSED_CHILD_AND_UNRESOLVED_BOUNDARIES')
 scope=HIST.strict_json(rows['scope']);attempt=HIST.strict_json(rows['attempted'])
 HIST.qualify_scope(scope,attempt)
 need(scope==SCOPE_FIXED and attempt==INPUTS['scope_and_attempt'],'HISTORICAL_SCOPE_OR_ATTEMPT_CHANGED')
 previous=INPUTS['current_observation']
 need(previous['stack']['path']==str(FLOW/'steps/native-launch-state-read-01/current-stacks-02.txt') and
  previous['command']['path']==str(FLOW/'steps/native-launch-state-read-01/command-006.result.json'),
  'EXACT_CURRENT_OBSERVATION_PATHS')
 current_raw=read_exact(Path(previous['stack']['path']),{k:previous['stack'][k] for k in ('bytes','sha256')},131072)
 current_command_raw=read_exact(Path(previous['command']['path']),{k:previous['command'][k] for k in ('bytes','sha256')})
 current_command=HIST.strict_json(current_command_raw)
 qualify_read_command(current_command,current_raw,b'',False)
 need(HIST.utc(native['ended_utc'])<=HIST.utc(current_command['ended_utc']),'CURRENT_OBSERVATION_MUST_FOLLOW_NATIVE_ATTEMPT')
 need(not os.path.lexists(FLOW/'launch-scope.json'),'OLD_SUCCESS_SCOPE_MUST_REMAIN_ABSENT')
 return {'rows':rows,'worker':w,'scope':scope,'baseline_raw':rows['prelaunch_stacks'],
  'previous_current_raw':current_raw,'native_started_utc':intent['started_utc'],'native_ended_utc':native['ended_utc']}

def qualify_read_command(row,output,err,mutation):
 need(row.get('returncode')==0 and row.get('spawned') is True and row.get('owned_command_joined') is True and
  row.get('timed_out') is False and row.get('errors')==[] and row.get('error') is None and
  row.get('action_attempted') is mutation and row.get('automatic_retry') is False and
  row.get('stdout_sha256')==sha(output) and row.get('stderr_sha256')==sha(err) and err==b'',
  'EXACT_JOINED_RECONCILIATION_COMMAND')

def main():
 need(os.getuid()==os.geteuid()==0,'ROOT_OWNED_RECONCILIATION_REQUIRED')
 began=time.monotonic();os.umask(0o077)
 history=historical_evidence();scope=history['scope'];worker=history['worker']
 raw=read_exact(SOURCE/'owned_inspect.py',ENTRY_PIN)
 entry=types.ModuleType('fixed_amazon_reconciliation_entry');entry.__file__=str(SOURCE/'owned_inspect.py')
 exec(compile(raw,entry.__file__,'exec'),entry.__dict__)
 need(entry.HERE==SOURCE and entry.FLOW==FLOW and entry.PACKAGE==PACKAGE and entry.HELPER_UID==10154,'ACTUAL_CURRENT_AMAZON_ENTRY')
 q=entry.qualified(SOURCE_MANIFEST);u,ref=q.util,q.ref
 task=entry.load(SOURCE/'amazon_task_context.py',q.manifest['files']['amazon_task_context.py']['sha256'],'fixed_amazon_task_context')
 context=u.module(q.resolver.INSTALL_SOURCE/'amazon_context.py',q.resolver.CONTEXT_SHA,'current_amazon_artifact_context')
 transport=u.module(q.resolver.INSTALL_SOURCE/'amazon_transport.py',q.resolver.TRANSPORT_SHA,'current_amazon_reconciliation_transport')
 shared=u.module(context.INSTALLED_SHARED/'source_contract.py',context.CONTRACT_SHA,'current_shared_contract_for_amazon')
 contract=shared.SourceContract(context.INSTALLED_SHARED/'source-manifest.json',context.SHARED_MANIFEST)
 recorder=contract.load('recorder.py','current_amazon_command_primitives')
 tasks=recorder.task_functions(context.INSTALLED_SHARED/'references/task_scope_baseline.py')
 baseline_roots,baseline_tasks=tasks.parse_stacks(history['baseline_raw'].decode('utf-8','strict'))
 previous_roots,previous_tasks=tasks.parse_stacks(history['previous_current_raw'].decode('utf-8','strict'))
 need(task_projection(history['baseline_raw'],baseline_roots,baseline_tasks)==INPUTS['prelaunch'] and
  task_projection(history['previous_current_raw'],previous_roots,previous_tasks)==INPUTS['current_observation']['projection'],
  'COMPLETE_ACTUAL_BASELINE_AND_CURRENT_PROJECTIONS_REPRODUCED')
 need(qualify_task_set(previous_roots,previous_tasks,baseline_roots,baseline_tasks,TASK,tasks.exact_leaf)==
  {'status':'exact_live_leaf','removal_allowed':True},'ACTUAL_CURRENT_READ_MUST_PROVE_EXACT_NEW_LEAF')
 activation=ref.current_baseline()
 epoch=ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),ref.EPOCH_SOURCE,'current_amazon_reconciliation_epoch')
 guard=lambda:ref.main_guard(activation,epoch)
 result={'schema':'pocket4-amazon-independent-native-launch-retirement-v1','ok':False,'error':None,'secondary_errors':[],
  'source_sha256':SOURCE_SHA256,'historical_native_reader':INPUTS['native_reader_actual'],
  'historical_current_two_stack_reader':INPUTS['current_reader_actual'],'task':TASK,'component':COMPONENT,
  'historical_launch_outcome_unknown_retained':True,'original_launch_scope_created':False,
  'native_registration_replayed':False,'Composer_control_remove_sent':False,
  'maximum_Android_task_remove_commands':1,'remove_requested':False,'remove_acknowledged':False,
  'removal_action_attempted':False,'retirement_outcome_unknown':False,'before_tables':[],
  'completion_observations':[],'command_records':[],'independent_after_attempted':False,'independent_after_completed':False,
  'helper_instrumentation_calls':0,'Bili_Flow_instantiated':False,'helper_nonce_values_consumed':False,
  'whole_process_tree_cleanup_qualified':False,'business_success_verified':False,'whole_app_production_ready':False}
 flow=artifacts=session=view=action_lock=flow_lock=resources=None;stage='admission';step_created=False
 authority=RetirementAuthority(TASK,baseline_roots,baseline_tasks,scope)
 def remember(where,error):
  item={'phase':where,**safe_error(error)}
  if result['error'] is None:result['error']=item
  else:result['secondary_errors'].append(item)
 def command_record(step,index,mutation=False,expected_output=None):
  stem=step/('command-%03d'%index);raw=u.read(str(stem)+'.result.json',65536);row=json.loads(raw)
  output=u.read(str(stem)+'.stdout',131072);err=u.read(str(stem)+'.stderr',65536)
  if expected_output is not None:need(output==expected_output,'COMMAND_AND_OBSERVED_STACK_DIFFER')
  qualify_read_command(row,output,err,mutation)
  record={'path':str(stem)+'.result.json',**pin(raw),'command':row}
  if not any(item['path']==record['path'] for item in result['command_records']):result['command_records'].append(record)
  return record
 def retain(step,count):
  for index in range(1,min(count,42)+1):
   path=step/('command-%03d.result.json'%index)
   if any(item['path']==str(path) for item in result['command_records']):continue
   try:
    raw=u.read(path,65536);result['command_records'].append({'path':str(path),**pin(raw),'command':json.loads(raw)})
   except BaseException as error:remember('retain_command_metadata',error)
 def verify_runtime(value):
  entry.verify_source(value);u.verify_source(q.resolver.INSTALL_SOURCE_SHA)
  entry.read(entry.RESOLVER_SOURCE,32768,entry.RESOLVER_SHA,entry.RESOLVER_BYTES)
  read_exact(SOURCE/'owned_inspect.py',ENTRY_PIN)
  for name in ('scope','attempted'):
   p=INPUTS['historical_observations'][name]
   read_exact(Path(p['path']),{k:p[k] for k in ('bytes','sha256')})
  need(not os.path.lexists(FLOW/'launch-scope.json'),'OLD_SUCCESS_SCOPE_MUST_REMAIN_ABSENT')
 def create_step(path,phase):
  need(not os.path.lexists(path),'RECONCILIATION_STEP_CANNOT_BE_REPLAYED')
  path.mkdir(mode=0o700)
  ref.write_new(path/'intent.json',{'schema':1,'source_sha256':SOURCE_SHA256,'phase':phase,'task':TASK,
   'historical_launch_outcome':'unknown_retained','native_launches':0,'helper_instrumentation_calls':0,
   'maximum_Android_task_removal':1 if path==STEP else 0,'automatic_retry':False})
 def close_primary():
  if artifacts is not None:
   try:
    if len(artifacts.records)==3 and 'target_after' not in result:
     result['failed_scope_files_revalidated']=artifacts.revalidate_files()
   except BaseException as error:remember('failed_scope_revalidation',error)
   try:result['target_FD_cleanup']=artifacts.close()
   except BaseException as error:remember('target_FD_cleanup',error)
  if flow is not None:
   result['actual_command_count']=flow.command_index;result['removal_action_attempted']=flow.action_attempted
   try:flow.guard(attempted=flow.action_attempted);result['final_primary_held_guard_passed']=True
   except BaseException as error:remember('final_primary_held_guard',error)
   try:flow.close();result['primary_held_binding_released']=True
   except BaseException as error:remember('primary_held_binding_release',error)
   retain(STEP,flow.command_index)
 try:
  resources=u.prepare_owned_limits();result['owned_before']=resources
  result['Main_before_lock']=guard()
  need(result['Main_before_lock']==worker['Main_after'],'CURRENT_MAIN_DIFFERS_FROM_ORIGINAL_FAILED_LAUNCH')
  result['retirement_controls']=retirement_controls(task,q.qa,q.adapter,transport,entry.PLAN,tasks.exact_leaf,scope)
  result['read_gate_controls']=gate_controls(task,q.qa,entry.PLAN)
  result['flow_lock_admission']={};flow_lock=u.acquire_action_lock(FLOW/'flow.lock',result['flow_lock_admission'])
  result['global_lock_admission']={};action_lock=u.acquire_action_lock(recorder.ACTION_LOCK,result['global_lock_admission'])
  result['Main_after_locks']=guard()
  need(not os.path.lexists(MARKER) and not os.path.lexists(RECONCILIATION),'NO_INDEPENDENT_RETIREMENT_REPLAY')
  recon=FLOW/'reconciliations'
  if not os.path.lexists(recon):recon.mkdir(mode=0o700)
  info=recon.lstat();need(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and not info.st_mode&0o077,'PRIVATE_RECONCILIATION_DIRECTORY')
  create_step(STEP,'independent-failed-native-leaf-retirement');step_created=True
  stage='held_current_amazon_reconciliation'
  cls=reconciliation_flow_class(task,authority)
  flow,recorder,phase_guard=open_reconciliation_context(ref,u,context,SOURCE_MANIFEST,verify_runtime,FLOW,STEP,
   transport,result,began+210,'cleanup',q.qa,entry.PLAN,q.resolver.RESOLVE,scope,task,cls)
  need(result['Main_before']==result['Main_before_lock'],'PRIMARY_CONTEXT_MAIN_MAP_CHANGED')
  view=RetirementView(flow,task,authority)
  reference=json.loads(u.read(q.resolver.INSTALL_SOURCE/'target-artifact-reference.json',expected=q.install_manifest['files']['target-artifact-reference.json']['sha256']))
  reader=u.module(q.resolver.INSTALL_SOURCE/'references/read_amazon.py',u.READER_SHA,'current_amazon_artifact_parser')
  artifacts=context.ArtifactSet(view,reference,reader)
  stage='current_target_before';result['target_before']=artifacts.before()
  session=q.adapter.Session(view,recorder,q.qa,q.proof,entry.HELPER_UID)
  stage='current_helper_before';result['helper_before']=session.installed()
  need(result['helper_before']==q.installed,'CURRENT_INSTALLED_HELPER_CHANGED')
  for number in (1,2):
   stage='fresh_pre_retirement_table_'+str(number)
   raw=view.android(task.STACKS,20);roots,task_ids=tasks.parse_stacks(raw.decode('utf-8','strict'))
   command_record(STEP,flow.command_index,False,raw)
   need(flow.command_index==4+number and not flow.action_attempted,'FRESH_PRE_RETIREMENT_READS_ONLY')
   gate=authority.observe(roots,task_ids,tasks.exact_leaf)
   result['before_tables'].append({**task_projection(raw,roots,task_ids),'qualification':gate,'sample':number})
   flow.guard()
  need(authority.samples[0]==authority.samples[1],'FRESH_COMPLETE_TABLES_CHANGED')
  result['before_tables_qualified']=True
  if gate['status']=='already_absent':
   result['already_absent_without_removal']=True
  else:
   authority.arm();flow.guard()
   ref.write_new(MARKER,{'schema':'pocket4-independent-failed-launch-retirement-attempt-v1','source_sha256':SOURCE_SHA256,
    'task':TASK,'component':COMPONENT,'historical_launch_outcome':'unknown_retained',
    'actual_native_reader':INPUTS['native_reader_actual'],'actual_current_reader':INPUTS['current_reader_actual'],
    'time_utc':recorder.now(),'automatic_retry':False})
   result['remove_requested']=True;stage='one_exact_Android_leaf_removal'
   removed=view.remove_exact_current_leaf()
   need(flow.command_index==7,'EXACTLY_ONE_SEVENTH_REMOVE_COMMAND')
   command_record(STEP,7,True,removed);result['remove_acknowledged']=True
   def completion_record(value):
    index=len(result['completion_observations'])+1
    need(type(value) is dict and type(value.get('raw_stacks')) is str,'COMPLETE_REMOVAL_READBACK_REQUIRED')
    ref.write_new(STEP/('private-retirement-readback-%02d.json'%index),value)
    r,t=tasks.parse_stacks(value['raw_stacks'])
    need(set(t)-{TASK}==baseline_tasks and set(r)-{TASK}==set(baseline_roots) and
     all(r.get(k)==v for k,v in baseline_roots.items()),'OTHER_ROOT_OR_TASK_CONTENT_CHANGED')
    result['completion_observations'].append({'sample':index,**task_projection(value['raw_stacks'].encode(),r,t),
     'target_absent':TASK not in r and TASK not in t})
   def completion_stacks(timeout):
    raw=view.android(task.STACKS,timeout)
    command_record(STEP,flow.command_index,False,raw)
    return raw.decode('utf-8','strict')
   stage='bounded_independent_completion_reads'
   result['normal_completion']=tasks.wait_for_removal(completion_stacks,TASK,PACKAGE,task_ids,completion_record)
   result['normal_removal_verified']=True
  stage='current_helper_after';result['helper_after']=session.installed()
  need(result['helper_after']==result['helper_before'],'CURRENT_HELPER_CHANGED')
  stage='current_target_after';result['target_after']=artifacts.after()
  need(result['target_after']==result['target_before'],'CURRENT_TARGET_CHANGED')
  expected=8+view.counts['stacks']+int(result['remove_requested'])
  need(flow.command_index==expected and session.nonces==set() and not flow.launch_claimed and
   {k:v for k,v in view.counts.items() if k!='stacks'}=={'target_uid':2,'target_path':2,'helper_uid':2,'helper_path':2},
   'EXACT_PRIMARY_RETIREMENT_COMMAND_BUDGET')
  for index in range(1,flow.command_index+1):command_record(STEP,index,index==7 and result['remove_requested'])
  result['primary_sequence_completed']=True
 except BaseException as error:remember(stage,error)
 finally:
  close_primary()
  # A poisoned/failed mutating Flow is never re-used. This fresh Context only
  # observes the independent after-table while both serialization locks remain held.
  if result.get('before_tables_qualified') is True and action_lock is not None and flow_lock is not None and result.get('primary_held_binding_released') is True:
   result['independent_after_attempted']=True
   post_flow=post_artifacts=post_session=None;post={}
   try:
    create_step(POST_STEP,'independent-read-only-after-retirement')
    post_flow,recorder,post_guard=task.open_task_context(ref,u,context,SOURCE_MANIFEST,verify_runtime,FLOW,POST_STEP,
     transport,post,began+285,'launch',q.qa,entry.PLAN,q.resolver.RESOLVE,scope)
    need(post['Main_before']==result['Main_before_lock'],'INDEPENDENT_AFTER_MAIN_MAP_CHANGED')
    post_view=ReadOnlyView(post_flow,task)
    post_artifacts=context.ArtifactSet(post_view,reference,reader)
    post['target_before']=post_artifacts.before()
    post_session=q.adapter.Session(post_view,recorder,q.qa,q.proof,entry.HELPER_UID)
    post['helper_before']=post_session.installed()
    need(post['helper_before']==q.installed,'POST_CURRENT_HELPER_CHANGED')
    raw=post_view.android(task.STACKS,20);r,t=tasks.parse_stacks(raw.decode('utf-8','strict'))
    command_record(POST_STEP,post_flow.command_index,False,raw)
    post['independent_table']=task_projection(raw,r,t)
    need(r==baseline_roots and t==baseline_tasks and TASK not in r and TASK not in t,
     'INDEPENDENT_AFTER_EXACT_BASELINE_RESTORATION_REQUIRED')
    post['helper_after']=post_session.installed()
    post['target_after']=post_artifacts.after()
    need(post['helper_after']==post['helper_before'] and post['target_after']==post['target_before'] and
     post_flow.command_index==9 and not post_flow.action_attempted and not post_flow.launch_claimed and post_session.nonces==set() and
     post_view.counts=={'target_uid':2,'target_path':2,'helper_uid':2,'helper_path':2,'stacks':1},
     'EXACT_NINE_INDEPENDENT_READS')
    for index in range(1,10):command_record(POST_STEP,index)
    post['sequence_complete']=True
   except BaseException as error:remember('independent_after',error)
   finally:
    if post_artifacts is not None:
     try:
      if len(post_artifacts.records)==3 and 'target_after' not in post:post['failed_files_revalidated']=post_artifacts.revalidate_files()
     except BaseException as error:remember('independent_after_files',error)
     try:post['target_FD_cleanup']=post_artifacts.close()
     except BaseException as error:remember('independent_after_FD_cleanup',error)
    if post_flow is not None:
     try:post_flow.guard(attempted=False);post['final_held_guard_passed']=True
     except BaseException as error:remember('independent_after_final_guard',error)
     try:post_flow.close();post['held_binding_released']=True
     except BaseException as error:remember('independent_after_binding_release',error)
     retain(POST_STEP,post_flow.command_index)
    result['independent_after']=post
    result['independent_after_completed']=bool(post.get('sequence_complete') and post.get('final_held_guard_passed') and post.get('held_binding_released'))
  try:
   result['Main_after']=guard()
   need(result['Main_after']==result.get('Main_before_lock')==result.get('Main_after_locks'),'MAIN_RECONCILIATION_WINDOW_CHANGED')
  except BaseException as error:remember('independent_final_Main',error)
  for fd,name in ((action_lock,'global_action_lock'),(flow_lock,'flow_lock')):
   if fd is not None:
    try:os.close(fd);result[name+'_released']=True
    except BaseException as error:remember(name+'_release',error)
  try:entry.qualified(SOURCE_MANIFEST);result['source_and_artifact_inputs_unchanged']=True
  except BaseException as error:remember('final_source_closure',error)
  if resources is not None:
   try:result['owned_after']=u.owned_resources();u.resources_qualified(resources,result['owned_after'])
   except BaseException as error:remember('final_owned_resources',error)
 result['ok']=bool(result['error'] is None and not result['secondary_errors'] and result.get('primary_sequence_completed') is True and
  result['independent_after_completed'] and result.get('final_primary_held_guard_passed') and result.get('primary_held_binding_released') and
  result.get('global_action_lock_released') and result.get('flow_lock_released') and
  (result.get('already_absent_without_removal') or result.get('normal_removal_verified')))
 if result['ok']:
  try:
   receipt={'schema':'pocket4-amazon-independent-native-launch-reconciliation-v1','source_sha256':SOURCE_SHA256,
    'task':TASK,'component':COMPONENT,'original_launch_outcome':'unknown_retained','native_registration_replayed':False,
    'original_launch_scope_created':False,'authorizes_future_action_replay':False,'owned_Android_leaf_absent':True,
    'preexisting_roots_and_tasks_preserved':True,'actual_native_reader':INPUTS['native_reader_actual'],
    'actual_current_reader':INPUTS['current_reader_actual'],'before_tables':result['before_tables'],
    'independent_after':result['independent_after']['independent_table'],
    'command_pins':[{k:row[k] for k in ('path','bytes','sha256')} for row in result['command_records']]}
   ref.write_new(RECONCILIATION,receipt);raw=u.read(RECONCILIATION,65536)
   result['independent_reconciliation_receipt']={'path':str(RECONCILIATION),**pin(raw)}
  except BaseException as error:remember('durable_reconciliation_receipt',error);result['ok']=False
 result['retirement_outcome_unknown']=bool(result['removal_action_attempted'] and not result['ok'])
 if step_created:
  try:ref.write_new(STEP/'result.json',result)
  except BaseException as error:remember('durable_retirement_result',error);result['ok']=False
 result['retirement_outcome_unknown']=bool(result['removal_action_attempted'] and not result['ok'])
 raw=(json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
 need(len(raw)<=131072,'SAFE_RECONCILIATION_OUTPUT_BOUND')
 print(raw.decode(),end='',flush=True);return 0 if result['ok'] else 1
