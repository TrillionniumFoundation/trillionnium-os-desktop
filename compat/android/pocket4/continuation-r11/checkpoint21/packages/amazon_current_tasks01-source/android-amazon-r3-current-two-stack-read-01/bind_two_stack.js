function bindAmazonCurrentTwoStack(template, actual, readerRequest, h, ll) {
 const need=(value,code)=>{if(!value)throw Error(code);};
 const pin=raw=>({bytes:h.utf8(raw).length,sha256:h.sha(raw)});
 const stable=value=>Array.isArray(value)?'['+value.map(stable).join(',')+']':value!==null&&typeof value==='object'?'{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+stable(value[k])).join(',')+'}':JSON.stringify(value);
 const same=(left,right)=>stable(left)===stable(right);
 need(same(pin(template),{bytes:19881,sha256:'2f98627c6a1d01d45566c51a9591679eda5ac3e751b98136920d5954141fb45c'}),'EXACT_REVIEWED_AMAZON_TEMPLATE');
 need(actual&&typeof actual.raw==='string'&&actual.exit_code===0&&actual.full===true&&actual.stderr_bytes===0&&
  /^[0-9a-f-]+$/.test(actual.job_id)&&/^[0-9a-f]{40}$/.test(actual.git_blob)&&same(pin(actual.raw),actual.pin),
  'ACTUAL_COMPLETE_HISTORICAL_READER_REQUIRED');
 const value=JSON.parse(actual.raw);
 need(value.schema==='pocket4-fixed-amazon-native-launch007-chain-v1'&&value.ok===true&&
  value.source_sha256==='36bfe5a58ebe2f542c973b855688a296d27165bb19539a4409a3cf636d97b8d9'&&
  Array.isArray(value.errors)&&value.errors.length===0,'EXACT_NATIVE007_READER_ACTUAL');
 const bindingKeys=['native_intent_and_result_equal_actual_worker','native_streams_exact','original_success_scope_absent',
  'prelaunch_exact_source_command_and_complete_original_parser','scope_and_attempt_exact_source'].sort();
 need(same(Object.keys(value.bindings).sort(),bindingKeys)&&bindingKeys.every(k=>value.bindings[k]===true),'ALL_HISTORICAL_BINDINGS');
 need(value.control_count===12&&Array.isArray(value.controls)&&value.controls.length===12&&value.controls.every(c=>c.passed===true)&&
  Number.isInteger(value.file_descriptors_opened)&&value.file_descriptors_opened>0&&
  value.file_descriptors_opened===value.file_descriptors_closed,'ACTUAL_CONTROLS_AND_ALL_FDS_CLOSED');
 need(value.historical_launch_outcome_unknown_retained===true&&value.original_files_modified===0&&
  value.Android_commands===0&&value.UI_actions===0&&value.processes_spawned===0&&value.task_cleanup_authorized===false&&
  value.current_task_state_observed===false&&value.raw_native_message_or_unknown_task_text_exported===false&&
  value.private_UI_read===false,'READ_ONLY_HISTORICAL_BOUNDARIES');
 const root='/home/alex/work/pocket4-amazon-r3-current-search-entry-01';
 const flow='/home/alex/work/pocket4-amazon-owned-qa-r3-flow-42ee4dd8ab30f563567ba353deff430c';
 const expectedParents={
  coordinator:{path:root+'/result.json',bytes:6731,sha256:'6ad6d5b5ee5007dccad21ef6a2847fb84a1afbf48d3de5c13ac9152bd3432541'},
  stage:{path:root+'/stage-result.json',bytes:2724,sha256:'ae0ce8201b2cb5ef8f263b746600029109a14d3e32bb790cd16d16ce745bde99'},
  worker:{path:flow+'/steps/launch-01/result.json',bytes:14255,sha256:'471fd0060d935a14af74a30206607d58267c96982769cb24e442fa5c92ecf95c'}
 };
 for(const[name,row]of Object.entries(expectedParents))need(same(value.observations[name],row),'EXACT_ACTUAL_PARENT:'+name);
 const paths={scope:flow+'/scope.json',attempted:flow+'/launch-attempted.json',prelaunch_stacks:flow+'/steps/launch-01/prelaunch-stacks.txt'};
 const pins={};for(const[name,path]of Object.entries(paths)){
  const row=value.observations[name];need(row&&Object.keys(row).sort().join(',')==='bytes,path,sha256'&&row.path===path&&
   Number.isInteger(row.bytes)&&row.bytes>0&&row.bytes<=(name==='prelaunch_stacks'?131072:65536)&&/^[0-9a-f]{64}$/.test(row.sha256),'EXACT_HISTORICAL_LEAF:'+name);
  pins[name]=row;
 }
 const fixedScope=JSON.parse(template.match(/^SCOPE_FIXED=json\.loads\((.*)\)$/m)[1]);
 const expectedScope=JSON.parse(fixedScope);
 need(value.scope_and_attempt&&Object.keys(value.scope_and_attempt).sort().join(',')==='scope,step,time_utc'&&
  same(value.scope_and_attempt.scope,expectedScope)&&value.scope_and_attempt.step==='launch-01'&&
  typeof value.scope_and_attempt.time_utc==='string','SOURCE_FIXED_SCOPE_AND_ATTEMPT');
 need(value.prelaunch&&same(value.prelaunch.raw_pin,{bytes:pins.prelaunch_stacks.bytes,sha256:pins.prelaunch_stacks.sha256})&&
  value.prelaunch.unknown_component_names_exported===false&&value.prelaunch.task_cleanup_authority_created===false&&
  Array.isArray(value.prelaunch.tasks)&&Array.isArray(value.prelaunch.roots)&&
  /^[0-9a-f]{64}$/.test(value.prelaunch.complete_parsed_roots_sha256),'COMPLETE_PRELAUNCH_PROJECTION_REQUIRED');
 need(value.observations.launch_scope_metadata&&value.observations.launch_scope_metadata.present===false,'ORIGINAL_SCOPE_ABSENT');
 const inputs={actual_historical_chain_qualified:true,native_reader_actual:{...actual.pin,job_id:actual.job_id,git_blob:actual.git_blob,
  reader_source_sha256:value.source_sha256,original_unknown_retained:true,does_not_grant_cleanup_authority:true},
  historical_file_pins:pins,scope_and_attempt:value.scope_and_attempt,prelaunch:value.prelaunch};
 need(template.split('__ACTUAL_HISTORICAL_INPUTS__').length===2,'ONE_INPUT_BINDING_SLOT');
 const source=template.replace('__ACTUAL_HISTORICAL_INPUTS__',ll.losslessPython(ll.losslessJsonNodes(JSON.stringify(inputs))));
 const sourcePin=pin(source);need(sourcePin.bytes<=32768&&!source.includes('__ACTUAL_HISTORICAL_INPUTS__'),'BOUNDED_FULLY_BOUND_READER_SOURCE');
 need(readerRequest.executable==='/usr/bin/sudo'&&same(readerRequest.args.slice(0,4),['-n','/usr/bin/python3','-I','-c'])&&
  readerRequest.host==='pocket4'&&readerRequest.cwd==='/home/alex/work'&&readerRequest.cpu_quota_percent===100&&readerRequest.nice===10,
  'EXACT_EXISTING_READ_ONLY_TRANSPORT');
 const wrapper='import hashlib,sys\nraw=sys.stdin.buffer.read(32769)\nassert len(raw)=='+sourcePin.bytes+
  ' and hashlib.sha256(raw).hexdigest()=='+JSON.stringify(sourcePin.sha256)+
  '\nscope={"__name__":"fixed_amazon_current_two_stack_read","__file__":"<fixed-current-Amazon-reader>","SOURCE_SHA256":'+JSON.stringify(sourcePin.sha256)+'}\n'+
  'exec(compile(raw,"current_two_stack.py","exec"),scope)\nraise SystemExit(scope["main"]())\n';
 const request={...readerRequest,args:[...readerRequest.args.slice(0,4),wrapper],stdin:source,
  memory_max_bytes:536870912,timeout_seconds:240,idempotency_key:'pocket4-amazon-r3-current-two-stack-observation01-20261106'};
 return{source,source_pin:sourcePin,inputs,request,request_raw:JSON.stringify(request,null,2)+'\n',
  proof:{actual_historical_reader_bound:true,full_current_Amazon_Context:true,Bili_Flow_instantiated:false,existing_helper_UID:10154,
   original_target_APK_count:3,maximum_command_count:10,maximum_stack_observations:2,gate_control_count:11,
   native_launches:0,helper_instrumentation_calls:0,UI_actions:0,task_removals:0,old_helper_nonce_values_consumed:false,
   task_cleanup_authority_created:false,historical_unknown_retained:true,Python_controls_executed:false,Hepta_dispatched:false}};
}
