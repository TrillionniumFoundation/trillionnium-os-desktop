"""One thread supervises the business worker and its fixed HTTP-server sibling.

The worker independently owns all short CLI children through the unchanged
bounded capture. This owner never signals Main or infers Binder task cleanup.
"""
import copy
import fcntl
import hashlib
import os
from pathlib import Path
import select
import selectors
import signal
import socket
import subprocess
import time

LIFECYCLE={'path':'/home/alex/work/pocket4-android-final/framework/runtime_support/capture_lifecycle.py',
    'bytes':25312,'sha256':'6a0ba9438b10740a593e2d90962420e04868465a0fb55c0ce2e03afdb835e877'}
LIMITS={'startup_seconds':10,'retirement_seconds':30,'server_stream_bytes':65536,
    'worker_stream_bytes':16777216,'maximum_control_requests':2,'maximum_stdout_receipts':8192,
    'maximum_read_bytes_per_pump':262144}
class SupervisorCancelled(BaseException):pass
def life_record():
    return {'child_started':False,'child_reaped':False,'pidfd_closed':True,
        'owned_tree_cleanup_complete':False,'descendants':[]}

def sealed(raw):
    if type(raw) is not bytes or not 0<len(raw)<=131072:raise RuntimeError('BOUNDED_FROZEN_SERVER_INPUT')
    fd=os.memfd_create('p4-fixed-webview-source',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
    try:
        offset=0
        while offset<len(raw):offset+=os.write(fd,raw[offset:])
        mask=fcntl.F_SEAL_WRITE|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_SEAL
        fcntl.fcntl(fd,fcntl.F_ADD_SEALS,mask)
        if fcntl.fcntl(fd,fcntl.F_GET_SEALS)!=mask:raise RuntimeError('SERVER_INPUT_NOT_SEALED')
        return fd
    except BaseException:os.close(fd);raise

def close_owned_descriptors(descriptors):
    """Complete a finite local-FD close before delivering cancellation."""
    old=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
    first=None
    try:
        for fd in descriptors:
            try:os.close(fd)
            except BaseException as error:
                if first is None:first=error
                else:first.add_note('OTHER_OWNED_LOCAL_FD_CLOSE:'+str(error))
    finally:signal.pthread_sigmask(signal.SIG_SETMASK,old)
    if first is not None:raise first

class Supervisor:
    def __init__(self,c,plan_ref,prep_ref,components,request_ref,packet):
        self.c=c;self.plan_ref=plan_ref;self.prep_ref=prep_ref;self.components=components
        self.runtime=components['app_runtime.py'];self.channel_module=components['webview_channel.py']
        self.plan=c.parse(c.read_ref(plan_ref));self.request_ref=request_ref;self.packet=packet
        _,support=c.support(self.plan['support_manifest'])
        self.baseline=support['business_baseline.py'].BusinessBaseline(self.plan['baseline'],self.plan['qualification'])
        components['webview_plan.py'].validate(c,self.plan,self.baseline)
        self.task=components['webview_plan.py'].source_packet(c,self.plan,packet)
        c.need(c.parse(c.read_ref(request_ref))=={'base_plan':plan_ref},'ONE_EXACT_WEBVIEW_EXECUTION_REQUEST')
        self.root=Path(self.plan['case_root']);c.need(not (self.root/'execute-once.json').exists(),'NO_WEBVIEW_CASE_REPLAY')
        self.out=c.private_dir(self.root/'fixture-supervisor',create=True)
        self.started=time.monotonic();self.deadline=self.started+self.plan['limits']['supervisor_seconds']-30
        self.reaper=self.selector=self.channel=self.main_view=None;self.actors={};self.pipe_map={}
        self.sequence=0;self.pending_reply=self.pending_reply_deadline=None
        self.server_start_used=self.server_stop_used=False;self.server_final=self.server_deadline=None
        self.owner_write=None;self.ready=None;self.channel_eof=False
        self.retiring=self.committed=False;self.signals=[];self.after_commit_signals=[];self.first=self.inner=None
        self.record={'schema':'pocket4-current-webview-supervisor-result-v1','state':'STARTING',
            'plan':plan_ref,'preparation':prep_ref,'kind':self.plan['kind'],'limits':copy.deepcopy(self.plan['limits']),
            'events':[],'errors':[],'received_signals':self.signals,'actors':{},'automatic_retry':False,
            'Main_signals':0,'Android_UI_actions_by_supervisor':0,'whole_app_business_accepted':False}
    def setup(self):
        c=self.c;c.need(os.getuid()==os.geteuid()==os.getgid()==os.getegid()==0,'ROOT_FIXED_WEBVIEW_SUPERVISOR')
        life=c.module(LIFECYCLE,'webview_unchanged_owned_lifecycle')
        self.reaper=life.OwnChildReaper(protected_pids=self.baseline.protected_pids)
        self.reaper.begin();self.selector=selectors.DefaultSelector()
        journal=c.private_dir(self.out/'held-main',create=True)
        def no_command(argv,timeout,root,private):raise RuntimeError('PARENT_HAS_NO_ANDROID_COMMAND_ADMISSION')
        self.main_view=c.MainView(self.plan['baseline'],self.plan['qualification'],journal,no_command,
            support_ref=self.plan['support_manifest'])
        parent,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);self.channel=parent
        try:
            for sock in (parent,child):sock.setsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED,1)
            parent.setblocking(False)
            value={'schema':'pocket4-current-webview-supervisor-parent-v1','plan':self.plan_ref,
                'preparation':self.prep_ref,'case_root':str(self.root),'parent':self.runtime.process(c,os.getpid()),
                'boot_id':self.runtime.boot(),'client_socket':self.channel_module.socket_identity(child.fileno()),
                'limits':copy.deepcopy(self.plan['limits']),'automatic_retry':False}
            self.parent_ref=c.write_new(self.out/'parent.json',value,0o400)
            entry=next(r for r in self.task['files'] if Path(r['path']).name=='webview_entry.py')
            c.read_ref(entry);c.read_ref(self.request_ref)
            argv=['/usr/bin/python3','-I','-B',entry['path'],'--preparation',self.prep_ref['path'],
                '--expect-preparation-sha256',self.prep_ref['sha256'],'execute-worker','--request',self.request_ref['path'],
                '--expect-request-sha256',self.request_ref['sha256'],'--fixture-fd',str(child.fileno()),
                '--fixture-parent',self.parent_ref['path'],'--expect-fixture-parent-sha256',self.parent_ref['sha256']]
            self.record['worker_argv']=argv
            c.need(time.monotonic()<self.started+LIMITS['startup_seconds'],'ORIGINAL_SUPERVISOR_STARTUP_BOUND')
            item=self.actor('business',argv,pass_fds=(child.fileno(),))
            item['identity']=self.runtime.process(c,item['process'].pid)
            c.need(item['identity']['parent']==os.getpid(),'ACTUAL_DIRECT_WEBVIEW_WORKER')
            self.record['business_process']=item['identity']
            self.selector.register(parent,selectors.EVENT_READ,('control',None,None))
        finally:child.close()
    def verify_phase(self,value):
        c=self.c;c.need(set(value)=={'active_plan','phase'},'EXACT_START_PHASE_REFERENCE')
        active=c.parse(c.read_ref(value['active_plan']));phase=c.parse(c.read_ref(value['phase']))
        c.need(value['active_plan']['path']==str(self.root/'active-plan.json') and active['base_plan']==self.plan_ref
            and {k:active[k] for k in self.plan if k!='schema'}=={k:v for k,v in self.plan.items() if k!='schema'},
            'ACTIVE_PLAN_SAME_FROZEN_BASE')
        components=self.components;components['webview_plan.py'].validate(c,active,self.baseline)
        lease=c.parse(c.read_ref(active['lease']));owner=self.actors['business']['identity'];now=time.monotonic_ns()
        c.need(lease['schema']=='pocket4-final-system-case-lease-v1' and lease['base_plan']==self.plan_ref
            and lease['kind']==self.plan['kind'] and lease['owner']==owner and lease['boot_id']==self.runtime.boot()
            and lease['automatic_retry'] is False and lease['cleanup_seconds']==90
            and lease['business_seconds']==self.plan['limits']['business_seconds']
            and lease['business_deadline_monotonic_ns']==lease['started_monotonic_ns']+lease['business_seconds']*1000000000
            and self.started*1e9<=lease['started_monotonic_ns']<=now<lease['business_deadline_monotonic_ns'],
            'ACTUAL_WORKER_ORIGINAL_ABSOLUTE_LEASE')
        c.need(value['phase']['path']==str(self.root/'phase-business.json')
            and phase['schema']=='pocket4-final-system-phase-lease-v1' and phase['phase']=='business'
            and phase['active_plan']==value['active_plan'] and phase['lease']==active['lease']
            and phase['owner']==owner and phase['trigger'] is None and phase['automatic_retry'] is False
            and lease['started_monotonic_ns']<=phase['started_monotonic_ns']<=now
            and phase['deadline_monotonic_ns']==lease['business_deadline_monotonic_ns'],
            'ACTUAL_BUSINESS_PHASE_BEFORE_FIXTURE_START')
        once=c.parse(c.read_ref(c.regular(self.root/'execute-once.json',contents=False)))
        c.need(once['plan']==self.plan_ref and once['operator']==owner,'ACTUAL_ONCE_WORKER_ENTRY')
        return phase
    def assets(self):
        name='webview_assets10.py' if self.plan['kind']=='webview_business10' else 'webview_assets11.py'
        row=next(r for r in self.task['files'] if Path(r['path']).name==name)
        source=self.c.read_ref(row);video=None
        if self.plan['kind']=='webview_media11':
            video=self.c.read_ref(self.components['webview_profiles.py'].ORIGINAL_VIDEO,65536)
        return row,source,video,self.components[name].build(video)
    def start_server(self,value):
        c=self.c;c.need(not self.server_start_used and not self.server_stop_used,'ONE_FIXED_FIXTURE_START')
        self.server_start_used=True;phase=self.verify_phase(value);self.main_view.guard()
        row,source,video,assets=self.assets();net=self.main_view.target.namespaces['net']
        expected='net:[%d]'%os.fstat(net).st_ino
        owner_read,self.owner_write=os.pipe2(os.O_CLOEXEC);fds=[]
        try:
            source_fd=sealed(source);fds.append(source_fd)
            video_fd=-1 if video is None else sealed(video)
            if video_fd!=-1:fds.append(video_fd)
            wrapper=('import os,hashlib;'
                'read=lambda fd,n:os.pread(fd,n+1,0);'
                'src=read(%d,%d);assert len(src)==%d and hashlib.sha256(src).hexdigest()==%r;'
                'v=None if %d<0 else read(%d,58199);'
                'ns={"__name__":"fixed_webview_assets","__file__":%r};exec(compile(src,%r,"exec"),ns);'
                'assets=ns["build"](v);os.close(%d);'
                'os.close(%d) if %d>=0 else None;'
                'assets.child(%d,%d,%r,%r,%d)')%(source_fd,len(source),len(source),row['sha256'],video_fd,video_fd,
                    row['path'],row['path'],source_fd,video_fd,video_fd,net,owner_read,self.plan['run_id'],expected,
                    self.plan['limits']['fixture_seconds'])
            c.need(time.monotonic_ns()<phase['deadline_monotonic_ns'],'FIXTURE_NO_SPAWN_AFTER_WORKER_PHASE')
            item=self.actor('server',['/usr/bin/python3','-I','-B','-c',wrapper],pass_fds=(net,owner_read,*fds))
        finally:close_owned_descriptors((owner_read,*fds))
        self.server_deadline=time.monotonic()+self.plan['limits']['fixture_seconds']
        deadline=min(time.monotonic()+8,phase['deadline_monotonic_ns']/1e9)
        out=item['streams']['stdout']
        while b'\n' not in out['buffer']:
            c.need(time.monotonic()<deadline and len(out['buffer'])<8192 and self.terminal('server') is None,
                'ORIGINAL_FIXTURE_READY_DEADLINE_LENGTH_AND_CHILD')
            self.verify_business();self.pump(.05,control=False)
        line,tail=bytes(out['buffer']).split(b'\n',1);ready=c.parse(line)
        identity=self.channel_module.child_identity(item['process'].pid)
        hostns={n:os.readlink('/proc/self/ns/'+n) for n in ('mnt','pid','uts','ipc','user','cgroup')}
        c.need(len(line)<8192 and not tail and ready['state']=='FIXTURE_READY'
            and ready['pid']==item['process'].pid and ready['start_ticks']==identity['start_ticks']
            and ready['uid']==ready['gid']==1000 and ready['groups']==[] and ready['net_namespace']==expected
            and ready['address']=='127.0.0.1' and type(ready['port']) is int and 1024<=ready['port']<=65535
            and type(ready['socket_inode']) is int and ready['socket_inode']>0
            and ready['other_namespaces_unchanged'] is True and ready['run']==self.plan['run_id']
            and ready['lease_seconds']==self.plan['limits']['fixture_seconds']
            and ready['assets']=={n:hashlib.sha256(b).hexdigest() for n,(_,b) in assets.assets.items()}
            and identity['parent']==os.getpid() and identity['net_namespace']==expected
            and identity['other_namespaces']==hostns and identity['cgroup']==self.runtime.process(c,os.getpid())['cgroup']
            and identity['status']=={'Uid':['1000']*4,'Gid':['1000']*4,'Groups':[],
                'CapEff':['0000000000000000'],'CapPrm':['0000000000000000'],'CapAmb':['0000000000000000'],'NoNewPrivs':['1']},
            'ACTUAL_FIXED_ASSETS_RUN_NAMESPACE_AND_DROPPED_SERVER_IDENTITY')
        self.ready=ready;self.main_view.guard();self.verify_business()
        payload={'ready':ready,'server_identity':identity,'pages':list(assets.pages),
            'base_url':'http://127.0.0.1:%d/p4/%s/'%(ready['port'],ready['run'])}
        ready_ref=c.write_new(self.out/'ready.json',payload,0o400)
        self.record['server_ready']=ready_ref
        return {**payload,'ready_ref':ready_ref}
    def close_owner(self):
        fd=self.owner_write;self.owner_write=None
        if fd is not None:os.close(fd)
    def signal_exact(self,role,number):
        item=self.actors.get(role)
        if item is None or item['process'] is None or item['lifecycle']['child_reaped']:return
        process=item['process'];self.reaper.signal_target(process.pid)
        if self.reaper.peek(process.pid,item['pidfd']) is None:
            if item['pidfd'] is not None:signal.pidfd_send_signal(item['pidfd'],number)
            else:os.kill(process.pid,number)
            self.record['events'].append({'event':role+'_signal','signal':number,'pid':process.pid,'monotonic_ns':time.monotonic_ns()})

    def stop_server(self,value):
        c=self.c;c.need(set(value)=={'started_request_sent'} and type(value['started_request_sent']) is bool
            and not self.server_stop_used,'ONCE_FIXED_SERVER_STOP')
        self.server_stop_used=True;self.close_owner();item=self.actors.get('server')
        if item is None:
            self.server_final={'server_started':False,'own_child_reaped':False,'socket_closed':False,
                'other_process_signals':0,'automatic_retry':False}
            return self.server_final
        deadline=time.monotonic()+5
        while time.monotonic()<deadline and (self.terminal('server') is None or not all(s['eof'] for s in item['streams'].values())):
            self.pump(.05,control=False)
        self.reaper.retire_leader(item['process'],item['pidfd'],item['lifecycle'],self.remember,time.monotonic()+4)
        c.need(item['lifecycle']['child_reaped'],'FIXTURE_LEADER_RETIREMENT_UNKNOWN')
        c.need(self.reaper.children()==[self.actors['business']['process'].pid],
            'FIXTURE_ADOPTED_DESCENDANT_REQUIRES_STOP_WORKER_BEFORE_GLOBAL_RETIREMENT')
        self.drain_available_pipes()
        c.need(all(s['eof'] for s in item['streams'].values()),'FIXTURE_ALL_WRITERS_EXITED')
        lines=bytes(item['streams']['stdout']['buffer']).splitlines()
        c.need(len(lines)==2 and c.parse(lines[0])==self.ready and not item['streams']['stderr']['buffer'],
            'EXACT_READY_AND_TERMINAL_SERVER_RECORDS')
        closed=c.parse(lines[1]);c.need(closed['state']=='FIXTURE_CLOSED' and closed['socket_closed'] is True
            and closed['reason']=='PARENT_PIPE_CLOSED' and item['process'].returncode==0,
            'ORIGINAL_NORMAL_OWNER_PIPE_STOP_REQUIRED_FOR_SUCCESS')
        self.server_final={'server_started':True,'own_child_reaped':True,'socket_closed':True,
            'exit_code':item['process'].returncode,'terminal':closed,'ready':self.ready,
            'pipe_eof':{n:s['eof'] for n,s in item['streams'].items()},'other_process_signals':0,'automatic_retry':False}
        return self.server_final
    def control(self):
        c=self.c;c.need(self.pending_reply is None,'NO_SECOND_REQUEST_WHILE_REPLY_PENDING');self.verify_business()
        item=self.actors['business']
        try:row=self.channel_module.receive(self.channel,(item['process'].pid,0,0),c.parse)
        except BlockingIOError:return
        c.need(type(row) is dict and set(row)==self.channel_module.REQUEST_KEYS and row['schema']==self.channel_module.SCHEMA
            and row['sequence']==self.sequence+1 and row['parent']==self.parent_ref and row['plan']==self.plan_ref
            and row['kind'] in ('start','stop') and type(row['value']) is dict and self.sequence<2,
            'EXACT_ONCE_WORKER_CONTROL_REQUEST')
        self.sequence=row['sequence'];kind=row['kind']
        result=(self.start_server if kind=='start' else self.stop_server)(row['value'])
        raw=c.canonical({'schema':self.channel_module.SCHEMA,'sequence':self.sequence,'kind':kind,'ok':True,'value':result,'error':None})
        c.need(len(raw)<=self.channel_module.MAX_PACKET,'BOUNDED_FIXTURE_REPLY')
        self.pending_reply=raw;self.pending_reply_deadline=time.monotonic()+1
        self.selector.modify(self.channel,selectors.EVENT_WRITE,('control',None,None))
    def assess(self):
        c=self.c;item=self.actors.get('business')
        c.need(item is not None and item['lifecycle']['child_reaped'],'ACTUAL_WEBVIEW_WORKER_REAPED')
        raw,ref=c.regular(self.root/'result.json');value=c.parse(raw)
        c.need(value['schema']=='pocket4-current-webview-original-case-result-v1' and value['plan']==self.plan_ref
            and value['source_preparation']==self.prep_ref and value['kind']==self.plan['kind']
            and value['whole_app_business_accepted'] is False,'ACTUAL_SAME_WEBVIEW_WORKER_RESULT')
        self.inner=value;self.record['inner_result']=ref
        c.need(self.server_final is not None and value['fixture_stop']==self.server_final
            and value['fixture_control_closed'] is True,'WORKER_AND_PARENT_EXACT_FIXTURE_RETIREMENT_AGREE')
        c.need(item['process'].returncode==(0 if value['case_business_success_verified'] else 1),'WORKER_EXIT_AND_RESULT_AGREE')
        c.need(self.record.get('subreaper',{}).get('restored') is True
            and self.record['subreaper']['final_children_empty'] is True
            and self.record.get('adopted_retirement',{}).get('owned_tree_cleanup_complete') is True
            and all(x['lifecycle']['child_reaped'] and x['lifecycle']['pidfd_closed']
                and all(s['eof'] for s in x['streams'].values()) for x in self.actors.values()),
            'ALL_WEBVIEW_OWNER_CHILDREN_DESCRIPTORS_AND_PIPES_RETIRED')
        self.baseline.guard();self.components['webview_plan.py'].validate(c,self.plan,self.baseline)
        c.need(time.monotonic()<=self.started+self.plan['limits']['supervisor_seconds'],'ORIGINAL_TOTAL_SUPERVISOR_BOUND')
    def run(self):
        worker_result_verified=False
        for number in (signal.SIGINT,signal.SIGTERM):signal.signal(number,self.cancelled)
        try:
            self.setup()
            while self.terminal('business') is None:
                self.c.need(time.monotonic()<self.deadline,'WEBVIEW_WORKER_ABSOLUTE_DEADLINE');self.pump(.1)
        except BaseException as error:self.remember(error,'supervisor_operation')
        finally:
            self.retiring=True
            try:self.close_owner();self.retire_all()
            except BaseException as error:self.remember(error,'supervisor_retirement')
            self.close()
            if self.main_view is not None:
                try:self.main_view.close();self.record['held_Main_closed']=True
                except BaseException as error:self.remember(error,'held_Main_close')
            try:self.assess();worker_result_verified=True
            except BaseException as error:self.remember(error,'actual_worker_and_retirement_result')
            signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
            pending=sorted(signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
            if self.signals or pending:self.remember(SupervisorCancelled('CANCELLED_BEFORE_WEBVIEW_COMMIT'),'terminal_cancel')
            success=bool(self.first is None and self.inner is not None and self.inner.get('case_business_success_verified') is True)
            self.record.update(state='ORIGINAL_WEBVIEW_SCOPE_VERIFIED_CLEAN' if success else 'FAILED_OR_UNKNOWN_RETAINED',
                case_business_success_verified=success,whole_app_business_accepted=False,error=self.first,
                cancellation_commit={'pending_at_commit':pending,'decision_after_all_context_close':True},
                elapsed_seconds=time.monotonic()-self.started,owned_fixture_stop=self.server_final,lifecycle_source=LIFECYCLE,
                worker_result_verified=worker_result_verified,
                outcome_unknown=bool(not worker_result_verified or self.record.get('subreaper',{}).get('final_children_empty') is not True
                    or (self.inner or {}).get('outcome_unknown') is True),automatic_rollback=False)
            ref=self.c.write_new(self.out/'result.json',self.record);self.committed=True
        return ref,self.record

    def remember(self,error,stage):
        row={'stage':stage,'type':type(error).__name__,'message':str(error),'errno':getattr(error,'errno',None)}
        if self.first is None:self.first=row
        self.record['errors'].append(row)

    def cancelled(self,number,frame):
        target=self.after_commit_signals if self.committed else self.signals
        if len(target)<32:target.append({'signal':number,'monotonic_ns':time.monotonic_ns(),'retiring':self.retiring})
        if not self.retiring and not self.committed:raise SupervisorCancelled('WEBVIEW_FIXTURE_SUPERVISOR_CANCELLED')

    def terminal(self,role):
        actor=self.actors.get(role)
        if actor is None or actor['process'] is None or actor['lifecycle']['child_reaped']:return None
        return self.reaper.peek(actor['process'].pid,actor['pidfd'])

    def actor(self,role,argv,*,pass_fds=(),alex=False):
        self.c.need(role in ('business','server') and role not in self.actors,'ONCE_EXACT_WEBVIEW_SIBLING')
        bound=LIMITS['server_stream_bytes'] if role=='server' else LIMITS['worker_stream_bytes']
        item={'process':None,'pidfd':None,'lifecycle':life_record(),'streams':{},'bound':bound,'receipts':[]}
        self.actors[role]=item;self.record['actors'][role]=item['lifecycle']
        for name in ('stdout','stderr'):
            item['streams'][name]={'buffer':bytearray(),'eof':False,'closed':False,'pipe':None,
                'file':open(self.out/(role+'.'+name),'xb'),'bytes_observed':0}
        env=dict(self.c.HOST_ENV)
        if alex:env.update(HOME='/home/alex',XDG_RUNTIME_DIR='/run/user/1000',
            DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/1000/bus')
        process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            start_new_session=True,close_fds=True,pass_fds=tuple(pass_fds),env=env,
            user=1000 if alex else 0,group=1000 if alex else 0,extra_groups=())
        item['process']=process
        item['lifecycle'].update(child_started=True,pid=process.pid,uid=1000 if alex else 0)
        # Retain Popen immediately. A subsequent pidfd/open/register failure
        # still leaves exact unreaped-child cleanup authority.
        # Register both actual descriptors as owned before any fallible setup.
        for name in ('stdout','stderr'):item['streams'][name]['pipe']=getattr(process,name)
        for name in ('stdout','stderr'):
            stream=item['streams'][name];pipe=stream['pipe']
            os.set_blocking(pipe.fileno(),False)
            self.selector.register(pipe,selectors.EVENT_READ,('pipe',role,name))
            self.pipe_map[pipe.fileno()]=(role,name)
        item['pidfd']=os.pidfd_open(process.pid,0);item['lifecycle']['pidfd_closed']=False
        self.c.need(os.getpgid(process.pid)==process.pid and os.getsid(process.pid)==process.pid,
            'WEBVIEW_SIBLING_PRIVATE_SESSION')
        self.record['events'].append({'event':role+'_spawned','pid':process.pid,'monotonic_ns':time.monotonic_ns()})
        return item

    def verify_business(self):
        item=self.actors['business'];self.c.need(not item['lifecycle']['child_reaped']
            and self.terminal('business') is None
            and self.runtime.process(self.c,item['process'].pid)==item['identity'],
            'ACTUAL_LIVE_WEBVIEW_WORKER_GENERATION_REQUIRED')

    def send_reply(self):
        self.c.need(self.pending_reply is not None,'CURRENT_FIXTURE_REPLY')
        self.verify_business()
        self.c.need(time.monotonic()<self.pending_reply_deadline,'FIXTURE_REPLY_BACKPRESSURE_DEADLINE')
        try:count=self.channel.send(self.pending_reply,socket.MSG_NOSIGNAL)
        except BlockingIOError:return
        self.c.need(count==len(self.pending_reply),'ATOMIC_FIXTURE_PARENT_REPLY')
        self.pending_reply=None;self.pending_reply_deadline=None
        self.selector.modify(self.channel,selectors.EVENT_READ,('control',None,None))

    def close_pipe(self,stream):
        pipe=stream['pipe']
        if pipe is not None and not stream['closed']:
            fd=pipe.fileno()
            self.pipe_map.pop(fd,None)
            try:
                try:self.selector.unregister(pipe)
                except KeyError:pass  # actual pipe can precede selector registration
            finally:
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
        if role=='server' and name=='stdout' and chunk:
            item['receipts'].append({'end_byte_offset':len(stream['buffer']),
                'monotonic_ns':time.monotonic_ns(),'realtime_ns':time.time_ns()})
            self.c.need(len(item['receipts'])<=LIMITS['maximum_stdout_receipts'],'FIXTURE_LOCAL_RECEIPT_BOUND')
        if len(data)>remain:
            # Stop reading both streams at the first extra byte. Retirement is
            # still mandatory, but overflow cannot produce a successful EOF.
            for other in item['streams'].values():self.close_pipe(other)
            raise RuntimeError('WEBVIEW_'+role.upper()+'_OUTPUT_BOUND_EXCEEDED:'+name)
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
                        self.c.need(self.server_stop_used,'WEBVIEW_WORKER_CLOSED_SERVER_CHANNEL_BEFORE_STOP')
                        self.channel_eof=True;self.selector.unregister(self.channel);continue
                    self.control()
                else:self.send_reply()
        if control and self.pending_reply is not None:
            self.c.need(time.monotonic()<self.pending_reply_deadline,'FIXTURE_REPLY_STALLED')
        if not self.server_stop_used and self.server_deadline is not None and self.terminal('server') is None:
            self.c.need(time.monotonic()<self.server_deadline,'ORIGINAL_FIXED_SERVER_LEASE_BOUND')

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
            except BaseException as error:self.remember(error,'cancel_actual_webview_worker')
            graceful=min(time.monotonic()+90,self.deadline)
            while time.monotonic()<graceful and self.terminal('business') is None:
                try:self.pump(.05)
                except BaseException as error:
                    self.remember(error,'worker_cleanup_pump')
                    # Once protocol observation failed, only bounded pipe
                    # draining continues; no action or request is replayed.
                    break
        retirement=time.monotonic()+LIMITS['retirement_seconds']
        for role in ('server','business'):
            item=self.actors.get(role)
            if item is not None and item['process'] is not None and not item['lifecycle']['child_reaped']:
                self.reaper.retire_leader(item['process'],item['pidfd'],item['lifecycle'],self.remember,retirement)
        adopted={'descendants':[],'owned_tree_cleanup_complete':False}
        if all(item['process'] is None or item['lifecycle']['child_reaped'] for item in self.actors.values()):
            self.reaper.retire_adopted(adopted,self.remember,retirement)
        self.record['adopted_retirement']=adopted
        try:
            while self.pipe_map and time.monotonic()<retirement:self.pump(.02,control=False)
            self.c.need(not self.pipe_map,'WEBVIEW_SUPERVISOR_RETAINED_PIPE_WRITERS')
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
