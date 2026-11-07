"""Six direct production phase/context wiring controls with explicit IO seams.
The real run/retire bodies, joined-command receipt checks, fixed parsers and
open_context admission closures execute. Synthetic host/Android observations
are confined to this module. No Main, Android, file or process operation occurs.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import types


def need(value,code):
    if not value:
        raise AssertionError(code)


def pin(raw):
    return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def load(raw,name):
    value=types.ModuleType(name)
    value.__file__='<exact-wiring-control-'+name+'>'
    exec(compile(raw,value.__file__,'exec'),value.__dict__)
    return value


def run_controls(sources,manifest_raw):
    manifest=json.loads(manifest_raw)
    need(set(manifest['files'])==set(sources) and
         all(pin(raw)==manifest['files'][name] for name,raw in sources.items()),
         'exact production phase sources')
    f=load(sources['fixture_contract.py'],'contract')
    p=load(sources['fixture_phases.py'],'phases')
    c=load(sources['fixture_context.py'],'context')
    cases=[]
    original_read=p.read_exact_file
    original_context=(c.os,c.Context)
    build_pin={'bytes':123,'sha256':'b'*64}
    build={'build_result':build_pin,'APK':{'bytes':1234,'sha256':'a'*64},
           'signer_sha256':'c'*64}
    scope_installation={'package':f.PACKAGE,'uid':14000,'user':0,
        'owned_install_qualified':True,'Main_epoch':f.MAIN_EPOCH,'build_result':build_pin}
    installed={'package':f.PACKAGE,'uid':14000,'user':0,'version_code':1,
        'artifact':{'path':'/data/app/~~synthetic/'+f.PACKAGE+'-synthetic/base.apk',
                    'file':{'bytes':1234,'device':1,'inode':22,'mode':33188,
                            'uid':1000,'gid':1000,'nlink':1,'mtime_ns':1,'ctime_ns':1},
                    'sha256':'a'*64},
        'directories':{k:{'path':'/data/'+k+'/0/'+f.PACKAGE,'uid':14000,'gid':14000,
                           'mode':16832,'device':1,'inode':31+i}
                       for i,k in enumerate(('user','user_de'))},
        'signer_sha256_from_identical_build_APK':'c'*64,'signer_independently_read_on_device':False}
    scopes={phase:f.scope(phase,digit*32,build_pin,scope_installation)
            for phase,digit in (('run','2'),('retire','3'))}
    source_view=types.SimpleNamespace(pin=pin(manifest_raw))
    main={'explicit_synthetic_Main_observation':True}
    metadata=('package:'+f.PACKAGE+' versionCode:1 uid:14000\n').encode()
    package_path=('package:'+installed['artifact']['path']+'\n').encode()
    empty_ps=b'UID PID NAME\n1000 123 unrelated-private-process\n'
    stacks=b'explicit synthetic empty task table\n'
    success=('\n'.join([
        'INSTRUMENTATION_STATUS: class='+f.PACKAGE+'.NdkTests',
        'INSTRUMENTATION_STATUS: test=testMain','INSTRUMENTATION_STATUS_CODE: 1',
        'INSTRUMENTATION_STATUS: class='+f.PACKAGE+'.NdkTests',
        'INSTRUMENTATION_STATUS: test=testMain','INSTRUMENTATION_STATUS_CODE: 0',
        'INSTRUMENTATION_CODE: -1',''])).encode()
    case_state={'files':{},'contexts':[],'admissions':[],'xml_calls':0}
    good_run=None

    def case(name,callback):
        callback()
        cases.append({'name':name,'passed':True})

    def reject(callback,code):
        try:
            callback()
        except RuntimeError as error:
            need(str(error)==code,('wrong runtime gate',str(error),code))
        else:
            raise AssertionError('unexpected runtime gate success')

    def read(path,limit,pin=None,expected_identity=None):
        need(pin is None and expected_identity is None,'unexpected synthetic read authority')
        value=case_state['files'].get(str(path))
        need(type(value) is bytes and len(value)<=limit,'only synthetic command receipt reads')
        return value

    class Admission:
        def __init__(self,phase):
            self.phase=phase
            self.entered=False
            self.calls=[]
            case_state['admissions'].append(self)
        def enter_phase_once(self,sources,fixture,scope,step,deadline):
            need(not self.entered and fixture is f and sources is source_view and
                 scope['phase']==self.phase and scope['uid']==14000,
                 'explicit synthetic phase admission')
            self.entered=True
            self.calls.append(('enter',scope['phase']))
        def verify_phase(self,sources,fixture,scope,step,deadline):
            need(self.entered and scope['phase']==self.phase,
                 'same explicit phase admission at context')
            self.calls.append(('verify',scope['phase']))

    class Context:
        def __init__(self,phase,scope,step,plan,admission,instrumentation):
            self.phase,self.scope,self.step,self.plan=phase,scope,step,plan
            self.admission,self.instrumentation=admission,instrumentation
            self.fixture=f
            self.protected_uids={10117,10155}
            self.command_index=self.next_command=0
            self.action_attempted=False
            self.closed=False
            self.guard_calls=0
            self.artifacts=None
            self.recorder=types.SimpleNamespace(task_functions=lambda path:
                types.SimpleNamespace(parse_stacks=lambda text:({},{})))
            self.contract=types.SimpleNamespace(root=Path('/synthetic-r6-source'))
            case_state['contexts'].append(self)
        def android(self,argv,timeout,*,mutation):
            expected=self.plan[self.next_command]
            need((list(argv),timeout,mutation)==expected,'actual ordered phase calls differ')
            self.next_command+=1
            self.command_index+=1
            self.action_attempted=self.action_attempted or mutation
            outputs=([metadata,package_path,empty_ps,stacks,self.instrumentation]
                     if self.phase=='run' else
                     [metadata,package_path,b'',empty_ps,empty_ps,stacks,package_path,metadata])
            raw=outputs[self.command_index-1]
            stem=str(self.step/('command-%03d'%self.command_index))
            row={'returncode':0,'spawned':True,'owned_command_joined':True,
                 'timed_out':False,'error':None,'errors':[],
                 'stdout_sha256':hashlib.sha256(raw).hexdigest(),
                 'stderr_sha256':hashlib.sha256(b'').hexdigest()}
            case_state['files'][stem+'.result.json']=json.dumps(row).encode()
            case_state['files'][stem+'.stderr']=b''
            return raw
        def guard(self,attempted=False):
            need(not self.closed,'synthetic context remains open until final guard')
            self.guard_calls+=1
        def close(self):
            self.closed=True

    class Artifact:
        def __init__(self,context,metadata,path,build,binding,expected=None):
            need(metadata=={k:installed[k] for k in ('package','uid','user','version_code')} and
                 path==installed['artifact']['path'] and expected==installed,
                 'exact synthetic installed tuple supplied to artifact boundary')
            self.context=context
            self.record=copy.deepcopy(installed)
            self.closed=False
            context.artifacts=self
        def xml_absent(self):
            need(self.context.phase=='run','XML absence only before run')
        def revalidate(self):
            need(not self.closed,'synthetic artifact revalidated while held')
            return copy.deepcopy(self.record)
        def close(self):
            self.closed=True
            self.context.artifacts=None
            return {'held_APK_and_data_FDs_closed':3,'all_tracked_artifact_FDs_closed':True}
        def read_fresh_xml(self,prior,current):
            need(prior.get('instrumentation_verified') is True and
                 prior.get('pre_run_XML_absent') is True and
                 current.get('force_stop_completed') is True and
                 current.get('two_complete_empty_own_UID_tables') is True and
                 current.get('task_set_restored') is True,
                 'real phase must establish retirement prerequisites before XML boundary')
            case_state['xml_calls']+=1
            root=f.ET.Element('testsuites',{'tests':'12','failures':'0','disabled':'0',
                'errors':'0','time':'0.1','timestamp':'2000-01-01T00:00:00','name':'AllTests'})
            suite=f.ET.SubElement(root,'testsuite',{'name':'ProcSelfMaps','tests':'12',
                'failures':'0','disabled':'0','skipped':'0','errors':'0','time':'0.1',
                'timestamp':'2000-01-01T00:00:00'})
            for name in f.FOCUS:
                f.ET.SubElement(suite,'testcase',{'name':name.split('.',1)[1],
                    'file':'synthetic/proc_self_maps_test.cc','line':'1','status':'run',
                    'result':'completed','time':'0.01','timestamp':'2000-01-01T00:00:00',
                    'classname':'ProcSelfMaps'})
            return f.native_xml(f.ET.tostring(root,encoding='utf-8'))

    def context_boundary(instrumentation):
        def open_context(sources,fixture,scope,step,plan,result,deadline,admission=None):
            need(admission is not None,'real phase forwarded the same explicit admission')
            admission.verify_phase(sources,fixture,scope,step,deadline)
            result['Main_before']=dict(main)
            context=Context(scope['phase'],scope,step,plan,admission,instrumentation)
            return context,None,lambda:dict(main)
        return types.SimpleNamespace(open_context=open_context,InstalledFixture=Artifact)

    def invoke(phase,prior=None,instrumentation=success):
        admission=Admission(phase)
        context_module=context_boundary(instrumentation)
        args=(source_view,f,context_module,scopes[phase],build,installed)
        if phase=='run':
            result=p.run_original_once(*args,Path('/synthetic-run-step'),1e30,admission=admission)
        else:
            result=p.retire_once(*args,prior,Path('/synthetic-retire-step'),1e30,admission=admission)
        return result,admission

    def positive_run():
        nonlocal good_run
        good_run,admission=invoke('run')
        need(good_run['ok'] is True and good_run['error'] is None and
             good_run['exact_command_count']==5 and good_run['instrumentation_verified'] is True and
             good_run['pre_run_XML_absent'] is True and good_run['retirement_required'] is True and
             good_run['native_twelve_tests_qualified'] is False and
             good_run['held_binding_released'] is True and
             good_run['current_Main_after_qualified'] is True and
             good_run['all_tracked_artifact_FDs_closed'] is True and
             admission.calls==[('enter','run'),('verify','run')] and
             case_state['contexts'][-1].closed,
             'real run body five commands and closure')

    def positive_retire():
        before=case_state['xml_calls']
        value,admission=invoke('retire',good_run)
        need(value['ok'] is True and value['error'] is None and
             value['exact_command_count']==8 and value['force_stop_completed'] is True and
             value['two_complete_empty_own_UID_tables'] is True and
             value['task_set_restored'] is True and
             value['native_XML']['tests']==12 and
             value['original_NdkTests_testMain_accepted'] is True and
             value['commercial_App_readiness_qualified'] is False and
             value['engine_feature_default_enabled'] is False and
             value['package_uninstalled'] is False and
             admission.calls==[('enter','retire'),('verify','retire')] and
             case_state['xml_calls']==before+1 and
             case_state['contexts'][-1].closed,
             'real independent retirement body and exact XML gate')

    def failed_run_retirement():
        failed,_=invoke('run',instrumentation=success.replace(
            b'STATUS_CODE: 0',b'STATUS_CODE: -2'))
        need(failed['ok'] is False and
             failed['error']['code']=='ONE_ORIGINAL_JAVA_TEST_MUST_COMPLETE_SUCCESSFULLY' and
             failed['instrumentation_verified'] is False and
             failed['retirement_required'] is True and failed['outcome_unknown'] is True and
             failed['held_binding_released'] is True,
             'original failed instrumentation remains failed and requires retirement')
        before=case_state['xml_calls']
        retired,_=invoke('retire',failed)
        need(retired['ok'] is True and retired['force_stop_completed'] is True and
             retired['original_NdkTests_testMain_accepted'] is False and
             'native_XML' not in retired and case_state['xml_calls']==before,
             'retirement of failed run cannot confer test acceptance')

    def wrong_uid():
        bad=copy.deepcopy(scopes['run']);bad['uid']=14001
        admission=Admission('run')
        before=len(case_state['contexts'])
        reject(lambda:p.run_original_once(source_view,f,context_boundary(success),bad,
               build,installed,Path('/synthetic-run-step'),1e30,admission=admission),
               'ACTUAL_INSTALLED_UID_RUN_SCOPE_REQUIRED')
        need(not admission.entered and admission.calls==[] and
             len(case_state['contexts'])==before,'wrong UID denied before admission or context')

    def reused_run_scope():
        bad=copy.deepcopy(good_run)
        bad['scope']['attempt_nonce']=scopes['retire']['attempt_nonce']
        before=len(case_state['contexts'])
        value,admission=invoke('retire',bad)
        need(value['ok'] is False and
             value['error']['code']=='NEW_INDEPENDENT_RETIREMENT_SCOPE_REQUIRED' and
             value['exact_command_count']==0 and admission.calls==[('enter','retire')] and
             len(case_state['contexts'])==before,
             'reused run/retire attempt denied before context or commands')

    def real_context_guards():
        counters={'verify_phase':0,'source_verify':0,'shared_verify':0,
                  'target_verify':0,'Main':0,'writes':0,'open':[],'closed':[]}
        helper=b'explicit synthetic pinned helper'
        proof={'explicit_synthetic_current_Main':True}
        expected={'host_pid':12345,'pid':12345,'starttime':'999'}
        baseline={'schema':'pocket4-main-current-baseline-v2','kind':'current-cell-generation',
            'deployment_performed':False,'framework_exit_cause_resolved':False,
            'whole_app_production_ready':False,'packages':{'protected.synthetic':10117},
            'framework_epoch':{'sha256':f.MAIN_EPOCH,'binding':{'processes':{'init':expected}}},
            'status':{'host_pid':23456}}
        env={'PATH':'/system/bin','BOOTCLASSPATH':'/synthetic.jar',
             'DEX2OATBOOTCLASSPATH':'/synthetic.jar','ANDROID_ROOT':'/system',
             'ANDROID_DATA':'/data','ANDROID_ART_ROOT':'/apex/com.android.art'}
        class NoAmbientOS:
            def open(self,path,flags):
                need(path=='/proc/12345' and flags==(
                    os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC),
                    'only explicit synthetic init proc read')
                counters['open'].append(9001)
                return 9001
            def close(self,fd):
                need(fd==9001 and counters['closed']==[],'synthetic init fd closes once')
                counters['closed'].append(fd)
            def __getattr__(self,name):
                if name in ('O_RDONLY','O_DIRECTORY','O_NOFOLLOW','O_CLOEXEC'):
                    return getattr(os,name)
                raise AssertionError('unexpected ambient OS method '+name)
        class Target:
            def __init__(self,*args):
                self.record={'synthetic_target':True}
                self.closed=False
            def verify(self):
                counters['target_verify']+=1
            def close(self):
                self.closed=True
        def guard_baseline(value,action_attempted=False):
            need(value is baseline and action_attempted is False,'original current guard inputs')
            counters['Main']+=1
            return dict(proof)
        current=types.SimpleNamespace(MAIN_EPOCH=f.MAIN_EPOCH,BASELINE_SHA=f.BASELINE_SHA,
            QUALIFICATION_SHA=f.QUALIFICATION_SHA,current_baseline=lambda:baseline,
            source_modules=lambda:(None,object(),None,None),current_guard=guard_baseline)
        held=types.SimpleNamespace(proc_identity_at=lambda fd,pid,deadline:
            (dict(expected) if fd==9001 and pid==12345 else None),HeldTarget=Target)
        binding=types.SimpleNamespace(same_epoch_identity=lambda actual,expect:actual==expect,
            main_classpaths=lambda *args:(dict(env),{'synthetic_classpath':True}))
        def write_new(path,value):
            need(str(path)=='/synthetic-context-step/held-main-binding.private.json' and
                 value['fixture_scope']==scopes['run'],'only synthetic private binding output')
            counters['writes']+=1
        recorder=types.SimpleNamespace(write_new=write_new)
        class Shared:
            files={'current_baseline_guard.py':{'sha256':c.CURRENT_GUARD_SHA}}
            def verify(self):
                counters['shared_verify']+=1
            def load(self,name,module_name):
                value={'recorder.py':recorder,'references/held_runtime_r5.py':held,
                    'main_binding.py':binding,'current_baseline_guard.py':current,
                    'references/android_app.py':object()}.get(name)
                need(value is not None,'exact synthetic shared module name')
                return value
        shared=Shared()
        source=types.SimpleNamespace(SourceContract=lambda path,pin:shared,
            HELPER_PATH=Path('/synthetic-held-helper'),HELPER_BYTES=len(helper),
            HELPER_SHA=hashlib.sha256(helper).hexdigest(),
            bounded_file=lambda path,limit:helper,
            verify_shared_helper=lambda:{'synthetic_shared_helper':True})
        discovery=types.SimpleNamespace(BASELINE_SHA=f.BASELINE_SHA,
            QUALIFICATION_SHA=f.QUALIFICATION_SHA,MAIN_EPOCH=f.MAIN_EPOCH,
            discover_current=lambda app,b,e,g:(12345,dict(env),{'host_pid':23456}))
        class Sources:
            def verify(self):
                counters['source_verify']+=1
            def fixed_reference(self,path,size,digest):
                need(str(path)==str(c.INSTALLED_SHARED/'source_contract.py') and
                     size==c.CONTRACT_BYTES and digest==c.CONTRACT_SHA,'exact source contract request')
                return b'synthetic source contract IO seam'
            def module(self,raw,path,name):
                need(raw==b'synthetic source contract IO seam','only synthetic contract module')
                return source
            def load(self,name,module_name):
                if name=='current_discovery.py':
                    return discovery
                need(name=='fixture_transport.py','only synthetic environment boundary')
                return types.SimpleNamespace(environment_values=lambda values:dict(values))
        class PhaseAdmission:
            def verify_phase(self,sources,fixture,scope,step,deadline):
                need(fixture is f and scope==scopes['run'] and
                     str(step)=='/synthetic-context-step' and deadline==1e30,
                     'real context must forward exact phase values')
                counters['verify_phase']+=1
        class ContextBoundary:
            def __init__(self,recorder,contract,target,environment,transport,main_guard,
                         step,plan,expected_init,deadline,fixture,scope,protected_uids):
                self.main_guard=main_guard
                self.target=target
                need(expected_init==12345 and scope==scopes['run'] and
                     plan==f.run_plan(scopes['run']) and protected_uids=={10117},
                     'context construction exact phase contract')
        c.os=NoAmbientOS()
        c.Context=ContextBoundary
        result={}
        context=None
        try:
            context,returned_binding,guard=c.open_context(Sources(),f,scopes['run'],
                Path('/synthetic-context-step'),f.run_plan(scopes['run']),result,1e30,
                admission=PhaseAdmission())
            context.main_guard()
            guard()
            need(returned_binding is binding and result['Main_before']==proof and
                 counters['verify_phase']==5 and counters['source_verify']==5 and
                 counters['shared_verify']==4 and counters['Main']==4 and
                 counters['open']==counters['closed']==[9001] and counters['writes']==1,
                 ('real current context admission at entry and each guard',counters))
        finally:
            if context is not None:
                context.target.close()
            c.os,c.Context=original_context

    try:
        p.read_exact_file=read
        case('production_run_forwards_one_admission_and_all_five_commands',positive_run)
        case('production_retirement_requires_independent_scope_and_exact_XML',positive_retire)
        case('failed_testMain_retirement_does_not_upgrade_native_tests',failed_run_retirement)
        case('production_phase_wrong_UID_stops_before_admission_or_context',wrong_uid)
        case('production_retirement_reused_attempt_stops_before_context',reused_run_scope)
        case('production_open_context_verifies_phase_at_entry_and_each_guard',real_context_guards)
    finally:
        p.read_exact_file=original_read
        c.os,c.Context=original_context
    need(len(cases)==6 and len({x['name'] for x in cases})==6 and
         p.read_exact_file is original_read and c.os is original_context[0] and
         c.Context is original_context[1] and
         all(x.closed for x in case_state['contexts']),
         'six real wiring controls and synthetic context closure')
    return {'schema':1,'ok':True,'count':6,'cases':cases,'seams_restored':True,
        'production_phase_bodies_and_joined_receipt_parser_called':True,
        'production_open_context_and_guard_closures_called':True,
        'synthetic_contexts_closed':len(case_state['contexts']),
        'synthetic_IO_only':True,'actual_Main_or_Android':0,'actual_children':0,
        'actual_files_read':0,'actual_files_written':0,
        'actual_run_or_retire_nonce_consumed':False,'runtime_qualified':False}
