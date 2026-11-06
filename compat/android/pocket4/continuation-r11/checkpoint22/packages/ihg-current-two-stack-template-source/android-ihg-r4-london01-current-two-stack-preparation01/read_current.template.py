"""Exactly two current IHG task tables through its qualified Context; no UI/native replay/removal."""
import datetime,hashlib,json,os,stat,time,types
from pathlib import Path
ROOT=Path('/home/alex/work/pocket4-ihg-r4-public-london-input-01')
SOURCE=ROOT/'source'
FLOW=Path('/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b')
STEP=FLOW/'steps/native-launch-state-read-01'
PACKAGE='com.ihg.apps.android'
COMPONENT=PACKAGE+'/.activity.MainActivity'
SOURCE_MANIFEST='24a8491dbb44faf1288869d278da96290597b7af1fcdcce12a72fd62bad9435f'
ENTRY_PIN={"bytes":46630,"sha256":"562629c6c00d40a41cdf6fe2edf3df01292fb6f78409f8fd08b7776f02bf7bb0"}
WORKER_PIN={"bytes":12051,"sha256":"3ab8190051ab6c628a7e6b67c0f10567cb18e273db6ecc067b5856098e37034b"}
SCOPE_FIXED=json.loads("{\"schema\":\"pocket4-current-recorder-scope-v2\",\"current_baseline_schema\":\"pocket4-main-current-baseline-v2\",\"package\":\"com.ihg.apps.android\",\"component\":\"com.ihg.apps.android/.activity.MainActivity\",\"uid\":10137,\"user\":0,\"nonce\":\"ec4f2977574102b1e5869d2494e8416b\",\"epoch_sha256\":\"7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c\",\"current_baseline_sha256\":\"633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364\",\"current_baseline_qualification_sha256\":\"ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e\",\"amazon_task_source_manifest_sha256\":\"24a8491dbb44faf1288869d278da96290597b7af1fcdcce12a72fd62bad9435f\",\"automatic_retry\":false,\"original_recorder_manifest_sha256\":\"002ee581a4bb399536dd7d594d01f050e2540d9c049b0cfb37e1c96954b6caff\",\"actual_resolution_result_sha256\":\"153ddbfc8393570621b64a478675c2a0180826a7a6ecada0ade8a6aa4ed79722\"}")
MAIN_BEFORE_FIXED=json.loads("{\"Main_epoch_sha256\":\"7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c\",\"authenticated_owner_chain_matches\":true,\"config_sha256\":\"f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc\",\"current_baseline_qualification_sha256\":\"ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e\",\"current_baseline_sha256\":\"633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364\",\"current_executable_and_root_backing_match\":true,\"current_user_namespaces_match\":true,\"framework_exit_cause_resolved\":false,\"historical_activation_sha256\":\"7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615\",\"historical_verified_sha256\":\"2d6f2ef7953b98109044f823da56694111bd9f8ff14fff5e746afb7bd42b0387\",\"old_helpers_and_tasks_reauthorized\":false,\"previous_current_baseline_sha256\":\"163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266\",\"production_ready\":false,\"resource_limits_match\":true,\"schema\":\"pocket4-current-main-guard-v2\",\"seven_processes_match\":true,\"three_host_processes_match\":true}")
INPUTS=__ACTUAL_HISTORICAL_INPUTS__
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
def historical_worker_qualified(worker):
 need(worker.get('nonce')==SCOPE_FIXED['nonce'] and worker.get('source_manifest_sha256')==SOURCE_MANIFEST and
  worker.get('phase')=='launch' and worker.get('package')==PACKAGE and worker.get('uid')==10137 and
  worker.get('helper_package')=='org.droidloom.qa.ihg.r4' and worker.get('helper_uid')==10158 and
  worker.get('action_attempted') is True and worker.get('outcome_unknown') is True and
  worker.get('automatic_retry') is False and worker.get('durable_command_count')==7 and
  worker.get('held_binding_released') is True and worker.get('action_lock_released') is True and
  worker.get('flow_lock_released') is True and worker.get('Main_before')==MAIN_BEFORE_FIXED and
  worker.get('Main_before_lock')==MAIN_BEFORE_FIXED and 'Main_after' not in worker and
  'final_Main_guard_passed' not in worker and
  worker.get('secondary_errors')==[
   {'phase':'final_Main_guard','type':'RuntimeError','message':'OWNER_SINGLE_DIRECT_CHILD_REQUIRED'},
   {'phase':'independent_final_Main','type':'RuntimeError','message':'OWNER_SINGLE_DIRECT_CHILD_REQUIRED'}],
  'EXACT_ORIGINAL_FAILED_MAIN_WINDOW_RETAINED')
 return True
