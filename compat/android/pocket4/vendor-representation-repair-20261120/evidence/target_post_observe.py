import hashlib,json,os,stat,subprocess,time
from pathlib import Path
INPUT={'units': [['hepta-terminal-dpty-192b8b17dd90e9b0949239158fa494e02a2cc4767b86fdb58fc61c7fd5da77a8.service', [3590473, 3590474, 3590476]], ['hepta-terminal-dpty-717870fcb484d52e846882b11df5aaf5b9219e61e3458cb475fa04cd9a515968.service', [3589403, 3589404]]], 'references': {'git': {'bytes': 4547768, 'identity': [66306, 82183527, 33261, 0, 0, 1, 4547768, 1792159905000000000, 1792537019083632668], 'path': '/usr/bin/git', 'sha256': 'ed8b2df973b28c0fb773b9c0dc0816d3ee2b3835bb932d9153c21417bb51b362'}, 'stdout': {'bytes': 240, 'identity': [66306, 59510161, 33152, 1000, 1000, 1, 240, 1795153667776873271, 1795153667776873271], 'path': '/home/qq/work/p4-text-auto-controls-20261120-9907-r1/controls.stdout', 'sha256': 'eeee69175d10516837fd643182cc5784161f371217fa1ad0441df1fae39483bb'}, 'stderr': {'bytes': 5483, 'identity': [66306, 59510162, 33152, 1000, 1000, 1, 5483, 1795153667747874344, 1795153667747874344], 'path': '/home/qq/work/p4-text-auto-controls-20261120-9907-r1/controls.stderr', 'sha256': '27d359bcc83c428a9b4709ac96931e8f886673e34b973ca82c0bef876768b1b4'}, 'controls': {'bytes': 2801935, 'identity': [66306, 59510163, 33152, 1000, 1000, 1, 2801935, 1795153667776873271, 1795153667776873271], 'path': '/home/qq/work/p4-text-auto-controls-20261120-9907-r1/CONTROLS.json', 'sha256': '05644e54c89d95ba4fff3c3cf8dc1ec77b39c035ecdb8010f11cbd0800d4dbe8'}, 'controls_gzip': {'bytes': 118754, 'identity': [66306, 59510164, 33152, 1000, 1000, 1, 118754, 1795153667860459171, 1795153667860459171], 'path': '/home/qq/work/p4-text-auto-controls-20261120-9907-r1/CONTROLS.json.gz', 'sha256': '74f38d05356e3111b3f5a57ed0dc5fa03d756cec92d359a6d135a547b8fab49e'}, 'target_execution': {'bytes': 6749, 'identity': [66306, 59510165, 33152, 1000, 1000, 1, 6749, 1795153667874974884, 1795153667874974884], 'path': '/home/qq/work/p4-text-auto-controls-20261120-9907-r1/TARGET-EXECUTION.json', 'sha256': '77f674b8f02fe06e5c464038d51c622a0a9a0ec98115940f080313af748bc73c'}, 'helper': {'bytes': 29338, 'identity': [66306, 59510142, 33152, 1000, 1000, 1, 29338, 1795153664395859096, 1795153664395859096], 'path': '/home/qq/work/p4-text-auto-controls-20261120-9907-r1/vendor_source_bookends_text_auto_9907.py', 'sha256': 'bab5c377bf642d4aaa7b50a416319cebad31537022e5179a77e6e8d63827fa88'}, 'original_client_stdout': {'path': '/home/qq/.local/state/hepta-runtime-mac-worker/terminals/dpty-192b8b17dd90e9b0949239158fa494e02a2cc4767b86fdb58fc61c7fd5da77a8/output.log', 'bytes': 987, 'sha256': '328ce7337019016df1a0a7c087bc688b0821cb9d22acf1339f8586e0b2746546'}}, 'client': {'host': 'ai395', 'session_id': 'dpty-192b8b17dd90e9b0949239158fa494e02a2cc4767b86fdb58fc61c7fd5da77a8', 'status': {'boot': 'b1620269-aaef-43e7-bf47-bc6eb1c1a447', 'bytes_seen': 987, 'bytes_stored': 987, 'capture_error': None, 'closed': False, 'created_unix_ms': 1795153664373, 'exit_code': 0, 'output_complete': True, 'owner_pid': 3590473, 'pid': 3590474, 'state': 'exited'}}}
assert os.getuid()==os.geteuid()==1000
def f9(s):return [s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
def reference(value):
 p=Path(value['path']);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  before=f9(os.fstat(fd));assert stat.S_ISREG(before[2]);h=hashlib.sha256();n=0
  while True:
   block=os.read(fd,1024*1024)
   if not block:break
   n+=len(block);h.update(block)
  assert before==f9(os.fstat(fd))==f9(p.lstat()) and n==before[6]
  out={'path':str(p),'bytes':n,'sha256':h.hexdigest(),'identity':before}
  assert all(out[k]==v for k,v in value.items())
  return out
 finally:os.close(fd)
started=time.time_ns();targets=[]
expected={'LoadState':'not-found','ActiveState':'inactive','SubState':'dead','MainPID':'0','ControlGroup':'','InvocationID':''}
for name,pids in INPUT['units']:
 for pid in pids:assert not os.path.lexists('/proc/'+str(pid))
 argv=['/usr/bin/systemctl','--user','show',name,'--property=LoadState,ActiveState,SubState,MainPID,ControlGroup,InvocationID']
 child=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 pidfd=os.pidfd_open(child.pid)
 try:
  stdout,stderr=child.communicate(timeout=15);assert child.returncode==0 and stderr==b''
 finally:os.close(pidfd)
 fields=dict(line.split('=',1) for line in stdout.decode().splitlines());assert fields==expected
 paths=['/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/'+name,'/sys/fs/cgroup/system.slice/'+name]
 assert all(not os.path.lexists(path) for path in paths)
 targets.append({'unit':name,'pids':[{'pid':pid,'exists':False} for pid in pids],
  'unit_observation':{'argv':argv,'exit_code':child.returncode,'stdout':stdout.decode(),'stderr':'','properties':fields,
                      'actual_child_reaped':True,'original_pidfd_held_until_reaped':True},
  'absent_cgroup_paths':paths})
refs={name:reference(value) for name,value in INPUT['references'].items()}
temporary=Path('/home/qq/work/p4-text-auto-controls-20261120-9907-r1/tmp')
assert temporary.resolve()==temporary and temporary.is_dir() and not any(temporary.iterdir())
report={'schema':'p4-text-auto-ai395-target-retirement-v1','observed_ns':started,'finished_ns':time.time_ns(),
 'host':'ai395','uid':1000,'read_only':True,'source_mutations':False,'errors':[],
 'targets':targets,'references':refs,'all_original_input_and_result_bodies_and_F9_unchanged':True,
 'temporary_fixture_root_empty':True,'original_client':INPUT['client'],
 'original_client_stdout':refs['original_client_stdout'],'runtime_qualified':False,'production_ready':False}
print(json.dumps(report,sort_keys=True),flush=True)
