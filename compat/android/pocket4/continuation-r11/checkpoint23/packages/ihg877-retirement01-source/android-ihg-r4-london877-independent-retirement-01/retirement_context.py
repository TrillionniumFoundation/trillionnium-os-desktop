"""Explicit current IHG task retirement context; original source remains frozen."""
import json,math,os,stat,time
from pathlib import Path
PACKAGE='com.ihg.apps.android'
UID=10137
TASK=877
COMPONENT=PACKAGE+'/'+PACKAGE+'.activity.MainActivity'
SCHEMA='pocket4-independent-current-IHG-task-retirement-scope-v1'
def need(value,code):
 if not value:raise RuntimeError(code)
def validate_retirement_scope(value,source_sha):
 fields={'schema','task','component','package','uid','user','epoch_sha256','baseline_sha256',
  'qualification_sha256','source_sha256','prelaunch_absent','cleanup_allowed',
  'independent_current_scope','original_launch_outcome','original_launch_scope_created',
  'authorizes_original_action_replay','native_reported_task_id'}
 need(type(value) is dict and set(value)==fields and value['schema']==SCHEMA and
  type(value['task']) is int and value['task']==TASK and value['component']==COMPONENT and
  value['package']==PACKAGE and value['uid']==10137 and value['user']==0 and
  value['epoch_sha256']=='7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c' and
  value['baseline_sha256']=='633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364' and
  value['qualification_sha256']=='ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e' and
  value['source_sha256']==source_sha and value['prelaunch_absent'] is True and value['cleanup_allowed'] is True and
  value['independent_current_scope'] is True and value['original_launch_outcome']=='unknown_retained' and
  value['original_launch_scope_created'] is False and value['authorizes_original_action_replay'] is False and
  value['native_reported_task_id'] is None,'EXACT_NEW_INDEPENDENT_IHG877_SCOPE')
 return True
def make_flow_type(task,bound_scope,source_sha):
 validate_retirement_scope(bound_scope,source_sha)
 frozen_scope=json.loads(json.dumps(bound_scope))
 class IndependentRetirementFlow(task.Flow):
  """An owned subclass, never a mutation of the original module or Policy."""
  def __init__(self,**options):
   need(options.get('phase')=='cleanup','ONLY_CURRENT_RETIREMENT_PHASE')
   super().__init__(**options)
   self.retirement_authority=None;self.retirement_counts={};self.retirement_remove_attempted=False
  def arm_after_exact_pair(self,first_roots,first_tasks,second_roots,second_tasks,preserved_roots,preserved_tasks):
   self.guard()
   need(self.command_index==6 and self.retirement_counts==self.policy.counts==
    {'target_uid':1,'target_path':1,'helper_uid':1,'helper_path':1,'stacks':2} and
    self.action_attempted is False and not self.launch_claimed and self.retirement_authority is None,
    'SIX_PRIOR_CURRENT_READS_BEFORE_RETIREMENT_ARM')
   need(first_roots==second_roots and first_tasks==second_tasks and
    set(second_tasks)-{TASK}==set(preserved_tasks) and set(second_roots)-{TASK}==set(preserved_roots) and
    all(second_roots.get(k)==v for k,v in preserved_roots.items()) and
    TASK not in preserved_tasks and TASK not in preserved_roots and
    self.tasks.exact_leaf(second_roots,TASK,PACKAGE) and
    second_roots[TASK]['children']==[{'id':TASK,'component':COMPONENT,'user':0}],
    'TWO_COMPLETE_CURRENT_TABLES_AND_EXACT_IHG877_LEAF')
   self.retirement_authority=json.loads(json.dumps(frozen_scope))
  def selected_task(self):
   need(self.retirement_authority==frozen_scope,'NEW_RETIREMENT_SCOPE_NOT_ARMED')
   validate_retirement_scope(self.retirement_authority,source_sha)
   return dict(self.retirement_authority)
  def android(self,argv,timeout=20,*,mutation=False):
   need(type(argv) is list and all(type(x) is str for x in argv) and type(mutation) is bool and
    type(timeout) in (int,float) and math.isfinite(timeout),
    'EXACT_INDEPENDENT_RETIREMENT_COMMAND_SHAPE')
   allowed={tuple(task.LIST):('target_uid',15,2),tuple(task.PATHS):('target_path',15,2),
    tuple(task.OWN_UID):('helper_uid',8,2),tuple(task.OWN_PATH):('helper_path',8,2)}
   if tuple(argv) in allowed:
    key,expected,limit=allowed[tuple(argv)]
    need(mutation is False and timeout==expected,'CURRENT_RETIREMENT_METADATA_ONLY')
   elif argv==task.STACKS:
    key,limit='stacks',33
    need(mutation is False and 0<timeout<=20,'CURRENT_RETIREMENT_STACK_READ_ONLY')
   else:
    need(argv==['/system/bin/cmd','activity','stack','remove',str(TASK)] and timeout==20 and mutation is True,
     'ONLY_EXACT_IHG877_REMOVE')
    self.selected_task()
    need(not self.retirement_remove_attempted and self.command_index==6,'SINGLE_REMOVE_AFTER_FRESH_PAIR')
    self.retirement_remove_attempted=True;key,limit='remove',1
   used=self.retirement_counts.get(key,0);need(used<limit,'INDEPENDENT_RETIREMENT_COMMAND_LIMIT')
   self.retirement_counts[key]=used+1
   # Original Policy.admit, BoundArun, held runner, guard and poison semantics remain active.
   return super().android(argv,timeout,mutation=mutation)
  def command(self,*args,**kwargs):raise RuntimeError('NATIVE_LAUNCH_FORBIDDEN_IN_INDEPENDENT_RETIREMENT')
  def launch_locked(self):raise RuntimeError('NATIVE_LAUNCH_FORBIDDEN_IN_INDEPENDENT_RETIREMENT')
  def cleanup(self):raise RuntimeError('ORIGINAL_LAUNCH_SCOPE_CLEANUP_FORBIDDEN')
 return IndependentRetirementFlow

def open_independent_context(task,flow_type,ref,util,context,source_manifest,source_verify,flow_root,step,
                      transport,result,deadline,phase,qa,inspect_plan,resolve,expected_scope, *,
                      install_source_manifest):
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
         'EXACT_NEW_CURRENT_IHG_FLOW_SCOPE_REQUIRED')
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
        init,discovered,status=context.current_discovery(
            util,install_source_manifest,util.verify_source,util.HERE,
            app,activation,epoch,guard)
        need(init==expected['host_pid'] and status['host_pid']==activation['status']['host_pid'],
             'FIXED_MAIN_DISCOVERY_CHANGED')
        values,classpath=binding.main_classpaths(held,target,activation['framework_epoch'],epoch,guard)
        need(all(discovered.get(k)==v for k,v in values.items()),'CLASSPATH_DISCOVERY_CHANGED')
        environment=transport.environment_values(discovered)
        tasks=recorder.task_functions(context.INSTALLED_SHARED/'references/task_scope_baseline.py')
        flow=flow_type(recorder=recorder,contract=contract,target=target,environment=environment,
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
