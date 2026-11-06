"""Fixed historical task-file package projection; no Android/process/Main/action access."""
import ast,hashlib,json,os,re,signal,stat,time
from pathlib import Path
PACKAGE='com.ihg.apps.android'
SHORT='com.ihg.apps.android/.activity.MainActivity'
FULL='com.ihg.apps.android/com.ihg.apps.android.activity.MainActivity'
PARSER=Path('/home/alex/work/pocket4-current-host-r6-source-01/references/task_scope_baseline.py')
PARSER_PIN={'bytes':17281,'sha256':'a16e347abb0de2ccbff24f6d7990f6dab1be600675054b45203e907fa8eef528'}
STEP=Path('/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b/steps/native-launch-state-read-02')
TABLE_PIN={'bytes':1326,'sha256':'b7e0d5df2bc42d78691443a55ee4d30303e4513ac48fa525f26ae985085b7973'}
ROOTS_SHA='623589a06d53ff445a30a59a1b89dc4793eba18d1b5654fc0606700d92c427da'
ACTUAL_READ={'bytes':20862,'sha256':'96d58a756c7e5179ced035925d99508955163a72a4f452f030a25f18df79e157'}
FIXED={str(PARSER):PARSER_PIN,str(STEP/'current-stacks-01.txt'):TABLE_PIN,str(STEP/'current-stacks-02.txt'):TABLE_PIN}
LEDGER={'opened':0,'close_attempted':0,'closed':0,'close_errors':[]}
DEADLINE=None
def need(value,code):
 if not value:raise RuntimeError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def pin(raw):return {'bytes':len(raw),'sha256':sha(raw)}
def canon(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
def budget():need(DEADLINE is not None and time.monotonic()<DEADLINE,'FIXED_READER_DEADLINE')
def read_exact(path):
 budget();expected=FIXED.get(str(path));need(expected is not None,'ONLY_THREE_FIXED_INPUTS')
 fds=[];raw=None;primary=None;close_errors=[]
 def opened(name,flags,dir_fd=None):
  budget();fd=os.open(name,flags,dir_fd=dir_fd);fds.append(fd);LEDGER['opened']+=1;return fd
 try:
  current=opened('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
  for part in path.parts[1:-1]:
   current=opened(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current)
  fd=opened(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current)
  before=os.fstat(fd)
  need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_uid==0 and before.st_size==expected['bytes'],
   'EXACT_ROOT_SINGLE_REGULAR_FILE')
  chunks=[];size=0
  while True:
   budget();part=os.read(fd,min(65536,expected['bytes']+1-size))
   if not part:break
   chunks.append(part);size+=len(part);need(size<=expected['bytes'],'EXACT_INPUT_SIZE_BOUND')
  after=os.fstat(fd);fields=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
  need(size==before.st_size and all(getattr(before,k)==getattr(after,k) for k in fields),'FIXED_INPUT_CHANGED')
  raw=b''.join(chunks);need(pin(raw)==expected,'FIXED_INPUT_SHA')
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
def project(raw,parse,sample):
 roots,tasks=parse(raw.decode('utf-8','strict'))
 need(len(roots)==2 and tasks=={875,877} and sha(canon(roots))==ROOTS_SHA,'EXACT_COMPLETE_CAPTURED_ROOTS')
 rows=[]
 for rid,root in sorted(roots.items()):
  children=[{'id':child['id'],'user':child['user'],**project_component(child['component'])} for child in root['children']]
  rows.append({'id':rid,'display':root['display'],'user':root['user'],'freeform':root['freeform'],
   'children':children,'complete_root_record_sha256':sha(canon(root))})
 return {'sample':sample,'file':str(STEP/('current-stacks-%02d.txt'%sample)),'raw_pin':pin(raw),
  'tasks':sorted(tasks),'complete_parsed_roots_sha256':sha(canon(roots)),'roots':rows}
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
 result={'schema':'pocket4-ihg-london-fixed-saved-task-package-projection-v1','ok':False,
  'error':None,'secondary_errors':[],'actual_two_stack_reader':ACTUAL_READ,'source_sha256':SOURCE_SHA256,
  'parser_source':{'path':str(PARSER),**PARSER_PIN},'observations':[],
  'original_launch_outcome_unknown_retained':True,'original_task876_disappearance_attributed':False,
  'original_parser_modified':False,'foreign_or_unknown_component_names_exported':False,
  'private_UI_tree_read':False,'current_Main_requalified':False,'new_current_task_observation':False,
  'Android_commands':0,'UI_actions':0,'native_launches':0,'processes_spawned':0,'task_removals':0,
  'original_files_modified':0,'cleanup_authority_created':False,'whole_app_production_ready':False}
 try:
  parser_raw=read_exact(PARSER);parse=original_parser(parser_raw)
  result['controls']=controls(parse);result['control_count']=len(result['controls'])
  raws=[read_exact(STEP/('current-stacks-%02d.txt'%sample)) for sample in (1,2)]
  need(raws[0]==raws[1],'TWO_FIXED_SAVED_CAPTURES_IDENTICAL')
  for sample,raw in enumerate(raws,1):result['observations'].append(project(raw,parse,sample))
  result['task877_known_public_IHG_MainActivity_in_both']=all(
   [child['canonical_public_IHG_MainActivity'] for root in row['roots'] for child in root['children'] if child['id']==877]==[FULL]
   for row in result['observations'])
  need(result['task877_known_public_IHG_MainActivity_in_both'],'TWO_COMPLETE_PUBLIC_COMPONENT_MATCHES')
  budget()
 except BaseException as error:result['error']=safe_error(error)
 finally:
  try:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
  except BaseException as error:result['secondary_errors'].append({'phase':'self_watchdog_restore',**safe_error(error)})
 result['FD_ledger']=LEDGER;result['seconds']=time.monotonic()-began
 result['ok']=bool(result['error'] is None and not result['secondary_errors'] and
  LEDGER['opened']==LEDGER['close_attempted']==LEDGER['closed'] and not LEDGER['close_errors'] and
  len(result['observations'])==2 and result.get('task877_known_public_IHG_MainActivity_in_both') is True)
 raw=(json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
 need(len(raw)<=16384,'PUBLIC_OUTPUT_BOUND');print(raw.decode(),end='',flush=True)
 return 0 if result['ok'] else 1
