function prepareCell02AppInstall(app,parent,helper,host,qualifyHost,h){
 const need=(v,s)=>{if(!v)throw Error(app+":"+s)},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 need(["ihg","amazon","bestbuy"].includes(app),"THREE_CUSTOM_CONTEXT_APPS_ONLY");
 const oldFiles=parent.files,oldManifest=JSON.parse(oldFiles["SOURCE_PINS.json"]),oldInput=JSON.parse(oldFiles["INPUTS.json"]);
 for(const[n,p]of Object.entries(oldManifest.files))need(oldFiles[n]!==undefined&&pin(oldFiles[n]).bytes===p.bytes&&pin(oldFiles[n]).sha256===p.sha256,"PARENT_SOURCE_PIN:"+n);
 need(helper.app===app&&helper.revision===4&&helper.manifestSha===h.sha(helper.files["SOURCE_PINS.json"]),"NEW_HELPER_SOURCE");
 need(helper.binding.host_recorder_source_manifest.sha256===host.manifest_sha256&&
      host.manifest.artifact==="pocket4-bilibili-current-recorder-held-r6"&&
      host.binding.schema==="pocket4-main-current-baseline-v2","EXACT_NEW_HOST_HELPER_LINK");
 const contextName=app+"_context.py",transportName=app+"_transport.py";
 const names=["install_state.py",contextName,transportName,"stage_execute.py","make_request.py","check_install_binding.py"];
 const files=Object.fromEntries(names.map(n=>[n,oldFiles[n]])),edits=[];
 const replace=(name,old,next,count=null)=>{
   const got=files[name].split(old).length-1;
   need(old.length>0&&got>0&&(count===null||got===count),"ANCHOR:"+name+":"+old.slice(0,60)+":"+got);
   files[name]=files[name].split(old).join(next);edits.push({file:name,old,next,count:got});
 };
 const py=s=>"'"+s.replaceAll("\\","\\\\").replaceAll("'","\\'")+"'";
 const constant=(name,key,value)=>{
   const r=new RegExp("^"+key+"\\s*=.*$","m"),m=files[name].match(r);need(m,"CONSTANT:"+name+":"+key);
   replace(name,m[0],key+" = "+value,1);
 };
 const block=(raw,name)=>{
   const start=raw.search(new RegExp("^def "+name+"\\(","m"));need(start>=0,"FUNCTION:"+name);
   const tail=raw.slice(start+1),next=tail.search(/\n(?:def|class) [A-Za-z_]/);
   return raw.slice(start,next<0?raw.length:start+1+next+1);
 };
 const root="/home/alex/work/pocket4-owned-"+app+"-qa-r4-install-state-01";
 const key="pocket4-owned-"+app+"-qa-r4-current-r6-install-state-01-20261106";
 const self="org.droidloom.qa."+app+".r4",oldSelf=oldInput.helper_package;
 const oldPrevious=Number(files["install_state.py"].match(/^PREVIOUS_HELPER_UID\s*=\s*(\d+)$/m)[1]);
 const bindings={
   ROOT:"Path("+py(root)+")",NONCE:py("__ACTUAL_INSTALL_FLOW_NONCE__"),
   STATE_NONCE:py("__ACTUAL_INSTALL_STATE_NONCE__"),SELF:py(self),
   QA_ROOT:"Path("+py(helper.sourceRoot+"/source")+")",QA_MANIFEST:py(helper.manifestSha),
   BUILD:"Path("+py(helper.outputRoot+"/build-result.json")+")",
   BUILD_SHA:py("__ACTUAL_BUILD_SHA256__"),BUILD_BYTES:"None",
   STAGE:"Path("+py(helper.sourceRoot+"/stage-result.json")+")",
   STAGE_SHA:py("__ACTUAL_BUILD_STAGE_SHA256__"),STAGE_BYTES:"None",
   APK:"Path("+py(helper.outputRoot+"/owned-"+app+"-qa.apk")+")",
   APK_SHA:py("__ACTUAL_APK_SHA256__"),APK_BYTES:"None",
   SIGNER_SHA:py("__ACTUAL_SIGNER_SHA256__"),
   REFERENCE_SHA:py(host.manifest.files["current_coordinator.py"].sha256),
   BASE_HOST_ROOT:"Path('/home/alex/work/pocket4-current-host-r6-source-01')",
   RECORDER_MANIFEST:py(host.manifest_sha256),
   HOST_STAGE_SHA:py("__ACTUAL_HOST_STAGE_SHA256__"),HOST_STAGE_BYTES:"None",
   CURRENT_EPOCH:py(host.binding.epoch_sha256),BASELINE_SHA:py(host.binding.baseline_sha256),
   QUALIFICATION_SHA:py(host.binding.qualification_sha256),
   PREVIOUS_HELPER_UID:String(helper.oldInstall.uid)
 };
 for(const[k,v]of Object.entries(bindings))constant("install_state.py",k,v);
 const uid=block(files["install_state.py"],"uid_from"),match=uid.match(/uid not in \(([\d,]+)\)/);
 need(match,"UID_DENYLIST");const priorUIDs=match[1].split(",").map(Number);
 if(!priorUIDs.includes(oldPrevious))replace("install_state.py",match[0],"uid not in ("+[...priorUIDs,oldPrevious].join(",")+")",1);
 let verify=block(files["install_state.py"],"verify_source");
 const verifyNext=verify.replace("get('revision') == 5","get('revision') == 6").replace("pocket4-bilibili-current-recorder-held-r5","pocket4-bilibili-current-recorder-held-r6");
 need(verify!==verifyNext,"SOURCE_GATE_REVISION_CHANGE");replace("install_state.py",verify,verifyNext,1);
 replace("install_state.py",block(files["install_state.py"],"qualify_host_stage"),qualifyHost,1);
 const qualified=block(files["install_state.py"],"qualified_inputs");
 const qualifiedNext=qualified.replaceAll("pocket4-main-current-baseline-v1","pocket4-main-current-baseline-v2")
  .replaceAll("== 21","== 32").replace("ACTUAL_21_SCOPE_AND_HOST_SESSION_CONTROLS_REQUIRED","ACTUAL_32_SCOPE_AND_HOST_SESSION_CONTROLS_REQUIRED");
 need(qualifiedNext!==qualified&&!qualifiedNext.includes("== 21"),"HELPER_32_BINDING_GATE");
 replace("install_state.py",qualified,qualifiedNext,1);
 replace("install_state.py","['/usr/bin/python3','-I',str(HERE/'install_state.py')","['/usr/bin/python3','-I','-B',str(HERE/'install_state.py')",1);
 const contextBindings={
  INSTALLED_SHARED:"Path('/home/alex/work/pocket4-current-host-r6-source-01')",
  SHARED_MANIFEST:py(host.manifest_sha256),CONTRACT_SHA:py(host.manifest.files["source_contract.py"].sha256),
  CURRENT_EPOCH:py(host.binding.epoch_sha256),BASELINE_SHA:py(host.binding.baseline_sha256),
  QUALIFICATION_SHA:py(host.binding.qualification_sha256)
 };
 for(const[k,v]of Object.entries(contextBindings))constant(contextName,k,v);
 replace(contextName,oldSelf,self,1);
 replace(contextName,"pocket4-current-recorder-scope-v1","pocket4-current-recorder-scope-v2",2);
 replace(contextName,"pocket4-main-current-baseline-v1","pocket4-main-current-baseline-v2",2);
 replace(contextName,"current-framework-generation","current-cell-generation",1);
 constant(transportName,"FRAMEWORK_EPOCH_SHA256",py(host.binding.epoch_sha256));
 for(const[k,v]of Object.entries({ROOT:"Path("+py(root)+")",NONCE:py("__ACTUAL_INSTALL_FLOW_NONCE__"),
   REFERENCE_SHA:py(host.manifest.files["current_coordinator.py"].sha256),
   BASE_ROOT:"Path('/home/alex/work/pocket4-current-host-r6-source-01')",
   R5_MANIFEST:py(host.manifest_sha256)}))constant("stage_execute.py",k,v);
 replace("stage_execute.py","R5_MANIFEST","R6_MANIFEST");
 replace("stage_execute.py","get('revision')==5","get('revision')==6",1);
 replace("stage_execute.py","pocket4-bilibili-current-recorder-held-r5","pocket4-bilibili-current-recorder-held-r6",1);
 for(const[k,v]of Object.entries({KEY:py(key),ROOT:py(root),NONCE:py("__ACTUAL_INSTALL_FLOW_NONCE__")}))constant("make_request.py",k,v);
 replace("make_request.py","'-I','-c',wrapper","'-I','-B','-c',wrapper",1);
 const control="check_install_binding.py",oldControlCount=app==="ihg"?40:38,newControlCount=app==="ihg"?51:50;
 constant(control,"CONTROL_COUNT",String(newControlCount));
 replace(control,"v['owned_fds'].update(closed=v['owned_fds']['closed']-1)","v['source_fds'].update(closed=v['source_fds']['closed']-1)",1);
 replace(control,"v.update(source_published=False)","v.update(all_staged_sources_unchanged=False)",1);
 replace(control,"v['controls'].update(count=25)","v['controls'].update(count=37)",1);
 const extraHost = "    def host_no_exact(name,change,code):\n"+
 "        value=copy.deepcopy(actual_host);change(value)\n"+
 "        try:entry.qualify_host_stage(value,manifest)\n"+
 "        except RuntimeError as error:entry.require(str(error)==code,'R6_HOST_CONTROL_WRONG_FIRST_ERROR')\n"+
 "        else:raise RuntimeError('R6_HOST_NEGATIVE_ACCEPTED:'+name)\n"+
 "        yes(name)\n"+
 "    host_no_exact('previous_host_stage_schema_rejected',lambda v:v.update(schema='pocket4-current-host-source-stage-result-v1'),\n"+
 "                  'ACTUAL_COMPLETE_R6_HOST_SOURCE_STAGE_REQUIRED')\n"+
 "    host_no_exact('publication_FD_close_incomplete',lambda v:v['publication_fds'].update(closed=v['publication_fds']['closed']-1),\n"+
 "                  'ACTUAL_CURRENT_HOST_SOURCE_FDS_NOT_RETIRED')\n"+
 "    host_no_exact('published_source_leaf_drift',lambda v:v['source_pins']['recorder.py'].update(sha256='0'*64),\n"+
 "                  'ACTUAL_R6_PUBLISHED_SOURCE_PINS_REQUIRED')\n"+
 "    host_no_exact('unauthenticated_owner_chain',lambda v:v['Main_before'].update(authenticated_owner_chain_matches=False),\n"+
 "                  'CURRENT_HOST_STAGE_MAIN_FENCES_CHANGED')\n"+
 "    host_no_exact('current_user_namespace_mismatch',lambda v:v['Main_final'].update(current_user_namespaces_match=False),\n"+
 "                  'CURRENT_HOST_STAGE_MAIN_FENCES_CHANGED')\n"+
 "    host_no_exact('durable_host_stage_pin_drift',lambda v:v['stage_result'].update(sha256='0'*64),\n"+
 "                  'ACTUAL_R6_DURABLE_STAGE_PIN_REQUIRED')\n"+
 "    host_no_exact('compiled_source_name_changed',lambda v:v['controls']['compiled_sources'].__setitem__(0,'foreign.py'),\n"+
 "                  'ACTUAL_38_CURRENT_HOST_CONTROLS_REQUIRED')\n";
 replace(control,"    entry.require(entry.uid_from",extraHost+"    entry.require(entry.uid_from",1);
 replace(control,"    for field in ('BASELINE_SHA','QUALIFICATION_SHA'):",
 "    base_no('previous_current_baseline_schema_rejected',lambda v:v.update(schema='pocket4-main-current-baseline-v1'))\n"+
 "    base_no('previous_current_baseline_kind_rejected',lambda v:v.update(kind='current-framework-generation'))\n"+
 "    for field in ('BASELINE_SHA','QUALIFICATION_SHA'):",1);
 replace(control,"    def scope_no(name,change):",
 "    rejected('constructor_previous_R5_manifest',lambda:create(scope,'6d99374e1580083fd0f30b7f9b3c520306680760c97ad0d5400798fda427fb6e'))\n"+
 "    def scope_no(name,change):",1);
 if(app==="ihg"){
   replace(control,"qa.SELF==entry.SELF=='org.droidloom.qa.ihg.r3'","qa.SELF==entry.SELF=='org.droidloom.qa.ihg.r4'",1);
   replace(control,"qa.PROTOCOL=='pocket4-owned-ihg-qa-v3'","qa.PROTOCOL=='pocket4-owned-ihg-qa-v4'",1);
   for(const [old,next]of [
     ["ihg_r3_install_plan_contract","ihg_r4_install_plan_contract"],
     ["EXACT_R3_PLAN_CONTRACT","EXACT_R4_PLAN_CONTRACT"],
     ["ACTUAL_R3_ORDERED_INSTALL_STATE_PLAN","ACTUAL_R4_ORDERED_INSTALL_STATE_PLAN"],
     ["production_ordered_commands_actual_R3_contract_positive","production_ordered_commands_actual_R4_contract_positive"]
   ])replace(control,old,next,1);
   replace(control,"    rows.extend(run_source_controls",
    "    rejected('production_ordered_commands_previous_R3_package_rejected',lambda:context.ordered_commands(\n"+
    "        qa,'org.droidloom.qa.ihg.r3',entry.GUEST_APK,entry.STATE_NONCE))\n"+
    "    rows.extend(run_source_controls",1);
 }else{
  const plan="    qa_manifest=json.loads(entry.read(entry.QA_ROOT/'SOURCE_PINS.json',131072,entry.QA_MANIFEST))\n"+
 "    qa=entry.module(entry.QA_ROOT/'qa_contract.py',qa_manifest['files']['qa_contract.py']['sha256'],'"+app+"_r4_install_plan_contract')\n"+
 "    entry.require(qa.SELF==entry.SELF=='"+self+"' and\n"+
 "                  qa.PROTOCOL=='pocket4-owned-"+app+"-qa-v4','EXACT_R4_PLAN_CONTRACT')\n"+
 "    actual_plan=context.ordered_commands(qa,entry.SELF,entry.GUEST_APK,entry.STATE_NONCE)\n"+
 "    state_request={'protocol':qa.PROTOCOL,'nonce':entry.STATE_NONCE,'op':'state'}\n"+
 "    qa.validate_request(state_request)\n"+
 "    entry.require(len(actual_plan)==13 and actual_plan[0]==(context.LIST,15,False) and\n"+
 "                  actual_plan[1]==(context.PATHS,15,False) and actual_plan[3]==(entry.INSTALL,40,True) and\n"+
 "                  actual_plan[7]==(qa.instrumentation_argv(state_request),20,False) and\n"+
 "                  sum(item[2] is True for item in actual_plan)==1,'ACTUAL_R4_ORDERED_INSTALL_STATE_PLAN')\n"+
 "    yes('production_ordered_commands_actual_R4_contract_positive')\n"+
 "    rejected('production_ordered_commands_previous_R3_package_rejected',lambda:context.ordered_commands(\n"+
 "        qa,'org.droidloom.qa."+app+".r3',entry.GUEST_APK,entry.STATE_NONCE))\n";
  replace(control,"    rows.extend(run_source_controls",plan+"    rows.extend(run_source_controls",1);
 }
 for(const [old,next]of [
   ["actual_R5_reference_read_only","actual_R6_reference_read_only"],
   ["production_verify_source_actual_R5_reference_positive","production_verify_source_actual_R6_reference_positive"],
   ["production_verify_source_missing_R5_coordinator_rejected","production_verify_source_missing_R6_coordinator_rejected"],
   ["production_verify_source_wrong_R5_coordinator_hash_rejected","production_verify_source_wrong_R6_coordinator_hash_rejected"]
 ])replace(control,old,next,1);
 const oldCountToken="controls['count']=="+oldControlCount,newCountToken="controls['count']=="+newControlCount;
 replace("stage_execute.py",oldCountToken,newCountToken,1);
 replace("stage_execute.py","len(controls['cases'])=="+oldControlCount,"len(controls['cases'])=="+newControlCount,1);
 const reverse={...files};
 for(const e of [...edits].reverse()){
   need(reverse[e.file].split(e.next).length-1===e.count,"INVERSE_ANCHOR:"+e.file+":"+e.next.slice(0,70));
   reverse[e.file]=reverse[e.file].split(e.next).join(e.old);
 }
 for(const name of names)need(reverse[name]===oldFiles[name],"COMPLETE_PRODUCTION_INVERSE:"+name);
 const target=JSON.parse(oldFiles["target-artifact-reference.json"]);
 const targetCount=target.artifacts.length;
 need(targetCount===(app==="ihg"?1:3),"ACTUAL_TARGET_APK_COUNT");
 return {schema:"pocket4-cell02-install-source-template-v1",app,root,key,self,templates:files,
   original_sources:Object.fromEntries(names.map(n=>[n,oldFiles[n]])),edits,complete_inverse_exact:true,
   parent_source_manifest:pin(oldFiles["SOURCE_PINS.json"]),parent_request:{...pin(parent.request_raw),git_blob:h.git(parent.request_raw),exact_original_raw:true},
   helper_manifest_sha256:helper.manifestSha,host_manifest_sha256:host.manifest_sha256,
   controls_expected:newControlCount,previous_helper:helper.oldInstall,older_previous_uid_retained:oldPrevious,
   target_reference:oldFiles["target-artifact-reference.json"],target_APK_count:targetCount,
   readonly_reader:oldFiles["references/read_"+app+".py"],current_baseline:host.binding,
   pending:["actual_host_stage","actual_helper_build","actual_helper_build_stage","actual_APK","actual_signer","two_actual_install_nonces"],
   bound_request_created:false,Python_executed:false,Android_actions:0,helper_uid:null};
}

