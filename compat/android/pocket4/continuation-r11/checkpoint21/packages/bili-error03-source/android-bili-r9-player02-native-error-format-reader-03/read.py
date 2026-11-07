"""Exact historical native error format projection; no Android/process actions."""
import datetime,hashlib,json,os,re,stat,time
from pathlib import Path
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
FILES={'worker':STEP/'result.json','native_intent':STEP/'command-004.intent.json',
 'native_result':STEP/'command-004.result.json','native_stdout':STEP/'command-004.stdout',
 'native_stderr':STEP/'command-004.stderr'}
PINS={"worker":{"bytes":5202,"sha256":"037076b15c27611f83815ad243280a1ec8eae82416616c928c9106e17f7a12ca"},"native_intent":{"bytes":905,"sha256":"d32349c997ab06bb4edfe66195b678dee9b9d1b68963ad3ef71cc315d9a40b11"},"native_result":{"bytes":442,"sha256":"82f2d9bc9dd72c6c99c02b8ec17ffa924d551a69c6d53697937569e981d2ae3e"},"native_stdout":{"bytes":495,"sha256":"2957db51935e4687990181acd1e9a395fb24326c4289725b67d2d48724024fc8"},"native_stderr":{"bytes":429,"sha256":"9c250f60fa544fa1a89c100d204dadf10e5e7f6a90f0cb7bd95b029e2910497b"}}
LIMITS={name:pin['bytes'] for name,pin in PINS.items()}
MESSAGE_PIN={'bytes':414,'sha256':'06a69fd403766d93148369a9dc947283dc96f27be71e26e8295d510b2f4c62a3'}
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
SOURCE_FORMAT_REFERENCES=json.loads("[{\"name\":\"cli\",\"bytes\":20413,\"sha256\":\"19a9e75d0deb0836fb9d125850600004a4a15be1b1ce8519fb8ca40e2165708d\",\"git_blob\":\"6f523958b64d22b481f77595fae7ab9842a6085a\",\"installed_binary_source_match\":false},{\"name\":\"control\",\"bytes\":70656,\"sha256\":\"8289b74fdf040d2bd3a85d12f4488a82bdab4e1c4c6844ab90fe113228d91200\",\"git_blob\":\"2bed3026cc4f00c819de2ba7fd253165d29bebbb\",\"installed_binary_source_match\":false},{\"name\":\"tasklib\",\"bytes\":56199,\"sha256\":\"8c2bd767a62d6d16a3e02daf7fc992d6c4f79adf6d61efd7c6c199b6650f08d0\",\"git_blob\":\"ada531e16c2ebd29c6d83bbfa1261673f29bff57\",\"installed_binary_source_match\":false},{\"name\":\"taskmain\",\"bytes\":7949,\"sha256\":\"23bb117afd8aa81e23f23b20ce8b4ca9901e7e17a20315d29b3d922b77c789ba\",\"git_blob\":\"3d437b0c5d4672c34906989006a731a255bff436\",\"installed_binary_source_match\":false},{\"name\":\"taskcontrol\",\"bytes\":24083,\"sha256\":\"03cb2bb4b13a78adadf173ffae4fd8e3c29a471fd439c7838e44345bd494fd01\",\"git_blob\":\"ef22176682715fc604d37efaf7a2208ed0243d3d\",\"installed_binary_source_match\":false},{\"name\":\"servicecontrol\",\"bytes\":30368,\"sha256\":\"f2314f92862bab1d5354220ecb24954acdbbc536529daf36818b0a8974e1499c\",\"git_blob\":\"5ff38e3b531a6cbe48aa92c45f581ff8e7bcdb17\",\"installed_binary_source_match\":false},{\"name\":\"composertask\",\"bytes\":16609,\"sha256\":\"daa184048871f89545858f30448982bd60212affbc37fe93c6b1b9c5394be350\",\"git_blob\":\"b9aa4e80581a7e4fdc814c0b1bcf320cd5284ebc\",\"installed_binary_source_match\":false}]")

