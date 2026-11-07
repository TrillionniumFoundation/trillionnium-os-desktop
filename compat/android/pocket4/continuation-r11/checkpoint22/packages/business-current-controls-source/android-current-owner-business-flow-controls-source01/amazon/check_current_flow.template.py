"""Current Amazon R4 exact attribution, plan, install, and typed constructor controls.

Every fixture is in memory. No original private UI tree, Main, file, child, or
Android entry is called. Historical failure/unknown receipts remain unchanged.
"""
import ast
import copy
import hashlib
import json
from pathlib import PurePosixPath
import types
NAME='retain_navigation_failure_observations'

def module(source,name):
    tree=ast.parse(source)
    tree.body=[n for n in tree.body if not(isinstance(n,ast.Assign) and
        any(isinstance(t,ast.Name) and t.id=='HERE' for t in n.targets))]
    value=types.ModuleType(name);value.__file__='/pure-control/'+name+'.py'
    value.HERE=PurePosixPath('/pure-control')
    exec(compile(tree,'<pure-module-'+name+'>','exec'),value.__dict__)
    return value

def one(nodes, kind, name=None):
    rows=[n for n in nodes if isinstance(n,kind) and (name is None or n.name==name)]
    assert len(rows)==1
    return rows[0]


def handler(module):
    worker=one(module.body,ast.FunctionDef,'worker')
    block=one([n for n in worker.body if isinstance(n,ast.Try) and n.finalbody],ast.Try)
    assert len(block.handlers)==1
    return block.handlers[0]


def execute_handler(module, seed, last, phase='inspect'):
    result=copy.deepcopy(seed)
    primary=RuntimeError('retained primary')
    calls=[]
    def remember(value,current,error):
        assert value is result and current=='original_phase' and error is primary
        calls.append(True)
    scope={'result':result,'phase':phase,'session':types.SimpleNamespace(sequence_observation=last),
           'u':types.SimpleNamespace(remember=remember),'current':'original_phase','error':primary}
    definitions=[copy.deepcopy(n) for n in module.body if isinstance(n,ast.FunctionDef) and n.name==NAME]
    source=ast.fix_missing_locations(ast.Module(body=definitions+copy.deepcopy(handler(module).body),type_ignores=[]))
    exec(compile(source,'<attribution-handler-only>','exec'),scope)
    assert calls==[True] and result.get('error')==seed.get('error')
    assert result.get('search_entry')==seed.get('search_entry')
    return result



