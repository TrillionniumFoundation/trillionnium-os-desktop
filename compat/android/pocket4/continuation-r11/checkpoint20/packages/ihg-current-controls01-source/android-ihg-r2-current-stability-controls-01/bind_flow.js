function bindIhgCurrentFlow(h,lossless,input){
  const need=(v,m)=>{if(!v)throw Error(m)};
  function canonical(v){return v===null?"null":Array.isArray(v)?"["+v.map(canonical).join(",")+"]":typeof v==="object"?"{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canonical(v[k])).join(",")+"}":JSON.stringify(v);}
  const same=(a,b)=>canonical(a)===canonical(b),pin=raw=>({bytes:h.utf8(raw).length,sha256:h.sha(raw)});
  const q=input.qualified,controls=input.controls,spec=input.nonce_spec;
  need(q&&q.actual_binding&&q.actual_binding.install_retired===true&&Number.isInteger(q.actual_binding.UID)&&
    q.actual_binding.source_manifest_sha256==="e8cf9d4c04025bb092663519a01624fa40e552600dc5643a50ebf9bace915103"&&
    q.UI_request_created===false&&q.UI_nonce_pool_bound===false,"QUALIFIED_ACTUAL_IHG_INSTALL02_REQUIRED");
  need(typeof input.control_actual?.raw==="string"&&same(pin(input.control_actual.raw),input.control_actual.pin)&&
    /^[a-z0-9-]+$/.test(input.control_job_id),"ACTUAL_PURE_CONTROL_PIN_AND_JOB");
  const out=JSON.parse(input.control_actual.raw);
  need(controls.planned_controls===106&&out.schema===1&&out.ok===true&&
    out.state==="IHG_CURRENT_TYPED_BOUNDED_SEARCH_READINESS_PURE_CONTROLS_PASS"&&
    out.control_count===106&&out.controls.length===106&&out.controls.every(x=>x.passed===true)&&
    new Set(out.controls.map(x=>x.case)).size===106&&
    out.control_stdin_sha256===h.sha(controls.raw)&&same(out.template_source_pins,controls.pins),"EXACT_SUCCESSFUL_106_CONTROLS");
  need(out.all_template_and_bound_python_compile===true&&out.synthetic_in_memory_IO_only===true&&
    out.original_Session_sequence_and_real_contract_summary_and_policy_executed===true&&
    out.production_Flow_and_BoundArun_constructors_executed===true&&out.production_typed_constructor_controls===17&&
    out.file_writes===0&&out.Android_actions===0&&out.device_or_child_process_commands===0&&
    out.real_Java_helper_executed===false&&out.actual_Main_and_target_callbacks===false&&out.live_Main_identity_validated===false&&
    out.actual_UI_readiness_verified===false&&out.runtime_flow_dispatched===false&&out.whole_app_production_ready===false,
    "PURE_CONTROL_SCOPE_NOT_RUNTIME_AUTHORITY");
  const fresh=out.fresh_nonce_values;
  need(spec.count===36&&spec.exclude_count===337&&spec.labels.length===36&&spec.slot_mapping.length===36&&
    spec.exclude_values.length===337&&new Set(spec.exclude_values).size===337&&out.nonce_exclusion_count===337&&
    out.nonce_values_disjoint_all_fixed_prior_literals===true&&Array.isArray(fresh)&&fresh.length===36&&
    new Set(fresh).size===36&&fresh.every(v=>typeof v==="string"&&/^[0-9a-f]{32}$/.test(v)&&!spec.exclude_values.includes(v)),
    "ACTUAL_DISTINCT_NEW_36_NONCES");
  const names={contract:input.helper_files["qa_contract.py"],adapter:input.helper_files["qa_adapter.py"],
    public_destination:q.files["public_destination.py"],context:q.files["ihg_task_context.py"],
    coordinator:q.files["owned_inspect.py"],stage:q.files["stage_execute.py"],transport:input.transport_source};
  need(Object.keys(names).every(k=>names[k]===controls.payload[k])&&
    same(controls.payload.nonce_slots,spec.slot_mapping.map(x=>x.slot))&&same(controls.payload.nonce_exclusions,spec.exclude_values),
    "EXACT_CONTROL_PAYLOAD_TO_RUNTIME_TEMPLATES");
  const bound={},nonce_edits=[];
  for(const[name,source]of Object.entries(names)){
    let text=source;
    for(let i=0;i<spec.slot_mapping.length;i++){
      const slot=spec.slot_mapping[i].slot,n=text.split(slot).length-1;
      if(n){text=text.split(slot).join(fresh[i]);nonce_edits.push({source:name,slot,value:fresh[i],count:n});}
    }
    need(!spec.slot_mapping.some(row=>text.includes(row.slot)),"UNBOUND_NONCE_SLOT");
    need(same(pin(text),out.bound_source_pins[name]),"ACTUAL_BOUND_SOURCE_PIN:"+name);
    bound[name]=text;
  }
  need(Object.keys(out.bound_source_pins).length===7&&out.bound_coordinator_sha256===h.sha(bound.coordinator)&&
    out.bound_stage_sha256===h.sha(bound.stage)&&out.maximum_readiness_sequences===8&&
    out.readiness_qualification_seconds===20&&out.minimum_consecutive_samples===3&&out.minimum_capture_span_ms===4000&&
    out.success_durable_commands_formula==="37+9*k; 3<=k<=8"&&out.maximum_success_durable_commands===109&&
    out.maximum_helper_nonces===35&&out.maximum_click_actions===2,"ACTUAL_BOUND_CONTROL_AND_BUDGET");
  const oldQ=JSON.parse(input.old_request.raw);
  need(same(pin(input.old_request.raw),input.old_request.pin)&&same(input.old_request.pin,
    {bytes:103133,sha256:"ab51c1ae3dc4652c424c6b3a222dc44c84f79371fede77559e305a06ba8e834c"}),"EXACT_ORIGINAL_IHG_UI_ENVELOPE");
  const nonceMap=Object.fromEntries(spec.labels.map((name,i)=>[name,fresh[i]])),abi=q.actual_binding;
  const plan=(role,op)=>({schema:1,operation:op,...(op==="click"?{selector:{text:role==="search"?"Search":"Destination"}}:{}),
    nonces:Object.fromEntries((op==="click"?["before","inspect","action","after"]:["before","inspect","after"]).map(k=>[k,nonceMap[role+"."+k]]))});
  const search=plan("search","click"),destination=plan("destination","click"),post=plan("post","inspect"),
    readiness=Array.from({length:8},(_,i)=>plan("readiness."+(i+1),"inspect"));
  const resolver_records={worker:{relative_path:"result.json",bytes:8878,sha256:"153ddbfc8393570621b64a478675c2a0180826a7a6ecada0ade8a6aa4ed79722"},
    stage:{relative_path:"stage-result.json",bytes:1583,sha256:"72224eae94c82a258b1a49d5730363f5e3c62cd8db769f083d5b5ec149dd55a8"}};
  const fields={
    schema:2,state:"ACTUAL_CURRENT_IHG_R2_INSTALL_AND_106_CONTROLS_BOUND_FRESH_FLOW_UNRUN",
    nonce:nonceMap.flow,component:"com.ihg.apps.android/.activity.MainActivity",
    helper_uid:abi.UID,helper_package:abi.helper_package,helper_protocol:abi.protocol,
    current_host_manifest_sha256:abi.current_host_manifest_sha256,current_baseline:abi.current_baseline,
    actual_install_job:abi.job_id,actual_install_receipts:abi.prior_receipts,
    actual_install_source_manifest_sha256:abi.source_manifest_sha256,
    state_nonce:abi.state_nonce,state_wire_sha256:abi.state_wire_sha256,
    state_recorder_command_result_sha256:abi.recorder_command_result_sha256,
    actual_fresh_nonce_source:{job_id:input.control_job_id,...input.control_actual.pin,generator:"secrets.token_hex(16)",
      order:spec.labels,values:fresh,excluded_values:337},
    actual_source_controls:{job_id:input.control_job_id,...input.control_actual.pin,count:106,
      control_stdin_sha256:h.sha(controls.raw),control_source:controls.source_pin,
      production_Flow_BoundArun_and_Session_constructors:true,synthetic_IO_only:true},
    resolver_records,
    historical_resolution_not_launch_authority:true,new_prelaunch_resolution_required:true,
    explicit_search_click_plan:search,public_destination_click_plan:destination,independent_post_plan:post,
    search_readiness_plans:readiness,
    exact_success_budgets:{phase_seconds:{launch:175,inspect:175,cleanup:115},inspect_worker_seconds:190,
      launch_durable_commands:12,cleanup_durable_commands:11,inspection_durable_commands_formula:"37+9*k; 3<=k<=8",
      maximum_inspection_durable_commands:109,maximum_private_foreground_observations:33,
      maximum_helper_nonces:35,total_nonces:36,request_seconds:600,
      maximum_counts:{target_uid:2,target_path:2,helper_uid:24,helper_path:24,stacks:22,foreground:33,instrument:35,click:2}},
    readiness:{complete_restored_inspections:8,qualification_seconds:20,minimum_consecutive_equal:3,
      minimum_capture_span_ms:4000,connection_scoped_window_id_compared_across_invocations:false,
      future_stability_proven:false,failed_or_partial_or_unknown_observation_retried:false,
      fresh_Search_inspection_must_equal_last_qualified_identity:true},
    historical_previous_failure:{job_id:"1a1af242a07-fc05-6624",
      inspect:{bytes:46612,sha256:"c0bfd55014992ef2a443154eb0b66d74d1664648d3422f876c2c830190f65aec",
        git_blob:"f8b25883ff04995ba1f5fc715f415896eb65a16e"},
      error:"FOCUS_CHANGED_BEFORE_ACTION",compound_guard:true,action_target_nodes:64,action_final_nodes:63,
      physical_focus_change_not_inferred:true,helper_action_attempted:false,helper_outcome_unknown:false,
      flow_action_attempted:true,flow_outcome_unknown:true,historical_failure_not_reclassified:true,
      failed_or_unknown_click_not_replayed:true,Destination_started:false},
    original_full_tree_window_node_refresh_final_guards_preserved:true,
    all_UI_input_requires_current_complete_semantic_selection:true,
    first_sequence_failure_or_unqualified_ACK_stops_destination:true,
    independent_final_post_read_always_attempted:true,
    public_destination_maximum_ancestor_levels:6,maximum_public_clicks:2,
    input_text_supported:false,business_success_verified:false,hotel_search_results_verified:false,
    login_or_booking_verified:false,shared_helper_whole_process_tree_cleanup_qualified:false,
    target_signer_independently_verified:false,framework_exit_cause_resolved:false,
    old_successful_click_outcome_unknown_preserved:true,automatic_retry:false,
    UI_request_dispatched:false,whole_app_production_ready:false
  };
  const raws=Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,canonical(v)]));
  raws.installed_helper=abi.installed_identity_lossless_json;
  raws.actual_target=abi.target_identity_lossless_json;
  raws.actual_build=abi.build_proof_lossless_json;
  for(const key of ["installed_helper","actual_target","actual_build"])lossless.losslessJsonNodes(raws[key]);
  const inputsRaw="{"+Object.keys(raws).sort().map(k=>JSON.stringify(k)+":"+raws[k]).join(",")+"}\n";
  need(lossless.losslessCanonical(lossless.nodeField(lossless.losslessJsonNodes(inputsRaw),["installed_helper"]))===
    abi.installed_identity_lossless_json,"LOSSLESS_INSTALLED_INPUT_IDENTITY");
  const files={"owned_inspect.py":bound.coordinator,"ihg_task_context.py":bound.context,
    "public_destination.py":bound.public_destination,"INPUTS.json":inputsRaw};
  const manifest={schema:1,files:Object.fromEntries(Object.entries(files).sort().map(([k,v])=>[k,pin(v)]))};
  files["SOURCE_PINS.json"]=canonical(manifest)+"\n";
  const manifestSHA=h.sha(files["SOURCE_PINS.json"]),packet={schema:1,nonce:nonceMap.flow,files},wire=canonical(packet)+"\n";
  need(h.utf8(wire).length<=131072&&Object.values(files).every(v=>h.utf8(v).length<=65536)&&
    Object.values(files).reduce((n,v)=>n+h.utf8(v).length,0)<=131072,"ORIGINAL_UI_PACKET_AND_SOURCE_BOUNDS");
  const wrapper="import hashlib,json,sys;raw=sys.stdin.buffer.read(131073);assert len(raw)=="+h.utf8(wire).length+
    " and hashlib.sha256(raw).hexdigest()=='"+h.sha(wire)+"';stage="+JSON.stringify(bound.stage)+
    ";assert hashlib.sha256(stage.encode()).hexdigest()=='"+h.sha(bound.stage)+
    "';scope={\"__name__\":\"amazon_fixed_task_stage\",\"__file__\":\"<verified-amazon-task-stage>\"};"+
    "exec(compile(stage,\"stage_execute.py\",\"exec\"),scope);raise SystemExit(scope[\"main\"](json.loads(raw),'"+manifestSHA+"'))";
  const request={...oldQ,args:["-n","/usr/bin/python3","-I","-c",wrapper],stdin:wire,
    idempotency_key:"pocket4-ihg-r2-current-search-destination-entry01-20261106"};
  return {files,stage_source:bound.stage,request,manifest_sha256:manifestSHA,nonce_edits,inputs_raw:inputsRaw,
    proof:{actual_install_and_control_pins_bound:true,actual_helper_UID:abi.UID,
      actual_mtime_ns:abi.installed_mtime_ns,actual_new_nonce_count:36,old_337_nonces_excluded:true,
      original_UI_envelope_resource_limits:true,original_131072_stdin_limit:true,
      packet:pin(wire),runtime_inputs_lossless:true,all_seven_actual_bound_source_pins_match:true,
      original_business_source_unchanged_except_current_scope_and_nonce_binding:true,
      source_functions_not_rewritten_by_final_binder:true,UI_dispatched:false,whole_app_production_ready:false}};
}