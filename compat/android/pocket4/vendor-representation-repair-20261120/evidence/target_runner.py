import gzip,hashlib,io,json,os,signal,stat,subprocess,sys,tarfile,time
from pathlib import Path,PurePosixPath

BASE=Path('/home/qq/work/p4-text-auto-controls-20261120-9907-r1')
PACKET=BASE/'target-test-packet.tar.gz'
MANIFEST={'Android_actions': False, 'files': [{'bytes': 29338, 'path': 'vendor_source_bookends_text_auto_9907.py', 'sha256': 'bab5c377bf642d4aaa7b50a416319cebad31537022e5179a77e6e8d63827fa88'}, {'bytes': 26778, 'path': 'baseline/vendor_source_bookends_r19_9907.py', 'sha256': '89c48f7fe7147db9ea8cb2309a3a3ae08ce4203ab63546fbe06db6d0764efe56'}, {'bytes': 19252, 'path': 'test_text_auto.py', 'sha256': '82b1767271853f9747e720075cd7506744efc5008ac083fbac6c41d05a474495'}, {'bytes': 477330, 'path': 'fixtures/actual-conversions.json.gz', 'sha256': 'f9e00af7c0fff3e580e5f10ea951c11dec278645c48885c975a0344f88d91977'}, {'bytes': 18856, 'path': 'legacy-test-suite/test_committed_crlf.py', 'sha256': 'd99bb44144a1f21018fd6a9007863c1af1d3ada2f9e429ad38c2a5f21e3c0435'}, {'bytes': 26545, 'path': 'legacy-test-suite/baseline/vendor_source_bookends_r18_2331.py', 'sha256': '95511da9a71294064259935a6917c2c8fcbf2d96307d84e1b2085f060f61ebb8'}, {'bytes': 26778, 'path': 'legacy-test-suite/vendor_source_bookends_r19_9907.py', 'sha256': '89c48f7fe7147db9ea8cb2309a3a3ae08ce4203ab63546fbe06db6d0764efe56'}, {'bytes': 377, 'path': 'legacy-test-suite/fixtures/autogen.bat.working', 'sha256': '8e5832cadb90219c1f99d016b5628ac87af887f52a99270d431e65db71fa20f5'}, {'bytes': 186, 'path': 'legacy-test-suite/fixtures/libopus.gitattributes', 'sha256': '8849b586b02d3be0144ce83a5fdcb6fefb6825a85b1dbcb8b660acb8db5e6bd2'}], 'operational_source_mutations': False, 'schema': 'p4-text-auto-target-test-packet-v1', 'test_deadline_seconds': 180}
EXPECTED_GIT={'bytes': 4547768, 'identity': [66306, 82183527, 33261, 0, 0, 1, 4547768, 1792159905000000000, 1792537019083632668], 'path': '/usr/bin/git', 'sha256': 'ed8b2df973b28c0fb773b9c0dc0816d3ee2b3835bb932d9153c21417bb51b362'}
assert os.getuid()==os.geteuid()==1000
assert BASE.resolve()==BASE and BASE.lstat().st_ino==59510139 and stat.S_ISDIR(BASE.lstat().st_mode)
started=time.time_ns()
def f9(s):return [s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
def reference(path):
 p=Path(path);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  before=f9(os.fstat(fd));assert stat.S_ISREG(before[2]);h=hashlib.sha256();n=0
  while True:
   block=os.read(fd,1024*1024)
   if not block:break
   n+=len(block);h.update(block)
  assert before==f9(os.fstat(fd))==f9(p.lstat()) and n==before[6]
  return {'path':str(p),'bytes':n,'sha256':h.hexdigest(),'identity':before}
 finally:os.close(fd)
def save(path,value):
 data=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
 with Path(path).open('xb') as output:output.write(data);output.flush();os.fsync(output.fileno())
 return reference(path)
packet=reference(PACKET)
assert packet['bytes']==503567 and packet['sha256']=='fd43ebe02f8069917db91c47bebdc3509b786e3f1fae75764383ecafd54a9d47'
raw=PACKET.read_bytes();assert hashlib.sha256(raw).hexdigest()==packet['sha256'] and reference(PACKET)==packet
expected={row['path']:row for row in MANIFEST['files']}
with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
 members=archive.getmembers();assert len(members)==10 and len({m.name for m in members})==10
 assert {m.name for m in members}==set(expected)|{'TARGET-TEST-PACKET.json'}
 for member in members:
  rel=PurePosixPath(member.name);assert member.isfile() and str(rel)==member.name and not rel.is_absolute() and '..' not in rel.parts
  body=archive.extractfile(member).read();assert len(body)==member.size
  if member.name=='TARGET-TEST-PACKET.json':
   assert hashlib.sha256(body).hexdigest()=='3db4f26db8293005a5c05513e1ed3b8022f715bd69fc631da8ea7a29477732b0' and json.loads(body)==MANIFEST
  else:
   item=expected[member.name];assert len(body)==item['bytes'] and hashlib.sha256(body).hexdigest()==item['sha256']
  destination=BASE/rel
  destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
  assert destination.parent.resolve()==destination.parent and destination.parent.lstat().st_uid==1000
  with destination.open('xb') as output:output.write(body);output.flush();os.fsync(output.fileno())
inputs=[reference(BASE/name) for name in expected]
git=reference('/usr/bin/git')
assert git==EXPECTED_GIT
tmp=BASE/'tmp';tmp.mkdir(mode=0o700)
argv=['/usr/bin/python3','-I','-B',str(BASE/'test_text_auto.py'),'--result',str(BASE/'CONTROLS.json')]
stdout_path,stderr_path=BASE/'controls.stdout',BASE/'controls.stderr'
with stdout_path.open('xb') as stdout,stderr_path.open('xb') as stderr:
 child=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,
  env={**os.environ,'TMPDIR':str(tmp),'PYTHONDONTWRITEBYTECODE':'1'},start_new_session=True)
 fd=os.pidfd_open(child.pid)
 try:
  try:exit_code=child.wait(timeout=190)
  except BaseException:
   if child.poll() is None:os.killpg(child.pid,signal.SIGKILL)
   child.wait(timeout=5);raise
  try:os.killpg(child.pid,0)
  except ProcessLookupError:group_gone=True
  else:group_gone=False
  assert group_gone
 finally:os.close(fd)
