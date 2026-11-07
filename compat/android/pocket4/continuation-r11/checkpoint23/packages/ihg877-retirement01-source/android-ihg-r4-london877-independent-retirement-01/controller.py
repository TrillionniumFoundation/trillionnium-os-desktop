"""One independently authorized current IHG877 retirement; original London failure remains unknown."""
import datetime,hashlib,json,math,os,re,stat,time,types
from pathlib import Path
ROOT=Path('/home/alex/work/pocket4-ihg-r4-public-london-input-01')
SOURCE=ROOT/'source'
FLOW=Path('/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b')
STEP_NAME='current-ihg877-independent-retirement-01'
STEP=FLOW/'steps'/STEP_NAME
MARKER=STEP/'remove-attempted.json'
RECONCILIATION=STEP/'independent-current-retirement.json'
PACKAGE='com.ihg.apps.android'
COMPONENT=PACKAGE+'/'+PACKAGE+'.activity.MainActivity'
TASK=877
SOURCE_MANIFEST='24a8491dbb44faf1288869d278da96290597b7af1fcdcce12a72fd62bad9435f'
ENTRY_PIN={'bytes':46630,'sha256':'562629c6c00d40a41cdf6fe2edf3df01292fb6f78409f8fd08b7776f02bf7bb0'}
def need(value,code):
 if not value:raise RuntimeError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def pin(raw):return {'bytes':len(raw),'sha256':sha(raw)}
def canon(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
MAIN_BEFORE_FIXED=json.loads("{\"Main_epoch_sha256\":\"7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c\",\"authenticated_owner_chain_matches\":true,\"config_sha256\":\"f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc\",\"current_baseline_qualification_sha256\":\"ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e\",\"current_baseline_sha256\":\"633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364\",\"current_executable_and_root_backing_match\":true,\"current_user_namespaces_match\":true,\"framework_exit_cause_resolved\":false,\"historical_activation_sha256\":\"7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615\",\"historical_verified_sha256\":\"2d6f2ef7953b98109044f823da56694111bd9f8ff14fff5e746afb7bd42b0387\",\"old_helpers_and_tasks_reauthorized\":false,\"previous_current_baseline_sha256\":\"163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266\",\"production_ready\":false,\"resource_limits_match\":true,\"schema\":\"pocket4-current-main-guard-v2\",\"seven_processes_match\":true,\"three_host_processes_match\":true}")

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

def summary(roots,tasks):
 need(0<len(roots)<=512 and 0<len(tasks)<=512,'CURRENT_TASK_COUNT_BOUND')
 rows=[]
 for rid,root in sorted(roots.items()):
  need(type(rid) is int and 0<rid<2147483648 and
       type(root['display']) is int and 0<=root['display']<2147483648 and
       type(root['user']) is int and 0<=root['user']<2147483648,'ROOT_METADATA_BOUND')
  children=[]
  for child in root['children']:
   need(type(child['id']) is int and 0<child['id']<2147483648 and
        type(child['user']) is int and 0<=child['user']<2147483648,'TASK_METADATA_BOUND')
   children.append({'task_id':child['id'],'user':child['user'],
    'is_target_package':child['component'].split('/')[0]==PACKAGE,
    'is_exact_target_component':child['component']==COMPONENT})
  rows.append({'root_id':rid,'display_id':root['display'],'user':root['user'],
      'freeform':root['freeform'],'children':children})
 return {'task_ids':sorted(tasks),'roots':rows}

def owned_command_record(number):
 need(type(number) is int and 1<=number<=42,'FIXED_RETIREMENT_COMMAND_INDEX')
 path=FLOW/'steps'/STEP_NAME/('command-%03d.result.json'%number)
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  first=os.fstat(fd)
  need(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and first.st_uid==0 and
       0<first.st_size<=8192,'OWNED_COMMAND_RECORD_SHAPE')
  raw=os.read(fd,8193);last=os.fstat(fd)
  keys=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
  need(len(raw)==first.st_size and all(getattr(first,k)==getattr(last,k) for k in keys),
       'OWNED_COMMAND_RECORD_CHANGED')
 finally:os.close(fd)
 v=json.loads(raw)
 need(type(v) is dict and set(v)=={'ended_utc','seconds','returncode','timed_out','spawned','error',
      'errors','owned_command_joined','stdout_sha256','stderr_sha256','action_attempted','automatic_retry'},
      'EXACT_ORIGINAL_COMMAND_METADATA')
 need(type(v['ended_utc']) is str and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}\+00:00',v['ended_utc']) and
      type(v['seconds']) in (int,float) and 0<=v['seconds']<=90 and
      (v['returncode'] is None or type(v['returncode']) is int) and
      all(type(v[k]) is bool for k in ('timed_out','spawned','owned_command_joined','action_attempted','automatic_retry')) and
      all(type(v[k]) is str and re.fullmatch('[0-9a-f]{64}',v[k]) for k in ('stdout_sha256','stderr_sha256')),
      'FIXED_COMMAND_SCALAR_TYPES')
 need(type(v['errors']) is list and len(v['errors'])<=32 and
      v['error']==(v['errors'][0] if v['errors'] else None),'FIXED_COMMAND_FIRST_ERROR')
 for e in v['errors']:
  need(type(e) is dict and set(e)=={'phase','exception_type','errno'} and
       e['phase'] in ('command_wait','owned_command_group_stop','owned_command_join',
       'command_spawn_or_wait','command_output_open','command_output_sync','command_output_close',
       'command_output_read','command_result_record','post_command_guard') and
       type(e['exception_type']) is str and re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,63}',e['exception_type']) and
       (e['errno'] is None or type(e['errno']) is int),'FIXED_COMMAND_ERROR_METADATA')
 return {'path':str(path),'bytes':len(raw),'sha256':sha(raw),'record':v}

