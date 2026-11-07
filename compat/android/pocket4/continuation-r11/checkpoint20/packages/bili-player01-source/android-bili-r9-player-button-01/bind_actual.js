function bindBiliR9Flow(h, lossless, input){
 const need=(v,c)=>{if(!v)throw Error(c)},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 const same=(a,b)=>canonical(a)===canonical(b);
 function canonical(v){return v===null?"null":Array.isArray(v)?"["+v.map(canonical).join(",")+"]":typeof v==="object"?"{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canonical(v[k])).join(",")+"}":JSON.stringify(v);}
 function check(row,name){need(row&&typeof row.raw==="string"&&same(pin(row.raw),row.pin),"EXACT_ACTUAL_PIN_REQUIRED:"+name);return JSON.parse(row.raw);}
 const oldQ=check(input.old_request,"old_request");
 need(same(input.old_request.pin,{bytes:133177,sha256:"ed6a2dc08fc96107b3124e073c79937f8da65a219456b3a4f2f36f2693a06128"}),"FIXED_R8_PARENT_REQUEST");
 const oldP=JSON.parse(oldQ.stdin),oldManifest=JSON.parse(oldP.files["SOURCE_PINS.json"]);
 need(h.sha(oldP.files["SOURCE_PINS.json"])===oldP.source_manifest_sha256&&Object.keys(oldManifest.files).length===6,"OLD_SIX_SOURCE_CLOSURE");
 for(const[n,p]of Object.entries(oldManifest.files))need(same(pin(oldP.files[n]),p),"OLD_SOURCE_PIN:"+n);
 const spec=check(input.nonce_spec,"nonce_spec"),pool=check(input.nonce_pool,"nonce_pool");
 need(spec.count===146&&spec.labels.length===146&&spec.exclude_values.length===155&&pool.schema==="pocket4-bili-r9-player-fresh-nonce-v1"&&pool.generator==="secrets.token_hex(16)"&&pool.count===146&&pool.exclude_count===155&&pool.all_distinct_and_excluded_old_values===true&&pool.source_only_nonce_generation===true&&pool.Android_commands===0&&pool.UI_actions===0&&pool.App_launches===0&&same(pool.spec,input.nonce_spec.pin)&&same(pool.labels,spec.labels),"ACTUAL_FRESH_NONCE_SOURCE");
 const fresh=spec.labels.map(l=>pool.nonces[l]);need(Object.keys(pool.nonces).length===146&&fresh.every(x=>typeof x==="string"&&/^[0-9a-f]{32}$/.test(x))&&new Set(fresh).size===146&&fresh.every(x=>!spec.exclude_values.includes(x)),"ALL_146_FRESH_DISTINCT_NONCES");
 const c=check(input.install.coordinator,"install coordinator"),s=check(input.install.stage,"install stage"),w=check(input.install.worker,"install worker"),cmd=check(input.install.worker_command,"install worker command");
 const state=check(input.state_command,"state command");
 need(Number.isInteger(input.state_command.index)&&input.state_command.index>=1&&input.state_command.index<=16,"ACTUAL_STATE_COMMAND_INDEX_REQUIRED");
 const isrc=input.install_source.files,im=JSON.parse(isrc["SOURCE_PINS.json"]),isha=h.sha(isrc["SOURCE_PINS.json"]);
 need(isha===input.install_source.manifest_sha256&&c.source_manifest_sha256===isha&&s.source_manifest_sha256===isha,"ACTUAL_INSTALL_SOURCE_MANIFEST");
 for(const[n,p]of Object.entries(im.files))need(same(pin(isrc[n]),p),"ACTUAL_INSTALL_SOURCE:"+n);
 const host=JSON.parse(isrc["host/source-manifest.json"]),hostSha=h.sha(isrc["host/source-manifest.json"]),scope=host.current_baseline;
 need(host.schema===2&&host.revision===5&&Object.keys(host.files).length===14&&hostSha===s.current_host_manifest_sha256&&hostSha===w.runtime_recorder_manifest_sha256,"ACTUAL_CURRENT_R5_INSTALL_HOST");
 const installRoot="/home/alex/work/pocket4-owned-bili-qa-r9-install-state-01",flowRoot="/home/alex/work/pocket4-bilibili-owned-qa-r9-flow-"+input.install_source.inputs.nonces.flow;
 need(c.flow===flowRoot&&c.nonce===s.nonce&&s.nonce===w.nonce&&w.nonce===input.install_source.inputs.nonces.flow&&w.state_nonce===input.install_source.inputs.nonces.state,"ACTUAL_INSTALL_FLOW_NONCE_CHAIN");
 need(same(c.worker_result,{path:flowRoot+"/steps/install-state-r9-01/result.json",...input.install.worker.pin})&&same(s.coordinator_result,{path:installRoot+"/result.json",...input.install.coordinator.pin}),"ACTUAL_FOUR_RECEIPT_CHAIN");
 need([c,s,w].every(r=>r.ok===true&&r.error===null&&same(r.secondary_errors,[]))&&s.coordinator_returncode===0&&s.source_unchanged===true&&c.source_and_artifact_unchanged===true&&s.packet_sha256===h.sha(input.install_source.request.stdin),"ACTUAL_INSTALL_COMPLETE_SUCCESS");
 const expectedMain=JSON.parse(isrc["host-stage-actual.json"]).Main_before;
 need([c.Main_before,c.Main_after,s.Main_before,s.Main_after,cmd.Main_after].every(m=>same(m,expectedMain))&&cmd.Main_before===true,"FIVE_ACTUAL_CURRENT_MAIN_MAPS");
 need(expectedMain.Main_epoch_sha256===scope.epoch_sha256&&expectedMain.current_baseline_sha256===scope.baseline_sha256&&expectedMain.current_baseline_qualification_sha256===scope.qualification_sha256&&expectedMain.seven_processes_match===true,"ACTUAL_MAIN_SCOPE");
 need(s.controls.all_passed===true&&s.controls.count===11&&s.controls.cases.length===11&&s.controls.cases.every(x=>x.passed===true)&&s.private_current_recorder_r5.private_copy_verified===true&&s.private_current_recorder_r5.files===14&&s.private_current_recorder_r5.all_runtime_bytes_equal_qualified_host===true,"ACTUAL_HOST_COPY_AND_INSTALL_CONTROLS");
 need(cmd.spawned===true&&cmd.joined===true&&cmd.returncode===0&&cmd.timed_out===false&&same(cmd.secondary_errors,[])&&cmd.name==="02-install-state"&&cmd.stderr.bytes===0&&cmd.stderr.sha256===h.sha(""),"ACTUAL_JOINED_INSTALL_WORKER");
 need(same(cmd.argv,["/usr/bin/python3","-I",installRoot+"/source/install_state.py","--worker-once","--source-manifest-sha256",isha]),"ACTUAL_INSTALL_WORKER_ARGV");
 const uid=w.owned_package_uid,self="org.droidloom.qa.bili.r9";
 need(Number.isInteger(uid)&&uid>=10000&&uid<100000&&![10117,10125,10164,10165,10166,10169,10170,10175,10184,10202,10204].includes(uid)&&c.owned_package_uid===uid&&w.package===self&&c.package===self,"ACTUAL_CURRENT_HELPER_UID");
 need(w.package===self&&c.package===self&&c.owned_package_retained_for_separate_UI_admission===true&&w.package_retained===true&&w.install_attempted===true&&w.install_success_observed===true&&w.state_attempted===true&&w.outcome_unknown===false&&w.final_Main_guard_passed===true&&w.held_binding_released===true&&w.action_lock_released===true&&w.UiAutomation_connection_requested===false&&w.UI_actions===0&&w.audio_actions===0,"ACTUAL_INSTALL_SCOPE_RETIRED");
 need(w.staging_cleanup.staged_apk_removed===true&&w.staging_cleanup.staged_directory_removed===true&&w.staging_cleanup.authority_fds_closed===true,"ACTUAL_STAGING_RETIRED");
 need(w.runtime_session_binding_sha256===h.sha(isrc["session_binding.py"])&&w.build.source_manifest_sha256===input.install_source.inputs.qa_source_manifest_sha256&&same(w.build.APK,input.install_source.inputs.APK)&&w.build.signer_certificate_sha256===input.install_source.inputs.signer_certificate_sha256,"ACTUAL_NEW_SIGNED_HELPER_AND_SOURCE");
 const nodes=lossless.losslessJsonNodes(input.install.worker.raw),installed=lossless.nodeField(nodes,["installed_before_state"]),after=lossless.nodeField(nodes,["installed_after_state"]);
 need(lossless.losslessCanonical(installed)===lossless.losslessCanonical(after),"LOSSLESS_INSTALLED_FILE_CHANGED");
 need(w.installed_before_state.package===self&&w.installed_before_state.uid===uid&&w.installed_before_state.apk_sha256===input.install_source.inputs.APK.sha256&&w.installed_before_state.bytes===input.install_source.inputs.APK.bytes&&w.installed_before_state.signer_bound_by_exact_signed_apk_bytes===input.install_source.inputs.signer_certificate_sha256,"ACTUAL_INSTALLED_APK_IDENTITY");
 const previous=w.state;
 need(input.state_command.pin.sha256===previous.recorder_command_result_sha256&&state.owned_command_joined===true&&state.spawned===true&&state.timed_out===false&&state.returncode===0&&same(state.errors,[])&&state.stdout_sha256===previous.stdout_sha256&&state.stderr_sha256===previous.stderr_sha256,"ACTUAL_STATE_COMMAND_RECEIPT");
 need(previous.actual_command_returncode===0&&previous.actual_instrumentation_finish_code===-1&&previous.held_transport_returned_after_post_guard===true&&previous.wire_sha256===c.state_wire_sha256&&previous.helper.ok===true&&previous.helper.error===null&&same(previous.helper.secondary_errors,[])&&previous.helper.self_uid===uid&&previous.helper.protocol==="pocket4-owned-bili-qa-v9"&&previous.helper.op==="state"&&previous.helper.nonce===w.state_nonce&&previous.helper.ui_automation_connected===false,"ACTUAL_NO_AUTOMATION_STATE");
 let files=Object.fromEntries(Object.keys(oldManifest.files).map(n=>[n,oldP.files[n]])),edits=[];
 function edit(file,a,b,n=1){const hits=files[file].split(a).length-1;need(hits===n,"EXACT_EDIT_ANCHOR:"+file+":"+a.slice(0,90)+":"+hits);files[file]=files[file].split(a).join(b);edits.push({file,old:a,next:b,count:n});}
 for(const row of spec.label_mapping){let hits=0;for(const file of Object.keys(files)){const found=files[file].split(row.old).length-1;if(found){edit(file,row.old,pool.nonces[row.label],found);hits+=found;}}need(hits>=1,"FRESH_NONCE_SOURCE_MISSING:"+row.label);}
 for(const file of Object.keys(files)){
  for(const[a,b]of [["pocket4-bilibili-r8-pause-resume-01","pocket4-bilibili-r9-pause-resume-01"],["pocket4-bilibili-owned-qa-r8-flow-","pocket4-bilibili-owned-qa-r9-flow-"],["R4_MANIFEST","R5_MANIFEST"]]){const n=files[file].split(a).length-1;if(n)edit(file,a,b,n);}
 }
 const nav="owned_navigation.py",stageFile="stage_execute.py",post="post_foreground.py";
 function constant(name,value){const re=new RegExp("^"+name+"=.*$","m"),m=files[nav].match(re);need(m,"NAV_CONSTANT:"+name);edit(nav,m[0],name+"="+value);}
 const py=x=>JSON.stringify(x),pypath=x=>"Path("+py(x)+")";
 edit(nav,"SELF,UID=('org.droidloom.qa.bili.r8',10204)","SELF,UID=("+py(self)+","+uid+")");
 constant("INSTALL_ROOT",pypath(installRoot));constant("INSTALL_ENTRY_SHA",py(h.sha(isrc["install_state.py"])));constant("INSTALL_ENTRY_BYTES",String(h.utf8(isrc["install_state.py"]).length));
 constant("INSTALL_MANIFEST_SHA",py(isha));constant("R5_MANIFEST",py(hostSha));constant("SESSION_SHA",py(h.sha(isrc["session_binding.py"])));
 constant("OLD_FLOW",pypath(flowRoot));constant("OLD_STEP","OLD_FLOW/'steps/install-state-r9-01'");
 constant("OLD_STATE_NONCE",py(w.state_nonce));constant("OLD_STATE_WIRE",py(previous.wire_sha256));constant("OLD_PACKET",py(s.packet_sha256));
 constant("MAIN_EPOCH",py(scope.epoch_sha256));constant("INSTALL_JOB_ID",py(input.install_job_id));
 constant("STATE_COMMAND_INDEX",String(input.state_command.index));constant("STATE_COMMAND_SHA",py(previous.recorder_command_result_sha256));
 constant("EXPECTED_INSTALLED_IDENTITY",lossless.losslessPython(installed));
 const paths={coordinator:installRoot+"/result.json",stage:installRoot+"/stage-result.json",worker:flowRoot+"/steps/install-state-r9-01/result.json",worker_command:installRoot+"/evidence/02-install-state.result.json"};
 constant("INSTALL_RECORDS","{"+Object.entries(paths).map(([name,path])=>py(name)+":("+pypath(path)+","+input.install[name].pin.bytes+","+py(input.install[name].pin.sha256)+")").join(",")+"}");
 edit(nav,"10175,10184,10202))","10175,10184,10202,10204))");
 edit(nav,"activation=json.loads(ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA))","activation=ref.current_baseline()");
 edit(stageFile,"activation=json.loads(ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA))","activation=ref.current_baseline()");
 edit(nav,"recorder.source_contract(R5_MANIFEST)[1].verify()\n  common=","source,contract=recorder.source_contract(R5_MANIFEST);contract.verify()\n  common=");
 edit(nav,"'--activation-after',str(ref.ACTIVATION),'--activation-sha256',ref.ACTIVATION_SHA,'--package',ref.PACKAGE,'--component',ref.COMPONENT",
          "'--current-baseline',str(ref.BASELINE),'--baseline-sha256',ref.BASELINE_SHA,'--package',source.PACKAGE,'--component',source.COMPONENT");
 edit(nav,"and(row['Main_before'].get('resource_limits_match')is True),'ACTUAL_INSTALL02_MAIN_CHAIN_REQUIRED')",
          "and(row['Main_before'].get('resource_limits_match')is True)and(row['Main_before'].get('schema')=='pocket4-current-main-guard-v1')and(row['Main_before'].get('seven_processes_match')is True)and(row['Main_before'].get('current_baseline_sha256')==prior.BASELINE_SHA)and(row['Main_before'].get('current_baseline_qualification_sha256')==prior.QUALIFICATION_SHA),'ACTUAL_INSTALL02_MAIN_CHAIN_REQUIRED')");
 edit(nav,"'owned_bili_r4_session'","'owned_bili_r5_session'");
 const oldEpoch="48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f";
 edit(post,oldEpoch,scope.epoch_sha256);
 edit(post,"'main_epoch_sha256':qa.MAIN_EPOCH})","'main_epoch_sha256':qa.MAIN_EPOCH,'main_baseline_schema':qa.MAIN_BASELINE_SCHEMA,'main_baseline_sha256':qa.MAIN_BASELINE_SHA,'main_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA})");
 for(const file of Object.keys(files)){
  for(const[a,b]of [["ACTUAL_R8","ACTUAL_R9"],["R8 ","R9 "],["INSTALL02_R4","INSTALL02_R5"]]){const n=files[file].split(a).length-1;if(n)edit(file,a,b,n);}
 }
 for(const file of Object.keys(files))need(!files[file].includes("ref.ACTIVATION")&&!files[file].includes("ref.PACKAGE")&&!files[file].includes("ref.COMPONENT"),"OLD_RUNTIME_REFERENCE:"+file);
 let back={...files};for(const e of [...edits].reverse()){need(back[e.file].split(e.next).length-1===e.count,"INVERSE_COUNT:"+e.file);back[e.file]=back[e.file].split(e.next).join(e.old);}
 need(Object.keys(back).every(n=>back[n]===oldP.files[n]),"FULL_FUNCTIONAL_LITERAL_INVERSE");
 const manifest={files:Object.fromEntries(Object.entries(files).sort().map(([n,v])=>[n,pin(v)])),schema:1};
 files["SOURCE_PINS.json"]=canonical(manifest)+"\n";
 const manifestSHA=h.sha(files["SOURCE_PINS.json"]),packet={files,nonce:pool.nonces.flow,schema:1,source_manifest_sha256:manifestSHA},wire=canonical(packet)+"\n";
 need(h.utf8(wire).length<=131072,"ORIGINAL_131072_PACKET_BOUND");
 need(Object.values(files).every(x=>h.utf8(x).length<=65536),"ORIGINAL_PER_SOURCE_BOUND");
 const root="/home/alex/work/pocket4-bilibili-r9-pause-resume-01";
 const wrapper="import hashlib,json,sys\nraw=sys.stdin.buffer.read(131073)\n"+
 "assert hashlib.sha256(raw).hexdigest()=='"+h.sha(wire)+"'\n"+
 "p=json.loads(raw);src=p['files']['stage_execute.py'].encode('utf-8')\n"+
 "assert hashlib.sha256(src).hexdigest()=='"+h.sha(files[stageFile])+"'\n"+
 "scope={'__name__':'owned_bili_inspect_stage','__file__':'"+root+"/source/stage_execute.py'}\n"+
 "exec(compile(src,scope['__file__'],'exec'),scope)\nraise SystemExit(scope['main'](raw))\n";
 const request={...oldQ,args:["-n","/usr/bin/python3","-I","-c",wrapper],stdin:wire,idempotency_key:"pocket4-bilibili-r9-current-player-button01-20261106"};
 return {files,manifest_sha256:manifestSHA,request,edits,proof:{full_inverse_to_exact_R8:true,
    nonce_count:146,all_new_nonce_values_from_actual:true,old_nonce_values_not_reused:true,
    actual_UID:uid,actual_installed_mtime_ns:lossless.nodeField(installed,["held_file","mtime_ns"]).raw,
    actual_four_install_originals:true,state_command_index:input.state_command.index,
    original_six_runtime_files:true,original_packet_bound_unchanged:true,packet_bytes:h.utf8(wire).length,
    packet_sha256:h.sha(wire),actual_helper_protocol:"pocket4-owned-bili-qa-v9",
    current_epoch:scope.epoch_sha256,current_baseline_sha256:scope.baseline_sha256,
    current_qualification_sha256:scope.qualification_sha256,host_manifest_sha256:hostSha,
    runtime_UI_not_dispatched:true,local_Python_controls:false,whole_app_production_ready:false}};
}
