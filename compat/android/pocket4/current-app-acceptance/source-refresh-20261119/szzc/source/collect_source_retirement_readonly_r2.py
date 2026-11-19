#!/usr/bin/env python3
"""Four exact user-unit observations and immutable APK evidence readback only."""
import os,json,stat,hashlib,pathlib,subprocess,resource,sys,time,re,signal,threading
P=pathlib.Path
ROOT=P('/home/qq/work/p4-szzc-current-source-5cd1-20261119-r1')
UNITS=('p4-szzc-current-download-5cd1-r1.service','p4-szzc-current-resume-5cd1-r1.service','p4-szzc-current-resume2-5cd1-r1.service','p4-szzc-current-sdk37-5cd1-r1.service')
CG=P('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice')
START=time.monotonic()
def need(ok,msg):
 if not ok:raise RuntimeError(msg)
def check():need(time.monotonic()-START<60,'independent readonly deadline')
def f9(s):return [str(x) for x in (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)]
def read(path,expected=None,keep=False,limit=16*1024**2):
 check();p=P(path);need(p.resolve(strict=True)==p,'canonical known evidence input')
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  s=os.fstat(fd);before=f9(s)
  need(stat.S_ISREG(s.st_mode) and s.st_uid==s.st_gid==1000 and s.st_nlink==1 and not s.st_mode&0o6000 and 0<=s.st_size<=limit,'bounded ordinary source evidence')
  h=hashlib.sha256();n=0;parts=[]
  while True:
   check();b=os.read(fd,1024*1024)
   if not b:break
   h.update(b);n+=len(b)
   if keep:parts.append(b)
  need(n==s.st_size and f9(os.fstat(fd))==before==f9(p.lstat()),'whole stable source evidence')
  pin={'path':str(p),'bytes':n,'sha256':h.hexdigest(),'identity':before}
  if expected is not None:
   need(pin['bytes']==expected['bytes'] and pin['sha256']==expected['sha256'],'exact evidence bytes/SHA')
   if 'identity' in expected:need(pin['identity']==expected['identity'],'exact evidence full F9')
  return pin,b''.join(parts) if keep else None
 finally:os.close(fd)
def absent(path):
 try:os.lstat(path)
 except FileNotFoundError:return True
 raise RuntimeError('expected exact original cgroup absent: '+str(path))
def unit(unit):
 check();argv=['/usr/bin/systemctl','--user','show',unit,'--property=LoadState,ActiveState,SubState,MainPID,ControlGroup']
 env=os.environ.copy();env['XDG_RUNTIME_DIR']='/run/user/1000';env['DBUS_SESSION_BUS_ADDRESS']='unix:path=/run/user/1000/bus'
 child=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
 pidfd=None
 try:
  pidfd=os.pidfd_open(child.pid);out,err=child.communicate(timeout=8)
  need(child.returncode==0 and not err and len(out)<=8192,'complete exact metadata child')
  fields=dict(x.split('=',1) for x in out.decode().splitlines())
  need(fields=={'LoadState':'not-found','ActiveState':'inactive','SubState':'dead','MainPID':'0','ControlGroup':''},'original exact user unit retired')
  path=CG/unit;absent(path)
  return {'name':unit,'unit_properties':fields,'expected_cgroup_path':str(path),'cgroup_exists':False,'argv':argv,'stdout':out.decode(),'stderr':err.decode(),'exit_code':0,'pid':child.pid,'original_pidfd_held_until_reaped':True,'actual_child_reaped':True}
 finally:
  if child.poll() is None:child.kill();child.wait(timeout=3)
  if pidfd is not None:os.close(pidfd)
  child.stdout.close();child.stderr.close()
