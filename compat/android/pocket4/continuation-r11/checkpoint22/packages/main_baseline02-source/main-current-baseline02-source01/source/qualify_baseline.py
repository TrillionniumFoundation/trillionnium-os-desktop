"""Collect one independent current framework baseline; never deploy or enter Android.

Private full identities/argv/maps are written only below the new root. The
stdout receipt exports pins and closed system-role facts. Historical deployment
is verified by its original exact files, never rewritten as a current deploy.
"""
import hashlib,json,os,re,select,selectors,signal,stat,subprocess,time,types
from pathlib import Path
ROOT=Path("/home/alex/work/pocket4-main-current-baseline-02")
SOURCE=ROOT/"source"
DEADLINE=time.monotonic()+110
BOOT_ID="981ff371-cd72-4f81-9be3-a862111afdb1"
INVOCATION="67cdc2375f394012ad9d7f39b0d77426"
CG="/sys/fs/cgroup/system.slice/droidloomd.service"
PROPERTIES=('MainPID','ControlGroup','InvocationID','ActiveState','SubState','Result','NRestarts','ExecMainStartTimestampMonotonic','StateChangeTimestampMonotonic','MemoryCurrent','MemoryPeak','TasksCurrent')
ENV={"PATH":"/usr/bin:/bin","LANG":"C","LC_ALL":"C","TZ":"UTC","SYSTEMD_PAGER":"","SYSTEMD_COLORS":"0"}
FILES={"qualify_baseline.py","baseline_policy.py","controls.py","framework_epoch.py","held_runtime_r5.py","historical_source_contract.py","current_baseline_guard.template.py","cell_ancestry.py"}
FROZEN_REFS={"framework_epoch.py":(8658,"f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288"),
 "held_runtime_r5.py":(22691,"72cf33399ca3c280fc0c9288669f7d6c13d387e41b5fb930cf477f2b940f16b4"),
 "historical_source_contract.py":(9103,"51c2b3dd7df80a8fcd4881eb7216f7292db77d39c01920f10feb650824919a7d")}
SOURCE_PINS={"journal03_actual_stdout_sha256":"210937399a340b632ef5cca71860caafdbde81cff405c4b52c184425a71d316b",
 "identity_read02_actual_stdout_sha256":"b49bbb4276c5a95de610956c878b0d23a1abdde0a8411bea310dbaca585396a6",
 "old_activation_projection_stdout_sha256":"843cc97bab8ba02e382223498d08b7f689c5cd6926955d178bea971383349e20",
 "runtime_R4_manifest_sha256":"52b95328e2f07aaf4416b7f48c9046ffa465337cad7a410ea3a7027512720dc1",
 "baseline01_private_sha256":"163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266",
 "current_status_owner_init_actual_stdout_sha256":"5f029ed98fa932f060a3617764b29485f09a4b09e1052c280ffd925235f488ae",
 "current_status_owner_init_source_sha256":"2d4808c6ae499443302dc4ecc195116a4e4a4ccb2a52d589ca995cda42173f3b"}
def need(v,m):
    if not v:raise RuntimeError(m)

def check():need(time.monotonic()<DEADLINE,'DIAGNOSTIC_DEADLINE')

def read(path,limit):
    check();fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        chunks=[];n=0
        while True:
            check();b=os.read(fd,min(8192,limit+1-n))
            if not b:break
            chunks.append(b);n+=len(b);need(n<=limit,'FIXED_READ_BOUND')
        return b''.join(chunks)
    finally:os.close(fd)

def cg():
    rows={}
    for name in ('memory.current','memory.peak','memory.events','memory.events.local','memory.max','memory.high','memory.swap.current','memory.swap.peak','memory.swap.max','cpu.max','pids.current','pids.max','pids.events'):
        try:rows[name]=read(CG+'/'+name,8192).decode('ascii','strict').strip()
        except OSError as e:rows[name]={'errno':e.errno}
    return rows

def safe_error(error):
    row={"type":type(error).__name__}
    if isinstance(error,OSError):
        row["errno"]=error.errno
    elif isinstance(error,RuntimeError) and re.fullmatch(r"[A-Z0-9_]{1,96}",str(error)):
        row["code"]=str(error)
    else:
        row["code"]="UNEXPECTED_DIAGNOSTIC_FAILURE"
    return row

