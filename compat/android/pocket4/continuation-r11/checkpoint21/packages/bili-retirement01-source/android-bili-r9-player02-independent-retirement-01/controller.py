"""Independent retirement after one unknown native launch; original receipt stays unchanged."""
import datetime,hashlib,json,os,re,stat,time,types
from pathlib import Path
FLOW=Path('/home/alex/work/pocket4-bilibili-owned-qa-r9-flow-474d7477074ea01fbc986e0d867924c1')
STEP_NAME='native-launch-retirement-01'
HOST_ROOT=Path('/home/alex/work/pocket4-current-host-r5-source-01')
HOST_MANIFEST='6d99374e1580083fd0f30b7f9b3c520306680760c97ad0d5400798fda427fb6e'
RECORDER_SHA='7101d2ab2cd4b73bf96cab1117c8d0177c2b290255c6946af52ec834115a7f44'
PACKAGE='tv.danmaku.bili'
COMPONENT=PACKAGE+'/tv.danmaku.bili.MainActivityV2'
TASK=873
MARKER=FLOW/'native-launch-retirement-attempted-01.json'
RECONCILIATION=FLOW/'reconciliations/native-launch-retirement-01.json'
def need(value,code):
 if not value:raise RuntimeError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read_exact(path,pin):
 # Only fixed pinned originals and published source; no directory traversal or discovery.
 path=Path(path);current=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);fd=None
 try:
  for part in path.parts[1:-1]:
   nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current)
   try:os.close(current)
   except BaseException:
    os.close(nxt);raise
   current=nxt
  fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current)
  first=os.fstat(fd)
  need(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and first.st_uid in (0,1000) and
       first.st_size==pin['bytes'] and 0<=first.st_size<=131072,'EXACT_REGULAR_FILE_REQUIRED')
  chunks=[];count=0
  while count<=pin['bytes']:
   part=os.read(fd,min(16384,pin['bytes']+1-count))
   if not part:break
   chunks.append(part);count+=len(part)
  last=os.fstat(fd);raw=b''.join(chunks)
  fields=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
  need(count==pin['bytes'] and sha(raw)==pin['sha256'] and
       all(getattr(first,k)==getattr(last,k) for k in fields),'FIXED_ORIGINAL_CHANGED')
  return raw
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
 need(type(number) is int and 1<=number<=36,'FIXED_RETIREMENT_COMMAND_INDEX')
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