function qualifyCell02HostActual(actual,host,h){
 const need=(v,s)=>{if(!v)throw Error(s)},canonical=v=>v===null?"null":Array.isArray(v)?"["+v.map(canonical).join(",")+"]":
 typeof v==="object"?"{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canonical(v[k])).join(",")+"}":JSON.stringify(v);
 need(h.utf8(actual.raw).length===actual.bytes&&h.sha(actual.raw)===actual.sha256&&h.git(actual.raw)===actual.blob,"ACTUAL_HOST_FULL_PIN");
 const v=JSON.parse(actual.raw),m=host.manifest;
 need(v.schema==="pocket4-current-host-source-stage-v2"&&v.ok===true&&v.error===null&&Array.isArray(v.secondary_errors)&&v.secondary_errors.length===0&&
 v.actual_source_constructor_qualified===true&&v.all_staged_sources_unchanged===true,"ACTUAL_R6_COMPLETE_STAGE");
 const root="/home/alex/work/pocket4-current-host-r6-source-01";
 need(v.source_root===root&&v.source_manifest_sha256===host.manifest_sha256&&m.revision===6,"HOST_SOURCE_BINDING");
 const expected=Object.fromEntries(Object.entries(m.files).map(([n,p])=>[n,{path:root+"/"+n,...p}]));
 expected["source-manifest.json"]={path:root+"/source-manifest.json",bytes:h.utf8(host.manifestRaw).length,sha256:host.manifest_sha256};
 need(canonical(v.source_pins)===canonical(expected),"ALL_FIFTEEN_HOST_PUBLISHED_PINS");
 const c=v.controls,caseNames=[...host.controlsSource.matchAll(/(?:passed|negative|constructor_no)\("([^"]+)"/g)].map(x=>x[1]);
 need(caseNames.length===38&&new Set(caseNames).size===38&&c.schema==="pocket4-current-host-source-controls-v2"&&c.all_passed===true&&
 c.count===38&&c.cases.length===38&&c.cases.every(x=>x.passed===true)&&
 canonical(c.cases.map(x=>x.name))===canonical(caseNames)&&canonical(c.compiled_sources)===canonical(Object.keys(m.files).sort()),"EXACT_38_CONTROLS_AND_FOURTEEN_COMPILES");
 need(c.fixture_is_not_baseline_observation===true&&["Android_commands","UI_actions","children","filesystem_operations"].every(k=>c[k]===0),"PURE_HOST_SOURCE_CONTROLS_SCOPE");
 for(const n of ["source_fds","publication_fds"]){
  const x=v[n];need(x.scope==="collector_managed_descriptors"&&["acquired","close_attempts","closed","remaining"].every(k=>Number.isInteger(x[k]))&&
  x.acquired>0&&x.acquired===x.close_attempts&&x.closed===x.acquired&&x.remaining===0&&Array.isArray(x.errors)&&x.errors.length===0,"HOST_FD_CLOSE:"+n);
 }
 const g={schema:"pocket4-current-main-guard-v2",Main_epoch_sha256:host.binding.epoch_sha256,current_baseline_sha256:host.binding.baseline_sha256,
 current_baseline_qualification_sha256:host.binding.qualification_sha256,
 historical_activation_sha256:host.binding.historical_activation_sha256,historical_verified_sha256:host.binding.historical_verified_sha256,
 previous_current_baseline_sha256:"163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266",
 config_sha256:"f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc",
 seven_processes_match:true,three_host_processes_match:true,authenticated_owner_chain_matches:true,current_user_namespaces_match:true,
 resource_limits_match:true,current_executable_and_root_backing_match:true,old_helpers_and_tasks_reauthorized:false,
 framework_exit_cause_resolved:false,production_ready:false};
 need(["Main_before","Main_after","Main_final"].every(k=>canonical(v[k])===canonical(g)),"ACTUAL_CURRENT_GUARDS");
 need(v.source_only===true&&v.runtime_admitted===false&&v.namespace_entry===false&&v.old_helpers_and_tasks_reauthorized===false&&
 v.whole_app_production_ready===false&&["Android_commands","UI_actions","helper_installs","App_launches","children_spawned"].every(k=>v[k]===0),"STAGE_ONLY_SCOPE");
 const durable={...v};delete durable.stage_result;delete durable.publication_fds;
 const durableRaw=canonical(durable)+"\n";
 need(canonical(v.stage_result)===canonical({path:root+"/stage-result.json",bytes:h.utf8(durableRaw).length,sha256:h.sha(durableRaw)}),"ACTUAL_PUBLISHER_DURABLE_STAGE_PIN");
 return {actual:{bytes:actual.bytes,sha256:actual.sha256,git_blob:actual.blob,tree:actual.tree,job:actual.job},source_root:root,manifest_sha256:host.manifest_sha256,
 all_38_cases_and_14_compiles:true,all_15_published_pins:true,source_fds:v.source_fds,publication_fds:v.publication_fds,
 actual_Main:g,durable_stage_pin:v.stage_result,durable_reconstructed_from_exact_stdout_not_private_path_reread:true,
 source_stage_qualified:true,runtime_admitted:false,old_helpers_and_tasks_reauthorized:false,Python_executed_by_this_qualifier:false};
}

