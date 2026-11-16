import os,sys,json,subprocess,pathlib,hashlib,datetime,re,stat,shutil,zipfile,time
os.umask(0o077)
assert os.getuid()==1000
os.sched_setaffinity(0,{2})
root=pathlib.Path("/home/alex/work/pocket4-official-drift-20261109-2840-r1")
root.mkdir(mode=0o700,exist_ok=False)
inputs=json.load(sys.stdin)
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def write_json(p,obj):
 data=(json.dumps(obj,ensure_ascii=False,indent=2)+"\n").encode()
 with open(p,"xb") as f:f.write(data);f.flush();os.fsync(f.fileno())
def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
 return h.hexdigest()
def ref(p):
 s=p.stat();return {"path":str(p),"bytes":s.st_size,"sha256":sha(p),"uid":s.st_uid,"gid":s.st_gid,"mode":oct(stat.S_IMODE(s.st_mode))}
def ident(p):
 s=p.lstat();assert stat.S_ISREG(s.st_mode) and s.st_nlink==1
 return (s.st_dev,s.st_ino,s.st_size,s.st_mode,s.st_uid,s.st_gid,s.st_mtime_ns,s.st_ctime_ns)
write_json(root/"input.json",inputs)
assert shutil.disk_usage(root).free>1500000000
for exe in ["/usr/bin/curl","/usr/bin/aapt","/usr/bin/apksigner"]:
 assert os.access(exe,os.X_OK),exe
