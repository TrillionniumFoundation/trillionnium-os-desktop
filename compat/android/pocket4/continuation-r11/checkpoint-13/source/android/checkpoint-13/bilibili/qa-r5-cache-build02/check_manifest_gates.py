#!/usr/bin/env python3
"""Execute only the two actual builder gates on the retained actual owned XML."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
XML=HERE/'references/manifest.stdout'
EXPECTED='825a53459b0fc3406d328aad3350624f9b658b150a2fbf56f3a908f46de4185d'
GATES=('actual self instrumentation target required',
       'one exact actual instrumentation component required')


def pin(path):
    data=path.read_bytes()
    return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}


def selected(path):
    tree=ast.parse(path.read_bytes())
    package=next(ast.literal_eval(node.value)for node in tree.body
                 if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name)
                 and node.targets[0].id=='PACKAGE')
    require=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='require')
    build=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='build_once')
    result={}
    for node in ast.walk(build):
        if not(isinstance(node,ast.Expr) and isinstance(node.value,ast.Call)):continue
        call=node.value
        if not(isinstance(call.func,ast.Name) and call.func.id=='require' and len(call.args)==2):continue
        if not(isinstance(call.args[1],ast.Constant) and call.args[1].value in GATES):continue
        reason=call.args[1].value
        assert reason not in result
        module=ast.Module(body=[copy.deepcopy(require),copy.deepcopy(node)],type_ignores=[])
        result[reason]=compile(ast.fix_missing_locations(module),str(path),'exec')
    assert set(result)==set(GATES) and package=='org.droidloom.qa.bili.r5'
    return package,result


def main():
    raw=XML.read_bytes();assert 0<len(raw)<=1048576 and pin(XML)['sha256']==EXPECTED
    old=HERE/'references/build_candidate-r5-01.py';new=HERE/'source/build_candidate.py'
    original=selected(old);fixed=selected(new)
    changed=raw.replace(b'org.droidloom.qa.bili.r5',b'org.droidloom.qa.bili.r4')
    assert changed!=raw and b'org.droidloom.qa.bili.r5'not in changed
    rows=[]
    for case,(package,gates),xml,accepted in [
        ('original_gates_actual_R5',original,raw,False),
        ('fixed_gates_actual_R5',fixed,raw,True),
        ('fixed_gates_derived_wrong_R4',fixed,changed,False),
    ]:
        for name in GATES:
            error=None
            try:exec(gates[name],{'re':re,'PACKAGE':package,'xml':xml})
            except RuntimeError as exc:error={'type':type(exc).__name__,'message':str(exc)}
            assert (error is None)==accepted,(case,name,error)
            rows.append({'case':case,'gate':name,'accepted':error is None,'expected_met':True,'error':error})
    result={'schema':1,'state':'PASS','controls':rows,'actual_owned_manifest_stdout':pin(XML),
            'original_builder':pin(old),'revised_builder':pin(new),
            'actual_AST_require_and_gate_executed':True,
            'negative_input':'Actual retained owned XML with only package r5 -> r4 substitution',
            'new_Android_build_or_install_or_UI_actions':0}
    path=HERE/'manifest-gate-controls.json'
    with path.open('x')as f:json.dump(result,f,sort_keys=True,indent=2);f.write('\n')
    print(json.dumps({'state':'PASS','controls':len(rows),'report':pin(path)}))


if __name__=='__main__':main()
