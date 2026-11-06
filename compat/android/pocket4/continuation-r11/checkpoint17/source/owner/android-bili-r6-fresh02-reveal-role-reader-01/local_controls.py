#!/usr/bin/env python3
"""Pure controls for the diagnostic; no retained raw UI or file collector call."""
from pathlib import Path
import copy
import hashlib
import json
import types

HERE=Path(__file__).resolve().parent
BASE=HERE.parent

def load(path,name):
    m=types.ModuleType(name);m.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__)
    return m

def main():
    d=load(HERE/'read_roles.py','diagnostic')
    fixture=load(BASE/'owned-bili-qa-r6-reveal-01/controls/check_reveal.py','actual_reveal_fixture')
    qa=fixture.qa;cases=[]
    for label,mutate,role in (
        ('valid_public_fixture',lambda v:None,None),
        ('missing_title',lambda v:v['nodes'].pop(0),'title'),
        ('different_title_digest',lambda v:v['nodes'][0].update(text='different public fixture',text_sha256=qa.sha(b'different public fixture')),'title'),
        ('duplicate_author',lambda v:v['nodes'].append({**v['nodes'][1],'path':'0/99'}),'author'),
        ('disabled_container',lambda v:v['nodes'][3].update(enabled=False),'container'),
        ('incomplete_title_class',lambda v:v['nodes'][0].update(class_truncated=True),'title')):
        value=fixture.fixture();mutate(value);fixture.refresh(value)
        qa.inspect_record(value)
        got=d.role_counts(qa,value);errors=d.predicate_errors(qa,value,fixture.scope())
        if role is None:
            assert got['first_nonunique_role_in_declared_order'] is None and errors=={'require_hidden':None,'allow_shown':None}
        else:
            assert got['first_nonunique_role_in_declared_order']==role
            assert errors['require_hidden']==errors['allow_shown']=='REVEAL_UNIQUE_PLAYER_ROLE_REQUIRED'
        d.no_raw_ui(got)
        raw=json.dumps(got)
        assert 'Very Basic Calculus' not in raw and 'Ayumu' not in raw and 'different public fixture' not in raw
        cases.append({'case':label,'passed':True,'first_nonunique_role':role})
    try:d.no_raw_ui({'safe':{'text':'not permitted'}})
    except RuntimeError as ex:assert str(ex)=='RAW_UI_EXPORT_FORBIDDEN'
    else:raise AssertionError('raw text allowed')
    cases.append({'case':'raw_UI_export_rejected','passed':True})
    ev=BASE/'root-recovery-20261104-02/evidence/bili-r6-pause-resume-fresh02-failure-read01'
    p=BASE/'root-recovery-20261104-02/evidence/bili-r6-pause-resume-fresh02-parent-read01'
    def exact(path,size,sha):
        raw=path.read_bytes();assert len(raw)==size and hashlib.sha256(raw).hexdigest()==sha;return json.loads(raw)
    c=exact(p/'coordinator.json',7406,d.COORDINATOR_SHA);s=exact(p/'stage.json',1773,d.STAGE_SHA)
    nav=exact(ev/'navigation.json',214331,d.NAV_SHA);cleanup=exact(ev/'cleanup.json',448,d.CLEANUP_SHA)
    scopes,meta=d.validate_retained(c,s,nav,cleanup)
    assert len(scopes)==3 and meta['nonce']==d.CASES[0][1]
    cases.append({'case':'actual_four_parent_navigation_cleanup_originals','passed':True})
    bad=copy.deepcopy(nav);bad['nonce']='0'*32
    try:d.validate_retained(c,s,bad,cleanup)
    except RuntimeError as ex:assert str(ex)=='EXACT_ORIGINAL_FAILED_FLOW_REQUIRED'
    else:raise AssertionError('old flow accepted')
    cases.append({'case':'foreign_flow_nonce_rejected','passed':True})
    helper={'ok':True,'error':None,'secondary_errors':[],'protocol':qa.PROTOCOL,'nonce':d.CASES[1][1],'op':'inspect',
        'self_uid':10184,'action_attempted':False,'outcome_unknown':False,'claim_persistence_completed':True,
        'helper_work_completed':True,'automatic_retry':False,'business_success_verified':False}
    assessed={'helper':helper,'held_transport_returned_after_post_guard':True,'actual_command_returncode':0,
              'actual_instrumentation_finish_code':-1,'wire_sha256':d.CASES[1][2]}
    try:d.validated_assessment(qa,assessed,d.CASES[1][1],d.CASES[1][2],scopes['reveal_admission'])
    except RuntimeError as ex:assert str(ex)=='ACTUAL_CANONICAL_HELPER_WIRE_PIN_REQUIRED'
    else:raise AssertionError('unbound helper accepted')
    cases.append({'case':'unbound_canonical_helper_wire_rejected','passed':True})
    print(json.dumps({'schema':1,'passed':len(cases),'cases':cases,'actual_production_player_reveal_scope_executed':True,
        'synthetic_complete_public_tree_controls':True,'actual_parent_records_checked':True,
        'retained_raw_UI_read':False,'Reader_read_or_collect_called':False,'Hepta_or_Android_calls':0},sort_keys=True,indent=2))

if __name__=='__main__':main()
