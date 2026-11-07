function buildIHGR3Install(material,h) {
  function need(v,r){if(!v)throw Error(r);}
  const pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
  const stable=v=>Array.isArray(v)?v.map(stable):v&&typeof v==="object"?Object.fromEntries(Object.keys(v).sort().map(k=>[k,stable(v[k])])):v;
  const canonical=v=>JSON.stringify(stable(v));
  const pretty=v=>JSON.stringify(v,null,2)+"\n";
  const parent=material.parent,helper=material.helper;
  const build=JSON.parse(material.build_raw),stage=JSON.parse(material.stage_raw);
  need(pin(material.build_raw).bytes===25686&&pin(material.build_raw).sha256==="40a7f7865a962b3bdaee3242cfa1fb7d84d860a3fc973ebb344cbc01fe088505","ACTUAL_BUILD_PIN");
  need(pin(material.stage_raw).bytes===1935&&pin(material.stage_raw).sha256==="764ca6cb3d3b6ea21f1f0425c5d1028352a5db9450925935b42085bb9460df30","ACTUAL_STAGE_PIN");
  need(helper.manifest_sha256==="8d96686f9e6937548e0295679ae6ecdfd3c3a1bf4e48c5feff7def949e81789a"&&h.sha(helper.files["SOURCE_PINS.json"])===helper.manifest_sha256,"R3_SOURCE_PIN");
  const manifest=JSON.parse(helper.files["SOURCE_PINS.json"]);
  need(Object.keys(manifest.files).length===14,"FOURTEEN_SOURCE_FILES");
  for(const [name,row] of Object.entries(manifest.files))need(canonical(pin(helper.files[name]))===canonical(row),"SOURCE_PIN:"+name);
  const names=["javac","d8","aapt-package","align","create-owned-signing-key","sign","signature","alignment","badging","permissions","manifest"];
  need(build.state==="BUILT_STATIC_VERIFIED_ANDROID_UNRUN"&&build.package==="org.droidloom.qa.ihg.r3"&&build.error===null&&build.android_installed===false&&build.Main_mutations===0&&build.Android_UI_actions===0,"ACTUAL_BUILD_SCOPE");
  need(build.source_manifest_sha256===helper.manifest_sha256&&build.source_unchanged===true&&build.tools_unchanged===true,"ACTUAL_BUILD_CLOSURE");
  need(canonical(build.source_sha256)===canonical(Object.fromEntries(Object.entries(manifest.files).map(([k,v])=>[k,v.sha256]))),"ACTUAL_ALL_SOURCE_HASHES");
  need(canonical(build.tools_before)===canonical(build.tools_after)&&Object.keys(build.tools_before).length===7,"ACTUAL_TOOLS_CANONICAL");
  need(canonical(build.commands.map(x=>x.name))===canonical(names)&&build.commands.every(x=>x.returncode===0&&x.owned_child_joined===true&&x.error===null&&Array.isArray(x.secondary_errors)&&x.secondary_errors.length===0),"ACTUAL_ELEVEN_COMMANDS");
  function report(key,count,filename){
    const item=build[key],r=item&&item.report;
    need(item&&item.source_sha256===manifest.files[filename].sha256&&r&&r.all_passed===true&&r.count===count&&r.cases.length===count&&new Set(r.cases.map(x=>x.name)).size===count&&r.cases.every(x=>x.passed===true),"ACTUAL_CONTROLS:"+key);
    need(r.production_adapter_sha256===manifest.files["qa_adapter.py"].sha256&&r.production_contract_sha256===manifest.files["qa_contract.py"].sha256,"ACTUAL_PRODUCTION_CONTROL_BINDING:"+key);
    return r;
  }
  const scope=report("current_baseline_scope_controls",21,"check_current_baseline.py");
  const london=report("public_destination_input_controls",45,"check_destination_input.py");
  need(london.fixed_public_value==="London"&&london.protocol==="pocket4-owned-ihg-qa-v3"&&london.actual_installed_helper_uid===null&&london.Java_action_runtime_executed===false,"LONDON_STATIC_BOUNDARY");
  need(scope.main_epoch_sha256===parent.inputs.current_baseline.epoch_sha256&&scope.host_recorder_manifest_sha256===parent.inputs.current_host_source_manifest_sha256,"CURRENT_BASELINE_BINDING");
  need(stage.state==="OWNED_QA_APK_STATIC_BUILD_PASS_ANDROID_UNRUN"&&stage.source_manifest_sha256===helper.manifest_sha256&&stage.build_returncode===0&&stage.error===null&&stage.secondary_errors.length===0&&canonical(stage.build_result)===canonical({path:"/home/alex/work/pocket4-owned-ihg-qa-r3-build-01/build-result.json",...pin(material.build_raw)}),"ACTUAL_STAGE_LINKAGE");
  need(build.APK.path==="/home/alex/work/pocket4-owned-ihg-qa-r3-build-01/owned-ihg-qa.apk"&&build.APK.bytes===24720&&build.APK.sha256==="58a24079a59c998d35a7233ccadd2a1d3b90480aa9a66d2c4fc7905ca1d51342"&&build.signer_certificate_sha256==="df8c2febe4feff3e65d7dc096cad9753bfb2e97b57a65044b314c2a51c7c3f01","ACTUAL_APK_SIGNER");
  for(const r of [stage.owned_before,stage.owned_after]){
    need(r["memory.max"]==="536870912"&&r["memory.swap.max"]==="0"&&r["pids.max"]==="128"&&r["cpu.max"]==="100000 100000"&&r["memory.swap.current"]==="0"&&r["memory.swap.peak"]==="0","OWNED_RESOURCE_GATE");
    const events=Object.fromEntries(r["memory.events"].split("\n").map(x=>x.split(" ")));
    need(["max","oom","oom_kill","oom_group_kill"].every(k=>events[k]==="0"),"OWNED_RESOURCE_EVENTS");
  }
  need(stage.owned_before.device===stage.owned_after.device&&stage.owned_before.inode===stage.owned_after.inode&&stage.owned_before.cgroup===stage.owned_after.cgroup,"OWNED_RESOURCE_IDENTITY");
  need(parent.manifest_sha256==="e8cf9d4c04025bb092663519a01624fa40e552600dc5643a50ebf9bace915103"&&h.sha(parent.files["SOURCE_PINS.json"])===parent.manifest_sha256,"ACTUAL_INSTALL02_PARENT");
  const oldManifest=JSON.parse(parent.files["SOURCE_PINS.json"]);
  for(const [name,row] of Object.entries(oldManifest.files))need(canonical(pin(parent.files[name]))===canonical(row),"PARENT_PAYLOAD_PIN:"+name);
  need(material.nonce_source&&material.nonce_source.generator==="secrets.token_hex(16)"&&material.nonce_source.actual===true,"ACTUAL_FRESH_NONCE_SOURCE");
  const labels=["ihg_r3_install_flow","ihg_r3_install_state"];
  need(canonical(material.nonce_source.labels)===canonical(labels)&&material.nonce_source.values.length===2,"EXACT_TWO_NONCE_LABELS");
  const [flow,state]=material.nonce_source.values;
  need([flow,state].every(v=>/^[0-9a-f]{32}$/.test(v))&&flow!==state,"EXACT_FRESH_NONCE_SHAPE");
  const excludes=material.exclusions.excluded_values;
  need(excludes.length===38&&new Set(excludes).size===38&&[flow,state].every(v=>!excludes.includes(v)),"ALL_38_COMMITTED_NONCES_EXCLUDED");
  need(material.nonce_source.stdout&&Number.isInteger(material.nonce_source.stdout.bytes)&&material.nonce_source.stdout.bytes>0&&/^[0-9a-f]{64}$/.test(material.nonce_source.stdout.sha256),"ACTUAL_NONCE_RECEIPT_PIN");
  const root="/home/alex/work/pocket4-owned-ihg-qa-r3-install-state-01";
  const key="pocket4-owned-ihg-qa-r3-current-r5-install-state-01-20261106";
  const substitutions=[
    ["/home/alex/work/pocket4-owned-ihg-qa-r2-install-state-02",root],
    ["pocket4-owned-ihg-qa-r2-current-r5-install-state-02-20261106",key],
    ["/home/alex/work/pocket4-owned-ihg-qa-r2-source-02","/home/alex/work/pocket4-owned-ihg-qa-r3-source-01"],
    ["/home/alex/work/pocket4-owned-ihg-qa-r2-build-02","/home/alex/work/pocket4-owned-ihg-qa-r3-build-01"],
    ["org.droidloom.qa.ihg.r2","org.droidloom.qa.ihg.r3"],
    [parent.inputs.qa_source_manifest_sha256,helper.manifest_sha256],
    [parent.inputs.build.sha256,pin(material.build_raw).sha256],
    ["BUILD_BYTES = 20396","BUILD_BYTES = 25686"],
    [parent.inputs.build_stage.sha256,pin(material.stage_raw).sha256],
    ["STAGE_BYTES = 1930","STAGE_BYTES = 1935"],
    [parent.inputs.APK.sha256,build.APK.sha256],
    [parent.inputs.signer_certificate_sha256,build.signer_certificate_sha256],
    [parent.inputs.nonces.flow,flow],[parent.inputs.nonces.state,state],
    ["PREVIOUS_HELPER_UID = 10196","PREVIOUS_HELPER_UID = 10153"],
    ["uid not in (10137,10129,10117,10125,10164,10165,10166,10169,10170,10175)","uid not in (10137,10129,10117,10125,10164,10165,10166,10169,10170,10175,10196)"]
  ];
  const files={...parent.files};
  const edits=[];
  for(const n of ["install_state.py","stage_execute.py","make_request.py","ihg_context.py"]){
    let s=files[n];const applied=[];
    for(const [old,value] of substitutions){const count=s.split(old).length-1;if(count){s=s.split(old).join(value);applied.push({old,value,count});}}
    let inverse=s;for(const e of applied.slice().reverse())inverse=inverse.split(e.value).join(e.old);
    need(inverse===files[n],"PRODUCTION_LITERAL_INVERSE:"+n);
    files[n]=s;edits.push({file:n,replacements:applied,inverse_exact:true});
  }
  const planControls="\n    qa_manifest=json.loads(entry.read(entry.QA_ROOT/'SOURCE_PINS.json',131072,entry.QA_MANIFEST))\n"+
    "    qa=entry.module(entry.QA_ROOT/'qa_contract.py',qa_manifest['files']['qa_contract.py']['sha256'],'ihg_r3_install_plan_contract')\n"+
    "    entry.require(qa.SELF==entry.SELF=='org.droidloom.qa.ihg.r3' and\n"+
    "                  qa.PROTOCOL=='pocket4-owned-ihg-qa-v3','EXACT_R3_PLAN_CONTRACT')\n"+
    "    actual_plan=context.ordered_commands(qa,entry.SELF,entry.GUEST_APK,entry.STATE_NONCE)\n"+
    "    state_request={'protocol':qa.PROTOCOL,'nonce':entry.STATE_NONCE,'op':'state'}\n"+
    "    qa.validate_request(state_request)\n"+
    "    entry.require(len(actual_plan)==13 and actual_plan[0]==(context.LIST,15,False) and\n"+
    "                  actual_plan[1]==(context.PATHS,15,False) and\n"+
    "                  actual_plan[3]==(entry.INSTALL,40,True) and\n"+
    "                  actual_plan[7]==(qa.instrumentation_argv(state_request),20,False) and\n"+
    "                  sum(item[2] is True for item in actual_plan)==1,\n"+
    "                  'ACTUAL_R3_ORDERED_INSTALL_STATE_PLAN')\n"+
    "    yes('production_ordered_commands_actual_R3_contract_positive')\n"+
    "    rejected('production_ordered_commands_old_R2_package_rejected',lambda:context.ordered_commands(\n"+
    "        qa,'org.droidloom.qa.ihg.r2',entry.GUEST_APK,entry.STATE_NONCE))\n";
  need(files["check_install_binding.py"].split("CONTROL_COUNT = 38").length===2,"ORIGINAL_38_CONTROLS");
  files["check_install_binding.py"]=files["check_install_binding.py"].replace("CONTROL_COUNT = 38","CONTROL_COUNT = 40");
  const controlAnchor="    rows.extend(run_source_controls(entry,files,source_manifest_sha256))\n";
  need(files["check_install_binding.py"].split(controlAnchor).length===2,"CONTROL_INSERTION");
  files["check_install_binding.py"]=files["check_install_binding.py"].replace(controlAnchor,planControls+controlAnchor);
  const stageCounts="controls['count']==38 and\n            len(controls['cases'])==38";
  need(files["stage_execute.py"].split(stageCounts).length===2,"STAGE_CONTROL_COUNT");
  files["stage_execute.py"]=files["stage_execute.py"].replace(stageCounts,"controls['count']==40 and\n            len(controls['cases'])==40");
  edits.push({file:"check_install_binding.py",change:"Retain 38 existing cases and add two direct production ordered_commands R3 positive / old R2 package negative cases",new_case_count:2,actual_qa_source_only:true,no_Android_commands:true});
  edits.push({file:"stage_execute.py",change:"Require 40 controls after two production ordered-plan cases",old_count:38,new_count:40});
  const inputs=JSON.parse(parent.files["INPUTS.json"]);
  inputs.helper_package="org.droidloom.qa.ihg.r3";inputs.helper_uid=null;
  inputs.build={path:stage.build_result.path,...pin(material.build_raw)};
  inputs.build_stage={path:"/home/alex/work/pocket4-owned-ihg-qa-r3-source-01/stage-result.json",...pin(material.stage_raw)};
  inputs.APK=build.APK;inputs.signer_certificate_sha256=build.signer_certificate_sha256;
  inputs.qa_source_manifest_sha256=helper.manifest_sha256;
  inputs.nonces={flow,state};
  inputs.actual_nonce_source={bytes:material.nonce_source.stdout.bytes,sha256:material.nonce_source.stdout.sha256,fields:labels,generator:"secrets.token_hex(16)"};
  inputs.previous_helper_uid_exclusion={uid:10153,actual_worker_result:{bytes:12552,sha256:"81f25ba7fcced82ecc0534ce41f70b7b98ce1f152aa1e5e6c132db825d65fb58"},source:"Root actual IHG R2 install02 receipt"};
  inputs.retained_older_helper_uid_exclusions=[10196];
  inputs.source_qualification_controls=40;
  inputs.actual_static_controls={baseline_scope:21,public_destination_input:45,fixed_public_value:"London",Android_action_runtime_executed:false};
  inputs.new_helper_business_input_authorized_by_installation=false;
  files["INPUTS.json"]=pretty(inputs);
  files["README.md"]=parent.files["README.md"].replace("38 source controls run","40 source controls run").replace("33 existing source/context cases and five production verify_source cases","33 existing source/context cases, five production verify_source cases, and two direct production R3 ordered-plan cases")+"\nThis R3 successor binds the actual London-capable static build and new installation nonces. The prior R2 helper UID 10153 and older R1 UID 10196 are rejected. All 38 prior cases remain, with the actual R3 ordered_commands positive and old R2 package negative added before persistent staging. The same 13-command no-UiAutomation installation plan remains. Installation does not authorize an App input; a future current-tree qualified flow requires separate admission.\n";
  const manifestOut={...oldManifest,artifact:"pocket4-owned-ihg-qa-r3-current-install-source-v1",qa_source_manifest_sha256:helper.manifest_sha256,actual_build:pin(material.build_raw),files:{}};
  for(const name of Object.keys(oldManifest.files).sort())manifestOut.files[name]=pin(files[name]);
  files["SOURCE_PINS.json"]=pretty(manifestOut);
  const manifestSHA=h.sha(files["SOURCE_PINS.json"]);
  const packet={schema:2,source_manifest_sha256:manifestSHA,nonce:flow,files};
  const stdin=canonical(packet)+"\n";need(h.utf8(stdin).length<=262144,"INSTALL_PACKET_BOUND");
  const oldWrapper=parent.request.args[4];
  let wrapper=oldWrapper
    .split(h.sha(parent.request.stdin)).join(h.sha(stdin))
    .split(h.sha(parent.files["stage_execute.py"])).join(h.sha(files["stage_execute.py"]))
    .split("/home/alex/work/pocket4-owned-ihg-qa-r2-install-state-02").join(root);
  let inverseWrapper=wrapper
    .split(h.sha(stdin)).join(h.sha(parent.request.stdin))
    .split(h.sha(files["stage_execute.py"])).join(h.sha(parent.files["stage_execute.py"]))
    .split(root).join("/home/alex/work/pocket4-owned-ihg-qa-r2-install-state-02");
  need(inverseWrapper===oldWrapper,"OUTER_WRAPPER_INVERSE");
  const request={...parent.request,args:[...parent.request.args.slice(0,4),wrapper],stdin,idempotency_key:key};
  need(request.timeout_seconds===300&&request.memory_max_bytes===536870912&&request.cpu_quota_percent===100&&request.nice===10,"ORIGINAL_REQUEST_LIMITS");
  const unchanged=["ihg_transport.py","references/read_ihg.py","target-artifact-reference.json","host/source-manifest.json","host-stage-actual.json"];
  need(unchanged.every(n=>files[n]===parent.files[n]),"ALL_FIVE_UNCHANGED_REFERENCES");
  return {state:"SOURCE_FROZEN_NOT_DISPATCHED",root,key,files,inputs,manifest_sha256:manifestSHA,request,request_raw:JSON.stringify(stable(request),null,2)+"\n",edits,unchanged,actual_static_build:pin(material.build_raw),actual_static_stage:pin(material.stage_raw),helper_uid:null,Android_commands_in_generator:0,local_Python_executed:false};
}