def run_task_discovery_route_controls(task_module, coordinator, qa):
    """Execute production open_task_context with explicit in-memory I/O seams.

    The already actual-tested installed discovery API is an observed boundary.
    These cases test forwarding, no legacy bypass, and original close-on-error;
    they do not claim real /proc, held-FD, baseline, or Android qualification.
    """
    import ast
    import copy
    import json
    import stat
    import types
    from pathlib import PurePosixPath
    rows=[]
    def need(value,reason):
        if not value:raise RuntimeError(reason)
    def case(mode):
        calls=[];state={'closed':False,'flow':False,'discover':0,'legacy':0}
        class MemoryPath(type(PurePosixPath('/'))):
            def lstat(self):
                return types.SimpleNamespace(st_mode=stat.S_IFDIR|0o700,st_uid=0)
        root=MemoryPath('/memory-flow');step=root/'steps/inspect'
        source_root=MemoryPath('/memory-install/source')
        host_root=MemoryPath('/memory-host')
        expected='d'*64
        install_pin=coordinator.INSTALL_SOURCE_SHA
        need(isinstance(install_pin,str) and len(install_pin)==64,'FIXED_INSTALL02_SOURCE_REQUIRED')
        baseline={'schema':qa.MAIN_BASELINE_SCHEMA,'kind':'current-cell-generation',
            'deployment_performed':False,'framework_exit_cause_resolved':False,
            'whole_app_production_ready':False,'packages':{qa.PACKAGE:qa.UID},
            'framework_epoch':{'sha256':qa.MAIN_EPOCH,
                'binding':{'processes':{'init':{'host_pid':12001}}}},
            'status':{'host_pid':12000}}
        ref=types.SimpleNamespace(current_baseline=lambda:copy.deepcopy(baseline),
            BASELINE=MemoryPath('/memory-baseline'),BASELINE_SHA=qa.MAIN_BASELINE_SHA,
            QUALIFICATION=MemoryPath('/memory-qualification'),
            QUALIFICATION_SHA=qa.MAIN_BASELINE_QUALIFICATION_SHA,
            EPOCH=qa.MAIN_EPOCH,EPOCH_SOURCE=MemoryPath('/memory-epoch.py'),EPOCH_SOURCE_SHA='e'*64)
        scope=coordinator.scope_record(types.SimpleNamespace(ref=ref,
            adapter=types.SimpleNamespace(RECORDER_MANIFEST_SHA=task_module.CURRENT_HOST_MANIFEST)),expected)
        scope_raw=json.dumps(scope).encode()
        epoch=object()
        def source_verify(value):
            need(value==expected,'TASK_SOURCE_MANIFEST_CHANGED');calls.append('task_source_verify')
        def read(path,maximum=1048576,expected=None,size=None):
            if path==root/'scope.json':return scope_raw
            return b'memory'
        ref.read=read
        ref.module=lambda raw,path,name:epoch
        def main_guard(value,module):
            need(value==baseline and module is epoch,'ORIGINAL_MAIN_CALLBACK_ARGUMENTS')
            calls.append('Main_guard');return {'in_memory':True}
        ref.main_guard=main_guard
        writes=[]
        ref.write_new=lambda path,value:writes.append((path,value))
        class Target:
            def __init__(self,identity,path,digest):
                need(identity==baseline['framework_epoch']['binding']['processes']['init'],
                     'ORIGINAL_HELD_TARGET_IDENTITY')
                self.record={'in_memory_target':True}
            def close(self):state['closed']=True
        held=types.SimpleNamespace(HeldTarget=Target,
            proc_identity_at=lambda fd,pid,deadline:copy.deepcopy(baseline['framework_epoch']['binding']['processes']['init']))
        def classpaths(held_arg,target,observed,module,guard):
            need(held_arg is held and observed==baseline['framework_epoch'] and module is epoch,
                 'ORIGINAL_CLASSPATH_ARGUMENTS')
            guard();return {'BOOTCLASSPATH':'/memory.jar'},{'fixture':True}
        binding=types.SimpleNamespace(same_epoch_identity=lambda a,b:a==b,main_classpaths=classpaths)
        recorder=types.SimpleNamespace(APP='/memory-android-app.py',APP_SHA='a'*64,
            task_functions=lambda path:types.SimpleNamespace())
        loads={'recorder.py':recorder,'references/held_runtime_r5.py':held,'main_binding.py':binding}
        contract=types.SimpleNamespace(sha256=task_module.CURRENT_HOST_MANIFEST,
            verify=lambda:calls.append('contract_verify'),load=lambda name,label:loads[name])
        shared=types.SimpleNamespace(SourceContract=lambda path,digest:contract,
            HELPER_PATH=MemoryPath('/memory-helper'),HELPER_BYTES=6,HELPER_SHA='f'*64,
            verify_shared_helper=lambda:{'whole_process_tree_cleanup_qualified':False})
        def legacy():
            state['legacy']+=1;raise RuntimeError('LEGACY_DISCOVERY_BYPASS')
        app=types.SimpleNamespace(discover=legacy)
        def module(path,digest,label):
            if str(path)==str(host_root/'source_contract.py'):
                need(digest=='b'*64,'EXACT_SHARED_CONTRACT_PIN');return shared
            need(str(path)==recorder.APP and digest==recorder.APP_SHA,
                 'EXACT_LEGACY_REFERENCE_PIN');return app
        def verify_install(value):
            need(value==install_pin,'INSTALL_SOURCE_MANIFEST_CHANGED')
            if mode=='source_changed':raise RuntimeError('EXACT_INSTALL_SOURCE_STOP')
            calls.append('install_source_verify');return {'in_memory_manifest':True}
        util=types.SimpleNamespace(HERE=source_root,module=module,read=read,verify_source=verify_install)
        def current_discovery(util_arg,manifest,verify,where,app_arg,base,epoch_arg,guard):
            need(util_arg is util and manifest==install_pin and verify is verify_install and
                 where==source_root and app_arg is app and base==baseline and epoch_arg is epoch,
                 'EXPLICIT_PINNED_DISCOVERY_ARGUMENTS_REQUIRED')
            verify(manifest)
            state['discover']+=1
            guard()
            status={'host_pid':12000}
            return (12002 if mode=='wrong_init' else 12001),{'BOOTCLASSPATH':'/memory.jar'},status
        context=types.SimpleNamespace(INSTALLED_SHARED=host_root,CONTRACT_SHA='b'*64,
            SHARED_MANIFEST=task_module.CURRENT_HOST_MANIFEST,
            baseline_scope=lambda ref_arg,base:{'package':qa.PACKAGE,'uid':qa.UID},
            current_discovery=current_discovery,
            verify_target_data=lambda target,base,binding_arg:need(
                base==baseline and binding_arg is binding,'ORIGINAL_TARGET_DATA_GUARD'))
        transport=types.SimpleNamespace(environment_values=lambda value:copy.deepcopy(value))
        def flow_factory(**values):
            need(values['recorder'] is recorder and values['contract'] is contract and
                 values['transport'] is transport and values['qa'] is qa and
                 values['scope']==scope and values['activation']==baseline,
                 'UNCHANGED_FLOW_CONSTRUCTOR_ARGUMENTS')
            state['flow']=True
            return types.SimpleNamespace(**values)
        namespace=dict(task_module.open_task_context.__globals__)
        namespace['Path']=MemoryPath
        namespace['time']=types.SimpleNamespace(monotonic=lambda:1.0)
        namespace['os']=types.SimpleNamespace(O_RDONLY=0,O_DIRECTORY=1,O_NOFOLLOW=2,O_CLOEXEC=4,
            open=lambda path,flags:(need(path=='/proc/12001','EXACT_PROTECTED_INIT_PROC') or 10),
            close=lambda fd:need(fd==10,'ONLY_MEMORY_PROC_FD'))
        namespace['Flow']=flow_factory
        gate=types.FunctionType(task_module.open_task_context.__code__,namespace)
        result={}
        def run():
            return gate(ref,util,context,expected,source_verify,root,step,transport,result,
                20.0,'inspect',qa,{},[],scope,install_source_manifest=install_pin)
        return run,state,calls,writes,result
    run,state,calls,writes,result=case('positive')
    flow,recorder,guard=run()
    need(state['discover']==1 and state['legacy']==0 and state['flow'] and not state['closed'] and
         len(writes)==1 and calls.count('install_source_verify')==1 and
         calls.count('Main_guard')==4 and result['Main_before']=={'in_memory':True},
         'PRODUCTION_TASK_OPEN_MUST_REACH_CURRENT_DISCOVERY')
    rows.append({'name':'production_open_task_context_routes_pinned_current_discovery','passed':True})
    for mode,error,name in [
        ('source_changed','EXACT_INSTALL_SOURCE_STOP','changed_install_source_stops_before_discovery'),
        ('wrong_init','FIXED_MAIN_DISCOVERY_CHANGED','wrong_discovered_init_retains_original_guard')]:
        run,state,calls,writes,result=case(mode)
        try:run()
        except RuntimeError as caught:need(str(caught)==error,'WRONG_TASK_ROUTE_FIRST_ERROR:'+name)
        else:raise RuntimeError('TASK_ROUTE_NEGATIVE_ACCEPTED:'+name)
        need(state['closed'] and not state['flow'] and state['legacy']==0 and not writes,
             'FAILED_TASK_ROUTE_MUST_CLOSE_HELD_TARGET')
        if mode=='source_changed':need(state['discover']==0,'SOURCE_FAILURE_REACHED_DISCOVERY')
        rows.append({'name':'production_open_task_context_'+name,'passed':True})
    return rows