def historical_worker_controls(worker):
 cases=[]
 need(historical_worker_qualified(worker),'ACTUAL_HISTORICAL_WORKER_POSITIVE')
 cases.append({'name':'actual-historical-unknown-and-missing-final-Main-retained','passed':True})
 for name,value in (
  ('later-current-Main-cannot-fill-historical-after',{**worker,'Main_after':dict(MAIN_BEFORE_FIXED),'final_Main_guard_passed':True}),
  ('historical-final-Main-error-cannot-be-erased',{**worker,'secondary_errors':[]})):
  try:historical_worker_qualified(value)
  except RuntimeError:cases.append({'name':name,'passed':True});continue
  raise RuntimeError('HISTORICAL_WORKER_CONTROL_ACCEPTED')
 need(len(cases)==3,'EXACT_THREE_HISTORICAL_CONTROLS')
 return cases

def main():
 need(os.getuid()==os.geteuid()==0,'ROOT_OWNED_OBSERVATION_REQUIRED')
 need(type(INPUTS) is dict and INPUTS.get('actual_historical_chain_qualified') is True,'ACTUAL_HISTORICAL_CHAIN_REQUIRED')
 expected_paths={'scope':FLOW/'scope.json','attempted':FLOW/'launch-attempted.json',
  'prelaunch_stacks':FLOW/'steps/launch-01/prelaunch-stacks.txt'}
 private={}
 for key,path in expected_paths.items():
  p=INPUTS['historical_file_pins'][key]
  need(p['path']==str(path),'EXACT_HISTORICAL_PATH')
  private[key]=read_exact(path,{k:p[k] for k in ('bytes','sha256')},131072 if key=='prelaunch_stacks' else 65536)
 scope=json.loads(private['scope']);attempt=json.loads(private['attempted'])
 need(scope==SCOPE_FIXED and attempt==INPUTS['scope_and_attempt'] and attempt['scope']==scope,'HISTORICAL_SOURCE_SCOPE_AND_ATTEMPT')
 worker=json.loads(read_exact(FLOW/'steps/launch-01/result.json',WORKER_PIN))
 historical_worker_qualified(worker)
 need(not os.path.lexists(FLOW/'launch-scope.json'),'NO_OLD_SUCCESS_SCOPE_CREATED')
 raw=read_exact(SOURCE/'owned_inspect.py',ENTRY_PIN)
 entry=types.ModuleType('fixed_ihg_readonly_entry');entry.__file__=str(SOURCE/'owned_inspect.py')
 exec(compile(raw,entry.__file__,'exec'),entry.__dict__)
 need(entry.HERE==SOURCE and entry.FLOW==FLOW and entry.PACKAGE==PACKAGE and entry.HELPER_UID==10158,'ACTUAL_CURRENT_IHG_ENTRY')
 q=entry.qualified(SOURCE_MANIFEST);u,ref=q.util,q.ref
 task=entry.load(SOURCE/'ihg_task_context.py',q.manifest['files']['ihg_task_context.py']['sha256'],'fixed_ihg_task_context')
 context=u.module(q.resolver.INSTALL_SOURCE/'ihg_context.py',q.resolver.CONTEXT_SHA,'current_ihg_artifact_context')
 transport=u.module(q.resolver.INSTALL_SOURCE/'ihg_transport.py',q.resolver.TRANSPORT_SHA,'current_ihg_read_transport')
 shared=u.module(context.INSTALLED_SHARED/'source_contract.py',context.CONTRACT_SHA,'current_shared_contract_for_ihg')
 contract=shared.SourceContract(context.INSTALLED_SHARED/'source-manifest.json',context.SHARED_MANIFEST)
 recorder=contract.load('recorder.py','current_ihg_command_primitives')
 activation=ref.current_baseline()
 epoch=ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),ref.EPOCH_SOURCE,'current_ihg_read_epoch')
 guard=lambda:ref.main_guard(activation,epoch)
 result={'schema':'pocket4-ihg-london-native-launch-current-two-stack-observation-v1','ok':False,'error':None,'secondary_errors':[],
  'source_sha256':SOURCE_SHA256,'historical_chain':INPUTS['native_reader_actual'],
  'historical_launch_outcome_unknown_retained':True,'new_native_launches':0,'UI_actions':0,
  'package_mutations':0,'task_removals':0,'helper_instrumentation_calls':0,'cleanup_authority_created':False,
  'Bili_Flow_instantiated':False,'old_helper_nonce_values_consumed':False,'observations':[],
  'command_records':[],'whole_app_production_ready':False}
 flow=artifacts=session=action_lock=flow_lock=resources=None;stage='admission';step_created=False
 began=time.monotonic()
 def remember(where,error):
  item={'phase':where,**safe_error(error)}
  if result['error'] is None:result['error']=item
  else:result['secondary_errors'].append(item)
 def command_record(index):
  stem=STEP/('command-%03d'%index);raw=u.read(str(stem)+'.result.json',65536);row=json.loads(raw)
  output=u.read(str(stem)+'.stdout',131072);err=u.read(str(stem)+'.stderr',65536)
  need(row.get('returncode')==0 and row.get('spawned') is True and row.get('owned_command_joined') is True and
   row.get('timed_out') is False and row.get('errors')==[] and row.get('error') is None and
   row.get('action_attempted') is False and row.get('automatic_retry') is False and
   row.get('stdout_sha256')==sha(output) and row.get('stderr_sha256')==sha(err) and err==b'',
   'EXACT_JOINED_READ_ONLY_COMMAND')
  return {'path':str(stem)+'.result.json',**pin(raw),'command':row}
 try:
  resources=u.prepare_owned_limits();result['owned_before']=resources
  result['Main_before_lock']=guard()
  need(result['Main_before_lock']==MAIN_BEFORE_FIXED,'FRESH_CURRENT_MAIN_BASELINE_DIFFERS')
  # A new guarded observation never fills the missing historical Main_after.
  result['historical_final_Main_qualified']=False
  result['controls']=gate_controls(task,q.qa,entry.PLAN)+historical_worker_controls(worker)
  need(len(result['controls'])==14,'EXACT_FOURTEEN_READ_CONTROLS')
  result['flow_lock_admission']={};flow_lock=u.acquire_action_lock(FLOW/'flow.lock',result['flow_lock_admission'])
  result['global_lock_admission']={};action_lock=u.acquire_action_lock(recorder.ACTION_LOCK,result['global_lock_admission'])
  result['Main_after_locks']=guard()
  need(not os.path.lexists(STEP),'NO_READ_STEP_REPLAY')
  STEP.mkdir(mode=0o700);step_created=True
  ref.write_new(STEP/'intent.json',{'schema':1,'source_sha256':SOURCE_SHA256,'phase':'independent-current-two-stack-read',
   'maximum_stack_reads':2,'maximum_total_commands':10,'native_launches':0,'UI_actions':0,'task_removals':0,'automatic_retry':False})
  def verify_runtime(value):
   entry.verify_source(value);u.verify_source(q.resolver.INSTALL_SOURCE_SHA)
   entry.read(entry.RESOLVER_SOURCE,32768,entry.RESOLVER_SHA,entry.RESOLVER_BYTES)
   read_exact(SOURCE/'owned_inspect.py',ENTRY_PIN)
   for key,path in expected_paths.items():
    original=INPUTS['historical_file_pins'][key]
    read_exact(path,{k:original[k] for k in ('bytes','sha256')},131072 if key=='prelaunch_stacks' else 65536)
  stage='held_current_ihg_context'
  flow,recorder,phase_guard=task.open_task_context(ref,u,context,SOURCE_MANIFEST,verify_runtime,FLOW,STEP,
   transport,result,began+175,'launch',q.qa,entry.PLAN,q.resolver.RESOLVE,scope)
  view=ReadOnlyView(flow,task)
  baseline_roots,baseline_tasks=flow.tasks.parse_stacks(private['prelaunch_stacks'].decode('utf-8','strict'))
  historical=task_projection(private['prelaunch_stacks'],baseline_roots,baseline_tasks)
  need(historical==INPUTS['prelaunch'],'HISTORICAL_COMPLETE_TASK_PARSER_REPRODUCED')
  result['historical_prelaunch']=historical
  reference=json.loads(u.read(q.resolver.INSTALL_SOURCE/'target-artifact-reference.json',expected=
   q.install_manifest['files']['target-artifact-reference.json']['sha256']))
  reader=u.module(q.resolver.INSTALL_SOURCE/'references/read_ihg.py',u.READER_SHA,'current_ihg_artifact_parser')
  artifacts=context.ArtifactSet(view,reference,reader)
  stage='current_target_before';result['target_before']=artifacts.before()
  session=q.adapter.Session(view,recorder,q.qa,q.proof,entry.HELPER_UID)
  stage='current_helper_before';result['helper_before']=session.installed()
  need(result['helper_before']==q.installed,'CURRENT_INSTALLED_HELPER_CHANGED')
  for number in (1,2):
   stage='current_stack_'+str(number)
   raw=view.android(task.STACKS,20)
   roots,tasks=flow.tasks.parse_stacks(raw.decode('utf-8','strict'))
   need(len(roots)<=256 and len(tasks)<=512 and all(type(v) is int and 0<=v<=2147483647 for v in set(roots)|tasks),
    'COMPLETE_CURRENT_TASK_TABLE_BOUND')
   observed=task_projection(raw,roots,tasks)
   observed.update({'sample':number,'observed_utc':recorder.now(),
    'preexisting_full_roots_preserved':all(roots.get(k)==v for k,v in baseline_roots.items()),
    'preexisting_task_ids_present':baseline_tasks<=tasks,
    'added_task_ids':sorted(tasks-baseline_tasks),'removed_task_ids':sorted(baseline_tasks-tasks)})
   ref.write_new(STEP/('current-stacks-%02d.txt'%number),raw)
   result['observations'].append(observed)
   need(flow.command_index==4+number and flow.action_attempted is False and not flow.launch_claimed,'ONLY_READS_DURING_TWO_SAMPLES')
   flow.guard()
  result['two_complete_tables_equal']=(result['observations'][0]['complete_parsed_roots_sha256']==result['observations'][1]['complete_parsed_roots_sha256'] and
   result['observations'][0]['tasks']==result['observations'][1]['tasks'])
  need(result['two_complete_tables_equal'],'CURRENT_TABLES_CHANGED_NO_RETRY')
  stage='current_helper_after';result['helper_after']=session.installed()
  need(result['helper_after']==result['helper_before'],'CURRENT_HELPER_CHANGED')
  stage='current_target_after';result['target_after']=artifacts.after()
  need(result['target_after']==result['target_before'],'CURRENT_TARGET_CHANGED')
  need(view.counts==flow.policy.counts=={'target_uid':2,'target_path':2,'helper_uid':2,'helper_path':2,'stacks':2} and
   flow.command_index==10 and flow.action_attempted is False and not flow.launch_claimed and session.nonces==set(),
   'EXACT_TEN_READ_ONLY_COMMANDS_NO_NONCE_CONSUMPTION')
  for index in range(1,11):result['command_records'].append(command_record(index))
  result['current_read_sequence_completed']=True
 except BaseException as error:remember(stage,error)
 finally:
  if artifacts is not None:
   try:
    if len(artifacts.records)==1 and 'target_after' not in result:result['failed_scope_files_revalidated']=artifacts.revalidate_files()
   except BaseException as error:remember('failed_scope_revalidation',error)
   try:result['target_FD_cleanup']=artifacts.close()
   except BaseException as error:remember('target_FD_cleanup',error)
  if flow is not None:
   result['actual_command_count']=flow.command_index;result['action_attempted']=flow.action_attempted
   try:flow.guard(attempted=False);result['final_held_guard_passed']=True
   except BaseException as error:remember('final_held_guard',error)
   try:flow.close();result['held_binding_released']=True
   except BaseException as error:remember('held_binding_release',error)
   # No namespace reads are retried after failure; only fixed child evidence is retained.
   if not result['command_records']:
    for index in range(1,min(flow.command_index,10)+1):
     try:
      path=STEP/('command-%03d.result.json'%index);raw=u.read(path,65536)
      result['command_records'].append({'path':str(path),**pin(raw),'command':json.loads(raw)})
     except BaseException as error:remember('retained_read_command',error)
  try:
   result['Main_after']=guard()
   need(result['Main_after']==result.get('Main_before_lock')==result.get('Main_after_locks'),'MAIN_READ_WINDOW_CHANGED')
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
 result['ok']=bool(result['error'] is None and not result['secondary_errors'] and result.get('current_read_sequence_completed') is True and
  result.get('final_held_guard_passed') is True and result.get('held_binding_released') is True and
  result.get('global_action_lock_released') is True and result.get('flow_lock_released') is True)
 result['outcome_unknown']=False
 if step_created:
  try:ref.write_new(STEP/'result.json',result)
  except BaseException as error:remember('durable_read_result',error);result['ok']=False
 raw=(json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
 need(len(raw)<=65536,'SAFE_OBSERVATION_OUTPUT_BOUND')
 print(raw.decode(),end='',flush=True);return 0 if result['ok'] else 1