function qualifyCell02HelperBuild(app,helper,buildActual,stageActual,host,h,ll){
 const need=(v,s)=>{if(!v)throw Error(app+":"+s)},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 const canonical=v=>v===null?"null":Array.isArray(v)?"["+v.map(canonical).join(",")+"]":typeof v==="object"?
  "{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canonical(v[k])).join(",")+"}":JSON.stringify(v);
 for(const [name,x]of [["build",buildActual],["stage",stageActual]]){
  need(x&&typeof x.raw==="string"&&Number.isInteger(x.bytes)&&x.bytes>0&&h.utf8(x.raw).length===x.bytes&&h.sha(x.raw)===x.sha256&&
   typeof x.blob==="string"&&h.git(x.raw)===x.blob,"ACTUAL_FULL_PIN:"+name);
 }
 const build=JSON.parse(buildActual.raw),stage=JSON.parse(stageActual.raw);
 const bn=ll.losslessJsonNodes(buildActual.raw),sn=ll.losslessJsonNodes(stageActual.raw);
 const sameField=(node,a,b)=>ll.losslessCanonical(ll.nodeField(node,a))===ll.losslessCanonical(ll.nodeField(node,b));
 const m=JSON.parse(helper.files["SOURCE_PINS.json"]);
 need(helper.app===app&&helper.manifestSha===h.sha(helper.files["SOURCE_PINS.json"])&&
  helper.binding.host_recorder_source_manifest.sha256===host.manifest_sha256,"FIXED_HELPER_SOURCE_AND_R6_LINK");
 for(const[n,p]of Object.entries(m.files))need(canonical(pin(helper.files[n]))===canonical(p),"EXACT_HELPER_FILE:"+n);
 need(build.state==="BUILT_STATIC_VERIFIED_ANDROID_UNRUN"&&build.package===helper.binding.helper_package&&
  build.source_manifest_sha256===helper.manifestSha&&build.source_unchanged===true&&build.tools_unchanged===true&&
  build.error===null&&build.android_installed===false&&build.Main_mutations===0&&build.Android_UI_actions===0,"ACTUAL_STATIC_BUILD_SCOPE");
 need(canonical(build.source_sha256)===canonical(Object.fromEntries(Object.entries(m.files).map(([n,p])=>[n,p.sha256]))),"ACTUAL_ALL_SOURCE_HASHES");
 const builder=helper.files["build_candidate.py"],adapter=helper.files["qa_adapter.py"];
 const namesRaw=adapter.match(/^BUILD_COMMANDS = (\[[\s\S]*?\])/m);
 need(namesRaw,"BUILD_COMMAND_NAMES_SOURCE");const commandNames=JSON.parse(namesRaw[1].replaceAll("'","\""));
 need(canonical(build.commands.map(x=>x.name))===canonical(commandNames)&&build.commands.every(x=>
  x.returncode===0&&x.owned_child_joined===true&&x.error===null&&Array.isArray(x.secondary_errors)&&x.secondary_errors.length===0),"ACTUAL_ALL_COMMANDS_JOINED");
 const constants={};for(const n of ["JDK","SDK_BASE"]){const x=builder.match(new RegExp("^"+n+" = '([^']+)'","m"));need(x,"TOOL_SOURCE_CONSTANT");constants[n]=x[1];}
 const toolsBlock=builder.match(/^TOOLS = \{([\s\S]*?)^\}/m);need(toolsBlock,"EXACT_TOOL_BLOCK");
 const toolRows=[...toolsBlock[1].matchAll(/'([^']+)': \((?:(JDK|SDK_BASE) \+ )?'([^']+)', '([0-9a-f]{64})'\)/g)];
 need(toolRows.length===7&&Object.keys(build.tools_before).length===7&&sameField(bn,["tools_before"],["tools_after"]),"LOSSLESS_ALL_TOOL_INPUTS_UNCHANGED");
 for(const x of toolRows){const actual=build.tools_before[x[1]],path=(x[2]?constants[x[2]]:"")+x[3];
  need(actual&&actual.declared_path===path&&actual.sha256===x[4]&&Number.isSafeInteger(actual.bytes)&&actual.bytes>0,"ACTUAL_TOOL_IDENTITY:"+x[1]);}
 const expectedContract={package:helper.binding.helper_package,instrumentation:helper.binding.helper_package+".ActionRunner",target_package:helper.binding.helper_package,
  compile_sdk_api:31,min_sdk:31,target_sdk:33,debuggable:false,test_only:true,permissions:[],activities:[],services:[],receivers:[],providers:[],native_libraries:[]};
 need(canonical(build.manifest_contract)===canonical(expectedContract),"SELF_INSTRUMENTATION_MANIFEST_CONTRACT");
 const scope=build.current_baseline_scope_controls,s=scope&&scope.report;
 need(scope&&scope.source_sha256===m.files["check_current_baseline.py"].sha256&&s&&s.schema==="pocket4-current-baseline-scope-controls-v2"&&
  s.all_passed===true&&s.count===32&&s.cases.length===32&&new Set(s.cases.map(x=>x.name)).size===32&&s.cases.every(x=>x.passed===true)&&
  s.production_contract_sha256===m.files["qa_contract.py"].sha256&&s.production_adapter_sha256===m.files["qa_adapter.py"].sha256&&
  s.host_recorder_manifest_sha256===host.manifest_sha256&&s.main_epoch_sha256===host.binding.epoch_sha256&&
  s.main_baseline_schema===host.binding.schema&&s.main_baseline_sha256===host.binding.baseline_sha256&&
  s.main_baseline_qualification_sha256===host.binding.qualification_sha256&&s.Android_commands===0&&s.UI_actions===0&&s.helper_installed_uid===null,
  "ACTUAL_32_CURRENT_BASELINE_CONTROLS");
 const appControls={baseline_scope:32};
 if(app==="ihg"){
  const item=build.public_destination_input_controls,r=item&&item.report;
  need(item&&item.source_sha256===m.files["check_destination_input.py"].sha256&&r&&r.all_passed===true&&r.count===45&&
   r.cases.length===45&&new Set(r.cases.map(x=>x.name)).size===45&&r.cases.every(x=>x.passed===true)&&
   r.production_contract_sha256===m.files["qa_contract.py"].sha256&&r.production_adapter_sha256===m.files["qa_adapter.py"].sha256&&
   r.protocol===helper.binding.protocol&&r.fixed_public_value==="London"&&r.actual_installed_helper_uid===null&&
   r.Java_action_runtime_executed===false&&r.Android_commands===0&&r.UI_actions===0,"ACTUAL_45_LONDON_PROTOCOL_CONTROLS");
  appControls.public_destination_input=45;
 }else if(app==="bestbuy"){
  const r=build.deep_tree_protocol_controls;
  need(r&&r.state==="PASS_PROTOCOL_CONTROLS_ONLY"&&r.cases===16&&r.max_depth===128&&r.Java_scanner_executed===false&&r.Android_actions===0,
   "ACTUAL_16_COMPLETE_TREE_PROTOCOL_CONTROLS");
  appControls.deep_tree_protocol=16;
 }else if(app==="amazon"||app==="bili"){
  for(const [field,listName,count,controlFile]of [
    ["inspection_idle_gate_controls","IDLE_GATE_CASES",22,"tests/InspectionIdleGateChecks.java"],
    ["inspection_idle_protocol_controls","IDLE_PROTOCOL_CASES",32,"check_idle_contract.py"]]){
   const text=builder.match(new RegExp("^"+listName+" = (\\[[\\s\\S]*?\\])","m"));need(text,"FIXED_IDLE_NAMES");
   const names=JSON.parse(text[1]),item=build[field],r=item&&item.report;
   need(names.length===count&&item&&item.control_source_sha256===m.files[controlFile].sha256&&r&&r.schema===1&&r.all_passed===true&&r.count===count&&
    canonical(r.cases)===canonical(names.map(name=>({name,passed:true})))&&r.android_calls===0&&r.tree_captures===0&&r.input_actions===0,"ACTUAL_IDLE_CONTROLS:"+field);
   if(count===32)need(r.production_contract_sha256===m.files["qa_contract.py"].sha256,"IDLE_PRODUCTION_CONTRACT");
   else need(item.gate_source_sha256===m.files["src/org/droidloom/qa/"+app+"/r"+helper.revision+"/InspectionIdleGate.java"].sha256&&
    /^[0-9a-f]{64}$/.test(item.stdout_sha256),"IDLE_GATE_SOURCE_AND_OUTPUT");
  }
  appControls.Java_idle=22;appControls.Python_idle=32;
 }else need(false,"UNKNOWN_HELPER_APP");
 need(stage.state==="OWNED_QA_APK_STATIC_BUILD_PASS_ANDROID_UNRUN"&&stage.source_manifest_sha256===helper.manifestSha&&
  stage.build_returncode===0&&stage.error===null&&Array.isArray(stage.secondary_errors)&&stage.secondary_errors.length===0&&
  stage.root===helper.sourceRoot&&stage.source===helper.sourceRoot+"/source"&&stage.output===helper.outputRoot&&
  canonical(stage.build_result)===canonical({path:helper.outputRoot+"/build-result.json",...pin(buildActual.raw)}),"ACTUAL_BUILD_STAGE_LINK");
 const apk=build.APK;
 need(apk&&apk.path===helper.outputRoot+"/owned-"+app+"-qa.apk"&&Number.isSafeInteger(apk.bytes)&&apk.bytes>0&&apk.bytes<=2097152&&
  /^[0-9a-f]{64}$/.test(apk.sha256)&&/^[0-9a-f]{64}$/.test(build.signer_certificate_sha256),"ACTUAL_APK_SIGNER");
 for(const x of [stage.owned_before,stage.owned_after]){
  need(x&&x["memory.max"]==="536870912"&&x["memory.swap.max"]==="0"&&x["pids.max"]==="128"&&
   x["cpu.max"]==="100000 100000"&&x["memory.swap.current"]==="0"&&x["memory.swap.peak"]==="0","BUILD_OWNED_RESOURCE_LIMITS");
  const events=Object.fromEntries(x["memory.events"].trim().split("\n").map(x=>x.split(" ")));
  need(["max","oom","oom_kill","oom_group_kill"].every(k=>events[k]==="0"),"BUILD_RESOURCE_EVENTS");
 }
 for(const k of ["device","inode","cgroup"])need(sameField(sn,["owned_before",k],["owned_after",k]),"LOSSLESS_BUILD_CGROUP_IDENTITY:"+k);
 return {app,build:{path:helper.outputRoot+"/build-result.json",...pin(buildActual.raw),git_blob:buildActual.blob},
  stage:{path:helper.sourceRoot+"/stage-result.json",...pin(stageActual.raw),git_blob:stageActual.blob},
  APK:{path:apk.path,bytes:apk.bytes,sha256:apk.sha256},signer_certificate_sha256:build.signer_certificate_sha256,
  source_manifest_sha256:helper.manifestSha,host_manifest_sha256:host.manifest_sha256,commands:commandNames.length,actual_controls:appControls,
  tools_lossless_equal:true,all_source_files_exact:true,old_helpers_and_tasks_reauthorized:false,
  installed:false,helper_uid:null,Android_UI_actions:0,whole_app_production_ready:false};
}

