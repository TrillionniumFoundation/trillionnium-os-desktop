#!/usr/bin/env python3
"""Actual loading classifier and bounded observer controls, without Android."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import types

HERE=Path(__file__).resolve().parent
B=HERE.parent
OLD=B/'android-bili-r3-public-query-01'
QA=B/'owned-bili-qa-r3-search-01/source'
PRIVATE=B/'root-recovery-20261104-02/private/qa-r3-public-query01-tree/private-tree.json'
def sha(x):return hashlib.sha256(x).hexdigest()
def load(path,name):
    m=types.ModuleType(name);m.__file__=str(path);exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__);return m
def funcs(p):return {n.name:n for n in ast.parse(p.read_bytes()).body if isinstance(n,ast.FunctionDef)}
def same(a,b):return ast.dump(a,include_attributes=False)==ast.dump(b,include_attributes=False)

def run():
    m=load(HERE/'owned_navigation.py','results_observer')
    old=load(OLD/'owned_navigation.py','query_controller')
    qa=load(QA/'qa_contract.py','pinned_contract');adapter=load(QA/'qa_adapter.py','pinned_adapter')
    f,o=funcs(HERE/'owned_navigation.py'),funcs(OLD/'owned_navigation.py')
    changed={'fixed_plan','worker','durable_phase','execute','main'}
    unchanged=sorted(set(o)-changed)
    for name in unchanged:assert same(f[name],o[name]),name
    for name in ('worker','execute'):
        a=next(n.finalbody for n in f[name].body if isinstance(n,ast.Try))
        b=next(n.finalbody for n in o[name].body if isinstance(n,ast.Try))
        assert same(ast.Module(body=a,type_ignores=[]),ast.Module(body=b,type_ignores=[]))
    for name in ('UID','SELF','MAIN_EPOCH','INSTALL_RECORDS','EXPECTED_INSTALLED_IDENTITY','R4_MANIFEST','SESSION_SHA'):
        assert getattr(m,name)==getattr(old,name)
    rows=[{'control':'unchanged_actual_query_actions_submit_predicate_and_finally_cleanup',
        'passed':True,'unchanged_functions':unchanged,'worker_and_coordinator_finally_AST_identical':True}]
    m.verify_source(sha((HERE/'SOURCE_PINS.json').read_bytes()));m.fixed_plan()
    plans=[m.PLAN,m.POST_PLAN,m.SET_TEXT_PLAN,m.SUBMIT_PLAN,m.RESULTS_PLAN,
        *m.STABILITY_PLANS,*m.QUERY_STABILITY_PLANS,*m.SUBMIT_STABILITY_PLANS,*m.RESULT_OBSERVATION_PLANS]
    assert len(plans)==25 and all(adapter.validate_plan(p,qa)==p for p in plans)
    nonces={m.NONCE,*(n for p in plans for n in p['nonces'].values())}
    assert len(nonces)==79 and not nonces&set(json.loads((OLD/'new-nonces.json').read_bytes()).values())
    assert len(m.RESULT_OBSERVATION_PLANS)==8 and all(p['operation']=='inspect' for p in m.RESULT_OBSERVATION_PLANS)
    rows.append({'control':'seventy_nine_fresh_nonces_and_only_read_only_added_plans','passed':True,
        'actual_pinned_adapter_plan_validator':True,'new_business_actions':0})
    raw=PRIVATE.read_bytes()
    assert len(raw)==27699 and sha(raw)=='8e984063e8035766326dac2824094956980a408c140268595635d52ab9386934'
    private=json.loads(raw);inspection=private['inspection'];scope=private['scope']
    proof=m.results_content_evidence(qa,inspection,scope)
    assert not proof['container_content_observed'] and proof['loading_control_count']==2 and proof['visible_pager_descendants']==0
    rows.append({'control':'actual_complete_twenty_eight_node_loading_tree_is_not_content',
        'passed':True,'loading_controls':2,'pager_descendants':0,'private_tree_external_sha256':sha(raw)})

    def fixture(loading,child,public=True):
        value=copy.deepcopy(inspection);nodes=value['nodes']
        load_root=next(n['path'] for n in nodes if n['resource_id']=='tv.danmaku.bili:id/loading_view')
        if not loading:
            nodes[:]=[n for n in nodes if n['path']!=load_root and not n['path'].startswith(load_root+'/')]
        pager=next(n for n in nodes if n['resource_id']=='tv.danmaku.bili:id/pager')
        if child:
            nodes.append({'path':pager['path']+'/0','package':m.BILI,'resource_id':'',
                'class':'android.view.View','visible':True,'enabled':True,'password':False,
                'editable':False,'supports_set_text':False,'clickable':False,'child_count':0})
        if not public:
            marker=next(n for n in nodes if n['resource_id']=='tv.danmaku.bili:id/search_fake_text')
            marker['text']='owned-fixture-other-query';marker['text_sha256']=sha(marker['text'].encode())
        for n in nodes:
            n['child_count']=sum(other['path'].rsplit('/',1)[0]==n['path'] for other in nodes if '/' in other['path'])
            n['node_sha256']=sha(qa.canonical({k:v for k,v in n.items() if k!='node_sha256'}))
        value['tree_sha256']=sha(qa.canonical(nodes));qa.inspect_record(value)
        return value
    for name,loading,child,expected in [('no_loading_but_empty_pager',False,False,False),
        ('pager_child_while_loading',True,True,False),('pager_content_without_loading',False,True,True)]:
        proof=m.results_content_evidence(qa,fixture(loading,child),scope)
        assert proof['container_content_observed'] is expected and proof['video_or_search_result_success_inferred'] is False
        rows.append({'control':'actual_classifier_'+name,'passed':True,
            'owned_in_memory_fixture_only':True,'video_success_claimed':False})
    caught=None
    try:m.results_content_evidence(qa,fixture(False,True,False),scope)
    except RuntimeError as error:caught=error
    assert str(caught)=='RESULTS_PUBLIC_QUERY_MARKER_CHANGED'
    rows.append({'control':'actual_classifier_rejects_changed_public_query','passed':True,'owned_fixture_only':True})

    original_read=m.read;original_summary=m.assessment_summary;clock=m.time.monotonic
    for case in ('loading_then_content','never_content','failed_read_not_retried','deadline_after_joined_read'):
        material={};installed=m.EXPECTED_INSTALLED_IDENTITY
        def assessed(plan,content):
            helper={'protocol':qa.PROTOCOL,'nonce':plan['nonces']['inspect'],'self_uid':m.UID,
                'op':'inspect','ok':True,'error':None,'secondary_errors':[],
                'host_scope_attestation':scope,'inspection':fixture(not content,content)}
            value={'helper':helper,'wire_sha256':sha(qa.canonical(helper)),
                'actual_command_returncode':0,'actual_instrumentation_finish_code':-1,
                'held_transport_returned_after_post_guard':True}
            data=json.dumps(value,sort_keys=True).encode();path=Path('/owned-fixture')/(helper['nonce']+'.assessment.json')
            material[path]=data
            summaries={'inspect':{'nonce':helper['nonce'],'assessment_sha256':sha(data),
                'assessment_bytes':len(data),'wire_sha256':value['wire_sha256']}}
            sequence={'installed_before':installed,'installed_after':installed,'restoration_qualified':True,
                'after_state_completed':True,'foreground_before':scope,'foreground_after':scope,
                '_owned_summary':summaries}
            return sequence,summaries
        class Session:
            def __init__(self):self.calls=[]
            def sequence(self,plan):
                self.calls.append(plan['operation']);assert plan['operation']=='inspect'
                if case=='failed_read_not_retried':raise RuntimeError('PRIMARY_OWNED_READ_FAILURE')
                return assessed(plan,case=='loading_then_content' and len(self.calls)==2)[0]
        initial,summaries=assessed(m.RESULTS_PLAN,False)
        result={'results_inspection_sequence':initial,'results_assessments':summaries}
        def read(path,maximum,expected,size):
            data=material[path];assert expected==sha(data) and size==len(data) and size<=maximum;return data
        m.read=read;m.assessment_summary=lambda _p,_q,_s,seq,_plan:seq['_owned_summary']
        session=Session();m.time.monotonic=lambda:21.0 if case=='deadline_after_joined_read' and session.calls else 0.0
        caught=None
        try:m.observe_result_content(None,qa,types.SimpleNamespace(step=Path('/owned-fixture')),session,installed,result)
        except RuntimeError as error:caught=error
        finally:m.read=original_read;m.assessment_summary=original_summary;m.time.monotonic=clock
        assert all(op=='inspect' for op in session.calls)
        if case=='loading_then_content':
            assert caught is None and len(session.calls)==2 and result['results_container_content_observed'] is True
            assert result['result_content_observation']['selected_additional_sequence']==2
        else:
            assert caught is not None and not result['result_content_observation']['qualified']
            expected={'never_content':('RESULTS_CONTAINER_CONTENT_NOT_OBSERVED_IN_BOUNDED_READS',8),
                'failed_read_not_retried':('PRIMARY_OWNED_READ_FAILURE',1),
                'deadline_after_joined_read':('RESULTS_OBSERVATION_DEADLINE',1)}[case]
            assert str(caught)==expected[0] and len(session.calls)==expected[1]
            assert not result.get('results_container_content_observed',False)
        rows.append({'control':'actual_observer_'+case,'passed':True,'additional_read_sequences':len(session.calls),
            'submission_calls':0,'explicit_seams':['Session.sequence I/O','assessed file materialization','monotonic clock'],
            'actual_observer_and_classifier_executed':True})
    return {'schema':1,'state':'LOCAL_RESULTS_OBSERVATION_CONTROLS_PASS','count':len(rows),'controls':rows,
        'source_sha256':sha((HERE/'owned_navigation.py').read_bytes()),'raw_UI_exported':False,
        'Android_actions':0,'remote_actions':0,'actual_results_loaded_claimed':False,'whole_app_ready':False}

if __name__=='__main__':print(json.dumps(run(),sort_keys=True,indent=2))
