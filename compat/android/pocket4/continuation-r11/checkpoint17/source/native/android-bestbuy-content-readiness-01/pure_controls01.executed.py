#!/usr/bin/env python3
"""Local synthetic readiness/original-Session controls; no device or private UI reads."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import types

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
CANDIDATE=HERE/'candidate'


def load(path,name):
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),module.__dict__)
    return module


def main():
    r=load(CANDIDATE/'bestbuy_readiness.py','candidate_readiness_controls')
    context=load(CANDIDATE/'bestbuy_task_context.py','candidate_policy_controls')
    worker=load(CANDIDATE/'owned_inspect.py','candidate_worker_plan_controls')
    qa_path=BASE/'owned-bestbuy-qa-r1-build01/source/qa_contract.py'
    adapter_path=BASE/'owned-bestbuy-qa-r1-build01/source/qa_adapter.py'
    assert hashlib.sha256(qa_path.read_bytes()).hexdigest()=='e751f26cba0e02258427216fdc69fb8cbfdd673623148c3700ea2dbe35364195'
    assert hashlib.sha256(adapter_path.read_bytes()).hexdigest()=='ba7b2a87301c9753a5d23b7aa384f918488e4943002ed682552ce8e9ddd2283f'
    qa=load(qa_path,'original_bestbuy_pure_contract')
    adapter=load(adapter_path,'original_bestbuy_session')
    cases=[]
    def passed(name):cases.append({'case':name,'passed':True})
    def rejected(name,call,reason=None):
        try:call()
        except RuntimeError as error:
            if reason is not None:assert str(error)==reason,(name,str(error))
            passed(name);return error
        raise AssertionError(name+' accepted')
    def defs(path):
        return {x.name:ast.dump(x,include_attributes=False) for x in ast.parse(path.read_text()).body
                if isinstance(x,(ast.FunctionDef,ast.ClassDef))}
    old=defs(BASE/'android-bestbuy-launch-inspect-01/bestbuy_task_context.py')
    new=defs(CANDIDATE/'bestbuy_task_context.py')
    assert old['Flow']==new['Flow'] and old['open_task_context']==new['open_task_context']
    original=defs(BASE/'android-bestbuy-launch01-public-roles-reader-01/read_roles.py')
    current=defs(CANDIDATE/'bestbuy_readiness.py')
    for name in ('need','sha','no_raw_ui','validated_assessment','public_role_counts'):
        assert original[name]==current[name],name
    passed('Flow_open_context_and_original_public_count_validators_AST_unchanged')
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
    meta_path=BASE/'root-recovery-20261104-02/evidence/bestbuy-launch-five-results-read01/inspect.json'
    raw=meta_path.read_bytes()
    assert len(raw)==21067 and hashlib.sha256(raw).hexdigest()=='95b15ea5f365c7a672cffa446ddb39faed675388ed7b123c84db8f55f818fd14'
    safe=json.loads(raw);plan=worker.PLANS[0]
    inspection=copy.deepcopy(ready)
    inspection['connection_scoped_window_id']=safe['assessments']['inspect']['connection_scoped_window_id']
    refresh(inspection)
    sequence=copy.deepcopy(safe['sequence'])
    metadata=copy.deepcopy(safe['assessments'])
    counters=copy.deepcopy(metadata['inspect']['tree_observations'])
    counters[0]['attempted_nodes']=counters[0]['emitted_nodes']=len(inspection['nodes'])
    counters[0]['serialized_bytes']=len(qa.canonical(inspection))
    before_state=sequence['accessibility_restoration']['state_before']
    helper={'protocol':qa.PROTOCOL,'nonce':plan['nonces']['inspect'],'op':'inspect','self_uid':10198,
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

    step=Path('/synthetic-bestbuy-control-step')
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
            h={'op':op,'nonce':request['nonce'],'self_uid':10198}
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
    worker_tree=ast.parse((CANDIDATE/'owned_inspect.py').read_text())
    collect=next(x for x in ast.walk(worker_tree) if isinstance(x,ast.FunctionDef) and x.name=='collect_round')
    body=ast.unparse(collect)
    assert body.index('session = None')<body.index('session = q.adapter.Session')<body.index('flow.policy.begin_round')
    assert "'semantic_ready'" in (CANDIDATE/'owned_inspect.py').read_text()
    assert worker.PHASE_SECONDS=={'launch':175,'inspect':175,'cleanup':115}
    passed('production_round_constructor_clears_stale_reference_and_original_phase_deadlines_remain')
    report={'schema':1,'ok':True,'count':len(cases),'cases':cases,
        'original_BestBuy_contract_functions_executed':True,
        'original_Session_sequence_executed_with_local_IO_subclass_only':True,
        'production_Flow_open_task_context_and_shared_helper_sources_unchanged':True,
        'private_retained_assessment_or_raw_commercial_UI_read':False,
        'Android_Hepta_process_or_UI_calls':0,'remote_qualification_performed':False}
    print(json.dumps(report,indent=2,sort_keys=True))


if __name__=='__main__':main()
