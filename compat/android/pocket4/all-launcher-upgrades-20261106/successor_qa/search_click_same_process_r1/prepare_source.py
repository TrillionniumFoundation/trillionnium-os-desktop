#!/usr/bin/env python3
"""Derive an isolated, closed fixed-search helper from the actual r2 source closure.

This is local source preparation only. It calls neither the generator's live
binding acquisition nor any builder, installer, recorder, or Android entry.
"""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
PARENT = PROJECT / 'successor_qa/reconstructed/source-generation-r2/helper'
OUTPUT = HERE / 'candidate-r1/helper'


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def replace(source, before, after, count=1):
    need(source.count(before) == count, 'EXACT_SOURCE_ANCHOR:' + before[:100])
    return source.replace(before, after)


def functions(source):
    return {node.name: ast.get_source_segment(source, node) for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef)}


def main():
    spec_raw = (HERE / 'GENERATION_SPEC.json').read_bytes()
    spec = json.loads(spec_raw)
    raw = (PARENT / 'SOURCE_PINS.json').read_bytes()
    need(len(raw) == 2431 and sha(raw) == 'dfb9b6a483f1069847433152b9b2e8b0f1b2cdd571a1dbde3068fc9393ad62c4', 'ACTUAL_PARENT_MANIFEST_PIN')
    parent_manifest = json.loads(raw)
    need(len(parent_manifest['files']) == 13 and parent_manifest['helper_package'] == spec['old_package'], 'ACTUAL_THIRTEEN_SOURCE_CLOSURE')
    parent = {}
    for name, pin in parent_manifest['files'].items():
        body = (PARENT / name).read_bytes()
        need(pin == {'bytes': len(body), 'sha256': sha(body)}, 'ACTUAL_PARENT_SOURCE_PIN:' + name)
        parent[name] = body.decode()
    old, new = spec['old_package'], spec['package']
    old_path, new_path = old.replace('.', '/'), new.replace('.', '/')
    need(new == 'org.droidloom.qa.successor.p8f89f253350ba2fa.r2' and
         spec['allowed_operations'] == ['state', 'inspect', 'search_click'] and
         re.fullmatch('[0-9a-f]{32}', spec['generation_nonce']), 'FIXED_NEW_OPERATION_AND_PACKAGE')
    texts = {name.replace(old_path, new_path): value.replace(old, new).replace(old_path, new_path)
             for name, value in parent.items()}
    java_name = 'src/' + new_path + '/ActionRunner.java'
    java = texts[java_name]
    java = replace(java, 'Arrays.asList("state", "inspect", "click", "set_text").contains(op)',
                   'Arrays.asList("state", "inspect", "search_click").contains(op)')
    java = replace(java, '            else if (op.equals("reveal_controls")) keys(request,',
                   '            else if (op.equals("search_click")) keys(request, "protocol", "nonce", "op", "scope", "inspection_nonce", "inspection_sha256", "node_path", "node_sha256");\n'
                   '            else if (op.equals("reveal_controls")) keys(request,')
    java = replace(java, '                } else if (op.equals("reveal_controls")) revealControls(request, result);',
                   '                } else if (op.equals("search_click")) searchClick(request, result);\n'
                   '                else if (op.equals("reveal_controls")) revealControls(request, result);')
    fragment_java = (HERE / 'fragments/search_click.java').read_text()
    java = replace(java, '    void act(JSONObject request, JSONObject result) throws Exception {',
                   fragment_java + '\n    void act(JSONObject request, JSONObject result) throws Exception {')
    texts[java_name] = java
    q = texts['qa_contract.py']
    q = replace(q, "ALLOWED_OPERATIONS = ('state', 'inspect', 'click', 'set_text')", "ALLOWED_OPERATIONS = ('state', 'inspect', 'search_click')")
    q = replace(q, "if op in ('inspect', 'click', 'set_text','reveal_controls','player_button'):",
                   "if op in ('inspect', 'click', 'set_text','reveal_controls','player_button','search_click'):")
    q = replace(q, "if op in ('click','set_text'):", "if op in ('click','set_text','search_click'):")
    q = replace(q, "require(op in ('state', 'inspect', 'click', 'set_text','reveal_controls','player_button') and set(value) == expected",
                   "require(op in ('state', 'inspect', 'click', 'set_text','reveal_controls','player_button','search_click') and set(value) == expected")
    q = replace(q, "        elif request['op']=='reveal_controls':", "        elif request['op']=='search_click':\n            assess_search_click(value,request,observed_window,observed_trees,observed_idle)\n        elif request['op']=='reveal_controls':")
    q = replace(q, "    if operation!='inspect':", "    if operation not in ('inspect','search_click'):")
    q = replace(q, "              if operation=='player_button' else ['action_target','action_final_window'])",
                   "              if operation=='player_button' else ['search_selection','action_target','action_final_window']\n              if operation=='search_click' else ['action_target','action_final_window'])")
    q = replace(q, "    if request['op']=='reveal_controls' and 'touch' in value:",
                   "    if request['op']=='search_click':\n        result['search_failure']=search_failure_diagnostic(value)\n    if request['op']=='reveal_controls' and 'touch' in value:")
    q = replace(q, 'helper_uid not in (UID, 10125,', 'helper_uid not in (UID, 10157, 10125,')
    q += '\n\n' + (HERE / 'fragments/search_contract.py').read_text()
    texts['qa_contract.py'] = q
    adapter = texts['qa_adapter.py']
    adapter = replace(adapter, "helper_uid not in (10117,10125,", "helper_uid not in (10117,10157,10125,")
    adapter = replace(adapter, "plan.get('operation') in ('state','inspect','click','set_text','reveal_controls','player_button')",
                      "plan.get('operation') in ('state','inspect','click','set_text','reveal_controls','player_button','search_click')")
    adapter = replace(adapter, "    if op in ('click','set_text'):", "    if op in ('click','set_text','search_click'):")
    adapter = replace(adapter, "    if op == 'set_text':", "    if op == 'search_click':\n        require(plan['selector'] == qa.SEARCH_SELECTOR, 'ONLY_FIXED_BEIKE_SEARCH_SELECTOR')\n    if op == 'set_text':")
    adapter = replace(adapter, "({'action'} if op in ('click','set_text','reveal_controls','player_button') else set())",
                      "({'action'} if op in ('click','set_text','reveal_controls','player_button','search_click') else set())")
    adapter = replace(adapter, "mutation=request['op'] in ('click','set_text','reveal_controls','player_button')",
                      "mutation=request['op'] in ('click','set_text','reveal_controls','player_button','search_click')")
    adapter = replace(adapter, "            elif plan['operation']=='reveal_controls':", '''            elif plan['operation']=='search_click':
                node = qa.fixed_search_node(inspected['helper']['inspection'])
                action = request('action','search_click',scope=scope,inspection_nonce=names['inspect'],
                    inspection_sha256=inspected['wire_sha256'],**node)
                middle = None
                middle = self.instrument(action)
                require(middle['helper']['action_window'] == inspected['helper']['inspection']['window'],
                        'SEARCH_ACKNOWLEDGED_STABLE_WINDOW_DIFFERS')
                result['search_click_acknowledged'] = True
                result['search_selection_sha256'] = middle['helper']['search_selection_sha256']
                result['atomic_android_transaction'] = False
            elif plan['operation']=='reveal_controls':''')
    adapter = replace(adapter, "mutation=plan['operation'] in ('click','set_text','reveal_controls','player_button')",
                      "mutation=plan['operation'] in ('click','set_text','reveal_controls','player_button','search_click')")
    adapter = replace(adapter, "'operations':['state','inspect','click','set_text','reveal_controls','player_button']",
                      "'operations':['state','inspect','search_click']")
    adapter = replace(adapter, "BUILD_COMMANDS = ['idle-gate-javac','idle-gate-java','javac'",
                      "BUILD_COMMANDS = ['idle-gate-javac','idle-gate-java','search-gate-javac','search-gate-java','javac'")
    adapter = replace(adapter, "    scope_controls = receipt.get('current_baseline_scope_controls', {})", '''    search_protocol = receipt.get('search_protocol_controls', {})
    search_gate = receipt.get('search_transaction_controls', {})
    builder.validate_idle_controls(search_protocol.get('report'), builder.SEARCH_PROTOCOL_CASES, manifest['files']['qa_contract.py']['sha256'])
    builder.validate_idle_controls(search_gate.get('report'), builder.SEARCH_GATE_CASES)
    require(search_protocol.get('control_source_sha256') == manifest['files']['check_search_contract.py']['sha256'] and
            search_gate.get('control_source_sha256') == manifest['files']['tests/SearchTransactionChecks.java']['sha256'] and
            search_gate.get('gate_source_sha256') == manifest['files']['src/''' + new_path + '''/PlayerButtonTransaction.java']['sha256'] and
            search_gate.get('stdout_sha256') == commands[3]['stdout_sha256'], 'ACTUAL_NEW_SEARCH_CONTROLS_REQUIRED')
    scope_controls = receipt.get('current_baseline_scope_controls', {})''')
    texts['qa_adapter.py'] = adapter
    texts['run_case.py'] = replace(texts['run_case.py'],
        "plan['operation'] in ('inspect','click','set_text','reveal_controls','player_button')",
        "plan['operation'] in ('inspect','click','set_text','reveal_controls','player_button','search_click')")
    tests_py = (HERE / 'fragments/check_search_contract.py').read_text()
    tests_java = (HERE / 'fragments/SearchTransactionChecks.java').read_text()
    texts['check_search_contract.py'] = tests_py
    texts['tests/SearchTransactionChecks.java'] = tests_java
    cases_py = [node for node in ast.parse(tests_py).body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CASES' for t in node.targets)]
    need(len(cases_py) == 1, 'EXACT_SEARCH_PARSER_CASES')
    protocol_cases = ast.literal_eval(cases_py[0].value)
    gate_cases = re.findall(r'"([a-z0-9_]+)"', tests_java.split('static final String[] NAMES = {',1)[1].split('};',1)[0])
    builder = texts['build_candidate.py']
    builder = replace(builder, "OUTPUT = Path('/home/alex/work/pocket4-successor-qa-build-b34f158f88bbebf112840fd88df25d03')",
                      "OUTPUT = Path('/home/alex/work/pocket4-successor-qa-build-" + spec['generation_nonce'] + "')")
    builder = replace(builder, 'IDLE_GATE_CASES = [', 'SEARCH_PROTOCOL_CASES = ' + repr(protocol_cases) + '\nSEARCH_GATE_CASES = ' + repr(gate_cases) + '\n\nIDLE_GATE_CASES = [')
    builder = replace(builder, "'tests/InspectionIdleGateChecks.java', 'check_idle_contract.py', 'qa_contract.py', 'build_candidate.py'}",
                      "'tests/InspectionIdleGateChecks.java', 'check_idle_contract.py', 'qa_contract.py', 'build_candidate.py', 'check_search_contract.py', 'tests/SearchTransactionChecks.java'}")
    builder = replace(builder, "        command('javac', [tool['javac']", '''        search_scope={'__name__':'owned_search_protocol_controls'}
        exec(compile((HERE/'check_search_contract.py').read_bytes(),str(HERE/'check_search_contract.py'),'exec'),search_scope)
        search_report=search_scope['run']((HERE/'qa_contract.py').read_text(encoding='utf-8'))
        validate_idle_controls(search_report,SEARCH_PROTOCOL_CASES,source['qa_contract.py']['sha256'])
        result['search_protocol_controls']={'report':search_report,'control_source_sha256':source['check_search_contract.py']['sha256']}
        (OUTPUT/'search-control-classes').mkdir(mode=0o700)
        search_gate=source_java.with_name('PlayerButtonTransaction.java')
        search_checks=HERE/'tests/SearchTransactionChecks.java'
        command('search-gate-javac',[tool['javac'],'-J-XX:ActiveProcessorCount=1','-J-XX:+UseSerialGC','-J-Xmx256m',
            '-proc:none','-Xmaxerrs','20','-Xmaxwarns','20','--release','8','-d',str(OUTPUT/'search-control-classes'),str(search_gate),str(search_checks)])
        search_classes=sorted((OUTPUT/'search-control-classes').rglob('*.class'))
        require(1<=len(search_classes)<=16 and all(x.is_file() and x.stat().st_size<=262144 for x in search_classes),'SEARCH_CONTROL_CLASS_OUTPUT_BOUND')
        search_output=command('search-gate-java',java+['-cp',str(OUTPUT/'search-control-classes'),PACKAGE+'.SearchTransactionChecks'],timeout=15)
        require(0<len(search_output)<=16384,'SEARCH_CONTROL_STDOUT_BOUND')
        search_gate_report=validate_idle_controls(json.loads(search_output),SEARCH_GATE_CASES)
        result['search_transaction_controls']={'report':search_gate_report,'stdout_sha256':digest(search_output),
            'gate_source_sha256':source['src/''' + new_path + '''/PlayerButtonTransaction.java']['sha256'],
            'control_source_sha256':source['tests/SearchTransactionChecks.java']['sha256']}
        command('javac', [tool['javac']''')
    texts['build_candidate.py'] = builder
    for name, text in texts.items():
        if name.endswith('.py'):
            compile(text, name, 'exec')
    manifest = {key: value for key, value in parent_manifest.items() if key != 'files'}
    manifest.update(helper_package=new, files={name: {'bytes':len(text.encode()),'sha256':sha(text.encode())}
        for name,text in sorted(texts.items())}, parent_source_manifest_sha256=sha(raw),
        derived_operation_contract='fixed-beike-search-three-capture-v1', allowed_operations=spec['allowed_operations'],
        live_identity_requalification_required=True, original_failed_cases_reclassified=False,
        new_helper_package_absence_proven=False)
    need(len(texts) == 15, 'EXACT_NEW_FIFTEEN_SOURCE_CLOSURE')
    need(not OUTPUT.exists(), 'NEW_UNPUBLISHED_CANDIDATE_DIRECTORY')
    OUTPUT.mkdir(parents=True)
    for name, text in texts.items():
        p=OUTPUT/name;p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('x') as out:out.write(text)
    manifest_raw=canonical(manifest)+b'\n'
    with (OUTPUT/'SOURCE_PINS.json').open('xb') as out:out.write(manifest_raw)
    changes=[];diff=[]
    for name,text in sorted(texts.items()):
        old_name=name.replace(new_path,old_path)
        original=parent.get(old_name,'')
        if original!=text:
            changes.append({'old_path':old_name if old_name in parent else None,'new_path':name,
                            'old_bytes':len(original.encode()),'new_bytes':len(text.encode()),
                            'new_sha256':sha(text.encode())})
            diff.extend(difflib.unified_diff(original.splitlines(True),text.splitlines(True),fromfile='actual-parent/'+old_name,tofile='candidate-r1/helper/'+name))
    with (HERE/'candidate-r1/SOURCE_DIFF.patch').open('x') as out:out.writelines(diff)
    plan={'schema':'pocket4-new-fixed-search-helper-source-review-plan-v1','helper_package':new,
          'helper_source_manifest_bytes':len(manifest_raw),'helper_source_manifest_sha256':sha(manifest_raw),
          'source_stage_output':'/home/alex/work/pocket4-successor-qa-build-source-'+spec['generation_nonce'],
          'build_output':'/home/alex/work/pocket4-successor-qa-build-'+spec['generation_nonce'],
          'build_argv_after_reviewed_stage':['/usr/bin/python3','-I','/home/alex/work/pocket4-successor-qa-build-source-'+spec['generation_nonce']+'/build_candidate.py','--build-once','--source-manifest-sha256',sha(manifest_raw)],
          'build_uid':1000,'new_private_owned_signer_required':True,'allowed_operations':spec['allowed_operations'],
          'new_selector':{'resource_id':'com.lianjia.beike:id/tv_nav_right_search_text','class':'android.widget.TextView','text':'\u641c\u7d22'},
          'fresh_complete_tree_captures':3,'max_selection_to_dispatch_ms':1000,'max_operation_ms':8000,'watchdog_ms':12000,
          'whole_tree_nodes_masked':False,'legacy_click_function_changed':False,'old_helper_changed':False,
          'source_stage_or_build_submitted':False,'live_runtime_qualification':False,'new_UID':'UNKNOWN_NOT_INSTALLED',
          'full_installed_scope_transition':'Requires current observed roster plus actual new helper identity after authorized install.',
          'old_failed_case':'search-click-after-partial-commit-01','original_failed_case_reclassified':False,
          'next_UI_prerequisites':['separate no-action append-only reconciliation under original r1 identities',
            'actual normal new build and whole APK signature proof','fresh exact runtime/app/task and new helper absence/UID/APK proof',
            'versioned whole installed-scope update','explicit new single search_click case with original independent after-state and post-inspection'],
          'changed_files':changes,'production_ready':False}
    with (HERE/'candidate-r1/REVIEW_PLAN.json').open('xb') as out:out.write(canonical(plan)+b'\n')
    print(json.dumps({'prepared':True,'files':len(texts),'package':new,'manifest_bytes':len(manifest_raw),
                     'manifest_sha256':sha(manifest_raw),'remote_execution_attempted':False},sort_keys=True))


if __name__ == '__main__':
    main()