STAGES=('control','policy','wake','snapshot','permission_resolver','activity','alias','discovery','registration')
NUMBER=r'(0|[1-9][0-9]{0,12})'
CLOSED_CHILD_PATTERNS=(('backend_different_registration_ownership',
 r'task-control request failed: Backend: Android task (?P<task>[1-9][0-9]{0,9}) is already registered with different ownership'),)
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
def project_message(message):
 need(type(message) is str and 0<len(message.encode('utf-8'))<=512,'MESSAGE_BOUND')
 base={'bytes':len(message.encode()),'sha256':sha(message.encode()),
       'raw_message_exported':False,'installed_binary_source_match':False,
       'source_format_reference_only':True,'semantic_cause_inferred':False,
       'complete_closed_error_shape':False,'task_cleanup_authority_created':False,
       'public_timing_diagnostic':public_timing_diagnostic(message),'first_rejection':None}
 def reject(stage):return {**base,'complete_wrapper_match':False,'first_rejection':stage}
 outer=re.fullmatch(r'Android task launch failed \(exit status: 1\): ([^\r\n]{1,384})\n([^\r\n]{1,256})',message)
 if outer is None:return reject('OUTER_TWO_LINE_WRAPPER')
 timing,error=outer.groups()
 parts=timing.split(' ')
 if len(parts)<5 or parts[0]!='droidloom-launch-timing' or parts[1]!='ok=false' or parts[2] not in ('policy_cached=false','policy_cached=true'):
  return reject('TIMING_HEADER_FIELDS')
 parsed=[]
 for token in parts[3:]:
  match=re.fullmatch(r'([a-z_]+)_us='+NUMBER,token)
  if match is None:return reject('TIMING_FIELD_FORMAT')
  parsed.append((match[1],int(match[2])))
 if len(parsed)<2 or tuple(k for k,v in parsed[-2:])!=('pending','total'):
  return reject('TIMING_TRAILER_FIELDS')
 stages=parsed[:-2];names=tuple(k for k,v in stages)
 if names!=STAGES[:len(names)] or not 1<=len(names)<=8:
  return reject('TIMING_STAGE_PREFIX')
 pending,total=parsed[-2][1],parsed[-1][1]
 # record() floors each stage separately; finish() obtains pending then total later.
 if total<sum(v for k,v in stages)+pending:
  return reject('TIMING_TOTAL_BELOW_SUM')
 prefix='droidloom-task-launcher: '
 if not error.startswith(prefix):return reject('TASK_LAUNCHER_PREFIX')
 child=error[len(prefix):]
 known_prefixes={'control':'task-control request failed: ',
 'io':'process operation failed: ','transport':'task-control transport failed: ',
 'codec':'task-control codec failed: ','activity':'Android activity launch failed: ',
 'discovery':'Android task discovery failed: ','request':'invalid launch request: '}
 found=[k for k,v in known_prefixes.items() if child.startswith(v)]
 if len(found)!=1:return reject('CHILD_ERROR_CLASS')
 payload=child[len(known_prefixes[found[0]]):]
 need(0<len(payload.encode())<=256,'CHILD_PAYLOAD_BOUND')
 closed=classify_closed_child(child)
 labelled=[]
 for match in re.finditer(r'(?<![A-Za-z0-9_])task(?:_id| id)?(?:=|: | )([1-9][0-9]{0,9})(?![A-Za-z0-9_])',payload):
  if int(match[1])<=2147483647:labelled.append(int(match[1]))
 return {**base,'complete_wrapper_match':True,'native_exit_status':1,
  'timing':{'ok':False,'policy_cached':parts[2]=='policy_cached=true',
    'recorded_stages':list(names),'stage_us':dict(stages),'pending_us':pending,'total_us':total,
    'recording_is_not_success_attestation':True},
  'child':{'class_from_known_source_prefix':found[0],
    'bytes':len(child.encode()),'sha256':sha(child.encode()),
    'private_payload_bytes':len(payload.encode()),'private_payload_sha256':sha(payload.encode()),
    'unknown_error_text_exported':False},
  'complete_closed_error_shape':closed is not None,'closed_error':closed,
  'unclassified_labelled_task_mentions':sorted(set(labelled)),
  'labelled_mentions_are_not_ownership_authority':True}

