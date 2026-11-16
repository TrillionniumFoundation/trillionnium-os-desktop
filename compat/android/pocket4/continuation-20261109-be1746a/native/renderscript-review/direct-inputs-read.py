import pathlib,json,hashlib,subprocess,os,re,datetime
root=pathlib.Path("/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1");src=root/"work/aosp-source";lock=json.loads((root/"recipe-tradefed-r1/android/native-generation-pair/source-lock.json").read_bytes());projects={p["path"]:p for p in lock["projects"]}
def pin(p):
 b=p.read_bytes();return {"path":str(p),"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
out={"observed_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"known_inputs":[],"cones":[],"owner_origin_shape":[]}
fixed={"prebuilts/sdk":["tools/lld","tools/lld-dummy","tools/linux/lld-bin/lld","tools/linux/lib64/libc++.so.1","tools/windows/lld-bin/lld.exe","tools/windows/lld-bin/libwinpthread-1.dll","tools/darwin/lld-bin/lld","tools/darwin/lib64/libc++.1.dylib","tools/darwin/lib64/libc++abi.1.dylib"],"frameworks/compile/slang":["RSCCOptions.td","lld_main.cpp"],"external/llvm":["Android.bp","lib/Linker/Android.bp"],"frameworks/compile/libbcc":["Android.bp","lib/Android.bp","bcinfo/Android.bp"],"external/clang":["Android.bp","LICENSE.TXT"]}
for proj,rels in fixed.items():
 p=projects[proj];sp=p.get("sparse_paths")
 for rel in rels:
  f=src/proj/rel
  out["known_inputs"].append({"project":proj,"path":rel,"exists":f.is_file(),"selected":sp is None or "/"not in rel or any(rel==s or rel.startswith(s.rstrip("/")+"/") for s in sp),"bytes":f.stat().st_size if f.is_file()else None,"ref":pin(f)if f.is_file()and f.stat().st_size<50000 else None})
# Read all directly declared source paths in the two already-read original C++ provider files.
for proj,rel in [("frameworks/compile/slang","Android.bp"),("frameworks/compile/libbcc","lib/Android.bp")]:
 p=src/proj/rel;txt=p.read_text()
 names=[]
 for block in re.finditer(r"\bsrcs\s*:\s*\[([^\]]*)\]",txt,re.S):
  names.extend(re.findall(r'"([^"]+)"',block.group(1)))
 for name in sorted(set(names)):
  if any(c in name for c in "*:"):continue
  f=p.parent/name
  out["known_inputs"].append({"project":proj,"provider_file":rel,"src_literal":name,"path":str(f.relative_to(src/proj)),"exists":f.is_file(),"bytes":f.stat().st_size if f.is_file()else None})
env={**os.environ,"GIT_NO_LAZY_FETCH":"1","GIT_OPTIONAL_LOCKS":"0","GIT_TERMINAL_PROMPT":"0","GIT_CONFIG_GLOBAL":"/dev/null","GIT_CONFIG_NOSYSTEM":"1"}
for proj,rel in [("frameworks/rs","script_api/include"),("external/clang","lib/Headers"),("prebuilts/sdk","renderscript/lib")]:
 p=projects[proj];r=subprocess.run(["/usr/bin/git","-C",str(src/proj),"ls-tree","-r",p["commit"],"--",rel],capture_output=True,env=env,timeout=20)
 rows=[]
 if r.returncode==0:
  for line in r.stdout.decode().splitlines():
   hdr,name=line.split("\t",1);mode,kind,oid=hdr.split();f=src/proj/name;rows.append({"path":name,"mode":mode,"type":kind,"oid":oid,"physical_exists":f.exists(),"symlink":f.is_symlink()})
 out["cones"].append({"project":proj,"path":rel,"commit":p["commit"],"selected_by_parent":any(rel==s or rel.startswith(s.rstrip("/")+"/")for s in p.get("sparse_paths",[])),"returncode":r.returncode,"stderr":r.stderr.decode(),"original_blob_count":sum(x["type"]=="blob"for x in rows),"physical_missing":[x for x in rows if not x["physical_exists"]],"source_rows_sha256":hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),"git_stdout_sha256":hashlib.sha256(r.stdout).hexdigest(),"git_stdout_bytes":len(r.stdout)})
rpath=root/"qualification/renderscript-provider-origin-r2/RESULT.json";result=json.loads(rpath.read_bytes());out["owner_origin_ref"]=pin(rpath)
pp=result.get("projects",[])
if isinstance(pp,dict):pp=[{"project_key":k,"value":v}for k,v in pp.items()]
for p in pp:
 x={"keys":list(p)if isinstance(p,dict)else str(type(p))}
 if isinstance(p,dict):
  for k,v in p.items():
   if isinstance(v,(str,int,float,bool))or v is None:x[k]=v
   elif isinstance(v,list):x[k+"_shape"]={"count":len(v),"first_keys":list(v[0])if v and isinstance(v[0],dict)else None}
 out["owner_origin_shape"].append(x)
for name in ["renderscript-api-consumer-audit-r2"]:
 p=root/"qualification"/name/"RESULT.json"
 if p.is_file():
  v=json.loads(p.read_bytes());out["owner_api_audit"]={"ref":pin(p),"qualification":v.get("qualification"),"lookup":v.get("lookup"),"source_write":v.get("source_write"),"source_manifest_unchanged":v.get("source_manifest_unchanged")}
print(json.dumps(out))