def run_controls(p):
    sources=p['sources']
    qa=module(sources['contract'],'actual_amazon_r4_contract')
    adapter=module(sources['adapter'],'actual_amazon_r4_adapter')
    navigation=module(sources['business'],'original_amazon_search_navigation')
    context=module(sources['context'],'current_amazon_task_context')
    worker=module(sources['coordinator'],'current_amazon_coordinator')
    transport=module(sources['transport'],'current_amazon_bound_arun')
    assert qa.PROTOCOL=='pocket4-owned-amazon-qa-v4' and qa.SELF=='org.droidloom.qa.amazon.r4'
    assert type(worker.HELPER_UID) is int and worker.HELPER_UID==context.HELPER_UID==p['actual_binding']['UID']
    assert worker.INSTALLED['uid']==worker.HELPER_UID and worker.INSTALLED['package']==qa.SELF
    assert worker.CURRENT_EPOCH==context.CURRENT_EPOCH==qa.MAIN_EPOCH==transport.FRAMEWORK_EPOCH_SHA256
    assert worker.CURRENT_BASELINE_SHA==context.CURRENT_BASELINE_SHA==qa.MAIN_BASELINE_SHA
    assert worker.CURRENT_QUALIFICATION_SHA==context.CURRENT_QUALIFICATION_SHA==qa.MAIN_BASELINE_QUALIFICATION_SHA
    assert worker.CURRENT_HOST_MANIFEST==context.CURRENT_HOST_MANIFEST==adapter.RECORDER_MANIFEST_SHA
    # Verify this generation's complete source delta before the original
    # historical inverse checks. No production validator is stubbed.
    def prior_current_source(name):
        value=sources[name]
        for edit in reversed(p['cell02_edits']+p['cell02_binding_edits']):
            if edit['file']!=name:continue
            assert value.count(edit['to'])==edit['count'],(name,edit['why'])
            value=value.replace(edit['to'],edit['from'])
        assert value==p['prior_current_sources'][name],name
        return value
    prior_current={name:prior_current_source(name) for name in ('coordinator','context','business','stage')}
    old=ast.parse(p['attribution_baseline'])
    new=ast.parse(sources['coordinator'])
    previous=ast.parse(p['attribution_candidate'])
    # No guard body is silently removed: undo exactly the declared source edits.
    for name,prior,key in [('coordinator',p['attribution_candidate'],'coordinator_edits'),
                           ('context',p['prior_context'],'context_edits')]:
        restored=prior_current[name]
        for row in p['nonce_mapping']:
            restored=restored.replace(row['value'],row['slot'])
        for row in reversed(p[key]):
            assert restored.count(row['next'])==row['count']
            restored=restored.replace(row['next'],row['old'])
        assert restored==prior,name
    assert sources['business']==p['prior_business']
    assert ast.dump(one(new.body,ast.FunctionDef,NAME),include_attributes=False)==ast.dump(
        one(previous.body,ast.FunctionDef,NAME),include_attributes=False)
    assert [ast.dump(x,include_attributes=False) for x in handler(new).body]==[
        ast.dump(x,include_attributes=False) for x in handler(previous).body]
    actual_raw=p['attribution_actual_inspection']
    actual=json.loads(actual_raw)
    original=actual['search_entry']['failed_sequence_observation']
    post=actual['search_entry']['post_sequence']
    assert original['restoration_qualified'] is False and post['restoration_qualified'] is True
    assert actual['error']['details']['previous_details']['owned_helper_failure']['helper_rejection']['error']=='TREE_CHANGED_NULL_CHILD'
    assert actual['failed_sequence_observation']==post
    cases=[]
    def passed(name):cases.append({'name':name,'passed':True})
    passed('full_declared_typed_source_inverse_and_original_attribution_guards')
    seed={'error':actual['error'],'search_entry':actual['search_entry']}
    old_result=execute_handler(old,seed,post)
    assert old_result['failed_sequence_observation']==post
    passed('actual_old_top_level_overwrites_first_failure_with_successful_post')
    new_result=execute_handler(new,seed,post)
    assert new_result['failed_sequence_observation']==original
    assert new_result['independent_post_sequence_observation']==post
    assert 'independent_failed_post_sequence_observation' not in new_result
    passed('actual_first_failure_and_independent_successful_post_both_retained')
    failed_post={'error':{'phase':'post-only'},'restoration_qualified':False,'test_marker':'post_failure'}
    early={'error':{'phase':'stable_search_entry_or_click'},'failed_sequence_observation':original,
           'failed_post_sequence_observation':failed_post}
    result=execute_handler(new,{'error':{'original':1},'search_entry':early},failed_post)
    assert result['failed_sequence_observation']==original and result['independent_failed_post_sequence_observation']==failed_post
    passed('secondary_post_failure_never_replaces_earlier_sequence')
    post_first={'error':{'phase':'independent_post_entry_inspection'},'failed_post_sequence_observation':failed_post}
    result=execute_handler(new,{'error':{'original':2},'search_entry':post_first},failed_post)
    assert result['failed_sequence_observation']==failed_post and result['independent_failed_post_sequence_observation']==failed_post
    passed('post_first_failure_is_primary_when_no_earlier_failure')
    missing={'error':{'phase':'stable_search_entry_or_click'},'failed_post_sequence_observation':failed_post}
    result=execute_handler(new,{'error':{'original':3},'search_entry':missing},post)
    assert 'failed_sequence_observation' not in result and result['independent_failed_post_sequence_observation']==failed_post
    passed('missing_primary_observation_does_not_fall_back_to_secondary_or_last')
    result=execute_handler(new,{'error':{'original':4}},post)
    assert 'failed_sequence_observation' not in result
    passed('no_navigation_record_does_not_invent_failure_from_stale_session')
    result=execute_handler(new,{'error':{'original':5},'search_entry':{'error':None,'post_sequence':post}},post)
    assert 'failed_sequence_observation' not in result and result['independent_post_sequence_observation']==post
    passed('later_non_sequence_failure_keeps_post_separate')
    result=execute_handler(new,{'error':{'original':6}},post,'launch')
    assert result['failed_sequence_observation']==post
    passed('non_inspect_original_handler_behavior_unchanged')

    assert len(cases)==9
    for name,source in sources.items():
        data=source.encode()
        assert p['bound_source_pins'][name]=={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        compile(source,'<seven-current-source-'+name+'>','exec')
    assert len(sources)==7
    passed('exact_current_R4_helper_and_seven_source_bindings_compile')
    plans=navigation.plans(worker.PLAN)
    for plan in plans:adapter.validate_plan(plan,qa)
    ordered=[worker.NONCE]
    for plan in worker.PLAN['stability']:
        ordered.extend(plan['nonces'][name] for name in ('before','inspect','after'))
    ordered.extend(worker.PLAN['entry']['nonces'][name] for name in ('before','inspect','action','after'))
    ordered.extend(worker.PLAN['post']['nonces'][name] for name in ('before','inspect','after'))
    assert ordered==p['fresh_nonce_values'] and len(ordered)==len(set(ordered))==32
    passed('production_adapter_validates_all_ten_plans_and_actual_thirty_two_nonce_order')
    install_docs={name:json.loads(p['actual_install'][name]) for name in ('coordinator','stage','worker')}
    observed=worker.actual_install(install_docs)
    assert observed['installed']==worker.INSTALLED and observed['actual_state_wire_sha256']==worker.STATE_WIRE
    passed('production_actual_install_accepts_exact_current_parent_worker_receipts')
    old_docs=copy.deepcopy(install_docs)
    old_docs['worker']['state']['helper']['protocol']='pocket4-owned-amazon-qa-v1'
    try:worker.actual_install(old_docs)
    except RuntimeError as error:assert str(error)=='ACTUAL_NO_AUTOMATION_STATE_REQUIRED'
    else:raise AssertionError('old Amazon helper protocol accepted')
    passed('production_actual_install_rejects_old_helper_protocol')
    # Exercise the production Flow and BoundArun constructors, with only in-memory
    # target/callback fixtures. No command, held entry, file operation or Main read
    # is allowed by these fixtures.
    class SyntheticPrivatePath(PurePosixPath):
        def is_dir(self):return True

    def typed_scope_fixture():
        baseline={'schema':qa.MAIN_BASELINE_SCHEMA,'kind':'current-cell-generation',
            'deployment_performed':False,'framework_exit_cause_resolved':False,'whole_app_production_ready':False,
            'framework_epoch':{'sha256':qa.MAIN_EPOCH},
            'packages':{qa.PACKAGE:qa.UID}}
        ref=types.SimpleNamespace(current_baseline=lambda:baseline,EPOCH=qa.MAIN_EPOCH,
            BASELINE_SHA=qa.MAIN_BASELINE_SHA,QUALIFICATION_SHA=qa.MAIN_BASELINE_QUALIFICATION_SHA)
        return worker.scope_record(types.SimpleNamespace(ref=ref,adapter=adapter),'a'*64)


    def construct_flow(scope):
        accesses=[]
        def forbidden(*args,**kwargs):
            accesses.append('FORBIDDEN_IO')
            raise AssertionError('pure constructor reached command/file/entry')
        root=SyntheticPrivatePath('/synthetic/current-AMAZON-flow')
        step=root/'steps'/'inspect-01'
        target=types.SimpleNamespace(expected={'pid':42},
            helper_sha256=transport.HELD_HELPER_SHA256,
            verify=lambda:accesses.append('target'),entry=forbidden,close=forbidden)
        recorder=types.SimpleNamespace(write_new=forbidden,
            Flow=types.SimpleNamespace(command=forbidden))
        flow=context.Flow(recorder=recorder,
            contract=types.SimpleNamespace(sha256=adapter.RECORDER_MANIFEST_SHA),
            target=target,environment={key:'/synthetic/non-authority' for key in transport.REQUIRED_ENV},
            transport=transport,main_guard=lambda:accesses.append('Main'),
            root=root,step=step,phase='inspect',scope=scope,
            activation={'framework_epoch':{'binding':{'processes':{'init':{'host_pid':42}}}}},
            tasks={},qa=qa,inspect_plan=worker.PLAN,
            resolve=['synthetic-resolve'],read=forbidden,deadline=context.time.monotonic()+60)
        return flow,accesses

    flow,accesses=construct_flow(typed_scope_fixture())
    assert not accesses and type(flow.transport) is transport.BoundArun
    assert flow.transport.target is flow.target and flow.transport.environment=={
        key:'/synthetic/non-authority' for key in transport.REQUIRED_ENV}
    assert flow.current_qualified_scope==flow.scope and flow.current_qualified_scope is not flow.scope
    session=adapter.Session(flow,None,qa,{},worker.HELPER_UID)
    flow.guard()
    assert accesses==['Main','target'] and session.uid==worker.HELPER_UID
    passed('production_typed_Flow_BoundArun_and_R4_Session_positive_without_IO')

    for name,mutate,expected in [
        ('old_scope_schema',lambda v:v.update(schema='old-recorder-scope'),'EXACT_TYPED_CURRENT_AMAZON_TASK_SCOPE'),
        ('wrong_baseline_schema',lambda v:v.update(current_baseline_schema='old-deployment'),'EXACT_TYPED_CURRENT_AMAZON_TASK_SCOPE'),
        ('foreign_package',lambda v:v.update(package='com.bilibili.app'),'EXACT_TYPED_CURRENT_AMAZON_TASK_SCOPE'),
        ('foreign_target_uid',lambda v:v.update(uid=10117),'EXACT_TYPED_CURRENT_AMAZON_TASK_SCOPE'),
        ('boolean_uid',lambda v:v.update(uid=True),'EXACT_TYPED_CURRENT_AMAZON_TASK_SCOPE'),
        ('boolean_user',lambda v:v.update(user=False),'EXACT_TYPED_CURRENT_AMAZON_TASK_SCOPE'),
        ('wrong_epoch',lambda v:v.update(epoch_sha256='e'*64),'EXACT_TYPED_CURRENT_AMAZON_TASK_SCOPE'),
        ('wrong_baseline_sha',lambda v:v.update(current_baseline_sha256='e'*64),'EXACT_TYPED_CURRENT_AMAZON_TASK_SCOPE'),
        ('wrong_qualification_sha',lambda v:v.update(current_baseline_qualification_sha256='e'*64),'EXACT_TYPED_CURRENT_AMAZON_TASK_SCOPE'),
        ('old_recorder_manifest',lambda v:v.update(original_recorder_manifest_sha256='e'*64),'EXACT_TYPED_CURRENT_AMAZON_TASK_SCOPE'),
        ('legacy_activation_extra',lambda v:v.update(activation_sha256='e'*64),'EXACT_TYPED_CURRENT_AMAZON_TASK_SCOPE'),
        ('foreign_component',lambda v:v.update(component='com.synthetic.foreign/.Main'),'EXACT_CURRENT_TASK_SOURCE_NONCE_AND_COMPONENT'),
        ('invalid_nonce',lambda v:v.update(nonce='not-a-nonce'),'EXACT_CURRENT_TASK_SOURCE_NONCE_AND_COMPONENT'),
        ('invalid_task_manifest',lambda v:v.update(amazon_task_source_manifest_sha256='bad'),'EXACT_CURRENT_TASK_SOURCE_NONCE_AND_COMPONENT'),
        ('invalid_resolver_pin',lambda v:v.update(actual_resolution_result_sha256='bad'),'EXACT_CURRENT_TASK_SOURCE_NONCE_AND_COMPONENT')]:
        value=typed_scope_fixture();mutate(value)
        try:construct_flow(value)
        except RuntimeError as error:assert str(error)==expected,(name,str(error))
        else:raise AssertionError(name+' accepted by production Flow')
        passed('production_Flow_'+name+'_rejected_before_transport')

    flow,accesses=construct_flow(typed_scope_fixture())
    flow.scope['component']=qa.PACKAGE+'/.activity.OtherActivity'
    try:flow.guard()
    except RuntimeError as error:assert str(error)=='CURRENT_AMAZON_TASK_SCOPE_CHANGED'
    else:raise AssertionError('mutated constructed scope admitted')
    assert accesses==[]
    passed('constructed_current_scope_mutation_stops_before_Main_target_or_IO')


    assert len(cases)==30 and len({x['name'] for x in cases})==30

    for name,field,value in [
        ('previous_guard_schema','schema','pocket4-current-main-guard-v1'),
        ('owner_chain_unqualified','authenticated_owner_chain_matches',False),
        ('user_namespace_unqualified','current_user_namespaces_match',False),
        ('executable_root_unqualified','current_executable_and_root_backing_match',False),
        ('previous_baseline_chain_changed','previous_current_baseline_sha256','e'*64),
        ('old_helper_authority_forged','old_helpers_and_tasks_reauthorized',True)]:
        rows=copy.deepcopy(install_docs)
        changed=copy.deepcopy(rows['worker']['Main_before']);changed[field]=value
        for role,fields in {'worker':('Main_before_lock','Main_before','Main_after'),
                            'coordinator':('Main_before','Main_after'),
                            'stage':('Main_before','Main_after')}.items():
            for key in fields:rows[role][key]=copy.deepcopy(changed)
        try:worker.actual_install(rows)
        except RuntimeError as error:
            assert str(error)=='ACTUAL_INSTALL_TYPED_CURRENT_BASELINE_REQUIRED',(name,str(error))
        else:raise AssertionError(name+' accepted by production actual_install')
        passed('current_cell02_actual_install_'+name+'_rejected')
    for name,field,value in [('wrong_generation_kind','kind','unrelated-generation'),
                             ('forged_deployment','deployment_performed',True)]:
        baseline={'schema':qa.MAIN_BASELINE_SCHEMA,'kind':'current-cell-generation',
            'deployment_performed':False,'framework_exit_cause_resolved':False,'whole_app_production_ready':False,
            'framework_epoch':{'sha256':qa.MAIN_EPOCH},'packages':{qa.PACKAGE:qa.UID}}
        baseline[field]=value
        ref=types.SimpleNamespace(current_baseline=lambda:baseline,EPOCH=qa.MAIN_EPOCH,
            BASELINE_SHA=qa.MAIN_BASELINE_SHA,QUALIFICATION_SHA=qa.MAIN_BASELINE_QUALIFICATION_SHA)
        try:worker.scope_record(types.SimpleNamespace(ref=ref,adapter=adapter),'a'*64)
        except RuntimeError as error:
            assert str(error)=='CURRENT_TYPED_OWN_TARGET_SCOPE_REQUIRED',(name,str(error))
        else:raise AssertionError(name+' accepted by production scope_record')
        passed('current_cell02_scope_record_'+name+'_rejected')
    rows=copy.deepcopy(install_docs)
    rows['worker']['state']['helper']['protocol']='pocket4-owned-amazon-qa-v3'
    try:worker.actual_install(rows)
    except RuntimeError as error:assert str(error)=='ACTUAL_NO_AUTOMATION_STATE_REQUIRED'
    else:raise AssertionError('previous v3 protocol accepted')
    passed('current_cell02_exact_previous_helper_protocol_rejected')
    assert len(cases)==39 and len({x['name'] for x in cases})==39
    for row in run_task_discovery_route_controls(context,worker,qa):passed(row['name'])
    assert len(cases)==42 and len({x['name'] for x in cases})==42
    return {'schema':1,'ok':True,'count':42,'cases':cases,
        'current_attribution_controls':9,'production_typed_constructor_controls':17,'current_cell02_generation_controls':9,'current_owner_task_route_controls':3,
        'production_scope_record_Flow_BoundArun_and_Session_executed':True,
        'production_actual_install_and_all_plan_validators_executed':True,
        'current_typed_source_exact_declared_inverse':True,
        'unchanged_search_readiness_and_full_tree_action_guards':True,
        'historical_failure_unknown_not_reclassified':True,
        'all_fixtures_in_memory':True,'file_writes':0,'child_processes':0,
        'Android_actions':0,'Main_accessed':False,'real_Java_helper_executed':False,
        'runtime_UI_dispatched':False,'whole_app_production_ready':False}
