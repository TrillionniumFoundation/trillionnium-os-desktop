import os,pathlib,subprocess,json,hashlib,datetime,shutil,re
R=pathlib.Path("/data/pocket4-audio-r12-source-closure-20261109-2840-r1")
P=R/"recipe";V=R/"validation-r1";V.mkdir()
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
expected=json.loads((R/"EDITED.json").read_bytes())
assert sha(R/"r12-original-provider-closure.patch")==expected["patch_sha256"]
assert sha(P/"android/manifest/audio-bridge-source-lock.json")==expected["lock_sha256"]
tracked={rel:sha(P/rel) for rel in expected["changed_files"]}
env=os.environ.copy()
env.update(PATH="/home/qian-qi/.cargo/bin:/usr/bin:/bin",CARGO_TARGET_DIR=str(R/"target"),CARGO_BUILD_JOBS="2",GIT_OPTIONAL_LOCKS="0")
record={"schema_version":1,"state":"RUNNING","started":stamp(),"base_commit":expected["base_commit"],"lock_sha256":expected["lock_sha256"],"changed_files_sha256":tracked,"cpu_affinity":sorted(os.sched_getaffinity(0)),"commands":[],"source_materialized":False,"full_build_succeeded":False,"runtime_qualified":False}
def save():
 t=V/"RESULT.tmp";t.write_text(json.dumps(record,indent=2)+"\n");t.replace(V/"RESULT.json")
def run(name,argv,expected_rc=0):
 o=V/(name+".stdout");e=V/(name+".stderr");start=stamp()
 with o.open("xb") as stdout,e.open("xb") as stderr:
  p=subprocess.run(argv,cwd=P,env=env,stdout=stdout,stderr=stderr)
 cmd={"name":name,"argv":argv,"cwd":str(P),"started":start,"finished":stamp(),"returncode":p.returncode,"expected_returncode":expected_rc,"stdout":{"path":str(o),"bytes":o.stat().st_size,"sha256":sha(o)},"stderr":{"path":str(e),"bytes":e.stat().st_size,"sha256":sha(e)}}
 if name.endswith("tests"):
  cmd["summaries"]=re.findall(r"test result: [^\n]+",o.read_text(errors="replace"))
 record["commands"].append(cmd);save()
 assert p.returncode==expected_rc,(name,p.returncode)
 print(json.dumps({"command":name,"returncode":p.returncode,"summaries":cmd.get("summaries")}),flush=True)
try:
 assert len(os.sched_getaffinity(0))==2
 free=shutil.disk_usage(R).free;record["free_bytes_before"]=free;assert free>20*1024**3
 cargo="/home/qian-qi/.cargo/bin/cargo"
 run("source-tests",[cargo,"test","--locked","--offline","-j2","-p","droidloom-source","--","--test-threads=2"])
 run("audio-updater-tests",[cargo,"test","--locked","--offline","-j2","-p","droidloom-update","audio_","--","--test-threads=2"])
 run("normal-tools-build",[cargo,"build","--locked","--offline","-j2","-p","droidloom-source","-p","droidloom-update"])
 tools=R/"tools";tools.mkdir()
 record["tools"]={}
 for name in ["droidloom-source","droidloom-update"]:
  src=R/"target/debug"/name;dst=tools/name
  with src.open("rb") as i,dst.open("xb") as o:
   shutil.copyfileobj(i,o);os.fchmod(o.fileno(),0o500);o.flush();os.fsync(o.fileno())
  record["tools"][name]={"path":str(dst),"bytes":dst.stat().st_size,"sha256":sha(dst)}
 run("normal-verify-lock",[str(tools/"droidloom-source"),"verify-lock","--lock",str(P/"android/manifest/audio-bridge-source-lock.json")])
 run("diff-check",["/usr/bin/git","diff","--check"])
 assert tracked=={rel:sha(P/rel) for rel in tracked}
 assert subprocess.run(["/usr/bin/git","rev-parse","HEAD"],cwd=P,env=env,stdout=subprocess.PIPE,text=True,check=True).stdout.strip()==expected["base_commit"]
 record["state"]="NORMAL_TOOLS_VALIDATED_SOURCE_NOT_RECONCILED"
except BaseException as e:
 record["state"]="FAILED";record["error"]=repr(e);record["finished"]=stamp();save();raise
record["finished"]=stamp();save();print(json.dumps(record,indent=2),flush=True)
