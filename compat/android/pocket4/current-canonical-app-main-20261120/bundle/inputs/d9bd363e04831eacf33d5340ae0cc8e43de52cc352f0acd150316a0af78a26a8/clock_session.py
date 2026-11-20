"""Fresh Clock identity, finite commands, owned tasks and actual ACK boundaries.

The original business state machines remain the decision makers. This session
binds their requests to this new Main, source packet and phase. It does not load
an old activation, mutate an old module's globals, or infer Binder cleanup from
host child retirement.
"""
import copy
import hashlib
import os
from pathlib import Path
import re
import time

PACKAGE='com.android.deskclock'
NATIVE='local.pocket4.actions.v2'
PULSE_CONFIG=Path('/home/alex/work/pocket4-android-final/qualification/app-runtime-dependencies-20261108-8b88-r2/runtime-inputs/pocket4-clock-delivery-contract-20261105-r12-03/pulse-client.conf')
PULSE_BYTES=b'autospawn = no\ndefault-server = unix:/run/user/1000/pulse/native\n'


class Evidence:
    def __init__(self,session):
        self.s=session;self.ALEX_PREFIX=list(session.c.NATIVE_PREFIX);self.RUNUSER='/usr/sbin/runuser'
        self.MAIN_HOST=session.baseline.docs['final_baseline']['daemon_status']['host_pid']
    def write_new(self,path,value,**options):
        s=self.s;path=Path(path)
        s.c.need(not set(options)-{'alex_readable'} and (not options or type(options['alex_readable']) is bool)
            and path.is_absolute() and path.is_relative_to(s.root) and path.parent.resolve()==path.parent,
            'ONLY_THIS_NEW_CLOCK_CASE_EVIDENCE')
        raw=value if type(value) is bytes else s.c.canonical(value)
        s.c.need(len(raw)<=(33554432 if path.suffix=='.png' else 16777216),'ORIGINAL_CLOCK_EVIDENCE_BOUND')
        ref=s.c.write_new(path,raw)
        if type(value) is dict:s.note_original_record(ref,value)
        return ref
    def read_regular(self,path,expected,maximum=16777216):
        s=self.s;s.original_caller(('clock_audio_observe.py',),{'sample'});s.guard()
        s.c.need(Path(path)==PULSE_CONFIG and expected==hashlib.sha256(PULSE_BYTES).hexdigest()
            and maximum==16777216,'ONLY_ORIGINAL_NO_AUTOSPAWN_PULSE_CONFIG')
        raw,ref=s.c.regular(path,4096)
        s.c.need(raw==PULSE_BYTES and ref['sha256']==expected,'ORIGINAL_NO_AUTOSPAWN_CONFIG_CHANGED')
        s.guard();return raw


class TargetReads:
    def __init__(self,session):self.s=session
    def read_file(self,path,maximum,**options):
        s=self.s;s.guard();p=s.components['clock_preservation.py']
        caller=s.original_caller(('clock_protection.py','clock_alarm_reader.py','clock_case.py'),
            skip=('read_file','resource_contract'))
        wanted=[(pkg,value) for pkg,value in s.apk_paths.items() if value==path]
        expected=metadata=None
        if wanted:
            s.c.need(len(wanted)==1 and not options,'ONE_ORIGINAL_CLOCK_OR_NATIVE_APK')
            pkg=wanted[0][0]
            s.c.need((pkg==PACKAGE and maximum==16777216) or (pkg==NATIVE and maximum==131072),
                'ORIGINAL_CLOCK_APK_READ_BOUND')
            artifact=s.identities[pkg]['artifacts'][0];expected=artifact['sha256'];metadata=artifact['held_file']
        else:
            s.c.need(path==p.PREFS and maximum in (1048576,2097152) and not options
                and caller['source'] in ('clock_protection.py','clock_alarm_reader.py'),
                'ONLY_ORIGINAL_CLOCK_PRIVATE_PREFERENCES_READ')
        raw,actual=s.view.target.read_file(path,maximum,single_link=True)
        s.c.need(expected is None or s.c.sha(raw)==expected,'ACTUAL_ORIGINAL_CLOCK_APK_CHANGED')
        s.c.need(metadata is None or actual==metadata,'CLOCK_APK_RECEIPT_BACKING_CHANGED')
        s.guard();return raw,actual
    def open_root(self,path,flags):
        s=self.s;s.guard();p=s.components['clock_preservation.py']
        caller=s.original_caller(('clock_protection.py','clock_alarm_reader.py'),skip=('open_root',))
        if path==p.DB:
            s.c.need(s.kind=='alarm04' and caller=={'source':'clock_alarm_reader.py','function':'data_identity'}
                and flags==os.O_RDONLY|os.O_NOFOLLOW,'ONLY_ORIGINAL_READONLY_ALARM_DATABASE_FD')
        else:
            s.c.need(path in ('/data/user/0/'+PACKAGE,'/data/user_de/0/'+PACKAGE)
                and flags==os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW
                and caller=={'source':'clock_protection.py','function':'snapshot'},
                'ONLY_ORIGINAL_CLOCK_CE_DE_IDENTITY_FD')
        return s.view.target.open_root(path,flags|os.O_CLOEXEC)
    @property
    def namespaces(self):
        self.s.original_caller(('clock_audio_observe.py',),{'sample'})
        return self.s.view.target.namespaces


