"""Five real own-host-child regressions and two pure transport order controls.
No Main/Android/namespace helper executes. Seven passed FDs are synthetic owned
regular files. R6 now/write_new definitions are compiled unchanged from the
pinned recorder source; production context/transport/contract are loaded whole.
"""
import ast
import contextlib
import datetime
import errno
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import stat
import subprocess
import sys
import time
import types

ROOT=Path('/home/alex/work/pocket4-ndk-bounded-output-host-controls01')
CAP=262144
ARTIFACT_BYTES=CAP*4+17
REAL_CASES=('own_artifact_larger_than_log_cap','both_streams_exactly_at_cap',
            'stdout_overflow_preserves_primary','stderr_overflow_preserves_primary',
            'timeout_retires_own_child')
PURE_CASES=('capture_error_before_cleanup_rc_is_primary',
            'observed_nonzero_exit_precedes_late_capture_error')


def need(value,message):
    if not value:
        raise AssertionError(message)


def pin(raw):
    return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def fd_map():
    values={}
    discarded=[]
    for name in os.listdir('/proc/self/fd'):
        if not name.isdecimal():
            continue
        fd=int(name)
        try:
            s=os.fstat(fd)
        except OSError as error:
            if error.errno==errno.EBADF:
                discarded.append(fd)
                continue
            raise
        values[str(fd)]=[s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_rdev,s.st_nlink]
    return values,discarded


def load(raw,name):
    module=types.ModuleType(name)
    module.__file__='<fixed-host-control-'+name+'>'
    exec(compile(raw,module.__file__,'exec'),module.__dict__)
    return module


def read_owned(path,maximum,opened_closed,parent_fd):
    fd=os.open(Path(path).name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent_fd)
    event={'role':'test_read','fd':fd,'closed':False}
    opened_closed.append(event)
    try:
        before=os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and
             before.st_uid==os.geteuid() and before.st_gid==os.getegid() and
             stat.S_IMODE(before.st_mode)==0o600 and before.st_size<=maximum,
             'fixed own file shape')
        chunks=[]
        count=0
        while count<=maximum:
            data=os.read(fd,min(65536,maximum+1-count))
            if not data:
                break
            count+=len(data)
            need(count<=maximum,'fixed own file bound')
            chunks.append(data)
        raw=b''.join(chunks)
        after=os.fstat(fd)
        named=os.stat(Path(path).name,dir_fd=parent_fd,follow_symlinks=False)
        fields=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,
                         s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        need(fields(before)==fields(after)==fields(named) and len(raw)==before.st_size,
             'fixed own file changed')
        return raw
    finally:
        os.close(fd)
        event['closed']=True


