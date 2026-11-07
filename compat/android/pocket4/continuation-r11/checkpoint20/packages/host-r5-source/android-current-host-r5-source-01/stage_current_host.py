"""Create-only current host R5 source publication and pure controls; no Android commands."""
import hashlib,json,os,stat,sys,time,types
from pathlib import Path,PurePosixPath
ROOT=Path("/home/alex/work/pocket4-current-host-r5-source-01")
DEADLINE=time.monotonic()+45
EXPECTED_MANIFEST="6d99374e1580083fd0f30b7f9b3c520306680760c97ad0d5400798fda427fb6e"
EXPECTED_GUARD="0ee54ef97c073857609aedb4670395db084ceacc7d28558315647ab2ffbef679"
EXPECTED_CONTROLS="2932410314566eb8c700ea67f94863583d67fcbd93a784c813c3d641281051f4"
EXPECTED_PARENT_MANIFEST="52b95328e2f07aaf4416b7f48c9046ffa465337cad7a410ea3a7027512720dc1"
def need(value,code):
    if not value:raise RuntimeError(code)
def check():need(time.monotonic()<DEADLINE,"CURRENT_HOST_STAGE_DEADLINE")
def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return value.encode("utf-8")
def parse(raw):
    def pairs(rows):
        out={}
        for key,value in rows:
            need(key not in out,"DUPLICATE_PACKET_FIELD")
            out[key]=value
        return out
    def invalid(value):raise RuntimeError("NONFINITE_PACKET_VALUE")
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)
def module(raw,name,filename):
    value=types.ModuleType(name);value.__file__=str(filename)
    exec(compile(raw,str(filename),"exec"),value.__dict__)
    return value
class FDs:
    def __init__(self):self.rows=[];self.acquired=0;self.attempted=0;self.closed=0;self.errors=[]
    def add(self,fd):self.rows.append(fd);self.acquired+=1;return fd
    def close(self):
        rows=self.rows;self.rows=[]
        for fd in reversed(rows):
            self.attempted+=1
            try:os.close(fd);self.closed+=1
            except BaseException as e:self.errors.append(type(e).__name__)
    def summary(self):return {"acquired":self.acquired,"close_attempts":self.attempted,"closed":self.closed,
                              "remaining":len(self.rows),"errors":self.errors}
def write_new(pool,dirfd,name,raw):
    check()
    need("/" not in name and name not in ("",".","..") and len(raw)<=131072,"FIXED_SOURCE_LEAF_BOUND")
    fd=pool.add(os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o400,dir_fd=dirfd))
    before=os.fstat(fd);need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_uid==0,"OWNED_SOURCE_FILE_REQUIRED")
    offset=0
    while offset<len(raw):
        check();count=os.write(fd,raw[offset:]);need(count>0,"SOURCE_WRITE_STALLED");offset+=count
    os.fchmod(fd,0o444);os.fsync(fd)
    after=os.fstat(fd);need(after.st_size==len(raw),"SOURCE_WRITE_LENGTH_CHANGED")
    return {"bytes":len(raw),"sha256":sha(raw)}
def validate(packet):
    need(type(packet) is dict and set(packet)=={"schema","files","manifest_raw","parents","parent_manifest_raw","controls_source"},
         "EXACT_CURRENT_HOST_STAGE_PACKET")
    need(packet["schema"]=="pocket4-current-host-source-stage-packet-v1","CURRENT_HOST_STAGE_PACKET_SCHEMA")
    files=packet["files"];parents=packet["parents"]
    need(type(files) is dict and len(files)==14 and type(parents) is dict and len(parents)==12,"EXACT_HOST_SOURCE_MAP_COUNTS")
    manifest_raw=encoded(packet["manifest_raw"]);m=parse(manifest_raw)
    need(sha(manifest_raw)==EXPECTED_MANIFEST and m["schema"]==2 and
         m["artifact"]=="pocket4-bilibili-current-recorder-held-r5" and set(m["files"])==set(files),
         "CURRENT_HOST_SOURCE_MANIFEST_CHANGED")
    need(sha(encoded(packet["controls_source"]))==EXPECTED_CONTROLS and
         sha(encoded(packet["parent_manifest_raw"]))==EXPECTED_PARENT_MANIFEST,"FIXED_CONTROL_OR_PARENT_CHANGED")
    old=parse(packet["parent_manifest_raw"])
    for source,rows in ((files,m["files"]),(parents,old["files"])):
        for name,text in source.items():
            check()
            rel=PurePosixPath(name)
            need(str(rel)==name and not rel.is_absolute() and ".." not in rel.parts and
                 len(rel.parts)<=2 and (len(rel.parts)==1 or rel.parts[0]=="references"),
                 "FIXED_HOST_SOURCE_PATH")
            raw=encoded(text)
            need(len(raw)==rows[name]["bytes"] and sha(raw)==rows[name]["sha256"] and 0<len(raw)<=131072,
                 "HOST_SOURCE_PIN_CHANGED")
    need(sha(encoded(files["current_baseline_guard.py"]))==EXPECTED_GUARD,"ACTUAL_GUARD_PIN_CHANGED")
    need(sum(len(encoded(x)) for x in files.values())<=393216,"CURRENT_HOST_SOURCE_TOTAL_BOUND")
    return files,manifest_raw,m