def qualify_joined_command(record,raw,mutation):
 need(type(mutation) is bool and isinstance(raw,bytes),'EXACT_COMMAND_OUTPUT_KIND')
 need(record['returncode']==0 and record['spawned'] is True and
      record['owned_command_joined'] is True and record['timed_out'] is False and
      record['error'] is None and record['errors']==[] and
      record['action_attempted'] is mutation and record['automatic_retry'] is False and
      record['stdout_sha256']==sha(raw) and record['stderr_sha256']==sha(b''),
      'EXACT_JOINED_QUIET_RETIREMENT_COMMAND')
 return True

def command_gate_controls():
 rows=[];raw=b'fixed synthetic result\n'
 base={'returncode':0,'spawned':True,'owned_command_joined':True,'timed_out':False,
       'error':None,'errors':[],'action_attempted':False,'automatic_retry':False,
       'stdout_sha256':sha(raw),'stderr_sha256':sha(b'')}
 need(qualify_joined_command(base,raw,False),'CONTROL_JOINED_READ')
 rows.append({'name':'joined_read_positive','passed':True})
 need(qualify_joined_command({**base,'action_attempted':True},raw,True),'CONTROL_JOINED_REMOVE')
 rows.append({'name':'joined_remove_positive','passed':True})
 bad=[
  ('nonzero_rc',{'returncode':1}),
  ('not_joined',{'owned_command_joined':False}),
  ('timeout',{'timed_out':True}),
  ('metadata_error',{'error':{'phase':'fixture'},'errors':[{'phase':'fixture'}]}),
  ('changed_stdout',{'stdout_sha256':'0'*64}),
  ('nonempty_stderr',{'stderr_sha256':sha(b'not empty')}),
  ('wrong_mutation_flag',{'action_attempted':True}),
  ('automatic_retry',{'automatic_retry':True})]
 for name,change in bad:
  try:qualify_joined_command({**base,**change},raw,False)
  except RuntimeError:rows.append({'name':name,'passed':True})
  else:raise RuntimeError('COMMAND_GATE_NEGATIVE_ACCEPTED_'+name.upper())
 need(len(rows)==10,'COMMAND_GATE_CONTROL_COUNT')
 return rows

def safe_error(error):
 name=type(error).__name__;message=str(error)
 value={'exception_type':name if name in ('RuntimeError','OSError','PermissionError','FileNotFoundError',
  'ValueError','KeyError','TypeError','TimeoutError') else 'other',
  'message_sha256':sha(message.encode('utf-8','replace')),'raw_message_exported':False}
 if isinstance(error,RuntimeError) and re.fullmatch('[A-Z][A-Z0-9_]{0,127}',message):
  value['fixed_code']=message
 if type(getattr(error,'errno',None)) is int:value['errno']=error.errno
 return value

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
  'children':[{'id':875,'user':0,'component':'fixture.system/Fixture'}]}}
 target={'display':0,'user':0,'freeform':True,
  'children':[{'id':877,'user':0,'component':COMPONENT}]}
 def qualify(roots,tasks):return qualify_task_set(roots,tasks,base,{875},877,exact_leaf)
 passed('exact_live_leaf',qualify({**base,877:target},{875,877})=={'status':'exact_live_leaf','removal_allowed':True})
 passed('already_absent',qualify(base,{875})=={'status':'already_absent','removal_allowed':False})
 rejected('preserved_task_missing',lambda:qualify({877:target},{877}))
 rejected('unrelated_new_task',lambda:qualify({**base,877:target},{875,877,878}))
 rejected('unrelated_new_root',lambda:qualify({**base,877:target,878:target},{875,877}))
 rejected('foreign_component',lambda:qualify({**base,877:{**target,'children':[{'id':877,'user':0,'component':'other.app/Main'}]}},{875,877}))
 rejected('wrong_same_package_component',lambda:qualify({**base,877:{**target,'children':[{'id':877,'user':0,'component':PACKAGE+'/Other'}]}},{875,877}))
 rejected('wrong_display',lambda:qualify({**base,877:{**target,'display':1}},{875,877}))
 rejected('wrong_user',lambda:qualify({**base,877:{**target,'user':1}},{875,877}))
 rejected('non_leaf',lambda:qualify({**base,877:{**target,'children':target['children']+[{'id':878,'user':0,'component':COMPONENT}]}},{875,877}))
 rejected('task_without_root',lambda:qualify(base,{875,877}))
 rejected('preexisting_target_id',lambda:qualify_task_set(base,{875},base,{875},875,exact_leaf))
 need(len(rows)==12,'TASK_GATE_CONTROL_COUNT')
 return rows

def current_read_plans(entry):
 # Exact shape used by the fixed production worker, even for phase='launch'.
 search_plan=json.loads(json.dumps(entry.SEARCH_PLAN));click_plan=json.loads(json.dumps(entry.PLAN))
 input_plan=json.loads(json.dumps(entry.INPUT_PLAN))
 post_plan=json.loads(json.dumps(entry.POST_PLAN));readiness_plans=json.loads(json.dumps(entry.SEARCH_READINESS_PLANS))
 return {'search':search_plan,'destination':click_plan,'input':input_plan,'post':post_plan,'readiness':readiness_plans}

def current_main_read_window(result):
 keys=('Main_before_lock','Main_after_locks','Main_after')
 sampled=[key for key in keys if key in result]
 need('Main_after' in sampled,'INDEPENDENT_FINAL_MAIN_SAMPLE_REQUIRED')
 need(all(type(result[key]) is dict and result[key]==MAIN_BEFORE_FIXED for key in sampled),
  'MAIN_READ_WINDOW_CHANGED')
 return {'sampled_fields':sampled,'all_available_samples_equal':True,'complete':sampled==list(keys),
  'historical_Main_fields_used':False,'missing_samples_filled':False}

