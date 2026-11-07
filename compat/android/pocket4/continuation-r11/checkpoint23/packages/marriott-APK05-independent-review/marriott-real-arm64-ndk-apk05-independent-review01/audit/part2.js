function auditAPK05Part2(r,c,U,B,oldSDK,newSDK) {
  const failures=[];let checks=0;const ok=(v,m)=>{checks++;if(!v)failures.push(m);};
  const canon=v=>JSON.stringify(v,(_,x)=>x&&typeof x==="object"&&!Array.isArray(x)?Object.fromEntries(Object.entries(x).sort(([a],[b])=>a.localeCompare(b))):x),eq=(a,b)=>canon(a)===canon(b);
  const ascii=b=>{let s="";for(let i=0;i<b.length;i+=16384)s+=String.fromCharCode(...b.subarray(i,i+16384));return s;};
  const tuple=row=>({...row.before,path:row.path,resolved_path:row.path,bytes:row.bytes,sha256:row.sha256});
  function complete(row,label) {
    ok(row.complete===true&&row.error===null&&row.full_reads===2&&row.expected_matches===true&&row.owned_leaf_FDs_closed===true&&row.whole_input_and_identity_unchanged===true,label+" complete full reads");
    for(const k of ["held_after","named_before","named_after"])ok(eq(row.before,row[k]),label+" "+k+" exact");
    ok(row.before.bytes===row.bytes&&/^[0-9a-f]{64}$/.test(row.sha256),label+" complete file");
  }
  ok(oldSDK.inputs.length===22&&oldSDK.collection_complete===false&&oldSDK.errors.length===1&&oldSDK.first_error.stage==="input:existing_soong_variables"&&oldSDK.first_error.errno===2,"old SDK22 failure preserved");
  ok(newSDK.inputs.length===9&&newSDK.collection_complete===true&&eq(newSDK.errors,[])&&newSDK.first_error===null&&newSDK.all_tracked_owned_FDs_closed===true,"new product-derived SDK actual PASS");
  const sdk=new Map();
  for(const x of oldSDK.inputs)if(x.complete){complete(x,"old SDK "+x.role);sdk.set(x.role,x);}
  ok(sdk.size===21,"exact 21 individually complete old rows");
  for(const x of newSDK.inputs){complete(x,"new SDK "+x.role);sdk.set(x.role,x);}
  ok(sdk.size===27,"composed 27 actual SDK input roles");
  for(const[k,x]of sdk)ok(eq(r.bound_inputs["SDK22:"+k],tuple(x)),"actual SDK full tuple "+k);
  for(const key of ["actual_sdk22_failed_original","actual_sdk_configuration"]){
    const b=B.dec(c[key].base64);ok(b.length===c[key].bytes&&U.sha256(b)===c[key].sha256,"original full SDK receipt "+key);
    const t=B.dec(c[key].terminal.base64),v=JSON.parse(ascii(t));
    ok(t.length===c[key].terminal.bytes&&U.sha256(t)===c[key].terminal.sha256,"SDK exact terminal bytes "+key);
    const code=key==="actual_sdk22_failed_original"?1:0;
    ok(v.job_id===c[key].terminal.job_id&&v.exit_code===code&&v.output_complete===true&&v.output_durable===true&&v.terminal_publication_confirmed===true&&v.timed_out===false&&v.cancelled===false&&v.automatic_retry===false,"SDK actual terminal lifecycle "+key);
  }
  const o=r.apk13_first_observation;
  ok(o.rows.length===13&&o.errors.length===0&&o.first_error===null&&o.format_requirements_passed===true&&o.control_deadline_met===true,"own actual 13 all-qualified");
  ok(o.children_started===0&&o.Android_actions===0&&o.Main_actions===0&&o.global_ambient_FD_equality_asserted===false&&o.prior_reader02_admission_borrowed===false,"observer no extra authority");
  ok(o.observation_deadline_seconds===40&&o.control_deadline_seconds===45&&o.elapsed_seconds<40,"observer original bounds");
  ok(o.FD_events.length===428&&o.FD_events.every(x=>x.close_attempted===true&&x.closed===true&&!x.close_error)&&o.all_tracked_owned_FDs_closed===true,"428 observer FDs closed");
  const ob=B.dec(c.apk13_observer.base64);
  ok(ob.length===c.apk13_observer.bytes&&U.sha256(ob)===c.apk13_observer.sha256&&o.source_sha256===c.apk13_observer.sha256,"actual observer source exact");
  let observedBytes=0;
  for(const spec of c.apk_input_specifications){
    const x=o.rows.find(x=>x.role===spec.role);
    ok(x!==undefined&&x.path===spec.path&&x.bytes===spec.expected_bytes&&x.sha256===spec.expected_sha256,"APK13 exact own specification "+spec.role);
    if(!x)continue;complete(x,"APK13 "+spec.role);observedBytes+=x.bytes*2;
    ok(eq(r.bound_inputs["APK13:"+spec.role],tuple(x)),"APK13 bound full tuple "+spec.role);
  }
  ok(o.complete_bytes_read===observedBytes&&observedBytes===104555928,"complete own13 full byte reads");
  const archiveCounts={ndk_libcxx_static:54,ndk_libcxxabi:18,arm64_unwind:9,arm64_builtins:288};
  for(const[k,n]of Object.entries(archiveCounts)){
    const f=o.rows.find(x=>x.role===k).format_facts;
    ok(f.format==="regular_archive"&&f.members===n&&eq(f.ELF_machine_type_class_data_counts,{"183:1:2:1":n})&&f.architecture_qualified===true&&f.all_members_ELF64_AARCH64_REL_LSB===true&&f.external_members_followed===false&&f.LLVM_bitcode_members===0&&f.other_members===0,"all real archive members "+k);
  }
  const classes={android_jar31_anchor:["android/app/Activity.class","android/os/Bundle.class"],android_test_runner31:["android/test/InstrumentationTestRunner.class"],android_test_base31:["android/test/InstrumentationTestCase.class","junit/framework/Assert.class","junit/framework/TestCase.class"],android_test_mock31:["android/test/mock/MockContext.class"]};
  let classCount=0;
  for(const[k,names]of Object.entries(classes)){
    const f=o.rows.find(x=>x.role===k).format_facts;
    ok(f.format==="zip"&&f.all_required_classes_present===true&&f.class_bodies_exported===false&&f.extracted_files===0&&eq(Object.keys(f.required_classes).sort(),names.sort()),"actual JAR class distribution "+k);
    for(const x of Object.values(f.required_classes)){classCount++;ok(x.present===true&&x.bytes>0&&/^[0-9a-f]{64}$/.test(x.sha256),"actual complete JAR class");}
  }
  const reg=r.linked_test_registry;
  ok(eq(Object.keys(reg.linked_TestBody_symbols).sort(),c.registry.registry)&&c.registry.registry_count===23&&reg.expected_count===23,"exact original23 registry");
  ok(reg.expected_focus_count===12&&c.registry.expected_selected_count===12&&eq(c.registry.expected_selected,c.registry.registry.filter(x=>x.startsWith("ProcSelfMaps."))),"exact12 focus");
  ok(c.new_test_names.length===9&&c.test_names.length===12&&c.new_test_names.every(n=>c.registry.expected_selected.includes("ProcSelfMaps."+n)),"nine FD plus three original tests");
  for(const[name,x]of Object.entries(reg.linked_TestBody_symbols)){
    const cls=name.replace(".","_")+"_Test";
    const symbol=name.startsWith("ProcSelfMaps.")?"_ZN12_GLOBAL__N_1"+cls.length+cls+"8TestBodyEv":"_ZN"+cls.length+cls+"8TestBodyEv";
    ok(x.name===symbol&&x.defined===true&&x.type===2&&x.size>0&&x.binding===(name.startsWith("ProcSelfMaps.")?0:1),"actual original TestBody "+name);
  }
  ok(reg.test_execution===false&&reg.registration_runtime_observed===false&&reg.runtime_must_supply_nonempty_original_VerifyTestList===true,"static registry boundary");
  ok(eq(r.compiled_JNI_symbol_join,{RunAllTests:"_ZN8ndk_test11RunAllTestsEP7_JNIEnvP8_jobjectP8_jstringS5_",entry:"Java_com_example_ndk_1tests_NdkTests_runTests",executed:false,linked:true}),"actual JNI reference/definition join");
  const libs=Object.fromEntries(r.linked_libraries.map(x=>[x.soname,x]));
  for(const name of ["libc.so","libdl.so","libm.so","liblog.so","libz.so"]){
    const x=libs[name];
    ok(x.SDK_link_interface_only===true&&x.packaged_or_executed===false&&x.official_symbol_count>0&&eq(x.needed,[]),"SDK interface only "+name);
  }
  const main=libs["libberberis_ndk_tests.so"],shared=libs["libberberis_ndk_tests_shared_lib.so"];
  ok(eq(shared.needed,["libc.so","libm.so","libdl.so"])&&eq(main.needed,["libberberis_ndk_tests_shared_lib.so","liblog.so","libz.so","libc.so","libm.so","libdl.so"]),"exact native DT_NEEDED");
  for(const x of [main,shared])ok(x.SDK_link_interface_only===false&&x.executed===false&&eq(x.notes.android_sdk_ident,[37])&&x.notes.GNU_build_id.length===1&&/^[0-9a-f]+$/.test(x.notes.GNU_build_id[0]),"real native dynamic/CRT identity");
  ok(shared.SharedFunction.defined===true&&shared.SharedFunction.type===2&&shared.SharedFunction.binding===1&&shared.SharedFunction.visibility===0&&shared.SharedFunction.size>0,"SharedFunction real defined");
  const exports=["JNI_OnLoad","Java_com_example_ndk_1tests_NdkTests_runTests","Java_com_example_ndk_1tests_NdkTests_returnInt","Java_com_example_ndk_1tests_NdkTests_returnFloat"];
  ok(eq(Object.keys(main.JNI_exports).sort(),exports.sort())&&main.GNU_EH_FRAME_program_headers===1,"four JNI exports/EH frame");
  for(const x of Object.values(main.JNI_exports))ok(x.defined===true&&x.type===2&&x.binding===1&&x.visibility===0&&x.size>0,"export full defined function");
  const contract=r.APK_contract;
  ok(contract.package==="com.example.ndk_tests"&&contract.min_sdk===14&&contract.target_sdk===24&&contract.java_classes===2&&contract.instrumentation==="android.test.InstrumentationTestRunner","original fixture manifest target24");
  ok(contract.native_members.length===2&&contract.SDK_interfaces_packaged===false&&contract.runtime_executed===false&&contract.runtime_must_use_instrumentation_with_nonempty_23_test_list===true&&contract.Activity_empty_test_list_route_admitted===false&&contract.private_signing_material_body_exported===false,"APK packaging/unused activity route boundary");
  for(const x of contract.native_members){const name=x.member.slice("lib/arm64-v8a/".length),a=libs[name]?.artifact;ok(x.member==="lib/arm64-v8a/"+name&&a&&a.bytes===x.bytes&&a.sha256===x.sha256,"actual packaged native full pin "+name);}
  const verify=r.commands.find(x=>x.argv[0]===c.java_tools.apksigner.path&&x.argv[1]==="verify");
  const match=[...verify.stdout.matchAll(/Signer #1 certificate SHA-256 digest: ([0-9a-f]{64})/g)].map(x=>x[1]);
  ok(eq(match,[contract.signature_certificate_sha256]),"actual signer command agrees");
  const badging=r.commands.find(x=>x.argv[0]===c.java_tools.aapt.path&&x.argv[1]==="dump"&&x.argv[2]==="badging").stdout;
  ok(badging.includes("package: name='com.example.ndk_tests'")&&badging.includes("sdkVersion:'14'")&&badging.includes("targetSdkVersion:'24'")&&badging.includes("native-code: 'arm64-v8a'"),"actual APK badging complete values");
  ok(r.real_CRT.brand_sdk===37&&r.real_CRT.legacy_workaround===false&&r.real_CRT.end_path===c.root+"/objects/crtend-so.o","real CRT/brand");
  const gen=r.sdk_interface_generation;
  ok(gen.original_generator_sha256===sdk.get("ndkstubgen_source").sha256&&gen.original_parser_sha256===sdk.get("symbolfile_source").sha256&&gen.api_argument==="current"&&gen.decoded_api===10000&&gen.arch==="arm64"&&gen.ndk===true&&gen.systemapi===false&&gen.apex===false&&gen.llndk===false&&gen.runtime_implementation===false&&gen.packaged_or_executed===false&&Object.keys(gen.outputs).length===5,"official SDK interface algorithm and scope");
  const target=r.native_module_targets;
  ok(target.CRT_brand===37&&target.SDK_values_modified===false&&target.manifest_min_sdk===14&&target.manifest_target_sdk===24&&target.cpufeatures.normalized===21&&target["libgtest_ndk_c++"].normalized===21&&target.original_APK_libraries.normalized===10000,"separate original native module SDKs preserved");
  ok(r.sdk_configuration.Platform_sdk_version===37&&r.sdk_configuration.SDK_values_modified===false&&r.sdk_configuration.source_sha256===sdk.get("existing_soong_variables").sha256&&r.sdk_configuration.api_map_sha256===sdk.get("existing_generated_api_map").sha256&&r.sdk_configuration.runtime_platform_library_qualification===false,"actual product SDK binding not Main SDK");
  ok(ascii(B.dec(c.sources["raw_owner_reference.h"].base64)).includes("#define BERBERIS_PROCMAPS_RAW_METADATA_OWNER 0")&&r.commands.every(x=>x.argv.every(a=>!a.includes("BERBERIS_PROCMAPS_RAW_METADATA_OWNER=1"))),"original engine default not enabled");
  return {checks,failures,composed_sdk_inputs:sdk.size,apk_inputs:o.rows.length,observer_FDs:o.FD_events.length,complete_bytes_read:observedBytes,class_count:classCount,registry23:23,focus12:12,new_FD_tests:9,actual_signer:contract.signature_certificate_sha256};
}