def verify_historical_attribution():
 need(type(INPUTS) is dict and INPUTS.get('schema')=='pocket4-independent-native-launch-retirement-input-v1' and
      INPUTS.get('task')==TASK and INPUTS.get('historical_launch_outcome')=='unknown_retained' and
      INPUTS.get('existing_launch_scope_must_remain_absent') is True,
      'ACTUAL_BOUND_RETIREMENT_INPUTS_REQUIRED')
 need(sha(HISTORICAL_PARSER_SOURCE.encode())=='ba9e2350304b87e35168ee19166bece041930693ea4feedbab47624dd03ce9af',
      'EXACT_EXECUTED_ERROR_PARSER_SOURCE')
 library=types.ModuleType('fixed_historical_native_error')
 library.__file__='<verified-historical-native-error-reader>'
 library.SOURCE_SHA256='ba9e2350304b87e35168ee19166bece041930693ea4feedbab47624dd03ce9af'
 exec(compile(HISTORICAL_PARSER_SOURCE,library.__file__,'exec'),library.__dict__)
 reader=library.Reader();raw={};primary=None
 try:
  for name,pin in library.PINS.items():
   value=reader.access(name,True)
   need(len(value)==pin['bytes'] and sha(value)==pin['sha256'],'ORIGINAL_NATIVE_EVIDENCE_CHANGED')
   raw[name]=value
  worker=library.strict_json(raw['worker'])
  original=library.qualify_worker(worker)
  native_intent=library.strict_json(raw['native_intent']);native_result=library.strict_json(raw['native_result'])
  library.qualify_native(native_intent,native_result,original)
  parsed=library.pair_projection(raw['native_stdout'],raw['native_stderr'])
  need(parsed==INPUTS['actual_error_projection'],'ACTUAL_NATIVE_ERROR_PROJECTION_CHANGED')
  need(parsed['bytes']==414 and parsed['sha256']=='06a69fd403766d93148369a9dc947283dc96f27be71e26e8295d510b2f4c62a3' and
       parsed['complete_wrapper_match'] is True and parsed['complete_closed_error_shape'] is True and
       parsed['closed_error']=={'shape':'backend_different_registration_ownership','labelled_fields':{'task':TASK}} and
       parsed['task_cleanup_authority_created'] is False and
       parsed['reference_source_format_match'] is False and parsed['opaque_prefix_semantics_known'] is False and
       parsed['installed_source_version_verified'] is False,'EXACT_NATIVE_REPORTED_TASK_BINDING_REQUIRED')
  need(reader.opened==reader.closed,'HISTORICAL_READER_FD_CLOSURE')
  return {'worker_pin':library.WORKER_PIN,'native_file_pins':library.PINS,
          'reported_task':TASK,'reported_error':'backend_different_registration_ownership',
          'source_binary_match_proven':False,'conflict_underlying_cause_known':False,
          'historical_reader_FDs_opened':reader.opened,'historical_reader_FDs_closed':reader.closed,
          'native_started_utc':native_intent['started_utc'],'native_ended_utc':native_result['ended_utc']}
 except BaseException as error:
  primary=error
  raise
 finally:
  if reader.opened!=reader.closed:
   if primary is None:raise RuntimeError('HISTORICAL_READER_FD_CLOSURE')
   primary.add_note('HISTORICAL_READER_FD_CLOSURE')