def current_main_window_controls():
 cases=[]
 incomplete={'Main_before_lock':dict(MAIN_BEFORE_FIXED),'Main_after':dict(MAIN_BEFORE_FIXED)}
 observed=current_main_read_window(incomplete)
 need(observed=={'sampled_fields':['Main_before_lock','Main_after'],'all_available_samples_equal':True,
  'complete':False,'historical_Main_fields_used':False,'missing_samples_filled':False} and
  'Main_after_locks' not in incomplete,'EARLY_FAILURE_RETAINS_INCOMPLETE_CURRENT_WINDOW')
 cases.append({'name':'early-failure-equal-current-samples-incomplete-without-false-drift','passed':True})
 complete={key:dict(MAIN_BEFORE_FIXED) for key in ('Main_before_lock','Main_after_locks','Main_after')}
 need(current_main_read_window(complete)['complete'] is True,'COMPLETE_CURRENT_MAIN_WINDOW')
 cases.append({'name':'three-actual-current-samples-required-for-complete-window','passed':True})
 for key in ('Main_after_locks','Main_after'):
  changed={name:dict(value) for name,value in complete.items()}
  changed[key]['Main_epoch_sha256']='0'*64
  try:current_main_read_window(changed)
  except RuntimeError as error:
   need(str(error)=='MAIN_READ_WINDOW_CHANGED','WRONG_CURRENT_MAIN_DRIFT_REJECTION')
   cases.append({'name':'sampled-'+key+'-drift-rejected','passed':True});continue
  raise RuntimeError('CURRENT_MAIN_DRIFT_ACCEPTED')
 need(len(cases)==4,'EXACT_FOUR_CURRENT_MAIN_WINDOW_CONTROLS')
 return cases

"""Private historical chain qualification for a new current IHG877 retirement scope."""
def verify_historical(hist,inputs,read_exact,qualify_joined_command):
 need(inputs['schema']=='pocket4-independent-current-IHG877-retirement-input-v1' and inputs['task']==TASK and
  inputs['package']==PACKAGE and inputs['component']==COMPONENT and
  inputs['original_launch_outcome']=='unknown_retained' and inputs['native_reported_task_id'] is None and
  inputs['old_task876_disappearance_attributed'] is False,'EXACT_CURRENT_RETIREMENT_INPUTS')
 r=hist.Reader();observed={};primary=None
 def get(name):
  expected=inputs['fixed_historical_files'][name]
  need(expected['path']==str(hist.FILES[name]),'EXACT_HISTORICAL_ALLOWLIST_PATH')
  raw=r.access(name,True);p={'bytes':expected['bytes'],'sha256':expected['sha256']}
  need(pin(raw)==p,'FIXED_HISTORICAL_ORIGINAL_CHANGED')
  observed[name]={'path':expected['path'],**p};return raw
 try:
  fixed={name:get(name) for name in hist.PINS}
  c,s,w=(hist.strict_json(fixed[k]) for k in ('coordinator','stage','worker'))
  original=hist.qualify_worker(c,s,w)
  parse,exact_leaf=hist.task_parser(fixed['task_parser'])
  intent=hist.strict_json(get('native_intent'));native_result=hist.strict_json(get('native_result'))
  hist.qualify_intent(intent,native_result,original)
  streams={name:get('native_'+name) for name in ('stdout','stderr')}
  for name,raw in streams.items():need(sha(raw)==hist.NATIVE_STREAMS[name],'ORIGINAL_NATIVE_STREAM_SHA')
  projection=hist.classify_native(streams['stdout'],streams['stderr'])
  need(projection==inputs['native_projection'] and projection['closed_child_matches']==[] and
   projection['whole_error_attribution_qualified'] is False and
   projection['task_cleanup_authority_created'] is False and projection['ok'] is False and
   projection['host_pid']==3268774 and projection['stderr_exactly_repeats_complete_message'] is True,
   'HISTORICAL_TIMEOUT_OBSERVATION_NOT_NATIVE_TASK_ATTRIBUTION')
  scope=hist.strict_json(get('scope'));attempt=hist.strict_json(get('attempted'))
  hist.qualify_scope(scope,attempt)
  raw=get('prelaunch_stacks');recorded=get('prelaunch_stdout')
  pr=hist.strict_json(get('prelaunch_result'));transport=hist.strict_json(get('prelaunch_transport'))
  need(raw==recorded,'COMPLETE_PRELAUNCH_STDOUT_BYTES')
  qualify_joined_command(pr,raw,False)
  command_sha=sha(json.dumps(hist.STACKS,separators=(',',':')).encode())
  need(transport.get('sequence')==6 and transport.get('epoch_sha256')==scope['epoch_sha256'] and
   transport.get('package')==PACKAGE and transport.get('uid')==10137 and transport.get('command_sha256')==command_sha and
   transport.get('returncode')==0 and transport.get('stdout_sha256')==sha(raw) and
   transport.get('stdout_bytes')==len(raw) and transport.get('stderr_bytes')==0 and
   transport.get('stderr_sha256')==sha(b'') and transport.get('outcome_unknown') is False and
   transport.get('automatic_retry') is False and transport.get('numeric_pid_target_used') is False,
   'EXACT_PRELAUNCH_HELD_TRANSPORT')
  need(hist.utc(pr['ended_utc'])<=hist.utc(attempt['time_utc'])<=hist.utc(intent['started_utc'])<=hist.utc(native_result['ended_utc']),
   'ORIGINAL_LAUNCH_TIME_ORDER')
  old_roots,old_tasks=parse(raw.decode('utf-8','strict'))
  need(hist.task_projection(raw,old_roots,old_tasks)==inputs['prelaunch'] and
   old_tasks=={875,876} and TASK not in old_tasks and TASK not in old_roots and
   not any(child['component'].split('/')[0]==PACKAGE for root in old_roots.values() for child in root['children']),
   'NO_IHG_PACKAGE_OR_TASK877_IN_COMPLETE_ORIGINAL_PRELAUNCH')
  need(r.access('launch_scope',False,optional=True) is None,'ORIGINAL_LAUNCH_SCOPE_MUST_REMAIN_ABSENT')
  samples=[]
  for number,row in enumerate(inputs['current_saved'],1):
   expected_path=FLOW/'steps/native-launch-state-read-02'/('current-stacks-%02d.txt'%number)
   command_path=FLOW/'steps/native-launch-state-read-02'/('command-%03d.result.json'%(number+4))
   need(row['sample']==number and row['path']==str(expected_path) and row['command']['path']==str(command_path),
    'EXACT_TWO_FIXED_SAVED_OBSERVATIONS')
   raw=read_exact(expected_path,{k:row[k] for k in ('bytes','sha256')},131072)
   cr=hist.strict_json(read_exact(command_path,{k:row['command'][k] for k in ('bytes','sha256')}))
   qualify_joined_command(cr,raw,False)
   need(hist.utc(native_result['ended_utc'])<=hist.utc(cr['ended_utc']),'SAVED_OBSERVATION_FOLLOWS_ORIGINAL_LAUNCH')
   roots,tasks=parse(raw.decode('utf-8','strict'))
   need(sha(canon(roots))==row['parsed_roots_sha256'] and tasks=={875,TASK} and set(roots)=={1,TASK} and
    exact_leaf(roots,TASK,PACKAGE) and roots[TASK]['children']==[{'id':TASK,'component':COMPONENT,'user':0}] and
    sha(canon(roots[1]))==inputs['preserved_root1_sha256'] and
    sha(canon(roots[TASK]))==inputs['current_root877_sha256'] and roots[1]==old_roots[1],
    'COMPLETE_SAVED_CURRENT_IHG877_AND_PRESERVED875')
   samples.append((roots,tasks))
  need(len(samples)==2 and samples[0]==samples[1],'EXACT_TWO_SAVED_TABLES_EQUAL')
  preserved_roots={k:v for k,v in samples[0][0].items() if k!=TASK}
  preserved_tasks=set(samples[0][1])-{TASK}
  need(preserved_tasks==set(inputs['preserved_current_tasks'])=={875} and
   set(preserved_roots)==set(inputs['preserved_current_root_ids'])=={1},'EXACT_CURRENT_PRESERVATION_BASELINE')
  need(r.opened==r.closed,'HISTORICAL_READER_FD_CLOSURE')
  safe={'fixed_historical_pins':observed,'actual_readers':inputs['evidence'],
   'native_intent_component':hist.COMPONENT,'canonical_public_component':COMPONENT,
   'component_not_present_in_original_prelaunch':True,'native_reported_task_id':None,
   'historical_launch_outcome':'unknown_retained','original_missing_Main_after_retained':True,
   'original_launch_scope_created':False,'original_task876_disappearance_attributed':False,
   'original_prelaunch_tasks':[875,876],'historical_current_tasks':[875,TASK],
   'preserved_current_tasks':[875],'entire_original_prelaunch_baseline_restored':False,
   'current_installed_native_source_version_verified':False,'whole_error_attribution_qualified':False,
   'reader_FDs_opened':r.opened,'reader_FDs_closed':r.closed,
   'current_saved_file_pins':inputs['current_saved']}
  return scope,preserved_roots,preserved_tasks,parse,exact_leaf,safe
 except BaseException as error:
  primary=error;raise
 finally:
  if r.opened!=r.closed:
   if primary is None:raise RuntimeError('HISTORICAL_READER_FD_CLOSURE')
   primary.add_note('HISTORICAL_READER_FD_CLOSURE')


