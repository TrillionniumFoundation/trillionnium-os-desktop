"""Current BestBuy R3 complete-tree readiness, original Session, and typed constructor controls.

All source and historical metadata fixtures are exact in-memory payload strings.
No live Main, private tree, filesystem, process, or Android entry is called.
"""
import ast
import copy
import hashlib
import json
from pathlib import PurePosixPath
import types

def module(source,name):
    tree=ast.parse(source)
    tree.body=[n for n in tree.body if not(isinstance(n,ast.Assign) and
        any(isinstance(t,ast.Name) and t.id=='HERE' for t in n.targets))]
    value=types.ModuleType(name);value.__file__='/pure-control/'+name+'.py'
    value.HERE=PurePosixPath('/pure-control')
    exec(compile(tree,'<pure-module-'+name+'>','exec'),value.__dict__)
    return value

def run_controls(p):
    sources=p['sources']
    r=module(sources['business'],'bestbuy_r3_readiness')
    context=module(sources['context'],'bestbuy_current_task_context')
    worker=module(sources['coordinator'],'bestbuy_current_coordinator')
    qa=module(sources['contract'],'actual_bestbuy_r3_contract')
    adapter=module(sources['adapter'],'actual_bestbuy_r3_adapter')
    transport=module(sources['transport'],'actual_bestbuy_current_bound_arun')
    assert qa.PROTOCOL=='pocket4-owned-bestbuy-qa-v3' and qa.SELF=='org.droidloom.qa.bestbuy.r3'
    assert type(worker.HELPER_UID) is int and worker.HELPER_UID==context.HELPER_UID==10155
    assert worker.INSTALLED['uid']==worker.HELPER_UID and worker.INSTALLED['package']==qa.SELF
    assert worker.CURRENT_EPOCH==context.CURRENT_EPOCH==qa.MAIN_EPOCH==transport.FRAMEWORK_EPOCH_SHA256
    assert worker.CURRENT_BASELINE_SHA==context.CURRENT_BASELINE_SHA==qa.MAIN_BASELINE_SHA
    assert worker.CURRENT_QUALIFICATION_SHA==context.CURRENT_QUALIFICATION_SHA==qa.MAIN_BASELINE_QUALIFICATION_SHA
    assert worker.CURRENT_HOST_MANIFEST==context.CURRENT_HOST_MANIFEST==adapter.RECORDER_MANIFEST_SHA
    cases=[]
    def passed(name):cases.append({'case':name,'passed':True})
    def rejected(name,call,reason=None):
        try:call()
        except RuntimeError as error:
            if reason is not None:assert str(error)==reason,(name,str(error))
            passed(name);return error
        raise AssertionError(name+' accepted')
    def defs(source):
        return {x.name:ast.dump(x,include_attributes=False) for x in ast.parse(source).body
                if isinstance(x,(ast.FunctionDef,ast.ClassDef))}
    restored=sources['context']
    for row in reversed(p['context_edits']):
        assert restored.count(row['next'])==row['count']
        restored=restored.replace(row['next'],row['old'])
    assert restored==p['prior_context']
    old=defs(p['prior_context']);new=defs(sources['context'])
    assert old['Policy']==new['Policy']
    current_business=sources['business']
    assert current_business.count('=='+str(worker.HELPER_UID))==2
    restored_business=current_business.replace('=='+str(worker.HELPER_UID),'==10198')
    assert restored_business==p['prior_business']
    original=defs(p['prior_business']);current=defs(restored_business)
    for name in ('need','sha','no_raw_ui','validated_assessment','public_role_counts'):
        assert original[name]==current[name],name
    passed('exact_declared_typed_context_inverse_and_original_public_count_guards')
    assert len(sources)==7
    for name,source in sources.items():
        data=source.encode()
        assert p['bound_source_pins'][name]=={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        compile(source,'<all-seven-bound-'+name+'>','exec')
    passed('exact_current_R3_helper_and_seven_source_bindings_compile')
    values=[worker.NONCE]
    for plan in worker.PLANS:
        adapter.validate_plan(plan,qa)
        values.extend(plan['nonces'][name] for name in ('before','inspect','after'))
    assert values==p['fresh_nonce_values'] and len(values)==len(set(values))==10
    passed('production_adapter_validates_all_three_plans_and_actual_ten_nonce_order')
    install_docs={name:json.loads(p['actual_install'][name]) for name in ('coordinator','stage','worker')}
    observed=worker.actual_install(install_docs)
    assert observed['installed']==worker.INSTALLED and observed['actual_state_wire_sha256']==worker.STATE_WIRE
    passed('production_actual_install_validator_accepts_exact_current_parent_worker_receipts')
    old_protocol_docs=copy.deepcopy(install_docs)
    old_protocol_docs['worker']['state']['helper']['protocol']='pocket4-owned-bestbuy-qa-v1'
    rejected('production_actual_install_validator_rejects_old_helper_protocol',
        lambda:worker.actual_install(old_protocol_docs),'ACTUAL_NO_AUTOMATION_STATE_REQUIRED')
    def node(path='0',label='',clickable=False,resource='',kind='android.widget.FrameLayout'):
        return {'path':path,'package':qa.PACKAGE,'class':kind,'class_truncated':False,
            'resource_id':resource,'resource_id_truncated':False,'visible':True,'enabled':True,
            'password':False,'editable':False,'supports_set_text':False,'clickable':clickable,
            'text':label,'text_sha256':qa.sha(label.encode()),'text_truncated':False,
            'content_desc':'','content_desc_sha256':qa.sha(b''),'content_desc_truncated':False,
            'bounds':[0,0,100,100],'child_count':0}
    def tree(nodes):
        value={'complete':True,'traversal':'visible-non-password-subtrees','nodes':copy.deepcopy(nodes),
            'window':{'package':qa.PACKAGE,'focused':True,'type':1,'display':0,'bounds':[0,0,100,100]},
            'observed_elapsed_ms':100,'connection_scoped_window_id':12}
        return refresh(value)
    def refresh(value):
        for n in value['nodes']:
            n.pop('node_sha256',None);n['node_sha256']=qa.sha(qa.canonical(n))
        value['tree_sha256']=qa.sha(qa.canonical(value['nodes']))
        value['window_sha256']=qa.sha(qa.canonical(value['window']))
        return value
    zero=tree([node()])
    ready=tree([node(),node('0/0','Search',True,'com.bestbuy.android:id/search_button','android.widget.Button')])
    def row(value):
        counts=r.public_role_counts(qa,value)
        return {'complete_current_assessment_verified':True,'public_role_counts':counts,
                'public_decision':r.decision(counts)}
    assert row(zero)['public_decision']['catalog_all_zero']
    assert row(ready)['public_decision']['public_entry_candidate_present']
    passed('actual_contract_complete_catalog_zero_and_actionable_public_entry')

    class Clock:
        def __init__(self):self.now=0.0;self.sleeps=[]
        def __call__(self):return self.now
        def sleep(self,seconds):
            assert 0<seconds<=10
            self.sleeps.append(seconds);self.now+=seconds
    def observe(values,cost=1.0):
        clock=Clock();calls=[];result=r.observation_record()
        def collect(plan,index):
            calls.append((index,copy.deepcopy(plan)))
            clock.now+=cost
            selected=values[min(index,len(values)-1)]
            if isinstance(selected,BaseException):raise selected
            if callable(selected):return selected(plan,index)
            return row(selected)
        try:r.observe(worker.PLANS,collect,lambda:None,result,clock=clock,sleep=clock.sleep)
        except BaseException as error:return result,calls,clock,error
        return result,calls,clock,None
    out,calls,clock,error=observe([zero,zero,ready])
    assert error is None and len(calls)==3 and out['public_entry_candidate_present']
    assert [x['began_seconds_after_qualification_start'] for x in out['rounds']]==[0,10,20]
    assert len({n for _,p in calls for n in p['nonces'].values()})==9
    passed('three_successful_independent_rounds_only_after_all_zero_at_0_10_20_seconds')
    out,calls,_,error=observe([ready])
    assert error is None and len(calls)==1 and out['public_entry_candidate_present']
    passed('first_actionable_entry_stops_without_another_read')
    out,calls,_,error=observe([zero])
    assert error is None and len(calls)==3 and not out['public_entry_candidate_present']
    assert out['stop_reason']=='THREE_COMPLETE_PUBLIC_CATALOGS_ALL_ZERO'
    passed('three_zero_observations_stop_without_loading_persistence_claim_or_fourth_round')
    for name,value in [
        ('retry_label',tree([node('0','Retry',True,kind='android.widget.Button')])),
        ('error_label',tree([node('0','Something went wrong')])),
        ('nonclickable_entry',tree([node('0','Search')])),
        ('generic_dialog_button',tree([node('0','',True,'android:id/button1','android.widget.Button')])),
        ('background_entry_with_error',tree([node(),node('0/0','Search',True),node('0/1','No internet connection')]))]:
        out,calls,_,error=observe([value,ready])
        assert error is None and len(calls)==1 and not out['public_entry_candidate_present'],name
        passed(name+'_never_ready_and_nonzero_cannot_trigger_a_second_read')
    partial=copy.deepcopy(ready);partial['complete']=False
    out,calls,_,error=observe([partial,ready])
    assert isinstance(error,RuntimeError) and len(calls)==1 and out['completed_rounds']==0
    passed('incomplete_current_tree_fails_without_retry')
    bad=copy.deepcopy(ready);bad['nodes'][1]['text_sha256']='0'*64;refresh(bad)
    out,calls,_,error=observe([bad,ready])
    assert str(error)=='PUBLIC_LABEL_DIGEST_MISMATCH' and len(calls)==1
    passed('bad_current_public_label_digest_fails_without_retry')
    out,calls,_,error=observe([RuntimeError('synthetic_first_read_failure'),ready])
    assert str(error)=='synthetic_first_read_failure' and len(calls)==1 and out['completed_rounds']==0
    passed('failed_first_read_is_preserved_and_never_retried')
    out,calls,_,error=observe([zero,RuntimeError('synthetic_second_read_failure'),ready])
    assert str(error)=='synthetic_second_read_failure' and len(calls)==2 and out['completed_rounds']==1
    assert out['rounds'][0]['public_decision']['catalog_all_zero'] is True
    passed('failed_second_read_keeps_first_complete_observation_and_cannot_start_third')
    out,calls,_,error=observe([ready],cost=31.0)
    assert error is None and len(calls)==1 and not out['public_entry_candidate_present']
    assert out['stop_reason']=='COMPLETED_AFTER_QUALIFICATION_DEADLINE'
    passed('late_complete_entry_preserved_without_30_second_execution_kill_or_readiness')
    clock=Clock();out=r.observation_record();calls=[]
    def slow_guard():clock.now=31.0
    rejected('deadline_before_first_round_prevents_any_session',
        lambda:r.observe(worker.PLANS,lambda p,i:calls.append(i),slow_guard,out,clock=clock,sleep=clock.sleep),
        'NO_COMPLETE_READINESS_OBSERVATION')
    assert calls==[] and out['rounds_started']==0
    private=tree([node('0','PRIVATE_USER_CONTENT_FIXTURE',True,'PRIVATE_RESOURCE_FIXTURE','PRIVATE_CLASS_FIXTURE')])
    encoded=json.dumps(row(private))
    assert not any(x in encoded for x in ('PRIVATE_USER_CONTENT_FIXTURE','PRIVATE_RESOURCE_FIXTURE','PRIVATE_CLASS_FIXTURE'))
    passed('unknown_user_labels_identifiers_classes_and_node_paths_never_exported')
    out,calls,_,error=observe([lambda p,i:{'complete_current_assessment_verified':True,'nodes':[]}])
    assert str(error)=='RAW_UI_EXPORT_FORBIDDEN' and len(calls)==1
    passed('nested_raw_UI_export_rejected_before_qualification')

    # Use only the five safe metadata originals, never their private assessment.
    raw=p['historical_inspect'].encode()
    assert len(raw)==21067 and hashlib.sha256(raw).hexdigest()=='95b15ea5f365c7a672cffa446ddb39faed675388ed7b123c84db8f55f818fd14'
    safe=json.loads(raw);plan=worker.PLANS[0]
    inspection=copy.deepcopy(ready)
    inspection['connection_scoped_window_id']=safe['assessments']['inspect']['connection_scoped_window_id']
    refresh(inspection)
    sequence=copy.deepcopy(safe['sequence'])
    # This is an explicitly synthetic protocol fixture, never current task authority.
    for key in ('foreground_before','foreground_after'):
        sequence[key].update(main_epoch_sha256=qa.MAIN_EPOCH,main_baseline_schema=qa.MAIN_BASELINE_SCHEMA,
            main_baseline_sha256=qa.MAIN_BASELINE_SHA,
            main_baseline_qualification_sha256=qa.MAIN_BASELINE_QUALIFICATION_SHA)
    sequence['installed_before']=copy.deepcopy(worker.INSTALLED)
    sequence['installed_after']=copy.deepcopy(worker.INSTALLED)
    sequence['post_termination_state']['helper_uid']=worker.HELPER_UID
    metadata=copy.deepcopy(safe['assessments'])
    counters=copy.deepcopy(metadata['inspect']['tree_observations'])
    # Synthetic current-protocol limit, not a claim about the historical capture.
    counters[0]['depth_limit']=qa.MAX_DEPTH
    counters[0]['attempted_nodes']=counters[0]['emitted_nodes']=len(inspection['nodes'])
    counters[0]['serialized_bytes']=len(qa.canonical(inspection))
    before_state=sequence['accessibility_restoration']['state_before']
    helper={'protocol':qa.PROTOCOL,'nonce':plan['nonces']['inspect'],'op':'inspect','self_uid':worker.HELPER_UID,
        'ok':True,'error':None,'secondary_errors':[],'action_attempted':False,'outcome_unknown':False,
        'claim_persistence_completed':True,'helper_work_completed':True,'automatic_retry':False,
        'business_success_verified':False,'request_sha256':qa.sha(qa.validate_request({
            'protocol':qa.PROTOCOL,'nonce':plan['nonces']['inspect'],'op':'inspect',
            'scope':sequence['foreground_after']})),'host_scope_attestation':sequence['foreground_after'],
        'target_uid_verified':qa.UID,'restoration':{'service_info_verified':True,'service_info_captured':True,
            'connection_flags':1},'requires_post_termination_state_check':True,
        'inspection':inspection,'window_observation':metadata['inspect']['window_observation'],
        'tree_observations':counters,'accessibility_state_before_connection':before_state}
    wire=qa.sha(qa.canonical(helper))
    assessed={'helper':helper,'held_transport_returned_after_post_guard':True,
        'actual_command_returncode':0,'actual_instrumentation_finish_code':-1,
        'wire_sha256':wire,'recorder_command_result_sha256':'a'*64}
    for name in ('before','inspect','after'):metadata[name]['nonce']=plan['nonces'][name]
    metadata['before']['wire_sha256']='1'*64;metadata['after']['wire_sha256']='2'*64
    metadata['inspect'].update(wire_sha256=wire,tree_sha256=inspection['tree_sha256'],
        window_sha256=inspection['window_sha256'],node_count=len(inspection['nodes']),
        tree_observations=counters,recorder_command_result_sha256='a'*64)
    sequence['inspection_wire_sha256']=wire
    sequence['post_termination_state'].update(nonce=plan['nonces']['after'],wire_sha256='2'*64)
    sequence['accessibility_restoration']['wire_sha256']=['1'*64,wire,'2'*64]
    expected_task=copy.deepcopy(sequence['owned_task'])
    installed=copy.deepcopy(sequence['installed_before'])
    current_row=r.qualify_current(qa,assessed,sequence,plan,metadata,expected_task,installed)
    assert current_row['public_decision']['public_entry_candidate_present'] is True
    passed('current_complete_assessment_wire_scope_counters_and_three_state_pins_rebound')
    changed=copy.deepcopy(sequence);changed['owned_task']['task']+=1
    rejected('foreign_task_cannot_qualify_current_public_entry',
        lambda:r.qualify_current(qa,assessed,changed,plan,metadata,expected_task,installed),
        'CURRENT_COMPLETE_ORIGINAL_SESSION_SAME_TASK_REQUIRED')
    changed=copy.deepcopy(sequence);changed['restoration_qualified']=False
    rejected('failed_after_state_cannot_qualify_current_public_entry',
        lambda:r.qualify_current(qa,assessed,changed,plan,metadata,expected_task,installed),
        'CURRENT_COMPLETE_ORIGINAL_SESSION_SAME_TASK_REQUIRED')
    changed=copy.deepcopy(metadata);changed['inspect']['node_count']+=1
    rejected('current_assessment_summary_mismatch_rejected',
        lambda:r.qualify_current(qa,assessed,sequence,plan,changed,expected_task,installed),
        'CURRENT_ASSESSMENT_TREE_WIRE_STATE_AND_COMMAND_BINDING_REQUIRED')
    changed=copy.deepcopy(assessed);changed['helper']['self_uid']=10196
    rejected('different_helper_UID_rejected',
        lambda:r.qualify_current(qa,changed,sequence,plan,metadata,expected_task,installed),
        'ACTUAL_SUCCESSFUL_NO_ACTION_INSPECTION_REQUIRED')

    step=PurePosixPath('/synthetic-bestbuy-control-step')
    request_bytes={}
    scope=sequence['foreground_after']
    requests=[]
    for p in worker.PLANS:
        trio=[]
        for phase in ('before','inspect','after'):
            request={'protocol':qa.PROTOCOL,'nonce':p['nonces'][phase],
                'op':'inspect' if phase=='inspect' else 'state'}
            if phase=='inspect':request['scope']=scope
            trio.append(request)
            request_bytes[step/(request['nonce']+'.request.json')]=qa.validate_request(request)
        requests.append(trio)
    def read_request(path,maximum):
        assert maximum==65536
        if path not in request_bytes:raise FileNotFoundError(path)
        return request_bytes[path]
    def policy():
        return context.Policy('inspect',qa,[],copy.deepcopy(worker.PLANS),step,read_request,lambda:expected_task)
    p=policy()
    rejected('instrumentation_cannot_precede_explicit_current_round',
        lambda:p.admit(qa.instrumentation_argv(requests[0][0]),20,False,False),'CURRENT_READ_ONLY_ROUND_REQUIRED')
    p.begin_round(0)
    rejected('inspection_cannot_precede_before_state',
        lambda:p.admit(qa.instrumentation_argv(requests[0][1]),20,False,False),
        'ONLY_ONE_CURRENT_SOURCE_BOUND_STATE_OR_INSPECT_REQUEST')
    rejected('future_round_nonce_cannot_run_in_current_round',
        lambda:p.admit(qa.instrumentation_argv(requests[1][0]),20,False,False),
        'ONLY_ONE_CURRENT_SOURCE_BOUND_STATE_OR_INSPECT_REQUEST')
    p.admit(qa.instrumentation_argv(requests[0][0]),20,False,False)
    rejected('next_round_cannot_start_without_current_after_state',
        lambda:p.begin_round(1),'NEXT_DISTINCT_COMPLETE_READ_ONLY_ROUND_REQUIRED')
    for req in requests[0][1:]:p.admit(qa.instrumentation_argv(req),20,False,False)
    for i in (1,2):
        p.begin_round(i)
        for req in requests[i]:p.admit(qa.instrumentation_argv(req),20,False,False)
    assert p.counts['instrument']==9 and len(p.used_nonces)==9
    rejected('fourth_round_rejected',lambda:p.begin_round(3),'NEXT_DISTINCT_COMPLETE_READ_ONLY_ROUND_REQUIRED')
    passed('policy_admits_exactly_nine_distinct_original_state_inspect_state_commands')
    click={'protocol':qa.PROTOCOL,'nonce':'f'*32,'op':'click','scope':scope,
        'inspection_nonce':worker.PLANS[0]['nonces']['inspect'],'inspection_sha256':'a'*64,
        'node_path':'0','node_sha256':'b'*64}
    p=policy();p.begin_round(0)
    rejected('click_command_not_admitted',
        lambda:p.admit(qa.instrumentation_argv(click),20,True,False),'NO_OTHER_BESTBUY_COMMAND_ADMITTED')
    rejected('arbitrary_settings_command_not_admitted',
        lambda:p.admit(['/system/bin/settings','put','secure','x','1'],20,True,False),
        'NO_OTHER_BESTBUY_COMMAND_ADMITTED')
    repeated=copy.deepcopy(worker.PLANS);repeated[1]['nonces']['before']=repeated[0]['nonces']['before']
    rejected('cross_round_nonce_reuse_rejected',
        lambda:context.Policy('inspect',qa,[],repeated,step,read_request,lambda:expected_task),
        'NINE_DISTINCT_READ_ONLY_HELPER_NONCES_REQUIRED')

    class SessionHarness(adapter.Session):
        """The production sequence method runs unchanged; only I/O methods are local fixtures."""
        def __init__(self,mode):
            self.qa=qa;self.mode=mode;self.events=[];self.installed_calls=0
        def installed(self):
            self.installed_calls+=1;self.events.append('installed')
            if self.mode=='before-installed':raise RuntimeError('synthetic_before_installed_failure')
            if self.mode=='after-installed' and self.installed_calls==2:return {'different':True}
            return installed
        def task(self):
            self.events.append('task')
            if self.mode=='post-task' and self.events.count('task')==2:return {'different_task':True}
            return expected_task
        def foreground(self):
            self.events.append('foreground');return scope
        def instrument(self,request):
            op=request['op'];self.events.append(op)
            if op=='inspect' and self.mode=='inspect':raise RuntimeError('synthetic_inspect_failure')
            if op=='state' and self.events.count('state')==2 and self.mode=='after-state':
                raise RuntimeError('synthetic_after_state_failure')
            h={'op':op,'nonce':request['nonce'],'self_uid':worker.HELPER_UID}
            if op=='state':h.update(state=before_state,ui_automation_connected=False)
            else:h.update(accessibility_state_before_connection=before_state,restoration={'service_info_verified':True})
            return {'helper':h,'wire_sha256':qa.sha(qa.canonical(h))}
    for mode in ('inspect','after-state','post-task','after-installed'):
        sessions=[]
        def original_failure(plan,index):
            session=SessionHarness(mode);sessions.append(session)
            session.sequence(plan)
            raise AssertionError('bad original Session unexpectedly accepted')
        out,calls,_,error=observe([original_failure,ready])
        assert isinstance(error,RuntimeError) and len(calls)==1 and len(sessions)==1
        session=sessions[0]
        assert session.events.count('state')==2
        assert session.sequence_observation['after_state_attempted'] is True
        assert session.installed_calls==2
        passed('original_Session_'+mode+'_failure_retains_after_state_finally_and_prevents_new_round')
    sessions=[]
    def installed_failure(plan,index):
        session=SessionHarness('before-installed');sessions.append(session);session.sequence(plan)
    out,calls,_,error=observe([zero,installed_failure,ready])
    assert isinstance(error,RuntimeError) and len(calls)==2 and out['completed_rounds']==1
    assert len(sessions)==1 and not hasattr(sessions[0],'sequence_observation')
    passed('fresh_second_Session_before_installed_failure_cannot_reuse_old_sequence_observation')
    worker_tree=ast.parse(sources['coordinator'])
    collect=next(x for x in ast.walk(worker_tree) if isinstance(x,ast.FunctionDef) and x.name=='collect_round')
    body=ast.unparse(collect)
    assert body.index('session = None')<body.index('session = q.adapter.Session')<body.index('flow.policy.begin_round')
    assert "'semantic_ready'" in sources['coordinator']
    assert worker.PHASE_SECONDS=={'launch':175,'inspect':175,'cleanup':115}
    passed('production_round_constructor_clears_stale_reference_and_original_phase_deadlines_remain')
    # Exercise the production Flow and BoundArun constructors, with only in-memory
    # target/callback fixtures. No command, held entry, file operation or Main read
    # is allowed by these fixtures.
    class SyntheticPrivatePath(PurePosixPath):
        def is_dir(self):return True

    def typed_scope_fixture():
        baseline={'schema':qa.MAIN_BASELINE_SCHEMA,'framework_epoch':{'sha256':qa.MAIN_EPOCH},
            'packages':{qa.PACKAGE:qa.UID}}
        ref=types.SimpleNamespace(current_baseline=lambda:baseline,EPOCH=qa.MAIN_EPOCH,
            BASELINE_SHA=qa.MAIN_BASELINE_SHA,QUALIFICATION_SHA=qa.MAIN_BASELINE_QUALIFICATION_SHA)
        return worker.scope_record(types.SimpleNamespace(ref=ref,adapter=adapter),'a'*64)


    def construct_flow(scope):
        accesses=[]
        def forbidden(*args,**kwargs):
            accesses.append('FORBIDDEN_IO')
            raise AssertionError('pure constructor reached command/file/entry')
        root=SyntheticPrivatePath('/synthetic/current-BESTBUY-flow')
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
            tasks={},qa=qa,inspect_plan=worker.PLANS,
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
    passed('production_typed_Flow_BoundArun_and_R3_Session_positive_without_IO')

    for name,mutate,expected in [
        ('old_scope_schema',lambda v:v.update(schema='old-recorder-scope'),'EXACT_TYPED_CURRENT_BESTBUY_TASK_SCOPE'),
        ('wrong_baseline_schema',lambda v:v.update(current_baseline_schema='old-deployment'),'EXACT_TYPED_CURRENT_BESTBUY_TASK_SCOPE'),
        ('foreign_package',lambda v:v.update(package='com.bilibili.app'),'EXACT_TYPED_CURRENT_BESTBUY_TASK_SCOPE'),
        ('foreign_target_uid',lambda v:v.update(uid=10117),'EXACT_TYPED_CURRENT_BESTBUY_TASK_SCOPE'),
        ('boolean_uid',lambda v:v.update(uid=True),'EXACT_TYPED_CURRENT_BESTBUY_TASK_SCOPE'),
        ('boolean_user',lambda v:v.update(user=False),'EXACT_TYPED_CURRENT_BESTBUY_TASK_SCOPE'),
        ('wrong_epoch',lambda v:v.update(epoch_sha256='e'*64),'EXACT_TYPED_CURRENT_BESTBUY_TASK_SCOPE'),
        ('wrong_baseline_sha',lambda v:v.update(current_baseline_sha256='e'*64),'EXACT_TYPED_CURRENT_BESTBUY_TASK_SCOPE'),
        ('wrong_qualification_sha',lambda v:v.update(current_baseline_qualification_sha256='e'*64),'EXACT_TYPED_CURRENT_BESTBUY_TASK_SCOPE'),
        ('old_recorder_manifest',lambda v:v.update(original_recorder_manifest_sha256='e'*64),'EXACT_TYPED_CURRENT_BESTBUY_TASK_SCOPE'),
        ('legacy_activation_extra',lambda v:v.update(activation_sha256='e'*64),'EXACT_TYPED_CURRENT_BESTBUY_TASK_SCOPE'),
        ('foreign_component',lambda v:v.update(component='com.synthetic.foreign/.Main'),'EXACT_CURRENT_TASK_SOURCE_NONCE_AND_COMPONENT'),
        ('invalid_nonce',lambda v:v.update(nonce='not-a-nonce'),'EXACT_CURRENT_TASK_SOURCE_NONCE_AND_COMPONENT'),
        ('invalid_task_manifest',lambda v:v.update(bestbuy_task_source_manifest_sha256='bad'),'EXACT_CURRENT_TASK_SOURCE_NONCE_AND_COMPONENT'),
        ('invalid_resolver_pin',lambda v:v.update(actual_resolution_result_sha256='bad'),'EXACT_CURRENT_TASK_SOURCE_NONCE_AND_COMPONENT')]:
        value=typed_scope_fixture();mutate(value)
        try:construct_flow(value)
        except RuntimeError as error:assert str(error)==expected,(name,str(error))
        else:raise AssertionError(name+' accepted by production Flow')
        passed('production_Flow_'+name+'_rejected_before_transport')

    flow,accesses=construct_flow(typed_scope_fixture())
    flow.scope['component']=qa.PACKAGE+'/.activity.OtherActivity'
    try:flow.guard()
    except RuntimeError as error:assert str(error)=='CURRENT_BESTBUY_TASK_SCOPE_CHANGED'
    else:raise AssertionError('mutated constructed scope admitted')
    assert accesses==[]
    passed('constructed_current_scope_mutation_stops_before_Main_target_or_IO')


    assert len(cases)==59 and len({x['case'] for x in cases})==59
    report={'schema':1,'ok':True,'count':len(cases),'cases':cases,
        'original_BestBuy_contract_functions_executed':True,
        'original_Session_sequence_executed_with_local_IO_subclass_only':True,
        'typed_context_declared_inverse_verified':True,
        'production_Flow_BoundArun_Session_constructors_executed':True,
        'production_typed_constructor_controls':17,
        'production_actual_install_and_adapter_plan_validators_executed':True,
        'private_retained_assessment_or_raw_commercial_UI_read':False,
        'Android_Hepta_process_or_UI_calls':0,'remote_qualification_performed':False}
    return report
