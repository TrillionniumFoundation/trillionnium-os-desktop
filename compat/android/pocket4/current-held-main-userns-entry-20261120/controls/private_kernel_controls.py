#!/usr/bin/python3
"""Owned private kernel fixture, never the actual Android Main or its daemon."""
from pathlib import Path
import array
import ctypes
import fcntl
import hashlib
import json
import os
import resource
import select
import signal
import socket
import stat
import subprocess
import time

ROOT = Path('/opt/p4-guest-entry-private-controls-20261120-runtimeaudit-r3')
INPUT = Path('/home/alex/work/p4-guest-entry-source-20261120-runtimeaudit-r1/held-namespace-entry')
SHA = '67cfd1c212e9f40ce3f0ff7be856a05f8189c674cbfa270757a672ea596a6c3f'
NS = {'mnt':0x00020000,'pid':0x20000000,'uts':0x04000000,
      'ipc':0x08000000,'net':0x40000000,'cgroup':0x02000000}
LIBC = ctypes.CDLL(None,use_errno=True)
LIBC.mount.argtypes = [ctypes.c_char_p,ctypes.c_char_p,ctypes.c_char_p,ctypes.c_ulong,ctypes.c_char_p]
LIBC.setgroups.argtypes = [ctypes.c_size_t,ctypes.c_void_p]


def need(ok,message):
    if not ok:raise RuntimeError(message)


def call(result,message):
    if result != 0:raise OSError(ctypes.get_errno(),message)


def f9(s):
    return [s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns]


def whole(path,limit=8*1024**2):
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        before=f9(os.fstat(fd));need(stat.S_ISREG(before[2]) and before[5]==1 and before[6]<=limit,'regular bounded source')
        with os.fdopen(os.dup(fd),'rb') as stream:raw=stream.read(limit+1)
        need(len(raw)==before[6] and before==f9(os.fstat(fd))==f9(path.lstat()),'complete input bookend')
        return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'identity':before},raw
    finally:os.close(fd)


def publish(path,raw,mode=0o600):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,mode)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())


def process(pid):
    p=Path('/proc')/str(pid);raw=(p/'stat').read_text();fields=raw.rsplit(') ',1)[1].split()
    return {'pid':pid,'ppid':int(fields[1]),'start_ticks':int(fields[19]),'state':fields[0]}


def alive(fd):
    poll=select.poll();poll.register(fd,select.POLLIN|select.POLLERR|select.POLLHUP)
    need(not poll.poll(0),'owned original process exited')


def send(s,value):s.send(json.dumps(value,separators=(',',':')).encode())


def receive(s):
    value=s.recv(16384);need(value,'owned private control closed');return json.loads(value)


