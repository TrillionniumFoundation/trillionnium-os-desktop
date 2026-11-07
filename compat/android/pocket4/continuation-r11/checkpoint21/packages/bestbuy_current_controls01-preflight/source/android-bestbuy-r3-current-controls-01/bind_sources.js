function bindCurrentTwoAppFlowSources(h,input){
 const need=(v,m)=>{if(!v)throw Error(m)},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 function canon(v){return v===null?"null":Array.isArray(v)?"["+v.map(canon).join(",")+"]":typeof v==="object"?"{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canon(v[k])).join(",")+"}":JSON.stringify(v);}
 const same=(a,b)=>canon(a)===canon(b);
 need(same(pin(input.spec.raw),input.spec.pin)&&same(pin(input.actual.raw),input.actual.pin),"EXACT_FRESH42_MATERIALS");
 const spec=JSON.parse(input.spec.raw),out=JSON.parse(input.actual.raw);
 need(spec.schema==="pocket4-current-amazon-bestbuy-fresh-flow-nonce-spec-v1"&&spec.count===42&&spec.exclude_count===564&&
  out.schema==="pocket4-current-amazon-bestbuy-fresh-flow-nonce-v1"&&out.count===42&&out.exclude_count===564&&
  same(out.spec,input.spec.pin)&&same(out.labels,spec.labels)&&Object.keys(out.nonces).length===42&&
  out.generator==="secrets.token_hex(16)"&&out.uid===1000&&out.source_only_nonce_generation===true&&
  out.all_distinct_and_old_values_excluded===true&&out.file_writes===0&&out.child_processes===0&&
  out.Android_commands===0&&out.App_launches===0&&out.UI_actions===0,"ACTUAL_FRESH42_GENERATION");
 const all=spec.labels.map(k=>out.nonces[k]);need(all.every(v=>typeof v==="string"&&/^[0-9a-f]{32}$/.test(v))&&
  new Set(all).size===42&&spec.exclude_values.length===564&&new Set(spec.exclude_values).size===564&&all.every(v=>!spec.exclude_values.includes(v)),"FRESH42_VALUES_AND_FIXED564_EXCLUSIONS");
 const result={};
 for(const app of ["amazon","bestbuy"]){const t=input.templates[app],files={...t.files},rows=spec.mapping.filter(r=>r.app===app);
  need(t.app===app&&t.proof.full_inverse_to_exact_prior===true&&t.actual_binding.install_retired===true&&t.actual_binding.target_APK_count===3,"ACTUAL_TYPED_TEMPLATE:"+app);
  need(rows.length===(app==="amazon"?32:10),"EXACT_APP_NONCE_COUNT");
  for(const[n,p]of Object.entries(spec.template_pins[app]))need(same(pin(files[n]),p),"EXACT_CURRENT_TEMPLATE:"+app+"/"+n);
  for(const row of rows){let count=0;for(const n of Object.keys(files)){const hits=files[n].split(row.slot).length-1;if(hits){files[n]=files[n].split(row.slot).join(out.nonces[row.label]);count+=hits;}}need(count>0,"EACH_SLOT_BOUND");}
  need(Object.values(files).every(s=>!rows.some(r=>s.includes(r.slot))),"NO_SLOT_LEFT");
  const inverse={...files};for(const row of [...rows].reverse())for(const n of Object.keys(inverse))inverse[n]=inverse[n].split(out.nonces[row.label]).join(row.slot);
  need(Object.keys(files).every(n=>inverse[n]===t.files[n]),"ONLY_ACTUAL_NONCE_BINDING");
  result[app]={...t,files,nonce_map:Object.fromEntries(rows.map(r=>[r.local_label,out.nonces[r.label]])),
    nonce_actual:{...input.actual.pin,job_id:input.job_id},nonce_spec:input.spec.pin,
    proof:{...t.proof,fresh_nonces_bound:true,nonce_count:rows.length,all_values_from_actual:true,
      all_564_old_values_excluded:true,cross_App_pool_disjoint:true,UI_request_created:false}};
 }
 return result;
}
