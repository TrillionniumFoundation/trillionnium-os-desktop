#!/usr/bin/env python3
"""Derive the unrun normal04 packet from the byte-pinned normal03 control source."""
import ast, copy, difflib, hashlib, json, pathlib
R=pathlib.Path(__file__).resolve().parent
I=R/'inputs'; A=R/'actual'; D=R/'normal04'
D.mkdir(exist_ok=True)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def source(name,digest):
    raw=(I/name).read_bytes()
    if sha(raw)!=digest:
        assert raw.endswith(b'\n') and sha(raw[:-1])==digest, name
        raw=raw[:-1]
        (I/name).write_bytes(raw)
    assert sha(raw)==digest
    return raw.decode()
def change(text,old,new):
    assert text.count(old)==1,(old,text.count(old))
    return text.replace(old,new)
def replace_function(text,name,body):
    tree=ast.parse(text); node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    lines=text.splitlines(keepends=True)
    return ''.join(lines[:node.lineno-1])+body.rstrip()+'\n'+''.join(lines[node.end_lineno:])
def pin(text):
    b=text.encode();return {'bytes':len(b),'sha256':sha(b)}
def save(name,text):
    (D/name).write_text(text)
    return pin(text)
original=source('framework_build_normal03.py','03f0b4aecba20149ad7f1301ea823eb5e7e5ba1efa00d08c92c4fa7ecf482132')
framework=original
replacements={
 "ROOT = OWNER / 'typed-ingress-framework-provider-build-03-20261106'":"ROOT = OWNER / 'typed-ingress-framework-native-provider-build-04-20261106'",
 "BUILD_PARENT = P('/home/alex/work/pocket4-native-typed-ingress-builder468-provider-closure-compile-03-20261106')":"BUILD_PARENT = P('/home/alex/work/pocket4-native-typed-ingress-builder469-native-provider-compile-01-20261106')",
 "BUILDER = BUILD_PARENT / 'attempt01/cargo-target/debug/droidloom-update'":"BUILDER = BUILD_PARENT / 'compile02/cargo-target/debug/droidloom-update'",
 'BUILDER_SHA = "8bf78794705a62f0a60d00af64cdd25e2b798739e445575c3d3cca5e566f4cf6"':'BUILDER_SHA = "6bb421afded7d77fa61d27548d12011b83e831a55e56c5bdc114f87fb2ba9bf3"',
 'BUILDER_BYTES = 34722200':'BUILDER_BYTES = 34766128',
 "BUILD_RESULT = BUILD_PARENT / 'attempt01/result.json'":"BUILD_RESULT = BUILD_PARENT / 'compile02/result.json'\nBUILDER_MANIFEST = BUILD_PARENT / 'candidate-source-manifest.json'\nQUALIFICATION_RESULT = BUILD_PARENT / 'qualify02/result.json'\nQUALIFICATION_SHA = 'f31bb31d29967bacdb0842eea99dae65f8b67425f26f10063c3d84099367fd64'",
 'BUILD_RESULT_SHA = "871e78f7ad8f3f3a12c165297e4fe566d96cfe3a2ce64a0d0010cffdb647b6b8"':'BUILD_RESULT_SHA = "a14dde5d3a2e85fe44d90c651527c8c8402d341403ef84a7bc92b93252de72b9"',
 'BUILD_RESULT_BYTES = 161423':'BUILD_RESULT_BYTES = 37384',
 'SOURCE_MANIFEST_SHA = "e06522400f746b62016f82dfd3ec913b39cd9a8f33f9bca4f61a19a2787684ee"':'SOURCE_MANIFEST_SHA = "d9340351c9653b10dfd0882afbff5ff4fc11dafaa6083191ed2a8fdb5c8dd934"',
 "EXTENDED_LOCK_SHA = '5c28f77e998cb75fd04de121e43a36fc3d8515c18249930268a2ffb6e5e372f7'":"EXTENDED_LOCK_SHA = '72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d'\nPREVIOUS_PROVIDER_LOCK_SHA = '5c28f77e998cb75fd04de121e43a36fc3d8515c18249930268a2ffb6e5e372f7'",
 "PREVIOUS_ROOT = OWNER / 'typed-ingress-framework-resume-build-01-20261106'":"PREVIOUS_ROOT = OWNER / 'typed-ingress-framework-provider-build-03-20261106'",
 "PUBLISHED_MANIFEST_SHA = '73a4cc1da8371482164aab2bc149498d03f481f212bb85cb4fda22b6b10c958d'":"PUBLISHED_MANIFEST_SHA = 'afb23d210fda970a09482a14b9b38af1c92b5be505edd0eda2b76ce5ffc6067f'",
 'PUBLISHED_MANIFEST_BYTES = 97784':'PUBLISHED_MANIFEST_BYTES = 108555',
 "PRIOR_INNER_SHA = '80f3508bab1884421af6db2f6d87537fd950100be009265b7e2efabc9b97fcdc'":"PRIOR_INNER_SHA = '6a525b9838f43579bc41b1106891f2f734a0c2d92b0c5cc355f7ab02b39eb2a8'",
 "PRIOR_OUTER_SHA = '2c36ab1cc9ff6f181855f195f9c5b7bc0f58e7fb99d9c76e4871e64b143bf059'":"PRIOR_OUTER_SHA = '273ba8a236253ee3873074a26f568144397044ebcfdd6f153ab8712b29ff70cf'",
}
for old,new in replacements.items():framework=change(framework,old,new)
current=json.loads((A/'compile02-result.json').read_text())
tree=ast.parse(framework); lines=framework.splitlines(keepends=True)
for node in reversed(tree.body):
    if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in {'EXPECTED_TESTS','EXPECTED_SOURCE_DELTA','EXPECTED_COMPILE_LABELS'} for t in node.targets):
        name=node.targets[0].id
        value={'EXPECTED_TESTS':current['test_names'],'EXPECTED_SOURCE_DELTA':json.loads((A/'qualify02-result.json').read_text())['source_delta'],'EXPECTED_COMPILE_LABELS':[c['label'] for c in current['commands']]}[name]
        lines[node.lineno-1:node.end_lineno]=[name+' = '+repr(value)+'\n']