def run_controls(inputs):
    need(set(inputs)=={'fixture_context.py','fixture_transport.py','fixture_contract.py','recorder.py'},
         'exact four source inputs')
    initial_fds,discarded=fd_map()
    initial_fsize=resource.getrlimit(resource.RLIMIT_FSIZE)
    initial_credentials=[os.getuid(),os.geteuid(),os.getgid(),os.getegid(),os.getgroups()]
    ns_names=('mnt','pid','uts','ipc','net','cgroup','user')
    initial_namespaces={n:os.readlink('/proc/self/ns/'+n) for n in ns_names}
    need(all(x==resource.RLIM_INFINITY or x>=ARTIFACT_BYTES for x in initial_fsize),
         'host fixture cannot prove larger artifact with an already-smaller ambient limit')
    need(signal.getsignal(signal.SIGCHLD)==signal.SIG_DFL and
         signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0) and
         signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK,[]),
         'host fixture signal precondition')
    initial_handler=signal.getsignal(signal.SIGALRM)
    initial_umask=os.umask(0o077)
    created_root=None
    directories=[]
    directory_by_path={}
    directory_FD_events=[]
    workspace_fd=None
    known_files=[]
    authority_rows=[]
    read_fd_events=[]
    real_results=[]
    pure_results=[]
    cleanup_errors=[]
    error=None
    signal_changed=False
    restored_timer=restored_umask=False
    contexts=[]
    records=[]
    started=time.monotonic()

    def public_error(exc):
        return {'type':type(exc).__name__,'message':str(exc)[:2048],
                'errno':getattr(exc,'errno',None)}

    def timeout(_signum,_frame):
        raise TimeoutError('fixed host-controls 45 second deadline')

    def remember_known(path):
        path=Path(path)
        if path not in known_files:
            known_files.append(path)

    def mkdir_owned(path):
        path=Path(path)
        parent_fd=(workspace_fd if path.parent==ROOT.parent else
                   directory_by_path[path.parent]['fd'])
        os.mkdir(path.name,0o700,dir_fd=parent_fd)
        fd=os.open(path.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,
                   dir_fd=parent_fd)
        event={'role':'own_directory','fd':fd,'closed':False}
        directory_FD_events.append(event)
        st=os.fstat(fd)
        named=os.stat(path.name,dir_fd=parent_fd,follow_symlinks=False)
        identity=lambda v:(v.st_dev,v.st_ino,v.st_mode,v.st_uid,v.st_gid)
        need(stat.S_ISDIR(st.st_mode) and stat.S_IMODE(st.st_mode)==0o700 and
             st.st_uid==os.geteuid() and st.st_gid==os.getegid() and
             identity(st)==identity(named),'own directory shape and held name')
        row={'path':path,'name':path.name,'fd':fd,'parent_fd':parent_fd,
             'identity':identity(st),'event':event}
        directories.append(row)
        directory_by_path[path]=row
        return row

    try:
        signal.signal(signal.SIGALRM,timeout)
        signal_changed=True
        signal.setitimer(signal.ITIMER_REAL,45.0)
        c=load(inputs['fixture_context.py'],'bounded_context')
        t=load(inputs['fixture_transport.py'],'bounded_transport')
        f=load(inputs['fixture_contract.py'],'original_contract')
        need(c.OUTPUT_LIMIT==CAP,'original output cap')
        tree=ast.parse(inputs['fixture_context.py'])
        calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call)]
        need(not any(isinstance(node.func,ast.Attribute) and node.func.attr=='setrlimit'
                     for node in calls),'candidate must not change file-size rlimits')
        cls=next(node for node in tree.body if isinstance(node,ast.ClassDef) and
                 node.name=='_OwnedCommandCapture')
        need(not any(isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and
                     node.func.attr in ('poll','communicate') for node in ast.walk(cls)),
             'capture may not reap with poll or communicate')
        old_recorder=ast.parse(inputs['recorder.py'])
        chosen=[node for node in old_recorder.body if isinstance(node,ast.FunctionDef) and
                node.name in ('now','write_new')]
        need(len(chosen)==2,'exact original recorder writers')
        writer_env={'datetime':datetime,'json':json,'os':os,'Path':Path}
        exec(compile(ast.Module(body=chosen,type_ignores=[]),'<original-R6-writers>','exec'),writer_env)
        original_write=writer_env['write_new']

        def write_new(path,value):
            remember_known(path)
            return original_write(path,value)

        recorder=types.SimpleNamespace(now=writer_env['now'],write_new=write_new)
        workspace_fd=os.open(ROOT.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        directory_FD_events.append({'role':'workspace_parent','fd':workspace_fd,'closed':False})
        created_root=mkdir_owned(ROOT)
        for number in range(7):
            path=ROOT/('authority-%d.bin'%number)
            fd=os.open(path.name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,
                       0o600,dir_fd=created_root['fd'])
            row={'role':'synthetic_authority','fd':fd,'closed':False}
            authority_rows.append(row)
            remember_known(path)
            os.write(fd,b'explicit synthetic authority\n')
            os.fsync(fd)
        descriptors=tuple(row['fd'] for row in authority_rows)
        need(len(set(descriptors))==7,'seven distinct own file descriptors')
        build_pin={'bytes':1,'sha256':'b'*64}
        synthetic_installation={'package':f.PACKAGE,'uid':14000,'user':0,
            'owned_install_qualified':True,'Main_epoch':f.MAIN_EPOCH,'build_result':build_pin}
        synthetic_scope=f.scope('run','d'*32,build_pin,synthetic_installation)

        class Context:
            def __init__(self,step):
                self.recorder=recorder
                self.step=step
                self.deadline=time.monotonic()+30.0
                self.command_index=0
                self.action_attempted=False
                self._android_mutation=False
                self.guards=0
                self.poisoned=False
                self.binding=types.SimpleNamespace(target=self)
            def guard(self,*_args,**_kwargs):
                self.guards+=1
            def poison_unjoined_command(self):
                self.poisoned=True

        class Target:
            expected={'pid':424242}
            helper_path='/explicit-host-fixture/not-executed-held-helper'
            helper_sha256=t.HELD_HELPER_SHA256
            def __init__(self):
                self.verifies=0
                self.entries=0
                self.releases=0
            def verify(self):
                self.verifies+=1
            @contextlib.contextmanager
            def entry(self,command):
                self.entries+=1
                argv=[self.helper_path,'--parent-pid='+str(os.getpid()),
                      '--root-fd='+str(descriptors[0])]
                argv+=['--'+name+'-fd='+str(fd) for name,fd in
                       zip(('mnt','pid','uts','ipc','net','cgroup'),descriptors[1:])]
                argv+=['--',*command]
                try:
                    yield argv,descriptors
                finally:
                    self.releases+=1

        def transport_call(runner):
            target=Target()
            seen=[]
            env={key:'/explicit-synthetic-environment' for key in t.REQUIRED_ENV}
            bound=t.BoundArun(target=target,environment=env,
                guard=lambda **kw:seen.append(('guard',kw)),
                record=lambda kind,value:seen.append((kind,value)),
                epoch_sha256=t.FRAMEWORK_EPOCH_SHA256,init_pid=424242,
                package=f.PACKAGE,uid=14000,interactive_production=True,
                fixture_scope=synthetic_scope,fixture_contract=f,runner=runner)
            records.append((target,seen))
            return bound,target,seen

        def write_program(body):
            return ('import json,os,resource,sys,time\n'
                'def send(fd,data):\n'
                '    offset=0\n'
                '    while offset<len(data):\n'
                '        n=os.write(fd,data[offset:])\n'
                '        if n<=0: raise RuntimeError("own child write stalled")\n'
                '        offset+=n\n'+body)

        programs={
            REAL_CASES[0]:write_program(
                'fd=os.open(sys.argv[1],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)\n'
                'try:\n'
                '    send(fd,b"A"*'+str(ARTIFACT_BYTES)+')\n'
                '    os.fsync(fd)\n'
                'finally:\n'
                '    os.close(fd)\n'
                'send(1,(json.dumps({"bytes":'+str(ARTIFACT_BYTES)+','
                '"RLIMIT_FSIZE":list(resource.getrlimit(resource.RLIMIT_FSIZE))})+"\\n").encode())\n'
                'send(2,b"own artifact complete\\n")\n'),
            REAL_CASES[1]:write_program(
                'for _ in range('+str(CAP//4096)+'):\n'
                '    send(1,b"O"*4096)\n'
                '    send(2,b"E"*4096)\n'),
            REAL_CASES[2]:write_program(
                'send(2,b"before stdout overflow\\n")\n'
                'send(1,b"X"*'+str(CAP+65536)+')\n'
                'time.sleep(30)\n'),
            REAL_CASES[3]:write_program(
                'send(1,b"before stderr overflow\\n")\n'
                'send(2,b"Y"*'+str(CAP+65536)+')\n'
                'time.sleep(30)\n'),
            REAL_CASES[4]:write_program(
                'send(1,b"own timeout started\\n")\n'
                'send(2,b"own timeout waiting\\n")\n'
                'time.sleep(30)\n')
        }

        for index,name in enumerate(REAL_CASES):
            step=ROOT/('case-%02d'%index)
            mkdir_owned(step)
            context=Context(step)
            contexts.append(context)
            artifact=step/'large-own-artifact.bin'
            if index==0:
                remember_known(artifact)
            argv=['/usr/bin/python3','-I','-B','-c',programs[name]]
            if index==0:
                argv.append(str(artifact))
            duration=2.0 if index==4 else 8.0
            options={'stdout':subprocess.PIPE,'stderr':subprocess.PIPE,'timeout':duration,
                'env':{'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},
                'pass_fds':descriptors,'close_fds':True}
            for suffix in ('.intent.json','.stdout','.stderr','.result.json'):
                remember_known(step/('command-001'+suffix))
            before_case,_=fd_map()
            captured=[]
            transport_error=None
            if index in (2,3):
                def host_runner(_never_executed_helper_argv,**passed):
                    need(passed['pass_fds']==descriptors and passed['close_fds'] is True and
                         passed['stdout']==subprocess.PIPE and passed['stderr']==subprocess.PIPE,
                         'explicit transport-to-host IO seam only')
                    value=c.command_with_bound(context,argv,options)
                    captured.append(value)
                    return value
                bound,target,seen=transport_call(host_runner)
                try:
                    bound(['/system/bin/true'],duration)
                except t.TransportError as exc:
                    transport_error=str(exc)
                    need(transport_error=='ANDROID_COMMAND_OUTPUT_LIMIT',
                         'overflow must precede cleanup return code')
                else:
                    raise AssertionError('overflow transport accepted')
                need(target.entries==target.releases==1 and
                     len(captured)==1 and bound._poisoned is True,
                     'one synthetic entry with real host child and closed transport')
                value=captured[0]
            else:
                value=c.command_with_bound(context,argv,options)
            need(context.command_index==1 and context.guards==1 and not context.poisoned,
                 'one real recorder command and joined direct child')
            need(value.recorder_spawned is True and value.recorder_joined is True,
                 'actual child spawned and reaped')
            for fd in descriptors:
                os.fstat(fd)
            need(resource.getrlimit(resource.RLIMIT_FSIZE)==initial_fsize,
                 'parent rlimit unchanged per case')
            after_case,_=fd_map()
            need(after_case==before_case,'each command closes its exact FD set')
            raw=read_owned(step/'command-001.result.json',65536,read_fd_events,directory_by_path[step]['fd'])
            receipt=json.loads(raw)
            stdout=read_owned(step/'command-001.stdout',CAP,read_fd_events,directory_by_path[step]['fd'])
            stderr=read_owned(step/'command-001.stderr',CAP,read_fd_events,directory_by_path[step]['fd'])
            need(stdout==value.stdout and stderr==value.stderr and
                 pin(stdout)['sha256']==receipt['stdout_sha256'] and
                 pin(stderr)['sha256']==receipt['stderr_sha256'],
                 'durable log bytes and completed process agree')
            capture=receipt['output_capture']
            life=receipt['owned_lifecycle']
            need(capture['maximum_bytes']==CAP and capture['RLIMIT_FSIZE_modified'] is False and
                 capture['RLIMIT_FSIZE_before']==capture['RLIMIT_FSIZE_after']==list(initial_fsize) and
                 capture['stored_bytes']=={'stdout':len(stdout),'stderr':len(stderr)} and
                 all(0<=x<=CAP for x in capture['stored_bytes'].values()) and
                 all(0<=x<=CAP+1 for x in capture['observed_bytes'].values()),
                 'same cap and inherited file-size limit observation')
            need(life['all_tracked_FDs_closed'] is True and
                 life['direct_child_reaped'] is True and
                 life['waitid_uses_WNOWAIT'] is True and
                 life['group_signals_after_reap_started'] is False and
                 life['retirement_deadline_met'] is True and
                 life['reap_started_at']<=life['reaped_at']<=life['retirement_deadline'] and
                 all(row['closed'] and row['close_attempted'] for row in life['FDs']),
                 'bounded direct-child and descriptor retirement')
            need(life['session_observations'] and
                 all(v['pid']==v['process_group']==v['session'] and
                     v['reap_started'] is False and v['pidfd_open'] is True
                     for v in life['session_observations']),
                 'fresh session/group and pidfd identity')
            if index in (0,1):
                need(value.returncode==0 and receipt['error'] is None and receipt['errors']==[] and
                     capture['complete'] is True and capture['EOF']=={'stdout':True,'stderr':True} and
                     receipt['timed_out'] is False and life['signal_observations']==[],
                     'normal EOF plus exited child without kill')
            if index==0:
                observation=json.loads(stdout)
                data=read_owned(artifact,ARTIFACT_BYTES,read_fd_events,directory_by_path[step]['fd'])
                need(observation=={'bytes':ARTIFACT_BYTES,'RLIMIT_FSIZE':list(initial_fsize)} and
                     data==b'A'*ARTIFACT_BYTES and stderr==b'own artifact complete\n',
                     'own child really writes a file larger than log cap')
            elif index==1:
                need(stdout==b'O'*CAP and stderr==b'E'*CAP,
                     'two full-cap streams concurrently drained')
            elif index in (2,3):
                stream='stdout' if index==2 else 'stderr'
                expected=b'X' if index==2 else b'Y'
                data=stdout if index==2 else stderr
                need(data==expected*CAP and capture['observed_bytes'][stream]==CAP+1 and
                     capture['limit_exceeded'] is True and capture['complete'] is False and
                     receipt['error']['code']=='COMMAND_OUTPUT_BOUND' and
                     receipt['error']==receipt['errors'][0] and receipt['timed_out'] is False and
                     value.capture_retirement_error==receipt['error'] and
                     value.observed_failure_preceded_capture_error is False and
                     value.returncode!=0 and transport_error=='ANDROID_COMMAND_OUTPUT_LIMIT',
                     'strict prefix and preserved overflow first error')
            else:
                need(receipt['timed_out'] is True and
                     receipt['error']['code']=='COMMAND_TIMEOUT' and
                     receipt['error']==receipt['errors'][0] and
                     capture['complete'] is False and capture['limit_exceeded'] is False and
                     value.returncode!=0,'timeout first error and reaped child')
            if index>=2:
                signals=life['signal_observations']
                need(any(v['kind']=='own_process_group' and v['attempted'] and
                         (v['sent'] or v['not_found']) for v in signals) and
                     any(v['stage']=='before_group_signal' for v in life['session_observations']) and
                     all(v['reap_started'] is False and v['observed_monotonic']<=life['reap_started_at']
                         for v in signals if v['kind']=='own_process_group'),
                     'failure signals only fresh unreaped owned session')
            real_results.append({'name':name,'passed':True,'command_receipt':pin(raw),
                'stdout':pin(stdout),'stderr':pin(stderr),'returncode':value.returncode,
                'timed_out':receipt['timed_out'],'capture':capture,
                'owned_lifecycle':life,'actual_host_child':True,
                'Main_or_Android_executed':False,'synthetic_guard_calls':context.guards})

        for name in PURE_CASES:
            value=subprocess.CompletedProcess(['<explicit-pure-no-process>'],-9,b'',b'')
            earlier=name==PURE_CASES[1]
            probe=object.__new__(c._OwnedCommandCapture)
            probe.errors=[]
            probe.observed_failure_preceded_capture_error=False
            probe.exit_observation=({'pid':424243,'code':os.CLD_EXITED,'status':153}
                                    if earlier else None)
            probe.remember('command_capture',OSError(errno.EMFILE,'explicit synthetic capture error'))
            failure=probe.errors[0]
            need(probe.observed_failure_preceded_capture_error==earlier,
                 'real first-error order recording')
            probe.exit_observation={'pid':424243,'code':os.CLD_KILLED,'status':signal.SIGKILL}
            probe.remember('secondary_close',OSError(errno.EIO,'explicit secondary error'))
            need(probe.observed_failure_preceded_capture_error==earlier,
                 'later error may not rewrite first order')
            value.host_timed_out=False
            value.capture_limit_exceeded=False
            # The hostile earlier-exit case deliberately supplies even a stale
            # capture marker: production transport must preserve the first exit.
            value.capture_retirement_error=failure
            value.recorder_errors=probe.errors
            value.observed_failure_preceded_capture_error=probe.observed_failure_preceded_capture_error
            if earlier:
                value.returncode=153
            bound,target,seen=transport_call(lambda *args,**kwargs:value)
            try:
                bound(['/system/bin/true'],8)
            except t.TransportError as exc:
                expected='ANDROID_COMMAND_FAILED' if earlier else 'HOST_COMMAND_CAPTURE_FAILED'
                need(str(exc)==expected and exc.details['returncode']==value.returncode,
                     'production transport preserves observed first cause')
                if not earlier:
                    need(exc.details['capture_first_error']==failure,'exact host primary metadata')
            else:
                raise AssertionError('pure failure accepted')
            need(target.entries==target.releases==1 and bound._poisoned is True,
                 'pure transport release and poison')
            pure_results.append({'name':name,'passed':True,'real_children':0,
                                 'explicit_CompletedProcess_seam':True})

        need([v['name'] for v in real_results]==list(REAL_CASES) and
             [v['name'] for v in pure_results]==list(PURE_CASES),'exact controls count')
    except BaseException as exc:
        error=public_error(exc)
    finally:
        for row in reversed(authority_rows):
            if not row['closed']:
                try:
                    os.close(row['fd'])
                    row['closed']=True
                except BaseException as exc:
                    cleanup_errors.append({'phase':'authority_close',**public_error(exc)})
        for path in reversed(known_files):
            # Operate only inside the exact directory object created and held
            # by this test. An absolute ancestor rename cannot redirect unlink.
            parent=directory_by_path.get(path.parent)
            if parent is None:
                cleanup_errors.append({'phase':'known_file_parent','type':'AssertionError',
                                       'message':'no held own parent','errno':None})
                continue
            try:
                current=os.fstat(parent['fd'])
                need((current.st_dev,current.st_ino,current.st_mode,current.st_uid,current.st_gid)==
                     parent['identity'],'held own parent changed')
                info=os.stat(path.name,dir_fd=parent['fd'],follow_symlinks=False)
            except FileNotFoundError:
                continue
            except BaseException as exc:
                cleanup_errors.append({'phase':'known_file_stat',**public_error(exc)})
                continue
            try:
                need(created_root is not None and stat.S_ISREG(info.st_mode) and info.st_nlink==1 and
                     info.st_uid==os.geteuid() and info.st_gid==os.getegid() and
                     stat.S_IMODE(info.st_mode)==0o600,'exact own file cleanup shape')
                os.unlink(path.name,dir_fd=parent['fd'])
            except BaseException as exc:
                cleanup_errors.append({'phase':'known_file_cleanup',**public_error(exc)})
        for row in reversed(directories):
            try:
                held=os.fstat(row['fd'])
                named=os.stat(row['name'],dir_fd=row['parent_fd'],follow_symlinks=False)
                identity=lambda v:(v.st_dev,v.st_ino,v.st_mode,v.st_uid,v.st_gid)
                need(identity(held)==identity(named)==row['identity'],
                     'exact own directory cleanup identity')
                os.rmdir(row['name'],dir_fd=row['parent_fd'])
            except BaseException as exc:
                cleanup_errors.append({'phase':'known_directory_cleanup',**public_error(exc)})
        for event in reversed(directory_FD_events):
            try:
                os.close(event['fd'])
                event['closed']=True
            except BaseException as exc:
                cleanup_errors.append({'phase':'own_directory_FD_close',**public_error(exc)})

        try:
            if signal_changed:
                signal.setitimer(signal.ITIMER_REAL,0.0)
                signal.signal(signal.SIGALRM,initial_handler)
            restored_timer=(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0) and
                            signal.getsignal(signal.SIGALRM)==initial_handler)
        except BaseException as exc:
            cleanup_errors.append({'phase':'alarm_restore',**public_error(exc)})
        try:
            os.umask(initial_umask)
            observed=os.umask(initial_umask)
            restored_umask=observed==initial_umask
        except BaseException as exc:
            cleanup_errors.append({'phase':'umask_restore',**public_error(exc)})

    final_fds,final_discarded=fd_map()
    final_credentials=[os.getuid(),os.geteuid(),os.getgid(),os.getegid(),os.getgroups()]
    final_namespaces={n:os.readlink('/proc/self/ns/'+n) for n in ns_names}
    root_removed=not os.path.lexists(ROOT) if created_root is not None else False
    same_fds=final_fds==initial_fds
    unchanged=(final_credentials==initial_credentials and final_namespaces==initial_namespaces and
               resource.getrlimit(resource.RLIMIT_FSIZE)==initial_fsize)
    ok=(error is None and cleanup_errors==[] and len(real_results)==5 and len(pure_results)==2 and
        all(row['closed'] for row in authority_rows+read_fd_events+directory_FD_events) and same_fds and unchanged and
        root_removed and restored_timer and restored_umask)
    return {'schema':1,'kind':'pocket4-ndk-bounded-output-host-controls01','ok':ok,
        'error':error,'cleanup_errors':cleanup_errors,'sources':{k:pin(v) for k,v in inputs.items()},
        'real_host_child_controls':real_results,'pure_transport_order_controls':pure_results,
        'expected_real_child_controls':5,'expected_pure_controls':2,
        'authority_FD_events':authority_rows,'test_read_FD_events':read_fd_events,
        'own_directory_FD_events':directory_FD_events,
        'all_owned_test_FDs_closed':all(row['closed'] for row in authority_rows+read_fd_events+directory_FD_events),
        'ambient_FD_baseline_before_production_load':initial_fds,
        'ambient_FD_final':final_fds,'ambient_FD_equality':same_fds,
        'enumeration_FDs_already_EBADF':{'before':discarded,'after':final_discarded},
        'host_namespaces_credentials_and_fsize_unchanged':unchanged,
        'private_fixture_root_removed':root_removed,'alarm_restored':restored_timer,
        'umask_restored':restored_umask,'elapsed_seconds':time.monotonic()-started,
        'Main_reads':0,'Android_commands':0,'namespace_entries':0,'network_calls':0,
        'shared_source_mutations':0,'runtime_nonce_consumed':False,
        'production_Android_execution_qualified':False,
        'original_run01_status':'FAILED_OUTCOME_UNKNOWN_PRESERVED',
        'signal_25_or_file_size_cause_qualified':False}
