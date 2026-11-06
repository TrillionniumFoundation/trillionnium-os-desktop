"""IHG task adapter using pinned shared methods, never the Bili Flow.

This module has no CLI or standalone execution. A separate frozen coordinator
must bind actual resolve/install/source receipts, a new private flow and Main.
Only launch, explicit Search then fresh Destination clicks, independent inspection,
and exact task retirement are described here. No text/media/screenshot opcode.
"""
import json
import math
import os
import re
from pathlib import Path
import subprocess
import stat
import time
import types

PACKAGE='com.ihg.apps.android'
UID=10137
SELF='org.droidloom.qa.ihg.r2'
HELPER_UID=None

CURRENT_HOST_MANIFEST='6d99374e1580083fd0f30b7f9b3c520306680760c97ad0d5400798fda427fb6e'
CURRENT_BASELINE_SCHEMA='pocket4-main-current-baseline-v1'
CURRENT_EPOCH='734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2'
CURRENT_BASELINE_SHA='163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266'
CURRENT_QUALIFICATION_SHA='f37b2eb00db80c398c9a4f9fd895628b6c7ecc827ccf9699c2242fa5ba862ed6'
LIST=['/system/bin/cmd','package','list','packages','-U','--show-versioncode','--user','0',PACKAGE]
PATHS=['/system/bin/cmd','package','path','--user','0',PACKAGE]
OWN_UID=['/system/bin/cmd','package','list','packages','-U','--user','0',SELF]
OWN_PATH=['/system/bin/cmd','package','path','--user','0',SELF]
STACKS=['/system/bin/cmd','activity','stack','list']
FOREGROUND=['/system/bin/dumpsys','window','displays']


def need(value,reason):
    if not value:
        raise RuntimeError(reason)


