function qualifyBiliR10Install(h, ll, input) {
 const need=(v,c)=>{if(!v)throw Error(c)},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 function canonical(v){return v===null?"null":Array.isArray(v)?"["+v.map(canonical).join(",")+"]":typeof v==="object"?"{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canonical(v[k])).join(",")+"}":JSON.stringify(v);}
 const same=(a,b)=>canonical(a)===canonical(b);
 function checked(name){const row=input.originals[name],p=input.expected[name];need(row&&p&&same(pin(row.raw),p),"EXACT_ORIGINAL_PIN:"+name);return JSON.parse(row.raw);}
 const c=checked("coordinator"),s=checked("stage"),w=checked("worker"),cmd=checked("worker_command"),sc=checked("state_command");
 checked("worker_stdout");
 need(same(Object.keys(input.originals).sort(),["coordinator","stage","state_command","worker","worker_command","worker_stdout"]),"EXACT_SIX_ORIGINALS");
 const i=input.install,isrc=i.files,manifest=JSON.parse(isrc["SOURCE_PINS.json"]),im=h.sha(isrc["SOURCE_PINS.json"]);
 need(im===i.manifest_sha256&&im==="e3cb2adbcfe46a47ca81ec3b5883f1e1a0cd806b21e964d75944e8fe5cd49387","ACTUAL_INSTALL02_SOURCE_AUTHORITY");
 for(const[n,p]of Object.entries(manifest.files))need(same(pin(isrc[n]),p),"EXACT_INSTALL_SOURCE:"+n);
 const host=JSON.parse(isrc["host/source-manifest.json"]),hostSha=h.sha(isrc["host/source-manifest.json"]),hostActual=JSON.parse(isrc["host-stage-actual.json"]),scope=host.current_baseline;
 need(host.revision===6&&host.schema===2&&hostSha===i.inputs.current_host_source_manifest_sha256&&Object.keys(host.files).length===14&&same(pin(isrc["host-stage-actual.json"]),i.inputs.current_host_stage),"R6_ORIGINAL_SOURCE_AND_ACTUAL_REQUIRED");
 need(hostActual.ok===true&&hostActual.error===null&&same(hostActual.secondary_errors,[])&&hostActual.source_manifest_sha256===hostSha&&same(hostActual.Main_before,hostActual.Main_after)&&same(hostActual.Main_before,hostActual.Main_final),"R6_ACTUAL_MAIN_AUTHORITY");
 const root="/home/alex/work/pocket4-owned-bili-qa-r10-install-state-02",flow="/home/alex/work/pocket4-bilibili-owned-qa-r10-flow-"+i.inputs.nonces.flow,step=flow+"/steps/install-state-r10-02";
 const paths={coordinator:root+"/result.json",stage:root+"/stage-result.json",worker:step+"/result.json",worker_command:root+"/evidence/02-install-state.result.json",state_command:step+"/command-006.result.json",worker_stdout:root+"/evidence/02-install-state.stdout"};
 need(i.root===root&&c.flow===flow&&c.nonce===s.nonce&&c.nonce===w.nonce&&w.nonce===i.inputs.nonces.flow&&w.state_nonce===i.inputs.nonces.state,"EXACT_ACTUAL02_FLOW_AND_NONCES");
 need([c,s,w].every(r=>r.ok===true&&r.error===null&&same(r.secondary_errors,[]))&&s.coordinator_returncode===0&&c.source_manifest_sha256===im&&s.source_manifest_sha256===im&&s.packet_sha256===h.sha(i.stdin)&&s.source_unchanged===true&&c.source_and_artifact_unchanged===true,"INSTALL02_COMPLETION_AND_PACKET");
 need(same(s.coordinator_result,{path:paths.coordinator,...input.expected.coordinator})&&same(c.worker_result,{path:paths.worker,...input.expected.worker}),"EXACT_ACTUAL02_PARENT_CHAIN");
 const main=hostActual.Main_before;
 need([c.Main_before,c.Main_after,s.Main_before,s.Main_after,cmd.Main_after].every(x=>same(x,main))&&cmd.Main_before===true,"FIVE_FULL_MAIN_MAPS_AND_COMMAND_BOOLEAN");
 need(main.schema==="pocket4-current-main-guard-v2"&&main.current_baseline_sha256===scope.baseline_sha256&&main.current_baseline_qualification_sha256===scope.qualification_sha256&&main.Main_epoch_sha256===scope.epoch_sha256&&main.authenticated_owner_chain_matches===true&&main.current_user_namespaces_match===true&&main.production_ready===false&&main.old_helpers_and_tasks_reauthorized===false,"EXACT_TYPED_CURRENT_BASELINE02");
 need(s.controls.all_passed===true&&s.controls.count===37&&s.controls.cases.length===37&&new Set(s.controls.cases.map(x=>x.name)).size===37&&s.controls.cases.every(x=>x.passed===true)&&s.controls.new_owner_discovery_controls===18&&s.private_current_recorder_r6.private_copy_verified===true&&s.private_current_recorder_r6.files===14&&s.private_current_recorder_r6.all_runtime_bytes_equal_qualified_host===true&&s.private_current_recorder_r6.current_host_manifest_sha256===hostSha,"ACTUAL_37_AND_R6_COPY");
 need(cmd.spawned===true&&cmd.joined===true&&cmd.returncode===0&&cmd.timed_out===false&&same(cmd.secondary_errors,[])&&cmd.name==="02-install-state"&&cmd.stderr.bytes===0&&cmd.stderr.sha256===h.sha("")&&same(cmd.argv,["/usr/bin/python3","-I","-B",root+"/source/install_state.py","--worker-once","--source-manifest-sha256",im]),"EXACT_JOINED_WORKER_COMMAND");
 need(same(cmd.stdout,input.expected.worker_stdout)&&ll.losslessCanonical(ll.losslessJsonNodes(input.originals.worker.raw))===ll.losslessCanonical(ll.losslessJsonNodes(input.originals.worker_stdout.raw)),"EXACT_PRINTED_WORKER_RAW_AND_LOSSLESS_SEMANTICS");
 const uid=w.owned_package_uid,self="org.droidloom.qa.bili.r10";
 need(Number.isInteger(uid)&&uid>=10000&&uid<100000&&![10117,10125,10164,10165,10166,10169,10170,10175,10184,10202,10204,10152].includes(uid)&&c.owned_package_uid===uid&&w.package===self&&c.package===self&&w.package_retained===true&&c.owned_package_retained_for_separate_UI_admission===true,"ACTUAL_R10_UID");
 need(w.install_attempted===true&&w.install_success_observed===true&&w.state_attempted===true&&w.action_attempted===true&&w.outcome_unknown===false&&w.possible_owned_package_retained===false&&w.final_Main_guard_passed===true&&w.held_binding_released===true&&w.action_lock_released===true,"INSTALL_AND_RELEASE_FACTS");
 need(w.UI_actions===0&&w.audio_actions===0&&w.UiAutomation_connection_requested===false&&w.permission_grants===0&&w.old_v2_helper_called===false&&w.automatic_retry===false&&w.whole_app_production_ready===false&&c.whole_app_production_ready===false&&s.whole_app_production_ready===false,"INSTALL_ONLY_NO_UI_QUALIFICATION");
 need(w.staging_cleanup.staged_apk_removed===true&&w.staging_cleanup.staged_directory_removed===true&&w.staging_cleanup.authority_fds_closed===true&&w.staging_cleanup.recursive_cleanup===false,"EXACT_STAGING_CLOSED");
 need(w.runtime_recorder_manifest_sha256===hostSha&&w.runtime_session_binding_sha256===h.sha(isrc["session_binding.py"])&&w.build.source_manifest_sha256===i.inputs.qa_source_manifest_sha256&&same(w.build.APK,i.inputs.APK)&&w.build.signer_certificate_sha256===i.inputs.signer_certificate_sha256&&w.build.build_receipt_sha256===i.inputs.build.sha256&&w.build.stage_receipt_sha256===i.inputs.build_stage.sha256&&w.build.self_instrumentation===true&&w.build.old_v2_provenance_inherited===false,"EXACT_ACTUAL_HELPER_BUILD");
 const nodes=ll.losslessJsonNodes(input.originals.worker.raw),installed=ll.nodeField(nodes,["installed_before_state"]),after=ll.nodeField(nodes,["installed_after_state"]);
 need(ll.losslessCanonical(installed)===ll.losslessCanonical(after),"INSTALLED_IDENTITY_LOSSLESS_EQUAL");
 const a=w.installed_before_state;
 need(a.package===self&&a.uid===uid&&a.apk_sha256===i.inputs.APK.sha256&&a.bytes===i.inputs.APK.bytes&&a.signer_bound_by_exact_signed_apk_bytes===i.inputs.signer_certificate_sha256&&a.base_apk.startsWith("/data/app/")&&a.base_apk.includes("/"+self+"-")&&a.base_apk.endsWith("/base.apk")&&a.held_file.nlink===1&&a.held_file.bytes===i.inputs.APK.bytes&&a.held_file.uid===1000&&a.held_file.gid===1000,"EXACT_INSTALLED_PACKAGE_FILE");
 const prev=w.state,b=prev.helper;
 need(sc.owned_command_joined===true&&sc.spawned===true&&sc.returncode===0&&sc.timed_out===false&&sc.error===null&&same(sc.errors,[])&&sc.action_attempted===false&&sc.automatic_retry===false&&sc.stdout_sha256===prev.stdout_sha256&&sc.stderr_sha256===prev.stderr_sha256&&sc.stderr_sha256===h.sha("")&&input.expected.state_command.sha256===prev.recorder_command_result_sha256,"EXACT_STATE006_METADATA");
 need(prev.actual_command_returncode===0&&prev.actual_instrumentation_finish_code===-1&&prev.held_transport_returned_after_post_guard===true&&prev.command_join_and_epoch_guards_must_be_bound_separately===true&&prev.wire_sha256===c.state_wire_sha256&&b.protocol==="pocket4-owned-bili-qa-v10"&&b.nonce===w.state_nonce&&b.self_uid===uid&&b.op==="state"&&b.ok===true&&b.error===null&&same(b.secondary_errors,[])&&b.action_attempted===false&&b.outcome_unknown===false&&b.helper_work_completed===true&&b.claim_persistence_completed===true&&b.ui_automation_connected===false&&b.requires_post_termination_state_check===false&&b.business_success_verified===false,"ACTUAL_NO_AUTOMATION_STATE");
 need(i.inputs.ordered_worker_Android_commands===9&&w.absence.command.command==="command-001"&&w.install_command.command==="command-002"&&w.uid_command.command==="command-003"&&w.all_users_after.command==="command-009","ORIGINAL_NINE_COMMAND_PATH_AND_LAST009");
 need(w.action_lock_admission.phase==="acquired"&&w.action_lock_admission.acquired===true&&w.action_lock_admission.same_inode_confirmed===true&&w.action_lock_admission.wait_limit_seconds===5,"ORIGINAL_EXACT_ACTION_LOCK");
 for(const field of ["memory.events","memory.swap.current","memory.swap.peak","memory.swap.max"]) {
   const val=c.owned_after[field];need(typeof val==="string","OWNED_RESOURCE_FIELD");
   if(field==="memory.events")need(val.trim().split("\n").every(x=>/^[a-z_]+ 0$/.test(x)),"OWNED_MEMORY_EVENT");
   else need(val==="0","OWNED_SWAP");
 }
 need(c.owned_before.path===c.owned_after.path&&c.owned_after["memory.max"]==="536870912"&&c.owned_after["pids.max"]==="128","OWNED_RESOURCE_IDENTITY");
 return {schema:"pocket4-bili-r10-install02-independent-qualification-v1",ok:true,actual_UID:uid,
  installed_identity_python:ll.losslessPython(installed),installed_identity_lossless_json:ll.losslessCanonical(installed),
  actual_mtime_ns:ll.nodeField(installed,["held_file","mtime_ns"]).raw,
  actual_install_job:input.install_job_id,install_root:root,flow_root:flow,step_root:step,paths,
  records:input.expected,source_manifest_sha256:im,packet_sha256:s.packet_sha256,
  host_manifest_sha256:hostSha,session_binding_sha256:w.runtime_session_binding_sha256,
  state_command_index:6,state_command_sha256:input.expected.state_command.sha256,state_wire_sha256:prev.wire_sha256,
  state_nonce:w.state_nonce,build:w.build,Main:main,controls:37,source_command_path:9,
  last_actual_command:"command-009",all_nine_command_originals_independently_collected:false,
  exact_collected_state_and_outer_commands_joined:true,complete_worker_route_succeeded:true,
  whole_process_tree_cleanup_qualified:false,commercial_APK_full_acceptance_pending_fresh_flow:true,
  no_UI_during_install:true,whole_app_production_ready:false,old_tasks_reauthorized:false};
}
