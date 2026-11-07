return function bindBiliSpanFlow(u, originalRequestRaw, templateSource, controlStdoutRaw, controlStdoutPin, slots, exclusions) {
  function need(ok,message){if(!ok)throw Error(message);}
  const bytes=s=>u.utf8Bytes(s), sha=s=>u.sha256(bytes(s));
  need(bytes(originalRequestRaw).length===131286 && sha(originalRequestRaw)==="6a3d4cd3f9382351506dc7f86a43658a3d309b8e8efc34bfc00a5382360a07a0","original full request mismatch");
  need(bytes(templateSource).length===59902 && sha(templateSource)==="98c90a686bfac4b3369e31d568e6742017a638d6f6a9674b5e9cec0dd6bc856c","template mismatch");
  need(controlStdoutPin && Number.isSafeInteger(controlStdoutPin.bytes) && controlStdoutPin.bytes>0 && controlStdoutPin.bytes<=32768 && /^[0-9a-f]{64}$/.test(controlStdoutPin.sha256),"external actual control stdout pin required");
  need(bytes(controlStdoutRaw).length===controlStdoutPin.bytes && sha(controlStdoutRaw)===controlStdoutPin.sha256,"actual control original changed");
  const c=JSON.parse(controlStdoutRaw);
  need(c.schema===1 && c.ok===true && c.state==="EXACT_PRODUCTION_FUNCTION_PURE_CONTROLS_PASS","actual controls did not pass");
  need(c.original_source_sha256==="14c72e48693aba988d78258851f534302f3898c519cf94bf20ae2f8997c5de6b" && c.template_source_sha256===sha(templateSource) && c.control_stdin_sha256==="5aa00cf4f5db2448a023bfcf82a24c25ffa34224620bfd716923f00d4de9f27c","actual controls binding mismatch");
  need(Array.isArray(c.controls)&&c.controls.length===43&&new Set(c.controls.map(x=>x.name)).size===43&&c.controls.every(x=>x.passed===true),"actual exact controls incomplete");
  need(c.python_full_source_compile===true&&c.exact_candidate_function_executed_with_synthetic_session===true&&c.real_qa_parser_executed===false&&c.private_UI_or_app_readiness_verified===false&&c.Android_actions===0&&c.process_or_device_commands===0&&c.file_writes===0&&c.production_module_executed===false&&c.runtime_flow_dispatched===false&&c.whole_app_production_ready===false,"pure control boundary changed");
  const pool=c.secrets_nonce_pool;
  need(Array.isArray(pool)&&pool.length===146&&new Set(pool).size===146&&pool.every(x=>typeof x==="string"&&/^[0-9a-f]{32}$/.test(x)&&!exclusions.includes(x))&&c.nonce_pool_size===146&&c.nonce_pool_disjoint_originals===true,"secure actual nonce pool mismatch");
  need(slots.length===146&&new Set(slots).size===146&&exclusions.length===136,"source slot inventory mismatch");
  const q=JSON.parse(originalRequestRaw),old=JSON.parse(q.stdin);
  need(bytes(q.stdin).length===128335&&sha(q.stdin)==="177b55e3d0a9468d1d755ada8b90201822642f59b28e88710a14ca7841f8eada","original packet mismatch");
  const oldRoot="/home/alex/work/pocket4-bilibili-r7-pause-resume-01",newRoot="/home/alex/work/pocket4-bilibili-r7-pause-resume-02";
  need(slots[0]===old.nonce&&old.nonce==="b73ad7a9e358f11585dab9281fde42b1","old root nonce mapping mismatch");
  const mapping=slots.map((slot,index)=>[slot,pool[index]]);
  const bind=s=>mapping.reduce((s,pair)=>s.split(pair[0]).join(pair[1]),s);
  const inverse=s=>mapping.reduce((s,pair)=>s.split(pair[1]).join(pair[0]),s.split(newRoot).join(oldRoot));
  need(sha(bind(templateSource))===c.bound_navigation_sha256_before_new_root,"actual compiled source and final nonce mapping differ");
  const names=Object.keys(old.files).filter(n=>n!=="SOURCE_PINS.json").sort();
  need(JSON.stringify(names)===JSON.stringify(["controls_reveal.py","owned_navigation.py","playback_controls.py","post_foreground.py","stage_execute.py","video_navigation.py"]),"original closure changed");
  const files={},manifest={files:{},schema:1},proof=[];
  for(const name of names){
    const before=name==="owned_navigation.py"?templateSource:old.files[name];
    const after=bind(before).split(oldRoot).join(newRoot);
    need(inverse(after)===before,"literal inverse mismatch "+name);
    need(bytes(after).length>0&&bytes(after).length<=65536,"runtime source bound "+name);
    files[name]=after;
    manifest.files[name]={bytes:bytes(after).length,sha256:sha(after)};
    proof.push({name,original_bytes:bytes(old.files[name]).length,bytes:bytes(after).length,sha256:sha(after),inverse_literal_exact:true,functional_change:name==="owned_navigation.py"});
  }
  files["SOURCE_PINS.json"]=JSON.stringify(manifest)+"\n";
  const orderedFiles=Object.fromEntries(Object.entries(files).sort(([a],[b])=>a.localeCompare(b)));
  const packet={files:orderedFiles,nonce:pool[0],schema:1,source_manifest_sha256:sha(files["SOURCE_PINS.json"])};
  const stdin=JSON.stringify(packet);
  need(bytes(stdin).length<=131072,"runtime packet over unchanged bound");
  const oldStageSha=JSON.parse(old.files["SOURCE_PINS.json"]).files["stage_execute.py"].sha256;
  need(q.args.length===5 && q.args[4].includes(sha(q.stdin)) && q.args[4].includes(oldStageSha) && q.args[4].includes(oldRoot),"old wrapper mismatch");
  q.args[4]=q.args[4].split(sha(q.stdin)).join(sha(stdin)).split(oldStageSha).join(manifest.files["stage_execute.py"].sha256).split(oldRoot).join(newRoot);
  q.stdin=stdin;
  q.idempotency_key="pocket4-bilibili-r7-player-button02-20261106";
  return {request:q,request_raw:JSON.stringify(q),packet,manifest,source_files:files,
          control_stdout_pin:controlStdoutPin,root:newRoot,nonce:pool[0],
          proof:{source_files:proof,source_manifest:{bytes:bytes(files["SOURCE_PINS.json"]).length,sha256:sha(files["SOURCE_PINS.json"])},
                 packet:{bytes:bytes(stdin).length,sha256:sha(stdin)},root_literal_only_changed:true,
                 no_helper_or_install_identity_change:true,all_future_action_guards_retained:true,
                 old_failure_preserved:true,pure_controls_not_runtime_UI_qualification:true,Hepta_dispatched:false}};
};