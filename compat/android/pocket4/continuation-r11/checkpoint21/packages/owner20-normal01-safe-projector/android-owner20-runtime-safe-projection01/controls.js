function projectionControls(project, utf8, sha256) {
  const pin=t=>({bytes:utf8(t).length,sha256:sha256(utf8(t))});
  const base=()=>({schema:1,kind:"owner07-normal-external-coordinator01",attempt_nonce:"eae6a2c3c00117d2a6a0f0f08949342de6a14cf8c2dbf695071e7a96b494661c",prepared_sha256:"ee857bb187cd27821fc441a2234da9bb16e4457ff64b0b986d5a02e13e95606f",success:false,errors:[]});
  const log=t=>{const b=utf8(t);return {capacity_bytes:262144,captured_bytes:b.length,captured_sha256:sha256(b),captured_hex:Array.from(b,x=>x.toString(16).padStart(2,"0")).join("")};};
  const run=v=>{const raw=JSON.stringify(v);return project(raw,pin(raw));};
  const rows=[];
  const ok=(name,fn)=>{fn();rows.push({name,passed:true});};
  const no=(name,fn,expected)=>{let actual;try{fn();}catch(e){actual=e.message;}if(actual!==expected)throw Error(name+": "+actual);rows.push({name,passed:true,rejected_with:actual});};
  ok("pre_action_failure_no_capture",()=>{if(run(base()).omitted_private_fields.length)throw Error("count");});
  ok("two_generation_captures_removed_with_exact_hash",()=>{const x=base();x.actor_result={latest_status:{relay_lifecycle:{init_log:log("private sentinel")}},failure_cleanup_stop:{relay_lifecycle:{init_log:log("private sentinel")}}};const o=run(x);if(o.omitted_private_fields.length!==2||JSON.stringify(o).includes("private sentinel")||JSON.stringify(o).includes(log("private sentinel").captured_hex))throw Error("export");});
  no("wrong_original_pin_rejected",()=>project(JSON.stringify(base()),{bytes:1,sha256:"0".repeat(64)}),"OWNER20_RAW_PIN");
  no("unknown_capture_path_rejected",()=>run({...base(),captured_hex:""}),"OWNER20_UNEXPECTED_CAPTURE_PATH");
  no("malformed_hex_rejected",()=>{const x=base();x.actor_result={latest_status:{relay_lifecycle:{init_log:{...log("a"),captured_hex:"zz"}}}};run(x);},"OWNER20_HEX_SHAPE");
  no("capture_size_mismatch_rejected",()=>{const x=base();x.actor_result={latest_status:{relay_lifecycle:{init_log:{...log("a"),captured_bytes:2}}}};run(x);},"OWNER20_INIT_CAPTURE_PIN");
  no("capture_hash_mismatch_rejected",()=>{const x=base();x.actor_result={latest_status:{relay_lifecycle:{init_log:{...log("a"),captured_sha256:"0".repeat(64)}}}};run(x);},"OWNER20_INIT_CAPTURE_PIN");
  function prop(t,key="ro.build.version.sdk"){const x=base(),v=log(t);x.actor_result={property_visibility_observation:{root_observation:{values:[{key,return:v.captured_bytes,errno_observation:0,value_hex:v.captured_hex}]}}};return x;}
  ok("public_numeric_sdk_and_empty_only_literal",()=>{for(const t of ["37","37.0",""]){if(run(prop(t)).public_sdk_value_projections[0].public_numeric_literal!==t)throw Error("literal");}});
  ok("nonnumeric_property_bytes_hash_only",()=>{const o=run(prop("private sentinel")),s=JSON.stringify(o);if(s.includes("private sentinel")||s.includes(log("private sentinel").captured_hex)||o.public_sdk_value_projections[0].public_numeric_literal!==null)throw Error("export");});
  no("unapproved_property_key_rejected",()=>run(prop("secret","user.secret")),"OWNER20_UNEXPECTED_PROPERTY_PATH");
  no("unapproved_payload_hex_rejected",()=>run({...base(),payload_hex:"736563726574"}),"OWNER20_UNEXPECTED_HEX_FIELD");
  ok("large_metadata_integer_token_preserved",()=>{const raw=JSON.stringify({...base(),mtime_ns:0}).replace('"mtime_ns":0','"mtime_ns":1793945758910937522');if(!JSON.stringify(project(raw,pin(raw))).includes('"mtime_ns":1793945758910937522'))throw Error("rounded");});
  return {schema:1,scope:"Pure V8 projection fixtures; no Python/process/device/Main/runtime evidence.",passed:true,count:rows.length,controls:rows};
}
