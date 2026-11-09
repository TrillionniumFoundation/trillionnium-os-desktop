"""Explicit privileged host qualification; actual existing namespace count is required.

Only owned children/namespaces are created or signalled. This host-observation
entry point is not the portable ordinary-UID CI suite.
"""
import ast
import argparse
import ctypes,fcntl,hashlib,json,os,re,select,signal,sys,time
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--expected-persistent-count',type=int,required=True)
options=parser.parse_args()
source=Path(__file__).with_name('reference_observer.py').read_text()
tree=ast.parse(source)
outer=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='live_references')
definitions=[node for node in outer.body if isinstance(node,ast.FunctionDef) and node.name=='make_namespace_view_collector']
if len(definitions)!=1:raise RuntimeError('exact_embedded_factory_required')
namespace={}
exec(compile(ast.fix_missing_locations(ast.Module(body=definitions,type_ignores=[])),'embedded_namespace_collector','exec'),namespace)
make_namespace_view_collector=namespace['make_namespace_view_collector']
deadline=time.monotonic()+45
checks=[];terminals=[];pools=[];owned_fds=[]
def need(value,label):
    if not value: raise RuntimeError(label)
def record(label):checks.append(label)
def rejected(label,call,kind=RuntimeError):
    try:call()
    except kind:record(label)
    else:raise RuntimeError(label+"_accepted")
def wait_owned(pid):
    while time.monotonic()<deadline:
        done,status=os.waitpid(pid,os.WNOHANG)
        if done:
            code=os.waitstatus_to_exitcode(status)
            terminals.append({"pid":pid,"reaped":True,"exit_code":code})
            return code
        time.sleep(.005)
    os.kill(pid,signal.SIGKILL)
    raise RuntimeError("owned_child_deadline")
def read_pipe(fd,limit=16384):
    data=bytearray()
    while time.monotonic()<deadline:
        ready,_,_=select.select([fd],[],[],max(0,min(.05,deadline-time.monotonic())))
        if ready:
            chunk=os.read(fd,limit+1-len(data))
            if not chunk:return bytes(data)
            data.extend(chunk);need(len(data)<=limit,"fixture_output_bound")
    raise RuntimeError("fixture_pipe_timeout")
def pdeath():
    libc=ctypes.CDLL(None,use_errno=True)
    need(libc.prctl(1,signal.SIGKILL,0,0,0)==0,"fixture_pdeath")
def new_pool():
    pool=make_namespace_view_collector(deadline)
    pools.append(pool);return pool
def close_pool(pool,allow_failure=False):
    try:pool.close()
    except RuntimeError:
        if not allow_failure:raise
    for item in pool.retirement:
        terminals.append(dict(item))
        need(item["reaped"],"collector_unreaped")
    if not allow_failure:need(all(x["exit_code"]==0 for x in pool.retirement),"collector_nonzero")
def all_arguments(w):
    return [w,w.pid,w.starttime,w.namespace,w.root_identity,w.root_displayed,w.raw]
