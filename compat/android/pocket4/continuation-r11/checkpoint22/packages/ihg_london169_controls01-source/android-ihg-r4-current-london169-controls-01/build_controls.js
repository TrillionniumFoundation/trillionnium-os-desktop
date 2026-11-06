function buildCell02LondonControls(bound,material,controlsTemplate,oldRequestRaw,h,ll){
 const need=(x,m)=>{if(!x)throw Error(m);};
 const pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 const stable=x=>Array.isArray(x)?'['+x.map(stable).join(',')+']':x!==null&&typeof x==='object'?'{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+stable(x[k])).join(',')+'}':JSON.stringify(x);
 const eq=(a,b)=>stable(a)===stable(b);
 const names=['adapter','context','contract','coordinator','public_destination','stage','transport'];
 need(controlsTemplate.complete_inverse_exact===true&&controlsTemplate.old_case_count===157&&
  controlsTemplate.new_case_count===12&&controlsTemplate.total_case_count===169&&
  controlsTemplate.owner_discovery_revision===2&&controlsTemplate.owner_complete_inverse_exact===true&&
  eq(pin(controlsTemplate.source),controlsTemplate.pin),'EXACT_169_CONTROL_TEMPLATE');
 need(bound.actual_install_qualified===true&&bound.complete_binding_inverse===true&&
  bound.command_pre_Main_guard_completed_true===true&&bound.all_eight_actual_Main_maps_equal===true&&
  eq(Object.keys(bound.sources).sort(),names)&&eq(Object.keys(bound.source_pins).sort(),names)&&
  names.every(k=>eq(pin(bound.sources[k]),bound.source_pins[k])),'SEVEN_ACTUAL_BOUND_CURRENT_SOURCES');
 need(Array.isArray(bound.fresh_nonces)&&bound.fresh_nonces.length===40&&new Set(bound.fresh_nonces).size===40&&
  bound.fresh_nonces.every(v=>typeof v==='string'&&/^[0-9a-f]{32}$/.test(v))&&
  bound.nonce_exclusions.length>=659&&new Set(bound.nonce_exclusions).size===bound.nonce_exclusions.length&&
  !bound.fresh_nonces.some(v=>bound.nonce_exclusions.includes(v))&&
  bound.nonce_receipt.actual_helper_uid===bound.actual_helper_uid,'ACTUAL_FRESH_FORTY_NONCES');
 const actualOriginals={},actualPins={};
 for(const key of ['coordinator','stage','worker']){
  const raw=material.install[key],p=bound.install_pins[key];
  need(typeof raw==='string'&&eq(pin(raw),p),'EXACT_ACTUAL_INSTALL_ORIGINAL:'+key);
  actualOriginals[key]=raw;actualPins[key]=p;
 }
 const packet={schema:3,...bound.sources,fresh_nonces:bound.fresh_nonces,
  nonce_exclusions:bound.nonce_exclusions,nonce_receipt:bound.nonce_receipt,
  actual_install_originals:actualOriginals};
 const packetRaw=stable(packet)+'\n',packetPin=pin(packetRaw);
 need(packetPin.bytes<=262144,'ORIGINAL_PURE_INPUT_LIMIT');
 const py=x=>ll.losslessPython(ll.losslessJsonNodes(stable(x)));
 const constants={CONTROL_INPUT_BYTES:packetPin.bytes,CONTROL_INPUT_SHA256:packetPin.sha256,
  CONTROL_SOURCE_PINS:bound.source_pins,CONTROL_EXCLUSION_COUNT:bound.nonce_exclusions.length,
  CONTROL_NONCE_RECEIPT:bound.nonce_receipt,CONTROL_ACTUAL_INSTALL_PINS:actualPins};
 let source=controlsTemplate.source;const edits=[];
 for(const [key,value]of Object.entries(constants)){
  const from=key+'=None  # Bound only after actual R4 install and fresh nonce receipts.';
  const to=key+'='+py(value);
  need(source.split(from).length===2,'EXACT_CONTROL_HEADER:'+key);
  source=source.replace(from,to);edits.push({key,from,to});
 }
 need(!source.includes('=None  # Bound only after actual R4 install and fresh nonce receipts.'),'ALL_HEADERS_BOUND');
 let inverse=source;for(const edit of [...edits].reverse()){
  need(inverse.split(edit.to).length===2,'UNIQUE_HEADER_INVERSE:'+edit.key);
  inverse=inverse.replace(edit.to,edit.from);
 }
 need(inverse===controlsTemplate.source,'CONTROL_BODY_UNCHANGED_AFTER_SIX_HEADER_BINDINGS');
 const old=JSON.parse(oldRequestRaw);
 need(old.host==='pocket4'&&old.executable==='/usr/bin/python3'&&
  eq(old.args.slice(0,3),['-I','-B','-c'])&&old.args.length===4&&typeof old.args[3]==='string'&&
  old.cwd==='/home/alex/work'&&old.timeout_seconds===120&&old.memory_max_bytes===134217728&&
  old.cpu_quota_percent===100&&old.nice===10&&eq(old.env,{PYTHONDONTWRITEBYTECODE:'1'})&&
  old.idempotency_key==='pocket4-ihg-r3-current-london-157-pure-controls-01-20261106',
  'ORIGINAL_EXPLICIT_NO_BYTECODE_PURE_ENVELOPE');
 const request={...old,args:['-I','-B','-c',source],stdin:packetRaw,
  idempotency_key:'pocket4-ihg-r4-cell02-london-169-pure-controls-01-20261106'};
 const sourcePin=pin(source),requestRaw=JSON.stringify(request,null,2)+'\n';
 return{source,source_pin:sourcePin,request,request_raw:requestRaw,request_pin:pin(requestRaw),
  packet:{packet,raw:packetRaw,pin:packetPin},packet_pin:packetPin,header_bindings:edits,count:169,
  proof:{source_template:controlsTemplate.pin,complete_six_header_inverse:true,
   source_and_nonce_material_regenerated:false,actual_install_UID:bound.actual_helper_uid,
   actual_install_job:bound.actual_install_job,all_six_install_originals_prequalified:true,
   three_originals_revalidated_by_production_actual_install:true,
   actual_nonce_count:40,excluded_count:bound.nonce_exclusions.length,
   production_control_body_unchanged:true,original_resource_limits_unchanged:true,
   explicit_isolated_and_no_bytecode:true,Android_actions:0,child_commands:0,file_writes:0,
   Python_executed:false,UI_dispatched:false,whole_app_production_ready:false}};
}