def pair_projection(stdout,stderr):
 value=strict_json(stdout)
 need(type(value) is dict and set(value)=={'ok','host_pid','message','state'} and
      value['ok'] is False and type(value['host_pid']) is int and value['host_pid']==3588089 and
      value['state']=='running' and type(value['message']) is str,'EXACT_NATIVE_RESPONSE_FIELDS')
 message=value['message']
 need(stderr==('droidloomctl: '+message+'\n').encode('utf-8'),'STDERR_MUST_EXACTLY_REPEAT_NATIVE_MESSAGE')
 return project_message(message)
def projection_controls():
 rows=[]
 def yes(name,condition):
  need(condition,'CONTROL_FAILED_'+name.upper());rows.append({'name':name,'passed':True})
 def no(name,call):
  try:call()
  except RuntimeError:yes(name,True);return
  raise RuntimeError('CONTROL_DID_NOT_REJECT_'+name.upper())
 timing='droidloom-launch-timing ok=false policy_cached=true control_us=1 policy_us=2 wake_us=3 snapshot_us=4 permission_resolver_us=5 activity_us=6 alias_us=7 discovery_us=8 pending_us=9 total_us=45'
 child='droidloom-task-launcher: task-control request failed: Synthetic: task 873 PRIVATE_UNKNOWN_LABEL'
 prefix='Android task launch failed (exit status: 1): '
 message=prefix+timing+'\n'+child
 projected=project_message(message)
 yes('complete_known_wrapper',projected['complete_wrapper_match'] and
     projected['timing']['recorded_stages']==list(STAGES[:8]) and projected['timing']['stage_us']['discovery']==8)
 yes('unknown_payload_private','PRIVATE_UNKNOWN_LABEL' not in json.dumps(projected) and
     projected['complete_closed_error_shape'] is False and projected['semantic_cause_inferred'] is False)
 yes('labelled_task_not_authority',projected['unclassified_labelled_task_mentions']==[873] and
     projected['task_cleanup_authority_created'] is False and projected['labelled_mentions_are_not_ownership_authority'] is True)
 for name,changed in (
  ('wrong_outer_prefix',message.replace('Android task launch','Android unrelated launch')),
  ('missing_recorded_stage',message.replace('policy_us=2 ','')),
  ('duplicate_recorded_stage',message.replace('policy_us=2 ','policy_us=2 policy_us=2 ')),
  ('unknown_recorded_stage',message.replace('policy_us=2','unknown_us=2')),
  ('negative_duration',message.replace('pending_us=9','pending_us=-9')),
  ('impossible_total',message.replace('total_us=45','total_us=1')),
  ('extra_message_line',message+'\nPRIVATE_UNKNOWN_LABEL'),
  ('wrong_task_launcher_prefix',message.replace('droidloom-task-launcher: ','unbound-launcher: ')),
 ):
  yes(name,project_message(changed)['complete_wrapper_match'] is False)
 opaque=project_message(prefix+timing+'\n'+'droidloom-task-launcher: task-control request failed: Synthetic: private 873 PRIVATE_UNKNOWN_LABEL')
 yes('unlabelled_number_not_exported',opaque['unclassified_labelled_task_mentions']==[])
 over=project_message(message.replace('task 873','task 2147483648'))
 yes('task_id_bound',over['unclassified_labelled_task_mentions']==[])
 raw=(json.dumps({'ok':False,'host_pid':3588089,'message':message,'state':'running'})+'\n').encode()
 error=('droidloomctl: '+message+'\n').encode()
 yes('exact_stdout_stderr_agreement',pair_projection(raw,error)==projected)
 no('stderr_disagreement',lambda:pair_projection(raw,error+b'x'))
 no('duplicate_JSON_key',lambda:pair_projection(b'{"ok":false,"ok":false}',error))
 exact_child='task-control request failed: Backend: Android task 873 is already registered with different ownership'
 exact=classify_closed_child(exact_child)
 yes('exact_producer_child',exact=={'shape':'backend_different_registration_ownership','labelled_fields':{'task':873}})
 closed_message=prefix+timing+'\n'+'droidloom-task-launcher: '+exact_child
 yes('complete_producer_message',project_message(closed_message)['closed_error']==exact and
     project_message(closed_message)['complete_closed_error_shape'] is True)
 yes('producer_suffix_rejected',classify_closed_child(exact_child+' PRIVATE_UNKNOWN_LABEL') is None)
 yes('producer_wrong_code_rejected',classify_closed_child(exact_child.replace('Backend:','Conflict:')) is None)
 no('producer_task_range_rejected',lambda:classify_closed_child(exact_child.replace('task 873','task 2147483648')))
 yes('producer_task_is_parsed_not_assumed',classify_closed_child(exact_child.replace('task 873','task 874'))['labelled_fields']=={'task':874})
 need(len(rows)==22,'CONTROL_COUNT_CHANGED')
 return rows
