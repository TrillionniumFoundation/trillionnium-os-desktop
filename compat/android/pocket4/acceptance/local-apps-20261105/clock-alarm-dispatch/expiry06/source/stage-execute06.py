import base64,gzip,hashlib,json,os,pathlib,sys
assert os.geteuid()==0
raw=base64.b64decode(sys.stdin.read(65537),validate=True)
assert len(raw)==19003 and hashlib.sha256(raw).hexdigest()=='3c89be7b0cfca4ef7dcf953c7e8a40fa9e96c6cc4216beb014e88292e8bbb0c8'
payload=gzip.decompress(raw);assert len(payload)==69932
files=json.loads(payload);pins={'timer_expiry06.py': 'fba956b1b2a681d5181b60ab5fccad55964a46029b89970ad1c9ad646a0776fc', 'timer_core04.py': '59598a298f768bd63f535efb5216233f916383bc4411e7d98531e3d078a6b69b', 'read_clock_expired_text02.py': '4eae2c4540ce0710f225c875b025fad48d9e8a14bbc5b81f99aa1e0cb26c0905'};assert set(files)==set(pins)
os.sched_setaffinity(0,{20,21})
root=pathlib.Path('/home/alex/work/pocket4-clock-expiry-tools-20261105-r12-06');root.mkdir(mode=0o750);os.chown(root,0,1000);os.chmod(root,0o750)
for name,v in files.items():
 assert '/' not in name and name.endswith('.py')
 data=v['text'].encode();assert len(data)==v['bytes'] and hashlib.sha256(data).hexdigest()==v['sha256']==pins[name]
 path=root/name;fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o640)
 try:
  os.fchown(fd,0,1000);os.fchmod(fd,0o640)
  with os.fdopen(os.dup(fd),'wb') as out:out.write(data);out.flush();os.fsync(out.fileno())
 finally:os.close(fd)
 assert hashlib.sha256(path.read_bytes()).hexdigest()==pins[name]
print(json.dumps({'stage_verified':pins,'root':str(root)}),flush=True)
os.execv('/usr/bin/python3',['/usr/bin/python3','-I',str(root/'timer_expiry06.py'),'--execute'])
