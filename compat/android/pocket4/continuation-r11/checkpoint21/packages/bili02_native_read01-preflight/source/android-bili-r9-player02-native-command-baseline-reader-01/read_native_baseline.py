"""Fixed Bili R9 player02 failed native command and historical task baseline.
No device access, process actions, cleanup, launch replay, or raw platform text export.
"""
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
ROOT=Path('/home/alex/work/pocket4-bilibili-r9-pause-resume-02')
FLOW=Path('/home/alex/work/pocket4-bilibili-owned-qa-r9-flow-474d7477074ea01fbc986e0d867924c1')
STEP=FLOW/'steps/launch-01'
NONCE='474d7477074ea01fbc986e0d867924c1'
SOURCE_SHA='296da6728d720584339eb47e47801e0c458c3427d06e3a593acdc2f0bc3c6e5d'
R5_SHA='6d99374e1580083fd0f30b7f9b3c520306680760c97ad0d5400798fda427fb6e'
EPOCH='734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2'
PACKAGE='tv.danmaku.bili'
COMPONENT=PACKAGE+'/tv.danmaku.bili.MainActivityV2'
WORKER_PIN={'bytes':5202,'sha256':'037076b15c27611f83815ad243280a1ec8eae82416616c928c9106e17f7a12ca'}
NATIVE_STREAM_SHA={
 'native_stdout':'2957db51935e4687990181acd1e9a395fb24326c4289725b67d2d48724024fc8',
 'native_stderr':'9c250f60fa544fa1a89c100d204dadf10e5e7f6a90f0cb7bd95b029e2910497b'}
SCOPE_FIXED={
 'schema':'pocket4-current-recorder-scope-v1',
 'current_baseline_schema':'pocket4-main-current-baseline-v1',
 'package':PACKAGE,'component':COMPONENT,'uid':10117,'user':0,
 'current_baseline_sha256':'163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266',
 'current_baseline_qualification_sha256':'f37b2eb00db80c398c9a4f9fd895628b6c7ecc827ccf9699c2242fa5ba862ed6',
 'historical_activation_sha256':'7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615',
 'historical_verified_sha256':'2d6f2ef7953b98109044f823da56694111bd9f8ff14fff5e746afb7bd42b0387',
 'epoch_sha256':EPOCH,'adapter_manifest_sha256':R5_SHA,
 'recorder_sha256':'7101d2ab2cd4b73bf96cab1117c8d0177c2b290255c6946af52ec834115a7f44',
 'automatic_retry':False}
NATIVE_ARGV=['/usr/bin/sudo','-n','-u','#1000','--','/usr/bin/env',
 'XDG_RUNTIME_DIR=/run/user/1000','DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus',
 '/usr/bin/droidloomctl','launch',PACKAGE,'--component',COMPONENT,'--json']
STACK_ARGV=['/system/bin/cmd','activity','stack','list']
FILES={
 'worker':STEP/'result.json',
 'native_intent':STEP/'command-004.intent.json',
 'native_result':STEP/'command-004.result.json',
 'native_stdout':STEP/'command-004.stdout',
 'native_stderr':STEP/'command-004.stderr',
 'scope':FLOW/'scope.json',
 'attempted':FLOW/'launch-attempted.json',
 'stack_transport_intent':STEP/'transport-003.intent.json',
 'stack_transport_verified':STEP/'transport-003.verified-result.json',
 'stack_result':STEP/'command-003.result.json',
 'stack_stdout':STEP/'command-003.stdout',
 'prelaunch_stacks':STEP/'prelaunch-stacks.txt',
 'launch_scope':FLOW/'launch-scope.json',
 'cleanup':FLOW/'steps/cleanup-01/result.json'}
LIMITS={name:16384 for name in FILES}
LIMITS.update(worker=5202,scope=4096,attempted=1126,native_stdout=262144,
 native_stderr=262144,stack_stdout=131072,prelaunch_stacks=131072)
def need(value,reason):
 if not value:raise RuntimeError(reason)
require=need
def sha(raw):return hashlib.sha256(raw).hexdigest()
def strict_json(raw):
 def pairs(items):
  result={}
  for key,value in items:
   need(key not in result,'DUPLICATE_JSON_KEY')
   result[key]=value
  return result
 def constant(value):raise RuntimeError('NONFINITE_JSON_NUMBER')
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)
def utc(value):
 need(type(value) is str and re.fullmatch(r'2026-11-06T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00',value),
      'FIXED_DAY_UTC_TIMESTAMP_REQUIRED')
 return datetime.datetime.fromisoformat(value)