def run(source_sha256):
 need(os.getuid()==os.geteuid()==0,'ROOT_BOUND_RETIREMENT_REQUIRED')
 os.umask(0o077)
 result={'schema':'pocket4-independent-native-launch-retirement-v1','ok':False,
  'source_sha256':source_sha256,'step_name':STEP_NAME,'task':TASK,'errors':[],'command_records':[],
  'historical_launch_outcome':'unknown_retained','original_launch_scope_created':False,
  'native_registration_replayed':False,'Composer_control_remove_sent':False,
  'maximum_Android_task_remove_commands':1,'remove_requested':False,'remove_acknowledged':False,
  'removal_action_attempted':False,'retirement_outcome_unknown':False,
  'before_tables':[],'completion_observations':[],'independent_after_attempted':False,
  'independent_after_completed':False,'global_action_lock_acquired':False,
  'global_action_lock_released':False,'held_binding_released':False,
  'flow_lock_held_until_process_exit':True,'whole_process_tree_cleanup_qualified':False,
  'helper_UiAutomation_calls':0,'business_success_verified':False,'whole_app_production_ready':False}
 flow=None;recorder=None;action_lock=None;baseline_roots=None;baseline_tasks=None
 def remember(phase,error):result['errors'].append({'phase':phase,**safe_error(error)})
 def record_command(number):
  path=str(FLOW/'steps'/STEP_NAME/('command-%03d.result.json'%number))
  if not any(x['path']==path for x in result['command_records']):
   result['command_records'].append(owned_command_record(number))
  return next(x['record'] for x in result['command_records'] if x['path']==path)
 def preserve(roots,tasks):
  need(set(tasks)-{TASK}==set(baseline_tasks),'OTHER_TASK_SET_CHANGED')
  need(set(roots)-{TASK}==set(baseline_roots),'OTHER_ROOT_SET_CHANGED')
  need(all(roots.get(k)==v for k,v in baseline_roots.items()),'PREEXISTING_ROOT_CONTENT_CHANGED')
 def observed(raw,roots,tasks):
  return {'raw_stack_bytes':len(raw.encode()),'raw_stack_sha256':sha(raw.encode()),
          'tasks':summary(roots,tasks),'target_absent':TASK not in roots and TASK not in tasks}
 try:
  result['historical_attribution']=verify_historical_attribution()
  need(not os.path.lexists(FLOW/'launch-scope.json') and not os.path.lexists(MARKER) and
       not os.path.lexists(RECONCILIATION),'NO_OLD_SCOPE_OR_RETIREMENT_REPLAY')
  saved_scope=json.loads(read_exact(FLOW/'scope.json',INPUTS['scope_pin']))
  attempted=json.loads(read_exact(FLOW/'launch-attempted.json',INPUTS['attempted_pin']))
  need(saved_scope==INPUTS['historical_scope'] and attempted==INPUTS['historical_attempted'] and
       attempted['scope']==saved_scope and attempted['step']=='launch-01' and
       saved_scope['component']==COMPONENT and saved_scope['user']==0 and
       saved_scope['automatic_retry'] is False,'EXACT_ORIGINAL_LAUNCH_SCOPE_AND_ATTEMPT')
  need(datetime.datetime.fromisoformat(saved_scope['created_utc'])<=
       datetime.datetime.fromisoformat(attempted['time_utc'])<=
       datetime.datetime.fromisoformat(result['historical_attribution']['native_started_utc'])<=
       datetime.datetime.fromisoformat(result['historical_attribution']['native_ended_utc']),
       'ORIGINAL_SCOPE_ATTEMPT_NATIVE_TIME_ORDER')
  baseline_raw=read_exact(FLOW/'steps/launch-01/prelaunch-stacks.txt',INPUTS['prelaunch_stacks_pin'])
  current_raw=read_exact(FLOW/'steps/native-reconciliation-stacks-read-01/command-002.stdout',
      INPUTS['previous_current_stack_pin'])
  previous_command=json.loads(read_exact(FLOW/'steps/native-reconciliation-stacks-read-01/command-002.result.json',
      INPUTS['previous_current_command_pin']))
  qualify_joined_command(previous_command,current_raw,False)
  need(datetime.datetime.fromisoformat(result['historical_attribution']['native_ended_utc'])<=
       datetime.datetime.fromisoformat(previous_command['ended_utc']),'CURRENT_OBSERVATION_FOLLOWS_NATIVE')
  manifest=json.loads(read_exact(HOST_ROOT/'source-manifest.json',{'bytes':3605,'sha256':HOST_MANIFEST}))
  need(manifest['files']['recorder.py']=={'bytes':41689,'sha256':RECORDER_SHA},'ORIGINAL_CURRENT_RECORDER_REQUIRED')
  recorder_raw=read_exact(HOST_ROOT/'recorder.py',manifest['files']['recorder.py'])
  recorder=types.ModuleType('original_current_bili_recorder_for_retirement')
  recorder.__file__=str(HOST_ROOT/'recorder.py')
  exec(compile(recorder_raw,recorder.__file__,'exec'),recorder.__dict__)
  args=types.SimpleNamespace(operation='cleanup',adapter_manifest_sha256=HOST_MANIFEST,flow_dir=FLOW,
   epoch_module=HOST_ROOT/'references/framework_epoch.py',
   task_source=HOST_ROOT/'references/task_scope_baseline.py',step=STEP_NAME,
   request={'purpose':'independent-owned-Android-leaf-retirement-after-unknown-native-launch',
    'historical_launch_outcome':'unknown_retained','task':TASK,
    'failed_worker_pin':INPUTS['worker_pin'],'actual_error_reader':INPUTS['actual_error_reader'],
    'maximum_remove_commands':1,'native_registration_replay':False},
   unknown_step=None,observation_step=None,postcondition=None)
  flow=recorder.Flow(args)
  need(not os.path.lexists(FLOW/'launch-scope.json') and not os.path.lexists(MARKER) and
       not os.path.lexists(RECONCILIATION),'NO_SCOPE_OR_RETIREMENT_CREATED_BEFORE_FLOW_LOCK')
  need(flow.scope==saved_scope and flow.scope['package']==PACKAGE and flow.scope['uid']==10117,
       'SAVED_FLOW_SCOPE_CHANGED')
  baseline_roots,baseline_tasks=flow.tasks.parse_stacks(baseline_raw.decode('utf-8','strict'))
  previous_roots,previous_tasks=flow.tasks.parse_stacks(current_raw.decode('utf-8','strict'))
  need(summary(baseline_roots,baseline_tasks)==INPUTS['prelaunch_task_baseline'] and
       summary(previous_roots,previous_tasks)==INPUTS['previous_current_task_summary'],
       'ACTUAL_STACK_PROJECTION_BINDING_CHANGED')
  need(qualify_task_set(previous_roots,previous_tasks,baseline_roots,baseline_tasks,TASK,flow.tasks.exact_leaf)['status']=='exact_live_leaf',
       'PREVIOUS_READ_DID_NOT_IDENTIFY_EXACT_NEW_LEAF')
  result['task_gate_controls']=task_set_controls(flow.tasks.exact_leaf)
  result['command_gate_controls']=command_gate_controls()
  flow.begin(args,mutation=True)
  action_lock=recorder.lock_file(recorder.ACTION_LOCK);result['global_action_lock_acquired']=True
  flow.guard();result['Main_before']=flow.current_guard.current_guard(flow.activation,action_attempted=False)
  for number in (1,2):
   raw,roots,tasks=flow.stacks(timeout=20)
   need(flow.command_index==number and flow.action_attempted is False,'PRE_RETIREMENT_READS_ONLY')
   cr=record_command(number)
   qualify_joined_command(cr,raw.encode(),False)
   gate=qualify_task_set(roots,tasks,baseline_roots,baseline_tasks,TASK,flow.tasks.exact_leaf)
   result['before_tables'].append({**observed(raw,roots,tasks),'qualification':gate})
   flow.guard()
  need(result['before_tables'][0]['tasks']==result['before_tables'][1]['tasks'] and
       result['before_tables'][0]['qualification']==result['before_tables'][1]['qualification'],
       'FRESH_TASK_IDENTITY_CHANGED_BETWEEN_SAMPLES')
  result['before_tables_qualified']=True
  if gate['status']=='already_absent':
   result['already_absent_without_removal']=True
  else:
   need(gate['removal_allowed'] is True,'CURRENT_EXACT_LEAF_REQUIRED')
   flow.guard()
   marker={'schema':'pocket4-independent-native-launch-retirement-attempt-v1','step':STEP_NAME,
     'source_sha256':source_sha256,'task':TASK,'component':COMPONENT,
     'scope_sha256':INPUTS['scope_pin']['sha256'],'historical_launch_outcome':'unknown_retained',
     'actual_error_reader':INPUTS['actual_error_reader'],'time_utc':recorder.now(),'automatic_retry':False}
   recorder.write_new(MARKER,marker);result['remove_requested']=True
   removed=flow.android(['/system/bin/cmd','activity','stack','remove',str(TASK)],20,mutation=True)
   need(flow.command_index==3,'EXACTLY_ONE_REMOVE_COMMAND')
   qualify_joined_command(record_command(3),removed,True)
   result['remove_acknowledged']=True
   def completion_record(value):
    index=len(result['completion_observations'])+1
    recorder.write_new(flow.step/('retirement-private-readback-%02d.json'%index),value)
    need(type(value) is dict and type(value.get('raw_stacks')) is str,'COMPLETE_RETIREMENT_READBACK_REQUIRED')
    r,t=flow.tasks.parse_stacks(value['raw_stacks']);preserve(r,t)
    result['completion_observations'].append({'observation':index,**observed(value['raw_stacks'],r,t)})
    if TASK in t:
     need(r.get(TASK,{}).get('children')==[{'id':TASK,'component':COMPONENT,'user':0}],
          'TARGET_COMPONENT_CHANGED_DURING_RETIREMENT')
   def completion_stacks(timeout):
    raw=flow.android(['/system/bin/cmd','activity','stack','list'],timeout)
    need(flow.command_index<=35,'RETIREMENT_READ_COUNT_BOUND')
    qualify_joined_command(record_command(flow.command_index),raw,False)
    return raw.decode('utf-8','strict')
   result['normal_completion']=flow.tasks.wait_for_removal(completion_stacks,TASK,PACKAGE,tasks,completion_record)
   result['normal_removal_verified']=True
 except BaseException as error:remember('retirement',error)
 finally:
  if flow is not None and flow.step is not None and result.get('before_tables_qualified') is True:
   result['independent_after_attempted']=True
   try:
    raw,roots,tasks=flow.stacks(timeout=20)
    need(flow.command_index<=36,'TOTAL_RETIREMENT_COMMAND_BOUND')
    qualify_joined_command(record_command(flow.command_index),raw.encode(),False)
    preserve(roots,tasks)
    result['independent_after']=observed(raw,roots,tasks)
    need(result['independent_after']['target_absent'] and roots==baseline_roots and tasks==baseline_tasks,
         'EXACT_TARGET_RETIREMENT_OR_BASELINE_RESTORATION_UNQUALIFIED')
    result['independent_after_completed']=True
   except BaseException as error:remember('independent_after',error)
  if flow is not None and flow.step is not None:
   for number in range(1,min(flow.command_index,36)+1):
    try:record_command(number)
    except BaseException as error:remember('retained_command_%d'%number,error)
  if flow is not None:
   result['removal_action_attempted']=bool(flow.action_attempted)
   try:
    flow.guard(attempted=flow.action_attempted)
    result['Main_after']=flow.current_guard.current_guard(flow.activation,action_attempted=flow.action_attempted)
    need(result.get('Main_before')==result['Main_after'],'MAIN_OUTER_MAP_CHANGED')
    result['after_Main_guard']=True
   except BaseException as error:remember('after_Main_guard',error)
   try:flow.close();result['held_binding_released']=True
   except BaseException as error:remember('held_binding_release',error)
  if action_lock is not None:
   try:os.close(action_lock);result['global_action_lock_released']=True
   except BaseException as error:remember('global_action_lock_release',error)
 complete=bool(not result['errors'] and result.get('before_tables_qualified') is True and
  result['independent_after_completed'] and result.get('after_Main_guard') is True and
  result['held_binding_released'] and result['global_action_lock_released'] and
  (result.get('already_absent_without_removal') is True or
   (result['remove_acknowledged'] and result.get('normal_removal_verified') is True)))
 result['ok']=complete
 result['retirement_outcome_unknown']=result['removal_action_attempted'] and not complete
 result['historical_launch_outcome']='unknown_retained'
 if complete:
  try:
   receipt={'schema':'pocket4-independent-native-launch-retirement-reconciliation-v1',
    'created_utc':recorder.now(),'source_sha256':source_sha256,'task':TASK,'component':COMPONENT,
    'original_action_outcome':'unknown_retained','old_action_replayed':False,
    'original_launch_scope_created':False,'authorizes_future_action_replay':False,
    'owned_Android_leaf_absent':True,'preexisting_root_and_task_content_preserved':True,
    'actual_error_reader':INPUTS['actual_error_reader'],'historical_attribution':result['historical_attribution'],
    'before_tables':result['before_tables'],'independent_after':result['independent_after'],
    'command_result_pins':[{k:row[k] for k in ('path','bytes','sha256')} for row in result['command_records']]}
   recorder.write_new(RECONCILIATION,receipt)
   receipt_raw=recorder.read_regular(RECONCILIATION)
   result['independent_reconciliation_receipt']={'path':str(RECONCILIATION),'bytes':len(receipt_raw),'sha256':sha(receipt_raw)}
  except BaseException as error:remember('new_reconciliation_receipt',error);result['ok']=False
 result['retirement_outcome_unknown']=result['removal_action_attempted'] and not result['ok']
 if flow is not None and flow.step is not None:
  try:recorder.write_new(flow.step/'result.json',result)
  except BaseException as error:remember('durable_retirement_result',error);result['ok']=False
 result['retirement_outcome_unknown']=result['removal_action_attempted'] and not result['ok']
 data=(json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
 need(len(data)<=65536,'SAFE_RETIREMENT_OUTPUT_BOUND')
 print(data.decode(),end='',flush=True)
 return 0 if result['ok'] else 1
