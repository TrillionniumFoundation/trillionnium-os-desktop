"""Fixed saved task-table evidence after retirement01 rejected; no Android/process/Main/action access."""
import ast,hashlib,json,os,re,signal,stat,time
from pathlib import Path
PACKAGE='com.ihg.apps.android'
SHORT='com.ihg.apps.android/.activity.MainActivity'
FULL='com.ihg.apps.android/com.ihg.apps.android.activity.MainActivity'
PARSER=Path('/home/alex/work/pocket4-current-host-r6-source-01/references/task_scope_baseline.py')
PARSER_PIN={'bytes':17281,'sha256':'a16e347abb0de2ccbff24f6d7990f6dab1be600675054b45203e907fa8eef528'}
STEP=Path('/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b/steps/current-ihg877-independent-retirement-01')
COMMAND=STEP/'command-005.result.json'
COMMAND_PIN={'bytes':443,'sha256':'f887e2f9da435418a3c6da526efb258015a734c8b901ed29b62f0a7652c40879'}
COMMAND_RECORD=json.loads("{\"action_attempted\":false,\"automatic_retry\":false,\"ended_utc\":\"2026-11-06T19:49:06.853589+00:00\",\"error\":null,\"errors\":[],\"owned_command_joined\":true,\"returncode\":0,\"seconds\":0.0328486351063475,\"spawned\":true,\"stderr_sha256\":\"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\",\"stdout_sha256\":\"bf84e8d77523a712a7b4dc5712dea5ab7e65d7c0a6c3b285eed2b30baec18b8b\",\"timed_out\":false}")
STDOUT=STEP/'command-005.stdout'
SAVED=STEP/'before-stacks-01.txt'
TABLE_PIN={'bytes':None,'maximum_bytes':131072,'sha256':'bf84e8d77523a712a7b4dc5712dea5ab7e65d7c0a6c3b285eed2b30baec18b8b'}
ACTUAL_READ={'bytes':24051,'sha256':'dd040d4a5ac8050a2fd3d854e0dec74be386c048f33b68d0e4b200aaa4a79e9a'}
PRIOR_SAVED={'tasks':[875,877],
 'roots_sha256':'623589a06d53ff445a30a59a1b89dc4793eba18d1b5654fc0606700d92c427da',
 'root1_sha256':'d7cf29998b32a57a3680dd9e3b5b1af813a2cde6216db4f376403e633cc3618a',
 'root877_sha256':'8539928b108b7b26fec241c4d3cb1ff010aa600269f78bf6c0c0e16f11f7f588'}
FIXED={str(PARSER):PARSER_PIN,str(COMMAND):COMMAND_PIN,str(STDOUT):TABLE_PIN,str(SAVED):TABLE_PIN}
LEDGER={'opened':0,'close_attempted':0,'closed':0,'close_errors':[]}
DEADLINE=None
def need(value,code):
 if not value:raise RuntimeError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def pin(raw):return {'bytes':len(raw),'sha256':sha(raw)}
