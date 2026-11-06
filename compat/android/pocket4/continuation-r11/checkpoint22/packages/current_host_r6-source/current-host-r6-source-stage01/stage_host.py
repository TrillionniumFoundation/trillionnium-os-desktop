"""Stage one immutable host R6 source closure after current-cell qualification.
No helper install, Android entry, UI operation, process creation or task adoption.
"""
import hashlib,json,os,re,signal,stat,sys,time,types
from pathlib import Path
ROOT=Path("/home/alex/work/pocket4-current-host-r6-source-01")
MANIFEST_SHA="002ee581a4bb399536dd7d594d01f050e2540d9c049b0cfb37e1c96954b6caff"
CONTROL_SHA="47df73fa3495931ef29e4050ee96df2c8ac33e97977203a187049fa3e9c3baa0"
PARENT_PINS=json.loads("{\"recorder.py\":{\"bytes\":40090,\"sha256\":\"5f25f22db55ba94e6ac895c2ce274b6959a274b64c9aa82bbc30d8c3c860f511\"},\"source_contract.py\":{\"bytes\":9103,\"sha256\":\"51c2b3dd7df80a8fcd4881eb7216f7292db77d39c01920f10feb650824919a7d\"},\"existing_ui_entry.py\":{\"bytes\":12963,\"sha256\":\"36da94a76fc336d259c19b33c522e1a6746d676d7e59ccaffab115dcadc68ebc\"}}")
HOST_FILES=set(json.loads("[\"bound_android_transport.py\",\"current_baseline_guard.py\",\"current_coordinator.py\",\"existing_ui_entry.py\",\"main_binding.py\",\"recorder.py\",\"references/android_app.py\",\"references/android_backend.py\",\"references/bound_android_transport_r3.py\",\"references/framework_epoch.py\",\"references/held_runtime_r5.py\",\"references/original_recorder.py\",\"references/task_scope_baseline.py\",\"source_contract.py\"]"))
GUARD_PATH=Path("/home/alex/work/pocket4-main-current-baseline-02/current_baseline_guard.py")
GUARD_SHA="96dbdaf7673d5298e6fe17cb1b7ebae29b37110ee59f31b0c927e2cb0ef4b150"
GUARD_BYTES=11541
DEADLINE=time.monotonic()+70
def need(v,m):
    if not v:raise RuntimeError(m)


def check():need(time.monotonic()<DEADLINE,'DIAGNOSTIC_DEADLINE')


def safe_error(error):
    row={"type":type(error).__name__}
    if isinstance(error,OSError):
        row["errno"]=error.errno
    elif isinstance(error,RuntimeError) and re.fullmatch(r"[A-Z0-9_]{1,96}",str(error)):
        row["code"]=str(error)
    else:
        row["code"]="UNEXPECTED_DIAGNOSTIC_FAILURE"
    return row


class ManagedFDs:
    def __init__(self):
        self.active={};self.acquired=0;self.close_attempts=0;self.closed=0;self.errors=[]
    def own(self,fd,label):
        if fd<3:
            try:os.close(fd)
            finally:raise RuntimeError("OWNED_FD_ALIASED_STANDARD_STREAM")
        need(fd not in self.active,"DUPLICATE_ACTIVE_FD")
        self.active[fd]=label;self.acquired+=1
        return fd
    def close(self,fd):
        if fd not in self.active:return
        label=self.active.pop(fd);self.close_attempts+=1
        try:os.close(fd);self.closed+=1
        except BaseException as e:self.errors.append({"phase":label,**safe_error(e)})
    def close_all(self):
        for fd in reversed(tuple(self.active)):self.close(fd)
    def require_clean(self):
        need(not self.active and not self.errors and self.acquired==self.closed==self.close_attempts,
             "MANAGED_FD_RETIREMENT_INCOMPLETE")
    def summary(self):
        return {"scope":"collector_managed_descriptors","acquired":self.acquired,"close_attempts":self.close_attempts,
                "closed":self.closed,"remaining":len(self.active),"errors":self.errors}


def metadata(fd):
    x=os.fstat(fd)
    return {k:getattr(x,k) for k in ("st_dev","st_ino","st_mode","st_uid","st_gid","st_nlink","st_size","st_mtime_ns","st_ctime_ns")}


def exact_path(path):
    need(type(path) is str and path.startswith("/") and not path.startswith("//") and "\0" not in path
         and all(x not in ("",".","..") for x in path[1:].split("/")),"EXACT_ABSOLUTE_PATH_REQUIRED")
    return path[1:].split("/")


def open_host(pool,path,flags=os.O_RDONLY):
    parts=exact_path(path);chain=[]
    try:
        d=pool.own(os.open("/",os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC),"host_root")
        chain.append(d)
        for name in parts[:-1]:
            d=pool.own(os.open(name,os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=d),"host_parent")
            chain.append(d)
        fd=pool.own(os.open(parts[-1],flags|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=d),"host_leaf")
        return fd
    finally:
        for fd in reversed(chain):pool.close(fd)


def bounded_regular(pool,path,limit,pin=None,size=None):
    check();fd=open_host(pool,path);raw=None
    try:
        before=metadata(fd)
        need(stat.S_ISREG(before["st_mode"]) and before["st_nlink"]==1 and
             0<=before["st_size"]<=limit,"BOUNDED_SINGLE_LINK_REGULAR_REQUIRED")
        chunks=[];count=0
        while True:
            check();part=os.read(fd,min(65536,limit+1-count))
            if not part:break
            count+=len(part);need(count<=limit,"REGULAR_FILE_BYTE_BOUND");chunks.append(part)
        raw=b"".join(chunks)
        need(len(raw)==before["st_size"] and metadata(fd)==before,"REGULAR_FILE_CHANGED_DURING_READ")
        need(pin is None or hashlib.sha256(raw).hexdigest()==pin,"EXACT_FILE_SHA_CHANGED")
        need(size is None or len(raw)==size,"EXACT_FILE_SIZE_CHANGED")
        return raw,before
    finally:pool.close(fd)


def load_module(raw,name,path,pin=None):
    if pin is not None:need(hashlib.sha256(raw).hexdigest()==pin,"MODULE_PIN_CHANGED")
    mod=types.ModuleType(name);mod.__file__=str(path)
    exec(compile(raw,str(path),"exec"),mod.__dict__)
    return mod


def write_new(pool,path,raw,mode=0o400):
    need(type(raw) is bytes and 0<len(raw)<=4*1024*1024,"OWNED_ARTIFACT_WRITE_BOUND")
    fd=open_host(pool,str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL)
    try:
        os.fchmod(fd,mode);offset=0
        while offset<len(raw):
            count=os.write(fd,raw[offset:]);need(count>0,"SHORT_ARTIFACT_WRITE");offset+=count
        os.fsync(fd)
        info=os.fstat(fd);need(info.st_uid==0 and stat.S_ISREG(info.st_mode) and info.st_nlink==1 and
                              info.st_size==len(raw) and stat.S_IMODE(info.st_mode)==mode,"OWNED_OUTPUT_METADATA")
    finally:pool.close(fd)
    return {"path":str(path),"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}


def alarm(signum,frame):raise RuntimeError("HOST_SOURCE_STAGE_DEADLINE")
def encoded(value):return (json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
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
