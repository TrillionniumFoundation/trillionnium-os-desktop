function bindCurrentOwnerAppTaskUI(h,lossless,input){
 const need=(v,m)=>{if(!v)throw Error(m)},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 function canonical(v){return v===null?"null":Array.isArray(v)?"["+v.map(canonical).join(",")+"]":typeof v==="object"?"{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canonical(v[k])).join(",")+"}":JSON.stringify(v);}
 const same=(a,b)=>canonical(a)===canonical(b);
 const app=input.app,amazon=app==="amazon",bb=app==="bestbuy";
 need(amazon||bb,"TWO_EXACT_APPS_ONLY");
 const controls=input.controls,t=input.bound;
 need(same(pin(input.old_nonce_spec_raw),{bytes:34670,sha256:"32f6f50390646e11a8c569a667ebf3799484c68efedc10a9917aa5c156b1e086"}),"EXACT_HISTORICAL_PLAN_NONCE_MAP");
 const originalMap=JSON.parse(input.old_nonce_spec_raw).mapping.filter(r=>r.app===app);
 const bound={...t,files:{"owned_inspect.py":t.sources.coordinator,[app+"_task_context.py"]:t.sources.context,
  [amazon?"search_navigation.py":"bestbuy_readiness.py"]:t.sources.business,"stage_execute.py":t.sources.stage},
  nonce_mapping:originalMap.map(r=>({label:r.local_label,old:r.old}))};
 const abi=bound.actual_binding,expectedCount=amazon?42:71,expectedUID=abi.UID;
 need(bound.app===app&&bound.template.complete_inverse_exact===true&&bound.template.owner_complete_inverse_exact===true&&
      bound.template.owner_discovery_revision===2&&bound.nonces_bound===true&&bound.complete_binding_inverse===true&&
      bound.nonce_excluded_count>=699&&Number.isInteger(expectedUID)&&expectedUID>=10000&&
      abi.install_retired===true&&abi.target_APK_count===3&&abi.source_controls===68&&abi.new_current_owner_discovery_controls===18&&
      abi.helper_package==="org.droidloom.qa."+app+".r4"&&abi.protocol==="pocket4-owned-"+app+"-qa-v4",
      "EXACT_ACTUAL_CURRENT_HELPER_AND_FRESH_SOURCE");
 need(typeof input.control_actual.raw==="string"&&same(pin(input.control_actual.raw),input.control_actual.pin)&&
      typeof input.control_job_id==="string"&&/^[a-z0-9-]+$/.test(input.control_job_id),"ACTUAL_CONTROL_RAW_PIN");
 const out=JSON.parse(input.control_actual.raw),names=out.cases?.map(x=>x[amazon?"name":"case"]);
 need(out.schema===1&&out.ok===true&&out.count===expectedCount&&controls.planned_controls===expectedCount&&
      Array.isArray(out.cases)&&out.cases.length===expectedCount&&out.cases.every(x=>x.passed===true)&&
      names.every(x=>typeof x==="string"&&x.length>0)&&new Set(names).size===expectedCount,
      "ACTUAL_EXACT_CONTROL_COUNT_AND_ALL_PASS");
 need(out.control_source_sha256===h.sha(controls.source)&&out.control_stdin_sha256===h.sha(controls.raw)&&
      same(out.bound_source_pins,controls.pins)&&same(out.nonce_actual,bound.nonce_actual)&&
      out.actual_helper_uid===expectedUID&&out.fresh_nonce_count===(amazon?32:10)&&
      out.current_cell02_generation_controls===9&&out.current_owner_task_route_controls===3&&
      out.actual_Main_and_target_callbacks===false&&out.real_Java_helper_executed===false&&
      out.UI_flow_dispatched===false&&out.whole_app_production_ready===false,
      "PURE_CONTROL_NOT_DEVICE_AUTHORITY");
 if(amazon)need(out.current_attribution_controls===9&&out.production_typed_constructor_controls===17&&
      out.production_scope_record_Flow_BoundArun_and_Session_executed===true&&
      out.production_actual_install_and_all_plan_validators_executed===true&&
      out.current_typed_source_exact_declared_inverse===true&&out.historical_failure_unknown_not_reclassified===true&&
      out.all_fixtures_in_memory===true&&out.file_writes===0&&out.child_processes===0&&
      out.Android_actions===0&&out.Main_accessed===false,"EXACT_AMAZON_PRODUCTION_CONTROL_REPORT");
 else need(out.production_typed_constructor_controls===17&&out.original_BestBuy_contract_functions_executed===true&&
      out.original_Session_sequence_executed_with_local_IO_subclass_only===true&&
      out.typed_context_declared_inverse_verified===true&&out.production_Flow_BoundArun_Session_constructors_executed===true&&
      out.production_actual_install_and_adapter_plan_validators_executed===true&&
      out.private_retained_assessment_or_raw_commercial_UI_read===false&&out.Android_Hepta_process_or_UI_calls===0&&
      out.remote_qualification_performed===false,"EXACT_BESTBUY_PRODUCTION_CONTROL_REPORT");
 const sourceMap={contract:input.helper_files["qa_contract.py"],adapter:input.helper_files["qa_adapter.py"],
      business:bound.files[amazon?"search_navigation.py":"bestbuy_readiness.py"],
      context:bound.files[app+"_task_context.py"],coordinator:bound.files["owned_inspect.py"],
      stage:bound.files["stage_execute.py"],transport:input.transport_source};
 need(Object.keys(out.bound_source_pins).length===7&&Object.entries(sourceMap).every(([k,s])=>
      s===controls.packet.payload.sources[k]&&same(pin(s),out.bound_source_pins[k])),
      "RUNTIME_SOURCE_BYTE_EQUAL_TO_ACTUAL_TESTED_SEVEN_SOURCES");
 const oldPin=amazon?{bytes:76588,sha256:"e58363cb444e19c481cf34e31d6aa36f1733ab759e545df93a00dfc2e3ce0cc5"}:
      {bytes:90181,sha256:"8526a376466a4a825b915e76a72ef38ce715207a0d767f029b7b2d6bc072df6f"};
 need(same(pin(input.old_request.raw),oldPin),"EXACT_ORIGINAL_UI_REQUEST");
 const oldQ=JSON.parse(input.old_request.raw),oldPacket=JSON.parse(oldQ.stdin),oldInputs=JSON.parse(oldPacket.files["INPUTS.json"]);
 need(oldQ.timeout_seconds===600&&oldQ.memory_max_bytes===536870912&&oldQ.host==="pocket4"&&
      oldQ.executable==="/usr/bin/sudo"&&same(oldQ.args.slice(0,4),["-n","/usr/bin/python3","-I","-c"]),
      "ORIGINAL_ROOT_SINGLE_UI_ENVELOPE");
 const map=bound.nonce_map,labels=amazon?["flow",...Array.from({length:8},(_,i)=>["before","inspect","after"].map(k=>"stability."+(i+1)+"."+k)).flat(),
      ...["before","inspect","action","after"].map(k=>"entry."+k),...["before","inspect","after"].map(k=>"post."+k)]:
      ["flow",...Array.from({length:3},(_,i)=>["before","inspect","after"].map(k=>"round."+(i+1)+"."+k)).flat()];
 need(same(Object.keys(map).sort(),[...labels].sort())&&same(labels.map(k=>map[k]),controls.packet.payload.fresh_nonce_values),
      "EXACT_ACTUAL_TESTED_NONCE_ORDER");
 const rebindPlan=plan=>{
      let raw=JSON.stringify(plan);
      for(const row of bound.nonce_mapping)raw=raw.split(row.old).join(map[row.label]);
      const result=JSON.parse(raw);return result;
 };
 const plan=amazon?rebindPlan(oldInputs.search_entry_plan):rebindPlan(oldInputs.read_only_inspection_plans);
 const expectedPlans=amazon?[...plan.stability,plan.entry,plan.post]:plan;
 const values=[map.flow,...expectedPlans.flatMap(p=>Object.values(p.nonces))];
 need(new Set(values).size===labels.length&&values.every(v=>Object.values(map).includes(v))&&
      expectedPlans.length===(amazon?10:3),"EXACT_PUBLIC_PLAN_AND_NONCE_SET");
 const fields={schema:3,state:"ACTUAL_CURRENT_"+app.toUpperCase()+"_R4_INSTALL02_AND_OWNER_ROUTE_CONTROLS_BOUND_FRESH_FLOW_UNRUN",
      nonce:map.flow,component:oldInputs.component,
      helper_uid:abi.UID,helper_package:abi.helper_package,helper_protocol:abi.protocol,
      current_host_manifest_sha256:abi.current_host_manifest_sha256,current_baseline:abi.current_baseline,
      actual_install_job:abi.job_id,actual_install_source_manifest_sha256:abi.source_manifest_sha256,
      actual_install_receipts:abi.prior_receipts,all_six_original_install_pins:abi.all_six_original_receipts,
      state_nonce:abi.state_nonce,state_wire_sha256:abi.state_wire_sha256,
      state_recorder_command_result_sha256:abi.recorder_command_result_sha256,
      actual_target_APK_count:3,current_install_INPUTS_target_APK_count:abi.historical_input_target_APK_count,
      current_install_INPUTS_count_matches_actual:abi.historical_input_count_matches_actual,
      prior_generation_install_metadata_not_rewritten:true,
      actual_source_controls:{job_id:input.control_job_id,...input.control_actual.pin,count:expectedCount,
        control_source:pin(controls.source),control_stdin_sha256:h.sha(controls.raw),
        production_constructor_and_plan_and_install_validators:true,synthetic_IO_only:true,
        current_generation_controls:9,current_owner_task_route_controls:3},
      actual_fresh_nonce_source:{...bound.nonce_actual,generator:"secrets.token_hex(16)",spec:bound.nonce_spec,
        app_count:labels.length,excluded_values:bound.nonce_excluded_count,order:labels,values:labels.map(k=>map[k])},
      resolver_records:oldInputs.resolver_records,
      historical_resolution_not_launch_authority:true,new_prelaunch_resolution_required:true,
      exact_success_budgets:{phase_seconds:{launch:175,inspect:175,cleanup:115},worker_seconds:{launch:190,inspect:190,cleanup:130},
        request_seconds:600,launch_durable_commands:12,
        inspection_durable_commands_formula:amazon?"27+9*k; 3<=k<=8":"8+9*k; 1<=k<=3",
        maximum_inspection_durable_commands:amazon?99:35,
        maximum_private_foreground_observations:amazon?30:9,maximum_helper_nonces:amazon?31:9,
        maximum_click_actions:amazon?1:0,total_nonces:labels.length,
        maximum_counts:amazon?{target_uid:2,target_path:2,helper_uid:22,helper_path:22,stacks:20,foreground:30,instrument:31,click:1}:
          {target_uid:2,target_path:2,helper_uid:8,helper_path:8,stacks:6,foreground:9,instrument:9,click:0}},
      original_full_tree_window_node_refresh_final_guards_preserved:true,
      original_independent_after_state_finally_preserved:true,
      failed_or_partial_observation_not_retried:true,old_failed_unknown_actions_not_replayed:true,
      maximum_native_launches:1,maximum_click_actions:amazon?1:0,text_actions:0,
      login_account_payment_booking_actions:0,business_success_verified:false,
      shared_helper_whole_process_tree_cleanup_qualified:false,target_signer_independently_verified:false,
      framework_exit_cause_resolved:false,automatic_retry:false,UI_request_dispatched:false,whole_app_production_ready:false};
 if(amazon){
      fields.search_entry_plan=plan;
      fields.observed_selector_reference=oldInputs.observed_selector_reference;
      fields.actual_resolver_reference=oldInputs.actual_resolver_reference;
      fields.search_readiness={maximum_complete_no_action_sequences:8,qualification_seconds:30,
        minimum_consecutive_equal:3,minimum_observed_span_seconds:4,future_stability_proven:false};
      fields.first_failure_attribution={original_actual_failed_summary_preserved:true,
        current_primary_from_navigation_retained_first_failure:true,independent_post_record_separate:true};
 }else{
      fields.read_only_inspection_plans=plan;fields.maximum_inspection_rounds=3;
      fields.qualification_window_seconds=30;fields.round_offsets_seconds=[0,10,20];
      fields.qualification_deadline_is_not_execution_kill=true;
      fields.only_previous_complete_all_zero_catalog_allows_next_round=true;
      fields.current_semantic_readiness_not_yet_observed=true;
      fields.complete_tree_depth_limit=128;fields.partial_tree_never_qualified=true;
 }
 const raws=Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,canonical(v)]));
 raws.installed_helper=abi.installed_identity_lossless_json;raws.actual_target=abi.target_identity_lossless_json;
 raws.actual_build=abi.build_proof_lossless_json;
 for(const key of ["installed_helper","actual_target","actual_build"])lossless.losslessJsonNodes(raws[key]);
 const inputsRaw="{"+Object.keys(raws).sort().map(k=>JSON.stringify(k)+":"+raws[k]).join(",")+"}\n";
 for(const key of ["installed_helper","actual_target","actual_build"])need(lossless.losslessCanonical(lossless.nodeField(lossless.losslessJsonNodes(inputsRaw),[key]))===raws[key],"LOSSLESS_RUNTIME_IDENTITY:"+key);
 const files={"owned_inspect.py":sourceMap.coordinator,[app+"_task_context.py"]:sourceMap.context,
      [amazon?"search_navigation.py":"bestbuy_readiness.py"]:sourceMap.business,"INPUTS.json":inputsRaw};
 const manifest={schema:1,files:Object.fromEntries(Object.entries(files).sort().map(([k,v])=>[k,pin(v)]))};
 files["SOURCE_PINS.json"]=canonical(manifest)+"\n";
 const manifestSHA=h.sha(files["SOURCE_PINS.json"]),packet={schema:1,nonce:map.flow,files},wire=canonical(packet)+"\n";
 need(h.utf8(wire).length<=131072&&Object.values(files).every(s=>h.utf8(s).length<=65536)&&
      Object.values(files).reduce((n,s)=>n+h.utf8(s).length,0)<=131072,"ORIGINAL_UI_SOURCE_AND_PACKET_BOUNDS");
 const stage=sourceMap.stage;
 const wrapper="import hashlib,json,sys;raw=sys.stdin.buffer.read(131073);assert len(raw)=="+h.utf8(wire).length+
      " and hashlib.sha256(raw).hexdigest()=='"+h.sha(wire)+"';stage="+JSON.stringify(stage)+
      ";assert hashlib.sha256(stage.encode()).hexdigest()=='"+h.sha(stage)+
      "';scope={\"__name__\":\""+app+"_fixed_task_stage\",\"__file__\":\"<verified-"+app+"-task-stage>\"};"+
      "exec(compile(stage,\"stage_execute.py\",\"exec\"),scope);raise SystemExit(scope[\"main\"](json.loads(raw),'"+manifestSHA+"'))";
 const request={...oldQ,args:["-n","/usr/bin/python3","-I","-B","-c",wrapper],stdin:wire,
      idempotency_key:"pocket4-"+app+"-r4-current-"+(amazon?"search-entry":"content-readiness")+"01-20261106"};
 return{app,files,stage_source:stage,request,manifest_sha256:manifestSHA,inputs_raw:inputsRaw,packet,
      proof:{actual_control_count:expectedCount,actual_controls_and_install_bound:true,actual_UID:abi.UID,
        installed_mtime_ns_lossless:abi.installed_mtime_ns,all_seven_actual_tested_sources_equal:true,
        source_functions_not_modified_by_UI_binder:true,fresh_nonce_count:labels.length,all_current_reserved_values_excluded:bound.nonce_excluded_count,
        production_current_owner_task_route_controls:3,
        original_UI_envelope_resource_limits:true,packet:pin(wire),runtime_inputs_lossless:true,
        actual_target_APK_count:3,historical_metadata_preserved:true,UI_dispatched:false,whole_app_production_ready:false}};
}