def bounded_command(argv,seconds,stdout_limit,stderr_limit):
    """Own one session; drain both pipes; kill before reap on every failed path."""
    check()
    need(type(seconds) is int and 1<=seconds<=8,"COMMAND_TIME_POLICY")
    started=time.monotonic()
    end=min(started+seconds,DEADLINE-4)
    need(end>started,"NO_COMMAND_BUDGET")
    record={"argv":argv,"pid":None,"returncode":None,"joined":False,
            "stdout_eof":False,"stderr_eof":False,"termination_attempted":False,
            "errors":[],"complete":False,"timed_out":False,"pipes_created":0,"pipes_closed":0,"selector_closed":False}
    buffers={"stdout":bytearray(),"stderr":bytearray()}
    hashes={"stdout":hashlib.sha256(),"stderr":hashlib.sha256()}
    seen={"stdout":0,"stderr":0}
    limits={"stdout":stdout_limit,"stderr":stderr_limit}
    child=None
    selector=selectors.DefaultSelector()
    pipes=[]
    try:
        child=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,env=ENV,cwd="/",close_fds=True,start_new_session=True)
        record["pid"]=child.pid
        for name,pipe in (("stdout",child.stdout),("stderr",child.stderr)):
            pipes.append(pipe)
            record["pipes_created"]+=1
            os.set_blocking(pipe.fileno(),False)
            selector.register(pipe,selectors.EVENT_READ,name)
        while selector.get_map():
            need(time.monotonic()<end,"COMMAND_TIMEOUT")
            events=selector.select(min(.1,max(0,end-time.monotonic())))
            for key,_ in events:
                name=key.data
                try:
                    part=os.read(key.fileobj.fileno(),min(65536,limits[name]+1-seen[name]))
                except BlockingIOError:
                    continue
                if not part:
                    record[name+"_eof"]=True
                    selector.unregister(key.fileobj)
                    continue
                hashes[name].update(part)
                seen[name]+=len(part)
                keep=max(0,limits[name]-len(buffers[name]))
                buffers[name].extend(part[:keep])
                need(seen[name]<=limits[name],name.upper()+"_BOUND")
        child.wait(timeout=max(.01,min(1,end-time.monotonic())))
        record["joined"]=True
        record["returncode"]=child.returncode
    except BaseException as error:
        record["timed_out"]=isinstance(error,subprocess.TimeoutExpired) or (isinstance(error,RuntimeError) and str(error)=="COMMAND_TIMEOUT")
        record["errors"].append(safe_error(error))
    finally:
        # No poll() before this point: the child PID cannot have been reaped and
        # reused before a required group kill. journalctl has no pager or shell.
        if child is not None and child.returncode is None:
            record["termination_attempted"]=True
            try:
                os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:
                pass
            except BaseException as error:
                record["errors"].append({"phase":"kill_owned_session",**safe_error(error)})
            try:
                child.wait(timeout=2)
                record["joined"]=True
                record["returncode"]=child.returncode
            except BaseException as error:
                record["errors"].append({"phase":"join_owned_child",**safe_error(error)})
        for pipe in pipes:
            try:
                pipe.close()
                record["pipes_closed"]+=1
            except BaseException as error:
                record["errors"].append({"phase":"close_owned_pipe",**safe_error(error)})
        try:
            selector.close()
            record["selector_closed"]=True
        except BaseException as error:
            record["errors"].append({"phase":"close_selector",**safe_error(error)})
        for name in ("stdout","stderr"):
            record[name+"_bytes_seen"]=seen[name]
            record[name+"_bytes_retained"]=len(buffers[name])
            record[name+"_sha256_seen"]=hashes[name].hexdigest()
        record["elapsed_ms"]=round((time.monotonic()-started)*1000,3)
        record["complete"]=bool(record["joined"] and record["returncode"]==0 and
                record["stdout_eof"] and record["stderr_eof"] and not record["errors"] and seen["stderr"]==0)
    return bytes(buffers["stdout"]),bytes(buffers["stderr"]),record

def service():
    argv=['/usr/bin/systemctl','show','droidloomd.service','--no-pager']+['--property='+p for p in PROPERTIES]
    out,err,record=bounded_command(argv,3,16384,8192)
    result={"command":record,"properties":None}
    if record["complete"]:
        lines=out.decode("ascii","strict").splitlines()
        need(all("=" in line for line in lines),"SERVICE_ROW_SCHEMA")
        pairs=[line.split("=",1) for line in lines]
        need(len(pairs)==len(PROPERTIES) and len({p[0] for p in pairs})==len(PROPERTIES),"SERVICE_ROW_DUPLICATE")
        rows=dict(pairs)
        need(set(rows)==set(PROPERTIES),"FIXED_SERVICE_FIELDS")
        result["properties"]=rows
    return result

def verify_service(value):
    need(value["command"]["complete"] and value["properties"] is not None,"FIXED_SERVICE_QUERY_FAILED")
    rows=value["properties"]
    need(rows["MainPID"]=="3588022" and rows["ControlGroup"]=="/system.slice/droidloomd.service" and
         rows["InvocationID"]==INVOCATION and rows["ActiveState"]=="active" and
         rows["SubState"]=="running" and rows["NRestarts"]=="0","MAIN_SERVICE_CHANGED")

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

