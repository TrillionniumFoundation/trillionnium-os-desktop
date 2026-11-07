#!/usr/bin/env python3
"""Narrow controls of the actual stability function and failure path; no device."""
import ast
import hashlib
import json
from pathlib import Path
import types

HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'android-bili-r3-search-entry-01'
QA=HERE.parent/'owned-bili-qa-r3-search-01/source'

def sha(b):return hashlib.sha256(b).hexdigest()
def load(path,name):
    m=types.ModuleType(name);m.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__);return m
def ast_functions(path):return {n.name:n for n in ast.parse(path.read_bytes()).body if isinstance(n,ast.FunctionDef)}
def same(a,b):return ast.dump(a,include_attributes=False)==ast.dump(b,include_attributes=False)

def run():
    m=load(HERE/'owned_navigation.py','stable_controller')
    old=load(OLD/'owned_navigation.py','prior_controller')
    qa=load(QA/'qa_contract.py','exact_r3_contract')
    adapter=load(QA/'qa_adapter.py','exact_r3_adapter')
    prior=load(HERE.parent/'android-qa-r3-install-state-01/install_state.py','actual_install_source')
    rows=[]
    functions=ast_functions(HERE/'owned_navigation.py');original=ast_functions(OLD/'owned_navigation.py')
    unchanged=['read','require_actual_install_binding','load_prior','actual_install','new_session','assessment_summary','owned_scope','verify_source']
    for name in unchanged:assert same(functions[name],original[name]),name
    for name in ('execute','worker'):
        left=next(n.finalbody for n in functions[name].body if isinstance(n,ast.Try))
        right=next(n.finalbody for n in original[name].body if isinstance(n,ast.Try))
        assert same(ast.Module(body=left,type_ignores=[]),ast.Module(body=right,type_ignores=[])),name
    identity_names=['SELF','UID','BILI','BILI_UID','INSTALL_ROOT','INSTALL_SOURCE','INSTALL_ENTRY_SHA','INSTALL_ENTRY_BYTES','INSTALL_MANIFEST_SHA','R4_MANIFEST','SESSION_SHA','OLD_FLOW','OLD_STEP','OLD_STATE_NONCE','OLD_STATE_WIRE','OLD_PACKET','MAIN_EPOCH','INSTALL_JOB_ID','STATE_COMMAND_INDEX','STATE_COMMAND_SHA','EXPECTED_INSTALLED_IDENTITY','INSTALL_RECORDS']
    for name in identity_names:assert getattr(m,name)==getattr(old,name),name
    original_receipt=(OLD/'local-controls.json').read_bytes()
    assert sha(original_receipt)=='00efbca8758f16a64491793598dec1f2f55e4c338606fbc3578aef6d65cd9d80'
    assert json.loads(original_receipt)['controls'][0]['control']=='actual_r3_build_install_state_consumer_pass'
    rows.append({'control':'actual_install_consumer_and_all_identity_constants_preserved','passed':True,
        'earlier_actual_consumer_receipt_sha256':sha(original_receipt),'earlier_receipt_not_relabelled_as_new_device_run':True,
        'unchanged_functions':unchanged,'original_worker_and_coordinator_finally_AST_unchanged':True})
    manifest=sha((HERE/'SOURCE_PINS.json').read_bytes());m.verify_source(manifest)
    m.require_actual_install_binding();m.fixed_plan()
    all_nonces={m.NONCE,*m.PLAN['nonces'].values(),*m.POST_PLAN['nonces'].values(),*(n for p in m.STABILITY_PLANS for n in p['nonces'].values())}
    assert len(all_nonces)==20
    assert not all_nonces&{old.NONCE,*old.PLAN['nonces'].values(),*old.POST_PLAN['nonces'].values(),old.OLD_STATE_NONCE}
    for plan in [m.PLAN,m.POST_PLAN,*m.STABILITY_PLANS]:adapter.validate_plan(plan,qa)
    assert len(m.STABILITY_PLANS)==4 and all(p['operation']=='inspect' for p in m.STABILITY_PLANS)
    rows.append({'control':'actual_five_source_manifest_and_twenty_distinct_nonce_plans','passed':True,
        'actual_r3_plan_validator':True,'read_only_stability_sequences':4,'click_limit':1,'set_text_actions':0})
    installed=m.EXPECTED_INSTALLED_IDENTITY
    actual_summary=m.assessment_summary;actual_clock=m.time.monotonic
    cases=[('changed_then_stable',['a','b','b'],None,False,False),
           ('never_stable',['a','b','c','d'],None,False,False),
           ('failed_read_is_not_retried',['a','b'],2,False,False),
           ('strict_action_failure_after_stability',['a','a'],None,True,False),
           ('deadline_after_joined_observation',['a','a'],None,False,True)]
    for name,hashes,read_fail,click_fail,deadline in cases:
        class Session:
            def __init__(self):self.calls=[];self.reads=0
            def sequence(self,plan):
                is_stable=plan['nonces']['inspect'] in {p['nonces']['inspect'] for p in m.STABILITY_PLANS}
                kind='stability' if is_stable else plan['operation']
                self.calls.append(kind);self.sequence_observation={'explicit_observer_seam':True,'kind':kind}
                if is_stable:
                    self.reads+=1
                    if self.reads==read_fail:raise RuntimeError('PRIMARY_READ_FAILURE')
                    label=hashes[self.reads-1]
                else:label='z'
                if kind=='click' and click_fail:raise RuntimeError('INSPECTED_TREE_OR_WINDOW_CHANGED')
                return {'installed_before':installed,'installed_after':installed,'click_acknowledged':kind=='click',
                    'restoration_qualified':True,'after_state_completed':True,
                    'foreground_after':{'package':m.BILI,'uid':m.BILI_UID,'window_token':'explicit-owned-fixture'},
                    'accessibility_restoration':{'state_after':{'accessibility_enabled':False}},'_test_label':label}
        def summary(_prior,_qa,_step,seq,_plan):
            return {'inspect':{'tree_sha256':seq['_test_label']*64,'window_sha256':'f'*64,'node_count':156}}
        clock_values=iter([0.0,0.0,13.0,13.0])
        m.assessment_summary=summary
        m.time.monotonic=(lambda:next(clock_values)) if deadline else (lambda:0.0)
        session=Session();result={'ok':False,'error':None,'secondary_errors':[]}
        try:m.navigation_sequences(prior,qa,types.SimpleNamespace(step=Path('/not-opened')),session,installed,result)
        finally:m.assessment_summary=actual_summary;m.time.monotonic=actual_clock
        assert session.calls[-1]=='inspect' and result['post_inspection_attempted'] is True
        assert result['business_outcome_unknown'] is True and result['next_business_action_requires_new_observation_and_admission'] is True
        assert session.calls.count('click')<=1 and result['secondary_errors']==[]
        if name=='changed_then_stable':
            assert session.calls==['stability','stability','stability','click','inspect']
            assert result['pre_action_stability']['matching_sequences']==[2,3]
            assert result['scoped_click_and_post_observation_completed'] is True and result['error'] is None
        elif name=='strict_action_failure_after_stability':
            assert session.calls==['stability','stability','click','inspect']
            assert result['error']['message']=='INSPECTED_TREE_OR_WINDOW_CHANGED'
            assert result['pre_action_stability']['qualified'] is True and result['scoped_click_and_post_observation_completed'] is False
        else:
            assert 'click' not in session.calls and result['click_sequence_started'] is False
            assert result['error']['phase']=='pre_action_stability' and not result['pre_action_stability']['qualified']
            expected={'never_stable':'COMPLETE_TREE_NOT_STABLE_IN_BOUNDED_READS','failed_read_is_not_retried':'PRIMARY_READ_FAILURE','deadline_after_joined_observation':'STABILITY_OBSERVATION_DEADLINE'}[name]
            assert result['error']['message']==expected and not result['scoped_click_and_post_observation_completed']
            assert session.calls.count('stability')==({'never_stable':4,'failed_read_is_not_retried':2,'deadline_after_joined_observation':1}[name])
        rows.append({'control':'actual_stability_function_'+name,'passed':True,'operations':session.calls,
            'explicit_seams':['Session.sequence observations/no Android','assessment_summary materialization/no private file','monotonic clock'],
            'original_strict_action_failure_not_converted_to_success':name=='strict_action_failure_after_stability'})
    for name in ('stage_execute.py','make_request.py'):
        a,b=ast_functions(HERE/name),ast_functions(OLD/name)
        assert set(a)==set(b) and all(same(a[k],b[k]) for k in a)
    rows.append({'control':'stage_and_generator_function_AST_unchanged','passed':True})
    return {'schema':1,'state':'LOCAL_STABILITY_CONTROLS_PASS','count':len(rows),'controls':rows,
        'source_sha256':sha((HERE/'owned_navigation.py').read_bytes()),'Android_actions':0,'remote_actions':0,
        'raw_commercial_UI_exported':False,'actual_stable_click_run':False,'whole_app_production_ready':False}

if __name__=='__main__':print(json.dumps(run(),sort_keys=True,indent=2))
