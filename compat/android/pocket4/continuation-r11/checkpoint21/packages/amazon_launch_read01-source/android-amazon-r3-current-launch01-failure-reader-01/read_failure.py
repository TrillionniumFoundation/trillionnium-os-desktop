#!/usr/bin/env python3
"""Read only exact Amazon terminal parents, retained phase summaries, and fixed launch command evidence."""
import hashlib,json,os,re,stat,time
from pathlib import Path
ROOT=Path('/home/alex/work/pocket4-amazon-r3-current-search-entry-01')
FLOW=Path('/home/alex/work/pocket4-amazon-owned-qa-r3-flow-42ee4dd8ab30f563567ba353deff430c')
NONCE='42ee4dd8ab30f563567ba353deff430c'
SOURCE_SHA='452b2c85207d60d5e47efbeafc05f49ecae416fabf6988fb7362100d55d6e46c'
PACKAGE='com.amazon.mShop.android.shopping'
SELF='org.droidloom.qa.amazon.r3'
UID=10129
HELPER_UID=10154
PARENTS={
 'coordinator':(6731,'6ad6d5b5ee5007dccad21ef6a2847fb84a1afbf48d3de5c13ac9152bd3432541'),
 'stage':(2724,'ae0ce8201b2cb5ef8f263b746600029109a14d3e32bb790cd16d16ce745bde99')}
FILES={
 'coordinator':ROOT/'result.json','stage':ROOT/'stage-result.json',
 'launch':FLOW/'steps/launch-01/result.json',
 'inspect':FLOW/'steps/inspect-01/result.json',
 'cleanup':FLOW/'steps/cleanup-01/result.json',
 'launch-command':ROOT/'evidence/01-launch.result.json',
 'launch-stdout':ROOT/'evidence/01-launch.stdout',
 'launch-stderr':ROOT/'evidence/01-launch.stderr',
 'launch-scope':FLOW/'launch-scope.json',
 'launch-attempted':FLOW/'launch-attempted.json'}
LIMITS={key:262144 for key in FILES}
LIMITS.update({'launch-command':65536,'launch-stderr':65536,'launch-scope':65536,'launch-attempted':65536})
ARGV=['/usr/bin/python3','-I',str(ROOT/'source/owned_inspect.py'),
 '--worker-once','launch','--source-manifest-sha256',SOURCE_SHA]
def need(value,reason):
 if not value:raise RuntimeError(reason)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def no_raw_ui(value,path=()):
 if isinstance(value,dict):
  need(not ({'nodes','text','content_desc','raw_tree','raw_ui_tree','screenshot'}&set(value)),
       'RAW_UI_FIELD_FORBIDDEN_IN_SUMMARY_EXPORT')
  for key,item in value.items():no_raw_ui(item,path+(key,))
 elif isinstance(value,list):
  for index,item in enumerate(value):no_raw_ui(item,path+(str(index),))
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
    need(size<=maximum and self.bytes<=2097152,'TOTAL_READ_BOUND')
   last=os.fstat(fd)
   fields=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
   need(size==first.st_size and all(getattr(first,k)==getattr(last,k) for k in fields),'FILE_CHANGED')
   return b''.join(chunks)
  finally:
   try:
    if fd is not None:self.close(fd)
   finally:self.close(current)
def pin(raw):return {'bytes':len(raw),'sha256':sha(raw)}
def record(name,raw):
 return {'path':str(FILES[name]),**pin(raw),'text':raw.decode('utf-8','strict')}
def phase_pin(value,phase):
 need(type(value) is dict and set(value)=={'path','bytes','sha256'} and
      value['path']==str(FILES[phase]) and type(value['bytes']) is int and 0<value['bytes']<=LIMITS[phase] and
      type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['sha256']),
      'EXACT_PARENT_BOUND_PHASE_PIN_REQUIRED:'+phase)
 return value
