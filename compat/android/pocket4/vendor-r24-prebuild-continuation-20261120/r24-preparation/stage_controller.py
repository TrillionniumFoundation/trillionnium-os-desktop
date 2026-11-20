from pathlib import Path,PurePosixPath
import io,os,stat,sys,resource,signal,hashlib,json,zipfile
sys.dont_write_bytecode=True
resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(15,15));resource.setrlimit(resource.RLIMIT_CORE,(0,0));signal.alarm(30)
f9=lambda s:[s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
archive=Path('/home/qq/work/p4-r24-controller-stage-20261120-3b9d-r1.zip')
stage=Path('/home/qq/work/p4-r24-controller-preparation-20261120-3b9d-r1')
pins={'r23_prebuild_admission.py': [20612, 'fe5511a7f22f17769c23cb8dbc18b31665556e358eb676575dfeac53c6ae0fa6'], 'R23-PREBUILD-ACTUAL-CONTROLS.json': [32987, 'c6511162ca1200f8523075c5706861e8bffcffcbe98138535082daaad95c1927'], 'test_r23_prebuild_actual.py': [12403, '52aab99fcb781b6466561401157b97bf021d5194991205bad825182257e8374b'], 'R23-PREBUILD-HELPER-INPUTS.json': [4629, '419b11a33e2ddd9bdc43cb16c9d44e442602e72586bbdce485cbfa21ea5c9f73'], 'R23-ACTUAL-FILE-INFO.json': [1785, 'f803b68c54f44107ce1a0214f3c344904e8c12ea807f721412d86b21ec47616a'], 'R23-PREBUILD-HELPER-HANDOFF.json': [3559, '427aa893bb5e9f2147163e3530b816471ed3d08980b71560f335b2c135149cb0'], 'SOURCE-INDEPENDENT-REVIEW.json': [3238, '1eee7c9c1a25dd442c49f970cb386320d31e3273ffc8e95a165c8a33a5cd7994'], 'SOURCE-CONSERVATION.json': [1477, '66b77c3bbb0ab2c31980507335ae236209c41c090c8e9b34f1404c52267d887f'], 'R24-BOOTSTRAP-ADMISSION.py': [11212, '59ff1334ea251f004f33100245b00bec3cc5b83ed4ead9b13daa205b23cbf185'], 'source-r24-template.py': [354072, 'b20145f9d8daee8616fb622aa63847e346d2afc188c12501f31c14f30c2bc5d1'], 'outer-r24-template.py': [35188, '7f1d71e782658d16c14c30f9c352025bf647f58e9c1aff289dcef5e5a935cb3c'], 'CLIENTS-RAW.json': [63259, '340d2afc32c11c1f20e6e099f79da2d31b5bd83bfe321e7929c2627d7e8536ee'], 'prepare_candidates.py': [5462, '3fa1a0f614f35a8ffe221213e9e030c7ff0e46f01d3c5415dfeb9de07fdc7ac1'], 'FREEZER-INDEPENDENT-REVIEW.json': [5649, '7237dc8ed5238bf0c04be03638dfc765066f34787b925cea8c8d71c89cbc6f61'], 'freeze_r24.py': [25510, 'cfe54cb25c34cb8b5bf36d03cdb259b19487fb98226caf581ea90d7312648e84']}
assert stage.parent.resolve()==stage.parent and not os.path.lexists(stage)
fd=os.open(archive,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
try:
 before=f9(os.fstat(fd));assert stat.S_ISREG(before[2]) and before[5]==1 and before[6]==146252
 raw=os.read(fd,146253)
 assert len(raw)==146252 and hashlib.sha256(raw).hexdigest()=='1dca5201c3cb2f4f0bae5778a9a5c35e218d4f98891285fb27f66750f197353c'
 assert before==f9(os.fstat(fd))==f9(archive.lstat())
finally:os.close(fd)
z=zipfile.ZipFile(io.BytesIO(raw),'r');infos=z.infolist()
assert len(infos)==len(pins)==15 and set(x.filename for x in infos)==set(pins)
prepared=[]
for info in infos:
 name=info.filename;parts=PurePosixPath(name)
 assert not parts.is_absolute() and all(x not in ('..','.','') for x in parts.parts) and stat.S_ISREG(info.external_attr>>16)
 body=z.read(info)
 assert [len(body),hashlib.sha256(body).hexdigest()]==pins[name] and info.file_size==len(body)
 prepared.append((name,body))
assert z.testzip() is None
stage.mkdir(mode=0o700);members=[]
for name,body in prepared:
 path=stage/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
 with os.fdopen(fd,'wb') as stream:stream.write(body);stream.flush();os.fsync(stream.fileno())
 assert path.read_bytes()==body
 members.append({'path':str(path),'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),'identity':f9(path.lstat())})
receipt=stage/'STAGE-RECEIPT.json'
body=(json.dumps({'schema':'p4-r24-actual-source-stage-v1','archive':{'path':str(archive),'bytes':146252,'sha256':hashlib.sha256(raw).hexdigest(),'identity':before},'members':members,'passed':True,'build_started':False,'source_mutations':False,'source_locks_acquired':False,'runtime_qualified':False,'production_ready':False},indent=2,sort_keys=True)+'\n').encode()
fd=os.open(receipt,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
with os.fdopen(fd,'wb') as stream:stream.write(body);stream.flush();os.fsync(stream.fileno())
print(json.dumps({'passed':True,'receipt':{'path':str(receipt),'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),'identity':f9(receipt.lstat())},'members':len(members),'build_started':False,'runtime_qualified':False,'production_ready':False}),flush=True)