class Reader:
 def __init__(self):
  self.started=time.monotonic();self.bytes=0;self.opened=0;self.closed=0
 def opened_fd(self,fd):self.opened+=1;return fd
 def close(self,fd):
  os.close(fd);self.closed+=1
 def maximum(self,name):
  return LIMITS[name]
 def access(self,name,read_bytes,optional=False):
  need(name in FILES,'EXACT_FILE_ALLOWLIST_REQUIRED')
  path=FILES[name];maximum=self.maximum(name)
  current=self.opened_fd(os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC));fd=None
  try:
   try:
    for part in path.parts[1:-1]:
     need(time.monotonic()-self.started<8,'READ_DEADLINE')
     nxt=self.opened_fd(os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current))
     try:self.close(current)
     except BaseException:
      self.close(nxt);raise
     current=nxt
    flags=(os.O_RDONLY if read_bytes else os.O_PATH)|os.O_NOFOLLOW|os.O_CLOEXEC
    fd=self.opened_fd(os.open(path.name,flags,dir_fd=current))
   except FileNotFoundError:
    if optional:return None
    raise
   first=os.fstat(fd)
   if not read_bytes:
    return {'present':True,'regular':stat.S_ISREG(first.st_mode),'symlink':stat.S_ISLNK(first.st_mode),
      'uid':first.st_uid,'nlink':first.st_nlink,'bytes':first.st_size,
      'contents_read':False,'contents_qualified':False}
   need(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and first.st_uid==0 and 0<=first.st_size<=maximum,
        'ROOT_SINGLE_REGULAR_SUMMARY_BOUND')
   chunks=[];size=0
   while True:
    need(time.monotonic()-self.started<8,'READ_DEADLINE')
    part=os.read(fd,min(16384,maximum+1-size))
    if not part:break
    chunks.append(part);size+=len(part);self.bytes+=len(part)
    need(size<=maximum and self.bytes<=1048576,'TOTAL_READ_BOUND')
   last=os.fstat(fd)
   fields=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
   need(size==first.st_size and all(getattr(first,k)==getattr(last,k) for k in fields),'FILE_CHANGED')
   return b''.join(chunks)
  finally:
   try:
    if fd is not None:self.close(fd)
   finally:self.close(current)
def parse_stacks(raw):
    roots={};tasks=set()
    for block in re.split(r'(?=^RootTask id=)',raw,flags=re.M):
        if not block.startswith('RootTask id='):continue
        head=block.splitlines()[0]
        rid=int(re.search(r'^RootTask id=(\d+)\b',head)[1])
        display=int(re.search(r'\bdisplayId=(\d+)\b',head)[1])
        user=int(re.search(r'\buserId=(\d+)\b',head)[1]);children=[]
        for line in block.splitlines():
            match=re.match(r'\s*taskId=(\d+):\s+(\S+)\s+.*?\buserId=(\d+)\b',line)
            require(not re.match(r'\s*taskId=',line) or match is not None,'UNPARSED_TASK_LINE')
            if match:
                tid=int(match[1]);require(tid not in tasks,'DUPLICATE_TASK');tasks.add(tid)
                children.append({'id':tid,'component':match[2],'user':int(match[3])})
        require(rid not in roots,'DUPLICATE_ROOT')
        roots[rid]={'display':display,'user':user,'freeform':'mWindowingMode=freeform' in block,'children':children}
    require(bool(roots) and bool(tasks),'UNRECOGNIZED_STACK_LIST')
    return roots,tasks


def exact_types(value,expected,reason):
 need(type(value) is dict and set(value)==set(expected),reason)
 for key,item in expected.items():
  need(type(value[key]) is type(item) and value[key]==item,reason)
 return value