def new_retirement_scope(source_sha):
 return {'schema':'pocket4-independent-current-IHG-task-retirement-scope-v1',
  'task':TASK,'component':COMPONENT,'package':PACKAGE,'uid':10137,'user':0,
  'epoch_sha256':'7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c',
  'baseline_sha256':'633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364',
  'qualification_sha256':'ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e',
  'source_sha256':source_sha,'prelaunch_absent':True,'cleanup_allowed':True,
  'independent_current_scope':True,'original_launch_outcome':'unknown_retained',
  'original_launch_scope_created':False,'authorizes_original_action_replay':False,
  'native_reported_task_id':None}

def independent_scope_controls(owned,task,qa,resolve,plans,exact_leaf,source_sha):
 cases=[];bound=new_retirement_scope(source_sha)
 def passed(name):cases.append({'name':name,'passed':True})
 def rejected(name,call):
  try:call()
  except RuntimeError:passed(name);return
  raise RuntimeError('INDEPENDENT_SCOPE_CONTROL_ACCEPTED')
 need(owned.validate_retirement_scope(bound,source_sha),'NEW_SCOPE_POSITIVE');passed('exact-new-current-scope-positive')
 rejected('source-pin-drift-rejected',lambda:owned.validate_retirement_scope(bound,'0'*64))
 rejected('native-task-id-claim-rejected',lambda:owned.validate_retirement_scope({**bound,'native_reported_task_id':TASK},source_sha))
 rejected('wrong-public-component-rejected',lambda:owned.validate_retirement_scope({**bound,'component':PACKAGE+'/Other'},source_sha))
 cls=owned.make_flow_type(task,bound,source_sha)
 def fixture():
  f=object.__new__(cls);calls=[]
  f.retirement_authority=None;f.retirement_counts={};f.retirement_remove_attempted=False
  f.command_index=0;f.action_attempted=False;f.launch_claimed=False;f.poisoned=False;f.closed=False
  f._private_backend_transport=False;f._android_mutation=False
  f.guard=lambda attempted=False:None # Explicit Main/held IO seam, not runtime qualification.
  f.tasks=types.SimpleNamespace(exact_leaf=exact_leaf)
  f.policy=task.Policy('cleanup',qa,resolve,plans,Path('/synthetic-current-retirement'),lambda *a:None,f.selected_task)
  def transport(argv,timeout):
   calls.append((list(argv),timeout,f._android_mutation));f.command_index+=1
   if f._android_mutation:f.action_attempted=True
   return b'fixture'
  f.transport=transport
  return f,calls
 f,calls=fixture()
 rejected('unarmed-remove-before-transport-rejected',
  lambda:f.android(['/system/bin/cmd','activity','stack','remove',str(TASK)],20,mutation=True))
 need(calls==[] and f.command_index==0,'UNARMED_REMOVE_FORWARDED')
 f,calls=fixture()
 base={1:{'display':0,'user':0,'freeform':False,'children':[{'id':875,'user':0,'component':'fixture.system/Fixture'}]}}
 roots={**base,TASK:{'display':0,'user':0,'freeform':True,'children':[{'id':TASK,'user':0,'component':COMPONENT}]}}
 for argv,timeout in ((task.LIST,15),(task.PATHS,15),(task.OWN_UID,8),(task.OWN_PATH,8),(task.STACKS,20),(task.STACKS,20)):
  f.android(list(argv),timeout)
 f.arm_after_exact_pair(roots,{875,TASK},roots,{875,TASK},base,{875})
 f.android(['/system/bin/cmd','activity','stack','remove',str(TASK)],20,mutation=True)
 need(f.command_index==7 and f.action_attempted is True and f.policy.remove_attempted is True and
  f.policy.counts=={'target_uid':1,'target_path':1,'helper_uid':1,'helper_path':1,'stacks':2} and
  f.retirement_counts=={**f.policy.counts,'remove':1} and
  calls[-1]==(['/system/bin/cmd','activity','stack','remove',str(TASK)],20,True),
  'REAL_ORIGINAL_POLICY_AND_FLOW_ANDROID_DELEGATION')
 passed('six-reads-new-scope-original-Policy-Flow-single-remove-route')
 rejected('second-remove-never-forwarded',lambda:f.android(['/system/bin/cmd','activity','stack','remove',str(TASK)],20,mutation=True))
 need(len(calls)==7,'SECOND_REMOVE_FORWARDED')
 f,calls=fixture()
 rejected('foreign-remove-never-forwarded',lambda:f.android(['/system/bin/cmd','activity','stack','remove','876'],20,mutation=True))
 need(calls==[],'FOREIGN_REMOVE_FORWARDED')
 f,calls=fixture();f.android(list(task.STACKS),0.125)
 need(calls==[(list(task.STACKS),0.125,False)] and f.policy.counts=={'stacks':1},
  'ORIGINAL_COMPLETION_FRACTIONAL_REMAINING_BUDGET')
 passed('fractional-original-completion-timeout-delegates')
 need(len(cases)==9,'EXACT_NINE_INDEPENDENT_SCOPE_CONTROLS')
 return cases

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

