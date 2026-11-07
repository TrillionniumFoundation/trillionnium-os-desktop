"""Fixed current-epoch diagnosis only; private baseline and raw cmdline never exported."""
import hashlib,json,os,re,stat,time,types
from pathlib import Path
BASELINE=Path('/home/alex/work/pocket4-main-current-baseline-01/baseline.private.json')
BASELINE_PIN={'bytes':41844,'sha256':'163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266'}
EPOCH_SOURCE=Path('/home/alex/work/pocket4-current-host-r5-source-01/references/framework_epoch.py')
EPOCH_PIN={'bytes':8658,'sha256':'f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288'}
OLD_EPOCH='734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2'
PIDS={'init':3588093,'zygote64':90360,'system_server':90516,'surfaceflinger':3588912}
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
 exe=value['executable'];known=exe==PUBLIC_EXE[role]
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
def qualify_discovered(epoch,old,module):
 need(type(epoch) is dict and epoch.get('schema')==module.SCHEMA and type(epoch.get('binding')) is dict and
  epoch.get('sha256')==module._digest(epoch['binding']),'DISCOVERY_EPOCH_DOCUMENT')
 need(set(epoch['binding'])=={'boot_id','processes'} and type(epoch['binding']['processes']) is dict and
  set(epoch['binding']['processes'])==set(PIDS),'DISCOVERY_ROLES')
 need(epoch['binding']['processes']['init']==old['binding']['processes']['init'],'DISCOVERY_INIT_DIFFERS_FROM_OLD_CELL')
 need(epoch['binding']['boot_id']==old['binding']['boot_id'],'DISCOVERY_BOOT_DIFFERS_FROM_BASELINE')
 for role,value in epoch['binding']['processes'].items():identity_shape(value)
 return True
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
def main():
 out={'schema':'pocket4-fixed-current-epoch-diagnosis-v1','ok':False,'source_sha256':SOURCE_SHA256,
  'old_baseline':{'path':str(BASELINE),**BASELINE_PIN},'original_epoch_source':{'path':str(EPOCH_SOURCE),**EPOCH_PIN},
  'old_framework_epoch_sha256':OLD_EPOCH,'old_roles':{},'discovery':{'attempted':False,'available':False},
  'controls':[],'errors':[],'read_budget_seconds':8,'self_watchdog_seconds':8,'original_module_modified':False,
  'private_baseline_exported':False,'raw_cmdline_or_cgroup_exported':False,
  'Android_commands':0,'UI_actions':0,'child_processes':0,'files_written':0,'signals_to_other_processes':0,
  'Main_restart_inferred':False,'current_task_state_observed':False,'new_baseline_created':False,
  'rebind_authorized':False,'old_flows_reauthorized':False,'framework_exit_cause_resolved':False,'production_ready':False}
 old=None;module=None;protocol_complete=False
 try:
  need(os.getuid()==os.geteuid()==0,'ROOT_READ_ONLY_REQUIRED')
  out['controls']=controls();check_time()
  baseline_raw=read_fixed(BASELINE,BASELINE_PIN)
  epoch_raw=read_fixed(EPOCH_SOURCE,EPOCH_PIN)
  module=types.ModuleType('fixed_original_framework_epoch_readonly');module.__file__=str(EPOCH_SOURCE)
  exec(compile(epoch_raw,module.__file__,'exec'),module.__dict__)
  baseline=strict_json(baseline_raw)
  need(type(baseline) is dict and baseline.get('schema')=='pocket4-main-current-baseline-v1' and
   type(baseline.get('framework_epoch')) is dict,'PRIVATE_BASELINE_SCHEMA')
  old=baseline['framework_epoch']
  need(old.get('schema')==module.SCHEMA and old.get('sha256')==OLD_EPOCH and
   type(old.get('binding')) is dict and set(old['binding'])=={'boot_id','processes'} and
   re.fullmatch('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',old['binding']['boot_id']) and
   module._digest(old['binding'])==OLD_EPOCH,'EXACT_OLD_EPOCH_DOCUMENT')
  expected=old['binding']['processes']
  need(type(expected) is dict and set(expected)==set(PIDS) and
   all(identity_shape(expected[role])['host_pid']==pid for role,pid in PIDS.items()),'EXACT_FOUR_OLD_ROLES')
  out['old_boot_id']=old['binding']['boot_id'];out['old_baseline_inputs_fully_pinned']=True
  init_observed=None
  for role,pid in PIDS.items():
   check_time()
   row={'fixed_host_pid':pid,'expected':project_identity(role,expected[role],expected[role]),'available':False}
   try:
    observed=module.process_identity(pid);check_time();identity_shape(observed)
    row.update({'available':True,'observed':project_identity(role,observed,expected[role]),
     'complete_identity_equal':observed==expected[role],'difference_fields':difference_fields(expected[role],observed)})
    if role=='init':init_observed=observed
   except Exception as error:row['error']=safe_error(error)
   out['old_roles'][role]=row
  init_match=same_old_init(init_observed,expected['init'])
  out['original_init_complete_identity_unchanged']=init_match
  out['all_four_old_identities_match']=all(row.get('complete_identity_equal') is True for row in out['old_roles'].values())
  if init_match:
   check_time();out['discovery']['attempted']=True
   try:
    snapshot=module.capture_android(PIDS['init']);check_time()
    qualify_discovered(snapshot,old,module)
    current=snapshot['binding']['processes']
    out['discovery'].update({'available':True,'same_old_init_cell_verified':True,
     'epoch_sha256':snapshot['sha256'],'boot_id':snapshot['binding']['boot_id'],
     'epoch_equals_old':snapshot['binding']==old['binding'],
     'roles':{role:project_identity(role,current[role],expected[role]) for role in PIDS},
     'difference_fields_from_old':{role:difference_fields(expected[role],current[role]) for role in PIDS},
     'original_capture_android_own_checks_completed':True,'qualified_for_UI_or_rebind':False})
   except Exception as error:out['discovery']['error']=safe_error(error)
  else:
   out['discovery']['skip_reason']='OLD_INIT_COMPLETE_IDENTITY_NOT_PROVEN'
  check_time();protocol_complete=True
 except BaseException as error:out['errors'].append(safe_error(error))
 finally:
  # The supplied self alarm is disarmed only after all source reads/calls ended.
  out['self_watchdog_disarmed']=STOP_WATCHDOG()
  out['tracked_input_FDs']={'acquired':FD_OPENED,'closed':FD_CLOSED,'close_error_count':len(FD_CLOSE_ERRORS)}
  out['original_epoch_internal_FDs_independently_counted']=False
  if FD_OPENED!=FD_CLOSED or FD_CLOSE_ERRORS:out['errors'].append({'code':'TRACKED_INPUT_FD_CLOSE_FAILED','raw_message_exported':False})
 out['diagnostic_protocol_complete']=protocol_complete
 out['ok']=bool(protocol_complete and not out['errors'])
 out['elapsed_seconds']=time.monotonic()-START
 raw=(json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
 need(len(raw)<=32768,'OUTPUT_BOUND')
 print(raw.decode(),end='',flush=True)
 return 0 if out['ok'] else 1