def qualify_worker(worker):
 fixed={'ok':False,'phase':'launch','nonce':NONCE,'package':PACKAGE,'uid':10117,
  'helper_package':'org.droidloom.qa.bili.r9','helper_uid':10152,
  'source_manifest_sha256':SOURCE_SHA,'runtime_recorder_manifest_sha256':R5_SHA,
  'action_attempted':True,'outcome_unknown':True,'final_Main_guard_passed':True,
  'held_binding_released':True,'action_lock_released':True,'automatic_retry':False}
 need(type(worker) is dict,'WORKER_OBJECT_REQUIRED')
 exact_types({key:worker.get(key) for key in fixed},fixed,'EXACT_FAILED_WORKER_BINDING')
 error=worker.get('error')
 need(type(error) is dict and set(error)=={'phase','type','message','command_observation'} and
      error['phase']=='launch' and error['type']=='RuntimeError' and error['message']=='COMMAND_FAILED' and
      worker.get('secondary_errors')==[],'EXACT_ORIGINAL_NATIVE_FAILURE')
 observation=error['command_observation']
 need(type(observation) is dict and observation.get('returncode')==1 and
      observation.get('spawned') is True and observation.get('owned_command_joined') is True and
      observation.get('timed_out') is False and observation.get('error') is None and
      observation.get('errors')==[] and observation.get('action_attempted') is True and
      observation.get('automatic_retry') is False,'ORIGINAL_NATIVE_OBSERVATION_REQUIRED')
 for name,key in (('native_stdout','stdout_sha256'),('native_stderr','stderr_sha256')):
  need(observation.get(key)==NATIVE_STREAM_SHA[name],'ORIGINAL_NATIVE_STREAM_PIN_REQUIRED')
 utc(worker['ended_utc']);utc(observation['ended_utc'])
 return observation
def qualify_native(intent,result,original):
 need(type(intent) is dict and 'started_utc' in intent,'NATIVE_INTENT_REQUIRED')
 expected={'argv':NATIVE_ARGV,'execution_argv':NATIVE_ARGV,'timeout_seconds':70,
  'authority_fds_passed':[],'mutation':True,'label':'One native launch',
  'started_utc':intent['started_utc'],'automatic_retry':False}
 exact_types(intent,expected,'EXACT_NATIVE_COMMAND_INTENT')
 need(type(result) is dict and result==original and
      json.dumps(result,sort_keys=True,separators=(',',':'))==
      json.dumps(original,sort_keys=True,separators=(',',':')),'NATIVE_RESULT_MUST_EQUAL_PINNED_WORKER')
 need(utc(intent['started_utc'])<=utc(result['ended_utc']),'NATIVE_TIMESTAMP_ORDER')
 return True
def qualify_scope(scope,attempted,native_intent,worker):
 need(type(scope) is dict and set(scope)==set(SCOPE_FIXED)|{'created_utc'},'EXACT_SCOPE_FIELD_SET')
 exact_types({key:scope[key] for key in SCOPE_FIXED},SCOPE_FIXED,'EXACT_TYPED_CURRENT_SCOPE')
 need(type(attempted) is dict and set(attempted)=={'step','time_utc','scope'} and
      attempted['step']=='launch-01' and attempted['scope']==scope and
      json.dumps(attempted['scope'],sort_keys=True,separators=(',',':'))==
      json.dumps(scope,sort_keys=True,separators=(',',':')),'ATTEMPTED_SAVED_SCOPE_EQUAL')
 times=[utc(scope['created_utc']),utc(attempted['time_utc']),
        utc(native_intent['started_utc']),utc(worker['error']['command_observation']['ended_utc']),
        utc(worker['ended_utc'])]
 need(times==sorted(times),'SCOPE_ATTEMPT_NATIVE_WORKER_ORDER')
 return {'scope':scope,'attempted':attempted,'source_binding_verified':True,
         'historical_metadata_only':True,'task_cleanup_authority_created':False}
