#!/usr/bin/env python3
"""Create R7 source from immutable R6 and explicit new protocol blocks only."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'owned-bili-qa-r6-reveal-01/source'
OUT=HERE/'source'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def pretty(value):return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
def put(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    raw=value.encode() if isinstance(value,str) else value
    with path.open('xb') as f:f.write(raw)
def change(source,before,after,count=1):
    assert source.count(before)==count,(before,source.count(before),count)
    return source.replace(before,after)
def assignment(source,name,value):
    nodes=[n for n in ast.parse(source).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)]
    assert len(nodes)==1;n=nodes[0];lines=source.splitlines(True)
    lines[n.lineno-1:n.end_lineno]=[name+'='+repr(value)+'\n'];return ''.join(lines)

manifest_raw=(OLD/'SOURCE_PINS.json').read_bytes();manifest=json.loads(manifest_raw)
assert len(manifest_raw)==1478 and sha(manifest_raw)=='6c75b4a976990d4815de58f504912d3f9a7181c0d5a9094c6319180a1279c419'
for name,row in manifest['files'].items():
    raw=(OLD/name).read_bytes();assert len(raw)==row['bytes'] and sha(raw)==row['sha256'],name
assert manifest['files']['qa_contract.py']['sha256']=='871c784812063739a6ab976784fb38243af52266b0d9a95aa1244779ccd2c005'
assert manifest['files']['qa_adapter.py']['sha256']=='1e939fb27aa4eaa9bb2fd79d7022ff4f48011fdf8824b0e7645bbc6f3308e1c8'
assert manifest['files']['src/org/droidloom/qa/bili/r6/ActionRunner.java']['sha256']=='c93b943bee94533fdeb31954879434f565227ed15e1315c5e697bfae8357c6f5'
assert not OUT.exists(),'CREATE_ONLY_R7_SOURCE_REQUIRED'
mapping=[('org.droidloom.qa.bili.r6','org.droidloom.qa.bili.r7'),
    ('org/droidloom/qa/bili/r6','org/droidloom/qa/bili/r7'),
    ('pocket4-owned-bili-qa-v6','pocket4-owned-bili-qa-v7'),
    ('owned-bili-qa-r6','owned-bili-qa-r7'),('QA R6','QA R7')]
def bind(text):
    for a,b in mapping:text=text.replace(a,b)
    return text
originals={bind(n):(OLD/n).read_text() for n in manifest['files']}
sources={n:bind(t) for n,t in originals.items()}

java='src/org/droidloom/qa/bili/r7/ActionRunner.java'
value=sources[java]
value=change(value,'            else if (op.equals("reveal_controls")) keys(request, "protocol", "nonce", "op", "scope", "inspection_nonce", "inspection_sha256", "player_scope_sha256", "viewport_bounds");',
    '            else if (op.equals("reveal_controls")) keys(request, "protocol", "nonce", "op", "scope", "inspection_nonce", "inspection_sha256", "player_scope_sha256", "viewport_bounds");\n'+
    '            else if (op.equals("player_button")) keys(request, "protocol", "nonce", "op", "scope", "inspection_nonce", "inspection_sha256", "transition", "player_frame_sha256");')
value=change(value,'                } else if (op.equals("reveal_controls")) revealControls(request, result);',
    '                } else if (op.equals("reveal_controls")) revealControls(request, result);\n'+
    '                else if (op.equals("player_button")) playerButton(request, result);')
value=change(value,'error instanceof Rejected || error instanceof TouchTransaction.Fault',
    'error instanceof Rejected || error instanceof TouchTransaction.Fault || error instanceof PlayerButtonTransaction.Fault')
block=(HERE/'player_java_block.txt').read_text()
value=change(value,'    void act(JSONObject request, JSONObject result) throws Exception {',block+'    void act(JSONObject request, JSONObject result) throws Exception {')
sources[java]=value
transaction='src/org/droidloom/qa/bili/r7/PlayerButtonTransaction.java'
sources[transaction]=(HERE/'PlayerButtonTransaction.java').read_text()

value=sources['qa_contract.py']
value=change(value,"if op in ('inspect', 'click', 'set_text','reveal_controls'):","if op in ('inspect', 'click', 'set_text','reveal_controls','player_button'):")
marker="    require(op in ('state', 'inspect', 'click', 'set_text','reveal_controls') and set(value) == expected, 'EXACT_OPERATION_KEYS_REQUIRED')"
value=change(value,marker,"""    if op == 'player_button':
        expected.update(('inspection_nonce','inspection_sha256','transition','player_frame_sha256'))
        require(nonce(value.get('inspection_nonce'))!=value['nonce'],'DISTINCT_PLAYER_BUTTON_NONCE_REQUIRED')
        digest(value.get('inspection_sha256'));digest(value.get('player_frame_sha256'))
        require(value.get('transition') in ('pause','resume') and value['scope']['activity']==REVEAL_ACTIVITY,
                'FIXED_PLAYER_TRANSITION_AND_CONTEXT_REQUIRED')
    require(op in ('state', 'inspect', 'click', 'set_text','reveal_controls','player_button') and set(value) == expected, 'EXACT_OPERATION_KEYS_REQUIRED')""")
value=change(value,"helper_uid not in (UID, 10125, 10164, 10165, 10166, 10169, 10170, 10175)",
    "helper_uid not in (UID, 10125, 10164, 10165, 10166, 10169, 10170, 10175, 10184)")
value=change(value,"        elif request['op']=='reveal_controls':\n            assess_reveal(value,request,observed_window,observed_trees)",
    "        elif request['op']=='reveal_controls':\n            assess_reveal(value,request,observed_window,observed_trees)\n        elif request['op']=='player_button':\n            assess_player_button(value,request,observed_window,observed_trees)")
value=change(value,"              if operation=='reveal_controls' else ['action_target','action_final_window'])",
    "              if operation=='reveal_controls' else ['player_selection','action_target','action_final_window']\n              if operation=='player_button' else ['action_target','action_final_window'])")
value=change(value,"middle['op'] in ('inspect','click','set_text','reveal_controls')", "middle['op'] in ('inspect','click','set_text','reveal_controls','player_button')")
value+=(HERE/'player_contract_block.py').read_text()
sources['qa_contract.py']=value

value=sources['qa_adapter.py']
value=change(value,"             'src/org/droidloom/qa/bili/r7/TouchTransaction.java'} <= set(manifest['files']),",
    "             'src/org/droidloom/qa/bili/r7/TouchTransaction.java',\n             'src/org/droidloom/qa/bili/r7/PlayerButtonTransaction.java'} <= set(manifest['files']),")
value=change(value,"plan.get('operation') in ('state','inspect','click','set_text','reveal_controls')",
    "plan.get('operation') in ('state','inspect','click','set_text','reveal_controls','player_button')")
value=change(value,"    require(set(plan) == keys and isinstance(plan['nonces'], dict), 'EXACT_PLAN_KEYS_REQUIRED')",
    "    if op == 'player_button':\n        keys.add('transition')\n        require(plan.get('transition') in ('pause','resume'),'FIXED_PLAYER_TRANSITION_REQUIRED')\n"+
    "    require(set(plan) == keys and isinstance(plan['nonces'], dict), 'EXACT_PLAN_KEYS_REQUIRED')")
value=change(value,"op in ('click','set_text','reveal_controls')", "op in ('click','set_text','reveal_controls','player_button')")
value=change(value,"helper_uid not in (10117,10125,10164,10165,10166,10169,10170,10175)",
    "helper_uid not in (10117,10125,10164,10165,10166,10169,10170,10175,10184)")
value=change(value,"request['op'] in ('click','set_text','reveal_controls')", "request['op'] in ('click','set_text','reveal_controls','player_button')")
value=change(value,"plan['operation'] in ('click','set_text','reveal_controls')", "plan['operation'] in ('click','set_text','reveal_controls','player_button')")
marker="                result['post_input_inspection_sha256']=qa.sha(qa.canonical(middle['helper']['post_inspection']))"
value=change(value,marker,marker+"""
            elif plan['operation']=='player_button':
                fields=qa.player_button_request_fields(inspected['helper']['inspection'],scope,plan['transition'])
                action=request('action','player_button',scope=scope,inspection_nonce=names['inspect'],
                    inspection_sha256=inspected['wire_sha256'],**fields)
                middle=None
                middle=self.instrument(action)
                require(middle['helper']['action_window']==inspected['helper']['inspection']['window'],
                        'PLAYER_BUTTON_ACKNOWLEDGED_WINDOW_DIFFERS')
                result['player_button_acknowledged']=True
                result['player_transition_requested']=plan['transition']
                result['player_current_inspection_sha256']=middle['helper']['player_inspection_sha256']
                result['atomic_android_transaction']=False""")
value=change(value,"plan['operation'] in ('inspect','reveal_controls')", "plan['operation'] in ('inspect','reveal_controls','player_button')")
value=change(value,"'operations':['state','inspect','click','set_text','reveal_controls']", "'operations':['state','inspect','click','set_text','reveal_controls','player_button']")
sources['qa_adapter.py']=value

value=sources['build_candidate.py']
value=change(value,"'src/org/droidloom/qa/bili/r7/TouchTransaction.java', 'qa_contract.py'", "'src/org/droidloom/qa/bili/r7/TouchTransaction.java', 'src/org/droidloom/qa/bili/r7/PlayerButtonTransaction.java', 'qa_contract.py'")
value=change(value,"str(source_java),str(source_java.with_name('TouchTransaction.java'))])",
    "str(source_java),str(source_java.with_name('TouchTransaction.java')),str(source_java.with_name('PlayerButtonTransaction.java'))])")
sources['build_candidate.py']=value
sources['make_build_request.py']=change(sources['make_build_request.py'],'pocket4-owned-bili-qa-r7-static-build-01-20261105','pocket4-owned-bili-qa-r7-static-build-01-20261106')
reference=json.loads(sources['build-input-reference.json'])
reference['r7_actual_compilation_performed']=False
reference['source_history']['frozen_r6_source_manifest_sha256']=sha(manifest_raw)
reference['source_history']['R7_not_qualified_by_prior_builds']=True
sources['build-input-reference.json']=pretty(reference).decode()
sources['README.md']='''# Owned Bili R7: fixed current player button

R7 preserves the R6 state, inspect, click, set_text and reveal_controls operations. The only new operation is player_button with the fixed pause or resume intent. It uses no caller coordinates or arbitrary selector. The earlier successful complete inspection proves the exact public course and player frame; its tree and node are explicitly context only for this new operation.

The helper takes a new complete tree inside the action invocation, verifies the original full title/author/rendering/geometry predicate and the unique fixed current player button, and takes two further complete captures. Every field in the captured tree and window must remain equal, all three captures belong to the same UiAutomation connection/window, and the original target refresh, full node hash, eligibility and final window checks remain. A fresh selection age limit of 1000 ms applies before one ACTION_CLICK. Any mismatch fails without another attempt. This is not an Android atomic transaction.

The helper result binds current private inspection bytes, all three complete capture hashes, exact selected node, intended transition, frame context, action acknowledgement and original own-service restoration. Host parsing independently verifies the public role and complete current inspection. It requires an independent no-automation after-state after helper termination. Acknowledgement alone does not establish a pause, resume, audio result or whole-App production readiness; an independent later label observation remains required, and failed/unknown actions never authorize automatic resume or retry.

All R6 request/result, compression, tree/depth/child/window, helper/watchdog, per-command, build resource and timeout limits remain. The previous helper UID 10184 is explicitly excluded for the separately installed R7 package; R7 UID/APK/signer remain unknown until actual build/install. R6 files, installed helper and failed attempts are not modified or replayed.

This is a source and build-only candidate. Root alone may dispatch the exact static build, then bind actual build and installation originals before any separately reviewed fresh UI flow. No commercial package/signature/settings/permission change is included. No whole-App or business success is claimed.
'''
for name,text in sources.items():
    if name.endswith('.py'):compile(text,name,'exec')
    put(OUT/name,text)
new_manifest={'schema':1,'files':{n:{'bytes':len(t.encode()),'sha256':sha(t.encode())} for n,t in sorted(sources.items())}}
put(OUT/'SOURCE_PINS.json',pretty(new_manifest))
put(HERE/'literal-rebindings.json',pretty(mapping))
full='';normalized=''
for name,text in sources.items():
    old=originals.get(name,'')
    delta=''.join(difflib.unified_diff(old.splitlines(True),text.splitlines(True),fromfile='R6/'+name,tofile='R7/'+name))
    put(HERE/('delta-'+name.replace('/','_')+'.patch'),delta)
    full+=delta
    normalized+=''.join(difflib.unified_diff(bind(old).splitlines(True),text.splitlines(True),fromfile='R6-literal-bound/'+name,tofile='R7/'+name))
put(HERE/'r6-to-r7-full.patch',full)
put(HERE/'normalized-semantic-residual.patch',normalized)
old_act=bind(originals[java]).split('    void act(JSONObject request, JSONObject result) throws Exception {',1)[1]
new_act=sources[java].split('    void act(JSONObject request, JSONObject result) throws Exception {',1)[1]
assert old_act==new_act,'ORIGINAL_GENERIC_ACTION_CHANGED'
old_tree=ast.parse(bind(originals['qa_contract.py']));new_tree=ast.parse(sources['qa_contract.py'])
old_functions={n.name:ast.dump(n,include_attributes=False) for n in old_tree.body if isinstance(n,ast.FunctionDef)}
new_functions={n.name:ast.dump(n,include_attributes=False) for n in new_tree.body if isinstance(n,ast.FunctionDef)}
changed={'validate_request','parse_completed','tree_observations','assess_restoration'}
unchanged=[name for name in old_functions if name not in changed]
assert all(old_functions[n]==new_functions[n] for n in unchanged)
put(HERE/'guard-correspondence.json',pretty({'schema':1,'baseline_manifest':{'bytes':len(manifest_raw),'sha256':sha(manifest_raw)},
    'original_generic_Java_act_body_and_file_tail_exact_after_package_protocol_binding':True,
    'original_generic_Java_act_sha256':sha(new_act.encode()),'unchanged_contract_functions_AST':unchanged,
    'changed_contract_functions':sorted(changed),'new_contract_functions':sorted(set(new_functions)-set(old_functions)),
    'whole_tree_comparison_fields_ignored':[],'new_action_selection_authority':'complete capture made within this player_button invocation',
    'earlier_inspection_scope_and_full_public_player_frame_rechecked':True,
    'same_connection_full_tree_rechecks':2,'current_selection_age_ms':1000,'Android_atomicity_claimed':False,
    'old_R6_edited':False,'Hepta_or_Android_calls':0}))
print(json.dumps({'state':'R7_SOURCE_PREPARED_NOT_FROZEN_OR_SUBMITTED','source_files':len(sources),
    'manifest':{'bytes':(OUT/'SOURCE_PINS.json').stat().st_size,'sha256':sha((OUT/'SOURCE_PINS.json').read_bytes())}}))
