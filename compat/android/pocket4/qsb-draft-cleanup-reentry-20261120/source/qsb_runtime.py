"""Finite QSB public-input session on the original held-Main transport.

Native release admission, Main v2, the original seven descriptors, action-lock
OFD and owned host retirement remain separate required authorities. No network
policy, APK, setting, permission or account write is available here.
"""
import base64
import copy
import json
import os
from pathlib import Path
import re
import resource
import time


def resource_report(c, live):
    value=live.report()
    c.need(type(value) is dict and value.get('schema')=='pocket4-held-effective-qsb-resources-v1',
           'ACTUAL_HELD_QSB_NATIVE_RESOURCES_REQUIRED')
    limits=value.get('limits')
    c.need(type(limits) is dict and set(limits)=={'cpu.max','memory.max','memory.swap.max','pids.max'}
           and limits['memory.max']=='2147483648' and limits['memory.swap.max']=='0'
           and limits['pids.max']=='64','QSB_FIXED_MEMORY_SWAP_PID_BUDGET')
    cpu=limits['cpu.max'].split()
    c.need(len(cpu)==2 and all(v.isdecimal() for v in cpu)
           and 0<int(cpu[0])<=2*int(cpu[1]) and int(cpu[1])>0,'QSB_CPU_BUDGET')
    events=value.get('memory_events')
    c.need(type(events) is dict and all(type(v) is int and v>=0 for v in events.values())
           and all(events.get(k)==0 for k in ('oom','oom_kill','oom_group_kill'))
           and type(value.get('swap_current_bytes')) is int and value['swap_current_bytes']==0
           and type(value.get('native_parent_pid')) is int and value['native_parent_pid']>0
           and type(value.get('native_parent_start_ticks')) is int and value['native_parent_start_ticks']>0,
           'QSB_ACTUAL_ANCESTOR_BUDGET_OR_NATIVE_PARENT_CHANGED')
    affinity=sorted(os.sched_getaffinity(0))
    c.need(value.get('affinity')==affinity and affinity and set(affinity)<={20,21}
           and resource.getrlimit(resource.RLIMIT_CORE)==(0,0),'QSB_AFFINITY_OR_CORE_LIMIT_CHANGED')
    return value


