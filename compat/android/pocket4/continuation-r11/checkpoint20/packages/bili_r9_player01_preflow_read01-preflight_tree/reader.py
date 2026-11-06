import hashlib,json,os,stat,time
ROOT='/home/alex/work/pocket4-bilibili-r9-pause-resume-01'
FLOW='/home/alex/work/pocket4-bilibili-owned-qa-r9-flow-fc02c98cd9a6fbf64ad55cc2c180d0df'
EXPECTED={'coordinator.json':(ROOT+'/result.json',2070,'cf209852df643dfe92c8520c01808f3a010c51494e10be1b107990a72325bceb'),'stage.json':(ROOT+'/stage-result.json',2665,'025810092ad322df0bee342853e5b893e07cb546283f2026c59d606565a6bf38')}
assert os.getuid()==os.geteuid()==0
deadline=time.monotonic()+8
def read(path,size,digest):
 fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
 try:
  before=os.fstat(fd)
  assert stat.S_ISREG(before.st_mode) and before.st_uid==0 and before.st_nlink==1 and before.st_size==size<=8192
  raw=b''
  while len(raw)<=size:
   assert time.monotonic()<deadline
   part=os.read(fd,min(4096,size+1-len(raw)))
   if not part:break
   raw+=part
  after=os.fstat(fd)
  assert (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
  assert len(raw)==size and hashlib.sha256(raw).hexdigest()==digest
  return raw.decode('utf-8','strict')
 finally:os.close(fd)
files={name:{'path':path,'bytes':size,'sha256':sha,'text':read(path,size,sha)} for name,(path,size,sha) in EXPECTED.items()}
c=json.loads(files['coordinator.json']['text']);s=json.loads(files['stage.json']['text'])
assert c['ok'] is False and c['error']=={'phase':'coordinator','type':'ProtocolError','message':'EXACT_R8_REVEAL_PROTOCOL_REQUIRED'} and c['secondary_errors']==[]
assert c['nonce']=='fc02c98cd9a6fbf64ad55cc2c180d0df' and c['flow']==FLOW
assert all(c[key] is False for key in ('launch_worker_requested','navigation_worker_requested','cleanup_requested','business_success_verified','whole_app_production_ready'))
assert c['business_outcome_unknown'] is True and c['source_and_artifact_unchanged'] is True
assert s['ok'] is False and s['secondary_errors']==[] and s['source_unchanged'] is True
assert s['coordinator_result']=={key:files['coordinator.json'][key] for key in ('path','bytes','sha256')}
assert s['error']=={'phase':'stage_or_coordinator','type':'RuntimeError','message':'OWNED_BUTTON_TRANSITIONS_CLEANUP_NOT_QUALIFIED'}
absence={}
for path in (FLOW,ROOT+'/evidence/01-init.result.json',ROOT+'/evidence/02-launch.result.json',ROOT+'/evidence/03-navigate.result.json'):
 assert time.monotonic()<deadline
 try:os.lstat(path)
 except FileNotFoundError:absence[path]=True
 else:raise RuntimeError('FIXED_PRE_ACTION_PATH_ALREADY_EXISTS')
out={'schema':1,'kind':'bili-r9-player01-preflow-protocol-failure-read01','files':files,'fixed_paths_absent':absence,'Android_commands':0,'process_actions':0,'raw_UI_exported':False,'unknown_outcome_original_preserved':True,'owned_read_FDs_closed':True}
encoded=json.dumps(out,sort_keys=True,separators=(',',':'))
assert len(encoded.encode())<=16384
print(encoded,flush=True)
