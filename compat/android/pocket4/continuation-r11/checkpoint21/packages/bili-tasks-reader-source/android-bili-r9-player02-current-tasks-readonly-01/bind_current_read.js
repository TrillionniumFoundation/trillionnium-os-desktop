function bindBili02CurrentTaskRead(h,input){
 const need=(v,m)=>{if(!v)throw Error(m)},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 function canonical(v){return v===null?"null":Array.isArray(v)?"["+v.map(canonical).join(",")+"]":typeof v==="object"?"{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canonical(v[k])).join(",")+"}":JSON.stringify(v);}
 const equal=(a,b)=>canonical(a)===canonical(b);
 need(typeof input.actual_raw==="string"&&equal(pin(input.actual_raw),input.actual_pin)&&typeof input.actual_job_id==="string"&&/^[a-z0-9-]+$/.test(input.actual_job_id),"ACTUAL_READER_RAW_PIN");
 const carrier=JSON.parse(input.actual_raw);
 need(carrier.schema===1&&carrier.encoding==="base64"&&carrier.private_UI_data===false&&
      typeof carrier.data==="string"&&carrier.data.length<=131072,"EXACT_READER_CARRIER");
 function decodeASCII(s){
  need(s.length%4===0&&/^[A-Za-z0-9+/]*={0,2}$/.test(s),"STRICT_BASE64");
  const alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  let out="";
  for(let i=0;i<s.length;i+=4){
   const n=(alphabet.indexOf(s[i])<<18)|(alphabet.indexOf(s[i+1])<<12)|
     ((s[i+2]==="="?0:alphabet.indexOf(s[i+2]))<<6)|(s[i+3]==="="?0:alphabet.indexOf(s[i+3]));
   const a=[(n>>>16)&255,...(s[i+2]==="="?[]:[(n>>>8)&255]),...(s[i+3]==="="?[]:[n&255])];
   need(a.every(b=>b<128),"SAFE_ASCII_CARRIER_ONLY");out+=String.fromCharCode(...a);
  }
  return out;
 }
 const raw=decodeASCII(carrier.data);
 need(h.utf8(raw).length===carrier.uncompressed_bytes&&h.sha(raw)===carrier.uncompressed_sha256,"DECODED_READER_PIN");
 const r=JSON.parse(raw),SOURCE="296da6728d720584339eb47e47801e0c458c3427d06e3a593acdc2f0bc3c6e5d";
 need(r.schema===1&&r.scope==="fixed-r9-player02-native-command-historical-task-baseline"&&
      r.collection_complete===true&&r.errors.length===0&&r.control_count===16&&
      r.controls.length===16&&r.controls.every(x=>x.passed===true)&&new Set(r.controls.map(x=>x.name)).size===16&&
      r.source_manifest_sha256===SOURCE&&r.flow_nonce==="474d7477074ea01fbc986e0d867924c1"&&
      r.reader_acquired_fds_closed===true&&r.reader_opened_fds===r.reader_closed_fds&&
      r.current_tasks_read===false&&r.no_device_commands_or_UI_input===true&&r.processes_spawned===0&&
      r.original_files_modified===0&&r.historical_launch_outcome_unknown_retained===true&&
      r.task_cleanup_authorized===false&&r.UI_window_release_claimed===false,"EXACT_COMPLETE_HISTORICAL_READ");
 for(const key of ["exact_external_worker_original","native_command_004_equals_original_failure",
  "native_stdout_original_SHA","native_stderr_original_SHA","attempted_scope_fixed_source_and_epoch",
  "prelaunch_stack_original_and_source_transport_chain"])need(r.bindings[key]===true,"EXACT_BINDING:"+key);
 const base=r.diagnostic.prelaunch_task_baseline,scope=r.diagnostic.launch_attempt_metadata.scope;
 need(base.target_package_task_count===0&&base.current_task_state_observed===false&&
      base.baseline_precedes_failed_native_command===true&&base.raw_stack_text_exported===false&&
      Array.isArray(base.roots)&&Array.isArray(base.task_ids)&&base.roots.length>0&&base.task_ids.length>0&&
      scope.schema==="pocket4-current-recorder-scope-v1"&&scope.package==="tv.danmaku.bili"&&scope.uid===10117&&
      scope.epoch_sha256==="734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2","EXACT_BASELINE_PROJECTION");
 const FLOW="/home/alex/work/pocket4-bilibili-owned-qa-r9-flow-474d7477074ea01fbc986e0d867924c1";
 const fixed={worker:FLOW+"/steps/launch-01/result.json",scope:FLOW+"/scope.json",
  attempted:FLOW+"/launch-attempted.json",prelaunch_stacks:FLOW+"/steps/launch-01/prelaunch-stacks.txt"};
 const inputs={schema:1,historical_launch_outcome_unknown:true,create_launch_scope:false,
  historical_reader_actual_pin:input.actual_pin,historical_reader_job_id:input.actual_job_id,
  historical_reader_source_sha256:"5d26f04e67e966bc11d0683d77aba8a8b69b541bd38c820de850636dfea1ab94",
  historical_reader_bundle_pin:pin(raw),prelaunch_task_baseline:{task_ids:base.task_ids,roots:base.roots}};
 for(const [name,path] of Object.entries(fixed)){
  const p=r.observations[name];need(p.path===path&&Number.isInteger(p.bytes)&&p.bytes>0&&p.bytes<=131072&&
      /^[0-9a-f]{64}$/.test(p.sha256),"FIXED_OBSERVED_RECORD:"+name);
  inputs[name+"_pin"]={bytes:p.bytes,sha256:p.sha256};
 }
 need(inputs.worker_pin.bytes===5202&&inputs.worker_pin.sha256===
 "037076b15c27611f83815ad243280a1ec8eae82416616c928c9106e17f7a12ca"&&
 inputs.attempted_pin.bytes===1126,"EXACT_PRIOR_WORKER_AND_ATTEMPT");
 need(typeof input.template==="string"&&input.template.split("INPUTS=None  # ACTUAL_BINDING_REQUIRED").length===2,
      "SINGLE_BINDING_SLOT");
 const value=JSON.stringify(inputs);
 const source=input.template.replace("INPUTS=None  # ACTUAL_BINDING_REQUIRED",
      "INPUTS=json.loads("+JSON.stringify(value)+")");
 need(!source.includes("ACTUAL_BINDING_REQUIRED")&&h.utf8(source).length<=32768,"BOUND_SOURCE_ONLY");
 const sourcePin=pin(source),bootstrap="import sys,hashlib;raw=sys.stdin.buffer.read(32769);assert 0<len(raw)<=32768 and hashlib.sha256(raw).hexdigest()=='"+sourcePin.sha256+"';scope={'__name__':'fixed_current_bili_stack_read','__file__':'<fixed-current-bili-stack-read>'};exec(compile(raw,scope['__file__'],'exec'),scope);raise SystemExit(scope['run']('"+sourcePin.sha256+"'))";
 const request={host:"pocket4",executable:"/usr/bin/sudo",args:["-n","/usr/bin/python3","-I","-c",bootstrap],
  cwd:"/home/alex/work",env:{PYTHONDONTWRITEBYTECODE:"1"},stdin:source,timeout_seconds:90,
  memory_max_bytes:268435456,cpu_quota_percent:100,nice:10,
  idempotency_key:"pocket4-bili-r9-player02-current-stacks-readonly01-20261106"};
 return{source,source_pin:sourcePin,request,inputs,proof:{actual_historical_reader_bound:true,
   new_create_only_readonly_step:"native-reconciliation-stacks-read-01",Android_commands:2,
   helper_UiAutomation_calls:0,UI_inputs:0,cleanup_authority_minted:false,old_UNKNOWN_retained:true,
   old_nonce_not_replayed_as_action:true,no_shared_source_changes:true,not_dispatched:true}};
}
