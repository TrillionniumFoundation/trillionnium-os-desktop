function qualifyIhgCurrentInstall(h,lossless,input){
  const need=(v,m)=>{if(!v)throw Error(m)};
  function canonical(v){return v===null?"null":Array.isArray(v)?"["+v.map(canonical).join(",")+"]":typeof v==="object"?"{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canonical(v[k])).join(",")+"}":JSON.stringify(v);}
  const same=(a,b)=>canonical(a)===canonical(b),pin=raw=>({bytes:h.utf8(raw).length,sha256:h.sha(raw)});
  function actual(row,name){need(row&&typeof row.raw==="string"&&same(pin(row.raw),row.pin),"EXACT_ACTUAL_RECEIPT_PIN:"+name);return {value:JSON.parse(row.raw),nodes:lossless.losslessJsonNodes(row.raw)};}
  const install=input.install_source, files=install.files,inputs=install.inputs;
  need(input.install_job_id&&/^[a-z0-9-]+$/.test(input.install_job_id),"ACTUAL_INSTALL_JOB_ID");
  const manifest=JSON.parse(files["SOURCE_PINS.json"]),isha=h.sha(files["SOURCE_PINS.json"]);
  need(isha===install.manifest_sha256&&isha==="e8cf9d4c04025bb092663519a01624fa40e552600dc5643a50ebf9bace915103","FIXED_IHG_INSTALL02_SOURCE");
  need(Object.keys(manifest.files).length===12&&Object.keys(files).length===13,"FIXED_THIRTEEN_INSTALL02_FILES");
  for(const[n,p]of Object.entries(manifest.files))need(same(pin(files[n]),p),"INSTALL02_SOURCE_CHANGED:"+n);
  const host=JSON.parse(files["host/source-manifest.json"]),hostSHA=h.sha(files["host/source-manifest.json"]),binding=host.current_baseline;
  need(host.schema===2&&host.revision===5&&hostSHA===inputs.current_host_source_manifest_sha256&&Object.keys(host.files).length===14&&same(binding,inputs.current_baseline),"CURRENT_R5_BASELINE_BINDING");
  const root="/home/alex/work/pocket4-owned-ihg-qa-r2-install-state-02";
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
  const self="org.droidloom.qa.ihg.r2",uid=w.owned_package_uid;
  need(Number.isInteger(uid)&&uid>=10000&&uid<100000&&![10137,10121,10129,10117,10125,10164,10165,10166,10169,10170,10175,10184,10190,10196].includes(uid)&&
    c.owned_package_uid===uid&&c.package===self&&w.package===self&&c.target_package==="com.ihg.apps.android"&&w.target_package==="com.ihg.apps.android","ACTUAL_CURRENT_IHG_HELPER_UID");
  need(w.exact_command_count===13&&w.runtime_shared_recorder_manifest_sha256===hostSHA&&
    w.runtime_ticket_context_sha256===h.sha(files["ihg_context.py"])&&w.runtime_ticket_transport_sha256===h.sha(files["ihg_transport.py"]),"ACTUAL_CUSTOM_IHG_RUNTIME_SOURCE_CHAIN");
  need(w.package_retained===true&&w.install_attempted===true&&w.install_success_observed===true&&w.state_attempted===true&&
    w.outcome_unknown===false&&w.final_Main_guard_passed===true&&w.held_binding_released===true&&w.action_lock_released===true&&
    w.UiAutomation_connection_requested===false&&w.UI_actions===0&&w.audio_actions===0&&w.App_launches===0&&
    w.Bili_Flow_instantiated===false&&w.automatic_retry===false&&w.whole_app_production_ready===false,
    "ACTUAL_INSTALL_SCOPE_AND_RETIREMENT");
  need(w.staging_cleanup.staged_apk_removed===true&&w.staging_cleanup.staged_directory_removed===true&&
    w.staging_cleanup.authority_fds_closed===true&&w.target_FD_cleanup.held_APK_FDs_closed===1,"ACTUAL_STAGING_AND_TARGET_FDS_RETIRED");
  const installed=lossless.nodeField(docs.worker.nodes,["installed_before_state"]);
  need(lossless.losslessCanonical(installed)===lossless.losslessCanonical(lossless.nodeField(docs.worker.nodes,["installed_after_state"])),"LOSSLESS_INSTALLED_IDENTITY_CHANGED");
  need(w.installed_before_state.package===self&&w.installed_before_state.uid===uid&&w.installed_before_state.apk_sha256===inputs.APK.sha256&&
    w.installed_before_state.bytes===inputs.APK.bytes&&w.installed_before_state.signer_bound_by_exact_signed_apk_bytes===inputs.signer_certificate_sha256,
    "ACTUAL_INSTALLED_APK_AND_SIGNER");
  need(w.build.source_manifest_sha256===inputs.qa_source_manifest_sha256&&same(w.build.APK,inputs.APK)&&
    w.build.signer_certificate_sha256===inputs.signer_certificate_sha256,"ACTUAL_SIGNED_BUILD_SOURCE_CHAIN");
  const before=lossless.nodeField(docs.worker.nodes,["target_before"]),after=lossless.nodeField(docs.worker.nodes,["target_after"]);
  need(lossless.losslessCanonical(before)===lossless.losslessCanonical(after)&&w.target_before.metadata.package==="com.ihg.apps.android"&&
    w.target_before.metadata.uid===10137&&w.target_before.metadata.user===0&&w.target_before.metadata.version_code===50023219&&
    w.target_before.artifacts.length===1&&w.target_before.artifacts[0].sha256==="c12bb3bae3514c94caaca0a4ef6e8f1ad4491cbce57fd2a15be48b83b4c85b90",
    "ACTUAL_CURRENT_COMMERCIAL_TARGET_UNCHANGED");
  const state=w.state,helper=state.helper;
  need(state.actual_command_returncode===0&&state.actual_instrumentation_finish_code===-1&&state.held_transport_returned_after_post_guard===true&&
    state.wire_sha256===c.state_wire_sha256&&typeof state.recorder_command_result_sha256==="string"&&/^[0-9a-f]{64}$/.test(state.recorder_command_result_sha256)&&
    helper.protocol==="pocket4-owned-ihg-qa-v2"&&helper.op==="state"&&helper.nonce===inputs.nonces.state&&helper.self_uid===uid&&
    helper.ok===true&&helper.error===null&&same(helper.secondary_errors,[])&&helper.ui_automation_connected===false,"ACTUAL_NO_AUTOMATION_STATE");
  need(state.wire_sha256===h.sha(lossless.losslessCanonical(lossless.nodeField(docs.worker.nodes,["state","helper"]))),"ACTUAL_STATE_WIRE_HASH");
  const templateFiles=input.templates;
  const expectedTemplates={
    "owned_inspect.py":{bytes:42321,sha256:"8a28dc090b19d26c529f4fd0540f5651799aeebff877e9047a5fad207e073999"},
    "ihg_task_context.py":{bytes:18829,sha256:"2633ca62059d3db5c37c9ece28ac273297048d3e4681a1252ef00f1c200544ca"},
    "public_destination.py":{bytes:32045,sha256:"d4d35f9729f4a4a8d0cef0f7ac4712630a00570e6e0d988713939aacd716e932"},
    "stage_execute.py":{bytes:4981,sha256:"0094cc48bc8d028268ebab37a22018fe3554f494b2d6b7fc7674da9a647943db"}};
  need(same(Object.keys(templateFiles).sort(),Object.keys(expectedTemplates).sort()),"FOUR_IHG_CURRENT_TEMPLATES");
  for(const[n,p]of Object.entries(expectedTemplates))need(same(pin(templateFiles[n]),p),"CURRENT_TEMPLATE_PIN:"+n);
  const result={...templateFiles},edits=[];
  const edit=(file,a,b)=>{need(result[file].split(a).length===2,"ACTUAL_BIND_ANCHOR:"+file+":"+a);result[file]=result[file].replace(a,b);edits.push({file,old:a,next:b,count:1});};
  const nav="owned_inspect.py";
  edit(nav,"HELPER_UID=None","HELPER_UID="+uid);
  edit("ihg_task_context.py","HELPER_UID=None","HELPER_UID="+uid);
  edit(nav,"STATE_NONCE=None","STATE_NONCE="+JSON.stringify(inputs.nonces.state));
  edit(nav,"STATE_WIRE=None","STATE_WIRE="+JSON.stringify(state.wire_sha256));
  edit(nav,"INSTALLED=None","INSTALLED="+lossless.losslessPython(installed));
  const rel={coordinator:"result.json",stage:"stage-result.json",worker:"worker/result.json"};
  edit(nav,"PRIOR=None","PRIOR={"+Object.keys(rel).map(k=>JSON.stringify(k)+":("+JSON.stringify(rel[k])+","+input.actual[k].pin.bytes+","+JSON.stringify(input.actual[k].pin.sha256)+")").join(",")+"}");
  let inverse={...result};for(const e of [...edits].reverse()){need(inverse[e.file].split(e.next).length===2,"ACTUAL_BIND_INVERSE");inverse[e.file]=inverse[e.file].replace(e.next,e.old);}
  need(Object.keys(templateFiles).every(n=>templateFiles[n]===inverse[n]),"ACTUAL_BINDING_ONLY_SOURCE_CHANGE");
  return {files:result,edits,actual_binding:{job_id:input.install_job_id,UID:uid,source_manifest_sha256:isha,
      helper_package:self,protocol:helper.protocol,prior_receipts:Object.fromEntries(Object.keys(rel).map(k=>[k,{path:root+"/"+rel[k],...input.actual[k].pin}])),
      state_nonce:inputs.nonces.state,state_wire_sha256:state.wire_sha256,recorder_command_result_sha256:state.recorder_command_result_sha256,
      current_host_manifest_sha256:hostSHA,current_baseline:binding,seven_Main_maps_match:true,
      commands:13,source_controls:38,install_retired:true,
      installed_identity_lossless_json:lossless.losslessCanonical(installed),
      target_identity_lossless_json:lossless.losslessCanonical(before),
      build_proof_lossless_json:lossless.losslessCanonical(lossless.nodeField(docs.worker.nodes,["build"])),
      installed_mtime_ns:lossless.nodeField(installed,["held_file","mtime_ns"]).raw,
      actual_no_automation_state:true,whole_process_tree_cleanup_qualified:false},
    UI_nonce_pool_bound:false,UI_request_created:false,Python_controls_performed:false};
}