class Policy:
    """Per-phase explicit command authority, separate from transport success."""
    def __init__(self,phase,qa,resolve,inspect_plan,step,read,selected_task):
        need(phase in ('launch','inspect','cleanup'),'EXACT_AMAZON_PHASE_REQUIRED')
        need(qa.PACKAGE==PACKAGE and qa.UID==UID and qa.SELF==SELF,'EXACT_AMAZON_CONTRACT_REQUIRED')
        need(set(inspect_plan)=={'search','destination','post','readiness'} and
             all(inspect_plan[role]['operation']=='click' and
                 set(inspect_plan[role]['nonces'])=={'before','inspect','action','after'}
                 for role in ('search','destination')) and
             inspect_plan['post']['operation']=='inspect' and set(inspect_plan['post']['nonces'])=={'before','inspect','after'} and
             isinstance(inspect_plan['readiness'],list) and len(inspect_plan['readiness'])==8 and
             all(plan['operation']=='inspect' and set(plan['nonces'])=={'before','inspect','after'}
                 for plan in inspect_plan['readiness']),
             'EXPLICIT_SEARCH_DESTINATION_POST_AND_EIGHT_NO_ACTION_READINESS_PLANS')
        flat={role:inspect_plan[role] for role in ('search','destination','post')}
        flat.update({'readiness_'+str(index+1):plan for index,plan in enumerate(inspect_plan['readiness'])})
        values=[n for plan in flat.values() for n in plan['nonces'].values()]
        need(len(values)==len(set(values))==35,'THIRTY_FIVE_DISTINCT_CURRENT_HELPER_NONCES')
        self.phase,self.qa,self.resolve,self.plan=phase,qa,list(resolve),flat
        self.step,self.read,self.selected_task=step,read,selected_task
        self.counts={};self.used_nonces=set();self.remove_attempted=False

    def claim(self,name,limit):
        count=self.counts.get(name,0)
        need(count<limit,'AMAZON_PHASE_COMMAND_LIMIT:'+name)
        self.counts[name]=count+1

    def admit(self,argv,timeout,mutation,private):
        need(isinstance(argv,list) and all(isinstance(x,str) for x in argv) and type(mutation) is bool and
             type(private) is bool and isinstance(timeout,(int,float)) and not isinstance(timeout,bool) and
             math.isfinite(timeout) and 0<timeout<=70,'EXACT_COMMAND_SHAPE_REQUIRED')
        if argv in (LIST,PATHS):
            need(timeout==15 and not mutation and not private,'TARGET_METADATA_READ_ONLY')
            self.claim('target_uid' if argv==LIST else 'target_path',2)
            return
        if argv in (OWN_UID,OWN_PATH):
            need(timeout==8 and not mutation and not private,'HELPER_METADATA_READ_ONLY')
            # Up to eight read-only sequences plus three original sequences and outer pair.
            self.claim('helper_uid' if argv==OWN_UID else 'helper_path',24 if self.phase=='inspect' else 2)
            return
        if argv==self.resolve:
            need(self.phase=='launch' and timeout==15 and not mutation and not private,
                 'CURRENT_COMPONENT_READ_ONLY_BEFORE_LAUNCH')
            self.claim('resolve',1);return
        if argv==STACKS:
            need(not mutation and not private and timeout<=20,'TASK_SNAPSHOT_READ_ONLY')
            self.claim('stacks',33 if self.phase=='cleanup' else 22 if self.phase=='inspect' else 2);return
        if argv==FOREGROUND:
            need(self.phase=='inspect' and timeout==15 and not mutation and private,
                 'ONLY_PRIVATE_CURRENT_FOREGROUND_READ')
            self.claim('foreground',33);return
        if self.phase=='cleanup' and argv[:4]==['/system/bin/cmd','activity','stack','remove']:
            # Full equality below, not a prefix-based permission grant.
            selected=self.selected_task()
            need(len(argv)==5 and argv==['/system/bin/cmd','activity','stack','remove',str(selected['task'])] and
                 selected['package']==PACKAGE and selected['prelaunch_absent'] is True and
                 selected['cleanup_allowed'] is True and timeout==20 and mutation and not private,
                 'ONLY_EXACT_NEW_OWNED_LEAF_REMOVAL')
            need(not self.remove_attempted,'REMOVAL_CANNOT_BE_REPLAYED')
            self.remove_attempted=True;return
        need(self.phase=='inspect' and timeout==20 and not private,
             'NO_OTHER_IHG_COMMAND_ADMITTED')
        matches=[]
        for plan in self.plan.values():
            for phase,nonce in plan['nonces'].items():
                if nonce in self.used_nonces:continue
                path=self.step/(nonce+'.request.json')
                try:raw=self.read(path,65536)
                except FileNotFoundError:continue
                request=json.loads(raw)
                operation='click' if phase=='action' else 'inspect' if phase=='inspect' else 'state'
                need(request.get('nonce')==nonce and request.get('op')==operation,
                     'FIXED_CURRENT_PHASE_REQUEST_REQUIRED')
                self.qa.validate_request(request)
                if self.qa.instrumentation_argv(request)==argv:
                    need(mutation is (operation=='click'),'EXACT_CURRENT_OPERATION_MUTATION_FLAG')
                    matches.append((nonce,operation))
        need(len(matches)==1,'ONLY_ONE_CURRENT_SOURCE_BOUND_HELPER_REQUEST')
        nonce,operation=matches[0]
        self.used_nonces.add(nonce);self.claim('instrument',35)
        if operation=='click':self.claim('click',2)



