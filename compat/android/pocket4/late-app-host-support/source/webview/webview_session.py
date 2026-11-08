"""Fresh Main and strict original WebView API/task boundaries.

Only the business worker owns this same-process action lock and its short
Android command children. The fixed web server remains an independently
supervised sibling, with a typed parent channel and a separate actual pidfd.
"""
import base64,copy,inspect,os,re,stat,time,types
from pathlib import Path
class Evidence:
    def __init__(self, session):
        self.s = session
        self.ALEX_PREFIX = list(session.c.NATIVE_PREFIX)
        self.MAIN_HOST = session.baseline.docs['final_baseline']['daemon_status']['host_pid']
    def write_new(self, path, value, **options):
        s = self.s; path = Path(path)
        s.c.need(not set(options) - {'alex_readable'} and (not options or type(options['alex_readable']) is bool)
            and path.is_relative_to(s.evidence_root) and path.parent.resolve() == path.parent,
            'ONLY_NEW_PRIVATE_CASE_EVIDENCE')
        raw = value if type(value) is bytes else s.c.canonical(value)
        s.c.need(len(raw) <= (33554432 if path.suffix == '.png' else 16777216), 'ORIGINAL_CASE_EVIDENCE_BOUND')
        ref = s.c.write_new(path, raw)
        if type(value) is dict:
            s.note_original_record(ref, value)
        return ref

