"""One authenticated daemon Status to one freshly verified owner/init chain."""
import hashlib,json,os,re,stat,time,types
from pathlib import Path
BASELINE=Path('/home/alex/work/pocket4-main-current-baseline-01/baseline.private.json')
BASELINE_PIN={'bytes':41844,'sha256':'163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266'}
EPOCH_SOURCE=Path('/home/alex/work/pocket4-current-host-r5-source-01/references/framework_epoch.py')
EPOCH_PIN={'bytes':8658,'sha256':'f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288'}
OLD_EPOCH='734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2'
PIDS={'daemon':3588022,'launcher':3588089,'presenter':3588024}
MAX_THREADS=64
MAX_CHILDREN=32
FIELDS=('host_pid','parent_host_pid','start_ticks','namespace_pids','uids','cmdline','executable','namespaces','cgroup')
PUBLIC_EXE={'init':'/system/bin/init','zygote64':'/system/bin/app_process64',
 'system_server':'/system/bin/app_process64','surfaceflinger':'/system/bin/surfaceflinger'}
CODES={'INVALID_PROCESS_ID','PROCESS_IDENTITY_UNSTABLE','PROCESS_IDENTITY_INCOMPLETE','PROCESS_IDENTITY_UNAVAILABLE',
 'INVALID_PROCESS_SET','PROCESS_SET_UNSTABLE','BOOT_CHANGED','ANDROID_INIT_UNVERIFIED',
 'FRAMEWORK_PROCESS_SET_AMBIGUOUS_OR_MISSING','ANDROID_INIT_CHANGED','ANDROID_CGROUP_UNVERIFIED',
 'FRAMEWORK_PROCESS_UNVERIFIED','INVALID_EPOCH_DOCUMENT','FRAMEWORK_EPOCH_CHANGED','FRAMEWORK_EPOCH_CHANGED_OR_UNAVAILABLE'}
FIXED_CODES={'ROOT_READ_ONLY_REQUIRED','INPUT_PATH_INVALID','ROOT_SINGLE_REGULAR_INPUT_REQUIRED','EXACT_INPUT_PIN',
 'INPUT_CHANGED_DURING_READ','PRIVATE_BASELINE_SCHEMA','EXACT_OLD_EPOCH_DOCUMENT','EXACT_FOUR_OLD_ROLES',
 'IDENTITY_SCHEMA','IDENTITY_NUMBERS','IDENTITY_NAMESPACES','IDENTITY_PRIVATE_FIELD_BOUND',
 'DISCOVERY_EPOCH_DOCUMENT','DISCOVERY_INIT_DIFFERS_FROM_OLD_CELL','DISCOVERY_BOOT_DIFFERS_FROM_BASELINE',
 'DISCOVERY_ROLES','READ_BUDGET_EXHAUSTED','TRACKED_INPUT_FD_CLOSE_FAILED','CONTROL_COUNT','OUTPUT_BOUND'}
FIXED_CODES.update(["CURRENT_BOOT_UNVERIFIED","CURRENT_BOOT_CHANGED","EXACT_HOST_ROLE_BINDINGS","HOST_BASELINE_BINDINGS","DAEMON_PIDFD_NOT_LIVE","DAEMON_CHANGED","THREAD_LIST_BOUND","THREAD_LIST_SCHEMA","DIRECT_CHILDREN_BOUND","DIRECT_CHILDREN_SCHEMA","DIRECT_CHILDREN_DUPLICATE","DIRECT_CHILDREN_SAMPLE_CHANGED","DIRECT_CHILD_PARENT_DIFFERS","DIRECT_CHILD_IDENTITY_CHANGED","PROC_LEAF_BOUND","CONTROL_COUNT"])
FIXED_CODES.update(['EXACT_OWNER_CANDIDATE','OWNER_GENERATION_CHANGED','OWNER_PARENT_CHANGED',
 'OWNER_PROGRAM_CHANGED','DAEMON_CHILD_SET_CHANGED','EXECUTABLE_PIN_SCHEMA','EXECUTABLE_BACKING_CHANGED',
 'EXECUTABLE_BYTES_CHANGED','STATUS_SOCKET_SHAPE','STATUS_PEER_MISMATCH','STATUS_RESPONSE_BOUND',
 'STATUS_RESPONSE_SCHEMA','STATUS_ANCILLARY_OR_TRUNCATION','STATUS_UNKNOWN_FIELD','FIXED_CELL_CONFIG'])
START=time.monotonic()
FD_OPENED=0
FD_CLOSED=0
FD_CLOSE_ERRORS=[]
def need(value,code):
 if not value:raise RuntimeError(code)
def check_time():
 if time.monotonic()-START>=25:raise BudgetExpired()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canon(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def strict_json(raw):
 def pairs(items):
  value={}
  for key,item in items:
   need(key not in value,'PRIVATE_BASELINE_SCHEMA');value[key]=item
  return value
 def constant(value):raise RuntimeError('PRIVATE_BASELINE_SCHEMA')
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)
def opened(fd):
 global FD_OPENED
 FD_OPENED+=1
 return fd
def close(fd):
 global FD_CLOSED
 try:os.close(fd);FD_CLOSED+=1
 except BaseException as error:
  FD_CLOSE_ERRORS.append(type(error).__name__);raise
def read_fixed(path,pin):
 need(path.is_absolute() and all(part not in ('','.','..') for part in path.parts[1:]),'INPUT_PATH_INVALID')
 check_time();directory=opened(os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC));fd=None
 try:
  for part in path.parts[1:-1]:
   check_time();following=opened(os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory))
   try:close(directory)
   except BaseException:
    close(following);raise
   directory=following
  check_time();fd=opened(os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory))
  first=os.fstat(fd)
  need(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and first.st_uid==0 and first.st_size==pin['bytes'],
   'ROOT_SINGLE_REGULAR_INPUT_REQUIRED')
  pieces=[];size=0
  while size<=pin['bytes']:
   check_time();piece=os.read(fd,min(16384,pin['bytes']+1-size))
   if not piece:break
   pieces.append(piece);size+=len(piece)
  last=os.fstat(fd)
  fields=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
  need(size==first.st_size and all(getattr(first,k)==getattr(last,k) for k in fields),'INPUT_CHANGED_DURING_READ')
  raw=b''.join(pieces);need(len(raw)==pin['bytes'] and sha(raw)==pin['sha256'],'EXACT_INPUT_PIN');return raw
 finally:
  try:
   if fd is not None:close(fd)
  finally:close(directory)
def identity_shape(value):
 need(type(value) is dict and set(value)==set(FIELDS),'IDENTITY_SCHEMA')
 need(type(value['host_pid']) is int and 0<value['host_pid']<=2147483647 and
  type(value['parent_host_pid']) is int and 0<=value['parent_host_pid']<=2147483647 and
  type(value['start_ticks']) is int and 0<=value['start_ticks']<2**64 and
  type(value['namespace_pids']) is list and 1<=len(value['namespace_pids'])<=8 and
  all(type(x) is int and 0<x<=2147483647 for x in value['namespace_pids']) and
  type(value['uids']) is list and len(value['uids'])==4 and
  all(type(x) is int and 0<=x<2**32 for x in value['uids']),'IDENTITY_NUMBERS')
 need(type(value['namespaces']) is dict and set(value['namespaces'])=={'pid','mnt'} and
  all(type(value['namespaces'][k]) is str and re.fullmatch(k+r':\[[0-9]{1,20}\]',value['namespaces'][k]) for k in ('pid','mnt')),
  'IDENTITY_NAMESPACES')
 need(type(value['cmdline']) is list and 1<=len(value['cmdline'])<=256 and all(type(x) is str for x in value['cmdline']) and
  type(value['cgroup']) is list and 1<=len(value['cgroup'])<=32 and all(type(x) is str for x in value['cgroup']) and
  type(value['executable']) is str and len(value['executable'].encode())<=4096 and
  len(canon(value['cmdline']))<=65536 and len(canon(value['cgroup']))<=65536,'IDENTITY_PRIVATE_FIELD_BOUND')
 return value