def canon(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
def budget():need(DEADLINE is not None and time.monotonic()<DEADLINE,'FIXED_READER_DEADLINE')
def read_exact(path):
 budget();expected=FIXED.get(str(path));need(expected is not None,'ONLY_FOUR_FIXED_INPUTS')
 limit=expected.get('maximum_bytes',expected['bytes'])
 need(type(limit) is int and 0<limit<=131072 and (expected['bytes'] is not None or path in (STDOUT,SAVED)),
  'EXACT_FIXED_INPUT_SIZE_POLICY')
 fds=[];raw=None;primary=None;close_errors=[]
 def opened(name,flags,dir_fd=None):
  budget();fd=os.open(name,flags,dir_fd=dir_fd);fds.append(fd);LEDGER['opened']+=1;return fd
 try:
  current=opened('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
  for part in path.parts[1:-1]:
   current=opened(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current)
  fd=opened(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current)
  before=os.fstat(fd)
  need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_uid==0 and 0<before.st_size<=limit and
   (expected['bytes'] is None or before.st_size==expected['bytes']),
   'EXACT_ROOT_SINGLE_REGULAR_FILE')
  chunks=[];size=0
  while True:
   budget();part=os.read(fd,min(65536,limit+1-size))
   if not part:break
   chunks.append(part);size+=len(part);need(size<=limit,'EXACT_INPUT_SIZE_BOUND')
  after=os.fstat(fd);fields=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
  need(size==before.st_size and all(getattr(before,k)==getattr(after,k) for k in fields),'FIXED_INPUT_CHANGED')
  raw=b''.join(chunks);need(sha(raw)==expected['sha256'] and
   (expected['bytes'] is None or len(raw)==expected['bytes']),'FIXED_INPUT_SHA')
 except BaseException as error:primary=error
 finally:
  for fd in reversed(fds):
   LEDGER['close_attempted']+=1
   try:os.close(fd);LEDGER['closed']+=1
   except BaseException as error:
    item={'type':type(error).__name__,'errno':getattr(error,'errno',None)}
    LEDGER['close_errors'].append(item);close_errors.append(error)
 if primary is not None:raise primary
 if close_errors:raise RuntimeError('FIXED_INPUT_FD_CLOSE_FAILED') from close_errors[0]
 return raw
def original_parser(raw):
 # Compile only the original pure function; never execute the historical module.
 body=[node for node in ast.parse(raw).body if isinstance(node,ast.FunctionDef) and node.name=='parse_stacks']
 need(len(body)==1,'EXACT_ORIGINAL_PARSER_FUNCTION')
 scope={'re':re,'require':need}
 exec(compile(ast.Module(body=body,type_ignores=[]),str(PARSER),'exec'),scope)
 return scope['parse_stacks']
def project_component(component):
 need(type(component) is str,'COMPONENT_STRING_REQUIRED')
 parts=component.split('/')
 need(len(parts)==2 and all(parts),'ONE_EXACT_COMPONENT_SEPARATOR')
 known=component in (SHORT,FULL)
 return {'component_utf8_bytes':len(component.encode()),'component_sha256':sha(component.encode()),
  'component_package_is_IHG':parts[0]==PACKAGE,'known_public_IHG_component':component if known else None,
  'canonical_public_IHG_MainActivity':FULL if known else None,'unknown_component_text_exported':False}
def controls(parse):
 cases=[]
 a=project_component(SHORT);b=project_component(FULL)
 need(a['component_package_is_IHG'] and b['component_package_is_IHG'] and
  a['canonical_public_IHG_MainActivity']==b['canonical_public_IHG_MainActivity']==FULL,'PUBLIC_COMPONENT_EQUIVALENCE')
 cases.append({'name':'short-and-expanded-public-MainActivity','passed':True})
 foreign=project_component(PACKAGE+'x/.Synthetic')
 need(foreign['component_package_is_IHG'] is False and foreign['known_public_IHG_component'] is None and
  foreign['canonical_public_IHG_MainActivity'] is None,'EXACT_PACKAGE_NOT_PREFIX')
 cases.append({'name':'foreign-package-prefix-not-IHG','passed':True})
 unknown=project_component(PACKAGE+'/.SyntheticPrivateLabel')
 need(unknown['component_package_is_IHG'] is True and unknown['known_public_IHG_component'] is None and
  unknown['canonical_public_IHG_MainActivity'] is None and unknown['unknown_component_text_exported'] is False,
  'UNKNOWN_IHG_CLASS_HASH_ONLY')
 cases.append({'name':'unlisted-IHG-class-never-exported','passed':True})
 try:project_component(PACKAGE)
 except RuntimeError as error:
  need(str(error)=='ONE_EXACT_COMPONENT_SEPARATOR','COMPONENT_CONTROL_FIRST_ERROR')
  cases.append({'name':'missing-component-separator-rejected','passed':True})
 else:raise RuntimeError('MALFORMED_COMPONENT_ACCEPTED')
 fixture='RootTask id=877 displayId=0 userId=0\n mWindowingMode=freeform\n taskId=877: '+FULL+' x userId=0\n'
 roots,tasks=parse(fixture)
 need(tasks=={877} and roots[877]['children']==[{'id':877,'component':FULL,'user':0}],
  'ORIGINAL_PARSER_PUBLIC_FIXTURE')
 try:parse(fixture+' taskId=877: '+FULL+' x userId=0\n')
 except RuntimeError as error:
  need(str(error)=='DUPLICATE_TASK','ORIGINAL_PARSER_WRONG_REJECTION')
  cases.append({'name':'original-parser-preserves-complete-component-and-duplicate-rejection','passed':True})
 else:raise RuntimeError('ORIGINAL_PARSER_DUPLICATE_ACCEPTED')
 need(len(cases)==5,'EXACT_FIVE_PROJECTION_CONTROLS');return cases
def qualify_command(record):
 need(type(record) is dict and record==COMMAND_RECORD,'EXACT_FAILED_RETIREMENT_COMMAND005_RECEIPT')
 need(record['spawned'] is True and record['owned_command_joined'] is True and record['returncode']==0 and
  record['timed_out'] is False and record['action_attempted'] is False and record['automatic_retry'] is False and
  record['error'] is None and record['errors']==[] and record['stdout_sha256']==TABLE_PIN['sha256'] and
  record['stderr_sha256']==sha(b''),'EXACT_JOINED_READ_ONLY_COMMAND005')
 return record
def project(raw,parse,sample,path):
 roots,tasks=parse(raw.decode('utf-8','strict'))
 need(0<len(roots)<=256 and 0<len(tasks)<=512,'COMPLETE_SAVED_TABLE_PROJECTION_BOUND')
 rows=[]
 for rid,root in sorted(roots.items()):
  children=[{'id':child['id'],'user':child['user'],**project_component(child['component'])} for child in root['children']]
  rows.append({'id':rid,'display':root['display'],'user':root['user'],'freeform':root['freeform'],
   'children':children,'complete_root_record_sha256':sha(canon(root))})
 previous=set(PRIOR_SAVED['tasks'])
 return {'sample':sample,'file':str(path),'raw_pin':pin(raw),'tasks':sorted(tasks),
  'complete_parsed_roots_sha256':sha(canon(roots)),'roots':rows,
  'comparison_to_previous_saved_table':{
   'previous_tasks':PRIOR_SAVED['tasks'],'added_task_ids':sorted(tasks-previous),'removed_task_ids':sorted(previous-tasks),
   'previous_complete_roots_equal':sha(canon(roots))==PRIOR_SAVED['roots_sha256'],
   'previous_root1_record_equal':1 in roots and sha(canon(roots[1]))==PRIOR_SAVED['root1_sha256'],
   'previous_root877_record_equal':877 in roots and sha(canon(roots[877]))==PRIOR_SAVED['root877_sha256'],
   'change_cause_determined':False,'authorizes_task_removal':False}}
def reader_controls(parse):
 cases=controls(parse)
 qualify_command(json.loads(canon(COMMAND_RECORD)))
 cases.append({'name':'actual-fixed-command005-is-complete-read-only','passed':True})
 for name,key,value in [('changed-command005-stdout-rejected','stdout_sha256','0'*64),
  ('command005-action-claim-rejected','action_attempted',True)]:
  bad=json.loads(canon(COMMAND_RECORD));bad[key]=value
  try:qualify_command(bad)
  except RuntimeError as error:
   need(str(error)=='EXACT_FAILED_RETIREMENT_COMMAND005_RECEIPT','COMMAND_CONTROL_FIRST_ERROR')
   cases.append({'name':name,'passed':True})
  else:raise RuntimeError('BAD_COMMAND005_ACCEPTED')
 fixture=('RootTask id=877 displayId=0 userId=0\n mWindowingMode=freeform\n taskId=877: '+FULL+
  ' x userId=0\nRootTask id=991 displayId=0 userId=0\n taskId=991: example.private/.Hidden x userId=0\n').encode()
 projected=project(fixture,parse,0,SAVED);delta=projected['comparison_to_previous_saved_table']
 need(delta['added_task_ids']==[991] and delta['removed_task_ids']==[875] and
  delta['authorizes_task_removal'] is False and 'example.private' not in json.dumps(projected) and
  '.Hidden' not in json.dumps(projected) and projected['tasks']==[877,991],
  'CHANGED_SAVED_TABLE_DIAGNOSTIC_WITHOUT_FOREIGN_NAMES_OR_AUTHORITY')
 cases.append({'name':'changed-task-set-projects-completely-without-foreign-names-or-authority','passed':True})
 need(len(cases)==9,'EXACT_NINE_PROJECTION_CONTROLS');return cases
def safe_error(error):
 text=str(error);out={'type':type(error).__name__,'message_sha256':sha(text.encode('utf-8','replace'))}
 if isinstance(error,RuntimeError) and re.fullmatch('[A-Z][A-Z0-9_]{0,127}',text):out['fixed_code']=text
 errno=getattr(error,'errno',None)
 if type(errno) is int:out['errno']=errno
 return out
def expired(signum,frame):raise RuntimeError('SELF_WATCHDOG_DEADLINE')
def main():
 global DEADLINE
 need(os.getuid()==os.geteuid()==0,'ROOT_READ_ONLY_REQUIRED')
 began=time.monotonic();DEADLINE=began+8
 previous=signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,10)
 result={'schema':'pocket4-ihg877-retirement01-fixed-saved-task-diagnostic-v1','ok':False,
  'error':None,'secondary_errors':[],'actual_failed_retirement':ACTUAL_READ,'source_sha256':SOURCE_SHA256,
  'parser_source':{'path':str(PARSER),**PARSER_PIN},'observations':[],
  'command005':None,'saved_table_bytes_previously_observed':None,
  'original_retirement_failure':'OTHER_TASK_SET_CHANGED','original_retirement_remove_requested':False,
  'original_retirement_outcome_unknown':False,'retirement_task_preservation_gate_modified':False,
  'original_launch_outcome_unknown_retained':True,'original_task876_disappearance_attributed':False,
  'original_parser_modified':False,'foreign_or_unknown_component_names_exported':False,
  'private_UI_tree_read':False,'current_Main_requalified':False,'new_current_task_observation':False,
  'Android_commands':0,'UI_actions':0,'native_launches':0,'processes_spawned':0,'task_removals':0,
  'original_files_modified':0,'cleanup_authority_created':False,'whole_app_production_ready':False}
 try:
  parser_raw=read_exact(PARSER);parse=original_parser(parser_raw)
  result['controls']=reader_controls(parse);result['control_count']=len(result['controls'])
  command_raw=read_exact(COMMAND);command=qualify_command(json.loads(command_raw.decode('utf-8','strict')))
  result['command005']={'path':str(COMMAND),**pin(command_raw),'record':command}
  raws=[read_exact(STDOUT),read_exact(SAVED)]
  need(raws[0]==raws[1],'SAVED_TABLE_EQUALS_EXACT_COMMAND005_STDOUT')
  for sample,(raw,path) in enumerate(zip(raws,(STDOUT,SAVED)),1):
   result['observations'].append(project(raw,parse,sample,path))
  result['same_complete_saved_table_in_both_files']=bool(
   result['observations'][0]['raw_pin']==result['observations'][1]['raw_pin'] and
   result['observations'][0]['complete_parsed_roots_sha256']==result['observations'][1]['complete_parsed_roots_sha256'])
  need(result['same_complete_saved_table_in_both_files'],'TWO_COMPLETE_FIXED_SAVED_TABLES')
  budget()
 except BaseException as error:result['error']=safe_error(error)
 finally:
  try:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
  except BaseException as error:result['secondary_errors'].append({'phase':'self_watchdog_restore',**safe_error(error)})
 result['FD_ledger']=LEDGER;result['seconds']=time.monotonic()-began
 result['ok']=bool(result['error'] is None and not result['secondary_errors'] and
  LEDGER['opened']==LEDGER['close_attempted']==LEDGER['closed'] and not LEDGER['close_errors'] and
  len(result['observations'])==2 and result.get('same_complete_saved_table_in_both_files') is True)
 raw=(json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
 need(len(raw)<=32768,'PUBLIC_OUTPUT_BOUND');print(raw.decode(),end='',flush=True)
 return 0 if result['ok'] else 1
