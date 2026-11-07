"use strict";
// Pure preparation only. Root separately qualifies actual job terminal/admission.
// Actual report/stdout strings are preserved verbatim; parsed nanosecond identities are never reserialized.
function bindNormal09(templateFiles, actualReportText, actualStdoutText, normal08RequestText, H) {
  const need=(ok,message)=>{if(!ok)throw Error(message);};
  const pin=s=>{const b=H.utf8(s);return {bytes:b.length,sha256:H.sha256(b)};};
  const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==="object"?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
  const equal=(a,b)=>JSON.stringify(canonical(a))===JSON.stringify(canonical(b));
  const templatePins={"main_snapshot.py":{"bytes":14642,"sha256":"264100ef85e1792c437a4f450050041141288a0f25a4387af5774c52d0dcea06"},"frozen-work-inventory.py":{"bytes":48443,"sha256":"203dd7f4efdac01891a4c31fd79f2eb3204e3c8c2be5702988f0875307cce9ab"},"actual-work-preparation.json":{"bytes":11091,"sha256":"ab286f3939acfeb648a716ca15e5df348fef6b7007eb5651735fe8a7bda96b1c"},"expected-builder473-manifest.json":{"bytes":99775,"sha256":"a3426e40f9446b85931c82e8ba08335e72cd9bd0ac4a3f70aa01d54200d1ae13"},"prior-framework-inner-terminal.json":{"bytes":2898,"sha256":"58a68cae2784bf401315c8016108304576e11d16bf3d5c64552698d4c3a2bb57"},"prior-framework-outer-terminal.json":{"bytes":24714,"sha256":"2e10bdca3a1b88fe8e72f87dde5f38d972f8db41ce087386fa189c40ad231612"},"actual-published-source-manifest.json":{"bytes":108555,"sha256":"afb23d210fda970a09482a14b9b38af1c92b5be505edd0eda2b76ce5ffc6067f"},"actual-native-prebuilt-Android.bp":{"bytes":1017,"sha256":"d1eca99403572ee9d481e777febac8d4e062f44fd8844285ffc452b17beb531a"},"actual-hal-provider-source-lock.json":{"bytes":96957,"sha256":"72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d"},"framework_build.py":{"bytes":63597,"sha256":"dd6734852b33517cd971f88a5f6ee263df4f78ec18d1b389da28e174b765e12e"},"fenced_build.py":{"bytes":25483,"sha256":"808daeb71496b9f8e49937c493d2a236a0d5110032cdd07464e0c4295d15bb55"},"pure_controls.py":{"bytes":10982,"sha256":"19d30bb230d148967d106cd43196baf402465a3c34b906ab25f08827951b7b3f"},"capture_lifecycle.py":{"bytes":25240,"sha256":"2dcf44609e6ef53e91b2d8e3a07c192fe65a7d44601f218dc8990272285d4dfe"},"root_snapshot_supervisor.py":{"bytes":12041,"sha256":"903ae227d9231a361c61fad6fd584c97a548bb5a41b09a4e5fa8824e13e02350"},"prior-normal02-outer-terminal.json":{"bytes":24722,"sha256":"42b2d7b8749047df9e1d40ddf9b70b3f3e187c39ce6a15dd0f5721610e814c00"},"actual-resource-observation01.json":{"bytes":399,"sha256":"feb95f82087d7c68a8c8c42b54cf267b8f9c343ce41e49bb8193e96f49f050da"},"actual-current225-source-manifest.json":{"bytes":109252,"sha256":"5ae96f8d2bc32986fdbf8fea12f54dbcb02b1ed1601894b2b23998f61aba0d7d"}};
  const oldRequestPin={"bytes":1022914,"sha256":"7ac74723eaff25849512943bfe25ec87ec0eff36807f5b787f44862c31033c65"};
  const expectedTests=["android::tests::repeated_projection_keeps_ninja_outputs_until_content_changes","android::tests::restoration_preserves_original_and_removes_created_file","android::patch_tests::native_engine_effective_projection_records_final_bytes_and_applied_patch","android::patch_tests::patch_in_source_without_git_root_is_restored_inside_enclosing_checkout","android::patch_tests::interrupted_projection_recovers_before_next_build","tests::native_engine_cli_requires_prepared_workspace_and_has_no_arbitrary_targets","tests::native_engine_output_selector_keeps_default_or_exact_explicit_directory","native_role_ingress::tests::observed_lock_passes_normal_schema_and_exact_extension_gate","native_role_ingress::tests::structurally_valid_unobserved_root_is_rejected_before_source_actions","android::tests::typed_shared_provider_projection_keeps_exact_upstream_bodies_and_metadata","android::tests::typed_shared_provider_projection_rejects_changed_missing_or_duplicate_stanzas","android::tests::typed_shared_provider_projection_keeps_other_root_projection_unchanged","native_role_ingress::tests::provider_extension_rejects_unlisted_path_commit_metadata_or_project_change","native_role_ingress::tests::published_workspace_selects_only_exact_current_or_previous_typed_lock","native_role_ingress::tests::previous_typed_manifest_does_not_bypass_fresh_project_verification","android::tests::typed_hal_provider_projection_restores_real_sources_and_keeps_consumers","android::tests::typed_hal_provider_late_source_drift_restores_earlier_projections","native_role_ingress::tests::hal_provider_extension_preserves_all_prior_projects_and_rejects_unlisted_changes","android::tests::typed_systemui_test_projection_keeps_metadata_parent_providers_and_other_paths","android::tests::typed_systemui_test_projection_rejects_wrong_source_before_journal_or_write","android::tests::typed_systemui_test_projection_recovers_complete_original_from_durable_journal","android::tests::typed_audiocontrol_example_projection_keeps_metadata_and_sibling_sources","android::tests::typed_audiocontrol_example_projection_rejects_source_drift_before_write","android::tests::typed_audiocontrol_example_projection_recovers_full_observed_original"];
  const expectedIndices=[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,200,201,202,203,204,205];
  const expectedSourceTests=["resume::tests::completed_project_reuse_has_no_fetch_or_checkout_and_publishes_only_after_verify","resume::tests::initial_checkout_reuses_cached_commit_and_preserves_interrupted_index_lock","resume::tests::nonempty_interrupted_index_lock_is_preserved_in_place_and_rejected","resume::tests::dirty_completed_project_keeps_original_bytes_and_never_gets_manifest","resume::tests::conflicting_untracked_partial_file_is_not_forced_or_removed","resume::tests::wrong_origin_is_rejected_before_any_fetch_or_checkout","resume::tests::recovered_parent_symlink_cannot_create_a_project_outside_staging","resume::tests::mismatched_staging_manifest_is_preserved_and_not_published","resume::tests::sparse_parent_normalization_keeps_exact_locked_selection"];
  const expectedLabels=["cargo-version","rustc-version","linked-libraries-0","linked-libraries-1","linked-libraries-2","linked-libraries-3","linked-libraries-4","linked-libraries-5","linked-libraries-6","linked-libraries-7","image-linked-libraries-0","image-linked-libraries-1","image-linked-libraries-2","image-linked-libraries-3","image-linked-libraries-4","image-linked-libraries-5","image-linked-libraries-6","image-linked-libraries-7","image-linked-libraries-8","image-linked-libraries-9","image-linked-libraries-10","image-linked-libraries-11","image-linked-libraries-12","image-linked-libraries-13","image-linked-libraries-14","workspace-no-deps","selected-build","selected-test","builder-compile","builder-help","source-resume-cli-help","builder-test-compile","builder-test-list","builder-test-help","projection-test-0","projection-test-1","projection-test-2","projection-test-3","projection-test-4","projection-test-5","projection-test-6","projection-test-7","projection-test-8","projection-test-9","projection-test-10","projection-test-11","projection-test-12","projection-test-13","projection-test-14","projection-test-15","projection-test-16","projection-test-17","projection-test-200","projection-test-201","projection-test-202","projection-test-203","projection-test-204","projection-test-205","source-resume-selected-test","source-resume-test-compile","source-resume-test-list","source-resume-test-help","projection-test-100","projection-test-101","projection-test-102","projection-test-103","projection-test-104","projection-test-105","projection-test-106","projection-test-107","projection-test-108"];
  const expectedDelta={"Cargo_lock_or_dependency_manifest_changed":false,"Go5_or_Blueprint_patch_changed":false,"Rust_source_files_changed":1,"SystemUI471_projection_and_fixture_unchanged":true,"actual_source_file_count":501,"added":["android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp"],"builder_revision_name":"473-fixed-audiocontrol-example-projection","changed_existing":["tools/droidloom-update/src/android.rs"],"current_hal_source_lock_unchanged":true,"engine_source_files_changed":0,"fixed_Audiocontrol_example_BP_original_fixture_added":true,"framework_sources_executed_or_built":false,"new_exact_hal_provider_source_lock_added":false,"new_exact_provider_source_lock_added":false,"previous_source_locks_changed":false,"real_published_source_accessed":false,"real_source_staging_accessed":false,"runtime_authorization_enabled":false,"source_resume_library_changed":false,"typed_ingress_framework_patch_changed":false,"unchanged_existing":499};
  const compileRoot="/home/alex/work/pocket4-native-typed-ingress-builder473-audiocontrol-example-projection-compile-01-20261106";
  const manifestSha="a3426e40f9446b85931c82e8ba08335e72cd9bd0ac4a3f70aa01d54200d1ae13";
  need(equal(Object.keys(templateFiles).sort(),Object.keys(templatePins).sort()),"closed template source set");
  for(const[name,wanted]of Object.entries(templatePins))
    need(typeof templateFiles[name]==="string"&&equal(pin(templateFiles[name]),wanted),"template pin differs: "+name);
  need(typeof normal08RequestText==="string"&&equal(pin(normal08RequestText),oldRequestPin),"actual Normal08 source request differs");
  need(typeof actualReportText==="string"&&typeof actualStdoutText==="string","raw actual originals required");
  const reportPin=pin(actualReportText);
  need(reportPin.bytes>0&&reportPin.bytes<=4*1024*1024&&pin(actualStdoutText).bytes<=65536,
       "actual compile originals exceed fixed bound");
  const result=JSON.parse(actualReportText),summary=JSON.parse(actualStdoutText);
  need(equal(Object.keys(summary).sort(),["Main_actions","builder_elf","full_engine_build","result","state"].sort())&&
       summary.state==="PASS"&&summary.Main_actions===0&&summary.full_engine_build===false&&
       summary.result.path===compileRoot+"/attempt01/result.json"&&
       summary.result.bytes===reportPin.bytes&&summary.result.sha256===reportPin.sha256,
       "actual stdout does not bind the complete compile report");
  need(result.state==="PASS"&&result.Main_actions===0&&result.Main_identity_observed===false&&
       result.install_actions===0&&result.network_downloads_permitted===false&&
       result.focused_tests_passed===33&&result.updater_focused_tests_passed===24&&
       result.source_resume_tests_passed===9&&result.provider_closure_tests_passed===6&&result.hal_provider_tests_passed===3&&result.systemui_test_projection_tests_passed===3&&result.audiocontrol_example_projection_tests_passed===3&&
       result.original_projection_tests_passed===7&&result.typed_ingress_lock_tests_passed===2&&
       result.actual_registered_test_count===214&&result.source_actual_registered_test_count===20&&
       equal(result.expected_test_names,expectedTests)&&equal(result.expected_source_resume_test_names,expectedSourceTests),
       "actual fixed builder473 focused test scope incomplete");
  need(result.commands.length===71&&equal(result.commands.map(r=>r.label),expectedLabels)&&
       result.commands.every(r=>r.returncode===0&&r.timed_out===false),"actual compile command closure differs");
  for(const[indices,names,count,elfKey,gatesKey]of [
      [expectedIndices,expectedTests,214,"test_elf","focused_result_gates"],
      [Array.from({length:9},(_,i)=>100+i),expectedSourceTests,20,"source_test_elf","source_resume_result_gates"]]){
    need(result[gatesKey].length===names.length,"exact result gate count");
    names.forEach((name,pos)=>{
      const label="projection-test-"+indices[pos],command=result.commands.find(r=>r.label===label);
      const log=compileRoot+"/attempt01/"+label+".libtest",raw="ok "+name+"\n",lp=pin(raw);
      const gate={exact_name:name,expected_stdout_runs:1,filtered_out_per_run:count-1,outer_results:1,
          registered_tests:count,summary_and_independent_result_agree:true};
      need(equal(command.argv,[result[elfKey].path,"--exact",name,"--test-threads=1","--nocapture","--logfile",log])&&
           equal(command.focused_result_gate,gate)&&equal(result[gatesKey][pos],gate)&&
           command.independent_libtest_result.path===log&&command.independent_libtest_result.bytes===lp.bytes&&
           command.independent_libtest_result.sha256===lp.sha256,"independent libtest binding: "+name);
    });
  }
  need(equal(result.source_delta,expectedDelta)&&result.copied_manifest.path===compileRoot+"/attempt01/copied-builder-source-manifest.json"&&
       result.copied_manifest.bytes===99775&&result.copied_manifest.sha256===manifestSha&&result.source_lock_writer==="UNKNOWN"&&
       result.actual_parent471_compile_authority.bytes===181273&&
       result.actual_parent471_compile_authority.sha256==="466d01e56fa6579636be8e82eedbc4276c31ce3e6b390dc985fe3bc454ead1e9"&&
       result.audiocontrol_example_projection_authority.bytes===6453&&
       result.audiocontrol_example_projection_authority.sha256==="c642e886b77adeb07d8f38a3dd10d042218e8e6582d6fd523be751ef1317b2e5"&&
       result.audiocontrol_example_original_fixture_authority.bytes===1869&&
       result.audiocontrol_example_original_fixture_authority.sha256==="9c8a0aecfa46ce0f1874362fa9dfff6a34326f9bf569b6fe7206dd6db1b3c9a6"&&
       result.systemui_test_projection_retained_from_parent471===true&&
       result.unchanged_225_project_lock_authority.bytes===96957&&
       result.unchanged_225_project_lock_authority.sha256==="72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d",
       "actual builder source, parent471, fixed Audiocontrol example projection and unchanged lock differ");
  need(equal(result.cleanup,{errors:[],forced_cleanup:false,initial_owned_children:[],reaped:[],remaining:[]})&&
       result.owned_resource_gate.pass===true&&["oom","oom_kill","oom_group_kill"].every(k=>result.owned_memory_events_delta[k]===0)&&
       ["copied_source_unchanged_after","original_source_unchanged_after","cargo_configs_unchanged_after","source_test_fixtures_network_disabled"].every(k=>result[k]===true)&&
       result.dependency_changes.length===0&&result.tool_changes.length===0&&result.observed_signals.length===0,
       "actual resource/input/child qualification incomplete");
  need(equal(result.actual_build_packages,result.actual_test_compile_packages)&&
       new Set(result.actual_build_packages).size===49&&result.actual_build_packages.filter(n=>n.startsWith("registry+")).length===45&&
       result.actual_source_test_compile_packages.length>0&&result.actual_source_test_compile_packages.every(n=>result.actual_build_packages.includes(n))&&
       result.actual_device_staging_reuse_qualified===false&&result.runtime_authorization_enabled===false&&
       result.framework_Java_and_Android_JNI_compiled===false&&result.transitive_framework_closure_qualified===false&&
       result.actual_toolchain.rustup_proxy_executed===false&&result.actual_toolchain.rustup_proxy_changed_bytes_approved_for_execution===false&&
       !Object.hasOwn(result.build_environment,"HOME"),"actual dependency/scope qualification differs");
  const elf=result.builder_elf;
  need(elf.path===compileRoot+"/attempt01/cargo-target/debug/droidloom-update"&&
       Number.isSafeInteger(elf.bytes)&&elf.bytes>0&&elf.bytes<=64*1024*1024&&/^[0-9a-f]{64}$/.test(elf.sha256)&&
       summary.builder_elf.path===elf.path&&summary.builder_elf.bytes===elf.bytes&&summary.builder_elf.sha256===elf.sha256,
       "actual ELF summary/report pins disagree");
  const files={...templateFiles};
  const bindings={
      '"__ACTUAL_BUILDER473_SHA256__"':JSON.stringify(elf.sha256),
      '"__ACTUAL_BUILDER473_BYTES__"':String(elf.bytes),
      '"__ACTUAL_COMPILE473_RESULT_SHA256__"':JSON.stringify(reportPin.sha256),
      '"__ACTUAL_COMPILE473_RESULT_BYTES__"':String(reportPin.bytes)
  };
  let source=files["framework_build.py"];
  for(const[before,after]of Object.entries(bindings)){
    need(source.split(before).length===2,"exact single future binding literal");source=source.replace(before,after);
  }
  need(!source.includes("__ACTUAL_"),"unbound actual pin remains");
  files["framework_build.py"]=source;
  const marker='"__BOUND_FRAMEWORK473_CONTROLLER_SHA256__"';
  need(files["fenced_build.py"].split(marker).length===2,"exact fence hash marker");
  files["fenced_build.py"]=files["fenced_build.py"].replace(marker,JSON.stringify(pin(source).sha256));
  files["actual-builder473-result.json"]=actualReportText;
  const old=JSON.parse(normal08RequestText),packet=JSON.parse(old.stdin);
  const oldRoot="typed-ingress-framework-provider-build-08-20261106",newRoot="typed-ingress-framework-provider-build-09-20261106";
  const expected=Object.fromEntries(Object.entries(files).map(([n,s])=>[n,pin(s)]));
  let stage=packet.stage;
  need(stage.split(oldRoot).length===2,"single original stage root");stage=stage.replace(oldRoot,newRoot);
  const oldExpected="EXPECTED = "+JSON.stringify(Object.fromEntries(Object.entries(packet.files).map(([n,s])=>[n,pin(s)])));
  need(stage.split(oldExpected).length===2,"original exact stage source map");
  stage=stage.replace(oldExpected,"EXPECTED = "+JSON.stringify(expected));
  need(Object.keys(files).length===18&&files["pure_controls.py"]===packet.files["pure_controls.py"]&&
       files["actual-published-source-manifest.json"]===packet.files["actual-published-source-manifest.json"],
       "original 46 controls/historical negative manifest not preserved");
  const wire=JSON.stringify({schema:1,stage,files})+"\n";
  need(pin(wire).bytes<=1024*1024,"actual tool one MiB stdin bound");
  let boundary=old.args[3];
  const replacements=[
    ["WIRE_BYTES = "+pin(old.stdin).bytes,"WIRE_BYTES = "+pin(wire).bytes],
    [pin(old.stdin).sha256,pin(wire).sha256],
    ["STAGE_BYTES = "+pin(packet.stage).bytes,"STAGE_BYTES = "+pin(stage).bytes],
    [pin(packet.stage).sha256,pin(stage).sha256]
  ];
  for(const[before,after]of replacements){need(boundary.split(before).length===2,"exact transport preimage");boundary=boundary.replace(before,after);}
  const request={...old,args:[...old.args],stdin:wire,idempotency_key:old.idempotency_key.replace("-08-20261106","-09-20261106")};
  request.args[3]=boundary;
  need(request.idempotency_key!==old.idempotency_key&&request.memory_max_bytes===10737418240&&
       request.cpu_quota_percent===200&&request.nice===10&&request.timeout_seconds===6400,
       "fresh root/key or original resource envelope differs");
  const requestText=JSON.stringify(request,null,2)+"\n";
  return {files,stage,wire,boundary,request,requestText,expected,actual_report_raw:actualReportText,actual_stdout_raw:actualStdoutText,
      actual_report_pin:reportPin,actual_stdout_pin:pin(actualStdoutText),actual_builder:{path:elf.path,bytes:elf.bytes,sha256:elf.sha256},
      proof:{state:"ACTUAL473_BOUND_NORMAL09_NOT_EXECUTED",request:pin(requestText),stdin:pin(wire),stage:pin(stage),
          raw_actual_strings_preserved:true,focused_tests:33,compile_commands:71,normal_controls:46,
          current_Main_snapshot_source_unchanged:true,source_writer:"UNKNOWN",Soong_or_Java_JNI_qualified:false}};
}
