#!/usr/bin/env python3
"""Narrow actual selector/Session controls. No Android, sockets, UI or remote calls.

Only the pinned historical private tree is read. Mutated trees are explicit
in-memory fixtures and never emitted or saved. All external Session I/O is a
declared seam; Session.sequence and the contract code are the actual sources.
"""
import ast
import copy
import hashlib
import json
from pathlib import Path
import types

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
OLD=BASE/'android-bili-r3-results-observe-01'
QA=BASE/'owned-bili-qa-r3-search-01/source'
PRIVATE=BASE/'root-recovery-20261104-02/private/qa-r3-results-observe01-tree/private-tree.json'

def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(path,name):
    m=types.ModuleType(name);m.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__);return m
def funcs(path):return {n.name:n for n in ast.parse(path.read_bytes()).body if isinstance(n,ast.FunctionDef)}
def same(a,b):return ast.dump(a,include_attributes=False)==ast.dump(b,include_attributes=False)

def run():
    m=load(HERE/'owned_navigation.py','video_main')
    v=load(HERE/'video_navigation.py','video_module')
    old=load(OLD/'owned_navigation.py','old_main')
    qa=load(QA/'qa_contract.py','actual_contract')
    adapter=load(QA/'qa_adapter.py','actual_adapter')
    prior=load(BASE/'android-qa-r3-install-state-01/install_state.py','actual_install')
    assert sha((QA/'qa_contract.py').read_bytes())=='6789ec1fef825d9738a6f59a14611dc2d60adc994b093f1ee4cfa9eb75ef9470'
    assert sha((QA/'qa_adapter.py').read_bytes())=='f58ee613069a6e8e4d6f1aa7c6532f2faeb5790a70564d294591444fa7de1767'
    rows=[];f,o=funcs(HERE/'owned_navigation.py'),funcs(OLD/'owned_navigation.py')
    names=['require','sha','read','require_actual_install_binding','load_prior','fixed_plan',
        'actual_install','new_session','assessment_summary','stable_before_click','navigation_sequences',
        'search_page_evidence','stable_search_page','submit_current_public_query','public_query_sequences',
        'results_content_evidence','observe_result_content','owned_scope']
    for name in names:assert same(f[name],o[name]),name
    for name in ('execute','worker'):
        a=next(n.finalbody for n in f[name].body if isinstance(n,ast.Try))
        b=next(n.finalbody for n in o[name].body if isinstance(n,ast.Try))
        assert same(ast.Module(body=a,type_ignores=[]),ast.Module(body=b,type_ignores=[])),name
    for name in ('SELF','UID','BILI','BILI_UID','INSTALL_ROOT','INSTALL_SOURCE','INSTALL_ENTRY_SHA',
        'INSTALL_ENTRY_BYTES','INSTALL_MANIFEST_SHA','R4_MANIFEST','SESSION_SHA','OLD_FLOW','OLD_STEP',
        'OLD_STATE_NONCE','OLD_STATE_WIRE','OLD_PACKET','MAIN_EPOCH','INSTALL_JOB_ID','STATE_COMMAND_INDEX',
        'STATE_COMMAND_SHA','EXPECTED_INSTALLED_IDENTITY','INSTALL_RECORDS'):
        assert getattr(m,name)==getattr(old,name),name
    rows.append({'control':'eighteen_original_functions_and_both_finally_AST_unchanged','passed':True,
        'functions':names,'actual_install_bindings_identical':True,'Session_Java_changed':False})

    manifest=sha((HERE/'SOURCE_PINS.json').read_bytes());m.verify_source(manifest);m.fixed_plan()
    module=m.video_extension(manifest,adapter,qa)
    groups=[m.PLAN,m.POST_PLAN,m.SET_TEXT_PLAN,m.SUBMIT_PLAN,m.RESULTS_PLAN,*m.STABILITY_PLANS,
        *m.QUERY_STABILITY_PLANS,*m.SUBMIT_STABILITY_PLANS,*m.RESULT_OBSERVATION_PLANS]
    plans=[*groups,module.VIDEO_PLAN,*module.VIDEO_STABILITY_PLANS,*module.VIDEO_POST_PLANS]
    nonces={m.NONCE,*(n for p in plans for n in p['nonces'].values())}
    assert len(nonces)==104 and all(adapter.validate_plan(p,qa)==p for p in plans)
    assert set(json.loads((HERE/'new-nonces.json').read_bytes()).values())==nonces
    for p in BASE.glob('android-bili-r3-*/new-nonces.json'):
        if p.parent!=HERE:assert not nonces&set(json.loads(p.read_bytes()).values()),str(p)
    rows.append({'control':'exact_six_source_loader_and_104_fresh_valid_nonces','passed':True,
        'original_source_bound':65536,'original_packet_bound':131072,'business_clicks_maximum':3,
        'fixed_text_edits_maximum':1})

    raw=PRIVATE.read_bytes()
    assert len(raw)==160429 and sha(raw)=='1b3cdaf5f70f4eeef2adcbb2e45feb56e7891a2edab6d4ad3da84a012ee56f10'
    private=json.loads(raw);inspection=qa.inspect_record(private['inspection']);scope=private['scope']
    target,proof=v.select_course(m,qa,inspection,scope)
    assert target['node_sha256']=='a1d4aa5b97fc0c927bf3a37e79f5e431fe5befdc9c89266d115bc939f0a2c5c3'
    rows.append({'control':'actual_178_node_private_tree_exact_same_card_direct_parent','passed':True,
        'source_tree_sha256':sha(raw),'selection':proof,'raw_nodes_or_text_exported':False})

    def fixture(case):
        tree=copy.deepcopy(inspection);nodes=tree['nodes']
        title=next(n for n in nodes if n.get('resource_id')=='tv.danmaku.bili:id/title' and n.get('text_sha256')==v.TITLE_SHA)
        parent=next(n for n in nodes if n['path']==title['path'].rsplit('/',1)[0])
        author=next(n for n in nodes if n['path'].startswith(parent['path']+'/') and n.get('resource_id')=='tv.danmaku.bili:id/upuser')
        duration=next(n for n in nodes if n['path'].startswith(parent['path']+'/') and n.get('resource_id')=='tv.danmaku.bili:id/duration')
        if case in ('title_changed','author_changed','duration_changed'):
            n={'title_changed':title,'author_changed':author,'duration_changed':duration}[case]
            n['text']='owned-fixture-changed';n['text_sha256']=sha(n['text'].encode())
        elif case=='title_missing':nodes.remove(title)
        elif case=='title_duplicate':
            duplicate=copy.deepcopy(title);duplicate['path']=parent['path']+'/63';nodes.append(duplicate)
        elif case=='parent_not_clickable':parent['clickable']=False
        elif case=='author_wrong_card':author['path']='0/63'
        elif case!='valid':raise AssertionError(case)
        for n in nodes:n['node_sha256']=sha(qa.canonical({k:x for k,x in n.items()if k!='node_sha256'}))
        tree['tree_sha256']=sha(qa.canonical(nodes));qa.inspect_record(tree);return tree
    cases=['title_changed','title_missing','title_duplicate','author_changed','duration_changed',
        'parent_not_clickable','author_wrong_card']
    for case in cases:
        caught=None
        try:v.select_course(m,qa,fixture(case),scope)
        except RuntimeError as error:caught=error
        assert caught is not None,case
    rows.append({'control':'exact_predicate_rejects_seven_owned_mismatches','passed':True,'cases':cases,
        'explicit_fixture':'hash-valid in-memory changes to pinned historical tree; never stored or emitted',
        'fallback_used':False})
    caught=None
    try:qa.select_unique_clickable(inspection,v.CARD_SELECTOR)
    except qa.ProtocolError as error:caught=error
    assert caught is not None
    rows.append({'control':'class_only_original_selector_cannot_authorize_this_card','passed':True,
        'original_rejection':str(caught),'original_contract_unchanged':True})

    installed=m.EXPECTED_INSTALLED_IDENTITY
    def session_fixture(case,fail_after=False):
        value=fixture(case);calls=[];session=adapter.Session.__new__(adapter.Session)
        session.qa=qa;session.installed=lambda:installed;session.task=lambda:{'owned_fixture':1}
        session.foreground=lambda:scope
        state={'accessibility_enabled':False,'touch_exploration_enabled':False,
            'enabled_service_count':0,'enabled_services_sha256':sha(b'owned fixture')}
        def instrument(request):
            op=request['op'];calls.append(op)
            if fail_after and request['nonce']==v.VIDEO_PLAN['nonces']['after']:
                raise RuntimeError('OWNED_AFTER_STATE_FAILURE')
            helper={'op':op,'nonce':request['nonce'],'self_uid':m.UID,'ui_automation_connected':op!='state'}
            if op=='state':helper['state']=state
            else:
                helper.update(accessibility_state_before_connection=state,restoration={'service_info_verified':True})
                if op=='inspect':helper['inspection']=value
                elif op=='click':
                    assert request['node_path']==target['node_path']
                    helper['action_window']=value['window']
                else:raise AssertionError(op)
            return {'helper':helper,'wire_sha256':sha(qa.canonical(helper))}
        session.instrument=instrument;return session,calls
    for case,fail_after in [('valid',False),('author_changed',False),('title_changed',False),('author_changed',True)]:
        session,calls=session_fixture(case,fail_after);observed={};caught=None;success=None
        try:success=v.course_sequence(m,qa,session,observed)
        except RuntimeError as error:caught=error
        assert session.qa is qa
        if case=='valid':
            assert caught is None and calls==['state','inspect','click','state']
            assert success['click_acknowledged']and success['restoration_qualified']
            assert observed['video_action_bound_selection']['unique_title_and_same_card_identity']
        else:
            assert caught is not None and calls==['state','inspect','state']
            assert 'video_action_bound_selection'not in observed
            assert session.sequence_observation['after_state_attempted']is True
            assert session.sequence_observation['after_state_completed']is(not fail_after)
            if fail_after:
                assert str(caught)=='EXACT_SAME_CARD_UPLOADER_AND_DURATION_REQUIRED'
                assert session.sequence_observation['secondary_errors'][0]['message']=='OWNED_AFTER_STATE_FAILURE'
        rows.append({'control':'actual_Session_fresh_'+case+('_after_failure'if fail_after else ''),
            'passed':True,'operations':calls,'contract_restored':True,'click_count':calls.count('click'),
            'explicit_seams':['installed/task/foreground/instrument I/O only'],
            'primary_preserved':True,'Android_executed':False})

    original_stable=v.stable_course;original_course=v.course_sequence
    for case in ['success','stability_failure','click_failure','post_failure','click_and_post_failure']:
        result={'ok':False,'error':None,'secondary_errors':[],
            'query_submission_controls_completed':True,'results_container_content_observed':True}
        calls=[]
        class Session:
            sequence_observation={'explicit_fixture':True}
            def sequence(self,plan):
                calls.append(plan['operation'])
                if case in ('post_failure','click_and_post_failure'):raise RuntimeError('POST_FAILURE')
                return {'installed_before':installed,'installed_after':installed,'restoration_qualified':True,
                    'after_state_completed':True,'foreground_after':scope,'accessibility_restoration':{}}
        def stable(*args):
            if case=='stability_failure':raise RuntimeError('STABILITY_FAILURE')
        def course(*args):
            calls.append('click')
            if case in ('click_failure','click_and_post_failure'):raise RuntimeError('CLICK_FAILURE')
            result['video_action_bound_selection']={'current_tree_sha256':'a'*64,'current_window_sha256':'b'*64}
            return {'installed_before':installed,'installed_after':installed,'click_acknowledged':True,
                'restoration_qualified':True,'after_state_completed':True,'foreground_before':scope}
        b=types.SimpleNamespace(**m.__dict__)
        b.assessment_summary=lambda *args:{'inspect':{'tree_sha256':'a'*64,'window_sha256':'b'*64}}
        v.stable_course=stable;v.course_sequence=course
        try:v.run(b,prior,qa,None,Session(),installed,result)
        finally:v.stable_course=original_stable;v.course_sequence=original_course
        assert calls.count('click')<=1
        if case=='success':assert calls==['click','inspect','inspect','inspect']and result['video_click_and_observations_completed']
        else:
            assert calls.count('inspect')==1 and not result['video_click_and_observations_completed']
            assert result['error']is not None
            if case=='stability_failure':assert calls==['inspect']
            if case=='click_and_post_failure':
                assert result['error']['message']=='CLICK_FAILURE'
                assert result['secondary_errors'][0]['message']=='POST_FAILURE'
        assert result['playback_or_audio_success_inferred']is False
        rows.append({'control':'actual_video_run_routing_'+case,'passed':True,'operations':calls,
            'explicit_seams':['stability','course action','Session I/O','assessment summary'],
            'failed_action_replayed':False,'business_success_inferred':False})
    return {'schema':1,'state':'LOCAL_VIDEO_OPEN_CONTROLS_PASS','count':len(rows),'controls':rows,
        'source_manifest_sha256':manifest,'source_sha256':sha((HERE/'owned_navigation.py').read_bytes()),
        'module_sha256':sha((HERE/'video_navigation.py').read_bytes()),'remote_actions':0,'Android_actions':0,
        'raw_commercial_UI_exported':False,'actual_video_open_run':False,'whole_app_production_ready':False}

if __name__=='__main__':print(json.dumps(run(),sort_keys=True,indent=2))
