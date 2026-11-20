"""New Documents multi-task session on the actual qualified final Main.

The original Features10 state machines own business decisions. This layer
binds their exact operations to fresh source/phase/launch/ACK evidence, one
held Main and one action-lock OFD. No old activation or nonce is authority.
"""
import copy
from contextlib import contextmanager
import os
from pathlib import Path
import re
import time
import types

DOCS='com.android.documentsui'
PROVIDER='com.android.externalstorage'
NATIVE='local.pocket4.actions.v2'


class Evidence:
    def __init__(self,session):
        self.s=session;self.ALEX_PREFIX=list(session.c.NATIVE_PREFIX)
        self.MAIN_HOST=session.baseline.docs['final_baseline']['daemon_status']['host_pid']
    def write_new(self,path,value,**options):
        s=self.s;path=Path(path)
        s.c.need(not set(options)-{'alex_readable'} and (not options or type(options['alex_readable']) is bool)
            and path.is_relative_to(s.root) and path.parent.resolve()==path.parent,'ONLY_THIS_NEW_DOCUMENTS_CASE_EVIDENCE')
        raw=value if type(value) is bytes else s.c.canonical(value)
        s.c.need(len(raw)<=(33554432 if path.suffix=='.png' else 16777216),'ORIGINAL_EVIDENCE_BYTE_BOUND')
        ref=s.c.write_new(path,raw)
        if type(value) is dict:s.note_original_record(ref,value)
        return ref
    def read_regular(self,path,expected,maximum):
        s=self.s;s.guard();a=s.artifacts
        allowed={(a.APK,a.APK_SHA,1048576),(a.BUILD,a.BUILD_SHA,1048576),(a.PM_HELP,a.PM_HELP_SHA,16384)}
        s.c.need((Path(path),expected,maximum) in allowed,'ONLY_EXPLICIT_NEW_HELPER_ARTIFACT_INPUT')
        raw,ref=s.c.regular(path,maximum)
        s.c.need(ref['sha256']==expected and (Path(path)!=a.APK or len(raw)==a.APK_BYTES),'HELPER_INPUT_BYTES_CHANGED')
        s.guard();return raw


class TargetReads:
    def __init__(self,session):self.s=session
    def read_file(self,path,maximum,**options):
        s=self.s;s.guard();wanted=[(pkg,value) for pkg,value in s.apk_paths.items() if value==path]
        expected=metadata=None
        if wanted:
            s.c.need(len(wanted)==1 and maximum==16777216,'ONE_ORIGINAL_CURRENT_PACKAGE_APK')
            package=wanted[0][0]
            if package==s.names.PACKAGE:expected=s.artifacts.APK_SHA
            else:
                identity=s.identities[package];art=[a for a in identity['artifacts'] if a['guest_path']==path]
                s.c.need(len(art)==1,'ACTUAL_PREOBSERVED_PACKAGE_ARTIFACT');expected=art[0]['sha256'];metadata=art[0]['held_file']
        elif path=='/data/local/tmp/pocket4-owned-docfeatures-'+s.names.RUN+'/owned-features.apk':
            s.c.need(maximum==1048576 and s.case is not None and s.case.pkg.staged is not None,
                'ONLY_EXACT_NEW_STAGED_HELPER_APK');expected=s.artifacts.APK_SHA
        else:
            s.c.need(path=='/data/user/0/'+s.names.PACKAGE+'/shared_prefs/owned-features-'+s.names.RUN+'.xml'
                and maximum==16384 and s.case is not None and s.case.pkg.installed is not None,
                'ONLY_ORIGINAL_NEW_HELPER_PRIVATE_PROTOCOL')
        s.c.need(options=={'single_link':True},'ORIGINAL_SINGLE_LINK_READ_REQUIRED')
        raw,actual=s.view.target.read_file(path,maximum,**options)
        s.c.need(expected is None or s.c.sha(raw)==expected,'EXACT_ORIGINAL_OR_NEW_HELPER_BYTES')
        s.c.need(metadata is None or actual==metadata,'ORIGINAL_APPROVED_APK_HELD_IDENTITY_CHANGED')
        s.guard();return raw,actual
    def open_root(self,path,flags):
        s=self.s;s.guard()
        paths={'/storage/emulated/0','/data/local/tmp'}
        paths|={'/data/'+prefix+'/0/'+pkg for prefix in ('user','user_de') for pkg in (DOCS,PROVIDER,s.names.PACKAGE)}
        s.c.need(path in paths and flags==os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,
            'ONLY_ORIGINAL_DOCUMENTS_EXACT_DIRECTORY_SCOPE')
        return s.view.target.open_root(path,flags|os.O_CLOEXEC)
    @property
    def namespaces(self):
        self.s.original_caller(['documents_runtime_evidence.py'],{'__init__'})
        return self.s.view.target.namespaces
    @property
    def proc_fd(self):
        self.s.original_caller(['documents_runtime_evidence.py'],{'__init__'})
        return self.s.view.target.proc_fd
    @contextmanager
    def lease(self):
        s=self.s;s.original_caller(['documents_runtime_evidence.py'],{'observe_boundary'});s.guard()
        with s.view.target.lease():yield
        s.guard()


