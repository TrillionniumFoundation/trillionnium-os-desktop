#!/usr/bin/env python3
"""Five exact user-unit observations and immutable APK source evidence readback only."""
import os,json,stat,hashlib,pathlib,subprocess,resource,sys,time,re,signal,threading
P=pathlib.Path
ROOT=P('/home/qq/work/p4-szzc-current-source-5cd1-20261119-r1')
UNITS=('p4-szzc-current-download-5cd1-r1.service','p4-szzc-current-resume-5cd1-r1.service','p4-szzc-current-resume2-5cd1-r1.service','p4-szzc-current-sdk37-5cd1-r1.service','p4-szzc-current-sdk37-5cd1-r2.service')
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
 specs=[('original_failed_transport',ROOT/'download/TRANSPORT-RESULT.json',2031,'25c53c96e6cccbd90479d023e9d0e60e955fd0d7485c750bb32171fe5bdf2b07'),('first_failed_resume',ROOT/'download/RESUME-TRANSPORT-RESULT.json',4818,'b8ee3b641bdfdce72a1e0cdab1f9f2af057af0a415e5a82397876676dc4c5ce8'),('resumed_transport',ROOT/'download/RESUME2-TRANSPORT-RESULT.json',rs,sys.argv[1]),('prior_failed_sdk',ROOT/'qualification/RESULT.json',13681,'39b9ef57cb36527de9caf1b4002f1776ad7cdd0bf5a4628fa5978b2b9dd30b82'),('sdk_qualification',ROOT/'qualification-r2/RESULT.json',ss,sys.argv[3])]
 pins={};docs={}
 for role,path,size,digest in specs:
  p,b=read(path,{'bytes':size,'sha256':digest},keep=True);pins[role]=p;docs[role]=json.loads(b)
 failed,resume,sdk=(docs[x] for x in ('original_failed_transport','resumed_transport','sdk_qualification'))
 need(failed['complete'] is False and failed['total_bytes_received_before_terminal']==58720256,'real original bounded failure retained')
 failed_range=docs['first_failed_resume'];need(failed_range['complete'] is False and failed_range['actual_inode_size_at_terminal']==168361302 and failed_range['all_three_input_bookends_unchanged'] is True,'real first Range failure retained without source credit')
 need(resume['schema']=='pocket4-szzc-observed-publisher-candidate-range-transport-v2' and resume['complete'] is True and resume['source_identity_verified'] is False and resume['signature_verified'] is False,'actual complete transport only')
 need(resume['full_SHA_readback_verified'] and resume['prefix_SHA_readback_unchanged'] and resume['same_inode_append_only'] and resume['all_five_input_bookends_unchanged'] and resume['tail_bytes_downloaded']==52137116 and resume['prefix_bytes_redownloaded']==0,'actual same-inode source chain')
 prior_sdk=docs['prior_failed_sdk']
 need(prior_sdk['success'] is False and prior_sdk['source_identity_verified'] is False and prior_sdk['SDK_commands']==[] and prior_sdk['error']=="ValueError('native ELF machine mismatches directory ABI')",'preserved original strict SDK failure')
 need(sdk['prior_failed_SDK']==pins['prior_failed_sdk'],'new SDK is explicitly bound to original failed qualification')
 need(sdk['schema']=='pocket4-szzc-current-publisher-source-qualification-v1' and sdk['success'] is True and sdk['source_identity_verified'] is True and sdk['package']=='com.szzc','actual SDK source identity only')
 for d in (resume,sdk):
  need(d['runtime_qualified'] is False and d['business_qualified'] is False and d['production_ready'] is False,'no source-to-runtime promotion')
 need(sdk['installed'] is False and sdk['current_input_selected'] is False and sdk['existing_selected_APK_changed'] is False and sdk['existing_registry_changed'] is False,'current package and registry preserved')
 need(sdk['worker_source']['sha256']=='a532640ead889c0b73345b45c9ddab7d34bc5eccb157d473222d6b099b2e4b7c' and sdk['reviewed_helper_source']['sha256']=='b75a440ab7707032a22c28a621d9df254e416b8170f9b1a9d96429ecf30e462d','actual reviewed worker/helper identities')
 source_pins=[]
 for role in ('worker_source','reviewed_helper_source'):
  pp,unused=read(sdk[role]['path'],sdk[role]);source_pins.append(pp)
 diagpin=sdk['original_native_inventory_diagnostic']
 need(diagpin['path']==str(ROOT/'NATIVE-INVENTORY-DIAGNOSTIC.json') and diagpin['bytes']==91834 and diagpin['sha256']=='6ca274d5ecfa097ad67a50ab4a5aacdcf2bb0f2ed26d74067acc2ab9b04fc4fd','exact original native diagnostic')
 dp,db=read(diagpin['path'],diagpin,keep=True);diagnostic=json.loads(db)
 cmds=sdk['SDK_commands'];need(len(cmds)==3 and [x['name'] for x in cmds]==['szzc-badging','szzc-manifest','szzc-signature'],'exact three SDK commands')
 logs=[]
 for cmd in cmds:
  need(cmd['exit']==0 and cmd['actual_child_reaped'] and cmd['original_pidfd_held_until_reaped'] and cmd['after_reap_echild'] and cmd['output_complete'] and not cmd.get('termination'),'actual SDK child complete retirement')
  for channel in ('stdout','stderr'):
   q=cmd[channel];path=ROOT/'qualification-r2/logs'/(cmd['name']+'.'+channel);need(q['path']==str(path),'exact original SDK log path');pp,unused=read(path,q);logs.append(pp)
 need(sdk['remaining_children']=='' and sdk['candidate_full_disk_SHA_readback_verified'] and sdk['bookends'] and all(x['F9_and_full_SHA_equal'] is True for x in sdk['bookends']),'complete actual source/worker/tool/input bookends')
 before=dict(x.split() for x in sdk['memory_events_before'].splitlines());after=dict(x.split() for x in sdk['memory_events_after'].splitlines());need(all(before[k]==after[k] for k in ('oom','oom_kill','oom_group_kill')),'actual OOM counters unchanged')
 artifact=resume['artifact'];candidate=sdk['candidate'];apk=ROOT/'download/com.szzc.publisher-current.apk'
 need(candidate['path']==artifact['path']==str(apk) and candidate['bytes']==artifact['bytes']==220498418 and candidate['sha256']==artifact['sha256'] and candidate['identity']==artifact['identity'],'transport/SDK same complete candidate')
 ap,unused=read(apk,candidate,limit=256*1024**2)
 proof=sdk['source_receipt'];need(proof['path']==str(ROOT/'qualification-r2/receipts/com.szzc.json'),'exact original source proof')
 pp,body=read(proof['path'],proof,keep=True);receipt=json.loads(body)
 need(receipt['commands']==cmds and receipt['source_identity_verified'] and receipt['source_qualification_is_conditional_on_successful_terminal_RESULT_and_all_bookends'] and receipt['required_terminal_RESULT_path']==pins['sdk_qualification']['path'],'qualified source proof bound to actual successful terminal')
 need(receipt['APK']==candidate and receipt['signer_certificate_sha256']==sdk['signer_certificate_sha256']==['d85bed4d2a7c08e1b6b5f0097d6c66a79a5b12b58d97e794d3b5c5bff2aeaf44'],'candidate and historical signer source identity')
 need(receipt['all_ZIP_members_CRC_and_SHA_verified'] and len(receipt['complete_zip_members'])==sdk['complete_ZIP_member_count'] and len(receipt['native_members'])==sdk['native_member_count'],'complete original ZIP and native proof cardinality')
 cross=receipt['cross_ABI_source_members'];native=receipt['native_members']
 expected={
 'lib/arm64-v8a/libexecmain_x86.so':(211616,'f2358a1888e0321f773875cffdce6629b3987f5237aca10d80bb4b51cfbee0ad',2,62,'x86_64'),
 'lib/arm64-v8a/libexec_x86.so':(667144,'7ad636af838b62daa7fb02bb440504c46b58d03040aee4bdb137b2686d5e7f89',2,62,'x86_64'),
 'lib/armeabi-v7a/libexecmain_x86.so':(132520,'937776804511269ce1d0c375fdac2d4ac3dfba6704bdf59a8e1be83851cd1cfb',1,3,'x86'),
 'lib/armeabi-v7a/libexec_x86.so':(556824,'db40145f67b021701ede31205357fc81e69a67825f061bc9d01e9bd739d79bd4',1,3,'x86')}
 need(ap['sha256']=='1461b66c3dc3497989eb4a71361b56584dca1caa6b8120ebc5c4c1f240782c03' and diagnostic['APK']==ap,'same exact whole APK bound to original diagnostic')
 need(len(native)==118 and len({x['name'] for x in native})==118 and len(cross)==4 and {x['name'] for x in cross}==set(expected),'exact complete native inventory and four cross-ABI source facts')
 need(cross==sdk['cross_ABI_source_members'] and receipt['original_native_inventory_diagnostic']==dp and receipt['prior_failed_SDK']==pins['prior_failed_sdk'],'source receipt/terminal diagnostic and original failure joins')
 for row in cross:
  need((row['bytes'],row['sha256'],row['elf_class'],row['elf_machine'],row['actual_ELF_ABI'])==expected[row['name']],'exact cross-ABI member body and actual ELF identity')
  need(row['directory_ABI_matches_ELF'] is False and row['generic_native_guard_passed'] is False and row['cross_ABI_source_inventory_only'] is True and row['native_runtime_blocker_retained'] is True and row['execution_qualified'] is False,'cross-ABI mismatch cannot become a native qualification')
 need([x for x in native if x['name'] in expected]==cross and all(x['generic_native_guard_passed'] is True and x['directory_ABI_matches_ELF'] is True and x['execution_qualified'] is False for x in native if x['name'] not in expected),'other114 retain generic guard without execution')
 selected_cross=[x for x in cross if x['abi']=='arm64-v8a']
 for obj in (receipt,sdk):
  need(obj['cross_ABI_source_member_count']==4 and obj['selected_arm64_directory_cross_ABI_member_count']==2 and obj['selected_arm64_directory_cross_ABI_members']==selected_cross and obj['generic_native_guard_passed_member_count']==114,'both selected-directory cross-ABI files remain explicit')
  need(obj['native_source_layout_qualified'] is False and obj['all_native_members_match_directory_ABI'] is False and obj['generic_native_validator_changed'] is False and obj['native_runtime_blocker_retained'] is True and obj['native_compatibility_qualified'] is False,'native layout/runtime blocker remains after source identity checks')
  need(obj['actual_native_ELF_ABIs']==['arm64-v8a','armeabi-v7a','x86','x86_64'],'actual complete native ELF ABIs are distinct from packaging directories')
 need(sdk['signature_manifest_identity_verified'] is True,'source signature/manifest identity explicitly verified')
 for p in pins.values():read(p['path'],p)
 for x in rows:absent(x['expected_cgroup_path'])
 print(json.dumps({'schema':'pocket4-szzc-source-independent-retirement-raw-v3','passed':True,'all_five_units_retired':True,'units':rows,'terminal_pins':pins,'original_download_failed_without_source_credit':True,'first_resume_failed_without_source_credit':True,'actual_candidate':ap,'candidate_full_post_retirement_SHA_F9_verified':True,'source_receipt':pp,'SDK_log_pins':logs,'source_pins':source_pins,'original_native_diagnostic':dp,'original_strict_SDK_failure_retained':True,'cross_ABI_source_member_count':4,'selected_arm64_directory_cross_ABI_member_count':2,'native_runtime_blocker_retained':True,'native_source_layout_qualified':False,'native_compatibility_qualified':False,'all_three_SDK_children_pidfd_reaped_echild':True,'SDK_recorded_full_input_bookends_passed':True,'SDK_recorded_OOM_counters_unchanged':True,'package':'com.szzc','version_name':sdk['version_name'],'version_code':sdk['version_code'],'long_version_code':sdk['long_version_code'],'version_comparison_to_actual_current329':sdk['version_comparison_to_actual_current329'],'signer_certificate_sha256':sdk['signer_certificate_sha256'],'complete_zip_members':sdk['complete_ZIP_member_count'],'native_member_count':sdk['native_member_count'],'current_input_selected':False,'installed':False,'runtime_qualified':False,'business_qualified':False,'production_ready':False,'source_mutations':0,'original_client_exit_still_requires_separate_exact_client_observation':True,'observed_ns':time.time_ns(),'elapsed_seconds':time.monotonic()-START},sort_keys=True),flush=True)
if __name__=='__main__':main()
