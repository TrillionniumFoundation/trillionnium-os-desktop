function buildCurrentAmazonControlsPacket(h,bound,source,helper,install,templates,actual,attribution){
 const pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)}),need=(v,m)=>{if(!v)throw Error(m)};
 function canon(v){return v===null?"null":Array.isArray(v)?"["+v.map(canon).join(",")+"]":typeof v==="object"?"{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canon(v[k])).join(",")+"}":JSON.stringify(v);}
 need(bound.app==="amazon"&&bound.actual_binding.UID===10154&&bound.proof.fresh_nonces_bound===true&&Object.keys(bound.nonce_map).length===32,"ACTUAL_CURRENT_AMAZON_BINDING");
 const sources={contract:helper.files["qa_contract.py"],adapter:helper.files["qa_adapter.py"],business:bound.files["search_navigation.py"],
  context:bound.files["amazon_task_context.py"],coordinator:bound.files["owned_inspect.py"],stage:bound.files["stage_execute.py"],transport:install.files["amazon_transport.py"]};
 const sourcePins=Object.fromEntries(Object.entries(sources).map(([n,s])=>[n,pin(s)]));
 const localOrder=["flow",...Array.from({length:8},(_,i)=>["before","inspect","after"].map(k=>"stability."+(i+1)+"."+k)).flat(),
  ...["before","inspect","action","after"].map(k=>"entry."+k),...["before","inspect","after"].map(k=>"post."+k)];
 need(localOrder.length===32&&attribution.candidate===templates.prior["owned_inspect.py"],"EXACT_ATTRIBUTION_BASE");
 const payload={sources,bound_source_pins:sourcePins,fresh_nonce_values:localOrder.map(k=>bound.nonce_map[k]),
  prior_context:templates.prior["amazon_task_context.py"],prior_business:templates.prior["search_navigation.py"],
  coordinator_edits:bound.edits.filter(x=>x.file==="owned_inspect.py"),
  context_edits:bound.edits.filter(x=>x.file==="amazon_task_context.py"),
  nonce_mapping:bound.nonce_mapping.map(r=>({...r,value:bound.nonce_map[r.label]})),
  attribution_baseline:attribution.baseline,attribution_candidate:attribution.candidate,
  attribution_actual_inspection:attribution.actual_inspection,
  actual_install:Object.fromEntries(["coordinator","stage","worker"].map(k=>[k,actual[k].raw])),
  actual_binding:bound.actual_binding,nonce_actual:bound.nonce_actual};
 need(payload.nonce_mapping.length===32&&payload.nonce_mapping.every(r=>/^[0-9a-f]{32}$/.test(r.value)),"NONCE_INVERSE_ROWS");
 const packet={schema:1,control_source:source,control_pin:pin(source),payload},raw=canon(packet)+"\n";
 need(h.utf8(raw).length<=524288,"PURE_INPUT_BOUND");
 const wrapper="import hashlib,json,sys,types\nraw=sys.stdin.buffer.read(524289)\n"+
 "assert 0<len(raw)<=524288 and hashlib.sha256(raw).hexdigest()=='"+h.sha(raw)+"'\n"+
 "p=json.loads(raw);assert p['schema']==1 and set(p)=={'schema','control_source','control_pin','payload'}\n"+
 "src=p['control_source'].encode();assert p['control_pin']=={'bytes':len(src),'sha256':hashlib.sha256(src).hexdigest()}\n"+
 "assert hashlib.sha256(src).hexdigest()=='"+h.sha(source)+"'\n"+
 "module=types.ModuleType('amazon_current_pure_controls');module.__file__='<amazon-pure-controls>'\n"+
 "exec(compile(src,module.__file__,'exec'),module.__dict__);out=module.run_controls(p['payload'])\n"+
 "assert out['ok'] is True and out['count']==30 and len(out['cases'])==30 and all(v['passed'] is True for v in out['cases'])\n"+
 "out.update(control_source_sha256=p['control_pin']['sha256'],control_stdin_sha256=hashlib.sha256(raw).hexdigest(),\n"+
 "    bound_source_pins=p['payload']['bound_source_pins'],nonce_actual=p['payload']['nonce_actual'],\n"+
 "    actual_helper_uid=10154,fresh_nonce_count=32,scope='PURE_CURRENT_AMAZON_ATTRIBUTION_BINDING_AND_PLAN_CONTROLS',\n"+
 "    actual_Main_and_target_callbacks=False,real_Java_helper_executed=False,UI_flow_dispatched=False,\n"+
 "    whole_app_production_ready=False)\n"+
 "encoded=json.dumps(out,sort_keys=True,separators=(',',':'));assert len(encoded.encode())<=32768;print(encoded,flush=True)\n";
 return{source,packet,raw,pins:sourcePins,request:{host:"pocket4",executable:"/usr/bin/python3",args:["-I","-B","-c",wrapper],
  cwd:"/home/alex/work",env:{},stdin:raw,idempotency_key:"pocket4-current-amazon-r3-search-entry30-controls01-20261106",
  timeout_seconds:90,cpu_quota_percent:100,memory_max_bytes:268435456,nice:10},planned_controls:30,Python_controls_executed:false};
}
