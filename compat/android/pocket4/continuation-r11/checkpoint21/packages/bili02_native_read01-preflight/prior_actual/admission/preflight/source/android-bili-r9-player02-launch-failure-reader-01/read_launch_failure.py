"""Fixed Bili R9 player02 launch-failure receipts. No device or process actions."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
ROOT=Path('/home/alex/work/pocket4-bilibili-r9-pause-resume-02')
FLOW=Path('/home/alex/work/pocket4-bilibili-owned-qa-r9-flow-474d7477074ea01fbc986e0d867924c1')
NONCE='474d7477074ea01fbc986e0d867924c1'
SOURCE_SHA='296da6728d720584339eb47e47801e0c458c3427d06e3a593acdc2f0bc3c6e5d'
R5_SHA='6d99374e1580083fd0f30b7f9b3c520306680760c97ad0d5400798fda427fb6e'
PARENTS={
 'coordinator':{'path':str(ROOT/'result.json'),'bytes':6749,'sha256':'66c18006c5d86e0cd86a6585a94be35ef4bf2ed815b9634cea93eeb916950c36'},
 'stage':{'path':str(ROOT/'stage-result.json'),'bytes':2665,'sha256':'54099482c05b463f8151e7a92e5ef9bbe4d3f2381fc00c98b4a7012454b2d272'}}
FILES={'coordinator':ROOT/'result.json','stage':ROOT/'stage-result.json',
 'launch_command':ROOT/'evidence/02-launch.result.json',
 'launch_stdout':ROOT/'evidence/02-launch.stdout','launch_stderr':ROOT/'evidence/02-launch.stderr',
 'launch':FLOW/'steps/launch-01/result.json','cleanup':FLOW/'steps/cleanup-01/result.json',
 'launch_scope':FLOW/'launch-scope.json','launch_attempted':FLOW/'launch-attempted.json'}
def need(value,reason):
 if not value:raise RuntimeError(reason)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def no_raw_ui(value,path=()):
 if path==('navigation','selector'):
  need(value=={'resource_id':'tv.danmaku.bili:id/expand_search','class':'android.widget.LinearLayout','content_desc':'Search bar, button'},'ONLY_FIXED_PUBLIC_SELECTOR_MAY_LEAVE')
  return
 if isinstance(value,dict):
  need(not({'nodes','text','content_desc','raw_tree','raw_ui_tree','screenshot'}&set(value)),'RAW_UI_FIELD_FORBIDDEN')
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
  return PARENTS[name]['bytes'] if name in PARENTS else (32768 if name=='launch' else 262144)
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
def exact_pin(name,pin,allow_empty=False):
 need(type(pin) is dict and set(pin)=={'path','bytes','sha256'} and pin['path']==str(FILES[name]) and
      type(pin['bytes']) is int and (0 if allow_empty else 1)<=pin['bytes']<=Reader.maximum(None,name) and
      type(pin['sha256']) is str and re.fullmatch('[0-9a-f]{64}',pin['sha256']),
      'EXACT_BOUNDED_PARENT_PIN_REQUIRED:'+name)
 return pin
def worker_binding(value):
 expected={'phase':'launch','nonce':NONCE,'package':'tv.danmaku.bili','uid':10117,
  'helper_package':'org.droidloom.qa.bili.r9','helper_uid':10152,
  'source_manifest_sha256':SOURCE_SHA,'runtime_recorder_manifest_sha256':R5_SHA}
 need(all(value.get(k)==v for k,v in expected.items()),'EXACT_LAUNCH_WORKER_SCOPE_REQUIRED')
def stderr_projection(raw):
 # Closed exception classes and syntax only; no exception message or traceback text leaves.
 classes=('RuntimeError','KeyError','TypeError','ValueError','AssertionError','FileNotFoundError',
          'PermissionError','TimeoutError','ProtocolError','OSError','ControlError','AttributeError')
 lines=raw.decode('utf-8','replace').splitlines()
 return {'bytes':len(raw),'sha256':sha(raw),'line_count':len(lines),
  'traceback_header_present':any(x=='Traceback (most recent call last):' for x in lines),
  'exception_class_counts':{k:sum(x==k or x.startswith(k+': ') for x in lines) for k in classes},
  'last_line_bytes':len(lines[-1].encode()) if lines else 0,
  'last_line_sha256':sha(lines[-1].encode()) if lines else sha(b''),
  'raw_stderr_exported':False,'cause_inferred':False}
def collect():
 need(os.getuid()==os.geteuid()==0,'ROOT_READ_ONLY_REQUIRED')
 reader=Reader();files={};observations={};errors=[];bindings={};presence={};diagnostic={}
 def attempt(label,call):
  try:return call()
  except Exception as error:
   errors.append({'stage':label,'type':type(error).__name__,'message':str(error),'errno':getattr(error,'errno',None)})
   return None
 def raw_read(name,pin):
  exact_pin(name,pin,allow_empty=name in ('launch_stdout','launch_stderr'))
  raw=reader.access(name,True)
  observations[name]={'path':str(FILES[name]),'bytes':len(raw),'sha256':sha(raw)}
  need(len(raw)==pin['bytes'] and sha(raw)==pin['sha256'],'PARENT_BOUND_ORIGINAL_CHANGED:'+name)
  return raw
 def add(name,pin):
  raw=raw_read(name,pin);value=json.loads(raw)
  need(type(value) is dict,'FIXED_RECORD_OBJECT_REQUIRED:'+name);no_raw_ui(value)
  files[name]={**observations[name],'text':raw.decode('utf-8','strict')}
  return value
 c=attempt('coordinator',lambda:add('coordinator',PARENTS['coordinator']))
 s=attempt('stage',lambda:add('stage',PARENTS['stage']))
 def parents():
  need(c is not None and s is not None,'BOTH_EXTERNAL_PARENTS_REQUIRED')
  for v in (c,s):
   need(v.get('source_manifest_sha256')==SOURCE_SHA and v.get('nonce')==NONCE and v.get('ok') is False and
        v.get('business_success_verified') is False and v.get('whole_app_production_ready') is False,
        'EXACT_FAILED_PARENT_SOURCE_AND_SCOPE_REQUIRED')
  need(s.get('coordinator_result')==PARENTS['coordinator'],'ACTUAL_PARENT_COORDINATOR_CHAIN')
  need(c.get('flow')==str(FLOW) and c.get('package')=='tv.danmaku.bili' and c.get('uid')==10117 and
       c.get('helper_package')=='org.droidloom.qa.bili.r9' and c.get('helper_uid')==10152 and
       c.get('launch_worker_requested') is True and c.get('navigation_worker_requested') is False,
       'EXACT_FAILED_LAUNCH_WITHOUT_NAVIGATION')
  commands=c.get('retained_phase_commands');results=c.get('retained_phase_results')
  need(type(commands) is dict and set(commands)=={'launch'},'FIXED_RETAINED_LAUNCH_COMMAND_REQUIRED')
  need(type(results) is dict and set(results)<= {'launch'},'NO_UNREQUESTED_PHASE_PINS')
  exact_pin('launch_command',commands['launch'])
  if 'launch' in results:exact_pin('launch',results['launch'])
  for name,field in (('cleanup','cleanup_result'),('launch_scope','owned_scope')):
   if field in c:exact_pin(name,c[field])
  if 'launch_result' in c:
   need(c['launch_result']==results.get('launch'),'DUPLICATE_LAUNCH_PIN_DIFFERS')
  bindings['parent_chain']=True
  bindings['parent_Main_records_equal']=all(k in v for v,k in ((c,'Main_before'),(c,'Main_after'),(s,'Main_before'),(s,'Main_after'))) and c['Main_before']==c['Main_after']==s['Main_before']==s['Main_after']
  return commands,results
 chain=attempt('parent_chain',parents)
 command=stdout_worker=launch_worker=None
 if chain is not None:
  commands,results=chain
  command=attempt('launch_command',lambda:add('launch_command',commands['launch']))
  def command_scope():
   need(command is not None and command.get('name')=='02-launch' and
        command.get('argv')==['/usr/bin/python3','-I',str(ROOT/'source/owned_navigation.py'),'--worker-once','launch','--source-manifest-sha256',SOURCE_SHA],
        'EXACT_ORIGINAL_LAUNCH_COMMAND_SCOPE')
   for key in ('stdout','stderr'):
    p=command.get(key)
    need(type(p) is dict and set(p)=={'bytes','sha256'},'ORIGINAL_COMMAND_STREAM_PIN_REQUIRED:'+key)
    exact_pin('launch_'+key,{'path':str(FILES['launch_'+key]),**p},allow_empty=True)
   bindings['launch_command_scope']=True
   return True
  if attempt('launch_command_scope',command_scope):
   def stderr_read():
    raw=raw_read('launch_stderr',{'path':str(FILES['launch_stderr']),**command['stderr']})
    diagnostic['stderr']=stderr_projection(raw);bindings['stderr_parent_pin']=True
   attempt('launch_stderr',stderr_read)
   def stdout_read():
    raw=raw_read('launch_stdout',{'path':str(FILES['launch_stdout']),**command['stdout']})
    bindings['stdout_parent_pin']=True
    if not raw:
     diagnostic['stdout']={'empty':True,'JSON_worker_exported':False};return None
    try:value=json.loads(raw)
    except (json.JSONDecodeError,UnicodeDecodeError):
     diagnostic['stdout']={'empty':False,'JSON_worker_exported':False,'non_JSON_original_retained_private':True}
     return None
    need(type(value) is dict,'PRINTED_WORKER_OBJECT_REQUIRED')
    no_raw_ui(value);worker_binding(value)
    files['launch_stdout']={**observations['launch_stdout'],'text':raw.decode('utf-8','strict')}
    bindings['printed_worker_scope']=True
    return value
   stdout_worker=attempt('launch_stdout',stdout_read)
  if 'launch' in results:
   def phase_read():
    v=add('launch',results['launch']);worker_binding(v);bindings['durable_worker_scope']=True;return v
   launch_worker=attempt('launch',phase_read)
  for name,field in (('cleanup','cleanup_result'),('launch_scope','owned_scope')):
   if field in c:
    def child_read(name=name,field=field):
     add(name,c[field]);bindings[name+'_parent_pin']=True
    attempt(name,child_read)
  if stdout_worker is not None and launch_worker is not None:
   bindings['printed_and_durable_worker_equal']=stdout_worker==launch_worker
  for name in ('launch','cleanup','launch_scope','launch_attempted'):
   def probe(name=name):
    value=reader.access(name,False,optional=True)
    presence[name]={'path':str(FILES[name]),'present':False,'contents_read':False} if value is None else {'path':str(FILES[name]),**value}
   attempt('presence_'+name,probe)
 if reader.opened!=reader.closed:
  errors.append({'stage':'reader_fd_accounting','type':'RuntimeError','message':'ACQUIRED_DESCRIPTOR_CLOSE_NOT_COMPLETE','errno':None})
 bundle={'schema':1,'scope':'fixed-r9-player02-launch-failure-receipts-only','files':files,
  'observations':observations,'bindings':bindings,'fixed_path_presence':presence,'diagnostic':diagnostic,
  'errors':errors,'collection_complete':not errors,'source_manifest_sha256':SOURCE_SHA,'flow_nonce':NONCE,
  'bytes_read':reader.bytes,'reader_opened_fds':reader.opened,'reader_closed_fds':reader.closed,
  'reader_acquired_fds_closed':reader.opened==reader.closed,'raw_UI_or_commercial_journal_exported':False,
  'raw_stderr_exported':False,'Android_or_process_actions':0,'permission_or_original_file_changes':0,
  'runtime_qualification_asserted':False,'cleanup_or_UI_window_release_claimed_by_reader':False,
  'no_launch_or_navigation_replay':True,'child_hashes_derived_only_from_exact_external_parent_bytes':True,
  'fixed_presence_probes_do_not_qualify_contents_or_task_state':True,'read_is_sequential_not_atomic':True}
 raw=(json.dumps(bundle,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
 need(len(raw)<=3145728,'SUMMARY_BUNDLE_BOUND')
 print(json.dumps({'schema':1,'encoding':'base64','private_UI_data':False,
  'uncompressed_bytes':len(raw),'uncompressed_sha256':sha(raw),'data':base64.b64encode(raw).decode('ascii')},sort_keys=True),flush=True)
 return 0 if not errors else 1
if __name__=='__main__':raise SystemExit(collect())
