function bindCell02LondonSources(template,material,expected,install,helper,host,hostActual,h,ll){
 const need=(x,m)=>{if(!x)throw Error(m);};
 const pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 const stable=x=>Array.isArray(x)?'['+x.map(stable).join(',')+']':x!==null&&typeof x==='object'?'{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+stable(x[k])).join(',')+'}':JSON.stringify(x);
 const eq=(a,b)=>stable(a)===stable(b);
 const kinds=['coordinator','stage','worker','state_command','worker_command','worker_stdout'];
 need(template.schema==='pocket4-ihg-r4-cell02-London-template-v1'&&template.complete_inverse_exact===true&&
  template.owner_discovery_revision===2&&template.owner_complete_inverse_exact===true&&
  template.actual_install_source_manifest===install.manifest_sha256&&template.helper_manifest_sha256===helper.manifestSha&&
  template.host_manifest_sha256===host.manifest_sha256,'EXACT_CURRENT_TEMPLATE_CLOSURE');
 for(const [name,raw]of Object.entries(template.sources))need(eq(pin(raw),template.source_pins[name]),'EXACT_CURRENT_TEMPLATE:'+name);
 need(eq(Object.keys(material.install).sort(),[...kinds].sort())&&eq(Object.keys(expected.install_pins).sort(),[...kinds].sort()),'SIX_EXACT_INSTALL_ORIGINALS');
 const roots={},obj={};for(const key of kinds){
  const raw=material.install[key],p=expected.install_pins[key];
  need(typeof raw==='string'&&p&&eq(pin(raw),{bytes:p.bytes,sha256:p.sha256})&&h.git(raw)===p.git_blob,'EXACT_INSTALL_ORIGINAL:'+key);
  roots[key]=ll.losslessJsonNodes(raw);obj[key]=JSON.parse(raw);
 }
 const canon=(key,path)=>ll.losslessCanonical(ll.nodeField(roots[key],path));
 const c=obj.coordinator,s=obj.stage,w=obj.worker,cmd=obj.worker_command,scmd=obj.state_command;
 const ipins=Object.fromEntries(kinds.map(k=>[k,{bytes:expected.install_pins[k].bytes,sha256:expected.install_pins[k].sha256}]));
 const installRoot='/home/alex/work/pocket4-owned-ihg-qa-r4-install-state-02';
 const row=(key,path)=>({path:installRoot+'/'+path,...ipins[key]});
 for(const [name,v]of Object.entries({coordinator:c,stage:s,worker:w})){
  need(v.ok===true&&v.error===null&&Array.isArray(v.secondary_errors)&&v.secondary_errors.length===0,'ACTUAL_INSTALL_PASS:'+name);
  need(v.source_manifest_sha256===install.manifest_sha256,'ACTUAL_INSTALL_SOURCE:'+name);
  need(v.nonce===install.inputs.nonces.flow,'ACTUAL_INSTALL_NONCE:'+name);
 }
 need(eq(c.worker_result,row('worker','worker/result.json'))&&eq(s.coordinator_result,row('coordinator','result.json')),'EXACT_INSTALL_PARENT_CHAIN');
 need(c.install_state_worker_requested===true&&c.source_and_artifact_unchanged===true&&s.source_unchanged===true&&
  s.shared_current_host_source_verified===true&&s.current_host_manifest_sha256===host.manifest_sha256&&s.coordinator_returncode===0,'COMPLETED_CURRENT_SOURCE_INSTALL');
 const ctrl=s.controls;
 need(ctrl.schema==='pocket4-current-app-install-context-controls-v1'&&ctrl.count===69&&ctrl.all_passed===true&&
  Array.isArray(ctrl.cases)&&ctrl.cases.length===69&&new Set(ctrl.cases.map(x=>x.name)).size===69&&ctrl.cases.every(x=>x.passed===true)&&
  ctrl.new_owner_discovery_controls===18&&ctrl.production_discovery_and_Context_route_used===true&&
  ctrl.legacy_discover_failure_reproduced_in_memory===true&&
  ctrl.actual_R6_reference_read_only===true&&ctrl.Android_commands===0&&ctrl.UI_actions===0&&ctrl.children===0&&ctrl.temporary_directories_removed===true,'ALL_CURRENT_69_INSTALL_CONTROLS');
 const uid=w.owned_package_uid;
 need(Number.isInteger(uid)&&uid>=10000&&uid<100000&&![10137,10196,10153,10156].includes(uid)&&
  c.owned_package_uid===uid&&w.state.helper.self_uid===uid&&w.installed_before_state.uid===uid&&
  w.installed_before_state.package===helper.binding.helper_package,'ACTUAL_NEW_HELPER_UID');
 need(canon('worker',['installed_before_state'])===canon('worker',['installed_after_state'])&&
  canon('worker',['target_before'])===canon('worker',['target_after']),'LOSSLESS_INSTALLED_AND_TARGET_UNCHANGED');
 need(ll.losslessCanonical(roots.worker)===ll.losslessCanonical(roots.worker_stdout),'EXACT_PRINTED_WORKER_SEMANTIC_EQUALITY');
 const main=canon('worker',['Main_before']),currentMain=stable(JSON.parse(hostActual.raw).Main_before);
 need(main===currentMain,'EXACT_COMPLETE_CURRENT_R6_MAIN_GUARD');
 for(const [key,fields]of Object.entries({worker:['Main_before_lock','Main_before','Main_after'],coordinator:['Main_before','Main_after'],stage:['Main_before','Main_after'],worker_command:['Main_after']}))
  for(const field of fields)need(canon(key,[field])===main,'FULL_MAIN_MAP:'+key+'.'+field);
 need(w.exact_command_count===13&&w.action_attempted===true&&w.outcome_unknown===false&&
  w.final_Main_guard_passed===true&&w.held_binding_released===true&&w.action_lock_released===true&&
  w.install_attempted===true&&w.install_success_observed===true&&w.state_attempted===true&&
  w.staging_cleanup.staged_apk_removed===true&&w.staging_cleanup.staged_directory_removed===true&&
  w.staging_cleanup.authority_fds_closed===true&&w.target_FD_cleanup.held_APK_FDs_closed===1&&
  w.target_FD_cleanup.commercial_files_changed===false&&w.UI_actions===0&&w.App_launches===0&&
  w.UiAutomation_connection_requested===false&&c.UI_actions===0&&c.App_launches===0&&s.UI_actions===0&&
  w.shared_helper.whole_process_tree_cleanup_qualified===false&&w.whole_app_production_ready===false,'CLOSED_INSTALL_ONLY_WITH_ORIGINAL_BOUNDARIES');
 need(w.runtime_shared_recorder_manifest_sha256===host.manifest_sha256&&
  w.runtime_ticket_context_sha256===h.sha(install.files['ihg_context.py'])&&
  w.runtime_ticket_transport_sha256===h.sha(install.files['ihg_transport.py']),'EXACT_CURRENT_RUNTIME_CLOSURE');
 need(eq(w.build.APK,install.inputs.APK)&&w.build.build_receipt_sha256===install.inputs.build.sha256&&
  w.build.stage_receipt_sha256===install.inputs.build_stage.sha256&&w.build.source_manifest_sha256===helper.manifestSha&&
  w.build.signer_certificate_sha256===install.inputs.signer_certificate_sha256&&w.build.self_instrumentation===true&&
  w.installed_before_state.apk_sha256===install.inputs.APK.sha256&&w.installed_before_state.bytes===install.inputs.APK.bytes&&
  w.installed_before_state.signer_bound_by_exact_signed_apk_bytes===install.inputs.signer_certificate_sha256,'EXACT_ACTUAL_SIGNED_BUILD_AND_INSTALLED_APK');
 need(w.state.helper.protocol===helper.binding.protocol&&w.state.helper.op==='state'&&w.state.helper.ok===true&&
  w.state.helper.error===null&&w.state.helper.secondary_errors.length===0&&w.state.helper.action_attempted===false&&
  w.state.helper.outcome_unknown===false&&w.state.helper.ui_automation_connected===false&&
  w.state.helper.nonce===install.inputs.nonces.state&&w.state_nonce===install.inputs.nonces.state&&
  /^[0-9a-f]{64}$/.test(w.state.wire_sha256)&&c.state_wire_sha256===w.state.wire_sha256&&
  w.state.actual_command_returncode===0&&w.state.actual_instrumentation_finish_code===-1&&
  w.state.held_transport_returned_after_post_guard===true,'EXACT_CURRENT_NO_AUTOMATION_STATE');
 need(w.state.recorder_command_result_sha256===ipins.state_command.sha256&&
  scmd.owned_command_joined===true&&scmd.spawned===true&&scmd.returncode===0&&scmd.timed_out===false&&
  scmd.error===null&&Array.isArray(scmd.errors)&&scmd.errors.length===0&&scmd.action_attempted===false&&
  scmd.stdout_sha256===w.state.stdout_sha256&&scmd.stderr_sha256===w.state.stderr_sha256,'EXACT_JOINED_STATE_COMMAND_CHAIN');
 need(cmd.Main_before===true&&cmd.joined===true&&cmd.spawned===true&&cmd.returncode===0&&cmd.timed_out===false&&
  Array.isArray(cmd.secondary_errors)&&cmd.secondary_errors.length===0&&
  eq(cmd.stdout,ipins.worker_stdout)&&cmd.stderr.bytes===0&&cmd.stderr.sha256===h.sha(''),'EXACT_JOINED_WORKER_STDOUT_CHAIN');
 need(typeof expected.install_job_id==='string'&&/^[0-9a-f-]+$/.test(expected.install_job_id),'ACTUAL_INSTALL_JOB_ID');
 const n=JSON.parse(material.nonce_raw),spec=JSON.parse(material.nonce_spec),excluded=JSON.parse(material.exclusions);
 for(const key of ['nonce_raw','nonce_spec','exclusions','generator']){
  const p=expected[key+'_pin'];need(p&&eq(pin(material[key]),{bytes:p.bytes,sha256:p.sha256}),'EXACT_MATERIAL:'+key);
  if(p.git_blob)need(h.git(material[key])===p.git_blob,'EXACT_MATERIAL_BLOB:'+key);
 }
 const literal=material.generator.match(/^EXCLUDED = (\[.*\])$/m),labelLiteral=material.generator.match(/^LABELS = (\[.*\])$/m);
 need(literal&&labelLiteral&&eq(JSON.parse(literal[1]),excluded)&&eq(JSON.parse(labelLiteral[1]),spec.labels),'EXACT_GENERATOR_LITERALS');
 need(Array.isArray(excluded)&&excluded.length>=659&&new Set(excluded).size===excluded.length&&
  excluded.every(v=>typeof v==='string'&&/^[0-9a-f]{32}$/.test(v))&&eq(excluded,[...excluded].sort())&&
  n.excluded_count===excluded.length&&h.sha(JSON.stringify(excluded)+'\n')===n.excluded_sha256&&
  spec.minimum_exclusions.length===659&&spec.minimum_exclusions.every(v=>excluded.includes(v)),'COMPLETE_GLOBAL_NONCE_EXCLUSIONS');
 need(n.generator==='secrets.token_hex(16)'&&n.no_redraw===true&&n.actual_helper_uid_bound===uid&&
  n.count===40&&eq(n.labels,spec.labels)&&n.labels.length===40&&new Set(n.labels).size===40&&
  n.values.length===40&&new Set(n.values).size===40&&n.values.every(v=>typeof v==='string'&&/^[0-9a-f]{32}$/.test(v)&&!excluded.includes(v)),'ACTUAL_FORTY_DISTINCT_CURRENT_NONCES');
 const bound={...template.sources},edits=[];
 function replace(file,from,to,why){need(bound[file].split(from).length===2,'EXACT_BINDING:'+file+':'+why);bound[file]=bound[file].replace(from,to);edits.push({file,from,to,why});}
 replace('coordinator','HELPER_UID=None  # Actual R4 install receipt required.','HELPER_UID='+uid,'actual-helper-UID');
 replace('context','HELPER_UID=None  # Await actual R4 installation receipt.','HELPER_UID='+uid,'actual-helper-UID');
 replace('coordinator','STATE_WIRE=None  # Actual R4 installation original required.','STATE_WIRE='+JSON.stringify(w.state.wire_sha256),'actual-state-wire');
 const installed=ll.losslessPython(ll.nodeField(roots.worker,['installed_before_state']));
 replace('coordinator','INSTALLED=None  # Actual R4 installation original required.','INSTALLED='+installed,'lossless-current-installed-identity');
 const prior={coordinator:['result.json',ipins.coordinator.bytes,ipins.coordinator.sha256],
  stage:['stage-result.json',ipins.stage.bytes,ipins.stage.sha256],worker:['worker/result.json',ipins.worker.bytes,ipins.worker.sha256]};
 const priorPy='{'+Object.entries(prior).map(([k,v])=>JSON.stringify(k)+':('+v.map(x=>JSON.stringify(x)).join(',')+')').join(',')+'}';
 replace('coordinator','PRIOR=None  # Actual R4 installation original required.','PRIOR='+priorPy,'exact-Python-tuple-parent-pins');
 for(let i=0;i<n.labels.length;i++){
  const hole='__FRESH_'+n.labels[i].toUpperCase().replaceAll('.','_')+'__';
  replace('coordinator',hole,n.values[i],'fresh-actual-nonce-'+n.labels[i]);
  if(n.labels[i]==='flow')replace('stage',hole,n.values[i],'fresh-actual-flow-nonce');
 }
 for(const [key,source]of Object.entries(bound))need(!source.includes('__FRESH_')&&h.utf8(source).length<=65536,'COMPLETE_BOUNDED_BOUND_SOURCE:'+key);
 const restored={...bound};for(const ed of [...edits].reverse()){need(restored[ed.file].split(ed.to).length===2,'EXACT_BINDING_INVERSE:'+ed.why);restored[ed.file]=restored[ed.file].replace(ed.to,ed.from);}
 need(Object.keys(restored).every(k=>restored[k]===template.sources[k]),'ALL_SEVEN_BINDING_INVERSE');
 const receipt={...expected.nonce_raw_pin,job_id:expected.nonce_job_id,count:40,excluded_count:excluded.length,
  excluded_sha256:n.excluded_sha256,generator:n.generator,no_redraw:true,actual_helper_uid:uid};
 return{sources:bound,source_pins:Object.fromEntries(Object.entries(bound).map(([k,v])=>[k,pin(v)])),
  edits,prior,installed_python:installed,nonce_receipt:receipt,fresh_nonces:n.values,nonce_exclusions:excluded,
  install_pins:ipins,install_expected:expected,actual_install_qualified:true,actual_install_job:expected.install_job_id,
  actual_helper_uid:uid,complete_binding_inverse:true,nonce_values_committed:true,UI_request_created:false,
  Python_controls_performed:false,main_guard_full_map_equal:true,all_eight_actual_Main_maps_equal:true,command_pre_Main_guard_completed_true:true};
}