assert all(reference(row['path'])==row for row in inputs) and reference('/usr/bin/git')==git
assert exit_code==0
result_ref=reference(BASE/'CONTROLS.json');result_body=(BASE/'CONTROLS.json').read_bytes()
assert hashlib.sha256(result_body).hexdigest()==result_ref['sha256'] and reference(BASE/'CONTROLS.json')==result_ref
result=json.loads(result_body)
assert result['passed'] is True and result['tests_run']==41 and result['actual_fixture_files_replayed']==440
assert result['git_version']=='git version 2.53.0' and result['git']==git and result['uid']==1000
assert all(result[key] for key in ['all_fixture_children_reaped','all_fixture_process_groups_gone','original_pidfds_held_until_reaped','temporary_repositories_removed'])
assert not any(tmp.iterdir())
compressed=gzip.compress(result_body,mtime=0)
with (BASE/'CONTROLS.json.gz').open('xb') as output:output.write(compressed);output.flush();os.fsync(output.fileno())
report={'schema':'p4-text-auto-ai395-target-execution-v1','started_ns':started,'finished_ns':time.time_ns(),
 'host':'ai395','uid':os.getuid(),'passed':True,'argv':argv,'child_pid':child.pid,'child_exit_code':exit_code,
 'actual_child_reaped':True,'original_pidfd_held_until_reaped':True,'child_process_group_gone':group_gone,
 'packet':packet,'git':git,'inputs':inputs,'all_input_bytes_and_F9_preserved':True,
 'stdout':reference(stdout_path),'stderr':reference(stderr_path),'controls':result_ref,
 'controls_gzip':reference(BASE/'CONTROLS.json.gz'),'temporary_fixture_root_empty':True,
 'operational_source_mutations':False,'Android_actions':False,'runtime_qualified':False,'production_ready':False}
out=save(BASE/'TARGET-EXECUTION.json',report)
print(json.dumps({'passed':True,'target_execution':out,'controls':result_ref,'controls_gzip':report['controls_gzip'],
                 'tests_run':41,'actual_fixture_files_replayed':440,'child_pid':child.pid},sort_keys=True),flush=True)