def current_task_scope(scope,qa,contract):
    fields={'schema','current_baseline_schema','package','component','uid','user','nonce',
        'epoch_sha256','current_baseline_sha256','current_baseline_qualification_sha256',
        'amazon_task_source_manifest_sha256','automatic_retry',
        'original_recorder_manifest_sha256','actual_resolution_result_sha256'}
    need(type(scope) is dict and set(scope)==fields and
         scope['schema']=='pocket4-current-recorder-scope-v1' and
         scope['current_baseline_schema']==CURRENT_BASELINE_SCHEMA==qa.MAIN_BASELINE_SCHEMA and
         scope['epoch_sha256']==CURRENT_EPOCH==qa.MAIN_EPOCH and
         scope['current_baseline_sha256']==CURRENT_BASELINE_SHA==qa.MAIN_BASELINE_SHA and
         scope['current_baseline_qualification_sha256']==CURRENT_QUALIFICATION_SHA==qa.MAIN_BASELINE_QUALIFICATION_SHA and
         scope['package']==PACKAGE==qa.PACKAGE and type(scope['uid']) is int and scope['uid']==UID==qa.UID and
         type(scope['user']) is int and scope['user']==0 and
         scope['original_recorder_manifest_sha256']==CURRENT_HOST_MANIFEST==contract.sha256 and
         scope['automatic_retry'] is False,'EXACT_TYPED_CURRENT_IHG_TASK_SCOPE')
    need(isinstance(scope['component'],str) and
         re.fullmatch(re.escape(PACKAGE)+r'/[A-Za-z0-9_.$]+',scope['component']) and
         isinstance(scope['nonce'],str) and re.fullmatch('[0-9a-f]{32}',scope['nonce']) and
         all(isinstance(scope[key],str) and re.fullmatch('[0-9a-f]{64}',scope[key])
             for key in ('amazon_task_source_manifest_sha256','actual_resolution_result_sha256')),
         'EXACT_CURRENT_TASK_SOURCE_NONCE_AND_COMPONENT')
    return scope


