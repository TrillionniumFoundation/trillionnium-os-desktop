"""27 owner-discovery/production-route controls; no installation or Android command."""
import hashlib,json,os,re,stat,sys,types
from pathlib import Path
BASE_ROOT=Path("/home/alex/work/pocket4-current-host-r6-source-01")
R6_MANIFEST="002ee581a4bb399536dd7d594d01f050e2540d9c049b0cfb37e1c96954b6caff"
REFERENCE_SHA="0a4a9f0d02b2a62f2b902983e43360c751a8f1952fb9ae7399850b112cb50a89"
PACKET_SHA="202e59b6656618e435d1c6fb988be21c18a864f580d826911db44e332f58e62a"
EXPECTED_FILES={"current_discovery.py","current_flow.py","check_current_discovery.py",
 "ihg_context.py","amazon_context.py","bestbuy_context.py","bili_install_state.py","host/source-manifest.json"}
def require(value,code):
 if not value:raise RuntimeError(code)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def read(path, maximum=1048576, expected=None, size=None):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
                0 <= before.st_size <= maximum, 'INPUT_SHAPE_OR_BOUND: ' + str(path))
        chunks = []; count = 0
        while True:
            part = os.read(fd, min(65536, maximum + 1 - count))
            if not part:
                break
            chunks.append(part); count += len(part)
            require(count <= maximum, 'INPUT_GREW: ' + str(path))
        after = os.fstat(fd)
        fields = ('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
        require(all(getattr(before, k) == getattr(after, k) for k in fields) and count == before.st_size,
                'INPUT_CHANGED: ' + str(path))
        raw = b''.join(chunks)
        require(expected is None or digest(raw) == expected, 'INPUT_SHA_CHANGED: ' + str(path))
        require(size is None or len(raw) == size, 'INPUT_SIZE_CHANGED: ' + str(path))
        return raw
    finally:
        os.close(fd)

def load_text(source,path,name):
    value=types.ModuleType(name);value.__file__=str(path)
    exec(compile(source,str(path),'exec'),value.__dict__)
    return value
def load_original_host(files):
    raw=read(BASE_ROOT/'source-manifest.json',131072,R6_MANIFEST)
    require(raw==files['host/source-manifest.json'],'EXACT_PUBLISHED_HOST_MANIFEST_REQUIRED')
    manifest=json.loads(raw)
    require(manifest.get('schema')==2 and manifest.get('revision')==6 and
            manifest.get('artifact')=='pocket4-bilibili-current-recorder-held-r6' and len(manifest['files'])==14,
            'EXACT_CURRENT_HOST_SOURCE_SCHEMA_REQUIRED')
    row=manifest['files']['source_contract.py']
    mod=load_text(read(BASE_ROOT/'source_contract.py',131072,row['sha256'],row['bytes']),
                  BASE_ROOT/'source_contract.py','original_current_host_contract')
    original=mod.SourceContract(BASE_ROOT/'source-manifest.json',R6_MANIFEST)
    original.verify()
    row=manifest['files']['current_coordinator.py']
    require(row['sha256']==REFERENCE_SHA,'CURRENT_COORDINATOR_PIN_CHANGED')
    ref=load_text(read(BASE_ROOT/'current_coordinator.py',131072,REFERENCE_SHA,row['bytes']),
                  BASE_ROOT/'current_coordinator.py','current_install_stage_reference')
    return ref,original,manifest

def main():
 raw=sys.stdin.buffer.read(262145)
 require(0<len(raw)<=262144 and digest(raw)==PACKET_SHA,"EXACT_BOUNDED_CONTROL_PACKET")
 packet=json.loads(raw)
 require(packet["schema"]=="pocket4-current-owner-controls27-source-v1" and
  set(packet["files"])==set(packet["source_pins"])==EXPECTED_FILES,"EXACT_CURRENT_DISCOVERY_SOURCE_SET")
 files={name:value.encode() for name,value in packet["files"].items()}
 for name,data in files.items():
  require(0<len(data)<=65536 and packet["source_pins"][name]=={"bytes":len(data),"sha256":digest(data)},
   "CONTROL_PRODUCTION_SOURCE_PIN_CHANGED")
  if name.endswith(".py"):compile(data,name,"exec")
 result={"schema":"pocket4-current-owner-discovery-controls27-v1","ok":False,"error":None,
  "secondary_errors":[],"source_pins":packet["source_pins"],
  "install_source_manifests":packet["install_source_manifests"],"cases":[],
  "Android_commands":0,"real_Status_children":0,"App_launches":0,"install_attempted":False,
  "UI_actions":0,"source_or_baseline_writes":0,"private_baseline_exported":False,
  "helper_nonces_consumed":False,"production_ready":False}
 ref=baseline=epoch=None;phase="actual_R6_source_and_baseline"
 try:
  ref,contract,manifest=load_original_host(files)
  baseline=ref.current_baseline()
  epoch=ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),ref.EPOCH_SOURCE,"owner_controls_epoch")
  result["Main_before"]=ref.main_guard(baseline,epoch)
  controls=load_text(files["check_current_discovery.py"],Path("/pure/check_current_discovery.py"),"actual_owner_controls")
  legacy=read(BASE_ROOT/"references/android_app.py",131072,controls.LEGACY_SHA,37574)
  phase="production_discovery"
  rows=controls.run_discovery_controls(files["current_discovery.py"],baseline,legacy)
  result["cases"]=[{"name":"common/"+row["name"],"passed":row["passed"]} for row in rows]
  for app in ("ihg","amazon","bestbuy"):
   phase="production_"+app+"_Context_route"
   context=load_text(files[app+"_context.py"],Path("/pure")/(app+"_context.py"),"owned_"+app+"_Context")
   own_files={**files,"install_state.py":files["bili_install_state.py"]}
   rows=controls.run_context_route_controls(context,own_files,baseline,legacy,
             packet["install_source_manifests"][app])
   result["cases"] += [{"name":app+"/"+row["name"],"passed":row["passed"]} for row in rows]
  phase="production_Bili_Flow_bind_route"
  entry=load_text(files["bili_install_state.py"],
    Path("/home/alex/work/pocket4-owned-bili-qa-r10-install-state-02/source/install_state.py"),
    "owned_Bili_install_entry")
  recorder=contract.load("recorder.py","actual_R6_recorder_for_owned_bind_controls")
  own_files={**files,"install_state.py":files["bili_install_state.py"]}
  rows=controls.run_bili_route_controls(entry,own_files,baseline,legacy,recorder)
  result["cases"] += [{"name":"bili/"+row["name"],"passed":row["passed"]} for row in rows]
  require(len(result["cases"])==27 and len({row["name"] for row in result["cases"]})==27 and
    all(row["passed"] is True for row in result["cases"]),"EXACT_27_OWNER_DISCOVERY_ROUTE_CONTROLS")
  result["count"]=27;result["all_passed"]=True;result["ok"]=True
 except BaseException as error:
  message=str(error)
  result["error"]={"phase":phase,"type":type(error).__name__,
   "code":message if re.fullmatch(r"[A-Za-z0-9_:./-]{1,200}",message) else "UNCLASSIFIED_CONTROL_ERROR",
   "message_sha256":digest(message.encode())}
 finally:
  if ref is not None and baseline is not None and epoch is not None:
   try:
    result["Main_after"]=ref.main_guard(baseline,epoch)
    require(result["Main_after"]==result.get("Main_before"),"CONTROL_MAIN_FENCE_CHANGED")
    contract.verify()
   except BaseException as error:
    result["secondary_errors"].append({"phase":"final_Main_and_source","type":type(error).__name__,
     "message_sha256":digest(str(error).encode())})
    result["ok"]=False
  print(json.dumps(result,sort_keys=True,separators=(",",":")),flush=True)
 return 0 if result["ok"] else 1
raise SystemExit(main())
