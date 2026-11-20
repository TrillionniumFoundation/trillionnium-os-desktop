"""Fixed current cell parent chain and fresh user-namespace observations.

No process discovery, namespace entry, command, signal or Android action. Only
the fixed parents/child identities in the actual discovery policy are read.
All opened descriptors belong to the caller's tracked scope.
"""
import os,re,select,stat
MAX_THREADS=64
MAX_CHILDREN=32
def need(value,code):
    if not value:raise RuntimeError(code)
def safe_error(error):
    result={"type":type(error).__name__}
    if isinstance(error,OSError):result["errno"]=error.errno
    elif isinstance(error,RuntimeError) and re.fullmatch(r"[A-Z0-9_]{1,96}",str(error)):
        result["code"]=str(error)
    else:result["code"]="UNEXPECTED_CELL_LINEAGE_FAILURE"
    return result

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


def read_proc_leaf(pool,directory,name,limit,check):
 check();fd=pool.own(os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory),"lineage_proc_leaf")
 try:
  raw=b''
  while True:
   check();piece=os.read(fd,min(4096,limit+1-len(raw)))
   if not piece:break
   raw+=piece;need(len(raw)<=limit,'PROC_LEAF_BOUND')
  return raw
 finally:pool.close(fd)

def parse_pid_words(raw,limit,code):
 need(type(raw) is bytes and len(raw)<=16384,code)
 text=raw.decode('ascii','strict')
 need(all(c in '0123456789 \t\n' for c in text),code)
 values=text.split()
 need(len(values)<=limit,code)
 need(all(re.fullmatch('[1-9][0-9]{0,9}',word) and int(word)<=2147483647 for word in values),code)
 result=[int(word) for word in values]
 need(len(set(result))==len(result),'DIRECT_CHILDREN_DUPLICATE')
 return sorted(result)

def join_children(per_thread):
 need(type(per_thread) is dict and 0<len(per_thread)<=MAX_THREADS,'THREAD_LIST_BOUND')
 values=[]
 for tid,children in per_thread.items():
  need(type(tid) is int and 0<tid<=2147483647 and type(children) is list,'THREAD_LIST_SCHEMA')
  values+=children
 need(len(values)<=MAX_CHILDREN,'DIRECT_CHILDREN_BOUND')
 need(len(set(values))==len(values),'DIRECT_CHILDREN_DUPLICATE')
 return sorted(values)

def children_sample(pool,proc,parent_pid,check):
 task=pool.own(os.open("task",os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=proc),"lineage_task_directory")
 try:
  names=os.listdir(task)
  need(0<len(names)<=MAX_THREADS and all(re.fullmatch('[1-9][0-9]{0,9}',name) and int(name)<=2147483647 for name in names),
   'THREAD_LIST_BOUND')
  tids=sorted(int(name) for name in names)
  need(len(set(tids))==len(tids) and parent_pid in tids,'THREAD_LIST_SCHEMA')
  rows={}
  for tid in tids:
   check();thread=pool.own(os.open(str(tid),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=task),"lineage_thread_directory")
   try:rows[tid]=parse_pid_words(read_proc_leaf(pool,thread,'children',16384,check),MAX_CHILDREN,'DIRECT_CHILDREN_SCHEMA')
   finally:pool.close(thread)
  after=os.listdir(task)
  need(sorted(after)==sorted(names),'DIRECT_CHILDREN_SAMPLE_CHANGED')
  all_children=join_children(rows)
  return {'thread_ids':tids,'per_thread':{str(k):v for k,v in rows.items()},'child_host_pids':all_children}
 finally:pool.close(task)

def require_pidfd_live(fd):
 import select
 poll=select.poll();poll.register(fd,select.POLLIN|select.POLLHUP|select.POLLERR)
 need(not poll.poll(0),'HELD_CELL_PROCESS_PIDFD_NOT_LIVE')


def hold_intermediary(pool,p):
    pid=p.EXPECTED_INTERMEDIARY["pid"]
    pidfd=pool.own(os.pidfd_open(pid,0),"intermediary_pidfd")
    proc=pool.own(os.open("/proc/"+str(pid),os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW),
                  "intermediary_proc_directory")
    require_pidfd_live(pidfd)
    return {"pidfd":pidfd,"proc":proc}

def namespace_sample(pool,procs,intermediary,check):
    check();host=os.readlink("/proc/self/ns/user")
    fd=pool.own(os.open("root",os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC,dir_fd=intermediary["proc"]),
                "intermediary_current_root")
    try:
        st=os.fstat(fd)
        need(stat.S_ISDIR(st.st_mode),"CURRENT_INTERMEDIARY_ROOT_NOT_DIRECTORY")
        root={"device":st.st_dev,"inode":st.st_ino}
        return {"host":host,"roles":{role:os.readlink("ns/user",dir_fd=proc) for role,proc in procs.items()},
                "intermediary":os.readlink("ns/user",dir_fd=intermediary["proc"]),"intermediary_root":root}
    finally:pool.close(fd)

def sample(pool,p,epoch,procs,intermediary,check):
    check()
    need(set(procs)==set(p.ROLES) and set(intermediary)=={"pidfd","proc"},"FIXED_LINEAGE_HANDLE_SET")
    require_pidfd_live(intermediary["pidfd"])
    first=epoch.process_identity(p.EXPECTED_INTERMEDIARY["pid"])
    before_ns=namespace_sample(pool,procs,intermediary,check)
    parents={"daemon":procs["daemon"],"launcher":procs["launcher"],"intermediary":intermediary["proc"]}
    before={}
    for row in p.CHAIN_PARENTS:
        check()
        before[row["role"]]=children_sample(pool,parents[row["role"]],row["pid"],check)
        p.validate_child_table(before[row["role"]],row["pid"],row["child"])
    after={}
    for row in p.CHAIN_PARENTS:
        check()
        after[row["role"]]=children_sample(pool,parents[row["role"]],row["pid"],check)
    last=epoch.process_identity(p.EXPECTED_INTERMEDIARY["pid"])
    after_ns=namespace_sample(pool,procs,intermediary,check)
    require_pidfd_live(intermediary["pidfd"])
    need(first==last and before==after,"CURRENT_OWNER_CHAIN_CHANGED_DURING_SAMPLE")
    need(before_ns==after_ns,"CURRENT_USER_NAMESPACES_CHANGED_DURING_SAMPLE")
    value={"schema":"pocket4-current-cell-owner-lineage-v1","intermediary_process":last,"child_tables":after,
           "host_user_namespace":after_ns["host"],"role_user_namespaces":after_ns["roles"],
           "intermediary_user_namespace":after_ns["intermediary"],"intermediary_root":after_ns["intermediary_root"],
           "intermediary_program_authority_assigned":False}
    p.validate_cell_lineage(value)
    check()
    return value
