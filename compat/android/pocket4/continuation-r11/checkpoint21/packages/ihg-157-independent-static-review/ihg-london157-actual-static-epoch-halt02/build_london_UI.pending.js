function buildLondonUI(bound,material,actualControl,oldInputRaw,oldRequestRaw,h,ll){
 const need=(x,m)=>{if(!x)throw Error(m);};
 const pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 const stable=x=>Array.isArray(x)?'['+x.map(stable).join(',')+']':x!==null&&typeof x==='object'?'{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+stable(x[k])).join(',')+'}':JSON.stringify(x);
 const eq=(a,b)=>stable(a)===stable(b);
 need(eq(pin(oldRequestRaw),{bytes:118688,sha256:'4144d110ccc53c15dbfe7b5376c265d41c7ca447478b567711ed7230cca4ae64'}),'EXACT_R2_UI_ENVELOPE');
 const sourceNames=['adapter','context','contract','coordinator','public_destination','stage','transport'];
 need(bound&&eq(Object.keys(bound.sources).sort(),sourceNames)&&eq(Object.keys(bound.source_pins).sort(),sourceNames)&&
  sourceNames.every(k=>typeof bound.sources[k]==='string'&&eq(pin(bound.sources[k]),bound.source_pins[k])),'EXACT_BOUND_SEVEN_SOURCE_BYTES');
 need(typeof material.public_editor_reference==='string'&&eq(pin(material.public_editor_reference),{"bytes":1505,"sha256":"989677dca231cceb7803d43933c75b05448b7000204193b893d51185744aeec9"}),'EXACT_HISTORICAL_PUBLIC_EDITOR_REFERENCE');
 const oldRequest=JSON.parse(oldRequestRaw);
 const oldPacket=JSON.parse(oldRequest.stdin);
 need(oldPacket.files['INPUTS.json']===oldInputRaw,'EXACT_R2_RUNTIME_INPUT_ORIGINAL');
 need(actualControl&&typeof actualControl.raw==='string'&&actualControl.full===true&&actualControl.exit_code===0&&
  actualControl.stderr_bytes===0&&/^[0-9a-f-]+$/.test(actualControl.job_id)&&eq(pin(actualControl.raw),actualControl.pin),'ACTUAL_COMPLETE_CONTROLS_REQUIRED');
 const result=JSON.parse(actualControl.raw);
 need(result.ok===true&&result.state==='IHG_R3_CURRENT_SEARCH_DESTINATION_LONDON_PURE_CONTROLS_PASS'&&result.control_count===157&&
  Array.isArray(result.controls)&&result.controls.length===157&&new Set(result.controls.map(x=>x.case)).size===157&&
  result.controls.every(x=>x.passed===true),'ALL_157_ACTUAL_PASS');
 need(eq(result.bound_source_pins,bound.source_pins)&&eq(result.template_source_pins,bound.source_pins)&&
  result.control_stdin_sha256==='94f62f87ab34a6e142e1cb4f1d55857b0b46bcac8dd84fc06781ba991111fe92'&&
  result.bound_coordinator_sha256===bound.source_pins.coordinator.sha256&&result.bound_stage_sha256===bound.source_pins.stage.sha256,
  'ACTUAL_CONTROLS_TEST_EXACT_SEVEN_SOURCES');
 need(result.all_template_and_bound_python_compile===true&&result.original_Session_sequence_and_real_contract_summary_and_policy_executed===true&&
  result.production_Flow_and_BoundArun_constructors_executed===true&&result.actual_prior_install_validator_executed===true&&
  result.production_qualified_initial_admission_executed===true&&result.Android_actions===0&&result.device_or_child_process_commands===0&&result.file_writes===0,
  'ACTUAL_PRODUCTION_CONTROL_BOUNDARIES');
 need(eq(result.fresh_nonce_values,bound.fresh_nonces)&&result.nonce_exclusion_count===609&&
  result.nonce_values_disjoint_all_fixed_prior_literals===true&&result.nonce_material_is_prior_actual_not_regenerated===true,
  'ACTUAL_FORTY_NONCE_CONTROL_BINDING');
 const root=ll.losslessJsonNodes(oldInputRaw),worker=ll.losslessJsonNodes(material.install.worker);
 const obj=JSON.parse(material.install.worker),n=JSON.parse(material.nonce_raw);
 const make=x=>ll.losslessJsonNodes(JSON.stringify(x));
 const put=(k,x)=>{root.fields[k]=make(x);};
 const putNode=(k,x)=>{root.fields[k]=x;};
 function plan(name){
  const re=new RegExp('^'+name+'=(.*)$','m'),m=bound.sources.coordinator.match(re);
  need(m,'EXACT_PLAN_LITERAL:'+name);return JSON.parse(m[1]);
 }
 const search=plan('SEARCH_PLAN'),destination=plan('PLAN'),input=plan('INPUT_PLAN'),post=plan('POST_PLAN'),readiness=plan('SEARCH_READINESS_PLANS');
 put('schema',3);put('state','ACTUAL_CURRENT_IHG_R3_INSTALL_AND_157_CONTROLS_BOUND_FRESH_LONDON_FLOW_UNRUN');
 put('nonce',n.values[0]);put('helper_package','org.droidloom.qa.ihg.r3');put('helper_protocol','pocket4-owned-ihg-qa-v3');put('helper_uid',obj.owned_package_uid);
 putNode('installed_helper',ll.nodeField(worker,['installed_before_state']));
 putNode('actual_target',ll.nodeField(worker,['target_before']));
 putNode('actual_build',ll.nodeField(worker,['build']));
 put('actual_install_job','1a1b093149f-fc05-7172');
 put('actual_install_source_manifest_sha256','7d7c97b453ed5e5f75a4bd3fcab92cc3e76603bb1e09745ce509d3cd73c7494d');
 const installRoot='/home/alex/work/pocket4-owned-ihg-qa-r3-install-state-01';
 put('actual_install_receipts',Object.fromEntries(Object.entries(bound.prior).map(([k,v])=>[k,{path:installRoot+'/'+v[0],bytes:v[1],sha256:v[2]}])));
 put('all_six_original_install_pins',bound.install_pins);
 put('actual_source_controls',{...actualControl.pin,job_id:actualControl.job_id,git_blob:actualControl.git_blob,
  count:157,control_source:{bytes:66619,sha256:'3d9216ddbddadbd87c0cadde240db563f4f7067149bfa5a3e3140eb4f27ee840'},
  control_stdin_sha256:result.control_stdin_sha256,production_Flow_BoundArun_Session_and_current_install_validators:true,synthetic_IO_only:true});
 put('actual_fresh_nonce_source',{...bound.nonce_receipt,order:n.labels,values:n.values});
 put('state_nonce',obj.state.helper.nonce);put('state_wire_sha256',obj.state.wire_sha256);
 put('state_recorder_command_result_sha256',bound.install_pins.state_command.sha256);
 put('explicit_search_click_plan',search);put('public_destination_click_plan',destination);
 put('public_destination_input_specification',input);put('independent_post_plan',post);put('search_readiness_plans',readiness);
 put('input_text_supported',true);put('maximum_public_set_text',1);put('fixed_public_input','London');
 put('input_selector_must_be_derived_from_fresh_complete_tree',true);
 put('first_or_second_sequence_failure_or_unknown_forbids_input',true);
 put('input_ACK_requires_separate_current_value_readback',true);
 put('input_semantic_context',{class:'android.widget.EditText',resource_namespace:'com.ihg.apps.android:id/',
  unique_eligible_editor:true,unique_public_Destination_ancestor:true,ancestor_maximum:6,other_public_roles_in_context:0,
  no_historical_task_or_node_reuse:true,original_node_refresh_fulltree_window_final_guards:true});
 put('historical_public_editor_reference',JSON.parse(material.public_editor_reference));
 const budgets=JSON.parse(ll.losslessCanonical(ll.nodeField(root,['exact_success_budgets'])));
 budgets.inspection_durable_commands_formula='47+9*k; 3<=k<=8';budgets.maximum_inspection_durable_commands=119;
 budgets.maximum_counts={target_uid:2,target_path:2,helper_uid:26,helper_path:26,stacks:24,instrument:39,foreground:36,click:2,set_text:1};
 budgets.maximum_helper_nonces=39;budgets.maximum_private_foreground_observations=36;budgets.total_nonces=40;
 put('exact_success_budgets',budgets);
 const inputRaw=ll.losslessCanonical(root)+'\n';
 need(ll.losslessCanonical(ll.nodeField(ll.losslessJsonNodes(inputRaw),['installed_helper']))===
  ll.losslessCanonical(ll.nodeField(worker,['installed_before_state'])),'LOSSLESS_INSTALLED_INPUT');
 need(ll.losslessCanonical(ll.nodeField(ll.losslessJsonNodes(inputRaw),['actual_target']))===
  ll.losslessCanonical(ll.nodeField(worker,['target_before'])),'LOSSLESS_TARGET_INPUT');
 const files={'owned_inspect.py':bound.sources.coordinator,'ihg_task_context.py':bound.sources.context,
  'public_destination.py':bound.sources.public_destination,'INPUTS.json':inputRaw};
 const manifest={schema:1,files:Object.fromEntries(Object.entries(files).sort(([a],[b])=>a.localeCompare(b)).map(([k,v])=>[k,pin(v)]))};
 const manifestRaw=stable(manifest)+'\n';files['SOURCE_PINS.json']=manifestRaw;
 for(const [name,raw]of Object.entries(files))need(h.utf8(raw).length<=65536,'SOURCE_MEMBER_BOUND:'+name);
 need(Object.values(files).reduce((sum,v)=>sum+h.utf8(v).length,0)<=131072,'ORIGINAL_STAGE_TOTAL_SOURCE_BOUND');
 const packetRaw=stable({schema:1,nonce:n.values[0],files})+'\n';
 const bytes=h.utf8(packetRaw).length;
 const transportBound=bytes<=131072?131072:196608;
 need(bytes<=transportBound,'BOUNDED_SOURCE_TRANSPORT');
 const stage=bound.sources.stage,stagePin=pin(stage),manifestSha=h.sha(manifestRaw);
 const wrapper='import sys,json,hashlib\nraw=sys.stdin.buffer.read('+String(transportBound+1)+')\nassert len(raw)=='+String(bytes)+
  ' and hashlib.sha256(raw).hexdigest()=='+JSON.stringify(h.sha(packetRaw))+'\nstage='+JSON.stringify(stage)+
  '\nassert len(stage.encode())=='+stagePin.bytes+' and hashlib.sha256(stage.encode()).hexdigest()=='+JSON.stringify(stagePin.sha256)+
  '\nscope={"__name__":"fixed_ihg_r3_london_stage","__file__":"<verified-current-IHG-stage>"}\nexec(compile(stage,"stage_execute.py","exec"),scope)\nraise SystemExit(scope["main"](json.loads(raw),'+JSON.stringify(manifestSha)+'))\n';
 need(oldRequest.executable==='/usr/bin/sudo'&&eq(oldRequest.args.slice(0,4),['-n','/usr/bin/python3','-I','-c'])&&
  oldRequest.memory_max_bytes===536870912&&oldRequest.cpu_quota_percent===100&&oldRequest.timeout_seconds===600,'EXACT_OLD_RESOURCE_ENVELOPE');
 const request={...oldRequest,args:[...oldRequest.args.slice(0,3),'-B',oldRequest.args[3],wrapper],stdin:packetRaw,
  idempotency_key:'pocket4-ihg-r3-current-search-destination-london01-20261106'};
 return{files,stage_source:stage,inputs_raw:inputRaw,manifest_sha256:manifestSha,request,request_raw:JSON.stringify(request,null,2)+'\n',
  proof:{exact_seven_actual_tested_sources:true,actual_controls:157,actual_UID:10156,lossless_ns:true,
   actual_fresh_nonce_count:40,excluded_values:609,stage_total_bound:131072,transport_packet_bound:transportBound,
   transport_only_bound_changed:transportBound!==131072,packet:pin(packetRaw),old_resource_envelope_unchanged:true,explicit_outer_Python_no_bytecode:true,
   no_Runtime_UI_dispatched:true,whole_app_production_ready:false}};
}