started=now();results=[]
for x in inputs:
 p=root/x["package"];p.mkdir(mode=0o700)
 result={"package":x["package"],"started_utc":now(),"previous_candidate":x,"installed":False,"canonical_custody":False,"selected":False,"runtime_accepted":False,"runtime_qualified":False,"production_ready":False,"whole_app_acceptance":"pending","artifact_input_eligible":False}
 try:
  apk=p/"official-current.apk";headers=p/"download.headers";meta_path=p/"curl.json";err_path=p/"curl.stderr"
  argv=["/usr/bin/curl","--fail","--location","--proto","=https","--proto-redir","=https","--max-redirs","5","--connect-timeout","20","--max-time","240","--max-filesize","536870912","--silent","--show-error","--dump-header",str(headers),"--output",str(apk),"--write-out","%{json}",x["official_current_download_url"]]
  with open(meta_path,"xb") as outf,open(err_path,"xb") as errf:
   command=subprocess.run(argv,stdout=outf,stderr=errf,timeout=250,check=False)
  result["download_command"]={"argv":argv,"exit_code":command.returncode,"stdout":ref(meta_path),"stderr":ref(err_path),"headers":ref(headers)}
  assert command.returncode==0,"official download failed"
  assert meta_path.stat().st_size<131072,"curl metadata over limit"
  meta=json.loads(meta_path.read_bytes())
  assert int(meta["http_code"])==200 and int(meta["ssl_verify_result"])==0
  import urllib.parse
  allowed={"com.lianjia.beike":{"m.ke.com","file.ljcdn.com"},"com.rytong.airchina":{"m.airchina.com.cn"}}[x["package"]]
  u=urllib.parse.urlsplit(meta["url_effective"])
  assert u.scheme=="https" and u.hostname in allowed,"unexpected publisher redirect host"
  size=apk.stat().st_size
  assert 0<size<=536870912 and size==int(meta["size_download"])
  with open(apk,"rb") as f:os.fsync(f.fileno())
  apk.chmod(0o400)
  before=ident(apk);artifact=ref(apk)
  result["artifact"]=artifact
  result["source_chain"]={"publisher_page":x["publisher_page"],"published_download_url":x["official_current_download_url"],"effective_url":meta["url_effective"],"http_status":int(meta["http_code"]),"ssl_verify_result":int(meta["ssl_verify_result"]),"bytes_downloaded":size,"redirects":int(meta.get("num_redirects",0)),"response_headers":ref(headers),"observed_utc":now(),"scope":"Current complete bytes served by the previously source-bound publisher public Android route at this observation, not a cross-store rollout assertion."}
  commands={}
  outputs={}
  for label,args in [("aapt-badging",["/usr/bin/aapt","dump","badging",str(apk)]),("aapt-manifest",["/usr/bin/aapt","dump","xmltree",str(apk),"AndroidManifest.xml"]),("apksigner",["/usr/bin/apksigner","verify","--verbose","--print-certs",str(apk)])]:
   out=p/(label+".stdout");err=p/(label+".stderr")
   with open(out,"xb") as outf,open(err,"xb") as errf:
    q=subprocess.run(args,stdout=outf,stderr=errf,timeout=180,check=False)
   assert out.stat().st_size<=16777216 and err.stat().st_size<=1048576,label+" output bound"
   commands[label]={"argv":args,"exit_code":q.returncode,"stdout":ref(out),"stderr":ref(err)}
   result["commands"]=commands
   assert q.returncode==0,label+" failed"
   outputs[label]=out.read_text(errors="strict")
  badging=outputs["aapt-badging"];manifest=outputs["aapt-manifest"];sig=outputs["apksigner"]
  pkg=re.findall(r"^package: name='([^']+)' versionCode='([0-9]+)' versionName='([^']*)'",badging,re.M)
  assert len(pkg)==1 and pkg[0][0]==x["package"],"package identity mismatch"
  _,code,name=pkg[0];code=int(code)
  native_lines=re.findall(r"^native-code: (.*)$",badging,re.M)
  abis=sorted(re.findall(r"'([^']+)'",native_lines[0])) if len(native_lines)==1 else []
  assert len(native_lines)<=1
  signers=sorted(re.findall(r"^Signer #[0-9]+ certificate SHA-256 digest: ([0-9a-fA-F]{64})$",sig,re.M))
  assert sig.startswith("Verifies\n") and signers and len(set(signers))==len(signers),"missing verified signer"
  schemes={m.group(1):m.group(2)=="true" for m in re.finditer(r"^Verified using (v[0-9.]+) scheme .*: (true|false)$",sig,re.M)}
  flags={}
  for flag in ["debuggable","testOnly","isSplitRequired"]:
   matches=re.findall(r"^\s*A: android:"+flag+r"\([^)]*\)=\(type 0x12\)(0x[0-9a-fA-F]+)\s*$",manifest,re.M)
   assert len(matches)<=1,"ambiguous manifest flag "+flag
   flags[flag]=False if not matches else int(matches[0],16)!=0
  package_line=next(l for l in badging.splitlines() if l.startswith("package: "))
  split_match=re.search(r"\bsplit='([^']+)'",package_line)
  split=split_match.group(1) if split_match else None
  with zipfile.ZipFile(apk) as z:
   infos=z.infolist();names=[i.filename for i in infos]
   assert len(infos)<=100000 and len(names)==len(set(names)),"ZIP entry ambiguity"
   assert "AndroidManifest.xml" in names and "classes.dex" in names
   zipabis=sorted({n.split("/")[1] for n in names if n.startswith("lib/") and n.endswith(".so") and len(n.split("/"))==3})
  assert zipabis==abis,"native ABI metadata mismatch"
  assert before==ident(apk),"APK changed during independent verification"
  result.update({"version_name":name,"version_code":code,"split_name":split,"native_abis":abis,"signature_verified":True,"signer_certificate_sha256":signers,"signature_schemes":schemes,"signature_warning_count":sum(l.startswith("WARNING:") for l in sig.splitlines()),"manifest_flags":flags,"archive":{"entries":len(names),"duplicate_entries":0,"AndroidManifest_present":True,"classes_dex_present":True,"native_library_abis":zipabis,"full_zip_crc_recheck_performed":False},"file_identity_unchanged_during_verification":True})
  comparison={"same_version_name":name==x["prior_version_name"],"same_version_code":code==x["prior_version_code"],"version_code_relation":"equal" if code==x["prior_version_code"] else ("newer" if code>x["prior_version_code"] else "older"),"same_native_abis":abis==sorted(x["prior_native_abis"]),"same_signer_set":signers==sorted(x["prior_signer_certificate_sha256"]),"same_full_sha256":artifact["sha256"]==x["prior_artifact"]["sha256"],"same_bytes":size==x["prior_artifact"]["bytes"],"matches_route_refresh_content_length":size==int(x["route_head"]["headers"]["content-length"])}
  result["comparison_to_prior_candidate"]=comparison
  eligible=code>=x["prior_version_code"] and comparison["same_signer_set"] and not split and not flags["debuggable"] and not flags["testOnly"] and not flags["isSplitRequired"] and "arm64-v8a" in abis
  result["artifact_input_eligible"]=eligible
  result["status"]="VERIFIED_OFFICIAL_SAME_VERSION_SAME_SIGNER_CHANGED_BYTES_CANDIDATE" if eligible and comparison["same_version_code"] and not comparison["same_full_sha256"] else ("VERIFIED_OFFICIAL_CURRENT_CANDIDATE" if eligible else "VERIFIED_ARTIFACT_REQUIRES_REVIEW")
 except Exception as e:
  result["status"]="FAILED_OR_BLOCKED"
  result["error"]={"type":type(e).__name__,"message":str(e)}
 result["completed_utc"]=now()
 write_json(p/"candidate.json",result)
 results.append(result)
 print(json.dumps({"package":result["package"],"status":result["status"],"artifact":result.get("artifact"),"version_name":result.get("version_name"),"version_code":result.get("version_code"),"native_abis":result.get("native_abis"),"signer_certificate_sha256":result.get("signer_certificate_sha256"),"comparison":result.get("comparison_to_prior_candidate"),"error":result.get("error"),"candidate":ref(p/"candidate.json")},ensure_ascii=False),flush=True)
final={"schema":"pocket4-official-current-route-drift-full-verification-v1","started_utc":started,"completed_utc":now(),"scope":"Only isolated full downloads and host APK inspection; no Android, install, package replacement, canonical write or user-data operation.","root":str(root),"input":ref(root/"input.json"),"candidates":results,"verified_current_inputs":sum(x["artifact_input_eligible"] for x in results),"runtime_accepted_count":0,"runtime_qualified":False,"production_ready":False}
write_json(root/"RESULT.json",final)
dirfd=os.open(root,os.O_RDONLY|os.O_DIRECTORY);os.fsync(dirfd);os.close(dirfd)
print(json.dumps({"result":ref(root/"RESULT.json"),"verified_current_inputs":final["verified_current_inputs"],"runtime_accepted_count":0,"production_ready":False}),flush=True)
sys.exit(0 if final["verified_current_inputs"]==len(inputs) else 1)