def qualify_stack(intent,verified,result,raw,saved,attempted):
 expected={'sequence':3,'epoch_sha256':EPOCH,'package':PACKAGE,'uid':10117,
  'command_sha256':sha(json.dumps(STACK_ARGV,ensure_ascii=False,separators=(',',':')).encode()),
  'timeout_seconds':20,'inner_timeout_seconds':15,'automatic_retry':False,
  'numeric_pid_target_used':False}
 exact_types(intent,expected,'EXACT_READONLY_STACK_TRANSPORT_INTENT')
 need(type(verified) is dict and set(verified)==set(expected)|{
      'returncode','stdout_bytes','stderr_bytes','stdout_sha256','stderr_sha256','action_attempted','outcome_unknown'},
      'EXACT_STACK_VERIFIED_FIELDS')
 exact_types({key:verified[key] for key in expected},expected,'STACK_VERIFIED_INTENT_CHAIN')
 need(verified['returncode']==0 and verified['action_attempted'] is True and
      verified['outcome_unknown'] is False and type(verified['stdout_bytes']) is int and
      type(verified['stderr_bytes']) is int and 0<=verified['stderr_bytes']<=262144,
      'STACK_TRANSPORT_SUCCEEDED')
 need(type(result) is dict and result.get('returncode')==0 and result.get('spawned') is True and
      result.get('owned_command_joined') is True and result.get('timed_out') is False and
      result.get('error') is None and result.get('errors')==[] and result.get('action_attempted') is False and
      result.get('automatic_retry') is False,'STACK_RECORDER_SUCCEEDED_WITHOUT_INPUT')
 need(result.get('stdout_sha256')==verified['stdout_sha256']==sha(raw) and
      result.get('stderr_sha256')==verified['stderr_sha256'] and
      verified['stdout_bytes']==len(raw) and saved==raw,'STACK_SAVED_BYTES_AND_TRANSPORT_BINDING')
 need(utc(result['ended_utc'])<=utc(attempted['time_utc']),'STACK_PRECEDES_NATIVE_ATTEMPT')
 roots,tasks=parse_stacks(raw.decode('utf-8','strict'))
 need(len(roots)<=512 and len(tasks)<=512,'TASK_PROJECTION_COUNT_BOUND')
 need(not any(child['component'].split('/')[0]==PACKAGE
      for root in roots.values() for child in root['children']),'SOURCE_PREEXISTING_TARGET_GATE_MISMATCH')
 rows=[]
 for root_id,root in sorted(roots.items()):
  need(0<root_id<2147483648 and 0<=root['display']<2147483648 and 0<=root['user']<=2147483647,
       'ROOT_METADATA_BOUNDS')
  children=[]
  for child in root['children']:
   need(0<child['id']<2147483648 and 0<=child['user']<=2147483647,'TASK_METADATA_BOUNDS')
   children.append({'task_id':child['id'],'user':child['user'],
    'is_target_package':child['component'].split('/')[0]==PACKAGE,
    'is_exact_target_component':child['component']==COMPONENT})
  rows.append({'root_id':root_id,'display_id':root['display'],'user':root['user'],
    'freeform':root['freeform'],'children':children})
 return {'task_ids':sorted(tasks),'roots':rows,'target_package_task_count':0,
  'raw_stack_text_exported':False,'non_target_components_exported':False,
  'baseline_precedes_failed_native_command':True,'current_task_state_observed':False,
  'parser':'exact_original_parse_stacks',
  'parser_source_sha256':'a16e347abb0de2ccbff24f6d7990f6dab1be600675054b45203e907fa8eef528'}
FEATURE_TERMS=('failed','failure','error','launch','task','display','component','package',
 'running','stopped','timeout','timed out','denied','permission','connection','dbus','d-bus',
 'broken pipe','no such file','not found','unavailable','busy','unsupported','invalid',
 'transport','binder','surface','activity','window','signal','sigkill','sigsegv',
 'object','presenter','daemon','launcher','protocol','reply')
KNOWN_VALUES={'running','stopped','starting','failed','error','unknown','ok','success',
 'timeout','timed_out','unavailable','denied','invalid','launch',PACKAGE,COMPONENT,
 'org.freedesktop.DBus.Error.NoReply','org.freedesktop.DBus.Error.AccessDenied',
 'org.freedesktop.DBus.Error.ServiceUnknown','org.freedesktop.DBus.Error.NameHasNoOwner',
 'org.freedesktop.DBus.Error.UnknownMethod','org.freedesktop.DBus.Error.Timeout'}
def format_features(value):
 need(type(value) is str,'STRING_FEATURE_INPUT')
 lower=value.lower()
 flags={term:bool(re.search(r'(?<![a-z0-9_])'+re.escape(term)+r'(?![a-z0-9_])',lower))
        for term in FEATURE_TERMS}
 numbers={}
 receipt=re.fullmatch(r'object=(\d{1,10}) composer_display=(\d{1,10}) android_display=(\d{1,10}) task=(\d{1,10})',value)
 if receipt and all(int(part)<2147483648 for part in receipt.groups()):
  numbers['exact_launch_receipt']={key:int(part) for key,part in
       zip(('object','composer_display','android_display','task'),receipt.groups())}
 errnos=re.findall(r'\bos error ([0-9]{1,4})\b',value)
 if errnos:
  numbers['labelled_os_error_codes']=sorted(set(int(x) for x in errnos if int(x)<=4095))
 return {'fixed_feature_flags':flags,'strict_format_numbers':numbers,
         'raw_text_exported':False,'features_do_not_determine_cause':True}
