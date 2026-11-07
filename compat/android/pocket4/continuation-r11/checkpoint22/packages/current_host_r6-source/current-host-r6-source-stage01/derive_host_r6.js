function buildHostR6(old,actual,h) {
 const need=(v,m)=>{if(!v)throw Error(m);};const proof={};const r=actual.report;
 need(r.ok===true&&actual.guardRaw&&h.sha(actual.guardRaw)===r.generated_current_guard.sha256,"ACTUAL_BASELINE02_REQUIRED");
 const mapping=[
 ["pocket4-bilibili-current-recorder-held-r5","pocket4-bilibili-current-recorder-held-r6"],
 ["pocket4-current-recorder-scope-v1","pocket4-current-recorder-scope-v2"],
 ["pocket4-main-current-baseline-v1","pocket4-main-current-baseline-v2"],
 ["current-framework-generation","current-cell-generation"],
 [old.binding.epoch_sha256,r.new_epoch_sha256],
 [old.binding.baseline_sha256,r.baseline.sha256],
 [old.binding.qualification_sha256,r.qualification.sha256],
 [old.binding.guard_sha256,r.generated_current_guard.sha256],
 ["/home/alex/work/pocket4-main-current-baseline-01/","/home/alex/work/pocket4-main-current-baseline-02/"]
 ];
 const files={};for(const [name,oldRaw]of Object.entries(old.files)){
   if(name==="current_baseline_guard.py"){files[name]=actual.guardRaw;proof[name]={parent:{bytes:h.utf8(oldRaw).length,sha256:h.sha(oldRaw)},generated:{bytes:h.utf8(actual.guardRaw).length,sha256:h.sha(actual.guardRaw)},actual_generated_guard:true,inverse_byte_exact:false};continue;}
   let raw=oldRaw;const edits=[];
   if(!name.startsWith("references/"))for(const [a,b]of mapping){const n=raw.split(a).length-1;if(n){raw=raw.split(a).join(b);edits.push({old:a,next:b,count:n});}}
   let inv=raw;for(const x of [...edits].reverse()){need(inv.split(x.next).length-1===x.count,"INVERSE_OCCURRENCE:"+name);inv=inv.split(x.next).join(x.old);}need(inv===oldRaw,"INVERSE_EXACT:"+name);files[name]=raw;
   proof[name]={parent:{bytes:h.utf8(oldRaw).length,sha256:h.sha(oldRaw)},generated:{bytes:h.utf8(raw).length,sha256:h.sha(raw)},edits,inverse_byte_exact:true};
 }
 const binding={schema:"pocket4-main-current-baseline-v2",epoch_sha256:r.new_epoch_sha256,baseline_sha256:r.baseline.sha256,qualification_sha256:r.qualification.sha256,guard_sha256:r.generated_current_guard.sha256,historical_activation_sha256:old.binding.historical_activation_sha256,historical_verified_sha256:old.binding.historical_verified_sha256};
 const oldManifest=JSON.parse(old.manifest_raw);
 const manifest={schema:2,artifact:"pocket4-bilibili-current-recorder-held-r6",revision:6,parent_R5_manifest_sha256:old.manifest_sha256,historical_R4_manifest_sha256:oldManifest.parent_R4_manifest_sha256,current_baseline:binding,actual_baseline_result:{bytes:actual.actual.bytes,sha256:actual.actual.sha256},current_baseline_private:r.baseline,current_qualification:r.qualification,source_fork_is_not_deployment:true,old_flows_reauthorized:false,old_helpers_and_tasks_reauthorized:false,whole_app_production_ready:false,files:Object.fromEntries(Object.keys(files).sort().map(n=>[n,{bytes:h.utf8(files[n]).length,sha256:h.sha(files[n])}]))};
 const manifestRaw=JSON.stringify(manifest,null,2)+"\n";
 let controls=old.controls_source;
 for(const [a,b]of mapping.slice(0,4))controls=controls.split(a).join(b);
 const insert=`    negative("previous_current_epoch_rejected",lambda s,b:s.update(epoch_sha256="${old.binding.epoch_sha256}"))
    negative("previous_current_baseline_schema_rejected",lambda s,b:b.update(schema="pocket4-main-current-baseline-v1"))
    negative("previous_current_baseline_kind_rejected",lambda s,b:b.update(kind="current-framework-generation"))
    negative("previous_typed_scope_schema_rejected",lambda s,b:s.update(schema="pocket4-current-recorder-scope-v1"))
    negative("previous_baseline_digest_rejected",lambda s,b:s.update(current_baseline_sha256="${old.binding.baseline_sha256}"))
    negative("previous_qualification_digest_rejected",lambda s,b:s.update(current_baseline_qualification_sha256="${old.binding.qualification_sha256}"))
    # Only the filesystem boundary is a memory fixture. Execute the actual
    # SourceContract constructor, verify, path/manifest/source pin predicates.
    from pathlib import PurePosixPath
    import re
    class MemoryPath(PurePosixPath):
        def resolve(self):return self
    namespace={"__file__":"/current-source/source_contract.py","Path":MemoryPath,
               "PurePosixPath":PurePosixPath,"hashlib":hashlib,"json":json,"re":re,"types":types}
    selected=[x for x in ast.parse(files["source_contract.py"]).body
        if isinstance(x,(ast.Assign,ast.AnnAssign)) or
           (isinstance(x,ast.FunctionDef) and x.name in {"require","sha"}) or
           (isinstance(x,ast.ClassDef) and x.name=="SourceContract")]
    exec(compile(ast.Module(body=selected,type_ignores=[]),namespace["__file__"],"exec"),namespace)
    def constructor(manifest,override=None):
        text=json.dumps(manifest,sort_keys=True,separators=(",",":"))+"\\n"
        contents={"/current-source/source-manifest.json":text.encode(),
                  **{"/current-source/"+n:v.encode() for n,v in files.items()}}
        if override:contents.update(override)
        reads=[]
        def memory_read(path,limit=131072):
            key=str(path);require(key in contents,"FIXTURE_UNEXPECTED_SOURCE_READ")
            raw=contents[key];require(len(raw)<=limit,"FIXTURE_INPUT_BOUND");reads.append(key);return raw
        namespace["bounded_file"]=memory_read
        value=namespace["SourceContract"](MemoryPath("/current-source/source-manifest.json"),
                                         hashlib.sha256(text.encode()).hexdigest())
        require(set(reads)==set(contents),"ACTUAL_CONSTRUCTOR_DID_NOT_VERIFY_ALL_INPUTS")
        return value
    constructor(copy.deepcopy(m));passed("actual_source_constructor_all_fourteen_leaves")
    def constructor_no(name,change,code,override=None):
        manifest=copy.deepcopy(m);change(manifest)
        try:constructor(manifest,override)
        except RuntimeError as error:
            require(str(error)==code,"SOURCE_CONSTRUCTOR_WRONG_FIRST_ERROR")
        else:raise RuntimeError("SOURCE_CONSTRUCTOR_NEGATIVE_ACCEPTED")
        passed(name)
    constructor_no("old_host_artifact_rejected",lambda v:v.update(artifact="pocket4-bilibili-current-recorder-held-r5"),
                   "ADAPTER_MANIFEST_SCHEMA_CHANGED")
    constructor_no("missing_current_coordinator_rejected",lambda v:v["files"].pop("current_coordinator.py"),
                   "ADAPTER_SOURCE_CLOSURE_INCOMPLETE")
    constructor_no("old_manifest_baseline_schema_rejected",lambda v:v["current_baseline"].update(schema="pocket4-main-current-baseline-v1"),
                   "ACTUAL_CURRENT_HOST_MANIFEST_BINDING_REQUIRED")
    constructor_no("different_generated_guard_pin_rejected",lambda v:v["files"]["current_baseline_guard.py"].update(sha256="0"*64),
                   "CURRENT_GUARD_SOURCE_PIN_CHANGED")
    constructor_no("actual_constructor_runtime_source_drift_rejected",lambda v:None,
                   "ADAPTER_SOURCE_CHANGED:recorder.py", {"/current-source/recorder.py":b"changed\\n"})
`;
 const target='    require(len(rows)==26 and len({r["name"] for r in rows})==26,"EXACT_CURRENT_HOST_CONTROL_COUNT")';
 need(controls.split(target).length===2,"OLD_26_CONTROL_GATE");
 controls=controls.replace(target,insert+'    require(len(rows)==38 and len({r["name"] for r in rows})==38,"EXACT_CURRENT_HOST_CONTROL_COUNT")');
 controls=controls.replace('"schema":"pocket4-current-host-source-controls-v1"','"schema":"pocket4-current-host-source-controls-v2"');
 return {files,manifest,manifestRaw,manifest_sha256:h.sha(manifestRaw),binding,proof,controlsSource:controls,controlsExpected:38,actualBaseline:actual.actual};
}

