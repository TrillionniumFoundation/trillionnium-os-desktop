function bindNext3Install(a,h,top,qualifyBuild) {
  const {slug,template,controls,helper,buildOriginal,stageOriginal,parentInputRaw,parentRequestRaw,nonceRaw,nonceSpec,excludedRaw}=a;
  const need=(x,m)=>{if(!x)throw Error(slug+":"+m);};
  function ordered(x) {
    if(Array.isArray(x))return x.map(ordered);
    if(x&&typeof x==="object")return Object.fromEntries(Object.keys(x).sort().map(k=>[k,ordered(x[k])]));
    return x;
  }
  const canonical=v=>JSON.stringify(ordered(v));
  const pretty=v=>JSON.stringify(v,null,2)+"\n";
  const pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s),git_blob:h.git(s)});
  function exact(raw,row,label) {
    need(h.utf8(raw).length===row.bytes&&h.sha(raw)===row.sha256&&(!row.blob||h.git(raw)===row.blob),label);
  }
  need(["ticket12306","hilton","united"].includes(slug)&&helper.slug===slug&&template.proof.target.slug===slug,"one fixed target");
  const target=helper.target,hm=JSON.parse(helper.files["SOURCE_PINS.json"]),hb=hm.current_baseline_binding;
  exact(buildOriginal.raw,buildOriginal,"actual build raw");
  exact(stageOriginal.raw,stageOriginal,"actual stage raw");
  const actualBuild=qualifyBuild(slug,helper,buildOriginal,stageOriginal,h,top);
  const n=JSON.parse(nonceRaw),excluded=JSON.parse(excludedRaw);
  exact(nonceRaw,{bytes:1453,sha256:"689fd9c3dc2f2e91b529635f3b4b52fb3ec273e7f066634e1c1d1cfae1085930",blob:"f1ed0b6990ad27ec673433690236941c8644a3ca"},"actual six nonce raw");
  exact(excludedRaw,nonceSpec.global_exclusion,"complete old global pool raw");
  need(n.schema==="pocket4-current-cell02-next3-install-nonce-material-v1"&&n.source_sha256==="d784a2af4d3c62b714f3f89afc7be80a5bb09a2b09a5511a1853efbde6b95bcb"&&n.target_catalog_sha256===nonceSpec.target_catalog.sha256&&n.count===6&&n.draw_count===6&&n.source_uid===1000&&n.no_redraw===true&&n.excluded_count===913&&n.excluded_all_913===true&&n.global_count_after===919&&n.whole_app_production_ready===false,"actual nonce generator contract");
  need(canonical(n.labels)===canonical(nonceSpec.labels)&&canonical(n.generated.map(x=>x.label))===canonical(nonceSpec.labels)&&canonical(n.generated.map(x=>x.package))===canonical(nonceSpec.packages)&&excluded.length===913&&new Set(excluded).size===913&&n.excluded_compact_sha256===h.sha(JSON.stringify(excluded)+"\n"),"complete exclusion and exact labels");
  const values=n.generated.map(x=>x.nonce);
  need(new Set(values).size===6&&values.every(x=>/^[0-9a-f]{32}$/.test(x)&&!/^0+$/.test(x)&&!excluded.includes(x))&&["Android_commands","UI_actions","file_writes","child_processes"].every(k=>n[k]===0),"six fresh one-draw values");
  const labels=[slug+"_r1_install_flow",slug+"_r1_install_state"];
  const selected=labels.map(label=>n.generated.filter(x=>x.label===label));
  need(selected.every(rows=>rows.length===1&&rows[0].package===target.package),"assigned own nonce pair");
  const flow=selected[0][0].nonce,state=selected[1][0].nonce;
  const files={...template.files};
  exact(files["actual-target-metadata.json"],target,"complete actual metadata");
  const authority=JSON.parse(files["actual-target-metadata.json"]);
  need(files["target-artifact-reference.json"]===helper.files["target-artifact-reference.json"]&&h.sha(files["target-artifact-reference.json"])===target.reference_pin.sha256&&canonical(authority.metadata_before)===canonical({package:target.package,uid:target.uid,user:0,version_code:target.version})&&canonical(authority.metadata_before)===canonical(authority.metadata_after)&&authority.ok===true&&authority.error===null&&authority.secondary_errors.length===0&&canonical(authority.Main_before)===canonical(authority.Main_after),"target authority and helper reference");
  exact(controls.source,controls.proof.candidate,"exact independent 75 controls source");
  need(controls.proof.inverse_exact===true&&controls.proof.control_count===75&&Object.keys(files).length===12,"unbound template and controls");
  const edits=[];
  function change(file,old,replacement,label) {
    const raw=files[file],at=raw.indexOf(old);
    need(at>=0&&raw.indexOf(old,at+old.length)<0,"one binding occurrence:"+label);
    files[file]=raw.slice(0,at)+replacement+raw.slice(at+old.length);
    edits.push({file,label,offset:at,old,replacement});
  }
  for(const file of ["install_state.py","stage_execute.py","make_request.py"])
    change(file,"NONCE = '__FRESH_INSTALL_FLOW__'","NONCE = '"+flow+"'","actual flow "+file);
  change("install_state.py","STATE_NONCE = '__FRESH_INSTALL_STATE__'","STATE_NONCE = '"+state+"'","actual state");
  change("stage_execute.py","controls['count']==68","controls['count']==75","75 actual production controls count");
  change("stage_execute.py","len(controls['cases'])==68","len(controls['cases'])==75","75 actual cases count");
  files["check_install_binding.py"]=controls.source;
  const inherited=JSON.parse(parentInputRaw);
  need(h.sha(parentInputRaw)==="69f9e94437be48d509821970b5fd332a2531e0cce2123853591fa7e42f7a6c29","parent INPUTS raw");
  const inputs={
    schema:2,state:"ACTUAL_BUILD_AND_METADATA_BOUND_INSTALL_UNRUN",
    helper_package:"org.droidloom.qa."+slug+".r1",helper_uid:null,
    target:{package:target.package,uid:target.uid,user:0,version_code:target.version},
    commercial_artifact_reference:{bytes:h.utf8(files["target-artifact-reference.json"]).length,sha256:h.sha(files["target-artifact-reference.json"])},
    actual_independent_target_metadata:{bytes:target.bytes,sha256:target.sha256,git_blob:target.blob,git_tree:target.tree,job_id:target.job},
    build:{path:helper.outputRoot+"/build-result.json",bytes:buildOriginal.bytes,sha256:buildOriginal.sha256},
    build_stage:{path:helper.sourceRoot+"/stage-result.json",bytes:stageOriginal.bytes,sha256:stageOriginal.sha256},
    APK:actualBuild.APK,signer_certificate_sha256:actualBuild.signer_certificate_sha256,
    qa_source_manifest_sha256:actualBuild.source_manifest_sha256,
    current_host_source_root:inherited.current_host_source_root,
    current_host_source_manifest_sha256:inherited.current_host_source_manifest_sha256,
    current_host_stage:inherited.current_host_stage,current_baseline:inherited.current_baseline,
    nonces:{flow,state},
    actual_nonce_source:{...pin(nonceRaw),fields:labels,generator:"secrets.token_hex(16)",draws:6,no_redraw:true,exclusion_count:913,exclusion_sha256:n.excluded_compact_sha256,global_count_after:919},
    parent_source_helper_uid_exclusion:hb.parent_source_helper_uid_exclusion,
    ordered_worker_Android_commands:13,target_APK_count:target.apks,
    target_APK_streaming_hashes_before_and_after:true,
    target_user_and_user_de_identity_authority:"complete fixed successful metadata receipt, then live packages.list and two O_PATH directory identities",
    target_metadata_authority_separate_from_Main_baseline:true,immutable_baseline_packages_modified:false,
    own_package_absence_required_all_users_including_uninstalled:true,install_replace_existing:false,
    UiAutomation_requested:false,source_qualification_controls:75,
    Bili_Flow_or_MainBinding_instantiated:false,whole_process_tree_cleanup_qualified:false,
    framework_exit_cause_resolved:false,whole_app_production_ready:false,
    actual_static_controls:{baseline_scope:32,deep_tree_protocol:16},
    old_helpers_and_tasks_reauthorized:false,new_helper_business_input_authorized_by_installation:false,
    current_discovery:{...inherited.current_discovery,production_entry:"worker -> own open_context -> exact independent target metadata -> real current discovery -> held init/data/classes -> own Context"},
    original_install_source:{root:"/home/alex/work/pocket4-owned-bestbuy-qa-r4-install-state-02",request:pin(parentRequestRaw),source:"read-only derivation parent, no target or action authority reused"},
    install_success_assumed:false,automatic_retry:false,
    controls_execution_status:"NOT_RUN_IN_THIS_PREPARATION",
    action_lock_admission:"original five-second EX|NB deadline; no lock clearing or bypass"
  };
  files["INPUTS.json"]=pretty(inputs);
  files["README.md"]="# "+target.label+" R1 independent owned-helper install\n\n"+
    "This single request installs the new owned helper "+inputs.helper_package+" and reads its no-UiAutomation state. "+
    "The commercial target is "+target.package+", user 0, UID "+target.uid+", version "+target.version+", "+target.apks+" APK(s). "+
    "The helper UID remains unknown until the actual install/state receipts agree.\n\n"+
    "The full successful metadata receipt and built helper artifact reference are staged byte-for-byte. The own Context checks both source pins, "+
    "the full target UID/version/APK reference and both data-directory identities. It does not add packages or directories to the immutable Main baseline. "+
    "Original R6 source/guard, current discovery, held init, packages.list, two root/classpath checks, recorder and cleanup boundaries remain active.\n\n"+
    "The stage runs 75 controls: 68 inherited controls adapted to this fixed target and seven real authority/open_context routes with explicit synthetic "+
    "I/O boundaries. They reach the actual metadata loader, target-data verification, current discovery, Context/BoundArun construction and held-binding "+
    "record creation. They reject changed directory, source pin, Main observation and discovered init. These controls have not run during preparation "+
    "and do not claim real held descriptors or Android observations.\n\n"+
    "There are 13 ordered Android commands, exactly one fixed cmd package install -R -t --user 0 --pkg mutation. The others verify the commercial target, "+
    "helper absence/identity or one state invocation. The helper must be absent for all users, including retained uninstalled records. The original "+
    "action lock, once claim, worker budget, exact command policy, fresh APK hashes, state protocol, staging removal and FD/held cleanup remain. "+
    "No automatic retry, uninstall, commercial launch, UI, settings, permissions or audio operation is provided.\n\n"+
    "The actual six-value source assigns only this target's flow/state pair; all 913 prior values were excluded with one draw per label. "+
    "Values are retained after any failure. Failed or uncertain installation requires durable-evidence reconciliation. Installation gives no business "+
    "flow or whole-app qualification.\n";
  const expected=["INPUTS.json","README.md",slug+"_context.py",slug+"_transport.py","check_current_discovery.py","check_install_binding.py","current_discovery.py","host-stage-actual.json","host/source-manifest.json","install_state.py","make_request.py","references/target_metadata_parsers.py","stage_execute.py","target-artifact-reference.json","actual-target-metadata.json"].sort();
  need(canonical(Object.keys(files).sort())===canonical(expected),"exact fifteen runtime sources");
  for(const[name,raw]of Object.entries(files))need(typeof raw==="string"&&h.utf8(raw).length>0&&h.utf8(raw).length<=65536&&!raw.includes("__FRESH_INSTALL_"),"complete bound source:"+name);
  const manifest={schema:2,artifact:"pocket4-owned-"+slug+"-qa-r1-independent-current-install-source-v1",
    host_recorder_manifest_sha256:inherited.current_host_source_manifest_sha256,qa_source_manifest_sha256:actualBuild.source_manifest_sha256,
    actual_build:{bytes:buildOriginal.bytes,sha256:buildOriginal.sha256},actual_host_stage:inherited.current_host_stage,
    actual_independent_target_metadata:{bytes:target.bytes,sha256:target.sha256},
    files:Object.fromEntries(expected.map(name=>[name,{bytes:h.utf8(files[name]).length,sha256:h.sha(files[name])}]))};
  files["SOURCE_PINS.json"]=pretty(manifest);
  const sourcePin=h.sha(files["SOURCE_PINS.json"]);
  const packet={schema:2,source_manifest_sha256:sourcePin,nonce:flow,files};
  const payload=canonical(packet)+"\n";
  need(h.utf8(payload).length<=262144,"inherited packet bound");
  const stageSHA=manifest.files["stage_execute.py"].sha256;
  let wrapper="import hashlib,json,sys\nraw=sys.stdin.buffer.read(262145)\n";
  wrapper+="assert hashlib.sha256(raw).hexdigest()=='"+h.sha(payload)+"'\n";
  wrapper+="p=json.loads(raw);src=p['files']['stage_execute.py'].encode('utf-8')\n";
  wrapper+="assert hashlib.sha256(src).hexdigest()=='"+stageSHA+"'\n";
  wrapper+="scope={'__name__':'owned_qa_stage','__file__':'"+template.newRoot+"/source/stage_execute.py'}\n";
  wrapper+="exec(compile(src,scope['__file__'],'exec'),scope)\nraise SystemExit(scope['main'](raw))\n";
  exact(parentRequestRaw,{bytes:192074,sha256:"38286355f9e5d224ac757d9b84f0f2376be8a33befc06c9f9eee7b20c7415609",blob:"7bf195b13d6fa59f6ef9917908cfe0c85b529af2"},"unchanged parent request envelope");
  const request=JSON.parse(parentRequestRaw);
  need(request.host==="pocket4"&&request.executable==="/usr/bin/sudo"&&canonical(request.args.slice(0,-1))===canonical(["-n","/usr/bin/python3","-I","-B","-c"])&&request.timeout_seconds===300&&request.memory_max_bytes===536870912&&request.cpu_quota_percent===100&&request.nice===10,"inherited execution limits and interpreter");
  request.args[request.args.length-1]=wrapper;
  request.stdin=payload;
  request.idempotency_key=template.key;
  const requestRaw=JSON.stringify(ordered(request),null,2)+"\n";
  const inverse={...files};
  for(const edit of [...edits].reverse()) {
    need(inverse[edit.file].slice(edit.offset,edit.offset+edit.replacement.length)===edit.replacement,"binding inverse location");
    inverse[edit.file]=inverse[edit.file].slice(0,edit.offset)+edit.old+inverse[edit.file].slice(edit.offset+edit.replacement.length);
  }
  for(const[name,raw]of Object.entries(template.files))need(inverse[name]===raw,"bound to unbound source inverse:"+name);
  const proof={schema:"next3-independent-install-final-binding-v1",state:"FROZEN_ACTUAL_BOUND_INSTALL_UNRUN",
    helper_uid:null,target:inputs.target,control_count:75,Python_controls_executed:false,old_baseline_modified:false,
    nonce_actual:pin(nonceRaw),assigned_labels:labels,flow_nonce:flow,state_nonce:state,final_binding_edits:edits,
    inverse_to_unbound_template_exact:true,source_manifest:pin(files["SOURCE_PINS.json"]),packet:pin(payload),
    exact_request:pin(requestRaw),source_files:15,packet_files:16,ordered_commands:13,UI_or_commercial_launch:false};
  return {slug,files,manifest,inputs,actualBuild,packet,request,requestRaw,proof};
}