function qualifyCell02InstallNonces(actual,exclusions,h){
 const need=(v,s)=>{if(!v)throw Error(s)};
 need(actual&&typeof actual.raw==="string"&&actual.bytes===h.utf8(actual.raw).length&&actual.sha256===h.sha(actual.raw)&&actual.blob===h.git(actual.raw),"ACTUAL_INSTALL_NONCE_FULL_PIN");
 const v=JSON.parse(actual.raw),labels=["bili_r10_install_flow","bili_r10_install_state","ihg_r4_install_flow","ihg_r4_install_state",
 "amazon_r4_install_flow","amazon_r4_install_state","bestbuy_r4_install_flow","bestbuy_r4_install_state"];
 need(Array.isArray(exclusions)&&exclusions.length===649&&new Set(exclusions).size===649&&
  JSON.stringify(exclusions)===JSON.stringify([...exclusions].sort())&&exclusions.every(x=>typeof x==="string"&&/^[0-9a-f]{32}$/.test(x)),"EXACT_GLOBAL649_PRIOR_COMMITMENTS");
 const excludedSha=h.sha(JSON.stringify(exclusions)+"\n");
 need(excludedSha==="fe089e0fc4de4f18762aa541e9efadba79aa14615749ef7ef0f6cf0fbfe5fbe8"&&v.excluded_count===649&&v.excluded_sha256===excludedSha,"ACTUAL_GLOBAL_EXCLUSION_BINDING");
 need(v.schema===1&&v.count===8&&v.generator==="secrets.token_hex(16)"&&v.no_redraw===true&&
  v.purpose==="fresh current-cell02 four helper installation"&&
  JSON.stringify(v.labels)===JSON.stringify(labels)&&Array.isArray(v.values)&&v.values.length===8&&new Set(v.values).size===8&&
  v.values.every(x=>typeof x==="string"&&/^[0-9a-f]{32}$/.test(x)&&!exclusions.includes(x))&&
  ["Android_actions","Main_actions","children_started","filesystem_mutations"].every(k=>v[k]===0),"EXACT_FRESH_INSTALL_POOL");
 return {actual:{bytes:actual.bytes,sha256:actual.sha256,git_blob:actual.blob,tree:actual.tree},
  generator:v.generator,labels,nonces:Object.fromEntries(labels.map((n,i)=>[n,v.values[i]])),
  exclusion_count:649,exclusion_sha256:excludedSha,all657_values_reserved:true,
  no_redraw:true,Android_actions:0,Main_actions:0,old_values_reused:false};
}