class SharedSessionMethods:
    def new_flow(self, index):
        flow = self.flow_type(self.c, self.scopes[index], 'launch', 'case-start', self.deadline,
            self.components['webview_guard.py'], self.policy_module.Policy,
            private_context={'phase_lease': self.phase_ref, 'session': self})
        try:
            original = self.transport_module.bound_class(self.c, flow.scope_module, self.active['support_manifest'], 'camera_android')
            def record(kind, value):
                self.c.write_new(flow.step / ('ordinary-transport-%03d.%s.json' % (value['sequence'], kind)), value)
            flow.camera_transport = original(target=flow.view.target, environment=flow.view.environment,
                binding=flow.bound, runner=lambda argv, **kw: flow.bridge.runner(argv, **kw), record=record)
            return flow
        except BaseException:
            flow.close(); raise

    def verify_runtime(self, flow):
            c = self.c
            c.need(not self.closed and flow.plan == self.active and flow.scope_ref in self.scopes
                and flow.scope['phase_plan'] == self.active_ref and flow.phase_lease_ref == self.phase_ref
                and flow.deadline == self.deadline and flow.session is self
                and self.action_lock.ref == self.active['action_lock'], 'EXACT_SAME_PROCESS_CASE_FLOW_AND_PHASE')
            self.action_lock.verify()

    def original_caller(self, names, methods=None, *, skip_trial_record=False):
            frame = inspect.currentframe()
            try:
                for _ in range(16):
                    frame = frame.f_back
                    if frame is None:
                        break
                    for name in names:
                        if frame.f_code.co_filename == self.source_paths.get(name):
                            # Trial.record is the unchanged observational writer.
                            # An intent belongs to its actual original launch,
                            # close, continuation step or Editor action caller.
                            if skip_trial_record and name == self.trial_source and frame.f_code.co_name == 'record':
                                continue
                            self.c.need(methods is None or frame.f_code.co_name in methods,
                                'ONLY_ORIGINAL_CASE_API_CALLER')
                            return {'source': name, 'function': frame.f_code.co_name}
                raise RuntimeError('TYPED_API_NOT_CALLED_BY_REVIEWED_ORIGINAL_COMPONENT')
            finally:
                del frame

    def consume_original_intent(self, kind, requested):
            c = self.c; matches = []
            for item in self.original_intents:
                if item['ref']['path'] in self.used_intents or item['phase'] != self.phase_ref:
                    continue
                value = item['value']; actual = value.get('argv')
                if kind == 'ui':
                    actual = value.get('command', value.get('request'))
                if kind == 'remove' and value.get('method') == 'normal exact owned leaf remove':
                    actual = ['/system/bin/cmd', 'activity', 'stack', 'remove', str(value['task'])]
                if actual == requested:
                    matches.append(item)
            c.need(len(matches) == 1, 'ONE_UNCONSUMED_ORIGINAL_INTENT_REQUIRED:' + kind)
            item = matches[0]; c.read_ref(item['ref'])
            c.need(kind == 'launch' or item['scope'] == self.flow.scope_ref, 'INTENT_NOT_CURRENT_NEW_TASK_SCOPE')
            self.used_intents.add(item['ref']['path'])
            self.c.write_new(self.flow.step / ('once-intent-%05d.json' % item['sequence']), {
                'kind': kind, 'original': item['ref'], 'original_source': item['caller'],
                'scope': self.flow.scope_ref, 'phase_lease': self.phase_ref, 'automatic_retry': False})
            return item

    def android(self, argv, timeout=20):
            self.guard(); argv = list(argv)
            self.c.need(self.ordinary_admission is None, 'NO_REENTRANT_ORIGINAL_ANDROID_CALL')
            mutate = self.flow.policy.command(argv, timeout)
            self.ordinary_admission = (argv, timeout, mutate)
            try:
                raw = self.flow.android(argv, timeout, mutation=mutate)
                self.flow.policy.observe(argv, raw)
                if argv == self.c.STACKS:
                    roots, tasks = self.flow.tasks.parse_stacks(raw.decode('utf-8', 'strict'))
                    self.last_stacks = (roots, tasks)
                    if self.baseline_tasks is None:
                        self.c.need(not any(x['component'].split('/')[0] == self.active['target_profile']['package']
                            for root in roots.values() for x in root['children']), 'PREEXISTING_TARGET_TASK_PRESERVED')
                        self.baseline_roots, self.baseline_tasks = copy.deepcopy(roots), set(tasks)
                return raw
            finally:
                self.ordinary_admission = None

    def begin_cleanup(self, trigger):
            self.c.need(self.phase_name == 'business' and self.active_api is None, 'ONCE_ORIGINAL_CLEANUP_SWITCH')
            ref = self.runtime.phase(self.c, self.host, self.active_ref, self.active, 'final_cleanup', trigger)
            phase = self.runtime.validate_phase(self.c, self.host, ref, self.active_ref, self.active)
            self.phase_ref, self.phase_value, self.phase_name = ref, phase, 'final_cleanup'
            self.flow.set_phase(ref)
            return ref

    def verify_final_consumers(self, app, backend):
            self.c.need(self.c.regular(app['path'], contents=False) == app
                and self.c.regular(backend['path'], contents=False) == backend,
                'ACTUAL_FINAL_QUALIFIED_UI_CLIENT_AND_BACKEND_REQUIRED')
            self.baseline.guard()

    def ui_guard(self, *, action_attempted=False):
            self.guard(action_attempted=action_attempted)
            self.c.need(self.active_api is None or self.active_api['scope'] == self.flow.scope_ref
                and self.active_api['phase_lease'] == self.phase_ref, 'API_SCOPE_OR_PHASE_CHANGED')

    def validate_internal_capture(self, request, context):
            c = self.c; expected = context['request']
            c.need(type(request) is dict and request.get('package') == expected.get('package', expected.get('expected_package'))
                and request.get('display') == 0 and request.get('accessibility_mode') == 'none'
                and set(request) <= {'op', 'package', 'display', 'accessibility_mode', 'window_token', 'with_png', 'selector',
                    'value', 'method', 'coords', 'input_source', 'frame_sha256', 'scope_sha256', 'context_token', 'crop'},
                'ONLY_ORIGINAL_INTERNAL_CAPTURE')
            if not context['mutation_sent']:
                c.need(request == expected, 'PRE_ACTION_CAPTURE_MUST_USE_UNCHANGED_ORIGINAL_REQUEST')
            else:
                c.need(set(request) <= {'package', 'display', 'accessibility_mode', 'crop'}, 'ONLY_ORIGINAL_POST_ACTION_CAPTURE_FIELDS')

    def validate_native_request(self, request, context, action_used):
            return self.policy_module.native_request(self.c, context['request'], request, action_used)

    def record_native_return(self, request, value, context):
            context['native_returns'] += 1
            try:
                # Encode synchronously before the exact backend mutates this same
                # dict with before/after or post-capture UNKNOWN fields.
                self.c.write_new(self.flow.step / ('native-return-%03d.json' % context['native_returns']),
                    {'request': request, 'native_response': value, 'scope': self.flow.scope_ref,
                     'phase_lease': self.phase_ref, 'automatic_retry': False})
            except BaseException as error:
                self.flow.bound.hold(error); self.flow.view.target.seal_admission(); raise

    def admit_ui_android(self, argv, timeout, context, action_used):
            self.c.need(context is self.active_api, 'CURRENT_ORIGINAL_API_CONTEXT_REQUIRED')
            return self.policy_module.backend_android(self.c, context['request'], argv, timeout, action_used)

    def ui_android(self, argv, timeout, context, *, mutation=False, image=False):
            f = self.flow
            self.c.need(context is self.active_api and self.ui_dispatch_admission is None, 'ONE_TYPED_BACKEND_CALL_AT_A_TIME')
            self.ui_dispatch_admission = (argv, timeout, mutation)
            if mutation:
                self.c.need(not context['mutation_sent'], 'ONE_MUTATION_PER_ORIGINAL_API_NO_REPLAY')
                context['mutation_sent'] = True
            f._private_backend_transport = True; f._image_transport = image
            try:
                return f.android(argv, timeout, mutation=mutation)
            finally:
                f._private_backend_transport = False; f._image_transport = False; self.ui_dispatch_admission = None

    def ui_readiness(self, argv, options, context):
            self.c.need(context is self.active_api, 'CURRENT_API_READINESS_ONLY')
            raw = self.flow.bridge.command(argv, 8, mutation=False, label='Original backend readiness')
            result = self.c.parse(self.c.regular(self.flow.step /
                ('command-%03d.result.json' % self.flow.bridge.command_index))[0])
            self.c.need(result['returncode'] == 0 and result['host_retirement_proved'] is True
                and result['evidence_complete'] is True and self.c.read_ref(result['stdout']) == raw,
                'ACTUAL_RETIRED_READINESS_RESULT')
            return types.SimpleNamespace(stdout=raw, stderr=self.c.read_ref(result['stderr']), returncode=result['returncode'])

    def validate_snapshot_request(self, request, frame):
            self.c.need(self.trial is not None and request.get('package') == self.active['target_profile']['package']
                and request.get('display') == 0 and request.get('accessibility_mode') == 'none'
                and request.get('window_token') == frame['meta']['scope']['window_token'],
                'ONLY_THIS_CASE_ISSUED_ORIGINAL_WINDOW_SNAPSHOT')

    def finish_ui_api(self, context, api, request, value, first, *, action_attempted):
            try:
                self.c.need(context is self.active_api, 'SAME_ORIGINAL_API_COMPLETION')
                result = value
                if api == 'capture' and value is not None:
                    result = {'meta': value['meta'], 'image': {'mode': value['image'].mode,
                        'width': value['image'].width, 'height': value['image'].height,
                        'pixel_sha256': self.helper.module.image_sha(value['image'])}}
                elif type(value) is dict and 'screenshot_png_base64' in value:
                    data = base64.b64decode(value['screenshot_png_base64'], validate=True)
                    self.c.need(len(data) <= 33554432, 'ORIGINAL_OBSERVATION_PNG_FILE_BOUND')
                    result = dict(value); result.pop('screenshot_png_base64')
                    result['recorded_png'] = self.c.write_new(self.flow.step / 'observation.png', data)
                self.c.write_new(self.flow.step / 'original-api-result.json', {
                    'schema': 'pocket4-final-original-api-result-v1', 'scope': self.flow.scope_ref,
                    'phase_lease': self.phase_ref, 'api': api, 'request': request, 'result': result,
                    'native_return_records': context['native_returns'], 'action_attempted': action_attempted,
                    'original_error': None if first is None else {'type': type(first).__name__, 'message': str(first),
                        'details': getattr(first, 'details', None)},
                    'unchanged_native_return_recorded_before_postcapture': True,
                    'automatic_retry': False, 'whole_app_business_accepted': False})
            except BaseException as error:
                self.flow.bound.hold(error); self.flow.view.target.seal_admission(); raise
            finally:
                self.flow.end_api(context['_previous']); self.active_api = None


