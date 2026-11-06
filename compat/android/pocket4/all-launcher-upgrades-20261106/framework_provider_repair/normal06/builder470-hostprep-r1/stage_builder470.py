
import os,sys,json,hashlib,stat,pathlib,datetime
P=pathlib.Path
ROOT=P('/home/alex/work/pocket4-native-typed-ingress-builder470-systemui-provider-compile-01-20261106')
BASE=P('/home/alex/work/pocket4-native-typed-ingress-builder469-native-provider-compile-01-20261106')
EXPECTED_BASELINE_SHA='d9340351c9653b10dfd0882afbff5ff4fc11dafaa6083191ed2a8fdb5c8dd934'
EXPECTED_CANDIDATE_SHA='f4a0e6ff82f1ecf9bd786872d99cc0b1608e1d94d0adc37761e87aed449c81bd'
FILE_PINS={'candidate-source-manifest.json': {'bytes': 99075, 'sha256': 'f4a0e6ff82f1ecf9bd786872d99cc0b1608e1d94d0adc37761e87aed449c81bd'}, 'compile_builder470.py': {'bytes': 32731, 'sha256': '9522d49fce5990361aabc40a225bf0766cbe0dd146fcd358614e03b653e47957'}, 'source-candidate.json': {'bytes': 3176, 'sha256': '858edc8cc683de670711fed936c941e2631b3939423acacac4bd3dcadb498040'}, 'source-controls.json': {'bytes': 2771, 'sha256': '7bdde8f6c86aa7b0e2b0b0b53df96efc4c89cde6f4920daa6daaa2f77820146e'}, 'overlay/android/manifest/m2-role-ingress-provider3-source-lock.json': {'bytes': 103409, 'sha256': 'f5717d49fe0d4656b952bd397beab5d2fa70aa0992dd936ac31f81246c9e4772'}, 'overlay/android/native-role-ingress/provider-fixtures/SystemUI-pods-build.Android.bp': {'bytes': 4218, 'sha256': '45a406d917e55d45ad1ef0eafd27f2146a894dbcd309813e5c58b1a1b9e6400f'}, 'overlay/android/native-role-ingress/provider-fixtures/SystemUI-pods-policy.Android.bp': {'bytes': 1278, 'sha256': 'abdbfc9d78daa2785dd2cb953b4ec081f135df032e348fab78c2731262744533'}, 'overlay/android/native-role-ingress/provider-fixtures/SystemUI-tests.Android.bp': {'bytes': 3392, 'sha256': 'f1b2422c693a8f8c52034369ded585a3a93ac861f9dd6dd73f0801a77e6be4da'}, 'overlay/android/native-role-ingress/provider-fixtures/WindowManager-Shell.Android.bp': {'bytes': 6272, 'sha256': 'fc3a3c4de8e8ffbfc4832125b6a7b448a50fea1e0b5c6bad8ceb767b55679738'}, 'overlay/tools/droidloom-update/src/android.rs': {'bytes': 293071, 'sha256': 'f50d1ff6010cec46e2fef6a5ba694b21c40f8c1b6a4add6d3aa6f4e707f833d1'}, 'overlay/tools/droidloom-update/src/native_role_ingress.rs': {'bytes': 50934, 'sha256': 'efcd00164cba047ec4b7e956680209dc0b4ecc1b34f1305d7a57b6f95863b5a3'}}
OVERLAY_NAMES=['android/manifest/m2-role-ingress-provider3-source-lock.json', 'android/native-role-ingress/provider-fixtures/SystemUI-pods-build.Android.bp', 'android/native-role-ingress/provider-fixtures/SystemUI-pods-policy.Android.bp', 'android/native-role-ingress/provider-fixtures/SystemUI-tests.Android.bp', 'android/native-role-ingress/provider-fixtures/WindowManager-Shell.Android.bp', 'tools/droidloom-update/src/android.rs', 'tools/droidloom-update/src/native_role_ingress.rs']
def require(c,m):
 if not c:raise RuntimeError(m)
def no_alias(p):
 for q in [p,*p.parents]:
  if q.exists() or q.is_symlink():require(stat.S_ISDIR(q.lstat().st_mode),'non-directory or aliased parent: '+str(q))
