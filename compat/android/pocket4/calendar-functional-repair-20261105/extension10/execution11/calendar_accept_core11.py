#!/usr/bin/python3 -I
"""Calendar first-use + one-event UI round. Default inert, continued by unique JSONL decisions."""
from pathlib import Path
import argparse, hashlib, json, os, re, signal, sys, time, types

PROFILE_TX=Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
PROFILE_TX_SHA='b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
PROFILE_ACTIVATION_SHA='7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'

HERE=Path(__file__).resolve().parent
ROOT=Path('/home/alex/work/pocket4-calendar-accept-core-20261105-r12-11')
ORIGINAL=Path('/home/alex/work/pocket4-calendar-flow-tools-20261105-r12-01/run_calendar01.py')
ORIGINAL_SHA='d307f4ceda9fc80e216f280cb1a9558fbe4e27b43cd659ecc83a1c6edab9c8fa'
INSTALL=Path('/home/alex/work/pocket4-calendar-repair-install-20261105-r12-10/result.json')
NEW_SHA='7872aa56b6aa35f4509a27a2c3c0ebb8743da7096136155e425f5b1e4499ae8e'
PROVIDER_SHA='eebf12f81981f7d8c59a9b9ed465945818d2ab0208c121d858cbc4e6426f5fff'
READER_SHA='1231e9c430a81b0af062c104b35516c3d2127e3e1cc43b78d15ffb2a5224f436'
ADAPTER_SHA='e983973141e4cb77cf5c26f9e9526fdec25fa3331cd3f24a313bef7704878aa9'
PROBE=Path('/home/alex/work/pocket4-calendar-shell-query-tools-20261105-r12-02/probe_shell_cleanup02.py')
PROBE_SHA='3696994fe45fba3152418e32667ac3ac6ed437cf5191189bfe65a27f21bccb88'
ATOMIC_SHA='1d66de839c05c11983196764d44c518175bc10481cff754b850d6034c8533796'
LEASE_SECONDS=720
CLEANUP_SECONDS=90
REQUIRED={'explicit_first_use_local_calendar','cancel_unsaved_without_event_write',
          'created_in_calendar_ui','edited_same_event','normal_close_reopen_detail','deleted_in_calendar_ui'}

def load(path,pin,name):
    raw=path.read_bytes();need(hashlib.sha256(raw).hexdigest()==pin,'SOURCE_CHANGED:'+name)
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__);return module

def need(value,reason):
    if not value:raise RuntimeError(reason)

def emit(value):print(json.dumps(value,ensure_ascii=True,separators=(',',':')),flush=True)