def validate_packet(packet):
    need(type(packet) is dict and set(packet)=={"schema","files","manifest_sha256"} and
         packet["schema"]=="pocket4-current-baseline-source-packet-v2" and
         type(packet["files"]) is dict and set(packet["files"])==FILES|{"SOURCE_PINS.json"},
         "EXACT_BASELINE_PACKET_SCHEMA")
    encoded={}
    for name,text in packet["files"].items():
        need(type(text) is str and name in FILES|{"SOURCE_PINS.json"},"EXACT_UTF8_SOURCE_MEMBER")
        raw=text.encode();need(0<len(raw)<=65536,"SOURCE_MEMBER_BOUND");encoded[name]=raw
    manifest_raw=encoded["SOURCE_PINS.json"]
    need(hashlib.sha256(manifest_raw).hexdigest()==packet["manifest_sha256"],"EXTERNAL_SOURCE_MANIFEST_PIN")
    manifest=json.loads(manifest_raw)
    need(manifest.get("schema")=="pocket4-current-baseline-source-v2" and
         set(manifest.get("files",{}))==FILES,"EXACT_BASELINE_SOURCE_CLOSURE")
    for name in FILES:
        need(manifest["files"][name]=={"bytes":len(encoded[name]),"sha256":hashlib.sha256(encoded[name]).hexdigest()},
             "BASELINE_SOURCE_PIN_CHANGED")
    for name,(length,pin) in FROZEN_REFS.items():
        need(len(encoded[name])==length and hashlib.sha256(encoded[name]).hexdigest()==pin,
             "FROZEN_REFERENCE_SOURCE_CHANGED")
    return encoded,manifest

def persistent_processes(pool,p):
    fds={};proc={}
    for role,row in p.EXPECTED.items():
        fds[role]=pool.own(os.pidfd_open(row["pid"],0),"fixed_role_pidfd")
        proc[role]=pool.own(os.open("/proc/"+str(row["pid"]),os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW),
                           "fixed_role_procdir")
    verify_pidfds(fds)
    return fds,proc

def verify_pidfds(fds):
    need(len(fds)==7 and len(set(fds.values()))==7,"SEVEN_DISTINCT_PIDFDS_REQUIRED")
    for fd in fds.values():
        poll=select.poll();poll.register(fd,select.POLLIN|select.POLLHUP|select.POLLERR)
        need(not poll.poll(0),"FIXED_PROCESS_PIDFD_DEAD")

def fixed_roots(pool,p,procs):
    roots={};fds={}
    for role,proc in procs.items():
        fd=pool.own(os.open("root",os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC,dir_fd=proc),"fixed_process_root")
        fds[role]=fd;st=os.fstat(fd)
        roots[role]={"device":st.st_dev,"inode":st.st_ino}
        need(stat.S_ISDIR(st.st_mode) and roots[role]==p.EXPECTED[role]["root_identity"],"FIXED_ROOT_IDENTITY_CHANGED")
    return roots,fds

def verify_roots(pool,p,procs,rootfds):
    for role,proc in procs.items():
        fd=pool.own(os.open("root",os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC,dir_fd=proc),"verify_process_root")
        try:
            a,b=os.fstat(fd),os.fstat(rootfds[role])
            need((a.st_dev,a.st_ino)==(b.st_dev,b.st_ino)==
                 (p.EXPECTED[role]["root_identity"]["device"],p.EXPECTED[role]["root_identity"]["inode"]),
                 "PROCESS_ROOT_CHANGED")
        finally:pool.close(fd)

def old_identities_remain_absent(p):
    rows={}
    for role,(pid,birth) in p.OLD_ROLES.items():
        try:os.stat("/proc/"+str(pid)+"/stat",follow_symlinks=False)
        except FileNotFoundError:rows[role]={"host_pid":pid,"old_start_ticks":birth,"absent":True}
        else:raise RuntimeError("OLD_HOST_PID_REAPPEARED_REQUIRE_NEW_REVIEW")
    return rows

def sampled_epoch(pool,p,epoch,ancestry,activation,procs,rootfds,pidfds,roots,intermediary):
    check();verify_pidfds(pidfds);verify_roots(pool,p,procs,rootfds)
    for role,proc in procs.items():
        need(all(os.readlink("ns/"+k,dir_fd=proc)==p.EXPECTED[role]["namespaces"][k] for k in ("pid","mnt")),
             "FIXED_PROCESS_NAMESPACE_SET_CHANGED")
    lineage=ancestry.sample(pool,p,epoch,procs,intermediary,check)
    current=epoch.capture_processes({role:row["pid"] for role,row in p.EXPECTED.items()})
    p.validate_snapshot(current,activation,roots)
    after_lineage=ancestry.sample(pool,p,epoch,procs,intermediary,check)
    need(lineage==after_lineage,"OWNER_LINEAGE_CHANGED_AROUND_SEVEN_ROLE_CAPTURE")
    verify_pidfds(pidfds);verify_roots(pool,p,procs,rootfds)
    old_identities_remain_absent(p)
    return current,lineage

def hash_fd(fd,limit,seconds=15):
    end=min(DEADLINE-6,time.monotonic()+seconds);before=metadata(fd)
    need(stat.S_ISREG(before["st_mode"]) and before["st_nlink"]==1 and
         0<before["st_size"]<=limit,"EXECUTABLE_OR_ARTIFACT_BOUND")
    os.lseek(fd,0,os.SEEK_SET);digest=hashlib.sha256();count=0
    while True:
        need(time.monotonic()<end,"ARTIFACT_HASH_DEADLINE")
        block=os.read(fd,min(131072,before["st_size"]+1-count))
        if not block:break
        count+=len(block);need(count<=before["st_size"],"ARTIFACT_GREW");digest.update(block)
    need(count==before["st_size"] and metadata(fd)==before,"ARTIFACT_CHANGED_DURING_HASH")
    return {"bytes":count,"sha256":digest.hexdigest(),"file":before}

