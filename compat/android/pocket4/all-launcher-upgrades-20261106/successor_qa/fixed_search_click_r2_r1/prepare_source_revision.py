#!/usr/bin/env python3
"""Prepare only fixed search_click source; actual inspect inputs remain unbound.

No process packet is emitted. No remote or Android operation is performed.
"""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import types

PROJECT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = HERE / 'source-r1'
PARENT = PROJECT / 'successor_qa/search_helper_readonly_inspect_r1/candidate-r1'
ROOT = '/home/alex/work/pocket4-beike-r2-fixed-search-click-20261107-r1'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path, remote=None):
    raw = path.read_bytes()
    return {'path':remote or str(path.relative_to(PROJECT)), 'bytes':len(raw), 'sha256':sha(raw)}


def definitions(source):
    lines=source.splitlines(keepends=True)
    return {n.name:''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)}


def replace_once(source, old, new):
    assert source.count(old)==1,(old,source.count(old))
    return source.replace(old,new)


def save(name, raw):
    if isinstance(raw,str): raw=raw.encode('utf-8')
    path=OUT/name
    if path.exists(): assert path.read_bytes()==raw, str(path)
    else: path.write_bytes(raw)
    return path


def json_file(name, value):
    return save(name,json.dumps(value,ensure_ascii=True,sort_keys=True,indent=2)+'\n')


