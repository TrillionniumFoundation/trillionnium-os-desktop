"""One pinned-daemon Status request; no lifecycle write or App action."""
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
 if time.monotonic()-START>=15:raise BudgetExpired()
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
def children_sample(proc):
 task=opened(os.open('task',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=proc))
 try:
  names=os.listdir(task)
  need(0<len(names)<=MAX_THREADS and all(re.fullmatch('[1-9][0-9]{0,9}',name) and int(name)<=2147483647 for name in names),
   'THREAD_LIST_BOUND')
  tids=sorted(int(name) for name in names)
  need(len(set(tids))==len(tids) and PIDS['daemon'] in tids,'THREAD_LIST_SCHEMA')
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


OWNER_ACTUAL=json.loads("{\"job_id\":\"1a1b0f64a74-fc05-7461\",\"git_tree\":\"c85e4a7cbf9a8e6a31a79e78f3fae305c97adb8b\",\"git_blob_sha\":\"7435fcf77357f9a7d7d6d5c6e45d85b53ad35692\",\"stdout\":{\"bytes\":9143,\"sha256\":\"73b17e4e3755cb681922463c784cab7ebacc76e14c23b7410b6d4c8d736f947c\"},\"source_sha256\":\"246e3c07125ce8227ec482310ab4fae3fcba68c390a210640bcd75ac15a61cbd\",\"host_pid\":2747275,\"start_ticks\":99050420,\"parent_host_pid\":3588022,\"identity_sha256\":\"3cfe9d4d411ecba738f07488604cd9a3a9a2585d10d9a1dbe9b6ac328cb59692\"}")
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
def require_owner(value,expected_old_launcher):
 identity_shape(value)
 need(value['host_pid']==OWNER_ACTUAL['host_pid'] and value['start_ticks']==OWNER_ACTUAL['start_ticks'] and
  sha(canon(value))==OWNER_ACTUAL['identity_sha256'],'OWNER_GENERATION_CHANGED')
 need(value['parent_host_pid']==PIDS['daemon'],'OWNER_PARENT_CHANGED')
 need(value['executable']==expected_old_launcher['executable'] and value['cmdline']==expected_old_launcher['cmdline'],
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
def project_status(value,raw):
 text=value['message']
 known=text if text in ('cell is stopped','Droidloom is stopped') else None
 return {'ok':value['ok'],'state':value['state'],'host_pid':value.get('host_pid'),
  'message':{'utf8_bytes':len(text.encode()),'sha256':sha(text.encode()),'known_constant':known,'raw_exported':False},
  'response_bytes':len(raw),'response_sha256':sha(raw),'raw_response_exported':False,
  'reported_running_owner_equals_fixed_kernel_candidate':value['ok'] is True and
   value['state']=='running' and value.get('host_pid')==OWNER_ACTUAL['host_pid']}
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
 valid={'ok':True,'state':'running','message':'PRIVATE_SENTINEL_STATUS','host_pid':OWNER_ACTUAL['host_pid']}
 raw=canon(valid);value=parse_status(raw);public=project_status(value,raw)
 passed('running_reply_matches_only_fixed_owner',public['reported_running_owner_equals_fixed_kernel_candidate'] is True)
 passed('status_message_and_raw_response_hidden','PRIVATE_SENTINEL' not in json.dumps(public))
 stopped=parse_status(canon({'ok':True,'state':'stopped','message':'cell is stopped'}))
 passed('stopped_reply_reports_no_owner',project_status(stopped,canon(stopped))['host_pid'] is None)
 foreign=parse_status(canon(dict(valid,host_pid=43)))
 passed('foreign_reply_pid_does_not_bind_current_owner',project_status(foreign,canon(foreign))['reported_running_owner_equals_fixed_kernel_candidate'] is False)
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
  check_time();sock.settimeout(max(.001,min(12,15-(time.monotonic()-START))))
  chunk,ancillary,flags,_=sock.recvmsg(min(8192,65537-length),socket.CMSG_SPACE(256),socket.MSG_CMSG_CLOEXEC)
  unexpected=close_received_rights(ancillary)
  need(not unexpected and not(flags&(socket.MSG_TRUNC|socket.MSG_CTRUNC)),'STATUS_ANCILLARY_OR_TRUNCATION')
  if not chunk:break
  chunks.append(chunk);length+=len(chunk);need(length<=65536,'STATUS_RESPONSE_BOUND')
 return b''.join(chunks)

def main():
 import socket,struct
 out={'schema':'pocket4-fixed-daemon-status-owner-diagnosis-v1','ok':False,'source_sha256':SOURCE_SHA256,
  'old_baseline':{'path':str(BASELINE),**BASELINE_PIN},'original_epoch_source':{'path':str(EPOCH_SOURCE),**EPOCH_PIN},
  'owner_actual':OWNER_ACTUAL,'controls':[],'errors':[],'phase':'source_and_inputs','read_budget_seconds':15,
  'self_watchdog_seconds':15,'client_child_processes':0,'client_Android_commands':0,'requested_mutations':0,
  'client_filesystem_writes':0,'UI_actions':0,'signals_to_other_processes':0,'original_epoch_module_modified':False,
  'status_request':{'command':'status','bytes':len(STATUS_REQUEST),'sha256':sha(STATUS_REQUEST),
   'send_attempted':False,'sent_complete':False,'response_complete':False,'automatic_retry':False},
  'server_read_behavior':{'reference_status_may_spawn_ip_netns_pids':True,
   'reference_status_may_spawn_nsenter_getprop':True,'server_child_count_independently_observed':False,
   'server_Android_read_count_independently_observed':False,'server_side_mutating_command_requested':False,
    'reference_poll_may_reap_exited_owner_and_teardown_existing_resources':True,
    'server_internal_side_effects_independently_counted':False},
  'raw_baseline_or_cmdline_or_cgroup_exported':False,'raw_status_message_exported':False,
  'current_framework_qualified':False,'new_init_discovered':False,'new_baseline_created':False,
  'rebind_authorized':False,'old_task_cleanup_authorized':False,'old_flows_reauthorized':False,
  'installed_Main_source_version_verified':False,'framework_exit_cause_resolved':False,'production_ready':False}
 held=[];sock=None;protocol_complete=False
 try:
  need(os.getuid()==os.geteuid()==0,'ROOT_READ_ONLY_REQUIRED')
  out['controls']=status_controls();check_time()
  b=strict_json(read_fixed(BASELINE,BASELINE_PIN));epoch_raw=read_fixed(EPOCH_SOURCE,EPOCH_PIN)
  module=types.ModuleType('fixed_original_epoch_status_owner');module.__file__=str(EPOCH_SOURCE)
  exec(compile(epoch_raw,module.__file__,'exec'),module.__dict__)
  need(b.get('schema')=='pocket4-main-current-baseline-v1' and
   b['framework_epoch']['schema']==module.SCHEMA and b['framework_epoch']['sha256']==OLD_EPOCH and
   module._digest(b['framework_epoch']['binding'])==OLD_EPOCH,'PRIVATE_BASELINE_SCHEMA')
  expected_daemon=identity_shape(b['daemon_process']);old_launcher=identity_shape(b['launcher_process'])
  need(expected_daemon['host_pid']==PIDS['daemon'] and old_launcher['host_pid']==PIDS['launcher'] and
   b['all_seven_processes']['binding']['processes']['daemon']==expected_daemon and
   b['all_seven_processes']['binding']['processes']['launcher']==old_launcher and
   b['status']=={'host_pid':PIDS['launcher']},'HOST_BASELINE_BINDINGS')
  boot=read_boot();need(boot==b['framework_epoch']['binding']['boot_id'],'CURRENT_BOOT_CHANGED')
  out['boot_id']=boot
  cell=b['cell_config']
  need(cell['path']=='/etc/droidloom/cell.json' and cell['sha256']=='f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc' and
   type(cell['bytes']) is int and 0<cell['bytes']<=131072,'FIXED_CELL_CONFIG')
  read_fixed(Path(cell['path']),{'bytes':cell['bytes'],'sha256':cell['sha256']})
  out['historical_cell_config_exact']=True
  out['phase']='fixed_daemon_and_owner_before'
  pidfds={};procs={}
  for role,pid in (('daemon',PIDS['daemon']),('owner',OWNER_ACTUAL['host_pid'])):
   check_time();fd=opened(os.pidfd_open(pid,0));held.append(fd);pidfds[role]=fd;require_pidfd_live(fd)
   proc=opened(os.open('/proc/'+str(pid),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC));held.append(proc);procs[role]=proc
  daemon=module.process_identity(PIDS['daemon']);need(daemon==expected_daemon,'DAEMON_CHANGED')
  owner=module.process_identity(OWNER_ACTUAL['host_pid']);require_owner(owner,old_launcher)
  first=children_sample(procs['daemon']);need(first['child_host_pids']==[OWNER_ACTUAL['host_pid']],'DAEMON_CHILD_SET_CHANGED')
  binaries={role:hold_binary(procs[role],b['current_process_executables'][old_role],held)
   for role,old_role in (('daemon','daemon'),('owner','launcher'))}
  out['before']={'daemon':project_identity('daemon',daemon,expected_daemon),
   'owner':project_identity('unknown_child',owner),'daemon_child_host_pids':first['child_host_pids'],
   'kernel_table_sha256':sha(canon(first)),'executables':{k:v['public'] for k,v in binaries.items()}}
  out['phase']='fixed_status_socket'
  socket_path_fd=opened(os.open(SOCKET_PATH,os.O_PATH|os.O_NOFOLLOW|os.O_CLOEXEC));held.append(socket_path_fd)
  path_before=proc_metadata(socket_path_fd)
  need(stat.S_ISSOCK(path_before['st_mode']) and path_before['st_uid']==0 and path_before['st_nlink']==1,'STATUS_SOCKET_SHAPE')
  sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM|socket.SOCK_CLOEXEC)
  opened(sock.fileno());sock.settimeout(max(.001,min(12,15-(time.monotonic()-START))))
  sock.connect(SOCKET_PATH)
  peer_values=struct.unpack('3i',sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
  peer=dict(zip(('pid','uid','gid'),peer_values));require_peer(peer);out['socket_peer']=peer
  require_pidfd_live(pidfds['daemon']);require_pidfd_live(pidfds['owner'])
  need(module.process_identity(PIDS['daemon'])==expected_daemon,'DAEMON_CHANGED')
  require_owner(module.process_identity(OWNER_ACTUAL['host_pid']),old_launcher)
  out['phase']='one_status_request'
  out['status_request']['send_attempted']=True;sock.sendall(STATUS_REQUEST)
  out['status_request']['sent_complete']=True;sock.shutdown(socket.SHUT_WR)
  raw=receive_status(sock);out['status_request']['response_complete']=True
  value=parse_status(raw);out['status']=project_status(value,raw)
  out['phase']='independent_owner_after'
  after_daemon=module.process_identity(PIDS['daemon']);after_owner=module.process_identity(OWNER_ACTUAL['host_pid'])
  need(after_daemon==expected_daemon,'DAEMON_CHANGED');require_owner(after_owner,old_launcher)
  last=children_sample(procs['daemon']);need(first==last,'DAEMON_CHILD_SET_CHANGED')
  for fd in pidfds.values():require_pidfd_live(fd)
  for record in binaries.values():verify_binary(record)
  named=os.stat(SOCKET_PATH,follow_symlinks=False)
  need(proc_metadata(socket_path_fd)==path_before and
   {key:getattr(named,key) for key in path_before}==path_before,'STATUS_SOCKET_SHAPE')
  need(read_boot()==boot,'CURRENT_BOOT_CHANGED')
  read_fixed(Path(cell['path']),{'bytes':cell['bytes'],'sha256':cell['sha256']})
  out['after']={'daemon_complete_identity_equal':True,'owner_complete_identity_equal':True,
   'both_pidfds_live':True,'two_daemon_kernel_tables_equal':True,'executables_held_and_named_unchanged':True,
   'socket_path_held_and_named_unchanged':True,'boot_and_cell_config_equal':True}
  out['daemon_reported_owner_binds_current_kernel_candidate']=out['status']['reported_running_owner_equals_fixed_kernel_candidate']
  out['phase']='complete';check_time();protocol_complete=True
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
 need(len(raw)<=65536,'OUTPUT_BOUND');print(raw.decode(),end='',flush=True)
 return 0 if out['ok'] else 1