def process_executables(pool,procs):
    artifacts={};fds={}
    for role,proc in procs.items():
        fd=pool.own(os.open("exe",os.O_RDONLY|os.O_CLOEXEC,dir_fd=proc),"fixed_process_executable")
        fds[role]=fd
        artifacts[role]=hash_fd(fd,128*1024*1024)
    return artifacts,fds

def verify_executables(pool,procs,fds,artifacts):
    for role,proc in procs.items():
        fd=pool.own(os.open("exe",os.O_RDONLY|os.O_CLOEXEC,dir_fd=proc),"verify_process_executable")
        try:
            need(metadata(fd)==metadata(fds[role])==artifacts[role]["file"],
                 "PROCESS_EXECUTABLE_BACKING_CHANGED")
        finally:pool.close(fd)

def guest_regular(pool,held,rootfd,path,limit):
    fd=pool.own(held.open_in_root(rootfd,path,os.O_RDONLY|os.O_NOFOLLOW),"fixed_guest_file")
    try:
        first=metadata(fd)
        need(stat.S_ISREG(first["st_mode"]) and first["st_nlink"]==1 and
             0<=first["st_size"]<=limit,"GUEST_FIXED_REGULAR_BOUND")
        raw=held.read_fd(fd,limit,min(DEADLINE-6,time.monotonic()+5))
        need(len(raw)==first["st_size"] and metadata(fd)==first,"GUEST_FILE_CHANGED")
        return raw,first
    finally:pool.close(fd)

def fixed_packages(pool,p,held,rootfd,activation):
    raw,meta=guest_regular(pool,held,rootfd,"/data/system/packages.list",1024*1024)
    found={}
    for line in raw.decode("utf-8","strict").splitlines():
        fields=line.split()
        if not fields or fields[0] not in p.TARGET_UIDS:continue
        need(len(fields)>=2 and fields[1].isdecimal() and fields[0] not in found,
             "FIXED_PACKAGE_UID_DUPLICATE_OR_INVALID")
        found[fields[0]]=int(fields[1])
    need(found==p.TARGET_UIDS,"CURRENT_FIXED_PACKAGE_UID_CHANGED")
    private={"source_sha256":p.sha(raw),"source_bytes":len(raw),"source_metadata":meta,
             "selected":found};del raw
    dirs={}
    for package in p.TARGETS:
        for kind in ("user","user_de"):
            relative=kind+"/0/"+package;path="/data/"+relative
            fd=pool.own(held.open_in_root(rootfd,path,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW),"fixed_package_data_directory")
            try:
                st=os.fstat(fd);now={"device":st.st_dev,"inode":st.st_ino,"uid":st.st_uid,"gid":st.st_gid}
                expected=activation["app_directories"][relative]
                need(stat.S_ISDIR(st.st_mode) and all(now[k]==expected[k] for k in now),
                     "HISTORICAL_APP_DATA_DIRECTORY_CHANGED")
                dirs[relative]=now
            finally:pool.close(fd)
    return private,dirs

def paired_classpaths(pool,p,held,procs,rootfds):
    deadline=min(DEADLINE-12,time.monotonic()+held.CLASSPATH_SECONDS)
    raw=held.read_at(procs["zygote64"],"environ",held.ENV_LIMIT,deadline)
    values=held.selected_classpaths(raw);del raw
    unique=list(dict.fromkeys(path for key in held.REQUIRED_CLASSPATHS for path in values[key].split(":")))
    need(len(unique)<=held.PATH_COUNT_LIMIT,"COMBINED_CLASSPATH_COUNT_EXCEEDED")
    files=[];total=0
    for path in unique:
        held.deadline_check(deadline);a=b=None
        try:
            a=pool.own(held.open_in_root(rootfds["android_init"],path,os.O_RDONLY),"classpath_init_file")
            b=pool.own(held.open_in_root(rootfds["zygote64"],path,os.O_RDONLY),"classpath_zygote_file")
            left,right=metadata(a),metadata(b)
            need(stat.S_ISREG(left["st_mode"]) and stat.S_ISREG(right["st_mode"]) and
                 0<left["st_size"]<=held.FILE_LIMIT and 0<right["st_size"]<=held.FILE_LIMIT,
                 "CLASSPATH_FILE_BOUND")
            need(tuple(left[k] for k in ("st_dev","st_ino","st_size"))==
                 tuple(right[k] for k in ("st_dev","st_ino","st_size")),"CLASSPATH_TWO_ROOT_BACKING_DIFFERS")
            total+=left["st_size"];need(total<=held.TOTAL_FILE_LIMIT,"CLASSPATH_TOTAL_BYTES_EXCEEDED")
            digest=hashlib.sha256();count=0
            while True:
                held.deadline_check(deadline);block=os.read(a,min(131072,left["st_size"]+1-count))
                if not block:break
                count+=len(block);need(count<=left["st_size"],"CLASSPATH_FILE_GREW");digest.update(block)
            need(count==left["st_size"] and metadata(a)==left and metadata(b)==right,"CLASSPATH_BACKING_CHANGED")
            files.append({"path":path,"sha256":digest.hexdigest(),"bytes":count,
                          "init_view":left,"zygote_view":right,"same_backing_verified":True})
        finally:
            if b is not None:pool.close(b)
            if a is not None:pool.close(a)
    again=held.selected_classpaths(held.read_at(procs["zygote64"],"environ",held.ENV_LIMIT,deadline))
    need(again==values,"SELECTED_CLASSPATHS_CHANGED")
    return {"values":values,"files":files,"total_bytes":total,"paired_complete":True,
            "limits":{"deadline_seconds":45,"path_count":256,"per_file_bytes":134217728,"total_bytes":805306368},
            "different_mount_namespaces_permitted":True,"different_backing_files_permitted":False}

