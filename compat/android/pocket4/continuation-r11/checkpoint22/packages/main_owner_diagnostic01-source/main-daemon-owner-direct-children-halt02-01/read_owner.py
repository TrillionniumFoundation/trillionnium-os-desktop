"""Fixed host-owner diagnosis; kernel direct children only, no cell adoption or action."""
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
START=time.monotonic()
FD_OPENED=0
FD_CLOSED=0
FD_CLOSE_ERRORS=[]
def need(value,code):
 if not value:raise RuntimeError(code)
def check_time():
 if time.monotonic()-START>=8:raise BudgetExpired()
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

def main():
 out={'schema':'pocket4-fixed-daemon-direct-children-diagnosis-v1','ok':False,'source_sha256':SOURCE_SHA256,
  'old_baseline':{'path':str(BASELINE),**BASELINE_PIN},'original_epoch_source':{'path':str(EPOCH_SOURCE),**EPOCH_PIN},
  'old_framework_epoch_sha256':OLD_EPOCH,'old_fixed_roles':{},'daemon_children':{'attempted':False,'complete':False},
  'controls':[],'errors':[],'read_budget_seconds':8,'self_watchdog_seconds':8,'original_module_modified':False,
  'bounds':{'daemon_threads':MAX_THREADS,'direct_children':MAX_CHILDREN,'child_list_bytes':16384},
  'private_baseline_exported':False,'raw_cmdline_or_cgroup_exported':False,
  'Android_commands':0,'UI_actions':0,'child_processes':0,'files_written':0,'signals_to_other_processes':0,
  'global_proc_scan':False,'descendant_recursion':False,'status_RPC_called':False,
  'daemon_cell_state_authoritatively_reported':False,'new_child_adopted_as_cell':False,'new_init_discovered':False,
  'new_baseline_created':False,'rebind_authorized':False,'old_flows_reauthorized':False,
  'current_task_state_observed':False,'cleanup_authority':False,'framework_exit_cause_resolved':False,'production_ready':False}
 protocol_complete=False;pidfd=proc=None
 try:
  need(os.getuid()==os.geteuid()==0,'ROOT_READ_ONLY_REQUIRED')
  out['controls']=host_owner_controls();check_time()
  baseline_raw=read_fixed(BASELINE,BASELINE_PIN);epoch_raw=read_fixed(EPOCH_SOURCE,EPOCH_PIN)
  module=types.ModuleType('fixed_original_framework_epoch_host_owner');module.__file__=str(EPOCH_SOURCE)
  exec(compile(epoch_raw,module.__file__,'exec'),module.__dict__)
  b=strict_json(baseline_raw)
  need(type(b) is dict and b.get('schema')=='pocket4-main-current-baseline-v1' and
       type(b.get('framework_epoch')) is dict and b['framework_epoch'].get('sha256')==OLD_EPOCH and
       b['framework_epoch'].get('schema')==module.SCHEMA and
       module._digest(b['framework_epoch']['binding'])==OLD_EPOCH,'PRIVATE_BASELINE_SCHEMA')
  seven=b['all_seven_processes']
  need(seven.get('schema')==module.SCHEMA and seven.get('sha256')==module._digest(seven['binding']) and
       seven['binding']['boot_id']==b['framework_epoch']['binding']['boot_id'],'HOST_BASELINE_BINDINGS')
  expected={role:b[role+'_process'] for role in PIDS}
  need(all(identity_shape(expected[role])['host_pid']==pid and
           seven['binding']['processes'][role]==expected[role] for role,pid in PIDS.items()) and
       b['status']=={'host_pid':PIDS['launcher']},'EXACT_HOST_ROLE_BINDINGS')
  out['old_boot_id']=seven['binding']['boot_id'];out['old_baseline_inputs_fully_pinned']=True
  boot_before=read_boot();out['current_boot_id']=boot_before
  boot_matches=boot_before==seven['binding']['boot_id'];out['baseline_boot_matches']=boot_matches
  observed={}
  for role,pid in PIDS.items():
   check_time();row={'fixed_host_pid':pid,'expected':project_identity(role,expected[role],expected[role]),'available':False}
   try:
    value=module.process_identity(pid);check_time();identity_shape(value);observed[role]=value
    row.update({'available':True,'observed':project_identity(role,value,expected[role]),
     'complete_identity_equal':value==expected[role],'difference_fields':difference_fields(expected[role],value)})
   except Exception as error:row['error']=safe_error(error)
   out['old_fixed_roles'][role]=row
  daemon_equal=observed.get('daemon')==expected['daemon']
  out['original_daemon_complete_identity_unchanged']=daemon_equal
  if not daemon_equal or not boot_matches:
   out['daemon_children']['skip_reason']='OLD_DAEMON_COMPLETE_IDENTITY_NOT_PROVEN' if not daemon_equal else 'BOOT_CHANGED_NO_PARENT_ADOPTION'
  else:
   check_time();pidfd=opened(os.pidfd_open(PIDS['daemon'],0))
   proc=opened(os.open('/proc/'+str(PIDS['daemon']),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC))
   require_pidfd_live(pidfd)
   need(module.process_identity(PIDS['daemon'])==expected['daemon'],'DAEMON_CHANGED')
   out['daemon_children']['attempted']=True
   first=children_sample(proc)
   out['daemon_children']['first_sample']={'thread_count':len(first['thread_ids']),
    'thread_ids':first['thread_ids'],'child_count':len(first['child_host_pids']),
    'child_host_pids':first['child_host_pids'],'kernel_table_sha256':sha(canon(first))}
   before={}
   for pid in first['child_host_pids']:
    check_time();before[pid]=module.process_identity(pid);identity_shape(before[pid])
    need(before[pid]['parent_host_pid']==PIDS['daemon'],'DIRECT_CHILD_PARENT_DIFFERS')
   last=children_sample(proc);after={}
   for pid in last['child_host_pids']:
    check_time();after[pid]=module.process_identity(pid);identity_shape(after[pid])
   qualify_children(first,last,before,after,expected['daemon'])
   require_pidfd_live(pidfd)
   final_daemon=module.process_identity(PIDS['daemon'])
   need(final_daemon==expected['daemon'],'DAEMON_CHANGED')
   need(read_boot()==boot_before,'CURRENT_BOOT_CHANGED')
   out['daemon_children'].update({'complete':True,'two_kernel_tables_equal':True,
    'all_child_full_identities_equal':True,'daemon_full_identity_before_after_equal':True,'daemon_pidfd_live':True,
    'second_sample':{'thread_count':len(last['thread_ids']),'thread_ids':last['thread_ids'],
     'child_count':len(last['child_host_pids']),'child_host_pids':last['child_host_pids'],'kernel_table_sha256':sha(canon(last))},
    'children':[{'host_pid':pid,'observed':project_identity('unknown_child',after[pid]),
     'exact_historical_launcher_identity':after[pid]==expected['launcher'],
     'historical_launcher_executable_and_argv_match':after[pid]['executable']==expected['launcher']['executable'] and
      after[pid]['cmdline']==expected['launcher']['cmdline'],
     'cell_owner_qualification':False,'adopted_as_launcher_or_init':False} for pid in last['child_host_pids']],
    'exact_historical_launcher_still_direct_child':any(value==expected['launcher'] for value in after.values()),
    'absence_of_matching_child_is_not_daemon_state_RPC':True})
  check_time();protocol_complete=True
 except BaseException as error:out['errors'].append(safe_error(error))
 finally:
  out['self_watchdog_disarmed']=STOP_WATCHDOG()
  for fd in (proc,pidfd):
   if fd is not None:
    try:close(fd)
    except BaseException as error:out['errors'].append({'phase':'held_daemon_FD_close',**safe_error(error)})
  out['tracked_input_and_daemon_FDs']={'acquired':FD_OPENED,'closed':FD_CLOSED,'close_error_count':len(FD_CLOSE_ERRORS)}
  out['original_epoch_internal_FDs_independently_counted']=False
  if FD_OPENED!=FD_CLOSED or FD_CLOSE_ERRORS:out['errors'].append({'code':'TRACKED_INPUT_FD_CLOSE_FAILED','raw_message_exported':False})
 out['diagnostic_protocol_complete']=protocol_complete;out['ok']=bool(protocol_complete and not out['errors'])
 out['elapsed_seconds']=time.monotonic()-START
 raw=(json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
 need(len(raw)<=65536,'OUTPUT_BOUND')
 print(raw.decode(),end='',flush=True)
 return 0 if out['ok'] else 1