def read(p,bound=2*1024*1024):
 no_alias(p.parent);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  a=os.fstat(fd);require(stat.S_ISREG(a.st_mode) and a.st_nlink==1 and a.st_size<=bound,'source file type/link/bound: '+str(p))
  parts=[];total=0
  while total<=bound:
   b=os.read(fd,min(65536,bound+1-total))
   if not b:break
   parts.append(b);total+=len(b)
  data=b''.join(parts);z=os.fstat(fd);n=p.lstat();ident=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
  require(total==a.st_size and ident(a)==ident(z)==ident(n),'source changed during read: '+str(p))
  return data,stat.S_IMODE(a.st_mode)
 finally:os.close(fd)
def inventory(root):
 result={}
 for here,ds,fs in os.walk(root,followlinks=False):
  for d in ds:require(stat.S_ISDIR((P(here)/d).lstat().st_mode),'directory alias')
  for f in fs:
   p=P(here)/f;b,mode=read(p);result[str(p.relative_to(root))]={'kind':'file','bytes':len(b),'mode':mode,'sha256':hashlib.sha256(b).hexdigest()}
 return result
def save(p,b,mode=384):
 no_alias(p.parent);fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
 with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno());os.fchmod(f.fileno(),mode)
def main(files):
 require(os.getuid()==os.geteuid()==1000,'unprivileged operator required');os.umask(63)
 require(set(files)==set(FILE_PINS),'exact staged file names differ')
 for name,contents in files.items():
  require(isinstance(contents,str),'UTF-8 file required');data=contents.encode();pin=FILE_PINS[name]
  require(len(data)==pin['bytes'] and hashlib.sha256(data).hexdigest()==pin['sha256'],'staged file differs: '+name)
 baseline_raw,unused=read(BASE/'candidate-source-manifest.json',1048576)
 require(hashlib.sha256(baseline_raw).hexdigest()==EXPECTED_BASELINE_SHA,'builder469 manifest differs')
 baseline=json.loads(baseline_raw);require(len(baseline)==493 and inventory(BASE/'builder-source')==baseline,'builder469 source baseline differs')
 expected_raw=files['candidate-source-manifest.json'].encode();require(hashlib.sha256(expected_raw).hexdigest()==EXPECTED_CANDIDATE_SHA,'candidate map differs')
 expected=json.loads(expected_raw);require(len(expected)==498 and set(baseline)<=set(expected),'candidate source count/ancestry differs')
 no_alias(ROOT.parent);require(not ROOT.exists() and not ROOT.is_symlink(),'fresh owned builder470 root required');ROOT.mkdir(mode=448)
 result={'schema':1,'state':'FAILED','Main_actions':0,'Android_actions':0,'commands_started':0,'compiler_invoked':False,'Soong_invoked':False,'bytes_copied':0,'files_copied':0,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 failure=None
 try:
  source=ROOT/'builder-source';source.mkdir(mode=448)
  for name,row in sorted(expected.items()):
   relative=P(name);require(not relative.is_absolute() and all(p not in ('','..','.') for p in relative.parts),'unsafe source relative path')
   if name in OVERLAY_NAMES:data=files['overlay/'+name].encode();mode=row['mode']
   else:
    data,mode=read(BASE/'builder-source'/name)
    require(name in baseline,'non-overlay source lacks baseline')
   require(mode==row['mode'] and len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'],'source copy differs: '+name)
   target=source/relative;target.parent.mkdir(parents=True,exist_ok=True,mode=448);save(target,data,mode);result['bytes_copied']+=len(data);result['files_copied']+=1
  require(inventory(source)==expected,'candidate source readback differs')
  require(inventory(BASE/'builder-source')==baseline,'builder469 source changed during stage')
  for name in ['candidate-source-manifest.json','compile_builder470.py','source-candidate.json','source-controls.json']:
   save(ROOT/name,files[name].encode())
  result.update(state='EXACT_BUILDER470_SOURCE_STAGED_NO_COMPILER_RUN',baseline_source_unchanged_after=True,candidate_source_exact=True,candidate_source_manifest_sha256=EXPECTED_CANDIDATE_SHA,source_files=498,added_files=5,changed_files=2)
 except BaseException as error:failure=repr(error);result['error']=failure
 finally:
  result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();save(ROOT/'stage-result.json',(json.dumps(result,indent=2)+'\n').encode());print(json.dumps(result),flush=True)
 if failure:raise RuntimeError(failure)
