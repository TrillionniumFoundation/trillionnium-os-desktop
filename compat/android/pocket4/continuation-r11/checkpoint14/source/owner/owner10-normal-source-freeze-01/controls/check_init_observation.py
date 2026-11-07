#!/usr/bin/env python3
"""Pure I/O seam controls for the actual actor's live sample and new gates."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import sys
import time
import types

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'source'))
import actor

def need(value, message):
    if not value: raise RuntimeError(message)

def main():
    sample = {'process': {'pid': 123, 'birth': 456, 'pidfd': {'device': 5, 'inode': 6}, 'proc_dir': {'device': 7, 'inode': 8}},
              'namespaces': [{'device': 5, 'inode': n + 1} for n in range(10)],
              'executable': {'device': 9, 'inode': 10}, 'executable_sha256': 'ab' * 32,
              'identity': {'pid':123, 'birth':456}}
    hello = {'sequence':3, 'observed_monotonic_ns':time.monotonic_ns() - 1000000,
             'detail': {'event':'init_hello', 'init':{k:copy.deepcopy(v) for k,v in sample.items() if k != 'identity'}}}
    audit = {'nonce':'12' * 32, 'records':[hello]}
    opened=[]; body=copy.deepcopy(sample); fail_snapshot=False
    class Process:
        def __init__(self, pid):
            assert pid == 123; self.closed=False; self.live_calls=0; opened.append(self)
        def live(self): self.live_calls += 1
        def snapshot(self):
            if fail_snapshot: raise RuntimeError('first held snapshot failure')
            return copy.deepcopy(body)
        def close(self): self.closed=True
    owned=types.SimpleNamespace(need=need, Process=Process)
    records=[]
    assert actor.observe_init_hello({'nonce':audit['nonce'],'records':[]}, owned) is None and not opened
    records.append({'case':'no_HELLO_opens_no_process','passed':True})
    proc,captured=actor.observe_init_hello(audit,owned)
    assert proc is opened[-1] and not proc.closed and proc.live_calls == 2
    assert captured['snapshot'] == sample and captured['global_kernel_lines_attributed'] is False and captured['atomic_clock_sample'] is False
    assert 0 < captured['monotonic_before_ns'] <= captured['monotonic_after_ns'] and captured['boottime_ns'] > 0 and captured['realtime_ns'] > 0
    proc.close();records.append({'case':'exact_held_identity_and_real_clock_calls','passed':True})
    body['process']['birth'] += 1
    try: actor.observe_init_hello(audit,owned)
    except RuntimeError as error:
        assert str(error) == 'observed init differs from actual HELLO: process' and opened[-1].closed
    else: raise AssertionError('changed birth accepted')
    records.append({'case':'changed_birth_rejected_and_capability_closed','passed':True})
    body=copy.deepcopy(sample);fail_snapshot=True
    try: actor.observe_init_hello(audit,owned)
    except RuntimeError as error:
        assert str(error) == 'first held snapshot failure' and opened[-1].closed
    else: raise AssertionError('snapshot failure lost')
    records.append({'case':'snapshot_first_error_preserved_and_capability_closed','passed':True})
    # Evaluate the exact three new qualifier predicates, not a rewritten gate.
    q=ast.parse((ROOT/'source/qualify.py').read_text())
    labels=['held init clock observation differs from exact HELLO',
            'held init observation or log-attribution scope differs',
            'held init three-clock observation is outside the actual live phase']
    calls={n.args[1].value:n for n in ast.walk(q) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)
           and n.func.id=='need' and len(n.args)>1 and isinstance(n.args[1],ast.Constant) and n.args[1].value in labels}
    assert set(calls)==set(labels)
    expressions={name:compile(ast.fix_missing_locations(ast.Expression(node.args[0])), 'actual-qualifier-predicate','eval') for name,node in calls.items()}
    env={'captured':copy.deepcopy(captured),'actual':{'active_observed_monotonic_ns':time.monotonic_ns()},
         'b':{'nonce':audit['nonce']},'hello_row':hello,'observed_init':sample}
    def passes(value):
        context={'__builtins__':{},'type':type,'int':int,'all':all,**value}
        return all(eval(expr, context, context) for expr in expressions.values())
    assert passes(env);records.append({'case':'exact_actual_capture_predicates_accept','passed':True})
    for name,mutate in [
        ('wrong_generation_rejected', lambda x:x['captured'].update(generation_nonce='34'*32)),
        ('wrong_HELLO_sequence_rejected',lambda x:x['captured'].update(audit_sequence=4)),
        ('replaced_snapshot_rejected',lambda x:x['captured']['snapshot']['process'].update(birth=999)),
        ('false_kernel_attribution_rejected',lambda x:x['captured'].update(global_kernel_lines_attributed=True)),
        ('capture_after_ACTIVE_rejected',lambda x:x['captured'].update(monotonic_after_ns=x['actual']['active_observed_monotonic_ns']+1)),
        ('prior_capture_error_rejected',lambda x:x['actual'].update(init_identity_clock_observation_error='first error'))]:
        value=copy.deepcopy(env);mutate(value);assert not passes(value),name;records.append({'case':name,'passed':True})
    report={'schema':1,'scope':'Pure I/O seam plus actual source predicate controls; no process/namespace/runtime qualification',
            'success':True,'passed':len(records),'cases':records,'actual_owner_runtime_executed':False,
            'pins':{name:hashlib.sha256((ROOT/'source'/name).read_bytes()).hexdigest() for name in ['actor.py','qualify.py']}}
    raw=(json.dumps(report,sort_keys=True,indent=2)+'\n').encode()
    with (ROOT/'init-observation-controls.json').open('xb') as output:output.write(raw)
    print(json.dumps({'passed':len(records),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}))

if __name__=='__main__':main()