class Flow:
    """Amazon-only object satisfying the actual original Session interface."""
    def __init__(self,*,recorder,contract,target,environment,transport,main_guard,root,step,
                 phase,scope,activation,tasks,qa,inspect_plan,resolve,read,deadline):
        current_task_scope(scope,qa,contract)
        need(scope['epoch_sha256']==transport.FRAMEWORK_EPOCH_SHA256,'EXACT_CURRENT_TRANSPORT_EPOCH_REQUIRED')
        need(root.is_dir() and step.is_relative_to(root),'NEW_PRIVATE_FLOW_REQUIRED')
        self.recorder,self.contract,self.target=recorder,contract,target
        self.main_guard,self.root,self.step=main_guard,root,step
        self.phase,self.scope,self.activation,self.tasks=phase,scope,activation,tasks
        self.current_qualified_scope=dict(scope);self.qa=qa
        self.deadline=deadline;self.command_index=0;self.action_attempted=False
        self._private_backend_transport=False;self._android_mutation=False
        self.binding=types.SimpleNamespace(target=target)
        self.artifacts=None;self.closed=False;self.poisoned=False;self.launch_claimed=False
        self.policy=Policy(phase,qa,resolve,inspect_plan,step,read,self.selected_task)

        def record(kind,value):
            recorder.write_new(step/('transport-%03d.%s.json'%(value['sequence'],kind)),value)
        def runner(argv,**options):
            need(options['close_fds'] is True and options['stdout']==subprocess.PIPE and
                 options['stderr']==subprocess.PIPE,'EXACT_HELD_RUNNER_PROTOCOL_REQUIRED')
            if self._private_backend_transport:
                # Same privacy branch as the frozen recorder: foreground text
                # is parsed in memory; its transport hash/rc remains recorded.
                return subprocess.run(argv,**options)
            return recorder.Flow.command(self,argv,options['timeout'],mutation=self._android_mutation,
                label='Android command',pass_fds=options['pass_fds'],check=False,host_env=options['env'])
        self.transport=transport.BoundArun(target=target,environment=environment,guard=lambda action_attempted:self.guard(attempted=action_attempted),
            record=record,epoch_sha256=transport.FRAMEWORK_EPOCH_SHA256,
            init_pid=activation['framework_epoch']['binding']['processes']['init']['host_pid'],
            package=PACKAGE,uid=UID,interactive_production=True,runner=runner)

    def guard(self,attempted=False):
        current_task_scope(self.scope,self.qa,self.contract)
        need(self.scope==self.current_qualified_scope,'CURRENT_IHG_TASK_SCOPE_CHANGED')
        need(not self.closed and time.monotonic()<self.deadline,'OPEN_BOUNDED_AMAZON_FLOW_REQUIRED')
        self.main_guard();self.target.verify()
        if self.artifacts is not None:self.artifacts.verify_held()

    def bind(self):
        self.guard();return self.binding

    def android(self,argv,timeout=20,*,mutation=False):
        try:
            need(not self.poisoned and not self.closed,'POISONED_AMAZON_COMMAND_NOT_REPLAYABLE')
            self.policy.admit(argv,timeout,mutation,self._private_backend_transport)
            self._android_mutation=mutation
            return self.transport(argv,timeout)
        except BaseException:
            self.poisoned=True
            raise
        finally:
            self._android_mutation=False

    def command(self,argv,timeout,*,mutation=False,label=None):
        expected=['/usr/bin/sudo','-n','-u','#1000','--','/usr/bin/env',
            'XDG_RUNTIME_DIR=/run/user/1000','DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus',
            '/usr/bin/droidloomctl','launch',PACKAGE,'--component',self.scope['component'],'--json']
        need(self.phase=='launch' and argv==expected and timeout==70 and mutation is True and
             label=='One native launch' and not self.launch_claimed and not self.poisoned,
             'ONLY_ONE_EXACT_ORIGINAL_NATIVE_LAUNCH')
        self.launch_claimed=True
        try:return self.recorder.Flow.command(self,argv,timeout,mutation=True,label=label)
        except BaseException:
            self.poisoned=True
            raise

    def stacks(self,timeout=20):
        value=self.recorder.Flow.stacks(self,timeout)
        self.last_stack_task_ids=sorted(value[2])
        return value

    def selected_task(self):
        value=self.recorder.Flow.selected_task(self)
        need(set(value)=={'task','package','epoch_sha256','prelaunch_absent','cleanup_allowed',
             'launch_step','prelaunch_task_ids','native_receipt_sha256'} and
             value['package']==PACKAGE and value['prelaunch_absent'] is True and
             value['cleanup_allowed'] is True and value['launch_step']=='launch-01' and
             type(value['task']) is int and value['task']>0 and
             isinstance(value['prelaunch_task_ids'],list) and
             all(type(x) is int and x>=0 for x in value['prelaunch_task_ids']) and
             value['task'] not in value['prelaunch_task_ids'] and
             isinstance(value['native_receipt_sha256'],str) and
             len(value['native_receipt_sha256'])==64 and
             set(value['native_receipt_sha256'])<=set('0123456789abcdef'),
             'NEW_AMAZON_TASK_PROOF_REQUIRED')
        return value

    def launch_locked(self):
        need(self.phase=='launch','LAUNCH_PHASE_REQUIRED')
        return self.recorder.Flow.launch_locked(self)

    def cleanup(self):
        need(self.phase=='cleanup','CLEANUP_PHASE_REQUIRED')
        return self.recorder.Flow.cleanup(self)

    def close(self):
        self.closed=True
        self.target.close()


