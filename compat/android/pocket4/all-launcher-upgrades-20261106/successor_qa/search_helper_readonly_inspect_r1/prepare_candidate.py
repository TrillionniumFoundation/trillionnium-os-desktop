#!/usr/bin/env python3
"""Local-only exact r2 inspect sealing after actual install and scope readback."""
import ast
import base64
import copy
import difflib
import hashlib
import json
from pathlib import Path
import types

PROJECT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = HERE / 'candidate-r1'
COEXIST = PROJECT / 'successor_qa/search_helper_coexist_install_r1'
ACTUAL = COEXIST / 'host-candidate-r1/actual-install'
SCOPE_ACTUAL = COEXIST / 'post_install_scope_readback_r1/actual'
HELPER = PROJECT / 'successor_qa/search_click_same_process_r1/candidate-r2/helper'
ROOT = '/home/alex/work/pocket4-beike-search-helper-r2-readonly-inspect-20261107-r1'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def pin(path, remote=None):
    raw = path.read_bytes()
    return {'path': remote or str(path.relative_to(PROJECT)), 'bytes': len(raw), 'sha256': sha(raw)}


def require_raw(path, count, digest):
    raw = path.read_bytes()
    assert len(raw) == count and sha(raw) == digest, str(path)
    return raw


def definitions(source):
    lines = source.splitlines(keepends=True)
    return {n.name: ''.join(lines[n.lineno - 1:n.end_lineno]) for n in ast.parse(source).body
            if isinstance(n, (ast.FunctionDef, ast.ClassDef))}


def load_definitions(path, name):
    value = types.ModuleType(name); value.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), value.__dict__)
    return value


def changed(source, old, new, expected=1):
    assert source.count(old) == expected, (old, source.count(old), expected)
    return source.replace(old, new)


def write(name, raw):
    if isinstance(raw, str):
        raw = raw.encode('utf-8')
    path = OUT / name
    if path.exists():
        assert path.read_bytes() == raw, 'Refuse frozen output change: ' + str(path)
    else:
        path.write_bytes(raw)
    return path


def write_json(name, value):
    return write(name, json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + '\n')


