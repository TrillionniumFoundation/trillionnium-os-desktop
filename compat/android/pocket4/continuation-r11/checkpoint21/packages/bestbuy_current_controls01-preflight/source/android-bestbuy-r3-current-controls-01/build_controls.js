function buildCurrentBestBuyControlsPacket(h,bound,source,helper,install,templates,actual,historical){
 const pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)}),need=(v,m)=>{if(!v)throw Error(m)};
 function canon(v){return v===null?"null":Array.isArray(v)?"["+v.map(canon).join(",")+"]":typeof v==="object"?"{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canon(v[k])).join(",")+"}":JSON.stringify(v);}
 need(bound.app==="bestbuy"&&bound.actual_binding.UID===10155&&bound.proof.fresh_nonces_bound===true&&Object.keys(bound.nonce_map).length===10,"ACTUAL_CURRENT_BB_BINDING");
 const sources={contract:helper.files["qa_contract.py"],adapter:helper.files["qa_adapter.py"],business:bound.files["bestbuy_readiness.py"],
  context:bound.files["bestbuy_task_context.py"],coordinator:bound.files["owned_inspect.py"],stage:bound.files["stage_execute.py"],transport:install.files["bestbuy_transport.py"]};
 const sourcePins=Object.fromEntries(Object.entries(sources).map(([n,s])=>[n,pin(s)]));
 const localOrder=["flow",...Array.from({length:3},(_,i)=>["before","inspect","after"].map(k=>"round."+(i+1)+"."+k)).flat()];
 const payload={sources,bound_source_pins:sourcePins,fresh_nonce_values:localOrder.map(k=>bound.nonce_map[k]),
  prior_context:templates.prior["bestbuy_task_context.py"],prior_business:templates.prior["bestbuy_readiness.py"],
  context_edits:bound.edits.filter(x=>x.file==="bestbuy_task_context.py"),
  actual_install:Object.fromEntries(["coordinator","stage","worker"].map(k=>[k,actual[k].raw])),
  historical_inspect:historical,actual_binding:bound.actual_binding,nonce_actual:bound.nonce_actual};
 const packet={schema:1,control_source:source,control_pin:pin(source),payload},raw=canon(packet)+"\n";
 need(h.utf8(raw).length<=524288,"PURE_INPUT_BOUND");
 const wrapper="import hashlib,json,sys,types\nraw=sys.stdin.buffer.read(524289)\n"+
 "assert 0<len(raw)<=524288 and hashlib.sha256(raw).hexdigest()=='"+h.sha(raw)+"'\n"+
 "p=json.loads(raw);assert p['schema']==1 and set(p)=={'schema','control_source','control_pin','payload'}\n"+
 "src=p['control_source'].encode();assert p['control_pin']=={'bytes':len(src),'sha256':hashlib.sha256(src).hexdigest()}\n"+
 "assert hashlib.sha256(src).hexdigest()=='"+h.sha(source)+"'\n"+
 "module=types.ModuleType('bestbuy_current_pure_controls');module.__file__='<bestbuy-pure-controls>'\n"+
 "exec(compile(src,module.__file__,'exec'),module.__dict__);out=module.run_controls(p['payload'])\n"+
 "assert out['ok'] is True and out['count']==59 and len(out['cases'])==59 and all(v['passed'] is True for v in out['cases'])\n"+
 "out.update(control_source_sha256=p['control_pin']['sha256'],control_stdin_sha256=hashlib.sha256(raw).hexdigest(),\n"+
 "    bound_source_pins=p['payload']['bound_source_pins'],nonce_actual=p['payload']['nonce_actual'],\n"+
 "    actual_helper_uid=10155,fresh_nonce_count=10,scope='PURE_CURRENT_BESTBUY_BINDING_AND_READINESS_CONTROLS',\n"+
 "    actual_Main_and_target_callbacks=False,real_Java_helper_executed=False,UI_flow_dispatched=False,\n"+
 "    whole_app_production_ready=False)\n"+
 "encoded=json.dumps(out,sort_keys=True,separators=(',',':'));assert len(encoded.encode())<=32768;print(encoded,flush=True)\n";
 return{source,packet,raw,pins:sourcePins,request:{host:"pocket4",executable:"/usr/bin/python3",args:["-I","-B","-c",wrapper],
  cwd:"/home/alex/work",env:{},stdin:raw,idempotency_key:"pocket4-current-bestbuy-r3-readiness59-controls01-20261106",
  timeout_seconds:90,cpu_quota_percent:100,memory_max_bytes:268435456,nice:10},planned_controls:59,Python_controls_executed:false};
}