def field_projection(value):
 if value is None or type(value) is bool:return {'type':type(value).__name__,'value':value}
 if type(value) is int:
  return {'type':'int','value':value} if -255<=value<=2147483647 else {'type':'int','in_range':False}
 if type(value) is str:
  out={'type':'str','utf8_bytes':len(value.encode()),'sha256':sha(value.encode()),**format_features(value)}
  if value in KNOWN_VALUES:out['known_literal']=value
  return out
 return {'type':('dict' if type(value) is dict else 'list' if type(value) is list else 'other'),
         'value_not_exported':True}
def platform_projection(raw):
 out={'bytes':len(raw),'sha256':sha(raw),'raw_text_exported':False,'cause_inferred':False}
 try:text=raw.decode('utf-8','strict')
 except UnicodeDecodeError:
  out.update(valid_utf8=False,JSON_object=False);return out
 lines=text.splitlines()
 out.update(valid_utf8=True,line_count=len(lines),features=format_features(text))
 out['line_hashes']=[{'bytes':len(line.encode()),'sha256':sha(line.encode())} for line in lines[:16]]
 out['line_hashes_truncated']=len(lines)>16
 try:value=strict_json(raw)
 except (ValueError,UnicodeDecodeError,RuntimeError,RecursionError):
  out['JSON_object']=False;return out
 out['JSON_object']=type(value) is dict
 if type(value) is not dict:return out
 fields=('schema','ok','state','host_pid','pid','task','android_display','composer_display',
  'object','returncode','errno','signal','exit_code','outcome_unknown','error','message',
  'reason','detail','code','launch','package','component','command')
 out['fields']={key:field_projection(value[key]) for key in fields if key in value}
 out['other_field_count']=len(set(value)-set(fields))
 for key in ('error','message','reason','detail'):
  if type(value.get(key)) is dict:
   out['fields'][key]['fields']={k:field_projection(value[key][k]) for k in fields if k in value[key]}
   out['fields'][key]['other_field_count']=len(set(value[key])-set(fields))
 return out