function bindCell02AppInstall(template,helper,host,hostActual,buildActual,stageActual,nonceActual,nonceExclusions,h,ll,qualifyHost,qualifyBuild,qualifyNonces){
 const need=(v,s)=>{if(!v)throw Error(template.app+":"+s)},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 const sorted=v=>Array.isArray(v)?v.map(sorted):v&&typeof v==="object"?Object.fromEntries(Object.keys(v).sort().map(k=>[k,sorted(v[k])])):v;
 const canonical=v=>JSON.stringify(sorted(v)),pretty=v=>JSON.stringify(v,null,2)+"\n";
 need(template.bound_request_created===false&&template.complete_inverse_exact===true&&template.app===helper.app&&
  template.helper_manifest_sha256===helper.manifestSha&&template.host_manifest_sha256===host.manifest_sha256,"EXACT_REVIEWED_TEMPLATE");
 const hostProof=qualifyHost(hostActual,host,h);
 const buildProof=qualifyBuild(template.app,helper,buildActual,stageActual,host,h,ll);
 const nonceProof=qualifyNonces(nonceActual,nonceExclusions,h);
 const labels=[template.app+"_r4_install_flow",template.app+"_r4_install_state"];
 const [flow,state]=labels.map(label=>nonceProof.nonces[label]);
 need([flow,state].every(x=>typeof x==="string"&&/^[0-9a-f]{32}$/.test(x))&&flow!==state,"TWO_ACTUAL_OWN_INSTALL_NONCES");
 const files={...template.templates},bindings=[];
 const replace=(name,old,next,count=1)=>{
  need(files[name].split(old).length-1===count,"MATERIAL_BINDING_ANCHOR:"+name+":"+old);
  files[name]=files[name].split(old).join(next);bindings.push({file:name,old,next,count});
 };
 for(const name of ["install_state.py","stage_execute.py","make_request.py"])
  replace(name,"__ACTUAL_INSTALL_FLOW_NONCE__",flow,1);
 replace("install_state.py","__ACTUAL_INSTALL_STATE_NONCE__",state,1);
 for(const [name,value]of [
  ["__ACTUAL_BUILD_SHA256__",buildActual.sha256],["__ACTUAL_BUILD_STAGE_SHA256__",stageActual.sha256],
  ["__ACTUAL_APK_SHA256__",buildProof.APK.sha256],["__ACTUAL_SIGNER_SHA256__",buildProof.signer_certificate_sha256],
  ["__ACTUAL_HOST_STAGE_SHA256__",hostActual.sha256]
 ])replace("install_state.py",name,value,1);
 for(const[name,value]of [
  ["BUILD_BYTES",buildActual.bytes],["STAGE_BYTES",stageActual.bytes],["APK_BYTES",buildProof.APK.bytes],["HOST_STAGE_BYTES",hostActual.bytes]
 ])replace("install_state.py","\n"+name+" = None\n","\n"+name+" = "+value+"\n",1);
 need(Object.values(files).every(x=>!x.includes("__ACTUAL_")),"ALL_TEMPLATE_FIELDS_ACTUALLY_BOUND");
 const input={
  schema:2,state:"ACTUAL_CURRENT_BUILD_AND_HOST_BOUND_INSTALL_UNRUN",helper_package:template.self,helper_uid:null,
  target:{package:helper.binding.target_package,uid:helper.binding.target_uid,user:0},
  commercial_artifact_reference:pin(template.target_reference),
  build:{path:buildProof.build.path,bytes:buildActual.bytes,sha256:buildActual.sha256},
  build_stage:{path:buildProof.stage.path,bytes:stageActual.bytes,sha256:stageActual.sha256},
  APK:buildProof.APK,signer_certificate_sha256:buildProof.signer_certificate_sha256,
  qa_source_manifest_sha256:helper.manifestSha,
  current_host_source_root:hostProof.source_root,current_host_source_manifest_sha256:host.manifest_sha256,
  current_host_stage:{bytes:hostActual.bytes,sha256:hostActual.sha256},
  current_baseline:host.binding,
  nonces:{flow,state},actual_nonce_source:{bytes:nonceActual.bytes,sha256:nonceActual.sha256,git_blob:nonceActual.blob,
   fields:labels,generator:nonceProof.generator,exclusion_count:nonceProof.exclusion_count,exclusion_sha256:nonceProof.exclusion_sha256},
  previous_helper_uid_exclusion:{uid:template.previous_helper.uid,
   actual_worker_result:{bytes:template.previous_helper.bytes,sha256:template.previous_helper.sha256,git_blob:template.previous_helper.blob},
   source:"exact historical prior-generation installed helper receipt; exclusion only"},
  retained_previous_helper_uid_exclusion:template.older_previous_uid_retained,
  ordered_worker_Android_commands:13,target_APK_count:template.target_APK_count,
  target_APK_streaming_hashes_before_and_after:true,target_user_and_user_de_current_baseline_identity:true,
  own_package_absence_required_all_users_including_uninstalled:true,install_replace_existing:false,UiAutomation_requested:false,
  source_qualification_controls:template.controls_expected,Bili_Flow_or_MainBinding_instantiated:false,
  whole_process_tree_cleanup_qualified:false,framework_exit_cause_resolved:false,whole_app_production_ready:false,
  actual_static_controls:buildProof.actual_controls,old_helpers_and_tasks_reauthorized:false,
  new_helper_business_input_authorized_by_installation:false
 };
 files["host/source-manifest.json"]=host.manifestRaw;
 files["host-stage-actual.json"]=hostActual.raw;
 files["references/read_"+template.app+".py"]=template.readonly_reader;
 files["target-artifact-reference.json"]=template.target_reference;
 files["INPUTS.json"]=pretty(input);
 files["README.md"]="# "+template.app+" R4 install and state on current cell baseline02\n\n"+
 "This create-only request binds the complete actual R6 source-stage receipt, the signed new helper build, and two newly generated installation nonces. "+
 "The commercial target keeps its own original Context, target UID, current-baseline user/user_de directory identities, held classpaths, "+
 template.target_APK_count+" held APK hashes, ordered 13-command policy and all cleanup paths. Shared R6 source verification does not instantiate the Bili Flow or MainBinding.\n\n"+
 template.controls_expected+" production-source and Context controls run before persistent staging or Android commands. "+
 "They include the original five real verify_source fixtures, direct new-helper ordered-plan validation, the actual R6 publication receipt "+
 "and rejected old generation/source/owner/user-namespace/FD cases. Actual execution of these installation controls remains pending until this request is admitted. "+
 "The source-only host stage does not itself authorize runtime. The build remains an exact static prerequisite.\n\n"+
 "The single install uses -R/-t and requires absence for all users including retained uninstalled package records. "+
 "The fresh helper UID remains unknown until the actual package query; previous actual helper UIDs remain rejected. "+
 "The state operation does not connect UiAutomation. This request has no App launch, inspect, click, text entry, permission grant or settings write. "+
 "The staging file/directory, held descriptors and action lock are independently retired by the original worker. "+
 "Failure preserves its first cause and unknown outcome and does not automatically replay or uninstall. "+
 "Only the original direct owned-child join is qualified; whole-process-tree cleanup remains false. "+
 "Old cells, tasks and helper receipts are historical evidence, with no transferred task or input authority. "+
 "Framework exit attribution and whole-App business acceptance remain unresolved production gates.\n";
 const manifest={schema:2,artifact:"pocket4-owned-"+template.app+"-qa-r4-current-install-source-v2",
  host_recorder_manifest_sha256:host.manifest_sha256,qa_source_manifest_sha256:helper.manifestSha,
  actual_build:{bytes:buildActual.bytes,sha256:buildActual.sha256},actual_host_stage:{bytes:hostActual.bytes,sha256:hostActual.sha256},
  files:Object.fromEntries(Object.entries(files).sort(([a],[b])=>a<b?-1:a>b?1:0).map(([n,v])=>[n,pin(v)]))};
 files["SOURCE_PINS.json"]=pretty(manifest);const manifestSHA=h.sha(files["SOURCE_PINS.json"]);
 const packet={schema:2,source_manifest_sha256:manifestSHA,nonce:flow,files};
 const stdin=canonical(packet)+"\n";
 need(h.utf8(stdin).length<=262144&&Object.values(files).every(v=>h.utf8(v).length>0&&h.utf8(v).length<=65536),"ORIGINAL_PACKET_AND_FILE_BOUNDS");
 const wrapper="import hashlib,json,sys\nraw=sys.stdin.buffer.read(262145)\n"+
  "assert hashlib.sha256(raw).hexdigest()=='"+h.sha(stdin)+"'\n"+
  "p=json.loads(raw);src=p['files']['stage_execute.py'].encode('utf-8')\n"+
  "assert hashlib.sha256(src).hexdigest()=='"+h.sha(files["stage_execute.py"])+"'\n"+
  "scope={'__name__':'owned_qa_stage','__file__':'"+template.root+"/source/stage_execute.py'}\n"+
  "exec(compile(src,scope['__file__'],'exec'),scope)\nraise SystemExit(scope['main'](raw))\n";
 const request={host:"pocket4",executable:"/usr/bin/sudo",args:["-n","/usr/bin/python3","-I","-B","-c",wrapper],
  cwd:"/home/alex/work",env:{PYTHONDONTWRITEBYTECODE:"1"},stdin,idempotency_key:template.key,
  timeout_seconds:300,cpu_quota_percent:100,memory_max_bytes:536870912,nice:10};
 const normalized=Object.fromEntries(Object.keys(template.templates).map(n=>[n,files[n]]));
 for(const e of [...bindings].reverse()){
  need(normalized[e.file].split(e.next).length-1===e.count,"ACTUAL_BINDING_INVERSE:"+e.file);
  normalized[e.file]=normalized[e.file].split(e.next).join(e.old);
 }
 for(const[n,v]of Object.entries(template.templates))need(normalized[n]===v,"EXACT_REVIEWED_TEMPLATE_REPRODUCTION:"+n);
 for(const e of [...template.edits].reverse()){
  need(normalized[e.file].split(e.next).length-1===e.count,"PRODUCTION_INVERSE:"+e.file);
  normalized[e.file]=normalized[e.file].split(e.next).join(e.old);
 }
 for(const[n,v]of Object.entries(template.original_sources))need(normalized[n]===v,"EXACT_ORIGINAL_PRODUCTION_PARENT:"+n);
 return {schema:"pocket4-cell02-actual-bound-install-candidate-v1",app:template.app,root:template.root,key:template.key,
  files,inputs:input,manifest,manifest_sha256:manifestSHA,packet,stdin,wrapper,request,requestRaw:JSON.stringify(sorted(request),null,2)+"\n",
  template_bindings:bindings,source_edits:template.edits,production_inverse_exact:true,parent_request:template.parent_request,
  host_actual_qualification:hostProof,build_actual_qualification:buildProof,nonce_actual_qualification:nonceProof,
  controls_expected:template.controls_expected,helper_uid:null,installed:false,Hepta_dispatched:false,Python_executed_here:false};
}
