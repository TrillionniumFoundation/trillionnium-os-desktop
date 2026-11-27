"""Single-threaded owner of the Clock worker and passive Notify sibling.

No Main process is signalled. The business worker owns its Android command
children; this parent owns only its two exact children and kernel-adopted
descendants. All captures are bounded pipes, with no RLIMIT_FSIZE inheritance.
"""
import copy
import os
from pathlib import Path
import select
import selectors
import signal
import socket
import subprocess
import time

LIFECYCLE={'path': '/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2/source/camera-display/capture_lifecycle.py', 'bytes': 25312, 'sha256': '6a0ba9438b10740a593e2d90962420e04868465a0fb55c0ce2e03afdb835e877'}
LIMITS={'startup_seconds':15,'worker_lease_seconds':240,'worker_cleanup_seconds':45,
    'retirement_seconds':30,'monitor_seconds':240,'monitor_stream_bytes':1048576,
    'worker_stream_bytes':16777216,'control_packet_bytes':32768,'maximum_control_requests':8,
    'maximum_stdout_receipts':8192,'maximum_read_bytes_per_pump':262144}


class SupervisorCancelled(BaseException):pass


def life_record():
    return {'child_started':False,'child_reaped':False,'pidfd_closed':True,
        'owned_tree_cleanup_complete':False,'descendants':[]}


