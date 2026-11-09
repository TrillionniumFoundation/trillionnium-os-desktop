#!/usr/bin/env python3
"""Real Linux alias controls in a private mount/PID namespace; no live mounts changed.

Usage: NAMESPACE_FIXTURE_DIR=<owned-stage> python3 -I -B this.py observer.py
The caller must run as root. The observer source is AST-loaded without executing
its historical entry point. This test creates no artifact outside its owned
temporary directory; all mounts exist only in a private child namespace.
"""
import ast,ctypes,datetime,hashlib,json,mmap,os,select,signal,stat,subprocess,sys,tempfile,time
from pathlib import Path
def need(ok,why):
    if not ok:raise RuntimeError(why)
need(os.geteuid()==0,"root_required_for_private_namespace_fixture")
need(len(sys.argv)==2,"one_observer_module_path_required")
module=Path(sys.argv[1]).resolve(strict=True)
raw_source=module.read_bytes()
node=[n for n in ast.parse(raw_source).body if isinstance(n,ast.FunctionDef) and n.name=="live_references"]
need(len(node)==1,"exact_live_references_function_required")
scope={"os":os,"Path":Path,"now":lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()}
exec(compile(ast.Module(body=node,type_ignores=[]),str(module),"exec"),scope)
observe=scope["live_references"]
base_input=os.environ["NAMESPACE_FIXTURE_DIR"]
need(base_input.startswith("/") and os.path.normpath(base_input)==base_input
     and "//" not in base_input and "\x00" not in base_input,"canonical_fixture_directory_required")
current=Path("/")
for part in Path(base_input).parts[1:]:
    current=current/part
    info=current.lstat()
    need(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),"fixture_directory_symlink_or_type")
base=Path(base_input).resolve(strict=True)
need(str(base)==base_input,"fixture_directory_resolution_changed")
libc=ctypes.CDLL(None,use_errno=True)
libc.mount.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_char_p,ctypes.c_ulong,ctypes.c_void_p]
libc.mount.restype=ctypes.c_int
libc.umount2.argtypes=[ctypes.c_char_p,ctypes.c_int]
libc.umount2.restype=ctypes.c_int
def mount(source,target,kind=None,flags=0):
    result=libc.mount(os.fsencode(source) if source else None,os.fsencode(target),os.fsencode(kind) if kind else None,flags,None)
    if result:raise OSError(ctypes.get_errno(),"private_fixture_mount")
def unmount(target):
    if libc.umount2(os.fsencode(target),0):raise OSError(ctypes.get_errno(),"private_fixture_umount")
def death_parent(expected):
    need(libc.prctl(1,signal.SIGKILL,0,0,0)==0,"fixture_pdeath")
    need(os.getppid()==expected,"fixture_parent_changed")
def wait_exact(pid,timeout=5):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        found,status=os.waitpid(pid,os.WNOHANG)
        if found:return os.waitstatus_to_exitcode(status)
        time.sleep(.005)
    os.kill(pid,signal.SIGKILL)
    found,status=os.waitpid(pid,0)
    raise RuntimeError("owned_fixture_child_timeout")
