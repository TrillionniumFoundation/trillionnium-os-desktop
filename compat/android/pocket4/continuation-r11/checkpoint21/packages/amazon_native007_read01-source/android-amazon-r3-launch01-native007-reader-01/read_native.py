"""Fixed historical Amazon launch007 chain and closed public error projection; no Android calls."""
import ast,datetime,hashlib,json,math,os,re,stat,time
from pathlib import Path
ROOT=Path('/home/alex/work/pocket4-amazon-r3-current-search-entry-01')
FLOW=Path('/home/alex/work/pocket4-amazon-owned-qa-r3-flow-42ee4dd8ab30f563567ba353deff430c')
STEP=FLOW/'steps/launch-01'
NONCE='42ee4dd8ab30f563567ba353deff430c'
SOURCE_SHA='452b2c85207d60d5e47efbeafc05f49ecae416fabf6988fb7362100d55d6e46c'
PACKAGE='com.amazon.mShop.android.shopping'
COMPONENT=PACKAGE+'/com.amazon.mShop.home.HomeActivity'
SCOPE_FIXED=json.loads("{\"schema\":\"pocket4-current-recorder-scope-v1\",\"current_baseline_schema\":\"pocket4-main-current-baseline-v1\",\"package\":\"com.amazon.mShop.android.shopping\",\"component\":\"com.amazon.mShop.android.shopping/com.amazon.mShop.home.HomeActivity\",\"uid\":10129,\"user\":0,\"nonce\":\"42ee4dd8ab30f563567ba353deff430c\",\"epoch_sha256\":\"734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2\",\"current_baseline_sha256\":\"163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266\",\"current_baseline_qualification_sha256\":\"f37b2eb00db80c398c9a4f9fd895628b6c7ecc827ccf9699c2242fa5ba862ed6\",\"amazon_task_source_manifest_sha256\":\"452b2c85207d60d5e47efbeafc05f49ecae416fabf6988fb7362100d55d6e46c\",\"automatic_retry\":false,\"original_recorder_manifest_sha256\":\"6d99374e1580083fd0f30b7f9b3c520306680760c97ad0d5400798fda427fb6e\",\"actual_resolution_result_sha256\":\"ebeaecf791eba4906502cd3167c08e735d826ffd565f7fdd45d66775c016c534\"}")
FILES={
 'coordinator':ROOT/'result.json','stage':ROOT/'stage-result.json','worker':STEP/'result.json',
 'native_intent':STEP/'command-007.intent.json','native_result':STEP/'command-007.result.json',
 'native_stdout':STEP/'command-007.stdout','native_stderr':STEP/'command-007.stderr',
 'scope':FLOW/'scope.json','attempted':FLOW/'launch-attempted.json',
 'prelaunch_stacks':STEP/'prelaunch-stacks.txt','prelaunch_result':STEP/'command-006.result.json',
 'prelaunch_stdout':STEP/'command-006.stdout','prelaunch_transport':STEP/'transport-006.verified-result.json',
 'task_parser':Path('/home/alex/work/pocket4-current-host-r5-source-01/references/task_scope_baseline.py'),
 'launch_scope':FLOW/'launch-scope.json'}
LIMITS={key:65536 for key in FILES}
LIMITS['prelaunch_stacks']=LIMITS['prelaunch_stdout']=131072
PINS={
 'coordinator':{'bytes':6731,'sha256':'6ad6d5b5ee5007dccad21ef6a2847fb84a1afbf48d3de5c13ac9152bd3432541'},
 'stage':{'bytes':2724,'sha256':'ae0ce8201b2cb5ef8f263b746600029109a14d3e32bb790cd16d16ce745bde99'},
 'worker':{'bytes':14255,'sha256':'471fd0060d935a14af74a30206607d58267c96982769cb24e442fa5c92ecf95c'},
 'task_parser':{'bytes':17281,'sha256':'a16e347abb0de2ccbff24f6d7990f6dab1be600675054b45203e907fa8eef528'}}
NATIVE_STREAMS={'stdout':'ca774384a094e8df77b574594fc64bc5f4a8a240952d56c5bdd086bf2e6bf604',
 'stderr':'1e388de5abbf8b2daa52b214888e805f53bce93f34ea207f97ccf526596f9ab3'}
NATIVE_ARGV=['/usr/bin/sudo','-n','-u','#1000','--','/usr/bin/env',
 'XDG_RUNTIME_DIR=/run/user/1000','DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus',
 '/usr/bin/droidloomctl','launch',PACKAGE,'--component',COMPONENT,'--json']
