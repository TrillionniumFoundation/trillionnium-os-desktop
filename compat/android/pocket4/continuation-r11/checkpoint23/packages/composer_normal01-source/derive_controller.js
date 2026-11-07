function deriveComposerController(i,H,qualify474){
 "use strict";
 const need=(v,m)=>{if(!v)throw Error(m);}, pin=s=>({bytes:H.utf8(s).length,sha256:H.sha256(H.utf8(s))});
 const wanted={framework:{bytes:69073,sha256:"05b6a43c65f2bd2e51ece69d76464c970890a07e5fed61253d3feac2844eb2bb"},completion:{bytes:8992,sha256:"05afc29ca24636c8a2c253641d9b812bc94ecd06b177ccca756c41ebe2a1c993"},controls:{bytes:10982,sha256:"19d30bb230d148967d106cd43196baf402465a3c34b906ab25f08827951b7b3f"},controlFragment:{bytes:4401,sha256:"80478de0f048b519caa6825f2d6638328e4d7971e9f0cb65da4e634bcee2821f"}};
 for(const[k,v]of Object.entries(wanted))need(JSON.stringify(pin(i[k]))===JSON.stringify(v),"FIXED_INPUT:"+k);
 const qualified=qualify474(i.actual,i.compiler,i.map,i.scope,i.proof,H),r=JSON.parse(i.actual),scope=JSON.parse(i.scope),sourceMap=JSON.parse(i.map);
 const root="/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/composer-retirement-normal-build-01-20261106";
 const parent="/home/alex/work/pocket4-native-builder474-composer-audiocontrol-projection-compile-01-20261106";
 let framework=i.framework,controls=i.controls;const edits=[],controlEdits=[];
 function edit(before,after){const at=framework.indexOf(before);need(at>=0&&framework.indexOf(before,at+before.length)<0,"FRAMEWORK_PREIMAGE:"+before.slice(0,60));edits.push({at,before,after});framework=framework.slice(0,at)+after+framework.slice(at+before.length);}
 function ctrl(before,after){const at=controls.indexOf(before);need(at>=0&&controls.indexOf(before,at+before.length)<0,"CONTROL_PREIMAGE:"+before.slice(0,60));controlEdits.push({at,before,after});controls=controls.slice(0,at)+after+controls.slice(at+before.length);}
 function constant(name,value){const m=framework.match(new RegExp("^"+name+" = .*$","m"));need(m,"CONSTANT:"+name);edit(m[0],name+" = "+value);}
 function funcs(s){const ms=[...s.matchAll(/^def (\w+)\([^\n]*:\n/gm)];need(ms.length===[...s.matchAll(/^def /gm)].length,"SINGLE_LINE_FUNCTION_HEADERS");return Object.fromEntries(ms.map(m=>{const body=m.index+m[0].length,e=s.slice(body).search(/^\S/gm);return[m[1],s.slice(m.index,e<0?s.length:body+e).trimEnd()];}));}
 const f=funcs(framework);
 constant("ROOT","OWNER / 'composer-retirement-normal-build-01-20261106'");
 constant("BUILD_PARENT","P("+JSON.stringify(parent)+")");
 constant("BUILDER_SHA",JSON.stringify(r.builder_elf.sha256));constant("BUILDER_BYTES",String(r.builder_elf.bytes));
 constant("BUILD_RESULT_SHA",JSON.stringify(pin(i.actual).sha256));constant("BUILD_RESULT_BYTES",String(pin(i.actual).bytes));
 constant("SOURCE_MANIFEST_SHA",JSON.stringify(pin(i.map).sha256));
 constant("TARGETS",JSON.stringify(scope.targets));constant("EXPECTED_TESTS",JSON.stringify(r.expected_test_names));
 constant("EXPECTED_TEST_INDICES",JSON.stringify([...Array.from({length:18},(_,n)=>n),...Array.from({length:8},(_,n)=>200+n)]));
 constant("EXPECTED_COMPILE_LABELS",JSON.stringify(r.commands.map(c=>c.label)));
 constant("EXPECTED_SOURCE_DELTA","json.loads("+JSON.stringify(JSON.stringify(r.source_delta))+")");
 const fixedInputs=Object.fromEntries(scope.complete_ACK_production_inputs.map(q=>[q.path,{bytes:q.bytes,sha256:q.sha256}]));
 const declarations=Object.fromEntries(scope.checkout_declarations.map(q=>[q.path,{bytes:q.bytes,sha256:q.sha256}]));
 const blueprints=Object.fromEntries([scope.fixed_SystemUI_child_projection,scope.fixed_Audiocontrol_example_projection].map((q,n)=>[q.path,{bytes:q.original.bytes,sha256:q.original.sha256,projected_sha256:n===0?"42118873220b0cc4d07e21a961052ddd5d81ab67be8df5d7c9dba9bd966aaeb5":"d73b00f17a80375d2d59e408088c5e875c3311bd0f7487b117d4b8d28f7cff93"}]));
 edit("def identity(info):","COMPOSER_INPUTS = json.loads("+JSON.stringify(JSON.stringify(fixedInputs))+")\nCOMPOSER_DECLARATIONS = json.loads("+JSON.stringify(JSON.stringify(declarations))+")\nCOMPOSER_PROJECTED_BLUEPRINTS = json.loads("+JSON.stringify(JSON.stringify(blueprints))+")\n\n\ndef identity(info):");
 let contract=f.builder_contract;
 function sub(before,after){need(contract.includes(before)&&contract.indexOf(before)===contract.lastIndexOf(before),"CONTRACT_PREIMAGE:"+before.slice(0,70));contract=contract.replace(before,after);}
 contract=contract.replaceAll("builder473","builder474").replaceAll("BUILDER473","BUILDER474");
 sub("result['focused_tests_passed'] == 33 and result['updater_focused_tests_passed'] == 24","result['focused_tests_passed'] == 35 and result['updater_focused_tests_passed'] == 26");
 sub("result['actual_registered_test_count'] == 214","result['actual_registered_test_count'] == 216");
 sub("result['systemui_test_projection_tests_passed'] == 3 and\n            result['audiocontrol_example_projection_tests_passed'] == 3","result['composer_entry_tests_passed'] == 5 and\n            result['composer_audiocontrol_projection_tests_passed'] == 3");
 sub("exact 33-control qualification","exact 35-control qualification");
 sub("(EXPECTED_TEST_INDICES, EXPECTED_TESTS, 214,","(EXPECTED_TEST_INDICES, EXPECTED_TESTS, 216,");
 contract=contract.replaceAll("99775","99750").replaceAll("473-fixed-audiocontrol-example-projection","474-composer-audiocontrol-example-projection");
 const start=contract.indexOf("    require(result['actual_parent471_compile_authority']"),end=contract.indexOf("    require(result['actual_toolchain']",start);
 need(start>=0&&end>start,"ACTUAL_PARENT_AUTHORITY_BLOCK");
 const block="    require(result['actual_parent472_compile_authority']['bytes'] == 185025 and\n"+
 "            result['actual_parent472_compile_authority']['sha256'] == '4c2f97bee3d6dbcc742f736c46fa18e9dc869830fe82211fb83c0afed6dfdbf4' and\n"+
 "            result['parent472_build_scope_authority']['bytes'] == 6535 and\n"+
 "            result['parent472_build_scope_authority']['sha256'] == 'f43cd778b75e484d53899eab543680e6b32ae5e54d6eca373b34223dcfcc8af9' and\n"+
 "            result['composer_entry_proof_authority']['bytes'] == 11586 and\n"+
 "            result['composer_entry_proof_authority']['sha256'] == '3bc022c9924dc13f7e2ad8d6ed85a079af1dec61733433b88c2c76d0df0c60da' and\n"+
 "            result['composer_build_scope_authority']['bytes'] == 7076 and\n"+
 "            result['composer_build_scope_authority']['sha256'] == '65f48507f685808728c1cd5a7f4a44e09e9b57f0588befbb97ba77a94a25da3d' and\n"+
 "            result['composer_audiocontrol_projection_authority']['bytes'] == 12564 and\n"+
 "            result['composer_audiocontrol_projection_authority']['sha256'] == '2a3d0c6c6727e83aa8c325c63488e932774d8c9fa41e32065b5a5952b8f5a1ab' and\n"+
 "            result['audiocontrol_example_original_fixture_authority']['bytes'] == 1869 and\n"+
 "            result['audiocontrol_example_original_fixture_authority']['sha256'] == '9c8a0aecfa46ce0f1874362fa9dfff6a34326f9bf569b6fe7206dd6db1b3c9a6' and\n"+
 "            result['actual_prior_wayland03_check_authority']['bytes'] == 81805 and\n"+
 "            result['actual_prior_wayland03_check_authority']['sha256'] == '57546b6c6c2d4e05aea6099097944cdbe6746bbcc0124768a314414ec5663abd' and\n"+
 "            result['unchanged_225_project_lock_authority']['bytes'] == 96957 and\n"+
 "            result['unchanged_225_project_lock_authority']['sha256'] == EXTENDED_LOCK_SHA and\n"+
 "            result['source_lock_writer'] == 'UNKNOWN',\n"+
 "            'builder474 actual parent, Composer sources, projection and unchanged current lock are incomplete')\n";
 contract=contract.slice(0,start)+block+contract.slice(end);
 sub("result['runtime_authorization_enabled'] is False and","result['runtime_authorization_enabled'] is False and\n            result['Composer_Android_Binder_ABI_compiled'] is False and\n            result['Composer_service_or_AIDL_tests_executed'] is False and\n            result['Main_identity_observed'] is False and result['Main_actions'] == 0 and");
 sub("            source_map['android/native-role-ingress/provider-fixtures/SystemUI-tests.Android.bp'] == {\n                'bytes': 3392, 'kind': 'file', 'mode': 420,\n                'sha256': 'f1b2422c693a8f8c52034369ded585a3a93ac861f9dd6dd73f0801a77e6be4da'} and\n","");
 sub("    return result, pin, source_map, source_pin, builder",
 "    for fixed in [COMPOSER_INPUTS, COMPOSER_DECLARATIONS]:\n"+
 "        for relative, wanted in fixed.items():\n"+
 "            require(source_map[relative]['kind'] == 'file' and\n"+
 "                    source_map[relative]['bytes'] == wanted['bytes'] and\n"+
 "                    source_map[relative]['sha256'] == wanted['sha256'],\n"+
 "                    'actual Composer production source or declaration differs: ' + relative)\n"+
 "    return result, pin, source_map, source_pin, builder");
 edit(f.builder_contract,contract);
 let plan=f.plan;
 function pl(before,after){need(plan.includes(before),"PLAN_PREIMAGE:"+before);plan=plan.replace(before,after);}
 pl("PLAN_NORMAL_STRICT_FRAMEWORK_PROVIDER_BUILD","PLAN_NORMAL_STRICT_COMPOSER_SERVICE_AND_AIDL_TEST_BUILD");
 pl("'actual_host_compile_commands': 71, 'actual_exact_controls': 33","'actual_host_compile_commands': 74, 'actual_exact_controls': 35");
 pl("'native-role-ingress-build'","'composer-retirement-build'");
 pl("'prior_inner_failure_sha256': PRIOR_INNER_SHA","'workspace_prior_typed_inner_failure_sha256': PRIOR_INNER_SHA");
 pl("'prior_outer_failure_sha256': PRIOR_OUTER_SHA","'workspace_prior_typed_outer_failure_sha256': PRIOR_OUTER_SHA");
 pl("'prior_builder468_static_compile_peak_bytes': 1073741824, 'prior_builder468_static_compile_memory_max_events': 1732","'actual_builder474_static_compile_peak_bytes': 1073741824, 'actual_builder474_static_compile_memory_max_events': 205");
 pl("'normal_build_success_not_complete_Java_JNI_qualification': True",
 "'normal_build_success_not_ELF_AIDL_or_native_link_qualification': True,\n"+
 "        'fixed_ACK_production_inputs': COMPOSER_INPUTS, 'fixed_checkout_declarations': COMPOSER_DECLARATIONS,\n"+
 "        'exact_private_Blueprint_projection_scope': COMPOSER_PROJECTED_BLUEPRINTS,\n"+
 "        'tests_executed': False, 'Android_Binder_ABI_qualified': False,\n"+
 "        'Wayland_GPU_runtime_qualified': False, 'service_activation_performed': False");
 edit(f.plan,plan);
 edit(f.completion_gate,i.completion.trimEnd());
 let build=f.build;
 need(build.includes("STARTING_TYPED_FRAMEWORK_NORMAL_STRICT_PROVIDER_TWO_TARGET_BUILD")&&build.includes("FRAMEWORK_COMMAND_COMPLETED_QUALIFICATION_PENDING"),"BUILD_STATE_PREIMAGE");
 build=build.replace("STARTING_TYPED_FRAMEWORK_NORMAL_STRICT_PROVIDER_TWO_TARGET_BUILD","STARTING_COMPOSER_NORMAL_STRICT_SERVICE_AND_AIDL_TEST_BUILD").replace("FRAMEWORK_COMMAND_COMPLETED_QUALIFICATION_PENDING","COMPOSER_COMMAND_COMPLETED_QUALIFICATION_PENDING");
 build=build.replace('"complete_framework_Java_and_Android_TU_qualified": False,','"actual_ELF_AIDL_and_native_link_inputs_qualified": False,\n                    "Android_Binder_ABI_qualified": False, "Wayland_GPU_runtime_qualified": False,\n                    "tests_executed": False,');
 edit(f.build,build);
 const count="    need(len(passed) == len(set(passed)) == 46, 'CONTROL_CASE_COUNT')";
 ctrl(count,i.controlFragment+"    need(len(passed) == len(set(passed)) == 56, 'CONTROL_CASE_COUNT')");
 ctrl("Actual pure Python functions with synthetic identity/resource/failure fixtures and exact staged lock metadata; no device reuse, Main observation, Rust or Soong qualification.","Actual pure Python functions with synthetic identity/resource/failure fixtures, exact staged lock metadata and ten Composer record gates; no device reuse, Main observation, Rust, Soong, Binder ABI or GPU qualification.");
 const after=funcs(framework),changed=Object.keys(f).filter(k=>f[k]!==after[k]),added=Object.keys(after).filter(k=>!(k in f));
 need(JSON.stringify(changed.sort())===JSON.stringify(["builder_contract","plan","completion_gate","build"].sort())&&JSON.stringify(added)===JSON.stringify(["qualify_composer_records"]),"ONLY_COMPOSER_GATES_AND_BUILD_LABELS");
 const unchanged=Object.keys(f).filter(k=>f[k]===after[k]);
 for(const k of["record_resource_admission","memory_admission","parse_admission_meminfo","prior_failure_contract","fresh_published_binding","verify_prepared","observe_inputs","verify_inputs_after","cleanup_children","preparation_contract","main"])need(unchanged.includes(k),"UNCHANGED_GATE:"+k);
 for(const[list,newText,oldText]of[[edits,framework,i.framework],[controlEdits,controls,i.controls]]){let t=newText;for(const e of [...list].reverse()){need(t.slice(e.at,e.at+e.after.length)===e.after,"INVERSE_SEGMENT");t=t.slice(0,e.at)+e.before+t.slice(e.at+e.after.length);}need(t===oldText,"WHOLE_INVERSE");}
 return {framework,controls,edits,controlEdits,root,build_parent:parent,unchangedFunctions:unchanged,changedFunctions:changed,addedFunctions:added,fixedInputs,declarations,blueprints,actual_review:qualified,sourceScope:{schema:1,state:"ACTUAL474_BOUND_COMPOSER_NORMAL_SOURCE_ONLY_RESOURCE_HOLD",targets:scope.targets,source_lock:scope.source_lock,source_files:501,ACK_inputs:9,checkout_declarations:3,actual_host_commands:74,actual_host_focused:35,planned_pure_controls:56,unchanged_base_controls:46,new_record_controls:10,real_capture_controls:4,Main8_source_unchanged:true,resource_functions_unchanged:true,workspace_locks:["package-build.lock","aosp-source-update.lock"],projection_journal:"source-projection.json",entry:"composer-retirement-build",ALLOW_MISSING_DEPENDENCIES:false,owned_memory_max:10737418240,owned_swap_max:0,fresh_MemAvailable_required:16106127360,jobs:1,CPU:2,builder_timeout_seconds:6100,outer_timeout_seconds:6400,command_completed:false,Android_Binder_ABI_qualified:false,Wayland_GPU_runtime_qualified:false,tests_executed:false,deployment:false,Main_actions:0}};
}
