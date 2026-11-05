#!/usr/bin/env python3
"""Actual receipt consumer and narrow source controls; no Android execution."""
import ast
import hashlib
import json
from pathlib import Path
import types

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
OLD=BASE/'android-bili-r2-search-entry-01'
QA=BASE/'owned-bili-qa-r3-search-01/source'
INSTALL=BASE/'android-qa-r3-install-state-01'
EVIDENCE=BASE/'root-recovery-20261104-02/evidence/qa-r3-install01'
BUILD=BASE/'root-recovery-20261104-02/evidence/qa-r3-build01'

def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(path,name):
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),module.__dict__)
    return module
def funcs(path):
    return {n.name:n for n in ast.parse(path.read_bytes()).body if isinstance(n,ast.FunctionDef)}
def same(a,b):return ast.dump(a,include_attributes=False)==ast.dump(b,include_attributes=False)

def run():
    rows=[]
    m=load(HERE/'owned_navigation.py','r3_navigation_actual')
    qa=load(QA/'qa_contract.py','r3_qa_actual')
    adapter=load(QA/'qa_adapter.py','r3_adapter_actual')
    builder=load(QA/'build_candidate.py','r3_builder_actual')
    prior=load(INSTALL/'install_state.py','r3_install_actual')
    manifest_raw=(QA/'SOURCE_PINS.json').read_bytes()
    assert sha(manifest_raw)==prior.QA_MANIFEST
    manifest=json.loads(manifest_raw)
    for name,row in manifest['files'].items():
        raw=(QA/name).read_bytes()
        assert row=={'bytes':len(raw),'sha256':sha(raw)}
    args=types.SimpleNamespace(build_receipt=BUILD/'build-result.json',build_receipt_sha256=prior.BUILD_SHA,
        source_manifest_sha256=prior.QA_MANIFEST,apk_sha256=prior.APK_SHA,signer_certificate_sha256=prior.SIGNER_SHA)
    proof=adapter.qualified_build(args,manifest,builder)
    stage_raw=(BUILD/'stage-result.json').read_bytes()
    assert len(stage_raw)==prior.STAGE_BYTES and sha(stage_raw)==prior.STAGE_SHA
    stage=json.loads(stage_raw)
    assert stage['build_returncode']==0 and stage['error'] is None and stage['secondary_errors']==[]
    assert stage['build_result']=={'path':str(prior.BUILD),'bytes':prior.BUILD_BYTES,'sha256':prior.BUILD_SHA}
    proof['stage_receipt_sha256']=prior.STAGE_SHA
    reader_raw=(EVIDENCE/'reader-report.json').read_bytes()
    assert len(reader_raw)==27361 and sha(reader_raw)=='34824cb6c433f2c56dec1946a7ee0432b575c302d2f729545ca7aee836736581'
    reader=json.loads(reader_raw)
    mapping={}
    for name,row in reader['files'].items():
        path=EVIDENCE/name;raw=path.read_bytes()
        assert row['text'].encode('utf-8')==raw and len(raw)==row['bytes'] and sha(raw)==row['sha256']
        mapping[row['path']]=path
    original_read=m.read
    def mapped_read(path,*args,**kwargs):
        assert str(path) in mapping,('unexpected remote path',str(path))
        return original_read(mapping[str(path)],*args,**kwargs)
    m.read=mapped_read
    try:
        m.require_actual_install_binding()
        installed,admission=m.actual_install(prior,qa,proof)
    finally:
        m.read=original_read
    assert installed==m.EXPECTED_INSTALLED_IDENTITY and installed['uid']==10166
    assert admission['historical_state_reparsed'] is True and admission['historical_state_used_as_current_baseline'] is False
    rows.append({'control':'actual_r3_build_install_state_consumer_pass','passed':True,
        'explicit_seam':'only exact remote receipt paths routed to hash-verified downloaded original files',
        'receipt_count':11,'actual_uid':10166,'state_command_index':6,'state_wire_sha256':m.OLD_STATE_WIRE,
        'build_receipt_sha256':prior.BUILD_SHA,'install_reader_sha256':sha(reader_raw),
        'old_receipt_body_modified':False,'no_Android_or_remote_invocation':True})
    plan=m.fixed_plan(); adapter.validate_plan(plan,qa);adapter.validate_plan(m.POST_PLAN,qa)
    all_values={m.NONCE,*plan['nonces'].values(),*m.POST_PLAN['nonces'].values()}
    old=load(OLD/'owned_navigation.py','old_navigation')
    assert len(all_values)==8 and not all_values&{old.NONCE,*old.PLAN['nonces'].values(),*old.POST_PLAN['nonces'].values(),prior.NONCE,prior.STATE_NONCE}
    assert plan['operation']=='click' and 'value' not in plan and m.POST_PLAN['operation']=='inspect'
    rows.append({'control':'eight_new_nonces_exact_click_then_inspect_plans','passed':True,'set_text_actions':0})
    original_summary=m.assessment_summary
    m.assessment_summary=lambda *args:{'explicit_summary_materialization_seam':True}
    class Session:
        def __init__(self,click_fail=False,post_fail=False):
            self.click_fail=click_fail;self.post_fail=post_fail;self.calls=[]
        def sequence(self,plan):
            op=plan['operation'];self.calls.append(op);self.sequence_observation={'explicit_seam':True,'operation':op}
            if op=='click' and self.click_fail:raise RuntimeError('PRIMARY_CLICK_FAILURE')
            if op=='inspect' and self.post_fail:raise OSError('SECONDARY_POST_FAILURE')
            return {'installed_before':installed,'installed_after':installed,'click_acknowledged':op=='click','restoration_qualified':True,'after_state_completed':True}
    try:
        for name,first,second in [('success',False,False),('click_error_post_observed',True,False),('primary_and_secondary',True,True)]:
            sess=Session(first,second);result={'ok':False,'error':None,'secondary_errors':[]}
            m.navigation_sequences(prior,qa,types.SimpleNamespace(step=Path('/not-opened')),sess,installed,result)
            assert sess.calls==['click','inspect'] and result['post_inspection_attempted'] is True
            assert result['business_outcome_unknown'] is True and result['next_business_action_requires_new_observation_and_admission'] is True
            assert result['scoped_click_and_post_observation_completed'] is (not first and not second)
            if first: assert result['error']['message']=='PRIMARY_CLICK_FAILURE'
            else:assert result['error'] is None
            assert len(result['secondary_errors'])==int(first and second)
            if second:assert result['secondary_errors'][0]['message']=='SECONDARY_POST_FAILURE'
            rows.append({'control':'actual_navigation_sequences_'+name,'passed':True,
                'explicit_seams':['Session.sequence (no Android)','assessment_summary (no private file writes)'],
                'operations':sess.calls,'business_outcome_unknown_retained':True})
    finally:m.assessment_summary=original_summary
    a,b=funcs(OLD/'owned_navigation.py'),funcs(HERE/'owned_navigation.py')
    unchanged=['read','actual_install','new_session','navigation_sequences','worker','durable_phase','owned_scope','execute','main','fixed_plan','verify_source']
    for name in unchanged: assert same(a[name],b[name]),name
    final_a=next(n.finalbody for n in a['execute'].body if isinstance(n,ast.Try))
    final_b=next(n.finalbody for n in b['execute'].body if isinstance(n,ast.Try))
    assert same(ast.Module(body=final_a,type_ignores=[]),ast.Module(body=final_b,type_ignores=[]))
    for name in ('stage_execute.py','make_request.py'):
        aa,bb=funcs(OLD/name),funcs(HERE/name)
        assert set(aa)==set(bb) and all(same(aa[k],bb[k]) for k in aa),name
    rows.append({'control':'original_cleanup_and_production_operation_AST_unchanged','passed':True,
        'functions':unchanged,'stage_and_generator_function_AST_unchanged':True})
    ast_a,ast_b=ast.parse((OLD/'owned_navigation.py').read_bytes()),ast.parse((HERE/'owned_navigation.py').read_bytes())
    modified=sorted(k for k in a if not same(a[k],b[k]))
    assert modified==['assessment_summary','load_prior','require_actual_install_binding'],modified
    rows.append({'control':'only_three_expected_function_deltas','passed':True,'functions':modified,
        'changes':['r3 actual UID rejection and pending labels','explicit exact install source byte count','safe complete tree counters on summaries']})
    for name in ('owned_navigation.py','stage_execute.py','make_request.py','check_local.py'):
        ast.parse((HERE/name).read_bytes())
    return {'schema':1,'state':'LOCAL_NARROW_CONTROLS_PASS','count':len(rows),'controls':rows,
        'source_sha256':sha((HERE/'owned_navigation.py').read_bytes()),'Android_actions':0,'remote_actions':0,
        'raw_commercial_UI_read_or_exported':False,'actual_r3_click_run':False,'whole_app_production_ready':False}

if __name__=='__main__':print(json.dumps(run(),sort_keys=True,indent=2))
