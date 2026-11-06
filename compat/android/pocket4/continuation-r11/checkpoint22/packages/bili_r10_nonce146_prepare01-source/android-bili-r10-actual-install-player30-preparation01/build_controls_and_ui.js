function buildBiliR10Controls(h,bound,control,helper,old21,originals) {
 const need=(v,c)=>{if(!v)throw Error(c)},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 const canonical=v=>v===null?"null":Array.isArray(v)?"["+v.map(canonical).join(",")+"]":typeof v==="object"?"{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canonical(v[k])).join(",")+"}":JSON.stringify(v),same=(a,b)=>canonical(a)===canonical(b);
 need(bound.pending_fresh_nonces===false&&bound.pending_actual_install===false&&bound.owner_discovery_revision===2&&bound.fresh_nonce_values.length===146&&control.case_count===30&&control.complete_previous27_inverse===true,"ACTUAL_CURRENT_R10_CONTROL_INPUTS");
 need(Object.keys(bound.files).length===6&&Object.keys(old21.new_files).length===6&&Object.entries(bound.original_sources).every(([k,v])=>v===old21.new_files[k]),"EXACT_ACTUAL_PRIOR_SIX_SOURCE_BASELINE");
 const qa=helper.files["qa_contract.py"],adapter=helper.files["qa_adapter.py"];
 need(qa.includes("pocket4-owned-bili-qa-v10")&&adapter.includes("org.droidloom.qa.bili.r10")&&helper.manifestSha===bound.actual_install.build.source_manifest_sha256,"ACTUAL_R10_HELPER_PROTOCOL_CLOSURE");
 const actual={};for(const name of ["coordinator","stage","worker","worker_command","state_command","worker_stdout"]){
  need(same(pin(originals[name].raw),bound.actual_install.records[name]),"ACTUAL_INSTALL_SAFE_ORIGINAL:"+name);actual[name]=originals[name].raw;
 }
 const payload={old_files:old21.new_files,new_files:bound.files,qa_source:qa,adapter_source:adapter,
  failed01_validators:old21.failed01_validators,actual_install_originals:actual,binding_proof:bound.binding_proof};
 payload.pins={old:Object.fromEntries(Object.entries(payload.old_files).map(([k,v])=>[k,pin(v)])),new:bound.source_pins,
  qa:pin(qa),adapter:pin(adapter),failed01_validators:Object.fromEntries(Object.entries(payload.failed01_validators).map(([k,v])=>[k,pin(v)])),
  actual_install_originals:bound.actual_install.records};
 const packet={schema:1,control_source:control.source,control_sha256:h.sha(control.source),payload},raw=canonical(packet)+"\n";
 need(h.utf8(raw).length<=524288,"ORIGINAL_PURE524288_BOUND");
 const manifestRaw=canonical({schema:1,files:bound.source_pins})+"\n",manifestSHA=h.sha(manifestRaw);
 const wrapper="import hashlib,json,sys,types\nraw=sys.stdin.buffer.read(524289)\n"+
  "assert 0<len(raw)<=524288 and hashlib.sha256(raw).hexdigest()=="+JSON.stringify(h.sha(raw))+"\n"+
  "p=json.loads(raw);assert p['schema']==1 and set(p)=={'schema','control_source','control_sha256','payload'}\n"+
  "src=p['control_source'].encode();assert hashlib.sha256(src).hexdigest()==p['control_sha256']=="+JSON.stringify(h.sha(control.source))+"\n"+
  "m=types.ModuleType('bili_r10_current_component_controls');m.__file__='<check_current_flow.py>'\n"+
  "exec(compile(src,m.__file__,'exec'),m.__dict__);out=m.run_controls(p['payload'])\n"+
  "assert out['all_passed'] is True and out['count']==30 and len(out['cases'])==30 and all(r['passed'] is True for r in out['cases'])\n"+
  "assert out['actual_install_receipt_route_controls']==3 and out['current_factory_and_cleanup_route_controls']==6\n"+
  "manifest=(json.dumps({'schema':1,'files':p['payload']['pins']['new']},sort_keys=True,separators=(',',':'))+'\\n').encode()\n"+
  "assert hashlib.sha256(manifest).hexdigest()=="+JSON.stringify(manifestSHA)+"\n"+
  "out.update(new_source_manifest_sha256=hashlib.sha256(manifest).hexdigest(),new_source_pins=p['payload']['pins']['new'],\n"+
  " control_source_sha256=p['control_sha256'],packet_sha256=hashlib.sha256(raw).hexdigest(),actual_install_binding=p['payload']['binding_proof'])\n"+
  "encoded=json.dumps(out,sort_keys=True,separators=(',',':'));assert len(encoded.encode())<=32768;print(encoded,flush=True)\n";
 return {source:control.source,packet,raw,manifest_raw:manifestRaw,manifest_sha256:manifestSHA,
  request:{host:"pocket4",executable:"/usr/bin/python3",args:["-I","-B","-c",wrapper],cwd:"/home/alex/work",env:{},stdin:raw,
   idempotency_key:"pocket4-current-bili-r10-owner-player30-controls01-20261106",timeout_seconds:90,cpu_quota_percent:100,memory_max_bytes:268435456,nice:10},
  Python_executed_here:false,UI_request_created:false};
}
function buildBiliR10UI(h,bound,controls,actualControl,oldRequest){
 const need=(v,c)=>{if(!v)throw Error(c)},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 const canonical=v=>v===null?"null":Array.isArray(v)?"["+v.map(canonical).join(",")+"]":typeof v==="object"?"{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canonical(v[k])).join(",")+"}":JSON.stringify(v),same=(a,b)=>canonical(a)===canonical(b);
 need(bound.pending_actual_install===false&&bound.pending_fresh_nonces===false&&bound.fresh_nonce_values.length===146&&
  actualControl.exit_code===0&&actualControl.full===true&&actualControl.durable===true&&actualControl.stderr_bytes===0&&
  same(pin(actualControl.raw),actualControl.pin)&&h.git(actualControl.raw)===actualControl.git_blob,"ACTUAL_CURRENT30_TERMINAL_REQUIRED");
 const actual=JSON.parse(actualControl.raw);
 need(actual.all_passed===true&&actual.count===30&&actual.cases.length===30&&new Set(actual.cases.map(x=>x.name)).size===30&&actual.cases.every(x=>x.passed===true)&&
  actual.actual_install_receipt_route_controls===3&&actual.current_factory_and_cleanup_route_controls===6&&
  actual.historical_state_streams_and_parse_are_explicit_memory_IO_seams===true&&actual.historical_state_streams_read_from_device===false&&
  actual.Android_commands===0&&actual.UI_actions===0&&actual.App_launches===0&&actual.children===0&&actual.filesystem_operations===0,"THIRTY_ACTUAL_MEMORY_CONTROLS_ONLY");
 need(actual.new_source_manifest_sha256===controls.manifest_sha256&&same(actual.new_source_pins,bound.source_pins)&&
  actual.control_source_sha256===h.sha(controls.source)&&actual.packet_sha256===h.sha(controls.raw)&&
  same(actual.actual_install_binding,bound.binding_proof),"EXACT_ACTUAL_CONTROL_SOURCE_AND_BINDING");
 need(oldRequest.host==="pocket4"&&oldRequest.executable==="/usr/bin/sudo"&&oldRequest.cwd==="/home/alex/work"&&
  oldRequest.timeout_seconds===600&&oldRequest.memory_max_bytes===536870912&&oldRequest.cpu_quota_percent===100&&oldRequest.nice===10,"ORIGINAL_RUNTIME_RESOURCE_ENVELOPE");
 const files={...bound.files,"SOURCE_PINS.json":controls.manifest_raw},packet={schema:1,nonce:bound.fresh_nonce_values[0],source_manifest_sha256:controls.manifest_sha256,files},raw=canonical(packet)+"\n";
 need(h.utf8(raw).length<=196608&&Object.values(files).every(s=>h.utf8(s).length<=65536),"CURRENT_PACKET_AND_LEAF_BOUNDS");
 const stage=files["stage_execute.py"],root="/home/alex/work/pocket4-bilibili-r10-pause-resume-01";
 const wrapper="import hashlib,json,sys\nraw=sys.stdin.buffer.read(196609)\nassert len(raw)=="+h.utf8(raw).length+" and hashlib.sha256(raw).hexdigest()=="+JSON.stringify(h.sha(raw))+"\n"+
  "p=json.loads(raw);src=p['files']['stage_execute.py'].encode()\nassert hashlib.sha256(src).hexdigest()=="+JSON.stringify(h.sha(stage))+"\n"+
  "scope={'__name__':'owned_bili_inspect_stage','__file__':"+JSON.stringify(root+"/source/stage_execute.py")+"}\n"+
  "exec(compile(src,scope['__file__'],'exec'),scope)\nraise SystemExit(scope['main'](raw))\n";
 const request={...oldRequest,args:["-n","/usr/bin/python3","-I","-B","-c",wrapper],stdin:raw,idempotency_key:"pocket4-bili-r10-player-button-01-20261106"};
 return {files,manifest_sha256:controls.manifest_sha256,request,request_raw:JSON.stringify(request,null,2)+"\n",
  proof:{actual_helper_uid:bound.helper_uid,actual_controls:30,actual_controls_job:actualControl.job_id,
   actual_install_step:bound.actual_install.step_root,actual_install_packet:bound.actual_install.packet_sha256,
   lossless_mtime_ns:bound.actual_install.actual_mtime_ns,new_nonce_count:146,excluded_count:741,
   current_discovery_in_launch_navigation_and_cleanup:true,full_tree_window_refresh_guards_unchanged:true,
   no_failure_or_unknown_action_replay:true,UI_request_created:true,UI_dispatched:false,whole_app_production_ready:false}};
}
