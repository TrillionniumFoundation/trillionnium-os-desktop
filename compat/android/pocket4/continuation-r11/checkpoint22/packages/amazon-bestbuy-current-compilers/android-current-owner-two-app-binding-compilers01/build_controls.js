function buildCurrentOwnerTaskControls(h,bound,control,install,priorPayload,actual){
 const need=(v,m)=>{if(!v)throw Error(m);},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 const canon=v=>v===null?'null':Array.isArray(v)?'['+v.map(canon).join(',')+']':typeof v==='object'?
  '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canon(v[k])).join(',')+'}':JSON.stringify(v);
 const app=bound.app,amazon=app==='amazon',count=amazon?42:71,nonceCount=amazon?32:10;
 need(['amazon','bestbuy'].includes(app)&&bound.template.owner_discovery_revision===2&&
  bound.actual_binding.install_retired===true&&bound.actual_binding.source_controls===68&&
  bound.nonces_bound===true&&bound.complete_binding_inverse===true&&
  bound.fresh_nonce_values.length===nonceCount&&control.owner_discovery_revision===2&&
  control.total_controls===count&&control.owner_route_controls===3,'EXACT_ACTUAL_CURRENT_OWNER_CONTROL_INPUT');
 const sources={...bound.sources,transport:install.files[app+'_transport.py']};
 need(Object.keys(sources).length===7,'SEVEN_BOUND_PRODUCTION_SOURCES');
 const normalize=e=>({file:e.file,from:e.from,to:e.to,count:e.count===undefined?1:e.count,why:e.why||e.reason});
 const delta=[...bound.template.edits,...bound.template.owner_edits].map(normalize);
 const payload={...priorPayload,sources,bound_source_pins:Object.fromEntries(Object.entries(sources).map(([k,v])=>[k,pin(v)])),
  fresh_nonce_values:bound.fresh_nonce_values,
  cell02_edits:delta,cell02_binding_edits:bound.binding_edits.map(normalize),
  prior_current_sources:bound.template.original_sources,
  actual_install:Object.fromEntries(['coordinator','stage','worker'].map(k=>[k,actual[k].raw])),
  actual_binding:bound.actual_binding,nonce_actual:bound.nonce_actual};
 for(const name of ['coordinator','context','business','stage']){
  let restored=sources[name];for(const e of [...delta,...payload.cell02_binding_edits].reverse()){
   if(e.file!==name)continue;need(restored.split(e.to).length-1===e.count,'EXACT_COMPLETE_SOURCE_INVERSE:'+name+':'+e.why);
   restored=restored.split(e.to).join(e.from);}
  need(restored===payload.prior_current_sources[name],'EXACT_PREVIOUS_CURRENT_SOURCE:'+name);
 }
 const packet={schema:1,control_source:control.source,control_pin:pin(control.source),payload},raw=canon(packet)+'\n';
 need(h.utf8(raw).length<=524288,'PURE_INPUT_BOUND');
 const wrapper="import hashlib,json,sys,types\nraw=sys.stdin.buffer.read(524289)\n"+
  "assert 0<len(raw)<=524288 and hashlib.sha256(raw).hexdigest()=='"+h.sha(raw)+"'\n"+
  "p=json.loads(raw);assert p['schema']==1 and set(p)=={'schema','control_source','control_pin','payload'}\n"+
  "src=p['control_source'].encode();assert p['control_pin']=={'bytes':len(src),'sha256':hashlib.sha256(src).hexdigest()}\n"+
  "assert hashlib.sha256(src).hexdigest()=='"+h.sha(control.source)+"'\n"+
  "module=types.ModuleType('"+app+"_current_owner_controls');module.__file__='<"+app+"-pure-controls>'\n"+
  "exec(compile(src,module.__file__,'exec'),module.__dict__);out=module.run_controls(p['payload'])\n"+
  "assert out['ok'] is True and out['count']=="+count+" and len(out['cases'])=="+count+" and all(v['passed'] is True for v in out['cases'])\n"+
  "assert out['current_owner_task_route_controls']==3 and out['current_cell02_generation_controls']==9\n"+
  "out.update(control_source_sha256=p['control_pin']['sha256'],control_stdin_sha256=hashlib.sha256(raw).hexdigest(),\n"+
  "    bound_source_pins=p['payload']['bound_source_pins'],nonce_actual=p['payload']['nonce_actual'],\n"+
  "    actual_helper_uid="+bound.actual_binding.UID+",fresh_nonce_count="+nonceCount+",scope='PURE_CURRENT_"+app.toUpperCase()+"_R4_OWNER_AND_BUSINESS_CONTROLS',\n"+
  "    actual_Main_and_target_callbacks=False,real_Java_helper_executed=False,UI_flow_dispatched=False,\n"+
  "    whole_app_production_ready=False)\n"+
  "encoded=json.dumps(out,sort_keys=True,separators=(',',':'));assert len(encoded.encode())<=32768;print(encoded,flush=True)\n";
 return{app,source:control.source,packet,raw,pins:payload.bound_source_pins,planned_controls:count,
  request:{host:'pocket4',executable:'/usr/bin/python3',args:['-I','-B','-c',wrapper],cwd:'/home/alex/work',env:{},
   stdin:raw,idempotency_key:'pocket4-current-'+app+'-r4-owner-business'+count+'-controls01-20261106',
   timeout_seconds:90,cpu_quota_percent:100,memory_max_bytes:268435456,nice:10},
  Python_controls_executed:false,UI_dispatched:false};
}
