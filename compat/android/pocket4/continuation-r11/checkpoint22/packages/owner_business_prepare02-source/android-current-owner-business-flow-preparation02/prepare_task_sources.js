function prepareOwnerFixedTaskFlow(app, prior, install, h, extract){
 const need=(v,m)=>{if(!v)throw Error(m);};
 const pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s),git_blob:h.git(s)});
 need(['ihg','amazon','bestbuy'].includes(app)&&install.root.endsWith('-02'),'EXACT_INSTALL02_TEMPLATE');
 const sources={...prior.sources},edits=[];
 function replace(file,from,to,reason){
   need(sources[file].split(from).length===2,'ONCE:'+file+':'+reason);
   sources[file]=sources[file].replace(from,to);edits.push({file,from,to,reason});
 }
 const oldRoot='/home/alex/work/pocket4-owned-'+app+'-qa-r4-install-state-01';
 replace('coordinator',oldRoot,install.root,'qualified-next-installation-source-root');
 const updates={
   INSTALL_SOURCE_SHA:JSON.stringify(install.manifest_sha256),
   UTIL_SHA:JSON.stringify(h.sha(install.files['install_state.py'])),
   UTIL_BYTES:String(h.utf8(install.files['install_state.py']).length),
   CONTEXT_SHA:JSON.stringify(h.sha(install.files[app+'_context.py'])),
   TRANSPORT_SHA:JSON.stringify(h.sha(install.files[app+'_transport.py'])),
   STATE_NONCE:JSON.stringify(install.inputs.nonces.state)
 };
 for(const [name,value]of Object.entries(updates)){
   const matches=[...sources.coordinator.matchAll(new RegExp('^'+name+'=.*$','gm'))];
   need(matches.length===1,'EXACT_BINDING_LINE:'+name);
   replace('coordinator',matches[0][0],name+'='+value,'exact-frozen-install02-'+name);
 }
 replace('context',
  'transport,result,deadline,phase,qa,inspect_plan,resolve,expected_scope):',
  'transport,result,deadline,phase,qa,inspect_plan,resolve,expected_scope, *,\n                      install_source_manifest):',
  'explicit-install-source-manifest-argument');
 replace('context',
  'init,discovered,status=app.discover()',
  'init,discovered,status=context.current_discovery(\n            util,install_source_manifest,util.verify_source,util.HERE,\n            app,activation,epoch,guard)',
  'actual-task-entry-routes-through-pinned-install02-discovery');
 const call=sources.coordinator.match(/transport,result,began\+PHASE_SECONDS\[phase\],phase,q\.qa,(plans|PLAN|PLANS),q\.resolver\.RESOLVE,scope_record\(q,expected\)\)/g);
 need(call&&call.length===1,'ONE_TASK_OPEN_CALL');
 replace('coordinator',call[0],call[0].slice(0,-1)+',\n            install_source_manifest=q.resolver.INSTALL_SOURCE_SHA)',
  'pass-actual-qualified-install-source-manifest');
 const restored={...sources};
 for(const e of [...edits].reverse()){
   need(restored[e.file].split(e.to).length===2,'EXACT_INVERSE:'+e.reason);
   restored[e.file]=restored[e.file].replace(e.to,e.from);
 }
 need(Object.keys(sources).every(k=>restored[k]===prior.sources[k]),'ALL_SOURCE_INVERSE_EXACT');
 for(const name of ['Policy','Flow','current_task_scope'])need(extract(sources.context,name)===extract(prior.sources.context,name),'UNCHANGED_CONTEXT:'+name);
 const originalOpen=extract(prior.sources.context,'open_task_context');
 let newOpen=extract(sources.context,'open_task_context');
 for(const e of [...edits].reverse().filter(e=>e.file==='context'))newOpen=newOpen.replace(e.to,e.from);
 need(newOpen===originalOpen,'OPEN_TASK_EXACT_TWO_CHANGE_INVERSE');
 need(!extract(sources.context,'open_task_context').includes('app.discover('),'NO_LEGACY_TASK_DISCOVERY');
 const coordinatorFunctions=['actual_install','resolve_current','fixed_inspect_plan'];
 const unchanged=[];
 for(const name of coordinatorFunctions){
   if(!new RegExp('^def '+name+'\\(','m').test(sources.coordinator))continue;
   need(extract(sources.coordinator,name)===extract(prior.sources.coordinator,name),'UNCHANGED_COORDINATOR:'+name);unchanged.push(name);
 }
 return{...prior,sources,source_pins:Object.fromEntries(Object.entries(sources).map(([k,v])=>[k,{bytes:pin(v).bytes,sha256:pin(v).sha256}])),
  owner_discovery_revision:2,owner_original_sources:prior.sources,owner_edits:edits,
  owner_complete_inverse_exact:true,unchanged_context_functions:['Policy','Flow','current_task_scope'],
  original_task_context_Policy_Flow_open_task_context_byte_exact:false,
  original_open_task_context_changes_only:['explicit_install_manifest_argument','pinned_install02_discovery_call'],
  original_context_functions:prior.original_context_functions,
  unchanged_coordinator_functions:unchanged,
  actual_install_source_manifest:install.manifest_sha256,
  actual_install_source_root:install.root+'/source',
  actual_install_source_pins:JSON.parse(install.files['SOURCE_PINS.json']),
  install_source_payload_pins:Object.fromEntries(['install_state.py',app+'_context.py',app+'_transport.py','current_discovery.py'].map(name=>[name,pin(install.files[name])])),
  discovery_source:pin(install.files['current_discovery.py']),
  expected_install_control_count:install.controls_expected,
  minimum_nonce_exclusion_count:659,
  installation_actual_status:'PENDING_NOT_ASSUMED',helper_uid:null,UI_request_created:false,Python_executed:false,Android_actions:0};
}
