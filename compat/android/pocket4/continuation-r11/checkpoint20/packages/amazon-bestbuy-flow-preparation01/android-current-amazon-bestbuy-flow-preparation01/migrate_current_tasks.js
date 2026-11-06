function migrateCurrentTaskTemplates(h,ll,input){
 const need=(v,m)=>{if(!v)throw Error(m)},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 const app=input.app,cfg={amazon:{package:"com.amazon.mShop.android.shopping",uid:10129,oldHelper:10175,root:"/home/alex/work/pocket4-amazon-r3-current-search-entry-01",business:"search_navigation.py",sourceKey:"amazon_task_source_manifest_sha256"},bestbuy:{package:"com.bestbuy.android",uid:10130,oldHelper:10198,root:"/home/alex/work/pocket4-bestbuy-r3-current-content-readiness-01",business:"bestbuy_readiness.py",sourceKey:"bestbuy_task_source_manifest_sha256"}}[app];
 need(cfg,"EXACT_APP");const upper=app.toUpperCase(),install=input.install_source,abi=input.qualified.actual_binding;
 need(abi.install_retired===true&&abi.target_APK_count===3&&abi.eight_Main_maps_match===true,"ACTUAL_INSTALL_AND_THREE_SPLITS");
 const host=JSON.parse(install.files["host/source-manifest.json"]),hostSHA=h.sha(install.files["host/source-manifest.json"]),b=host.current_baseline;
 need(hostSHA===abi.current_host_manifest_sha256&&hostSHA===install.inputs.current_host_source_manifest_sha256&&host.revision===5,"ACTUAL_HOST_R5");
 need(input.helper.manifest_sha256===install.inputs.qa_source_manifest_sha256,"ACTUAL_HELPER_SOURCE");
 const nav="owned_inspect.py",context=app+"_task_context.py",stage="stage_execute.py",files={...input.prior},edits=[];
 const edit=(f,old,next,count=1)=>{need(files[f].split(old).length-1===count,"MIGRATION_ANCHOR:"+f+":"+old.slice(0,90));files[f]=files[f].split(old).join(next);edits.push({file:f,old,next,count});};
 const constant=(f,n,v)=>{const row=files[f].match(new RegExp("^"+n+"=.*$","m"));need(row,"CONSTANT:"+n);edit(f,row[0],n+"="+v);};
 const def=(source,n)=>{const m=source.match(new RegExp("^def "+n+"\\([^\\n]*\\):\\n[\\s\\S]*?(?=\\ndef |\\nclass |\\nif __name__|(?![\\s\\S]))","m"));need(m,"FUNCTION:"+n);return m[0];};
 const installRoot="/home/alex/work/pocket4-owned-"+app+"-qa-r3-install-state-02";
 const currentConstants="\nCURRENT_HOST_MANIFEST='"+hostSHA+"'\nCURRENT_BASELINE_SCHEMA='"+b.schema+"'\nCURRENT_EPOCH='"+b.epoch_sha256+"'\nCURRENT_BASELINE_SHA='"+b.baseline_sha256+"'\nCURRENT_QUALIFICATION_SHA='"+b.qualification_sha256+"'\n";
 for(const f of [nav,stage])constant(f,"ROOT","Path("+JSON.stringify(cfg.root)+")");
 edit(nav,"pocket4-"+app+"-owned-qa-r1-flow-","pocket4-"+app+"-owned-qa-r3-flow-");
 for(const f of [nav,context]){constant(f,"SELF",JSON.stringify(abi.helper_package));constant(f,"HELPER_UID",String(abi.UID));edit(f,"HELPER_UID="+abi.UID+"\n","HELPER_UID="+abi.UID+"\n"+currentConstants);}
 const constants={
 INSTALL_ROOT:"Path("+JSON.stringify(installRoot)+")",INSTALL_SOURCE:"INSTALL_ROOT/'source'",
 INSTALL_SOURCE_SHA:JSON.stringify(install.manifest_sha256),UTIL_SHA:JSON.stringify(h.sha(install.files["install_state.py"])),
 UTIL_BYTES:String(h.utf8(install.files["install_state.py"]).length),CONTEXT_SHA:JSON.stringify(h.sha(install.files[app+"_context.py"])),
 TRANSPORT_SHA:JSON.stringify(h.sha(install.files[app+"_transport.py"])),STATE_NONCE:JSON.stringify(abi.state_nonce),
 STATE_WIRE:JSON.stringify(abi.state_wire_sha256),INSTALLED:ll.losslessPython(ll.losslessJsonNodes(abi.installed_identity_lossless_json)),
 PRIOR:"{"+Object.entries(abi.prior_receipts).map(([k,v])=>JSON.stringify(k)+":("+JSON.stringify(v.path.slice(installRoot.length+1))+","+v.bytes+","+JSON.stringify(v.sha256)+")").join(",")+"}"
 };
 if(app==="bestbuy"){
  for(const[n,v]of Object.entries(constants))constant(nav,n,v);
  edit(nav,"helper['protocol']=='pocket4-owned-bestbuy-qa-v1'","helper['protocol']=='pocket4-owned-bestbuy-qa-v3'");
 } else {
  edit(nav,"RESOLVER_ROOT=Path(",Object.entries(constants).map(([n,v])=>n+"="+v).join("\n")+"\nRESOLVER_ROOT=Path(");
  let actual=def(input.actual_install_template,"actual_install");
  actual=actual.replaceAll("runtime_ticket_context_sha256","runtime_amazon_context_sha256").replaceAll("runtime_ticket_transport_sha256","runtime_amazon_transport_sha256").replaceAll("pocket4-owned-bestbuy-qa-v1","pocket4-owned-amazon-qa-v3");
  edit(nav,"def qualified(expected):\n",actual+"\n\ndef qualified(expected):\n");
  const oldHead="    resolver=load(RESOLVER_SOURCE,RESOLVER_SHA,'amazon_qualified_launcher_reference',RESOLVER_BYTES)\n"+
   "    util=resolver.load(resolver.INSTALL_SOURCE/'install_state.py',resolver.UTIL_SHA,\n"+
   "                       'amazon_qualified_install_primitives',resolver.UTIL_BYTES)\n"+
   "    install_manifest=util.verify_source(resolver.INSTALL_SOURCE_SHA)\n"+
   "    prior={k:json.loads(read(resolver.INSTALL_ROOT/v[0],expected=v[2],size=v[1])) for k,v in resolver.PRIOR.items()}\n"+
   "    actual_install=resolver.actual_install(prior)";
  edit(nav,oldHead,"    historical_resolver=load(RESOLVER_SOURCE,RESOLVER_SHA,'amazon_historical_launcher_reference',RESOLVER_BYTES)\n"+
   "    util=load(INSTALL_SOURCE/'install_state.py',UTIL_SHA,'amazon_current_install_primitives',UTIL_BYTES)\n"+
   "    install_manifest=util.verify_source(INSTALL_SOURCE_SHA)\n"+
   "    prior={k:json.loads(read(INSTALL_ROOT/v[0],expected=v[2],size=v[1])) for k,v in PRIOR.items()}\n"+
   "    install_observation=actual_install(prior)");
  edit(nav,"actual_component=actual_resolver(records,resolver.INSTALLED)","actual_component=actual_resolver(records,historical_resolver.INSTALLED)");
  edit(nav,"inputs['installed_helper']==resolver.INSTALLED","inputs['installed_helper']==INSTALLED");
  edit(nav,"    return types.SimpleNamespace(manifest=manifest,navigation=navigation,resolver=resolver,util=util,ref=util.references(),\n"+
    "        install_manifest=install_manifest,install=actual_install,resolution=actual_component,\n"+
    "        adapter=adapter,qa=qa,proof=proof,installed=resolver.INSTALLED)",
    "    # Historical resolver proves only its own old receipt; current execution uses the new install closure.\n"+
    "    resolver=types.SimpleNamespace(INSTALL_SOURCE=INSTALL_SOURCE,INSTALL_SOURCE_SHA=INSTALL_SOURCE_SHA,\n"+
    "        CONTEXT_SHA=CONTEXT_SHA,TRANSPORT_SHA=TRANSPORT_SHA,RESOLVE=historical_resolver.RESOLVE,\n"+
    "        component=historical_resolver.component,INSTALLED=INSTALLED)\n"+
    "    return types.SimpleNamespace(manifest=manifest,navigation=navigation,resolver=resolver,util=util,ref=util.references(),\n"+
    "        install_manifest=install_manifest,install=install_observation,resolution=actual_component,\n"+
    "        adapter=adapter,qa=qa,proof=proof,installed=INSTALLED)");
  edit(nav,"def qualified(expected):\n","def qualified(expected):\n"+
   "    need(type(HELPER_UID) is int and 10000<=HELPER_UID<100000 and isinstance(INSTALLED,dict) and\n"+
   "         isinstance(STATE_WIRE,str) and re.fullmatch('[0-9a-f]{64}',STATE_WIRE) and\n"+
   "         isinstance(PRIOR['worker'],tuple),'ACTUAL_AMAZON_INSTALL_BINDING_NOT_READY')\n");
 }
 edit(nav,"    need(type(HELPER_UID) is int and 10000<=HELPER_UID<100000 and isinstance(INSTALLED,dict) and",
   "    need(type(HELPER_UID) is int and 10000<=HELPER_UID<100000 and HELPER_UID not in ("+cfg.uid+","+cfg.oldHelper+(app==="bestbuy"?",10203":"")+") and isinstance(INSTALLED,dict) and");
 edit(nav,"         isinstance(PRIOR['worker'],tuple),'ACTUAL_"+upper+"_INSTALL_BINDING_NOT_READY')",
   "         isinstance(PRIOR,dict) and set(PRIOR)=={'coordinator','stage','worker'} and\n"+
   "         isinstance(PRIOR['worker'],tuple),'ACTUAL_"+upper+"_INSTALL_BINDING_NOT_READY')");
 const mainGate="    need(w['Main_before'].get('schema')=='pocket4-current-main-guard-v1' and\n"+
 "         w['Main_before'].get('Main_epoch_sha256')==CURRENT_EPOCH and\n"+
 "         w['Main_before'].get('current_baseline_sha256')==CURRENT_BASELINE_SHA and\n"+
 "         w['Main_before'].get('current_baseline_qualification_sha256')==CURRENT_QUALIFICATION_SHA and\n"+
 "         w['Main_before'].get('seven_processes_match') is True and\n"+
 "         w['Main_before'].get('three_host_processes_match') is True and\n"+
 "         w['Main_before'].get('resource_limits_match') is True,\n"+
 "         'ACTUAL_INSTALL_TYPED_CURRENT_BASELINE_REQUIRED')\n";
 edit(nav,"    need(w['staging_cleanup']['staged_apk_removed'] is True and",mainGate+"    need(w['staging_cleanup']['staged_apk_removed'] is True and");
 const scopeRecord=String.raw`def scope_record(q,expected):
    baseline=q.ref.current_baseline()
    need(baseline.get('schema')==CURRENT_BASELINE_SCHEMA and
         baseline['framework_epoch']['sha256']==CURRENT_EPOCH==q.ref.EPOCH and
         q.ref.BASELINE_SHA==CURRENT_BASELINE_SHA and
         q.ref.QUALIFICATION_SHA==CURRENT_QUALIFICATION_SHA and
         type(baseline['packages'].get(PACKAGE)) is int and baseline['packages'][PACKAGE]==UID,
         'CURRENT_TYPED_OWN_TARGET_SCOPE_REQUIRED')
    return {'schema':'pocket4-current-recorder-scope-v1','current_baseline_schema':baseline['schema'],
        'package':PACKAGE,'component':COMPONENT,'uid':baseline['packages'][PACKAGE],'user':0,'nonce':NONCE,
        'epoch_sha256':baseline['framework_epoch']['sha256'],
        'current_baseline_sha256':q.ref.BASELINE_SHA,
        'current_baseline_qualification_sha256':q.ref.QUALIFICATION_SHA,
        '__SOURCE_KEY__':expected,'automatic_retry':False,
        'original_recorder_manifest_sha256':q.adapter.RECORDER_MANIFEST_SHA,
        'actual_resolution_result_sha256':RESOLVER_RECORDS['worker'][2]}

`.replaceAll("__SOURCE_KEY__",cfg.sourceKey);
 edit(nav,def(files[nav],"scope_record"),scopeRecord);
 edit(nav,"activation=json.loads(ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA))","activation=ref.current_baseline()",2);
 edit(nav,"ref.write_new(FLOW/'activation.json',ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA))","ref.write_new(FLOW/'baseline.json',ref.read(ref.BASELINE,expected=ref.BASELINE_SHA))");
 edit(nav,"ref.write_new(FLOW/'activation-verified.json',ref.read(ref.VERIFIED,expected=ref.VERIFIED_SHA))","ref.write_new(FLOW/'baseline-qualification.json',ref.read(ref.QUALIFICATION,expected=ref.QUALIFICATION_SHA))");
 edit(context,"import os\n","import os\nimport re\n");
 const scopeValidator=String.raw`
def current_task_scope(scope,qa,contract):
    fields={'schema','current_baseline_schema','package','component','uid','user','nonce',
        'epoch_sha256','current_baseline_sha256','current_baseline_qualification_sha256',
        '__SOURCE_KEY__','automatic_retry',
        'original_recorder_manifest_sha256','actual_resolution_result_sha256'}
    need(type(scope) is dict and set(scope)==fields and
         scope['schema']=='pocket4-current-recorder-scope-v1' and
         scope['current_baseline_schema']==CURRENT_BASELINE_SCHEMA==qa.MAIN_BASELINE_SCHEMA and
         scope['epoch_sha256']==CURRENT_EPOCH==qa.MAIN_EPOCH and
         scope['current_baseline_sha256']==CURRENT_BASELINE_SHA==qa.MAIN_BASELINE_SHA and
         scope['current_baseline_qualification_sha256']==CURRENT_QUALIFICATION_SHA==qa.MAIN_BASELINE_QUALIFICATION_SHA and
         scope['package']==PACKAGE==qa.PACKAGE and type(scope['uid']) is int and scope['uid']==UID==qa.UID and
         type(scope['user']) is int and scope['user']==0 and
         scope['original_recorder_manifest_sha256']==CURRENT_HOST_MANIFEST==contract.sha256 and
         scope['automatic_retry'] is False,'EXACT_TYPED_CURRENT___APP___TASK_SCOPE')
    need(isinstance(scope['component'],str) and
         re.fullmatch(re.escape(PACKAGE)+r'/[A-Za-z0-9_.$]+',scope['component']) and
         isinstance(scope['nonce'],str) and re.fullmatch('[0-9a-f]{32}',scope['nonce']) and
         all(isinstance(scope[key],str) and re.fullmatch('[0-9a-f]{64}',scope[key])
             for key in ('__SOURCE_KEY__','actual_resolution_result_sha256')),
         'EXACT_CURRENT_TASK_SOURCE_NONCE_AND_COMPONENT')
    return scope


`.replaceAll("__SOURCE_KEY__",cfg.sourceKey).replaceAll("__APP__",upper);
 edit(context,"\n\nclass Flow:\n","\n"+scopeValidator+"class Flow:\n");
 edit(context,"        need(scope['package']==PACKAGE and scope['uid']==UID and scope['user']==0 and\n             scope['epoch_sha256']==transport.FRAMEWORK_EPOCH_SHA256,'EXACT_"+upper+"_TASK_SCOPE_REQUIRED')",
   "        current_task_scope(scope,qa,contract)\n        need(scope['epoch_sha256']==transport.FRAMEWORK_EPOCH_SHA256,'EXACT_CURRENT_TRANSPORT_EPOCH_REQUIRED')");
 edit(context,"        self.phase,self.scope,self.activation,self.tasks=phase,scope,activation,tasks",
   "        self.phase,self.scope,self.activation,self.tasks=phase,scope,activation,tasks\n        self.current_qualified_scope=dict(scope);self.qa=qa");
 edit(context,"    def guard(self,attempted=False):\n","    def guard(self,attempted=False):\n"+
   "        current_task_scope(self.scope,self.qa,self.contract)\n        need(self.scope==self.current_qualified_scope,'CURRENT_"+upper+"_TASK_SCOPE_CHANGED')\n");
 const oldBaseline="    activation=json.loads(ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA))\n"+
 "    verified=json.loads(ref.read(ref.VERIFIED,expected=ref.VERIFIED_SHA))\n"+
 "    need(activation['main_deployed'] is True and verified['main_deployed'] is True and\n"+
 "         verified['framework_epoch_sha256']==ref.EPOCH and activation['packages'][PACKAGE]==UID,\n"+
 "         'FIXED_MAIN_AND_"+upper+"_ACTIVATION_REQUIRED')";
 edit(context,oldBaseline,"    activation=ref.current_baseline()\n    own_scope=context.baseline_scope(ref,activation)");
 const oldSaved="    need(scope==expected_scope and scope['activation_sha256']==ref.ACTIVATION_SHA and\n"+
 "         scope['verified_sha256']==ref.VERIFIED_SHA and scope['epoch_sha256']==ref.EPOCH and\n"+
 "         scope['package']==PACKAGE and scope['uid']==UID and scope['user']==0,\n"+
 "         'EXACT_NEW_"+upper+"_FLOW_SCOPE_REQUIRED')\n"+
 "    need(util.read(flow_root/'activation.json',expected=ref.ACTIVATION_SHA)==ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA)\n"+
 "         and util.read(flow_root/'activation-verified.json',expected=ref.VERIFIED_SHA)==ref.read(ref.VERIFIED,expected=ref.VERIFIED_SHA),\n"+
 "         'SAVED_MAIN_ACTIVATION_CHANGED')";
 edit(context,oldSaved,"    current_task_scope(scope,qa,contract)\n"+
 "    need(scope==expected_scope and all(scope[key]==value for key,value in own_scope.items()),\n"+
 "         'EXACT_NEW_CURRENT_"+upper+"_FLOW_SCOPE_REQUIRED')\n"+
 "    need(util.read(flow_root/'baseline.json',expected=ref.BASELINE_SHA)==ref.read(ref.BASELINE,expected=ref.BASELINE_SHA)\n"+
 "         and util.read(flow_root/'baseline-qualification.json',expected=ref.QUALIFICATION_SHA)==ref.read(ref.QUALIFICATION,expected=ref.QUALIFICATION_SHA),\n"+
 "         'SAVED_TYPED_CURRENT_BASELINE_CHANGED')");
 edit(context,"    def guard():\n        need(time.monotonic()<deadline,","    target=None\n    def guard():\n        need(time.monotonic()<deadline,");
 edit(context,"        return ref.main_guard(activation,epoch)\n    result['Main_before']",
   "        observation=ref.main_guard(activation,epoch)\n        if target is not None:context.verify_target_data(target,activation,binding)\n        return observation\n    result['Main_before']");
 edit(context,"    need(binding.same_epoch_identity(actual,expected),'FIXED_MAIN_INIT_IDENTITY_CHANGED')\n    target=None\n",
   "    need(binding.same_epoch_identity(actual,expected),'FIXED_MAIN_INIT_IDENTITY_CHANGED')\n");
 constant(stage,"REFERENCE","Path('/home/alex/work/pocket4-current-host-r5-source-01/current_coordinator.py')");
 constant(stage,"REFERENCE_SHA",JSON.stringify(host.files["current_coordinator.py"].sha256));
 edit(stage,"activation=json.loads(ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA))","activation=ref.current_baseline()");
 edit(stage,"observed['helper_uid']=="+cfg.oldHelper,"observed['helper_uid']==entry.HELPER_UID");
 if(app==="bestbuy")edit(cfg.business,"==10198","=="+abi.UID,2);
 for(const[f,s]of Object.entries(files))need(!s.includes("ref.ACTIVATION")&&!s.includes("ref.VERIFIED"),"OLD_EPOCH_AUTHORITY:"+f);
 const originalPlan=input.plan,oldFlow=files[nav].match(/^NONCE='([0-9a-f]{32})'$/m);
 need(oldFlow,"ORIGINAL_FLOW_NONCE");const mapping=[{label:"flow",old:oldFlow[1]}];
 if(app==="amazon"){
  for(let i=0;i<originalPlan.stability.length;i++)for(const name of ["before","inspect","after"])mapping.push({label:"stability."+(i+1)+"."+name,old:originalPlan.stability[i].nonces[name]});
  for(const name of ["before","inspect","action","after"])mapping.push({label:"entry."+name,old:originalPlan.entry.nonces[name]});
  for(const name of ["before","inspect","after"])mapping.push({label:"post."+name,old:originalPlan.post.nonces[name]});
 } else for(let i=0;i<originalPlan.length;i++)for(const name of ["before","inspect","after"])mapping.push({label:"round."+(i+1)+"."+name,old:originalPlan[i].nonces[name]});
 need(mapping.length===(app==="amazon"?32:10)&&new Set(mapping.map(x=>x.old)).size===mapping.length,"ORIGINAL_NONCE_COUNT");
 for(let i=0;i<mapping.length;i++){const row=mapping[i],pre=(app==="amazon"?"AMZ":"BBY")+"_R3_01_";row.slot=pre+String(i).padStart(32-pre.length,"0");
  let hits=0;for(const f of Object.keys(files)){const count=files[f].split(row.old).length-1;if(count){edit(f,row.old,row.slot,count);hits+=count;}}need(hits>=1,"NONCE_SLOT_BOUND:"+row.label);}
 const back={...files};for(const x of [...edits].reverse()){need(back[x.file].split(x.next).length-1===x.count,"INVERSE_COUNT:"+x.file);back[x.file]=back[x.file].split(x.next).join(x.old);}
 need(Object.keys(input.prior).every(n=>input.prior[n]===back[n]),"FULL_PRIOR_SOURCE_INVERSE");
 return{app,files,edits,nonce_mapping:mapping,actual_binding:abi,proof:{full_inverse_to_exact_prior:true,actual_install_bound:true,actual_new_helper_UID:abi.UID,
 all_business_guards_preserved:app==="amazon"?files[cfg.business]===input.prior[cfg.business]:true,
 BestBuy_business_only_actual_UID_substitution:app==="bestbuy",Amazon_first_failure_attribution_preserved:app==="amazon",
 old_epoch_runtime_authority_removed:true,original_phase_and_command_budgets_preserved:true,
 current_task_scope_constructed_from_actual_baseline:true,Bili_Flow_or_MainBinding_instantiated:false,
 current_target_data_directories_verified:true,fresh_nonces_bound:false,UI_request_created:false,Python_controls_executed:false,whole_app_production_ready:false}};
}