hostraw=Path("/proc/self/mountinfo").read_bytes()
hostnsfd=os.open("/proc/self/ns/mnt",os.O_RDONLY|os.O_CLOEXEC);owned_fds.append(hostnsfd)
hostkey=(os.fstat(hostnsfd).st_dev,os.fstat(hostnsfd).st_ino)
hostpid=os.getpid()
summaries=[]
try:
    pool=new_pool()
    host=pool.acquire(hostnsfd,expected=hostkey)
    need(pool.verify(host) is True,"verify_not_true")
    need(pool.matches(*all_arguments(host)),"normal_match")
    record("host_native_root_real_setns")
    need(host.pdeath_signal==signal.SIGKILL,"pdeath_configuration")
    record("pdeathsig_configuration_read_back")
    need(pool.acquire(hostnsfd,expected=hostkey) is host,"duplicate_not_same")
    record("duplicate_fd_reuses_owned_witness")
    rejected("wrong_expected_namespace",lambda:pool.acquire(hostnsfd,expected=(hostkey[0],hostkey[1]+1)))
    other=os.open("/proc/self/ns/net",os.O_RDONLY|os.O_CLOEXEC);owned_fds.append(other)
    rejected("wrong_namespace_type",lambda:pool.acquire(other))
    rejected("json_cannot_forge_witness",lambda:pool.verify({"pid":host.pid}))
    rejected("unregistered_object_cannot_forge_witness",lambda:pool.verify(type(host)()))
    args=all_arguments(host);args[1]+=1
    rejected("wrong_owned_pid",lambda:pool.matches(*args))
    args=all_arguments(host);args[2]+=1
    rejected("wrong_starttime",lambda:pool.matches(*args))
    args=all_arguments(host);args[3]=(hostkey[0],hostkey[1]+1)
    rejected("wrong_scanner_namespace",lambda:pool.matches(*args))
    args=all_arguments(host);args[4]=(host.root_identity[0],host.root_identity[1]+1)
    rejected("wrong_scanner_root",lambda:pool.matches(*args))
    args=all_arguments(host);args[5]="/not-the-native-root"
    rejected("wrong_root_display",lambda:pool.matches(*args))
    args=all_arguments(host);args[6]=host.raw+b"\n"
    rejected("changed_mount_view",lambda:pool.matches(*args))
    rejected("missing_namespace_coverage",lambda:pool.require_coverage([(hostkey[0],hostkey[1]+100000)]))
    rejected("deadline_reserve_enforced",lambda:make_namespace_view_collector(time.monotonic()+1),ValueError)
    rejected("deadline_over_45_rejected",lambda:make_namespace_view_collector(time.monotonic()+46),ValueError)
    nsfs=[]
    for line in hostraw.splitlines():
        fields=line.split();cut=fields.index(b"-")
        if fields[cut+1]!=b"nsfs":continue
        match=re.fullmatch(rb"mnt:\[([1-9][0-9]*)\]",fields[3])
        need(match is not None,"unknown_nsfs_type")
        point=re.sub(rb"\\([0-7]{3})",lambda m:bytes([int(m.group(1),8)]),fields[4])
        fd=os.open(point,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW);owned_fds.append(fd)
        stat=os.fstat(fd);key=(stat.st_dev,stat.st_ino)
        need(key[1]==int(match[1]),"nsfs_inode_changed")
        w=pool.acquire(fd,expected=key)
        need(pool.verify(w) and pool.matches(*all_arguments(w)),"persistent_ns_witness")
        nsfs.append(key)
        summaries.append({"namespace":key,"pid":w.pid,"starttime":w.starttime,"root_identity":w.root_identity,"root_displayed":w.root_displayed,"root_mnt_id":w.root_mnt_id,"mountinfo_bytes":len(w.raw),"mountinfo_sha256":hashlib.sha256(w.raw).hexdigest()})
    if options.expected_persistent_count is not None:
        need(len(nsfs)==options.expected_persistent_count,"persistent_namespace_count_changed")
    record("actual_persistent_namespace_views")
    # Fresh mount namespace, retained only by a held FD after its sole task exits.
    ack_read,ack_write=os.pipe2(os.O_CLOEXEC);ctl_read,ctl_write=os.pipe2(os.O_CLOEXEC)
    before_parent=os.getpid()
    creator=os.fork()
    if creator==0:
        try:
            os.close(ack_read);os.close(ctl_write)
            pdeath();need(os.getppid()==before_parent,"fixture_parent_changed")
            signal.signal(signal.SIGALRM,signal.SIG_DFL);signal.alarm(10)
            os.unshare(0x20000)
            os.write(ack_write,b"R");os.close(ack_write)
            need(os.read(ctl_read,1)==b"X","fixture_release")
            os._exit(0)
        except BaseException:os._exit(126)
    os.close(ack_write);os.close(ctl_read)
    need(read_pipe(ack_read)==b"R","fd_only_creator_ready");os.close(ack_read)
    fdonly=os.open("/proc/"+str(creator)+"/ns/mnt",os.O_RDONLY|os.O_CLOEXEC);owned_fds.append(fdonly)
    fs=os.fstat(fdonly);fdkey=(fs.st_dev,fs.st_ino)
    need(fdkey not in nsfs+[hostkey],"fd_only_namespace_not_new")
    os.write(ctl_write,b"X");os.close(ctl_write)
    need(wait_owned(creator)==0,"fd_only_creator_exit")
    only=pool.acquire(fdonly,expected=fdkey)
    need(pool.verify(only) and pool.matches(*all_arguments(only)),"fd_only_witness")
    need(pool.require_coverage(nsfs+[hostkey,fdkey]),"all_coverage")
    record("fd_only_namespace_without_live_task_or_bind")
    record("complete_requested_coverage")
    close_pool(pool)
    need(pool.close()==pool.retirement,"idempotent_close")
    record("normal_children_reaped_and_close_idempotent")
    rejected("retired_witness_rejected",lambda:pool.verify(host))
    # Deliberately kill only a child owned by this fresh pool.
    death_pool=new_pool();dead=death_pool.acquire(hostnsfd,expected=hostkey)
    pidfd=os.pidfd_open(dead.pid,0)
    signal.pidfd_send_signal(pidfd,signal.SIGKILL)
    need(select.select([pidfd],[],[],min(2,max(0,deadline-time.monotonic())))[0],"child_did_not_exit")
    os.close(pidfd)
    rejected("child_exit_rejected",lambda:death_pool.verify(dead))
    rejected("nonzero_retirement_rejected",lambda:death_pool.close())
    terminals.extend(dict(item) for item in death_pool.retirement)
    need(all(item["reaped"] and item["exit_code"]==-signal.SIGKILL for item in death_pool.retirement),"killed_child_not_reaped")
    # Allocation failures must close partial descriptors before any success.
    def fd_count():return len(os.listdir("/proc/self/fd"))
    failure_pool=new_pool()
    before_fds=fd_count();old_pipe=os.pipe2;pipe_calls=[0]
    def fail_second_pipe(flags):
        pipe_calls[0]+=1
        if pipe_calls[0]==2:raise OSError(24,"fixture")
        return old_pipe(flags)
    os.pipe2=fail_second_pipe
    try:rejected("partial_pipe_allocation_rejected",lambda:failure_pool.acquire(hostnsfd),OSError)
    finally:os.pipe2=old_pipe
    need(fd_count()==before_fds,"partial_pipe_fd_leak")
    close_pool(failure_pool)
    fork_pool=new_pool();before_fds=fd_count();old_fork=os.fork
    def fail_fork():raise OSError(11,"fixture")
    os.fork=fail_fork
    try:rejected("fork_failure_rejected",lambda:fork_pool.acquire(hostnsfd),OSError)
    finally:os.fork=old_fork
    need(fd_count()==before_fds,"fork_failure_fd_leak")
    close_pool(fork_pool)
    pidfd_pool=new_pool();old_pidfd=os.pidfd_open
    def fail_pidfd(*args):raise OSError(24,"fixture")
    os.pidfd_open=fail_pidfd
    try:rejected("pidfd_failure_after_fork_rejected",lambda:pidfd_pool.acquire(hostnsfd),OSError)
    finally:os.pidfd_open=old_pidfd
    close_pool(pidfd_pool)
    failed_child_pool=new_pool();old_setns=os.setns
    def fail_setns(*args):raise PermissionError(1,"fixture")
    os.setns=fail_setns
    try:rejected("setns_syscall_failure_rejected",lambda:failed_child_pool.acquire(hostnsfd))
    finally:os.setns=old_setns
    close_pool(failed_child_pool,allow_failure=True)
    need(all(item["exit_code"]==126 for item in failed_child_pool.retirement),"failed_setns_terminal")
    # Parent death: adopt only our own grandchild and verify SIGKILL, not a leak.
    libc=ctypes.CDLL(None,use_errno=True)
    need(libc.prctl(36,1,0,0,0)==0,"subreaper_setup")
    report_read,report_write=os.pipe2(os.O_CLOEXEC)
    middle=os.fork()
    if middle==0:
        try:
            os.close(report_read);pdeath()
            midpool=make_namespace_view_collector(deadline)
            midw=midpool.acquire(hostnsfd,expected=hostkey)
            os.write(report_write,json.dumps({"pid":midw.pid}).encode())
            os.close(report_write)
            os._exit(0)
        except BaseException:os._exit(126)
    os.close(report_write)
    mid_report=json.loads(read_pipe(report_read));os.close(report_read)
    need(wait_owned(middle)==0,"intermediate_parent_exit")
    parent_death_exit=wait_owned(mid_report["pid"])
    need(parent_death_exit in (0,-signal.SIGKILL),"parent_death_did_not_retire_child")
    record("parent_death_signal_or_control_eof_retires_owned_orphan")
    need((os.stat("/proc/self/ns/mnt").st_dev,os.stat("/proc/self/ns/mnt").st_ino)==hostkey,"parent_namespace_changed")
    need(Path("/proc/self/mountinfo").read_bytes()==hostraw,"host_mountinfo_changed")
    record("parent_namespace_and_mounts_unchanged")
    need(all(item["reaped"] for item in terminals),"terminal_gap")
    result={"schema":"namespace-view-collector-controls-v1","status":"PASS","optimized":sys.flags.optimize,"controls":len(checks),"checks":checks,"elapsed_seconds":round(45-(deadline-time.monotonic()),6),"persistent_namespace_count":len(nsfs),"persistent_views":summaries,"owned_child_terminals":terminals,"host_namespace":hostkey,"host_mountinfo_sha256":hashlib.sha256(hostraw).hexdigest(),"no_mount_operations":True,"parent_death_child_exit":parent_death_exit,"deletion_authorized":False}
    print(json.dumps(result,sort_keys=True))
finally:
    for pool in pools:
        try:pool.close()
        except BaseException:pass
    for fd in owned_fds:
        try:os.close(fd)
        except OSError:pass