framework=''.join(lines)
framework=replace_function(framework,'builder_contract',(R/'normal04_builder_contract.py.part').read_text())
framework=replace_function(framework,'prior_failure_contract',(R/'normal04_prior_failure_contract.py.part').read_text())
for old,new in {
 "'previous_locked_projects': 214, 'new_locked_projects': 224":"'previous_locked_projects': 224, 'new_locked_projects': 225",
 "'actual 491-file builder source changed'":"'actual 493-file builder source changed'",
 "len(document['plan']['projects']) == 224":"len(document['plan']['projects']) == 225",
 "lock, _ = json_pin(BUILD_SOURCE / 'android/manifest/m2-role-ingress-provider-source-lock.json',\n                       EXTENDED_LOCK_SHA, 96322)":"lock, _ = json_pin(BUILD_SOURCE / 'android/manifest/m2-role-ingress-provider2-source-lock.json',\n                       EXTENDED_LOCK_SHA, 96957)",
 "inputs['provider_source_lock_extension_exact'] is True and":"inputs['provider_source_lock_extension_exact'] is True and\n            inputs['previous_provider_source_lock_sha256'] == PREVIOUS_PROVIDER_LOCK_SHA and\n            inputs['native_provider_extension_exact'] is True and",
 "'published_projects': 224, 'published_root_links': 8":"'published_projects': 225, 'published_root_links': 8",
 "(BUILD_PARENT / 'attempt01/copied-builder-source-manifest.json', context['builder_map_pin'])":"(BUILDER_MANIFEST, context['builder_map_pin']),\n                         (QUALIFICATION_RESULT, context['qualification_pin'])",
 "context['published_manifest'], context['prior_failure_authority_pins'] = prior_failure_contract()":"context['qualification_pin'] = json_pin(QUALIFICATION_RESULT, QUALIFICATION_SHA, 65386)[1]\n    context['published_manifest'], context['prior_failure_authority_pins'] = prior_failure_contract()",
 "'builder_source_files': 491, 'actual_host_compile_commands': 62, 'actual_exact_controls': 24":"'builder_source_files': 493, 'actual_host_compile_commands': 20, 'actual_current_exact_controls': 16,\n        'qualification_commands': 17, 'unchanged_source_resume_controls_inherited': 9,\n        'source_resume_controls_rerun_in_successor': False, 'qualification_result_sha256': QUALIFICATION_SHA",
 "'fresh verification of the published 214-project exact old lock, then normal monotonic reconciliation to 224 locked projects and 8 root links'":"'fresh verification of the published 224-project provider1 lock, then normal monotonic reconciliation to 225 locked projects and 8 root links'",
 "'prior_reaped_children': 1":"'prior_reaped_children': 27",
 "'prior_normal_peak_bytes': 7947964416, 'prior_normal_swap_peak_bytes': 50835456":"'prior_normal_peak_bytes': 8141615104, 'prior_normal_swap_peak_bytes': 0",
 "'actual_static_compile_memory_max_events': 1732":"'actual_static_compile_memory_max_events': 314",
}.items():framework=change(framework,old,new)
save('framework_build.py',framework); ast.parse(framework)
fence=source('fenced_build_normal03.py','ce3c0d1fc221e36055d75837a9bba337ccea33c8c7f89f8101a36defbd09c684')
fence=change(fence,"CONTROLLER_SHA = '03f0b4aecba20149ad7f1301ea823eb5e7e5ba1efa00d08c92c4fa7ecf482132'","CONTROLLER_SHA = "+repr(pin(framework)['sha256']))
fence=change(fence,'typed-ingress-framework-provider-build-03-20261106','typed-ingress-framework-native-provider-build-04-20261106')
save('fenced_build.py',fence)
pure=source('normal03-pure_controls.py','5096a8a42c6f7cd1e1b6703ca25c1551a74ee58d55a8db8e68b195994d5a550e')
pure=change(pure,"len(lock['projects']) == 224","len(lock['projects']) == 225")
pure=change(pure,"complete_expected_224_project_plan","complete_expected_225_project_plan")
pure=change(pure,"actual_old_214_manifest_is_not_current_completion","actual_provider1_224_manifest_is_not_current_completion")
save('pure_controls.py',pure)
files={
 'framework_build.py':framework, 'fenced_build.py':fence,'pure_controls.py':pure,
 'parent-normal03-framework_build.py':original,
 'main_snapshot.py':source('normal03-main_snapshot.py','1fd614b6e7b4900feff1a114c0cd221a1fb00fc0cea9878db1f3ae5672d561cf'),
 'capture_lifecycle.py':source('normal03-capture_lifecycle.py','4ffc5a7d6a54ad2cd4351ef30f90a12143614206953e97219f3d6cf5c6e1fc28'),
 'root_snapshot_supervisor.py':source('normal03-root_snapshot_supervisor.py','f493a324cb5694f618d0fed3d5ed17ff90aa64924b671ea99550622f6090b5b7'),
 'frozen-work-inventory.py':source('normal03-frozen-work-inventory.py','203dd7f4efdac01891a4c31fd79f2eb3204e3c8c2be5702988f0875307cce9ab'),
 'actual-work-preparation.json':source('actual-work-preparation.json','ab286f3939acfeb648a716ca15e5df348fef6b7007eb5651735fe8a7bda96b1c'),
 'actual-native-prebuilt-Android.bp':source('actual-native-prebuilt-Android.bp','d1eca99403572ee9d481e777febac8d4e062f44fd8844285ffc452b17beb531a'),
 'actual-builder469-result.json':(A/'compile02-result.json').read_text(),
 'actual-builder469-qualification.json':(A/'qualify02-result.json').read_text(),
 'expected-builder469-manifest.json':(A/'candidate-source-manifest.json').read_text(),
 'prior-framework-inner-terminal.json':(I/'normal03-terminal.json').read_text(),
 'prior-framework-outer-terminal.json':(I/'normal03-outer-terminal.json').read_text(),
 'actual-published-source-manifest.json':(A/'current-published-source-manifest.json').read_text(),
 'actual-provider-source-lock.json':(R/'candidate/android/manifest/m2-role-ingress-provider2-source-lock.json').read_text(),
}
expected={n:save(n,t) for n,t in files.items()}
stage=source('normal03-stage.py','d4d80d5e44ca6990f351a71b6ae6b59a66359b21db356472aabdc55f4e0a2443')
stage=change(stage,'typed-ingress-framework-provider-build-03-20261106','typed-ingress-framework-native-provider-build-04-20261106')
lines=stage.splitlines(keepends=True)
node=next(n for n in ast.parse(stage).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='EXPECTED' for t in n.targets))
lines[node.lineno-1:node.end_lineno]=['EXPECTED = '+repr(expected)+'\n']; stage=''.join(lines)
save('stage.py',stage)
wire=(json.dumps({'schema':1,'stage':stage,'files':files},ensure_ascii=False,separators=(',',':'))+'\n')
save('exact-stdin.json',wire)
transport=source('normal03-transport-boundary.py', '882ed7f1748372919b5167ba5bc7f9a5393c4d2e8af168ba6748239251e3003a')
node_names={'WIRE_BYTES':len(wire.encode()),'WIRE_SHA256':sha(wire.encode()),'STAGE_BYTES':len(stage.encode()),'STAGE_SHA256':sha(stage.encode())}
lines=transport.splitlines(keepends=True)
for node in reversed(ast.parse(transport).body):
 if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id in node_names:
  name=node.targets[0].id;lines[node.lineno-1:node.end_lineno]=[name+' = '+repr(node_names[name])+'\n']