def project_identity(role,value,expected=None):
 identity_shape(value)
 if expected is not None:identity_shape(expected)
 exe=value['executable'];known=exe==PUBLIC_EXE.get(role)
 return {'host_pid':value['host_pid'],'parent_host_pid':value['parent_host_pid'],'start_ticks':value['start_ticks'],
  'namespace_pids':value['namespace_pids'],'uids':value['uids'],'namespaces':value['namespaces'],
  'identity_sha256':sha(canon(value)),
  'executable':{'known_role_executable':PUBLIC_EXE[role] if known else None,
   'known_role_match':known,'utf8_bytes':len(exe.encode()),'sha256':sha(exe.encode())},
  'cmdline':{'argc':len(value['cmdline']),'canonical_utf8_bytes':len(canon(value['cmdline'])),
   'sha256':sha(canon(value['cmdline'])),'raw_exported':False},
  'cgroup':{'line_count':len(value['cgroup']),'canonical_utf8_bytes':len(canon(value['cgroup'])),
   'sha256':sha(canon(value['cgroup'])),'raw_exported':False,
   'within_known_Main_service':any(line=='0::/system.slice/droidloomd.service' or line.startswith('0::/system.slice/droidloomd.service/') for line in value['cgroup'])},
  'exact_old_identity_match':value==expected if expected is not None else None}
def difference_fields(expected,observed):
 identity_shape(expected);identity_shape(observed)
 result=[key for key in FIELDS if expected[key]!=observed[key]]
 if 'namespaces' in result:result+=['namespaces.'+key for key in ('pid','mnt') if expected['namespaces'][key]!=observed['namespaces'][key]]
 return result
def same_old_init(observed,expected):
 return type(observed) is dict and observed==expected
def safe_error(error):
 kind=type(error).__name__
 code=getattr(error,'code',None)
 if code not in CODES:
  text=str(error);code=text if text in FIXED_CODES else 'UNCLASSIFIED_ERROR'
 if isinstance(error,BudgetExpired):code='READ_BUDGET_EXHAUSTED'
 out={'type':kind if kind in ('EpochError','RuntimeError','OSError','FileNotFoundError','ProcessLookupError',
  'PermissionError','ValueError','KeyError','IndexError','UnicodeDecodeError','JSONDecodeError','BudgetExpired') else 'other',
  'code':code,'raw_message_exported':False}
 cause=getattr(error,'__cause__',None)
 for label,item in (('errno',error),('cause_errno',cause)):
  number=getattr(item,'errno',None)
  if type(number) is int and 0<=number<=4095:out[label]=number
 if cause is not None:
  out['cause_type']=type(cause).__name__ if type(cause).__name__ in ('OSError','FileNotFoundError','ProcessLookupError',
   'PermissionError','ValueError','KeyError','IndexError','UnicodeDecodeError','EpochError') else 'other'
 return out
def controls():
 rows=[]
 def passed(name,condition):
  need(condition,'CONTROL_COUNT');rows.append({'name':name,'passed':True})
 def rejected(name,call):
  try:call()
  except RuntimeError:passed(name,True);return
  raise RuntimeError('CONTROL_COUNT')
 sample={'host_pid':42,'parent_host_pid':1,'start_ticks':100,'namespace_pids':[42,1],'uids':[0,0,0,0],
  'cmdline':['/init','PRIVATE_SENTINEL_COMMAND'],'executable':'/system/bin/init',
  'namespaces':{'pid':'pid:[100]','mnt':'mnt:[200]'},'cgroup':['0::/system.slice/droidloomd.service/PRIVATE_SENTINEL_GROUP']}
 projected=project_identity('init',sample,sample)
 passed('exact_identity_numeric_projection',projected['exact_old_identity_match'] is True and projected['host_pid']==42)
 passed('cmdline_and_cgroup_private','PRIVATE_SENTINEL' not in json.dumps(projected))
 passed('complete_init_equality_required',same_old_init(dict(sample),sample))
 passed('same_pid_changed_birth_denied',not same_old_init(dict(sample,start_ticks=101),sample))
 passed('same_pid_changed_private_cmdline_denied',not same_old_init(dict(sample,cmdline=['/init','changed']),sample))
 passed('closed_difference_field',difference_fields(sample,dict(sample,start_ticks=101))==['start_ticks'])
 hidden=project_identity('init',dict(sample,executable='/PRIVATE_SENTINEL_EXECUTABLE'),sample)
 passed('unknown_executable_hash_only','PRIVATE_SENTINEL' not in json.dumps(hidden) and hidden['executable']['known_role_executable'] is None)
 rejected('malformed_namespace_not_exported',lambda:project_identity('init',dict(sample,namespaces={'pid':'PRIVATE_SENTINEL','mnt':'mnt:[200]'})))
 try:
  try:raise FileNotFoundError(2,'PRIVATE_SENTINEL_ERROR')
  except FileNotFoundError as cause:raise RuntimeError('PROCESS_IDENTITY_UNAVAILABLE') from cause
 except RuntimeError as error:
  error.code='PROCESS_IDENTITY_UNAVAILABLE';public=safe_error(error)
 passed('closed_error_and_errno_without_raw',public['code']=='PROCESS_IDENTITY_UNAVAILABLE' and public['cause_errno']==2 and 'PRIVATE_SENTINEL' not in json.dumps(public))
 passed('unknown_error_text_hidden','PRIVATE_SENTINEL' not in json.dumps(safe_error(RuntimeError('PRIVATE_SENTINEL_ERROR'))))
 need(len(rows)==10,'CONTROL_COUNT');return rows

def read_proc_leaf(directory,name,limit):
 check_time();fd=opened(os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory))
 try:
  raw=b''
  while True:
   check_time();piece=os.read(fd,min(4096,limit+1-len(raw)))
   if not piece:break
   raw+=piece;need(len(raw)<=limit,'PROC_LEAF_BOUND')
  return raw
 finally:close(fd)
def read_boot():
 raw=read_proc_leaf(None,'/proc/sys/kernel/random/boot_id',128)
 text=raw.decode('ascii','strict')
 need(re.fullmatch('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\n',text) is not None,'CURRENT_BOOT_UNVERIFIED')
 return text[:-1]
def parse_pid_words(raw,limit,code):
 need(type(raw) is bytes and len(raw)<=16384,code)
 text=raw.decode('ascii','strict')
 need(all(c in '0123456789 \t\n' for c in text),code)
 values=text.split()
 need(len(values)<=limit,code)
 need(all(re.fullmatch('[1-9][0-9]{0,9}',word) and int(word)<=2147483647 for word in values),code)
 result=[int(word) for word in values]
 need(len(set(result))==len(result),'DIRECT_CHILDREN_DUPLICATE')
 return sorted(result)
