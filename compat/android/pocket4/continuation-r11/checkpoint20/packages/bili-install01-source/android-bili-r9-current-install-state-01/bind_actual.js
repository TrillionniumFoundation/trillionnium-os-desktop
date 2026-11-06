function finalizeBiliR9Install(h,prepared,materials) {
  "use strict";
  const need=(v,c)=>{if(!v)throw Error(c);};
  const size=s=>h.utf8(s).length,pin=s=>({bytes:size(s),sha256:h.sha(s)});
  const canonical=v=>{
    if(v===null||typeof v!=="object")return JSON.stringify(v);
    if(Array.isArray(v))return"["+v.map(canonical).join(",")+"]";
    return"{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canonical(v[k])).join(",")+"}";
  };
  const read=(row,wanted)=>{
    need(row&&typeof row.raw==="string"&&Number.isSafeInteger(row.pin?.bytes)&&/^[a-f0-9]{64}$/.test(row.pin.sha256),
         "EXACT_ACTUAL_RAW_AND_EXTERNAL_PIN_REQUIRED");
    need(size(row.raw)===row.pin.bytes&&h.sha(row.raw)===row.pin.sha256,"ACTUAL_RAW_PIN_CHANGED");
    if(wanted)need(row.pin.bytes===wanted.bytes&&row.pin.sha256===wanted.sha256,"EXACT_FIXED_ACTUAL_REQUIRED");
    return JSON.parse(row.raw);
  };
  need(materials&&Object.keys(materials).sort().join(",")==="build,host_stage,nonces,stage","EXACT_CURRENT_INSTALL_ACTUAL_INPUT_SET");
  const build=read(materials.build,{bytes:32483,sha256:"fa75b7934ac2afe6b032b72234da2ccbb2755b97886197c050aa806eb972596b"});
  const stage=read(materials.stage,{bytes:1935,sha256:"2257ac9fe9b67d88fe92cde127bfe89855bd105a4839458ad707188ccf0d6772"});
  const host=read(materials.host_stage,{bytes:6851,sha256:"bbd21b3e83f39a355a44e32f3448f747d0e76a6cc79c8d920cac4c8399c986a0"});
  const nonces=read(materials.nonces);
  const labels=["bili_flow","bili_state","ihg_flow","ihg_state","amazon_flow","amazon_state","bestbuy_flow","bestbuy_state"];
  need(nonces.generator==="secrets.token_hex(16)"&&nonces.source_only_nonce_generation===true&&
       nonces.Android_commands===0&&nonces.UI_actions===0&&nonces.uid===1000&&
       canonical(nonces.labels)===canonical(labels)&&
       canonical(Object.keys(nonces.nonces).sort())===canonical([...labels].sort())&&
       Object.values(nonces.nonces).every(v=>typeof v==="string"&&/^[0-9a-f]{32}$/.test(v))&&
       new Set(Object.values(nonces.nonces)).size===8,
       "ACTUAL_EIGHT_DISTINCT_32HEX_NONCES_REQUIRED");
  const flowNonce=nonces.nonces.bili_flow,stateNonce=nonces.nonces.bili_state;
  need(!["fd9784f9e464119899726c3b583243a8","c296619272cb68fddb8923891ff0dff9"].includes(flowNonce)&&
       !["fd9784f9e464119899726c3b583243a8","c296619272cb68fddb8923891ff0dff9"].includes(stateNonce),
       "OLD_ISSUED_R8_NONCES_FORBIDDEN");
  const qaManifest=JSON.parse(prepared.qa_manifest_raw),hostManifest=JSON.parse(prepared.host_manifest_raw);
  need(h.sha(prepared.qa_manifest_raw)==="4eb11cf497615272c1bef280bbd849de4f983ba4147ea9356356dff076ce9c56"&&
       h.sha(prepared.host_manifest_raw)==="6d99374e1580083fd0f30b7f9b3c520306680760c97ad0d5400798fda427fb6e",
       "EXACT_QA_AND_CURRENT_HOST_SOURCE_REQUIRED");
  need(build.state==="BUILT_STATIC_VERIFIED_ANDROID_UNRUN"&&build.package==="org.droidloom.qa.bili.r9"&&
       build.source_manifest_sha256===h.sha(prepared.qa_manifest_raw)&&
       build.source_unchanged===true&&build.tools_unchanged===true&&build.error===null&&
       build.android_installed===false&&build.Android_UI_actions===0&&build.Main_mutations===0&&
       canonical(build.source_sha256)===canonical(Object.fromEntries(Object.entries(qaManifest.files).map(([n,p])=>[n,p.sha256]))),
       "ACTUAL_NEW_HELPER_SOURCE_OR_BUILD_SCOPE_REQUIRED");
  need(stage.state==="OWNED_QA_APK_STATIC_BUILD_PASS_ANDROID_UNRUN"&&stage.build_returncode===0&&stage.error===null&&
       Array.isArray(stage.secondary_errors)&&stage.secondary_errors.length===0&&
       stage.source_manifest_sha256===build.source_manifest_sha256&&
       canonical(stage.build_result)===canonical({path:"/home/alex/work/pocket4-owned-bili-qa-r9-build-02/build-result.json",...materials.build.pin}),
       "ACTUAL_BUILD_STAGE_BINDING_REQUIRED");
  const report=build.current_baseline_scope_controls?.report;
  need(report&&report.all_passed===true&&report.count===21&&report.cases.length===21&&
       report.cases.every(x=>x.passed===true)&&report.host_recorder_manifest_sha256===h.sha(prepared.host_manifest_raw),
       "ACTUAL_21_CURRENT_SESSION_CONTROLS_REQUIRED");
  need(host.ok===true&&host.source_stage_qualified===true&&host.current_runtime_admitted===false&&
       host.source_manifest_sha256===h.sha(prepared.host_manifest_raw)&&
       host.controls?.all_passed===true&&host.controls.count===26&&
       canonical(host.source_files)===canonical(hostManifest.files)&&
       host.owned_fds.acquired===18&&host.owned_fds.closed===18&&host.owned_fds.close_attempts===18&&
       host.owned_fds.remaining===0&&host.owned_fds.errors.length===0,
       "ACTUAL_CURRENT_HOST_SOURCE_QUALIFICATION_REQUIRED");
  need(build.APK.path==="/home/alex/work/pocket4-owned-bili-qa-r9-build-02/owned-bili-qa.apk"&&
       Number.isSafeInteger(build.APK.bytes)&&build.APK.bytes>0&&build.APK.bytes<=2097152&&
       /^[a-f0-9]{64}$/.test(build.APK.sha256)&&/^[a-f0-9]{64}$/.test(build.signer_certificate_sha256),
       "ACTUAL_SIGNED_APK_BINDING_REQUIRED");
  const values={FLOW_NONCE:flowNonce,STATE_NONCE:stateNonce,BUILD_SHA:materials.build.pin.sha256,
    BUILD_BYTES:materials.build.pin.bytes,STAGE_SHA:materials.stage.pin.sha256,STAGE_BYTES:materials.stage.pin.bytes,
    APK_SHA:build.APK.sha256,APK_BYTES:build.APK.bytes,SIGNER_SHA:build.signer_certificate_sha256,
    HOST_STAGE_SHA:materials.host_stage.pin.sha256,HOST_STAGE_BYTES:materials.host_stage.pin.bytes};
  const bind=src=>{
    for(const[k,v]of Object.entries(values))src=src.split("@@"+k+"@@").join(String(v));
    need(!src.includes("@@"),"PENDING_ACTUAL_BINDING_SLOT");
    return src;
  };
  const inputs={
    schema:2,state:"ACTUAL_R9_BUILD_AND_CURRENT_HOST_BOUND_INSTALL_NOT_RUN",
    helper_package:build.package,helper_uid:null,APK:build.APK,signer_certificate_sha256:build.signer_certificate_sha256,
    build:{path:stage.build_result.path,...materials.build.pin},
    build_stage:{path:"/home/alex/work/pocket4-owned-bili-qa-r9-source-02/stage-result.json",...materials.stage.pin},
    current_host_source_manifest_sha256:h.sha(prepared.host_manifest_raw),
    current_host_stage:materials.host_stage.pin,current_baseline:hostManifest.current_baseline,
    qa_source_manifest_sha256:build.source_manifest_sha256,
    nonces:{flow:flowNonce,state:stateNonce},actual_nonce_source:{...materials.nonces.pin,fields:["bili_flow","bili_state"],generator:nonces.generator},
    own_package_absence_required_all_users_including_uninstalled:true,install_replace_existing:false,
    state_UiAutomation_requested:false,ordered_worker_Android_commands:9,global_action_lock_seconds:5,
    source_qualification_controls:11,source_copies_current_host_files:14,
    helper_installed:false,whole_process_tree_cleanup_qualified:false,
    commercial_APK_full_acceptance_pending_fresh_flow:true,framework_exit_cause_resolved:false,whole_app_production_ready:false
  };
  const files={
    "install_state.py":bind(prepared.install_template),"stage_execute.py":bind(prepared.stage_template),
    "make_request.py":bind(prepared.make_template),"session_binding.py":prepared.session_source,
    "check_install_binding.py":prepared.control_source,"host/source-manifest.json":prepared.host_manifest_raw,
    "host-stage-actual.json":materials.host_stage.raw,"INPUTS.json":JSON.stringify(inputs,null,2)+"\n",
    "README.md":"# Bili R9 first current-baseline install and state\n\n"+
      "The exact signed APK from actual build02 is installed once with -R after all-users absence checks. "+
      "The actual R5 host source and its 26 controls, new helper 21 scope/Session controls, original 22 Java idle and 32 Python idle controls "+
      "are required. The exact 14 current host runtime files are copied into a fresh private source directory. "+
      "Initialization uses the typed current baseline; old deployment receipts are historical lineage only.\n\n"+
      "The original nine Android commands, action lock, held namespace entry, APK staging identity and independent FD cleanup remain. "+
      "One state request uses the new 32-hex actual nonce and does not connect UiAutomation. "+
      "No launch, inspect, text, player action, permissions or commercial data mutation is requested. "+
      "Failed or uncertain installation is not automatically retried or uninstalled. The owned helper UID is unknown until actual installation.\n\n"+
      "The coordinator guarantees only its directly owned child join; the native helper's whole-process-tree cleanup qualification remains false. "+
      "Current commercial APK business acceptance and the framework SIGKILL sender remain unresolved.\n"
  };
  const manifest={schema:2,artifact:"pocket4-owned-bili-qa-r9-current-host-install-source-v1",
    host_recorder_manifest_sha256:h.sha(prepared.host_manifest_raw),qa_source_manifest_sha256:build.source_manifest_sha256,
    actual_build:materials.build.pin,actual_host_stage:materials.host_stage.pin,
    files:Object.fromEntries(Object.entries(files).sort().map(([n,s])=>[n,pin(s)]))};
  files["SOURCE_PINS.json"]=JSON.stringify(manifest,null,2)+"\n";
  const manifestSHA=h.sha(files["SOURCE_PINS.json"]);
  const packet={schema:2,source_manifest_sha256:manifestSHA,nonce:flowNonce,files};
  const wire=canonical(packet)+"\n";need(size(wire)<=262144,"INSTALL_PACKET_BOUND");
  const stageSHA=h.sha(files["stage_execute.py"]);
  const root="/home/alex/work/pocket4-owned-bili-qa-r9-install-state-01";
  const wrapper="import hashlib,json,sys\nraw=sys.stdin.buffer.read(262145)\n"+
    "assert hashlib.sha256(raw).hexdigest()=='"+h.sha(wire)+"'\n"+
    "p=json.loads(raw);src=p['files']['stage_execute.py'].encode('utf-8')\n"+
    "assert hashlib.sha256(src).hexdigest()=='"+stageSHA+"'\n"+
    "scope={'__name__':'owned_qa_stage','__file__':'"+root+"/source/stage_execute.py'}\n"+
    "exec(compile(src,scope['__file__'],'exec'),scope)\nraise SystemExit(scope['main'](raw))\n";
  const request={host:"pocket4",executable:"/usr/bin/sudo",args:["-n","/usr/bin/python3","-I","-c",wrapper],
    cwd:"/home/alex/work",env:{PYTHONDONTWRITEBYTECODE:"1"},stdin:wire,
    idempotency_key:"pocket4-owned-bili-qa-r9-current-r5-install-state-01-20261106",
    timeout_seconds:300,cpu_quota_percent:100,memory_max_bytes:536870912,nice:10};
  return{files,manifest_sha256:manifestSHA,inputs,request,APK_already_built:true,installed:false,helper_uid:null,
    controls11_locally_executed:false,Hepta_dispatched:false};
}