class TargetReads:
    def __init__(self,session):self.s=session
    def read_file(self,path,maximum,**options):
        s=self.s;c=s.c;s.guard();s.original_caller(['webview_protection.py'],{'identity','app_identity'})
        c.need(options=={'single_link':True},'ORIGINAL_SINGLE_LINK_ARTIFACT_READ')
        p=s.components['webview_protection.py']
        if path==s.identities[0]['artifacts'][0]['guest_path']:
            expected=s.identities[0]['artifacts'][0];c.need(maximum==16777216,'ORIGINAL_SHELL_APK_READ_BOUND')
        else:
            c.need(path in p.SHARED_LIBRARIES and maximum==131072,'ONLY_ORIGINAL_THREE_SHARED_LIBRARIES')
            size,digest=p.SHARED_LIBRARIES[path];expected={'bytes':size,'sha256':digest}
        raw,record=s.flow.view.target.read_file(path,maximum,**options)
        c.need(len(raw)==expected['bytes'] and c.sha(raw)==expected['sha256'],'ORIGINAL_EXACT_ARTIFACT_BYTES')
        if 'held_file' in expected:c.need(record==expected['held_file'],'CURRENT_SIGNED_SHELL_APK_HELD_IDENTITY')
        s.guard();return raw,record
    def open_root(self,path,flags):
        s=self.s;c=s.c;s.guard()
        caller=s.original_caller(['webview_protection.py'])
        if path=='/product/app/webview/webview.apk':
            c.need(caller['function']=='provider_identity' and flags==os.O_RDONLY|os.O_NOFOLLOW,
                'ONLY_ORIGINAL_FULL_PROVIDER_READ')
        else:
            c.need(path in ('/data/user/0/org.chromium.webview_shell','/data/user_de/0/org.chromium.webview_shell')
                and caller['function']=='identity' and flags==os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,
                'ONLY_ORIGINAL_SHELL_CE_DE_IDENTITY_READS')
        return s.flow.view.target.open_root(path,flags|os.O_CLOEXEC)