def counters_safe(value):
    for name in ("memory.events","memory.events.local"):
        fields=dict(line.split() for line in value[name].splitlines())
        need(all(fields.get(k)=="0" for k in ("oom","oom_kill","oom_group_kill")),"MAIN_OOM_COUNTER_NOT_ZERO")
    fields=dict(line.split() for line in value["pids.events"].splitlines())
    need(fields.get("max")=="0","MAIN_PIDS_MAX_EVENT_OBSERVED")

def validate_service_pair(first,last):
    verify_service(first);verify_service(last)
    keys=("MainPID","ControlGroup","InvocationID","ActiveState","SubState","Result","NRestarts",
          "ExecMainStartTimestampMonotonic","StateChangeTimestampMonotonic")
    need(all(first["properties"][k]==last["properties"][k] for k in keys),"MAIN_SERVICE_IDENTITY_CHANGED")

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

def publish(pool,encoded,manifest_sha,baseline,qualification,guard_template,p):
    need(not os.path.lexists(ROOT),"FRESH_CURRENT_BASELINE_ROOT_REQUIRED")
    parent=open_host(pool,str(ROOT.parent),os.O_PATH|os.O_DIRECTORY)
    try:
        os.mkdir(ROOT.name,mode=0o700,dir_fd=parent)
        root=open_host(pool,str(ROOT),os.O_PATH|os.O_DIRECTORY)
        try:os.mkdir("source",mode=0o700,dir_fd=root)
        finally:pool.close(root)
    finally:pool.close(parent)
    need(ROOT.lstat().st_uid==0 and SOURCE.lstat().st_uid==0 and
         stat.S_IMODE(ROOT.lstat().st_mode)==0o700 and stat.S_IMODE(SOURCE.lstat().st_mode)==0o700,
         "PRIVATE_OWNED_ROOT_REQUIRED")
    for name,raw in sorted(encoded.items()):write_new(pool,SOURCE/name,raw)
    bpin=write_new(pool,ROOT/"baseline.private.json",p.canonical(baseline)+b"\n")
    qualification["baseline"]=bpin
    qpin=write_new(pool,ROOT/"qualification.json",p.canonical(qualification)+b"\n")
    replacements={"@@BASELINE_SHA@@":bpin["sha256"],"@@QUALIFICATION_SHA@@":qpin["sha256"],
                  "@@BASELINE_BYTES@@":str(bpin["bytes"]),"@@QUALIFICATION_BYTES@@":str(qpin["bytes"]),
                  "@@CURRENT_EPOCH@@":baseline["framework_epoch"]["sha256"],
                  "@@MANIFEST_SHA@@":manifest_sha}
    guard=guard_template
    for old,new in replacements.items():
        need(guard.count(old)>=1,"GUARD_TEMPLATE_MARKER_MISSING");guard=guard.replace(old,new)
    need("@@" not in guard,"GUARD_TEMPLATE_MARKER_REMAINS")
    compile(guard,str(ROOT/"current_baseline_guard.py"),"exec")
    gpin=write_new(pool,ROOT/"current_baseline_guard.py",guard.encode())
    d=open_host(pool,str(SOURCE),os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(d)
    finally:pool.close(d)
    d=open_host(pool,str(ROOT),os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(d)
    finally:pool.close(d)
    d=open_host(pool,str(ROOT.parent),os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(d)
    finally:pool.close(d)
    return bpin,qpin,gpin

def main(packet):
    os.umask(0o077)
    need(os.getuid()==os.geteuid()==0,"ROOT_READONLY_BASELINE_REQUIRED")
    encoded,manifest=validate_packet(packet);manifest_sha=packet["manifest_sha256"]
    p=load_module(encoded["baseline_policy.py"],"current_baseline_policy",SOURCE/"baseline_policy.py")
    epoch=load_module(encoded["framework_epoch.py"],"current_baseline_epoch",SOURCE/"framework_epoch.py",FROZEN_REFS["framework_epoch.py"][1])
    held=load_module(encoded["held_runtime_r5.py"],"current_baseline_held",SOURCE/"held_runtime_r5.py",FROZEN_REFS["held_runtime_r5.py"][1])
    historical_source=load_module(encoded["historical_source_contract.py"],"historical_source_contract",SOURCE/"historical_source_contract.py",FROZEN_REFS["historical_source_contract.py"][1])
    ancestry=load_module(encoded["cell_ancestry.py"],"current_cell_ancestry",SOURCE/"cell_ancestry.py")
    controls=load_module(encoded["controls.py"],"current_baseline_controls",SOURCE/"controls.py")
    control_result=controls.run(p,encoded)
    pool=ManagedFDs();result={"schema":"pocket4-main-current-baseline-result-v2","ok":False,
      "error":None,"secondary_errors":[],"source_manifest_sha256":manifest_sha,"source_basis":SOURCE_PINS,
      "controls":control_result,"namespace_entry":False,"Android_commands":0,"UI_actions":0,
      "App_launches":0,"helper_installs":0,"deployment_performed":False,"automatic_retry":False,
      "old_epoch_reauthorized":False,"framework_exit_cause_resolved":False,"whole_app_production_ready":False}
    activation=verified=pidfds=procs=rootfds=roots=first=last=before_service=None
    baseline=None;artifacts=exefds=None;engine_fd=None;engine_record=None;samples=[]
    previous=None;intermediary=None;lineage_samples=[];first_lineage=None;previous_exes=None
    started=time.monotonic_ns();phase="initial_historical_lineage"
    try:
        need(not os.path.lexists(ROOT),"FRESH_CURRENT_BASELINE_ROOT_REQUIRED")
        need(read("/proc/sys/kernel/random/boot_id",128).decode().strip()==BOOT_ID,"BOOT_CHANGED")
        activation_raw,_=bounded_regular(pool,p.ACTIVATION_PATH,131072,p.ACTIVATION_SHA,p.ACTIVATION_BYTES)
        verified_raw,_=bounded_regular(pool,p.VERIFIED_PATH,131072,p.VERIFIED_SHA)
        activation,verified=p.parse(activation_raw),p.parse(verified_raw);p.historical(activation,verified)
        previous_raw,_=bounded_regular(pool,p.PREVIOUS_BASELINE["path"],131072,
              p.PREVIOUS_BASELINE["sha256"],p.PREVIOUS_BASELINE["bytes"])
        previous=p.parse(previous_raw);p.validate_previous_baseline(previous,activation)
        previous_exes=p.executable_content(previous["current_process_executables"])
        cell_raw,cell_meta=bounded_regular(pool,p.CELL_PATH,131072,p.CELL_SHA)
        source_raw,_=bounded_regular(pool,"/home/alex/work/pocket4-framework-epoch-20261104-r10/framework_epoch.py",
             16384,FROZEN_REFS["framework_epoch.py"][1],FROZEN_REFS["framework_epoch.py"][0])
        need(source_raw==encoded["framework_epoch.py"],"HISTORICAL_EPOCH_SOURCE_DIFFERS")
        phase="fixed_current_processes"
        pidfds,procs=persistent_processes(pool,p);roots,rootfds=fixed_roots(pool,p,procs)
        intermediary=ancestry.hold_intermediary(pool,p)
        first,first_lineage=sampled_epoch(pool,p,epoch,ancestry,activation,procs,rootfds,pidfds,roots,intermediary)
        samples.append(first);lineage_samples.append(first_lineage)
        before_service=service();verify_service(before_service);result["service_before"]=before_service
        before_cgroup=cg();need(all(before_cgroup.get(k)==v for k,v in p.LIMITS.items()),"MAIN_LIMITS_CHANGED")
        counters_safe(before_cgroup);result["cgroup_before"]=before_cgroup
        # The shared native helper's static qualification is re-read, not promoted.
        phase="historical_native_helper_qualification"
        helper_qualification=historical_source.verify_shared_helper()
        need(helper_qualification["whole_process_tree_cleanup_qualified"] is False,"HELPER_QUALIFICATION_SCOPE_CHANGED")
        phase="live_process_executables_and_engine"
        artifacts,exefds=process_executables(pool,procs)
        need(artifacts["presenter"]["sha256"]==p.PRESENTER_SHA,"LIVE_PRESENTER_ARTIFACT_DIFFERS")
        p.validate_executable_content(artifacts,previous_exes)
        need(all(artifacts[k]["file"]==previous["current_process_executables"][k]["file"]
             for k in ("daemon","launcher","presenter")),"HOST_EXECUTABLE_BACKING_LINEAGE_CHANGED")
        engine_fd=pool.own(held.open_in_root(rootfds["android_init"],"/system/lib64/libberberis_arm64.so",os.O_RDONLY),
                           "current_engine_artifact")
        engine_record=hash_fd(engine_fd,256*1024*1024,20)
        need(engine_record["sha256"]==p.ENGINE_SHA,"CURRENT_DEPLOYED_ENGINE_DIFFERS")
        phase="fixed_package_uid_and_data"
        packages,dirs=fixed_packages(pool,p,held,rootfds["android_init"],activation)
        phase="complete_paired_classpaths"
        classpaths=paired_classpaths(pool,p,held,procs,rootfds)
        phase="bounded_full_identity_continuity"
        second,second_lineage=sampled_epoch(pool,p,epoch,ancestry,activation,procs,rootfds,pidfds,roots,intermediary)
        samples.append(second);lineage_samples.append(second_lineage)
        threshold=first["collected_monotonic_ns"]+10_000_000_000
        while time.monotonic_ns()<=max(threshold,second["collected_monotonic_ns"]):
            check();verify_pidfds(pidfds)
            time.sleep(min(.2,max(.001,(threshold-time.monotonic_ns())/1e9)))
        last,last_lineage=sampled_epoch(pool,p,epoch,ancestry,activation,procs,rootfds,pidfds,roots,intermediary)
        samples.append(last);lineage_samples.append(last_lineage)
        p.validate_samples(samples,activation,roots)
        p.validate_lineage_samples(lineage_samples)
        verify_executables(pool,procs,exefds,artifacts)
        need(metadata(engine_fd)==engine_record["file"],"CURRENT_ENGINE_BACKING_CHANGED")
        test=pool.own(held.open_in_root(rootfds["android_init"],"/system/lib64/libberberis_arm64.so",os.O_RDONLY),
                      "verify_current_engine")
        try:need(metadata(test)==engine_record["file"],"CURRENT_ENGINE_PATH_CHANGED")
        finally:pool.close(test)
        packages_after,dirs_after=fixed_packages(pool,p,held,rootfds["android_init"],activation)
        need(packages_after==packages and dirs_after==dirs,"FIXED_PACKAGE_OR_DATA_CHANGED")
        phase="current_baseline_document"
        newepoch=p.android_epoch(last)
        baseline={"schema":p.SCHEMA,"kind":"current-cell-generation","deployment_performed":False,
          "old_epoch_sha256":p.OLD_EPOCH,"framework_epoch":newepoch,
          "previous_current_baseline":dict(p.PREVIOUS_BASELINE),"discovery_observation":dict(p.DISCOVERY),
          "owner_lineage":last_lineage,"previous_executable_content":previous_exes,
          "surviving_host_executable_backing_equal":True,"previous_cell_runtime_authority_transferred":False,
          "historical_deployment":{"activation_path":p.ACTIVATION_PATH,"activation_bytes":p.ACTIVATION_BYTES,
             "activation_sha256":p.ACTIVATION_SHA,"verification_path":p.VERIFIED_PATH,"verification_sha256":p.VERIFIED_SHA},
          "daemon_process":last["binding"]["processes"]["daemon"],
          "launcher_process":last["binding"]["processes"]["launcher"],
          "presenter_process":last["binding"]["processes"]["presenter"],
          "status":{"host_pid":p.EXPECTED["launcher"]["pid"]},
          "all_seven_processes":last,"process_roots":roots,"sample_monotonic_ns":[x["collected_monotonic_ns"] for x in samples],
          "sample_span_ns":samples[-1]["collected_monotonic_ns"]-samples[0]["collected_monotonic_ns"],
          "three_double_samples_equal":True,"bounded_observation_is_not_future_stability_proof":True,
          "limits":dict(p.LIMITS),"cell_config":{"path":p.CELL_PATH,"sha256":p.CELL_SHA,"bytes":len(cell_raw),"file":cell_meta},
          "engine_sha256":p.ENGINE_SHA,"presenter_sha256":p.PRESENTER_SHA,"engine_artifact":engine_record,
          "current_process_executables":artifacts,"current_package_source":packages,"packages":packages["selected"],
          "app_directories":dirs,"classpath":classpaths,"held_helper_static_qualification":helper_qualification,
          "current_service":{k:before_service["properties"][k] for k in ("MainPID","ControlGroup","InvocationID","ActiveState","SubState","NRestarts","ExecMainStartTimestampMonotonic")},
          "namespace_entry":False,"Android_commands":0,"UI_actions":0,"App_launches":0,"helper_installs":0,
          "framework_exit_cause_resolved":False,"whole_app_production_ready":False,
          "production_gate":{"unresolved_framework_exit_cause":True,"repeated_crash_freedom_proved":False,"business_acceptance_proved":False}}
        p.validate_new_baseline(baseline)
    except BaseException as e:result["error"]={"phase":phase,**safe_error(e)}
    finally:
        if pidfds is not None and procs is not None and rootfds is not None and activation is not None and intermediary is not None:
            try:
                final,final_lineage=sampled_epoch(pool,p,epoch,ancestry,activation,procs,rootfds,pidfds,roots,intermediary)
                need(first is not None and final["binding"]==first["binding"],"FINAL_FULL_IDENTITY_CHANGED")
                need(first_lineage is not None and final_lineage==first_lineage,
                     "FINAL_OWNER_CHAIN_OR_USER_NAMESPACE_CHANGED")
                result["final_owner_lineage_and_user_namespaces_equal"]=True
                result["final_fixed_identity_equal"]=True
                result["additional_final_double_sample_monotonic_ns"]=final["collected_monotonic_ns"]
                if artifacts is not None:verify_executables(pool,procs,exefds,artifacts)
            except BaseException as e:result["secondary_errors"].append({"phase":"final_fixed_identity",**safe_error(e)})
        try:
            result["service_after"]=service();verify_service(result["service_after"])
            if before_service is not None:validate_service_pair(before_service,result["service_after"])
        except BaseException as e:result["secondary_errors"].append({"phase":"final_service",**safe_error(e)})
        try:
            result["cgroup_after"]=cg()
            need(all(result["cgroup_after"].get(k)==v for k,v in p.LIMITS.items()),"FINAL_MAIN_LIMITS_CHANGED")
            counters_safe(result["cgroup_after"])
        except BaseException as e:result["secondary_errors"].append({"phase":"final_cgroup",**safe_error(e)})
        try:
            bounded_regular(pool,p.ACTIVATION_PATH,131072,p.ACTIVATION_SHA,p.ACTIVATION_BYTES)
            bounded_regular(pool,p.VERIFIED_PATH,131072,p.VERIFIED_SHA)
            bounded_regular(pool,p.CELL_PATH,131072,p.CELL_SHA)
            bounded_regular(pool,p.PREVIOUS_BASELINE["path"],131072,
                 p.PREVIOUS_BASELINE["sha256"],p.PREVIOUS_BASELINE["bytes"])
            need(read("/proc/sys/kernel/random/boot_id",128).decode().strip()==BOOT_ID,"FINAL_BOOT_CHANGED")
            result["historical_inputs_and_boot_unchanged"]=True
        except BaseException as e:result["secondary_errors"].append({"phase":"final_historical_inputs",**safe_error(e)})
        pool.close_all()
        result["observation_fds"]=pool.summary()
        try:pool.require_clean()
        except BaseException as e:result["secondary_errors"].append({"phase":"all_observation_fd_retirement",**safe_error(e)})
    result["elapsed_ns"]=time.monotonic_ns()-started
    if baseline is not None and result["error"] is None and not result["secondary_errors"]:
        output=ManagedFDs()
        try:
            qualification={"schema":p.QUAL_SCHEMA,"identity_qualified":True,"historical_deployment_revalidated":True,
              "new_deployment_performed":False,"old_epoch_reauthorized":False,"epoch_sha256":baseline["framework_epoch"]["sha256"],
              "source_manifest_sha256":manifest_sha,"source_pins":SOURCE_PINS,
              "three_double_samples_equal":True,"final_seven_role_identity_equal":True,
              "previous_current_baseline":dict(p.PREVIOUS_BASELINE),"discovery_observation":dict(p.DISCOVERY),
              "three_owner_chain_and_user_namespace_samples_equal":True,
              "final_owner_chain_and_user_namespaces_equal":True,"seven_executable_content_lineages_equal":True,
              "user_namespaces_freshly_measured":True,"old_helpers_and_tasks_reauthorized":False,
              "protected_processes":p.protected_process_projection(baseline["all_seven_processes"],
                     baseline["process_roots"],baseline["owner_lineage"]),
              "protected_process_projection_is_actual_measurement":True,
              "private_full_identity_exported":False,"observation_fds":result["observation_fds"],
              "all_owned_service_children_joined":True,"framework_exit_cause_resolved":False,
              "production_ready":False,"UI_or_install_runtime_admitted":False}
            bpin,qpin,gpin=publish(output,encoded,manifest_sha,baseline,qualification,
                                 encoded["current_baseline_guard.template.py"].decode(),p)
            result.update(baseline=bpin,qualification=qpin,generated_current_guard=gpin,
               new_epoch_sha256=baseline["framework_epoch"]["sha256"],
               double_sample_count=3,explicit_observation_span_ns=baseline["sample_span_ns"],
               fixed_role_pids={k:v["pid"] for k,v in p.EXPECTED.items()},
               selected_package_uids=dict(p.TARGET_UIDS),
               current_owner_chain_host_pids=[p.EXPECTED["daemon"]["pid"],p.EXPECTED["launcher"]["pid"],
                     p.EXPECTED_INTERMEDIARY["pid"],p.EXPECTED["android_init"]["pid"]],
               old_helpers_and_tasks_reauthorized=False,
               protected_processes=qualification["protected_processes"],
               protected_process_projection_is_actual_measurement=True,
               classpath_file_count=len(baseline["classpath"]["files"]),
               classpath_total_bytes=baseline["classpath"]["total_bytes"],identity_qualified=True)
        except BaseException as e:result["error"]={"phase":"private_baseline_publication",**safe_error(e)}
        finally:
            output.close_all();result["publication_fds"]=output.summary()
            try:output.require_clean()
            except BaseException as e:result["secondary_errors"].append({"phase":"publication_fd_retirement",**safe_error(e)})
    result["ok"]=bool(result.get("identity_qualified") is True and result["error"] is None and not result["secondary_errors"])
    raw=json.dumps(result,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    need(len(raw)<=65536,"SAFE_RESULT_BOUND")
    print(raw.decode(),flush=True)
    return 0 if result["ok"] else 1
