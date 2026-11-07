"""Fresh current-baseline fence. No deployment, discovery, namespace entry or action.

A caller must pin this generated module and use a separately admitted new flow.
The unresolved framework-exit cause remains a production acceptance gate.
"""
import hashlib,json,os,stat,time,types
from pathlib import Path
ROOT=Path("/home/alex/work/pocket4-main-current-baseline-02")
SOURCE=ROOT/"source"
BASELINE_PATH=ROOT/"baseline.private.json"
QUALIFICATION_PATH=ROOT/"qualification.json"
BASELINE_SHA="@@BASELINE_SHA@@"
QUALIFICATION_SHA="@@QUALIFICATION_SHA@@"
BASELINE_BYTES=@@BASELINE_BYTES@@
QUALIFICATION_BYTES=@@QUALIFICATION_BYTES@@
MAIN_EPOCH="@@CURRENT_EPOCH@@"
SOURCE_MANIFEST_SHA="@@MANIFEST_SHA@@"
SOURCE_SCHEMA="pocket4-current-baseline-source-v2"
EXPECTED_FILES={"qualify_baseline.py","baseline_policy.py","controls.py","framework_epoch.py","held_runtime_r5.py","historical_source_contract.py","current_baseline_guard.template.py","cell_ancestry.py"}
REFERENCE_PINS={"framework_epoch.py":(8658,"f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288"),
 "held_runtime_r5.py":(22691,"72cf33399ca3c280fc0c9288669f7d6c13d387e41b5fb930cf477f2b940f16b4")}
def need(v,code):
    if not v:raise RuntimeError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def meta(fd):
    x=os.fstat(fd)
    return {k:getattr(x,k) for k in ("st_dev","st_ino","st_mode","st_uid","st_gid","st_nlink","st_size","st_mtime_ns","st_ctime_ns")}
def raw_file(path,limit,pin=None,size=None):
    path=str(path);need(path.startswith("/") and not path.startswith("//") and "\0" not in path and
         all(x not in ("",".","..") for x in path[1:].split("/")),"FIXED_SOURCE_PATH_REQUIRED")
    fds=[];primary=None;close_errors=[];deadline=time.monotonic()+5
    try:
        d=os.open("/",os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC);fds.append(d)
        parts=path[1:].split("/")
        for part in parts[:-1]:
            d=os.open(part,os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=d);fds.append(d)
        fd=os.open(parts[-1],os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=d);fds.append(fd)
        before=meta(fd);need(stat.S_ISREG(before["st_mode"]) and before["st_nlink"]==1 and
            0<=before["st_size"]<=limit,"PINNED_FILE_SHAPE")
        chunks=[];count=0
        while True:
            need(time.monotonic()<deadline,"PINNED_FILE_READ_DEADLINE")
            data=os.read(fd,min(65536,limit+1-count))
            if not data:break
            count+=len(data);need(count<=limit,"PINNED_FILE_BOUND");chunks.append(data)
        raw=b"".join(chunks)
        need(len(raw)==before["st_size"] and meta(fd)==before,"PINNED_FILE_CHANGED")
        need((pin is None or sha(raw)==pin) and (size is None or len(raw)==size),"PINNED_FILE_BYTES_CHANGED")
        return raw
    except BaseException as e:primary=e;raise
    finally:
        for fd in reversed(fds):
            try:os.close(fd)
            except BaseException as e:close_errors.append(type(e).__name__)
        if close_errors:
            if primary is None:raise RuntimeError("PINNED_FILE_DESCRIPTOR_CLOSE_FAILED")
            primary.add_note("PINNED_FILE_DESCRIPTOR_CLOSE_FAILED")
def module(raw,name,path):
    mod=types.ModuleType(name);mod.__file__=str(path)
    exec(compile(raw,str(path),"exec"),mod.__dict__)
    return mod