def open_task_context(ref,util,context,source_manifest,source_verify,flow_root,step,
                      transport,result,deadline,phase,qa,inspect_plan,resolve,expected_scope):
    """Same held Main/classpath primitives as the qualified Amazon install.

    The only newly constructed object is the phase-restricted task Flow above.
    No original Bili Flow/MainBinding or old UI client constructor is called.
    """
    source=util.module(context.INSTALLED_SHARED/'source_contract.py',context.CONTRACT_SHA,
                       'amazon_task_shared_contract')
    contract=source.SourceContract(context.INSTALLED_SHARED/'source-manifest.json',context.SHARED_MANIFEST)
    recorder=contract.load('recorder.py','amazon_task_actual_command')
    held=contract.load('references/held_runtime_r5.py','amazon_task_actual_held_main')
    binding=contract.load('main_binding.py','amazon_task_shared_classpath_only')
    activation=ref.current_baseline()
    own_scope=context.baseline_scope(ref,activation)
    epoch=ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),ref.EPOCH_SOURCE,
                     'amazon_task_fixed_epoch')
    scope_raw=util.read(flow_root/'scope.json',65536)
    scope=json.loads(scope_raw)
    current_task_scope(scope,qa,contract)
    need(scope==expected_scope and all(scope[key]==value for key,value in own_scope.items()),
         'EXACT_NEW_CURRENT_IHG_FLOW_SCOPE_REQUIRED')
    need(util.read(flow_root/'baseline.json',expected=ref.BASELINE_SHA)==ref.read(ref.BASELINE,expected=ref.BASELINE_SHA)
         and util.read(flow_root/'baseline-qualification.json',expected=ref.QUALIFICATION_SHA)==ref.read(ref.QUALIFICATION,expected=ref.QUALIFICATION_SHA),
         'SAVED_TYPED_CURRENT_BASELINE_CHANGED')
    info=flow_root.lstat()
    need(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and not info.st_mode&0o077,
         'PRIVATE_ROOT_OWNED_NEW_FLOW_REQUIRED')
    target=None
    def guard():
        need(time.monotonic()<deadline,'AMAZON_PHASE_DEADLINE')
        source_verify(source_manifest);contract.verify()
        need(util.read(flow_root/'scope.json',65536)==scope_raw,'AMAZON_SCOPE_CHANGED')
        ref.read(recorder.APP,expected=recorder.APP_SHA)
        util.read(source.HELPER_PATH,source.HELPER_BYTES,source.HELPER_SHA,source.HELPER_BYTES)
        observation=ref.main_guard(activation,epoch)
        if target is not None:context.verify_target_data(target,activation,binding)
        return observation
    result['Main_before']=guard();result['shared_helper']=source.verify_shared_helper()
    expected=activation['framework_epoch']['binding']['processes']['init']
    proc=os.open('/proc/'+str(expected['host_pid']),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:actual=held.proc_identity_at(proc,expected['host_pid'],time.monotonic()+3)
    finally:os.close(proc)
    need(binding.same_epoch_identity(actual,expected),'FIXED_MAIN_INIT_IDENTITY_CHANGED')
    try:
        target=held.HeldTarget(actual,source.HELPER_PATH,source.HELPER_SHA);guard()
        app=util.module(Path(recorder.APP),recorder.APP_SHA,'amazon_task_discovery_only')
        init,discovered,status=app.discover()
        need(init==expected['host_pid'] and status['host_pid']==activation['status']['host_pid'],
             'FIXED_MAIN_DISCOVERY_CHANGED')
        values,classpath=binding.main_classpaths(held,target,activation['framework_epoch'],epoch,guard)
        need(all(discovered.get(k)==v for k,v in values.items()),'CLASSPATH_DISCOVERY_CHANGED')
        environment=transport.environment_values(discovered)
        tasks=recorder.task_functions(context.INSTALLED_SHARED/'references/task_scope_baseline.py')
        flow=Flow(recorder=recorder,contract=contract,target=target,environment=environment,
            transport=transport,main_guard=guard,root=flow_root,step=step,phase=phase,
            scope=scope,activation=activation,tasks=tasks,qa=qa,inspect_plan=inspect_plan,
            resolve=resolve,read=util.read,deadline=deadline)
        ref.write_new(step/'held-main-binding.json',{'target':target.record,'classpath':classpath,
            'shared_helper':result['shared_helper'],'target_package':PACKAGE,'target_uid':UID,
            'shared_recorder_primitive_manifest':context.SHARED_MANIFEST,
            'amazon_task_runtime_source_manifest':source_manifest,'Bili_Flow_instantiated':False})
        return flow,recorder,lambda:ref.main_guard(activation,epoch)
    except BaseException as primary:
        if target is not None:
            try:target.close()
            except BaseException as secondary:primary.add_note('held target close: '+repr(secondary))
        raise