def make_session_class(base):
    class Session(base.DocumentsTransportBase):
        def __init__(self,c,request,root,components,action_lock,source_guard,business_deadline,names,artifacts,identities):
            self.c=self.common=c;self.request=request;self.root=Path(root);self.components=components
            self.names=names;self.artifacts=artifacts;self.identities={v['metadata']['package']:v for v in identities}
            self.action_lock=action_lock;self.source_guard=source_guard
            self.business_deadline=self.deadline=business_deadline;self.phase='business'
            self.closed=False;self.view=self.peer=self.helper=self.case=self.held_artifacts=None
            self.command_index=self.api_sequence=self.native_launches=self.adopt_sequence=0
            self.records=[];self.intents=[];self.used_intents=set();self.claimed_tasks={};self.launch_receipts={}
            self.completed_inputs={};self.last_focus=self.last_stacks=None;self.active_api=self.ui_owner=None
            self.host_cancelled=self.host_retirement_unknown=self.possible_effect=False
            self.allowed_ui_packages={DOCS,names.PACKAGE}
            self.apk_paths={pkg:v['artifacts'][0]['guest_path'] for pkg,v in self.identities.items()}
            self.source_paths={k:v.__file__ for k,v in components.items()}
            self.journal=c.private_dir(self.root/'commands',create=True);self.api_root=c.private_dir(self.root/'api',create=True)
            self.phase_ref=c.write_new(self.root/'phase-business.json',{'schema':'pocket4-documents-case-phase-v1',
                'phase':'business','baseline':request['baseline'],'qualification':request['qualification'],
                'owner_pid':os.getpid(),'deadline_monotonic':self.deadline,'business_seconds':750,'cleanup_seconds':150,
                'automatic_retry':False})
            try:
                def no_view_dispatch(*unused):raise RuntimeError('ALL_DOCUMENTS_COMMANDS_REQUIRE_TYPED_TRANSPORT')
                self.view=c.MainView(request['baseline'],request['qualification'],self.journal,no_view_dispatch,support_ref=c.SUPPORT_REF)
                self.baseline=self.view.baseline;self.environment=self.view.environment;self.scope_module=self.view.scope
                self.commands=components['app_runtime.py'].PhaseCommands(self.view.commands,self)
                reader=self.baseline.data
                self.held=c.module({'path':str(reader.READER_PATH),'bytes':reader.READER_BYTES,'sha256':reader.READER_SHA},'documents_actual_held_reader')
                self.held_artifacts=c.HeldArtifacts(self.view.target,list(self.identities.values()))
                self.target=TargetReads(self);self.tx=Evidence(self)
                self.policy=components['documents_policy.py'].Policy(self)
                self.guard();self.helper=components['documents_api.py'].OriginalAPIs(self)
            except BaseException:
                self.close();raise

        def guard(self,*,action_attempted=False):
            value=super().guard(action_attempted=action_attempted)
            if self.held_artifacts is not None:self.held_artifacts.verify()
            self.c.need(time.monotonic()<self.deadline,'DOCUMENTS_FULL_GUARD_EXHAUSTED_PHASE')
            return value

        def begin_cleanup(self,trigger):
            self.c.need(self.phase=='business' and self.active_api is None,'ONCE_DOCUMENTS_FINAL_PHASE')
            self.phase='final_cleanup';self.deadline=min(time.monotonic()+150,self.business_deadline+150)
            self.c.need(time.monotonic()<self.deadline,'NO_DOCUMENTS_CLEANUP_AFTER_ORIGINAL_900_SECONDS')
            self.phase_ref=self.c.write_new(self.root/'phase-final-cleanup.json',{'schema':'pocket4-documents-case-phase-v1',
                'phase':self.phase,'trigger':trigger,'owner_pid':os.getpid(),'business_deadline_monotonic':self.business_deadline,
                'deadline_monotonic':self.deadline,'cleanup_seconds':150,'automatic_retry':False})

        def note_original_record(self,ref,value):
            caller=self.original_caller(['documents_features_core.py','documents_features_ui.py',
                'documents_package_fixture.py','documents_owned_tree.py','documents_runtime_evidence.py','documents_diagnostics.py',
                'documents_search_sort.py'],skip=('record',))
            if caller=={'source':'documents_features_ui.py','function':'focus'} and set(value)=={'focus','raw'}:
                self.last_focus=copy.deepcopy(value['focus'])
            if caller=={'source':'documents_features_ui.py','function':'check_tasks'} and set(value)=={'task','grant','prelaunch_absent'}:
                self.record_adopted_task(ref,value)
            if value.get('automatic_retry') is False and (type(value.get('argv')) is list or type(value.get('request')) is dict
                    or value.get('method')=='normal exact owned leaf remove'
                    or value.get('package')==self.names.PACKAGE and 'identity' in value
                    or value.get('key')=='KEYCODE_BACK'):
                self.intents.append({'ref':ref,'value':copy.deepcopy(value),'caller':caller,'phase':self.phase_ref})

        def consume_intent(self,kind,requested):
            matches=[]
            for item in self.intents:
                if item['ref']['path'] in self.used_intents or item['phase']!=self.phase_ref:continue
                v=item['value'];actual=v.get('argv',v.get('request'))
                if kind=='task-remove' and v.get('method')=='normal exact owned leaf remove':
                    actual=['/system/bin/cmd','activity','stack','remove',str(v['task'])]
                if kind=='helper-uninstall' and v.get('package')==self.names.PACKAGE and 'identity' in v:
                    actual=['/system/bin/pm','uninstall',self.names.PACKAGE]
                if kind=='back' and v.get('key')=='KEYCODE_BACK':
                    actual=['/system/bin/input','keyboard','-d','0','keyevent','KEYCODE_BACK']
                if kind=='long-press' and v.get('kind')=='long-press':
                    point=v['request'].get('coords',[])
                    if len(point)==2:actual=['/system/bin/input','-d','0','swipe',str(point[0]),str(point[1]),str(point[0]),str(point[1]),'650']
                if actual==requested:matches.append(item)
            self.c.need(len(matches)==1,'ONE_CURRENT_DOCUMENTS_INTENT:'+kind)
            item=matches[0];self.c.read_ref(item['ref']);self.used_intents.add(item['ref']['path'])
            self.c.write_new(self.journal/('once-%04d.json'%len(self.used_intents)),{'kind':kind,'intent':item['ref'],
                'original_caller':item['caller'],'phase':self.phase_ref,'automatic_retry':False})
            return item

        def android(self,argv,timeout=20):
            self.guard();argv=list(argv);mutation=self.policy.command(argv,timeout)
            result=self._transport('original-documents',argv,timeout,mutation=mutation)
            self.policy.observe(argv,result['stdout']);return result['stdout']

        def run_host(self,label,argv,timeout=20,pass_fds=()):
            self.original_caller(['documents_features_ui.py'],{'launch'});f=self.case;c=self.c
            expected=list(c.NATIVE_PREFIX)+['launch',self.names.PACKAGE,'--component',self.names.PACKAGE+'/.FeaturesActivity','--json']
            c.need(not pass_fds and self.phase=='business' and self.active_api is None and timeout==45 and argv==expected
                and self.native_launches<3 and label=='launch-'+str(self.native_launches+1)
                and f.ui.launches==self.native_launches+1 and set(f.ui.pending)=={label}
                and not f.ui.owned and self.last_stacks is not None and self.last_stacks[1]==f.ui.baseline
                and f.pkg.installed is not None and not f.pkg.install_pending and not f.pkg.uninstall_pending,
                'ONCE_ORIGINAL_HELPER_LAUNCH_FROM_RESTORED_TASKS')
            self.consume_intent('launch',argv);self.native_launches+=1
            pre_roots,pre_tasks=copy.deepcopy(self.last_stacks)
            value=self._host(label,argv,timeout,True);decoded=c.parse(value['stdout'])
            match=re.fullmatch(r'object=(\d+) composer_display=(\d+) android_display=(\d+) task=(\d+)',decoded.get('launch',''))
            c.need(decoded.get('ok') is True and decoded.get('state')=='running' and decoded.get('host_pid')==self.tx.MAIN_HOST
                and decoded.get('outcome_unknown') is not True and match and match[3]=='0'
                and int(match[4]) not in pre_roots and int(match[4]) not in pre_tasks,'ACTUAL_NEW_DOCUMENTS_HELPER_TASK')
            task=int(match[4]);claim={'schema':'pocket4-documents-current-owned-launch-v1','baseline':self.request['baseline'],
                'qualification':self.request['qualification'],'source':label,'phase':self.phase_ref,'native':decoded,'task':task,
                'prelaunch_tasks':sorted(pre_tasks),'component':list(self.names.CLIENT),'automatic_retry':False}
            ref=c.write_new(self.root/(label+'-scope.json'),claim);self.launch_receipts[label]=ref
            self.claimed_tasks[task]={**claim,'source_ref':ref}
            return value

        def observe_owned_tasks(self):
            if self.case is None or self.last_stacks is None:return
            roots,tasks=self.last_stacks
            for task,owned in self.case.ui.owned.items():
                claim=self.claimed_tasks.get(task)
                # A new picker/files leaf is admitted by the preserved UI
                # check_tasks only after its real returned input ACK.
                if claim is None:continue
                self.c.read_ref(claim['source_ref'])
                self.c.need(tuple(owned['component'])==tuple(claim['component']) and owned['source']==claim['source']
                    and self.components['documents_features_ui.py'].leaf(roots,task,tuple(claim['component'])),
                    'CURRENT_DOCUMENTS_OWNED_TASK_CLAIM_CHANGED')

        def record_adopted_task(self,ref,value):
            f=self.case;c=self.c;task=value['task'];grant=value['grant'];token=grant['source']
            c.need(value['prelaunch_absent'] is True and task in f.ui.owned and f.ui.allow_new==grant
                and token in f.ui.pending and f.ui.pending[token]['input_acknowledged'] is True
                and token in self.completed_inputs and task not in f.ui.baseline and self.last_stacks is not None,
                'ONLY_REAL_ACK_SOURCE_BOUND_DOCUMENTS_TASK_ADOPTION')
            ack=self.completed_inputs[token];c.read_ref(ack['result'])
            c.need(ack['phase']==self.phase_ref and tuple(grant['component']) in ((DOCS,DOCS+'.files.FilesActivity'),(DOCS,DOCS+'.picker.PickActivity'))
                and self.components['documents_features_ui.py'].leaf(self.last_stacks[0],task,tuple(grant['component']))
                and task not in ack['pre_action_tasks'],'ADOPTED_LEAF_NOT_NEW_FROM_THIS_ACTUAL_INPUT')
            claim={**copy.deepcopy(value),'source':token,'component':list(grant['component']),
                'baseline':self.request['baseline'],'qualification':self.request['qualification'],
                'phase':self.phase_ref,'actual_input':ack['result'],'original_record':ref,'automatic_retry':False}
            self.adopt_sequence+=1
            source=self.c.write_new(self.root/('adopt-%04d.json'%self.adopt_sequence),claim)
            self.claimed_tasks[task]={**claim,'source_ref':source}

        def admit_direct_input(self,item,kind):
            f=self.case;c=self.c
            c.need(self.phase=='business' and len(f.ui.pending)==1 and 1<=f.ui.actions<=80,
                'ONE_ORIGINAL_PENDING_DIRECT_INPUT')
            token=next(iter(f.ui.pending));c.need(f.ui.pending[token].get('kind')==kind
                and not f.ui.pending[token]['input_acknowledged'],'NO_UNKNOWN_DIRECT_INPUT_REPLAY')
            v=item['value'];focus=v.get('focus',f.ui.last['focus']);snapshot=v.get('snapshot',v.get('request'))
            c.need(focus==self.last_focus and focus['task'] in f.ui.owned and focus['task'] in self.claimed_tasks
                and snapshot['window_token']==focus['window_token'],'EXACT_OBSERVED_OWNED_DIRECT_INPUT_WINDOW')
            if kind=='back':c.need((focus['package'],focus['activity'])==(DOCS,DOCS+'.picker.PickActivity') and not focus.get('popup'),
                'BACK_ONLY_FROM_THIS_OWNED_PICKER')
            else:self._validate_pointer_intent(snapshot,v)

        def caller_status(self,label):
            self.c.need(label=='documents-features-final-caller' and self.phase=='final_cleanup','ONLY_ORIGINAL_FINAL_CALLER_STATUS')
            value=self._host(label,list(self.c.NATIVE_PREFIX)+['status','--json'],10)
            status=self.c.parse(value['stdout'])
            self.c.need(status.get('ok') is True and status.get('state')=='running' and status.get('host_pid')==self.tx.MAIN_HOST
                and 'cell u1000 ' in status.get('message',''),'SAME_ACTUAL_FINAL_MAIN_AND_USER')
            return status

        def verify_original_callback(self,kind,callback,previous):
            fn=getattr(callback,'__func__',None);owner=getattr(callback,'__self__',None)
            self.c.need(kind=='foreground' and fn is not None and owner is not None and owner.s is self
                and fn.__code__.co_filename==self.source_paths['documents_features_ui.py']
                and fn.__code__.co_name=='helper_foreground' and self.ui_owner is None,
                'ONE_ORIGINAL_DOCUMENTS_OWNED_FOREGROUND_CALLBACK')
            self.ui_owner=owner

        def begin_ui_api(self,api,request):
            c=self.c;f=self.case
            c.need(api in ('capture','ui','dispatch','window_state') and f is not None and self.ui_owner is f.ui
                and self.active_api is None,'BOUND_ORIGINAL_DOCUMENTS_API_ONLY')
            caller=self.original_caller(['documents_features_ui.py'])
            package=request.get('package',request.get('expected_package'))
            c.need(package in self.allowed_ui_packages and request.get('display')==0 and request.get('accessibility_mode')=='none',
                'EXACT_DOCUMENTS_API_PACKAGE_DISPLAY_MODE')
            mutation=api=='dispatch' and request.get('op') in ('snapshot-tap','set-text')
            if api in ('capture','window_state'):
                c.need('op' not in request and set(request)<= {'package','display','accessibility_mode','window_token',
                    'frame_sha256','scope_sha256','context_token'} and 'window_token' in request,'ORIGINAL_WINDOW_BOUND_CAPTURE')
            elif api=='ui':
                c.need(request=={'op':'dump','expected_package':package,'display':0,'accessibility_mode':'none'},'ONLY_ORIGINAL_NATIVE_DUMP')
            elif not mutation:
                c.need(request=={'op':'observe','package':package,'display':0,'accessibility_mode':'none',
                    'window_token':request.get('window_token'),'with_png':True},'ONLY_ORIGINAL_FULL_OBSERVATION')
            else:
                c.need(self.phase=='business' and caller['function']=='input' and len(f.ui.pending)==1 and 1<=f.ui.actions<=80,
                    'ONE_ORIGINAL_FEATURES_INPUT_AND_BUDGET')
                fields={'op','package','display','accessibility_mode','window_token'}
                fields|={'selector','value'} if request['op']=='set-text' else {'frame_sha256','scope_sha256','context_token','coords','input_source'}
                c.need(set(request)==fields,'ONLY_ORIGINAL_FRAME_TOUCH_OR_EXACT_TEXT_FIELDS')
                if request['op']=='set-text' and request['value']!=self.names.COPIES:
                    f.search_sort.admit_query(request)
            self.guard();f.ui.check_tasks('api-current-owned-tasks')
            actual=self.helper.foreground_callback();focus=self.last_focus
            c.need(focus is not None and focus['task'] in f.ui.owned and focus['task'] in self.claimed_tasks,
                'ACTUAL_NEW_TASK_CLAIM_BEFORE_DOCUMENTS_API')
            self.api_sequence+=1
            context={'schema':'pocket4-documents-current-original-api-context-v1','api':api,'request':copy.deepcopy(request),
                'phase':self.phase_ref,'owned_task':focus['task'],'claim':self.claimed_tasks[focus['task']]['source_ref'],
                'caller':caller,'api_sequence':self.api_sequence,'mutation_sent':False,'native_returns':0,
                'pre_action_tasks':sorted(self.last_stacks[1]),'automatic_retry':False}
            self.validate_ui_foreground(actual,context)
            if mutation:
                token=next(iter(f.ui.pending));context['pending_token']=token
                c.need(f.ui.pending[token]['input_acknowledged'] is False,'PENDING_INPUT_ALREADY_ACKNOWLEDGED')
                item=self.consume_intent('ui',request);context['original_intent']=item['ref']
                self._validate_pointer_intent(request,item['value'])
            context['output']=str(c.private_dir(self.api_root/('api-%04d'%self.api_sequence),create=True))
            c.write_new(Path(context['output'])/'context.json',context);self.active_api=context;return context

        def _validate_pointer_intent(self,request,value):
            if request['op']!='snapshot-tap':return
            box=value['node'].get('bounds_array');shot=self.case.ui.last['screenshot']
            self.c.need(type(box) is list and len(box)==4 and all(type(x) is int for x in box)
                and box[0]<box[2] and box[1]<box[3] and request['coords']==[(box[0]+box[2])//2,(box[1]+box[3])//2]
                and request['input_source']=='touch' and all(request[k]==shot[k] for k in ('frame_sha256','scope_sha256','context_token')),
                'ONLY_ORIGINAL_CURRENT_OBSERVED_NODE_AND_FRAME_POINTER')

        def validate_ui_foreground(self,value,context):
            focus=self.last_focus
            self.c.need(type(value) is dict and set(value)=={'package','activity','window_token'} and focus is not None
                and focus['task']==context['owned_task'] and focus['task'] in self.case.ui.owned
                and (focus['package'],focus['activity']) in self.case.ui.allowed
                and value=={k:focus[k] for k in ('package','activity','window_token')}
                and value['package']==context['request'].get('package',context['request'].get('expected_package')),
                'ACTUAL_DOCUMENTS_OWNED_FOREGROUND_REQUIRED')
            if not context['mutation_sent'] and 'window_token' in context['request']:
                self.c.need(value['window_token']==context['request']['window_token'],'DOCUMENTS_WINDOW_CHANGED_BEFORE_INPUT')

        def validate_native_request(self,request,context,action_used):
            return self.components['documents_policy.py'].native_request(self.c,context['request'],request,action_used)

        def admit_ui_android(self,argv,timeout,context,action_used):
            self.c.need(context is self.active_api,'CURRENT_DOCUMENTS_API_CONTEXT')
            return self.components['documents_policy.py'].backend_android(self.c,context['request'],argv,timeout,action_used)

        def finish_ui_api(self,context,api,request,value,first,*,action_attempted):
            super().finish_ui_api(context,api,request,value,first,action_attempted=action_attempted)
            token=context.get('pending_token')
            if token is not None and first is None and type(value) is dict and context['mutation_sent'] and action_attempted:
                success=(value.get('ok') is True and (value.get('input_command_completed') is True
                    and (value.get('outcome_unknown') is not True or value.get('post_action_observation_available') is False)
                    or request.get('op')=='set-text' and value.get('performed')=='set-text'
                    and value.get('outcome_unknown') is not True and value.get('readback_verified') is True and value.get('password') is False))
                if success:
                    ref=self.c.regular(Path(context['output'])/'result.json',contents=False)
                    self.completed_inputs[token]={'result':ref,'phase':self.phase_ref,
                        'pre_action_tasks':context['pre_action_tasks'],'business_effect_not_inferred':True}
            # The finite runtime sample is explicitly labeled; it is never a
            # substitute for continuous/soak evidence or original file readback.
            if (context.get('pending_token') in ('open-files','open-files-cleanup')
                    and context.get('mutation_sent') and first is None and self.case.runtime is not None):
                self.case.runtime.after_input('api-'+str(context['api_sequence']))

        def close(self):
            first=None
            if self.held_artifacts is not None:
                try:self.held_artifacts.close()
                except BaseException as exc:first=exc
                self.held_artifacts=None
            try:super().close()
            except BaseException as exc:
                if first is None:first=exc
                else:first.add_note('DOCUMENTS_OTHER_CONTEXT_CLOSE:'+type(exc).__name__)
            if first is not None:raise first
    return Session
