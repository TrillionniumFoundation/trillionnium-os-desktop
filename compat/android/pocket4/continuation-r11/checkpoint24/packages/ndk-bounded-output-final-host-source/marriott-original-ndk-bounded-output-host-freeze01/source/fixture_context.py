"""Original NDK runtime Main context, never a commercial App Flow.
Unbound calls stop before Main/OS reads; run and retirement require an explicit
held phase admission, fresh Main guards and source checks at every boundary.
Original R6 SourceContract verification, current8 guard, explicit discovery,
paired classpaths and held six-namespace entry are used without monkeypatching.
"""
import hashlib
import json
import os
from pathlib import Path
import resource
import selectors
import signal
import stat
import subprocess
import time
import types

PACKAGE = 'com.example.ndk_tests'
INSTALLED_SHARED = Path('/home/alex/work/pocket4-current-host-r6-source-01')
SHARED_MANIFEST = '002ee581a4bb399536dd7d594d01f050e2540d9c049b0cfb37e1c96954b6caff'
CONTRACT_BYTES = 11359
CONTRACT_SHA = 'f92d2598221c5bf65e783df39864879a2056da47f794680668b34df11f97da49'
MAIN_EPOCH = '7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c'
BASELINE_SHA = '633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364'
QUALIFICATION_SHA = 'ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e'
CURRENT_GUARD_SHA = '96dbdaf7673d5298e6fe17cb1b7ebae29b37110ee59f31b0c927e2cb0ef4b150'
OUTPUT_LIMIT = 262144
APK_LIMIT = 33554432
HASH_SECONDS = 20


def need(ok, code):
    if not ok:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(fd):
    s=os.fstat(fd)
    return {'device':s.st_dev,'inode':s.st_ino,'mode':s.st_mode,'uid':s.st_uid,'gid':s.st_gid,
            'nlink':s.st_nlink,'bytes':s.st_size,'mtime_ns':s.st_mtime_ns,'ctime_ns':s.st_ctime_ns}


def baseline_binding(guard, baseline, fixture, scope):
    fixture.validate_scope(scope)
    need(baseline.get('schema')=='pocket4-main-current-baseline-v2' and
         baseline.get('kind')=='current-cell-generation' and
         baseline.get('deployment_performed') is False and 'main_deployed' not in baseline and
         baseline['framework_epoch']['sha256']==MAIN_EPOCH==guard.MAIN_EPOCH and
         guard.BASELINE_SHA==BASELINE_SHA and guard.QUALIFICATION_SHA==QUALIFICATION_SHA and
         baseline.get('framework_exit_cause_resolved') is False and
         baseline.get('whole_app_production_ready') is False,
         'ACTUAL_CURRENT_MAIN_BASELINE_REQUIRED')
    need(PACKAGE not in baseline['packages'],'NEW_FIXTURE_MUST_NOT_ADOPT_BASELINE_APP')
    protected=set(baseline['packages'].values())
    need(all(type(x) is int for x in protected),'BASELINE_PACKAGE_UID_SCHEMA')
    need(scope['uid'] is None or scope['uid'] not in protected,'FIXTURE_UID_ALIASES_BASELINE_APP')
    return protected


class CommandCaptureError(RuntimeError):
    pass


