"""Actual Camera parent/channel; only Main and acoustic backend are host fixtures.

No Pulse, Android, production socket, service or audio device is accessed.
Every process is a private Python fixture in one test owner cgroup.
"""
import argparse,copy,errno,fcntl,hashlib,json,os,selectors,signal,socket,stat,sys,time,traceback,types
from pathlib import Path
LIFE_SHA='6a0ba9438b10740a593e2d90962420e04868465a0fb55c0ce2e03afdb835e877'
CASES=('queued-prepare-old','queued-prepare-new','queued-go-old','queued-go-new',
       'adoptee-old','adoptee-new','three-leader-channel','pipe-register-failure','missing-worker-terminal')

def need(v,s):
    if not v:raise RuntimeError(s)
def encoded(v):return (json.dumps(v,sort_keys=True,indent=2)+'\n').encode()
def ref(p):
    p=Path(p);b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def write(p,v):
    p=Path(p);b=v if type(v) is bytes else encoded(v)
    with p.open('xb') as f:f.write(b)
    return ref(p)
def load(p,name):
    p=Path(p);m=types.ModuleType(name);m.__file__=str(p);sys.modules[name]=m
    exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__);return m

def fd_table():
    out={}
    for name in os.listdir('/proc/self/fd'):
        try:
            fd=int(name);s=os.fstat(fd);link=os.readlink('/proc/self/fd/'+name)
        except OSError as e:
            if e.errno in (errno.EBADF,errno.ENOENT):continue
            raise
        out[name]={'link':link,'CLOEXEC':not os.get_inheritable(fd),'access_mode':fcntl.fcntl(fd,fcntl.F_GETFL),
            **{k:str(getattr(s,k)) for k in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size')}}
    return out

def sources(a):
    p=Path(a.packet);rows=json.loads(Path(a.source_map).read_bytes())
    need(set(rows)=={x.name for x in p.glob('*.py')},'EXACT_SOURCE_SET')
    for n,r in rows.items():need({k:ref(p/n)[k] for k in ('bytes','sha256')}==r,'EXACT_SOURCE:'+n)
    names=('app_common.py','app_runtime.py','camera_audio_channel.py','camera_owner_core.py',
           'camera_audio_supervisor.py','camera_audio_binding.py')
    return rows,{n:load(p/n,'camera_host_'+n[:-3]) for n in names}

def new_supervisor(a,m,life,root,old=False):
    module=load(a.old_supervisor,'actual_old_camera_supervisor') if old else m['camera_audio_supervisor.py']
    if old:need(ref(a.old_supervisor)['sha256']==a.expect_old_sha256,'EXACT_OLD_SUPERVISOR_PIN')
    cls=module.make_supervisor(m['camera_owner_core.py']);s=cls.__new__(cls)
    c=m['app_common.py'];runtime=m['app_runtime.py'];root.mkdir(mode=0o700)
    s.c=c;s.runtime=runtime;s.channel_module=m['camera_audio_channel.py'];s.components=dict(m)
    s.root=root;s.out=root/'acoustic-supervisor';s.out.mkdir(mode=0o700)
    s.plan={'schema':'explicit_host_external_Main_fixture','kind':'camera_video','case_root':str(root),
        'run_id':os.urandom(16).hex(),'audio_nonce':'13579bdf02468ace',
        'limits':{'business_seconds':420,'cleanup_seconds':60,'supervisor_seconds':510}}
    s.plan_ref=c.write_new(root/'base.json',s.plan,0o400)
    s.prep_ref=c.write_new(root/'preparation.json',{'explicit_host_Main_and_Pulse_backend_fixture':True},0o400)
    s.started=time.monotonic();s.deadline=s.started+12
    s.reaper=life.OwnChildReaper(protected_pids=(os.getpid(),os.getppid()));s.reaper.begin()
    s.selector=selectors.DefaultSelector();s.channel=None;s.actors={};s.pipe_map={};s.sequence=0
    s.pending_reply=s.pending_reply_deadline=None;s.actor_sources={};s.actor_gates={};s.actor_ready={};s.actor_final={}
    s.actor_go={};s.actor_deadlines={};s.memory=s.executable=None;s.channel_eof=False;s.retiring=s.committed=False
    s.signals=[];s.after_commit_signals=[];s.first=s.inner=None;s.record={'actors':{},'events':[],'errors':[],'received_signals':s.signals}
    s.main_view=types.SimpleNamespace(guard=lambda:None,close=lambda:None)
    s.baseline=types.SimpleNamespace(protected_pids=(),guard=lambda:None)
    s.components['camera_plan.py']=types.SimpleNamespace(validate=lambda *a:None)
    s.components['camera_audio_challenge.py']=types.SimpleNamespace(analyze=lambda *a,**k:{
        'explicit_host_synthetic_zero_PCM_fixture':True,'actual_audio_or_physical_qualification':False})
    s.method_entries=[]
    for name in ('prepare_actor','go_actor'):
        fn=getattr(s,name)
        def observed(*args,_fn=fn,_name=name,**kw):
            s.method_entries.append({'method':_name,'retiring':s.retiring,'received_signals':copy.deepcopy(s.signals)})
            return _fn(*args,**kw)
        setattr(s,name,observed)
    return s

# Fixed fake Pulse backend runs inside an actual sealed Python executable,
# after the exact same NNP/groups/GID/UID drop. It accesses only inherited
# stdin/stdout and the private listen memfd. No socket is opened in this actor.
ACTOR_PROGRAM=r'''import json,os,sys,time
role,nonce,memory=sys.argv[1],sys.argv[2],int(sys.argv[3])
common={'mode':role,'nonce':nonce,'pid':os.getpid(),'uid':os.getuid(),'gid':os.getgid(),'pulse_stream_index':901,'started':False}
if role=='emit':common.update(event='camera_challenge_ready',sink_name='alsa_output.pci-0000_c5_00.6.analog-stereo',sink_index=31)
else:common.update(event='camera_playback_observer_ready',source_name='alsa_input.pci-0000_c5_00.6.analog-stereo',source_index=32,bus_path='pci-0000:c5:00.6',active_port='analog-input-internal-mic',output_streams_created=0)
print(json.dumps(common),flush=True)
line=sys.stdin.readline()
if not line:time.sleep(.3);raise SystemExit(0)
assert line=='GO '+nonce+'\n'
print(json.dumps({'event':'camera_challenge_started' if role=='emit' else 'camera_playback_observer_started','nonce':nonce,'monotonic_ns':time.monotonic_ns()}),flush=True)
if role=='listen':assert sys.stdin.readline()=='STOP '+nonce+'\n';os.pwrite(memory,b'\0'*288000,0)
else:time.sleep(.1)
closed={k:v for k,v in common.items() if k not in ('pid','uid','gid','started')}
closed.update(event='camera_challenge_closed' if role=='emit' else 'camera_playback_observer_closed',stream_closed=True,runtime_qualified=False,monotonic_ns=time.monotonic_ns())
if role=='emit':closed.update(submitted_frames=133440,playback_phase_emit=False)
else:closed.update(raw_audio_persisted=False,rate=48000,channels=1,format='s16le',captured_bytes=288000)
print(json.dumps(closed),flush=True)
time.sleep(.05)
'''

def install_backend(s):
    raw=Path('/usr/bin/python3').read_bytes();s.executable=os.memfd_create('private-fake-Pulse-python',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
    offset=0
    while offset<len(raw):offset+=os.write(s.executable,raw[offset:])
    os.fchmod(s.executable,0o555);mask=fcntl.F_SEAL_WRITE|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_SEAL
    fcntl.fcntl(s.executable,fcntl.F_ADD_SEALS,mask)
    need(fcntl.fcntl(s.executable,fcntl.F_GET_SEALS)==mask,'PRIVATE_ACTOR_EXE_SEAL')
    original=s.actor
    def backend_actor(role,argv,*,pass_fds=(),alex=False):
        if alex:
            args=['/proc/self/fd/'+str(s.executable),'-I','-B','-c',ACTOR_PROGRAM,role,s.plan['audio_nonce'],str(-1 if role=='emit' else s.memory)]
            wrapper=('import ctypes,os;lib=ctypes.CDLL(None,use_errno=True);assert lib.prctl(38,1,0,0,0)==0;'
                'os.setgroups([]);os.setgid(1000);os.setuid(1000);os.execve('+repr(args[0])+','+repr(args)+',dict(os.environ))')
            argv=['/usr/bin/python3','-I','-B','-c',wrapper]
        return original(role,argv,pass_fds=pass_fds,alex=alex)
    s.actor=backend_actor
    return {'explicit_fake_backend':'private Python protocol only; never Pulse','executable':ref('/usr/bin/python3'),
        'seals':mask,'program_sha256':hashlib.sha256(ACTOR_PROGRAM.encode()).hexdigest()}

def bind_child(a,s,kind):
    parent,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);s.channel=parent
    for sock in (parent,child):sock.setsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED,1)
    parent.setblocking(False)
    value={'schema':'pocket4-current-camera-acoustic-parent-v1','plan':s.plan_ref,'preparation':s.prep_ref,
        'case_root':str(s.root),'parent':s.runtime.process(s.c,os.getpid()),'boot_id':s.runtime.boot(),
        'client_socket':s.channel_module.socket_identity(child.fileno()),'limits':s.plan['limits'],
        'nonce':s.plan['audio_nonce'],'automatic_retry':False}
    s.parent_ref=s.c.write_new(s.out/'parent.json',value,0o400)
    binding=s.c.write_new(s.root/'binding.json',{'plan':s.plan_ref,'preparation':s.prep_ref,'parent':s.parent_ref,
        'kind':kind,'prior_actor_final':s.actor_final,'initial_sequence':s.sequence},0o400)
    argv=['/usr/bin/python3','-I','-B',__file__,'--packet',a.packet,'--source-map',a.source_map,
          '--child-binding',binding['path'],'--client-fd',str(child.fileno())]
    try:
        item=s.actor('business',argv,pass_fds=(child.fileno(),));item['identity']=s.runtime.process(s.c,item['process'].pid)
        s.selector.register(parent,selectors.EVENT_READ,('control',None,None))
    finally:child.close()
    return item

def child(a):
    _,m=sources(a);c=m['app_common.py'];runtime=m['app_runtime.py'];ch=m['camera_audio_channel.py']
    binding=c.parse(Path(a.child_binding).read_bytes());plan_ref=binding['plan'];base=c.parse(c.read_ref(plan_ref));root=Path(base['case_root'])
    if binding['kind']=='missing-terminal':return 7
    owner=runtime.process(c,os.getpid());now=time.monotonic_ns()
    lease={'schema':'pocket4-final-camera-case-lease-v1','base_plan':plan_ref,'kind':'camera_video','owner':owner,
        'boot_id':runtime.boot(),'automatic_retry':False,'cleanup_seconds':60,'business_seconds':420,
        'started_monotonic_ns':now,'business_deadline_monotonic_ns':now+420000000000}
    lease_ref=c.write_new(root/'lease.json',lease,0o400);active={**base,'base_plan':plan_ref,'lease':lease_ref}
    active_ref=c.write_new(root/'active-plan.json',active,0o400)
    phase={'schema':'pocket4-final-camera-phase-lease-v1','phase':'business','active_plan':active_ref,'lease':lease_ref,
        'owner':owner,'trigger':None,'automatic_retry':False,'started_monotonic_ns':time.monotonic_ns(),
        'deadline_monotonic_ns':lease['business_deadline_monotonic_ns']}
    phase_ref=c.write_new(root/'phase-business.json',phase,0o400)
    c.write_new(root/'execute-once.json',{'plan':plan_ref,'operator':owner},0o400)
    session=types.SimpleNamespace(active=active,kind='camera_video',root=root,active_ref=active_ref,phase_ref=phase_ref,
        deadline=lease['business_deadline_monotonic_ns']/1e9,guard=lambda:None)
    client=ch.AcousticClient(c,runtime,a.client_fd,binding['parent'],plan_ref,binding['preparation'],base)
    final=copy.deepcopy(binding['prior_actor_final']);success=False;unknown=True
    try:
        client.attach(session)
        if binding['kind'] in ('queued-prepare','queued-go'):
            cancelled=[]
            signal.signal(signal.SIGINT,lambda n,f:cancelled.append(n))
            kind='listen_prepare' if binding['kind']=='queued-prepare' else 'emit_go'
            row={'schema':ch.SCHEMA,'sequence':binding['initial_sequence']+1,'kind':kind,'parent':binding['parent'],
                'plan':plan_ref,'value':{'active_plan':active_ref,'phase':phase_ref}}
            need(client.sock.send(c.canonical(row))>0,'ACTUAL_PRIVATE_QUEUED_REQUEST')
            c.write_new(root/'queued.json',{'kind':kind,'actual_sender':owner},0o400)
            bound=time.monotonic()+3
            while not cancelled:
                need(time.monotonic()<bound,'ACTUAL_PARENT_CANCEL_BOUND');time.sleep(.01)
            time.sleep(.5)
            c.write_new(root/'cancel-observed.json',{'signals':cancelled,'owner':owner},0o400)
        elif binding['kind']=='normal':
            for kind in ('emit_prepare','emit_go','emit_finish','listen_prepare','listen_go'):client.request(kind)
            started=time.monotonic_ns();uri='content://media/external/video/media/777'
            decode=c.write_new(root/'evidence'/'fixture-decode.json',{'uri':uri,'clip_sha256':'a'*64,'nonce':base['audio_nonce'],
                'full_video_decode':True,'current_nonce_audio_verified':True,'tone_offset_ms':1500,
                'explicit_host_only_artifact_fixture':True},0o400)
            request=c.write_new(root/'evidence'/'fixture-view-request.json',{'uri':uri,'started_monotonic_ns':started},0o400)
            ended=time.monotonic_ns();response=c.write_new(root/'evidence'/'fixture-view-result.json',{'uri':uri,'same_owned_task':True,'finished_monotonic_ns':ended},0o400)
            origin=client.results['listen_go']['actual_started']['monotonic_ns'];first=(started-origin)//1000000+1500-250
            br=c.write_new(root/'evidence'/'fixture-playback-acoustic-binding.json',{
                'schema':'pocket4-current-camera-playback-acoustic-binding-v1','plan':plan_ref,'active_plan':active_ref,
                'phase':phase_ref,'nonce':base['audio_nonce'],'uri':uri,'clip_sha256':'a'*64,'clip_decode':decode,
                'view_request':request,'view_result':response,'listener_started_monotonic_ns':origin,
                'tone_window_ms':[max(1500,first),(ended-origin)//1000000+1500+750],
                'baseline_end_ms':min(1500,max(1280,first-250)),
                'emitter_final':client.results['emit_finish']['reference'],'automatic_retry':False},0o400)
            client.request('listen_finish',{'playback_binding':br});final={r:client.results[r+'_finish'] for r in ('emit','listen')}
            success=True;unknown=False
        else:raise RuntimeError('EXACT_PRIVATE_CHILD_KIND')
    finally:client.close()
    c.write_new(root/'result.json',{'schema':'pocket4-current-camera-video-case-result-v1','plan':plan_ref,
        'source_preparation':binding['preparation'],'kind':'camera_video','whole_app_business_accepted':False,
        'case_business_success_verified':success,'outcome_unknown':unknown,'acoustic_results':final,
        'acoustic_channel_closed':client.closed,'explicit_host_fixture_not_Main_or_audio_qualification':True},0o400)
    return 0 if success else 1

def retire(s):
    s.retiring=True;s.close_owner()
    if s.reaper.active:s.retire_all()
    s.close()
    need(s.reaper.record.get('restored') is True and s.reaper.record.get('final_children_empty') is True,'ACTUAL_OWNER_RETIREMENT')
    for item in s.actors.values():
        if item['process'] is not None:need(item['lifecycle']['child_reaped'] and item['lifecycle']['pidfd_closed'],'ACTUAL_ACTOR_REAP_AND_PIDFD_CLOSE')

def run_queue(a,root,m,life,old,go):
    s=new_supervisor(a,m,life,root/'fixture',old);backend=install_backend(s);(s.root/'evidence').mkdir(mode=0o700)
    if go:
        item=s.actor('emit',[],pass_fds=(s.executable,),alex=True)
        while not s.lines('emit'):
            need(time.monotonic()<s.deadline,'PRIVATE_PREPARED_ACTOR_READY');s.pump(.02,control=False)
        s.actor_ready['emit']=s.lines('emit')[0];s.actor_deadlines['emit']=s.deadline;s.sequence=1
    else:s.actor_final={'emit':{'explicit_fixture_prior_finished_emitter':True}};s.sequence=3
    before_sequence=s.sequence
    def setup():
        bind_child(a,s,'queued-go' if go else 'queued-prepare')
        while not (s.root/'queued.json').exists():
            need(time.monotonic()<s.deadline,'ACTUAL_QUEUE_READY_BOUND');s.pump(.01,control=False)
        os.kill(os.getpid(),signal.SIGTERM)
    s.setup=setup
    ref_result,value=s.run()
    need(s.sequence==before_sequence+(1 if old else 0),'OLD_CANCELLED_REQUEST_CONSUMED_NEW_UNCONSUMED')
    need(len(s.method_entries)==(1 if old else 0),'OLD_DISPATCH_BOUNDARY_ENTERED_NEW_NEVER_ENTERED')
    need(all(row['retiring'] and row['received_signals'] for row in s.method_entries),'ACTUAL_CANCEL_PRECEDED_OLD_DISPATCH')
    if not go:need(('listen' in s.actors) is old,'OLD_ACTOR_AFTER_CANCEL_NEW_ZERO_SPAWN')
    need(value['case_business_success_verified'] is False and value['outcome_unknown'] is True,'CANCEL_AND_WORKER_UNKNOWN_RETAINED')
    need(s.reaper.record.get('restored') and s.reaper.record.get('final_children_empty'),'ALL_CANCELLED_PRIVATE_CHILDREN_RETIRED')
    return {'expected_old_failure':old,'kind':'go' if go else 'listen_prepare','backend_fixture':backend,
        'sequence_before_cancel':before_sequence,'sequence_after_retirement':s.sequence,'method_entries':s.method_entries,
        'actual_parent_result':ref_result,'actual_parent_value':value,
        'actual_worker_cancel':json.loads((s.root/'cancel-observed.json').read_bytes()) if (s.root/'cancel-observed.json').exists() else None,
        'actual_parent_cancel_signals':[r for r in s.record['events'] if r.get('event')=='business_signal']} 

def three_leader(a,root,m,life):
    s=new_supervisor(a,m,life,root/'fixture');backend=install_backend(s);(s.root/'evidence').mkdir(mode=0o700)
    s.setup=lambda:bind_child(a,s,'normal')
    result,value=s.run()
    need(value['case_business_success_verified'] is True and value['worker_result_verified'] is True and not value['outcome_unknown'],
        'ACTUAL_THREE_LEADER_SIX_REQUEST_PARENT_SUCCESS_WITH_EXPLICIT_BACKEND_FIXTURE')
    need(set(s.actors)=={'business','emit','listen'} and s.sequence==6,'EXACT_THREE_REAL_LEADERS')
    need(all(i['process'].returncode==0 and i['lifecycle']['child_reaped'] and i['lifecycle']['pidfd_closed'] for i in s.actors.values()),'ACTUAL_THREE_ZERO_EXITS')
    return {'backend_fixture':backend,'actual_parent_result':result,'actual_parent_value':value,
        'physical_audio_or_Android_qualification':False}

def adoptee(a,root,m,life,old):
    s=new_supervisor(a,m,life,root/'fixture',old);s.actor_final={'emit':{'explicit_host_fixture':True},'listen':{'explicit_host_fixture':True}};s.sequence=6
    v={'schema':'pocket4-current-camera-video-case-result-v1','plan':s.plan_ref,'source_preparation':s.prep_ref,
        'kind':'camera_video','whole_app_business_accepted':False,'case_business_success_verified':True,
        'outcome_unknown':False,'acoustic_results':s.actor_final,'acoustic_channel_closed':True,'explicit_host_fixture':True}
    c=s.c;pidfile=s.root/'adopted.json'
    code=('import os,time,json;from pathlib import Path\np=os.fork()\nif p==0:\n os.setsid();Path('+repr(str(pidfile))+').write_text(json.dumps({"pid":os.getpid()}));os._exit(17)\n'
          'else:\n time.sleep(.2);Path('+repr(str(s.root/'result.json'))+').write_text('+repr(encoded(v).decode())+');os._exit(0)')
    item=s.actor('business',['/usr/bin/python3','-I','-B','-c',code]);item['identity']=s.runtime.process(c,item['process'].pid)
    while s.terminal('business') is None:
        need(time.monotonic()<s.deadline,'ACTUAL_ORPHAN_WORKER_EXIT');s.pump(.02,control=False)
    retire(s);error=None
    try:s.assess()
    except BaseException as e:error={'type':type(e).__name__,'message':str(e)}
    rows=s.record['adopted_retirement']['descendants'];pid=json.loads(pidfile.read_bytes())['pid']
    need(len(rows)==1 and rows[0]['pid']==pid and rows[0]['wait_status']==17<<8 and rows[0]['reaped']
        and rows[0]['pidfd_closed'] and not Path('/proc/'+str(pid)).exists(),'EXACT_NONZERO_ESCAPED_ADOPTEE_ACTUALLY_RETIRED')
    need((error is None) is old and (old or error['message']=='NO_UNACCOUNTED_ADOPTED_SUBTREE_FOR_SUCCESS'),'OLD_ASSESS_ACCEPTED_NEW_EXPLICITLY_REFUSED')
    need(s.first is not None and any(r['stage']=='driver_left_descendants' for r in s.record['errors']),
        'ORIGINAL_LIFECYCLE_ALREADY_PRESERVED_DRIVER_FAILURE_NO_OLD_RUN_PASS_CLAIM')
    return {'expected_old_assess_gap':old,'old_run_was_already_failed_by_lifecycle':True,'assessment_error':error,
        'actual_adopted_process':rows[0],'supervisor':s.record}

def pipe_fault(a,root,m,life):
    s=new_supervisor(a,m,life,root/'fixture');real=s.selector
    class Fail:
        def __getattr__(self,n):return getattr(real,n)
        def register(self,*a,**k):raise OSError(errno.ENOMEM,'EXPLICIT_FIRST_PIPE_REGISTER_FAULT')
    s.selector=Fail();error=None
    try:
        try:s.actor('business',['/usr/bin/python3','-I','-B','-c','import time;time.sleep(30)'])
        except BaseException as e:error={'type':type(e).__name__,'message':str(e)}
        need(error and 'EXPLICIT_FIRST_PIPE_REGISTER_FAULT' in error['message'],'ACTUAL_FIRST_PIPE_FAULT')
        item=s.actors['business'];s.reaper.retire(item['process'],item['pidfd'],item['lifecycle'],s.remember,time.monotonic()+5)
        s.reaper.finish();s.close()
        closed={n:getattr(item['process'],n).closed for n in ('stdout','stderr')}
        need(closed=={'stdout':True,'stderr':True},'BOTH_ACTUAL_POPEN_PIPES_REGISTERED_AND_CLOSED')
        return {'actual_fault':error,'pipe_closed':closed,'lifecycle':item['lifecycle'],'subreaper':s.reaper.record}
    finally:
        if s.reaper.active:retire(s)

def missing(a,root,m,life):
    s=new_supervisor(a,m,life,root/'fixture');(s.root/'evidence').mkdir(mode=0o700)
    s.setup=lambda:bind_child(a,s,'missing-terminal');result,value=s.run()
    need(value['case_business_success_verified'] is False and value['outcome_unknown'] is True
        and value['worker_result_verified'] is False,'MISSING_BUSINESS_TERMINAL_UNKNOWN_DESPITE_HOST_RETIREMENT')
    need(s.actors['business']['process'].returncode==7 and s.reaper.record['final_children_empty'],'ACTUAL_MISSING_WORKER_EXIT_AND_RETIREMENT')
    return {'actual_parent_result':result,'actual_parent_value':value}

def main():
    p=argparse.ArgumentParser();p.add_argument('--packet',required=True);p.add_argument('--source-map',required=True)
    p.add_argument('--case',choices=CASES);p.add_argument('--output');p.add_argument('--lifecycle')
    p.add_argument('--old-supervisor');p.add_argument('--expect-old-sha256');p.add_argument('--child-binding');p.add_argument('--client-fd',type=int)
    a=p.parse_args();os.umask(0o077)
    if a.child_binding:return child(a)
    need(a.case and a.output and a.lifecycle and a.old_supervisor and a.expect_old_sha256,'EXPLICIT_PRIVATE_CONTROL_INPUTS')
    root=Path(a.output);root.mkdir(mode=0o700);rows,m=sources(a)
    need(ref(a.lifecycle)['sha256']==LIFE_SHA,'UNCHANGED_ACTUAL_LIFECYCLE');life=load(a.lifecycle,'camera_control_actual_lifecycle')
    cold=fd_table();warm=life.OwnChildReaper(protected_pids=(os.getpid(),os.getppid()));warm.flag();before=fd_table()
    details=error=None
    try:
        if a.case.startswith('queued-'):details=run_queue(a,root,m,life,a.case.endswith('-old'),a.case.startswith('queued-go'))
        elif a.case.startswith('adoptee-'):details=adoptee(a,root,m,life,a.case.endswith('-old'))
        elif a.case=='three-leader-channel':details=three_leader(a,root,m,life)
        elif a.case=='pipe-register-failure':details=pipe_fault(a,root,m,life)
        else:details=missing(a,root,m,life)
    except BaseException as e:error={'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()}
    after=fd_table();children=warm.children();passed=error is None and before==after and children==[]
    value={'schema':'pocket4-camera-video-supervisor-host-control-v1','case':a.case,'passed':passed,'details':details,'error':error,
        'source_sha256':{n:r['sha256'] for n,r in rows.items()},'old_supervisor':ref(a.old_supervisor),
        'lifecycle_source':ref(a.lifecycle),'cold_FD_before_actual_libffi_initialization':cold,'FD_before':before,'FD_after':after,
        'remaining_children':children,'Main_actions':0,'Android_UI_actions':0,'actual_audio_stream_actions':0,
        'physical_audio_qualified':False,'runtime_qualified':False,'whole_app_business_accepted':False}
    result=write(root/'result.json',value);print(json.dumps({'passed':passed,'result':result}));return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