def make_session_class(base):
    class Session(base.ClockTransportBase):
        def __init__(self,c,request,root,components,action_lock,source_guard,started,identities):
            self.c=self.common=c;self.request=request;self.root=Path(root);self.components=components
            self.kind=request['kind'];self.limits=copy.deepcopy(components['clock_profiles.py'].LIMITS[self.kind])
            self.identities={value['metadata']['package']:value for value in identities}
            c.need(set(self.identities)=={PACKAGE,NATIVE},'EXACT_CLOCK_AND_NATIVE_IDENTITIES')
            self.action_lock=action_lock;self.source_guard=source_guard;self.started=started
            self.business_deadline=started+self.limits['business_seconds']
            self.lease_deadline=self.deadline=started+self.limits['lease_seconds'];self.phase='business'
            self.closed=False;self.view=self.peer=self.helper=self.held_artifacts=None
            self.trial=self.flow=self.protection=self.alarm_reader=self.delivery=None
            self.command_index=self.api_sequence=self.native_launches=self.adopt_sequence=0
            self.records=[];self.intents=[];self.used_intents=set();self.claimed_tasks={};self.launch_receipts={}
            self.last_focus=self.last_stacks=self.task_baseline=self.task_baseline_roots=None
            self.last_alarm_activities=self.last_alarm_summary=None
            self.active_api=self.ui_owner=self.native_observer=None
            self.host_cancelled=self.host_retirement_unknown=self.possible_effect=False
            self.allowed_ui_packages={PACKAGE};self.source_paths={k:v.__file__ for k,v in components.items()}
            self.apk_paths={pkg:value['artifacts'][0]['guest_path'] for pkg,value in self.identities.items()}
            self.journal=c.private_dir(self.root/'commands',create=True);self.api_root=c.private_dir(self.root/'api',create=True)
            self.phase_ref=c.write_new(self.root/'phase-business.json',{'schema':'pocket4-clock-current-phase-v1',
                'phase':'business','baseline':request['baseline'],'qualification':request['qualification'],
                'kind':self.kind,'owner_pid':os.getpid(),'started_monotonic':started,
                'business_deadline_monotonic':self.business_deadline,'deadline_monotonic':self.deadline,
                'limits':self.limits,'automatic_retry':False})
            try:
                def no_view_dispatch(*unused):raise RuntimeError('CLOCK_COMMAND_REQUIRES_FINITE_CURRENT_TRANSPORT')
                self.view=c.MainView(request['baseline'],request['qualification'],self.journal,no_view_dispatch,
                    support_ref=request['support_manifest'])
                self.baseline=self.view.baseline;self.environment=self.view.environment;self.scope_module=self.view.scope
                self.commands=components['app_runtime.py'].PhaseCommands(self.view.commands,self)
                data=self.baseline.data
                ref=c.regular(data.EPOCH_PATH,contents=False)
                c.need(ref['sha256']==data.EPOCH_SHA,'EXACT_BASELINE_PROCESS_IDENTITY_IMPLEMENTATION')
                self.epoch_ref=ref;self.epoch=c.module(ref,'clock_current_epoch_observer_only')
                self.held_artifacts=c.HeldArtifacts(self.view.target,list(self.identities.values()))
                self.target=TargetReads(self);self.tx=Evidence(self)
                self.policy=components['clock_policy.py'].Policy(self)
                self.guard();self.helper=components['clock_api.py'].OriginalAPIs(self)
            except BaseException:
                self.close();raise

        def guard(self,*,action_attempted=False):
            value=super().guard(action_attempted=action_attempted)
            if self.held_artifacts is not None:self.held_artifacts.verify()
            if hasattr(self,'epoch_ref'):self.c.read_ref(self.epoch_ref)
            self.c.need(time.monotonic()<self.deadline,'CLOCK_COMPLETE_GUARD_EXHAUSTED_PHASE')
            return value

        def begin_cleanup(self,trigger):
            self.c.need(self.phase=='business' and self.active_api is None,'ONCE_ORIGINAL_CLOCK_CLEANUP')
            seconds=self.limits['cleanup_seconds'];self.phase='final_cleanup'
            self.deadline=min(time.monotonic()+seconds,self.lease_deadline+seconds)
            self.c.need(time.monotonic()<self.deadline,'NO_CLOCK_CLEANUP_AFTER_ORIGINAL_ABSOLUTE_BOUND')
            self.phase_ref=self.c.write_new(self.root/'phase-final-cleanup.json',{'schema':'pocket4-clock-current-phase-v1',
                'phase':self.phase,'trigger':trigger,'owner_pid':os.getpid(),'kind':self.kind,
                'lease_deadline_monotonic':self.lease_deadline,'deadline_monotonic':self.deadline,
                'cleanup_seconds':seconds,'automatic_retry':False})

        def pending_input(self):
            if self.flow is None:return None
            return self.flow.pending if self.kind=='alarm04' else self.flow.c.pending

        def note_original_record(self,ref,value):
            caller=self.original_caller(('clock_delivery_trial.py','clock_continuation.py','clock_timer_core.py',
                'clock_expiry_flow.py','clock_alarm_flow.py','clock_audio_observe.py','clock_delivery.py'),
                skip=('record','write_new'))
            if caller=={'source':'clock_delivery_trial.py','function':'focus'}:
                self.last_focus=copy.deepcopy(value)
            actual=value.get('argv',value.get('command',value.get('native_request',value.get('request'))))
            if type(actual) in (list,dict) and (value.get('automatic_retry') is False
                    or caller=={'source':'clock_expiry_flow.py','function':'stop'}):
                self.intents.append({'ref':ref,'value':copy.deepcopy(value),'actual':copy.deepcopy(actual),
                    'caller':caller,'phase':self.phase_ref})
            if caller=={'source':'clock_expiry_flow.py','function':'claim_alert'} and 'sole_timer_id' in value:
                self.admit_alert(ref,value)

        def consume_intent(self,kind,requested):
            matches=[item for item in self.intents if item['ref']['path'] not in self.used_intents
                and item['phase']==self.phase_ref and item['actual']==requested]
            self.c.need(len(matches)==1,'ONE_CURRENT_ORIGINAL_CLOCK_INTENT:'+kind)
            item=matches[0];self.c.read_ref(item['ref']);self.used_intents.add(item['ref']['path'])
            self.c.write_new(self.journal/('once-%04d.json'%len(self.used_intents)),{'kind':kind,'intent':item['ref'],
                'caller':item['caller'],'phase':self.phase_ref,'automatic_retry':False})
            return item

        def android(self,argv,timeout=20):
            self.guard();argv=list(argv);mutation=self.policy.command(argv,timeout)
            value=self._transport('original-clock',argv,timeout,mutation=mutation)
            self.policy.observe(argv,value['stdout']);return value['stdout']

        def sql(self,label,sql):
            self.guard();self.policy.sql(label,sql);p=self.components['clock_preservation.py']
            argv=['/system/bin/sqlite3','-readonly','-json',p.DB,'PRAGMA query_only=ON;BEGIN;'+sql+'ROLLBACK;']
            result=self._transport(label,argv,16,root=True)
            self.policy.observe_sql(label,result['stdout']);return result['stdout']

        def root_query(self,label,argv):
            self.original_caller(('clock_alarm_reader.py',),{'fingerprint'});self.guard()
            p=self.components['clock_preservation.py']
            script=('set -o pipefail; /system/bin/sqlite3 -readonly -json '+p.DB+
                " 'PRAGMA query_only=ON;BEGIN;SELECT * FROM alarm_templates WHERE _id IN (1,2) ORDER BY _id;ROLLBACK;'"
                +' | /system/bin/sha256sum')
            self.c.need(self.kind=='alarm04' and label=='alarm-original-digest'
                and argv==['/system/bin/sh','-c',script],'ONLY_ORIGINAL_TEMPLATE_DIGEST_PIPELINE')
            return self._transport(label,argv,16,root=True)

        def run_host(self,label,argv,timeout=20,pass_fds=()):
            c=self.c;c.need(not pass_fds,'NO_EXTRA_CLOCK_HOST_AUTHORITY_FDS')
            if label.startswith('clock-notify-'):
                c.need(self.delivery is not None,'ACTUAL_CLOCK_DELIVERY_BINDING_REQUIRED')
                return self.delivery.binding.run_host(label,argv,timeout)
            if label.startswith('clock-audio-stream-'):
                self.original_caller(('clock_audio_observe.py',),{'sample'})
                wanted=[self.tx.RUNUSER,'-u','alex','--','/usr/bin/env','PULSE_CLIENTCONFIG='+str(PULSE_CONFIG),
                    'PULSE_SERVER=unix:/run/user/1000/pulse/native','XDG_RUNTIME_DIR=/run/user/1000',
                    str(Path('/usr/bin/pactl').resolve(strict=True)),'--format=json','list','sink-inputs']
                c.need(self.kind=='expiry06' and timeout==10 and argv==wanted
                    and re.fullmatch(r'clock-audio-stream-[1-9][0-9]*',label),'ORIGINAL_READONLY_PULSE_QUERY')
                return self._host(label,argv,timeout)
            self.original_caller(('clock_delivery_trial.py',),{'launch'})
            expected=list(c.NATIVE_PREFIX)+['launch',PACKAGE,'--component',PACKAGE+'/.DeskClock','--json']
            c.need(label=='contacts-launch' and timeout==45 and argv==expected and self.active_api is None
                and self.trial is not None and self.flow is not None and self.trial.owned is None
                and self.native_launches<2 and self.trial.launches==self.native_launches+1
                and type(self.pending_input()) is str and self.pending_input().startswith('launch-')
                and self.flow.effect_pending is None and self.flow.close_pending is None and self.last_stacks is not None,
                'ONE_ORIGINAL_CLOCK_NATIVE_LAUNCH')
            roots,tasks=copy.deepcopy(self.last_stacks)
            c.need(not any(row['component'].split('/')[0]==PACKAGE for root in roots.values() for row in root['children']),
                'PREEXISTING_CLOCK_TASK_CANNOT_BE_ADOPTED')
            if self.task_baseline is None:
                self.task_baseline=set(tasks);self.task_baseline_roots=copy.deepcopy(roots)
            else:
                c.need(tasks==self.task_baseline and roots==self.task_baseline_roots,
                    'SECOND_CLOCK_LAUNCH_REQUIRES_EXACT_ORIGINAL_TASK_SET')
                c.need(all(task not in roots and task not in tasks for task in self.claimed_tasks),
                    'PRIOR_CLOCK_TASK_MUST_ACTUALLY_BE_ABSENT')
            item=self.consume_intent('launch',argv);self.native_launches+=1
            result=self._host('clock-launch-'+str(self.native_launches),argv,timeout,True);value=c.parse(result['stdout'])
            match=re.fullmatch(r'object=(\d+) composer_display=(\d+) android_display=(\d+) task=(\d+)',value.get('launch',''))
            c.need(value.get('ok') is True and value.get('state')=='running' and value.get('host_pid')==self.tx.MAIN_HOST
                and value.get('outcome_unknown') is not True and match and match[3]=='0'
                and int(match[4]) not in roots and int(match[4]) not in tasks,'ACTUAL_NEW_MAIN_CLOCK_TASK')
            task=int(match[4]);claim={'schema':'pocket4-clock-current-owned-task-v1','source':'native-launch',
                'baseline':self.request['baseline'],'qualification':self.request['qualification'],'phase':self.phase_ref,
                'intent':item['ref'],'actual_host_result':self.records[-1],'native':value,'task':task,
                'prelaunch_tasks':sorted(tasks),'component':PACKAGE+'/.DeskClock','automatic_retry':False}
            ref=c.write_new(self.root/('launch-%02d-scope.json'%self.native_launches),claim)
            self.claimed_tasks[task]={**claim,'source_ref':ref};self.launch_receipts[str(self.native_launches)]=ref
            return result

        def admit_alert(self,original_ref=None,original_value=None):
            c=self.c;f=self.flow;t=self.trial
            c.need(f is not None and t is not None and t.owned is not None and self.last_stacks is not None,
                'ACTUAL_SOURCE_BOUND_ALERT_OWNERSHIP')
            task,preserved=t.owned
            if task in self.claimed_tasks:return
            roots,tasks=self.last_stacks
            c.need(self.task_baseline is not None and preserved==self.task_baseline
                and tasks==self.task_baseline|{task} and task not in self.task_baseline
                and all(roots.get(k)==v for k,v in self.task_baseline_roots.items()) and f.alert_task==task,
                'SOLE_NEW_ALERT_WITH_ALL_ORIGINAL_TASKS_PRESERVED')
            if self.kind=='expiry06':
                c.need(original_ref is not None and original_value=={'task':task,
                    'activity':self.components['clock_expiry_flow.py'].ALERT,'sole_timer_id':f.timer_id,
                    'cleanup_only':original_value.get('cleanup_only'),'full_screen_intent_has_no_timer_id':True,
                    'native_launch_performed':False} and type(original_value['cleanup_only']) is bool
                    and self.components['clock_expiry_flow.py'].exact_alert(roots,task)
                    and f.timer_id==f.r.get('owned_timer_id') and 'created-running' in f.r['phases']
                    and self.pending_input() is None and f.effect_pending is None and f.close_pending is None,
                    'EXPIRY_ALERT_REQUIRES_THIS_ACK_CREATED_SOLE_TIMER')
                component=next(row['component'] for root in roots.values() for row in root['children'] if row['id']==task)
                proof={'original_record':original_ref,'sole_timer_id':f.timer_id,'native_launch_performed':False}
            else:
                self.original_caller(('clock_alarm_flow.py',),{'claim_alert','observe'},skip=('admit_alert',))
                binding=f.alert_binding
                c.need(self.kind=='alarm04' and type(binding) is dict and f.reader.instance is not None
                    and f.r.get('actual_firing_verified') is True and f.r.get('actual_alarm_notification_posted') is True
                    and f.pending is None and f.effect_pending is None and f.close_pending is None
                    and self.last_alarm_activities is not None and binding['task']==task
                    and binding['activity_dump_sha256']==c.sha(self.last_alarm_activities)
                    and binding['uri']=='content://com.android.deskclock/instances/'+str(f.reader.instance['_id'])
                    and f.r['phases']['fired']['instances'][0]['_id']==f.reader.instance['_id']
                    and f.r['phases']['fired']['instances'][0]['alarm_state']==5 and t.base.exact_leaf(roots,task),
                    'ALARM_ALERT_REQUIRES_THIS_FIRED_INSTANCE_INTENT')
                component=binding['component'];proof={'original_binding':copy.deepcopy(binding),
                    'activity_dump':c.write_new(self.root/'adopted-alarm-activity.txt',self.last_alarm_activities),
                    'original_reader_instance':copy.deepcopy(f.reader.instance),'native_launch_performed':False}
            self.adopt_sequence+=1
            claim={'schema':'pocket4-clock-current-owned-task-v1','source':'source-bound-alert','task':task,
                'component':component,'prelaunch_tasks':sorted(self.task_baseline),'proof':proof,
                'baseline':self.request['baseline'],'qualification':self.request['qualification'],
                'phase':self.phase_ref,'automatic_retry':False}
            ref=c.write_new(self.root/('alert-%02d-scope.json'%self.adopt_sequence),claim)
            self.claimed_tasks[task]={**claim,'source_ref':ref}

        def verify_original_callback(self,kind,callback,previous):
            fn=getattr(callback,'__func__',None);owner=getattr(callback,'__self__',None)
            self.c.need(kind=='foreground' and fn is not None and owner is self.trial and previous is None
                and self.ui_owner is None and fn.__code__.co_filename==self.source_paths['clock_delivery_trial.py']
                and fn.__code__.co_name=='helper_foreground','ONE_CURRENT_CLOCK_FOREGROUND_CALLBACK')
            self.ui_owner=owner

        def begin_ui_api(self,api,request):
            c=self.c;f=self.flow;t=self.trial
            c.need(api in ('dispatch','ui') and f is not None and t is not None and self.ui_owner is t
                and self.active_api is None and t.owned is not None,'CURRENT_CLOCK_API_AND_OWNED_TASK_ONLY')
            caller=self.original_caller(('clock_delivery_trial.py','clock_continuation.py','clock_alarm_flow.py','clock_expiry_flow.py'),
                skip=('dispatch',))
            c.need(request.get('package',request.get('expected_package'))==PACKAGE
                and request.get('display')==0 and request.get('accessibility_mode')=='none','EXACT_CLOCK_DISPLAY_PACKAGE_POLICY')
            mutation=request.get('op') in ('click','set-text')
            if not mutation:
                c.need(api=='dispatch' and caller=={'source':'clock_delivery_trial.py','function':'observe'}
                    and request=={'op':'observe','package':PACKAGE,'window_token':request.get('window_token'),
                        'display':0,'accessibility_mode':'none','with_png':True},'ONLY_ORIGINAL_CLOCK_FULL_OBSERVATION')
            elif api=='dispatch':
                c.need(self.kind in ('timer15','expiry06') and caller=={'source':'clock_continuation.py','function':'step'}
                    and self.native_observer is not None and request['op']=='click'
                    and set(request)=={'op','package','window_token','display','accessibility_mode','selector','method'}
                    and request['method']=='accessibility','ONLY_ORIGINAL_TIMER_CONTINUATION_CLICK')
            else:
                c.need((self.kind=='alarm04' and caller=={'source':'clock_alarm_flow.py','function':'native'})
                    or (self.kind=='expiry06' and caller=={'source':'clock_expiry_flow.py','function':'stop'}),
                    'ONLY_ORIGINAL_DIRECT_CLOCK_NATIVE_INPUT')
                fields={'op','expected_package','display','accessibility_mode','selector'}
                fields|={'method'} if request['op']=='click' else {'value'}
                c.need(set(request)==fields and (request.get('method') in ('accessibility','mouse') if request['op']=='click'
                    else self.kind=='alarm04' and type(request['value']) is str and 0<len(request['value'])<=64),
                    'EXACT_ORIGINAL_CLOCK_DIRECT_INPUT_FIELDS')
            self.guard();roots,tasks=t.stacks('api-current-clock-tasks');self.admit_alert() if t.owned[0] not in self.claimed_tasks else None
            task,preserved=t.owned;claim=self.claimed_tasks[task];c.read_ref(claim['source_ref'])
            c.need(t.base.exact_leaf(roots,task) and tasks==preserved|{task}
                and preserved==set(claim['prelaunch_tasks']),'ACTUAL_CURRENT_CLOCK_TASK_CLAIM')
            actual=self.helper.foreground_callback();focus=copy.deepcopy(self.last_focus)
            c.need(focus is not None and t.focus_allowed(focus,False),'ACTUAL_ORIGINAL_CLOCK_FOCUS')
            self.api_sequence+=1
            context={'schema':'pocket4-clock-current-api-context-v1','api':api,'request':copy.deepcopy(request),
                'caller':caller,'phase':self.phase_ref,'owned_task':task,'claim':claim['source_ref'],
                'observed_focus':focus,'api_sequence':self.api_sequence,'mutation_sent':False,'native_returns':0,
                'automatic_retry':False}
            self.validate_ui_foreground(actual,context)
            if mutation:
                actions=f.actions if self.kind=='alarm04' else f.c.actions
                c.need(1<=actions<=self.limits['maximum_UI_actions'] and self.pending_input() is not None
                    and f.close_pending is None,'ORIGINAL_CLOCK_INPUT_BUDGET_AND_PENDING_REQUEST')
                item=self.consume_intent('ui',request);context['original_intent']=item['ref']
                observed=item['value'].get('wm_focus',item['value'].get('focus'))
                if observed is not None:c.need(observed==focus,'ORIGINAL_OBSERVED_CLOCK_WINDOW_CHANGED')
                elif 'window_token' in request:
                    c.need(request['window_token']==focus['window_token'],'CONTINUATION_WINDOW_CHANGED')
                else:raise RuntimeError('DIRECT_CLOCK_INPUT_HAS_NO_OBSERVED_FOCUS')
                if request.get('method')=='mouse':
                    c.need(self.kind=='alarm04' and self.pending_input().endswith('-expand-owned')
                        and request['selector'].get('text')==self.alarm_reader.MARKER,
                        'MOUSE_ONLY_FOR_THIS_OWNED_COLLAPSED_ALARM_LABEL')
            context['output']=str(c.private_dir(self.api_root/('api-%04d'%self.api_sequence),create=True))
            c.write_new(Path(context['output'])/'context.json',context);self.active_api=context;return context

        def validate_ui_foreground(self,value,context):
            focus=self.last_focus;t=self.trial
            self.c.need(type(value) is dict and set(value)=={'package','activity','window_token'}
                and focus is not None and t is not None and t.owned is not None
                and focus['task']==context['owned_task']==t.owned[0] and t.focus_allowed(focus,False)
                and value=={k:focus[k] for k in ('package','activity','window_token')}
                and value['package']==PACKAGE,'ACTUAL_CURRENT_CLOCK_FOREGROUND_REQUIRED')
            if not context['mutation_sent']:
                self.c.need(focus==context['observed_focus'],'CLOCK_OBSERVED_WINDOW_DRIFT_BEFORE_INPUT')
                if 'window_token' in context['request']:
                    self.c.need(value['window_token']==context['request']['window_token'],'CLOCK_TOKEN_CHANGED_BEFORE_INPUT')

        def validate_native_request(self,request,context,action_used):
            self.c.need(context is self.active_api,'CURRENT_CLOCK_NATIVE_CONTEXT')
            return self.components['clock_policy.py'].native_request(self.c,context['request'],request,action_used)

        def admit_ui_android(self,argv,timeout,context,action_used):
            self.c.need(context is self.active_api,'CURRENT_CLOCK_BACKEND_CONTEXT')
            return self.components['clock_policy.py'].backend_android(self.c,context['request'],argv,timeout,action_used)

        def record_native_return(self,request,value,context):
            # The final consumer mutates the returned dict when attaching
            # post-capture fields. Seal the actual native boundary first.
            super().record_native_return(copy.deepcopy(request),copy.deepcopy(value),context)
            if self.native_observer is not None:
                self.c.need(context['api']=='dispatch' and self.kind in ('timer15','expiry06'),
                    'ONLY_REAL_TIMER_CONTINUATION_ACK_OBSERVER')
                self.native_observer(copy.deepcopy(request),copy.deepcopy(value))

        def timer_read(self):return self.protection.timer_read()
        def caller_status(self,label):
            self.c.need(label in ('clock-timer-final-caller','clock-expiry-final-caller','alarm-final-caller'),
                'ONLY_CURRENT_CLOCK_FINAL_STATUS')
            value=self.guard();self.c.write_new(self.root/(label+'.json'),value);return value

        def close(self):
            first=None
            if self.held_artifacts is not None:
                try:self.held_artifacts.close()
                except BaseException as error:first=error
                self.held_artifacts=None
            try:super().close()
            except BaseException as error:
                if first is None:first=error
                else:first.add_note('CLOCK_OTHER_CONTEXT_CLOSE:'+type(error).__name__)
            if first is not None:raise first
    return Session