def qualify_command(value):
 allowed={'name','argv','spawned','joined','timed_out','returncode','secondary_errors','Main_before',
          'owned_child_pid','primary_error','Main_after','stdout','stderr'}
 required={'name','argv','spawned','joined','timed_out','returncode','secondary_errors','Main_before','stdout','stderr'}
 need(type(value) is dict and required<=set(value)<=allowed,'EXACT_COMMAND_METADATA_FIELDS')
 need(value['name']=='01-launch' and value['argv']==ARGV and value['Main_before'] is True,
      'EXACT_SOURCE_FIXED_LAUNCH_COMMAND')
 need(all(type(value[key]) is bool for key in ('spawned','joined','timed_out')) and
      (value['returncode'] is None or type(value['returncode']) is int) and
      type(value['secondary_errors']) is list,'COMMAND_OUTCOME_TYPES')
 if 'owned_child_pid' in value:
  need(type(value['owned_child_pid']) is int and value['owned_child_pid']>1,'OWN_CHILD_PID_TYPE')
 for stream in ('stdout','stderr'):
  v=value[stream];limit=LIMITS['launch-'+stream]
  need(type(v) is dict and set(v)=={'bytes','sha256'} and type(v['bytes']) is int and
       0<=v['bytes']<=limit and type(v['sha256']) is str and re.fullmatch('[0-9a-f]{64}',v['sha256']),
       'EXACT_BOUNDED_COMMAND_STREAM_PIN:'+stream)
 no_raw_ui(value)
 return value
def check_controls():
 cases=[]
 def reject(label,fn):
  try:fn()
  except (RuntimeError,KeyError,TypeError,ValueError):cases.append({'name':label,'passed':True});return
  raise RuntimeError('CONTROL_ACCEPTED:'+label)
 good={'name':'01-launch','argv':ARGV,'spawned':True,'joined':True,'timed_out':False,'returncode':2,
       'secondary_errors':[],'Main_before':True,'stdout':{'bytes':0,'sha256':sha(b'')},
       'stderr':{'bytes':0,'sha256':sha(b'')}}
 need(qualify_command(good) is good,'FAILED_COMMAND_MUST_REMAIN_READABLE')
 cases.append({'name':'failed-returncode-preserved','passed':True})
 for label,change in (
  ('wrong-command-name',{'name':'02-inspect'}),
  ('wrong-command-argv',{'argv':ARGV+['--execute-once']}),
  ('unknown-command-field',{'raw_ui_tree':{}}),
  ('bool-not-returncode',{'returncode':True}),
  ('unbounded-stream',{'stdout':{'bytes':262145,'sha256':sha(b'')}})):
  changed={**good,**change};reject(label,lambda changed=changed:qualify_command(changed))
 valid={'path':str(FILES['launch']),'bytes':1,'sha256':'0'*64}
 need(phase_pin(valid,'launch') is valid,'FIXED_PHASE_POSITIVE')
 cases.append({'name':'parent-fixed-phase-positive','passed':True})
 reject('foreign-phase-path',lambda:phase_pin({**valid,'path':str(FILES['inspect'])},'launch'))
 reject('private-ui-field',lambda:no_raw_ui({'safe':{'nodes':[]}}))
 need(len(cases)==9,'EXACT_NINE_READER_CONTROLS')
 return cases
