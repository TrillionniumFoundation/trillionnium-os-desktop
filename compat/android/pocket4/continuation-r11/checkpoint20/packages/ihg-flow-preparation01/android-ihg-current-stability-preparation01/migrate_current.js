function migrateIhgCurrentTemplates(h,prior,installSource,helper){
 const need=(v,c)=>{if(!v)throw Error(c)},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 const host=JSON.parse(installSource.files['host/source-manifest.json']),hostSHA=h.sha(installSource.files['host/source-manifest.json']);
 need(hostSHA===installSource.inputs.current_host_source_manifest_sha256&&host.revision===5,'ACTUAL_CURRENT_INSTALL_SOURCE_HOST');
 const helperManifest=JSON.parse(helper.files['SOURCE_PINS.json']);
 need(helper.manifest_sha256===installSource.inputs.qa_source_manifest_sha256&&helperManifest.files['qa_contract.py'].sha256===h.sha(helper.files['qa_contract.py']),'ACTUAL_CURRENT_HELPER_SOURCE');
 const scope=host.current_baseline;
 let files={...prior},edits=[];
 function edit(file,old,next,count=1){need(files[file].split(old).length-1===count,'MIGRATION_ANCHOR:'+file+':'+old.slice(0,90));files[file]=files[file].split(old).join(next);edits.push({file,old,next,count});}
 function constant(file,name,next){const m=files[file].match(new RegExp('^'+name+'=.*$','m'));need(m,'CONSTANT:'+name);edit(file,m[0],name+'='+next);}
 const context='ihg_task_context.py',nav='owned_inspect.py',stage='stage_execute.py';
 const root='/home/alex/work/pocket4-ihg-r2-public-search-destination-entry-01';
 constant(nav,'ROOT',"Path('"+root+"')");constant(stage,'ROOT',"Path('"+root+"')");
 edit(nav,"pocket4-ihg-owned-qa-r1-flow-","pocket4-ihg-owned-qa-r2-flow-");
 for(const file of [nav,context]){constant(file,'SELF',"'org.droidloom.qa.ihg.r2'");constant(file,'HELPER_UID','None');}
 const currentConstants="\nCURRENT_HOST_MANIFEST='"+hostSHA+"'\nCURRENT_BASELINE_SCHEMA='"+scope.schema+"'\nCURRENT_EPOCH='"+scope.epoch_sha256+"'\nCURRENT_BASELINE_SHA='"+scope.baseline_sha256+"'\nCURRENT_QUALIFICATION_SHA='"+scope.qualification_sha256+"'\n";
 edit(context,"HELPER_UID=None\n","HELPER_UID=None\n"+currentConstants);
 edit(nav,"HELPER_UID=None\n","HELPER_UID=None\n"+currentConstants);
 constant(nav,'INSTALL_ROOT',"Path("+JSON.stringify(installSource.files['install_state.py'].match(/^ROOT = Path\((.+)\)$/m)[1].slice(1,-1))+")");
 constant(nav,'INSTALL_SOURCE_SHA',JSON.stringify(installSource.manifest_sha256));
 constant(nav,'UTIL_SHA',JSON.stringify(h.sha(installSource.files['install_state.py'])));constant(nav,'UTIL_BYTES',String(h.utf8(installSource.files['install_state.py']).length));
 constant(nav,'CONTEXT_SHA',JSON.stringify(h.sha(installSource.files['ihg_context.py'])));
 constant(nav,'TRANSPORT_SHA',JSON.stringify(h.sha(installSource.files['ihg_transport.py'])));
 for(const name of ['STATE_NONCE','STATE_WIRE','INSTALLED','PRIOR'])constant(nav,name,'None');
 edit(nav,"helper['protocol']=='pocket4-owned-ihg-qa-v1'","helper['protocol']=='pocket4-owned-ihg-qa-v2'");
 edit(nav,"    need(type(HELPER_UID) is int and 10000<=HELPER_UID<100000 and isinstance(INSTALLED,dict) and",
      "    need(type(HELPER_UID) is int and 10000<=HELPER_UID<100000 and HELPER_UID not in (10137,10196) and isinstance(INSTALLED,dict) and");
 edit(nav,"         isinstance(PRIOR['worker'],tuple),'ACTUAL_IHG_INSTALL_BINDING_NOT_READY')",
      "         isinstance(PRIOR,dict) and set(PRIOR)=={'coordinator','stage','worker'} and\n         isinstance(PRIOR['worker'],tuple),'ACTUAL_IHG_INSTALL_BINDING_NOT_READY')");
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
        'amazon_task_source_manifest_sha256':expected,'automatic_retry':False,
        'original_recorder_manifest_sha256':q.adapter.RECORDER_MANIFEST_SHA,
        'actual_resolution_result_sha256':RESOLVER_RECORDS['worker'][2]}