def main(packet):
    result={"schema":"pocket4-current-host-source-stage-result-v1","ok":False,"error":None,"secondary_errors":[],
            "source_root":str(ROOT),"source_manifest_sha256":EXPECTED_MANIFEST,"source_published":False,
            "namespace_entry":False,"Android_commands":0,"UI_actions":0,"helper_installs":0,"App_launches":0,
            "automatic_retry":False,"framework_exit_cause_resolved":False,"whole_app_production_ready":False,
            "current_runtime_admitted":False,"all45_app_production_ready_count":0}
    pool=FDs();guard=None
    try:
        need(os.getuid()==os.geteuid()==0,"ROOT_SOURCE_OWNER_REQUIRED")
        os.umask(0o077)
        files,manifest_raw,m=validate(packet)
        controls=module(packet["controls_source"],"current_host_pure_controls","<current-host-controls>")
        report=controls.run_controls(files,packet["parents"],packet["manifest_raw"])
        need(report["all_passed"] is True and report["count"]==26 and len(report["cases"])==26 and
             all(x["passed"] is True for x in report["cases"]),"CURRENT_HOST_CONTROLS_REQUIRED")
        result["controls"]=report
        guard=module(files["current_baseline_guard.py"],"current_host_stage_guard",ROOT/"current_baseline_guard.py")
        result["Main_before"]=guard.current_guard()
        check()
        need(ROOT.parent==Path("/home/alex/work") and ROOT.parent.resolve()==ROOT.parent and
             not os.path.lexists(ROOT),"FRESH_OWN_SOURCE_ROOT_REQUIRED")
        os.mkdir(ROOT,0o700)
        rootfd=pool.add(os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW))
        meta=os.fstat(rootfd)
        need(meta.st_uid==0 and stat.S_ISDIR(meta.st_mode) and meta.st_mode&0o077==0,"PRIVATE_SOURCE_DIRECTORY_REQUIRED")
        os.mkdir("references",0o700,dir_fd=rootfd)
        reffd=pool.add(os.open("references",os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=rootfd))
        observed={}
        for name,text in sorted(files.items()):
            parts=name.split("/")
            observed[name]=write_new(pool,reffd if len(parts)==2 else rootfd,parts[-1],encoded(text))
        need(observed==m["files"],"STAGED_SOURCE_PIN_SET_CHANGED")
        write_new(pool,rootfd,"source-manifest.json",manifest_raw)
        os.fsync(reffd);os.fsync(rootfd)
        parentfd=pool.add(os.open(ROOT.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW))
        os.fsync(parentfd)
        contract_module=module(files["source_contract.py"],"current_host_stage_contract",ROOT/"source_contract.py")
        contract=contract_module.SourceContract(ROOT/"source-manifest.json",EXPECTED_MANIFEST)
        contract.verify()
        current_root=os.stat(ROOT,follow_symlinks=False)
        need((current_root.st_dev,current_root.st_ino)==(meta.st_dev,meta.st_ino),
             "STAGED_SOURCE_DIRECTORY_REPLACED")
        result["source_files"]=observed
        result["source_published"]=True
        result["Main_after"]=guard.current_guard()
        check();result["ok"]=True
    except BaseException as error:
        result["error"]={"type":type(error).__name__,"code":str(error)[:256]}
    finally:
        if guard is not None:
            try:result["Main_final"]=guard.current_guard()
            except BaseException as error:
                result["secondary_errors"].append({"stage":"final-Main-guard","type":type(error).__name__,"code":str(error)[:256]})
        pool.close()
        result["owned_fds"]=pool.summary()
        if pool.errors:result["secondary_errors"].append({"stage":"owned-source-FD-close","errors":pool.errors})
        result["ok"]=bool(result["ok"] and result["error"] is None and not result["secondary_errors"] and not pool.rows)
        result["source_stage_qualified"]=bool(result["ok"] and result["source_published"])
        result["elapsed_seconds"]=round(45-(DEADLINE-time.monotonic()),6)
        print(json.dumps(result,sort_keys=True,separators=(",",":")),flush=True)
    return 0 if result["ok"] else 1
if __name__=="__main__":raise SystemExit(main(PACKET))