class Supervisor:
    def __init__(self,c,plan_ref,prep_ref,components,request_ref):
        self.c=c;self.plan_ref=plan_ref;self.prep_ref=prep_ref;self.components=components
        self.runtime=components['app_runtime.py'];self.channel_module=components['clock_monitor_channel.py']
        self.binding_module=components['clock_notify_binding.py']
        self.plan,self.source,self.baseline,_,self.packet,self.task=components['clock_plan.py'].validate_plan(c,plan_ref,prep_ref)
        c.need(self.plan['kind']=='expiry06' and c.parse(c.read_ref(request_ref))=={'plan':plan_ref},
            'ONLY_ORIGINAL_EXPIRY_REQUIRES_CONTINUOUS_MONITOR')
        self.request_ref=request_ref;self.root=Path(self.plan['case_root'])
        c.need(not (self.root/'execute-once.json').exists(),'NO_REPLAY_OF_CLOCK_CASE')
        self.out=c.private_dir(self.root/'notify-supervisor',create=True)
        self.started=time.monotonic();self.deadline=min(self.started+300,self.baseline.live.deadline)
        self.reaper=None;self.selector=None;self.channel=None;self.actors={};self.pipe_map={}
        self.sequence=0;self.pending_reply=None;self.pending_reply_deadline=None;self.snapshots=0
        self.monitor_binding=None;self.monitor_started=None;self.monitor_deadline=None
        self.monitor_start_used=False;self.monitor_stop_used=False;self.monitor_final=None
        self.channel_eof=False;self.retiring=False;self.committed=False
        self.signals=[];self.after_commit_signals=[];self.first=None;self.inner=None
        self.record={'schema':'pocket4-clock-notify-supervisor-result-v1','state':'STARTING',
            'plan':plan_ref,'preparation':prep_ref,'limits':copy.deepcopy(LIMITS),'events':[],
            'errors':[],'received_signals':self.signals,'actors':{},'automatic_retry':False,
            'Main_signals':0,'Android_UI_actions_by_supervisor':0,'notification_method_calls':0,
            'service_activation_requests':0,'whole_app_business_accepted':False}

    def remember(self,error,stage):
        row={'stage':stage,'type':type(error).__name__,'message':str(error),'errno':getattr(error,'errno',None)}
        if self.first is None:self.first=row
        self.record['errors'].append(row)

    def cancelled(self,number,frame):
        target=self.after_commit_signals if self.committed else self.signals
        if len(target)<32:target.append({'signal':number,'monotonic_ns':time.monotonic_ns(),'retiring':self.retiring})
        if not self.retiring and not self.committed:raise SupervisorCancelled('CLOCK_NOTIFY_SUPERVISOR_CANCELLED')

    def terminal(self,role):
        actor=self.actors.get(role)
        if actor is None or actor['process'] is None or actor['lifecycle']['child_reaped']:return None
        return self.reaper.peek(actor['process'].pid,actor['pidfd'])

    def actor(self,role,argv,*,pass_fds=(),alex=False):
        self.c.need(role in ('business','monitor') and role not in self.actors,'ONCE_EXACT_CLOCK_SIBLING')
        bound=LIMITS['monitor_stream_bytes'] if role=='monitor' else LIMITS['worker_stream_bytes']
        item={'process':None,'pidfd':None,'lifecycle':life_record(),'streams':{},'bound':bound,'receipts':[]}
        self.actors[role]=item;self.record['actors'][role]=item['lifecycle']
        for name in ('stdout','stderr'):
            item['streams'][name]={'buffer':bytearray(),'eof':False,'closed':False,'pipe':None,
                'file':open(self.out/(role+'.'+name),'xb'),'bytes_observed':0}
        env=dict(self.c.HOST_ENV)
        if alex:env.update(HOME='/home/alex',XDG_RUNTIME_DIR='/run/user/1000',
            DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/1000/bus')
        for key in ('DROIDLOOM_NATIVE_LEAF_FACTS_FD','DROIDLOOM_NATIVE_LEAF_GUARD_FD'):env.pop(key,None)
        if role=='business':
            self.c.need(not alex,'NORMAL_CLOCK_WORKER_OWNER_REQUIRED')
            env,pass_fds=self.baseline.live.inherit_for_host(argv,env,pass_fds)
        process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            start_new_session=True,close_fds=True,pass_fds=tuple(pass_fds),env=env,
            user=1000 if alex else 0,group=1000 if alex else 0,extra_groups=())
        item['process']=process
        item['lifecycle'].update(child_started=True,pid=process.pid,uid=1000 if alex else 0)
        # Retain Popen immediately. A subsequent pidfd/open/register failure
        # still leaves exact unreaped-child cleanup authority.
        for name in ('stdout','stderr'):
            stream=item['streams'][name];pipe=getattr(process,name);stream['pipe']=pipe
            os.set_blocking(pipe.fileno(),False);self.pipe_map[pipe.fileno()]=(role,name)
            self.selector.register(pipe,selectors.EVENT_READ,('pipe',role,name))
        item['pidfd']=os.pidfd_open(process.pid,0);item['lifecycle']['pidfd_closed']=False
        self.c.need(os.getpgid(process.pid)==process.pid and os.getsid(process.pid)==process.pid,
            'CLOCK_SIBLING_PRIVATE_SESSION')
        self.record['events'].append({'event':role+'_spawned','pid':process.pid,'monotonic_ns':time.monotonic_ns()})
        return item

    def setup(self):
        self.c.need(os.getuid()==os.geteuid()==os.getgid()==os.getegid()==0,'ROOT_CLOCK_SUPERVISOR_CONTEXT')
        life=self.c.module(LIFECYCLE,'clock_unchanged_owned_lifecycle')
        self.reaper=life.OwnChildReaper(protected_pids=self.baseline.protected_pids)
        self.reaper.begin();self.selector=selectors.DefaultSelector()
        parent,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
        self.channel=parent
        try:
            for sock in (parent,child):sock.setsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED,1)
            parent.setblocking(False)
            parent_value={'schema':'pocket4-clock-notify-supervisor-parent-v1','plan':self.plan_ref,
                'preparation':self.prep_ref,'case_root':str(self.root),'parent':self.runtime.process(self.c,os.getpid()),
                'boot_id':self.runtime.boot(),'client_socket':self.channel_module.socket_identity(child.fileno()),
                'limits':copy.deepcopy(LIMITS),'automatic_retry':False}
            self.parent_ref=self.c.write_new(self.out/'parent.json',parent_value,0o400)
            copied_entry=next(row for row in self.task['files'] if Path(row['path']).name=='clock_entry.py')
            self.c.read_ref(copied_entry)
            entry=next(row for row in self.packet['files'] if Path(row['path']).name=='clock_entry.py')
            self.c.need((entry['bytes'],entry['sha256'])==(copied_entry['bytes'],copied_entry['sha256']),
                'TASK_COPY_MUST_MATCH_CANONICAL_FIXED_CLOCK_ENTRY')
            self.c.read_ref(entry);self.c.read_ref(self.request_ref)
            argv=['/usr/bin/python3','-I','-B',entry['path'],'--preparation',self.prep_ref['path'],
                '--expect-preparation-sha256',self.prep_ref['sha256'],'execute-worker',
                '--request',self.request_ref['path'],'--expect-request-sha256',self.request_ref['sha256'],
                '--monitor-fd',str(child.fileno()),'--monitor-parent',self.parent_ref['path'],
                '--expect-monitor-parent-sha256',self.parent_ref['sha256']]
            self.record['worker_argv']=argv
            self.c.need(time.monotonic()<self.started+LIMITS['startup_seconds'],'CLOCK_SUPERVISOR_STARTUP_BUDGET')
            item=self.actor('business',argv,pass_fds=(child.fileno(),))
            item['identity']=self.runtime.process(self.c,item['process'].pid)
            self.c.need(item['identity']['parent']==os.getpid(),'ACTUAL_DIRECT_CLOCK_WORKER')
            self.record['business_process']=item['identity']
            self.selector.register(parent,selectors.EVENT_READ,('control',None,None))
        finally:child.close()

    def verify_business(self):
        item=self.actors['business'];self.c.need(not item['lifecycle']['child_reaped']
            and self.terminal('business') is None
            and self.runtime.process(self.c,item['process'].pid)==item['identity'],
            'ACTUAL_LIVE_CLOCK_WORKER_GENERATION_REQUIRED')

    def verify_phase(self,ref):
        phase=self.c.parse(self.c.read_ref(ref,131072))
        self.c.need(ref['path'] in (str(self.root/'phase-business.json'),str(self.root/'phase-final-cleanup.json'))
            and phase['schema']=='pocket4-clock-current-phase-v1' and phase['kind']=='expiry06'
            and phase['owner_pid']==self.actors['business']['process'].pid
            and time.monotonic()<phase['deadline_monotonic'],'CURRENT_ACTUAL_CLOCK_OBSERVATION_PHASE')
        once=self.c.parse(self.c.read_ref(self.c.regular(self.root/'execute-once.json',contents=False)))
        self.c.need(once['plan']==self.plan_ref and once['kind']=='expiry06'
            and once['operator']==self.actors['business']['identity']
            and once['lease_deadline_monotonic']==once['started_monotonic']+240
            and once['absolute_final_deadline_monotonic']==once['started_monotonic']+285,
            'ORIGINAL_ABSOLUTE_CLOCK_WORKER_LEASE')
        if phase['phase']=='business':
            self.c.need(phase['baseline']==self.source['baseline'] and phase['qualification']==self.source['qualification']
                and phase['started_monotonic']==once['started_monotonic']
                and phase['deadline_monotonic']==once['lease_deadline_monotonic'],'ACTUAL_BUSINESS_MONITOR_PHASE')
        else:self.c.need(phase['phase']=='final_cleanup' and phase['deadline_monotonic']<=once['absolute_final_deadline_monotonic'],
            'ORIGINAL_CLOCK_CLEANUP_PHASE_BOUND')
        return phase

    def start_monitor(self,value):
        self.c.need(set(value)=={'binding','phase'} and not self.monitor_start_used and not self.monitor_stop_used,
            'ONCE_PASSIVE_CLOCK_MONITOR_START');self.monitor_start_used=True
        phase=self.verify_phase(value['phase']);self.c.need(phase['phase']=='business','MONITOR_START_BEFORE_TIMER_ONLY')
        self.baseline.guard();ref=value['binding'];binding=self.c.parse(self.c.read_ref(ref,131072))
        expected_presenter=self.baseline.docs['runtime_observation']['host_processes']['presenter']
        self.c.need(ref['path']==str(self.root/'notify-binding.json')
            and set(binding)=={'schema','baseline','qualification','phase','binding','tool','baseline_state','queries',
                'service_activation_requests','notification_method_calls','Android_UI_actions'}
            and binding['schema']=='pocket4-clock-current-notify-binding-v1'
            and binding['baseline']==self.source['baseline'] and binding['qualification']==self.source['qualification']
            and binding['phase']==value['phase'] and binding['binding']['presenter']==expected_presenter
            and binding['baseline_state']['record'] is None and len(binding['queries'])==6
            and all(binding[key]==0 for key in ('service_activation_requests','notification_method_calls','Android_UI_actions')),
            'ACTUAL_CURRENT_PRESENTER_AND_BUS_BINDING')
        for query in binding['queries']:self.c.read_ref(query)
        tool=self.binding_module.tool_identity();self.c.need(tool==binding['tool'],'MONITOR_TOOL_CHANGED_AFTER_BINDING')
        argv=self.binding_module.monitor_argv(binding['binding'])
        self.monitor_binding=ref;self.monitor_started=time.monotonic();self.monitor_deadline=self.monitor_started+240
        self.c.write_new(self.out/'monitor-start-intent.json',{'argv':argv,'binding':ref,'phase':value['phase'],
            'max_bytes_per_stream':1048576,'max_seconds':240,'uid':1000,'gid':1000,'maximum_messages':32,
            'original_timeout_wrapper_replaced_by_exact_parent_pidfd_deadline':True,'automatic_retry':False})
        self.verify_business();self.c.need(time.monotonic()<phase['deadline_monotonic'],'MONITOR_SPAWN_AFTER_PHASE_FORBIDDEN')
        actor=self.actor('monitor',argv,alex=True)
        self.c.need(self.binding_module.tool_identity()==tool,'MONITOR_TOOL_CHANGED_DURING_SPAWN')
        return {'state':'MONITOR_STARTED','child_started':True,'pid':actor['process'].pid,
            'binding':ref,'match':self.binding_module.monitor_match(binding['binding']),
            'subscription_ready_verified':False,'absence_proves_delivery_failure':False,
            'service_activation_requests':0,'UI_actions':0,'notification_method_calls':0}

    def snapshot(self,value):
        self.c.need(set(value)=={'phase'} and self.monitor_binding is not None and not self.monitor_stop_used,
            'CURRENT_STARTED_NOTIFY_MONITOR_SNAPSHOT');self.verify_phase(value['phase'])
        self.snapshots+=1;self.c.need(self.snapshots<=5,'ORIGINAL_BOUNDED_NOTIFY_OBSERVATION_POINTS')
        item=self.actors['monitor'];stream=item['streams']['stdout'];self.drain_available_pipes()
        stdout=self.c.write_new(self.out/('snapshot-%02d.stdout'%self.snapshots),bytes(stream['buffer']))
        receipts=self.c.write_new(self.out/('snapshot-%02d.receipts.json'%self.snapshots),item['receipts'])
        observed=self.terminal('monitor')
        return {'stdout':stdout,'receipts':receipts,'errors':[], 'binding':self.monitor_binding,
            'running':observed is None,'bounded':True,
            'pipe_eof':{name:entry['eof'] for name,entry in item['streams'].items()},
            'terminal_observation':None if observed is None else self.reaper.observed(observed),
            'started_monotonic':self.monitor_started,'monitor_deadline_monotonic':self.monitor_deadline}

    def signal_exact(self,role,number):
        item=self.actors.get(role)
        if item is None or item['process'] is None or item['lifecycle']['child_reaped']:return
        process=item['process'];self.reaper.signal_target(process.pid)
        if self.reaper.peek(process.pid,item['pidfd']) is None:
            if item['pidfd'] is not None:signal.pidfd_send_signal(item['pidfd'],number)
            else:os.kill(process.pid,number)
            self.record['events'].append({'event':role+'_signal','signal':number,'pid':process.pid,'monotonic_ns':time.monotonic_ns()})

    def stop_monitor(self,value):
        self.c.need(set(value)=={'started_request_sent'} and type(value['started_request_sent']) is bool
            and not self.monitor_stop_used,'ONCE_NOTIFY_MONITOR_RETIREMENT');self.monitor_stop_used=True
        item=self.actors.get('monitor')
        if item is None:
            self.monitor_final={'child_joined':False,'reader_joined':True,'returncode':None,'cleanup_error':None,
                'pipe_eof':{'stdout':True,'stderr':True},'all_owned_monitor_writers_closed':True}
            return self.monitor_final
        self.signal_exact('monitor',signal.SIGTERM)
        deadline=time.monotonic()+3
        while time.monotonic()<deadline and (self.terminal('monitor') is None
                or not all(stream['eof'] for stream in item['streams'].values())):
            self.pump(.05,control=False)
        self.reaper.retire_leader(item['process'],item['pidfd'],item['lifecycle'],self.remember,time.monotonic()+3)
        self.c.need(item['lifecycle']['child_reaped'],'MONITOR_LEADER_RETIREMENT_UNKNOWN')
        # While the business sibling still owns its children, any other direct
        # child here is an escaped monitor descendant. Do not retire_adopted
        # while it could also target the still-live business principal.
        children=self.reaper.children()
        self.c.need(children==[self.actors['business']['process'].pid],
            'MONITOR_HAS_ADOPTED_DESCENDANT_CANCEL_BUSINESS_BEFORE_GLOBAL_RETIREMENT')
        self.drain_available_pipes()
        self.c.need(all(stream['eof'] for stream in item['streams'].values()),'MONITOR_BOTH_PIPE_EOF_REQUIRED')
        self.monitor_final={'child_joined':True,'owned_process_joined':True,'reader_joined':True,
            'all_owned_monitor_writers_closed':True,'pipe_eof':{'stdout':True,'stderr':True},
            'returncode':item['process'].returncode,'bytes':{name:len(row['buffer']) for name,row in item['streams'].items()},
            'cleanup_error':None,'errors':[],'single_thread_parent_reader':True,
            'no_reader_thread_created':True,'notification_method_calls':0,'UI_actions':0,'service_activation_requests':0}
        return self.monitor_final

    def control(self):
        self.c.need(self.pending_reply is None,'NO_SECOND_NOTIFY_REQUEST_WHILE_REPLY_PENDING')
        item=self.actors['business'];self.verify_business()
        try:row=self.channel_module.receive(self.channel,(item['process'].pid,0,0),self.c.parse)
        except BlockingIOError:return
        self.c.need(type(row) is dict and set(row)==self.channel_module.REQUEST_KEYS
            and row['schema']==self.channel_module.SCHEMA and row['sequence']==self.sequence+1
            and row['parent']==self.parent_ref and row['plan']==self.plan_ref
            and row['kind'] in ('start','snapshot','stop') and type(row['value']) is dict
            and self.sequence<LIMITS['maximum_control_requests'],'EXACT_TYPED_NOTIFY_WORKER_REQUEST')
        self.sequence=row['sequence'];kind=row['kind']
        result={'start':self.start_monitor,'snapshot':self.snapshot,'stop':self.stop_monitor}[kind](row['value'])
        reply={'schema':self.channel_module.SCHEMA,'sequence':self.sequence,'kind':kind,'ok':True,'value':result,'error':None}
        raw=self.c.canonical(reply);self.c.need(len(raw)<=self.channel_module.MAX_PACKET,'BOUNDED_NOTIFY_REPLY')
        self.pending_reply=raw;self.pending_reply_deadline=time.monotonic()+1
        self.selector.modify(self.channel,selectors.EVENT_WRITE,('control',None,None))

    def send_reply(self):
        self.c.need(self.pending_reply is not None,'CURRENT_NOTIFY_REPLY')
        self.verify_business()
        self.c.need(time.monotonic()<self.pending_reply_deadline,'NOTIFY_REPLY_BACKPRESSURE_DEADLINE')
        try:count=self.channel.send(self.pending_reply,socket.MSG_NOSIGNAL)
        except BlockingIOError:return
        self.c.need(count==len(self.pending_reply),'ATOMIC_NOTIFY_PARENT_REPLY')
        self.pending_reply=None;self.pending_reply_deadline=None
        self.selector.modify(self.channel,selectors.EVENT_READ,('control',None,None))

    def close_pipe(self,stream):
        pipe=stream['pipe']
        if pipe is not None and not stream['closed']:
            fd=pipe.fileno()
            if fd in self.pipe_map:
                self.selector.unregister(pipe);del self.pipe_map[fd]
            pipe.close();stream['closed']=True

    def read_pipe(self,role,name,budget):
        item=self.actors[role];stream=item['streams'][name]
        remain=item['bound']-len(stream['buffer'])
        try:data=os.read(stream['pipe'].fileno(),min(65536,remain+1,budget))
        except BlockingIOError:return 0
        if not data:
            stream['eof']=True;self.close_pipe(stream);return 0
        stream['bytes_observed']+=len(data);chunk=data[:remain]
        stream['file'].write(chunk);stream['buffer'].extend(chunk)
        if role=='monitor' and name=='stdout' and chunk:
            item['receipts'].append({'end_byte_offset':len(stream['buffer']),
                'monotonic_ns':time.monotonic_ns(),'realtime_ns':time.time_ns()})
            self.c.need(len(item['receipts'])<=LIMITS['maximum_stdout_receipts'],'NOTIFY_LOCAL_RECEIPT_BOUND')
        if len(data)>remain:
            # Stop reading both streams at the first extra byte. Retirement is
            # still mandatory, but overflow cannot produce a successful EOF.
            for other in item['streams'].values():self.close_pipe(other)
            raise RuntimeError('CLOCK_'+role.upper()+'_OUTPUT_BOUND_EXCEEDED:'+name)
        return len(data)

    def drain_available_pipes(self):
        budget=LIMITS['maximum_read_bytes_per_pump']
        for fd in list(self.pipe_map):
            if budget<=0:break
            if fd not in self.pipe_map:continue
            role,name=self.pipe_map[fd];budget-=self.read_pipe(role,name,budget)

    def pump(self,timeout,*,control=True):
        self.reaper.single_thread();budget=LIMITS['maximum_read_bytes_per_pump']
        for key,mask in self.selector.select(max(0,min(.1,timeout))):
            kind,role,name=key.data
            if kind=='pipe':
                if key.fd in self.pipe_map and budget>0:budget-=self.read_pipe(role,name,budget)
            elif control:
                if self.pending_reply is None:
                    # EOF is expected only after the typed stop completed. The
                    # worker may still be doing its final independent guards.
                    try:peek=self.channel.recv(1,socket.MSG_PEEK)
                    except BlockingIOError:continue
                    if not peek:
                        self.c.need(self.monitor_stop_used,'CLOCK_WORKER_CLOSED_MONITOR_CHANNEL_BEFORE_STOP')
                        self.channel_eof=True;self.selector.unregister(self.channel);continue
                    self.control()
                else:self.send_reply()
        if control and self.pending_reply is not None:
            self.c.need(time.monotonic()<self.pending_reply_deadline,'NOTIFY_REPLY_STALLED')
        if not self.monitor_stop_used and self.monitor_deadline is not None and self.terminal('monitor') is None:
            self.c.need(time.monotonic()<self.monitor_deadline,'ORIGINAL_NOTIFY_MONITOR_240_SECOND_BOUND')

    def retire_all(self):
        self.retiring=True
        if self.reaper is None:return
        if not self.reaper.record['begin_passed']:
            # A failed empty-child admission cannot authorize retirement of
            # children that predated this supervisor's actors.
            if self.reaper.original is not None:
                try:self.reaper.finish()
                except BaseException as error:self.remember(error,'restore_failed_reaper_admission')
            self.record['subreaper']=copy.deepcopy(self.reaper.record)
            return
        if self.terminal('business') is None and self.actors.get('business',{}).get('process') is not None:
            try:self.signal_exact('business',signal.SIGINT)
            except BaseException as error:self.remember(error,'cancel_actual_clock_worker')
            graceful=min(time.monotonic()+45,self.deadline)
            while time.monotonic()<graceful and self.terminal('business') is None:
                try:self.pump(.05)
                except BaseException as error:
                    self.remember(error,'worker_cleanup_pump')
                    # Once protocol observation failed, only bounded pipe
                    # draining continues; no action or request is replayed.
                    break
        retirement=time.monotonic()+LIMITS['retirement_seconds']
        for role in ('monitor','business'):
            item=self.actors.get(role)
            if item is not None and item['process'] is not None and not item['lifecycle']['child_reaped']:
                self.reaper.retire_leader(item['process'],item['pidfd'],item['lifecycle'],self.remember,retirement)
        adopted={'descendants':[],'owned_tree_cleanup_complete':False}
        if all(item['process'] is None or item['lifecycle']['child_reaped'] for item in self.actors.values()):
            self.reaper.retire_adopted(adopted,self.remember,retirement)
        self.record['adopted_retirement']=adopted
        try:
            while self.pipe_map and time.monotonic()<retirement:self.pump(.02,control=False)
            self.c.need(not self.pipe_map,'CLOCK_SUPERVISOR_RETAINED_PIPE_WRITERS')
            self.reaper.finish()
        except BaseException as error:self.remember(error,'final_owned_children_and_pipe_eof')
        self.record['subreaper']=copy.deepcopy(self.reaper.record)

    def close(self):
        for role,item in self.actors.items():
            for name,stream in item['streams'].items():
                try:self.close_pipe(stream)
                except BaseException as error:self.remember(error,'close_'+role+'_'+name+'_pipe')
                try:
                    stream['file'].flush();os.fsync(stream['file'].fileno());stream['file'].close()
                except BaseException as error:self.remember(error,'close_'+role+'_'+name+'_file')
            if item['pidfd'] is not None:
                try:os.close(item['pidfd']);item['lifecycle']['pidfd_closed']=True
                except BaseException as error:self.remember(error,'close_'+role+'_pidfd')
                item['pidfd']=None
            self.record['actors'][role]['pipe_eof']={name:row['eof'] for name,row in item['streams'].items()}
            self.record['actors'][role]['observed_bytes']={name:row['bytes_observed'] for name,row in item['streams'].items()}
        if self.channel is not None:
            try:self.channel.close();self.record['control_fd_closed']=True
            except BaseException as error:self.remember(error,'close_control_fd')
            self.channel=None
        if self.selector is not None:
            try:self.selector.close();self.record['selector_closed']=True
            except BaseException as error:self.remember(error,'close_selector')
            self.selector=None

    def assess(self):
        item=self.actors.get('business')
        self.c.need(item is not None and item['lifecycle']['child_reaped'],'ACTUAL_CLOCK_CHILD_RESULT_REQUIRED')
        raw,ref=self.c.regular(self.root/'result.json');value=self.c.parse(raw)
        self.c.need(value.get('schema')=='pocket4-current-clock-original-case-result-v1'
            and value.get('plan')==self.plan_ref and value.get('source_preparation')==self.prep_ref
            and value.get('kind')=='expiry06' and value.get('whole_app_business_accepted') is False,
            'CLOCK_WORKER_RESULT_IS_THIS_ORIGINAL_SCOPE')
        self.inner=value;self.record['inner_result']=ref
        self.c.need(self.monitor_final is not None and value['notify_watch_stop']==self.monitor_final
            and value['notify_monitor_closed_verified'] is True and value['monitor_control_FD_closed'] is True,
            'WORKER_RESULT_MATCHES_ACTUAL_PARENT_MONITOR_RETIREMENT')
        self.c.need(item['process'].returncode==(0 if value['case_business_success_verified'] else 1),
            'CLOCK_WORKER_EXIT_AND_RESULT_AGREE')
        self.c.need(self.record.get('subreaper',{}).get('restored') is True
            and self.record['subreaper'].get('final_children_empty') is True
            and self.record.get('adopted_retirement',{}).get('owned_tree_cleanup_complete') is True
            and all(actor['lifecycle']['child_reaped'] and actor['lifecycle']['pidfd_closed']
                and all(stream['eof'] for stream in actor['streams'].values()) for actor in self.actors.values()),
            'ALL_ACTUAL_CLOCK_SUPERVISOR_CHILDREN_FDS_AND_PIPES_CLOSED')
        self.baseline.guard();self.components['clock_plan.py'].validate_plan(self.c,self.plan_ref,self.prep_ref)

    def run(self):
        for number in (signal.SIGINT,signal.SIGTERM):signal.signal(number,self.cancelled)
        try:
            self.setup()
            while self.terminal('business') is None:
                self.c.need(time.monotonic()<self.deadline,'CLOCK_SUPERVISOR_WORKER_ABSOLUTE_DEADLINE')
                self.pump(.1)
        except BaseException as error:self.remember(error,'supervisor_operation')
        finally:
            self.retiring=True
            try:self.retire_all()
            except BaseException as error:self.remember(error,'supervisor_retirement')
            self.close()
            try:self.assess()
            except BaseException as error:self.remember(error,'actual_worker_and_retirement_result')
            signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
            pending=sorted(signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
            if self.signals or pending:self.remember(SupervisorCancelled('CANCELLED_BEFORE_CLOCK_SUPERVISOR_COMMIT'),'terminal_cancel')
            success=bool(self.first is None and self.inner is not None
                and self.inner.get('case_business_success_verified') is True)
            self.record.update(state='ORIGINAL_CLOCK_SCOPE_VERIFIED_CLEAN' if success else 'FAILED_OR_UNKNOWN_RETAINED',
                case_business_success_verified=success,whole_app_business_accepted=False,
                error=self.first,cancellation_commit={'pending_at_commit':pending,'decision_after_all_context_close':True},
                elapsed_seconds=time.monotonic()-self.started,owned_monitor_stop=self.monitor_final,
                lifecycle_source=LIFECYCLE,inner_case_state=None if self.inner is None else self.inner.get('state'),
                outcome_unknown=bool(self.record.get('subreaper',{}).get('final_children_empty') is not True
                    or (self.inner or {}).get('outcome_unknown') is True),automatic_rollback=False)
            ref=self.c.write_new(self.out/'result.json',self.record);self.committed=True
        return ref,self.record
