#!/usr/bin/env python3
"""Consume the extracted-Java control observations with the actual contract.

Java cache/window/time doubles remain explicit; these are not Android receipts.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
path=HERE/'source/qa_contract.py'
spec=importlib.util.spec_from_file_location('actual_owned_r5_contract',path)
qa=importlib.util.module_from_spec(spec);spec.loader.exec_module(qa)
raw=(HERE/'cache-control-01/window/stdout.jsonl').read_bytes()
actual=[json.loads(line)for line in raw.splitlines()]
rows=[]


def check(name,value,accepted,ready):
    error=None
    try:qa.window_observation(value,ready_required=ready)
    except Exception as exc:error={'type':type(exc).__name__,'message':str(exc)}
    assert (error is None)==accepted,(name,error)
    rows.append({'case':name,'accepted':error is None,'expected_met':True,'error':error})


for row in actual:
    if 'observation' not in row:continue
    check(('r5_' if row['revised'] else 'r4_')+row['case']+'_'+str(row['qualified']),
          row['observation'],row['revised'],row['qualified'])
success=next(row['observation']for row in actual if row.get('revised') and row.get('qualified'))
changes=[
    ('cache_false_cannot_qualify',lambda x:x.update(cache_last_result=False)),
    ('cache_exception_cannot_qualify',lambda x:x.update(cache_last_exception='java.lang.IllegalStateException')),
    ('unconfirmed_sample_cannot_qualify',lambda x:x['sample_timings'][0].update(cache_cleared=False)),
    ('missing_api_evidence_cannot_qualify',lambda x:x.pop('cache_api')),
    ('wrong_api_cannot_qualify',lambda x:x.update(cache_api='android.app.UiAutomation.setCacheEnabled')),
    ('uncleared_query_cannot_qualify',lambda x:x.update(cache_clears=x['samples']-1)),
    ('extra_attempt_cannot_qualify',lambda x:x.update(cache_attempts=x['samples']+1)),
    ('old_sdk_cannot_qualify',lambda x:x.update(cache_runtime_sdk=33)),
    ('longer_deadline_cannot_qualify',lambda x:x.update(wait_budget_ms=2001)),
    ('unfocused_cannot_qualify',lambda x:x['last']['windows'][0].update(focused=False)),
    ('missing_timing_cannot_qualify',lambda x:x['sample_timings'].pop()),
]
for name,change in changes:
    value=copy.deepcopy(success);change(value);check(name,value,False,True)
check('state_without_UiAutomation_observation_preserved',{},True,False)
report={'schema':1,'status':'PASS','controls':rows,
        'contract_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'actual_Java_observation_file_sha256':hashlib.sha256(raw).hexdigest(),
        'observation_scope':'Owned Java seams, consumed by production validator; not Android evidence',
        'Android_or_UI_actions':0,'runtime_cache_cause_proven':False}
out=HERE/'contract-controls.json'
with out.open('x')as f:json.dump(report,f,sort_keys=True,indent=2);f.write('\n')
print(json.dumps({'status':'PASS','controls':len(rows),'sha256':hashlib.sha256(out.read_bytes()).hexdigest()}))