class _OwnedCommandCapture:
    """One unreaped new session, two bounded pipes and exact private log files.

    The leader stays waitable until all group signalling has finished.
    waitid always uses WNOHANG|WNOWAIT; Popen.poll/communicate are never used.
    This owns the direct entry process and its new process group only. It does
    not assert ownership of escaped sessions or Binder-launched processes.
    """
    def __init__(self,context,argv,options):
        self.context,self.argv,self.options=context,list(argv),options
        self.process=self.selector=None
        self.pidfd=None
        self.pidfd_registered=False
        self.reap_started=self.spawned=False
        self.reap_started_at=None
        self.joined=True
        self.errors=[]
        self.capture_retirement_error=None
        self.observed_failure_preceded_capture_error=False
        self.journal=[]
        self.logs={}
        self.pipe_rows={}
        self.buffers={'stdout':[],'stderr':[]}
        self.observed={'stdout':0,'stderr':0}
        self.stored={'stdout':0,'stderr':0}
        self.eof={'stdout':False,'stderr':False}
        self.limit_exceeded=False
        self.timed_out=False
        self.returncode=None
        self.exit_observation=None
        self.identity_observations=[]
        self.signal_observations=[]
        self.started=self.deadline=self.last_observed_monotonic=None
        self.retirement_started=self.retirement_deadline=self.reaped_at=self.retired_at=None
        self.fsize_before=resource.getrlimit(resource.RLIMIT_FSIZE)
        self.fsize_after=None

    def remember(self,phase,error,code=None):
        if not self.errors:
            observed=self.exit_observation
            self.observed_failure_preceded_capture_error=bool(observed is not None and
                (observed['code']!=os.CLD_EXITED or observed['status']!=0))
        value={'phase':phase,'exception_type':type(error).__name__,
               'errno':getattr(error,'errno',None)}
        if code is not None:
            value['code']=code
        self.errors.append(value)

    def own(self,role,fd,closer):
        row={'role':role,'fd':fd,'close_attempted':False,'closed':False,
             '_closer':closer}
        self.journal.append(row)
        return row

    def close_row(self,row):
        if row['close_attempted']:
            return
        row['close_attempted']=True
        try:
            row['_closer']()
            row['closed']=True
        except BaseException as error:
            self.remember('command_'+row['role']+'_close',error)

    def waitable(self):
        need(self.process is not None and not self.reap_started,
             'OWN_LEADER_MUST_STILL_BE_UNREAPED')
        kind= os.P_PIDFD if self.pidfd is not None else os.P_PID
        identity=self.pidfd if self.pidfd is not None else self.process.pid
        event=os.waitid(kind,identity,os.WEXITED|os.WNOHANG|os.WNOWAIT)
        if event is not None:
            need(event.si_pid==self.process.pid and
                 event.si_code in (os.CLD_EXITED,os.CLD_KILLED,os.CLD_DUMPED),
                 'OWN_WAIT_IDENTITY_CHANGED')
            value={'pid':event.si_pid,'code':event.si_code,'status':event.si_status}
            if self.exit_observation is not None:
                need(self.exit_observation==value,'OWN_WAIT_STATUS_CHANGED')
            self.exit_observation=value
        return event

    def session_view(self,stage):
        # This first establishes that the exact child remains ours to wait for.
        # No reaping call has occurred, so the leader PID cannot be recycled.
        self.waitable()
        pid=self.process.pid
        view={'stage':stage,'pid':pid,'process_group':os.getpgid(pid),
              'session':os.getsid(pid),'pidfd_open':self.pidfd is not None,
              'reap_started':self.reap_started,'observed_monotonic':time.monotonic()}
        self.identity_observations.append(view)
        need(view['process_group']==pid and view['session']==pid,
             'OWN_NEW_SESSION_IDENTITY_CHANGED')
        return view

    def signal_owned(self):
        need(self.process is not None and not self.reap_started,
             'NO_PROCESS_GROUP_SIGNAL_AFTER_REAP_STARTED')
        # Failure to establish the fresh group relation prevents killpg.
        try:
            view=self.session_view('before_group_signal')
            entry={'kind':'own_process_group','pid':view['pid'],'attempted':True,
                   'sent':False,'not_found':False,'reap_started':self.reap_started,
                   'observed_monotonic':time.monotonic()}
            self.signal_observations.append(entry)
            try:
                os.killpg(view['pid'],signal.SIGKILL)
                entry['sent']=True
            except ProcessLookupError:
                entry['not_found']=True
        except BaseException as error:
            self.remember('owned_command_group_stop',error)
        if self.pidfd is not None:
            entry={'kind':'own_pidfd_leader','attempted':True,
                   'sent':False,'not_found':False,'reap_started':self.reap_started,
                   'observed_monotonic':time.monotonic()}
            self.signal_observations.append(entry)
            try:
                signal.pidfd_send_signal(self.pidfd,signal.SIGKILL,None,0)
                entry['sent']=True
            except ProcessLookupError:
                entry['not_found']=True
            except BaseException as error:
                self.remember('owned_command_leader_stop',error)
        else:
            # pidfd acquisition itself may have failed. A never-reaped direct
            # child plus a fresh own-session check still permits its exact PID.
            # That path retains the pidfd error and can never become success.
            try:
                view=self.session_view('before_direct_child_signal_without_pidfd')
                entry={'kind':'own_unreaped_direct_child','pid':view['pid'],
                       'attempted':True,'sent':False,'not_found':False,
                       'reap_started':self.reap_started,'observed_monotonic':time.monotonic()}
                self.signal_observations.append(entry)
                try:
                    os.kill(view['pid'],signal.SIGKILL)
                    entry['sent']=True
                except ProcessLookupError:
                    entry['not_found']=True
            except BaseException as error:
                self.remember('owned_command_leader_stop_without_pidfd',error)

    def close_pipe(self,name):
        row=self.pipe_rows.get(name)
        if row is None or row['close_attempted']:
            return
        try:
            self.selector.unregister(row['fd'])
        except KeyError:
            pass
        except BaseException as error:
            self.remember('command_'+name+'_unregister',error)
        self.close_row(row)

    def write_prefix(self,name,part):
        offset=0
        while offset<len(part):
            amount=os.write(self.logs[name]['fd'],part[offset:])
            need(amount>0,'OWN_COMMAND_LOG_WRITE_STALLED')
            self.buffers[name].append(part[offset:offset+amount])
            self.stored[name]+=amount
            offset+=amount
            need(self.stored[name]<=OUTPUT_LIMIT,'OWN_COMMAND_LOG_BOUND')

    def capture(self):
        self.selector=selectors.DefaultSelector()
        self.own('selector',self.selector.fileno(),self.selector.close)
        for name in ('stdout','stderr'):
            fd=os.open(str(self.stem)+'.'+name,
                       os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
            self.logs[name]=self.own(name+'_log',fd,lambda fd=fd:os.close(fd))
            observed=os.fstat(fd)
            self.logs[name]['_path']=str(self.stem)+'.'+name
            self.logs[name]['_identity']=(observed.st_dev,observed.st_ino,observed.st_mode,
                                         observed.st_uid,observed.st_gid,observed.st_nlink)
            need(stat.S_ISREG(observed.st_mode) and observed.st_nlink==1 and
                 observed.st_size==0,'OWN_COMMAND_LOG_SHAPE')
        before_spawn=time.monotonic()
        self.last_observed_monotonic=before_spawn
        need(before_spawn<self.deadline,'OWN_COMMAND_DEADLINE_BEFORE_SPAWN')
        self.process=subprocess.Popen(self.argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            env=self.options['env'],start_new_session=True,
            pass_fds=tuple(self.options['pass_fds']),close_fds=True)
        self.spawned=True
        self.joined=False
        self.context.action_attempted |= self.context._android_mutation
        for name in ('stdout','stderr'):
            stream=getattr(self.process,name)
            need(stream is not None,'OWN_COMMAND_PIPE_MISSING')
            self.pipe_rows[name]=self.own(name+'_pipe',stream.fileno(),stream.close)
        self.pidfd=os.pidfd_open(self.process.pid,0)
        self.own('leader_pidfd',self.pidfd,lambda:os.close(self.pidfd))
        need(not os.get_inheritable(self.pidfd),'OWN_PIDFD_MUST_BE_CLOEXEC')
        self.session_view('after_spawn')
        for name,row in self.pipe_rows.items():
            os.set_blocking(row['fd'],False)
            self.selector.register(row['fd'],selectors.EVENT_READ,('pipe',name))
        self.selector.register(self.pidfd,selectors.EVENT_READ,('leader',None))
        self.pidfd_registered=True
        while not self.errors:
            now=time.monotonic()
            self.last_observed_monotonic=now
            if now>=self.deadline:
                self.timed_out=True
                self.remember('command_wait',subprocess.TimeoutExpired(
                    '<owned Android command>',self.options['timeout']),'COMMAND_TIMEOUT')
                break
            self.waitable()
            if self.exit_observation is not None and self.pidfd_registered:
                self.selector.unregister(self.pidfd)
                self.pidfd_registered=False
            if self.exit_observation is not None and all(self.eof.values()):
                break
            events=self.selector.select(min(0.05,self.deadline-now))
            for key,_mask in events:
                if self.errors:
                    break
                before_read=time.monotonic()
                self.last_observed_monotonic=before_read
                if before_read>=self.deadline:
                    self.timed_out=True
                    self.remember('command_wait',subprocess.TimeoutExpired(
                        '<owned Android command>',self.options['timeout']),'COMMAND_TIMEOUT')
                    break
                kind,name=key.data
                if kind=='leader':
                    self.waitable()
                    continue
                remaining=OUTPUT_LIMIT-self.stored[name]
                try:
                    part=os.read(key.fd,min(65536,remaining+1))
                except BlockingIOError:
                    continue
                if not part:
                    self.eof[name]=True
                    self.close_pipe(name)
                    continue
                self.observed[name]+=len(part)
                self.write_prefix(name,part[:remaining])
                if len(part)>remaining:
                    self.limit_exceeded=True
                    self.remember('command_output_bound',CommandCaptureError(
                        'per-stream output bound'),'COMMAND_OUTPUT_BOUND')
                    break

    def join_leader(self):
        if self.process is None or self.joined:
            return
        if self.errors and not self.reap_started:
            try:
                self.signal_owned()
            except BaseException as error:
                self.remember('owned_command_stop',error)
        if not self.reap_started:
            self.reap_started_at=time.monotonic()
        self.reap_started=True
        try:
            self.returncode=self.process.wait(
                timeout=max(0.001,self.retirement_deadline-time.monotonic()))
            self.joined=True
            self.reaped_at=time.monotonic()
        except BaseException as error:
            self.remember('owned_command_join',error)
            # Never call killpg after Popen.wait may have reaped the leader.
            # A held pidfd remains an exact leader-only authority.
            if self.pidfd is not None:
                entry={'kind':'own_pidfd_after_wait','attempted':True,
                       'sent':False,'not_found':False,'reap_started':self.reap_started,
                       'observed_monotonic':time.monotonic()}
                self.signal_observations.append(entry)
                try:
                    signal.pidfd_send_signal(self.pidfd,signal.SIGKILL,None,0)
                    entry['sent']=True
                except ProcessLookupError:
                    entry['not_found']=True
                except BaseException as close_error:
                    self.remember('owned_command_late_leader_stop',close_error)
            remaining=self.retirement_deadline-time.monotonic()
            if remaining>0:
                try:
                    self.returncode=self.process.wait(timeout=remaining)
                    self.joined=True
                    self.reaped_at=time.monotonic()
                except BaseException as close_error:
                    self.remember('owned_command_final_join',close_error)

    def finish(self):
        self.capture_retirement_error=(dict(self.errors[0]) if self.errors and
            not self.observed_failure_preceded_capture_error else None)
        # Establish an already-observed fallback before consulting the clock:
        # a phase alarm at cleanup entry still leaves a finite, non-extended
        # cleanup bound and reaches the same-child stop/join path.
        self.retirement_started=self.last_observed_monotonic
        self.retirement_deadline=self.retirement_started+5.0
        try:
            self.retirement_started=time.monotonic()
            self.retirement_deadline=self.retirement_started+5.0
            self.join_leader()
        except BaseException as error:
            self.remember('owned_command_retirement',error)
            # Best-effort cleanup of the same child, never a new command.
            # The already-established absolute retirement deadline stays.
            try:
                self.join_leader()
            except BaseException as close_error:
                self.remember('owned_command_retirement_secondary',close_error)
        finally:
            for name in ('stdout','stderr'):
                self.close_pipe(name)
            for name,row in self.logs.items():
                if not row['close_attempted']:
                    try:
                        observed=os.fstat(row['fd'])
                        named=os.stat(row['_path'],follow_symlinks=False)
                        fixed=(observed.st_dev,observed.st_ino,observed.st_mode,
                               observed.st_uid,observed.st_gid,observed.st_nlink)
                        need(fixed==row['_identity'] and
                             (named.st_dev,named.st_ino,named.st_mode,named.st_uid,named.st_gid,
                              named.st_nlink,named.st_size,named.st_mtime_ns,named.st_ctime_ns)==
                             (observed.st_dev,observed.st_ino,observed.st_mode,observed.st_uid,observed.st_gid,
                              observed.st_nlink,observed.st_size,observed.st_mtime_ns,observed.st_ctime_ns) and
                             observed.st_size==self.stored[name] and
                             observed.st_size<=OUTPUT_LIMIT,'OWN_COMMAND_LOG_SHAPE_OR_BOUND_CHANGED')
                        os.fsync(row['fd'])
                    except BaseException as error:
                        self.remember('command_'+name+'_log_sync',error)
            for row in reversed(self.journal):
                self.close_row(row)
            try:
                self.fsize_after=resource.getrlimit(resource.RLIMIT_FSIZE)
                need(self.fsize_after==self.fsize_before,'AMBIENT_FILE_SIZE_LIMIT_CHANGED')
            except BaseException as error:
                self.remember('command_file_size_limit_observation',error)
            try:
                self.retired_at=time.monotonic()
                need(self.retirement_deadline is not None and
                     self.retired_at<=self.retirement_deadline,
                     'OWN_COMMAND_RETIREMENT_DEADLINE_EXCEEDED')
            except BaseException as error:
                self.remember('owned_command_retirement_deadline',error)
            if self.process is not None and not self.joined and self.context.binding is not None:
                try:
                    self.context.binding.target.poison_unjoined_command()
                except BaseException as error:
                    self.remember('owned_unjoined_command_poison',error)

    def run(self):
        self.context.guard()
        self.context.command_index+=1
        self.stem=self.context.step/('command-%03d'%self.context.command_index)
        self.context.recorder.write_new(str(self.stem)+'.intent.json',{
            'argv':self.argv,'execution_argv':self.argv,
            'timeout_seconds':self.options['timeout'],
            'authority_fds_passed':list(self.options['pass_fds']),
            'mutation':self.context._android_mutation,'label':'Android command',
            'started_utc':self.context.recorder.now(),'automatic_retry':False})
        self.started=time.monotonic()
        self.last_observed_monotonic=self.started
        self.deadline=min(self.started+self.options['timeout'],self.context.deadline)
        try:
            self.capture()
        except BaseException as error:
            self.remember('command_capture',error)
        finally:
            self.finish()
        output={name:b''.join(self.buffers[name]) for name in ('stdout','stderr')}
        complete=all(self.eof.values()) and not self.errors and self.joined
        receipt={'ended_utc':self.context.recorder.now(),
            'seconds':time.monotonic()-self.started,'returncode':self.returncode,
            'timed_out':self.timed_out,'spawned':self.spawned,
            'error':self.errors[0] if self.errors else None,'errors':list(self.errors),
            'owned_command_joined':self.joined,
            'stdout_sha256':sha(output['stdout']),'stderr_sha256':sha(output['stderr']),
            'action_attempted':self.spawned and self.context._android_mutation,
            'automatic_retry':False,
            'output_capture':{'policy':'per-stream-private-prefix-v1','maximum_bytes':OUTPUT_LIMIT,
                'stored_bytes':dict(self.stored),'observed_bytes':dict(self.observed),
                'EOF':dict(self.eof),'complete':complete,'limit_exceeded':self.limit_exceeded,
                'prefix_only':not all(self.eof.values()),
                'no_stream_reads_after_first_failure':True,
                'observed_failure_preceded_capture_error':self.observed_failure_preceded_capture_error,
                'RLIMIT_FSIZE_before':list(self.fsize_before),
                'RLIMIT_FSIZE_after':list(self.fsize_after) if self.fsize_after is not None else None,
                'RLIMIT_FSIZE_modified':False},
            'owned_lifecycle':{'observation_deadline':self.deadline,
                'retirement_started':self.retirement_started,'retirement_deadline':self.retirement_deadline,
                'reap_started_at':self.reap_started_at,
                'reaped_at':self.reaped_at,'retired_at':self.retired_at,
                'retirement_deadline_met':self.retired_at is not None and
                    self.retirement_deadline is not None and self.retired_at<=self.retirement_deadline,
                'direct_child_reaped':self.spawned and self.joined,
                'session_observations':self.identity_observations,
                'signal_observations':self.signal_observations,
                'waitid_uses_WNOWAIT':True,'group_signals_after_reap_started':False,
                'all_tracked_FDs_closed':all(row['closed'] for row in self.journal),
                'FDs':[{k:v for k,v in row.items() if not k.startswith('_')} for row in self.journal],
                'escaped_sessions_or_Binder_descendants_qualified':False}}
        try:
            self.context.recorder.write_new(str(self.stem)+'.result.json',receipt)
        except BaseException as error:
            self.remember('command_result_record',error)
        captured=subprocess.CompletedProcess(self.argv,self.returncode,output['stdout'],output['stderr'])
        captured.host_timed_out=self.timed_out
        captured.capture_limit_exceeded=self.limit_exceeded
        captured.capture_retirement_error=self.capture_retirement_error
        captured.observed_failure_preceded_capture_error=self.observed_failure_preceded_capture_error
        captured.recorder_errors=list(self.errors)
        captured.recorder_spawned=self.spawned
        captured.recorder_joined=self.joined
        return captured


def command_with_bound(context,argv,options):
    """Bound only this command's private logs; do not change runtime rlimits."""
    need(options['close_fds'] is True and options['stdout']==subprocess.PIPE and
         options['stderr']==subprocess.PIPE and
         type(options['timeout']) in (int,float) and 0<options['timeout']<=70 and
         isinstance(options['pass_fds'],(tuple,list)) and len(options['pass_fds'])==7 and
         len(set(options['pass_fds']))==7 and
         all(type(fd) is int and fd>=3 for fd in options['pass_fds']),
         'EXACT_SHARED_RUNNER_PROTOCOL_REQUIRED')
    need(signal.getsignal(signal.SIGCHLD)==signal.SIG_DFL and
         hasattr(os,'P_PIDFD') and hasattr(os,'pidfd_open') and
         hasattr(signal,'pidfd_send_signal'),'OWN_UNREAPED_CHILD_PROTOCOL_REQUIRED')
    return _OwnedCommandCapture(context,argv,options).run()


class Context:
    def __init__(self,recorder,contract,target,environment,transport,main_guard,
                 step,plan,expected_init,deadline,fixture,scope,protected_uids):
        fixture.validate_scope(scope)
        need(contract.sha256==SHARED_MANIFEST and
             scope['Main_epoch']==MAIN_EPOCH and scope['package']==PACKAGE,
             'EXACT_CURRENT_NDK_CONTEXT_REQUIRED')
        need(type(deadline) in (int,float) and time.monotonic()<deadline,
             'FRESH_FIXTURE_CONTEXT_DEADLINE')
        self.recorder,self.contract,self.fixture=recorder,contract,fixture
        self.scope=json.loads(json.dumps(scope,sort_keys=True))
        self.scope_text=json.dumps(self.scope,sort_keys=True,separators=(',',':'))
        self.target,self.main_guard,self.step=target,main_guard,step
        self.command_index=0
        self.action_attempted=False
        self._android_mutation=False
        self.binding=types.SimpleNamespace(target=target)
        self.artifacts=None
        self.closed=self.poisoned=False
        self.deadline=deadline
        self.protected_uids=set(protected_uids)
        self.plan=[(list(a),b,c) for a,b,c in plan]
        self.next_command=0
        def record(kind,value):
            recorder.write_new(self.step/('transport-%03d.%s.json'%(value['sequence'],kind)),value)
        def runner(argv,**options):
            return command_with_bound(self,argv,options)
        self.transport=transport.BoundArun(target=target,environment=environment,
            guard=lambda action_attempted:self.guard(attempted=self.action_attempted),
            record=record,epoch_sha256=MAIN_EPOCH,init_pid=expected_init,
            package=PACKAGE,uid=scope['uid'],interactive_production=True,
            fixture_scope=scope,fixture_contract=fixture,runner=runner)

    def guard(self,attempted=False):
        self.fixture.validate_scope(self.scope)
        need(type(attempted) is bool and not self.closed and time.monotonic()<self.deadline,
             'OPEN_FIXED_FIXTURE_CONTEXT_DEADLINE')
        need(json.dumps(self.scope,sort_keys=True,separators=(',',':'))==self.scope_text,
             'FIXTURE_SCOPE_CHANGED')
        self.main_guard()
        self.target.verify()
        if self.artifacts is not None:
            self.artifacts.verify_held()

    def android(self,argv,timeout=20,*,mutation=False):
        try:
            need(not self.closed and not self.poisoned,'FAILED_FIXTURE_CONTEXT_CANNOT_RETRY')
            need(self.next_command<len(self.plan),'FIXED_FIXTURE_PLAN_EXHAUSTED')
            need(type(mutation) is bool and
                 (list(argv),timeout,mutation)==self.plan[self.next_command],
                 'ONLY_EXACT_ORDERED_FIXTURE_COMMAND_ALLOWED')
            self.next_command+=1
            self._android_mutation=mutation
            return self.transport(argv,timeout)
        except BaseException:
            self.poisoned=True
            raise
        finally:
            self._android_mutation=False

    def close(self):
        self.closed=True
        self.target.close()


def open_context(sources,fixture,scope,step,plan,result,deadline,admission=None):
    if admission is None:
        fixture.pending_gate()
    fixture.validate_scope(scope)
    need(scope['phase'] in ('run','retire') and type(scope['uid']) is int,
         'ACTUAL_OWN_RUNTIME_PHASE_ADMISSION_REQUIRED')
    admission.verify_phase(sources,fixture,scope,step,deadline)
    # Only the separately pinned runtime worker supplies this live phase lease.
    # Installation is unavailable through this runtime source manifest.
    sources.verify()
    raw=sources.fixed_reference(INSTALLED_SHARED/'source_contract.py',CONTRACT_BYTES,CONTRACT_SHA)
    source=sources.module(raw,INSTALLED_SHARED/'source_contract.py','ndk_shared_contract')
    contract=source.SourceContract(INSTALLED_SHARED/'source-manifest.json',SHARED_MANIFEST)
    recorder=contract.load('recorder.py','ndk_shared_command_only')
    held=contract.load('references/held_runtime_r5.py','ndk_actual_held_main')
    binding=contract.load('main_binding.py','ndk_shared_classpath_only')
    current=contract.load('current_baseline_guard.py','ndk_current_baseline_guard')
    need(contract.files['current_baseline_guard.py']['sha256']==CURRENT_GUARD_SHA,
         'CURRENT_GUARD_PIN_CHANGED')
    baseline=current.current_baseline()
    protected=baseline_binding(current,baseline,fixture,scope)
    _,epoch,_,_=current.source_modules()
    target=None
    def guard():
        admission.verify_phase(sources,fixture,scope,step,deadline)
        need(time.monotonic()<deadline,'FIXTURE_PHASE_DEADLINE')
        sources.verify()
        contract.verify()
        helper=source.bounded_file(source.HELPER_PATH,source.HELPER_BYTES)
        need(len(helper)==source.HELPER_BYTES and sha(helper)==source.HELPER_SHA,
             'HELD_HELPER_CONTENT_CHANGED')
        observed=current.current_guard(baseline,action_attempted=False)
        if target is not None:
            target.verify()
        return observed
    result['Main_before']=guard()
    result['shared_helper']=source.verify_shared_helper()
    expected=baseline['framework_epoch']['binding']['processes']['init']
    proc=os.open('/proc/'+str(expected['host_pid']),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    first=None
    try:
        actual=held.proc_identity_at(proc,expected['host_pid'],min(deadline,time.monotonic()+3))
    except BaseException as error:
        first=error
        raise
    finally:
        try:
            os.close(proc)
        except BaseException as close_error:
            if first is None:
                raise
            first.add_note('fixture init proc FD close:'+type(close_error).__name__)
    need(binding.same_epoch_identity(actual,expected),'FIXED_MAIN_INIT_IDENTITY_CHANGED')
    try:
        target=held.HeldTarget(actual,source.HELPER_PATH,source.HELPER_SHA)
        guard()
        app=contract.load('references/android_app.py','ndk_discovery_only')
        discovery=sources.load('current_discovery.py','ndk_current_discovery')
        need(discovery.BASELINE_SHA==BASELINE_SHA and
             discovery.QUALIFICATION_SHA==QUALIFICATION_SHA and discovery.MAIN_EPOCH==MAIN_EPOCH,
             'CURRENT_DISCOVERY_SOURCE_BINDING_REQUIRED')
        init,discovered,status=discovery.discover_current(app,baseline,epoch,guard)
        need(init==expected['host_pid'] and status['host_pid']==baseline['status']['host_pid'],
             'FIXED_MAIN_DISCOVERY_CHANGED')
        values,classpath=binding.main_classpaths(held,target,baseline['framework_epoch'],epoch,guard)
        need(all(discovered.get(k)==v for k,v in values.items()),'CLASSPATH_DISCOVERY_CHANGED')
        transport=sources.load('fixture_transport.py','ndk_bound_transport')
        environment=transport.environment_values(discovered)
        context=Context(recorder,contract,target,environment,transport,guard,
            step,plan,expected['host_pid'],deadline,fixture,scope,protected)
        # Full classpaths/identity are retained privately at the owned step.
        recorder.write_new(step/'held-main-binding.private.json',{
            'target':target.record,'classpath':classpath,'shared_helper':result['shared_helper'],
            'fixture_scope':scope,'R6_primitive_manifest':SHARED_MANIFEST,
            'commercial_Flow_or_scope_instantiated':False})
        result['held_main_binding']={'file':'held-main-binding.private.json',
            'same_current_Main8':True,'six_namespace_FDs':6,
            'numeric_PID_namespace_entry':False,'private_body_exported':False}
        def independent_guard():
            admission.verify_phase(sources,fixture,scope,step,deadline)
            sources.verify()
            contract.verify()
            return current.current_guard(baseline,action_attempted=False)
        return context,binding,independent_guard
    except BaseException as primary:
        if target is not None:
            try:
                target.close()
            except BaseException as secondary:
                primary.add_note('held target close:'+type(secondary).__name__)
        raise


class InstalledFixture:
    """One actual APK and two exact owned data directories; no commercial data."""
    def __init__(self,context,metadata,path,build,binding,expected=None):
        self.context,self.binding,self.build=context,binding,build
        need(metadata['package']==PACKAGE and metadata['user']==0 and
             metadata['uid'] not in context.protected_uids,'NEW_FIXED_FIXTURE_UID_REQUIRED')
        need(context.scope['uid'] is None or metadata['uid']==context.scope['uid'],
             'INSTALLED_UID_DIFFERS_FROM_SCOPE')
        self.metadata=dict(metadata)
        self.path=path
        self.expected=expected
        self.opened=[]
        self.record=None
        self.closed=False
        try:
            fd=context.target.open_root(path,os.O_RDONLY|os.O_NOFOLLOW)
            self.opened.append(fd)
            row=self._hash(fd)
            directories={}
            for kind in ('user','user_de'):
                name='/data/'+kind+'/0/'+PACKAGE
                data_fd=context.target.open_root(name,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW)
                self.opened.append(data_fd)
                value=identity(data_fd)
                need(stat.S_ISDIR(value['mode']) and value['uid']==metadata['uid'],
                     'FIXTURE_DATA_DIRECTORY_UID_CHANGED')
                directories[kind]={'path':name,**{k:value[k] for k in
                    ('device','inode','mode','uid','gid')}}
            self.record={'package':PACKAGE,'uid':metadata['uid'],'user':0,
                'version_code':metadata['version_code'],'artifact':row,'directories':directories,
                'signer_sha256_from_identical_build_APK':build['signer_sha256'],
                'signer_independently_read_on_device':False}
            if expected is not None:
                need(self.record==expected,'ACTUAL_INSTALLED_FIXTURE_TUPLE_CHANGED')
            self.verify_held()
            context.artifacts=self
        except BaseException as primary:
            try:
                self.close()
            except BaseException as secondary:
                primary.add_note('installed fixture FD close:'+type(secondary).__name__)
            raise

    def _hash(self,fd):
        first=identity(fd)
        need(stat.S_ISREG(first['mode']) and first['nlink']==1 and
             first['uid']==first['gid']==1000 and not first['mode']&0o022 and
             first['bytes']==self.build['APK']['bytes'] and 0<first['bytes']<=APK_LIMIT,
             'ACTUAL_INSTALLED_APK_SHAPE_DIFFERS')
        os.lseek(fd,0,os.SEEK_SET)
        count=0
        digest=hashlib.sha256()
        deadline=min(self.context.deadline,time.monotonic()+HASH_SECONDS)
        while True:
            need(time.monotonic()<deadline,'FIXTURE_APK_HASH_DEADLINE')
            block=os.read(fd,min(65536,first['bytes']+1-count))
            if not block:
                break
            count+=len(block)
            need(count<=first['bytes'],'FIXTURE_APK_GREW')
            digest.update(block)
        need(count==first['bytes'] and identity(fd)==first and
             digest.hexdigest()==self.build['APK']['sha256'],
             'INSTALLED_APK_NOT_EXACT_ORIGINAL_SIGNED_BUILD')
        return {'path':self.path,'file':first,'sha256':digest.hexdigest()}

    def verify_held(self):
        need(not self.closed and self.record is not None and len(self.opened)==3,
             'OPEN_FIXED_INSTALLED_FIXTURE_REQUIRED')
        self.context.target.verify()
        need(identity(self.opened[0])==self.record['artifact']['file'],'HELD_FIXTURE_APK_CHANGED')
        for index,kind in enumerate(('user','user_de'),1):
            value=identity(self.opened[index])
            expected=self.record['directories'][kind]
            need(all(value[k]==expected[k] for k in ('device','inode','mode','uid','gid')),
                 'HELD_FIXTURE_DATA_DIRECTORY_CHANGED')
            current=self.context.target.open_root(expected['path'],os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW)
            first=None
            try:
                row=identity(current)
                need(all(row[k]==expected[k] for k in ('device','inode','mode','uid','gid')),
                     'NAMED_FIXTURE_DATA_DIRECTORY_CHANGED')
            except BaseException as error:
                first=error
                raise
            finally:
                try:
                    os.close(current)
                except BaseException as close_error:
                    if first is None:
                        raise
                    first.add_note('named data FD close:'+type(close_error).__name__)
        # Original RunAllTests writes /data/data, so qualify that named view
        # against the same held installed user-0 data directory. A usual alias
        # layout is not assumed, and no other package path is read.
        alias=self.context.target.open_root('/data/data/'+PACKAGE,
            os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW)
        primary=None
        try:
            actual=identity(alias)
            expected=self.record['directories']['user']
            need(all(actual[k]==expected[k] for k in ('device','inode','mode','uid','gid')),
                 'ORIGINAL_XML_DATA_VIEW_DIFFERS_FROM_OWN_USER_ZERO_DIRECTORY')
        except BaseException as error:
            primary=error
            raise
        finally:
            try:
                os.close(alias)
            except BaseException as close_error:
                if primary is None:
                    raise
                primary.add_note('original XML data view FD close:'+type(close_error).__name__)
        raw,_=self.context.target.read_file('/data/system/packages.list',1048576)
        self.binding.package_uids(raw,{PACKAGE:self.metadata['uid']})
        del raw
        self.context.target.verify()

    def revalidate(self):
        self.verify_held()
        row=self._hash(self.opened[0])
        named=self.context.target.open_root(self.path,os.O_RDONLY|os.O_NOFOLLOW)
        first=None
        try:
            need(identity(named)==row['file'],'NAMED_FIXTURE_APK_CHANGED')
        except BaseException as error:
            first=error
            raise
        finally:
            try:
                os.close(named)
            except BaseException as close_error:
                if first is None:
                    raise
                first.add_note('named APK FD close:'+type(close_error).__name__)
        need(row==self.record['artifact'],'FIXTURE_APK_AFTER_DIFFERS')
        return dict(self.record)

    def xml_absent(self):
        need(not self.context.target.exists(self.context.fixture.XML_PATH),
             'STALE_NATIVE_XML_PREEXISTS')

    def read_fresh_xml(self,run_observation,retirement_observation):
        need(run_observation.get('pre_run_XML_absent') is True and
             run_observation.get('instrumentation_verified') is True and
             run_observation.get('installed_before')==self.record and
             run_observation.get('scope',{}).get('phase')=='run' and
             run_observation['scope']['uid']==self.metadata['uid'] and
             retirement_observation.get('scope',{}).get('phase')=='retire' and
             retirement_observation['scope']['uid']==self.metadata['uid'] and
             run_observation['scope']['attempt_nonce'] !=
                retirement_observation['scope']['attempt_nonce'] and
             retirement_observation.get('force_stop_completed') is True and
             retirement_observation.get('two_complete_empty_own_UID_tables') is True and
             retirement_observation.get('task_set_restored') is True,
             'FRESH_INSTRUMENTATION_AND_INDEPENDENT_RETIREMENT_REQUIRED')
        self.revalidate()
        deadline=min(self.context.deadline,time.monotonic()+5)
        raw,record=self.context.target.read_file(self.context.fixture.XML_PATH,
            self.context.fixture.MAX_XML,single_link=True,deadline=deadline)
        need(record['uid']==self.metadata['uid'] and record['nlink']==1 and
             not record['mode']&0o022,'XML_IS_NOT_OWNED_BY_INSTALLED_FIXTURE')
        again,named=self.context.target.read_file(self.context.fixture.XML_PATH,
            self.context.fixture.MAX_XML,single_link=True,deadline=deadline)
        need(named==record and again==raw,'OWN_XML_NAMED_CONTENT_CHANGED')
        value=self.context.fixture.native_xml(raw)
        self.verify_held()
        value['held_file']=record
        value['same_actual_fixture_UID']=self.metadata['uid']
        value['run_attempt_nonce']=run_observation['scope']['attempt_nonce']
        value['retirement_attempt_nonce']=retirement_observation['scope']['attempt_nonce']
        value['freshness_and_same_owned_UID_binding_still_required']=False
        return value

    def close(self):
        self.closed=True
        failures=[]
        count=len(self.opened)
        for fd in reversed(self.opened):
            try:
                os.close(fd)
            except BaseException as error:
                failures.append({'type':type(error).__name__,'errno':getattr(error,'errno',None)})
        self.opened=[]
        if self.context.artifacts is self:
            self.context.artifacts=None
        need(not failures,'FIXTURE_ARTIFACT_FD_CLOSE_FAILED')
        return {'held_APK_and_data_FDs_closed':count,'all_tracked_artifact_FDs_closed':True}
