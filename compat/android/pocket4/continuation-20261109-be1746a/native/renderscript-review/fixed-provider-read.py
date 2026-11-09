import pathlib,json,hashlib,subprocess,os,re,datetime
root=pathlib.Path("/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1");src=root/"work/aosp-source";recipe=root/"recipe-tradefed-r1"
def pin(p):
 b=p.read_bytes();return {"path":str(p),"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
lockpath=recipe/"android/native-generation-pair/source-lock.json";lock=json.loads(lockpath.read_bytes())
wanted=["development","frameworks/compile/libbcc","frameworks/compile/slang","frameworks/rs","external/llvm","external/clang","prebuilts/sdk","prebuilts/clang/host/linux-x86","prebuilts/build-tools","build/soong","system/core","system/logging"]
out={"observed_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"lock":pin(lockpath),"projects":[p for p in lock["projects"]if p["path"]in wanted],"owner_blobs":[],"fixed_bp":[],"sdk_target_files":[],"owner_updates":[]}
for entry in json.loads((root/"qualification/renderscript-bcc-originals-r2/RESULT.json").read_bytes())["files"]:
 p=pathlib.Path(entry["saved_path"]);b=p.read_bytes();oid=hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()
 out["owner_blobs"].append({"path":entry["path"],"saved":pin(p),"git_blob_oid":oid,"git_oid_matches_owner":oid==entry["oid"],"sha_matches_owner":hashlib.sha256(b).hexdigest()==entry["sha256"],"bytes_matches_owner":len(b)==entry["bytes"],"body_matches_saved":b==entry["body"].encode()})
for rel in ["prebuilts/sdk/Android.bp","prebuilts/sdk/tools/Android.bp","prebuilts/clang/host/linux-x86/Android.bp","prebuilts/build-tools/Android.bp"]:
 p=src/rel
 if not p.is_file():out["fixed_bp"].append({"path":str(p),"exists":False});continue
 lines=p.read_text().splitlines();idx=set()
 for i,l in enumerate(lines):
  if any(x in l for x in ["build-tools-lld","lld","bootstrap_go_package","pluginFor","prebuilt_apis"]):
   idx.update(range(max(0,i-7),min(len(lines),i+40)))
 out["fixed_bp"].append({"ref":pin(p),"selected_lines":[{"n":i+1,"text":lines[i]}for i in sorted(idx)]})
sdk=next(p for p in lock["projects"]if p["path"]=="prebuilts/sdk")
env={**os.environ,"GIT_NO_LAZY_FETCH":"1","GIT_OPTIONAL_LOCKS":"0","GIT_TERMINAL_PROMPT":"0","GIT_CONFIG_GLOBAL":"/dev/null","GIT_CONFIG_NOSYSTEM":"1"}
for rel in ["36/system-server/api/service-ondeviceintelligence.txt","36/system-server/api/service-ondeviceintelligence-removed.txt"]:
 p=src/"prebuilts/sdk"/rel
 proc=subprocess.run(["/usr/bin/git","-C",str(src/"prebuilts/sdk"),"ls-tree",sdk["commit"],"--",rel],capture_output=True,timeout=20,env=env)
 out["sdk_target_files"].append({"path":rel,"physical_exists":p.is_file(),"selected_explicitly_or_by_parent":any(rel==s or rel.startswith(s.rstrip("/")+"/") for s in sdk["sparse_paths"]),"physical_ref":pin(p)if p.is_file()else None,"original_tree":{"returncode":proc.returncode,"stdout":proc.stdout.decode(),"stderr":proc.stderr.decode()}})
for d in [root,root/"qualification",root/"control"]:
 for p in sorted(d.iterdir()):
  if "renderscript" not in p.name.lower() and "bcc" not in p.name.lower():continue
  x={"path":str(p),"is_dir":p.is_dir(),"mtime_ns":p.stat().st_mtime_ns}
  if p.is_dir():
   x["entries"]=[{"name":f.name,"bytes":f.stat().st_size,"is_dir":f.is_dir()}for f in sorted(p.iterdir())]
   for name in ["RESULT.json","result.json"]:
    f=p/name
    if f.is_file():
     v=json.loads(f.read_bytes());x[name]={"ref":pin(f),"state":v.get("state"),"errors":v.get("errors"),"keys":list(v),"changes":v.get("changes")}
  out["owner_updates"].append(x)
print(json.dumps(out))