def inner(root):
    need(os.getpid()==1,"private_pid1_required")
    mount("proc","/proc","proc",0)
    os.chdir("/")
    parent=root/"parent";target=parent/"target";alias=root/"alias";outside=root/"outside";mirror=root/"mirror"
    for p in (target,target/"subtree",target/"mounted",alias,outside,mirror):p.mkdir(parents=True,exist_ok=True)
    (target/"payload").write_bytes(b"owned alias fixture\n")
    mount(parent,alias,None,4096)
    alias_target=alias/"target";rows=[];child_rows=[]
    def run(name,expect):
        result=observe([str(target)])
        fields={key:result.get(key) for key in ("visibility","namespace_fd_count","opaque_mount_namespace_count","covered_opaque_mount_namespace_count","uncovered_mount_namespace_count","visible_alias_path_count","verified_shadowed_alias_path_count")}
        fields.update({"case":name,"process_hits":len(result["process_or_owner_hits"]),
                       "mount_hits":len(result["mount_hits"]),
                       "coverage_errors":result["coverage_errors"][:16],
                       "coverage_error_count":len(result["coverage_errors"]),
                       "uncovered_mount_namespaces":result.get("uncovered_mount_namespaces",[])[:16],
                       "namespace_child_lifecycle":result.get("namespace_child_lifecycle"),
                       "namespace_child_terminals":result.get("namespace_child_terminals")})
        detail=":"+json.dumps(fields,sort_keys=True)
        if expect=="clear":
            need(result["visibility"]=="OBSERVED" and not result["process_or_owner_hits"] and not result["mount_hits"] and not result["coverage_errors"],name+"_not_observed_clear"+detail)
        elif expect=="reference":
            need(result["visibility"]=="OBSERVED" and result["process_or_owner_hits"] and not result["coverage_errors"],name+"_actual_reference_not_vetoed"+detail)
        elif expect=="mount":
            need(result["visibility"]=="OBSERVED" and result["mount_hits"] and not result["coverage_errors"],name+"_actual_mount_not_vetoed"+detail)
        elif expect=="unknown":
            need(result["visibility"]=="UNKNOWN" and result["coverage_errors"],name+"_wrong_inode_not_rejected"+detail)
        else:raise RuntimeError("fixture_expectation")
        rows.append(fields)
        return result
    def path_mount_identity(path):
        handle=os.open(path,os.O_PATH|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            info=os.fstat(handle)
            raw=Path("/proc/self/fdinfo",str(handle)).read_bytes()
            values=[line.split(b":",1)[1].strip() for line in raw.splitlines() if line.startswith(b"mnt_id:")]
            need(len(values)==1 and values[0].isdigit() and int(values[0])>0,"fixture_mount_id_unknown")
            return int(values[0]),(info.st_dev,info.st_ino)
        finally:os.close(handle)
    def mount_rows_at(path):
        point=os.fsencode(path);found=[]
        for line in Path("/proc/self/mountinfo").read_bytes().splitlines():
            fields=line.split(b" - ",1)[0].split()
            need(len(fields)>=6,"fixture_mountinfo_shape")
            value=fields[4]
            for encoded,decoded in ((b"\\040",b" "),(b"\\011",b"\t"),(b"\\012",b"\n"),(b"\\134",b"\\")):
                value=value.replace(encoded,decoded)
            if value==point:
                found.append({"mount_id":int(fields[0]),"parent_id":int(fields[1])})
        return found
    def masked_alias(name,expect,reference_kind=None,reference_pid=1,descriptor=None):
        before_id,before_identity=path_mount_identity(alias)
        need(before_identity==path_mount_identity(parent)[1],"mask_preimage_is_not_parent_bind")
        mount(outside,alias,None,4096)
        try:
            after_id,after_identity=path_mount_identity(alias)
            need(after_id!=before_id and after_identity==path_mount_identity(outside)[1],"mask_mount_not_observed")
            try:os.stat(alias_target,follow_symlinks=False)
            except FileNotFoundError:pass
            else:raise RuntimeError("masked_target_should_be_missing_below_strict_ancestor")
            result=run(name,expect)
            count=result.get("verified_shadowed_alias_path_count")
            need(type(count) is int and count>=1,name+"_shadow_branch_not_observed")
            if reference_kind is not None:
                need(any(hit.get("kind")==reference_kind and hit.get("pid")==reference_pid
                         and (descriptor is None or hit.get("fd")==str(descriptor))
                         for hit in result["process_or_owner_hits"]),name+"_specific_reference_not_vetoed")
            rows[-1]["fixture_mask"]={"strict_ancestor_overmount":True,"target_lookup_errno":"ENOENT",
                                       "before_mount_id":before_id,"after_mount_id":after_id,
                                       "covering_identity":list(after_identity)}
            if reference_kind is not None:rows[-1]["required_reference_kind"]=reference_kind
        finally:unmount(alias)
    try:
        run("ancestor_alias_only","clear")
        masked_alias("strict_ancestor_mask_without_references","clear")
        lower_id,_=path_mount_identity(alias)
        mount(parent,alias,None,4096)
        try:
            upper_id,_=path_mount_identity(alias)
            samepoint=mount_rows_at(alias)
            selected=[row for row in samepoint if row["mount_id"]==upper_id]
            need(upper_id!=lower_id and len(samepoint)>=2 and len(selected)==1
                 and selected[0]["parent_id"]==lower_id,"samepoint_stack_not_exactly_bound")
            target_mnt,target_identity=path_mount_identity(alias_target)
            need(target_mnt==upper_id and target_identity==path_mount_identity(target)[1],"samepoint_top_target_not_bound")
            result=run("samepoint_stack_visible_top_layer","clear")
            count=result.get("visible_alias_path_count")
            need(type(count) is int and count>=1,"samepoint_visible_alias_not_observed")
            rows[-1]["fixture_stack"]={"lower_mount_id":lower_id,"selected_mount_id":upper_id,
                                        "target_mount_id":target_mnt,"target_identity":list(target_identity),
                                        "samepoint_rows":samepoint}
        finally:unmount(alias)
        fd=os.open(alias_target/"payload",os.O_RDONLY|os.O_CLOEXEC)
        try:
            need(os.readlink("/proc/self/fd/"+str(fd))==str(alias_target/"payload"),"masked_fd_alias_display")
            masked_alias("strict_ancestor_mask_with_held_fd","reference","fd",descriptor=fd)
        finally:os.close(fd)
        fd=os.open(alias_target/"payload",os.O_RDONLY|os.O_CLOEXEC)
        mapped=mmap.mmap(fd,0,access=mmap.ACCESS_READ);os.close(fd)
        try:masked_alias("strict_ancestor_mask_with_mmap","reference","maps")
        finally:mapped.close()
        ready_read,ready_write=os.pipe2(os.O_CLOEXEC);ctl_read,ctl_write=os.pipe2(os.O_CLOEXEC)
        code="import os,sys;os.write(int(sys.argv[1]),b'R');os.read(int(sys.argv[2]),1)"
        process=subprocess.Popen([sys.executable,"-I","-B","-c",code,str(ready_write),str(ctl_read),str(alias_target/"payload")],pass_fds=(ready_write,ctl_read),cwd="/",stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        os.close(ready_write);os.close(ctl_read)
        try:
            need(select.select([ready_read],[],[],3)[0] and os.read(ready_read,1)==b"R","masked_argv_child_ready")
            os.close(ready_read);ready_read=None
            need(os.fsencode(alias_target/"payload") in Path("/proc",str(process.pid),"cmdline").read_bytes().split(b"\0"),"masked_argv_exact_argument_absent")
            masked_alias("strict_ancestor_mask_with_argv_only","reference","owner_argument_reference",process.pid)
        finally:
            os.write(ctl_write,b"X");os.close(ctl_write)
            try:code=process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();code=process.wait(timeout=3)
            child_rows.append({"pid":process.pid,"exit_code":code,"reaped":True})
            need(code==0,"masked_argv_child_terminal")
            if ready_read is not None:os.close(ready_read)
        fd=os.open(alias_target/"payload",os.O_RDONLY|os.O_CLOEXEC)
        try:run("actual_fd_via_alias","reference")
        finally:os.close(fd)
        fd=os.open(alias_target/"payload",os.O_RDONLY|os.O_CLOEXEC)
        mapped=mmap.mmap(fd,0,access=mmap.ACCESS_READ);os.close(fd)
        try:run("actual_mmap_via_alias","reference")
        finally:mapped.close()
        os.chdir(alias_target)
        try:run("actual_cwd_via_alias","reference")
        finally:os.chdir("/")
        ready_read,ready_write=os.pipe2(os.O_CLOEXEC);ctl_read,ctl_write=os.pipe2(os.O_CLOEXEC)
        code="import os,sys;os.write(int(sys.argv[1]),b'R');os.read(int(sys.argv[2]),1)"
        process=subprocess.Popen([sys.executable,"-I","-B","-c",code,str(ready_write),str(ctl_read),str(alias_target/"payload")],pass_fds=(ready_write,ctl_read),cwd="/",stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        os.close(ready_write);os.close(ctl_read)
        try:
            need(select.select([ready_read],[],[],3)[0] and os.read(ready_read,1)==b"R","argv_child_ready")
            os.close(ready_read);ready_read=None
            run("argv_only_alias_path","reference")
        finally:
            os.write(ctl_write,b"X");os.close(ctl_write)
            try:code=process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();code=process.wait(timeout=3)
            child_rows.append({"pid":process.pid,"exit_code":code,"reaped":True})
            need(code==0,"argv_child_terminal")
            if ready_read is not None:os.close(ready_read)
        mount(outside,alias_target/"mounted",None,4096)
        try:run("mountpoint_inside_target_via_alias","mount")
        finally:unmount(alias_target/"mounted")
        mount(target/"subtree",mirror,None,4096)
        try:run("target_subtree_as_bind_source","mount")
        finally:unmount(mirror)
        mount(outside,alias_target,None,4096)
        try:run("shadowed_alias_wrong_inode","unknown")
        finally:unmount(alias_target)
        # A namespace with no live task and no nsfs bind, retained only by P1's FD.
        ready_read,ready_write=os.pipe2(os.O_CLOEXEC);ctl_read,ctl_write=os.pipe2(os.O_CLOEXEC)
        expected_parent=os.getpid();creator=os.fork()
        if creator==0:
            try:
                os.close(ready_read);os.close(ctl_write);death_parent(expected_parent)
                os.unshare(0x20000)
                os.write(ready_write,b"R");os.close(ready_write)
                need(os.read(ctl_read,1)==b"X","fd_only_release")
                os._exit(0)
            except BaseException:os._exit(126)
        os.close(ready_write);os.close(ctl_read)
        need(select.select([ready_read],[],[],3)[0] and os.read(ready_read,1)==b"R","fd_only_creator_ready")
        os.close(ready_read)
        nsfd=os.open("/proc/"+str(creator)+"/ns/mnt",os.O_RDONLY|os.O_CLOEXEC)
        nsinfo=os.fstat(nsfd)
        os.write(ctl_write,b"X");os.close(ctl_write)
        code=wait_exact(creator);child_rows.append({"pid":creator,"exit_code":code,"reaped":True})
        need(code==0,"fd_only_creator_terminal")
        try:
            result=run("fd_only_namespace_discovery_and_coverage","clear")
            need(type(result.get("namespace_fd_count")) is int and result["namespace_fd_count"]>=1,"fd_only_namespace_not_discovered")
            expected_namespace=[nsinfo.st_dev,nsinfo.st_ino]
            terminals=result.get("namespace_child_terminals")
            need(type(terminals) is list and any(list(item.get("namespace",()))==expected_namespace
                 and item.get("reaped") is True and type(item.get("exit_code")) is int
                 and item["exit_code"]==0 for item in terminals),"fd_only_namespace_not_witnessed_and_retired")
            need("mnt:["+str(nsinfo.st_ino)+"]" not in result.get("uncovered_mount_namespaces",[]),
                 "fd_only_namespace_uncovered")
            lifecycle=result.get("namespace_child_lifecycle",{})
            need(lifecycle.get("close_succeeded") is True,"collector_retirement_not_successful")
            rows[-1]["retained_namespace_identity"]=expected_namespace
            rows[-1]["exact_fd_only_namespace_witness_reaped"]=True
        finally:os.close(nsfd)
        run("restored_alias_only_after_all_negative_controls","clear")
        need(len(rows)==15,"exact_fifteen_controls_required")
    finally:
        os.chdir("/")
        unmount(alias)
    try:
        os.waitpid(-1,os.WNOHANG)
    except ChildProcessError:no_remaining_children=True
    else:no_remaining_children=False
    need(no_remaining_children,"unexpected_live_or_unreaped_child")
    return {"schema":"pocket4-isolated-alias-controls-v1","status":"PASS","optimized":sys.flags.optimize,"controls":len(rows),"rows":rows,"owned_fixture_child_terminals":child_rows,"source_sha256":hashlib.sha256(raw_source).hexdigest(),"deletion_authorized":False,"private_pid_namespace":True,"private_mount_propagation":True}
host_mounts=Path("/proc/self/mountinfo").read_bytes()
host_ns=(os.stat("/proc/self/ns/mnt").st_dev,os.stat("/proc/self/ns/mnt").st_ino)
need(libc.prctl(36,1,0,0,0)==0,"fixture_subreaper")
with tempfile.TemporaryDirectory(prefix="isolated-alias-",dir=base) as directory:
    report_read,report_write=os.pipe2(os.O_CLOEXEC)
    parent=os.getpid();outer=os.fork()
    if outer==0:
        try:
            os.close(report_read);death_parent(parent)
            os.unshare(0x20000)
            mount(None,"/",None,(1<<14)|(1<<18))
            os.unshare(0x20000000)
            outer_pidfd=os.pidfd_open(os.getpid(),0);pid1=os.fork()
            if pid1==0:
                try:
                    need(libc.prctl(1,signal.SIGKILL,0,0,0)==0,"pid1_pdeath")
                    need(not select.select([outer_pidfd],[],[],0)[0],"pid1_parent_already_exited")
                    os.close(outer_pidfd)
                    result=inner(Path(directory))
                    payload=json.dumps(result,sort_keys=True).encode()
                    need(len(payload)<=65536,"fixture_result_bound")
                    while payload:
                        count=os.write(report_write,payload);payload=payload[count:]
                    os.close(report_write);os._exit(0)
                except BaseException as error:
                    payload=json.dumps({"status":"FAIL","error":type(error).__name__,"detail":str(error)}).encode()
                    try:os.write(report_write,payload[:16384])
                    except BaseException:pass
                    os._exit(1)
            os.close(outer_pidfd);os.close(report_write)
            os._exit(0 if wait_exact(pid1,40)==0 else 1)
        except BaseException:os._exit(126)
    os.close(report_write);os.set_blocking(report_read,False)
    payload=bytearray();deadline=time.monotonic()+43;complete=False
    try:
        while time.monotonic()<deadline:
            ready,_,_=select.select([report_read],[],[],max(0,min(.1,deadline-time.monotonic())))
            if ready:
                chunk=os.read(report_read,65537-len(payload))
                if not chunk:complete=True;break
                payload.extend(chunk);need(len(payload)<=65536,"fixture_result_bound")
        need(complete,"fixture_total_deadline")
        outer_code=wait_exact(outer,3)
        result=json.loads(payload)
        need(outer_code==0 and result.get("status")=="PASS","isolated_controls_failed:"+json.dumps(result,sort_keys=True))
        need((os.stat("/proc/self/ns/mnt").st_dev,os.stat("/proc/self/ns/mnt").st_ino)==host_ns,"host_namespace_changed")
        need(Path("/proc/self/mountinfo").read_bytes()==host_mounts,"host_mountinfo_changed")
        result.update({"outer_pid":outer,"outer_exit_code":outer_code,"outer_reaped":True,"pid1_exit_code":0,"pid1_reaped_by_outer":True,"host_namespace_unchanged":True,"host_mountinfo_sha256":hashlib.sha256(host_mounts).hexdigest(),"host_mountinfo_unchanged":True})
    finally:
        os.close(report_read)
        try:
            found,status=os.waitpid(outer,os.WNOHANG)
            if not found:os.kill(outer,signal.SIGKILL);os.waitpid(outer,0)
        except ChildProcessError:pass
        until=time.monotonic()+3
        while time.monotonic()<until:
            try:
                found,status=os.waitpid(-1,os.WNOHANG)
                if not found:time.sleep(.01)
            except ChildProcessError:break

need(not os.path.lexists(directory),"private_fixture_paths_not_retired")
result["all_fixture_paths_retired_after_namespace_exit"]=True
print(json.dumps(result,sort_keys=True))