def join_children(per_thread):
 need(type(per_thread) is dict and 0<len(per_thread)<=MAX_THREADS,'THREAD_LIST_BOUND')
 values=[]
 for tid,children in per_thread.items():
  need(type(tid) is int and 0<tid<=2147483647 and type(children) is list,'THREAD_LIST_SCHEMA')
  values+=children
 need(len(values)<=MAX_CHILDREN,'DIRECT_CHILDREN_BOUND')
 need(len(set(values))==len(values),'DIRECT_CHILDREN_DUPLICATE')
 return sorted(values)
def children_sample(proc,parent_pid):
 task=opened(os.open('task',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=proc))
 try:
  names=os.listdir(task)
  need(0<len(names)<=MAX_THREADS and all(re.fullmatch('[1-9][0-9]{0,9}',name) and int(name)<=2147483647 for name in names),
   'THREAD_LIST_BOUND')
  tids=sorted(int(name) for name in names)
  need(len(set(tids))==len(tids) and parent_pid in tids,'THREAD_LIST_SCHEMA')
  rows={}
  for tid in tids:
   check_time();thread=opened(os.open(str(tid),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=task))
   try:rows[tid]=parse_pid_words(read_proc_leaf(thread,'children',16384),MAX_CHILDREN,'DIRECT_CHILDREN_SCHEMA')
   finally:close(thread)
  after=os.listdir(task)
  need(sorted(after)==sorted(names),'DIRECT_CHILDREN_SAMPLE_CHANGED')
  all_children=join_children(rows)
  return {'thread_ids':tids,'per_thread':rows,'child_host_pids':all_children}
 finally:close(task)
def require_pidfd_live(fd):
 import select
 poll=select.poll();poll.register(fd,select.POLLIN|select.POLLHUP|select.POLLERR)
 need(not poll.poll(0),'DAEMON_PIDFD_NOT_LIVE')
def qualify_children(first,last,before,after,daemon):
 need(first==last,'DIRECT_CHILDREN_SAMPLE_CHANGED')
 children=first['child_host_pids']
 need(set(before)==set(after)==set(children),'DIRECT_CHILDREN_SAMPLE_CHANGED')
 for pid in children:
  identity_shape(before[pid]);identity_shape(after[pid])
  need(before[pid]==after[pid],'DIRECT_CHILD_IDENTITY_CHANGED')
  need(before[pid]['host_pid']==pid and before[pid]['parent_host_pid']==daemon['host_pid'],'DIRECT_CHILD_PARENT_DIFFERS')
 return True
def host_owner_controls():
 rows=controls()
 def passed(name,condition):
  need(condition,'CONTROL_COUNT');rows.append({'name':name,'passed':True})
 def rejected(name,call,code):
  try:call()
  except RuntimeError as error:
   need(str(error)==code,'CONTROL_COUNT');passed(name,True);return
  raise RuntimeError('CONTROL_COUNT')
 passed('empty_children_are_complete_empty_observation',parse_pid_words(b'',MAX_CHILDREN,'DIRECT_CHILDREN_SCHEMA')==[])
 passed('kernel_numeric_child_list_parsed',parse_pid_words(b'42 51 \n',MAX_CHILDREN,'DIRECT_CHILDREN_SCHEMA')==[42,51])
 rejected('non_numeric_child_token_rejected',lambda:parse_pid_words(b'42 private',MAX_CHILDREN,'DIRECT_CHILDREN_SCHEMA'),'DIRECT_CHILDREN_SCHEMA')
 rejected('child_duplicate_rejected',lambda:join_children({10:[42],11:[42]}),'DIRECT_CHILDREN_DUPLICATE')
 rejected('child_count_bound_rejected',lambda:parse_pid_words((' '.join(str(i) for i in range(1,34))).encode(),MAX_CHILDREN,'DIRECT_CHILDREN_SCHEMA'),'DIRECT_CHILDREN_SCHEMA')
 sample={'host_pid':42,'parent_host_pid':10,'start_ticks':100,'namespace_pids':[42],'uids':[0,0,0,0],
  'cmdline':['PRIVATE_SENTINEL_CHILD'],'executable':'/PRIVATE_SENTINEL_CHILD',
  'namespaces':{'pid':'pid:[100]','mnt':'mnt:[200]'},'cgroup':['0::/system.slice/droidloomd.service']}
 table={'thread_ids':[10],'per_thread':{10:[42]},'child_host_pids':[42]}
 passed('two_equal_samples_and_exact_parent_qualify_topology_only',qualify_children(table,dict(table),{42:sample},{42:dict(sample)},{'host_pid':10}))
 rejected('foreign_parent_rejected',lambda:qualify_children(table,table,{42:sample},{42:sample},{'host_pid':11}),'DIRECT_CHILD_PARENT_DIFFERS')
 rejected('changed_child_birth_rejected',lambda:qualify_children(table,table,{42:sample},{42:dict(sample,start_ticks=101)},{'host_pid':10}),'DIRECT_CHILD_IDENTITY_CHANGED')
 rejected('changed_thread_child_sample_rejected',lambda:qualify_children(table,dict(table,child_host_pids=[]),{42:sample},{42:sample},{'host_pid':10}),'DIRECT_CHILDREN_SAMPLE_CHANGED')
 child=project_identity('unknown_child',sample)
 passed('unknown_child_private_fields_hash_only','PRIVATE_SENTINEL' not in json.dumps(child))
 need(len(rows)==20,'CONTROL_COUNT');return rows


HISTORICAL_STATUS01_FAILURE={'job_id':'1a1b10b5f79-fc05-754f','git_tree':'5b0623b496dd210ed256842cc648dc1f40281601',
 'stdout':{'bytes':4812,'sha256':'1910e877b4353d810571ae1e6b074e04fda65771ace73967c7bf52db0ab2a0e3'},
 'git_blob_sha':'de625c54aa4a1aeef383c309fcd0a7f55197814a','phase':'fixed_daemon_and_owner_before',
 'process_role_unresolved':True,'send_attempted':False,'old_owner_pid_not_reused_as_authority':True}
CONTROL_OWNER_PID=42
MAX_OWNER_LINKS=3
SOCKET_PATH='/run/droidloom/control.sock'
STATUS_REQUEST=b'{"command":"status"}'