def source_modules():
    raw=raw_file(SOURCE/"SOURCE_PINS.json",65536,SOURCE_MANIFEST_SHA)
    manifest=json.loads(raw)
    need(manifest.get("schema")==SOURCE_SCHEMA and set(manifest.get("files",{}))==EXPECTED_FILES,
         "CURRENT_BASELINE_SOURCE_SET_CHANGED")
    contents={}
    for name,pin in manifest["files"].items():
        contents[name]=raw_file(SOURCE/name,65536,pin["sha256"],pin["bytes"])
    for name,(n,digest) in REFERENCE_PINS.items():
        need(len(contents[name])==n and sha(contents[name])==digest,"FROZEN_GUARD_REFERENCE_CHANGED")
    p=module(contents["baseline_policy.py"],"current_guard_policy",SOURCE/"baseline_policy.py")
    e=module(contents["framework_epoch.py"],"current_guard_epoch",SOURCE/"framework_epoch.py")
    h=module(contents["held_runtime_r5.py"],"current_guard_root_reader",SOURCE/"held_runtime_r5.py")
    c=module(contents["cell_ancestry.py"],"current_guard_cell_ancestry",SOURCE/"cell_ancestry.py")
    return p,e,h,c
def load_current():
    p,e,h,c=source_modules()
    b=p.parse(raw_file(BASELINE_PATH,4*1024*1024,BASELINE_SHA,BASELINE_BYTES))
    q=p.parse(raw_file(QUALIFICATION_PATH,65536,QUALIFICATION_SHA,QUALIFICATION_BYTES))
    p.validate_new_baseline(b)
    need(b["framework_epoch"]["sha256"]==MAIN_EPOCH and q.get("schema")==p.QUAL_SCHEMA and
         q.get("identity_qualified") is True and q.get("epoch_sha256")==MAIN_EPOCH and
         q.get("baseline")=={"path":str(BASELINE_PATH),"bytes":BASELINE_BYTES,"sha256":BASELINE_SHA} and
         q.get("source_manifest_sha256")==SOURCE_MANIFEST_SHA and
         q.get("historical_deployment_revalidated") is True and
         q.get("new_deployment_performed") is False and q.get("old_epoch_reauthorized") is False and
         q.get("three_double_samples_equal") is True and q.get("final_seven_role_identity_equal") is True and
         q.get("previous_current_baseline")==p.PREVIOUS_BASELINE and q.get("discovery_observation")==p.DISCOVERY and
         q.get("three_owner_chain_and_user_namespace_samples_equal") is True and
         q.get("final_owner_chain_and_user_namespaces_equal") is True and
         q.get("seven_executable_content_lineages_equal") is True and q.get("user_namespaces_freshly_measured") is True and
         q.get("old_helpers_and_tasks_reauthorized") is False and
         q.get("protected_process_projection_is_actual_measurement") is True and
         q.get("protected_processes")==p.protected_process_projection(b["all_seven_processes"],b["process_roots"],b["owner_lineage"]) and
         q.get("all_owned_service_children_joined") is True and
         q.get("framework_exit_cause_resolved") is False and q.get("production_ready") is False and
         q.get("UI_or_install_runtime_admitted") is False,"ACTUAL_CURRENT_BASELINE_QUALIFICATION_REQUIRED")
    fds=q["observation_fds"]
    need(fds["acquired"]==fds["closed"]==fds["close_attempts"] and fds["remaining"]==0 and
         fds["errors"]==[],"BASELINE_OBSERVATION_FDS_NOT_RETIRED")
    return b,q,p,e,h,c
def current_baseline():
    b,_,_,_,_,_=load_current()
    return b
