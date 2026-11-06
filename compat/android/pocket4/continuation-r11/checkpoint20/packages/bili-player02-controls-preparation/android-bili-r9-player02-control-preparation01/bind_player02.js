function bindBiliR9Player02(h,input){
 const need=(v,m)=>{if(!v)throw Error(m)};
 function canonical(v){return v===null?"null":Array.isArray(v)?"["+v.map(canonical).join(",")+"]":typeof v==="object"?"{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canonical(v[k])).join(",")+"}":JSON.stringify(v);}
 const pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)}),same=(a,b)=>canonical(a)===canonical(b);
 need(same(pin(input.failed01_request.raw),input.failed01_request.pin)&&same(input.failed01_request.pin,
  {bytes:133937,sha256:"338b3a87abff1cd01d3d4c6b93607f7f689df8b526aee563609245ac0b2a7586"}),"EXACT_FAILED01_SOURCE_REQUEST");
 const oldQ=JSON.parse(input.failed01_request.raw),oldP=JSON.parse(oldQ.stdin),oldManifest=JSON.parse(oldP.files["SOURCE_PINS.json"]);
 need(h.sha(oldP.files["SOURCE_PINS.json"])===oldP.source_manifest_sha256&&Object.keys(oldManifest.files).length===6,"FAILED01_SIX_SOURCE_MANIFEST");
 for(const[n,p]of Object.entries(oldManifest.files))need(same(pin(oldP.files[n]),p),"FAILED01_SOURCE_PIN:"+n);
 need(same(pin(input.nonce_spec.raw),input.nonce_spec.pin)&&same(pin(input.nonce_actual.raw),input.nonce_actual.pin),"EXACT_NONCE_MATERIAL_PINS");
 const spec=JSON.parse(input.nonce_spec.raw),pool=JSON.parse(input.nonce_actual.raw);
 need(spec.schema==="pocket4-bili-r9-player02-fresh-nonce-spec-v1"&&spec.count===146&&spec.exclude_count===337&&
  pool.schema==="pocket4-bili-r9-player02-fresh-nonce-v1"&&pool.count===146&&pool.exclude_count===337&&
  pool.generator==="secrets.token_hex(16)"&&pool.uid===1000&&pool.source_only_nonce_generation===true&&
  pool.all_distinct_and_excluded_old_values===true&&pool.prior_failed_146_not_reused===true&&
  pool.Android_commands===0&&pool.App_launches===0&&pool.UI_actions===0&&same(pool.spec,input.nonce_spec.pin)&&
  same(pool.labels,spec.labels)&&spec.labels.length===146&&Object.keys(pool.nonces).length===146,"ACTUAL_PLAYER02_NONCE_GENERATION");
 const fresh=spec.labels.map(l=>pool.nonces[l]);
 need(fresh.every(v=>typeof v==="string"&&/^[0-9a-f]{32}$/.test(v))&&new Set(fresh).size===146&&
  spec.exclude_values.length===337&&new Set(spec.exclude_values).size===337&&
  fresh.every(v=>!spec.exclude_values.includes(v)),"FRESH_146_EXCLUDES_ALL_FIXED_337");
 const files={...input.templates};
 need(same(Object.keys(files).sort(),Object.keys(oldManifest.files).sort()),"SAME_SIX_RUNTIME_FILES");
 for(const[n,p]of Object.entries(spec.template_pins))need(same(pin(files[n]),p),"PROTOCOL_FIXED_TEMPLATE_PIN:"+n);
 for(let i=0;i<spec.label_mapping.length;i++){
  const row=spec.label_mapping[i];need(row.label===spec.labels[i]&&spec.exclude_values.includes(row.old),"LABEL_ORDER_AND_PREVIOUS_NONCE");
  let count=0;for(const n of Object.keys(files)){const hits=files[n].split(row.slot).length-1;if(hits){files[n]=files[n].split(row.slot).join(fresh[i]);count+=hits;}}
  need(count>=1,"ALL_NEW_NONCES_BOUND:"+row.label);
 }
 need(Object.values(files).every(s=>!s.includes("BILI_R9_02_")&&!s.includes("pocket4-owned-bili-qa-v8")&&!s.includes("EXACT_R8_")),"ALL_CURRENT_PROTOCOL_AND_NONCE_BOUNDARIES");
 const manifest={schema:1,files:Object.fromEntries(Object.entries(files).sort().map(([n,v])=>[n,pin(v)]))};
 files["SOURCE_PINS.json"]=canonical(manifest)+"\n";
 const sha=h.sha(files["SOURCE_PINS.json"]),packet={files,nonce:pool.nonces.flow,schema:1,source_manifest_sha256:sha},wire=canonical(packet)+"\n";
 need(h.utf8(wire).length<=131072&&Object.values(files).every(v=>h.utf8(v).length<=65536),"ORIGINAL_PACKET_AND_FILE_BOUNDS");
 const root="/home/alex/work/pocket4-bilibili-r9-pause-resume-02";
 const wrapper="import hashlib,json,sys\nraw=sys.stdin.buffer.read(131073)\n"+
  "assert hashlib.sha256(raw).hexdigest()=='"+h.sha(wire)+"'\n"+
  "p=json.loads(raw);src=p['files']['stage_execute.py'].encode('utf-8')\n"+
  "assert hashlib.sha256(src).hexdigest()=='"+h.sha(files["stage_execute.py"])+"'\n"+
  "scope={'__name__':'owned_bili_inspect_stage','__file__':'"+root+"/source/stage_execute.py'}\n"+
  "exec(compile(src,scope['__file__'],'exec'),scope)\nraise SystemExit(scope['main'](raw))\n";
 const request={...oldQ,args:["-n","/usr/bin/python3","-I","-c",wrapper],stdin:wire,idempotency_key:"pocket4-bilibili-r9-current-player-button02-20261106"};
 return {files,manifest_sha256:sha,request,nonce_material:{actual:input.nonce_actual.pin,spec:input.nonce_spec.pin},
  proof:{actual_UID:10152,actual_helper_protocol:"pocket4-owned-bili-qa-v9",
   current_epoch:"734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2",
   current_baseline_sha256:"163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266",
   current_qualification_sha256:"f37b2eb00db80c398c9a4f9fd895628b6c7ecc827ccf9699c2242fa5ba862ed6",
   host_manifest_sha256:"6d99374e1580083fd0f30b7f9b3c520306680760c97ad0d5400798fda427fb6e",
   actual_installed_mtime_ns:"1793949174953297011",actual_install_binding_bytes_unchanged:true,
   helper_and_host_sources_unchanged:true,nonce_count:146,all_new_nonce_values_from_actual:true,
   all_337_prior_values_excluded:true,failed01_values_not_reused:true,
   prior_failed_job:"1a1afec2d95-fc05-6cc3",prior_failed_record_preserved:true,
   protocol_admission_literals_updated:2,original_guard_semantics_other_than_exact_version_unchanged:true,
   fresh_UI_candidate_requires_actual_production_validator_controls:true,
   local_Python_controls:false,runtime_UI_not_dispatched:true,whole_app_production_ready:false}};
}