def proc_metadata(fd):
 value=os.fstat(fd)
 return {key:getattr(value,key) for key in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')}
def hold_binary(proc,expected,held):
 need(type(expected) is dict and set(expected)=={'bytes','sha256','file'} and
  type(expected['bytes']) is int and 0<expected['bytes']<=128*1024*1024 and
  re.fullmatch('[0-9a-f]{64}',expected['sha256']) is not None,'EXECUTABLE_PIN_SCHEMA')
 fd=opened(os.open('exe',os.O_RDONLY|os.O_CLOEXEC,dir_fd=proc));held.append(fd)
 before=proc_metadata(fd)
 need(stat.S_ISREG(before['st_mode']) and before==expected['file'] and before['st_size']==expected['bytes'],
  'EXECUTABLE_BACKING_CHANGED')
 digest=hashlib.sha256();count=0
 while True:
  check_time();chunk=os.read(fd,min(131072,expected['bytes']+1-count))
  if not chunk:break
  count+=len(chunk);need(count<=expected['bytes'],'EXECUTABLE_BYTES_CHANGED');digest.update(chunk)
 need(count==expected['bytes'] and digest.hexdigest()==expected['sha256'] and proc_metadata(fd)==before,
  'EXECUTABLE_BYTES_CHANGED')
 return {'held_fd':fd,'proc_fd':proc,'expected':expected,
  'public':{'bytes':count,'sha256':digest.hexdigest(),'historical_backing_metadata_equal':True}}
def verify_binary(record):
 need(proc_metadata(record['held_fd'])==record['expected']['file'],'EXECUTABLE_BACKING_CHANGED')
 again=opened(os.open('exe',os.O_RDONLY|os.O_CLOEXEC,dir_fd=record['proc_fd']))
 try:need(proc_metadata(again)==record['expected']['file'],'EXECUTABLE_BACKING_CHANGED')
 finally:close(again)
def require_owner(value,expected_old_launcher,reported_pid,daemon):
 identity_shape(value);identity_shape(daemon);identity_shape(expected_old_launcher)
 need(type(reported_pid) is int and value['host_pid']==reported_pid and
  value['start_ticks']>=daemon['start_ticks'],'OWNER_GENERATION_CHANGED')
 need(value['parent_host_pid']==daemon['host_pid']==PIDS['daemon'],'OWNER_PARENT_CHANGED')
 need(value['uids']==expected_old_launcher['uids']==[0,0,0,0] and
  value['namespace_pids']==[reported_pid] and value['namespaces']['pid']==daemon['namespaces']['pid'] and
  value['cgroup']==expected_old_launcher['cgroup'] and
  value['executable']==expected_old_launcher['executable'] and value['cmdline']==expected_old_launcher['cmdline'],
  'OWNER_PROGRAM_CHANGED')
 return True
def require_peer(peer):
 need(type(peer) is dict and set(peer)=={'pid','uid','gid'} and
  peer['pid']==PIDS['daemon'] and peer['uid']==0 and type(peer['gid']) is int and 0<=peer['gid']<2**32,
  'STATUS_PEER_MISMATCH')
 return True
def parse_status(raw):
 need(type(raw) is bytes and 0<len(raw)<=65536,'STATUS_RESPONSE_BOUND')
 value=strict_json(raw)
 need(type(value) is dict and {'ok','state','message'}<=set(value),'STATUS_RESPONSE_SCHEMA')
 optional={'host_pid','launch','applications','application_icon','diagnostics'}
 need(set(value)<={'ok','state','message'}|optional,'STATUS_UNKNOWN_FIELD')
 need(type(value['ok']) is bool and value['state'] in ('running','stopped') and
  type(value['message']) is str and len(value['message'].encode())<=32768,'STATUS_RESPONSE_SCHEMA')
 need(all(value.get(key) is None for key in optional-{'host_pid'}),'STATUS_RESPONSE_SCHEMA')
 pid=value.get('host_pid')
 need(pid is None or (type(pid) is int and 0<pid<=2147483647),'STATUS_RESPONSE_SCHEMA')
 need((value['state']=='running' and pid is not None) or (value['state']=='stopped' and pid is None),
  'STATUS_RESPONSE_SCHEMA')
 return value
def project_status(value,raw,expected_owner_pid):
 text=value['message']
 known=text if text in ('cell is stopped','Droidloom is stopped') else None
 return {'ok':value['ok'],'state':value['state'],'host_pid':value.get('host_pid'),
  'message':{'utf8_bytes':len(text.encode()),'sha256':sha(text.encode()),'known_constant':known,'raw_exported':False},
  'response_bytes':len(raw),'response_sha256':sha(raw),'raw_response_exported':False,
  'reported_running_owner_equals_supplied_kernel_candidate':value['ok'] is True and
   value['state']=='running' and type(expected_owner_pid) is int and value.get('host_pid')==expected_owner_pid}
def close_received_fds(ids,admit=opened,retire=close):
 tracked=[admit(fd) for fd in ids];first=None
 for fd in tracked:
  try:retire(fd)
  except BaseException as error:
   if first is None:first=error
 if first is not None:raise first
def status_controls():
 rows=host_owner_controls()
 def passed(name,condition):
  need(condition,'CONTROL_COUNT');rows.append({'name':name,'passed':True})
 def rejected(name,call,code=None):
  try:call()
  except RuntimeError as error:
   need(code is None or str(error)==code,'CONTROL_COUNT');passed(name,True);return
  raise RuntimeError('CONTROL_COUNT')
 valid={'ok':True,'state':'running','message':'PRIVATE_SENTINEL_STATUS','host_pid':CONTROL_OWNER_PID}
 raw=canon(valid);value=parse_status(raw);public=project_status(value,raw,CONTROL_OWNER_PID)
 passed('running_reply_matches_only_fixed_owner',public['reported_running_owner_equals_supplied_kernel_candidate'] is True)
 passed('status_message_and_raw_response_hidden','PRIVATE_SENTINEL' not in json.dumps(public))
 stopped=parse_status(canon({'ok':True,'state':'stopped','message':'cell is stopped'}))
 passed('stopped_reply_reports_no_owner',project_status(stopped,canon(stopped),None)['host_pid'] is None)
 foreign=parse_status(canon(dict(valid,host_pid=43)))
 passed('foreign_reply_pid_does_not_bind_current_owner',project_status(foreign,canon(foreign),CONTROL_OWNER_PID)['reported_running_owner_equals_supplied_kernel_candidate'] is False)
 rejected('boolean_reply_pid_rejected',lambda:parse_status(canon(dict(valid,host_pid=True))),'STATUS_RESPONSE_SCHEMA')
 rejected('unknown_reply_state_rejected',lambda:parse_status(canon(dict(valid,state='unknown'))),'STATUS_RESPONSE_SCHEMA')
 rejected('unexpected_response_key_rejected',lambda:parse_status(canon(dict(valid,extra=1))),'STATUS_UNKNOWN_FIELD')
 rejected('diagnostic_payload_not_exported',lambda:parse_status(canon(dict(valid,diagnostics='PRIVATE_SENTINEL'))),'STATUS_RESPONSE_SCHEMA')
 passed('exact_root_daemon_peer_qualified',require_peer({'pid':PIDS['daemon'],'uid':0,'gid':0}))
 rejected('foreign_socket_peer_rejected',lambda:require_peer({'pid':43,'uid':0,'gid':0}),'STATUS_PEER_MISMATCH')
 rejected('duplicate_response_key_rejected',lambda:parse_status(b'{"ok":true,"ok":false,"state":"stopped","message":"cell is stopped"}'))
 events=[]
 close_received_fds([10,11],lambda fd:(events.append(('admit',fd)) or fd),lambda fd:events.append(('close',fd)))
 passed('all_received_fds_registered_before_closing',events==[('admit',10),('admit',11),('close',10),('close',11)])
 events=[];original=RuntimeError('first-close-error');caught=None
 def failing_close(fd):
  events.append(('close',fd))
  if fd in (10,11):raise original if fd==10 else RuntimeError('secondary-close-error')
 try:close_received_fds([10,11,12],lambda fd:(events.append(('admit',fd)) or fd),failing_close)
 except RuntimeError as error:caught=error
 passed('received_fd_close_failure_preserves_first_and_attempts_remaining',caught is original and
  events==[('admit',10),('admit',11),('admit',12),('close',10),('close',11),('close',12)])
 need(len(rows)==33,'CONTROL_COUNT');return rows
def close_received_rights(ancillary):
 import array,socket
 received=[]
 for level,kind,data in ancillary:
  if level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS:
   ids=array.array('i')
   ids.frombytes(data[:len(data)-(len(data)%ids.itemsize)]);received.extend(ids)
 close_received_fds(received)
 return bool(ancillary)
def receive_status(sock):
 import socket
 chunks=[];length=0
 while True:
  check_time();sock.settimeout(max(.001,min(12,25-(time.monotonic()-START))))
  chunk,ancillary,flags,_=sock.recvmsg(min(8192,65537-length),socket.CMSG_SPACE(256),socket.MSG_CMSG_CLOEXEC)
  unexpected=close_received_rights(ancillary)
  need(not unexpected and not(flags&(socket.MSG_TRUNC|socket.MSG_CTRUNC)),'STATUS_ANCILLARY_OR_TRUNCATION')
  if not chunk:break
  chunks.append(chunk);length+=len(chunk);need(length<=65536,'STATUS_RESPONSE_BOUND')
 return b''.join(chunks)


FIXED_CODES.update(['CURRENT_DAEMON_REPORTS_NO_RUNNING_OWNER','UNIQUE_DIRECT_CHILD_REQUIRED',
 'OWNER_CHILD_CYCLE','OWNER_CHAIN_BOUND','CHILD_PARENT_MISMATCH','INTERMEDIARY_IDENTITY_REQUIRED',
 'INIT_NAMESPACE_PID_ONE_REQUIRED','INIT_IDENTITY_REQUIRED','INIT_CGROUP_REQUIRED','INIT_CHANGED',
 'INIT_EXECUTABLE_BYTES_CHANGED','INIT_EXECUTABLE_BACKING_CHANGED','CURRENT_INIT_ROOT_CHANGED',
 'FRAMEWORK_INIT_DIFFERS','CURRENT_FRAMEWORK_BINDING_INVALID','PRESENTER_CHANGED',
 'MAIN_LIMITS_SCHEMA','MAIN_LIMITS_CHANGED','MAIN_EVENT_SCHEMA','MAIN_OOM_COUNTER_NOT_ZERO',
 'MAIN_PIDS_MAX_EVENT_OBSERVED','INVALID_CHILD_TABLE'])
LIMITS={'cpu.max':'200000 100000','memory.high':'5368709120','memory.max':'6442450944',
 'memory.swap.max':'max','pids.max':'12288'}
CG='/sys/fs/cgroup/system.slice/droidloomd.service'
def running_owner_pid(value):
 need(value.get('ok') is True and value.get('state')=='running' and
  type(value.get('host_pid')) is int and 0<value['host_pid']<=2147483647,
  'CURRENT_DAEMON_REPORTS_NO_RUNNING_OWNER')
 return value['host_pid']
def unique_direct_child(table,parent_pid):
 need(type(table) is dict and parent_pid in table.get('thread_ids',[]) and
  type(table.get('child_host_pids')) is list,'INVALID_CHILD_TABLE')
 children=table['child_host_pids']
 need(len(children)==1 and type(children[0]) is int and 0<children[0]<=2147483647,
  'UNIQUE_DIRECT_CHILD_REQUIRED')
 return children[0]
def require_child_relation(value,pid,parent):
 identity_shape(value);identity_shape(parent)
 need(value['host_pid']==pid and value['parent_host_pid']==parent['host_pid'] and
  value['start_ticks']>=parent['start_ticks'],'CHILD_PARENT_MISMATCH')
 expected_groups=[x for x in parent['cgroup'] if x.startswith('0::')]
 observed_groups=[x for x in value['cgroup'] if x.startswith('0::')]
 need(len(expected_groups)==len(observed_groups)==1 and
  (observed_groups[0]==expected_groups[0] or observed_groups[0].startswith(expected_groups[0]+'/')) and
  (observed_groups[0]=='0::/system.slice/droidloomd.service' or
   observed_groups[0].startswith('0::/system.slice/droidloomd.service/')),'INIT_CGROUP_REQUIRED')
 return True
def classify_child(value,pid,parent,old_init):
 require_child_relation(value,pid,parent);identity_shape(old_init)
 if value['namespace_pids']==[pid,1]:
  need(value['namespaces']['pid']!=parent['namespaces']['pid'],'INIT_NAMESPACE_PID_ONE_REQUIRED')
  need(value['uids']==[0,0,0,0] and value['cmdline']==old_init['cmdline'] and
   value['executable']==old_init['executable']=='/system/bin/init','INIT_IDENTITY_REQUIRED')
  return 'init'
 need(value['uids']==[0,0,0,0] and value['namespace_pids']==[pid] and
  value['namespaces']['pid']==parent['namespaces']['pid'],'INTERMEDIARY_IDENTITY_REQUIRED')
 return 'host_intermediary'
def admit_chain_node(pid,seen,link_index):
 need(type(link_index) is int and 1<=link_index<=MAX_OWNER_LINKS,'OWNER_CHAIN_BOUND')
 need(pid not in seen,'OWNER_CHILD_CYCLE')
 return True
def hold_init_executable(proc,expected,held):
 need(type(expected) is dict and set(expected)=={'bytes','sha256','file'} and
  type(expected['bytes']) is int and 0<expected['bytes']<=128*1024*1024 and
  type(expected['sha256']) is str and re.fullmatch('[0-9a-f]{64}',expected['sha256']),
  'INIT_EXECUTABLE_BYTES_CHANGED')
 fd=opened(os.open('exe',os.O_RDONLY|os.O_CLOEXEC,dir_fd=proc));held.append(fd);first=proc_metadata(fd)
 need(stat.S_ISREG(first['st_mode']) and first['st_size']==expected['bytes'],'INIT_EXECUTABLE_BYTES_CHANGED')
 digest=hashlib.sha256();count=0
 while True:
  check_time();block=os.read(fd,min(131072,expected['bytes']+1-count))
  if not block:break
  count+=len(block);need(count<=expected['bytes'],'INIT_EXECUTABLE_BYTES_CHANGED');digest.update(block)
 need(count==expected['bytes'] and digest.hexdigest()==expected['sha256'] and proc_metadata(fd)==first,
  'INIT_EXECUTABLE_BYTES_CHANGED')
 return {'held_fd':fd,'proc_fd':proc,'metadata':first,
  'public':{'bytes':count,'sha256':digest.hexdigest(),'content_equals_historical_init':True,
   'backing_metadata_equals_historical_init':first==expected['file'],'current_backing':first}}
def verify_init_executable(record):
 again=opened(os.open('exe',os.O_RDONLY|os.O_CLOEXEC,dir_fd=record['proc_fd']))
 try:need(proc_metadata(again)==proc_metadata(record['held_fd'])==record['metadata'],'INIT_EXECUTABLE_BACKING_CHANGED')
 finally:close(again)
def parse_events(raw,required):
 need(type(raw) is bytes and 0<len(raw)<=8192,'MAIN_EVENT_SCHEMA')
 fields={}
 for line in raw.decode('ascii','strict').splitlines():
  words=line.split()
  need(len(words)==2 and re.fullmatch('[a-z_]{1,64}',words[0]) and
   re.fullmatch('[0-9]{1,20}',words[1]) and words[0] not in fields,'MAIN_EVENT_SCHEMA')
  fields[words[0]]=int(words[1])
 need(set(required)<=set(fields),'MAIN_EVENT_SCHEMA')
 return {k:fields[k] for k in required}
def main_resources(baseline):
 need(baseline.get('limits')==LIMITS,'MAIN_LIMITS_SCHEMA')
 limits={name:read_proc_leaf(None,CG+'/'+name,8192).decode('ascii','strict').strip() for name in LIMITS}
 need(limits==LIMITS,'MAIN_LIMITS_CHANGED')
 result={'limits':limits}
 for name in ('memory.events','memory.events.local'):
  fields=parse_events(read_proc_leaf(None,CG+'/'+name,8192),('oom','oom_kill','oom_group_kill'))
  need(all(value==0 for value in fields.values()),'MAIN_OOM_COUNTER_NOT_ZERO');result[name]=fields
 fields=parse_events(read_proc_leaf(None,CG+'/pids.events',8192),('max',))
 need(fields['max']==0,'MAIN_PIDS_MAX_EVENT_OBSERVED');result['pids.events']=fields
 return result
def require_framework(snapshot,init,boot,module):
 need(type(snapshot) is dict and snapshot.get('schema')==module.SCHEMA and
  snapshot.get('sha256')==module._digest(snapshot['binding']),'CURRENT_FRAMEWORK_BINDING_INVALID')
 value=snapshot['binding'];processes=value.get('processes')
 need(value.get('boot_id')==boot and type(processes) is dict and
  set(processes)=={'init','zygote64','system_server','surfaceflinger'} and processes['init']==init,
  'FRAMEWORK_INIT_DIFFERS')
 for item in processes.values():identity_shape(item)
 return True

def live_chain_controls():
 rows=status_controls()
 def passed(name,condition):
  need(condition,'CONTROL_COUNT');rows.append({'name':name,'passed':True})
 def rejected(name,call,code):
  try:call()
  except RuntimeError as error:
   need(str(error)==code,'CONTROL_COUNT');passed(name,True);return
  raise RuntimeError('CONTROL_COUNT')
 daemon={'host_pid':PIDS['daemon'],'parent_host_pid':1,'start_ticks':100,'namespace_pids':[PIDS['daemon']],
  'uids':[0]*4,'cmdline':['PRIVATE_SENTINEL_DAEMON'],'executable':'/PRIVATE_SENTINEL_DAEMON',
  'namespaces':{'pid':'pid:[100]','mnt':'mnt:[200]'},'cgroup':['0::/system.slice/droidloomd.service']}
 owner=dict(daemon,host_pid=42,parent_host_pid=PIDS['daemon'],start_ticks=101,namespace_pids=[42],
  cmdline=['PRIVATE_SENTINEL_OWNER'],executable='/PRIVATE_SENTINEL_OWNER')
 old=dict(owner,host_pid=PIDS['launcher'],start_ticks=100,namespace_pids=[PIDS['launcher']])
 init={'host_pid':43,'parent_host_pid':42,'start_ticks':102,'namespace_pids':[43,1],'uids':[0]*4,
  'cmdline':['/init','second_stage'],'executable':'/system/bin/init',
  'namespaces':{'pid':'pid:[101]','mnt':'mnt:[201]'},'cgroup':['0::/system.slice/droidloomd.service']}
 intermediate=dict(owner,host_pid=44,parent_host_pid=42,start_ticks=102,namespace_pids=[44])
 passed('successful_current_reply_supplies_candidate_pid',running_owner_pid({'ok':True,'state':'running','host_pid':42})==42)
 rejected('stopped_reply_does_not_start_owner_discovery',lambda:running_owner_pid({'ok':True,'state':'stopped','host_pid':None}),'CURRENT_DAEMON_REPORTS_NO_RUNNING_OWNER')
 rejected('failed_reply_does_not_start_owner_discovery',lambda:running_owner_pid({'ok':False,'state':'running','host_pid':42}),'CURRENT_DAEMON_REPORTS_NO_RUNNING_OWNER')
 passed('reply_owner_requires_original_program_and_exact_daemon_parent',require_owner(owner,old,42,daemon))
 rejected('different_reported_owner_pid_rejected',lambda:require_owner(owner,old,43,daemon),'OWNER_GENERATION_CHANGED')
 rejected('reply_owner_foreign_parent_rejected',lambda:require_owner(dict(owner,parent_host_pid=99),old,42,daemon),'OWNER_PARENT_CHANGED')
 passed('one_kernel_direct_child_is_candidate',unique_direct_child({'thread_ids':[42],'child_host_pids':[43]},42)==43)
 rejected('empty_kernel_child_table_not_adopted',lambda:unique_direct_child({'thread_ids':[42],'child_host_pids':[]},42),'UNIQUE_DIRECT_CHILD_REQUIRED')
 rejected('multiple_kernel_children_not_adopted',lambda:unique_direct_child({'thread_ids':[42],'child_host_pids':[43,44]},42),'UNIQUE_DIRECT_CHILD_REQUIRED')
 passed('exact_new_pid1_init_role_qualified',classify_child(init,43,owner,init)=='init')
 passed('host_intermediary_remains_relationship_only',classify_child(intermediate,44,owner,init)=='host_intermediary')
 rejected('foreign_child_parent_rejected',lambda:classify_child(dict(init,parent_host_pid=99),43,owner,init),'CHILD_PARENT_MISMATCH')
 rejected('nonroot_init_candidate_rejected',lambda:classify_child(dict(init,uids=[1000]*4),43,owner,init),'INIT_IDENTITY_REQUIRED')
 rejected('non_pid1_child_namespace_not_followed',lambda:classify_child(dict(init,namespace_pids=[43,2]),43,owner,init),'INTERMEDIARY_IDENTITY_REQUIRED')
 rejected('wrong_pid1_executable_not_adopted',lambda:classify_child(dict(init,executable='/PRIVATE_SENTINEL_EXEC'),43,owner,init),'INIT_IDENTITY_REQUIRED')
 rejected('kernel_chain_cycle_rejected',lambda:admit_chain_node(42,{42},1),'OWNER_CHILD_CYCLE')
 rejected('fourth_owner_link_rejected',lambda:admit_chain_node(46,{42,43,44,45},4),'OWNER_CHAIN_BOUND')
 passed('third_owner_link_is_last_allowed_observation',admit_chain_node(45,{42,43,44},3))
 passed('closed_resource_event_values_projected',parse_events(b'oom 0\noom_kill 0\noom_group_kill 0\n',('oom','oom_kill','oom_group_kill'))=={'oom':0,'oom_kill':0,'oom_group_kill':0})
 rejected('missing_resource_counter_rejected',lambda:parse_events(b'oom 0\n',('oom','oom_kill')),'MAIN_EVENT_SCHEMA')
 need(len(rows)==53,'CONTROL_COUNT');return rows

def main():
 import socket,struct
 out={'schema':'pocket4-live-daemon-status-owner-init-diagnosis-v2','ok':False,'source_sha256':SOURCE_SHA256,
  'old_baseline':{'path':str(BASELINE),**BASELINE_PIN},'original_epoch_source':{'path':str(EPOCH_SOURCE),**EPOCH_PIN},
  'historical_status01_failure':HISTORICAL_STATUS01_FAILURE,'controls':[],'errors':[],'phase':'source_and_inputs',
  'read_budget_seconds':25,'self_watchdog_seconds':25,'maximum_owner_links':MAX_OWNER_LINKS,
  'client_child_processes':0,'client_Android_commands':0,'requested_mutations':0,'client_filesystem_writes':0,
  'UI_actions':0,'signals_to_other_processes':0,'original_epoch_module_modified':False,
  'status_request':{'command':'status','bytes':len(STATUS_REQUEST),'sha256':sha(STATUS_REQUEST),
   'send_attempted':False,'sent_complete':False,'response_complete':False,'automatic_retry':False},
  'server_read_behavior':{'reference_status_may_spawn_ip_netns_pids':True,
   'reference_status_may_spawn_nsenter_getprop':True,'server_child_count_independently_observed':False,
   'server_Android_read_count_independently_observed':False,'server_side_mutating_command_requested':False,
   'reference_poll_may_reap_exited_owner_and_teardown_existing_resources':True,
   'server_internal_side_effects_independently_counted':False},
  'raw_baseline_or_cmdline_or_cgroup_exported':False,'raw_status_message_exported':False,
  'candidate_owner_source':'one_authenticated_current_daemon_Status_reply',
  'old_observed_owner_pid_not_reused_as_current_authority':True,'kernel_chain':[],
  'arbitrary_init_pid_scan':False,'original_capture_android_may_enumerate_proc_only_after_init_chain':True,
  'capture_android_attempted':False,'new_init_discovered':False,'current_framework_observation_qualified':False,
  'new_baseline_created':False,'new_baseline_qualified':False,'rebind_authorized':False,
  'old_task_cleanup_authorized':False,'old_helpers_or_flows_reauthorized':False,
  'installed_Main_source_version_verified':False,'framework_exit_cause_resolved':False,'production_ready':False}
 held=[];sock=None;protocol_complete=False
 try:
  need(os.getuid()==os.geteuid()==0,'ROOT_READ_ONLY_REQUIRED')
  out['controls']=live_chain_controls();check_time()
  b=strict_json(read_fixed(BASELINE,BASELINE_PIN));epoch_raw=read_fixed(EPOCH_SOURCE,EPOCH_PIN)
  module=types.ModuleType('fixed_original_epoch_live_status_owner');module.__file__=str(EPOCH_SOURCE)
  exec(compile(epoch_raw,module.__file__,'exec'),module.__dict__)
  need(b.get('schema')=='pocket4-main-current-baseline-v1' and
   b['framework_epoch']['schema']==module.SCHEMA and b['framework_epoch']['sha256']==OLD_EPOCH and
   module._digest(b['framework_epoch']['binding'])==OLD_EPOCH,'PRIVATE_BASELINE_SCHEMA')
  expected_daemon=identity_shape(b['daemon_process']);old_launcher=identity_shape(b['launcher_process'])
  expected_presenter=identity_shape(b['presenter_process'])
  old_init=identity_shape(b['framework_epoch']['binding']['processes']['init'])
  seven=b['all_seven_processes']
  need(seven['schema']==module.SCHEMA and seven['sha256']==module._digest(seven['binding']) and
   seven['binding']['boot_id']==b['framework_epoch']['binding']['boot_id'] and
   expected_daemon['host_pid']==PIDS['daemon'] and old_launcher['host_pid']==PIDS['launcher'] and
   expected_presenter['host_pid']==PIDS['presenter'] and
   seven['binding']['processes']['daemon']==expected_daemon and
   seven['binding']['processes']['launcher']==old_launcher and
   seven['binding']['processes']['presenter']==expected_presenter and
   seven['binding']['processes']['android_init']==old_init and
   b['status']=={'host_pid':PIDS['launcher']},'HOST_BASELINE_BINDINGS')
  boot=read_boot();need(boot==b['framework_epoch']['binding']['boot_id'],'CURRENT_BOOT_CHANGED')
  out['boot_id']=boot
  cell=b['cell_config']
  need(cell['path']=='/etc/droidloom/cell.json' and
   cell['sha256']=='f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc' and
   type(cell['bytes']) is int and 0<cell['bytes']<=131072,'FIXED_CELL_CONFIG')
  read_fixed(Path(cell['path']),{'bytes':cell['bytes'],'sha256':cell['sha256']})
  out['historical_cell_config_exact']=True
  out['phase']='fixed_original_daemon_before'
  pidfds={};procs={}
  fd=opened(os.pidfd_open(PIDS['daemon'],0));held.append(fd);pidfds[PIDS['daemon']]=fd;require_pidfd_live(fd)
  proc=opened(os.open('/proc/'+str(PIDS['daemon']),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC));held.append(proc);procs[PIDS['daemon']]=proc
  daemon=module.process_identity(PIDS['daemon']);need(daemon==expected_daemon,'DAEMON_CHANGED')
  daemon_binary=hold_binary(proc,b['current_process_executables']['daemon'],held)
  out['daemon_before']={'identity':project_identity('daemon',daemon,expected_daemon),'executable':daemon_binary['public']}
  out['phase']='fixed_status_socket'
  socket_path_fd=opened(os.open(SOCKET_PATH,os.O_PATH|os.O_NOFOLLOW|os.O_CLOEXEC));held.append(socket_path_fd)
  path_before=proc_metadata(socket_path_fd)
  need(stat.S_ISSOCK(path_before['st_mode']) and path_before['st_uid']==0 and path_before['st_nlink']==1,'STATUS_SOCKET_SHAPE')
  sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM|socket.SOCK_CLOEXEC);opened(sock.fileno())
  check_time();sock.settimeout(max(.001,min(12,25-(time.monotonic()-START))));sock.connect(SOCKET_PATH)
  peer_values=struct.unpack('3i',sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
  peer=dict(zip(('pid','uid','gid'),peer_values));require_peer(peer);out['socket_peer']=peer
  require_pidfd_live(pidfds[PIDS['daemon']]);need(module.process_identity(PIDS['daemon'])==expected_daemon,'DAEMON_CHANGED')
  out['phase']='one_status_request';check_time()
  out['status_request']['send_attempted']=True;sock.sendall(STATUS_REQUEST)
  out['status_request']['sent_complete']=True;sock.shutdown(socket.SHUT_WR)
  raw=receive_status(sock);out['status_request']['response_complete']=True
  value=parse_status(raw);out['status']=project_status(value,raw,None)
  out['phase']='current_reply_owner_binding'
  owner_pid=running_owner_pid(value)
  need(owner_pid not in (PIDS['daemon'],PIDS['presenter']),'OWNER_GENERATION_CHANGED')
  daemon_table=children_sample(procs[PIDS['daemon']],PIDS['daemon'])
  need(daemon_table['child_host_pids']==[owner_pid],'DAEMON_CHILD_SET_CHANGED')
  fd=opened(os.pidfd_open(owner_pid,0));held.append(fd);pidfds[owner_pid]=fd;require_pidfd_live(fd)
  proc=opened(os.open('/proc/'+str(owner_pid),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC));held.append(proc);procs[owner_pid]=proc
  owner=module.process_identity(owner_pid);require_owner(owner,old_launcher,owner_pid,daemon)
  owner_binary=hold_binary(proc,b['current_process_executables']['launcher'],held)
  need(module.process_identity(owner_pid)==owner,'OWNER_GENERATION_CHANGED')
  need(module.process_identity(PIDS['daemon'])==expected_daemon,'DAEMON_CHANGED')
  need(children_sample(procs[PIDS['daemon']],PIDS['daemon'])==daemon_table,'DAEMON_CHILD_SET_CHANGED')
  require_pidfd_live(pidfds[owner_pid])
  out['status']=project_status(value,raw,owner_pid)
  out['current_owner']={'identity':project_identity('unknown_child',owner),'executable':owner_binary['public'],
   'daemon_kernel_table_sha256':sha(canon(daemon_table)),'only_direct_child_matches_current_reply':True}
  out['phase']='current_owner_bounded_init_chain'
  chain={owner_pid:owner};tables={};seen={PIDS['daemon'],PIDS['presenter'],owner_pid};parent_pid=owner_pid;init=None;init_pid=None
  for link in range(1,MAX_OWNER_LINKS+1):
   check_time();table=children_sample(procs[parent_pid],parent_pid);child_pid=unique_direct_child(table,parent_pid)
   admit_chain_node(child_pid,seen,link)
   fd=opened(os.pidfd_open(child_pid,0));held.append(fd);pidfds[child_pid]=fd;require_pidfd_live(fd)
   child_proc=opened(os.open('/proc/'+str(child_pid),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC));held.append(child_proc);procs[child_pid]=child_proc
   child=module.process_identity(child_pid);kind=classify_child(child,child_pid,chain[parent_pid],old_init)
   need(module.process_identity(parent_pid)==chain[parent_pid],'DIRECT_CHILD_IDENTITY_CHANGED')
   need(module.process_identity(child_pid)==child,'DIRECT_CHILD_IDENTITY_CHANGED')
   need(children_sample(procs[parent_pid],parent_pid)==table,'DIRECT_CHILDREN_SAMPLE_CHANGED')
   require_pidfd_live(pidfds[parent_pid]);require_pidfd_live(pidfds[child_pid])
   tables[parent_pid]=table;chain[child_pid]=child;seen.add(child_pid)
   out['kernel_chain'].append({'link':link,'parent_host_pid':parent_pid,'child_host_pid':child_pid,
    'classification':kind,'complete_child_table_sha256':sha(canon(table)),
    'two_child_tables_equal':True,'child_identity':project_identity('init' if kind=='init' else 'unknown_child',child),
    'intermediary_program_authority_assigned':False})
   if kind=='init':
    init=child;init_pid=child_pid;break
   parent_pid=child_pid
  need(init is not None,'OWNER_CHAIN_BOUND')
  out['phase']='current_init_artifact_and_resources'
  rootfd=opened(os.open('root',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC,dir_fd=procs[init_pid]));held.append(rootfd);root_before=proc_metadata(rootfd)
  init_artifact=hold_init_executable(procs[init_pid],b['current_process_executables']['android_init'],held)
  out['current_init']={'identity':project_identity('init',init),'current_root':root_before,
   'executable':init_artifact['public'],'current_root_is_new_observation_not_old_baseline_substitution':True}
  out['new_init_discovered']=True
  resource_before=main_resources(b);out['Main_resources_before']=resource_before
  out['phase']='fixed_presenter_before'
  fd=opened(os.pidfd_open(PIDS['presenter'],0));held.append(fd);pidfds[PIDS['presenter']]=fd;require_pidfd_live(fd)
  presenter=module.process_identity(PIDS['presenter']);need(presenter==expected_presenter,'PRESENTER_CHANGED')
  out['presenter']=project_identity('presenter',presenter,expected_presenter)
  out['phase']='original_capture_for_bound_init'
  check_time();out['capture_android_attempted']=True;snapshot=module.capture_android(init_pid)
  require_framework(snapshot,init,boot,module)
  out['framework_observation']={'schema':snapshot['schema'],'epoch_sha256':snapshot['sha256'],
   'boot_id':snapshot['binding']['boot_id'],
   'processes':{role:project_identity(role,item) for role,item in snapshot['binding']['processes'].items()},
   'raw_binding_exported':False}
  out['phase']='independent_final_identity'
  module.require_unchanged(snapshot)
  need(module.process_identity(PIDS['daemon'])==expected_daemon,'DAEMON_CHANGED')
  need(module.process_identity(PIDS['presenter'])==expected_presenter,'PRESENTER_CHANGED')
  for pid,identity in chain.items():need(module.process_identity(pid)==identity,'DIRECT_CHILD_IDENTITY_CHANGED')
  for pid,table in tables.items():need(children_sample(procs[pid],pid)==table,'DIRECT_CHILDREN_SAMPLE_CHANGED')
  need(children_sample(procs[PIDS['daemon']],PIDS['daemon'])==daemon_table,'DAEMON_CHILD_SET_CHANGED')
  for fd in pidfds.values():require_pidfd_live(fd)
  for binary in (daemon_binary,owner_binary):verify_binary(binary)
  verify_init_executable(init_artifact)
  root_again=opened(os.open('root',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC,dir_fd=procs[init_pid]))
  try:need(proc_metadata(root_again)==proc_metadata(rootfd)==root_before,'CURRENT_INIT_ROOT_CHANGED')
  finally:close(root_again)
  named=os.stat(SOCKET_PATH,follow_symlinks=False)
  need(proc_metadata(socket_path_fd)==path_before and {key:getattr(named,key) for key in path_before}==path_before,
   'STATUS_SOCKET_SHAPE')
  need(read_boot()==boot,'CURRENT_BOOT_CHANGED')
  read_fixed(Path(cell['path']),{'bytes':cell['bytes'],'sha256':cell['sha256']})
  resource_after=main_resources(b);need(resource_after==resource_before,'MAIN_LIMITS_CHANGED')
  out['Main_resources_after']=resource_after
  out['final']={'daemon_complete_identity_equal':True,'presenter_complete_identity_equal':True,
   'owner_and_all_chain_identities_equal':True,'all_retained_pidfds_live':True,
   'owner_chain_and_daemon_child_tables_unchanged':True,'daemon_and_owner_executables_held_and_named_unchanged':True,
   'init_executable_held_and_named_unchanged':True,'init_root_held_and_named_unchanged':True,
   'socket_held_and_named_unchanged':True,'original_four_role_epoch_unchanged':True,'boot_and_cell_config_equal':True,
   'Main_limits_and_required_error_counters_equal':True}
  out['current_framework_observation_qualified']=True
  check_time();out['phase']='complete';protocol_complete=True
 except BaseException as error:out['errors'].append({'phase':out['phase'],**safe_error(error)})
 finally:
  out['self_watchdog_disarmed']=STOP_WATCHDOG()
  if sock is not None:
   try:close(sock.detach())
   except BaseException as error:out['errors'].append({'phase':'client_socket_close',**safe_error(error)})
  for fd in reversed(held):
   try:close(fd)
   except BaseException as error:out['errors'].append({'phase':'held_FD_close',**safe_error(error)})
  out['tracked_FDs']={'acquired':FD_OPENED,'closed':FD_CLOSED,'close_error_count':len(FD_CLOSE_ERRORS)}
  out['original_epoch_internal_FDs_independently_counted']=False
  if FD_OPENED!=FD_CLOSED or FD_CLOSE_ERRORS:out['errors'].append({'code':'TRACKED_INPUT_FD_CLOSE_FAILED'})
 out['diagnostic_protocol_complete']=protocol_complete;out['ok']=bool(protocol_complete and not out['errors'])
 out['status_request']['read_completion_unknown']=out['status_request']['send_attempted'] and not out['status_request']['response_complete']
 out['elapsed_seconds']=time.monotonic()-START
 raw=(json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
 need(len(raw)<=98304,'OUTPUT_BOUND');print(raw.decode(),end='',flush=True)
 return 0 if out['ok'] else 1
