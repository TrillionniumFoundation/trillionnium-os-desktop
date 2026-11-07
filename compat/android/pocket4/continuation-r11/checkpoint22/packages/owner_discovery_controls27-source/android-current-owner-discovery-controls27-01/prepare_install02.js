function prepareCurrentOwnerInstall02(app,prior,discovery,controls,factory,contextFunction,biliFunction,h){
 const need=(v,s)=>{if(!v)throw Error(app+":"+s)},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 const files={...prior.files};delete files["SOURCE_PINS.json"];
 const original={...files},edits=[];
 function change(file,from,to,count=1){
  const n=files[file].split(from).length-1;need(n===count,"ANCHOR:"+file+":"+from.slice(0,80));
  files[file]=files[file].split(from).join(to);edits.push({file,from,to,count});
 }
 function addSet(file,name,additions){
  const re=new RegExp("^"+name+"\\s*=\\s*\\{[^}]*\\}","m"),m=files[file].match(re);need(m,"SET:"+file);
  const next=m[0].slice(0,-1)+", "+additions.map(x=>"'"+x+"'").join(", ")+"}";
  change(file,m[0],next);
 }
 const root=prior.root.replace(/-01$/,"-02"),key=prior.key.replace(/-01-20261106$/,"-02-20261106");
 need(root!==prior.root&&key!==prior.key,"CREATE_ONLY_SUCCESSOR_ROOT_KEY");
 for(const name of Object.keys(files)){
  if(name==="INPUTS.json"||name==="README.md")continue;
  const n=files[name].split(prior.root).length-1;if(n)change(name,prior.root,root,n);
  const k=files[name].split(prior.key).length-1;if(k)change(name,prior.key,key,k);
 }
 const pendingNonces=app==="ihg";
 const oldFlow=prior.inputs.nonces.flow,oldState=prior.inputs.nonces.state;
 if(pendingNonces)for(const name of Object.keys(files)){
  if(name==="INPUTS.json"||name==="README.md")continue;
  for(const[old,next]of[[oldFlow,"__FRESH_IHG_INSTALL02_FLOW__"],[oldState,"__FRESH_IHG_INSTALL02_STATE__"]]){
   const n=files[name].split(old).length-1;if(n)change(name,old,next,n);
  }
 }
 const add=["current_discovery.py","check_current_discovery.py",...(app==="bili"?["current_flow.py"]:[])];
 addSet("install_state.py","EXPECTED_SOURCE_FILES",add);
 addSet("stage_execute.py","FILES",add);
 files["current_discovery.py"]=discovery.source;
 files["check_current_discovery.py"]=controls;
 const oldCount=prior.controls_expected,newCount=oldCount+18;
 if(app!=="bili"){
  const context=app+"_context.py";
  change(context,"def open_context(",contextFunction+"def open_context(");
  change(context,"        init,discovered,status = app.discover()\n",
   "        init,discovered,status = current_discovery(util,source_manifest,source_verify,source_root,\n"+
   "                                                    app,activation,epoch,guard)\n");
  change("check_install_binding.py","CONTROL_COUNT = "+oldCount,"CONTROL_COUNT = "+newCount);
  const target="    rows.extend(run_source_controls(entry,files,source_manifest_sha256))\n";
  const replacement=target+
   "    discovery_controls = types.ModuleType('production_current_discovery_controls')\n"+
   "    exec(compile(files['check_current_discovery.py'],'<current-discovery-controls>','exec'),discovery_controls.__dict__)\n"+
   "    legacy_source = entry.read(entry.BASE_HOST_ROOT/'references/android_app.py',131072,\n"+
   "                               discovery_controls.LEGACY_SHA)\n"+
   "    rows.extend(discovery_controls.run_discovery_controls(files['current_discovery.py'],baseline,legacy_source))\n"+
   "    rows.extend(discovery_controls.run_context_route_controls(context,files,baseline,legacy_source,source_manifest_sha256))\n";
  change("check_install_binding.py",target,replacement);
  change("check_install_binding.py","'production_verify_source_calls':5}","'production_verify_source_calls':5,\n"+
   "            'new_owner_discovery_controls':18,'production_discovery_and_Context_route_used':True,\n"+
   "            'legacy_discover_failure_reproduced_in_memory':True}");
 }else{
  files["current_flow.py"]=factory.source;
  change("install_state.py","def worker(expected):\n",biliFunction+"def worker(expected):\n");
  change("install_state.py","        flow = recorder.Flow(flow_args)\n",
      "        flow = current_flow_type(runtime_manifest,recorder)(flow_args)\n");
  change("install_state.py","STEP = 'install-state-r10-01'","STEP = 'install-state-r10-02'");
  change("check_install_binding.py","import copy\n","import copy\nimport types\n");
  change("check_install_binding.py","def run_controls(entry,actual_host,manifest):\n",
      "def run_controls(entry,actual_host,manifest,files,baseline,recorder):\n");
  const old="    entry.require(len(rows)==19,'EXACT_INSTALL_BINDING_CONTROL_COUNT')\n";
  const next="    discovery_controls = types.ModuleType('production_current_discovery_controls')\n"+
   "    exec(compile(files['check_current_discovery.py'],'<current-discovery-controls>','exec'),discovery_controls.__dict__)\n"+
   "    legacy_source = entry.read(entry.BASE_HOST_ROOT/'references/android_app.py',131072,\n"+
   "                               discovery_controls.LEGACY_SHA)\n"+
   "    rows.extend(discovery_controls.run_discovery_controls(files['current_discovery.py'],baseline,legacy_source))\n"+
   "    rows.extend(discovery_controls.run_bili_route_controls(entry,files,baseline,legacy_source,recorder))\n"+
   "    entry.require(len(rows)=="+newCount+",'EXACT_INSTALL_BINDING_CONTROL_COUNT')\n";
  change("check_install_binding.py",old,next);
  change("check_install_binding.py","'count':19,'cases':rows","'count':"+newCount+",'cases':rows");
  change("check_install_binding.py","'Android_commands':0,'UI_actions':0,'children':0}",
    "'Android_commands':0,'UI_actions':0,'children':0,\n"+
    "            'new_owner_discovery_controls':18,'production_discovery_and_Bili_bind_route_used':True,\n"+
    "            'legacy_discover_failure_reproduced_in_memory':True}");
  change("stage_execute.py","    controls_module=load_text(files['check_install_binding.py'],SOURCE/'check_install_binding.py','current_install_pure_controls')\n",
    "    ref,original,manifest=load_original_host(files)\n"+
    "    baseline=ref.current_baseline()\n"+
    "    recorder=original.load('recorder.py','actual_R6_recorder_controls')\n"+
    "    controls_module=load_text(files['check_install_binding.py'],SOURCE/'check_install_binding.py','current_install_pure_controls')\n");
  change("stage_execute.py","    controls=controls_module.run_controls(entry,actual_host,host_manifest)\n",
    "    controls=controls_module.run_controls(entry,actual_host,host_manifest,files,baseline,recorder)\n");
  // Remove only the now-duplicated old loading after controls.
  change("stage_execute.py","            'ACTUAL_CURRENT_INSTALL_SOURCE_CONTROLS_REQUIRED')\n    ref,original,manifest=load_original_host(files)\n    baseline=ref.current_baseline()\n",
    "            'ACTUAL_CURRENT_INSTALL_SOURCE_CONTROLS_REQUIRED')\n");
 }
 change("stage_execute.py","controls['count']=="+oldCount,"controls['count']=="+newCount);
 change("stage_execute.py","len(controls['cases'])=="+oldCount,"len(controls['cases'])=="+newCount);
 const inputs=JSON.parse(JSON.stringify(prior.inputs));
 inputs.state=pendingNonces?"CURRENT_OWNER_FIX_SOURCE_ONLY_PENDING_FRESH_IHG_NONCES":"CURRENT_OWNER_FIX_ACTUAL_BOUND_INSTALL_UNRUN";
 inputs.source_qualification_controls=newCount;
 inputs.current_discovery={...pin(discovery.source),old_discover_sha256:discovery.old_discover_sha256,
  original_discover_inverse_exact:true,full_current_owner_identity_pins:discovery.identity_pins,
  guard_on_both_sides:true,installed_android_app_modified:false,R6_source_and_manifest_modified:false,
  original_helper_APK_and_QA_source_modified:false,production_entry:app==="bili"?
   "worker -> current_flow_type -> own CurrentFlow.bind -> original MainBinding -> explicit discovery facade -> discover_current":
   "worker -> original open_context -> current_discovery source-pin loader -> discover_current"};
 inputs.original_install_source={bytes:h.utf8(prior.files["SOURCE_PINS.json"]).length,sha256:prior.manifest_sha256,
   root:prior.root,request:pin(prior.requestRaw),state:app==="ihg"?"ACTUAL_FAILED_BEFORE_INSTALL_AND_STATE":"UNRUN"};
 inputs.original_discover_failure_preserved=app==="ihg";
 if(pendingNonces){inputs.nonces={flow:null,state:null};inputs.actual_nonce_source=null;
  inputs.consumed_previous_install_nonces={flow:oldFlow,state:oldState};
  inputs.required_nonce_labels=["ihg_r4_install02_flow","ihg_r4_install02_state"];}
 files["INPUTS.json"]=JSON.stringify(inputs,null,2)+"\n";
 files["README.md"]=prior.files["README.md"].replace(new RegExp("\\b"+oldCount+" production-source"),newCount+" production-source")+
 "\n## Current owner discovery correction 02\n\n"+
 "The original android-app owner argv constant rejected the qualified baseline02 intermediary before any installation or state command. "+
 "This successor uses its own pinned current_discovery module; the old reference remains unchanged. Status, the unique InputBridge, "+
 "namespace, environment and paired-classpath checks remain. The complete actual launcher/intermediary/init/daemon identities "+
 "and original full Main guard on both sides are required. No old task or failed input is replayed. "+
 "The shared R6 source, helper APK, QA adapter/contract and target transport remain exact original bytes. "+
 "Fifteen targeted discovery controls reproduce the old production failure and exercise the new complete identity gates, "+
 "plus three controls exercise the actual source loader and own Context/bind route. "+
 "All prior installation controls remain. New controls have not been executed locally.\n";
 const normalized={...files};for(const e of [...edits].reverse()){
  need(normalized[e.file].split(e.to).length-1===e.count,"INVERSE_ANCHOR:"+e.file);
  normalized[e.file]=normalized[e.file].split(e.to).join(e.from);
 }
 for(const[name,body]of Object.entries(original))if(!["INPUTS.json","README.md"].includes(name))
  need(normalized[name]===body,"COMPLETE_OLD_PRODUCTION_INVERSE:"+name);
 const untouched=Object.keys(original).filter(n=>files[n]===original[n]).map(name=>({name,...pin(original[name])}));
 return{schema:"pocket4-current-owner-correction-install02-source-v1",app,root,key,files,inputs,prior_manifest:prior.manifest,
  prior_request:pin(prior.requestRaw),prior_source_manifest_sha256:prior.manifest_sha256,edits,
  original_sources:original,production_inverse_exact:true,unchanged_files:untouched,
  controls_expected:newCount,added_controls:18,helper_uid:null,pending_fresh_nonces:pendingNonces,
  request_created:false,Python_executed_here:false,Hepta_dispatched:false,
  original_helper_and_R6_bytes_unchanged:true};
}
