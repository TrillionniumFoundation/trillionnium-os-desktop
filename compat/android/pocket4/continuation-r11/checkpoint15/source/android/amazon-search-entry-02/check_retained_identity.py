#!/usr/bin/env python3
"""Replay only retained safe identities through the actual stability function.

No private nodes, helper execution, Android calls or action authority. The
current_inspection and selector I/O are explicit seams. Original full Session
controls live in check_search.py and keep the real current-selector path.
"""
import copy
import hashlib
import json
from pathlib import Path
import types

HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'android-amazon-search-entry-01'


def load(path,name):
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),module.__dict__)
    return module


def main():
    raw=(HERE/'retained-observation-identities.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest()=='4c5939d99e9efacde15178c26bc27b7fcc111708dbae2a3122761b0737ca81ee'
    trace=json.loads(raw);rows=trace['observations'];assert len(rows)==5
    assert [r['node_count'] for r in rows]==[72,220,281,464,464]
    assert hashlib.sha256((OLD/'search_navigation.py').read_bytes()).hexdigest()=='3b3ed0a54d1bdd1c520dbcd35b0d7729425139ca0f936b059e5b628e49fc0b00'
    assert hashlib.sha256((OLD/'fresh-plans.json').read_bytes()).hexdigest()=='1faf99985a01713b36ed993c46736af9c919167f782c339568e8d7555e1904f5'
    old=load(OLD/'search_navigation.py','old_stability')
    new=load(HERE/'search_navigation.py','new_stability')
    assert old.STABLE_READ_BUDGET_SECONDS==new.STABLE_READ_BUDGET_SECONDS==30
    cases=[]

    def replay(module,spec,late=False):
        calls=[];clock=[0.0]
        def sequence(plan):
            index=len(calls);calls.append(plan['nonces']['inspect'])
            row=copy.deepcopy(rows[index])
            clock[0]=(row['last_elapsed_ms']-rows[0]['began_elapsed_ms'])/1000
            if late and index==4:clock[0]=30.0
            return {'row':row,'foreground_before':row['scope'],
                'foreground_after':row['scope'],'restoration_qualified':True,
                'after_state_completed':True}
        # A summary-only seam makes no claim of executing inspect_record or
        # reconstructing nodes. The exact hashes are retained observations.
        def current(base,q,step,plan,value):
            row=value['row']
            return {k:row[k] for k in ('tree_sha256','window_sha256')},{'retained_identity_only':True}
        def eligible(inspection,selector):
            assert selector==module.SELECTOR
            return {'retained_selector_eligibility_seam':True}
        module.current_inspection=current
        module.time=types.SimpleNamespace(monotonic=lambda:clock[0])
        q=types.SimpleNamespace(qa=types.SimpleNamespace(select_unique_clickable=eligible))
        result={};error=None
        try:module.stable_entry(None,q,types.SimpleNamespace(sequence=sequence),None,spec,result)
        except BaseException as exc:error=str(exc)
        assert len(calls)==len(set(calls))
        return result,error,calls

    old_spec=json.loads((OLD/'fresh-plans.json').read_text())['plan']
    new_spec=json.loads((HERE/'fresh-plans.json').read_text())['plan']
    value,error,calls=replay(old,old_spec)
    assert error=='TWO_CONSECUTIVE_COMPLETE_SEARCH_ENTRY_OBSERVATIONS_REQUIRED'
    assert len(calls)==4 and 'stable_read_indices' not in value
    cases.append({'case':'original_four_read_limit_reproduces_actual_identity_failure',
        'calls':4,'expected_met':True})
    value,error,calls=replay(new,new_spec)
    assert error is None and len(calls)==5 and value['stable_read_indices']==[3,4]
    cases.append({'case':'candidate_fifth_complete_identity_matches_fourth',
        'calls':5,'stable_pair':[3,4],'expected_met':True})
    value,error,calls=replay(new,new_spec,late=True)
    assert error=='SEARCH_ENTRY_STABILITY_READ_DEADLINE' and len(calls)==5
    assert 'stable_read_indices' not in value
    cases.append({'case':'even_matching_fifth_identity_at_original_deadline_rejected',
        'calls':5,'expected_met':True})
    print(json.dumps({'schema':1,'state':'PASS','cases':cases,'count':len(cases),
        'trace_sha256':hashlib.sha256(raw).hexdigest(),
        'seams':['current_inspection returns retained safe identity only',
                 'selector uses prior eligibility and equal complete fourth/fifth identity',
                 'sequence and clock model retained summary order and elapsed values'],
        'raw_private_UI_read':False,'device_calls':0,'actions_executed':0,
        'candidate_runtime_qualification':'NOT_RUN'},sort_keys=True,indent=2))


if __name__=='__main__':main()