def run(source_sha256):
 need(os.getuid()==os.geteuid()==0,'ROOT_CURRENT_RETIREMENT_REQUIRED')
 os.umask(0o077)
 result={'schema':'pocket4-independent-current-IHG877-retirement-v1','ok':False,
  'source_sha256':source_sha256,'step_name':STEP_NAME,'task':TASK,'errors':[],'command_records':[],
  'historical_launch_outcome':'unknown_retained','original_launch_scope_created':False,
  'native_reported_task_id':None,'historical_Main_after_filled':False,
  'original_task876_disappearance_attributed':False,'entire_original_prelaunch_baseline_restored':False,
  'native_registration_replayed':False,'Composer_control_remove_sent':False,'native_launches':0,
  'maximum_Android_task_remove_commands':1,'remove_requested':False,'remove_acknowledged':False,
  'removal_action_attempted':False,'retirement_outcome_unknown':False,
  'before_tables':[],'completion_observations':[],'independent_after_attempted':False,
  'independent_after_completed':False,'global_action_lock_released':False,'flow_lock_released':False,
  'held_binding_released':False,'whole_process_tree_cleanup_qualified':False,
  'helper_UiAutomation_calls':0,'old_helper_nonce_values_consumed':False,
  'business_success_verified':False,'whole_app_production_ready':False}
 flow=recorder=artifacts=session=action_lock=flow_lock=resources=q=entry=u=ref=guard=None
 preserved_roots=preserved_tasks=None;step_created=False;phase='fixed_historical_chain';began=time.monotonic()
 def remember(where,error):result['errors'].append({'phase':where,**safe_error(error)})
 def record_command(number):
  path=str(STEP/('command-%03d.result.json'%number))
  existing=next((x for x in result['command_records'] if x['path']==path),None)
  if existing is None:
   existing=owned_command_record(number);result['command_records'].append(existing)
  return existing['record']
 def preserve(roots,tasks):
  need(set(tasks)-{TASK}==set(preserved_tasks),'OTHER_TASK_SET_CHANGED')
  need(set(roots)-{TASK}==set(preserved_roots),'OTHER_ROOT_SET_CHANGED')
  need(all(roots.get(k)==v for k,v in preserved_roots.items()),'PREEXISTING_ROOT_CONTENT_CHANGED')
 def observed(raw,roots,tasks):
  return {'raw_stack_pin':pin(raw),'tasks':summary(roots,tasks),
   'complete_parsed_roots_sha256':sha(canon(roots)),
   'other_complete_root_content_sha256':sha(canon({k:v for k,v in roots.items() if k!=TASK})),
   'target_absent':TASK not in roots and TASK not in tasks,
   'foreign_component_names_exported':False}
 def current_table(label,timeout=20):
  raw=flow.android(task.STACKS,timeout)
  qualify_joined_command(record_command(flow.command_index),raw,False)
  roots,tasks=flow.tasks.parse_stacks(raw.decode('utf-8','strict'))
  need(len(roots)<=256 and len(tasks)<=512,'CURRENT_COMPLETE_TASK_TABLE_BOUND')
  ref.write_new(STEP/(label+'.txt'),raw)
  return raw,roots,tasks
 try:
  need(pin(HISTORICAL_PARSER_SOURCE.encode())==HISTORICAL_PARSER_PIN,'EXACT_EXECUTED_NATIVE007_SOURCE')
  hist=types.ModuleType('fixed_historical_IHG_native007');hist.__file__='<fixed-historical-IHG-native007>'
  hist.SOURCE_SHA256=HISTORICAL_PARSER_PIN['sha256']
  exec(compile(HISTORICAL_PARSER_SOURCE,hist.__file__,'exec'),hist.__dict__)
  scope,preserved_roots,preserved_tasks,parse,exact_leaf,historical=verify_historical(hist,INPUTS,read_exact,qualify_joined_command)
  result['historical_chain']=historical
  need(not os.path.lexists(STEP) and not os.path.lexists(FLOW/'launch-scope.json'),'NO_CURRENT_RETIREMENT_OR_ORIGINAL_SCOPE_REPLAY')
  entry_raw=read_exact(SOURCE/'owned_inspect.py',ENTRY_PIN)
  entry=types.ModuleType('fixed_ihg_current_retirement_entry');entry.__file__=str(SOURCE/'owned_inspect.py')
  exec(compile(entry_raw,entry.__file__,'exec'),entry.__dict__)
  need(entry.HERE==SOURCE and entry.FLOW==FLOW and entry.PACKAGE==PACKAGE and entry.HELPER_UID==10158,
   'EXACT_CURRENT_IHG_ENTRY')
  q=entry.qualified(SOURCE_MANIFEST);u,ref=q.util,q.ref
  task=entry.load(SOURCE/'ihg_task_context.py',q.manifest['files']['ihg_task_context.py']['sha256'],'fixed_IHG_original_task_context')
  context=u.module(q.resolver.INSTALL_SOURCE/'ihg_context.py',q.resolver.CONTEXT_SHA,'fixed_IHG_install_artifact_context')
  transport=u.module(q.resolver.INSTALL_SOURCE/'ihg_transport.py',q.resolver.TRANSPORT_SHA,'fixed_IHG_held_transport')
  shared=u.module(context.INSTALLED_SHARED/'source_contract.py',context.CONTRACT_SHA,'fixed_current_source_contract')
  contract=shared.SourceContract(context.INSTALLED_SHARED/'source-manifest.json',context.SHARED_MANIFEST)
  recorder=contract.load('recorder.py','fixed_current_original_command')
  activation=ref.current_baseline()
  epoch=ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),ref.EPOCH_SOURCE,'fixed_current_epoch')
  guard=lambda:ref.main_guard(activation,epoch)
  need(pin(OWNED_CONTEXT_SOURCE.encode())==OWNED_CONTEXT_PIN,'EXACT_OWNED_RETIREMENT_CONTEXT')
  owned=types.ModuleType('owned_IHG_current_retirement_context');owned.__file__='<verified-owned-IHG-retirement-context>'
  exec(compile(OWNED_CONTEXT_SOURCE,owned.__file__,'exec'),owned.__dict__)
  bound_scope=new_retirement_scope(source_sha256)
  flow_type=owned.make_flow_type(task,bound_scope,source_sha256)
  plans=current_read_plans(entry)
  phase='admission';resources=u.prepare_owned_limits();result['owned_before']=resources
  result['Main_before_lock']=guard()
  need(result['Main_before_lock']==MAIN_BEFORE_FIXED,'FRESH_CURRENT_MAIN_BASELINE_DIFFERS')
  result['controls']=task_set_controls(exact_leaf)+command_gate_controls()+current_main_window_controls()+independent_scope_controls(
   owned,task,q.qa,q.resolver.RESOLVE,plans,exact_leaf,source_sha256)+open_context_route_controls(task,q,plans,scope,source_sha256)
  need(len(result['controls'])==38 and len({x['name'] for x in result['controls']})==38,'EXACT_THIRTY_EIGHT_CONTROLS')
  result['flow_lock_admission']={};flow_lock=u.acquire_action_lock(FLOW/'flow.lock',result['flow_lock_admission'])
  result['global_lock_admission']={};action_lock=u.acquire_action_lock(recorder.ACTION_LOCK,result['global_lock_admission'])
  result['Main_after_locks']=guard()
  need(not os.path.lexists(STEP) and not os.path.lexists(FLOW/'launch-scope.json'),'NO_RETIREMENT_STEP_OR_OLD_SUCCESS_SCOPE')
  STEP.mkdir(mode=0o700);step_created=True
  ref.write_new(STEP/'intent.json',{'schema':'pocket4-independent-current-retirement-intent-v1',
   'source_sha256':source_sha256,'task':TASK,'component':COMPONENT,'historical_launch_outcome':'unknown_retained',
   'native_reported_task_id':None,'current_preserved_tasks':[875],'original_task876_disappearance_attributed':False,
   'maximum_remove_commands':1,'maximum_completion_reads':30,'maximum_total_commands':42,
   'native_launches':0,'helper_instrumentation_calls':0,'automatic_retry':False})
  def verify_runtime(value):
   entry.verify_source(value);u.verify_source(q.resolver.INSTALL_SOURCE_SHA)
   entry.read(entry.RESOLVER_SOURCE,32768,entry.RESOLVER_SHA,entry.RESOLVER_BYTES)
   read_exact(SOURCE/'owned_inspect.py',ENTRY_PIN)
   for item in INPUTS['fixed_historical_files'].values():
    read_exact(Path(item['path']),{k:item[k] for k in ('bytes','sha256')},131072)
   for item in INPUTS['current_saved']:
    read_exact(Path(item['path']),{k:item[k] for k in ('bytes','sha256')},131072)
    read_exact(Path(item['command']['path']),{k:item['command'][k] for k in ('bytes','sha256')})
   need(not os.path.lexists(FLOW/'launch-scope.json'),'ORIGINAL_LAUNCH_SCOPE_MUST_REMAIN_ABSENT')
  phase='held_current_IHG_context'
  flow,recorder,phase_guard=owned.open_independent_context(task,flow_type,ref,u,context,SOURCE_MANIFEST,verify_runtime,
   FLOW,STEP,transport,result,began+175,'cleanup',q.qa,plans,q.resolver.RESOLVE,scope,
   install_source_manifest=q.resolver.INSTALL_SOURCE_SHA)
  need(flow.scope==scope and flow.tasks.parse_stacks is not None,'CURRENT_TYPED_CONTEXT_REQUIRED')
  reference=json.loads(u.read(q.resolver.INSTALL_SOURCE/'target-artifact-reference.json',
   expected=q.install_manifest['files']['target-artifact-reference.json']['sha256']))
  reader=u.module(q.resolver.INSTALL_SOURCE/'references/read_ihg.py',u.READER_SHA,'current_IHG_artifact_parser')
  artifacts=context.ArtifactSet(flow,reference,reader)
  phase='current_target_before';result['target_before']=artifacts.before()
  session=q.adapter.Session(flow,recorder,q.qa,q.proof,entry.HELPER_UID)
  phase='current_helper_before';result['helper_before']=session.installed()
  need(result['helper_before']==q.installed and flow.command_index==4,'EXACT_CURRENT_INSTALLED_HELPER')
  fresh=[]
  for number in (1,2):
   phase='current_complete_table_'+str(number)
   raw,roots,tasks=current_table('before-stacks-%02d'%number)
   need(flow.command_index==4+number and flow.action_attempted is False and not flow.launch_claimed,'ONLY_SIX_PRE_RETIREMENT_READS')
   gate=qualify_task_set(roots,tasks,preserved_roots,preserved_tasks,TASK,flow.tasks.exact_leaf)
   fresh.append((roots,tasks));result['before_tables'].append({**observed(raw,roots,tasks),'qualification':gate})
   flow.guard()
  need(fresh[0]==fresh[1] and result['before_tables'][0]['qualification']==result['before_tables'][1]['qualification'],
   'FRESH_COMPLETE_TABLES_CHANGED_NO_RETRY')
  result['before_tables_qualified']=True
  if gate['status']=='already_absent':
   result['already_absent_without_removal']=True
  else:
   phase='arm_new_current_scope'
   flow.arm_after_exact_pair(fresh[0][0],fresh[0][1],fresh[1][0],fresh[1][1],preserved_roots,preserved_tasks)
   ref.write_new(STEP/'new-current-retirement-scope.json',bound_scope);result['new_current_retirement_scope_armed']=True
   flow.guard()
   ref.write_new(MARKER,{'schema':'pocket4-independent-current-retirement-attempt-v1','scope':bound_scope,
    'source_sha256':source_sha256,'time_utc':recorder.now(),'automatic_retry':False,
    'original_launch_scope_created':False})
   phase='one_exact_Android_remove877';result['remove_requested']=True
   removed=flow.android(['/system/bin/cmd','activity','stack','remove',str(TASK)],20,mutation=True)
   need(flow.command_index==7,'EXACT_SINGLE_REMOVE_INDEX')
   qualify_joined_command(record_command(7),removed,True);result['remove_acknowledged']=True
   completion_reads=0
   def completion_stacks(timeout):
    nonlocal completion_reads
    need(completion_reads<30,'COMPLETION_CAP_PRESERVES_INDEPENDENT_AFTER_SLOT')
    completion_reads+=1
    raw=flow.android(task.STACKS,timeout)
    need(flow.command_index<=37,'THIRTY_COMPLETION_READS_BOUND')
    qualify_joined_command(record_command(flow.command_index),raw,False)
    return raw.decode('utf-8','strict')
   def completion_record(value):
    index=len(result['completion_observations'])+1
    ref.write_new(STEP/('completion-private-%02d.json'%index),value)
    need(type(value) is dict and type(value.get('raw_stacks')) is str,'COMPLETE_COMPLETION_TABLE')
    roots,tasks=flow.tasks.parse_stacks(value['raw_stacks']);preserve(roots,tasks)
    if TASK in tasks:
     need(roots.get(TASK,{}).get('children')==[{'id':TASK,'component':COMPONENT,'user':0}],
      'CURRENT_TARGET_CHANGED_DURING_RETIREMENT')
    result['completion_observations'].append({'observation':index,**observed(value['raw_stacks'].encode(),roots,tasks)})
   phase='original_bounded_removal_completion'
   result['normal_completion']=flow.tasks.wait_for_removal(completion_stacks,TASK,PACKAGE,fresh[-1][1],completion_record)
   result['normal_removal_verified']=True
 except BaseException as error:remember(phase,error)
 finally:
  if flow is not None and result.get('before_tables_qualified') is True:
   result['independent_after_attempted']=True
   try:
    raw,roots,tasks=current_table('independent-after-stacks')
    preserve(roots,tasks);result['independent_after']=observed(raw,roots,tasks)
    need(TASK not in tasks and TASK not in roots and roots==preserved_roots and tasks==preserved_tasks,
     'EXACT_CURRENT_TARGET_ABSENT_AND_OTHER_CONTENT_PRESERVED')
    result['independent_after_completed']=True
   except BaseException as error:remember('independent_after',error)
  if session is not None and artifacts is not None:
   try:
    result['helper_after']=session.installed()
    need(result['helper_after']==result['helper_before'],'CURRENT_HELPER_CHANGED')
    result['target_after']=artifacts.after()
    need(result['target_after']==result['target_before'],'CURRENT_TARGET_CHANGED')
   except BaseException as error:remember('current_package_metadata_after',error)
  if flow is not None:
   result['actual_command_count']=flow.command_index;result['removal_action_attempted']=flow.action_attempted
   result['original_policy_counts']=dict(flow.policy.counts);result['owned_retirement_counts']=dict(flow.retirement_counts)
   try:
    need(not flow.launch_claimed and session is not None and session.nonces==set() and flow.policy.used_nonces==set(),
     'NO_NATIVE_OR_HELPER_NONCE_CONSUMPTION')
    need(flow.command_index<=42 and flow.policy.counts.get('stacks',0)<=33 and
     flow.retirement_counts.get('remove',0)<=1,'EXACT_TOTAL_RETIREMENT_BOUNDS')
    if not result['errors']:
     need(all(flow.policy.counts.get(k)==2 for k in ('target_uid','target_path','helper_uid','helper_path')) and
      sum(flow.retirement_counts.values())==flow.command_index and
      flow.policy.counts=={k:v for k,v in flow.retirement_counts.items() if k!='remove'},
      'EXACT_ORIGINAL_POLICY_AND_OWNED_COMMAND_COUNTS')
    for number in range(1,min(flow.command_index,42)+1):
     row=record_command(number)
     output=u.read(STEP/('command-%03d.stdout'%number),131072)
     if not result['errors']:qualify_joined_command(row,output,result['remove_requested'] and number==7)
   except BaseException as error:remember('complete_command_and_nonce_accounting',error)
  if artifacts is not None:
   try:
    if len(artifacts.records)==1 and 'target_after' not in result:result['failed_scope_files_revalidated']=artifacts.revalidate_files()
   except BaseException as error:remember('failed_scope_file_revalidation',error)
   try:result['target_FD_cleanup']=artifacts.close()
   except BaseException as error:remember('target_FD_cleanup',error)
  if flow is not None:
   try:flow.guard(attempted=flow.action_attempted);result['final_held_guard_passed']=True
   except BaseException as error:remember('final_held_guard',error)
   try:flow.close();result['held_binding_released']=True
   except BaseException as error:remember('held_binding_release',error)
  if guard is not None:
   try:
    result['Main_after']=guard();result['current_Main_window']=current_main_read_window(result)
   except BaseException as error:remember('independent_final_Main',error)
  for fd,name in ((action_lock,'global_action_lock'),(flow_lock,'flow_lock')):
   if fd is not None:
    try:os.close(fd);result[name+'_released']=True
    except BaseException as error:remember(name+'_release',error)
  if entry is not None:
   try:
    entry.qualified(SOURCE_MANIFEST)
    need(not os.path.lexists(FLOW/'launch-scope.json'),'ORIGINAL_LAUNCH_SCOPE_MUST_REMAIN_ABSENT')
    result['source_and_artifact_inputs_unchanged']=True
   except BaseException as error:remember('final_source_closure',error)
  if resources is not None:
   try:result['owned_after']=u.owned_resources();u.resources_qualified(resources,result['owned_after'])
   except BaseException as error:remember('final_owned_resources',error)
 complete=bool(not result['errors'] and result.get('before_tables_qualified') is True and
  result['independent_after_completed'] and result.get('final_held_guard_passed') is True and
  result.get('current_Main_window',{}).get('complete') is True and
  result['held_binding_released'] and result['flow_lock_released'] and result['global_action_lock_released'] and
  result.get('source_and_artifact_inputs_unchanged') is True and
  result.get('target_FD_cleanup',{}).get('held_APK_FDs_closed')==1 and
  (result.get('already_absent_without_removal') is True or
   (result['remove_acknowledged'] and result.get('normal_removal_verified') is True)))
 result['ok']=complete
 if complete:
  try:
   receipt={'schema':'pocket4-independent-current-IHG877-retirement-reconciliation-v1',
    'created_utc':recorder.now(),'source_sha256':source_sha256,'task':TASK,'component':COMPONENT,
    'original_action_outcome':'unknown_retained','original_launch_scope_created':False,
    'authorizes_original_action_replay':False,'native_reported_task_id':None,
    'owned_current_Android_leaf_absent':True,'all_other_current_root_and_task_content_preserved':True,
    'original_task876_disappearance_attributed':False,'entire_original_prelaunch_baseline_restored':False,
    'actual_historical_chain':result['historical_chain'],'before_tables':result['before_tables'],
    'independent_after':result['independent_after'],
    'command_result_pins':[{k:row[k] for k in ('path','bytes','sha256')} for row in result['command_records']]}
   ref.write_new(RECONCILIATION,receipt);raw=u.read(RECONCILIATION,65536)
   result['independent_reconciliation_receipt']={'path':str(RECONCILIATION),**pin(raw)}
  except BaseException as error:remember('new_independent_receipt',error);result['ok']=False
 result['retirement_outcome_unknown']=bool(result['removal_action_attempted'] and not result['ok'])
 if step_created:
  try:ref.write_new(STEP/'result.json',result)
  except BaseException as error:
   remember('durable_retirement_result',error);result['ok']=False
   result['retirement_outcome_unknown']=bool(result['removal_action_attempted'])
 data=(json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
 need(len(data)<=131072,'SAFE_RETIREMENT_OUTPUT_BOUND')
 print(data.decode(),end='',flush=True)
 return 0 if result['ok'] else 1
