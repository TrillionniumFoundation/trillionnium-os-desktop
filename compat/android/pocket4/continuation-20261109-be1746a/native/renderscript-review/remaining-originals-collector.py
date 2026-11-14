import pathlib,json,hashlib,urllib.request,base64,datetime,traceback,time
root=pathlib.Path("/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1")
outdir=pathlib.Path("/home/qq/work/pocket4-renderscript-originals-be1746a-r1")
outdir.mkdir(mode=0o700,exist_ok=False)
lock=root/"recipe-tradefed-r1/android/native-generation-pair/source-lock.json";before=hashlib.sha256(lock.read_bytes()).hexdigest()
commit="943016fade3dbbb725c363d0dc60a6e962bd88e5";expected={"tools/bcc/Android.bp":"d2d36ad8c2f94c6548e085613b99d9fe16a7647e","tools/bcc/Main.cpp":"e1d3096ff7b355b905d99c213eb3d723265f2516","tools/bcc_strip_attr/Android.bp":"724377036218b7d04636939a63e7cd6a80dc8d83","tools/bcc_strip_attr/bcc_strip_attr.cpp":"d987635c4b110826d0a3d67e9f4d1271a5340210"}
v={"schema":1,"started_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"scope":"four exact original libbcc tools blobs only; independent directory; no Git cache/source writes","project":"platform/frameworks/compile/libbcc","commit":commit,"output_dir":str(outdir),"files":[],"errors":[],"source_lock_sha256_before":before,"source_write":False,"full_build_started":False,"child_processes_started":0}
try:
 for rel,oid in expected.items():
  url="https://android.googlesource.com/platform/frameworks/compile/libbcc/+/"+commit+"/"+rel+"?format=TEXT"
  t=time.monotonic()
  with urllib.request.urlopen(url,timeout=15) as response:
   encoded=response.read(1048577)
   if len(encoded)>1048576:raise RuntimeError("bounded original response exceeded 1 MiB")
   status=response.status
  raw=base64.b64decode(encoded,validate=True);actual=hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
  if actual!=oid:raise RuntimeError("original Git blob mismatch "+rel)
  p=outdir/"original"/rel;p.parent.mkdir(parents=True,exist_ok=True)
  with p.open("xb")as f:f.write(raw)
  v["files"].append({"path":rel,"url":url,"http_status":status,"elapsed_seconds":round(time.monotonic()-t,3),"git_blob_oid":actual,"expected_git_blob_oid":oid,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"saved_path":str(p),"body":raw.decode()})
 v["state"]="EXACT_ORIGINAL_TOOLS_BLOBS_VERIFIED"
except Exception:
 v["state"]="FAILED";v["errors"].append(traceback.format_exc())
finally:
 v["source_lock_sha256_after"]=hashlib.sha256(lock.read_bytes()).hexdigest();v["source_manifest_unchanged"]=v["source_lock_sha256_after"]==before
 v["finished_utc"]=datetime.datetime.now(datetime.timezone.utc).isoformat()
 data=(json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2)+"\n").encode()
 with (outdir/"RESULT.json").open("xb")as f:f.write(data)
 print(json.dumps({"result_path":str(outdir/"RESULT.json"),"result_bytes":len(data),"result_sha256":hashlib.sha256(data).hexdigest(),"result":v}))
raise SystemExit(0 if v["state"]=="EXACT_ORIGINAL_TOOLS_BLOBS_VERIFIED"else 1)
