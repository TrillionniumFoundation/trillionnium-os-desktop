"use strict";
// Pure binder. No I/O, dispatch, process launch, or source-tree mutation.
// actualPins must come from Root's independently qualified actual compile stdout.
// Raw result bytes are retained without JSON reserialization; ns identities stay exact.
const PART_PINS = {"framework_build.template.py":{"bytes":62362,"sha256":"abb6c1ba7c791e73c48d3411de3426b4cc3850d0f34a64124326cf937bf67887"},"fenced_build.template.py":{"bytes":25419,"sha256":"615b688447a28e071fb5d5c5edc36833c201392d8094ab8356a736a18b622028"},"stage.base.py":{"bytes":5442,"sha256":"d4d80d5e44ca6990f351a71b6ae6b59a66359b21db356472aabdc55f4e0a2443"},"transport.base.py":{"bytes":1233,"sha256":"882ed7f1748372919b5167ba5bc7f9a5393c4d2e8af168ba6748239251e3003a"},"main_snapshot.py":{"bytes":14294,"sha256":"1fd614b6e7b4900feff1a114c0cd221a1fb00fc0cea9878db1f3ae5672d561cf"},"frozen-work-inventory.py":{"bytes":48443,"sha256":"203dd7f4efdac01891a4c31fd79f2eb3204e3c8c2be5702988f0875307cce9ab"},"actual-work-preparation.json":{"bytes":11091,"sha256":"ab286f3939acfeb648a716ca15e5df348fef6b7007eb5651735fe8a7bda96b1c"},"actual-native-prebuilt-Android.bp":{"bytes":1017,"sha256":"d1eca99403572ee9d481e777febac8d4e062f44fd8844285ffc452b17beb531a"},"capture_lifecycle.py":{"bytes":25227,"sha256":"4ffc5a7d6a54ad2cd4351ef30f90a12143614206953e97219f3d6cf5c6e1fc28"},"root_snapshot_supervisor.py":{"bytes":12041,"sha256":"f493a324cb5694f618d0fed3d5ed17ff90aa64924b671ea99550622f6090b5b7"},"prior-normal02-outer-terminal.json":{"bytes":24722,"sha256":"42b2d7b8749047df9e1d40ddf9b70b3f3e187c39ce6a15dd0f5721610e814c00"},"actual-resource-observation01.json":{"bytes":399,"sha256":"feb95f82087d7c68a8c8c42b54cf267b8f9c343ce41e49bb8193e96f49f050da"},"expected-builder469-manifest.json":{"bytes":99327,"sha256":"88dc3c8020c436009862800ffdc5af97f50f6ae7efff832562c2784d66794701"},"prior-framework-inner-terminal.json":{"bytes":5239,"sha256":"6a525b9838f43579bc41b1106891f2f734a0c2d92b0c5cc355f7ab02b39eb2a8"},"prior-framework-outer-terminal.json":{"bytes":24689,"sha256":"273ba8a236253ee3873074a26f568144397044ebcfdd6f153ab8712b29ff70cf"},"actual-published-source-manifest.json":{"bytes":108555,"sha256":"afb23d210fda970a09482a14b9b38af1c92b5be505edd0eda2b76ce5ffc6067f"},"actual-hal-provider-source-lock.json":{"bytes":96934,"sha256":"c7154e445c2bf1a4539418c68a04731538f9ac11050132571b911e706084f8fd"},"pure_controls.py":{"bytes":10970,"sha256":"f9f29b3b31c06967657b02efb291f3c31ab80e3ba77e197733be63bd81c60647"}};
const FILE_ORDER = ["main_snapshot.py","frozen-work-inventory.py","actual-work-preparation.json","expected-builder469-manifest.json","prior-framework-inner-terminal.json","prior-framework-outer-terminal.json","actual-published-source-manifest.json","actual-native-prebuilt-Android.bp","actual-hal-provider-source-lock.json","framework_build.py","fenced_build.py","actual-builder469-result.json","pure_controls.py","capture_lifecycle.py","root_snapshot_supervisor.py","prior-normal02-outer-terminal.json","actual-resource-observation01.json"];
const EXPECTED_TESTS = ["android::tests::repeated_projection_keeps_ninja_outputs_until_content_changes","android::tests::restoration_preserves_original_and_removes_created_file","android::patch_tests::native_engine_effective_projection_records_final_bytes_and_applied_patch","android::patch_tests::patch_in_source_without_git_root_is_restored_inside_enclosing_checkout","android::patch_tests::interrupted_projection_recovers_before_next_build","tests::native_engine_cli_requires_prepared_workspace_and_has_no_arbitrary_targets","tests::native_engine_output_selector_keeps_default_or_exact_explicit_directory","native_role_ingress::tests::observed_lock_passes_normal_schema_and_exact_extension_gate","native_role_ingress::tests::structurally_valid_unobserved_root_is_rejected_before_source_actions","android::tests::typed_shared_provider_projection_keeps_exact_upstream_bodies_and_metadata","android::tests::typed_shared_provider_projection_rejects_changed_missing_or_duplicate_stanzas","android::tests::typed_shared_provider_projection_keeps_other_root_projection_unchanged","native_role_ingress::tests::provider_extension_rejects_unlisted_path_commit_metadata_or_project_change","native_role_ingress::tests::published_workspace_selects_only_exact_current_or_previous_typed_lock","native_role_ingress::tests::previous_typed_manifest_does_not_bypass_fresh_project_verification","android::tests::typed_hal_provider_projection_restores_real_sources_and_keeps_consumers","android::tests::typed_hal_provider_late_source_drift_restores_earlier_projections","native_role_ingress::tests::hal_provider_extension_preserves_all_prior_projects_and_rejects_unlisted_changes"];
const EXPECTED_SOURCE_TESTS = ["resume::tests::completed_project_reuse_has_no_fetch_or_checkout_and_publishes_only_after_verify","resume::tests::initial_checkout_reuses_cached_commit_and_preserves_interrupted_index_lock","resume::tests::nonempty_interrupted_index_lock_is_preserved_in_place_and_rejected","resume::tests::dirty_completed_project_keeps_original_bytes_and_never_gets_manifest","resume::tests::conflicting_untracked_partial_file_is_not_forced_or_removed","resume::tests::wrong_origin_is_rejected_before_any_fetch_or_checkout","resume::tests::recovered_parent_symlink_cannot_create_a_project_outside_staging","resume::tests::mismatched_staging_manifest_is_preserved_and_not_published","resume::tests::sparse_parent_normalization_keeps_exact_locked_selection"];
const EXPECTED_LABELS = ["cargo-version","rustc-version","linked-libraries-0","linked-libraries-1","linked-libraries-2","linked-libraries-3","linked-libraries-4","linked-libraries-5","linked-libraries-6","linked-libraries-7","image-linked-libraries-0","image-linked-libraries-1","image-linked-libraries-2","image-linked-libraries-3","image-linked-libraries-4","image-linked-libraries-5","image-linked-libraries-6","image-linked-libraries-7","image-linked-libraries-8","image-linked-libraries-9","image-linked-libraries-10","image-linked-libraries-11","image-linked-libraries-12","image-linked-libraries-13","image-linked-libraries-14","workspace-no-deps","selected-build","selected-test","builder-compile","builder-help","source-resume-cli-help","builder-test-compile","builder-test-list","builder-test-help","projection-test-0","projection-test-1","projection-test-2","projection-test-3","projection-test-4","projection-test-5","projection-test-6","projection-test-7","projection-test-8","projection-test-9","projection-test-10","projection-test-11","projection-test-12","projection-test-13","projection-test-14","projection-test-15","projection-test-16","projection-test-17","source-resume-selected-test","source-resume-test-compile","source-resume-test-list","source-resume-test-help","projection-test-100","projection-test-101","projection-test-102","projection-test-103","projection-test-104","projection-test-105","projection-test-106","projection-test-107","projection-test-108"];
const EXPECTED_DELTA = {"Cargo_lock_or_dependency_manifest_changed":false,"Go5_or_Blueprint_patch_changed":false,"Rust_source_files_changed":2,"actual_source_file_count":499,"added":["android/manifest/m2-role-ingress-hal-provider-source-lock.json","android/native-role-ingress/provider-fixtures/car-large-parcelable.Android.bp","android/native-role-ingress/provider-fixtures/car-vhal-client.Android.bp","android/native-role-ingress/provider-fixtures/hardware-neural-common.Android.bp","android/native-role-ingress/provider-fixtures/hardware-remote-access.Android.bp","android/native-role-ingress/provider-fixtures/neuralnetworks-common.Android.bp","android/native-role-ingress/provider-fixtures/neuralnetworks-root.Android.bp","android/native-role-ingress/provider-fixtures/neuralnetworks-types.Android.bp"],"builder_revision_name":"469-hal-provider-closure","changed_existing":["tools/droidloom-update/src/android.rs","tools/droidloom-update/src/native_role_ingress.rs"],"engine_source_files_changed":0,"framework_sources_executed_or_built":false,"new_exact_provider_source_lock_added":false,"previous_source_locks_changed":false,"real_published_source_accessed":false,"real_source_staging_accessed":false,"runtime_authorization_enabled":false,"source_resume_library_changed":false,"typed_ingress_framework_patch_changed":false,"unchanged_existing":489,"new_exact_hal_provider_source_lock_added":true};
const BUILD_PARENT = "/home/alex/work/pocket4-native-typed-ingress-builder469-hal-provider-closure-compile-01-20261106";
const NORMAL_ROOT = "/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-provider-build-04-20261106";
const BASE_REQUEST = {"host":"pocket4","executable":"/usr/bin/python3","cwd":"/home/alex/work","env":{"PYTHONDONTWRITEBYTECODE":"1"},"idempotency_key":"pocket4-native-typed-ingress-framework-strict-provider-two-target-build-04-20261106","timeout_seconds":6400,"cpu_quota_percent":200,"memory_max_bytes":10737418240,"nice":10};
const REQUEST_ORDER = ["host","executable","args","cwd","env","stdin","idempotency_key","timeout_seconds","cpu_quota_percent","memory_max_bytes","nice"];
function bindNormal04(parts, actualResultRaw, actualPins, H) {
  function need(value, reason) { if (!value) throw new Error(reason); }
  function pin(raw) {const b=H.utf8(raw);return {bytes:b.length,sha256:H.sha256(b)};}
  function equal(a,b) {
    if(a===b)return true;
    if(a===null||b===null||typeof a!=="object"||typeof b!=="object")return false;
    if(Array.isArray(a)!==Array.isArray(b))return false;
    if(Array.isArray(a))return a.length===b.length&&a.every((v,i)=>equal(v,b[i]));
    const ak=Object.keys(a).sort(),bk=Object.keys(b).sort();
    return equal(ak,bk)&&ak.every(k=>equal(a[k],b[k]));
  }
  function replaceOnce(source, old, value, label) {
    need(source.split(old).length===2,"fixed source replacement count: "+label);
    return source.replace(old,value);
  }
  function replaceLine(source, name, value) {
    const re=new RegExp("^"+name+" = .*$","m"),match=source.match(re);
    need(match!==null,"fixed assignment absent: "+name);
    return replaceOnce(source,match[0],name+" = "+value,name);
  }
  need(equal(Object.keys(parts).sort(),Object.keys(PART_PINS).sort()),"template source set differs");
  for(const [name,want]of Object.entries(PART_PINS))
    need(typeof parts[name]==="string"&&equal(pin(parts[name]),want),"template source pin: "+name);
  need(actualPins&&actualPins.result&&actualPins.builder_elf,"actual four compile output pins required");
  need(actualPins.result.path===BUILD_PARENT+"/attempt01/result.json"&&
       actualPins.builder_elf.path===BUILD_PARENT+"/attempt01/cargo-target/debug/droidloom-update",
       "actual result/ELF path is not this fresh compile01");
  for(const [name,max]of [["result",4*1024*1024],["builder_elf",64*1024*1024]]) {
    const v=actualPins[name];
    need(Number.isSafeInteger(v.bytes)&&v.bytes>0&&v.bytes<=max&&/^[0-9a-f]{64}$/.test(v.sha256),
         "invalid actual "+name+" size/hash");
  }
  need(typeof actualResultRaw==="string"&&
       equal(pin(actualResultRaw),{bytes:actualPins.result.bytes,sha256:actualPins.result.sha256}),
       "actual whole result bytes differ");
  const result=JSON.parse(actualResultRaw);
  need(result.state==="PASS"&&result.focused_tests_passed===27&&
       result.updater_focused_tests_passed===18&&result.source_resume_tests_passed===9&&
       result.original_projection_tests_passed===7&&result.typed_ingress_lock_tests_passed===2&&
       result.provider_closure_tests_passed===6&&result.hal_provider_tests_passed===3&&
       result.actual_registered_test_count===208&&result.source_actual_registered_test_count===20,
       "actual 469 compile and 27 focused controls required");
  need(equal(result.expected_test_names,EXPECTED_TESTS)&&
       equal(result.expected_source_resume_test_names,EXPECTED_SOURCE_TESTS),
       "actual exact test-name sets differ");
  const commands=result.commands;
  need(Array.isArray(commands)&&commands.length===65&&
       equal(commands.map(r=>r.label).sort(),[...EXPECTED_LABELS].sort())&&
       commands.every(r=>r.returncode===0&&r.timed_out===false),
       "actual 65 command closure incomplete");
  for(const [offset,names,count,elfKey,gatesKey]of [
    [0,EXPECTED_TESTS,208,"test_elf","focused_result_gates"],
    [100,EXPECTED_SOURCE_TESTS,20,"source_test_elf","source_resume_result_gates"]]) {
    need(Array.isArray(result[gatesKey])&&result[gatesKey].length===names.length,
         "actual independent result gate count differs");
    names.forEach((name,position)=>{
      const label="projection-test-"+(offset+position), row=commands.find(r=>r.label===label);
      const log="ok "+name+"\n", lp=BUILD_PARENT+"/attempt01/"+label+".libtest";
      const gate={exact_name:name,expected_stdout_runs:1,filtered_out_per_run:count-1,
        outer_results:1,registered_tests:count,summary_and_independent_result_agree:true};
      need(row&&equal(row.argv,[result[elfKey].path,"--exact",name,"--test-threads=1","--nocapture","--logfile",lp])&&
           equal(row.focused_result_gate,gate)&&equal(result[gatesKey][position],gate)&&
           row.independent_libtest_result.path===lp&&
           row.independent_libtest_result.bytes===pin(log).bytes&&
           row.independent_libtest_result.sha256===pin(log).sha256,
           "actual independent exact libtest gate differs: "+name);
    });
  }
  need(equal(result.actual_build_packages,result.actual_test_compile_packages)&&
       new Set(result.actual_build_packages).size===49&&
       result.actual_build_packages.filter(x=>x.startsWith("registry+")).length===45&&
       Array.isArray(result.actual_source_test_compile_packages)&&result.actual_source_test_compile_packages.length>0&&
       result.actual_source_test_compile_packages.every(x=>result.actual_build_packages.includes(x)),
       "actual complete compiler package closure differs");
  need(["copied_source_unchanged_after","original_source_unchanged_after",
        "cargo_configs_unchanged_after","source_test_fixtures_network_disabled"].every(k=>result[k]===true)&&
       equal(result.dependency_changes,[])&&equal(result.tool_changes,[])&&equal(result.observed_signals,[])&&
       equal(result.cleanup,{errors:[],forced_cleanup:false,initial_owned_children:[],reaped:[],remaining:[]})&&
       result.owned_resource_gate.pass===true&&
       ["oom","oom_kill","oom_group_kill"].every(k=>result.owned_memory_events_delta[k]===0),
       "actual unchanged source/tool/config or owned cleanup/resource gate differs");
  need(equal(result.source_delta,EXPECTED_DELTA)&&
       result.copied_manifest.bytes===99327&&
       result.copied_manifest.sha256==="88dc3c8020c436009862800ffdc5af97f50f6ae7efff832562c2784d66794701"&&
       result.actual_device_staging_reuse_qualified===false&&
       !Object.hasOwn(result.build_environment,"HOME")&&
       result.actual_toolchain.rustup_proxy_executed===false&&
       result.actual_toolchain.rustup_proxy_changed_bytes_approved_for_execution===false&&
       result.runtime_authorization_enabled===false&&
       result.framework_Java_and_Android_JNI_compiled===false&&
       result.transitive_framework_closure_qualified===false,
       "actual source delta or host-only scope differs");
  need(result.builder_elf.path===actualPins.builder_elf.path&&
       result.builder_elf.bytes===actualPins.builder_elf.bytes&&
       result.builder_elf.sha256===actualPins.builder_elf.sha256&&
       Array.isArray(result.builder_elf.identity)&&
       Number.isInteger(result.builder_elf.identity[2])&&(result.builder_elf.identity[2]&0o111)!==0,
       "actual ELF binding differs");
  let controller=parts["framework_build.template.py"];
  for(const [name,value]of [
      ["BUILDER_SHA",JSON.stringify(actualPins.builder_elf.sha256)],
      ["BUILDER_BYTES",String(actualPins.builder_elf.bytes)],
      ["BUILD_RESULT_SHA",JSON.stringify(actualPins.result.sha256)],
      ["BUILD_RESULT_BYTES",String(actualPins.result.bytes)]])
    controller=replaceOnce(controller,name+" = None",name+" = "+value,name);
  let fence=replaceOnce(parts["fenced_build.template.py"],"CONTROLLER_SHA = None",
                        "CONTROLLER_SHA = "+JSON.stringify(pin(controller).sha256),"controller digest");
  const files={};
  for(const name of FILE_ORDER){
    if(name==="framework_build.py")files[name]=controller;
    else if(name==="fenced_build.py")files[name]=fence;
    else if(name==="actual-builder469-result.json")files[name]=actualResultRaw;
    else files[name]=parts[name];
    need(typeof files[name]==="string","staged file missing: "+name);
  }
  const expected=Object.fromEntries(Object.entries(files).map(([k,v])=>[k,pin(v)]));
  let stage=replaceLine(parts["stage.base.py"],"ROOT","Path("+JSON.stringify(NORMAL_ROOT)+")");
  stage=replaceLine(stage,"EXPECTED",JSON.stringify(expected));
  need(stage.includes("controls['passed']!=45")&&stage.includes("capture_lifecycle_controls_expected':4"),
       "unchanged 45 pure/four real capture gates absent");
  const wire=JSON.stringify({schema:1,stage,files})+"\n",wp=pin(wire),sp=pin(stage);
  need(wp.bytes<=1024*1024,"actual normal04 wire exceeds one MiB tool limit");
  let boundary=parts["transport.base.py"];
  for(const [name,value]of [["WIRE_BYTES",String(wp.bytes)],["WIRE_SHA256",JSON.stringify(wp.sha256)],
                            ["STAGE_BYTES",String(sp.bytes)],["STAGE_SHA256",JSON.stringify(sp.sha256)]])
    boundary=replaceLine(boundary,name,value);
  const unsorted={...BASE_REQUEST,args:["-I","-B","-c",boundary,"--execute-once"],stdin:wire},requestObject={};
  for(const name of REQUEST_ORDER)requestObject[name]=unsorted[name];
  const request=JSON.stringify(requestObject,null,2)+"\n";
  const bindings={schema:1,state:"ACTUAL_469_COMPILE_BOUND_NORMAL04_UNRUN",
    actual_result:{path:actualPins.result.path,...pin(actualResultRaw)},
    actual_builder_elf:{path:actualPins.builder_elf.path,bytes:actualPins.builder_elf.bytes,sha256:actualPins.builder_elf.sha256},
    source_manifest:{bytes:99327,sha256:"88dc3c8020c436009862800ffdc5af97f50f6ae7efff832562c2784d66794701"},
    current_lock_projects:225,previous_published_projects:224,normal_builder_source_files:499,
    actual_host_compile_commands:65,actual_focused_controls:27,
    fresh_full_previous224_worktree_qualification_required:true,normal04_executed:false,
    Java_and_Android_JNI_qualified:false,runtime_authorization_enabled:false,
    request:pin(request),stdin:wp,stage:sp,controller:pin(controller),fence:pin(fence)};
  return {request,request_object:requestObject,stdin:wire,files,stage,boundary,bindings};
}