`;
 const oldScope=files[nav].match(/def scope_record\(q,expected\):\n[\s\S]*?(?=\ndef )/)[0];edit(nav,oldScope,scopeRecord);
 edit(nav,"activation=json.loads(ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA))","activation=ref.current_baseline()",2);
 edit(nav,"ref.write_new(FLOW/'activation.json',ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA))",
      "ref.write_new(FLOW/'baseline.json',ref.read(ref.BASELINE,expected=ref.BASELINE_SHA))");
 edit(nav,"ref.write_new(FLOW/'activation-verified.json',ref.read(ref.VERIFIED,expected=ref.VERIFIED_SHA))",
      "ref.write_new(FLOW/'baseline-qualification.json',ref.read(ref.QUALIFICATION,expected=ref.QUALIFICATION_SHA))");
 edit(context,"import os\n","import os\nimport re\n");
 const scopeValidator=String.raw`
def current_task_scope(scope,qa,contract):
    fields={'schema','current_baseline_schema','package','component','uid','user','nonce',
        'epoch_sha256','current_baseline_sha256','current_baseline_qualification_sha256',
        'amazon_task_source_manifest_sha256','automatic_retry',
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
         scope['automatic_retry'] is False,'EXACT_TYPED_CURRENT_IHG_TASK_SCOPE')
    need(isinstance(scope['component'],str) and
         re.fullmatch(re.escape(PACKAGE)+r'/[A-Za-z0-9_.$]+',scope['component']) and
         isinstance(scope['nonce'],str) and re.fullmatch('[0-9a-f]{32}',scope['nonce']) and
         all(isinstance(scope[key],str) and re.fullmatch('[0-9a-f]{64}',scope[key])
             for key in ('amazon_task_source_manifest_sha256','actual_resolution_result_sha256')),
         'EXACT_CURRENT_TASK_SOURCE_NONCE_AND_COMPONENT')
    return scope