def flow_class(m,model,base,probe):
    class CoreFlow(m.Flow):
        def __init__(self,s,tx,base,doc,diag):
            super().__init__(s,tx,base,doc,diag)
            self.model=model.Model(s,self.record);self.business_pending=None
            self.cleanup_pending=False;self.cleanup_calls=0;self.roles={};self.role_tokens={};self.scrolls=0
            self.result={'schema':'calendar-first-use-event-ui-v1','state':'FAILED','started_utc':m.stamp(),
                'run_id':model.RUN,'candidate_apk_sha256':NEW_SHA,'gates':{},'ui_roles':[],
                'transport_sha256':PROFILE_TX_SHA,'activation_sha256':PROFILE_ACTIVATION_SHA,
                'automatic_retry':False,'whole_app_production_ready':False,'package_mutations':0,
                'permission_changes':0,'account_operations':0,'helper_event_writes':0,
                'provider_write_commands_excluding_empty_calendar_cleanup':0,
                'reader_sha256':READER_SHA,'private_adapter_sha256':ADAPTER_SHA,
                'atomic_empty_delete_review_sha256':ATOMIC_SHA,
                'lease_seconds':LEASE_SECONDS,'cleanup_seconds':CLEANUP_SECONDS}

        def setup(self):
            self.result['guard_before']=self.s.guard()
            installed_raw=self.tx.read_regular(INSTALL,maximum=65536);installed=json.loads(installed_raw)
            self.result['verified_installer_receipt_sha256']=hashlib.sha256(installed_raw).hexdigest()
            need(installed['state']=='INSTALLED_VERIFIED_NOT_BUSINESS_QUALIFIED' and
                installed['new_sha256']==NEW_SHA and installed['install_calls']==1 and
                not installed['install_pending'] and installed['guard_after']==self.result['guard_before'],
                'VERIFIED_CANDIDATE_INSTALL_REQUIRED')
            need(m.sha(m.TASK_PROOF.read_bytes())==m.TASK_PROOF_SHA,'ACTUAL_TASK_OPTION_PROOF_REQUIRED')
            self.result['calendar_before']=self.calendar_identity()
            self.result['provider_before']=self.doc.identity(self.s,'com.android.providers.calendar',PROVIDER_SHA,10017,37)
            self.result['existing_shell_calendar_permissions']=self.shell_grants()
            roots,tasks=self.ui.stacks('first-use-baseline')
            need(not any(c['component'].split('/')[0] in (m.CALENDAR,m.PACKAGE)
                for r in roots.values() for c in r['children']),'PREEXISTING_CALENDAR_TASK')
            self.ui.baseline=set(tasks);self.result['baseline_task_ids']=sorted(tasks)
            self.baseline_counts=self.counts('first-use-baseline');need(not any(self.baseline_counts.values()),'FRESH_ZERO_CALENDAR_BASELINE')
            value=self.model.read('baseline');self.model.require_empty(value)
            self.before_diag=self.diagnostics.diagnostics('before',10061)
            now=self.before_diag['guest_seconds'];need(type(now) in (int,float),'GUEST_TIME_REQUIRED')
            begin=(int(now)//86400+8)*86400000+12*3600000
            self.lease={'dtstart':begin,'dtend':begin+2700000,'calendar_id':-1,'event_id':-1}
            self.result['intended_event']={'title':model.TITLE,'edited_title':model.EDITED,
                'begin_utc_ms':begin,'end_utc_ms':begin+2700000,'reminders':0,'attendees':0}
            self.phase='FIRST_USE';self.ui.launch();self.observe('first-use-calendar')

        def shell_grants(self):
            raw=self.s.android(['/system/bin/pm','list','packages','-U','--user','0','com.android.shell'],12).decode()
            need([line for line in raw.splitlines() if line.startswith('package:com.android.shell ')]==
                 ['package:com.android.shell uid:2000'],'ACTUAL_SHELL_UID_REQUIRED')
            rows=probe.shared_shell_permission_rows(self.s.android(
                ['/system/bin/dumpsys','package','com.android.shell'],15).decode())
            need(all(m.permission_granted(rows,name) for name in m.GRANTS),'EXISTING_SHELL_CALENDAR_GRANTS_REQUIRED')
            return [row for row in rows if any(row.startswith(name+':') for name in m.GRANTS)]

        def snapshot(self,label):
            value=self.model.read(label)
            emit({'type':'owned-provider-observation','phase':self.phase,'value':value,
                'business_pending':self.business_pending,'ui_pending':self.ui.pending})
            return value

        def wait_state(self,kind):
            deadline=time.monotonic()+35
            for attempt in range(6):
                value=self.model.read('verify-'+kind+'-'+str(attempt+1))
                try:
                    if kind in ('calendar','cancel','deleted'):self.model.require_no_event(value)
                    else:self.model.require_event(value,model.EDITED if kind in ('edited','reopened') else model.TITLE,
                        self.lease['dtstart'],self.lease['dtend'])
                    return value
                except RuntimeError:
                    # No input is repeated. The immutable snapshot is still in the
                    # journal; only asynchronous provider completion may be awaited.
                    if attempt==5 or time.monotonic()+15>deadline:raise
                    time.sleep(.4)
            raise RuntimeError('PROVIDER_STATE_NOT_OBSERVED')

        def finish_business(self,role,proof):
            need(self.business_pending is not None and self.business_pending['role']==role,'EXACT_PENDING_BUSINESS_ROLE_REQUIRED')
            token=self.business_pending['token']
            if token in self.ui.pending:
                old=self.ui.pending[token]
                need(old.get('kind')=='tap','UNKNOWN_NONBUSINESS_INPUT_RETAINED')
                self.record('business-input-readback-reconciled',{'token':token,'original_pending':old,
                    'proof':proof,'action_replayed':False,'original_ack_rewritten':False})
                del self.ui.pending[token]
            need(not self.ui.pending,'ANOTHER_INPUT_STILL_PENDING')
            self.business_pending=None

        def role_node(self,role,kind,node,value):
            text=node.get('text');hint=node.get('hint');desc=node.get('content-desc')
            activity=self.obs['focus']['activity']
            if role=='scroll-form':
                need(kind in ('scroll-forward','scroll-backward') and value is None and self.scrolls<8 and
                     node.get('scrollable') is True and node.get('class')=='android.widget.ScrollView' and
                     activity in (m.EDITOR,m.EDITOR_ALIAS,m.INFO),'OBSERVED_OWNED_FORM_SCROLL_ONLY');return
            buttons={'open-new':{'New event'},'local-open':{'Create local calendar'},
                'local-confirm':{'Create'},'cancel-open':{'Cancel'},'cancel-confirm':{'Discard'},
                'save-create':{'Save'},'open-edit':{'Edit'},'save-edit':{'Save'},
                'delete-open':{'Delete'},'delete-confirm':{'Delete'}}
            if kind=='set-text':
                need(node.get('editable') is True and node.get('password') is not True,'OWNED_EDITABLE_FIELD_REQUIRED')
                allowed={'local-name':model.CALENDAR_LABEL,'cancel-title':model.UNSAVED,'edit-title':model.EDITED}
                need(role in allowed and value==allowed[role],'ONLY_REVIEWED_OWNED_TEXT')
                if role=='local-name':need(hint=='Calendar name' or text=='On this device','LOCAL_NAME_FIELD')
                elif role=='cancel-title':need(hint=='Title' or text=='Title','UNSAVED_TITLE_FIELD')
                else:need(text==model.TITLE and activity in (m.EDITOR,m.EDITOR_ALIAS),'EXACT_EXISTING_TITLE_FIELD')
                return
            need(kind=='tap' and value is None,'TAP_OR_REVIEWED_TEXT_ONLY')
            if role=='open-menu':
                need(activity==m.MAIN and desc=='More options','OWNED_MAIN_OVERFLOW_ONLY');return
            if role in ('focus-cancel-title','focus-local-name','focus-edit-title'):
                need(node.get('editable') is True and ((role=='focus-cancel-title' and (hint=='Title' or text=='Title'))
                    or (role=='focus-local-name' and (hint=='Calendar name' or text=='On this device'))
                    or (role=='focus-edit-title' and text==model.TITLE)),'EXACT_OWNED_FOCUS_FIELD');return
            need(role in buttons and (text in buttons[role] or desc in buttons[role]),'OBSERVED_SEMANTIC_ROLE_MISMATCH')
            need(node.get('clickable') is True,'CLICKABLE_ROLE_REQUIRED')
            if role=='open-new':need(activity==m.MAIN,'MAIN_NEW_EVENT_ENTRY_REQUIRED')
            elif role in ('open-edit','delete-open'):need(activity==m.INFO,'OWNED_DETAIL_ACTION_REQUIRED')
            else:need(activity in (m.EDITOR,m.EDITOR_ALIAS,m.INFO),'CALENDAR_EDITOR_OR_DETAIL_REQUIRED')
            if role=='local-confirm':need(self.roles.get('local-name')==1,'OWNED_LOCAL_LABEL_REQUIRED')
            if role=='cancel-open':need(self.roles.get('cancel-title')==1,'ACTUAL_UNSAVED_FORM_CHANGE_REQUIRED')
            if role=='save-edit':need(self.roles.get('edit-title')==1,'EXACT_TITLE_EDIT_REQUIRED')
            if role.endswith('confirm'):need(node.get('resource-id')=='android:id/button1','POSITIVE_CONFIRMATION_BUTTON_REQUIRED')

        def input_step(self,c):
            need(self.business_pending is None and not self.ui.pending,'UNKNOWN_INPUT_READ_ONLY_UNTIL_RECONCILED')
            need(c.get('view')==self.view_id and self.obs is not None,'LATEST_SNAPSHOT_TOKEN_REQUIRED')
            index=c.get('node');need(type(index) is int and 0<=index<len(self.obs['nodes']),'OBSERVED_NODE_INDEX')
            role=c.get('role');kind=c.get('kind','tap');node=self.obs['nodes'][index];value=c.get('value')
            allowed={'FIRST_USE':{'open-new','open-menu','local-open','local-name','focus-local-name','local-confirm'},
                'CANCELLING':{'focus-cancel-title','cancel-title','cancel-open','cancel-confirm'},
                'CREATING':{'save-create'},'CREATED':{'open-edit'},'EDITING':{'focus-edit-title','edit-title','save-edit'},
                'REOPENED':{'delete-open','delete-confirm'}}
            if self.phase in allowed:allowed[self.phase].add('scroll-form')
            need(role in allowed.get(self.phase,set()) and (role=='scroll-form' or self.roles.get(role,0)==0),
                 'ONE_ROLE_IN_CURRENT_PHASE_NO_REPLAY')
            self.role_node(role,kind,node,value)
            token='core-'+c['id'];business=role in ('local-confirm','save-create','save-edit','delete-confirm')
            if business:self.business_pending={'role':role,'token':token}
            self.record('role-intent',{'role':role,'phase':self.phase,'token':token,'node':node,'kind':kind,
                'value':value,'business_write_expected':business,'automatic_retry':False})
            if role=='open-menu':
                # The imported adapter is private to this session. Its existing
                # acknowledged-popup fence is restricted to our Main Activity.
                base.FILES=m.MAIN
            try:self.ui.input(self.obs,token,node,kind=kind,value=value,popup=role=='open-menu')
            except BaseException:
                if token not in self.ui.pending:
                    # Source-proven pre-dispatch failure or explicit native no-effect.
                    # The original rejection receipt remains; a new observation and
                    # new command ID are required for any later decision.
                    if business:self.business_pending=None
                else:
                    self.roles[role]=self.roles.get(role,0)+1;self.role_tokens[role]=token
                    if role=='scroll-form':self.scrolls+=1
                raise
            self.roles[role]=self.roles.get(role,0)+1;self.role_tokens[role]=token
            if role=='scroll-form':self.scrolls+=1
            self.result['ui_roles'].append({'role':role,'token':token,'kind':kind,'phase':self.phase})
            self.observe('after-'+c['id'])
            if role=='open-edit':
                need(self.obs['focus']['activity'] in (m.EDITOR,m.EDITOR_ALIAS),'EDITOR_ROUTE_NOT_OBSERVED');self.phase='EDITING'

        def verify(self,kind):
            if kind=='calendar':
                need(self.phase=='FIRST_USE' and self.roles.get('local-confirm')==1,'UI_LOCAL_CREATE_REQUIRED')
                value=self.wait_state('calendar');self.finish_business('local-confirm',value)
                self.lease['calendar_id']=self.model.calendar['_id']
                self.result['gates']['explicit_first_use_local_calendar']=value
                self.phase='CANCELLING';self.observe('created-calendar-empty-event-form');return
            if kind=='cancel':
                need(self.phase=='CANCELLING' and self.roles.get('cancel-open')==self.roles.get('cancel-confirm')==1,
                    'UI_CANCEL_AND_DISCARD_REQUIRED')
                value=self.wait_state('cancel');need(not self.ui.pending,'CANCEL_INPUT_STILL_UNKNOWN')
                need(self.observe('cancel-returned-to-calendar')['focus']['activity']==m.MAIN,'CANCEL_DID_NOT_RETURN_TO_CALENDAR')
                self.result['gates']['cancel_unsaved_without_event_write']=value
                self.phase='CREATING';self.route('insert');return
            if kind=='created':
                need(self.phase=='CREATING' and self.roles.get('save-create')==1,'UI_CREATE_SAVE_REQUIRED')
                value=self.wait_state('created');self.finish_business('save-create',value)
                self.event_id=self.model.event_id;self.lease['event_id']=self.event_id
                self.result['gates']['created_in_calendar_ui']=value;self.phase='CREATED';self.route('view');return
            if kind=='edited':
                need(self.phase=='EDITING' and self.roles.get('save-edit')==1,'UI_EDIT_SAVE_REQUIRED')
                value=self.wait_state('edited');self.finish_business('save-edit',value)
                self.result['gates']['edited_same_event']=value;self.phase='EDITED';return
            if kind=='deleted':
                need(self.phase=='REOPENED' and self.roles.get('delete-open')==self.roles.get('delete-confirm')==1,
                    'UI_DELETE_CONFIRMATION_REQUIRED')
                value=self.wait_state('deleted');self.finish_business('delete-confirm',value)
                self.result['gates']['deleted_in_calendar_ui']=value;self.phase='DELETED';return
            raise RuntimeError('VERIFICATION_KIND_NOT_ALLOWED')

        def reopen(self):
            need(self.phase=='EDITED' and not self.business_pending and not self.ui.pending,'EDIT_NOT_VERIFIED_BEFORE_CLOSE')
            self.ui.close_all();need(self.ui.removals==len(self.ui.closed)==1,'ONE_NORMAL_CLOSE_REQUIRED')
            value=self.wait_state('edited');self.record('closed-event-persistence',value)
            self.ui.launch();self.route('view');observed=self.observe('reopened-exact-detail')
            need(observed['focus']['activity']==m.INFO and any(n.get('text')==model.EDITED for n in observed['nodes']),
                'EDITED_DETAIL_NOT_VISIBLE_AFTER_REOPEN')
            value=self.wait_state('reopened')
            self.result['gates']['normal_close_reopen_detail']={'provider':value,'owned_task':observed['focus']['task'],
                'display_text':[n.get('text') for n in observed['nodes'] if n.get('text')]}
            self.phase='REOPENED'

        def step(self,c):
            need(isinstance(c,dict) and not set(c)-{'id','op','view','node','kind','value','role'},'COMMAND_SCHEMA')
            ident=c.get('id');need(isinstance(ident,str) and re.fullmatch('[a-z][a-z0-9-]{0,39}',ident)
                and ident not in self.seen and len(self.seen)<48,'UNIQUE_BOUNDED_COMMAND_ID')
            self.seen.add(ident);self.record('command-'+ident,c)
            op=c.get('op')
            if op=='abort':return False
            if op=='observe':
                observed=self.observe('observe-'+ident)
                if (self.phase=='CREATED' and self.roles.get('open-edit')==1 and not self.ui.pending and
                    observed['focus']['activity'] in (m.EDITOR,m.EDITOR_ALIAS)):
                    self.phase='EDITING'
                return True
            if op=='inspect':self.snapshot(ident);return True
            if op=='input':self.input_step(c);return True
            if op in ('verify-calendar','verify-cancel','verify-created','verify-edited','verify-deleted'):
                self.verify(op[7:]);return True
            if op=='reopen':self.reopen();return True
            need(op=='finish' and self.phase=='DELETED' and set(self.result['gates'])==REQUIRED and
                not self.business_pending and not self.ui.pending,'ALL_CORE_GATES_REQUIRED')
            self.result['business_scope_completed']=True;return False

        def cleanup(self):
            result={'errors':[],'calendar_removed':False,'provider_baseline_restored':False}
            try:self.ui.close_all()
            except BaseException as exc:result['errors'].append('owned-task:'+type(exc).__name__+':'+str(exc))
            try:
                need(not self.ui.owned and not self.ui.pending and not self.business_pending and not self.cleanup_pending,
                    'UNKNOWN_EFFECT_RETAIN_OWNED_FIXTURE')
                value=self.model.read('before-empty-calendar-cleanup')
                if self.model.calendar is None:
                    self.model.require_empty(value);result['calendar_removed']=True
                else:
                    self.model.require_no_event(value)
                    need('deleted_in_calendar_ui' in self.result['gates'] or self.roles.get('save-create',0)==0,
                        'EVENT_UI_DELETE_NOT_VERIFIED_RETAIN_FIXTURE')
                    uri,where=self.model.deletion_request()
                    need(self.shell_grants()==self.result['existing_shell_calendar_permissions'],
                         'SHELL_CALENDAR_GRANTS_CHANGED')
                    argv=['/system/bin/content','query','--user','0','--uri',uri,'--projection','_id','--where',where]
                    raw=self.s.android(argv,15).decode()
                    need(raw=='Row: 0 _id='+str(self.model.calendar['_id'])+'\n','FRESH_GUARDED_CALENDAR_NOT_UNIQUE')
                    # Same actual provider collection DELETE path already proved
                    # to re-evaluate this complete empty predicate transactionally.
                    self.ui.check_tasks('before-empty-calendar-cleanup')
                    request=['/system/bin/content','delete','--user','0','--uri',uri,'--where',where]
                    self.record('empty-calendar-cleanup-intent',{'argv':request,'calendar':self.model.calendar,
                        'expected_events':0,'automatic_retry':False,
                        'provider_internal_side_effect':'May schedule unsubscribe for this same unregistered LOCAL account; no external account or sync API is used.'})
                    self.cleanup_pending=True;self.cleanup_calls+=1
                    output=self.s.android(request,20).decode();self.record('empty-calendar-cleanup-ack',{'stdout':output})
                    value=self.model.read('after-empty-calendar-cleanup');self.model.require_empty(value)
                    self.cleanup_pending=False;result['calendar_removed']=True
                result['provider_baseline_restored']=True
            except BaseException as exc:result['errors'].append('fixture:'+type(exc).__name__+':'+str(exc))
            return result
    return CoreFlow

def execute():
    m=load(ORIGINAL,ORIGINAL_SHA,'calendar_original_owned_flow')
    # Bind the independently approved original 12288 profile; original helper and guard sources remain intact.
    previous_tx=str(m.TX)
    need(m.PINS[previous_tx]=='b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470','ORIGINAL_TRANSPORT_PREIMAGE_CHANGED')
    m.PINS={str(PROFILE_TX) if path==previous_tx else path: PROFILE_TX_SHA if path==previous_tx else pin
            for path,pin in m.PINS.items()}
    m.TX=PROFILE_TX
    model=load(HERE/'read_owned_calendar11.py',READER_SHA,'calendar_core_owned_reader')
    tx,oldbase,doc,diag=[m.load(Path(p),pin,'calendar_core_dependency_'+str(i)) for i,(p,pin) in enumerate(m.PINS.items())]
    base=load(HERE/'calendar_ui11.py',ADAPTER_SHA,'calendar_private_ui')
    probe=load(PROBE,PROBE_SHA,'calendar_existing_shell_grants')
    proof_raw=(HERE/'atomic-delete-review.json').read_bytes()
    need(hashlib.sha256(proof_raw).hexdigest()==ATOMIC_SHA and
         json.loads(proof_raw)['provider_apk_sha256']==PROVIDER_SHA,'ATOMIC_PROVIDER_CHAIN_CHANGED')
    m.ROOT=ROOT;m.CALENDAR_SHA=NEW_SHA;m.TITLE=model.TITLE;m.EDITED=model.EDITED;m.TABLES=model.TABLES
    # Report actual focus/scroll state for subsequent semantic decisions; no input guard changes.
    m.NODE_FIELDS=(*m.NODE_FIELDS,'focused','focusable','scrollable','visible','window_id')
    base.PACKAGE=base.DOCS=m.CALENDAR;base.CLIENT=m.MAIN;base.FILES=m.INFO;diag.PACKAGE=m.CALENDAR
    # Profile creation changed only the activation binding; all guard logic is unchanged.
    need(m.PINS[str(m.TX)]==PROFILE_TX_SHA and tx.ACTIVATION_SHA==PROFILE_ACTIVATION_SHA,
         'REVIEWED_PROFILE_AND_UNCHANGED_GUARD_REQUIRED')
    cls=flow_class(m,model,base,probe);flow=None;result={'state':'FAILED','whole_app_production_ready':False}
    old=signal.signal(signal.SIGALRM,m.expired)
    try:
        with tx.ui_lock():
            need(not os.path.lexists(ROOT),'CREATE_ONLY_ACCEPTANCE_ROOT_REQUIRED')
            os.umask(0o077);ROOT.mkdir(mode=0o750);os.chown(ROOT,0,1000);os.chmod(ROOT,0o750)
            for name in ('ui','diagnostics'):(ROOT/name).mkdir(mode=0o700)
            signal.setitimer(signal.ITIMER_REAL,LEASE_SECONDS)
            with tx.CameraSession(ROOT/'commands') as s:
                flow=cls(s,tx,base,doc,diag);result=flow.result
                try:
                    flow.setup()
                    for _ in range(48):
                        raw=sys.stdin.buffer.readline(16385)
                        need(raw and len(raw)<=16384 and raw.endswith(b'\n'),'EOF_OR_COMMAND_BOUND')
                        c=json.loads(raw)
                        try:
                            if not flow.step(c):break
                        except Exception as exc:
                            flow.record('command-error',{'request':c,'error':type(exc).__name__+':'+str(exc),
                                'ui_pending':flow.ui.pending,'business_pending':flow.business_pending,'action_replayed':False})
                            emit({'type':'command-failed','request_id':c.get('id'),'error':str(exc),'phase':flow.phase,
                                'ui_pending':flow.ui.pending,'business_pending':flow.business_pending,'session_still_held':True})
                        else:emit({'type':'command-complete','request_id':c.get('id'),'phase':flow.phase})
                    else:raise RuntimeError('COMMAND_LIMIT_REACHED')
                except BaseException as exc:result['error']=type(exc).__name__+':'+str(exc)
                finally:
                    signal.setitimer(signal.ITIMER_REAL,CLEANUP_SECONDS);result['cleanup']=flow.cleanup()
                    try:
                        result['calendar_after']=flow.calendar_identity()
                        need(result['calendar_after']==result['calendar_before'],'CALENDAR_IDENTITY_CHANGED')
                        result['provider_after']=doc.identity(s,'com.android.providers.calendar',PROVIDER_SHA,10017,37)
                        need(result['provider_after']==result['provider_before'],'PROVIDER_IDENTITY_CHANGED')
                        result['final_counts']=flow.counts('final');need(not any(result['final_counts'].values()),'BASELINE_NOT_RESTORED')
                        _,tasks=flow.ui.check_tasks('final');result['task_set_restored']=not flow.ui.owned and tasks==flow.ui.baseline
                        need(result['task_set_restored'],'TASK_SET_NOT_RESTORED')
                        after=flow.diagnostics.diagnostics('after',10061)
                        result['diagnostics']=diag.fresh_crashes(flow.before_diag,after,10061,flow.before_diag['guest_seconds'])
                        need(result['diagnostics']['clear'],'FRESH_CALENDAR_CRASH_OR_ANR')
                        s.caller_status('calendar-core-final');result['guard_after']=s.guard()
                    except BaseException as exc:result['final_check_error']=type(exc).__name__+':'+str(exc)
                    if (result.get('business_scope_completed') and set(result['gates'])==REQUIRED and
                        not result['cleanup']['errors'] and result['cleanup']['calendar_removed'] and
                        result['cleanup']['provider_baseline_restored'] and not result.get('error') and
                        not result.get('final_check_error') and result.get('guard_after')==result.get('guard_before') and
                        flow.ui.launches==flow.ui.removals==len(flow.ui.closed)==2 and
                        not flow.ui.owned and not flow.ui.pending and not flow.business_pending and not flow.cleanup_pending):
                        result['state']='FIRST_USE_LOCAL_CALENDAR_AND_SINGLE_EVENT_UI_CORE_VERIFIED'
    except BaseException as exc:result['state']='FAILED';result['outer_error']=type(exc).__name__+':'+str(exc)
    finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
    if flow is not None:
        result.update(phase=flow.phase,ui_actions=flow.ui.actions,role_calls=flow.roles,ui_pending=flow.ui.pending,
            business_pending=flow.business_pending,owned_tasks=flow.ui.owned,normal_close_calls=flow.ui.removals,
            normally_closed_tasks=flow.ui.closed,native_launches=flow.ui.launches,intent_calls=flow.intent_calls,
            empty_calendar_cleanup_calls=flow.cleanup_calls,empty_calendar_cleanup_pending=flow.cleanup_pending,
            owned_calendar=flow.model.calendar,owned_event_id=flow.model.event_id)
    result['finished_utc']=m.stamp()
    if ROOT.is_dir():tx.write_new(ROOT/'result.json',result,alex_readable=True)
    emit({'type':'terminal','state':result['state'],'ui_pending':result.get('ui_pending'),
        'business_pending':result.get('business_pending'),'cleanup':result.get('cleanup')})
    return 0 if result['state']=='FIRST_USE_LOCAL_CALENDAR_AND_SINGLE_EVENT_UI_CORE_VERIFIED' else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    if not args.execute:
        emit({'state':'INERT','ui_inputs':0,'provider_mutations':0,'package_mutations':0,'lease_seconds':LEASE_SECONDS})
        raise SystemExit(0)
    raise SystemExit(execute())