def collect():
 need(os.getuid()==os.geteuid()==0,'ROOT_READ_ONLY_REQUIRED')
 controls=check_controls()
 reader=Reader();files={};values={};metadata={}
 for name in ('coordinator','stage'):
  raw=reader.access(name,True);expected=PARENTS[name]
  need(len(raw)==expected[0] and sha(raw)==expected[1],'EXTERNAL_TERMINAL_PIN:'+name)
  value=json.loads(raw);no_raw_ui(value)
  need(type(value) is dict and value.get('source_manifest_sha256')==SOURCE_SHA and
       value.get('nonce')==NONCE and value.get('package')==PACKAGE,
       'EXACT_FRESH_FLOW_PARENT_BINDING:'+name)
  files[name]=record(name,raw);values[name]=value
 c,s=values['coordinator'],values['stage']
 need(s.get('coordinator_result')=={k:files['coordinator'][k] for k in ('path','bytes','sha256')},
      'STAGE_COORDINATOR_LINK_REQUIRED')
 need(c.get('helper_package')==SELF and c.get('helper_uid')==HELPER_UID and c.get('uid')==UID and
      c.get('flow')==str(FLOW),'EXACT_AMAZON_COORDINATOR_SCOPE')
 need(c.get('ok') is False and type(c.get('error')) is dict and c.get('launch_worker_requested') is True,
      'EXACT_FAILED_LAUNCH_PARENT_REQUIRED')
 retained=c.get('retained_phase_results')
 fields={'launch':'launch_result','inspect':'inspection_result','cleanup':'cleanup_result'}
 need(type(retained) is dict and set(retained)<=set(fields),'ONLY_THREE_FIXED_RETAINED_PHASES')
 for phase,field in fields.items():
  if phase not in retained:
   need(field not in c,'UNRETAINED_DUPLICATE_PHASE_PIN')
   metadata[phase]=reader.access(phase,False,optional=True)
   if metadata[phase] is None:metadata[phase]={'present':False,'contents_read':False,'contents_qualified':False}
   continue
  expected=phase_pin(retained[phase],phase)
  if field in c:need(c[field]==expected,'DUPLICATE_PHASE_PINS_DIFFER:'+phase)
  raw=reader.access(phase,True)
  need(pin(raw)=={k:expected[k] for k in ('bytes','sha256')},'PARENT_PHASE_BYTES_CHANGED:'+phase)
  value=json.loads(raw);no_raw_ui(value)
  need(value.get('source_manifest_sha256')==SOURCE_SHA and value.get('nonce')==NONCE and
       value.get('phase')==phase and value.get('helper_package')==SELF and value.get('helper_uid')==HELPER_UID and
       value.get('package')==PACKAGE and value.get('uid')==UID,'EXACT_PHASE_SCOPE:'+phase)
  files[phase]=record(phase,raw);values[phase]=value
 raw=reader.access('launch-command',True);command=qualify_command(json.loads(raw))
 files['launch-command']=record('launch-command',raw)
 stream_metadata={}
 for stream in ('stdout','stderr'):
  name='launch-'+stream;raw=reader.access(name,True)
  need(pin(raw)==command[stream],'FIXED_COMMAND_STREAM_CHANGED:'+stream)
  stream_metadata[stream]={'path':str(FILES[name]),**pin(raw),'raw_exported':False}
  if stream=='stdout':
   try:printed=json.loads(raw)
   except (UnicodeDecodeError,json.JSONDecodeError):printed=None
   same='launch' in values and type(printed) is dict and printed==values['launch']
   stream_metadata[stream]['lossless_json_equal_to_parent_bound_worker']=same
   if same:
    no_raw_ui(printed);files[name]=record(name,raw);stream_metadata[stream]['raw_exported']=True
 for name in ('launch-scope','launch-attempted'):
  value=reader.access(name,False,optional=True)
  metadata[name]=value if value is not None else {'present':False,'contents_read':False,'contents_qualified':False}
 need(reader.opened==reader.closed,'ALL_ACQUIRED_FILE_DESCRIPTORS_CLOSED')
 bundle={'schema':1,'scope':'fixed-Amazon-current-launch01-failure-safe-results','files':files,
  'source_manifest_sha256':SOURCE_SHA,'flow_nonce':NONCE,'fixed_file_metadata_only':metadata,
  'launch_command_streams':stream_metadata,'reader_controls':controls,'bytes_read':reader.bytes,
  'file_descriptors_opened':reader.opened,'file_descriptors_closed':reader.closed,
  'command_metadata_external_pin_supplied':False,'command_path_and_argv_bound_to_frozen_source':True,
  'native_command_stdout_read':False,'raw_UI_or_commercial_journal_exported':False,
  'Android_or_process_actions':0,'runtime_qualification_asserted':False,
  'cleanup_authority_created':False,'launch_replayed':False,'permission_or_original_file_changes':0}
 raw=(json.dumps(bundle,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
 need(len(raw)<=3145728,'SUMMARY_BUNDLE_BOUND')
 print(json.dumps({'schema':1,'encoding':'plain-utf8','private_UI_data':False,
  'uncompressed_bytes':len(raw),'uncompressed_sha256':sha(raw),'data':raw.decode('utf-8','strict')},
  sort_keys=True),flush=True)
 return 0
if __name__=='__main__':raise SystemExit(collect())