STACKS=['/system/bin/cmd','activity','stack','list']
NUMBER=r'(0|[1-9][0-9]{0,12})'
STAGES=('control','policy','wake','snapshot','permission_resolver','activity','alias','discovery')
CLOSED_CHILD_PATTERNS=(('backend_different_registration_ownership',
 r'task-control request failed: Backend: Android task (?P<task>[1-9][0-9]{0,9}) is already registered with different ownership'),)
def need(value,code):
 if not value:raise RuntimeError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def pin(raw):return {'bytes':len(raw),'sha256':sha(raw)}
def canon(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
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


def safe_error(error):
 value=str(error);kind=type(error).__name__
 out={'type':kind if kind in ('RuntimeError','OSError','FileNotFoundError','PermissionError',
     'ValueError','TypeError','JSONDecodeError','UnicodeDecodeError','KeyError') else 'other',
     'message_sha256':sha(value.encode('utf-8','replace')),'raw_error_text_exported':False}
 if isinstance(error,RuntimeError) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,127}',value):out['fixed_code']=value
 if type(getattr(error,'errno',None)) is int and 0<=error.errno<=4095:out['errno']=error.errno
 return out

def classify_closed_child(error):
 matches=[]
 for name,pattern in CLOSED_CHILD_PATTERNS:
  matched=re.fullmatch(pattern,error)
  if matched is not None:
   fields={}
   for key,value in matched.groupdict().items():
    need(re.fullmatch(r'[1-9][0-9]{0,9}',value) and int(value)<=2147483647,'CLOSED_ID_BOUND')
    fields[key]=int(value)
   matches.append({'shape':name,'labelled_fields':fields})
 need(len(matches)<=1,'AMBIGUOUS_CLOSED_ERROR_SHAPE')
 return matches[0] if matches else None

def public_timing_diagnostic(message):
 lines=message.split('\n')
 first=lines[0]
 marker='droidloom-launch-timing'
 out={'line_count':len(lines),'line_metadata':[{'bytes':len(x.encode()),'sha256':sha(x.encode())} for x in lines],
      'first_line_has_exact_outer_prefix':first.startswith('Android task launch failed (exit status: 1): '),
      'known_timing_marker_count_in_first_line':first.count(marker),'tokens':[],
      'unknown_token_text_exported':False,'numeric_values_are_label_bound':True}
 if first.count(marker)!=1:return out
 offset=first.index(marker);out['prefix_before_timing']={'bytes':len(first[:offset].encode()),'sha256':sha(first[:offset].encode())}
 tokens=first[offset:].split(' ')
 if len(tokens)>64:
  out['token_bound_exceeded']=True;return out
 known={'droidloom-launch-timing','ok=false','ok=true','policy_cached=false','policy_cached=true'}
 labels=set(STAGES)|{'pending','total'}
 fields=[]
 for token in tokens:
  item={'bytes':len(token.encode()),'sha256':sha(token.encode())}
  if token in known:item['known_marker']=token
  else:
   part=re.fullmatch(r'([a-z_]+)_us=(.*)',token)
   if part is not None and part[1] in labels:
    item['known_time_label']=part[1]
    item['unsigned_bounded_decimal']=re.fullmatch(NUMBER,part[2]) is not None
    if item['unsigned_bounded_decimal']:
     item['value_us']=int(part[2]);fields.append((part[1],int(part[2])))
  out['tokens'].append(item)
 out['known_numeric_fields']=[{'label':k,'value_us':v} for k,v in fields]
 out['known_stage_sum_us']=sum(v for k,v in fields if k in STAGES)
 return out