def main():
 need(os.getuid()==os.geteuid()==1000,'ordinary qq observation')
 need(signal.getsignal(signal.SIGCHLD)==signal.SIG_DFL and threading.get_native_id()==os.getpid() and os.listdir('/proc/self/task')==[str(os.getpid())],'default SIGCHLD and single original main thread')
 os.sched_setaffinity(0,{31});resource.setrlimit(resource.RLIMIT_AS,(128*1024**2,128*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(20,25));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
 need(len(sys.argv)==5 and re.fullmatch('[0-9a-f]{64}',sys.argv[1]) and re.fullmatch('[0-9a-f]{64}',sys.argv[3]),'exact actual resume/SDK terminal SHA and sizes')
 rs,ss=int(sys.argv[2]),int(sys.argv[4]);need(1<=rs<=65536 and 1<=ss<=16*1024**2,'terminal size bounds')
 rows=[unit(x) for x in UNITS]
 specs=[('original_failed_transport',ROOT/'download/TRANSPORT-RESULT.json',2031,'25c53c96e6cccbd90479d023e9d0e60e955fd0d7485c750bb32171fe5bdf2b07'),('first_failed_resume',ROOT/'download/RESUME-TRANSPORT-RESULT.json',4818,'b8ee3b641bdfdce72a1e0cdab1f9f2af057af0a415e5a82397876676dc4c5ce8'),('resumed_transport',ROOT/'download/RESUME2-TRANSPORT-RESULT.json',rs,sys.argv[1]),('sdk_qualification',ROOT/'qualification/RESULT.json',ss,sys.argv[3])]
 pins={};docs={}
 for role,path,size,digest in specs:
  p,b=read(path,{'bytes':size,'sha256':digest},keep=True);pins[role]=p;docs[role]=json.loads(b)
 failed,resume,sdk=(docs[x] for x in ('original_failed_transport','resumed_transport','sdk_qualification'))
 need(failed['complete'] is False and failed['total_bytes_received_before_terminal']==58720256,'real original bounded failure retained')
 failed_range=docs['first_failed_resume'];need(failed_range['complete'] is False and failed_range['actual_inode_size_at_terminal']==168361302 and failed_range['all_three_input_bookends_unchanged'] is True,'real first Range failure retained without source credit')
 need(resume['schema']=='pocket4-szzc-observed-publisher-candidate-range-transport-v2' and resume['complete'] is True and resume['source_identity_verified'] is False and resume['signature_verified'] is False,'actual complete transport only')
 need(resume['full_SHA_readback_verified'] and resume['prefix_SHA_readback_unchanged'] and resume['same_inode_append_only'] and resume['all_five_input_bookends_unchanged'] and resume['tail_bytes_downloaded']==52137116 and resume['prefix_bytes_redownloaded']==0,'actual same-inode source chain')
 need(sdk['schema']=='pocket4-szzc-current-publisher-source-qualification-v1' and sdk['success'] is True and sdk['source_identity_verified'] is True and sdk['package']=='com.szzc','actual SDK source identity only')
 for d in (resume,sdk):
  need(d['runtime_qualified'] is False and d['business_qualified'] is False and d['production_ready'] is False,'no source-to-runtime promotion')
 need(sdk['installed'] is False and sdk['current_input_selected'] is False and sdk['existing_selected_APK_changed'] is False and sdk['existing_registry_changed'] is False,'current package and registry preserved')
 need(sdk['worker_source']['sha256']=='fb9cd65a6f33f699099e8c71c9b9e7b5c7b5c17659a55f67b71006291600612d' and sdk['reviewed_helper_source']['sha256']=='b75a440ab7707032a22c28a621d9df254e416b8170f9b1a9d96429ecf30e462d','actual reviewed worker/helper identities')
 cmds=sdk['SDK_commands'];need(len(cmds)==3 and [x['name'] for x in cmds]==['szzc-badging','szzc-manifest','szzc-signature'],'exact three SDK commands')
 logs=[]
 for cmd in cmds:
  need(cmd['exit']==0 and cmd['actual_child_reaped'] and cmd['original_pidfd_held_until_reaped'] and cmd['after_reap_echild'] and cmd['output_complete'] and not cmd.get('termination'),'actual SDK child complete retirement')
  for channel in ('stdout','stderr'):
   q=cmd[channel];path=ROOT/'qualification/logs'/(cmd['name']+'.'+channel);need(q['path']==str(path),'exact original SDK log path');pp,unused=read(path,q);logs.append(pp)
 need(sdk['remaining_children']=='' and sdk['candidate_full_disk_SHA_readback_verified'] and sdk['bookends'] and all(x['F9_and_full_SHA_equal'] is True for x in sdk['bookends']),'complete actual source/worker/tool/input bookends')
 before=dict(x.split() for x in sdk['memory_events_before'].splitlines());after=dict(x.split() for x in sdk['memory_events_after'].splitlines());need(all(before[k]==after[k] for k in ('oom','oom_kill','oom_group_kill')),'actual OOM counters unchanged')
 artifact=resume['artifact'];candidate=sdk['candidate'];apk=ROOT/'download/com.szzc.publisher-current.apk'
 need(candidate['path']==artifact['path']==str(apk) and candidate['bytes']==artifact['bytes']==220498418 and candidate['sha256']==artifact['sha256'] and candidate['identity']==artifact['identity'],'transport/SDK same complete candidate')
 ap,unused=read(apk,candidate,limit=256*1024**2)
 proof=sdk['source_receipt'];need(proof['path']==str(ROOT/'qualification/receipts/com.szzc.json'),'exact original source proof')
 pp,body=read(proof['path'],proof,keep=True);receipt=json.loads(body)
 need(receipt['commands']==cmds and receipt['source_identity_verified'] and receipt['source_qualification_is_conditional_on_successful_terminal_RESULT_and_all_bookends'] and receipt['required_terminal_RESULT_path']==pins['sdk_qualification']['path'],'qualified source proof bound to actual successful terminal')
 need(receipt['APK']==candidate and receipt['signer_certificate_sha256']==sdk['signer_certificate_sha256']==['d85bed4d2a7c08e1b6b5f0097d6c66a79a5b12b58d97e794d3b5c5bff2aeaf44'],'candidate and historical signer source identity')
 need(receipt['all_ZIP_members_CRC_and_SHA_verified'] and len(receipt['complete_zip_members'])==sdk['complete_ZIP_member_count'] and len(receipt['native_members'])==sdk['native_member_count'],'complete original ZIP and native proof cardinality')
 for p in pins.values():read(p['path'],p)
 for x in rows:absent(x['expected_cgroup_path'])
 print(json.dumps({'schema':'pocket4-szzc-source-independent-retirement-raw-v2','passed':True,'all_four_units_retired':True,'units':rows,'terminal_pins':pins,'original_download_failed_without_source_credit':True,'first_resume_failed_without_source_credit':True,'actual_candidate':ap,'candidate_full_post_retirement_SHA_F9_verified':True,'source_receipt':pp,'SDK_log_pins':logs,'all_three_SDK_children_pidfd_reaped_echild':True,'SDK_recorded_full_input_bookends_passed':True,'SDK_recorded_OOM_counters_unchanged':True,'package':'com.szzc','version_name':sdk['version_name'],'version_code':sdk['version_code'],'long_version_code':sdk['long_version_code'],'version_comparison_to_actual_current329':sdk['version_comparison_to_actual_current329'],'signer_certificate_sha256':sdk['signer_certificate_sha256'],'complete_zip_members':sdk['complete_ZIP_member_count'],'native_member_count':sdk['native_member_count'],'current_input_selected':False,'installed':False,'runtime_qualified':False,'business_qualified':False,'production_ready':False,'source_mutations':0,'original_client_exit_still_requires_separate_exact_client_observation':True,'observed_ns':time.time_ns(),'elapsed_seconds':time.monotonic()-START},sort_keys=True),flush=True)
if __name__=='__main__':main()