def make_session_class(original):
    class Session(original.ClockTransportBase):
        def __init__(self,c,base_ref,base,parts,release,resources,source_guard,action_lock):
            self.c=c;self.base_ref=base_ref;self.base=base;self.parts=parts
            self.profile=parts['qsb_profile.py'];self.task=parts['qsb_tasks.py']
            self.observer=parts['qsb_observation.py'];self.root=Path(base['case_root'])
            self.release=release;self.resources=resources;self.source_guard=source_guard
            self.action_lock=action_lock;self.closed=False;self.view=self.peer=self.helper=None
            self.artifacts=None;self.host_retirement_unknown=self.host_cancelled=self.possible_effect=False
            self.phase='business';self.started=time.monotonic();self.deadline=self.started+600
            self.cleanup_deadline=self.started+720;self.command_index=0;self.records=[]
            self.active_api=None;self.api_sequence=0;self.pending=None;self.native_launches=0
            self.claimed={};self.removed=[];self.original_roots=self.original_tasks=None
            self.qsb_task=self.browser_task=None;self.last_focus=None;self.last_frame=None
            self.last_api_ref=None;self.native_return=None;self.allowed_ui_packages={self.profile.PACKAGE,self.profile.BROWSER['package']}
            self.observations=0;self.text_edits=0;self.clicks=0;self.back_events=0
            self.journal=c.private_dir(self.root/'commands',create=True)
            self.api_root=c.private_dir(self.root/'api',create=True)
            self.phase_ref=c.write_new(self.root/'phase-business.json',{
                'schema':'pocket4-qsb-phase-v1','base_plan':base_ref,'phase':'business',
                'owner':parts['app_runtime.py'].process(c,os.getpid()),'started_monotonic':self.started,
                'business_deadline_monotonic':self.deadline,'cleanup_deadline_monotonic':self.cleanup_deadline,
                'limits':self.profile.LIMITS,'automatic_retry':False},0o400)
            try:
                def no_bootstrap_commands(*args):
                    raise RuntimeError('QSB_COMMANDS_REQUIRE_FINITE_SOURCE_POLICY')
                self.view=c.MainView(base['baseline'],base['qualification'],self.journal,no_bootstrap_commands,
                                     support_ref=base['support_manifest'])
                self.baseline=self.view.baseline;self.environment=self.view.environment
                self.commands=parts['app_runtime.py'].PhaseCommands(self.view.commands,self)
                identities=[c.parse(c.read_ref(base[key])) for key in ('target_identity','helper_identity','browser_identity')]
                self.artifacts=c.HeldArtifacts(self.view.target,identities)
                self.guard();self.helper=parts['original_ui.py'].OriginalAPIs(self)
                self.helper.foreground=self.helper_foreground
            except BaseException:
                self.close();raise

        def guard(self,*,action_attempted=False):
            self.release.guard();resource_report(self.c,self.resources)
            value=super().guard(action_attempted=action_attempted)
            if self.artifacts is not None:self.artifacts.verify()
            return value

        def record(self,name,value):
            self.c.need(re.fullmatch('[a-z0-9][a-z0-9-]{0,95}',name),'QSB_EVIDENCE_NAME')
            return self.c.write_new(self.root/(name+'.json'),value)

        def _transport(self,label,logical,timeout,*,mutation=False,image=False,root=False):
            c=self.c;p=self.profile
            c.need(root is False and type(logical) is list,'QSB_NEVER_ROOT_ANDROID_OR_UNTYPED_COMMAND')
            ordinary=[(c.STACKS,15),(c.FOREGROUND,6),
                (['/system/bin/dumpsys','package',p.PACKAGE],20),
                (['/system/bin/dumpsys','package',p.BROWSER['package']],20)]
            if any(logical==argv and timeout==bound for argv,bound in ordinary):
                c.need(not mutation and not image,'QSB_READ_ONLY_PACKAGE_TASK_WINDOW')
            elif logical==['/system/bin/dumpsys','activity','activities',p.BROWSER['package']]:
                c.need(timeout==20 and not mutation and not image and self.pending is not None
                       and self.pending['kind']=='open-result','QSB_ONLY_CURRENT_RESULT_INTENT_READ')
            elif logical==['/system/bin/input','keyevent','KEYCODE_BACK']:
                c.need(timeout==15 and mutation and not image and self.pending is not None
                       and self.pending['kind']=='return' and not self.pending['sent'],
                       'QSB_ONE_OWNED_BROWSER_BACK_EVENT')
                self.pending['sent']=True
            elif logical[:4]==['/system/bin/cmd','activity','stack','remove']:
                c.need(timeout==15 and mutation and not image and self.phase=='cleanup'
                       and self.pending is not None and self.pending['kind']=='remove'
                       and logical==['/system/bin/cmd','activity','stack','remove',str(self.pending['task'])]
                       and not self.pending['sent'],'QSB_ONLY_KNOWN_OWNED_TASK_REMOVAL')
                self.pending['sent']=True
            else:
                c.need(self.active_api is not None,'QSB_NO_ANDROID_COMMAND_OUTSIDE_FIXED_POLICY')
                actual_mutation,actual_image=self.admit_ui_android(logical,timeout,self.active_api,False)
                c.need(mutation is actual_mutation and image is actual_image,'QSB_BACKEND_COMMAND_MODE_CHANGED')
            return super()._transport(label,logical,timeout,mutation=mutation,image=image,root=False)

        def _host(self,label,argv,timeout,mutation=False):
            launch=list(self.c.NATIVE_PREFIX)+['launch',self.profile.PACKAGE,'--component',self.profile.COMPONENT,'--json']
            if argv==launch:
                self.c.need(timeout==70 and mutation and self.phase=='business'
                    and self.pending is not None and self.pending['kind']=='launch' and not self.pending['sent'],
                    'QSB_ONLY_ONCE_CURRENT_NATIVE_LAUNCH')
                self.pending['sent']=True
            else:
                self.c.need(argv==['/usr/bin/droidloomctl','readiness','--json'] and timeout==8
                    and not mutation and self.active_api is not None,'QSB_NO_OTHER_HOST_COMMAND')
            return super()._host(label,argv,timeout,mutation)

        def verify_final_consumers(self,app,backend):
            self.guard();module=self.view.modules['business_ui_entry.py']
            value=self.c.parse(self.c.read_ref(module.CONSUMERS))
            rows=module.final_consumer_contract(self.baseline.docs['deployment_manifest'],value)
            actual=[]
            for row in rows:
                self.c.need(self.c.regular(row['path'],contents=False)==row,'QSB_FINAL_UI_CONSUMER_BODY_CHANGED')
                info=Path(row['path']).lstat()
                self.c.need(info.st_uid==info.st_gid==0 and info.st_nlink==1
                            and info.st_mode & 0o7777==0o755,'QSB_FINAL_UI_CONSUMER_OWNER_MODE')
                actual.append(row)
            self.c.need(app in actual and backend in actual,'QSB_UI_CONSUMER_NOT_DEPLOYED_WITH_MAIN')

        def stacks(self):
            raw=self._transport('qsb-tasks',self.c.STACKS,15)['stdout']
            return self.task.parse_stacks(raw.decode('utf-8','strict'))

        def topology(self):
            roots,tasks=self.stacks()
            active={task for task in self.claimed if task not in self.removed}
            self.task.preserved(roots,tasks,self.original_roots,self.original_tasks,active)
            for task in active:
                self.c.read_ref(self.claimed[task]['ref'])
                self.task.one_leaf(roots,task,self.claimed[task]['package'],
                                   native_freeform=self.claimed[task]['package']==self.profile.PACKAGE)
            return roots,tasks

        def focus(self,package):
            raw=self._transport('qsb-focus',self.c.FOREGROUND,6)['stdout']
            value=self.task.focus_metadata(raw.decode('utf-8','strict'))
            self.c.need(value.get('verified') is True and value.get('package')==package
                and value.get('user')==0 and value.get('task') in self.claimed
                and self.claimed[value['task']]['package']==package
                and value['task'] not in self.removed,'QSB_CURRENT_OWNED_FOCUS_REQUIRED')
            if package==self.profile.PACKAGE:
                self.c.need(value['activity'] in ('.SearchActivity',self.profile.ACTIVITY)
                    and value['focused_activity'] in ('.SearchActivity',self.profile.ACTIVITY),
                    'QSB_MAIN_SEARCH_ACTIVITY_REQUIRED')
            self.topology();self.last_focus=copy.deepcopy(value);return value

        def helper_foreground(self):
            self.c.need(self.active_api is not None,'QSB_FOREGROUND_ONLY_INSIDE_CURRENT_API')
            p=self.active_api['package'];value=self.focus(p)
            return {k:value[k] for k in ('package','activity','window_token')}

        def verify_original_callback(self,kind,callback,previous):
            fn=getattr(callback,'__func__',None)
            self.c.need(kind=='foreground' and previous is None and getattr(callback,'__self__',None) is self
                and fn is type(self).helper_foreground,'QSB_ONLY_THIS_SOURCE_BOUND_FOREGROUND_CALLBACK')

        def begin_ui_api(self,api,request):
            c=self.c;c.need(self.phase=='business' and self.active_api is None,'QSB_SINGLE_CURRENT_UI_API')
            package=request.get('package',request.get('expected_package'))
            c.need(package in self.allowed_ui_packages and request.get('display')==0
                   and request.get('accessibility_mode')=='none','QSB_EXACT_ADMITTED_UI_SCOPE')
            if api=='dispatch':
                c.need(request=={'op':'observe','package':package,'window_token':request.get('window_token'),
                     'display':0,'accessibility_mode':'none','with_png':True},'QSB_ONLY_SCOPED_FULL_OBSERVATION')
                self.observations+=1;c.need(self.observations<=self.profile.LIMITS['maximum_UI_observations'],'QSB_OBSERVATION_BOUND')
            else:
                c.need(api=='ui' and package==self.profile.PACKAGE and self.pending is not None
                    and self.pending['kind'] in ('set-query','open-result')
                    and self.pending['request']==request and not self.pending['sent'],
                    'QSB_UI_MUTATION_NEEDS_EXACT_DURABLE_ONCE_INTENT')
            focus=self.focus(package)
            if 'window_token' in request:c.need(request['window_token']==focus['window_token'],'QSB_WINDOW_CHANGED_BEFORE_UI')
            if api=='ui':c.need(focus==self.pending['focus'],'QSB_INPUT_FOCUS_CHANGED')
            self.api_sequence+=1
            context={'schema':'pocket4-qsb-current-ui-context-v1','api':api,'request':copy.deepcopy(request),
                'package':package,'phase':self.phase_ref,'observed_focus':focus,
                'owned_task':self.claimed[focus['task']]['ref'],'api_sequence':self.api_sequence,
                'mutation_sent':False,'native_returns':0,'automatic_retry':False,
                'output':str(c.private_dir(self.api_root/('api-%04d'%self.api_sequence),create=True))}
            c.write_new(Path(context['output'])/'context.json',context)
            self.active_api=context;return context

        def validate_ui_foreground(self,value,context):
            self.c.need(context is self.active_api and self.last_focus is not None
                and value=={k:self.last_focus[k] for k in ('package','activity','window_token')}
                and value['package']==context['package'],'QSB_ACTUAL_UI_FOREGROUND_CHANGED')
            if not context['mutation_sent']:
                self.c.need(self.last_focus==context['observed_focus'],'QSB_PRE_INPUT_WINDOW_CHANGED')

        def validate_native_request(self,request,context,action_used):
            c=self.c;c.need(context is self.active_api and type(request) is dict
                and request.get('expected_package')==context['package'] and request.get('display')==0
                and request.get('accessibility_mode')=='none','QSB_EXACT_NATIVE_PACKAGE_DISPLAY')
            if request.get('op') in ('meta','dump'):
                c.need(context['api']=='dispatch' and set(request)=={'op','expected_package','display','accessibility_mode'},
                    'QSB_ONLY_OBSERVATION_INTERNAL_META_DUMP');return False
            c.need(context['api']=='ui' and not action_used and request==context['request']
                and request.get('op') in ('click','set-text'),'QSB_ONE_EXACT_NATIVE_INPUT')
            return True

        def admit_ui_android(self,argv,timeout,context,action_used):
            self.c.need(context is self.active_api,'QSB_CURRENT_NATIVE_BACKEND_CALL')
            if argv==['/system/bin/screencap','-p']:
                self.c.need(context['api']=='dispatch' and timeout==20,'QSB_ONLY_CURRENT_OBSERVATION_PIXELS')
                return False,True
            self.c.need(len(argv)==8 and argv[:6]==['/system/bin/am','instrument','-w','-r','-e','request']
                and argv[-1]=='local.pocket4.actions.v2/.ActionRunner' and timeout==70,
                'QSB_ONLY_PINNED_NATIVE_ACTION_RUNNER')
            raw=base64.b64decode(argv[6],validate=True);self.c.need(0<len(raw)<=65536,'QSB_NATIVE_WIRE_BOUND')
            req=self.c.parse(raw)
            self.c.need(base64.b64encode(json.dumps(req,ensure_ascii=True,separators=(',',':')).encode()).decode()==argv[6],
                'QSB_ORIGINAL_NATIVE_WIRE_ENCODING')
            return self.validate_native_request(req,context,action_used),False

        def ui_android(self,argv,timeout,context,*,mutation=False,image=False):
            if mutation:
                self.c.need(self.pending is not None and not self.pending['sent'],'QSB_NATIVE_ACTION_ALREADY_SENT')
                self.pending['sent']=True
            return super().ui_android(argv,timeout,context,mutation=mutation,image=image)

        def record_native_return(self,request,value,context):
            super().record_native_return(copy.deepcopy(request),copy.deepcopy(value),context)
            if request.get('op') in ('click','set-text'):
                self.native_return={'request':copy.deepcopy(request),'response':copy.deepcopy(value),
                    'receipt':self.c.regular(Path(context['output'])/('native-return-%03d.json'%context['native_returns']),contents=False)}

        def finish_ui_api(self,context,api,request,value,first,*,action_attempted):
            try:
                super().finish_ui_api(context,api,request,value,first,action_attempted=action_attempted)
                self.last_api_ref=self.c.regular(Path(context['output'])/'result.json',contents=False)
            except BaseException:
                self.host_retirement_unknown=True;raise

        def observe(self,package,label):
            focus=self.focus(package)
            value=self.helper.dispatch({'op':'observe','package':package,'window_token':focus['window_token'],
                'display':0,'accessibility_mode':'none','with_png':True})
            after=self.focus(package);self.c.need(after==focus,'QSB_FOCUS_CHANGED_DURING_OBSERVATION')
            observed=self.observer.scoped(value,package=package,focus=focus,init_pid=self.view.target.expected['pid'])
            observed['actual_API_result']=self.last_api_ref;observed['focus']=focus
            ref=self.record(label,observed);self.last_frame=(observed,ref);return observed,ref

        def launch(self):
            self.c.need(self.phase=='business' and self.pending is None and self.native_launches<2,
                'QSB_ONLY_TWO_FRESH_NATIVE_LAUNCHES')
            roots,tasks=self.stacks()
            if self.original_roots is None:
                self.c.need(not any(ch['component'].split('/')[0] in self.allowed_ui_packages
                    for root in roots.values() for ch in root['children']),
                    'QSB_PREEXISTING_QSB_OR_BROWSER_TASKS_PRESERVED')
                self.original_roots=copy.deepcopy(roots);self.original_tasks=set(tasks)
                self.record('task-baseline',{'roots':roots,'task_ids':sorted(tasks)})
            else:self.c.need(roots==self.original_roots and tasks==self.original_tasks,'QSB_REOPEN_REQUIRES_FULL_TASK_RESTORATION')
            self.native_launches+=1
            argv=list(self.c.NATIVE_PREFIX)+['launch',self.profile.PACKAGE,'--component',self.profile.COMPONENT,'--json']
            intent=self.record('launch-%d-intent'%self.native_launches,{'argv':argv,'before_tasks':sorted(tasks),'automatic_retry':False})
            self.pending={'kind':'launch','sent':False,'intent':intent}
            before_launch_records = len(self.records)
            response = self._host('qsb-native-launch', argv, 70, True)
            self.c.need(len(self.records) == before_launch_records + 1,
                        'QSB_NATIVE_LAUNCH_RESULT_RECORD_REQUIRED')
            launch_result = self.records[-1]
            self.c.read_ref(launch_result)
            reply = self.c.parse(response['stdout'])
            after,after_tasks=self.stacks()
            task=self.task.native_claim(reply,after,after_tasks,roots,tasks,self.profile,self.view.target.expected['pid'])
            ref=self.record('launch-%d-claim'%self.native_launches,{'source':'actual-native-launch',
                'intent':intent,'native_reply':reply,'actual_host_result':launch_result,
                'task':task,'package':self.profile.PACKAGE,'before_tasks':sorted(tasks),
                'baseline':self.base['baseline'],'qualification':self.base['qualification'],'automatic_retry':False})
            self.claimed[task]={'ref':ref,'package':self.profile.PACKAGE};self.qsb_task=task
            self.pending=None;self.focus(self.profile.PACKAGE);return ref

        def set_query(self,value):
            self.c.need(self.pending is None and self.last_frame is not None and self.text_edits<3
                and value==(*self.profile.QUERIES,'')[self.text_edits],'QSB_FIXED_ONCE_UNICODE_QUERY_ORDER')
            observed,prior=self.last_frame;self.c.read_ref(prior)
            selected=[n for n in self.observer.visible(observed['nodes'],self.profile.PACKAGE)
                if n.get('resource-id')==self.profile.QUERY_ID and n.get('editable') is True]
            self.c.need(len(selected)==1,'QSB_ONE_OBSERVED_EDITABLE_QUERY_FIELD')
            focus=self.focus(self.profile.PACKAGE);self.c.need(focus==observed['focus'],'QSB_QUERY_NODE_WINDOW_STALE')
            request={'op':'set-text','expected_package':self.profile.PACKAGE,'display':0,
                'accessibility_mode':'none','selector':{'id':self.profile.QUERY_ID,'editable':True,'enabled':True},'value':value}
            self.text_edits+=1
            intent=self.record('edit-%d-intent'%self.text_edits,{'request':request,'observed_node':selected[0],
                'observation':prior,'focus':focus,'automatic_retry':False})
            self.pending={'kind':'set-query','sent':False,'request':request,'focus':focus,'intent':intent}
            response=self.helper.ui(request);self.observer.input_ack(response,request,selected[0])
            actual,ref=self.observe(self.profile.PACKAGE,'edit-%d-readback'%self.text_edits)
            checked=self.observer.query(actual['nodes'],self.profile,value,matches=bool(value),empty=not value)
            result=self.record('edit-%d-verified'%self.text_edits,{'intent':intent,'native':self.native_return,
                'actual_observation':ref,'query':checked,'automatic_retry':False})
            self.pending=None;return checked,result

        def open_result(self):
            self.c.need(self.pending is None and self.clicks==0 and self.text_edits==2
                and self.last_frame is not None,'QSB_ONCE_KNOWN_RESULT_AFTER_UNICODE_READBACK')
            observed,prior=self.last_frame;chosen=self.observer.known_result(observed['nodes'],self.profile)
            focus=self.focus(self.profile.PACKAGE);self.c.need(focus==observed['focus'],'QSB_RESULT_LABEL_WINDOW_STALE')
            before,before_tasks=self.topology()
            request={'op':'click','expected_package':self.profile.PACKAGE,'display':0,'accessibility_mode':'none',
                'selector':{'id':self.profile.TITLE_ID,'text':self.profile.KNOWN_RESULT,'enabled':True},'method':'accessibility'}
            intent=self.record('open-result-intent',{'request':request,'label':chosen,'observation':prior,
                'focus':focus,'before_roots':before,'before_tasks':sorted(before_tasks),'automatic_retry':False})
            self.pending={'kind':'open-result','sent':False,'request':request,'focus':focus,'intent':intent};self.clicks=1
            ack=self.helper.ui(request);self.observer.input_ack(ack,request,chosen)
            roots,tasks=self.stacks();extra=tasks-before_tasks
            self.c.need(len(extra)==1 and before_tasks<=tasks,'QSB_RESULT_MUST_CREATE_ONE_NEW_BROWSER_TASK')
            browser=next(iter(extra));self.task.one_leaf(roots,browser,self.profile.BROWSER['package'])
            self.task.preserved(roots,tasks,before,before_tasks,{browser})
            raw=self._transport('qsb-browser-intent',
                ['/system/bin/dumpsys','activity','activities',self.profile.BROWSER['package']],20)['stdout']
            url=self.task.browser_intent(raw,browser,self.profile,self.profile.KNOWN_RESULT,self.observer.search_url)
            raw_ref=self.c.write_new(self.root/'browser-activity.txt',raw)
            ref=self.record('browser-result-claim',{'source':'QSB-native-click-and-actual-caller-intent',
                'task':browser,'package':self.profile.BROWSER['package'],'source_task':self.qsb_task,
                'intent':intent,'actual_native_return':self.native_return,'actual_activity':raw_ref,'search':url,
                'baseline':self.base['baseline'],'qualification':self.base['qualification'],
                'preexisting_browser_task_adopted':False,'automatic_retry':False})
            self.claimed[browser]={'ref':ref,'package':self.profile.BROWSER['package']};self.browser_task=browser
            page,page_ref=self.observe(self.profile.BROWSER['package'],'opened-browser-document')
            rendered=self.observer.browser_document(page['nodes'],self.profile,self.profile.KNOWN_RESULT)
            self.pending=None
            return self.record('opened-result-verified',{'claim':ref,'URL':url,'rendered':rendered,
                'actual_observation':page_ref,'query_state_return_verified':False})

        def return_to_query(self):
            self.c.need(self.pending is None and self.browser_task is not None and self.back_events==0,
                'QSB_ONE_NORMAL_RETURN_FROM_OWNED_BROWSER')
            focus=self.focus(self.profile.BROWSER['package'])
            intent=self.record('return-intent',{'browser_claim':self.claimed[self.browser_task]['ref'],
                'focus':focus,'argv':['/system/bin/input','keyevent','KEYCODE_BACK'],'automatic_retry':False})
            self.pending={'kind':'return','sent':False,'intent':intent};self.back_events=1
            self._transport('qsb-normal-back',['/system/bin/input','keyevent','KEYCODE_BACK'],15,mutation=True)
            roots,tasks=self.stacks()
            self.c.need(self.browser_task not in tasks and self.browser_task not in roots,
                'QSB_BROWSER_TASK_NOT_NORMALLY_CLOSED_AFTER_BACK_NO_EXTRA_ACTION')
            self.removed.append(self.browser_task)
            self.topology();page,ref=self.observe(self.profile.PACKAGE,'returned-query')
            checked=self.observer.query(page['nodes'],self.profile,self.profile.QUERIES[1],matches=True)
            self.pending=None
            return self.record('return-verified',{'intent':intent,'observation':ref,'query':checked,
                'source_task':self.qsb_task,'browser_task_absent':True,'exact_query_preserved':True,
                'browser_tabs_history_or_preferences_qualified':False})

        def begin_cleanup(self):
            self.c.need(self.pending is None and self.active_api is None and not self.host_retirement_unknown
                and self.phase=='business' and time.monotonic()<self.cleanup_deadline,
                'QSB_CLEANUP_REQUIRES_KNOWN_EFFECTS_AND_ORIGINAL_RESERVE')
            self.phase='cleanup';self.deadline=self.cleanup_deadline
            self.phase_ref=self.record('phase-cleanup-%d'%self.native_launches,{'phase':'cleanup','base_plan':self.base_ref,
                'deadline_monotonic':self.deadline,'automatic_retry':False})

        def normal_close_qsb(self,label):
            self.c.need(self.pending is None and self.active_api is None and self.qsb_task is not None
                and self.qsb_task not in self.removed,'QSB_ONLY_KNOWN_NEW_QSB_TASK_CLOSE')
            if self.phase=='business':self.begin_cleanup()
            self.topology();task=self.qsb_task
            intent=self.record(label+'-intent',{'claim':self.claimed[task]['ref'],'task':task,'automatic_retry':False})
            self.pending={'kind':'remove','task':task,'sent':False,'intent':intent}
            self._transport('qsb-owned-remove',['/system/bin/cmd','activity','stack','remove',str(task)],15,mutation=True)
            roots,tasks=self.stacks()
            self.c.need(task not in tasks and task not in roots,'QSB_OWNED_TASK_REMOVAL_NOT_OBSERVED')
            self.removed.append(task);self.pending=None;self.topology()
            return self.record(label+'-verified',{'intent':intent,'task_absent':True,'other_tasks_preserved':True})

        def reopen_business(self):
            # The second normal launch is still within the original absolute
            # 600-second business deadline; cleanup never extends that budget.
            self.c.need(self.phase=='cleanup' and self.native_launches==1 and self.pending is None
                and time.monotonic()<self.started+600,'QSB_REOPEN_INSIDE_ORIGINAL_BUSINESS_BUDGET')
            self.phase='business';self.deadline=self.started+600
            self.phase_ref=self.record('phase-reopen',{'phase':'business','base_plan':self.base_ref,
                'deadline_monotonic':self.deadline,'automatic_retry':False})

        def run_search_case(self):
            """Run the finite query/open case inside this admitted Session.

            The caller owns release, Main, source, resources and Session retirement.
            Each business step returns its existing evidence reference. Unknown
            effects remain with the original owner and are never replayed here.
            """
            self.guard()
            self.c.need(self.native_launches == 0 and self.phase == 'business'
                        and self.pending is None and self.active_api is None
                        and not self.claimed and not self.removed,
                        'QSB_CASE_REQUIRES_FRESH_SESSION')
            started = self.record('search-case-once', {
                'base_plan': self.base_ref, 'phase': self.phase_ref,
                'automatic_retry': False,
            })
            receipts = {'started': started}
            close_attempted = False
            try:
                receipts['first_launch'] = self.launch()
                _, receipts['initial_window'] = self.observe(self.profile.PACKAGE, 'initial-query')
                for index, query in enumerate(self.profile.QUERIES, start=1):
                    _, receipts['query_%d' % index] = self.set_query(query)
                receipts['opened_result'] = self.open_result()
                receipts['returned_to_query'] = self.return_to_query()
                _, receipts['cleared_query'] = self.set_query('')
                close_attempted = True
                receipts['first_close'] = self.normal_close_qsb('first-close')
                self.reopen_business()
                close_attempted = False
                receipts['second_launch'] = self.launch()
                reopened, receipts['reopened_window'] = self.observe(
                    self.profile.PACKAGE, 'reopened-query')
                self.observer.query(reopened['nodes'], self.profile, '', matches=False, empty=True)
                close_attempted = True
                receipts['second_close'] = self.normal_close_qsb('second-close')
                self.guard()
                roots, tasks = self.stacks()
                self.c.need(roots == self.original_roots and tasks == self.original_tasks
                            and self.pending is None and self.active_api is None
                            and not self.host_cancelled and not self.host_retirement_unknown
                            and self.native_launches == 2 and self.text_edits == 3
                            and self.clicks == self.back_events == 1,
                            'QSB_COMPLETE_TASK_RESTORATION_AND_ACTION_COUNTS_REQUIRED')
                for ref in receipts.values():
                    self.c.read_ref(ref)
                return self.record('search-case-observations', {
                    'base_plan': self.base_ref, 'receipts': receipts,
                    'observed_scope': ['search.query', 'search.open'],
                    'remaining_business_gates': ['search.failure'],
                    'whole_app_business_accepted': False,
                })
            except BaseException as error:
                # Only an identified, still-owned QSB task can be closed here.
                # A browser still present or an uncertain input needs reconciliation.
                known_qsb = self.qsb_task in self.claimed and self.qsb_task not in self.removed
                browser_closed = self.browser_task is None or self.browser_task in self.removed
                if (known_qsb and browser_closed and not close_attempted and self.pending is None
                        and self.active_api is None and not self.host_retirement_unknown
                        and not self.host_cancelled):
                    try:
                        self.normal_close_qsb('failure-close')
                    except BaseException as cleanup_error:
                        error.add_note('QSB owned task cleanup: ' + str(cleanup_error))
                raise

        def close(self):
            first=None
            if self.artifacts is not None:
                try:self.artifacts.close()
                except BaseException as error:first=error
                self.artifacts=None
            try:super().close()
            except BaseException as error:
                if first is None:first=error
                else:first.add_note('QSB_OTHER_CONTEXT_CLOSE:'+type(error).__name__)
            if first is not None:raise first
    return Session


def execute(c, base_ref, parts, release, resources, source_guard, action_lock):
    """Execute an already admitted QSB plan and retire its host context.

    The native caller supplies its live release, held resources, original action
    lock and source loader. This entry does not acquire or issue those objects.
    """
    base = c.parse(c.read_ref(base_ref))
    release.guard()
    resource_report(c, resources)
    source_guard()
    action_lock.verify()
    session_class = make_session_class(parts['original_transport.py'])
    session = session_class(c, base_ref, base, parts, release, resources,
                            source_guard, action_lock)
    try:
        observations = session.run_search_case()
    except BaseException as error:
        try:
            session.close()
        except BaseException as close_error:
            error.add_note('QSB session retirement: ' + str(close_error))
        raise
    session.close()
    release.guard()
    resource_report(c, resources)
    source_guard()
    action_lock.verify()
    c.read_ref(base_ref)
    c.read_ref(observations)
    return session.record('search-case-result', {
        'base_plan': base_ref,
        'observations': observations,
        'session_closed': True,
        'observed_scope': ['search.query', 'search.open'],
        'remaining_business_gates': ['search.failure'],
        'whole_app_business_accepted': False,
    })