def qualify_worker(c,s,w):
 need(c.get('nonce')==s.get('nonce')==w.get('nonce')==NONCE and
  c.get('source_manifest_sha256')==s.get('source_manifest_sha256')==w.get('source_manifest_sha256')==SOURCE_SHA,
  'EXACT_PARENT_SOURCE_NONCE')
 need(s.get('coordinator_result')=={'path':str(FILES['coordinator']),**PINS['coordinator']} and
  c.get('retained_phase_results',{}).get('launch')=={'path':str(FILES['worker']),**PINS['worker']},
  'EXACT_PARENT_CHAIN')
 for key,val in {'ok':False,'phase':'launch','package':PACKAGE,'uid':10129,
  'helper_package':'org.droidloom.qa.amazon.r3','helper_uid':10154,'action_attempted':True,
  'outcome_unknown':True,'automatic_retry':False,'final_Main_guard_passed':True,
  'held_binding_released':True,'action_lock_released':True,'flow_lock_released':True,
  'source_and_artifact_unchanged':True,'durable_command_count':7}.items():
  need(type(w.get(key)) is type(val) and w[key]==val,'EXACT_FAILED_WORKER_SCOPE')
 need(w.get('secondary_errors')==[] and w.get('target_FD_cleanup',{}).get('held_APK_FDs_closed')==3 and
  w['target_before']==w['failed_scope_files_revalidated'],'THREE_ORIGINAL_ARTIFACTS_REVALIDATED')
 error=w.get('error')
 need(type(error) is dict and set(error)=={'phase','type','message','command_observation'} and
  error['phase']=='one_native_launch' and error['type']=='RuntimeError' and error['message']=='COMMAND_FAILED',
  'EXACT_NATIVE_FAILURE_LOCATION')
 original=error['command_observation']
 need(original.get('spawned') is True and original.get('owned_command_joined') is True and
  original.get('returncode')==1 and original.get('timed_out') is False and original.get('error') is None and
  original.get('errors')==[] and original.get('action_attempted') is True and original.get('automatic_retry') is False,
  'EXACT_ORIGINAL_NATIVE_FAILURE_METADATA')
 for name,digest in NATIVE_STREAMS.items():need(original.get(name+'_sha256')==digest,'ORIGINAL_NATIVE_STREAM_SHA')
 maps=[c['Main_before'],c['Main_after'],s['Main_before'],s['Main_after'],w['Main_before_lock'],w['Main_before'],w['Main_after']]
 need(all(v==maps[0] for v in maps) and maps[0].get('Main_epoch_sha256')==SCOPE_FIXED['epoch_sha256'],
  'ORIGINAL_MAIN_MAPS_DIFFER')
 return original
def qualify_intent(intent,result,original):
 need(type(intent) is dict and set(intent)=={'argv','execution_argv','timeout_seconds','authority_fds_passed',
  'mutation','label','started_utc','automatic_retry'},'EXACT_NATIVE_INTENT_FIELDS')
 need(intent['argv']==intent['execution_argv']==NATIVE_ARGV and intent['timeout_seconds']==70 and
  intent['authority_fds_passed']==[] and intent['mutation'] is True and intent['label']=='One native launch' and
  intent['automatic_retry'] is False,'EXACT_SINGLE_NATIVE_INTENT')
 need(result==original and canon(result)==canon(original),'NATIVE_RESULT_EQUALS_PINNED_WORKER')
 need(utc(intent['started_utc'])<=utc(result['ended_utc']),'NATIVE_TIME_ORDER')
 return True
def qualify_scope(scope,attempted):
 need(type(scope) is dict and scope==SCOPE_FIXED and canon(scope)==canon(SCOPE_FIXED),'EXACT_TYPED_AMAZON_SCOPE')
 need(type(attempted) is dict and set(attempted)=={'step','time_utc','scope'} and
  attempted['step']=='launch-01' and attempted['scope']==scope,'EXACT_NATIVE_ATTEMPT_SCOPE')
 utc(attempted['time_utc']);return True
def task_parser(raw):
 body=[n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name in ('parse_stacks','exact_leaf')]
 need(len(body)==2 and {n.name for n in body}=={'parse_stacks','exact_leaf'},'EXACT_TWO_PURE_TASK_FUNCTIONS')
 env={'re':re,'require':need}
 exec(compile(ast.Module(body=body,type_ignores=[]),'<fixed-original-pure-task-functions>','exec'),env)
 return env['parse_stacks'],env['exact_leaf']
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
def classify_native(stdout,stderr):
 out={'stdout':pin(stdout),'stderr':pin(stderr),'raw_streams_exported':False,
  'current_installed_source_version_verified':False,'complete_wrapper_match':False,
  'whole_error_attribution_qualified':False,'task_cleanup_authority_created':False}
 try:value=strict_json(stdout)
 except (ValueError,UnicodeError,RuntimeError):return {**out,'format':'not_complete_strict_JSON'}
 expected={'ok','host_pid','message','state'}
 if type(value) is not dict or set(value)!=expected:return {**out,'format':'other_JSON_schema'}
 if type(value['ok']) is not bool or type(value['host_pid']) is not int or type(value['state']) is not str or type(value['message']) is not str:
  return {**out,'format':'other_JSON_field_types'}
 message=value['message'];encoded=message.encode()
 need(len(encoded)<=65536,'MESSAGE_BOUND')
 out.update(format='known_four_field_JSON',ok=value['ok'],host_pid=value['host_pid'],
  expected_launcher_host_pid_match=value['host_pid']==3588089,
  state=value['state'] if value['state'] in ('running','stopped','failed') else None,
  state_sha256=sha(value['state'].encode()),message=pin(encoded),
  stderr_exactly_repeats_complete_message=stderr==('droidloomctl: '+message+'\n').encode(),
  closed_word_flags={word:bool(re.search(r'(?<![A-Za-z0-9_])'+re.escape(word)+r'(?![A-Za-z0-9_])',message,re.I))
   for word in ('failed','launch','launcher','task','registered','ownership','permission','timeout','denied','signal','crash')})
 lines=message.split('\n')
 out['line_metadata']=[pin(line.encode()) for line in lines[:32]]
 out['line_count']=len(lines)
 out['closed_child_matches']=[]
 if len(lines)<=32:
  for index,line in enumerate(lines):
   prefix='droidloom-task-launcher: '
   if line.startswith(prefix):
    child=classify_closed_child(line[len(prefix):])
    if child is not None:out['closed_child_matches'].append({'line_index':index,**child})
 if 0<len(encoded)<=512:out['public_timing_diagnostic']=public_timing_diagnostic(message)
 # This first read does not silently generalize any prior opaque token/message.
 return out
