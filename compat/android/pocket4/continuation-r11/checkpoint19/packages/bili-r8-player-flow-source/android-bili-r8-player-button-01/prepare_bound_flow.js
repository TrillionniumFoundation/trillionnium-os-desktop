return function bindR8Flow(u,e,originalRequestRaw,preparationInputRaw,fourRaw,nonceRaw) {
 const bytes=s=>u.utf8Bytes(s),sha=s=>u.sha256(bytes(s));
 const need=(v,m)=>{if(!v)throw Error(m);};
 need(bytes(preparationInputRaw).length===22074&&sha(preparationInputRaw)==="a978a34fb7b63156b4322ac1b196826076ee71947c410d8f0e8c11e8d3db458c","fixed preparation input changed");
 const cfg=JSON.parse(preparationInputRaw);
 for(const [raw,pin,label]of [[originalRequestRaw,cfg.baseline_request,"baseline"],[fourRaw,cfg.actual_four_pin,"actual four"],[nonceRaw,cfg.actual_nonce_pin,"actual nonce"]])need(bytes(raw).length===pin.bytes&&sha(raw)===pin.sha256,label+" exact input");
 const q=JSON.parse(originalRequestRaw),old=JSON.parse(q.stdin),outer=JSON.parse(fourRaw),nonce=JSON.parse(nonceRaw);
 need(bytes(q.stdin).length===cfg.baseline_packet.bytes&&sha(q.stdin)===cfg.baseline_packet.sha256,"baseline packet exact");
 const rows=Object.fromEntries(Object.entries(outer.files).map(([n,r])=>{need(bytes(r.text).length===r.bytes&&sha(r.text)===r.sha256,"actual original "+n);return[n,e.parseExactIntegerView(r.text)];}));
 const c=rows["coordinator.json"],s=rows["stage.json"],w=rows["worker.json"],cmd=rows["worker-command-result.json"];
 need(Object.keys(rows).sort().join("|")==="coordinator.json|stage.json|worker-command-result.json|worker.json","four exact originals");
 need([c,s,w].every(r=>r.ok===true&&r.error===null&&Array.isArray(r.secondary_errors)&&r.secondary_errors.length===0),"successful actual install originals");
 need(c.package===cfg.helper_package&&w.package===cfg.helper_package&&c.owned_package_uid===w.owned_package_uid&&w.installed_before_state.uid===w.owned_package_uid&&w.state.helper.self_uid===w.owned_package_uid&&Number.isSafeInteger(w.owned_package_uid)&&w.owned_package_uid>=10000&&w.owned_package_uid<100000,"actual UID agreement");
 need(e.exactEqual(w.installed_before_state,w.installed_after_state)&&w.outcome_unknown===false&&w.final_Main_guard_passed===true&&w.held_binding_released===true&&w.action_lock_released===true&&cmd.spawned===true&&cmd.joined===true&&cmd.returncode===0&&cmd.timed_out===false,"actual installed identity and completed worker");
 need(w.state.wire_sha256===c.state_wire_sha256&&c.state_wire_sha256===outer.state_wire_sha256&&outer.state_command_index===outer.state_command_binding.index&&outer.state_command_binding.sha256===w.state.recorder_command_result_sha256&&outer.state_command_binding.actual_command_joined===true&&outer.state_command_binding.actual_command_returncode===0,"actual unique state binding");
 need(c.source_manifest_sha256===cfg.install_source_manifest_sha256&&s.source_manifest_sha256===cfg.install_source_manifest_sha256&&w.runtime_session_binding_sha256===cfg.session_sha256,"frozen install source reference");
 const pool=nonce.secrets_nonce_pool,oldPool=cfg.old_nonce_pool;
 need(nonce.schema===1&&nonce.ok===true&&nonce.purpose==="fresh-bili-r8-flow-nonce-pool-only"&&nonce.source_input_sha256==="858ec2a5aadbc3fca76f4a23a33a489ec185f7e169e4189d2118c4c529433082"&&nonce.count===146&&nonce.disjoint_exclusions===true&&nonce.nonce_exclusions_count===296&&nonce.Android_actions===0&&nonce.Main_actions===0&&nonce.child_processes===0&&nonce.file_writes===0&&nonce.UI_flow_dispatched===false,"actual pure material");
 need(Array.isArray(pool)&&pool.length===146&&new Set(pool).size===146&&pool.every(n=>/^[0-9a-f]{32}$/.test(n)&&!cfg.nonce_exclusions.includes(n))&&oldPool.length===146&&new Set(oldPool).size===146&&oldPool[0]===old.nonce,"exact fresh nonce map");
 const py=v=>{
  if(v===null)return"None";
  if(v===true)return"True";
  if(v===false)return"False";
  if(typeof v==="number"){need(Number.isSafeInteger(v),"unsafe JS number cannot become Python literal");return String(v);}
  if(typeof v==="string")return"'"+v.replaceAll("\\","\\\\").replaceAll("'","\\'").replaceAll("\n","\\n").replaceAll("\r","\\r")+"'";
  if(Array.isArray(v))return"["+v.map(py).join(",")+"]";
  need(v&&typeof v==="object","supported literal");
  if(Object.keys(v).length===1&&typeof v.__exact_json_integer__==="string"){need(/^-?(0|[1-9][0-9]*)$/.test(v.__exact_json_integer__),"bad exact integer");return v.__exact_json_integer__;}
  return"{"+Object.entries(v).map(([k,x])=>py(k)+":"+py(x)).join(",")+"}";
 };
 const refs=[["coordinator","coordinator.json"],["stage","stage.json"],["worker","worker.json"],["worker_command","worker-command-result.json"]];
 const assignmentValues={
 "SELF,UID":"("+py(cfg.helper_package)+","+py(w.owned_package_uid)+")",
 INSTALL_ENTRY_SHA:py(cfg.install_entry.sha256),INSTALL_ENTRY_BYTES:String(cfg.install_entry.bytes),
 INSTALL_MANIFEST_SHA:py(cfg.install_source_manifest_sha256),SESSION_SHA:py(cfg.session_sha256),
 OLD_FLOW:"Path("+py(c.flow)+")",OLD_STATE_NONCE:py(w.state_nonce),OLD_STATE_WIRE:py(w.state.wire_sha256),
 OLD_PACKET:py(s.packet_sha256),INSTALL_JOB_ID:py(cfg.install_job),
 STATE_COMMAND_INDEX:py(outer.state_command_index),STATE_COMMAND_SHA:py(outer.state_command_binding.sha256),
 EXPECTED_INSTALLED_IDENTITY:py(w.installed_before_state),
 INSTALL_RECORDS:"{"+refs.map(([key,name])=>{const r=outer.files[name];return py(key)+":(Path("+py(r.path)+"),"+r.bytes+","+py(r.sha256)+")";}).join(",")+"}"
 };
 need(Object.keys(assignmentValues).sort().join("|")===Object.keys(cfg.old_renamed_assignments).sort().join("|"),"exact binding assignment set");
 const names=Object.keys(old.files).filter(n=>n!=="SOURCE_PINS.json").sort();
 need(JSON.stringify(names)===JSON.stringify(cfg.source_names)&&names.length===6,"six runtime closure");
 const renamed={},sourceFiles={},proof=[],replacementRows=[];
 const ren=s=>s.split(cfg.old_root).join(cfg.new_root).split("r7").join("r8").split("R7").join("R8").split("pocket4-owned-bili-qa-v7").join("pocket4-owned-bili-qa-v8");
 const bind=s=>oldPool.reduce((v,n,i)=>v.split(n).join(pool[i]),s);
 const unbind=s=>pool.reduce((v,n,i)=>v.split(n).join(oldPool[i]),s);
 for(const name of names){
  renamed[name]=ren(old.files[name]);let out=renamed[name];
  if(name==="owned_navigation.py"){
   for(const [key,value]of Object.entries(assignmentValues)){
    const before=cfg.old_renamed_assignments[key],after=key+"="+value;
    need(out.split(before).length===2,key+" single original assignment");
    out=out.replace(before,after);replacementRows.push({name:key,before,after});
   }
   const oldUid="10170,10175,10184",newUid=oldUid+",10202";
   need(out.split(oldUid).length===2,"single original UID gate");out=out.replace(oldUid,newUid);
   const anchor="   window=inspection['window']\n";
   need(out.split(anchor).length===2,"single safe summary anchor");out=out.replace(anchor,anchor+cfg.safe_idle_summary_addition);
  }
  out=bind(out);need(bytes(out).length>0&&bytes(out).length<=65536,"unchanged source leaf cap "+name);
  need(!out.includes("BILI_R8_NONCE_")&&!oldPool.some(n=>out.includes(n)),"no pending or old flow nonce");
  sourceFiles[name]=out;
  let inverse=unbind(out);
  if(name==="owned_navigation.py"){
   need(inverse.split(cfg.safe_idle_summary_addition).length===2,"one safe summary addition");
   inverse=inverse.replace(cfg.safe_idle_summary_addition,"").replace("10170,10175,10184,10202","10170,10175,10184");
   for(const row of replacementRows){need(inverse.split(row.after).length===2,"single actual assignment "+row.name);inverse=inverse.replace(row.after,row.before);}
  }
  need(inverse===renamed[name],"full source literal inverse "+name);
  proof.push({name,original_bytes:bytes(old.files[name]).length,original_sha256:sha(old.files[name]),bytes:bytes(out).length,sha256:sha(out),inverse_exact_after_declared_bindings:true,only_added_runtime_logic:name==="owned_navigation.py"?["reject_previous_helper_uid_10202","export_revalidated_safe_idle_metadata"]:[]});
 }
 const manifest={files:{},schema:1};
 for(const name of names)manifest.files[name]={bytes:bytes(sourceFiles[name]).length,sha256:sha(sourceFiles[name])};
 const manifestRaw=JSON.stringify(manifest)+"\n";
 const all={...sourceFiles,"SOURCE_PINS.json":manifestRaw};
 const ordered=Object.fromEntries(Object.entries(all).sort(([a],[b])=>a.localeCompare(b)));
 const packet={files:ordered,nonce:pool[0],schema:1,source_manifest_sha256:sha(manifestRaw)};
 const stdin=JSON.stringify(packet);need(bytes(stdin).length<=131072,"unchanged total packet cap");
 const oldManifest=JSON.parse(old.files["SOURCE_PINS.json"]),oldStage=oldManifest.files["stage_execute.py"].sha256,newStage=manifest.files["stage_execute.py"].sha256;
 need(q.args.length===5&&q.args[4].split(sha(q.stdin)).length===2&&q.args[4].split(oldStage).length===2&&q.args[4].split(cfg.old_root).length===2,"exact old wrapper slots");
 const wrapper=q.args[4].replace(sha(q.stdin),sha(stdin)).replace(oldStage,newStage).replace(cfg.old_root,cfg.new_root);
 need(wrapper.replace(sha(stdin),sha(q.stdin)).replace(newStage,oldStage).replace(cfg.new_root,cfg.old_root)===q.args[4],"wrapper inverse exact");
 q.args[4]=wrapper;q.stdin=stdin;q.idempotency_key=cfg.idempotency_key;
 return{source_files:sourceFiles,source_manifest:manifest,source_manifest_raw:manifestRaw,packet,request:q,request_raw:JSON.stringify(q),replacements:replacementRows,proof,nonce_map:oldPool.map((n,i)=>({slot:i,old:n,new:pool[i]}))};
};