def main():
    raw = require_raw(ACTUAL / 'stdout.original.json', 33582, '5d7d4e22f8351a3ab58b99bb9236bda69bcf51a1a3a115f079f2834d8d83fbcf')
    term_raw = require_raw(ACTUAL / 'terminal.original.json', 733, '5350ed913cfb078591d6bf2a13a7fc39b7f74990d9e26009f38bb16a67365bfc')
    scope_raw = require_raw(SCOPE_ACTUAL / 'app-scope-after.private.json', 60614, '7187bc544cf6812ad47efdf141cd111897a1124b9532f84b7cf599b0c0fee1e3')
    require_raw(ACTUAL / 'root-validation.actual.json', 2365, 'a0f0f236e39d2af99fa68b9b585764471b4e30c53f3081ce490c18d38dba8e61')
    require_raw(SCOPE_ACTUAL / 'root-validation.actual.json', 1363, '27844d03beb3644ff5cdf2c4932db9d48d4ba5d2ba81d903bc1619daee7620c8')
    actual, terminal, scope = json.loads(raw), json.loads(term_raw), json.loads(scope_raw)
    child = json.loads(actual['child_stdout_original']); original = json.loads(child['original_stdout'])
    assert actual['helper_uid'] == 10167 and actual['observed_explicit_packages'] == 49 and actual['observed_APKs'] == 89
    assert actual['next_app_scope']['sha256'] == sha(scope_raw) and actual['next_app_scope']['bytes'] == len(scope_raw)
    assert original['installed_before_state'] == original['installed_after_state']
    ui_path = PROJECT / 'successor_qa/reusable_owned_ui_r1/owned_ui_request_once.py'
    old_source = require_raw(ui_path, 25377, 'c394598e477f1912378c6c3d582850a196e64f77791d0b7f5c4d498ec9b61e38').decode()
    ui = load_definitions(ui_path, 'original_ui_definitions_for_local_derivation')
    old = definitions(old_source)
    install_path = COEXIST / 'host-candidate-r1/owned_install_once.py'
    require_raw(install_path, 39677, '0288098834b039fad646331dce2caa2c4bde7166224a1b770866c7c09b5cae41')
    install = load_definitions(install_path, 'completed_install_pure_definitions_for_local_derivation')
    installer_path = COEXIST / 'candidate-r1/install_search_helper_full_scope.py'
    installer = load_definitions(installer_path, 'scope_transition_pure_actual_validator')
    parent_scope = json.loads((PROJECT / 'successor_install/source-r4-zbj-full48/candidate-r1/post_install_scope_readback_r1/actual/app-scope-after.private.json').read_bytes())
    transition = installer.validate_scope_transition(parent_scope, scope, original['build'], actual['helper_uid'], original['installed_after_state'])
    assert transition == original['whole_scope_after']['transition']
    assert actual['source'] == pin(install_path, install.ROOT + '/owned_install_once.py')
    # The original launch/ownership sources remain the actual r1 sources. Only
    # the new helper itself, completed install evidence and full49 input change.
    constants = {k: getattr(ui, k) for k in ('FLOW','BASE','SESSION','LAUNCH','LAUNCH_STDOUT','LAUNCH_TERMINAL',
        'SCOPE','LAUNCH_SCOPE_SHA','RECORDER_ROOT','TASK')}
    constants.update(ROOT=ROOT, ADAPTER=install.ADAPTER, HELPER_MANIFEST=install.HELPER_MANIFEST['sha256'],
        BUILD=install.BUILD_RESULT['path'], BUILD_SHA=install.BUILD_RESULT['sha256'], APK_SHA=install.APK['sha256'],
        SIGNER_SHA=install.SIGNER_SHA, HELPER_PACKAGE=actual['package'], HELPER_UID=actual['helper_uid'],
        INSTALL_OWNER=actual['source'], INSTALL_REQUEST=actual['request'], INSTALL_RESULT=actual['original_result'],
        INSTALL_JOB=terminal['job_id'], INSTALL_JOINT=actual['joint_artifact'],
        INSTALL_STDOUT=pin(ACTUAL / 'stdout.original.json', ROOT + '/install.stdout.original.json'),
        INSTALL_TERMINAL=pin(ACTUAL / 'terminal.original.json', ROOT + '/install.terminal.original.json'),
        CURRENT_SCOPE=actual['next_app_scope'], CURRENT_GUARD=installer.CURRENT_GUARD,
        RUNTIME_EPOCH=scope['runtime_epoch_sha256'], ALL_PACKAGES=sorted(scope['apps']),
        INSTALLED_HELPER=original['installed_after_state'], INSTALLED_HELPER_SCOPE_ROW=scope['apps'][actual['package']])
    plan = {'schema':1, 'operation':'inspect', 'nonces':{
        'before':'c20cae3e0baa4b0a8a329afba5fb11a6', 'inspect':'8598a0f4db21458f9a4a3924386b8ed1',
        'after':'7d1fb5b142df41e0a238ea4d0de4d7aa'}}
    plan_raw = canonical(plan) + b'\n'
    request = {'schema':'pocket4-fixed-r2-readonly-inspect-request-v1', 'kind':'plan',
        'step':'r2-readonly-inspect-01', 'payload_text':plan_raw.decode(), 'payload_sha256':sha(plan_raw)}
    constants['FIXED_REQUEST'] = request
    new = {}
    for name in ('need','sha','canonical','load_base','write_once','launch_gate'):
        new[name] = old[name]
    entry = old['entry']
    entry = changed(entry, "ROOT + '/owned_ui_request_once.py'", "ROOT + '/owned_readonly_inspect_once.py'")
    entry = changed(entry, "ROOT + '/request-' + sys.argv[7] + '.json'", "ROOT + '/request.json'")
    entry = changed(entry, "'REAL_REUSABLE_ENTRY_LOCATION'", "'REAL_FIXED_R2_READONLY_ENTRY_LOCATION'")
    new['entry'] = entry
    outer = old['outer_request']
    outer = changed(outer, "value['schema'] == 'pocket4-fixed-beike-owned-ui-request-v1' and value['kind'] in ('plan', 'case')", "value == FIXED_REQUEST and value['schema'] == 'pocket4-fixed-r2-readonly-inspect-request-v1' and value['kind'] == 'plan'")
    outer = changed(outer, "(16384 if value['kind'] == 'plan' else 49152)", '16384')
    new['outer_request'] = outer
    new['declared_request'] = '''def declared_request(raw, core, adapter, qa):
    request, body, payload = outer_request(raw, core)
    adapter.validate_plan(payload, qa)
    need(payload['operation'] == 'inspect', 'ONLY_ONE_COMPILED_READONLY_INSPECT')
    return request, body, payload, False'''
    new['original_argv'] = '''def original_argv(request, body_path):
    return [ADAPTER['path'], '--execute-once', '--interactive-production',
        '--source-manifest-sha256', HELPER_MANIFEST, '--build-receipt', BUILD,
        '--build-receipt-sha256', BUILD_SHA, '--apk-sha256', APK_SHA,
        '--signer-certificate-sha256', SIGNER_SHA,
        '--plan', str(body_path), '--plan-sha256', request['payload_sha256'],
        '--step', request['step'], '--recorder-root', RECORDER_ROOT,
        '--flow-dir', FLOW, '--helper-uid', str(HELPER_UID)]'''
    original_verify = old['verify_original']
    start = original_verify.index("    else:\n        need(result.get('schema')")
    end = original_verify.index("    return result,", start)
    verify = original_verify[:start] + original_verify[end:]
    verify = changed(verify, "result['installed_before'].get('uid') == 10157", "result['installed_before'].get('uid') == HELPER_UID")
    verify = changed(verify, "    need(raw.endswith(b'\\n')", "    need(mutation is False and request['kind'] == 'plan' and payload['operation'] == 'inspect', 'READONLY_PLAN_ONLY')\n    need(raw.endswith(b'\\n')")
    verify = changed(verify, "    return result,", "    need(result['installed_before'] == INSTALLED_HELPER and result['foreground_before'] == result['foreground_after'],\n         'ACTUAL_NORMAL_INSTALL_IDENTITY_AND_FULL_READONLY_FOREGROUND_UNCHANGED')\n    return result,")
    new['verify_original'] = verify
    child_source = old['child']
    child_source = changed(child_source, "'pocket4-fixed-reusable-owned-ui-child-v1'", "'pocket4-fixed-r2-readonly-inspect-child-v1'")
    child_source = changed(child_source, "        adapter = base.load(ADAPTER, 'unchanged_actual_owned_adapter')", "        result['completed_install'] = completed_install_gate(base, core)\n        result['whole_scope_before'] = whole_scope_guard(base, core)\n        adapter = base.load(ADAPTER, 'unchanged_actual_r2_owned_adapter')")
    child_source = changed(child_source, "        cases = base.load(CASE, 'unchanged_actual_bounded_case')\n", '')
    child_source = changed(child_source, 'declared_request(base.pinned(REQUEST), core, adapter, qa, cases)', 'declared_request(base.pinned(REQUEST), core, adapter, qa)')
    child_source = changed(child_source, "returned = (adapter if request['kind'] == 'plan' else cases).main()", 'returned = adapter.main()')
    child_source = changed(child_source, '        base.preserved(bodies, identities)\n', "        result['whole_scope_after'] = whole_scope_guard(base, core)\n        need(result['whole_scope_after'] == result['whole_scope_before'], 'ALL49_AND_TYPED_RUNTIME_CHANGED_DURING_INSPECT')\n        need(completed_install_gate(base, core) == result['completed_install'], 'ACTUAL_INSTALL_BUILD_B_AND_OLD_FAILURES_CHANGED')\n        base.preserved(bodies, identities)\n")
    child_source = changed(child_source, '(SELF, REQUEST, BASE, SESSION, ADAPTER, CASE, LAUNCH_STDOUT, LAUNCH_TERMINAL, base.RECORDER, base.CORE, base.SUPPORT, support.PROBE_SOURCE)', '(SELF, REQUEST, BASE, SESSION, ADAPTER, LAUNCH_STDOUT, LAUNCH_TERMINAL, INSTALL_OWNER, INSTALL_REQUEST, INSTALL_STDOUT, INSTALL_TERMINAL, CURRENT_SCOPE, CURRENT_GUARD, base.RECORDER, base.CORE, base.SUPPORT, support.PROBE_SOURCE)')
    child_source = changed(child_source, 'result.update(ok=True, original_result=result_pin,', 'result.update(ok=True, helper_uid=HELPER_UID, current_explicit_scope=CURRENT_SCOPE, original_result=result_pin,')
    new['child'] = child_source
    parent = old['parent']
    parent = changed(parent, 'def parent(publish):', 'def parent():')
    parent = changed(parent, "base = entry('--publish-and-execute' if publish else '--execute-request')", "base = entry('--execute-request')")
    parent = changed(parent, "'pocket4-fixed-reusable-owned-ui-result-v1'", "'pocket4-fixed-r2-readonly-inspect-result-v1'")
    start = parent.index('        if publish:\n'); end = parent.index('        request, _, _ = outer_request', start)
    parent = parent[:start] + parent[end:]
    parent = changed(parent, "probe.run_owned_child(argv, seconds=360 if request['kind'] == 'plan' else 600)", 'probe.run_owned_child(argv, seconds=360)')
    parent = changed(parent, "'pocket4-fixed-reusable-owned-ui-child-v1'", "'pocket4-fixed-r2-readonly-inspect-child-v1'")
    parent = changed(parent, "value.get('original_action_outcome_unknown') is value.get('declared_mutation'),", "value.get('original_action_outcome_unknown') is False and value.get('declared_mutation') is False and\n             value.get('helper_uid') == HELPER_UID and value.get('current_explicit_scope') == CURRENT_SCOPE and\n             value.get('whole_scope_before') == value.get('whole_scope_after') and\n             value.get('completed_install', {}).get('job_id') == INSTALL_JOB,")
    parent = changed(parent, '(SELF, REQUEST, BASE, SESSION, ADAPTER, CASE, LAUNCH_STDOUT, LAUNCH_TERMINAL, base.SUPPORT, support.PROBE_SOURCE)', '(SELF, REQUEST, BASE, SESSION, ADAPTER, LAUNCH_STDOUT, LAUNCH_TERMINAL, INSTALL_OWNER, INSTALL_REQUEST, INSTALL_STDOUT, INSTALL_TERMINAL, CURRENT_SCOPE, CURRENT_GUARD, base.SUPPORT, support.PROBE_SOURCE)')
    parent = changed(parent, "result.update(ok=True, step=request['step'], kind=request['kind'], original_result=value['original_result'],", "result.update(ok=True, step=request['step'], kind=request['kind'], original_result=value['original_result'],\n            helper_uid=HELPER_UID, current_explicit_scope=CURRENT_SCOPE, completed_install=value['completed_install'],\n            all49_guard_before_after_equal=True, full_PM_or_launcher_inventory_claimed=False,")
    new['parent'] = parent
    header = '#!/usr/bin/env python3\n"""One exact r2 readonly inspect over the unchanged owned QA adapter. No action or reconciliation."""\n'
    header += 'import contextlib\nimport hashlib\nimport io\nimport json\nimport os\nfrom pathlib import Path\nimport re\nimport stat\nimport sys\nimport types\n\nsys.dont_write_bytecode = True\n'
    header += '\n'.join(k + ' = ' + repr(v) for k,v in constants.items()) + '\nSELF = REQUEST = None\n\n\n'
    order = ['need','sha','canonical','load_base','entry','outer_request','declared_request','write_once','launch_gate','original_argv','verify_original']
    source = header + '\n\n\n'.join(new[n] for n in order) + '\n\n\n'
    source += (HERE / 'install_gate.fragment.py').read_text() + '\n\n\n' + new['child'] + '\n\n\n' + new['parent']
    source += "\n\n\nif __name__ == '__main__':\n    mode = sys.argv[1:2]\n    if mode == ['--child']:\n        raise SystemExit(child())\n    need(mode == ['--execute-request'], 'CLOSED_ONE_FIXED_READONLY_INSPECT_ENTRY')\n    raise SystemExit(parent())\n"
    compile(source, ROOT + '/owned_readonly_inspect_once.py', 'exec')
    # There is no case producer, alternate action entry, install owner entry or
    # unbound helper UID anywhere in the new execution graph.
    calls = [ast.unparse(n.func) for n in ast.walk(ast.parse(source)) if isinstance(n,ast.Call)]
    assert not any(n in calls for n in ('owner.parent','owner.child','owner.entry','owner.main','cases.main','installer.main'))
    assert not any(isinstance(n,ast.Name) and n.id=='CASE' for n in ast.walk(ast.parse(source)))
    OUT.mkdir(exist_ok=True)
    write('owned_readonly_inspect_once.py', source)
    write('request.json', canonical(request) + b'\n')
    write('plan.review-only.json', plan_raw)
    write('install.stdout.original.json', raw); write('install.terminal.original.json', term_raw)
    write('OWNER_DIFF.patch', ''.join(difflib.unified_diff(old_source.splitlines(True),source.splitlines(True),
        fromfile=str(ui_path.relative_to(PROJECT)),tofile=str((OUT/'owned_readonly_inspect_once.py').relative_to(PROJECT)))))
    names = ['owned_readonly_inspect_once.py','request.json','install.stdout.original.json','install.terminal.original.json']
    pins = {name:{k:v for k,v in pin(OUT/name).items() if k!='path'} for name in names}
    payload = {'schema':'pocket4-r2-readonly-inspect-source-stage-payload-v1','root':ROOT,
        'files':{name:dict(pins[name],base64=base64.b64encode((OUT/name).read_bytes()).decode()) for name in names}}
    payload_raw = canonical(payload)+b'\n'; assert len(payload_raw)<=524288
    write('stage-input.json', payload_raw)
    old_stage_path = COEXIST / 'host-candidate-r1/stage_source_once.py'; old_stage = old_stage_path.read_text()
    stage = old_stage
    lines = stage.splitlines(keepends=True)
    assignments = {n.targets[0].id:n for n in ast.parse(stage).body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name)}
    changes = {'ROOT': 'Path('+repr(ROOT)+')', 'PINS':repr(pins), 'PAYLOAD_SHA':repr(sha(payload_raw))}
    for name in sorted(changes,key=lambda k:assignments[k].lineno,reverse=True):
        n=assignments[name];lines[n.lineno-1:n.end_lineno]=[name+' = '+changes[name]+'\n']
    stage=''.join(lines)
    stage=stage.replace('pocket4-search-helper-coexist-source-stage-payload-v1','pocket4-r2-readonly-inspect-source-stage-payload-v1')
    stage=stage.replace('pocket4-search-helper-coexist-source-stage-v1','pocket4-r2-readonly-inspect-source-stage-v1')
    stage=stage.replace('pocket4-beike-search-helper-coexist-install-20261106-r1',ROOT.rsplit('/',1)[-1])
    stage=stage.replace('source-only-normal-coexist-installer-not-invoked','source-only-readonly-inspect-owner-not-invoked')
    stage=stage.replace('Publish only the fixed coexistence owner and completed build/B receipts. No Android entry.',
                        'Publish the fixed readonly inspect owner and actual install receipts. No Android entry.')
    compile(stage,'<readonly-source-stage>','exec')
    assert all(definitions(stage)[n]==definitions(old_stage)[n] for n in ('need','sha','census'))
    write('stage_source_once.py',stage)
    write('STAGE_DIFF.patch',''.join(difflib.unified_diff(old_stage.splitlines(True),stage.splitlines(True),
        fromfile=str(old_stage_path.relative_to(PROJECT)),tofile=str((OUT/'stage_source_once.py').relative_to(PROJECT)))))
    common={'host':'pocket4','executable':'/usr/bin/sudo','cwd':'/home/alex/work','nice':10}
    stage_packet=dict(common,args=['-n','/usr/bin/python3','-I','-B','-c',stage,'--payload-sha256',sha(payload_raw)],stdin=payload_raw.decode(),
        cpu_quota_percent=50,memory_max_bytes=268435456,timeout_seconds=60,idempotency_key='pocket4-beike-r2-readonly-inspect-source-stage-r1-20261107')
    p,q=pins['owned_readonly_inspect_once.py'],pins['request.json']
    execute_packet=dict(common,args=['-n','/usr/bin/python3','-I','-B',ROOT+'/owned_readonly_inspect_once.py','--execute-request',
        '--source-sha256',p['sha256'],'--source-bytes',str(p['bytes']),'--request-sha256',q['sha256'],'--request-bytes',str(q['bytes'])],
        cpu_quota_percent=100,memory_max_bytes=536870912,timeout_seconds=480,
        idempotency_key='pocket4-beike-r2-readonly-inspect-once-r1-20261107')
    write_json('exact-stage-request.review-only.json',stage_packet)
    write_json('exact-inspect-request.review-only.json',execute_packet)
    local_owner=load_definitions(OUT/'owned_readonly_inspect_once.py','local_readonly_owner_control_definitions')
    base_path=PROJECT/'successor_qa/owned_cleanup_r1/cleanup_owned_task_once.py'
    partial_path=PROJECT/'successor_qa/no_action_runtime_commit_r1/stage-a-candidate-r1/no_action_core.py'
    base=load_definitions(base_path,'local_normal_exit_only');partial=load_definitions(partial_path,'local_terminal_only')
    controls=[]
    def check(name,fn,reject=False):
        try: fn()
        except RuntimeError as error:
            assert reject,(name,str(error));controls.append({'name':name,'passed':True,'rejection':str(error)})
        else:
            assert not reject,name;controls.append({'name':name,'passed':True})
    check('actual_install_original_stdout_terminal_and_owned_child_header',lambda:local_owner.completed_install_header(base,partial,raw,terminal))
    check('actual49_full_original_scope',lambda:local_owner.validate_scope49(scope))
    bad=copy.deepcopy(scope);del bad['apps'][next(p for p in bad['apps'] if p!=actual['package'])]
    check('drop_one_protected_package_rejected',lambda:local_owner.validate_scope49(bad),True)
    bad_term=dict(terminal);bad_term['output_durable']=False
    check('install_not_durable_rejected',lambda:local_owner.completed_install_header(base,partial,raw,bad_term),True)
    parser=types.SimpleNamespace(document=json.loads)
    check('exact_readonly_request',lambda:local_owner.outer_request(canonical(request)+b'\n',parser))
    bad_request=dict(request);bad_plan=copy.deepcopy(plan);bad_plan['operation']='search_click';bad_request['payload_text']=canonical(bad_plan).decode();bad_request['payload_sha256']=sha(canonical(bad_plan))
    check('any_action_request_rejected',lambda:local_owner.outer_request(canonical(bad_request)+b'\n',parser),True)
    write_json('LOCAL_CONTROLS.json',{'schema':'pocket4-r2-readonly-inspect-local-integration-controls-v1','status':'PASS_LOCAL_ONLY',
        'count':len(controls),'cases':controls,'source_bound_actual_helper_UID':actual['helper_uid'],
        'actual_scope_raw_used':pin(SCOPE_ACTUAL/'app-scope-after.private.json'),'full_host_history_recheck_executed_locally':False,
        'remote_processes':0,'new_Main_or_UI_observations':0,'production_ready':False})
    inheritance={'schema':'pocket4-r2-readonly-inspect-source-inheritance-v1','parent':pin(ui_path),
        'unchanged_functions':[n for n in ('need','sha','canonical','load_base','write_once','launch_gate') if new[n]==old[n]],
        'changed_original_functions':['entry','outer_request','declared_request','original_argv','verify_original','child','parent'],
        'added_functions':list(definitions((HERE/'install_gate.fragment.py').read_text())),
        'original_helper15files_unchanged':True,'original_adapter_main_and_Session_unchanged':True,
        'source_reuses_actual_completed_install_definitions_without_execution':pin(install_path),
        'original_ownership_launch_AND_old_unknown_proof_preserved':True,
        'fixed_kind':'plan','only_operation':'inspect','new_app_or_task_launch':False,'private_UI_in_public_packet':False,
        'full49_fences':'Original current_guard + exact current 49 identities immediately before and after original entry. Original adapter alone owns actions lock; no nested lock added. Existing per-command typed/App/helper/task/window guards stay unchanged.',
        'resources':{'owned_child_seconds':360,'outer_seconds':480,'cpu_percent':100,'memory_bytes':536870912,
                     'child_stdout_limit':131072,'child_stderr_limit':16384,'parent_stdout_limit':262144},
        'resource_reference':pin(PROJECT/'successor_qa/inspect_after_partial_commit_r1/process-request.review-only.json'),
        'new_readonly_runtime_result':None,'production_ready':False}
    write_json('SOURCE_INHERITANCE.json',inheritance)
    plan_review={'schema':'pocket4-r2-readonly-inspect-reviewed-plan-v1','state':'SEALED_FOR_REVIEW_NOT_SUBMITTED',
        'helper_package':actual['package'],'helper_UID':actual['helper_uid'],'actual_current_scope':actual['next_app_scope'],
        'actual_install_job':terminal['job_id'],'actual_install_joint':actual['joint_artifact'],'root':ROOT,'flow':constants['FLOW'],
        'step':request['step'],'operation':'inspect','source_stage_invokes_owner':False,
        'expected_sequence':'Original state-before, current full foreground, full inspect, independent state-after, same foreground/task/helper and accessibility restoration. No input dispatch.',
        'fresh_observation_not_a_search_success_assertion':True,
        'later_action':'Search navigation and editor controls remain unknown. A future fixed search_click requires a separately reviewed new request and independent actual post-inspection. Do not use preexisting homepage 搜索 TextView as navigation proof.',
        'all49_current_fence_check_before_and_after':True,'full_PM_or_launcher_enumeration_claimed':False,
        'coordination':'Root must keep other Main writes/UI/lifecycle serialized while this original Flow/actions-lock entry and owned-child termination are in flight. Public-network host-only jobs may continue.',
        'old_FAILED_UNKNOWN_and_r1_helper_retained':True,'automatic_retry':False,'UI_input_actions':0,'permission_changes':0,
        'installs':0,'cleanup_bytes':0,'production_ready':False,'requests':[pin(OUT/'exact-stage-request.review-only.json'),pin(OUT/'exact-inspect-request.review-only.json')]}
    write_json('EXECUTION_PLAN.json',plan_review)
    inputs=[Path(__file__),HERE/'install_gate.fragment.py',ui_path,install_path,installer_path,
        HELPER/'SOURCE_PINS.json',HELPER/'qa_adapter.py',HELPER/'qa_contract.py',base_path,partial_path,
        ACTUAL/'stdout.original.json',ACTUAL/'terminal.original.json',ACTUAL/'root-validation.actual.json',
        SCOPE_ACTUAL/'app-scope-after.private.json',SCOPE_ACTUAL/'stdout.original.json',SCOPE_ACTUAL/'terminal.original.json',SCOPE_ACTUAL/'root-validation.actual.json',
        PROJECT/'recovery/independent_repair_r2/actual-execute-01/current_baseline_guard.py',old_stage_path,
        PROJECT/'successor_qa/inspect_after_partial_commit_r1/process-request.review-only.json']
    outputs=[p for p in OUT.iterdir() if p.is_file() and p.name!='SOURCE_PINS.json']
    write_json('SOURCE_PINS.json',{'schema':'pocket4-r2-readonly-inspect-frozen-packet-pins-v1','inputs':[pin(p) for p in inputs],
        'outputs':[pin(p) for p in sorted(outputs)],'staged_members':pins,'scope_original_not_reconstructed':True,
        'request_sealed':True,'remote_submitted':False,'private_UI_body_included':False})
    print(json.dumps({'status':'SEALED_LOCAL_ONLY','root':str(OUT),'owner':pin(OUT/'owned_readonly_inspect_once.py'),
        'stage_request':pin(OUT/'exact-stage-request.review-only.json'),'inspect_request':pin(OUT/'exact-inspect-request.review-only.json'),
        'manifest':pin(OUT/'SOURCE_PINS.json'),'inputs':len(inputs),'outputs':len(outputs),'controls':len(controls),
        'actual_bound_UID':actual['helper_uid'],'actual_current_scope':actual['next_app_scope'],'remote_calls':0},sort_keys=True))


if __name__=='__main__':
    main()