`;
 edit(context,"\n\nclass Flow:\n","\n"+scopeValidator+"class Flow:\n");
 edit(context,"        need(scope['package']==PACKAGE and scope['uid']==UID and scope['user']==0 and\n             scope['epoch_sha256']==transport.FRAMEWORK_EPOCH_SHA256,'EXACT_AMAZON_TASK_SCOPE_REQUIRED')",
      "        current_task_scope(scope,qa,contract)\n        need(scope['epoch_sha256']==transport.FRAMEWORK_EPOCH_SHA256,'EXACT_CURRENT_TRANSPORT_EPOCH_REQUIRED')");
 edit(context,"        self.phase,self.scope,self.activation,self.tasks=phase,scope,activation,tasks",
      "        self.phase,self.scope,self.activation,self.tasks=phase,scope,activation,tasks\n        self.current_qualified_scope=dict(scope);self.qa=qa");
 edit(context,"    def guard(self,attempted=False):\n",
      "    def guard(self,attempted=False):\n        current_task_scope(self.scope,self.qa,self.contract)\n        need(self.scope==self.current_qualified_scope,'CURRENT_IHG_TASK_SCOPE_CHANGED')\n");
 const oldBaseline="    activation=json.loads(ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA))\n"+
 "    verified=json.loads(ref.read(ref.VERIFIED,expected=ref.VERIFIED_SHA))\n"+
 "    need(activation['main_deployed'] is True and verified['main_deployed'] is True and\n"+
 "         verified['framework_epoch_sha256']==ref.EPOCH and activation['packages'][PACKAGE]==UID,\n"+
 "         'FIXED_MAIN_AND_AMAZON_ACTIVATION_REQUIRED')";
 edit(context,oldBaseline,"    activation=ref.current_baseline()\n    own_scope=context.baseline_scope(ref,activation)");
 const oldSaved="    need(scope==expected_scope and scope['activation_sha256']==ref.ACTIVATION_SHA and\n"+
 "         scope['verified_sha256']==ref.VERIFIED_SHA and scope['epoch_sha256']==ref.EPOCH and\n"+
 "         scope['package']==PACKAGE and scope['uid']==UID and scope['user']==0,\n"+
 "         'EXACT_NEW_AMAZON_FLOW_SCOPE_REQUIRED')\n"+
 "    need(util.read(flow_root/'activation.json',expected=ref.ACTIVATION_SHA)==ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA)\n"+
 "         and util.read(flow_root/'activation-verified.json',expected=ref.VERIFIED_SHA)==ref.read(ref.VERIFIED,expected=ref.VERIFIED_SHA),\n"+
 "         'SAVED_MAIN_ACTIVATION_CHANGED')";
 const newSaved="    current_task_scope(scope,qa,contract)\n"+
 "    need(scope==expected_scope and all(scope[key]==value for key,value in own_scope.items()),\n"+
 "         'EXACT_NEW_CURRENT_IHG_FLOW_SCOPE_REQUIRED')\n"+
 "    need(util.read(flow_root/'baseline.json',expected=ref.BASELINE_SHA)==ref.read(ref.BASELINE,expected=ref.BASELINE_SHA)\n"+
 "         and util.read(flow_root/'baseline-qualification.json',expected=ref.QUALIFICATION_SHA)==ref.read(ref.QUALIFICATION,expected=ref.QUALIFICATION_SHA),\n"+
 "         'SAVED_TYPED_CURRENT_BASELINE_CHANGED')";
 edit(context,oldSaved,newSaved);
 edit(context,"    def guard():\n        need(time.monotonic()<deadline,",
      "    target=None\n    def guard():\n        need(time.monotonic()<deadline,");
 edit(context,"        return ref.main_guard(activation,epoch)\n    result['Main_before']",
      "        observation=ref.main_guard(activation,epoch)\n        if target is not None:context.verify_target_data(target,activation,binding)\n        return observation\n    result['Main_before']");
 edit(context,"    need(binding.same_epoch_identity(actual,expected),'FIXED_MAIN_INIT_IDENTITY_CHANGED')\n    target=None\n",
      "    need(binding.same_epoch_identity(actual,expected),'FIXED_MAIN_INIT_IDENTITY_CHANGED')\n");
 constant(stage,'REFERENCE',"Path('/home/alex/work/pocket4-current-host-r5-source-01/current_coordinator.py')");
 constant(stage,'REFERENCE_SHA',JSON.stringify(host.files['current_coordinator.py'].sha256));
 edit(stage,"activation=json.loads(ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA))","activation=ref.current_baseline()");
 edit(stage,"observed['helper_uid']==10196","observed['helper_uid']==entry.HELPER_UID");
 for(const[file,s]of Object.entries(files))need(!s.includes('ref.ACTIVATION')&&!s.includes('ref.VERIFIED'),'OLD_EPOCH_AUTHORITY_REMAINS:'+file);
 let back={...files};for(const e of [...edits].reverse()){need(back[e.file].split(e.next).length-1===e.count,'FULL_MIGRATION_INVERSE_COUNT:'+e.file);back[e.file]=back[e.file].split(e.next).join(e.old);}
 need(Object.keys(prior).every(n=>back[n]===prior[n]),'FULL_MIGRATION_INVERSE');
 need(files['public_destination.py']===prior['public_destination.py'],'ALL_PUBLIC_AND_READINESS_GUARDS_UNCHANGED');
 return {files,edits,proof:{typed_baseline_template_only:true,full_inverse_to_prior:true,public_readiness_and_search_destination_source_byte_exact:true,original_task_lock_policy_and_transport_constructor_preserved:true,actual_new_install_receipts_bound:false,actual_helper_UID:null,fresh_UI_nonce_pool_bound:false,executable_UI_request_created:false,Python_controls_executed:false,whole_app_production_ready:false}};
}
