function next3MetadataRuntimeTools(h,templates,stages,priorRequestRaw,discovery,globalRaw,globalPin) {
 const need=(v,m)=>{if(!v)throw Error(m)},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 const canonical=v=>v===null?"null":Array.isArray(v)?"["+v.map(canonical).join(",")+"]":typeof v==="object"?"{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canonical(v[k])).join(",")+"}":JSON.stringify(v);
 const same=(a,b)=>canonical(a)===canonical(b);
 const keys=["ticket12306","hilton","united"],labels=keys.map(k=>k+".metadata");
 const pins={ticket12306:{bytes:30056,sha256:"3d1f8c4702ad9415b50251b6ee2a31dd1b6c1064f0146bce481eabdd7d56d5f9"},hilton:{bytes:30064,sha256:"d0a79b5b71a3243fe2f370f068ee6ecaf2000e263d97ecd4de95b5a890435a69"},united:{bytes:30063,sha256:"8b662a27ff05d8da3542e1706dbe53c298b6ea94810bbbf7eb36194b52840307"}};
 need(same(Object.keys(templates).sort(),[...keys].sort())&&same(Object.keys(stages).sort(),[...keys].sort()),"CLOSED_THREE_SOURCE_SET");
 for(const key of keys){need(same(pin(templates[key]),pins[key])&&typeof stages[key].source==="string"&&stages[key].complete_prior_stage_inverse===true,"EXACT_REVIEWED_TARGET_SOURCE:"+key);}
 need(same(pin(discovery),{bytes:8332,sha256:"9ed0069897faebba50cec3d93b08da54f1c791d6e2e775d26ec798c38b227886"}),"EXACT_CURRENT_DISCOVERY");
 need(same(pin(priorRequestRaw),{bytes:27232,sha256:"4af819e91a34c992b58eb3aabbf4fdbc253372c004488c5fc6e7f75c0c15d21f"}),"EXACT_PRIOR_METADATA_REQUEST");
 const old=JSON.parse(priorRequestRaw);
 need(old.host==="pocket4"&&old.executable==="/usr/bin/sudo"&&same(old.args.slice(0,4),["-n","/usr/bin/python3","-I","-c"])&&old.cwd==="/home/alex/work"&&old.timeout_seconds===240&&old.memory_max_bytes===536870912&&old.cpu_quota_percent===100&&old.nice===10,"EXACT_PRIOR_METADATA_ENVELOPE");
 const exclusions=JSON.parse(globalRaw);
 need(same(pin(globalRaw),globalPin)&&same(globalPin,{bytes:33709,sha256:"fb82257978fc5514eebafc1251658cbc89cfa4b872ef035b3f2c79f3f0628161"})&&
   exclusions.length===887&&new Set(exclusions).size===887&&same(exclusions,[...exclusions].sort())&&exclusions.every(x=>/^[0-9a-f]{32}$/.test(x)),"EXACT_CURRENT_GLOBAL887");
 function qualifyControl(actual){
  need(actual&&typeof actual.raw==="string"&&same(pin(actual.raw),actual.pin)&&h.git(actual.raw)===actual.blob&&
   actual.full===true&&actual.durable===true&&actual.exit_code===0&&actual.stderr_bytes===0&&typeof actual.job_id==="string"&&/^[a-z0-9-]+$/.test(actual.job_id),"ACTUAL_METADATA49_TERMINAL");
  const v=JSON.parse(actual.raw);
  need(v.schema===1&&v.ok===true&&v.count===49&&Array.isArray(v.cases)&&v.cases.length===49&&new Set(v.cases.map(x=>x.name)).size===49&&v.cases.every(x=>x.passed===true),"ALL_ACTUAL49_CASES");
  need(v.control_source_sha256==="708b979512ef3a9570ac3b1e7588db59d7cd3347b3843f059b2514e424fa32ba"&&v.packet_sha256==="4f59c46988278e694f90f6bf634c1300b26c329266ecc1b192fc1771067a7546"&&same(v.fixed_targets,keys)&&same(v.source_pins,pins)&&v.original_parser_and_Context_cases_per_target===13&&v.current_scope_discovery_and_directory_cases===10&&v.synthetic_IO_only===true&&v.actual_UID_or_version_or_APK_observed===false&&v.private_directory_contents_read===false&&v.filesystem_writes===0&&v.child_processes===0&&v.Android_commands===0&&v.App_launches===0&&v.UI_actions===0&&v.new_target_runtime_scope_authorized===false&&v.whole_app_production_ready===false,"ACTUAL49_SOURCE_AND_LIMITS");
  return {job_id:actual.job_id,...actual.pin,blob:actual.blob};
 }
 function prepareNonce(actual){
  const control=qualifyControl(actual),spec={schema:"pocket4-fixed-next3-cell02-metadata-nonce-spec-v1",labels,count:3,source_pins:pins,controls_actual:control,exclude_count:887,exclude_values:exclusions,exclusion_source:globalPin,generator:"secrets.token_hex(16)",exact_one_draw_per_value:true,no_redraw:true,metadata_or_business_runtime_authorized:false};
  const raw=canonical(spec)+"\n";
  need(h.utf8(raw).length<=65536,"NONCE_SPEC_BOUND");
  const source="import hashlib,json,os,re,secrets,sys\nraw=sys.stdin.buffer.read(65537)\nassert 0<len(raw)<=65536 and hashlib.sha256(raw).hexdigest()=="+JSON.stringify(h.sha(raw))+
   "\np=json.loads(raw)\nassert p['schema']=='pocket4-fixed-next3-cell02-metadata-nonce-spec-v1'\nassert os.getuid()==os.geteuid()==1000\nassert p['labels']=="+JSON.stringify(labels)+
   "\nassert p['count']==3 and p['exclude_count']==len(p['exclude_values'])==len(set(p['exclude_values']))==887\nassert all(type(x) is str and re.fullmatch('[0-9a-f]{32}',x) for x in p['exclude_values'])\nvalues=[secrets.token_hex(16) for _ in range(3)]\nassert len(values)==len(set(values))==3 and not set(values)&set(p['exclude_values'])\nprint(json.dumps({'schema':'pocket4-fixed-next3-cell02-metadata-nonces-v1','labels':p['labels'],'values':values,'count':3,'exclude_count':887,'controls_actual':p['controls_actual'],'source_pins':p['source_pins'],'spec':{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()},'generator':'secrets.token_hex(16)','uid':os.getuid(),'no_redraw':True,'distinct_and_all_excluded':True,'Android_commands':0,'App_launches':0,'UI_actions':0,'child_processes':0,'file_writes':0},sort_keys=True,separators=(',',':')),flush=True)\n";
  return {spec,spec_raw:raw,source,request:{host:"pocket4",executable:"/usr/bin/python3",args:["-I","-B","-c",source],cwd:"/home/alex/work",env:{},stdin:raw,idempotency_key:"pocket4-cell02-fixed-next3-metadata-nonce03-01-20261106",timeout_seconds:30,cpu_quota_percent:50,memory_max_bytes:134217728,nice:10}};
 }
 function bindRuntime(actualControl,nonceSpecRaw,actualNonce){
  const control=qualifyControl(actualControl),ns=prepareNonce(actualControl);
  need(nonceSpecRaw===ns.spec_raw,"EXACT_QUALIFIED_NONCE_SPEC");
  need(actualNonce&&typeof actualNonce.raw==="string"&&same(pin(actualNonce.raw),actualNonce.pin)&&h.git(actualNonce.raw)===actualNonce.blob&&actualNonce.full===true&&actualNonce.durable===true&&actualNonce.exit_code===0&&actualNonce.stderr_bytes===0,"ACTUAL_NEW_THREE_NONCES");
  const n=JSON.parse(actualNonce.raw);
  need(n.schema==="pocket4-fixed-next3-cell02-metadata-nonces-v1"&&n.count===3&&n.exclude_count===887&&n.generator==="secrets.token_hex(16)"&&n.uid===1000&&n.no_redraw===true&&n.distinct_and_all_excluded===true&&same(n.labels,labels)&&same(n.source_pins,pins)&&same(n.controls_actual,control)&&same(n.spec,pin(nonceSpecRaw))&&n.values.length===3&&new Set(n.values).size===3&&n.values.every(x=>/^[0-9a-f]{32}$/.test(x)&&!exclusions.includes(x))&&n.Android_commands===0&&n.App_launches===0&&n.UI_actions===0&&n.child_processes===0&&n.file_writes===0,"ACTUAL_METADATA_NONCE_MATERIAL");
  return Object.fromEntries(keys.map((key,index)=>{
   const nonce=n.values[index],slot="__FRESH_METADATA_NONCE__";
   need(templates[key].split(slot).length===2&&stages[key].source.split(slot).length===2,"ONE_SOURCE_AND_STAGE_NONCE_SLOT");
   const source=templates[key].replace(slot,nonce),stage=stages[key].source.replace(slot,nonce);
   need(source.replace(nonce,slot)===templates[key]&&stage.replace(nonce,slot)===stages[key].source,"EXACT_ONLY_NONCE_BINDING_INVERSE");
   need(h.utf8(source).length<=32768&&h.utf8(stage).length<=8192,"EXACT_STAGE_SOURCE_BOUNDS");
   const packet={schema:1,nonce,source,discovery},raw=canonical(packet)+"\n",size=h.utf8(raw).length;
   need(size<=65536,"METADATA_TRANSPORT_BOUND");
   const wrapper="import hashlib,json,sys\nraw=sys.stdin.buffer.read(65537)\nassert len(raw)=="+size+" and hashlib.sha256(raw).hexdigest()=="+JSON.stringify(h.sha(raw))+
    "\nstage="+JSON.stringify(stage)+"\nassert len(stage.encode())=="+h.utf8(stage).length+" and hashlib.sha256(stage.encode()).hexdigest()=="+JSON.stringify(h.sha(stage))+
    "\nscope={'__name__':'fixed_"+key+"_metadata_stage','__file__':'<verified-fixed-metadata-stage>'}\nexec(compile(stage,'stage_execute.py','exec'),scope)\nraise SystemExit(scope['main'](json.loads(raw),"+JSON.stringify(h.sha(source))+"))\n";
   const request={...old,args:["-n","/usr/bin/python3","-I","-B","-c",wrapper],stdin:raw,idempotency_key:"pocket4-current-cell02-"+key+"-metadata-01-20261106"};
   return [key,{source,stage,packet,request,request_raw:JSON.stringify(request,null,2)+"\n",proof:{actual49:control,actualNonce:{...actualNonce.pin,blob:actualNonce.blob,job_id:actualNonce.job_id},fixed_key:key,nonce,
    source_pin:pin(source),stage_pin:pin(stage),source_only_nonce_delta:true,read_commands:5,App_launches:0,UI_actions:0,source_and_discovery_exact:true,baseline_packages_unmodified:true,no_Bili_scope_or_Flow_constructor:true,target_data_directory_contents_read:false,metadata_results_pending:true,dispatched:false,whole_app_production_ready:false}}];
  }));
 }
 return {prepareNonce,bindRuntime};
}
