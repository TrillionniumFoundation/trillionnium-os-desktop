function qualifyCurrentThreeSplitInstall(h,lossless,input){
  const app=input.app;
  const config={amazon:{package:'com.amazon.mShop.android.shopping',uid:10129,source:'0240a8bae8d0881cb802f7fa7c9e1670b6fbf19b3444d6bc7a504d31e962f9f6',field:'amazon'},bestbuy:{package:'com.bestbuy.android',uid:10130,source:'e45801a193c6e5e1cdfb5285074d1d6e554db37fdbad876e3d1f19ff55e7742a',field:'ticket'}}[app];
  if(!config)throw Error('ONLY_AMAZON_AND_BESTBUY');
  const need=(v,m)=>{if(!v)throw Error(m)};
  function canonical(v){return v===null?"null":Array.isArray(v)?"["+v.map(canonical).join(",")+"]":typeof v==="object"?"{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canonical(v[k])).join(",")+"}":JSON.stringify(v);}
  const same=(a,b)=>canonical(a)===canonical(b),pin=raw=>({bytes:h.utf8(raw).length,sha256:h.sha(raw)});
  function actual(row,name){need(row&&typeof row.raw==="string"&&same(pin(row.raw),row.pin),"EXACT_ACTUAL_RECEIPT_PIN:"+name);return {value:JSON.parse(row.raw),nodes:lossless.losslessJsonNodes(row.raw)};}
  const install=input.install_source, files=install.files,inputs=install.inputs;
  need(input.install_job_id&&/^[a-z0-9-]+$/.test(input.install_job_id),"ACTUAL_INSTALL_JOB_ID");
  const manifest=JSON.parse(files["SOURCE_PINS.json"]),isha=h.sha(files["SOURCE_PINS.json"]);
  need(isha===install.manifest_sha256&&isha===config.source,"FIXED_CUSTOM_APP_INSTALL02_SOURCE");
  need(Object.keys(manifest.files).length===12&&Object.keys(files).length===13,"FIXED_THIRTEEN_INSTALL02_FILES");
  for(const[n,p]of Object.entries(manifest.files))need(same(pin(files[n]),p),"INSTALL02_SOURCE_CHANGED:"+n);
  const host=JSON.parse(files["host/source-manifest.json"]),hostSHA=h.sha(files["host/source-manifest.json"]),binding=host.current_baseline;
  need(host.schema===2&&host.revision===5&&hostSHA===inputs.current_host_source_manifest_sha256&&Object.keys(host.files).length===14&&same(binding,inputs.current_baseline),"CURRENT_R5_BASELINE_BINDING");
  const root="/home/alex/work/pocket4-owned-"+app+"-qa-r3-install-state-02";
  const docs=Object.fromEntries(["coordinator","stage","worker"].map(k=>[k,actual(input.actual[k],k)]));
  const c=docs.coordinator.value,s=docs.stage.value,w=docs.worker.value;
  need([c,s,w].every(v=>v.ok===true&&v.error===null&&same(v.secondary_errors,[])&&v.source_manifest_sha256===isha),"SUCCESSFUL_EXACT_INSTALL02_CHAIN");
  need([c,s,w].every(v=>v.nonce===inputs.nonces.flow)&&w.state_nonce===inputs.nonces.state,"ACTUAL_INSTALL02_NONCE_CHAIN");
  need(same(s.coordinator_result,{path:root+"/result.json",...input.actual.coordinator.pin})&&
    same(c.worker_result,{path:root+"/worker/result.json",...input.actual.worker.pin})&&c.worker_root===root+"/worker","EXACT_THREE_RECEIPT_PARENT_PATH_CHAIN");
  need(s.coordinator_returncode===0&&s.source_unchanged===true&&s.packet_sha256===h.sha(install.request.stdin)&&
    s.current_host_manifest_sha256===hostSHA&&s.shared_current_host_source_verified===true&&s.Bili_Flow_or_MainBinding_instantiated===false&&
    s.controls.all_passed===true&&s.controls.count===38&&s.controls.cases.length===38&&s.controls.cases.every(v=>v.passed===true)&&
    c.source_and_artifact_unchanged===true&&c.install_state_worker_requested===true&&c.owned_package_retained_for_separate_UI_admission===true,
    "ACTUAL_SOURCE_CONTROLS_AND_CURRENT_HOST_COMPLETE");
  const expectedHost=lossless.nodeField(lossless.losslessJsonNodes(files["host-stage-actual.json"]),["Main_before"]);
  for(const[name,keys]of [["coordinator",["Main_before","Main_after"]],["stage",["Main_before","Main_after"]],["worker",["Main_before_lock","Main_before","Main_after"]]]){
    for(const key of keys)need(lossless.losslessCanonical(lossless.nodeField(docs[name].nodes,[key]))===lossless.losslessCanonical(expectedHost),"EXACT_TYPED_MAIN_MAP:"+name+"."+key);
  }
  const main=w.Main_before;
  need(main.schema==="pocket4-current-main-guard-v1"&&main.Main_epoch_sha256===binding.epoch_sha256&&
    main.current_baseline_sha256===binding.baseline_sha256&&main.current_baseline_qualification_sha256===binding.qualification_sha256&&
    main.seven_processes_match===true&&main.three_host_processes_match===true&&main.resource_limits_match===true,"ACTUAL_CURRENT_BASELINE_QUALIFICATION");
  const self="org.droidloom.qa."+app+".r3",uid=w.owned_package_uid;
  need(Number.isInteger(uid)&&uid>=10000&&uid<100000&&![config.uid,inputs.previous_helper_uid_exclusion.uid].includes(uid)&&
    c.owned_package_uid===uid&&c.package===self&&w.package===self&&c.target_package===config.package&&w.target_package===config.package,"ACTUAL_CURRENT_CUSTOM_APP_HELPER_UID");
  need(w.exact_command_count===13&&w.runtime_shared_recorder_manifest_sha256===hostSHA&&
    w["runtime_"+config.field+"_context_sha256"]===h.sha(files[app+"_context.py"])&&w["runtime_"+config.field+"_transport_sha256"]===h.sha(files[app+"_transport.py"]),"ACTUAL_CUSTOM_CUSTOM_APP_RUNTIME_SOURCE_CHAIN");
  need(w.package_retained===true&&w.install_attempted===true&&w.install_success_observed===true&&w.state_attempted===true&&
    w.outcome_unknown===false&&w.final_Main_guard_passed===true&&w.held_binding_released===true&&w.action_lock_released===true&&
    w.UiAutomation_connection_requested===false&&w.UI_actions===0&&w.audio_actions===0&&w.App_launches===0&&
    w.Bili_Flow_instantiated===false&&w.automatic_retry===false&&w.whole_app_production_ready===false,
    "ACTUAL_INSTALL_SCOPE_AND_RETIREMENT");
  need(w.staging_cleanup.staged_apk_removed===true&&w.staging_cleanup.staged_directory_removed===true&&
    w.staging_cleanup.authority_fds_closed===true&&w.target_FD_cleanup.held_APK_FDs_closed===3,"ACTUAL_STAGING_AND_TARGET_FDS_RETIRED");
  const installed=lossless.nodeField(docs.worker.nodes,["installed_before_state"]);
  need(lossless.losslessCanonical(installed)===lossless.losslessCanonical(lossless.nodeField(docs.worker.nodes,["installed_after_state"])),"LOSSLESS_INSTALLED_IDENTITY_CHANGED");
  need(w.installed_before_state.package===self&&w.installed_before_state.uid===uid&&w.installed_before_state.apk_sha256===inputs.APK.sha256&&
    w.installed_before_state.bytes===inputs.APK.bytes&&w.installed_before_state.signer_bound_by_exact_signed_apk_bytes===inputs.signer_certificate_sha256,
    "ACTUAL_INSTALLED_APK_AND_SIGNER");
  need(w.build.source_manifest_sha256===inputs.qa_source_manifest_sha256&&same(w.build.APK,inputs.APK)&&
    w.build.signer_certificate_sha256===inputs.signer_certificate_sha256,"ACTUAL_SIGNED_BUILD_SOURCE_CHAIN");
  const before=lossless.nodeField(docs.worker.nodes,["target_before"]),after=lossless.nodeField(docs.worker.nodes,["target_after"]);
  const targetRef=lossless.losslessJsonNodes(files["target-artifact-reference.json"]);
  need(lossless.losslessCanonical(before)===lossless.losslessCanonical(after)&&
    lossless.losslessCanonical(lossless.nodeField(before,["metadata"]))===lossless.losslessCanonical(lossless.nodeField(targetRef,["target"]))&&
    lossless.losslessCanonical(lossless.nodeField(before,["artifacts"]))===lossless.losslessCanonical(lossless.nodeField(targetRef,["artifacts"]))&&
    w.target_before.metadata.package===config.package&&w.target_before.metadata.uid===config.uid&&
    w.target_before.metadata.user===0&&w.target_before.artifacts.length===3&&
    w.target_before.signer_independently_verified===false&&w.target_FD_cleanup.commercial_files_changed===false,
    "ACTUAL_CURRENT_THREE_COMMERCIAL_APKS_UNCHANGED");
  const state=w.state,helper=state.helper;
  need(state.actual_command_returncode===0&&state.actual_instrumentation_finish_code===-1&&state.held_transport_returned_after_post_guard===true&&
    state.wire_sha256===c.state_wire_sha256&&typeof state.recorder_command_result_sha256==="string"&&/^[0-9a-f]{64}$/.test(state.recorder_command_result_sha256)&&
    helper.protocol==="pocket4-owned-"+app+"-qa-v3"&&helper.op==="state"&&helper.nonce===inputs.nonces.state&&helper.self_uid===uid&&
    helper.ok===true&&helper.error===null&&same(helper.secondary_errors,[])&&helper.ui_automation_connected===false,"ACTUAL_NO_AUTOMATION_STATE");
  need(state.wire_sha256===h.sha(lossless.losslessCanonical(lossless.nodeField(docs.worker.nodes,["state","helper"]))),"ACTUAL_STATE_WIRE_HASH");

  const extras=Object.fromEntries(["state_command","worker_command","printed_worker"].map(k=>[k,actual(input.actual[k],k)]));
  const wc=extras.worker_command.value,sc=extras.state_command.value;
  need(wc.returncode===0&&wc.joined===true&&wc.timed_out===false&&wc.spawned===true&&
    same(wc.secondary_errors,[])&&wc.name==="01-install-state"&&wc.Main_before===true&&
    same(wc.argv,["/usr/bin/python3","-I",root+"/source/install_state.py","--worker-once","--source-manifest-sha256",isha])&&
    same(wc.stdout,input.actual.printed_worker.pin)&&wc.stderr.bytes===0&&wc.stderr.sha256===h.sha(""),
    "EXACT_JOINED_WORKER_PROCESS_AND_ORIGINAL_PRINTED_STDOUT");
  need(lossless.losslessCanonical(extras.printed_worker.nodes)===lossless.losslessCanonical(docs.worker.nodes),
    "LOSSLESS_ORIGINAL_PRINTED_AND_DURABLE_WORKER_EQUAL");
  need(lossless.losslessCanonical(lossless.nodeField(extras.worker_command.nodes,["Main_after"]))===
    lossless.losslessCanonical(expectedHost),"EIGHTH_TYPED_MAIN_MAP");
  need(input.actual.state_command.pin.sha256===state.recorder_command_result_sha256&&
    sc.returncode===0&&sc.timed_out===false&&sc.spawned===true&&sc.error===null&&same(sc.errors,[])&&
    sc.owned_command_joined===true&&sc.stdout_sha256===state.stdout_sha256&&
    sc.stderr_sha256===state.stderr_sha256&&sc.stderr_sha256===h.sha("")&&sc.action_attempted===false&&
    sc.automatic_retry===false,"EXACT_ORIGINAL_STATE_COMMAND_NO_ACTION");
  const rel={coordinator:"result.json",stage:"stage-result.json",worker:"worker/result.json"};
  return {app,actual_binding:{job_id:input.install_job_id,UID:uid,source_manifest_sha256:isha,
      helper_package:self,protocol:helper.protocol,prior_receipts:Object.fromEntries(Object.keys(rel).map(k=>[k,{path:root+"/"+rel[k],...input.actual[k].pin}])),
      all_six_original_receipts:Object.fromEntries(Object.keys(input.actual).map(k=>[k,input.actual[k].pin])),
      state_nonce:inputs.nonces.state,state_wire_sha256:state.wire_sha256,recorder_command_result_sha256:state.recorder_command_result_sha256,
      current_host_manifest_sha256:hostSHA,current_baseline:binding,eight_Main_maps_match:true,
      commands:13,source_controls:38,install_retired:true,target_APK_count:3,
      historical_input_target_APK_count:inputs.target_APK_count,
      historical_input_count_matches_actual:inputs.target_APK_count===3,
      installed_identity_lossless_json:lossless.losslessCanonical(installed),
      target_identity_lossless_json:lossless.losslessCanonical(before),
      build_proof_lossless_json:lossless.losslessCanonical(lossless.nodeField(docs.worker.nodes,["build"])),
      installed_mtime_ns:lossless.nodeField(installed,["held_file","mtime_ns"]).raw,
      actual_no_automation_state:true,whole_process_tree_cleanup_qualified:false},
    UI_nonce_pool_bound:false,UI_request_created:false,Python_controls_performed:false,
    framework_exit_cause_resolved:false,whole_app_production_ready:false};
}