def controls(parse,exact_leaf):
 cases=[]
 def passed(name):cases.append({'name':name,'passed':True})
 def reject(name,fn):
  try:fn()
  except (RuntimeError,ValueError,KeyError,TypeError):passed(name);return
  raise RuntimeError('CONTROL_ACCEPTED')
 attempt={'step':'launch-01','time_utc':'2026-11-06T11:28:18.000000+00:00','scope':dict(SCOPE_FIXED)}
 need(qualify_scope(dict(SCOPE_FIXED),attempt),'SCOPE_POSITIVE');passed('typed-scope-and-attempt-positive')
 reject('foreign-package-scope',lambda:qualify_scope({**SCOPE_FIXED,'package':'foreign.pkg'},attempt))
 reject('old-epoch-scope',lambda:qualify_scope({**SCOPE_FIXED,'epoch_sha256':'0'*64},attempt))
 reject('attempt-other-step',lambda:qualify_scope(SCOPE_FIXED,{**attempt,'step':'launch-02'}))
 reject('attempt-other-scope',lambda:qualify_scope(SCOPE_FIXED,{**attempt,'scope':{}}))
 fixture=('RootTask id=123 displayId=0 userId=0 mWindowingMode=freeform\n'
          '  taskId=123: SYNTHETIC_PRIVATE/.Activity bounds=[0,0][1,1] userId=0\n').encode()
 roots,tasks=parse(fixture.decode());need(tasks=={123},'TASK_FIXTURE')
 safe=task_projection(fixture,roots,tasks)
 need('SYNTHETIC_PRIVATE' not in json.dumps(safe),'TASK_TEXT_LEAK');passed('original-task-parser-safe-summary')
 reject('duplicate-task-rejected',lambda:parse((fixture+fixture).decode()))
 reject('unparsed-task-rejected',lambda:parse('RootTask id=123 displayId=0 userId=0\n taskId=invalid\n'))
 child='task-control request failed: Backend: Android task 123 is already registered with different ownership'
 need(classify_closed_child(child)=={'shape':'backend_different_registration_ownership','labelled_fields':{'task':123}},'CLOSED_CHILD')
 passed('exact-public-child-shape')
 need(classify_closed_child(child+' UNKNOWN') is None,'CLOSED_FULLMATCH');passed('child-suffix-not-accepted')
 raw=canon({'ok':False,'host_pid':3588089,'state':'running','message':'SYNTHETIC_PRIVATE message'})
 p=classify_native(raw,b'private mismatch')
 need('SYNTHETIC_PRIVATE' not in json.dumps(p) and not p['stderr_exactly_repeats_complete_message'] and
  p['whole_error_attribution_qualified'] is False,'MESSAGE_PRIVACY')
 passed('unknown-message-hash-only-no-attribution')
 reject('duplicate-JSON-key',lambda:strict_json(b'{"x":1,"x":2}'))
 need(len(cases)==12,'EXACT_TWELVE_CONTROLS');return cases
