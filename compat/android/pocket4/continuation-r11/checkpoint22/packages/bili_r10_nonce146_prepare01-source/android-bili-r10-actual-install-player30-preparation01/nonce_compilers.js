function prepareBiliR10Fresh146(h,bound,excludedRaw,excludedPin){
 const need=(v,c)=>{if(!v)throw Error(c)},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 const canonical=v=>v===null?"null":Array.isArray(v)?"["+v.map(canonical).join(",")+"]":typeof v==="object"?"{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canonical(v[k])).join(",")+"}":JSON.stringify(v);
 const excluded=JSON.parse(excludedRaw);
 need(bound.actual_install?.ok===true&&bound.actual_install.source_manifest_sha256==="e3cb2adbcfe46a47ca81ec3b5883f1e1a0cd806b21e964d75944e8fe5cd49387"&&bound.pending_actual_install===false&&bound.pending_fresh_nonces===true&&bound.nonce_count===146,"ACTUAL_R10_INSTALL02_BEFORE_NONCE_GENERATION");
 need(canonical(pin(excludedRaw))===canonical(excludedPin)&&excludedPin.bytes===25937&&excludedPin.sha256==="ab71ef5c617f75ae7cbc5d1e4a5d457462cdb45a28e8c7d5148d1438f4ae5b14"&&excluded.length===741&&new Set(excluded).size===741&&canonical(excluded)===canonical([...excluded].sort())&&excluded.every(x=>/^[0-9a-f]{32}$/.test(x)),"COMPLETE_EXACT_741_GLOBAL_EXCLUSIONS");
 const labels=bound.nonce_labels;need(labels.length===146&&new Set(labels).size===146&&labels[0]==="flow","ORIGINAL_EXACT_146_LABELS");
 const mapping=labels.map((label,index)=>{const slot="__FRESH_NONCE_"+String(index).padStart(3,"0")+"__",files={};
  for(const [name,source]of Object.entries(bound.files)){const count=source.split(slot).length-1;if(count)files[name]=count;}
  need(Object.keys(files).length>0,"MISSING_FIXED_SLOT:"+label);return {label,slot,files};
 });
 const spec={schema:"pocket4-bili-r10-current-owner-player-fresh146-spec-v1",count:146,labels,mapping,
  exclude_count:741,exclude_values:excluded,exclusion_source:excludedPin,source_pins:bound.source_pins,
  actual_helper_UID:bound.helper_uid,actual_install_source_manifest_sha256:bound.actual_install.source_manifest_sha256,
  actual_install_packet_sha256:bound.actual_install.packet_sha256,actual_install_step:bound.actual_install.step_root,
  actual_install_records:bound.actual_install.records,source_only:true,UI_request_created:false,
  exact_one_draw_per_value:true,no_redraw:true};
 const specRaw=canonical(spec)+"\n";need(h.utf8(specRaw).length<=131072,"SPEC_BOUND");
 const source="import hashlib,json,os,re,secrets,sys\nraw=sys.stdin.buffer.read(131073)\n"+
  "assert 0<len(raw)<=131072 and hashlib.sha256(raw).hexdigest()=="+JSON.stringify(h.sha(specRaw))+"\n"+
  "p=json.loads(raw)\nassert p['schema']=='pocket4-bili-r10-current-owner-player-fresh146-spec-v1'\n"+
  "assert os.getuid()==os.geteuid()==1000\n"+
  "assert p['count']==146 and len(p['labels'])==len(set(p['labels']))==146\n"+
  "assert len(p['mapping'])==146 and [x['label'] for x in p['mapping']]==p['labels']\n"+
  "assert p['exclude_count']==len(p['exclude_values'])==len(set(p['exclude_values']))==741\n"+
  "assert all(type(v) is str and re.fullmatch('[0-9a-f]{32}',v) for v in p['exclude_values'])\n"+
  "assert p['actual_helper_UID']=="+bound.helper_uid+" and p['source_only'] is True and p['UI_request_created'] is False\n"+
  "assert p['exact_one_draw_per_value'] is True and p['no_redraw'] is True\n"+
  "pool=[secrets.token_hex(16) for _ in range(146)]\n"+
  "assert len(pool)==len(set(pool))==146 and not set(pool)&set(p['exclude_values'])\n"+
  "print(json.dumps({'schema':'pocket4-bili-r10-current-owner-player-fresh146-v1',\n"+
  " 'spec':{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()},'count':146,\n"+
  " 'labels':p['labels'],'values':pool,'exclude_count':741,'all_distinct_and_old_values_excluded':True,\n"+
  " 'actual_helper_UID':p['actual_helper_UID'],'generator':'secrets.token_hex(16)','uid':os.getuid(),'no_redraw':True,\n"+
  " 'source_only_nonce_generation':True,'file_writes':0,'child_processes':0,'Android_commands':0,'App_launches':0,'UI_actions':0},sort_keys=True,separators=(',',':')),flush=True)\n";
 return {spec,specRaw,source,request:{host:"pocket4",executable:"/usr/bin/python3",args:["-I","-B","-c",source],cwd:"/home/alex/work",env:{},stdin:specRaw,
  idempotency_key:"pocket4-current-bili-r10-owner-fresh146-01-20261106",timeout_seconds:30,cpu_quota_percent:50,memory_max_bytes:134217728,nice:10},
  actual_nonce_values_generated:false,UI_request_created:false};
}
function bindBiliR10Fresh146(h,bound,specRaw,actualRaw,expected){
 const need=(v,c)=>{if(!v)throw Error(c)},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 const canonical=v=>v===null?"null":Array.isArray(v)?"["+v.map(canonical).join(",")+"]":typeof v==="object"?"{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canonical(v[k])).join(",")+"}":JSON.stringify(v),same=(a,b)=>canonical(a)===canonical(b);
 need(same(pin(specRaw),expected.spec)&&same(pin(actualRaw),expected.actual),"EXACT_ACTUAL146_ORIGINAL_PINS");
 const s=JSON.parse(specRaw),a=JSON.parse(actualRaw);
 need(s.schema==="pocket4-bili-r10-current-owner-player-fresh146-spec-v1"&&a.schema==="pocket4-bili-r10-current-owner-player-fresh146-v1"&&same(a.spec,expected.spec)&&
  a.count===146&&a.exclude_count===741&&a.actual_helper_UID===bound.helper_uid&&s.actual_helper_UID===bound.helper_uid&&same(a.labels,s.labels)&&same(s.labels,bound.nonce_labels)&&
  a.generator==="secrets.token_hex(16)"&&a.uid===1000&&a.no_redraw===true&&a.all_distinct_and_old_values_excluded===true&&
  a.source_only_nonce_generation===true&&a.file_writes===0&&a.child_processes===0&&a.Android_commands===0&&a.App_launches===0&&a.UI_actions===0,"ACTUAL_CURRENT146_GENERATOR");
 need(a.values.length===146&&new Set(a.values).size===146&&a.values.every(x=>/^[0-9a-f]{32}$/.test(x)&&!s.exclude_values.includes(x))&&s.exclude_values.length===741&&same(bound.source_pins,s.source_pins),"ACTUAL_SOURCE_AND_GLOBAL_NONCE_FRESHNESS");
 const files={...bound.files},edits=[];
 s.mapping.forEach((row,index)=>{
  need(row.label===a.labels[index],"MAPPING_ORDER");
  for(const [file,count]of Object.entries(row.files)){need(files[file].split(row.slot).length-1===count,"EXACT_SLOT_COUNT:"+file+":"+row.label);files[file]=files[file].split(row.slot).join(a.values[index]);edits.push({file,old:row.slot,next:a.values[index],count,label:row.label});}
 });
 for(const [name,raw]of Object.entries(files))need(!raw.includes("__FRESH_NONCE_")&&h.utf8(raw).length<=65536,"COMPLETE_BOUNDED_FRESH_SOURCE:"+name);
 const inverse={...files};for(const e of [...edits].reverse()){need(inverse[e.file].split(e.next).length-1===e.count,"NONCE_INVERSE_COUNT");inverse[e.file]=inverse[e.file].split(e.next).join(e.old);}
 need(Object.keys(files).every(n=>inverse[n]===bound.files[n]),"EXACT_FRESH146_BINDING_INVERSE");
 return {...bound,files,source_pins:Object.fromEntries(Object.entries(files).map(([n,raw])=>[n,pin(raw)])),
  nonce_binding_edits:edits,nonce_binding_originals:bound.files,pending_fresh_nonces:false,nonce_pool_consumed:false,
  fresh_nonce_values:a.values,actual_nonce_receipt:{...expected.actual,job_id:expected.job_id},nonce_spec:expected.spec,
  nonce_exclusions:s.exclude_values,UI_request_created:false,
  binding_proof:{...bound.binding_proof,nonce_count:146,actual_new146_bound:true,excluded_count:741,full_nonce_inverse:true,source_only_until_actual_new146:false}};
}