def creator(channel,parent):
    """Only this newly forked test actor creates namespaces and a private proc."""
    child=None
    try:
        call(LIBC.prctl(1,9,0,0,0),'creator parent-death')
        need(os.getppid()==parent,'creator parent changed')
        call(LIBC.setgroups(0,None),'clear fixture host groups')
        call(LIBC.unshare(0x10000000),'create private test userns')
        send(channel,{'map_ready':True})
        need(receive(channel)=={'maps_written':True},'exact map barrier')
        call(LIBC.setresgid(0,0,0),'fixed private guest group')
        call(LIBC.setresuid(0,0,0),'fixed private guest user')
        call(LIBC.prctl(1,9,0,0,0),'restore creator parent-death')
        need(os.getppid()==parent,'creator parent changed after mapping')
        self_pidfd=os.pidfd_open(os.getpid(),0)
        call(LIBC.unshare(sum(NS.values())),'create six private test namespaces')
        # This is only the newly copied namespace. The controller's original
        # mount tree is never changed, and is independently bookended below.
        call(LIBC.mount(None,b'/',None,(1<<14)|(1<<18),None),'private mount propagation')
        stop_read,stop_write=os.pipe2(os.O_CLOEXEC)
        child=os.fork()
        if child==0:
            try:
                os.close(stop_write)
                call(LIBC.prctl(1,9,0,0,0),'private init parent-death')
                alive(self_pidfd)
                need(os.getpid()==1,'private PID namespace init required')
                call(LIBC.mount(b'proc',b'/proc',b'proc',2|4|8,None),'private proc mount')
                send(channel,{'init_ready':True})
                channel.close();os.close(self_pidfd)
                need(os.read(stop_read,1)==b'','private init stops only on owned pipe closure')
                os.close(stop_read);os._exit(0)
            except BaseException as error:
                try:send(channel,{'init_error':repr(error)})
                finally:os._exit(125)
        os.close(stop_read);os.close(self_pidfd)
        send(channel,{'init_host_pid':child})
        need(receive(channel)=={'stop':True},'owned private stop only')
        os.close(stop_write)
        pid,status=os.waitpid(child,0);need(pid==child and os.waitstatus_to_exitcode(status)==0,'original private init reaped normally')
        child=None
        send(channel,{'init_reaped':True,'init_exit_code':0})
        channel.close();os._exit(0)
    except BaseException as error:
        try:send(channel,{'creator_error':repr(error)})
        except BaseException:pass
        if child is not None:
            try:os.kill(child,signal.SIGKILL)
            except ProcessLookupError:pass
            try:os.waitpid(child,0)
            except ChildProcessError:pass
        os._exit(125)


def own_children():
    result=set()
    for task in Path('/proc/self/task').iterdir():result.update(int(x) for x in (task/'children').read_text().split())
    return result