transport=''.join(lines);save('transport-boundary.py',transport)
request={'host':'pocket4','executable':'/usr/bin/python3','args':['-B','-I','-c',transport,'--execute-once'],'stdin':wire,
 'idempotency_key':'pocket4-native-typed-ingress-framework-strict-native-provider-two-target-build-04-20261106',
 'timeout_seconds':6400,'cpu_quota_percent':200,'memory_max_bytes':10737418240,'nice':10}
save('exact-request.json',json.dumps(request,ensure_ascii=False,indent=2)+'\n')
scope={'__name__':'local_normal04_pure_controls'}
exec(compile(pure,'pure_controls.py','exec'),scope,scope)
controls=scope['run'](files)
assert controls['state']=='PASS' and controls['passed']==45
save('local-pure-controls-result.json',json.dumps(controls,indent=2)+'\n')
allpins={n:pin((D/n).read_text()) for n in [*files,'stage.py','transport-boundary.py','exact-stdin.json','exact-request.json','local-pure-controls-result.json']}
save('SOURCE_PINS.json',json.dumps({'schema':1,'state':'NORMAL04_SOURCE_ONLY_UNRUN','files':allpins,'Main_actions':0,'Android_actions':0,'Soong_invoked':False,'production_ready':False},indent=2)+'\n')
save('framework_build.from-normal03.patch',''.join(difflib.unified_diff(original.splitlines(keepends=True),framework.splitlines(keepends=True),fromfile='normal03/framework_build.py',tofile='normal04/framework_build.py')))
oldf=(I/'fenced_build_normal03.py').read_text()
save('fenced_build.from-normal03.patch',''.join(difflib.unified_diff(oldf.splitlines(keepends=True),fence.splitlines(keepends=True),fromfile='normal03/fenced_build.py',tofile='normal04/fenced_build.py')))
assert len(wire.encode())<=1048576,'runtime stdin maximum exceeded'
plan_scope={'__name__':'normal04_plan_only'}
exec(compile(framework,'framework_build.py','exec'),plan_scope,plan_scope)
plan=plan_scope['plan']()
plan.update({'state':'NORMAL04_EXACT_PACKET_PREPARED_NOT_SUBMITTED','source_packet':allpins['exact-stdin.json'],'request':allpins['exact-request.json'],
 'local_pure_controls_passed':45,'runtime_capture_lifecycle_controls_to_rerun':4,'actual_builder_contract_on_host_recheck_pending':True,
 'parent_review_before_dispatch_required':True,'Soong_invoked':False,'remote_submitted':False,
 'cleanup_eligible':False,'production_ready':False,'request_idempotency_key':request['idempotency_key'],
 'original_normal03_source_tree':'d46d2b8cc5294fbf94f51774b3a3b0bae1ce1e51',
 'new_root_is_distinct':True,'current_fixed_Main_seven_roles_unchanged':True,
 'locked_neuralnetworks_commit':'a44a9032ab9a8438c0e13aca765d6ee4edebba2c',
 'locked_car_commit_unchanged':'9f04df65daa8b9a65ee05fd4039fe95446874d76',
 'provider_source_fetch_and_sparse_reconciliation':'only the existing normal Rust source mechanism under both original work/source locks; actual project reuse not prequalified',
 'real_Android_variant_visibility_generation_and_link_validation':'pending actual strict Soong run',
 'if_memory_or_identity_gate_fails':'save actual failure and bound resource/fence evidence; do not launch builder, retry automatically, change Main limits or kill unrelated processes'})
save('execution-plan.json',json.dumps(plan,indent=2)+'\n')
print(json.dumps({'state':plan['state'],'files':len(files),'wire':allpins['exact-stdin.json'],'request':allpins['exact-request.json'],'pure_controls':controls['passed'],'framework':allpins['framework_build.py'],'fence':allpins['fenced_build.py']},indent=2))

