#!/usr/bin/env python3
"""Seal one fixed action request from actual completed r2 inspect evidence.

Local files only. No device/remote process or Android action is executed.
"""
import ast
import base64
import copy
import difflib
import hashlib
import json
from pathlib import Path
import types

PROJECT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
PARENT=HERE/'source-r2'
OUT=HERE/'candidate-r1'
READONLY=PROJECT/'successor_qa/search_helper_readonly_inspect_r1/candidate-r1'
ACTUAL=READONLY/'actual-inspect'
HELPER=PROJECT/'successor_qa/search_click_same_process_r1/candidate-r2/helper'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')


def pin(path,remote=None):
    raw=path.read_bytes()
    return {'path':remote or str(path.relative_to(PROJECT)),'bytes':len(raw),'sha256':sha(raw)}


def exact(path,count,digest):
    raw=path.read_bytes();assert len(raw)==count and sha(raw)==digest,str(path)
    return raw


def definitions(source):
    lines=source.splitlines(keepends=True)
    return {n.name:''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)}


def load(path,name):
    value=types.ModuleType(name);value.__file__=str(path.resolve())
    exec(compile(path.read_bytes(),value.__file__,'exec'),value.__dict__)
    return value


def write(name,raw):
    if isinstance(raw,str):raw=raw.encode('utf-8')
    path=OUT/name
    if path.exists():assert path.read_bytes()==raw,'frozen output differs: '+str(path)
    else:path.write_bytes(raw)
    return path


def write_json(name,value):
    return write(name,json.dumps(value,sort_keys=True,ensure_ascii=True,indent=2)+'\n')


def replace_constants(source,values):
    tree=ast.parse(source);lines=source.splitlines(keepends=True)
    nodes={n.targets[0].id:n for n in tree.body if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name)}
    for name in sorted(values,key=lambda k:nodes[k].lineno,reverse=True):
        n=nodes[name];lines[n.lineno-1:n.end_lineno]=[name+' = '+repr(values[name])+'\n']
    return ''.join(lines)