class Session(SharedSessionMethods):
    def __init__(self,c,active_ref,active,scopes,phase_ref,action_lock,components,evidence_root,fixture,on_cleanup):
        self.c,self.active_ref,self.active=c,active_ref,active
        self.scopes,self.phase_ref,self.action_lock=list(scopes),phase_ref,action_lock
        self.components=components;self.kind=active['kind'];self.case=self.trial=None
        self.fixture=fixture;self.on_cleanup=on_cleanup;self.home_identity=None
        self.evidence_root=c.private_dir(evidence_root);self.root=Path(active['case_root'])
        self.host=components['app_runtime.py'];self.runtime=components['webview_runtime.py']
        self.plan=components['webview_plan.py'];self.policy_module=components['webview_policy.py']
        self.flow_type=components['webview_flow.py'].make_flow(components['app_flow.py'])
        self.transport_module=components['webview_transport.py'];self.protection_module=components['webview_protection.py']
        _,support=c.support(active['support_manifest'])
        self.baseline=support['business_baseline.py'].BusinessBaseline(active['baseline'],active['qualification'])
        self.epoch_sha256=self.baseline.value['framework_epoch']['sha256']
        init=self.baseline.value['framework_epoch']['binding']['processes']['init']
        self.main_identity={'epoch_sha256':self.epoch_sha256,
            'host_pid':self.baseline.docs['final_baseline']['daemon_status']['host_pid'],
            'init_pid':init['host_pid'],'init_start_ticks':init['start_ticks']}
        self.identities=[c.parse(c.read_ref(active[key])) for key in ('target_identity','helper_identity')]
        self.protection=c.parse(c.read_ref(active['protection_identity']))
        self.protection_provider_expected=self.protection['provider_after']['file_metadata']
        self.phase_name='business';self.phase_value=self.runtime.validate_phase(c,self.host,phase_ref,active_ref,active)
        lease=self.runtime.validate_lease(c,self.host,active['lease'],active['base_plan'],active)
        self.original_started=lease['started_monotonic_ns']/1000000000
        self.source_paths={name:str(Path(module.__file__)) for name,module in components.items()}
        self.trial_source='webview_trial10.py' if self.kind=='webview_business10' else 'webview_trial11.py'
        self.allowed_ui_packages={active['target_profile']['package']}
        self.flow=self.helper=self.provider_handle=None;self.closed=False;self.initializing=True
        self.scope_index=self.native_launches=self.record_sequence=self.api_sequence=0
        self.task_claims=[];self.last_stacks=self.baseline_roots=self.baseline_tasks=None
        self.original_intents=[];self.used_intents=set()
        self.active_api=self.ordinary_admission=self.ui_dispatch_admission=self.ui_owner=None
        self.observations={}
        try:
            self.flow=self.new_flow(0);self.scope_module=self.flow.scope_module
            self.provider_handle=self.protection_module.HeldProvider(c,self.flow.view.target,self.protection_provider_expected)
            self.target=TargetReads(self);self.tx=Evidence(self)
            self.helper=components['webview_ui.py'].OriginalAPIs(self)
            self.initializing=False;self.guard()
        except BaseException as first:
            try:self.close()
            except BaseException as secondary:first.add_note('WEBVIEW_SESSION_CONSTRUCTION_CLOSE:'+str(secondary))
            raise
    @property
    def deadline(self):return self.phase_value['deadline_monotonic_ns']/1000000000
    @property
    def environment(self):return dict(self.flow.view.environment)
    def command_boundary(self,flow):
        if self.provider_handle is not None:self.provider_handle.verify(flow.view.target)
        else:self.c.need(self.initializing,'PROVIDER_AUTHORITY_REQUIRED_AT_COMMAND_BOUNDARY')
        self.fixture.verify_parent_and_server()
    def guard(self,*,action_attempted=False):
        self.c.need(not self.closed and self.flow is not None,'ACTUAL_OPEN_FRESH_WEBVIEW_SESSION')
        self.flow.guard(action_attempted=action_attempted)
        if self.provider_handle is not None:self.provider_handle.verify(self.flow.view.target)
        else:self.c.need(self.initializing,'PROVIDER_HELD_AUTHORITY_REQUIRED_AFTER_CONSTRUCTION')
        self.fixture.verify_parent_and_server()
        self.baseline.guard(action_attempted=action_attempted)
        return copy.deepcopy(self.main_identity)
    def note_original_record(self,ref,value):
        self.record_sequence+=1
        if value.get('automatic_retry') is False and (type(value.get('argv')) is list or type(value.get('request')) is dict):
            caller=self.original_caller([self.trial_source],skip_trial_record=True)
            self.original_intents.append({'ref':ref,'value':copy.deepcopy(value),'phase':self.phase_ref,
                'scope':self.flow.scope_ref,'sequence':self.record_sequence,'caller':caller})
        if value.get('ok') is True and type(value.get('screenshot')) is dict and type(value.get('native')) is dict:
            self.observations={'ref':ref,'value':copy.deepcopy(value),'phase':self.phase_ref,'scope':self.flow.scope_ref}
    def bind_trial(self,trial):
        self.c.need(self.trial is None and trial.s is self and trial.fixture is self.fixture,'ONE_ORIGINAL_WEBVIEW_TRIAL')
        self.trial=self.case=trial;self.helper.foreground=self.owned_foreground
    def begin_original_cleanup(self):
        self.c.need(self.phase_name=='business' and self.active_api is None,'ONE_ORIGINAL_WEBVIEW_CLEANUP_TRANSITION')
        self.on_cleanup()
        trigger=self.c.write_new(self.root/'cleanup-trigger.json',{'original_trial_state':None if self.trial is None else self.trial.result['state'],
            'pending_effects':[] if self.trial is None else sorted(self.trial.pending),'automatic_retry':False})
        return self.begin_cleanup(trigger)
    def verify_prelaunch_tasks(self,roots,tasks):
        c=self.c
        c.need(self.phase_name=='business' and self.home_identity is not None and tasks==self.baseline_tasks
            and roots==self.baseline_roots and sorted(tasks)==self.home_identity['tasks']
            and 1<=self.native_launches<=2,'ONLY_SAME_FRESH_HOME_BEFORE_EACH_LAUNCH')
    def run_host(self,label,argv,timeout=20,pass_fds=()):
        c=self.c;t=self.trial;number=self.native_launches+1
        expected=c.NATIVE_PREFIX+['launch',self.active['target_profile']['package'],'--component',
            self.active['target_profile']['component'],'--json']
        c.need(not pass_fds and self.active_api is None and argv==expected and timeout==45
            and self.phase_name=='business' and number in (1,2) and label=='webview-launch-'+str(number)
            and t is not None and t.launches==number and t.pending=={'launch-'+str(number)},
            'EXACT_ORIGINAL_ONCE_WEBVIEW_NATIVE_LAUNCH')
        item=self.consume_original_intent('launch',argv)
        c.need(item['caller']=={'source':self.trial_source,'function':'launch'},'ORIGINAL_WEBVIEW_LAUNCH_CALLER')
        if self.native_launches:
            old=self.flow;claim=old.selected_task()
            c.need(old.policy.remove_sent and self.last_stacks is not None and t.owned is None
                and claim['task'] not in self.last_stacks[0] and claim['task'] not in self.last_stacks[1]
                and self.last_stacks[1]==self.baseline_tasks and self.last_stacks[0]==self.baseline_roots,
                'FIRST_TASK_ACTUALLY_ABSENT_BEFORE_DISTINCT_SECOND_SCOPE')
            old.close();self.scope_index=1;self.flow=self.new_flow(1)
        self.native_launches=number;return self.flow.native_launch()
    def caller_status(self,label):
        self.c.need(self.phase_name=='final_cleanup' and label in ('webview10-final-caller','webview11-final-caller'),
            'ONLY_ORIGINAL_FINAL_WEBVIEW_CALLER_STATUS')
        raw=self.flow.bridge.command(self.c.NATIVE_PREFIX+['status','--json'],10,mutation=False,label='Original final caller status')
        value=self.c.parse(raw)
        self.c.need(value.get('ok') is True and value.get('state')=='running'
            and value.get('host_pid')==self.main_identity['host_pid'] and 'cell u1000 ' in value.get('message',''),
            'SAME_FRESH_MAIN_AND_ORIGINAL_USER_STATUS')
        return value
    def owned_foreground(self):
        t=self.trial;c=self.c;c.need(t is not None and t.owned is not None,'OWNED_WEBVIEW_FOREGROUND_ONLY')
        t.owned_check('typed-api-owned-focus');value=t.focus()
        c.need(value.get('verified') is True and value.get('package')==self.active['target_profile']['package']
            and value.get('task')==t.owned[0] and value.get('user')==0,'ACTUAL_NATIVE_OWNED_WEBVIEW_FOCUS')
        activity=value['activity'];activity=value['package']+activity if activity.startswith('.') else activity
        focused=value['focused_activity'];focused=value['package']+focused if focused.startswith('.') else focused
        c.need(activity==focused=='org.chromium.webview_shell.WebViewBrowserActivity','ORIGINAL_EXACT_WEBVIEW_ACTIVITY')
        return {'package':value['package'],'activity':activity,'window_token':value['window_token']}
    def verify_original_callback(self,kind,callback,previous):
        c=self.c;fn=getattr(callback,'__func__',callback)
        c.need(hasattr(fn,'__code__'),'FROZEN_WEBVIEW_CALLBACK_SOURCE')
        if kind=='foreground':
            c.need(getattr(callback,'__self__',None) is self and fn.__code__.co_filename==__file__
                and fn.__code__.co_name=='owned_foreground' and self.ui_owner is None,
                'ONE_TYPED_WEBVIEW_OWNED_FOREGROUND_CALLBACK')
            self.ui_owner=self.trial;return
        c.need(kind=='native_observer' and fn.__code__.co_filename==self.source_paths[self.trial_source]
            and fn.__code__.co_name=='record_native' and not self.helper.ui_stack,
            'ORIGINAL_SINGLE_WEBVIEW_NATIVE_ACK_OBSERVER')
        values={k:cell.cell_contents for k,cell in zip(fn.__code__.co_freevars,fn.__closure__ or ())}
        c.need(any(v is previous for v in values.values()) and values.get('self') is self.trial,
            'ORIGINAL_ACK_OBSERVER_CALLS_UNCHANGED_NATIVE_BOUNDARY')
    def validate_ui_foreground(self,value,context):
        c=self.c;c.need(type(value) is dict and set(value)=={'package','activity','window_token'}
            and value['package']=='org.chromium.webview_shell'
            and value['activity']=='org.chromium.webview_shell.WebViewBrowserActivity'
            and re.fullmatch('[0-9a-f]{1,32}',value['window_token']) and self.trial is self.ui_owner
            and self.trial.owned is not None and self.trial.owned[0]==context['owned_task'],
            'CURRENT_EXACT_OWNED_WEBVIEW_ACTIVITY_AND_TASK')
        if not context.get('mutation_sent'):
            c.need(value['window_token']==context['request']['window_token']
                and (context.get('observed_focus') is None or value==context['observed_focus']),
                'WEBVIEW_WINDOW_DRIFT_BEFORE_ACTUAL_NATIVE_INPUT')
        context['last_foreground']=copy.deepcopy(value)
    def begin_ui_api(self,api,request):
        c=self.c;t=self.trial
        c.need(api=='dispatch' and t is not None and self.active_api is None and self.ui_owner is t,
            'ONLY_ORIGINAL_WEBVIEW_DISPATCH_TOPOLOGY')
        caller=self.original_caller([self.trial_source],{'observe','mutate','button'})
        c.need(request.get('package')=='org.chromium.webview_shell' and request.get('display')==0
            and request.get('accessibility_mode')=='none' and type(request.get('window_token')) is str,
            'EXPLICIT_ORIGINAL_WEBVIEW_PACKAGE_WINDOW_DISPLAY')
        op=request.get('op');mutates=op in ('click','set-text','snapshot-tap');intent=None
        if op=='observe':
            c.need(caller['function']=='observe' and request=={'op':'observe','package':request['package'],
                'window_token':request['window_token'],'display':0,'accessibility_mode':'none','with_png':True},
                'ONLY_ORIGINAL_PNG_AND_NATIVE_OBSERVATION')
        else:
            c.need(mutates and self.phase_name=='business' and len(t.pending)==1
                and 1<=t.actions<=self.active['limits']['maximum_UI_actions'], 'ORIGINAL_PENDING_WEBVIEW_ACTION')
            intent=self.consume_original_intent('ui',request);label=next(iter(t.pending))
            c.need(intent['caller']==caller,'ACTION_INTENT_FROM_CURRENT_ORIGINAL_METHOD')
            if op in ('click','set-text'):
                fields={'op','package','display','window_token','accessibility_mode','selector'}|({'value'} if op=='set-text' else {'method'})
                c.need(set(request)==fields and caller['function']=='mutate','ORIGINAL_WEBVIEW_SEMANTIC_MUTATION_SHAPE')
                sel=request['selector'];c.need(sel.get('package')==request['package'] and sel.get('enabled') is True,
                    'ORIGINAL_SELECTED_WEBVIEW_NODE')
                if op=='set-text':
                    if label.startswith('url-'):
                        name=label[4:];c.need(name in self.fixture.pages and name!='submitted.html'
                            and request['value']==self.fixture.base_url+name and sel.get('id')==request['package']+':id/url_field',
                            'ONLY_CURRENT_OWNED_FIXTURE_URL')
                    else:c.need(label in ('unicode','form-unicode') and request['value']=='Pocket4 中文 café 😀 — r12'
                        and sel.get('id') in (None,'entry') and sel.get('editable') is True,
                        'ONLY_ORIGINAL_FIXED_UNICODE_FORM_VALUE')
                else:
                    c.need(request['method']=='accessibility','ORIGINAL_SEMANTIC_CLICK_METHOD')
                    if label.startswith('go-'):
                        c.need(label[3:] in self.fixture.pages and label[3:]!='submitted.html'
                            and sel.get('class')=='android.widget.ImageButton' and sel.get('desc')=='Load URL',
                            'ONLY_ORIGINAL_OBSERVED_LOAD_URL_CONTROL')
                    else:c.need(self.kind=='webview_media11' and (label,sel.get('id')) in
                        (('form-checkbox','agree'),('pause-video','pause')),'ONLY_ORIGINAL_CHECKBOX_OR_PAUSE')
            else:
                fields={'op','package','display','accessibility_mode','input_source','window_token','frame_sha256','scope_sha256','context_token','coords'}
                c.need(caller['function']=='button' and set(request)==fields and request['input_source']=='touch'
                    and all(type(request[k]) is str and re.fullmatch('[0-9a-f]{64}',request[k]) for k in
                        ('frame_sha256','scope_sha256','context_token')),'ORIGINAL_EXACT_SNAPSHOT_TOUCH_SHAPE')
                ids=({'save-owned-key':'save','next-page':'next','increment':'increment','history-back':'back','remove-owned-key':'cleanup'}
                    if self.kind=='webview_business10' else {'reload-image':'reload','open-form':'next-form','submit-form':'submit',
                        'open-media':'next-media','play-video':'play','resume-video':'resume','open-network':'next-network',
                        'fetch-https':'https','open-404':'next-missing'})
                node=intent['value'].get('observed_node');bounds=node.get('bounds_array') if type(node) is dict else None
                c.need(label in ids and node.get('resource-id')==ids[label] and node.get('enabled') is True
                    and node.get('clickable') is True and node.get('visible') is True and node.get('package')==request['package']
                    and type(bounds) is list and len(bounds)==4 and all(type(x) is int for x in bounds)
                    and bounds[0]<bounds[2] and bounds[1]<bounds[3] and request['coords']==[(bounds[0]+bounds[2])//2,(bounds[1]+bounds[3])//2],
                    'ONLY_ORIGINAL_FRESH_OBSERVED_FIXED_HTML_CONTROL_CENTER')
        self.guard();claim,claim_ref=self.flow.scope_module.load_owned_task(self.flow.bound)
        raw=self.android(c.STACKS,15);roots,tasks=self.flow.tasks.parse_stacks(raw.decode('utf-8','strict'))
        c.need(self.flow.tasks.exact_leaf(roots,claim['task'],self.flow.scope['package'])
            and tasks==set(claim['prelaunch_task_ids'])|{claim['task']} and t.owned[0]==claim['task'],
            'CURRENT_EXACT_ORIGINAL_WEBVIEW_OWNED_SCOPE')
        self.api_sequence+=1
        context={'schema':'pocket4-final-original-api-context-v1','api':api,'request':copy.deepcopy(request),
            'scope':self.flow.scope_ref,'phase_lease':self.phase_ref,'owned_claim':claim_ref,'owned_task':claim['task'],
            'caller':caller,'mutation_sent':False,'api_sequence':self.api_sequence,'native_returns':0,'automatic_retry':False}
        if intent is not None:context['original_intent']=intent['ref']
        focus=self.owned_foreground();self.validate_ui_foreground(focus,context);context['observed_focus']=copy.deepcopy(focus)
        context['_previous']=self.flow.begin_api('api-%04d-dispatch'%self.api_sequence,request,context)
        self.active_api=context;return context
    def close(self):
        first=None
        for obj,label in ((self.helper,'typed_backend'),(self.provider_handle,'held_provider'),(self.flow,'fresh_Main_flow')):
            if obj is not None:
                try:obj.close()
                except BaseException as error:
                    if first is None:first=error
                    else:first.add_note('WEBVIEW_OTHER_CONTEXT_CLOSE:'+label+':'+str(error))
        self.closed=True
        if first is not None:raise first