def safe_error(error):
 value=str(error);kind=type(error).__name__
 out={'type':kind if kind in ('RuntimeError','OSError','FileNotFoundError','PermissionError',
     'ValueError','TypeError','JSONDecodeError','UnicodeDecodeError','KeyError') else 'other',
     'message_sha256':sha(value.encode('utf-8','replace')),'raw_error_text_exported':False}
 if isinstance(error,RuntimeError) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,127}',value):out['fixed_code']=value
 if type(getattr(error,'errno',None)) is int and 0<=error.errno<=4095:out['errno']=error.errno
 return out
def collect():
 need(os.getuid()==os.geteuid()==0,'ROOT_READ_ONLY_REQUIRED')
 reader=Reader();observations={};errors=[];projection=None;bindings={}
 controls=projection_controls()
 try:
  raw={}
  for name,pin in PINS.items():
   data=reader.access(name,True)
   need(len(data)==pin['bytes'] and sha(data)==pin['sha256'],'FIXED_NATIVE_ORIGINAL_CHANGED')
   raw[name]=data;observations[name]={'path':str(FILES[name]),**pin}
  worker=strict_json(raw['worker']);original=qualify_worker(worker)
  intent=strict_json(raw['native_intent']);result=strict_json(raw['native_result'])
  need(qualify_native(intent,result,original),'NATIVE_COMMAND_BINDING_FAILED')
  value=strict_json(raw['native_stdout']);message=value.get('message')
  need(type(message) is str and len(message.encode())==MESSAGE_PIN['bytes'] and
       sha(message.encode())==MESSAGE_PIN['sha256'],'EXACT_ACTUAL_MESSAGE_PIN_REQUIRED')
  child_line=message.split('\n')[-1].encode()
  need(len(child_line)==126 and sha(child_line)=='557a6cb23e42b9f540c083e98bf7b4548205cb72ad3e4f39fbc4ad705d03fe87',
       'EXACT_PRIOR_ACTUAL_CHILD_ERROR_LINE')
  projection=pair_projection(raw['native_stdout'],raw['native_stderr'])
  bindings={'worker_exact':True,'native_command_equals_worker':True,
            'stdout_and_stderr_pins_exact':True,'exact_message_pin':True,
            'stdout_and_stderr_complete_agreement':True}
 except BaseException as error:errors.append(safe_error(error))
 finally:
  if reader.opened!=reader.closed:errors.append({'fixed_code':'READER_FD_CLOSE_NOT_COMPLETE'})
 result={'schema':'pocket4-fixed-native-error-format-projection-v1','ok':not errors,
  'source_sha256':SOURCE_SHA256,'historical_flow_nonce':NONCE,'historical_worker_pin':WORKER_PIN,
  'observations':observations,'bindings':bindings,'projection':projection,
  'source_format_references':SOURCE_FORMAT_REFERENCES,
  'controls':controls,'control_count':len(controls),'errors':errors,
  'reader_opened_fds':reader.opened,'reader_closed_fds':reader.closed,
  'reader_acquired_fds_closed':reader.opened==reader.closed,'bytes_read':reader.bytes,
  'historical_launch_outcome_unknown_retained':True,'original_files_modified':0,
  'raw_message_or_unknown_text_exported':False,'private_UI_read':False,
  'Android_commands':0,'UI_actions':0,'processes_spawned':0,'task_cleanup_authorized':False,
  'current_task_state_observed':False,'current_installed_source_version_verified':False,
  'whole_app_production_ready':False}
 data=(json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
 need(len(data)<=32768,'SAFE_SUMMARY_BOUND')
 print(data.decode(),end='',flush=True)
 return 0 if result['ok'] else 1
