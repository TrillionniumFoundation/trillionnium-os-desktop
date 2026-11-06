function bindAmazonRetirement(template,historicalSource,nativeActual,currentActual,originalUIInput,h,ll) {
 const need=(x,c)=>{if(!x)throw Error(c);},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 const canonical=x=>Array.isArray(x)?'['+x.map(canonical).join(',')+']':x!==null&&typeof x==='object'?'{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+canonical(x[k])).join(',')+'}':JSON.stringify(x);
 const eq=(a,b)=>canonical(a)===canonical(b);
 need(eq(pin(template),{bytes:46745,sha256:'a0ecc834102f056e1421998ac565863cc960d574f1fd323f9156037f74646026'}),'EXACT_REVIEWED_RETIREMENT_TEMPLATE');
 need(eq(pin(historicalSource),{bytes:22570,sha256:'36bfe5a58ebe2f542c973b855688a296d27165bb19539a4409a3cf636d97b8d9'}),'EXACT_ORIGINAL_NATIVE_READER_SOURCE');
 for(const[a,label]of[[nativeActual,'native'],[currentActual,'current']]){
  need(a&&typeof a.raw==='string'&&eq(pin(a.raw),a.pin)&&a.full===true&&a.exit_code===0&&a.stderr_bytes===0&&
   /^[0-9a-f-]+$/.test(a.job_id)&&/^[0-9a-f]{40}$/.test(a.git_blob),'ACTUAL_FULL_RECEIPT:'+label);
 }
 need(eq(nativeActual.pin,{bytes:10704,sha256:'b41485c17c1079544eb8674f6a9e040bd4133c0501cf64fef01111a2e2e3e23f'}),'EXACT_HISTORICAL_NATIVE_ACTUAL');
 const n=JSON.parse(nativeActual.raw),c=JSON.parse(currentActual.raw),cn=ll.losslessJsonNodes(currentActual.raw);
 need(n.ok===true&&n.errors.length===0&&n.control_count===12&&n.controls.every(x=>x.passed===true)&&
  n.file_descriptors_opened===n.file_descriptors_closed&&Object.values(n.bindings).every(x=>x===true),'NATIVE_ACTUAL_COMPLETE');
 need(c.schema==='pocket4-amazon-native-launch-current-two-stack-observation-v1'&&c.ok===true&&c.error===null&&c.secondary_errors.length===0&&
  c.source_sha256==='57b4ce695df3e1e6b58e80ec11a7895759cdb5ffa9d6fac6846a6e34297acea6','EXACT_CURRENT_READ_SOURCE_PASS');
 need(c.controls.length===11&&new Set(c.controls.map(x=>x.name)).size===11&&c.controls.every(x=>x.passed===true)&&
  c.current_read_sequence_completed===true&&c.actual_command_count===10&&c.command_records.length===10&&
  c.final_held_guard_passed===true&&c.held_binding_released===true&&c.global_action_lock_released===true&&c.flow_lock_released===true&&
  c.source_and_artifact_inputs_unchanged===true&&c.target_FD_cleanup.held_APK_FDs_closed===3,'CURRENT_READ_ALL_GATES_AND_RELEASE');
 need(c.historical_launch_outcome_unknown_retained===true&&c.action_attempted===false&&c.outcome_unknown===false&&
  c.new_native_launches===0&&c.UI_actions===0&&c.package_mutations===0&&c.task_removals===0&&
  c.helper_instrumentation_calls===0&&c.cleanup_authority_created===false&&c.Bili_Flow_instantiated===false&&c.old_helper_nonce_values_consumed===false,
  'CURRENT_READ_NO_NEW_ACTION_OR_AUTHORITY');
 const lossless=(node,path)=>ll.losslessCanonical(ll.nodeField(node,path));
 const main=lossless(cn,['Main_before_lock']);
 for(const key of ['Main_after_locks','Main_before','Main_after'])need(lossless(cn,[key])===main,'ALL_CURRENT_MAIN_MAPS:'+key);
 need(c.Main_after.Main_epoch_sha256==='734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2','EXACT_CURRENT_EPOCH');
 need(lossless(cn,['helper_before'])===lossless(cn,['helper_after'])&&lossless(cn,['target_before'])===lossless(cn,['target_after']),
  'LOSSLESS_CURRENT_HELPER_AND_TARGET_EQUAL');
 const oldInput=ll.losslessJsonNodes(originalUIInput);
 need(lossless(cn,['helper_before'])===lossless(oldInput,['installed_helper'])&&c.helper_before.uid===10154&&
  c.helper_before.package==='org.droidloom.qa.amazon.r3'&&c.target_before.artifacts.length===3&&
  c.target_before.metadata.package==='com.amazon.mShop.android.shopping'&&c.target_before.metadata.uid===10129,'EXACT_CURRENT_HELPER_AND_THREE_TARGET_APKS');
 need(c.two_complete_tables_equal===true&&c.observations.length===2&&eq(c.historical_prelaunch,n.prelaunch),'TWO_COMPLETE_CURRENT_TABLES_AND_BASELINE');
 const matches=n.native_projection.closed_child_matches;
 need(matches.length===1&&matches[0].shape==='backend_different_registration_ownership'&&matches[0].line_index===1&&
  Number.isInteger(matches[0].labelled_fields.task)&&matches[0].labelled_fields.task>0&&
  n.native_projection.whole_error_attribution_qualified===false&&n.native_projection.current_installed_source_version_verified===false&&
  n.native_projection.task_cleanup_authority_created===false,'CLOSED_CHILD_IS_EVIDENCE_NOT_AUTHORITY');
 const task=matches[0].labelled_fields.task,component='com.amazon.mShop.android.shopping/com.amazon.mShop.home.HomeActivity';
 const keys=Object.keys(n.prelaunch).sort();
 const projection=row=>Object.fromEntries(keys.map(k=>[k,row[k]]));
 for(const[row,index]of c.observations.map((v,i)=>[v,i])){
  need(row.sample===index+1&&row.preexisting_full_roots_preserved===true&&row.preexisting_task_ids_present===true&&
   eq(row.added_task_ids,[task])&&eq(row.removed_task_ids,[])&&row.task_cleanup_authority_created===false&&
   row.unknown_component_names_exported===false,'EXACT_FRESH_TABLE_CHANGE');
  need(eq(row.tasks,[...n.prelaunch.tasks,task].sort((a,b)=>a-b))&&row.roots.length===n.prelaunch.roots.length+1,'NO_OTHER_TASK_OR_ROOT');
  for(const old of n.prelaunch.roots)need(row.roots.some(r=>eq(r,old)),'ORIGINAL_FULL_ROOT_PRESERVED');
  const selected=row.roots.filter(r=>r.id===task);
  need(selected.length===1&&selected[0].display===0&&selected[0].user===0&&selected[0].freeform===true&&selected[0].children.length===1&&
   selected[0].children[0].id===task&&selected[0].children[0].user===0&&selected[0].children[0].target_component_match===true&&
   selected[0].children[0].public_target_component===component&&selected[0].children[0].component_sha256===h.sha(component),'EXACT_ISOLATED_CURRENT_TARGET_LEAF');
 }
 need(c.observations[0].complete_parsed_roots_sha256===c.observations[1].complete_parsed_roots_sha256,'SAME_CURRENT_COMPLETE_ROOTS');
 const root='/home/alex/work/pocket4-amazon-owned-qa-r3-flow-42ee4dd8ab30f563567ba353deff430c';
 const records=new Map(c.command_records.map(row=>[row.path,row]));
 need(records.size===10,'TEN_DISTINCT_CURRENT_COMMANDS');
 for(let i=1;i<=10;i++){
  const path=root+'/steps/native-launch-state-read-01/command-'+String(i).padStart(3,'0')+'.result.json',row=records.get(path);
  need(row&&Number.isInteger(row.bytes)&&row.bytes>0&&/^[0-9a-f]{64}$/.test(row.sha256)&&row.command.returncode===0&&
   row.command.spawned===true&&row.command.owned_command_joined===true&&row.command.timed_out===false&&
   row.command.error===null&&eq(row.command.errors,[])&&row.command.action_attempted===false&&row.command.automatic_retry===false&&
   row.command.stderr_sha256===h.sha(''),'EXACT_JOINED_CURRENT_READ:'+i);
 }
 const sixth=records.get(root+'/steps/native-launch-state-read-01/command-006.result.json'),last=c.observations[1];
 need(sixth.command.stdout_sha256===last.raw_pin.sha256,'LAST_CURRENT_COMMAND_BINDS_COMPLETE_STACK');
 const receipt=a=>({...a.pin,job_id:a.job_id,git_blob:a.git_blob});
 const inputs={task,actual_native_reader_qualified:true,actual_current_two_stack_read_qualified:true,
  native_reader_actual:receipt(nativeActual),current_reader_actual:receipt(currentActual),
  historical_observations:n.observations,native_projection:n.native_projection,scope_and_attempt:n.scope_and_attempt,
  prelaunch:n.prelaunch,current_observation:{stack:{path:root+'/steps/native-launch-state-read-01/current-stacks-02.txt',...last.raw_pin},
   command:{path:sixth.path,bytes:sixth.bytes,sha256:sixth.sha256},projection:projection(last)}};
 need(template.split('__ACTUAL_RETIREMENT_INPUTS__').length===2,'ONE_EXPLICIT_RETIREMENT_BINDING_SLOT');
 const source=template.replace('__ACTUAL_RETIREMENT_INPUTS__',ll.losslessPython(ll.losslessJsonNodes(JSON.stringify(inputs))));
 const sourcePin=pin(source);need(sourcePin.bytes<=65536,'BOUNDED_OWNED_RETIREMENT_SOURCE');
 const files={'historical_reader.py':historicalSource,'retire.py':source};
 const packet=canonical({schema:1,files,pins:Object.fromEntries(Object.entries(files).map(([k,v])=>[k,pin(v)]))})+'\n';
 need(h.utf8(packet).length<=131072,'BOUNDED_FULL_SOURCE_TRANSPORT');
 const wrapper='import hashlib,json,sys,types\nraw=sys.stdin.buffer.read(131073)\nassert len(raw)=='+h.utf8(packet).length+
  ' and hashlib.sha256(raw).hexdigest()=='+JSON.stringify(h.sha(packet))+
  '\np=json.loads(raw)\nassert p["schema"]==1 and set(p)=={"schema","files","pins"} and set(p["files"])==set(p["pins"])=={"historical_reader.py","retire.py"}\n'+
  'for name,text in p["files"].items():\n data=text.encode();assert len(data)==p["pins"][name]["bytes"] and hashlib.sha256(data).hexdigest()==p["pins"][name]["sha256"]\n'+
  'h=types.ModuleType("fixed_original_Amazon_native007_reader");h.__file__="<fixed-historical-reader>"\nexec(compile(p["files"]["historical_reader.py"],h.__file__,"exec"),h.__dict__)\n'+
  'scope={"__name__":"fixed_amazon_independent_retirement","__file__":"<fixed-Amazon-retirement>","SOURCE_SHA256":p["pins"]["retire.py"]["sha256"],"HIST":h}\n'+
  'exec(compile(p["files"]["retire.py"],scope["__file__"],"exec"),scope)\nraise SystemExit(scope["main"]())\n';
 const request={host:'pocket4',cwd:'/home/alex/work',executable:'/usr/bin/sudo',args:['-n','/usr/bin/python3','-I','-B','-c',wrapper],
  env:{PYTHONDONTWRITEBYTECODE:'1'},stdin:packet,cpu_quota_percent:100,memory_max_bytes:536870912,nice:10,timeout_seconds:360,
  idempotency_key:'pocket4-amazon-r3-independent-native-leaf-retirement01-20261106'};
 return{source,source_pin:sourcePin,inputs,files,packet,request,request_raw:JSON.stringify(request,null,2)+'\n',
  proof:{historical_unknown_preserved:true,whole_error_attribution_qualified:false,source_version_match:false,
   current_table_task_from_two_actual_receipts:task,whole_baseline_preserved:true,fresh_two_tables_required_before_remove:true,
   new_independent_authority_not_old_launch_scope:true,maximum_remove_commands:1,no_native_registration_replay:true,
   actual_Policy_Flow_BoundArun_guards_preserved:true,independent_after_new_read_only_Context:true,
   maximum_primary_commands:42,maximum_independent_after_commands:9,planned_controls:41,
   explicit_outer_Python_no_bytecode:true,Python_executed:false,Hepta_dispatched:false,whole_app_production_ready:false}};
}