def main():
    parent_path=PARENT/'owned_fixed_search_click_once.py'
    before=exact(parent_path,45164,'50bf55a0fa3c23cbe125c619ef1e18d6d7ac34f7bcb9b61f5f90b3c68633e591').decode()
    old=load(parent_path,'unbound_fixed_action_definitions_only')
    stdout=exact(ACTUAL/'stdout.original.json',24661,'7e4c812377d3562ad9fd236899ba151c2bb11772672c3f04956e02a469d487ed')
    terminal_raw=exact(ACTUAL/'terminal.original.json',733,'e58b70b49e0a9e61be8d7dcfe72517652cedc8e890f135f618c9558b3c70b6f0')
    child_raw=exact(ACTUAL/'child.stdout.original.json',18212,'1776f75bd8d3be023c2e8add5168272e3bc5c3cb3f9f65eb066765fe40b0e788')
    adapter_raw=exact(ACTUAL/'adapter.stdout.original.json',5752,'d74106ad60282ecebf78cfe8aa10f2c75028c42e856f8ad15dda61ffcd71acfc')
    validation_raw=exact(ACTUAL/'root-validation.actual.json',4008,'c54d9bdce4c3fdfdedfc33d6fdd9aa2edad12c1a5892fb6cec3260ce785e30ed')
    reconstructed=exact(ACTUAL/'joint.reconstructed.exact.json',24390,'58607e7ab4d3463ac50f7d915b4c886ea7286d57cd6ea77a9fd8d392990aed47')
    outer,terminal,child,adapter_result,validation=map(json.loads,(stdout,terminal_raw,child_raw,adapter_raw,validation_raw))
    assert outer['child_stdout_original'].encode()==child_raw and child['original_stdout'].encode()==adapter_raw
    assert outer['source']==old.INSPECT_OWNER and outer['request']==old.INSPECT_REQUEST
    assert terminal['job_id']=='1a1b35f9774-fc05-827f' and validation['job_id']==terminal['job_id']
    assert validation['state']=='PASS_READONLY_INSPECT_ACTUAL49_IDENTITY_RESTORATION_OWNED_EXIT_AND_DURABLE_TERMINAL'
    assert validation['private_UI_tree_read_back_locally'] is False and validation['business_success_verified'] is False
    joint=dict(outer);jp=joint.pop('joint_artifact')
    assert canonical(joint)+b'\n'==reconstructed and jp['bytes']==len(reconstructed) and jp['sha256']==sha(reconstructed)
    assert adapter_result['inspection_wire_sha256']=='c44cfe0deb683261c272029d938b2ae13d41bf94b09243130a08b3ff70785223'
    assert adapter_result['foreground_before']==adapter_result['foreground_after']==validation['foreground']
    assert adapter_result['installed_before']==adapter_result['installed_after']==old.INSTALLED_HELPER
    assert outer['current_explicit_scope']==old.CURRENT_SCOPE and outer['helper_uid']==old.HELPER_UID==10167
    manifest=json.loads((HELPER/'SOURCE_PINS.json').read_bytes())
    assert sha((HELPER/'SOURCE_PINS.json').read_bytes())==old.HELPER_MANIFEST
    for name,row in manifest['files'].items():
        body=(HELPER/name).read_bytes();assert len(body)==row['bytes'] and sha(body)==row['sha256']
    qa=load(HELPER/'qa_contract.py','actual_frozen_qa_plan_parser_only')
    adapter=load(HELPER/'qa_adapter.py','actual_frozen_adapter_plan_parser_only')
    plan={'schema':1,'operation':'search_click','selector':qa.SEARCH_SELECTOR,
          'nonces':{'before':'2dcf1b82a4f34e4b974beb48d4156d19','inspect':'1396fd1e88454afdabba7b73a1bb8a96',
                    'action':'c9df0017d7a64731b9e27df9973ac928','after':'8aa4e9f3aa2e4556b22dd0ca7c10f3ed'}}
    plan_raw=canonical(plan)+b'\n'
    request={'schema':'pocket4-fixed-r2-search-click-request-v1','kind':'plan','step':'r2-fixed-search-click-01',
             'payload_text':plan_raw.decode(),'payload_sha256':sha(plan_raw)}
    changes={'FIXED_REQUEST':request,'INSPECT_INPUTS_BOUND':True,'INSPECT_JOB':terminal['job_id'],
        'INSPECT_STDOUT':pin(ACTUAL/'stdout.original.json',old.ROOT+'/inspect.stdout.original.json'),
        'INSPECT_TERMINAL':pin(ACTUAL/'terminal.original.json',old.ROOT+'/inspect.terminal.original.json'),
        'INSPECT_RESULT':outer['original_result'],'INSPECT_JOINT':outer['joint_artifact'],
        'INSPECT_WIRE_SHA':adapter_result['inspection_wire_sha256']}
    source=replace_constants(before,changes)
    source=source.replace('Source-only fixed search_click revision. Disabled until actual inspect inputs and exact request are bound.',
                          'One fixed search_click bound to actual completed r2 inspect. No retry or business-success assertion.')
    compile(source,old.ROOT+'/owned_fixed_search_click_once.py','exec')
    assert definitions(source)==definitions(before),'Sealing must not change any function body'
    OUT.mkdir(exist_ok=True)
    write('owned_fixed_search_click_once.py',source)
    write('request.json',canonical(request)+b'\n');write('plan.review-only.json',plan_raw)
    write('inspect.stdout.original.json',stdout);write('inspect.terminal.original.json',terminal_raw)
    write('SEAL_DIFF.patch',''.join(difflib.unified_diff(before.splitlines(True),source.splitlines(True),
        fromfile=str(parent_path.relative_to(PROJECT)),tofile=str((OUT/'owned_fixed_search_click_once.py').relative_to(PROJECT)))))
    readonly_source=(READONLY/'owned_readonly_inspect_once.py').read_text()
    write('OWNER_DIFF_FROM_READONLY.patch',''.join(difflib.unified_diff(readonly_source.splitlines(True),source.splitlines(True),
        fromfile=str((READONLY/'owned_readonly_inspect_once.py').relative_to(PROJECT)),tofile=str((OUT/'owned_fixed_search_click_once.py').relative_to(PROJECT)))))
    members=['owned_fixed_search_click_once.py','request.json','inspect.stdout.original.json','inspect.terminal.original.json']
    pins={name:{k:v for k,v in pin(OUT/name).items() if k!='path'} for name in members}
    payload={'schema':'pocket4-r2-fixed-search-click-source-stage-payload-v1','root':old.ROOT,
             'files':{name:dict(pins[name],base64=base64.b64encode((OUT/name).read_bytes()).decode()) for name in members}}
    payload_raw=canonical(payload)+b'\n';assert len(payload_raw)<=524288
    write('stage-input.json',payload_raw)
    stage_path=READONLY/'stage_source_once.py';stage_before=stage_path.read_text()
    # Preserve the original root-owned nofollow, readback and FD retirement code.
    stage=replace_constants(stage_before,{'PINS':pins,'PAYLOAD_SHA':sha(payload_raw)})
    stage=stage.replace("ROOT = Path('/home/alex/work/pocket4-beike-search-helper-r2-readonly-inspect-20261107-r1')",'ROOT = Path('+repr(old.ROOT)+')')
    stage=stage.replace('pocket4-beike-search-helper-r2-readonly-inspect-20261107-r1',old.ROOT.rsplit('/',1)[-1])
    stage=stage.replace('pocket4-r2-readonly-inspect-source-stage-payload-v1','pocket4-r2-fixed-search-click-source-stage-payload-v1')
    stage=stage.replace('pocket4-r2-readonly-inspect-source-stage-v1','pocket4-r2-fixed-search-click-source-stage-v1')
    stage=stage.replace('source-only-readonly-inspect-owner-not-invoked','source-only-fixed-search-click-owner-not-invoked')
    stage=stage.replace('Publish the fixed readonly inspect owner and actual install receipts. No Android entry.',
                        'Publish the single fixed search owner and completed r2 inspect receipts. No Android entry.')
    compile(stage,'<source-stage-only>','exec')
    assert all(definitions(stage)[n]==definitions(stage_before)[n] for n in ('need','sha','census'))
    write('stage_source_once.py',stage)
    write('STAGE_DIFF.patch',''.join(difflib.unified_diff(stage_before.splitlines(True),stage.splitlines(True),
        fromfile=str(stage_path.relative_to(PROJECT)),tofile=str((OUT/'stage_source_once.py').relative_to(PROJECT)))))
    common={'host':'pocket4','executable':'/usr/bin/sudo','cwd':'/home/alex/work','nice':10}
    stage_packet=dict(common,args=['-n','/usr/bin/python3','-I','-B','-c',stage,'--payload-sha256',sha(payload_raw)],
        stdin=payload_raw.decode(),cpu_quota_percent=50,memory_max_bytes=268435456,timeout_seconds=60,
        idempotency_key='pocket4-beike-r2-fixed-search-click-source-stage-r1-20261107')
    a,b=pins['owned_fixed_search_click_once.py'],pins['request.json']
    action_packet=dict(common,args=['-n','/usr/bin/python3','-I','-B',old.ROOT+'/owned_fixed_search_click_once.py','--execute-request',
        '--source-sha256',a['sha256'],'--source-bytes',str(a['bytes']),'--request-sha256',b['sha256'],'--request-bytes',str(b['bytes'])],
        cpu_quota_percent=100,memory_max_bytes=536870912,timeout_seconds=480,
        idempotency_key='pocket4-beike-r2-fixed-search-click-once-r1-20261107')
    write_json('exact-stage-request.review-only.json',stage_packet)
    write_json('exact-action-request.review-only.json',action_packet)
    sealed=load(OUT/'owned_fixed_search_click_once.py','sealed_action_pure_local_controls')
    base_path=PROJECT/'successor_qa/owned_cleanup_r1/cleanup_owned_task_once.py'
    partial_path=PROJECT/'successor_qa/no_action_runtime_commit_r1/stage-a-candidate-r1/no_action_core.py'
    base=load(base_path,'normal_owned_exit_pure_control');partial=load(partial_path,'authoritative_terminal_pure_control')
    controls=[]
    def check(name,fn,reject=False):
        try:fn()
        except RuntimeError as error:
            assert reject,(name,str(error));controls.append({'name':name,'passed':True,'rejection':str(error)})
        else:
            assert not reject,name;controls.append({'name':name,'passed':True})
    check('actual_r2_readonly_complete_stdout_terminal_and_child_gate',lambda:sealed.completed_inspect_header(base,partial,stdout,terminal))
    bad_terminal=dict(terminal);bad_terminal['output_durable']=False
    check('non_durable_previous_inspect_rejected',lambda:sealed.completed_inspect_header(base,partial,stdout,bad_terminal),True)
    parser=types.SimpleNamespace(document=json.loads)
    check('one_fixed_search_plan_accepted_by_actual_compiled_adapter',lambda:sealed.declared_request(canonical(request)+b'\n',parser,adapter,qa))
    bad_plan=copy.deepcopy(plan);bad_plan['operation']='click';bad_request=dict(request,payload_text=(canonical(bad_plan)+b'\n').decode(),payload_sha256=sha(canonical(bad_plan)+b'\n'))
    check('generic_click_request_rejected',lambda:sealed.declared_request(canonical(bad_request)+b'\n',parser,adapter,qa),True)
    bad_case=dict(request,kind='case')
    check('case_request_rejected',lambda:sealed.outer_request(canonical(bad_case)+b'\n',parser),True)
    write_json('LOCAL_CONTROLS.json',{'schema':'pocket4-fixed-search-sealed-local-controls-v1','state':'PASS_LOCAL_PARSING_AND_BINDINGS_ONLY',
        'count':len(controls),'cases':controls,'actual_action_result_created':False,'prior_tree_body_available_locally':False,
        'remote_processes':0,'UI_actions':0,'production_ready':False})
    old_defs=definitions(readonly_source);final_defs=definitions(source)
    unchanged=[name for name in old_defs if old_defs[name]==final_defs[name]]
    changed=[name for name in old_defs if old_defs[name]!=final_defs[name]]
    inheritance={'schema':'pocket4-fixed-search-sealed-source-inheritance-v1','source_only_parent':pin(parent_path),
        'actual_readonly_parent':pin(READONLY/'owned_readonly_inspect_once.py'),
        'all_source_r2_function_bodies_unchanged':True,'source_r2_function_count':len(definitions(before)),
        'seal_changes_only':['Eight actual inspect/request constant bindings','Nonfunctional module description'],
        'unchanged_from_readonly':unchanged,'changed_from_readonly':changed,
        'added_functions':[n for n in final_defs if n not in old_defs],
        'frozen_helper_files_checked':len(manifest['files']),'helper_adapter_Session_or_ActionRunner_modified':False,
        'unknown_semantics':'Successful input acknowledgement still has action_attempted/outcome_unknown true. No reconciliation or business result is manufactured.',
        'foreground_semantics':'No outer before==after foreground assertion on search_click. Original target package, owned task, helper, exact action-window and independent after-state restoration remain.',
        'post_guard_failure_attribution':'Original actual action_attempted flag passed to unchanged typed guard after action; not treated as readonly failure.',
        'source_stage_executes_owner':False,'private_UI_body_included':False}
    write_json('SOURCE_INHERITANCE.json',inheritance)
    plan_review={'schema':'pocket4-fixed-search-one-action-review-v1','state':'SEALED_FOR_ROOT_REVIEW_NOT_SUBMITTED',
        'root':old.ROOT,'flow':old.FLOW,'step':request['step'],'operation':'search_click','selector':qa.SEARCH_SELECTOR,
        'actual_prior_inspect':{'job_id':terminal['job_id'],'stdout':pin(ACTUAL/'stdout.original.json'),
            'terminal':pin(ACTUAL/'terminal.original.json'),'root_validation':pin(ACTUAL/'root-validation.actual.json'),
            'joint_pin':outer['joint_artifact'],'local_joint_is_reconstructed_comparison_not_host_readback':True,
            'original_result':outer['original_result'],'inspection_wire_sha256':changes['INSPECT_WIRE_SHA']},
        'actual_scope49':old.CURRENT_SCOPE,'actual_helper_UID':old.HELPER_UID,
        'previous_private_tree_readback_available':False,'current_search_button_presence_prejudged':False,
        'action_admission':'Actual completed readonly observer plus fresh original Flow checks. The new action plan takes a new full inspection and the compiled fixed same-process search transaction before dispatching at most once.',
        'next_step':'After action actual terminal, a separate readonly inspect must obtain current new tree. Do not claim navigation from homepage 搜索 TextView, do not automatically retry or chain another click.',
        'generic_actions_or_case_allowed':False,'automatic_retry':False,'permission_changes':0,'installs':0,'cleanup_bytes':0,
        'action_expected_outcome_unknown_even_on_acknowledgement':True,'business_success_verified':False,'production_ready':False,
        'resources':{'owned_child_seconds':360,'outer_seconds':480,'cpu_percent':100,'memory_bytes':536870912,
                     'child_stdout_bytes':131072,'child_stderr_bytes':16384,'parent_stdout_bytes':262144},
        'requests':[pin(OUT/'exact-stage-request.review-only.json'),pin(OUT/'exact-action-request.review-only.json')]}
    write_json('EXECUTION_PLAN.json',plan_review)
    inputs=[Path(__file__),parent_path,PARENT/'SOURCE_PINS.json',READONLY/'owned_readonly_inspect_once.py',READONLY/'request.json',stage_path,
        ACTUAL/'stdout.original.json',ACTUAL/'terminal.original.json',ACTUAL/'child.stdout.original.json',ACTUAL/'adapter.stdout.original.json',
        ACTUAL/'root-validation.actual.json',ACTUAL/'joint.reconstructed.exact.json',HELPER/'SOURCE_PINS.json',HELPER/'qa_adapter.py',HELPER/'qa_contract.py',
        base_path,partial_path,PROJECT/'successor_qa/search_helper_coexist_install_r1/post_install_scope_readback_r1/actual/app-scope-after.private.json']
    outputs=[p for p in OUT.iterdir() if p.is_file() and p.name!='SOURCE_PINS.json']
    write_json('SOURCE_PINS.json',{'schema':'pocket4-fixed-search-sealed-packet-pins-v1','inputs':[pin(p) for p in inputs],
        'outputs':[pin(p) for p in sorted(outputs)],'staged_members':pins,'sealed_to_actual_completed_inspect':True,
        'remote_submitted':False,'action_performed':False,'private_UI_body_included':False})
    print(json.dumps({'state':'SEALED_NOT_SUBMITTED','owner':pin(OUT/'owned_fixed_search_click_once.py'),
        'stage_request':pin(OUT/'exact-stage-request.review-only.json'),'action_request':pin(OUT/'exact-action-request.review-only.json'),
        'seal_diff':pin(OUT/'SEAL_DIFF.patch'),'manifest':pin(OUT/'SOURCE_PINS.json'),'inputs':len(inputs),'outputs':len(outputs),
        'unchanged_source_r2_functions':len(definitions(before)),'controls':len(controls),'actual_action_result':None},sort_keys=True))


if __name__=='__main__':main()
