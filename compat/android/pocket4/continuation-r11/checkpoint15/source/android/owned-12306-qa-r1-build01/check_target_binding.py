#!/usr/bin/env python3
"""Local actual Python admission predicates; no process/Android execution."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import re
import types

HERE=Path(__file__).resolve().parent


def load(name):
    path=HERE/'source'/name
    module=types.ModuleType(name.replace('.','_'));module.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),module.__dict__)
    return module


def main():
    qa,adapter,builder=(load(n) for n in ('qa_contract.py','qa_adapter.py','build_candidate.py'))
    rows=[]
    def check(name,fn,accepted):
        error=None
        try:fn()
        except Exception as exc:error={'type':type(exc).__name__,'message':str(exc)}
        assert error is None or error['type'] in ('RuntimeError','ProtocolError','ControlError'),(name,error)
        assert (error is None)==accepted,(name,error)
        rows.append({'case':name,'accepted':error is None,'expected_met':True,'error':error})
    scope={'package':qa.PACKAGE,'uid':10121,'user':0,'display':0,
        'activity':qa.PACKAGE+'/OwnedSyntheticActivity','window_token':'aa11','main_epoch_sha256':qa.MAIN_EPOCH}
    check('exact_current_12306_scope',lambda:qa.scope(dict(scope)),True)
    for name,key,value in (
        ('old_Amazon_package','package','com.amazon.mShop.android.shopping'),
        ('old_Amazon_UID','uid',10129),('old_Bili_UID','uid',10117),
        ('other_display','display',1),('other_Main','main_epoch_sha256','0'*64),
        ('regex_wildcard_activity','activity','comXMobileTicket/OwnedSyntheticActivity')):
        check('reject_'+name,lambda key=key,value=value:qa.scope({**scope,key:value}),False)
    request={'protocol':qa.PROTOCOL,'nonce':'1'*32,'op':'click','scope':scope,
        'inspection_nonce':'2'*32,'inspection_sha256':'3'*64,'node_path':'0/1','node_sha256':'4'*64}
    check('exact_current_click_request_shape',lambda:qa.validate_request(request),True)
    check('state_request_no_scope_or_UI',lambda:qa.validate_request({'protocol':qa.PROTOCOL,'nonce':'1'*32,'op':'state'}),True)
    for op in ('set_text','reveal_controls','back','grant'):
        check('request_rejects_'+op,lambda op=op:qa.validate_request({**request,'op':op}),False)
    check('reject_old_Amazon_protocol',lambda:qa.validate_request({**request,'protocol':'pocket4-owned-amazon-qa-v1'}),False)
    plan={'schema':1,'operation':'inspect','nonces':{'before':'1'*32,'inspect':'2'*32,'after':'3'*32}}
    check('exact_inspect_plan',lambda:adapter.validate_plan(plan,qa),True)
    check('plan_rejects_set_text_before_selector',lambda:adapter.validate_plan({**plan,'operation':'set_text'},qa),False)
    check('actual_XML_manifest_contract',builder.manifest_contract,True)
    check('standalone_old_flow_execution_denied',lambda:adapter.execute(None),False)
    # Exercise the exact helper-UID predicate without creating a session or a
    # fake APK. No outcome below is an installed-helper qualification.
    tree=ast.parse((HERE/'source/qa_contract.py').read_bytes())
    require=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='require')
    assess=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='parse_completed')
    predicates=[n for n in ast.walk(assess) if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call)
        and isinstance(n.value.func,ast.Name) and n.value.func.id=='require'
        and 'helper_uid not in' in (ast.get_source_segment((HERE/'source/qa_contract.py').read_text(),n) or '')]
    assert len(predicates)==1
    uid_code=compile(ast.fix_missing_locations(ast.Module(body=[copy.deepcopy(require),copy.deepcopy(predicates[0])],type_ignores=[])),'actual-helper-UID-predicate','exec')
    for uid in (10121,10129,10170,10175):
        check('actual_assessor_rejects_prior_or_target_UID_'+str(uid),lambda uid=uid:exec(uid_code,
            {'ProtocolError':qa.ProtocolError,'UID':qa.UID,'helper_uid':uid,'value':{'self_uid':uid,'self_pid':2},'SELF':qa.SELF}),False)
    check('UID_predicate_accepts_distinct_synthetic_UID_not_installed_qualification',lambda:exec(uid_code,
        {'ProtocolError':qa.ProtocolError,'UID':qa.UID,'helper_uid':10199,'value':{'self_uid':10199,'self_pid':2},'SELF':qa.SELF}),True)
    source=HERE/'source/build_candidate.py';tree=ast.parse(source.read_bytes())
    require=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='require')
    build=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='build_once')
    reasons={'actual self instrumentation target required','one exact actual instrumentation component required'}
    gates={}
    for n in ast.walk(build):
        if not(isinstance(n,ast.Expr) and isinstance(n.value,ast.Call)):continue
        c=n.value
        if isinstance(c.func,ast.Name) and c.func.id=='require' and len(c.args)==2 and isinstance(c.args[1],ast.Constant) and c.args[1].value in reasons:
            gates[c.args[1].value]=compile(ast.fix_missing_locations(ast.Module(body=[copy.deepcopy(require),copy.deepcopy(n)],type_ignores=[])),str(source),'exec')
    assert set(gates)==reasons
    xml=(HERE/'references/actual-bili-r5-manifest.stdout').read_bytes()
    assert hashlib.sha256(xml).hexdigest()=='825a53459b0fc3406d328aad3350624f9b658b150a2fbf56f3a908f46de4185d'
    derived=xml.replace(b'org.droidloom.qa.bili.r5',b'org.droidloom.qa.ticket.r1')
    for name,code in gates.items():
        check('actual_old_manifest_rejected:'+name,lambda code=code:exec(code,{'re':re,'PACKAGE':builder.PACKAGE,'xml':xml}),False)
        check('derived_new_manifest_predicate:'+name,lambda code=code:exec(code,{'re':re,'PACKAGE':builder.PACKAGE,'xml':derived}),True)
    java=(HERE/'source/src/org/droidloom/qa/ticket/r1/ActionRunner.java').read_text()
    gate='need(op.equals("state") || op.equals("inspect") || op.equals("click"), "TICKET_READ_INSPECT_CLICK_ONLY");'
    assert java.count(gate)==1 and java.index(gate)<java.index('nonce = string(request, "nonce", 32);')
    print(json.dumps({'schema':1,'state':'PASS','controls':rows,'count':len(rows),
        'static_Java_operation_gate_precedes_nonce_claim_and_UI':True,
        'actual_Android_or_build_actions':0,
        'synthetic':['OwnedSyntheticActivity and node path only validate request shape',
            'New-package XML is derived only for actual production Python regex expressions',
            'UID control extracts the actual predicate without constructing a Session'],
        'actual_manifest_reference_sha256':hashlib.sha256(xml).hexdigest(),
        'actual_12306_Java_compile_APK_signer_or_UI_qualification':False},sort_keys=True,indent=2))


if __name__=='__main__':main()
