function bindFixedCommercial22Metadata(material,slug,h){
 const C={"catalog":{"bytes":56355,"sha256":"55b6dc90e808b113ec63ca7b9532d157f1ffded3aa1f04aa72f47c0a2f07b5c7"},"prior_request":{"bytes":46285,"sha256":"6fd46edcc0965801a61a1e7c5c6f2c95cbff628b597661c36b6cf09f17ac10b3"},"discovery":{"bytes":8332,"sha256":"9ed0069897faebba50cec3d93b08da54f1c791d6e2e775d26ec798c38b227886"},"exclusions":{"bytes":33861,"sha256":"c19f6007c56b50dd048203f155461a6e11d8c3328254bfc9064d5f94abc84312"},"nonce_generator":{"bytes":33664,"sha256":"3becf9529e336442c05aa322638c9a5b607c5ea46ea9880c260f689508e11cb7","blob":"d3dcba974a8bfa18d78fb7461fcee99b6d3a72b6"},"excluded_compact_sha256":"112a2b3ee4498df5c235de53b656516c4571f8f0e91ef3f7fa24d335d41b7550"};
 const need=(value,code)=>{if(!value)throw Error(code);};
 const pinned=(raw,pin,code)=>{need(typeof raw==="string"&&h.utf8(raw).length===pin.bytes&&h.sha(raw)===pin.sha256,code);return raw;};
 const catalog=JSON.parse(pinned(material.catalog,C.catalog,"CATALOG_PIN"));
 need(Array.isArray(catalog)&&catalog.length===22&&new Set(catalog.map(x=>x.slug)).size===22,"CLOSED_22_TARGETS");
 const selected=catalog.filter(x=>x.slug===slug);need(selected.length===1,"ONLY_EXPLICIT_FIXED_TARGET");
 const target=selected[0];
 const prior=JSON.parse(pinned(material.prior_request,C.prior_request,"ACTUAL_NEXT3_REQUEST_PIN"));
 const template=pinned(material.source_template,target.source_template,"FIXED_SOURCE_TEMPLATE_PIN");
 const stageTemplate=pinned(material.stage_template,target.stage_template,"FIXED_STAGE_TEMPLATE_PIN");
 const discovery=pinned(material.discovery,C.discovery,"CURRENT_DISCOVERY_PIN");
 const excluded=JSON.parse(pinned(material.exclusions,C.exclusions,"ACTUAL_891_EXCLUSION_PIN"));
 need(excluded.length===891&&new Set(excluded).size===891&&excluded.every(x=>/^[0-9a-f]{32}$/.test(x))&&
  h.sha(JSON.stringify(excluded)+"\n")===C.excluded_compact_sha256,"COMPLETE_891_EXCLUSIONS");
 const actualRaw=pinned(material.nonce_actual,material.nonce_actual_pin,"ACTUAL_NONCE_STDOUT_PIN");
 const actual=JSON.parse(actualRaw),labels=catalog.map(x=>x.label);
 need(actual.schema==="pocket4-current-cell02-commercial22-metadata-nonce-material-v1"&&actual.source_sha256===C.nonce_generator.sha256&&
  actual.count===22&&actual.draw_count===22&&actual.source_uid===1000&&actual.no_redraw===true&&actual.excluded_all_891===true&&
  actual.excluded_count===891&&actual.excluded_compact_sha256===C.excluded_compact_sha256&&actual.global_count_after===913&&
  actual.target_catalog_sha256===C.catalog.sha256&&JSON.stringify(actual.labels)===JSON.stringify(labels)&&
  actual.Android_commands===0&&actual.child_processes===0&&actual.file_writes===0&&actual.UI_actions===0&&
  actual.whole_app_production_ready===false&&Array.isArray(actual.generated)&&actual.generated.length===22,"EXACT_ACTUAL_GENERATOR_RESULT");
 const values=actual.generated.map((row,index)=>{need(JSON.stringify(Object.keys(row).sort())===JSON.stringify(["label","nonce","package"])&&
  row.label===labels[index]&&row.package===catalog[index].package&&/^[0-9a-f]{32}$/.test(row.nonce),"LABEL_PACKAGE_NONCE_ORDER");return row.nonce;});
 need(new Set(values).size===22&&!values.some(x=>excluded.includes(x)),"UNIQUE_22_EXCLUDING_891");
 const row=actual.generated.find(x=>x.label===target.label);
 const replace=(raw,before,after)=>{const i=raw.indexOf(before);need(i>=0&&raw.indexOf(before,i+1)<0,"UNIQUE_NONCE_SLOT");return raw.slice(0,i)+after+raw.slice(i+before.length);};
 const source=replace(template,"__FRESH_METADATA_NONCE__",row.nonce);
 const stage=replace(stageTemplate,"__FRESH_METADATA_NONCE__",row.nonce);
 need(h.utf8(source).length<=32768&&source.includes("PACKAGE = '"+target.package+"'")&&
  stage.includes('entry.PACKAGE=="'+target.package+'"'),"EXACT_FIXED_TARGET_RUNTIME");
 const pin=raw=>({bytes:h.utf8(raw).length,sha256:h.sha(raw)});
 const sourcePin=pin(source),stagePin=pin(stage);
 const packet={discovery,nonce:row.nonce,schema:1,source};
 const oldPacket=JSON.parse(prior.stdin);
 need(JSON.stringify(Object.keys(oldPacket))===JSON.stringify(Object.keys(packet)),"ORIGINAL_PACKET_FIELD_ORDER");
 const stdin=JSON.stringify(packet),packetPin=pin(stdin);
 need(packetPin.bytes<=65536,"ORIGINAL_PACKET_BOUND");
 const bootstrap="import hashlib,json,sys\nraw=sys.stdin.buffer.read(65537)\nassert len(raw)=="+packetPin.bytes+
  " and hashlib.sha256(raw).hexdigest()=="+JSON.stringify(packetPin.sha256)+"\nstage="+JSON.stringify(stage)+
  "\nassert len(stage.encode())=="+stagePin.bytes+" and hashlib.sha256(stage.encode()).hexdigest()=="+JSON.stringify(stagePin.sha256)+
  "\nscope={'__name__':'fixed_ticket12306_metadata_stage','__file__':'<verified-fixed-metadata-stage>'}\n"+
  "exec(compile(stage,'stage_execute.py','exec'),scope)\nraise SystemExit(scope['main'](json.loads(raw),"+JSON.stringify(sourcePin.sha256)+"))\n";
 need(prior.host==="pocket4"&&prior.executable==="/usr/bin/sudo"&&JSON.stringify(prior.args.slice(0,-1))===
  JSON.stringify(["-n","/usr/bin/python3","-I","-B","-c"])&&prior.cwd==="/home/alex/work"&&
  prior.timeout_seconds===240&&prior.memory_max_bytes===536870912&&prior.cpu_quota_percent===100&&prior.nice===10,"ORIGINAL_RUNTIME_ENVELOPE");
 const request={...prior,args:[...prior.args.slice(0,-1),bootstrap],stdin,
  idempotency_key:"pocket4-current-cell02-"+slug+"-metadata-01-20261106"};
 return {target,source,stage,stdin,request,requestRaw:JSON.stringify(request,null,2)+"\n",
  sourcePin,stagePin,packetPin,nonceActualPin:material.nonce_actual_pin,nonce:row.nonce,
  original_Policy_Context_guard_and_data_directory_source_unchanged:true,metadata_only_no_business_authority:true};
}