def collect():
 need(os.getuid()==os.geteuid()==0,'ROOT_FIXED_READ_ONLY')
 r=Reader();observations={};bindings={};errors=[];native=None;prelaunch=None;safe_attempt=None;tests=[]
 def get(name,expected=None):
  raw=r.access(name,True)
  if expected is not None:need(pin(raw)==expected,'FIXED_ORIGINAL_PIN_CHANGED')
  observations[name]={'path':str(FILES[name]),**pin(raw)};return raw
 try:
  fixed={name:get(name,p) for name,p in PINS.items()}
  c,s,w=(strict_json(fixed[k]) for k in ('coordinator','stage','worker'))
  original=qualify_worker(c,s,w)
  parse,exact_leaf=task_parser(fixed['task_parser']);tests=controls(parse,exact_leaf)
  intent_raw=get('native_intent');result_raw=get('native_result')
  intent,result=strict_json(intent_raw),strict_json(result_raw)
  qualify_intent(intent,result,original);bindings['native_intent_and_result_equal_actual_worker']=True
  streams={name:get('native_'+name) for name in ('stdout','stderr')}
  for name,raw in streams.items():need(sha(raw)==NATIVE_STREAMS[name],'NATIVE_STREAM_BOUND_TO_WORKER')
  native=classify_native(streams['stdout'],streams['stderr']);bindings['native_streams_exact']=True
  scope_raw,attempt_raw=get('scope'),get('attempted')
  scope,attempt=strict_json(scope_raw),strict_json(attempt_raw)
  qualify_scope(scope,attempt);bindings['scope_and_attempt_exact_source']=True
  safe_attempt={'step':attempt['step'],'time_utc':attempt['time_utc'],'scope':scope}
  raw=get('prelaunch_stacks');recorded=get('prelaunch_stdout')
  pr=strict_json(get('prelaunch_result'));transport=strict_json(get('prelaunch_transport'))
  need(raw==recorded and pr.get('stdout_sha256')==sha(raw) and pr.get('stderr_sha256')==sha(b'') and
   pr.get('returncode')==0 and pr.get('spawned') is True and pr.get('owned_command_joined') is True and
   pr.get('timed_out') is False and pr.get('error') is None and pr.get('errors')==[] and
   pr.get('action_attempted') is False and pr.get('automatic_retry') is False,'PRELAUNCH_JOINED_READ_ONLY')
  command_sha=sha(json.dumps(STACKS,separators=(',',':')).encode())
  need(transport.get('sequence')==6 and transport.get('epoch_sha256')==SCOPE_FIXED['epoch_sha256'] and
   transport.get('package')==PACKAGE and transport.get('uid')==10129 and transport.get('command_sha256')==command_sha and
   transport.get('returncode')==0 and transport.get('stdout_sha256')==sha(raw) and
   transport.get('stdout_bytes')==len(raw) and transport.get('stderr_bytes')==0 and
   transport.get('stderr_sha256')==sha(b'') and transport.get('outcome_unknown') is False and
   transport.get('automatic_retry') is False and transport.get('numeric_pid_target_used') is False,
   'PRELAUNCH_VERIFIED_HELD_STACKS_ONLY')
  need(utc(pr['ended_utc'])<=utc(attempt['time_utc'])<=utc(intent['started_utc'])<=utc(result['ended_utc']),
   'HISTORICAL_SEQUENCE_ORDER')
  roots,tasks=parse(raw.decode('utf-8','strict'))
  need(not any(child['component'].split('/')[0]==PACKAGE for root in roots.values() for child in root['children']),
   'NO_PREEXISTING_TARGET_BASELINE')
  prelaunch=task_projection(raw,roots,tasks);bindings['prelaunch_exact_source_command_and_complete_original_parser']=True
  meta=r.access('launch_scope',False,optional=True)
  observations['launch_scope_metadata']=meta if meta is not None else {'present':False,'contents_read':False}
  need(meta is None,'ORIGINAL_SUCCESS_SCOPE_MUST_REMAIN_ABSENT')
  bindings['original_success_scope_absent']=True
 except BaseException as error:errors.append(safe_error(error))
 finally:
  if r.opened!=r.closed:errors.append({'fixed_code':'READER_FD_CLOSE_NOT_COMPLETE'})
 out={'schema':'pocket4-fixed-amazon-native-launch007-chain-v1','ok':not errors,'source_sha256':SOURCE_SHA256,
  'observations':observations,'bindings':bindings,'native_projection':native,
  'scope_and_attempt':safe_attempt,'prelaunch':prelaunch,'controls':tests,'control_count':len(tests),
  'errors':errors,'file_descriptors_opened':r.opened,'file_descriptors_closed':r.closed,
  'bytes_read':r.bytes,'historical_launch_outcome_unknown_retained':True,'private_UI_read':False,
  'raw_native_message_or_unknown_task_text_exported':False,'original_files_modified':0,
  'Android_commands':0,'UI_actions':0,'processes_spawned':0,'task_cleanup_authorized':False,
  'current_task_state_observed':False,'current_installed_source_version_verified':False,
  'whole_app_production_ready':False}
 data=(json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
 need(len(data)<=65536,'SAFE_SUMMARY_BOUND')
 print(data.decode(),end='',flush=True);return 0 if out['ok'] else 1
