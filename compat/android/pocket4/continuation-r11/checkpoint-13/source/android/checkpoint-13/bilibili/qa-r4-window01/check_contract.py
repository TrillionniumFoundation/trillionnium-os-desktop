#!/usr/bin/env python3
"""Narrow controls for the new timing metadata, using the actual contract."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
path=HERE/'source/qa_contract.py'
spec=importlib.util.spec_from_file_location('actual_owned_r4_contract',path)
qa=importlib.util.module_from_spec(spec);spec.loader.exec_module(qa)

window={'display':0,'id':7,'type':1,'focused':True,'active':True,'accessibility_focused':False,'layer':1}
first={'sample':1,'event_serial':0,'elapsed_ms':1,'displays':[0],'windows':[dict(window,focused=False,active=False)]}
last={'sample':2,'event_serial':0,'elapsed_ms':102,'displays':[0],'windows':[window]}
value={'requested_display':0,'selection':'exact-display-0-focused-application','wait_budget_ms':2000,
       'recheck_max_ms':100,'ready':True,'first':first,'last':last,'samples':2,'waited_ms':102,
       'selected_display':0,'selected_window_id':7,
       'sample_timings':[{k:r[k]for k in ('sample','event_serial','elapsed_ms')}for r in (first,last)]}
rows=[]

def check(name,observed,accepted,ready=True):
    error=None
    try:qa.window_observation(observed,ready_required=ready)
    except Exception as exc:error={'type':type(exc).__name__,'message':str(exc)}
    assert (error is None)==accepted,(name,error)
    rows.append({'case':name,'accepted':error is None,'expected_met':True,'error':error})

check('complete_two_sample_success',copy.deepcopy(value),True)
x=copy.deepcopy(value);x['sample_timings'].pop();check('omitted_sample_rejected',x,False)
x=copy.deepcopy(value);x['sample_timings'][1]['event_serial']=1;check('event_census_mismatch_rejected',x,False)
x=copy.deepcopy(value);x['waited_ms']=101;check('sample_after_claimed_wait_rejected',x,False)
x=copy.deepcopy(value);x['last']['windows'][0]['focused']=False;check('unfocused_never_accepted',x,False)
x=copy.deepcopy(value);x['wait_budget_ms']=2001;check('longer_deadline_rejected',x,False)
x={'requested_display':0,'selection':'exact-display-0-focused-application','wait_budget_ms':2000,
   'recheck_max_ms':100,'sample_timings':[],'ready':False}
check('failure_before_first_census_preserved',x,True,False)
report={'schema':1,'status':'PASS','controls':rows,'contract_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'fixture':'synthetic metadata only; actual production validator', 'Android_or_UI_actions':0}
out=HERE/'contract-controls.json'
with out.open('x') as f:json.dump(report,f,sort_keys=True,indent=2);f.write('\n')
print(json.dumps({'status':'PASS','controls':len(rows),'sha256':hashlib.sha256(out.read_bytes()).hexdigest()}))
