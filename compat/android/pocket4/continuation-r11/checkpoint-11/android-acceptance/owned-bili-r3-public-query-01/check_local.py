#!/usr/bin/env python3
"""Narrow current-value and first-error controls; no device commands or UI.

The private historical tree is read only to verify real selector provenance.
Any changed input used below is an explicitly synthetic in-memory fixture;
no raw node text or commercial tree is emitted or copied into this package.
"""
import ast
import copy
import hashlib
import json
from pathlib import Path
import types

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
OLD=BASE/'android-bili-r3-stable-search-entry-01'
QA=BASE/'owned-bili-qa-r3-search-01/source'
PRIVATE=BASE/'root-recovery-20261104-02/private/qa-r3-stable-search01-tree/private-tree.json'

def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(path,name):
    m=types.ModuleType(name);m.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__);return m
def funcs(path):return {n.name:n for n in ast.parse(path.read_bytes()).body if isinstance(n,ast.FunctionDef)}
def same(a,b):return ast.dump(a,include_attributes=False)==ast.dump(b,include_attributes=False)

def run():
    m=load(HERE/'owned_navigation.py','query_controller')
    old=load(OLD/'owned_navigation.py','stable_controller')
    qa=load(QA/'qa_contract.py','pinned_r3_contract')
    adapter=load(QA/'qa_adapter.py','pinned_r3_adapter')
    prior=load(BASE/'android-qa-r3-install-state-01/install_state.py','actual_install_source')
    assert sha((QA/'qa_contract.py').read_bytes())=='6789ec1fef825d9738a6f59a14611dc2d60adc994b093f1ee4cfa9eb75ef9470'
    assert sha((QA/'qa_adapter.py').read_bytes())=='f58ee613069a6e8e4d6f1aa7c6532f2faeb5790a70564d294591444fa7de1767'
    rows=[]
    f,o=funcs(HERE/'owned_navigation.py'),funcs(OLD/'owned_navigation.py')
    names=['require','sha','read','require_actual_install_binding','load_prior','verify_source',
           'actual_install','new_session','stable_before_click','navigation_sequences','owned_scope']
    for name in names:assert same(f[name],o[name]),name
    for name in ('execute','worker'):
        left=next(n.finalbody for n in f[name].body if isinstance(n,ast.Try))
        right=next(n.finalbody for n in o[name].body if isinstance(n,ast.Try))
        assert same(ast.Module(body=left,type_ignores=[]),ast.Module(body=right,type_ignores=[])),name
    bindings=['SELF','UID','BILI','BILI_UID','INSTALL_ROOT','INSTALL_SOURCE','INSTALL_ENTRY_SHA',
        'INSTALL_ENTRY_BYTES','INSTALL_MANIFEST_SHA','R4_MANIFEST','SESSION_SHA','OLD_FLOW','OLD_STEP',
        'OLD_STATE_NONCE','OLD_STATE_WIRE','OLD_PACKET','MAIN_EPOCH','INSTALL_JOB_ID',
        'STATE_COMMAND_INDEX','STATE_COMMAND_SHA','EXPECTED_INSTALLED_IDENTITY','INSTALL_RECORDS']
    for name in bindings:assert getattr(m,name)==getattr(old,name),name
    rows.append({'control':'original_install_identity_entry_stability_and_cleanup_preserved',
        'passed':True,'unchanged_functions':names,'worker_and_coordinator_finally_AST_identical':True,
        'session_and_java_source_changed':False})
    m.verify_source(sha((HERE/'SOURCE_PINS.json').read_bytes()));m.fixed_plan()
    plans=[m.PLAN,m.POST_PLAN,m.SET_TEXT_PLAN,m.SUBMIT_PLAN,m.RESULTS_PLAN,
           *m.STABILITY_PLANS,*m.QUERY_STABILITY_PLANS,*m.SUBMIT_STABILITY_PLANS]
    nonces={m.NONCE,*(n for p in plans for n in p['nonces'].values())}
    assert len(nonces)==55 and all(adapter.validate_plan(p,qa)==p for p in plans)
    assert set(json.loads((HERE/'new-nonces.json').read_bytes()).values())==nonces
    old_nonces=set(json.loads((OLD/'new-nonces.json').read_bytes()).values())
    assert not old_nonces&nonces
    rows.append({'control':'actual_r3_plan_validator_all_seventeen_plans_and_fifty_five_nonces',
        'passed':True,'clicks_at_most':2,'fixed_public_edits_at_most':1,'all_other_plans_read_only':True})
    raw=PRIVATE.read_bytes()
    assert len(raw)==26771 and sha(raw)=='cc93bc42d606cae55308086f602a084a710e00d8a25a5fcccdf4611a43dacc10'
    private=json.loads(raw);inspection=qa.inspect_record(private['inspection'])
    edit=qa.select_unique_editable(inspection,m.EDIT_SELECTOR)
    button=qa.select_unique_clickable(inspection,m.SUBMIT_SELECTOR)
    assert private['scope']['activity']==m.SEARCH_ACTIVITY
    rows.append({'control':'actual_private_search_page_selectors_proved_with_pinned_contract',
        'passed':True,'historical_tree_sha256':private['inspection']['tree_sha256'],
        'node_count':len(inspection['nodes']),'edit_resource':m.EDIT_SELECTOR['resource_id'],
        'submit_resource':m.SUBMIT_SELECTOR['resource_id'],'raw_node_or_input_text_exported':False})
    installed=m.EXPECTED_INSTALLED_IDENTITY;scope=private['scope']

    def inspected_fixture(public):
        # Deliberately owned fixture data. No mutated tree is saved or printed.
        value=copy.deepcopy(inspection)
        node=next(n for n in value['nodes'] if n['path']==edit['node_path'])
        node['text']=m.PUBLIC_QUERY if public else 'owned-fixture-other-value'
        node['text_truncated']=False;node['text_sha256']=sha(node['text'].encode())
        node['node_sha256']=sha(qa.canonical({k:v for k,v in node.items() if k!='node_sha256'}))
        value['tree_sha256']=sha(qa.canonical(value['nodes']))
        qa.inspect_record(value)
        return value

    def original_session(public,fail_after=False):
        value=inspected_fixture(public);calls=[]
        session=adapter.Session.__new__(adapter.Session)
        session.qa=qa;session.installed=lambda:installed
        session.task=lambda:{'task':1,'owned_fixture':True}
        session.foreground=lambda:scope
        state={'accessibility_enabled':False,'touch_exploration_enabled':False,
               'enabled_service_count':0,'enabled_services_sha256':sha(b'owned-fixture')}
        def instrument(request):
            op=request['op'];calls.append(op)
            if fail_after and request['nonce']==m.SUBMIT_PLAN['nonces']['after']:
                raise RuntimeError('OWNED_AFTER_STATE_FAILURE')
            helper={'op':op,'nonce':request['nonce'],'self_uid':m.UID,
                    'ui_automation_connected':op!='state'}
            if op=='state':helper['state']=state
            else:
                helper.update(accessibility_state_before_connection=state,
                              restoration={'service_info_verified':True})
                if op=='inspect':helper['inspection']=value
                elif op=='click':helper['action_window']=value['window']
                else:raise AssertionError('unexpected operation')
            return {'helper':helper,'wire_sha256':sha(qa.canonical(helper))}
        session.instrument=instrument
        return session,calls,value

    # The prior algorithm permits a changed query when the new inspect and
    # action tree match. The new predicate must reject that exact situation.
    baseline,calls,_=original_session(False)
    baseline_result=baseline.sequence(copy.deepcopy(m.SUBMIT_PLAN))
    assert baseline_result['click_acknowledged'] is True and calls==['state','inspect','click','state']
    fixed,calls,value=original_session(False);observed={};caught=None
    try:m.submit_current_public_query(fixed,qa,observed)
    except RuntimeError as error:caught=error
    assert caught is not None and str(caught)=='ACTION_BOUND_PUBLIC_QUERY_VALUE_REQUIRED'
    assert calls==['state','inspect','state'] and fixed.qa is qa
    assert fixed.sequence_observation['after_state_completed'] is True
    assert fixed.sequence_observation['error']['message']=='ACTION_BOUND_PUBLIC_QUERY_VALUE_REQUIRED'
    assert 'submit_action_bound_value' not in observed
    rows.append({'control':'actual_original_Session_changed_submit_value_old_red_new_rejected',
        'passed':True,'original_click_count':1,'new_click_count':0,'new_after_state_completed':True,
        'contract_restored':True,'explicit_seams':['Session installed/task/foreground/instrument I/O',
          'owned in-memory input value; no Android; original Session.sequence and selectors are actual code']})

    good,calls,value=original_session(True);observed={}
    success=m.submit_current_public_query(good,qa,observed)
    assert calls==['state','inspect','click','state'] and good.qa is qa
    assert success['click_acknowledged'] is True and success['restoration_qualified'] is True
    assert observed['submit_action_bound_value']['tree_sha256']==value['tree_sha256']
    assert observed['submit_action_bound_value']['public_value_observed'] is True
    rows.append({'control':'actual_original_Session_exact_public_value_one_click_then_after_state',
        'passed':True,'operations':calls,'synthetic_input_not_device_evidence':True,'contract_restored':True})

    failed,calls,_=original_session(False,True);caught=None
    try:m.submit_current_public_query(failed,qa,{})
    except RuntimeError as error:caught=error
    assert str(caught)=='ACTION_BOUND_PUBLIC_QUERY_VALUE_REQUIRED' and calls==['state','inspect','state']
    assert failed.qa is qa and failed.sequence_observation['after_state_attempted'] is True
    assert failed.sequence_observation['secondary_errors'][0]['message']=='OWNED_AFTER_STATE_FAILURE'
    rows.append({'control':'actual_original_Session_value_failure_plus_after_failure_preserves_primary',
        'passed':True,'click_count':0,'after_state_attempted':True,'secondary_retained':True,'contract_restored':True})

    # Exercise the production receipt consumer, with the file read explicitly
    # routed to a synthetic assessed wrapper around the real historical tree.
    helper={'protocol':qa.PROTOCOL,'nonce':m.POST_PLAN['nonces']['inspect'],'self_uid':m.UID,
        'op':'inspect','ok':True,'error':None,'secondary_errors':[],
        'host_scope_attestation':scope,'inspection':inspection}
    assessed={'helper':helper,'actual_command_returncode':0,'actual_instrumentation_finish_code':-1,
        'wire_sha256':sha(qa.canonical(helper)),'held_transport_returned_after_post_guard':True}
    material=json.dumps(assessed,sort_keys=True).encode()
    summary={'inspect':{'nonce':helper['nonce'],'assessment_sha256':sha(material),
        'assessment_bytes':len(material),'wire_sha256':assessed['wire_sha256']}}
    original_read=m.read
    def routed_read(path,maximum,expected,size):
        assert path==Path('/owned-fixture')/(helper['nonce']+'.assessment.json')
        assert expected==sha(material) and size==len(material) and len(material)<=maximum
        return material
    m.read=routed_read
    try:
        sequence={'foreground_before':scope,'foreground_after':scope}
        proof=m.search_page_evidence(qa,Path('/owned-fixture'),sequence,summary,False)
        assert proof['public_value_observed'] is False
        caught=None
        try:m.search_page_evidence(qa,Path('/owned-fixture'),sequence,summary,True)
        except RuntimeError as error:caught=error
        assert str(caught)=='CURRENT_PUBLIC_QUERY_VALUE_NOT_OBSERVED'
    finally:m.read=original_read
    rows.append({'control':'production_search_page_consumer_does_not_infer_public_value_from_selector',
        'passed':True,'historical_selector_acceptance':True,'nonpublic_input_rejected':True,
        'explicit_seams':['read routed to owned assessed wrapper; actual historical inspection unchanged'],
        'raw_node_or_input_text_exported':False})

    originals={name:getattr(m,name) for name in ('navigation_sequences','search_page_evidence',
        'stable_search_page','assessment_summary','submit_current_public_query')}
    cases=['entry_failure','entry_page_failure','edit_failure','value_postcondition_failure',
           'submit_failure','edit_and_final_read_failure','successful_sequence']
    for case in cases:
        class Session:
            def __init__(self):self.calls=[]
            def foreground(self):return scope
            def sequence(self,plan):
                op=plan['operation'];self.calls.append(op)
                self.sequence_observation={'explicit_no_device_seam':True,'op':op}
                if op=='set_text' and case in ('edit_failure','edit_and_final_read_failure'):
                    raise RuntimeError('PRIMARY_EDIT_FAILURE')
                if op=='click' and case=='submit_failure':raise RuntimeError('PRIMARY_SUBMIT_FAILURE')
                if op=='inspect' and case=='edit_and_final_read_failure':raise RuntimeError('SECONDARY_RESULTS_FAILURE')
                return {'installed_before':installed,'installed_after':installed,
                    'restoration_qualified':True,'after_state_completed':True,
                    'foreground_before':scope,'foreground_after':scope,
                    'set_text_acknowledged':op=='set_text','click_acknowledged':op=='click'}
        def entry(_prior,_qa,_flow,_session,_installed,result):
            if case=='entry_failure':prior.remember(result,'original_entry',RuntimeError('PRIMARY_ENTRY_FAILURE'))
            else:result.update(post_inspection_sequence={},post_assessments={})
        def page(*args):
            if case=='entry_page_failure':raise RuntimeError('PRIMARY_SEARCH_PAGE_FAILURE')
            return {'public_value_observed':False}
        def stability(_prior,_qa,_flow,_session,_installed,result,phase,plans,public):
            if phase=='before_submit' and case=='value_postcondition_failure':
                raise RuntimeError('CURRENT_PUBLIC_QUERY_VALUE_NOT_OBSERVED')
            return {'public_value_observed':public}
        def summary(*args):return {'inspect':{'tree_sha256':'a'*64,'window_sha256':'b'*64}}
        def submit(session,_qa,result):
            result['submit_action_bound_value']={'tree_sha256':'a'*64,'window_sha256':'b'*64}
            return session.sequence(m.SUBMIT_PLAN)
        m.navigation_sequences=entry;m.search_page_evidence=page;m.stable_search_page=stability
        m.assessment_summary=summary;m.submit_current_public_query=submit
        session=Session();result={'ok':False,'error':None,'secondary_errors':[]}
        try:m.public_query_sequences(prior,qa,types.SimpleNamespace(step=Path('/not-opened')),session,installed,result)
        finally:
            for name,value in originals.items():setattr(m,name,value)
        assert session.calls.count('set_text')<=1 and session.calls.count('click')<=1
        if case=='entry_failure':
            assert session.calls==[] and not result['public_query_sequences_started']
        else:
            assert session.calls[-1]=='inspect' and result['final_results_inspection_attempted'] is True
        if case=='successful_sequence':
            assert session.calls==['set_text','click','inspect'] and result['query_submission_controls_completed'] is True
            assert result['error'] is None and result['secondary_errors']==[] and result['business_outcome_unknown'] is True
        else:
            assert result['query_submission_controls_completed'] is False and result['error'] is not None
            if case in ('entry_page_failure','edit_failure','edit_and_final_read_failure','value_postcondition_failure'):
                assert 'click' not in session.calls
            if case=='edit_and_final_read_failure':
                assert result['error']['message']=='PRIMARY_EDIT_FAILURE'
                assert result['secondary_errors'][0]['message']=='SECONDARY_RESULTS_FAILURE'
            else:assert result['secondary_errors']==[]
        rows.append({'control':'actual_public_query_routing_'+case,'passed':True,'operations':session.calls,
            'explicit_seams':['original entry observation','search evidence/stability','Session.sequence I/O',
                'assessment materialization; actual submit boundary separately tested above'],
            'failed_action_replayed':False,'independent_final_read_attempted':case!='entry_failure'})
    return {'schema':1,'state':'LOCAL_PUBLIC_QUERY_CONTROLS_PASS','count':len(rows),'controls':rows,
        'source_sha256':sha((HERE/'owned_navigation.py').read_bytes()),'Android_actions':0,'remote_actions':0,
        'actual_query_run':False,'raw_commercial_UI_exported':False,'whole_app_production_ready':False}

if __name__=='__main__':print(json.dumps(run(),sort_keys=True,indent=2))
