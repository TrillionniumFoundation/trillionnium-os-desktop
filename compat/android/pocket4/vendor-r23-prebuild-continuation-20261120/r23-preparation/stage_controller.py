from pathlib import Path,PurePosixPath
import io,os,stat,sys,resource,signal,hashlib,json,zipfile
sys.dont_write_bytecode=True
resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(15,15));resource.setrlimit(resource.RLIMIT_CORE,(0,0));signal.alarm(30)
f9=lambda s:[s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
archive=Path('/home/qq/work/p4-r23-controller-stage-20261120-3b9d-r1.zip')
stage=Path('/home/qq/work/p4-r23-controller-preparation-20261120-3b9d-r1')
pins=json.loads("{\"r22_prebuild_admission.py\":[17250,\"3ebc4eaf743b3a733501c4743178cc604469c49b1e6588a306bef484a76665eb\"],\"actual-controls/RESULT.json\":[22777,\"01ac2b7392896edb2490c110ec44f79f3a3beddb6dad832c0c6461bbc40df46e\"],\"actual-controls/test_r22_prebuild_actual.py\":[8504,\"cbcceb7543ec6f613cc8277d454de4316978418af8a86e6eff8e66f356f24961\"],\"actual-controls/ACTUAL-INPUT-CAPTURE.json\":[34919,\"062eefc14699e17785fe0169afd3e8bbcabb9c6bfe4ca9633c4843268e7ed471\"],\"R22-PREBUILD-INDEPENDENT-REVIEW.json\":[4646,\"ab13bc3a29b075e8f34ee3b8c84bd10ff4c5e3afda764587e0f20cf0cd78886f\"],\"SOURCE-INDEPENDENT-REVIEW.json\":[3992,\"74cb91076e2a30c53e3c5589d5c790ce2eae719f16172839e4b6a98b7e98ef09\"],\"SOURCE-CONSERVATION.json\":[1051,\"61a5c72fb6237a4922fc6dccd81b4a6743c10924527cc30a3e5fa256269c45b2\"],\"R23-BOOTSTRAP-ADMISSION.py\":[11840,\"252c7a833c810f29e34208f1c0766806b3da6dcf6d89d409ad97ca11559f5a15\"],\"source-r23-template.py\":[334948,\"72f8bafe081a18afea3422b5417e16b93221d7f00caac26293cad231f3d644a5\"],\"outer-r23-template.py\":[35188,\"8ad4e5eb98b72877990bc9ee0f20211be1be551e040a5d1fabc7042ff988f7e7\"],\"CLIENTS-RAW.json\":[107521,\"a166d2fea7ac6cf187a518641a1c0b725347b574e726a26d7dcb71929961b7ae\"],\"ROOT-ABSENCE-OBSERVATION-RAW.json\":[2431,\"859a47ab73daf787caa76bce1cc15ca5dd684454ac98f639bc19ab07bf2d618a\"]}")
assert stage.parent.resolve()==stage.parent and not os.path.lexists(stage)
fd=os.open(archive,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
try:
 before=f9(os.fstat(fd));assert stat.S_ISREG(before[2]) and before[5]==1 and before[6]==155953
 raw=os.read(fd,155954)
 assert len(raw)==155953 and hashlib.sha256(raw).hexdigest()=='9d0f89ca885bdf5fd938022753e3d8f6c4ce9e4fe6cd214db8d4cbc7696a63ab'
 assert before==f9(os.fstat(fd))==f9(archive.lstat())
finally:os.close(fd)
z=zipfile.ZipFile(io.BytesIO(raw),'r');infos=z.infolist()
assert len(infos)==len(pins)==12 and set(x.filename for x in infos)==set(pins)
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
body=(json.dumps({'schema':'p4-r23-actual-source-stage-v1','archive':{'path':str(archive),'bytes':155953,'sha256':hashlib.sha256(raw).hexdigest(),'identity':before},'members':members,'passed':True,'build_started':False,'source_mutations':False,'source_locks_acquired':False,'runtime_qualified':False,'production_ready':False},indent=2,sort_keys=True)+'\n').encode()
fd=os.open(receipt,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
with os.fdopen(fd,'wb') as stream:stream.write(body);stream.flush();os.fsync(stream.fileno())
print(json.dumps({'passed':True,'receipt':{'path':str(receipt),'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),'identity':f9(receipt.lstat())},'members':len(members),'build_started':False,'runtime_qualified':False,'production_ready':False}),flush=True)
