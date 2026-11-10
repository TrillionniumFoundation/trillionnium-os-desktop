#!/usr/bin/python3 -I
"""Fixed-APK editor contract trial; inert until exact task-option proof is pinned."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, os, re, signal, stat, time, types

HERE=Path(__file__).resolve().parent
ROOT=Path('/home/alex/work/pocket4-editor-ui-20261105-r12-03')
CONTACT=Path('/home/alex/work/pocket4-contacts-session-tools-20261105-r12-01')
DIAGNOSTIC=Path('/home/alex/work/pocket4-qa-fixture-ui-tools-20261105-r12-01/diagnostics_source.py')
PACKAGE='org.droidloom.qa.editorcontract';COMPONENT=PACKAGE+'/.EditorContractActivity'
APK='/data/app/~~azb5Z9bqpcSnfR4fbzSWoA==/org.droidloom.qa.editorcontract-bpP3Aa1qzcaX1a7uHGVhTw==/base.apk'
APK_SHA='0d08f59024e4228e5d5b8f56742aafd1fbc04966d74224acd48542e09482743d'
UID=10149;RUN='p4r12_editor_d39107ac';LEASE=360;RESERVE=45
TASK_PROOF=HERE/'task-option-proof.json'
TASK_PROOF_SHA='9cb008b7050d3bb0b8da2221140c02b39ebde973833b5ee24039932e266e90a5'
PINS={str(CONTACT/'ui_preflight04.py'):'d02821d751736a9e3cf275ec0b27383852e24362928fd4257ebb6d3dee7f6a58',
    str(CONTACT/'session_loop07.py'):'c8cd713f3e323016dbfdce8e41a5c474ac58d365ebcd613dd539fc9568bb7784',
    str(DIAGNOSTIC):'93cf4567c19f6033dce0b120d068a7120a2b27952a4a1d0d4cfdd8b988ebfbcb'}

def need(value,reason):
    if not value:raise RuntimeError(reason)
def sha(data):return hashlib.sha256(data).hexdigest()
def stamp():return datetime.now(timezone.utc).isoformat()
def load(path,pin):
    raw=Path(path).read_bytes();need(sha(raw)==pin,'SOURCE_CHANGED')
    module=types.ModuleType('editor_owned_'+Path(path).stem);module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__);return module
def expired(signum,frame):raise TimeoutError('EDITOR_DEADLINE_NO_REPLAY')

def key_context(reference,current):
    # Keyboard events target the native focused editor. Pixel repainting is
    # observed, but a pixel hash is not the identity of that keyboard target.
    fields=('package','activity','window_token','display_id','window_bounds','android_init_host_pid')
    need(all(reference['scope'][k]==current['scope'][k] for k in fields)
        and reference['context_token']==current['context_token'],'KEY_WINDOW_CONTEXT_CHANGED')
    need(current['scope']['package']==PACKAGE
        and current['scope']['activity']==PACKAGE+'.EditorContractActivity'
        and current['scope']['display_id']==0,'KEY_TARGET_SCOPE_CHANGED')
    return {k:current[k] for k in ('frame_sha256','scope_sha256','context_token','captured_unix_ms')}

def fp(info):return {k:getattr(info,k) for k in ('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')}

def identity(session):
    raw,_=session.target.read_file(APK,65536,single_link=True)
    need(len(raw)==20883 and sha(raw)==APK_SHA,'EDITOR_APK_CHANGED')
    paths=session.android(['/system/bin/pm','path','--user','0',PACKAGE]).decode().splitlines()
    need(paths==['package:'+APK],'ACTIVE_APK_CHANGED')
    dump=session.android(['/system/bin/dumpsys','package',PACKAGE]).decode()
    sections=re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)',dump,re.M|re.S)
    need(len(sections)==1,'PACKAGE_SECTION_AMBIGUOUS');active=sections[0]
    def one(pattern):
        values=re.findall(pattern,active,re.M);need(len(values)==1,'PACKAGE_FIELD_UNKNOWN');return values[0]
    value={'uid':int(one(r'^    appId=(\d+)$')),'version':int(one(r'^    versionCode=(\d+)\b')),
        'data_dir':one(r'^      dataDir=(.*)$'),'android_user':0,'apk_sha256':APK_SHA,
        'epoch_sha256':session.epoch_sha256,
        'permission_lines':sorted(line.strip() for line in active.splitlines() if re.search(r'android\.permission\.[^:]+: granted=',line))}
    need(value['uid']==UID and value['version']==1 and value['data_dir']=='/data/user/0/'+PACKAGE,'EDITOR_IDENTITY_CHANGED')
    session.guard();return value

class Evidence:
    def __init__(self,trial,run):
        self.t=trial;self.run=run;self.path='/data/user/0/'+PACKAGE+'/files/editor-contract-v1'
        self.names=[run+'.json',run+'.claim'];self.final=None;self.cleaned=False;self.intent_submitted=False

    def absent(self):
        for suffix in ('.claim','.json','.json.new','.json.bak'):
            try:fd=self.t.s.target.open_root(self.path+'/'+self.run+suffix,os.O_RDONLY|os.O_NOFOLLOW)
            except FileNotFoundError:continue
            else:os.close(fd);raise RuntimeError('RUN_IDENTIFIER_ALREADY_USED')
        self.t.record('nonce-absent-'+self.run,{'run':self.run,'exact_files_absent':True,'no_file_writes':True})

    def read(self,label,ready=False):
        raw,meta=self.t.s.target.read_file(self.path+'/'+self.run+'.json',65536,single_link=True)
        value=json.loads(raw)
        need(value.get('schema')=='p4-owned-editor-contract-v1' and value.get('run_id')==self.run
            and value.get('package')==PACKAGE and value.get('uid')==UID and value.get('collection_only') is True,
            'EXACT_OWNED_APP_RECORD_REQUIRED')
        need(value.get('field_id')==0x100901 and value.get('single_line') is True
            and value.get('advertised_action')==3 and value.get('max_events')==96
            and value.get('max_bytes')==65536 and value.get('dropped_events')==0,'EDITOR_CONTRACT_BOUND_CHANGED')
        events=value.get('events');need(isinstance(events,list) and 0<len(events)<=96
            and [e.get('sequence') for e in events]==list(range(1,len(events)+1)),'EVENT_SEQUENCE_INVALID')
        if ready:need(value.get('ready') is True and value.get('window_focused') is True
            and value.get('editor_focused') is True and value.get('input_connection_count',0)>0,'EDITOR_NOT_READY')
        self.t.record(label,{'sha256':sha(raw),'metadata':meta,'record':value})
        return value

    def cleanup(self):
        need(self.t.owned is None,'TASK_MUST_BE_CLOSED_BEFORE_FILE_CLEANUP')
        value=self.read('closed-record-'+self.run)
        directory=self.t.s.target.open_root(self.path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        held=[]
        try:
            need(os.fstat(directory).st_uid==UID,'EVIDENCE_DIRECTORY_OWNER_CHANGED')
            for name in (self.run+'.json.new',self.run+'.json.bak'):
                try:os.stat(name,dir_fd=directory,follow_symlinks=False)
                except FileNotFoundError:continue
                raise RuntimeError('ATOMIC_WRITE_IN_PROGRESS_PRESERVE')
            for name in self.names:
                fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory)
                held.append((name,fd));info=os.fstat(fd)
                need(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==UID
                    and info.st_size<65536,'OWNED_FILE_IDENTITY_CHANGED')
                data=os.read(fd,65537)
                need(fp(os.fstat(fd))==fp(info) and fp(os.stat(name,dir_fd=directory,follow_symlinks=False))==fp(info),
                    'OWNED_FILE_CHANGED_DURING_READ')
                if name.endswith('.claim'):need(data==b'','CLAIM_NOT_EMPTY')
                else:need(json.loads(data)==value,'FINAL_APP_RECORD_CHANGED')
                self.t.record('exact-file-delete-intent',{'run':self.run,'name':name,'identity':fp(info),'sha256':sha(data),'automatic_retry':False})
            # Recheck both held file identities before either unlink.
            for name,fd in held:need(fp(os.stat(name,dir_fd=directory,follow_symlinks=False))==fp(os.fstat(fd)),'FILE_REPLACED_BEFORE_CLEANUP')
            for name,fd in held:os.unlink(name,dir_fd=directory)
            for name in self.names:
                try:os.stat(name,dir_fd=directory,follow_symlinks=False)
                except FileNotFoundError:continue
                raise RuntimeError('OWNED_FILE_NOT_REMOVED')
            self.cleaned=True;self.final=value
            self.t.record('owned-files-cleaned-'+self.run,{'only_exact_run_files':self.names,'other_entries_not_modified':True})
        finally:
            for name,fd in held:os.close(fd)
            os.close(directory)

class Flow:
    def __init__(self,trial,loop,result):
        self.t,self.loop,self.r=trial,loop,result;self.c=loop.Continuation(trial,PACKAGE)
        self.owned=[];self.closed=[];self.evidence=[];self.actions=0;self.current=None;self.intent_calls=0

    def node(self,expected=None):
        nodes=[n for n in self.c.nodes if n.get('package')==PACKAGE and n.get('visible') is True
            and n.get('enabled') is True and n.get('editable') is True and n.get('password') is False]
        need(len(nodes)==1,'ONE_ACTUAL_PLAIN_EDITOR_REQUIRED');n=nodes[0]
        need(n.get('hint')=='Owned editor contract' and n.get('focused') is True,'OWNED_EDITOR_NOT_FOCUSED')
        if expected is not None:need(n.get('text')==expected or expected=='' and n.get('text')==n.get('hint'),'EXACT_EDITOR_TEXT_REQUIRED')
        return n

    def text(self,label,value,expected):
        n=self.node(expected);need(self.actions<20 and self.c.pending is None,'ACTION_LIMIT_OR_PENDING')
        selector={'class':n['class'],'editable':True,'focused':True,'text':n['text']}
        if n.get('resource-id'):selector['id']=n['resource-id']
        before=self.c.actions
        try:self.c.step({'id':label,'op':'set-text','observation':self.c.latest,'selector':selector,'value':value})
        finally:self.actions+=self.c.actions-before
        self.node(value)

    def key(self,label,key,expected):
        need(key in ('KEYCODE_ENTER','KEYCODE_MOVE_END','KEYCODE_DEL') and self.actions<20
            and self.c.pending is None,'KEY_SCOPE_OR_ACTION_BOUND')
        old=self.node(expected);previous=self.t.last_observation['screenshot']
        self.c.observe('fresh-'+label,publish=False);new=self.node(expected)
        need(self.loop.node_identity(new)==self.loop.node_identity(old),'EDITOR_NODE_CHANGED')
        current=self.t.last_observation['screenshot'];key_context(previous,current)
        request={'package':PACKAGE,'display':0,'accessibility_mode':'none',
            'window_token':current['scope']['window_token']}
        observed=[key_context(previous,current)]
        for _ in range(2):
            frame=self.t.s.helper.capture(request)
            observed.append(key_context(current,frame['meta']))
        # Re-query the actual native focused field after captures. Do not mask
        # changed text, a second editor, lost focus, a task switch or geometry.
        self.c.observe('native-before-'+label,publish=False);final=self.node(expected)
        need(self.loop.node_identity(final)==self.loop.node_identity(new),'EDITOR_CHANGED_BEFORE_KEY')
        finalshot=self.t.last_observation['screenshot'];observed.append(key_context(current,finalshot))
        self.current.read('app-ready-before-'+label,True)
        focus=self.t.ready_focus(False)
        # Trial's WM record and helper's native window metadata have distinct
        # real schemas. Validate each directly; do not invent missing fields.
        need(focus.get('verified') is True and focus.get('task')==self.t.owned[0]
            and focus.get('user')==0
            and all(focus.get(k)==finalshot['scope'][k] for k in ('package','activity','window_token')),
            'KEY_OWNED_TASK_FOCUS_CHANGED')
        window=self.t.s.helper.window_state(PACKAGE,focus['window_token'],0,'none')
        need(self.t.s.helper.stable_window(window)==self.t.s.helper.stable_window(finalshot['scope']),
            'KEY_NATIVE_WINDOW_CONTEXT_CHANGED')
        argv=['/system/bin/input','keyboard','-d','0','keyevent',key]
        self.t.record(label+'-intent',{'argv':argv,'node':final,'owned_task':self.t.owned[0],
            'automatic_retry':False,'target_binding':'same native focused editor plus fixed window/task/context',
            'pixel_observations':observed,'pixel_equality_required_for_keyboard':False,
            'final_owned_task_focus':focus,'final_native_window_context':window})
        self.c.pending=label;self.actions+=1
        self.t.s.android(argv,12);self.t.s.guard();self.c.observe('after-'+label)
        self.c.pending=None

    def start(self,index):
        ev=Evidence(self.t,RUN+'_'+str(index));ev.absent();self.evidence.append(ev);self.current=ev
        self.c.pending='native-launch-'+str(index);self.t.launch();self.owned.append(self.t.owned[0]);self.c.pending=None
        self.c.observe('native-'+str(index))
        need(any(n.get('text')=='A unique run identifier is required' and n.get('package')==PACKAGE
            and n.get('visible') is True for n in self.c.nodes),'DECLARED_EMPTY_INTENT_SCREEN_REQUIRED')
        task=self.t.owned[0];focus=self.t.ready_focus(False);ev.absent()
        argv=['/system/bin/am','start-activity','-W','--user','0','--display','0','--task',str(task),
            '--activity-clear-top','-n',COMPONENT,'--es','run_id',ev.run]
        self.t.record('nonce-launch-intent-'+str(index),{'argv':argv,'owned_task':task,'automatic_retry':False})
        self.c.pending='nonce-launch-'+str(index)
        ev.intent_submitted=True;self.intent_calls+=1
        raw=self.t.s.android(argv,35).decode();self.t.record('nonce-launch-result-'+str(index),{'stdout':raw})
        need(re.findall(r'^Status:\s*(\S+)',raw,re.M)==['ok'] and 'Error:' not in raw and 'Exception' not in raw,'NONCE_LAUNCH_UNKNOWN')
        self.c.observe('nonce-'+str(index));need(self.t.owned[0]==task,'OWNED_TASK_CHANGED')
        initial=ev.read('editor-ready-'+str(index),True);need(initial['text_length']==0 and initial['editor_action_count']==0,'INITIAL_EDITOR_STATE_CHANGED')
        self.node('');self.c.pending=None;return ev

    def close(self):
        if self.t.owned is None:return
        task=self.t.owned[0];count=self.t.removals;self.t.close()
        need(self.t.removals==count+1 and self.t.result.get('other_tasks_preserved') is True,'NORMAL_CLOSE_UNVERIFIED')
        self.closed.append(task)

    def run(self):
        for index in range(2):
            ev=self.start(index);value='Pocket4 editor %d 中文 café 😀'%index
            self.text('unicode-'+str(index),value,'')
            before=ev.read('before-enter-'+str(index),True)
            self.key('enter-one-'+str(index),'KEYCODE_ENTER',value);self.node(value)
            first=ev.read('after-first-enter-'+str(index),True)
            need(first['editor_action_count']>before['editor_action_count'],'FIRST_ENTER_NOT_DELIVERED')
            self.key('enter-two-'+str(index),'KEYCODE_ENTER',value);self.node(value)
            second=ev.read('after-second-enter-'+str(index),True)
            need(second['editor_action_count']>first['editor_action_count'],'SECOND_ENTER_NOT_DELIVERED')
            self.key('move-end-'+str(index),'KEYCODE_MOVE_END',value);self.node(value)
            self.key('delete-emoji-'+str(index),'KEYCODE_DEL',value);self.node(value[:-1])
            self.text('clear-'+str(index),'',value[:-1]);self.node('')
            self.close();need(self.c.pending is None,'UNKNOWN_INPUT_PRESERVE_EVIDENCE');ev.cleanup()
            self.r['rounds'].append({'run':ev.run,'task':self.closed[-1],
                'unicode_readback_verified':True,'keyboard_enter_counts':[before['editor_action_count'],first['editor_action_count'],second['editor_action_count']],
                'single_emoji_deletion_verified':True,'cleared':True,'owned_record_removed':ev.cleaned})

def execute():
    need(re.fullmatch('[0-9a-f]{64}',TASK_PROOF_SHA) is not None,'EXACT_TASK_OPTION_PROOF_NOT_REVIEWED')
    need(sha(TASK_PROOF.read_bytes())==TASK_PROOF_SHA,'TASK_OPTION_PROOF_CHANGED')
    base,loop,diagnostic=[load(p,h) for p,h in PINS.items()];tx=base.load_session()
    base.PACKAGE,base.COMPONENT,base.ROOT=PACKAGE,COMPONENT,ROOT;diagnostic.PACKAGE=PACKAGE;loop.emit=lambda value:None
    result={'schema':'pocket4-editor-ui-core-v2','state':'FAILED','whole_app_production_ready':False,
        'automatic_retry':False,'source_pins':PINS,'task_option_proof_sha256':TASK_PROOF_SHA,'rounds':[],'started_utc':stamp(),'lease_seconds':LEASE,'cleanup_seconds':RESERVE,
        'scope':'Native task plus exact owned-task intent; focused-native-editor keyboard binding; Unicode, two keyboard Enter commands, emoji deletion and independent reopen.',
        'prior_editor01_exact_cleanup_result_sha256':'3dd4f2c5aaf76a6e9a2f6821e73ff256a063e87dda7f7b0c4ed5fe1498b13f51'}
    flow=None;old=signal.signal(signal.SIGALRM,expired)
    try:
        with tx.ui_lock():
            ROOT.mkdir(mode=0o700);signal.setitimer(signal.ITIMER_REAL,LEASE)
            with tx.CameraSession(ROOT/'commands') as s:
                trial=base.Trial(s,tx);flow=Flow(trial,loop,result);diagnostics=diagnostic.Trial(s,tx,ROOT)
                try:
                    result['identity_before']=identity(s);before=diagnostics.diagnostics('before',UID)
                    diagnostic.exit_events(before['exits']);flow.run()
                    after=diagnostics.diagnostics('after',UID);result['diagnostics']=diagnostic.fresh_crashes(before,after,UID,before['guest_seconds'])
                    need(result['diagnostics']['clear'],'FRESH_EDITOR_CRASH_OR_ANR')
                    result['identity_after']=identity(s);need(result['identity_after']==result['identity_before'],'EDITOR_IDENTITY_OR_PERMISSION_CHANGED')
                    need(len(flow.closed)==2 and flow.closed==flow.owned and flow.c.pending is None,'LIFECYCLE_INCOMPLETE')
                    result['state']='UNICODE_KEYBOARD_ENTER_DELETE_REOPEN_CLEANUP_VERIFIED';s.caller_status('editor-final-caller')
                except BaseException as exc:result['error']=type(exc).__name__+': '+str(exc)
                finally:
                    signal.setitimer(signal.ITIMER_REAL,RESERVE)
                    try:flow.close()
                    except BaseException as exc:result['cleanup_error']=type(exc).__name__+': '+str(exc)
                    # Unknown input or nonce launch leaves exact records for a separate read-only reconciliation.
                    result['owned_nonces_requiring_reconciliation']=[ev.run for ev in flow.evidence if ev.intent_submitted and not ev.cleaned]
                    result['guard_after']=s.guard()
    except BaseException as exc:result.update(state='FAILED',terminal_error=type(exc).__name__+': '+str(exc))
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
        result.update(finished_utc=stamp(),ui_actions=flow.actions if flow else 0,pending_effect=flow.c.pending if flow else None,
            owned_tasks=flow.owned if flow else [],closed_tasks=flow.closed if flow else [],
            native_launch_calls=flow.t.launches if flow else 0,nonce_intent_calls=flow.intent_calls if flow else 0)
        if ROOT.is_dir():tx.write_new(ROOT/'result.json',result)
        tx.write_new(HERE/'editor-ui03-result.json',result,alex_readable=True)
        print(json.dumps({k:result.get(k) for k in ('state','error','terminal_error','ui_actions','pending_effect','owned_tasks','closed_tasks','owned_nonces_requiring_reconciliation')}))
    return 0 if result['state']=='UNICODE_KEYBOARD_ENTER_DELETE_REOPEN_CLEANUP_VERIFIED' else 1

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--execute',action='store_true');args=ap.parse_args()
    if args.execute:raise SystemExit(execute())
    print(json.dumps({'state':'INERT','task_option_proof_reviewed':bool(re.fullmatch('[0-9a-f]{64}',TASK_PROOF_SHA)),'ui_actions':0,'package_changes':0}))
