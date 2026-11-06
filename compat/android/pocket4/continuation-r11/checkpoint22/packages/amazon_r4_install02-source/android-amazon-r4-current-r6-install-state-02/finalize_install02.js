function finalizeCurrentOwnerInstall02(prepared, prior, nonceActual, global659, h){
 const need=(v,s)=>{if(!v)throw Error(prepared.app+":"+s)},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 const sorted=v=>Array.isArray(v)?v.map(sorted):v&&typeof v==="object"?Object.fromEntries(Object.keys(v).sort().map(k=>[k,sorted(v[k])])):v;
 const canonical=v=>JSON.stringify(sorted(v)),pretty=v=>JSON.stringify(v,null,2)+"\n";
 need(prepared.production_inverse_exact&&prepared.original_helper_and_R6_bytes_unchanged&&prior.helper_uid===null,
      "UNMODIFIED_REVIEWED_SOURCE_PARENT");
 const files={...prepared.files},inputs=JSON.parse(JSON.stringify(prepared.inputs)),bindings=[];
 if(prepared.pending_fresh_nonces){
  need(nonceActual.bytes===h.utf8(nonceActual.raw).length&&nonceActual.sha256===h.sha(nonceActual.raw)&&
       nonceActual.blob===h.git(nonceActual.raw),"EXACT_ACTUAL_FRESH_PAIR_BYTES");
  const n=JSON.parse(nonceActual.raw);
  need(n.schema===1&&n.count===2&&n.generator==="secrets.token_hex(16)"&&n.no_redraw===true&&
       n.Android_actions===0&&n.Main_actions===0&&n.children_started===0&&n.filesystem_mutations===0&&
       n.excluded_count===657&&n.excluded_sha256==="d793bd6aad537724fb78d1258d7544a0bd35d7aeda9696e65f0cd29f56920e4a"&&
       canonical(n.labels)===canonical(["ihg_r4_install02_flow","ihg_r4_install02_state"])&&
       n.values.length===2&&new Set(n.values).size===2&&n.values.every(v=>/^[0-9a-f]{32}$/.test(v)),
       "ACTUAL_NEW_PAIR_AND_COMPLETE_EXCLUSION_REQUIRED");
  const values=JSON.parse(global659.raw);
  need(Array.isArray(values)&&values.length===659&&new Set(values).size===659&&
       values.every(v=>typeof v==="string"&&/^[0-9a-f]{32}$/.test(v))&&
       values.every((v,i)=>i===0||values[i-1]<v)&&global659.sha256===h.sha(global659.raw)&&
       global659.bytes===h.utf8(global659.raw).length&&global659.blob===h.git(global659.raw)&&
       n.values.every(v=>values.includes(v)),"ACTUAL_GLOBAL659_EXCLUSION_UNION");
  const previous=values.filter(v=>!n.values.includes(v));
  need(previous.length===657&&h.sha(JSON.stringify(previous)+"\n")===n.excluded_sha256&&
       !n.values.includes(prior.inputs.nonces.flow)&&!n.values.includes(prior.inputs.nonces.state),
       "OLD_CONSUMED_PAIR_MUST_STAY_EXCLUDED");
  for(const name of Object.keys(files)){
   if(name==="INPUTS.json"||name==="README.md")continue;
   for(const[old,next]of[["__FRESH_IHG_INSTALL02_FLOW__",n.values[0]],["__FRESH_IHG_INSTALL02_STATE__",n.values[1]]]){
    const count=files[name].split(old).length-1;
    if(count){files[name]=files[name].split(old).join(next);bindings.push({file:name,old,next,count});}
   }
  }
  inputs.nonces={flow:n.values[0],state:n.values[1]};
  inputs.actual_nonce_source={bytes:nonceActual.bytes,sha256:nonceActual.sha256,git_blob:nonceActual.blob,
   fields:n.labels,generator:n.generator,exclusion_count:n.excluded_count,exclusion_sha256:n.excluded_sha256,
   global_reserved_union:{bytes:global659.bytes,sha256:global659.sha256,git_blob:global659.blob,count:659}};
  inputs.state="CURRENT_OWNER_FIX_ACTUAL_BOUND_INSTALL_UNRUN";
 }
 need(Object.values(files).every(x=>!/__FRESH_IHG_/.test(x)),"NO_PENDING_NONCE_LITERAL");
 const previousSource=inputs.original_install_source;
 inputs.install_success_assumed=false;inputs.original_install_failure_replayed=false;
 inputs.previous_reserved_unrun_pair_reused=prepared.app!=="ihg";
 files["INPUTS.json"]=pretty(inputs);
 const manifest={...prepared.prior_manifest,files:Object.fromEntries(Object.entries(files).sort(([a],[b])=>a<b?-1:a>b?1:0).map(([name,body])=>[name,pin(body)]))};
 files["SOURCE_PINS.json"]=pretty(manifest);
 const manifestSha=h.sha(files["SOURCE_PINS.json"]);
 const packet={schema:2,source_manifest_sha256:manifestSha,nonce:inputs.nonces.flow,files};
 const stdin=canonical(packet)+"\n";
 need(h.utf8(stdin).length<=262144&&Object.values(files).every(x=>0<h.utf8(x).length&&h.utf8(x).length<=65536),
      "ORIGINAL_PACKET_AND_LEAF_BOUNDS");
 const wrapper="import hashlib,json,sys\nraw=sys.stdin.buffer.read(262145)\n"+
  "assert hashlib.sha256(raw).hexdigest()=='"+h.sha(stdin)+"'\n"+
  "p=json.loads(raw);src=p['files']['stage_execute.py'].encode('utf-8')\n"+
  "assert hashlib.sha256(src).hexdigest()=='"+h.sha(files["stage_execute.py"])+"'\n"+
  "scope={'__name__':'owned_qa_stage','__file__':'"+prepared.root+"/source/stage_execute.py'}\n"+
  "exec(compile(src,scope['__file__'],'exec'),scope)\nraise SystemExit(scope['main'](raw))\n";
 const request={...prior.request,args:["-n","/usr/bin/python3","-I","-B","-c",wrapper],
  stdin,idempotency_key:prepared.key};
 need(request.timeout_seconds===300&&request.memory_max_bytes===536870912&&request.cpu_quota_percent===100&&
      request.nice===10&&request.host==="pocket4"&&request.executable==="/usr/bin/sudo",
      "ORIGINAL_INSTALL_RUNTIME_ENVELOPE");
 const normalized={...files};
 for(const e of [...bindings].reverse()){
  need(normalized[e.file].split(e.next).length-1===e.count,"BOUND_NONCE_INVERSE");
  normalized[e.file]=normalized[e.file].split(e.next).join(e.old);
 }
 for(const e of [...prepared.edits].reverse()){
  need(normalized[e.file].split(e.to).length-1===e.count,"SOURCE_INVERSE_ANCHOR:"+e.file);
  normalized[e.file]=normalized[e.file].split(e.to).join(e.from);
 }
 for(const[name,body]of Object.entries(prepared.original_sources))if(!["INPUTS.json","README.md"].includes(name))
  need(normalized[name]===body,"FULL_ORIGINAL_PRODUCTION_INVERSE:"+name);
 return{...prepared,files,inputs,manifest,manifest_sha256:manifestSha,packet,stdin,wrapper,request,
  requestRaw:JSON.stringify(sorted(request),null,2)+"\n",pending_fresh_nonces:false,
  request_created:true,nonce_bindings:bindings,production_inverse_exact:true,previousSource};
}
