"""New read-only step in the existing failed Bili flow; never replays launch."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import types
INPUTS=json.loads("{\"schema\":1,\"historical_launch_outcome_unknown\":true,\"create_launch_scope\":false,\"historical_reader_actual_pin\":{\"bytes\":20094,\"sha256\":\"ae37d9b93d94cd367aad404652d18519a1c279b2a1087840949e3e3670abce2d\"},\"historical_reader_job_id\":\"1a1b03beb74-fc05-6f41\",\"historical_reader_source_sha256\":\"5d26f04e67e966bc11d0683d77aba8a8b69b541bd38c820de850636dfea1ab94\",\"historical_reader_bundle_pin\":{\"bytes\":14924,\"sha256\":\"bcf94b903d33875c05ce18613eba42bdc90c7a1554403b83eeedf8897e0d8ca0\"},\"prelaunch_task_baseline\":{\"task_ids\":[870],\"roots\":[{\"children\":[{\"is_exact_target_component\":false,\"is_target_package\":false,\"task_id\":870,\"user\":0}],\"display_id\":0,\"freeform\":false,\"root_id\":1,\"user\":0}]},\"worker_pin\":{\"bytes\":5202,\"sha256\":\"037076b15c27611f83815ad243280a1ec8eae82416616c928c9106e17f7a12ca\"},\"scope_pin\":{\"bytes\":1006,\"sha256\":\"ac6dea24873125a8ac322306786f9f5760fd20b0f1c8d06bc80a498e33eddc50\"},\"attempted_pin\":{\"bytes\":1126,\"sha256\":\"aa6f6ceb01e87b64e1ab0dd2e539958146690b1e1370e1e22d88299239e384d1\"},\"prelaunch_stacks_pin\":{\"bytes\":665,\"sha256\":\"4828128d5f155cfcbdd15b713ae6430eef36735163ca5ed53dd59a7409670e76\"}}")
FLOW=Path('/home/alex/work/pocket4-bilibili-owned-qa-r9-flow-474d7477074ea01fbc986e0d867924c1')
STEP_NAME='native-reconciliation-stacks-read-01'
HOST_ROOT=Path('/home/alex/work/pocket4-current-host-r5-source-01')
HOST_MANIFEST='6d99374e1580083fd0f30b7f9b3c520306680760c97ad0d5400798fda427fb6e'
RECORDER_SHA='7101d2ab2cd4b73bf96cab1117c8d0177c2b290255c6946af52ec834115a7f44'
PACKAGE='tv.danmaku.bili'
COMPONENT=PACKAGE+'/tv.danmaku.bili.MainActivityV2'
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
 need(type(number) is int and number in (1,2),'FIXED_CURRENT_COMMAND_INDEX')
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
def safe_error(error):
 name=type(error).__name__;message=str(error)
 value={'exception_type':name if name in ('RuntimeError','OSError','PermissionError','FileNotFoundError',
  'ValueError','KeyError','TypeError','TimeoutError') else 'other',
  'message_sha256':sha(message.encode('utf-8','replace')),'raw_message_exported':False}
 if isinstance(error,RuntimeError) and re.fullmatch('[A-Z][A-Z0-9_]{0,127}',message):
  value['fixed_code']=message
 if type(getattr(error,'errno',None)) is int:value['errno']=error.errno
 return value
def run(source_sha256):
 need(os.getuid()==os.geteuid()==0,'ROOT_BOUND_READ_REQUIRED')
 need(type(INPUTS) is dict and INPUTS.get('schema')==1 and
      INPUTS.get('historical_launch_outcome_unknown') is True and
      INPUTS.get('create_launch_scope') is False,'EXPLICIT_UNKNOWN_RECONCILIATION_INPUTS')
 result={'schema':1,'ok':False,'errors':[],'source_sha256':source_sha256,
  'step_name':STEP_NAME,'historical_worker_pin':INPUTS['worker_pin'],'command_records':[],
  'historical_launch_outcome_unknown':True,'no_action_replay':True,'current_observations':[],
  'raw_stack_exported':False,'helper_UiAutomation_calls':0,'UI_actions':0,
  'create_launch_scope':False,'task_cleanup_authorized':False,'whole_app_production_ready':False,
  'owned_direct_commands_only':True,'whole_process_tree_cleanup_qualified':False,
  'flow_lock_held_until_process_exit':True,'global_action_lock_acquired':False,
  'global_action_lock_released':False,'held_binding_released':False,
  'before_Main_guard':False,'after_Main_guard':False}
 flow=None;recorder=None;action_lock=None
 def remember(phase,error):result['errors'].append({'phase':phase,**safe_error(error)})
 try:
  for name,path in (
   ('scope',FLOW/'scope.json'),('attempted',FLOW/'launch-attempted.json'),
   ('worker',FLOW/'steps/launch-01/result.json'),
   ('prelaunch_stacks',FLOW/'steps/launch-01/prelaunch-stacks.txt')):
   raw=read_exact(path,INPUTS[name+'_pin'])
   if name=='scope':saved_scope=json.loads(raw)
   elif name=='prelaunch_stacks':baseline_raw=raw
  require_manifest={'bytes':3605,'sha256':HOST_MANIFEST}
  manifest=json.loads(read_exact(HOST_ROOT/'source-manifest.json',require_manifest))
  need(manifest['files']['recorder.py']=={'bytes':41689,'sha256':RECORDER_SHA},
       'ORIGINAL_CURRENT_RECORDER_REQUIRED')
  raw=read_exact(HOST_ROOT/'recorder.py',manifest['files']['recorder.py'])
  recorder=types.ModuleType('fixed_current_bili_recorder_readonly')
  recorder.__file__=str(HOST_ROOT/'recorder.py')
  exec(compile(raw,recorder.__file__,'exec'),recorder.__dict__)
  args=types.SimpleNamespace(operation='stacks',adapter_manifest_sha256=HOST_MANIFEST,flow_dir=FLOW,
   epoch_module=HOST_ROOT/'references/framework_epoch.py',
   task_source=HOST_ROOT/'references/task_scope_baseline.py',step=STEP_NAME,
   request={'purpose':'failed-native-launch-readonly-task-reconciliation',
    'historical_worker_pin':INPUTS['worker_pin'],'historical_launch_outcome':'unknown_retained',
    'Android_command':['/system/bin/cmd','activity','stack','list'],'samples':2},
   unknown_step=None,observation_step=None,postcondition=None)
  flow=recorder.Flow(args)
  need(flow.scope==saved_scope and flow.scope['package']==PACKAGE and flow.scope['uid']==10117,
       'SAVED_FLOW_SCOPE_CHANGED')
  flow.begin(args,mutation=False)
  action_lock=recorder.lock_file(recorder.ACTION_LOCK)
  result['global_action_lock_acquired']=True
  flow.guard();result['before_Main_guard']=True
  result['Main_before']=flow.current_guard.current_guard(flow.activation,action_attempted=False)
  baseline_roots,baseline_tasks=flow.tasks.parse_stacks(baseline_raw.decode('utf-8','strict'))
  baseline=summary(baseline_roots,baseline_tasks)
  need(baseline==INPUTS['prelaunch_task_baseline'],'PINNED_PRELAUNCH_PROJECTION_DIFFERS')
  for number in range(1,3):
   raw,roots,tasks=flow.stacks(timeout=20)
   need(flow.command_index==number and flow.action_attempted is False,'READ_ONLY_COMMAND_COUNT')
   command=owned_command_record(number);result['command_records'].append(command)
   cr=command['record']
   need(cr['returncode']==0 and cr['spawned'] is True and cr['owned_command_joined'] is True and
        cr['timed_out'] is False and cr['errors']==[] and cr['action_attempted'] is False and
        cr['automatic_retry'] is False and cr['stdout_sha256']==sha(raw.encode()),'EXACT_JOINED_CURRENT_STACK_COMMAND')
   observed=summary(roots,tasks)
   result['current_observations'].append({'sample':number,'tasks':observed,
       'raw_stack_bytes':len(raw.encode()),'raw_stack_sha256':sha(raw.encode()),
       'capture_monotonic_ns':time.monotonic_ns()})
   # A failed/partial command throws before another sample; there is no retry.
   flow.guard()
  first,second=[x['tasks'] for x in result['current_observations']]
  same=first==second
  result['two_current_samples_equal']=same
  previous=set(baseline['task_ids']);current=set(second['task_ids'])
  result['prelaunch_task_ids']=sorted(previous)
  result['preserved_prelaunch_task_ids']=sorted(previous&current)
  result['missing_prelaunch_task_ids']=sorted(previous-current)
  result['new_current_task_ids']=sorted(current-previous)
  candidates=[]
  for root in second['roots']:
   for child in root['children']:
    if child['is_target_package']:
     candidates.append({'root_id':root['root_id'],'task_id':child['task_id'],
      'display_id':root['display_id'],'root_user':root['user'],'task_user':child['user'],
      'freeform':root['freeform'],'exact_target_component':child['is_exact_target_component'],
      'root_children':len(root['children']),
      'absent_in_prelaunch_tasks_and_roots':child['task_id'] not in previous and
        child['task_id'] not in {r['root_id'] for r in baseline['roots']}})
  result['target_task_candidates']=candidates
  result['target_candidate_is_an_observation_not_cleanup_authority']=True
  result['read_completed']=True
  need(same,'CURRENT_TASK_SET_CHANGED_BETWEEN_SAMPLES')
 except BaseException as error:remember('current_read',error)
 finally:
  if flow is not None and flow.step is not None:
   for number in range(1,min(flow.command_index,2)+1):
    path=str(FLOW/'steps'/STEP_NAME/('command-%03d.result.json'%number))
    if not any(row['path']==path for row in result['command_records']):
     try:result['command_records'].append(owned_command_record(number))
     except BaseException as error:remember('retained_command_%d'%number,error)
  if flow is not None:
   try:
    flow.guard(attempted=False)
    result['Main_after']=flow.current_guard.current_guard(flow.activation,action_attempted=False)
    need(result.get('Main_before')==result['Main_after'],'MAIN_OUTER_MAP_CHANGED')
    result['after_Main_guard']=True
   except BaseException as error:remember('after_Main_guard',error)
   try:flow.close();result['held_binding_released']=True
   except BaseException as error:remember('held_binding_release',error)
  if action_lock is not None:
   try:os.close(action_lock);result['global_action_lock_released']=True
   except BaseException as error:remember('global_action_lock_release',error)
 result['reader_action_attempted']=False if flow is None else bool(flow.action_attempted)
 result['reader_outcome_unknown']=result['reader_action_attempted']
 result['ok']=(not result['errors'] and result.get('read_completed') is True and result['after_Main_guard'] and
  result['held_binding_released'] and result['global_action_lock_released'] and not result['reader_action_attempted'])
 if flow is not None and flow.step is not None:
  try:recorder.write_new(flow.step/'result.json',result)
  except BaseException as error:remember('durable_readonly_result',error);result['ok']=False
 raw=(json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
 need(len(raw)<=65536,'SAFE_OUTPUT_BOUND')
 print(raw.decode(),end='',flush=True)
 return 0 if result['ok'] else 1