def projection_controls():
 cases=[]
 def passed(name,condition):
  need(condition,'CONTROL_FAILED:'+name);cases.append({'name':name,'passed':True})
 def rejected(name,call):
  try:call()
  except RuntimeError:passed(name,True);return
  raise RuntimeError('CONTROL_DID_NOT_REJECT:'+name)
 p=platform_projection(b'{"ok":false,"state":"failed","launch":"object=2 composer_display=0 android_display=0 task=9"}')
 passed('exact_receipt_numbers',p['fields']['launch']['strict_format_numbers']['exact_launch_receipt']['task']==9)
 secret='PRIVATE_LABEL_DO_NOT_EXPORT_684920'
 p=platform_projection(json.dumps({'error':secret,'unknown_'+secret:secret}).encode())
 passed('unknown_text_and_keys_private',secret not in json.dumps(p))
 p=platform_projection((secret+'\n').encode())
 passed('non_json_text_private',secret not in json.dumps(p) and p['JSON_object'] is False)
 rejected('duplicate_json_key',lambda:strict_json(b'{"ok":true,"ok":false}'))
 passed('receipt_suffix_rejected','exact_launch_receipt' not in
        format_features('object=2 composer_display=0 android_display=0 task=9 '+secret)['strict_format_numbers'])
 passed('labelled_errno_only',format_features('os error 13 hidden 98765')['strict_format_numbers']=={'labelled_os_error_codes':[13]})
 start='2026-11-06T09:03:00.000000+00:00';end='2026-11-06T09:03:01.000000+00:00'
 intent={'argv':list(NATIVE_ARGV),'execution_argv':list(NATIVE_ARGV),'timeout_seconds':70,
  'authority_fds_passed':[],'mutation':True,'label':'One native launch','started_utc':start,'automatic_retry':False}
 result={'ended_utc':end}
 passed('native_intent_exact',qualify_native(intent,result,dict(result)))
 rejected('native_wrong_component',lambda:qualify_native({**intent,'argv':NATIVE_ARGV[:-1]+['--other']},result,result))
 rejected('native_result_mismatch',lambda:qualify_native(intent,{**result,'returncode':0},result))
 scope={**SCOPE_FIXED,'created_utc':'2026-11-06T09:02:58.000000+00:00'}
 attempted={'step':'launch-01','time_utc':'2026-11-06T09:02:59.000000+00:00','scope':scope}
 worker={'error':{'command_observation':result},'ended_utc':end}
 passed('current_scope_exact',qualify_scope(scope,attempted,intent,worker)['source_binding_verified'])
 wrong={**scope,'epoch_sha256':'0'*64}
 rejected('wrong_current_epoch',lambda:qualify_scope(wrong,{**attempted,'scope':wrong},intent,worker))
 stack=b'RootTask id=8 displayId=0 userId=0 mWindowingMode=freeform\n taskId=8: example.app/.MainActivity userId=0\n'
 roots,tasks=parse_stacks(stack.decode())
 passed('original_stack_parser',set(roots)=={8} and tasks=={8})
 rejected('duplicate_task',lambda:parse_stacks(stack.decode()+' taskId=8: example.app/.MainActivity userId=0\n'))
 rejected('unparsed_task_line',lambda:parse_stacks(stack.decode()+' taskId=malformed\n'))
 si={'sequence':3,'epoch_sha256':EPOCH,'package':PACKAGE,'uid':10117,
  'command_sha256':sha(json.dumps(STACK_ARGV,separators=(',',':')).encode()),
  'timeout_seconds':20,'inner_timeout_seconds':15,'automatic_retry':False,'numeric_pid_target_used':False}
 sr={'returncode':0,'spawned':True,'owned_command_joined':True,'timed_out':False,'error':None,'errors':[],
  'action_attempted':False,'automatic_retry':False,'stdout_sha256':sha(stack),'stderr_sha256':sha(b''),
  'ended_utc':'2026-11-06T09:02:58.000000+00:00'}
 sv={**si,'returncode':0,'stdout_bytes':len(stack),'stderr_bytes':0,'stdout_sha256':sha(stack),
  'stderr_sha256':sha(b''),'action_attempted':True,'outcome_unknown':False}
 passed('source_bound_baseline_projection',qualify_stack(si,sv,sr,stack,stack,attempted)['task_ids']==[8])
 rejected('saved_stack_mismatch',lambda:qualify_stack(si,sv,sr,stack,stack+b'x',attempted))
 need(len(cases)==16,'CONTROL_COUNT_CHANGED')
 return cases
def safe_error(stage,error):
 name=type(error).__name__
 known={'RuntimeError','FileNotFoundError','PermissionError','OSError','ValueError','TypeError',
  'KeyError','JSONDecodeError','UnicodeDecodeError','RecursionError','OverflowError'}
 message=str(error)
 row={'stage':stage,'type':name if name in known else 'other',
      'message_sha256':sha(message.encode('utf-8','replace')),'raw_error_text_exported':False}
 if isinstance(error,RuntimeError) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,127}',message):
  row['fixed_code']=message
 if type(getattr(error,'errno',None)) is int and 0<=error.errno<=4095:row['errno']=error.errno
 return row