def main():
    need(os.getuid()==os.geteuid()==0,'actual privileged test operator')
    available=sorted(os.sched_getaffinity(0));need(20 in available and len(available)>=3,'one core and two reserved')
    os.sched_setaffinity(0,{20})
    resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
    resource.setrlimit(resource.RLIMIT_CPU,(45,45));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024**2,16*1024**2))
    call(LIBC.prctl(36,1,0,0,0),'private controller subreaper')
    need(own_children()==set(),'fresh controller owns no preexisting child')
    need(not ROOT.exists(),'fresh private test root');ROOT.mkdir(mode=0o700)
    initial_mounts=Path('/proc/self/mountinfo').read_bytes()
    initial_ns={k:f9(os.stat('/proc/self/ns/'+k))[:3] for k in (*NS,'user')}
    source,raw=whole(INPUT);need(source['sha256']==SHA,'actual compiled candidate')
    executable=ROOT/'held-namespace-entry';publish(executable,raw,0o700)
    copied,_=whole(executable);need(copied['sha256']==SHA and copied['identity'][3:5]==[0,0],'root private executable copy')
    parent_channel,child_channel=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET|socket.SOCK_CLOEXEC)
    parent_channel.settimeout(10);child_channel.settimeout(35)
    keeper=None;keeper_fd=None;init=None;init_fd=None;fds=[];commands=[];failure=None;normal_retired=False
    started=time.time_ns();deadline=time.monotonic()+40
    def interrupted(signum,frame):raise TimeoutError('private controller interrupted '+str(signum))
    for signum in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP,signal.SIGALRM):signal.signal(signum,interrupted)
    signal.alarm(45)
    try:
        parent=os.getpid();keeper=os.fork()
        if keeper==0:
            parent_channel.close();creator(child_channel,parent)
        child_channel.close();keeper_fd=os.pidfd_open(keeper,0)
        need(receive(parent_channel)=={'map_ready':True},'actual private map barrier')
        before=process(keeper);need(before['ppid']==parent,'original creator child')
        proc=os.open('/proc/'+str(keeper),os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
        try:
            # A one-ID, non-host-root private mapping. It creates no durable
            # account or credential file, and is never adopted by Droidloom.
            for name in ('uid_map','gid_map'):
                fd=os.open(name,os.O_WRONLY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=proc)
                try:need(os.write(fd,b'0 805306368 1\n')==14,'complete private map write')
                finally:os.close(fd)
        finally:os.close(proc)
        need(process(keeper)==before,'same original creator through map writes');alive(keeper_fd)
        send(parent_channel,{'maps_written':True})
        responses=[receive(parent_channel),receive(parent_channel)]
        need(sum(x=={'init_ready':True} for x in responses)==1,'private init actually mounted proc: '+repr(responses))
        pids=[x['init_host_pid'] for x in responses if set(x)=={'init_host_pid'}]
        need(len(pids)==1 and type(pids[0]) is int and pids[0]>1,'own creator returned one actual child')
        init=pids[0];init_fd=os.pidfd_open(init,0);init_record=process(init)
        need(init_record['ppid']==keeper and init_record['state'] not in ('Z','X'),'same owned private init')
        proc=os.open('/proc/'+str(init),os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC);fds.append(proc)
        root=os.open('root',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC,dir_fd=proc);fds.append(root)
        namespaces={}
        for name,kind in NS.items():
            fd=os.open('ns/'+name,os.O_RDONLY|os.O_CLOEXEC,dir_fd=proc);fds.append(fd)
            need(fcntl.ioctl(fd,0xb703)==kind,'actual private namespace kind');namespaces[name]=fd
        userns=os.open('ns/user',os.O_RDONLY|os.O_CLOEXEC,dir_fd=proc);fds.append(userns)
        user_meta=os.fstat(userns)
        uidmap=Path('/proc/'+str(init)+'/uid_map').read_text();gidmap=Path('/proc/'+str(init)+'/gid_map').read_text()
        need(process(init)==init_record,'original private Main acquisition');alive(init_fd);alive(keeper_fd)
        def run(name,code=0,reason=None,change=None):
            need(time.monotonic()+5<deadline,'bounded fixture case deadline')
            parameters={'root':root,**namespaces};expected_userns=user_meta.st_ino;expected_start=init_record['start_ticks']
            extras=[]
            if change=='user':expected_userns+=1
            elif change=='start':expected_start+=1
            elif change=='mixed':
                fd=os.open('/proc/self/ns/uts',os.O_RDONLY|os.O_CLOEXEC);extras.append(fd);parameters['uts']=fd
            elif change=='root':
                fd=os.open('/',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC);extras.append(fd);parameters['root']=fd
            argv=[str(executable),'--parent-pid='+str(os.getpid()),'--root-fd='+str(parameters['root'])]
            argv+=['--'+key+'-fd='+str(parameters[key]) for key in NS]
            argv+=['--expected-userns-device='+str(user_meta.st_dev),'--expected-userns-inode='+str(expected_userns),
                   '--expected-init-start-ticks='+str(expected_start),'--','/usr/bin/id','-u']
            authority=tuple(parameters.values());need(len(authority)==len(set(authority))==7,'exact seven transferred FDs')
            output,errors=ROOT/(name+'.stdout'),ROOT/(name+'.stderr');child=None;pidfd=None;begin=time.time_ns()
            try:
                with output.open('xb') as out,errors.open('xb') as err:
                    child=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=out,stderr=err,
                        env={'PATH':'/usr/bin:/bin','LANG':'C'},pass_fds=authority,start_new_session=True)
                    pidfd=os.pidfd_open(child.pid,0)
                    child.wait(timeout=5)
            finally:
                if child is not None and child.returncode is None:
                    try:os.killpg(child.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    child.wait(timeout=5)
                if pidfd is not None:os.close(pidfd)
                for fd in extras:os.close(fd)
            out_ref,out=whole(output);err_ref,err=whole(errors)
            commands.append({'name':name,'argv':argv,'pid':child.pid,'exit_code':child.returncode,
                'started_ns':begin,'finished_ns':time.time_ns(),'actual_child_reaped':True,
                'original_pidfd_held_until_reaped':pidfd is not None,'stdout':out_ref,'stderr':err_ref})
            need(child.returncode==code,'real helper exit: '+name)
            if code==0:need(out==b'0\n' and err==b'','actual helper command ran as guest UID zero')
            else:need(out==b'' and reason.encode() in err,'negative rejected before fixed command: '+name)
            alive(init_fd);alive(keeper_fd);need(process(init)==init_record,'same original private init after case')
            need(own_children()=={keeper},'no leftover helper subtree')
        run('wrong-userns',125,'derived namespace is not the exact held Main userns','user')
        run('wrong-start',125,'actual fixed Main init generation changed','start')
        run('mixed-namespace',125,'mixed namespace owners','mixed')
        run('wrong-root',125,'invalid mapped Main UID extent','root')
        run('actual-private-userns-entry')
        need(Path('/proc/'+str(init)+'/uid_map').read_text()==uidmap and Path('/proc/'+str(init)+'/gid_map').read_text()==gidmap,
             'private actual maps unchanged')
        send(parent_channel,{'stop':True})
        need(receive(parent_channel)=={'init_reaped':True,'init_exit_code':0},'original creator actually reaped private init')
        pid,status=os.waitpid(keeper,0);need(pid==keeper and os.waitstatus_to_exitcode(status)==0,'original creator reaped normally')
        keeper=None;normal_retired=True
    except BaseException as error:failure={'type':type(error).__name__,'message':str(error)}
    finally:
        signal.alarm(0)
        for signum in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(signum,signal.SIG_IGN)
        if not normal_retired:
            for fd in (init_fd,keeper_fd):
                if fd is not None:
                    try:signal.pidfd_send_signal(fd,signal.SIGKILL)
                    except ProcessLookupError:pass
            until=time.monotonic()+5
            while own_children() and time.monotonic()<until:
                for pid in own_children():
                    try:
                        fd=os.pidfd_open(pid,0)
                        try:signal.pidfd_send_signal(fd,signal.SIGKILL)
                        except ProcessLookupError:pass
                        finally:os.close(fd)
                    except ProcessLookupError:pass
                    try:os.waitpid(pid,os.WNOHANG)
                    except ChildProcessError:pass
                time.sleep(0.02)
        for fd in reversed(fds):os.close(fd)
        for fd in (init_fd,keeper_fd):
            if fd is not None:os.close(fd)
        parent_channel.close();child_channel.close()
        host_unchanged=(initial_mounts==Path('/proc/self/mountinfo').read_bytes()
            and initial_ns=={k:f9(os.stat('/proc/self/ns/'+k))[:3] for k in (*NS,'user')})
        input_unchanged=whole(INPUT)[0]==source and whole(executable)[0]==copied
        report={'schema':'p4-held-main-userns-entry-private-kernel-controls-v1','passed':failure is None and normal_retired and not own_children() and host_unchanged and input_unchanged,
            'error':failure,'started_ns':started,'finished_ns':time.time_ns(),'source_binary':source,'private_binary':copied,
            'commands':commands,'normal_fixture_retirement':normal_retired,'all_owned_children_reaped':not own_children(),
            'host_mount_and_namespace_bookends_equal':host_unchanged,'input_bookends_equal':input_unchanged,
            'original_privileged_root_operator':True,'inherited_authority_fd_count':7,'private_guest_uid':805306368,
            'Android_namespace_entries':0,'Android_commands_executed':0,'daemon_ReadyTreeWitness_issued':False,
            'production_ready':False,'runtime_qualified':False,'current_or_original_inputs_mutated':False}
        publish(ROOT/'RESULT.json',(json.dumps(report,indent=2)+'\n').encode())
        ref,_=whole(ROOT/'RESULT.json');print(json.dumps({'passed':report['passed'],'report':ref,'error':failure}),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
