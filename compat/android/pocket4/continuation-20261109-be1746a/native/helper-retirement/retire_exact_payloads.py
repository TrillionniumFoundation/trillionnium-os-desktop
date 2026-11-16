#!/usr/bin/env python3
"""Retire only four explicitly identified obsolete helper payload directories."""
import collections,datetime,gzip,hashlib,json,os,pathlib,signal,stat,subprocess,sys,time
ROOT=pathlib.Path("/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1")
HELPER=ROOT/"native-tradefed-helper-be1746a-r1"
EVIDENCE=HELPER/"retirement-be1746a-r1"
EXPECTED={
"target":{"dev":66306,"ino":85479099,"uid":1000,"gid":1000,"mode":448,"files":1817,"dirs":142,"bytes":655073212},
"cargo-home":{"dev":66306,"ino":85472695,"uid":1000,"gid":1000,"mode":448,"files":4326,"dirs":1441,"bytes":148014254},
"rustup":{"dev":66306,"ino":85475273,"uid":1000,"gid":1000,"mode":448,"files":140,"dirs":27,"bytes":629234822},
"tmp-r2":{"dev":66306,"ino":85482692,"uid":1000,"gid":1000,"mode":448,"files":0,"dirs":0,"bytes":0}}
KEEP=["source","OWNER.json","SETUP.json","QUALIFICATION.json","QUALIFICATION-r2.json","logs","qualification","qualification-r2"]
CURRENT_INPUT=ROOT/"control/full-ai395-r10/build-inputs.json"
INPUT_SHA="2677abd4b386a87aa8a0dd2564605fe0eb2ab7c721431698989af3fc0190c4c4"
SOURCE_HEAD="ff910cc50d842b5308b860340295bda44c28cf5a"
SOURCE_LOCK_SHA="02fd330466357ecf744d85f27d23b03fabde46f31fae3ef69a5f6634e66e8837"
DIRFLAGS=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC
FILEFLAGS=os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC
report={"schema":"pocket4-native-helper-exact-payload-retirement-v1","started_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"host":"ai395","helper":str(HELPER),"state":"PRECHECK","removed_roots":[],"removed_regular_files":0,"removed_directories":0,"commands":[],"errors":[],"Android_starts":0,"full_builds_started":0,"shared_source_writes":0,"CURRENT_writes":0,"production_ready":False}
removed_links=collections.Counter()
def need(x,m):
 if not x:raise RuntimeError(m)
def identity(s):return {"dev":s.st_dev,"ino":s.st_ino,"uid":s.st_uid,"gid":s.st_gid,"mode":stat.S_IMODE(s.st_mode),"type":stat.S_IFMT(s.st_mode),"nlink":s.st_nlink,"bytes":s.st_size,"mtime_ns":s.st_mtime_ns,"ctime_ns":s.st_ctime_ns}
def stable(a,b):return identity(a)==identity(b)
def open_directory_absolute(p):
 fd=os.open("/",DIRFLAGS)
 try:
  for name in p.parts[1:]:
   nxt=os.open(name,DIRFLAGS,dir_fd=fd);os.close(fd);fd=nxt
  return fd
 except BaseException:os.close(fd);raise
def read_regular(p,limit=67108864):
 fd=os.open(p,FILEFLAGS)
 try:
  a=os.fstat(fd);need(stat.S_ISREG(a.st_mode),"not regular: "+str(p));need(a.st_size<=limit,"read bound: "+str(p))
  raw=b""
  while True:
   chunk=os.read(fd,min(1048576,limit+1-len(raw)))
   if not chunk:break
   raw+=chunk;need(len(raw)<=limit,"growing read: "+str(p))
  b=os.fstat(fd);need(stable(a,b)and len(raw)==a.st_size,"changed during read: "+str(p))
  return raw,{"path":str(p),"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"identity":identity(a)}
 finally:os.close(fd)
def create(p,raw):
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
 try:
  with os.fdopen(fd,"wb")as f:f.write(raw);f.flush();os.fsync(f.fileno())
 except BaseException:raise
 return {"path":str(p),"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
def jsonfile(p,value):return create(p,(json.dumps(value,sort_keys=True,indent=2)+"\n").encode())
def command(name,args,env=None,timeout=20):
 started=time.monotonic()
 with subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)as p:
  try:stdout,stderr=p.communicate(timeout=timeout);timed_out=False
  except subprocess.TimeoutExpired:
   p.kill();stdout,stderr=p.communicate();timed_out=True
  rec={"name":name,"argv":args if name!="root-live-reference-guard" else ["/usr/bin/sudo","-n","/usr/bin/python3","-I","-B","-c","<exact frozen guard>"],"pid":p.pid,"returncode":p.returncode,"timed_out":timed_out,"direct_child_reaped":p.returncode is not None,"elapsed_seconds":time.monotonic()-started,"stdout_sha256":hashlib.sha256(stdout).hexdigest(),"stderr":stderr.decode(errors="replace")}
  report["commands"].append(rec)
  need(not timed_out,"command timed out: "+name)
  return p.returncode,stdout,stderr
def protected_manifest():
 result=[]
 for name in KEEP:
  top=HELPER/name;need(top.exists()and not top.is_symlink(),"protected top missing or link: "+name)
  paths=[top]
  if top.is_dir():
   for current,dirs,files in os.walk(top,followlinks=False):
    dirs[:]=[n for n in dirs if n!=".git"and not(pathlib.Path(current)/n).is_symlink()]
    paths.extend(pathlib.Path(current)/n for n in files)
  for p in sorted(set(paths)):
   s=p.lstat()
   if stat.S_ISDIR(s.st_mode):
    result.append({"path":str(p.relative_to(HELPER)),"directory":True,"dev":s.st_dev,"ino":s.st_ino,"uid":s.st_uid,"gid":s.st_gid,"mode":stat.S_IMODE(s.st_mode)})
   elif stat.S_ISLNK(s.st_mode):result.append({"path":str(p.relative_to(HELPER)),"symlink":os.readlink(p),"dev":s.st_dev,"ino":s.st_ino})
   else:
    raw,ref=read_regular(p);result.append({"path":str(p.relative_to(HELPER)),"bytes":ref["bytes"],"sha256":ref["sha256"],"dev":s.st_dev,"ino":s.st_ino,"uid":s.st_uid,"gid":s.st_gid,"mode":stat.S_IMODE(s.st_mode)})
 return result
def source_identity():
 env=dict(os.environ,GIT_NO_LAZY_FETCH="1",GIT_OPTIONAL_LOCKS="0",GIT_TERMINAL_PROMPT="0",GIT_CONFIG_GLOBAL="/dev/null",GIT_CONFIG_NOSYSTEM="1")
 vals=[]
 for label,args in [("source-head",["rev-parse","HEAD"]),("source-clean",["status","--porcelain","--untracked-files=no"])]:
  rc,out,err=command(label,["/usr/bin/git","-C",str(HELPER/"source")]+args,env);need(rc==0,label+" failed");vals.append(out.decode())
 need(vals==[SOURCE_HEAD+"\n",""],"source identity changed")
 raw,ref=read_regular(HELPER/"source/android/native-generation-pair/source-lock.json")
 need(ref["sha256"]==SOURCE_LOCK_SHA,"source lock changed")
 return {"head":SOURCE_HEAD,"tracked_clean":True,"lock":ref}
def snapshot_native():
 obs={"observed_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"files":[]}
 names=["control/full-ai395-r10/READY.json","control/full-ai395-r10/inner-started.json","control/full-ai395-r10/outer-terminal.json","qualification/full-ai395-r10/terminal.json","qualification/full-ai395-r9/terminal.json","control/full-ai395-r9/outer-terminal.json"]
 for name in names:
  p=ROOT/name
  if not p.exists():obs["files"].append({"path":str(p),"exists":False});continue
  raw,ref=read_regular(p,4194304);value=json.loads(raw)
  wanted=["schema","state","outer_job_id","full_unit","build_success","inner_build_success","owned_unit_retired","source_projection_absent_after","source_restored","after_qualified","errors","resource_events","MainPID","Description","InvocationID","LoadState","ActiveState","ControlGroup"]
  ref["selected"]={k:value[k]for k in wanted if k in value};obs["files"].append(ref)
  create(EVIDENCE/("observed-"+name.replace("/","--")),raw)
 rc,out,err=command("r10-unit-read-only",["/usr/bin/systemctl","show","p4-native-source600-full-ai395-20261109-8b88-r10.service","--property=Id,Description,LoadState,ActiveState,SubState,MainPID,Result,ExecMainCode,ExecMainStatus,ControlGroup,InvocationID"],timeout=10)
 obs["unit"]={"returncode":rc,"stdout":out.decode(),"stderr":err.decode()}
 return obs
ROOT_GUARD=r'''import os,pathlib,json,signal,datetime
signal.alarm(20)
prefix="/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/native-tradefed-helper-be1746a-r1"
payload=[prefix+"/"+x for x in ["target","cargo-home","rustup","tmp-r2"]]
def points(value):return any(value==p or value.startswith(p+"/") or value==p+" (deleted)" for p in payload)
def ident(pid):
 raw=pathlib.Path("/proc",str(pid),"stat").read_text();end=raw.rfind(")");tail=raw[end+2:].split()
 return {"pid":pid,"ppid":int(tail[1]),"start_ticks":int(tail[19]),"comm":raw[raw.find("(")+1:end]}
anc=[];pid=os.getpid()
for _ in range(16):
 a=ident(pid);anc.append(a)
 if a["ppid"]==0:break
 pid=a["ppid"]
known={x["pid"]for x in anc}
out={"observed_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"uid":os.getuid(),"known_guard_ancestry":anc,"examined":0,"references":[],"errors":[],"environment_not_read":True}
for p in pathlib.Path("/proc").iterdir():
 if not p.name.isdigit():continue
 out["examined"]+=1;found=[]
 for field in ["exe","cwd"]:
  try:
   v=os.readlink(p/field)
   if points(v):found.append({"field":field,"path":v})
  except FileNotFoundError:pass
  except PermissionError:out["errors"].append({"pid":int(p.name),"field":field,"error":"PermissionError"})
 try:
  raw=(p/"cmdline").read_bytes()
  if prefix.encode()in raw and int(p.name)not in known:found.append({"field":"cmdline","contains_helper_prefix":True})
 except FileNotFoundError:pass
 except PermissionError:out["errors"].append({"pid":int(p.name),"field":"cmdline","error":"PermissionError"})
 try:
  for fd in(p/"fd").iterdir():
   try:
    v=os.readlink(fd)
    if points(v):found.append({"field":"fd","number":fd.name,"path":v})
   except FileNotFoundError:pass
 except FileNotFoundError:pass
 except PermissionError:out["errors"].append({"pid":int(p.name),"field":"fd","error":"PermissionError"})
 try:
  raw=(p/"maps").read_bytes()
  if any(x.encode()in raw for x in payload):found.append({"field":"maps","contains_payload_prefix":True})
 except FileNotFoundError:pass
 except PermissionError:out["errors"].append({"pid":int(p.name),"field":"maps","error":"PermissionError"})
 if found:out["references"].append({"pid":int(p.name),"references":found})
print(json.dumps(out,sort_keys=True))
'''
def inventory(fd,path,items):
 for name in sorted(os.listdir(fd)):
  s=os.stat(name,dir_fd=fd,follow_symlinks=False);rel=path+"/"+name;v=identity(s)
  need(s.st_uid==1000 and s.st_gid==1000 and s.st_dev==66306,"member ownership/device drift: "+rel)
  need(stat.S_ISREG(s.st_mode)or stat.S_ISDIR(s.st_mode),"unexpected member type: "+rel)
  need(len(items)<200000,"payload inventory bound");items[rel]=v
  if stat.S_ISDIR(s.st_mode):
   sub=os.open(name,DIRFLAGS,dir_fd=fd)
   try:need(identity(os.fstat(sub))==v,"directory changed on open: "+rel);inventory(sub,rel,items)
   finally:os.close(sub)
def remove_tree(fd,path,items):
 expected={p.rsplit("/",1)[1]for p in items if "/" in p and p.rsplit("/",1)[0]==path}
 need(set(os.listdir(fd))==expected,"directory membership changed: "+path)
 for name in sorted(expected):
  rel=path+"/"+name;exp=items[rel];s=os.stat(name,dir_fd=fd,follow_symlinks=False);actual=identity(s)
  for k in ["dev","ino","uid","gid","mode","type"]:need(actual[k]==exp[k],"member identity drift: "+rel)
  if stat.S_ISDIR(s.st_mode):
   sub=os.open(name,DIRFLAGS,dir_fd=fd)
   try:
    need(os.fstat(sub).st_ino==s.st_ino and os.fstat(sub).st_dev==s.st_dev,"directory replaced: "+rel)
    remove_tree(sub,rel,items)
    now=os.stat(name,dir_fd=fd,follow_symlinks=False);need(now.st_ino==s.st_ino and now.st_dev==s.st_dev,"directory changed before rmdir")
    os.rmdir(name,dir_fd=fd);report["removed_directories"]+=1
   finally:os.close(sub)
  else:
   key=(s.st_dev,s.st_ino)
   need(actual["bytes"]==exp["bytes"]and actual["mtime_ns"]==exp["mtime_ns"],"payload file drift: "+rel)
   need(actual["nlink"]==exp["nlink"]-removed_links[key],"hardlink count drift: "+rel)
   if not removed_links[key]:need(actual["ctime_ns"]==exp["ctime_ns"],"payload ctime drift: "+rel)
   os.unlink(name,dir_fd=fd);removed_links[key]+=1;report["removed_regular_files"]+=1
 need(not os.listdir(fd),"directory repopulated: "+path)
helper_fd=None;payload_fds={};deleting=False
try:
 need(os.getuid()==os.geteuid()==1000 and os.getgid()==1000,"wrong cleanup account")
 os.sched_setaffinity(0,{0});helper_fd=open_directory_absolute(HELPER)
 hs=os.fstat(helper_fd);need(hs.st_uid==hs.st_gid==1000 and stat.S_IMODE(hs.st_mode)==0o700,"helper identity/mode differs")
 os.mkdir(EVIDENCE,0o700)
 report["helper_identity"]=identity(hs);report["source_before"]=source_identity()
 retained_before=protected_manifest();report["protected_before"]=jsonfile(EVIDENCE/"protected-before.json",retained_before)
 report["latest_native_generation"]=snapshot_native()
 old=pathlib.Path("/proc/2842763")
 report["prior_cmdline_pid"]={"pid":2842763,"absent":not old.exists()}
 need(not old.exists(),"prior cmdline-only PID remains; retain")
 raw,inp=read_regular(CURRENT_INPUT,4194304)
 need(inp["bytes"]==3293953 and inp["sha256"]==INPUT_SHA,"current r10 input differs; retain")
 inp["helper_name_occurrences"]=raw.count(HELPER.name.encode());inp["full_prefix_occurrences"]=raw.count(str(HELPER).encode())
 need(inp["helper_name_occurrences"]==0,"current r10 input references helper; retain");report["current_build_input"]=inp
 raw,ready=read_regular(ROOT/"control/full-ai395-r10/READY.json",32768)
 need(ready["sha256"]=="fd39fee61fb27628756daf0313b9f2a0d336a37a628659a308df95284b72d90c","current r10 READY changed");report["current_request_ready"]=ready
 rc,out,err=command("root-live-reference-guard",["/usr/bin/sudo","-n","/usr/bin/python3","-I","-B","-c",ROOT_GUARD],timeout=30)
 need(rc==0,"root process guard failed");proc=json.loads(out);report["current_process_guard"]=proc
 need(proc["uid"]==0 and not proc["errors"]and not proc["references"],"current consumer or process visibility failure; retain")
 mounts=pathlib.Path("/proc/self/mountinfo").read_text()
 for line in mounts.splitlines():
  point=line.split()[4]
  need(not any(point==str(HELPER/n)or point.startswith(str(HELPER/n)+"/")for n in EXPECTED),"payload mount present; retain")
 items={};groups=collections.defaultdict(list)
 for name,exp in EXPECTED.items():
  fd=os.open(name,DIRFLAGS,dir_fd=helper_fd);payload_fds[name]=fd;s=os.fstat(fd);v=identity(s)
  for k in ["dev","ino","uid","gid","mode"]:need(v[k]==exp[k],"candidate directory drift: "+name)
  need(stat.S_ISDIR(s.st_mode),"candidate not directory")
  items[name]=v;inventory(fd,name,items)
  members=[(p,x)for p,x in items.items()if p.startswith(name+"/")]
  nfiles=sum(x["type"]==stat.S_IFREG for _,x in members);ndirs=sum(x["type"]==stat.S_IFDIR for _,x in members);nbytes=sum(x["bytes"]for _,x in members if x["type"]==stat.S_IFREG)
  need((nfiles,ndirs,nbytes)==(exp["files"],exp["dirs"],exp["bytes"]),"candidate contents drift: "+name)
 for p,x in items.items():
  if x["type"]==stat.S_IFREG:groups[(x["dev"],x["ino"])].append(p)
 for key,paths in groups.items():need(items[paths[0]]["nlink"]==len(paths),"external hardlink present; retain")
 unique_bytes=sum(items[paths[0]]["bytes"]for paths in groups.values())
 report["preinventory"]=create(EVIDENCE/"payload-preinventory.json.gz",gzip.compress((json.dumps(items,sort_keys=True)+"\n").encode(),mtime=0))
 report["payload_unique_inode_bytes"]=unique_bytes;report["payload_path_bytes"]=sum(x["bytes"]for x in EXPECTED.values());report["unique_regular_file_inodes"]=len(groups);report["hardlink_groups"]=sum(len(p)>1 for p in groups.values())
 report["candidate_roots"]=EXPECTED;jsonfile(EVIDENCE/"predelete-gates.json",report)
 deleting=True;report["state"]="RETIRING"
 for name,fd in payload_fds.items():
  if name=="tmp-r2":need(not os.listdir(fd),"temporary directory no longer empty")
  else:remove_tree(fd,name,items)
  now=os.stat(name,dir_fd=helper_fd,follow_symlinks=False);need(now.st_dev==EXPECTED[name]["dev"]and now.st_ino==EXPECTED[name]["ino"],"root changed before removal")
  os.rmdir(name,dir_fd=helper_fd);report["removed_directories"]+=1
  report["removed_roots"].append({"path":str(HELPER/name),"identity":EXPECTED[name],"absent_after":not(HELPER/name).exists()})
 retained_after=protected_manifest();report["protected_after"]=jsonfile(EVIDENCE/"protected-after.json",retained_after)
 need(retained_before==retained_after,"retained source/evidence changed")
 report["protected_unchanged"]=True;report["source_after"]=source_identity()
 need(report["source_before"]==report["source_after"],"source identity changed after retirement")
 need(all(not(HELPER/n).exists()for n in EXPECTED),"candidate remains")
 report["state"]="RETIRED_EXACT_FOUR_OWN_PAYLOADS"
 report["space_claim"]="Unique regular-file inode bytes retired; physical freed blocks not measured and may differ due to reflinks or filesystem behavior."
except BaseException as e:
 report["state"]="PARTIAL_RETIREMENT_STOPPED"if deleting else"RETAINED_NO_PAYLOAD_DELETIONS"
 report["errors"].append({"type":type(e).__name__,"message":str(e)})
finally:
 for fd in payload_fds.values():os.close(fd)
 if helper_fd is not None:os.close(helper_fd)
 report["finished_utc"]=datetime.datetime.now(datetime.timezone.utc).isoformat()
 try:
  receipt=jsonfile(EVIDENCE/"RESULT.json",report)
  print(json.dumps({"state":report["state"],"receipt":receipt,"removed_roots":report["removed_roots"],"errors":report["errors"],"latest_native_generation":report.get("latest_native_generation")},sort_keys=True),flush=True)
 except BaseException as e:
  print(json.dumps({"state":report["state"],"receipt_write_error":str(e),"report":report},sort_keys=True),flush=True)
sys.exit(0 if report["state"]=="RETIRED_EXACT_FOUR_OWN_PAYLOADS"else 2)