def collect():
 need(os.getuid()==os.geteuid()==0,'ROOT_READ_ONLY_REQUIRED')
 controls=projection_controls()
 reader=Reader();observations={};errors=[];bindings={};diagnostic={};presence={}
 def attempt(name,call):
  try:return call()
  except Exception as error:errors.append(safe_error(name,error));return None
 def read(name,expected=None):
  raw=reader.access(name,True)
  observations[name]={'path':str(FILES[name]),'bytes':len(raw),'sha256':sha(raw)}
  if expected is not None:
   need(set(expected)=={'bytes','sha256'} and len(raw)==expected['bytes'] and
        sha(raw)==expected['sha256'],'EXACT_PINNED_FILE_CHANGED')
  return raw
 def object_read(name,expected=None):
  value=strict_json(read(name,expected));need(type(value) is dict,'RECORD_OBJECT_REQUIRED');return value
 worker=attempt('worker',lambda:object_read('worker',WORKER_PIN))
 original=attempt('worker_scope',lambda:qualify_worker(worker)) if worker is not None else None
 if original is not None:
  bindings['exact_external_worker_original']=True
  intent=attempt('native_intent',lambda:object_read('native_intent'))
  result=attempt('native_result',lambda:object_read('native_result'))
  native_ok=attempt('native_binding',lambda:qualify_native(intent,result,original))
  if native_ok:
   bindings['native_command_004_equals_original_failure']=True
   diagnostic['native_command']={'intent':intent,'result':result,
    'command_index_source_derived_then_actual_verified':4,'failed_launch_outcome_remains_unknown':True}
   for name in ('native_stdout','native_stderr'):
    def stream(name=name):
     raw=read(name)
     need(sha(raw)==NATIVE_STREAM_SHA[name],'EXACT_NATIVE_STREAM_CHANGED')
     diagnostic[name]=platform_projection(raw);bindings[name+'_original_SHA']=True
    attempt(name,stream)
   scope=attempt('scope',lambda:object_read('scope'))
   attempted=attempt('attempted',lambda:object_read('attempted'))
   if attempted is not None:
    attempt('attempted_exact_size',lambda:need(observations['attempted']['bytes']==1126,'ACTUAL_ATTEMPTED_SIZE_CHANGED'))
   def scope_bound():
    diagnostic['launch_attempt_metadata']=qualify_scope(scope,attempted,intent,worker)
    bindings['attempted_scope_fixed_source_and_epoch']=True
    return True
   if attempt('scope_binding',scope_bound):
    stack_intent=attempt('stack_transport_intent',lambda:object_read('stack_transport_intent'))
    stack_verified=attempt('stack_transport_verified',lambda:object_read('stack_transport_verified'))
    stack_result=attempt('stack_result',lambda:object_read('stack_result'))
    stack_raw=attempt('stack_stdout',lambda:read('stack_stdout'))
    saved=attempt('prelaunch_stacks',lambda:read('prelaunch_stacks'))
    if all(x is not None for x in (stack_intent,stack_verified,stack_result,stack_raw,saved)):
     def stack_bound():
      diagnostic['prelaunch_task_baseline']=qualify_stack(stack_intent,stack_verified,stack_result,stack_raw,saved,attempted)
      diagnostic['baseline_command']={'transport_intent':stack_intent,'verified_result':stack_verified,'recorder_result':stack_result}
      bindings['prelaunch_stack_original_and_source_transport_chain']=True
     attempt('prelaunch_binding',stack_bound)
  for name in ('launch_scope','cleanup'):
   def probe(name=name):
    value=reader.access(name,False,optional=True)
    presence[name]={'path':str(FILES[name]),'present':False,'contents_read':False} if value is None else {'path':str(FILES[name]),**value}
   attempt('fixed_presence_'+name,probe)
 if reader.opened!=reader.closed:
  errors.append({'stage':'reader_fd_accounting','type':'RuntimeError','fixed_code':'ACQUIRED_DESCRIPTOR_CLOSE_NOT_COMPLETE'})
 value={'schema':1,'scope':'fixed-r9-player02-native-command-historical-task-baseline',
  'observations':observations,'bindings':bindings,'diagnostic':diagnostic,'fixed_path_presence':presence,
  'controls':controls,'control_count':len(controls),'errors':errors,'collection_complete':not errors,
  'bytes_read':reader.bytes,'reader_opened_fds':reader.opened,'reader_closed_fds':reader.closed,
  'reader_acquired_fds_closed':reader.opened==reader.closed,
  'source_manifest_sha256':SOURCE_SHA,'flow_nonce':NONCE,'historical_launch_outcome_unknown_retained':True,
  'source_derived_record_pins_are_new_observations':True,'current_tasks_read':False,
  'no_device_commands_or_UI_input':True,'processes_spawned':0,'original_files_modified':0,
  'raw_UI_or_unknown_platform_text_exported':False,'raw_stack_text_exported':False,
  'runtime_qualification_asserted':False,'task_cleanup_authorized':False,
  'UI_window_release_claimed':False,'cause_inferred':False,'no_action_replay':True,
  'read_is_sequential_not_atomic':True}
 raw=(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
 need(len(raw)<=65536,'SUMMARY_BUNDLE_BOUND')
 print(json.dumps({'schema':1,'encoding':'base64','private_UI_data':False,
  'uncompressed_bytes':len(raw),'uncompressed_sha256':sha(raw),'data':base64.b64encode(raw).decode('ascii')},sort_keys=True),flush=True)
 return 0 if not errors else 1
if __name__=='__main__':raise SystemExit(collect())