def current_guard(candidate=None,*,action_attempted=False):
    b,q,p,e,h,c=load_current()
    need(candidate is None or candidate==b,"CACHED_BASELINE_DIFFERS_FROM_PINNED_CURRENT_BASELINE")
    old=p.parse(raw_file(p.ACTIVATION_PATH,131072,p.ACTIVATION_SHA,p.ACTIVATION_BYTES))
    verified=p.parse(raw_file(p.VERIFIED_PATH,131072,p.VERIFIED_SHA))
    p.historical(old,verified)
    previous=p.parse(raw_file(p.PREVIOUS_BASELINE["path"],131072,
                  p.PREVIOUS_BASELINE["sha256"],p.PREVIOUS_BASELINE["bytes"]))
    p.validate_previous_baseline(previous,old)
    p.validate_executable_content(b["current_process_executables"],p.executable_content(previous["current_process_executables"]))
    raw_file(p.CELL_PATH,131072,p.CELL_SHA)
    e.require_unchanged(b["framework_epoch"],action_attempted=action_attempted)
    fixed=e.capture_processes({k:v["pid"] for k,v in p.EXPECTED.items()})
    need(fixed["binding"]==b["all_seven_processes"]["binding"],"CURRENT_SEVEN_ROLE_BINDING_CHANGED")
    procs={};roots={};pidfds={};pool=c.ManagedFDs();primary=None;guard_deadline=time.monotonic()+8
    def check():
        need(time.monotonic()<guard_deadline,"CURRENT_CELL_GUARD_READ_DEADLINE")
    try:
        for role,row in p.EXPECTED.items():
            check()
            pidfds[role]=pool.own(os.pidfd_open(row["pid"],0),"guard_fixed_role_pidfd")
            c.require_pidfd_live(pidfds[role])
            proc=pool.own(os.open("/proc/"+str(row["pid"]),os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW),
                          "guard_fixed_role_proc")
            procs[role]=proc
            root=pool.own(os.open("root",os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC,dir_fd=proc),"guard_fixed_role_root")
            roots[role]=root;rs=os.fstat(root)
            need({"device":rs.st_dev,"inode":rs.st_ino}==b["process_roots"][role],"CURRENT_ROOT_CHANGED")
            need(os.readlink("ns/user",dir_fd=proc)==b["owner_lineage"]["role_user_namespaces"][role],
                 "CURRENT_USER_NAMESPACE_CHANGED")
            exe=pool.own(os.open("exe",os.O_RDONLY|os.O_CLOEXEC,dir_fd=proc),"guard_fixed_role_executable")
            need(meta(exe)==b["current_process_executables"][role]["file"],"CURRENT_EXECUTABLE_FILE_IDENTITY_CHANGED")
        intermediary=c.hold_intermediary(pool,p)
        lineage=c.sample(pool,p,e,procs,intermediary,check)
        need(lineage==b["owner_lineage"],"CURRENT_OWNER_CHAIN_OR_USER_NAMESPACE_CHANGED")
        p.validate_snapshot(fixed,old,b["process_roots"])
        engine=pool.own(h.open_in_root(roots["android_init"],"/system/lib64/libberberis_arm64.so",os.O_RDONLY),
                        "guard_current_engine")
        need(meta(engine)==b["engine_artifact"]["file"],"CURRENT_ENGINE_FILE_IDENTITY_CHANGED")
        limits={}
        for name in p.LIMITS:
            check();path="/sys/fs/cgroup/system.slice/droidloomd.service/"+name
            fd=pool.own(os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW),"guard_cgroup_limit")
            raw=os.read(fd,8193);need(len(raw)<=8192,"CGROUP_LIMIT_BOUND")
            limits[name]=raw.decode("ascii","strict").strip()
        need(limits==p.LIMITS==b["limits"],"MAIN_RESOURCE_LIMITS_CHANGED")
        again=e.capture_processes({k:v["pid"] for k,v in p.EXPECTED.items()})
        need(again["binding"]==fixed["binding"],"CURRENT_FULL_IDENTITIES_CHANGED_DURING_GUARD")
        final_lineage=c.sample(pool,p,e,procs,intermediary,check)
        need(final_lineage==lineage,"CURRENT_OWNER_CHAIN_CHANGED_DURING_GUARD")
        for fd in pidfds.values():c.require_pidfd_live(fd)
        e.require_unchanged(b["framework_epoch"],action_attempted=action_attempted)
        check()
    except BaseException as error:primary=error;raise
    finally:
        pool.close_all()
        try:pool.require_clean()
        except BaseException:
            if primary is None:raise RuntimeError("CURRENT_BASELINE_GUARD_FD_CLOSE_FAILED")
            primary.add_note("CURRENT_BASELINE_GUARD_FD_CLOSE_FAILED")
    return {"schema":"pocket4-current-main-guard-v2","Main_epoch_sha256":MAIN_EPOCH,
       "current_baseline_sha256":BASELINE_SHA,"current_baseline_qualification_sha256":QUALIFICATION_SHA,
       "historical_activation_sha256":p.ACTIVATION_SHA,"historical_verified_sha256":p.VERIFIED_SHA,
       "previous_current_baseline_sha256":p.PREVIOUS_BASELINE["sha256"],
       "config_sha256":p.CELL_SHA,"seven_processes_match":True,"three_host_processes_match":True,
       "authenticated_owner_chain_matches":True,"current_user_namespaces_match":True,
       "resource_limits_match":True,"current_executable_and_root_backing_match":True,
       "old_helpers_and_tasks_reauthorized":False,"framework_exit_cause_resolved":False,"production_ready":False}
def main_guard(activation=None,epoch=None):
    # Legacy parameter names preserve call shape; the accepted document is
    # exclusively the typed current-baseline schema. An old activation fails.
    return current_guard(activation,action_attempted=False)