def main():
    parent_path=PARENT/'owned_readonly_inspect_once.py'
    before=parent_path.read_text()
    assert len(before.encode())==37462 and sha(before.encode())=='a7734300638acbd93535b2bdf03df8af2bf186e782cba47809bab058e5379ab1'
    current=types.ModuleType('local_fixed_readonly_owner_definitions');current.__file__=str(parent_path)
    exec(compile(before,str(parent_path),'exec'),current.__dict__)
    constants={}
    for node in ast.parse(before).body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            name=node.targets[0].id
            if name!='SELF' and hasattr(current,name): constants[name]=getattr(current,name)
    constants.update(ROOT=ROOT, FIXED_REQUEST=None, INSPECT_INPUTS_BOUND=False,
        INSPECT_OWNER=pin(parent_path,current.ROOT+'/owned_readonly_inspect_once.py'),
        INSPECT_REQUEST=pin(PARENT/'request.json',current.ROOT+'/request.json'),
        INSPECT_JOB=None, INSPECT_STDOUT=None, INSPECT_TERMINAL=None,
        INSPECT_RESULT=None, INSPECT_JOINT=None, INSPECT_WIRE_SHA=None)
    old=definitions(before); new=dict(old)
    entry=new['entry']
    entry=replace_once(entry,'    global SELF, REQUEST\n',
        "    global SELF, REQUEST\n    need(INSPECT_INPUTS_BOUND is True and FIXED_REQUEST is not None, 'ACTUAL_R2_INSPECT_AND_ACTION_REQUEST_NOT_YET_BOUND')\n")
    entry=replace_once(entry,"ROOT + '/owned_readonly_inspect_once.py'","ROOT + '/owned_fixed_search_click_once.py'")
    entry=replace_once(entry,"'REAL_FIXED_R2_READONLY_ENTRY_LOCATION'","'REAL_FIXED_R2_SEARCH_CLICK_ENTRY_LOCATION'")
    new['entry']=entry
    new['outer_request']=replace_once(new['outer_request'],'pocket4-fixed-r2-readonly-inspect-request-v1','pocket4-fixed-r2-search-click-request-v1')
    new['declared_request']='''def declared_request(raw, core, adapter, qa):
    request, body, payload = outer_request(raw, core)
    adapter.validate_plan(payload, qa)
    need(payload['operation'] == 'search_click' and payload['selector'] == qa.SEARCH_SELECTOR,
         'ONLY_THE_COMPILED_FIXED_BEIKE_SEARCH_CLICK')
    return request, body, payload, True'''
    verify=new['verify_original']
    verify=replace_once(verify,"mutation is False and request['kind'] == 'plan' and payload['operation'] == 'inspect', 'READONLY_PLAN_ONLY'",
        "mutation is True and request['kind'] == 'plan' and payload['operation'] == 'search_click', 'FIXED_SEARCH_CLICK_PLAN_ONLY'")
    verify=replace_once(verify,"    need(result['installed_before'] == INSTALLED_HELPER and result['foreground_before'] == result['foreground_after'],\n         'ACTUAL_NORMAL_INSTALL_IDENTITY_AND_FULL_READONLY_FOREGROUND_UNCHANGED')",
        "    need(result['installed_before'] == INSTALLED_HELPER, 'ACTUAL_NORMAL_INSTALL_IDENTITY_UNCHANGED')\n    need(result.get('search_click_acknowledged') is True and result.get('atomic_android_transaction') is False and\n         type(result.get('search_selection_sha256')) is str and re.fullmatch('[0-9a-f]{64}', result['search_selection_sha256']),\n         'EXACT_ORIGINAL_FIXED_SEARCH_ACK_AND_FULL_TREE_SELECTION')")
    new['verify_original']=verify
    child=new['child']
    child=replace_once(child,'pocket4-fixed-r2-readonly-inspect-child-v1','pocket4-fixed-r2-search-click-child-v1')
    child=replace_once(child,"        result['completed_install'] = completed_install_gate(base, core)",
        "        result['prior_readonly_inspect'] = prior_inspect_gate(base, core)\n        result['completed_install'] = completed_install_gate(base, core)")
    child=replace_once(child,"        base.preserved(bodies, identities)",
        "        need(prior_inspect_gate(base, core) == result['prior_readonly_inspect'], 'ACTUAL_PRIOR_INSPECT_EVIDENCE_CHANGED')\n        base.preserved(bodies, identities)")
    child=replace_once(child,"INSTALL_STDOUT, INSTALL_TERMINAL, CURRENT_SCOPE, CURRENT_GUARD, base.RECORDER",
        "INSTALL_STDOUT, INSTALL_TERMINAL, INSPECT_OWNER, INSPECT_REQUEST, INSPECT_STDOUT, INSPECT_TERMINAL, CURRENT_SCOPE, CURRENT_GUARD, base.RECORDER")
    child=replace_once(child,"result.update(ok=True, helper_uid=HELPER_UID, current_explicit_scope=CURRENT_SCOPE, original_result=result_pin,",
        "result.update(ok=True, helper_uid=HELPER_UID, current_explicit_scope=CURRENT_SCOPE, original_result=result_pin,\n            search_click_acknowledged=original['search_click_acknowledged'], search_selection_sha256=original['search_selection_sha256'],\n            atomic_android_transaction=False, search_page_navigation_verified=False, independent_after_inspect_required=True,")
    new['child']=child
    parent=new['parent']
    parent=replace_once(parent,'pocket4-fixed-r2-readonly-inspect-result-v1','pocket4-fixed-r2-search-click-result-v1')
    parent=replace_once(parent,'pocket4-fixed-r2-readonly-inspect-child-v1','pocket4-fixed-r2-search-click-child-v1')
    parent=replace_once(parent,"value.get('original_action_outcome_unknown') is False and value.get('declared_mutation') is False and",
        "value.get('original_action_attempted') is True and value.get('original_action_outcome_unknown') is True and\n             value.get('declared_mutation') is True and value.get('search_click_acknowledged') is True and\n             value.get('atomic_android_transaction') is False and value.get('search_page_navigation_verified') is False and\n             value.get('independent_after_inspect_required') is True and\n             value.get('prior_readonly_inspect', {}).get('job_id') == INSPECT_JOB and")
    parent=replace_once(parent,"INSTALL_STDOUT, INSTALL_TERMINAL, CURRENT_SCOPE, CURRENT_GUARD, base.SUPPORT",
        "INSTALL_STDOUT, INSTALL_TERMINAL, INSPECT_OWNER, INSPECT_REQUEST, INSPECT_STDOUT, INSPECT_TERMINAL, CURRENT_SCOPE, CURRENT_GUARD, base.SUPPORT")
    parent=replace_once(parent,"all49_guard_before_after_equal=True, full_PM_or_launcher_inventory_claimed=False,",
        "all49_guard_before_after_equal=True, full_PM_or_launcher_inventory_claimed=False,\n            prior_readonly_inspect=value['prior_readonly_inspect'], search_click_acknowledged=True,\n            search_selection_sha256=value['search_selection_sha256'], atomic_android_transaction=False,\n            search_page_navigation_verified=False, independent_after_inspect_required=True,")
    new['parent']=parent
    header='#!/usr/bin/env python3\n"""Source-only fixed search_click revision. Disabled until actual inspect inputs and exact request are bound."""\n'
    header+='import contextlib\nimport hashlib\nimport io\nimport json\nimport os\nfrom pathlib import Path\nimport re\nimport stat\nimport sys\nimport types\n\nsys.dont_write_bytecode = True\n'
    header+='\n'.join(k+' = '+repr(v) for k,v in constants.items())+'\nSELF = REQUEST = None\n\n\n'
    order=list(old)
    source=header+'\n\n\n'.join(new[k] for k in order if k not in ('child','parent'))+'\n\n\n'
    source+=(HERE/'prior_inspect_gate.fragment.py').read_text()+'\n\n\n'+new['child']+'\n\n\n'+new['parent']
    source+="\n\n\nif __name__ == '__main__':\n    mode = sys.argv[1:2]\n    if mode == ['--child']:\n        raise SystemExit(child())\n    need(mode == ['--execute-request'], 'CLOSED_ONE_FIXED_SEARCH_CLICK_ENTRY')\n    raise SystemExit(parent())\n"
    compile(source,ROOT+'/owned_fixed_search_click_once.py','exec')
    code=types.ModuleType('unbound_action_source_local_control');code.__file__=ROOT+'/owned_fixed_search_click_once.py'
    exec(compile(source,code.__file__,'exec'),code.__dict__)
    try:code.entry('--execute-request')
    except RuntimeError as error: assert str(error)=='ACTUAL_R2_INSPECT_AND_ACTION_REQUEST_NOT_YET_BOUND'
    else:raise AssertionError('unbound source accepted entry')
    assert code.INSPECT_INPUTS_BOUND is False and code.FIXED_REQUEST is None
    assert "result['foreground_before'] == result['foreground_after']" not in new['verify_original']
    assert "result.get('outcome_unknown') is mutation" in new['verify_original']
    changed_names=[k for k in old if old[k]!=new[k]]
    assert changed_names==['entry','outer_request','declared_request','verify_original','child','parent'],changed_names
    OUT.mkdir(exist_ok=True)
    save('owned_fixed_search_click_once.py',source)
    save('SOURCE_DIFF.patch',''.join(difflib.unified_diff(before.splitlines(True),source.splitlines(True),
        fromfile=str(parent_path.relative_to(PROJECT)),tofile=str((OUT/'owned_fixed_search_click_once.py').relative_to(PROJECT)))))
    summary={'schema':'pocket4-fixed-r2-search-click-source-preparation-v1','state':'UNBOUND_SOURCE_ONLY_NO_PROCESS_REQUEST',
        'parent':pin(parent_path),'source':pin(OUT/'owned_fixed_search_click_once.py'),
        'changed_original_functions':changed_names,'unchanged_original_functions':[k for k in old if k not in changed_names],
        'added_functions':list(definitions((HERE/'prior_inspect_gate.fragment.py').read_text())),
        'helper_source_and_original_adapter_Session_modified':False,
        'only_proposed_operation':'search_click','selector_source':'unchanged compiled qa.SEARCH_SELECTOR',
        'generic_click_set_text_case_player_operations_opened':False,
        'mutation_semantics':'Original action_attempted=true/outcome_unknown=true even after acknowledged successful action. No postcondition reconciliation is performed.',
        'foreground_semantics':'Original Session permits search_click navigation with changed activity/window inside the same target package and exact owned task; do not compare foreground_before to foreground_after in this action owner. Original action-window, task, helper and before/after state restoration guards remain.',
        'next_observation':'One separately reviewed independent readonly inspect after action actual terminal. Do not loop or retry; do not infer navigation from homepage 搜索 TextView.',
        'new_fresh_inspection_required_by_action':True,'prior_readonly_nodes_reused_for_dispatch':False,
        'actual_r2_inspect_job':None,'actual_r2_inspect_stdout':None,'actual_r2_inspect_terminal':None,
        'action_request':None,'source_entry_refuses_unbound_inputs':True,'static_compilation_only':True,
        'resource_budgets_changed':False,'remote_calls':0,'UI_actions':0,'production_ready':False}
    json_file('PREPARATION.json',summary)
    inputs=[Path(__file__),HERE/'prior_inspect_gate.fragment.py',parent_path,PARENT/'request.json',PARENT/'SOURCE_PINS.json',
        PROJECT/'successor_qa/search_click_same_process_r1/candidate-r2/helper/qa_adapter.py',
        PROJECT/'successor_qa/search_click_same_process_r1/candidate-r2/helper/qa_contract.py']
    outputs=[p for p in OUT.iterdir() if p.is_file() and p.name!='SOURCE_PINS.json']
    json_file('SOURCE_PINS.json',{'schema':'pocket4-fixed-search-unbound-source-pins-v1','inputs':[pin(p) for p in inputs],
        'outputs':[pin(p) for p in sorted(outputs)],'source_entry_disabled':True,'execution_request_created':False,
        'no_remote_or_UI_operation':True})
    print(json.dumps({'state':summary['state'],'source':pin(OUT/'owned_fixed_search_click_once.py'),
        'diff':pin(OUT/'SOURCE_DIFF.patch'),'preparation':pin(OUT/'PREPARATION.json'),
        'manifest':pin(OUT/'SOURCE_PINS.json'),'changed_functions':changed_names,
        'unchanged_functions':len(summary['unchanged_original_functions']),'execution_request_created':False},sort_keys=True))


if __name__=='__main__':
    main()