function buildHostR6Stage(c,baselineSource,parents,h,ex) {
 const need=(v,m)=>{if(!v)throw Error(m);};const sourceRoot="/home/alex/work/pocket4-current-host-r6-source-01";
 const parentNames=["recorder.py","source_contract.py","existing_ui_entry.py"];
 const parentBodies=Object.fromEntries(parentNames.map(k=>[k,parents[k]]));
 const parentPins=Object.fromEntries(parentNames.map(k=>[k,{bytes:h.utf8(parents[k]).length,sha256:h.sha(parents[k])}]));
 const helperNames=["need","check","safe_error","ManagedFDs","metadata","exact_path","open_host","bounded_regular","load_module","write_new"];
 const inherited=helperNames.map(k=>ex(baselineSource,k)).join("\n");
 const python=x=>JSON.stringify(x);
 const script=`"""Stage one immutable host R6 source closure after current-cell qualification.
No helper install, Android entry, UI operation, process creation or task adoption.
"""
import hashlib,json,os,re,signal,stat,sys,time,types
from pathlib import Path
ROOT=Path(${python(sourceRoot)})
MANIFEST_SHA=${python(c.manifest_sha256)}
CONTROL_SHA=${python(h.sha(c.controlsSource))}
PARENT_PINS=json.loads(${python(JSON.stringify(parentPins))})
HOST_FILES=set(json.loads(${python(JSON.stringify(Object.keys(c.files).sort()))}))
GUARD_PATH=Path("/home/alex/work/pocket4-main-current-baseline-02/current_baseline_guard.py")
GUARD_SHA=${python(c.binding.guard_sha256)}
GUARD_BYTES=${c.manifest.files["current_baseline_guard.py"].bytes}
DEADLINE=time.monotonic()+70
${inherited}
def alarm(signum,frame):raise RuntimeError("HOST_SOURCE_STAGE_DEADLINE")
def encoded(value):return (json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)+"\\n").encode()
def validate_packet(packet):
    need(type(packet) is dict and set(packet)=={"schema","stage_source","files","manifest_raw","control_source","parents"} and
         packet["schema"]=="pocket4-current-host-r6-stage-packet-v1","EXACT_HOST_STAGE_PACKET")
    need(type(packet["files"]) is dict and set(packet["files"])==HOST_FILES,"EXACT_HOST_SOURCE_SET")
    need(type(packet["manifest_raw"]) is str and hashlib.sha256(packet["manifest_raw"].encode()).hexdigest()==MANIFEST_SHA,
         "HOST_MANIFEST_PIN")
    manifest=json.loads(packet["manifest_raw"])
    need(manifest.get("schema")==2 and manifest.get("artifact")=="pocket4-bilibili-current-recorder-held-r6" and
         manifest.get("revision")==6 and set(manifest.get("files",{}))==HOST_FILES,"EXACT_HOST_MANIFEST_SCHEMA")
    for name,raw in packet["files"].items():
        need(type(raw) is str and 0<len(raw.encode())<=131072,"HOST_SOURCE_MEMBER_BOUND")
        need(manifest["files"][name]=={"bytes":len(raw.encode()),"sha256":hashlib.sha256(raw.encode()).hexdigest()},
             "HOST_SOURCE_MEMBER_PIN")
    need(type(packet["control_source"]) is str and hashlib.sha256(packet["control_source"].encode()).hexdigest()==CONTROL_SHA,
         "HOST_CONTROL_SOURCE_PIN")
    need(type(packet["parents"]) is dict and set(packet["parents"])==set(PARENT_PINS),"EXACT_PARENT_SOURCE_SET")
    for name,raw in packet["parents"].items():
        need(type(raw) is str and PARENT_PINS[name]=={"bytes":len(raw.encode()),"sha256":hashlib.sha256(raw.encode()).hexdigest()},
             "ORIGINAL_CONTROL_PARENT_SOURCE_PIN")
    return manifest
def main(packet):
    os.umask(0o077);signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,70)
    result={"schema":"pocket4-current-host-source-stage-v2","ok":False,"error":None,"secondary_errors":[],
            "source_manifest_sha256":MANIFEST_SHA,"source_only":True,"runtime_admitted":False,
            "namespace_entry":False,"Android_commands":0,"UI_actions":0,"App_launches":0,"helper_installs":0,
            "children_spawned":0,"old_helpers_and_tasks_reauthorized":False,"whole_app_production_ready":False}
    pool=ManagedFDs();guard=None;created=False;manifest=None;phase="packet_and_controls";start=time.monotonic_ns()
    try:
        need(os.getuid()==os.geteuid()==0,"ROOT_HOST_STAGE_REQUIRED")
        manifest=validate_packet(packet)
        parents={**packet["files"],**packet["parents"]}
        controls=load_module(packet["control_source"].encode(),"current_host_r6_source_controls",
                             ROOT/"source-controls.py",CONTROL_SHA)
        report=controls.run_controls(packet["files"],parents,packet["manifest_raw"])
        need(report.get("all_passed") is True and report.get("count")==38 and len(report.get("cases",[]))==38 and
             all(row.get("passed") is True for row in report["cases"]) and len(report["compiled_sources"])==14,
             "ACTUAL_HOST_SOURCE_CONTROLS_REQUIRED")
        result["controls"]=report
        phase="current_Main_before"
        raw,_=bounded_regular(pool,str(GUARD_PATH),131072,GUARD_SHA,GUARD_BYTES)
        need(raw==packet["files"]["current_baseline_guard.py"].encode(),"GUARD_PACKET_AND_ACTUAL_FILE_DIFFER")
        guard=load_module(raw,"actual_current_host_r6_guard",GUARD_PATH,GUARD_SHA)
        result["Main_before"]=guard.current_guard()
        need(result["Main_before"]["schema"]=="pocket4-current-main-guard-v2" and
             result["Main_before"]["current_baseline_sha256"]==manifest["current_baseline"]["baseline_sha256"] and
             result["Main_before"]["current_baseline_qualification_sha256"]==manifest["current_baseline"]["qualification_sha256"] and
             result["Main_before"]["Main_epoch_sha256"]==manifest["current_baseline"]["epoch_sha256"],
             "CURRENT_BASELINE_HOST_BINDING_CHANGED")
        phase="create_only_host_source_root"
        need(not os.path.lexists(ROOT),"FRESH_HOST_SOURCE_ROOT_REQUIRED")
        parent=open_host(pool,str(ROOT.parent),os.O_PATH|os.O_DIRECTORY)
        try:os.mkdir(ROOT.name,mode=0o700,dir_fd=parent);created=True
        finally:pool.close(parent)
        root=open_host(pool,str(ROOT),os.O_PATH|os.O_DIRECTORY)
        try:
            info=os.fstat(root)
            need(info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o700,"PRIVATE_HOST_SOURCE_ROOT")
            os.mkdir("references",mode=0o700,dir_fd=root)
        finally:pool.close(root)
        phase="write_exact_host_sources"
        source_pins={}
        for name,text in sorted(packet["files"].items()):
            source_pins[name]=write_new(pool,ROOT/name,text.encode())
        source_pins["source-manifest.json"]=write_new(pool,ROOT/"source-manifest.json",packet["manifest_raw"].encode())
        for directory in (ROOT/"references",ROOT,ROOT.parent):
            fd=open_host(pool,str(directory),os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:pool.close(fd)
        phase="real_staged_source_contract"
        source=load_module(packet["files"]["source_contract.py"].encode(),"staged_host_r6_source",ROOT/"source_contract.py")
        contract=source.SourceContract(ROOT/"source-manifest.json",MANIFEST_SHA)
        contract.verify()
        result["actual_source_constructor_qualified"]=True
        result["source_root"]=str(ROOT);result["source_pins"]=source_pins
        phase="current_Main_after"
        result["Main_after"]=guard.current_guard()
        need(result["Main_after"]==result["Main_before"],"MAIN_CHANGED_DURING_HOST_SOURCE_STAGE")
        phase="source_revalidation"
        for name,pin in source_pins.items():
            bounded_regular(pool,pin["path"],131072,pin["sha256"],pin["bytes"])
        result["all_staged_sources_unchanged"]=True
    except BaseException as error:result["error"]={"phase":phase,**safe_error(error)}
    finally:
        if guard is not None:
            try:
                result["Main_final"]=guard.current_guard()
                need(result.get("Main_before")==result["Main_final"],"FINAL_MAIN_CHANGED")
            except BaseException as error:result["secondary_errors"].append({"phase":"final_Main",**safe_error(error)})
        pool.close_all();result["source_fds"]=pool.summary()
        try:pool.require_clean()
        except BaseException as error:result["secondary_errors"].append({"phase":"source_fd_retirement",**safe_error(error)})
    result["ok"]=bool(result["error"] is None and not result["secondary_errors"] and
                      result.get("actual_source_constructor_qualified") is True and
                      result.get("all_staged_sources_unchanged") is True)
    result["elapsed_ns"]=time.monotonic_ns()-start
    output=ManagedFDs()
    if created:
        try:
            pin=write_new(output,ROOT/"stage-result.json",encoded(result))
            result["stage_result"]=pin
            fd=open_host(output,str(ROOT),os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:output.close(fd)
        except BaseException as error:
            result["ok"]=False;result["secondary_errors"].append({"phase":"stage_result_publication",**safe_error(error)})
        finally:output.close_all()
    result["publication_fds"]=output.summary()
    try:output.require_clean()
    except BaseException as error:
        result["ok"]=False;result["secondary_errors"].append({"phase":"publication_fd_retirement",**safe_error(error)})
    signal.setitimer(signal.ITIMER_REAL,0)
    raw=encoded(result);need(len(raw)<=65536,"HOST_STAGE_SAFE_RESULT_BOUND")
    sys.stdout.write(raw.decode());sys.stdout.flush()
    return 0 if result["ok"] else 1
`;
 const packet={schema:"pocket4-current-host-r6-stage-packet-v1",stage_source:script,files:c.files,manifest_raw:c.manifestRaw,control_source:c.controlsSource,parents:parentBodies};
 const stdin=JSON.stringify(packet)+"\n";need(h.utf8(stdin).length<=524288,"HOST_STAGE_PACKET_BOUND");
 const wrapper=`import hashlib,json,sys\nraw=sys.stdin.buffer.read(524289)\nassert len(raw)<=524288 and hashlib.sha256(raw).hexdigest()==${python(h.sha(stdin))}\np=json.loads(raw);source=p["stage_source"]\nassert hashlib.sha256(source.encode()).hexdigest()==${python(h.sha(script))}\nscope={"__name__":"current_host_r6_stage","__file__":${python(sourceRoot+"/stage_current_host.py")}}\nexec(compile(source,scope["__file__"],"exec"),scope)\nraise SystemExit(scope["main"](p))\n`;
 const request={host:"pocket4",executable:"/usr/bin/sudo",args:["-n","/usr/bin/python3","-I","-B","-c",wrapper],cwd:"/",idempotency_key:"pocket4-current-host-r6-source-stage01-"+h.sha(stdin).slice(0,16),timeout_seconds:90,cpu_quota_percent:25,memory_max_bytes:134217728,nice:15,stdin};
 const requestRaw=JSON.stringify(request,null,2)+"\n";
 return {sourceRoot,script,packet,stdin,wrapper,request,requestRaw,parentPins,parentBodies,inheritedFunctions:helperNames};
}
