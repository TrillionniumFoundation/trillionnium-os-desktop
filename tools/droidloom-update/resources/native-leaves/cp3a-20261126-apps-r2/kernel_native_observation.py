"""Current kernel-first leaf comparisons, subordinate to the live Rust owner.

The Rust producer/leaf runner supplies the actual Main, actual PM token, target
working-directory metadata and a private bounded check channel. This module
does not authenticate a socket peer, admit a saved owner, select an alternative
Main, or mint a business gate. It preserves actual proc/PIDFD/root/namespace,
normal service, classpath and fixed readonly helper observations.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import time
import types

ROOT=Path('/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2')
MAIN=ROOT/'source/main'
QUALIFICATION=Path('/var/lib/droidloom/qualification/pocket4')
CHANNEL_SHA='3ec881482aef5bffb2c9d05e79d6ca3f44cd3c0d94a36c3c1dd7fd995e5e7ac1'
DATA_SHA='700c81b80bf8378cb1d3e2e916d82ba3a9004bfb9d2d75c9aab7773a8c3c98ed'
ANCESTRY_SHA='824492a2e9068aa30c3d5dc148402802843a3aaa574c41c290819a9f3d65d201'
EPOCH_SHA='ba4854fcc42def3fb37ac8add1e2b4382d24cb716e2d8181e84b286d5975c377'
READER_SHA='3d2860cde4ec7c7cbe67ed4756d9f599646ee39dc36f2f80b3ef008fba6b80cb'
CAPTURE_SHA='eac7d44f24f299718dd4f090a2aecfe1e40bace3578c0ddb15831357615dabff'
HELPER_SHA='3a3dd3037c03c09fd7ebc1068123a202a29d286c1bf77fb81a4476fb25576a3c'
READONLY_SHA='98f6af7733896835da8d375a950a5cc0de01bd4429622c8ada230a869efc25d1'
COMMANDS_SHA='25aac17bf57736ab0a6680b2da2304cc2b68fec31c1f9c421d62b2bcbf1a759a'
SCHEMA='droidloom.native-leaf-business-baseline.v1'
QUAL_SCHEMA='droidloom.native-leaf-business-qualification.v1'
RUNTIME_SCHEMA='droidloom.native-leaf-runtime-comparison.v1'
ROLES=('daemon','presenter','init','zygote64','system_server','surfaceflinger')
ANDROID=('init','zygote64','system_server','surfaceflinger')
NS=('user','mnt','pid','uts','ipc','net','cgroup')
PROGRAM='/usr/lib/droidloom/production/current/droidloomd'
PRESENTER='/usr/bin/droidloom-wayland'
ENGINE='/system/system_ext/lib64/libberberis_arm64.so'
SYSTEM_UNIT='droidloom-production.service'
USER_UNIT='droidloom-production-desktop.service'
CGROUP='/system.slice/droidloom-production.service'
PAYLOAD_CGROUP=CGROUP+'/cell-u1000/payload/'
LIMITS={'cpu.max':'600000 100000','memory.high':'6442450944',
        'memory.max':'8589934592','memory.swap.max':'0','pids.max':'32768'}
META=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')

def need(value,code):
    if not value:raise RuntimeError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def parse(raw):
    def pairs(rows):
        out={}
        for key,value in rows:
            need(key not in out,'DUPLICATE_NATIVE_LEAF_BASELINE_FIELD');out[key]=value
        return out
    def bad(_):raise RuntimeError('NONFINITE_NATIVE_LEAF_BASELINE_FIELD')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=bad)
def metadata(fd):return {key:getattr(os.fstat(fd),key) for key in META}
def node(fd):
    st=os.fstat(fd);return {'device':st.st_dev,'inode':st.st_ino}
def root_parents(path,private=False):
    need(path.is_absolute() and path.resolve()==path,'CANONICAL_NATIVE_LEAF_FILE_REQUIRED')
    for parent in path.parents:
        st=parent.lstat()
        need(stat.S_ISDIR(st.st_mode) and st.st_uid==st.st_gid==0 and not st.st_mode&0o022,
             'ROOT_PROTECTED_NATIVE_LEAF_PARENT_REQUIRED')
    if private:
        need(path.is_relative_to(QUALIFICATION) and
             stat.S_IMODE(path.parent.lstat().st_mode)==0o700,
             'PRIVATE_NORMAL_BASELINE_DIRECTORY_REQUIRED')
def read_ref(ref,maximum=16*1024*1024,source=False):
    need(type(ref) is dict and set(ref) in ({'path','sha256'},{'path','bytes','sha256'}) and
         type(ref['path']) is str and type(ref['sha256']) is str and
         re.fullmatch('[0-9a-f]{64}',ref['sha256']),'EXACT_NATIVE_LEAF_FILEPIN_REQUIRED')
    path=Path(ref['path']);root_parents(path,private=not source)
    if source:need(path.is_relative_to(ROOT),'FIXED_COHORT_SOURCE_REQUIRED')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=metadata(fd)
        need(stat.S_ISREG(before['st_mode']) and before['st_uid']==before['st_gid']==0 and
             before['st_nlink']==1 and 0<before['st_size']<=maximum and
             stat.S_IMODE(before['st_mode'])==(0o444 if source else 0o600),
             'SEALED_SOURCE_OR_PRIVATE_NORMAL_BASELINE_REQUIRED')
        raw=bytearray();end=time.monotonic()+10
        while True:
            need(time.monotonic()<end,'NATIVE_LEAF_FILE_READ_DEADLINE')
            block=os.read(fd,min(65536,maximum+1-len(raw)))
            if not block:break
            raw.extend(block);need(len(raw)<=maximum,'NATIVE_LEAF_FILE_GREW')
        named=path.lstat()
        need(before==metadata(fd)=={k:getattr(named,k) for k in META} and
             len(raw)==before['st_size'] and sha(raw)==ref['sha256'] and
             ('bytes' not in ref or ref['bytes']==len(raw)),'NATIVE_LEAF_FILE_BOOKEND_CHANGED')
        return bytes(raw)
    finally:os.close(fd)
def load(path,pin,name):
    raw=read_ref({'path':str(path),'sha256':pin},1024*1024,source=True)
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__);return module
def data_module():
    # Only its original duplicate-safe parser and mapped namespace reader are
    # reused. The historical 45-package/predeployment measure is never called.
    return load(ROOT/'source/support/business_data.py',DATA_SHA,'native_leaf_data_read_helpers')
def channel():
    return load(MAIN/'native_leaf_channel.py',CHANNEL_SHA,'native_leaf_private_comparison').ComparisonChannel()
def exact_epoch(boot,processes):
    binding={'boot_id':boot,'processes':processes}
    return {'schema':'pocket4-framework-epoch-v1','binding':binding,'sha256':sha(canonical(binding))}
def target_data(core):
    app=core['application'];data=core['data'];origin=core['main']['persistent_data']['original_copy_origin']
    rows={}
    for row in data['directories'][2:]:
        prefix=row['path'].removeprefix('/data/')
        rows[prefix]={'device':row['device'],'inode':row['inode'],'mount_id':row['mount_id'],
            'mode':row['mode'],'uid':row['host_uid'],'gid':row['host_gid']}
    return {'schema':'droidloom.native-leaf-target-working-data.v1',
        'scope':'actual_inspected_user_0_package_only',
        'package_uids':{app['package']:app['uid']},'directories':rows,
        'working_data_root':data['data_root'],'original_copy_origin':origin,
        'original_directory_identity_compared':False,'account_contents_read':False}

def validate_process_against_main(role,identity,held,core):
    key={'init':'init','zygote64':'zygote','system_server':'framework'}.get(role)
    if key:
        actual=core['main'][key]
        need(all(identity[name]==actual[name] for name in
             ('host_pid','parent_host_pid','start_ticks')) and
             node(held['pidfd'])==actual['pidfd'] and node(held['root'])==actual['root'] and
             node(held['exe'])==actual['executable'],'ACTUAL_PROCESS_DIFFERS_FROM_RUST_MAIN')
        values=core['main']['owner']['namespaces'] if role=='init' else (
            core['main']['framework_namespaces'] if role=='system_server' else None)
        if values is not None:
            for item in values:
                name='mnt' if item['name']=='mount' else item['name']
                need(node(held['namespaces'][name])=={'device':item['device'],'inode':item['inode']},
                     'ACTUAL_NAMESPACES_DIFFER_FROM_RUST_MAIN')
    elif role=='daemon':
        need(identity['host_pid']==core['peer']['pid'] and
             identity['start_ticks']==core['peer']['start_ticks'] and
             identity['uids']==[0]*4 and identity['executable']==PROGRAM and
             identity['cmdline']==[PROGRAM,'--socket','/run/droidloom/control.sock'],
             'ACTUAL_NORMAL_BROKER_DIFFERS_FROM_RUST_PEER')
    elif role=='presenter':
        need(identity['uids']==[1000]*4 and identity['executable']==PRESENTER and
             identity['cmdline']==[PRESENTER,'--production'],
             'ACTUAL_NORMAL_PRODUCTION_PRESENTER_REQUIRED')
    else:
        need(role=='surfaceflinger' and identity['executable']=='/system/bin/surfaceflinger' and
             identity['cmdline']==['/system/bin/surfaceflinger'] and
             identity['parent_host_pid']==core['main']['init']['host_pid'],
             'ACTUAL_CURRENT_SURFACEFLINGER_REQUIRED')

# Two fixed local status reads. They inherit no Main/channel descriptors and
# execute one held normal systemctl ELF; no runuser, PAM, shell or arbitrary
# command/UID is accepted. Source-controlled seccomp forbids fork/clone.
class FixedUnitReader:
    PROGRAM=Path('/usr/bin/systemctl')
    PROGRAM_BYTES=302112
    PROGRAM_SHA='639bce3ce5c06b605079ea56f74e3f08216ddffcfa76e11f62073aa775180082'
    FIELDS=('ActiveState','SubState','MainPID','ControlPID','ControlGroup',
            'InvocationID','FragmentPath','DropInPaths')
    MASK=(1<<6)|(1<<7)|(1<<19)
    _pending=None

    def __init__(self,live,deadline):
        import ctypes
        self.ctypes=ctypes;self.libc=ctypes.CDLL(None,use_errno=True)
        self.libc.syscall.restype=ctypes.c_long
        self.live=live;self.deadline=min(deadline,live.deadline)
        self.pid=os.getpid();self.fds=set();self.acquired=0;self.closed=0;self.attempts=0
        self.errors=[];self.records=[];self.parents=[]
        self.program=None;self.finished=False
        class Header(ctypes.Structure):
            _fields_=[('version',ctypes.c_uint32),('pid',ctypes.c_int)]
        class Cap(ctypes.Structure):
            _fields_=[('effective',ctypes.c_uint32),('permitted',ctypes.c_uint32),('inheritable',ctypes.c_uint32)]
        class Filter(ctypes.Structure):
            _fields_=[('code',ctypes.c_ushort),('jt',ctypes.c_ubyte),('jf',ctypes.c_ubyte),('k',ctypes.c_uint)]
        class Program(ctypes.Structure):
            _fields_=[('len',ctypes.c_ushort),('filter',ctypes.POINTER(Filter))]
        self.Header=Header;self.Cap=Cap;self.Filter=Filter;self.ProgramFilter=Program
        try:
            self._root()
            need(os.uname().machine=='x86_64' and ctypes.sizeof(ctypes.c_void_p)==8,
                 'FIXED_UNIT_READER_REQUIRES_NORMAL_X86_64_HOST')
            for path in (Path('/'),Path('/usr'),Path('/usr/bin')):
                fd=self._own(os.open(path,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC))
                pin=metadata(fd)
                need(stat.S_ISDIR(pin['st_mode']) and pin['st_uid']==pin['st_gid']==0
                     and pin['st_mode']&0o022==0,'PROTECTED_NORMAL_SYSTEMCTL_PARENT_REQUIRED')
                self.parents.append((path,fd,{k:pin[k] for k in META[:6]}))
            self.program=self._own(os.open(self.PROGRAM,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW|os.O_CLOEXEC))
            self.program_meta=metadata(self.program)
            p=self.program_meta
            need(stat.S_ISREG(p['st_mode']) and p['st_uid']==p['st_gid']==0 and p['st_nlink']==1 and
                 stat.S_IMODE(p['st_mode'])==0o755 and p['st_size']==self.PROGRAM_BYTES,
                 'FIXED_NORMAL_SYSTEMCTL_FILE_REQUIRED')
            self._program_guard()
        except BaseException:
            self.close();raise

    def _own(self,fd):
        need(fd>=0 and fd not in self.fds,'NEW_OWNED_UNIT_DESCRIPTOR_REQUIRED')
        self.fds.add(fd);self.acquired+=1;return fd
    def _close(self,fd):
        if fd is None:return
        need(fd in self.fds,'UNIT_DESCRIPTOR_ALREADY_CLOSED')
        self.attempts+=1
        try:os.close(fd);self.closed+=1;self.fds.remove(fd)
        except OSError as error:
            self.errors.append({'errno':error.errno,'stage':'descriptor_close'});raise
    def _caps(self):
        c=self.ctypes;header=self.Header(0x20080522,0);data=(self.Cap*2)()
        need(self.libc.syscall(125,c.byref(header),c.byref(data))==0,'UNIT_CAPGET_FAILED')
        return tuple(int(getattr(data[0],k))|(int(getattr(data[1],k))<<32)
                     for k in ('permitted','effective','inheritable'))
    def _root(self):
        c=self.ctypes
        need(os.getresuid()==(0,0,0) and os.getresgid()==(0,0,0) and
             self.libc.syscall(122,c.c_uint(0xffffffff))==0 and
             self.libc.syscall(123,c.c_uint(0xffffffff))==0 and
             self._caps()==(self.MASK,self.MASK,0) and self.libc.prctl(39,0,0,0,0)==1 and
             self.libc.prctl(27,0,0,0,0)==0,'EXACT_ROOT_THREE_CAP_UNIT_OWNER_REQUIRED')
    def _program_guard(self):
        need(not self.finished and self.pid==os.getpid() and FixedUnitReader._pending is None,
             'UNIT_READER_CHANGED_OR_HAS_UNRETIRED_CHILD')
        self._root()
        need(time.monotonic()<self.deadline,'ORIGINAL_UNIT_OBSERVATION_END_EXPIRED')
        for path,fd,pin in self.parents:
            named=path.lstat()
            need({k:metadata(fd)[k] for k in META[:6]}==pin==
                 {k:getattr(named,k) for k in META[:6]},'NORMAL_SYSTEMCTL_PARENT_CHANGED')
        need(metadata(self.program)==self.program_meta==
             {k:getattr(self.PROGRAM.lstat(),k) for k in META},'HELD_NORMAL_SYSTEMCTL_CHANGED')
        raw=os.pread(self.program,self.PROGRAM_BYTES+1,0)
        need(len(raw)==self.PROGRAM_BYTES and sha(raw)==self.PROGRAM_SHA and
             raw[:6]==b'\x7fELF\x02\x01' and raw[18:20]==b'\x3e\x00',
             'NORMAL_SYSTEMCTL_WHOLE_ELF_CHANGED')
        try:
            os.getxattr(self.program,'security.capability')
        except OSError as error:
            need(error.errno==61,'SYSTEMCTL_FILECAP_READ_FAILED')
        else:raise RuntimeError('NORMAL_SYSTEMCTL_CANNOT_HAVE_FILE_CAPABILITIES')
        need(metadata(self.program)==self.program_meta,'SYSTEMCTL_CHANGED_DURING_FULL_READ')

    def _signal(self,pidfd,number,uid):
        import threading
        need(number in (15,9) and uid in (0,1000) and
             FixedUnitReader._pending is not None and
             FixedUnitReader._pending['pidfd']==pidfd,'ONLY_HELD_OWNED_UNIT_CHILD_SIGNAL')
        self._root();errors=[]
        def worker():
            c=self.ctypes
            try:
                self._root()
                need(self.libc.syscall(186)!=self.pid,'SIGNAL_SCOPE_CANNOT_CHANGE_TGID_LEADER')
                try:
                    if uid==1000:
                        need(self.libc.syscall(117,c.c_uint(0xffffffff),c.c_uint(1000),
                             c.c_uint(0xffffffff))==0 and os.getresuid()==(0,1000,0)
                             and self._caps()==(self.MASK,0,0),'FIXED_UNIT_SIGNAL_EUID_SWITCH_FAILED')
                    result=self.libc.syscall(424,pidfd,number,c.c_void_p(),0)
                    if result!=0:
                        raise OSError(c.get_errno(),'owned unit PIDFD signal failed')
                finally:
                    need(self.libc.syscall(117,c.c_uint(0xffffffff),c.c_uint(0),
                         c.c_uint(0xffffffff))==0,'UNIT_SIGNAL_EUID_RESTORE_FAILED')
                    self._root()
            except BaseException as error:errors.append(error)
        thread=threading.Thread(target=worker,name='droidloom-unit-retirement')
        thread.start();thread.join();self._root()
        if errors:raise errors[0]

    def _child_exec(self,uid,parent,args,env,null,out,err,status,argv_array,env_array,filters,filter_program):
        # This is a new single-thread process. No libc process-wide credential
        # wrapper is used in a live multithread parent.
        import resource
        c=self.ctypes
        try:
            os.dup2(null,0);os.dup2(out,1);os.dup2(err,2)
            need(self.libc.syscall(116,0,c.c_void_p())==0,'UNIT_CHILD_GROUP_CLEAR_FAILED')
            need(self.libc.syscall(119,uid,uid,uid)==0,'UNIT_CHILD_FIXED_GID_FAILED')
            need(self.libc.syscall(117,uid,uid,uid)==0,'UNIT_CHILD_FIXED_UID_FAILED')
            header=self.Header(0x20080522,0);zero=(self.Cap*2)()
            need(self.libc.syscall(126,c.byref(header),c.byref(zero))==0,'UNIT_CHILD_CAP_CLEAR_FAILED')
            need(os.getresuid()==(uid,uid,uid) and os.getresgid()==(uid,uid,uid)
                 and os.getgroups()==[] and self._caps()==(0,0,0),'EXACT_UNPRIVILEGED_UNIT_CHILD_REQUIRED')
            # Set only after the credential switch, which clears PDEATHSIG.
            need(self.libc.prctl(1,9,0,0,0)==0 and os.getppid()==parent,
                 'ORIGINAL_UNIT_PARENT_DIED_BEFORE_EXEC')
            resource.setrlimit(resource.RLIMIT_CORE,(0,0))
            resource.setrlimit(resource.RLIMIT_AS,(256*1024*1024,256*1024*1024))
            resource.setrlimit(resource.RLIMIT_CPU,(1,2))
            resource.setrlimit(resource.RLIMIT_NOFILE,(4096,4096))
            need(self.libc.prctl(38,1,0,0,0)==0 and self.libc.prctl(39,0,0,0,0)==1,
                 'UNIT_CHILD_NO_NEW_PRIVILEGES_REQUIRED')
            # All non-stdio descriptors close at this one ELF exec. No Main,
            # control, source lease or private comparison channel is inherited.
            need(self.libc.syscall(436,3,c.c_uint(0xffffffff),4)==0,'UNIT_CHILD_CLOSE_RANGE_FAILED')
            need(self.libc.prctl(22,2,c.byref(filter_program),0,0)==0,
                 'UNIT_CHILD_SINGLE_PROCESS_FILTER_FAILED')
            self.libc.syscall(322,self.program,c.c_char_p(b''),argv_array,env_array,0x1000)
            raise OSError(c.get_errno(),'fixed held systemctl execveat failed')
        except BaseException as error:
            try:os.write(status,('UNIT_CHILD_EXEC_FAILED:'+type(error).__name__+':'+str(error))[:1024].encode())
            except BaseException:pass
            os._exit(127)

    def show(self,role):
        import select
        started=time.monotonic_ns()
        deadline_ns=min(int(self.deadline*10**9),int(self.live.deadline*10**9),started+3*10**9)
        end=deadline_ns/10**9
        self._program_guard()
        need(role in ('daemon','presenter') and len(self.records)<128,
             'ONLY_TWO_FIXED_NORMAL_UNIT_READS_WITHIN_BOUND')
        uid=0 if role=='daemon' else 1000
        unit=SYSTEM_UNIT if uid==0 else USER_UNIT
        args=[str(self.PROGRAM),'--no-pager','--no-ask-password']+(['--user'] if uid else [])
        args+=['show',unit,'--property='+','.join(self.FIELDS)]
        env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8',
             'SYSTEMD_PAGER':'','SYSTEMD_COLORS':'0','SYSTEMD_ASK_PASSWORD':'0'}
        if uid==1000:
            env.update(HOME='/home/alex',XDG_RUNTIME_DIR='/run/user/1000')
        else:env['HOME']='/root'
        c=self.ctypes
        argv_array=(c.c_char_p*(len(args)+1))(*(s.encode() for s in args),None)
        env_array=(c.c_char_p*(len(env)+1))(*(k.encode()+b'='+v.encode() for k,v in sorted(env.items())),None)
        # Architecture check, no x32, and no process/thread creation after exec.
        bpf=[(0x20,0,0,4),(0x15,1,0,0xc000003e),(0x06,0,0,0x80000000),
             (0x20,0,0,0),(0x35,0,1,0x40000000),(0x06,0,0,0x80000000)]
        for nr in (56,57,58,435,59):bpf.extend(((0x15,0,1,nr),(0x06,0,0,0x00050001)))
        bpf.append((0x06,0,0,0x7fff0000))
        filters=(self.Filter*len(bpf))(*(self.Filter(*r) for r in bpf))
        filter_program=self.ProgramFilter(len(bpf),filters)
        need(end-time.monotonic()>0.8,'ORIGINAL_UNIT_READ_CANNOT_COVER_RETIREMENT')
        work_end=end-0.6;owned=[];pid=None;pidfd=None;reaped=False;first=None
        output={'stdout':bytearray(),'stderr':bytearray(),'exec_error':bytearray()}
        record={'schema':'droidloom.native-host-unit-read.v1','role':role,'unit':unit,
            'argv':args,'program':{'path':str(self.PROGRAM),'bytes':self.PROGRAM_BYTES,'sha256':self.PROGRAM_SHA},
            'program_file':self.program_meta,'child_uid':uid,'child_gid':uid,'child_pre_exec_caps':0,
            'fork_clone_forbidden':True,'child_started':False,'child_reaped':False,
            'automatic_retry':False,'started_monotonic_ns':started,'deadline_monotonic_ns':deadline_ns}
        try:
            null=self._own(os.open('/dev/null',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC));owned.append(null)
            null_stat=os.fstat(null)
            need(stat.S_ISCHR(null_stat.st_mode) and os.major(null_stat.st_rdev)==1 and
                 os.minor(null_stat.st_rdev)==3,'NORMAL_NULL_DEVICE_REQUIRED')
            streams={}
            for name in output:
                read,write=os.pipe2(os.O_CLOEXEC);self._own(read);self._own(write);owned.extend((read,write))
                os.set_blocking(read,False);streams[name]=(read,write)
            pid=os.fork()
            if pid==0:
                self._child_exec(uid,self.pid,args,env,null,streams['stdout'][1],streams['stderr'][1],
                    streams['exec_error'][1],argv_array,env_array,filters,filter_program)
                os._exit(127)
            record['child_started']=True;record['pid']=pid
            FixedUnitReader._pending={'pid':pid,'pidfd':None,'owner':self}
            pidfd=self._own(os.pidfd_open(pid,0));owned.append(pidfd)
            FixedUnitReader._pending['pidfd']=pidfd
            record['pidfd']={k:metadata(pidfd)[k] for k in ('st_dev','st_ino')}
            for fd in [null]+[v[1] for v in streams.values()]:self._close(fd);owned.remove(fd)
            open_streams={v[0]:k for k,v in streams.items()}
            def exited():
                result=os.waitid(os.P_PIDFD,pidfd,os.WEXITED|os.WNOWAIT|os.WNOHANG)
                return result
            def drain():
                for fd,name in list(open_streams.items()):
                    while True:
                        try:block=os.read(fd,4096)
                        except BlockingIOError:break
                        if not block:open_streams.pop(fd);break
                        output[name].extend(block)
                        need(len(output[name])<=(16384 if name=='stdout' else 4096),
                             'FIXED_UNIT_OUTPUT_BOUND_EXCEEDED')
            while exited() is None:
                drain()
                if time.monotonic()>=work_end:raise TimeoutError('fixed unit read original work end')
                poll=select.poll();poll.register(pidfd,select.POLLIN)
                for fd in open_streams:poll.register(fd,select.POLLIN|select.POLLHUP|select.POLLERR)
                poll.poll(max(0,min(10,int((work_end-time.monotonic())*1000))))
            drain()
        except BaseException as error:first=error
        finally:
            if pid and pid>0 and pidfd is not None:
                try:
                    info=os.waitid(os.P_PIDFD,pidfd,os.WEXITED|os.WNOWAIT|os.WNOHANG)
                    if info is None:
                        try:self._signal(pidfd,15,uid)
                        except BaseException as error:first=first or error
                        grace=min(end,time.monotonic()+0.15)
                        while info is None and time.monotonic()<grace:
                            poll=select.poll();poll.register(pidfd,select.POLLIN);poll.poll(5)
                            info=os.waitid(os.P_PIDFD,pidfd,os.WEXITED|os.WNOWAIT|os.WNOHANG)
                    if info is None:
                        try:self._signal(pidfd,9,uid)
                        except BaseException as error:first=first or error
                    while info is None and time.monotonic()<end:
                        poll=select.poll();poll.register(pidfd,select.POLLIN);poll.poll(5)
                        info=os.waitid(os.P_PIDFD,pidfd,os.WEXITED|os.WNOWAIT|os.WNOHANG)
                    need(info is not None and info.si_pid==pid,'OWNED_UNIT_CHILD_RETIREMENT_UNKNOWN')
                    waited,status=os.waitpid(pid,0)
                    need(waited==pid,'UNIT_CHILD_REAP_IDENTITY_CHANGED')
                    reaped=True;FixedUnitReader._pending=None
                    record.update(child_reaped=True,waitid_code=info.si_code,waitid_status=info.si_status,
                                  wait_status=status,returncode=os.waitstatus_to_exitcode(status))
                    if 'drain' in locals():drain()
                except BaseException as error:first=first or error
            # If no verified retirement exists, retain this sole PIDFD/pipe
            # custody and block all subsequent normal queries. Parent death
            # also has a kernel PDEATHSIG backstop; it is not claimed as observed.
            if not pid or reaped:
                for fd in reversed(owned):
                    try:self._close(fd)
                    except BaseException as error:first=first or error
            record['retirement_within_deadline']=reaped and time.monotonic()<=end
            record['finished_monotonic_ns']=time.monotonic_ns()
            for name,raw in output.items():
                record[name]={'bytes':len(raw),'sha256':sha(raw),'hex':bytes(raw).hex()}
            self.records.append(record)
        if first is not None or not record['retirement_within_deadline'] or record.get('returncode')!=0 or output['stderr'] or output['exec_error']:
            error=RuntimeError('NORMAL_UNIT_READ_FAILED:'+json.dumps(record,sort_keys=True,separators=(',',':')))
            error.unit_observation=record;error.automatic_retry=False
            error.outcome_unknown=not reaped;error.action_attempted=False
            raise error from first
        self._program_guard()
        raw=bytes(output['stdout']).decode('utf-8','strict');fields={}
        for line in raw.splitlines():
            key,separator,value=line.partition('=')
            need(separator and key in self.FIELDS and key not in fields,'EXACT_UNIT_PROPERTIES_REQUIRED')
            fields[key]=value
        need(set(fields)==set(self.FIELDS) and fields['ActiveState']=='active' and fields['SubState']=='running'
             and fields['MainPID'].isdecimal() and int(fields['MainPID'])>1 and fields['ControlPID']=='0',
             'ACTUAL_RUNNING_NORMAL_UNIT_REQUIRED')
        need(time.monotonic()<=end,'ORIGINAL_FIXED_UNIT_READ_END_EXPIRED')
        return fields

    def close(self):
        if self.finished:return
        # Never discard unresolved child custody. Failure is retained in the
        # source-owned module and the normal enclosing invocation must fail.
        need(FixedUnitReader._pending is None,'UNRETIRED_UNIT_CHILD_BLOCKS_OBSERVATION_CLOSURE')
        for fd in reversed(sorted(self.fds)):self._close(fd)
        self.finished=True
    def summary(self):
        return {'acquired':self.acquired,'closed':self.closed,'close_attempts':self.attempts,
                'remaining':len(self.fds),'errors':list(self.errors)}


class Observation:
    def __init__(self,live,expected=None,seconds=120):
        self.live=live;self.core=live.core;self.expected=expected
        self.deadline=min(time.monotonic()+seconds,live.deadline)
        self.data=data_module()
        self.epoch=load(MAIN/'framework_epoch.py',EPOCH_SHA,'native_leaf_actual_epoch')
        self.reader=load(MAIN/'held_runtime.py',READER_SHA,'native_leaf_actual_root_reader')
        self.ancestry=load(MAIN/'cell_ancestry.py',ANCESTRY_SHA,'native_leaf_actual_fd_helpers')
        self.host=load(MAIN/'capture_main.py',CAPTURE_SHA,'native_leaf_existing_bounded_unit_reader')
        self.pool=self.ancestry.ManagedFDs();self.handles={};self.main_user_namespace=None
        self.rows={};self.android_environment=None;self.units=None;self.child_selection=None
        self.programs=None;self.unit_reader=None
    def check(self):
        need(FixedUnitReader._pending is None,'UNRETIRED_UNIT_CHILD_BLOCKS_FURTHER_OBSERVATION')
        need(time.monotonic()<self.deadline,'ORIGINAL_NATIVE_LEAF_OBSERVATION_DEADLINE')
    def _unit_rows(self):
        self.check();self.live.guard()
        if self.unit_reader is None:self.unit_reader=FixedUnitReader(self.live,self.deadline)
        rows={'daemon':self.unit_reader.show('daemon'),'presenter':self.unit_reader.show('presenter')}
        self.check();self.live.guard()
        need(int(rows['daemon']['MainPID'])==self.core['peer']['pid'] and
             rows['daemon']['ControlGroup']==CGROUP and
             re.fullmatch('[0-9a-f]{32}',rows['daemon']['InvocationID']) and
             re.fullmatch('[0-9a-f]{32}',rows['presenter']['InvocationID']) and
             rows['presenter']['ControlGroup'].startswith('/user.slice/user-1000.slice/') and
             rows['presenter']['ControlGroup'].endswith('/'+USER_UNIT),
             'ACTUAL_FIXED_NORMAL_SERVICE_INVOCATIONS_REQUIRED')
        return rows
    def _children(self,proc,pid):
        task=self.pool.own(os.open('task',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,
                                  dir_fd=proc),'init_tasks')
        try:
            names=os.listdir(task)
            need(0<len(names)<=256 and all(re.fullmatch('[1-9][0-9]{0,9}',v) for v in names),
                 'FIXED_MAIN_INIT_THREAD_BOUND')
            tids=sorted(map(int,names));need(pid in tids,'ACTUAL_MAIN_INIT_THREAD_REQUIRED')
            rows={};flat=[]
            for tid in tids:
                self.check()
                thread=self.pool.own(os.open(str(tid),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,
                                            dir_fd=task),'init_thread')
                try:
                    raw=self.ancestry.read_proc_leaf(self.pool,thread,'children',65536,self.check)
                    need(all(c in b'0123456789 \t\n' for c in raw),'ACTUAL_INIT_CHILD_LIST_REQUIRED')
                    values=[int(v) for v in raw.split()]
                    need(len(values)<=1024 and len(values)==len(set(values)) and
                         all(1<v<2**31 for v in values),'ACTUAL_INIT_CHILD_BOUND')
                    rows[str(tid)]=sorted(values);flat.extend(values)
                finally:self.pool.close(thread)
            need(len(flat)<=4096 and len(flat)==len(set(flat)) and
                 sorted(os.listdir(task))==sorted(names),'ACTUAL_INIT_CHILDREN_CHANGED')
            return {'thread_ids':tids,'per_thread':rows,'child_host_pids':sorted(flat)}
        finally:self.pool.close(task)
    def _surfaceflinger(self):
        init=self.core['main']['init']['host_pid']
        pidfd=self.pool.own(os.pidfd_open(init,0),'discovery_init_pidfd')
        proc=self.pool.own(os.open('/proc/'+str(init),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC),
                           'discovery_init_proc')
        try:
            need(node(pidfd)==self.core['main']['init']['pidfd'],'EXACT_RUST_INIT_PIDFD_REQUIRED')
            self.ancestry.require_pidfd_live(pidfd)
            first=self._children(proc,init);matches=[]
            for pid in first['child_host_pids']:
                self.check()
                child=self.pool.own(os.open('/proc/'+str(pid),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC),
                                    'init_child_proc')
                try:
                    raw=self.ancestry.read_proc_leaf(self.pool,child,'cmdline',65536,self.check)
                    if raw==b'/system/bin/surfaceflinger\0':matches.append(pid)
                finally:self.pool.close(child)
            second=self._children(proc,init)
            self.ancestry.require_pidfd_live(pidfd);self.live.guard()
            need(first==second and len(matches)==1,'ONE_STABLE_SAME_MAIN_SURFACEFLINGER_REQUIRED')
            self.child_selection={'method':'actual_held_init_all_thread_direct_children',
                                  'selected_host_pid':matches[0],'initial_table':second}
            return matches[0]
        finally:self.pool.close(proc);self.pool.close(pidfd)
    def identities(self):
        self.check();self.live.guard()
        actual=self.epoch.capture_processes({name:row['host_pid'] for name,row in self.rows.items()})
        need(actual['binding']=={'boot_id':self.core['main']['epoch']['boot_id'],'processes':self.rows},
             'ACTUAL_NORMAL_PROCESS_GENERATION_CHANGED')
        if self.handles:
            for name,row in self.rows.items():
                if name in self.handles:
                    validate_process_against_main(name,row,self.handles[name],self.core)
        self.check();return actual['binding']['processes']
    def acquire(self):
        self.live.guard();self.units=self._unit_rows()
        if self.expected is None:
            sf=self._surfaceflinger()
        else:
            self.live.require_core(self.expected['native_owner'])
            need(self.units==self.expected['systemd_units'],'NORMAL_SERVICE_INVOCATION_CHANGED')
            sf=self.expected['main_epoch']['binding']['processes']['surfaceflinger']['host_pid']
            self.child_selection=self.expected['surfaceflinger_selection']
        chosen={'daemon':self.core['peer']['pid'],'presenter':int(self.units['presenter']['MainPID']),
                'init':self.core['main']['init']['host_pid'],'zygote64':self.core['main']['zygote']['host_pid'],
                'system_server':self.core['main']['framework']['host_pid'],'surfaceflinger':sf}
        need(len(set(chosen.values()))==6,'SIX_DISTINCT_ACTUAL_RUNTIME_PROCESSES_REQUIRED')
        value=self.epoch.capture_processes(chosen)
        need(value['binding']['boot_id']==self.core['main']['epoch']['boot_id'],'SAME_ACTUAL_BOOT_REQUIRED')
        self.rows=value['binding']['processes']
        if self.expected is not None:
            need(self.rows==self.expected['processes'],'ACTUAL_NORMAL_PROCESS_SET_CHANGED')
        for name,row in self.rows.items():
            pid=row['host_pid'];self.check()
            pidfd=self.pool.own(os.pidfd_open(pid,0),name+'_pidfd')
            proc=self.pool.own(os.open('/proc/'+str(pid),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC),
                               name+'_proc')
            self.ancestry.require_pidfd_live(pidfd)
            root=self.pool.own(os.open('root',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC,dir_fd=proc),name+'_root')
            exe=self.pool.own(os.open('exe',os.O_RDONLY|os.O_CLOEXEC,dir_fd=proc),name+'_exe')
            ns={k:self.pool.own(os.open('ns/'+k,os.O_RDONLY|os.O_CLOEXEC,dir_fd=proc),name+'_ns_'+k) for k in NS}
            self.handles[name]={'pidfd':pidfd,'proc':proc,'root':root,'exe':exe,'namespaces':ns}
            validate_process_against_main(name,row,self.handles[name],self.core)
        self.identities()
        owner=self.core['main']['persistent_data']['user_namespace']
        owner={**owner,'link':'user:['+str(owner['inode'])+']'}
        host=self.pool.own(os.open('/proc/self/ns/user',os.O_RDONLY|os.O_CLOEXEC),'host_user_namespace')
        self.main_user_namespace=self.data.userns_module().HeldMainUserNamespace(
            self.rows['init'],self.handles['init'],owner,host,self.core['main']['epoch']['boot_id'],self.identities)
        mapping=self.main_user_namespace.guard()
        for name in ('uid_map','gid_map'):
            need([{'inside':mapping[name]['inside'],'outside':mapping[name]['outside'],
                   'count':mapping[name]['count']}]==self.core['data'][name],
                 'PYTHON_AND_RUST_ACTUAL_ID_MAPS_DIFFER')
        if self.expected is not None:
            need(mapping==self.expected['main_user_namespace'],'ACTUAL_MAPPED_USER_NAMESPACE_CHANGED')
        self.programs=self.program_artifacts(None if self.expected is None else self.expected['installed_programs'])
        self.identities()
    def artifact(self,fd,limit=268435456):
        before=metadata(fd)
        need(stat.S_ISREG(before['st_mode']) and before['st_nlink']==1 and
             0<before['st_size']<=limit,'CURRENT_ARTIFACT_BOUND')
        os.lseek(fd,0,os.SEEK_SET);h=hashlib.sha256();count=0
        while True:
            self.check();part=os.read(fd,min(131072,before['st_size']+1-count))
            if not part:break
            count+=len(part);need(count<=before['st_size'],'CURRENT_ARTIFACT_GREW');h.update(part)
        need(count==before['st_size'] and metadata(fd)==before,'CURRENT_ARTIFACT_CHANGED')
        return {'bytes':count,'sha256':h.hexdigest(),'file':before}
    def guest(self,role,path,flags=os.O_RDONLY):
        self.check()
        return self.pool.own(self.reader.open_in_root(self.handles[role]['root'],path,flags),'guest_artifact')
    def program_artifacts(self,expected):
        # The source-owned Rust release reader must supply the selected normal
        # host program commitments. Root ownership alone is not that proof.
        contract=getattr(self.live,'normal_host_release',None)
        need(type(contract) is dict and contract.get('schema')=='droidloom.normal-host-release.v1' and
             set(contract)=={'schema','manager','presenter'} and
             contract['manager']['path']==PROGRAM and contract['presenter']['path']==PRESENTER,
             'ACTUAL_SELECTED_NORMAL_HOST_PROGRAMS_REQUIRED')
        output={}
        for role,path in (('daemon',PROGRAM),('presenter',PRESENTER)):
            root_parents(Path(path))
            named=self.pool.own(os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW),'named_normal_program')
            try:
                held=self.handles[role]['exe'];info=metadata(named)
                need(metadata(held)==info and info['st_uid']==info['st_gid']==0 and
                     stat.S_IMODE(info['st_mode'])==0o755 and info['st_nlink']==1,
                     'ACTUAL_RUNNING_NORMAL_PROGRAM_BACKING_REQUIRED')
                if expected is None:actual=self.artifact(held)
                else:
                    actual=expected[path]
                    need(info==actual['file'],'ACTUAL_NORMAL_PROGRAM_CHANGED')
                wanted=contract['manager' if role=='daemon' else 'presenter']
                need(actual['bytes']==wanted['bytes'] and actual['sha256']==wanted['sha256'],
                     'ACTUAL_NORMAL_PROGRAM_DIFFERS_FROM_SELECTED_RELEASE')
                if role=='daemon':
                    need(actual['bytes']==self.core['peer']['executable_bytes'] and
                         actual['sha256']==self.core['peer']['executable_sha256'],
                         'OBSERVED_NORMAL_PROGRAM_DIFFERS_FROM_AUTHENTICATED_PEER')
                need(metadata(named)==info==metadata(held),'NORMAL_PROGRAM_BOOKEND_CHANGED')
                output[path]=actual
            finally:self.pool.close(named)
        self.live.guard();return output
    def observe(self):
        value={'roles':self.identities(),'roots':{},'namespaces':{},'executables':{},
            'host_user_namespace':os.readlink('/proc/self/ns/user'),'limits':{},
            'main_user_namespace':self.main_user_namespace.guard(),'role_user_namespaces':{}}
        for role,h in self.handles.items():
            self.check();self.ancestry.require_pidfd_live(h['pidfd'])
            for leaf,flags,label in (('root',os.O_PATH|os.O_DIRECTORY,'roots'),('exe',os.O_RDONLY,'executables')):
                fd=self.pool.own(os.open(leaf,flags|os.O_CLOEXEC,dir_fd=h['proc']),'reopened_'+leaf)
                try:
                    need(node(fd)==node(h['root' if leaf=='root' else 'exe']),'HELD_ROLE_BACKING_CHANGED')
                    value[label][role]=node(fd) if leaf=='root' else metadata(fd)
                    if leaf=='exe':need(metadata(fd)==metadata(h['exe']),'HELD_EXECUTABLE_METADATA_CHANGED')
                finally:self.pool.close(fd)
            value['namespaces'][role]={}
            for name,held in h['namespaces'].items():
                link=os.readlink('ns/'+name,dir_fd=h['proc'])
                fd=self.pool.own(os.open('ns/'+name,os.O_RDONLY|os.O_CLOEXEC,dir_fd=h['proc']),'reopened_namespace')
                try:
                    actual=node(fd)
                    need(actual==node(held) and link==name+':['+str(actual['inode'])+']','HELD_NAMESPACE_CHANGED')
                    value['namespaces'][role][name]={'link':link,**actual}
                finally:self.pool.close(fd)
            fact=self.main_user_namespace.observe_role(h,self.rows[role],role)
            need(fact['user_namespace']==value['namespaces'][role]['user'],'ACTUAL_ROLE_USER_NAMESPACE_CHANGED')
            value['role_user_namespaces'][role]=fact
        for name in LIMITS:
            fd=self.pool.own(os.open('/sys/fs/cgroup'+CGROUP+'/'+name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC),
                               'normal_runtime_limit')
            try:value['limits'][name]=self.reader.read_fd(fd,8192,self.deadline).decode('ascii').strip()
            finally:self.pool.close(fd)
        need(value['limits']==LIMITS,'NORMAL_RUNTIME_LIMITS_CHANGED')
        need(self.rows['daemon']['cgroup'] in (['0::'+CGROUP],['0::'+CGROUP+'/broker']),
             'NORMAL_BROKER_CGROUP_CHANGED')
        for role in ANDROID:
            rows=[x[3:] for x in self.rows[role]['cgroup'] if x.startswith('0::')]
            need(len(rows)==1 and (rows[0]+'/'==PAYLOAD_CGROUP or rows[0].startswith(PAYLOAD_CGROUP)),
                 'ACTUAL_ANDROID_PROCESS_LEFT_NORMAL_PAYLOAD')
            need(value['roots'][role]==value['roots']['init'],'ACTUAL_ANDROID_ROOT_BACKING_DIFFERS')
        self.identities();self.live.guard()
        return value
    def classpaths(self,expected=None):
        raw=self.ancestry.read_proc_leaf(self.pool,self.handles['zygote64']['proc'],'environ',
                                        self.reader.ENV_LIMIT,self.check)
        values=self.reader.selected_classpaths(raw)
        self.android_environment=self.data.userns_module().android_environment(raw);del raw
        if self.expected is not None:
            need(self.android_environment==self.expected['android_env'],'CURRENT_ANDROID_ENVIRONMENT_CHANGED')
        paths=list(dict.fromkeys(p for k in self.reader.REQUIRED_CLASSPATHS for p in values[k].split(':')))
        need(0<len(paths)<=self.reader.PATH_COUNT_LIMIT,'CLASSPATH_PATH_BOUND')
        files=[];total=0
        if expected is not None:need(values==expected['values'] and len(paths)==len(expected['files']),
                                    'COMPLETE_CLASSPATH_SET_CHANGED')
        for index,path in enumerate(paths):
            left=self.guest('init',path);right=None
            try:
                right=self.guest('zygote64',path);a,b=metadata(left),metadata(right)
                need(a==b,'TWO_ACTUAL_CLASSPATH_ROOT_VIEWS_DIFFER')
                if expected is None:proof=self.artifact(left,self.reader.FILE_LIMIT)
                else:
                    old=expected['files'][index]
                    need(path==old['path'] and a==old['init_view'] and b==old['zygote_view'],
                         'CLASSPATH_BACKING_CHANGED')
                    proof={'sha256':old['sha256'],'bytes':old['bytes']}
                need(metadata(left)==a and metadata(right)==b,'CLASSPATH_READ_BOOKEND_CHANGED')
                files.append({'path':path,'sha256':proof['sha256'],'bytes':proof['bytes'],
                              'init_view':a,'zygote_view':b})
                total+=proof['bytes'];need(total<=self.reader.TOTAL_FILE_LIMIT,'CLASSPATH_TOTAL_BOUND')
            finally:
                if right is not None:self.pool.close(right)
                self.pool.close(left)
        self.live.guard();return {'values':values,'files':files,'total_bytes':total}
    def engine_file(self,expected=None):
        fd=self.guest('init',ENGINE)
        try:
            if expected is None:return self.artifact(fd)
            need(metadata(fd)==expected['file'],'ACTUAL_ENGINE_FILE_BACKING_CHANGED')
            return expected
        finally:self.pool.close(fd)
    def data_proof(self):
        self.live.guard();return target_data(self.core)
    def runtime(self,observation,classpath,artifacts):
        processes={name:self.rows[name] for name in ANDROID}
        epoch=exact_epoch(self.core['main']['epoch']['boot_id'],processes)
        return {'schema':RUNTIME_SCHEMA,'native_owner':self.core,
            'main_epoch':epoch,'processes':self.rows,'host_processes':{k:self.rows[k] for k in ('daemon','presenter')},
            'init_host_pid':self.rows['init']['host_pid'],'android_env':self.android_environment,
            'main_user_namespace':self.main_user_namespace.guard(),'systemd_units':self.units,
            'systemd_unit_observations':copy.deepcopy(self.unit_reader.records),
            'surfaceflinger_selection':self.child_selection,'installed_programs':self.programs,
            'normal_host_release':self.live.normal_host_release,
            'observation':observation,'classpath':classpath,'artifacts':artifacts,
            'daemon_status':self.native_status(),'data_continuity':self.data_proof(),
            'saved_document_can_create_authority':False,'business_acceptance_evaluated':False}
    def native_status(self):
        self.live.guard()
        return {'ok':True,'state':'running','host_pid':self.core['peer']['pid'],
            'runtime_epoch':self.core['main']['epoch'],'image_custody':{'owner':self.core['main']['owner']},
            'custody_comparison_only':True,'fresh_full_main_rpc':False,
            'native_ready_permit_issued':False,'outcome_unknown':False}
    def guard(self,runtime):
        self.check();self.live.require_core(runtime['native_owner']);self.identities()
        need(self._unit_rows()==runtime['systemd_units'],'ACTUAL_NORMAL_UNIT_INVOCATION_CHANGED')
        need(self.observe()==runtime['observation'] and
             self.classpaths(runtime['classpath'])==runtime['classpath'] and
             self.engine_file(runtime['artifacts']['engine'])==runtime['artifacts']['engine'] and
             self.data_proof()==runtime['data_continuity'] and
             self.program_artifacts(runtime['installed_programs'])==runtime['installed_programs'],
             'ACTUAL_RUNTIME_COMPARISON_CHANGED')
        self.identities();self.live.guard()
    def close(self):
        mapping=None;primary=None;unit_files=None
        try:
            if self.main_user_namespace is not None:mapping=self.main_user_namespace.close()
        except BaseException as error:primary=error
        finally:
            try:
                if self.unit_reader is not None:
                    self.unit_reader.close();unit_files=self.unit_reader.summary()
            except BaseException as error:
                if primary is None:primary=error
                else:primary.add_note('NORMAL_UNIT_CUSTODY_CLOSE_FAILED:'+type(error).__name__)
            finally:self.pool.close_all()
        self.pool.require_clean()
        if primary is not None:raise primary
        result=self.pool.summary()
        if unit_files is not None:
            need(unit_files['remaining']==0 and not unit_files['errors'] and
                 unit_files['acquired']==unit_files['closed']==unit_files['close_attempts'],
                 'ACTUAL_NORMAL_UNIT_FDS_UNCLOSED')
            for key in ('acquired','closed','close_attempts'):result[key]+=unit_files[key]
        if mapping is not None:
            need(mapping['remaining']==0 and not mapping['errors'] and
                 mapping['acquired']==mapping['closed']==mapping['close_attempts'],
                 'ACTUAL_MAPPED_NAMESPACE_FDS_UNCLOSED')
            for key in ('acquired','closed','close_attempts'):result[key]+=mapping[key]
        return result

def validate_unit_observations(runtime):
    """Compare complete normal receipts; a saved receipt grants no authority."""
    rows=runtime.get('systemd_unit_observations');units=runtime.get('systemd_units')
    need(type(rows) is list and 2<=len(rows)<=128 and len(rows)%2==0 and
         type(units) is dict and set(units)=={'daemon','presenter'},
         'COMPLETE_TWO_ROLE_UNIT_OBSERVATIONS_REQUIRED')
    keys={'schema','role','unit','argv','program','program_file','child_uid','child_gid',
          'child_pre_exec_caps','fork_clone_forbidden','child_started','child_reaped',
          'automatic_retry','started_monotonic_ns','deadline_monotonic_ns','pid','pidfd',
          'waitid_code','waitid_status','wait_status','returncode','retirement_within_deadline',
          'finished_monotonic_ns','stdout','stderr','exec_error'}
    program=None;previous=0
    for index,row in enumerate(rows):
        role=('daemon','presenter')[index%2];uid=0 if role=='daemon' else 1000
        unit=SYSTEM_UNIT if uid==0 else USER_UNIT
        args=[str(FixedUnitReader.PROGRAM),'--no-pager','--no-ask-password']+(['--user'] if uid else [])
        args+=['show',unit,'--property='+','.join(FixedUnitReader.FIELDS)]
        need(type(row) is dict and set(row)==keys and
             row['schema']=='droidloom.native-host-unit-read.v1' and row['role']==role and
             row['unit']==unit and row['argv']==args and
             row['program']=={'path':str(FixedUnitReader.PROGRAM),'bytes':FixedUnitReader.PROGRAM_BYTES,
                              'sha256':FixedUnitReader.PROGRAM_SHA} and
             row['child_uid']==uid and row['child_gid']==uid and row['child_pre_exec_caps']==0 and
             row['fork_clone_forbidden'] is True and row['child_started'] is True and
             row['child_reaped'] is True and row['retirement_within_deadline'] is True and
             row['automatic_retry'] is False and
             all(type(row[k]) is int and row[k]==0 for k in
                 ('waitid_status','wait_status','returncode')) and row['waitid_code']==1,
             'EXACT_RETIRED_FIXED_NORMAL_UNIT_QUERY_REQUIRED')
        for key in ('started_monotonic_ns','finished_monotonic_ns','deadline_monotonic_ns','pid'):
            need(type(row[key]) is int and row[key]>0,'ACTUAL_UNIT_RECEIPT_INTEGER_REQUIRED')
        start=row['started_monotonic_ns'];finish=row['finished_monotonic_ns'];end=row['deadline_monotonic_ns']
        need(previous<=start<=finish<=end and end-start<=3*10**9 and row['pid']>1,
             'ORIGINAL_UNIT_QUERY_WINDOW_OR_ORDER_CHANGED')
        previous=finish
        handle=row['pidfd']
        need(type(handle) is dict and set(handle)=={'st_dev','st_ino'} and
             all(type(v) is int and v>0 for v in handle.values()),'ACTUAL_UNIT_PIDFD_REQUIRED')
        pin=row['program_file']
        need(type(pin) is dict and set(pin)==set(META) and
             all(type(pin[k]) is int and pin[k]>=0 for k in META) and
             pin['st_dev']>0 and pin['st_ino']>0 and pin['st_mode']==0o100755 and
             pin['st_uid']==pin['st_gid']==0 and pin['st_nlink']==1 and
             pin['st_size']==FixedUnitReader.PROGRAM_BYTES and
             (program is None or pin==program),'SAME_HELD_NORMAL_SYSTEMCTL_FILE_REQUIRED')
        program=pin;streams={}
        for name in ('stdout','stderr','exec_error'):
            body=row[name]
            need(type(body) is dict and set(body)=={'bytes','sha256','hex'} and
                 type(body['bytes']) is int and 0<=body['bytes']<=(16384 if name=='stdout' else 4096) and
                 type(body['hex']) is str and re.fullmatch('[0-9a-f]*',body['hex']) is not None,
                 'COMPLETE_FIXED_UNIT_STREAM_REQUIRED')
            raw=bytes.fromhex(body['hex'])
            need(len(raw)==body['bytes'] and sha(raw)==body['sha256'],
                 'FIXED_UNIT_STREAM_WHOLE_BYTES_DIFFER')
            streams[name]=raw
        need(streams['stderr']==streams['exec_error']==b'' and streams['stdout'],
             'NORMAL_UNIT_READ_MUST_FINISH_WITH_EMPTY_ERRORS')
        fields={}
        for line in streams['stdout'].decode('utf-8','strict').splitlines():
            key,separator,value=line.partition('=')
            need(separator and key in FixedUnitReader.FIELDS and key not in fields,
                 'EXACT_OBSERVED_UNIT_PROPERTIES_REQUIRED')
            fields[key]=value
        need(set(fields)==set(FixedUnitReader.FIELDS) and fields==units[role] and
             fields['ActiveState']=='active' and fields['SubState']=='running' and
             fields['MainPID'].isdecimal() and int(fields['MainPID'])>1 and
             fields['ControlPID']=='0','RECEIPT_AND_ACTUAL_NORMAL_UNIT_FIELDS_DIFFER')

def validate_document(value,live):
    need(type(value) is dict and set(value)=={'schema','native_owner','runtime_observation','framework_epoch',
        'observation','classpath','artifacts','data_continuity','user_zero_package_inventory','sampling','observation_fds',
        'captured_unix_ns','comparison_only','account_contents_read','whole_app_business_accepted',
        'production_ready'} and value['schema']==SCHEMA and value['comparison_only'] is True and
        value['account_contents_read'] is False and value['whole_app_business_accepted'] is False and
        value['production_ready'] is False,'EXACT_CURRENT_KERNEL_FIRST_BASELINE_REQUIRED')
    live.require_core(value['native_owner'])
    live.validate_inventory_comparison(value['user_zero_package_inventory'])
    runtime=value['runtime_observation']
    validate_unit_observations(runtime)
    need(runtime['schema']==RUNTIME_SCHEMA and runtime['native_owner']==value['native_owner'] and
        runtime['main_epoch']==value['framework_epoch'] and
        value['framework_epoch']==exact_epoch(value['native_owner']['main']['epoch']['boot_id'],
            {k:runtime['processes'][k] for k in ANDROID}) and
        all(value[k]==runtime[k] for k in ('observation','classpath','artifacts','data_continuity')) and
        runtime['normal_host_release']==live.normal_host_release and
        runtime['saved_document_can_create_authority'] is False and
        runtime['business_acceptance_evaluated'] is False,
        'CURRENT_NORMAL_OBSERVATION_COMPONENTS_DIFFER')
    need(value['data_continuity']==target_data(value['native_owner']),'EXACT_TARGET_ONLY_DATA_COMPARISON_REQUIRED')
    sampling=value['sampling']
    need(sampling['double_observation_pairs']==3 and sampling['pairs_equal'] is True and
        10*10**9<=sampling['finished_monotonic_ns']-sampling['started_monotonic_ns']<=120*10**9,
        'ACTUAL_BOUNDED_REPEATED_RUNTIME_OBSERVATION_REQUIRED')
    closed=value['observation_fds']
    need(closed['acquired']>0 and closed['acquired']==closed['closed']==closed['close_attempts'] and
         closed['remaining']==0 and closed['errors']==[],'ACTUAL_OBSERVATION_FD_RETIREMENT_REQUIRED')
    return runtime

class BusinessBaseline:
    def __init__(self,baseline_ref,qualification_ref):
        self.data=data_module();self.live=channel()
        self.baseline_ref=baseline_ref;self.qualification_ref=qualification_ref
        self.value=parse(read_ref(baseline_ref));self.qualification=parse(read_ref(qualification_ref,262144))
        runtime=validate_document(self.value,self.live);q=self.qualification
        need(set(q)=={'schema','baseline','normal_source_recipe','core_sha256','main_epoch_sha256','user_zero_package_inventory_sha256',
            'actual_main_and_target_metadata_observed','working_copy_lineage_bound',
            'working_target_directory_identity_preserved','fixed_main_readonly_entry_observed',
            'comparison_only','account_contents_read','business_actions_admitted',
            'whole_app_business_accepted','production_ready','observation_fds'} and
            q['schema']==QUAL_SCHEMA and q['baseline']==baseline_ref and
            q['normal_source_recipe']==self.live.normal_source_recipe and
            q['core_sha256']==sha(canonical(self.live.core)) and
            q['user_zero_package_inventory_sha256']==sha(canonical(self.value['user_zero_package_inventory'])) and
            q['main_epoch_sha256']==self.value['framework_epoch']['sha256'] and
            q['actual_main_and_target_metadata_observed'] is True and
            q['working_copy_lineage_bound'] is True and
            q['working_target_directory_identity_preserved'] is True and
            q['fixed_main_readonly_entry_observed'] is True and q['comparison_only'] is True and
            q['account_contents_read'] is False and q['business_actions_admitted'] is False and
            q['whole_app_business_accepted'] is False and q['production_ready'] is False and
            q['observation_fds']==self.value['observation_fds'],
            'NORMAL_CURRENT_COMPARISON_QUALIFICATION_REQUIRED')
        self.docs={'runtime_observation':runtime}
        self._current_native_discovery=None
        helper=load(MAIN/'helper_contract.py',HELPER_SHA,'native_leaf_current_helper_contract')
        helper.verify_main_receipt(runtime)

    def package_uid_preimage(self):
        need(self.live.core['application']['package']=='com.ihg.apps.android',
             'FIXED_IHG_PACKAGE_INVENTORY_REQUIRED')
        return self.live.validate_inventory_comparison(self.value['user_zero_package_inventory'])
    def require_preinstall_inventory(self):
        before=self.package_uid_preimage();self.live.guard()
        need('org.droidloom.qa.ihg.finalmain.r1' not in before and
             self.live.user_zero_records==before,
             'COMPLETE_ACTUAL_PREINSTALL_TABLE_AND_HELPER_ABSENCE_REQUIRED')
        return dict(before)
    def require_installed_helper_inventory(self,helper_uid):
        before=self.package_uid_preimage();self.live.guard()
        name='org.droidloom.qa.ihg.finalmain.r1'
        need(name not in before and type(helper_uid) is int and 10000<=helper_uid<100000 and
             helper_uid not in before.values(),'NEW_HELPER_CANNOT_SHARE_ANY_PRESERVED_UID')
        expected=dict(before);expected[name]=helper_uid
        need(self.live.user_zero_records==expected,
             'ONLY_THE_ACTUAL_FIXED_HELPER_MAY_BE_ADDED_TO_USER0')
        return {'before_records_sha256':self.value['user_zero_package_inventory']['records_sha256'],
                'current_records_sha256':self.live.user_zero_package_inventory['records_sha256'],
                'only_added_package':name,'helper_uid':helper_uid}

    @property
    def protected_pids(self):
        return tuple(row['host_pid'] for row in self.value['observation']['roles'].values())
    def discover(self):
        self.guard()
        need(self._current_native_discovery is not None,'FRESH_NORMAL_RUNTIME_COMPARISON_REQUIRED')
        pid,env,status=self._current_native_discovery
        return pid,dict(env),dict(status)
    def guard(self,*,action_attempted=False):
        observer=None;primary=None;self._current_native_discovery=None
        try:
            read_ref(self.baseline_ref);read_ref(self.qualification_ref)
            runtime=validate_document(self.value,self.live)
            observer=Observation(self.live,runtime,seconds=15)
            observer.acquire();observer.guard(runtime)
            self._current_native_discovery=(runtime['init_host_pid'],
                dict(observer.android_environment),observer.native_status())
        except BaseException as error:
            primary=error;error.action_attempted=action_attempted
            error.outcome_unknown=action_attempted;error.automatic_retry=False
            raise
        finally:
            try:closed=observer.close() if observer is not None else None
            except BaseException as error:
                if primary is None:
                    error.action_attempted=action_attempted
                    error.outcome_unknown=action_attempted;error.automatic_retry=False;raise
                primary.add_note('NORMAL_BASELINE_HELD_FD_CLOSE_FAILED:'+type(error).__name__)
        return {'schema':'droidloom.native-leaf-business-main-guard.v1',
            'main_epoch_sha256':self.value['framework_epoch']['sha256'],
            'business_baseline_sha256':self.baseline_ref['sha256'],
            'business_qualification_sha256':self.qualification_ref['sha256'],
            'actual_identity_roots_executables_namespaces_checked':True,
            'original_working_lineage_bound':True,'current_target_directories_preserved':True,
            'local_rust_owner_check':True,'fresh_full_main_rpc':False,'observation_fds':closed,
            'systemd_unit_observations':copy.deepcopy(observer.unit_reader.records),
            'Binder_task_cleanup_verified':False,'Binder_UID_cleanup_verified':False,
            'whole_app_business_accepted':False}

def collect(output_directory):
    """Internal comparison collector, invoked only by the source-owned Rust CLI."""
    need(os.getuid()==os.geteuid()==0,'NORMAL_ROOT_OBSERVER_REQUIRED')
    output=Path(output_directory);root_parents(output/'OBSERVED.json',private=True)
    need(output.is_relative_to(QUALIFICATION) and output.is_dir() and
         stat.S_IMODE(output.lstat().st_mode)==0o700 and not (output/'OBSERVED.json').exists(),
         'FRESH_PRIVATE_NORMAL_CAPTURE_DIRECTORY_REQUIRED')
    live=channel();observer=None;primary=None;closed=None
    commands=load(ROOT/'source/support/business_commands.py',COMMANDS_SHA,'normal_current_readonly_commands')
    helper=load(MAIN/'helper_contract.py',HELPER_SHA,'normal_current_readonly_contract')
    entry=load(MAIN/'main_readonly_entry.py',READONLY_SHA,'normal_current_readonly_entry')
    try:
        observer=Observation(live,seconds=240);observer.acquire()
        started=time.monotonic_ns();pairs=[];first=observer.observe()
        classpath=observer.classpaths()
        artifacts={role:observer.artifact(observer.handles[role]['exe']) for role in ROLES}
        artifacts['engine']=observer.engine_file()
        for index in range(3):
            left=observer.observe();right=observer.observe()
            need(left==right==first,'ACTUAL_RUNTIME_CHANGED_DURING_SAMPLING')
            need(observer.classpaths(classpath)==classpath,'ACTUAL_CLASSPATH_CHANGED_DURING_SAMPLING')
            pairs.append({'before':left,'after':right})
            if index<2:
                end=time.monotonic()+5
                while time.monotonic()<end:
                    observer.check();live.guard();time.sleep(max(0,min(0.1,end-time.monotonic())))
        finished=time.monotonic_ns()
        runtime=observer.runtime(first,classpath,artifacts)
        runtime['capture_output_path']=str(output/'BASELINE.json')
        runtime['collector_parent_pid']=os.getppid()
        runtime['normal_live_comparison_before']={'finished_monotonic_ns':finished,
            'source':'actual_rust_opaque_main_and_pm_with_local_comparison_channel',
            'fresh_full_main_rpc_from_python':False}
        def guard():
            observer.guard(runtime)
            return helper.main_binding(runtime)
        ref=entry.capture(runtime,observer.main_user_namespace,observer.reader,commands,helper,guard,
                          output/'main-readonly-entry',live=live)
        runtime['main_readonly_entry']=ref
        runtime['normal_live_comparison_after']={'started_monotonic_ns':time.monotonic_ns(),
            'source':'same_live_rust_owner_local_check','fresh_full_main_rpc_from_python':False}
        guard();runtime['captured_unix_ns']=time.time_ns()
        helper.verify_main_receipt(runtime)
        runtime['systemd_unit_observations']=copy.deepcopy(observer.unit_reader.records)
        validate_unit_observations(runtime)
        value={'schema':SCHEMA,'native_owner':live.core,'runtime_observation':runtime,
            'framework_epoch':runtime['main_epoch'],'observation':first,'classpath':classpath,
            'artifacts':artifacts,'data_continuity':runtime['data_continuity'],
            'user_zero_package_inventory':live.user_zero_package_inventory,
            'sampling':{'double_observation_pairs':3,'pairs_equal':True,
                'started_monotonic_ns':started,'finished_monotonic_ns':finished},
            'captured_unix_ns':time.time_ns(),'comparison_only':True,'account_contents_read':False,
            'whole_app_business_accepted':False,'production_ready':False}
    except BaseException as error:primary=error;raise
    finally:
        try:closed=observer.close() if observer is not None else None
        except BaseException as error:
            if primary is None:raise
            primary.add_note('NORMAL_CAPTURE_HELD_FD_CLOSE_FAILED:'+type(error).__name__)
    value['observation_fds']=closed
    validate_document(value,live);live.guard()
    result=commands.write_new(output/'OBSERVED.json',value)
    print(json.dumps({'schema':'droidloom.native-leaf-observer-output.v1','observation':result,
                      'comparison_only':True,'whole_app_business_accepted':False},sort_keys=True))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--collect',action='store_true',required=True)
    parser.add_argument('--output-directory',required=True)
    args=parser.parse_args();collect(args.output_directory)
if __name__=='__main__':main()
