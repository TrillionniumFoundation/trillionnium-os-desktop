def open_context_route_controls(task,q,plans,scope,source_sha):
 """Execute the real new open_context body; all OS/source/held I/O is explicitly synthetic."""
 cases=[]
 def run_fixture(mode):
  module=types.ModuleType('synthetic_IO_only_owned_retirement_context')
  exec(compile(OWNED_CONTEXT_SOURCE,'<exact-owned-context-with-explicit-IO-seams>','exec'),module.__dict__)
  events=[];written=[];targets=[]
  class P:
   def __init__(self,value):self.value=value
   def __truediv__(self,tail):return P(self.value+'/'+str(tail))
   def __str__(self):return self.value
   def is_dir(self):return True
   def is_relative_to(self,root):return self.value.startswith(str(root)+'/')
   def lstat(self):return types.SimpleNamespace(st_mode=stat.S_IFDIR|0o700,st_uid=0)
  root=P('/synthetic/flow');step=root/'steps/current-retirement'
  init={'host_pid':1};activation={'framework_epoch':{'binding':{'processes':{'init':init}}},'status':{'host_pid':2}}
  expected_scope=json.loads(json.dumps(scope));epoch=object()
  class Target:
   def __init__(self,actual,path,digest):
    need(actual==init,'FIXTURE_TARGET_IDENTITY');self.record=dict(actual);self.closed=False;targets.append(self)
   def verify(self):need(not self.closed,'FIXTURE_CLOSED_TARGET')
   def close(self):self.closed=True;events.append('held.close')
  def proc_open(path,flags):
   need(path=='/proc/1','FIXTURE_FIXED_PROC');events.append('proc.open');return 7
  def proc_close(fd):
   need(fd==7,'FIXTURE_FD');events.append('proc.close')
  module.os=types.SimpleNamespace(open=proc_open,close=proc_close,O_RDONLY=os.O_RDONLY,
   O_DIRECTORY=os.O_DIRECTORY,O_NOFOLLOW=os.O_NOFOLLOW,O_CLOEXEC=os.O_CLOEXEC)
  recorder=types.SimpleNamespace(APP='/synthetic/app.py',APP_SHA='1'*64,
   task_functions=lambda path:types.SimpleNamespace(exact_leaf=lambda *a:True))
  held=types.SimpleNamespace(proc_identity_at=lambda fd,pid,deadline:dict(init),HeldTarget=Target)
  def classpaths(held_arg,target_arg,framework,epoch_arg,guard):
   guard();events.append('classpath');return {'CLASSPATH':'synthetic'},{'synthetic':True}
  binding=types.SimpleNamespace(same_epoch_identity=lambda left,right:left==right,main_classpaths=classpaths)
  def load(name,label):
   need(name in ('recorder.py','references/held_runtime_r5.py','main_binding.py'),'FIXTURE_EXACT_MODULE')
   return {'recorder.py':recorder,'references/held_runtime_r5.py':held,'main_binding.py':binding}[name]
  contract=types.SimpleNamespace(sha256=task.CURRENT_HOST_MANIFEST,verify=lambda:events.append('contract.verify'),load=load)
  source=types.SimpleNamespace(SourceContract=lambda path,pin:contract,HELPER_PATH=P('/synthetic/helper'),HELPER_BYTES=1,
   HELPER_SHA='2'*64,verify_shared_helper=lambda:{'whole_process_tree_cleanup_qualified':False})
  def module_read(path,*args,**kwargs):
   value=str(path)
   if value.endswith('/scope.json'):return canon(expected_scope)
   if value.endswith('/baseline.json') or value=='/synthetic/baseline':return b'B'
   if value.endswith('/baseline-qualification.json') or value=='/synthetic/qualification':return b'Q'
   return b'x'
  def load_module(path,pin,label):
   return source if str(path).endswith('/source_contract.py') else types.SimpleNamespace()
  util=types.SimpleNamespace(module=load_module,read=module_read,verify_source=lambda sha:None,HERE=P('/synthetic/install-source'))
  def main_guard(baseline,epoch_arg):
   need(baseline is activation and epoch_arg is epoch,'FIXTURE_MAIN_ARGUMENTS')
   events.append('Main.guard');return dict(MAIN_BEFORE_FIXED)
  def write_new(path,value):written.append((str(path),value))
  ref=types.SimpleNamespace(current_baseline=lambda:activation,EPOCH_SOURCE='/synthetic/epoch.py',EPOCH_SOURCE_SHA='3'*64,
   module=lambda *args:epoch,read=module_read,main_guard=main_guard,write_new=write_new,
   BASELINE='/synthetic/baseline',BASELINE_SHA=task.CURRENT_BASELINE_SHA,
   QUALIFICATION='/synthetic/qualification',QUALIFICATION_SHA=task.CURRENT_QUALIFICATION_SHA)
  def discover(*args):
   events.append('current.discovery')
   return (99 if mode=='wrong_discovery_init' else 1),{'CLASSPATH':'synthetic'},{'host_pid':2}
  context=types.SimpleNamespace(INSTALLED_SHARED=P('/synthetic/shared'),CONTRACT_SHA='4'*64,
   SHARED_MANIFEST=task.CURRENT_HOST_MANIFEST,baseline_scope=lambda *args:{'package':PACKAGE,'uid':10137},
   verify_target_data=lambda *args:None,current_discovery=discover)
  transport=types.SimpleNamespace(FRAMEWORK_EPOCH_SHA256=task.CURRENT_EPOCH,
   environment_values=lambda value:dict(value),BoundArun=lambda **kwargs:object())
  def verify_runtime(value):
   need(value==SOURCE_MANIFEST,'FIXTURE_SOURCE_ARGUMENT')
   if mode=='reject_source':raise RuntimeError('SYNTHETIC_SOURCE_REJECTED')
   events.append('source.verify')
  flow_type=module.make_flow_type(task,new_retirement_scope(source_sha),source_sha)
  result={}
  try:
   flow,actual_recorder,guard=module.open_independent_context(task,flow_type,ref,util,context,SOURCE_MANIFEST,verify_runtime,
    root,step,transport,result,time.monotonic()+30,'cleanup',q.qa,plans,q.resolver.RESOLVE,expected_scope,
    install_source_manifest=q.resolver.INSTALL_SOURCE_SHA)
  except RuntimeError as error:
   if mode=='reject_source':
    need(str(error)=='SYNTHETIC_SOURCE_REJECTED' and not targets and not written and 'proc.open' not in events,
     'SOURCE_FAILURE_BEFORE_HELD_IO')
   elif mode=='wrong_discovery_init':
    need(str(error)=='FIXED_MAIN_DISCOVERY_CHANGED' and len(targets)==1 and targets[0].closed and not written and
     events.count('proc.open')==events.count('proc.close')==events.count('held.close')==1,
     'WRONG_DISCOVERY_INIT_CLOSES_OWNED_HELD_TARGET')
   else:raise
   return
  need(mode=='positive' and actual_recorder is recorder and isinstance(flow,flow_type) and
   len(written)==1 and written[0][0]==str(step/'held-main-binding.json') and
   written[0][1]['target_package']==PACKAGE and written[0][1]['target_uid']==10137 and
   written[0][1]['amazon_task_runtime_source_manifest']==SOURCE_MANIFEST and
   written[0][1]['Bili_Flow_instantiated'] is False and
   flow.scope==expected_scope and flow.policy.phase=='cleanup' and
   flow.retirement_authority is None and
   events.count('proc.open')==events.count('proc.close')==1 and not targets[0].closed,
   'REAL_OPEN_CONTEXT_REACHES_TYPED_HELD_BINDING_WITH_UID')
  flow.close();need(targets[0].closed and events.count('held.close')==1,'RETURNED_FLOW_CLOSES_HELD_TARGET')
 for mode,name in (('positive','real-open-context-reaches-held-binding-UID-and-original-Flow'),
  ('reject_source','real-open-context-source-rejection-before-held-IO'),
  ('wrong_discovery_init','real-open-context-wrong-discovery-init-closes-held-target')):
  run_fixture(mode);cases.append({'name':name,'passed':True})
 need(len(cases)==3,'EXACT_THREE_OPEN_CONTEXT_ROUTE_CONTROLS')
 return cases
