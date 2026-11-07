function bindLondonSources(material,h,ll){
 const fail=(x,m)=>{if(!x)throw Error(m);};
 const pins={"coordinator":{"bytes":44748,"sha256":"4daac40b57f971577433d2cde37d6464c8e72b45df44dab629b967fab0baed98"},"context":{"bytes":19441,"sha256":"1b976c63724eff963219f934629f69535c5be4f2a46c5c700ded1888021a8ffe"},"public_destination":{"bytes":42662,"sha256":"30738abe4b4ba740fd3e0c47de8437792f8d52a539e74afd5e140878e29a4076"},"stage":{"bytes":5175,"sha256":"50f2dac94c81a329e83bb498d06c00693098f7686292671ea65b9bc4b1f03dba"},"contract":{"bytes":28750,"sha256":"bec85084822d68090f39215807c60d6ea583526f17d5e2028c3a8fcacbc27c43"},"adapter":{"bytes":21670,"sha256":"0b192041fde9f238188051854410c372c5d73eb4f1b24ab6e122c34a15ba082c"},"transport":{"bytes":15606,"sha256":"27e07fbaaccca4e5113e1750a3b7baa9d05048a1e8588f09cdc8f9ed5cf44089"}};
 const ipins={"coordinator":{"bytes":3961,"sha256":"6b5e539c535f2cb39e04dcdaebbdfa02545db33e11c640022d4af6196ca804d3"},"stage":{"bytes":7082,"sha256":"771d062222c3a9af23ddcfa095fdcf755036d557438f36e05c8d42fb6dc9a132"},"worker":{"bytes":12552,"sha256":"ee3f30004e68748fc0ad9af8258866bf272b4642f5868fb28a3dc5a03af3ebcc"},"state_command":{"bytes":443,"sha256":"c0fde5ede194568a2485e1488e0826d6a95caac775ed3b7d10891d511b4dc737"},"worker_command":{"bytes":1598,"sha256":"cccd22025470ed58316e0dfe523e543682bed20ab160dcaebe3a521ab912dc8c"},"worker_stdout":{"bytes":11028,"sha256":"162c7eead19fbcaab9f1cb74f72211f2cb85e0ae409f262aa07d1cf91a6da302"}};
 const pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 const stable=x=>Array.isArray(x)?'['+x.map(stable).join(',')+']':x!==null&&typeof x==='object'?'{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+stable(x[k])).join(',')+'}':JSON.stringify(x);
 const same=(a,b)=>stable(a)===stable(b);
 const roots={};
 for(const [key,p]of Object.entries(pins)){const raw=material.templates[key];fail(typeof raw==='string'&&same(pin(raw),p),'EXACT_TEMPLATE:'+key);}
 for(const [key,p]of Object.entries(ipins)){const raw=material.install[key];fail(typeof raw==='string'&&same(pin(raw),p),'EXACT_INSTALL_ORIGINAL:'+key);roots[key]=ll.losslessJsonNodes(raw);}
 const obj=Object.fromEntries(Object.entries(material.install).map(([k,v])=>[k,JSON.parse(v)]));
 const canon=(k,path)=>ll.losslessCanonical(ll.nodeField(roots[k],path));
 const c=obj.coordinator,s=obj.stage,w=obj.worker;
 for(const x of [c,s,w])fail(x.ok===true&&x.error===null&&Array.isArray(x.secondary_errors)&&x.secondary_errors.length===0,'ACTUAL_INSTALL_PASS');
 const installRoot='/home/alex/work/pocket4-owned-ihg-qa-r3-install-state-01';
 const row=(key,path)=>({path:installRoot+'/'+path,...ipins[key]});
 fail(same(c.worker_result,row('worker','worker/result.json')),'WORKER_PARENT_CHAIN');
 fail(same(s.coordinator_result,row('coordinator','result.json')),'COORDINATOR_PARENT_CHAIN');
 fail(c.source_manifest_sha256===s.source_manifest_sha256&&s.source_manifest_sha256===w.source_manifest_sha256&&
  w.source_manifest_sha256==='7d7c97b453ed5e5f75a4bd3fcab92cc3e76603bb1e09745ce509d3cd73c7494d','INSTALL_SOURCE');
 fail(w.owned_package_uid===10156&&c.owned_package_uid===10156&&w.state.helper.self_uid===10156&&
  w.installed_before_state.uid===10156&&w.installed_before_state.package==='org.droidloom.qa.ihg.r3','ACTUAL_NEW_UID');
 fail(canon('worker',['installed_before_state'])===canon('worker',['installed_after_state'])&&
      canon('worker',['target_before'])===canon('worker',['target_after']),'EXACT_LOSSLESS_INSTALLED_TARGET');
 fail(ll.losslessCanonical(roots.worker)===ll.losslessCanonical(roots.worker_stdout),'ACTUAL_PRINTED_WORKER_EQUALS_DURABLE');
 const main=canon('worker',['Main_before']);
 for(const [key,fields]of Object.entries({worker:['Main_before_lock','Main_before','Main_after'],coordinator:['Main_before','Main_after'],stage:['Main_before','Main_after']}))
  for(const field of fields)fail(canon(key,[field])===main,'MAIN_MAP:'+key+'.'+field);
 fail(w.Main_before.Main_epoch_sha256==='734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2'&&
  w.exact_command_count===13&&w.action_attempted===true&&w.outcome_unknown===false&&
  w.final_Main_guard_passed===true&&w.held_binding_released===true&&w.action_lock_released===true&&
  w.staging_cleanup.staged_apk_removed===true&&w.staging_cleanup.staged_directory_removed===true&&
  w.target_FD_cleanup.held_APK_FDs_closed===1&&w.UI_actions===0&&w.App_launches===0,'CLOSED_INSTALL_ONLY');
 fail(w.state.helper.protocol==='pocket4-owned-ihg-qa-v3'&&w.state.helper.op==='state'&&w.state.helper.ok===true&&
  w.state.helper.ui_automation_connected===false&&w.state.wire_sha256==='135985d2abcf6ade7f343a658b975c657dd97ed144889397543eb4a6cf5d4164'&&
  w.state.helper.nonce==='a8c37991b3fdd2f6b40d8f6fd6354bf0','ACTUAL_STATE');
 const cmd=obj.worker_command,scmd=obj.state_command;
 fail(cmd.joined===true&&cmd.returncode===0&&cmd.timed_out===false&&cmd.secondary_errors.length===0&&
  same(cmd.stdout,{bytes:ipins.worker_stdout.bytes,sha256:ipins.worker_stdout.sha256}),'JOINED_WORKER_STDOUT_CHAIN');
 fail(scmd.owned_command_joined===true&&scmd.returncode===0&&scmd.timed_out===false&&
  scmd.action_attempted===false&&scmd.error===null,'JOINED_NO_ACTION_STATE_COMMAND');
 const n=JSON.parse(material.nonce_raw),spec=JSON.parse(material.nonce_spec),excluded=JSON.parse(material.exclusions);
 fail(same(pin(material.nonce_raw),{bytes:2587,sha256:'094a4127a19e352552dde1ea182f6009c3eddbf75571ad1da4a44bd2bab934f4'}),'NONCE_ACTUAL_PIN');
 fail(same(pin(material.exclusions),{bytes:23145,sha256:'66e49e591d79cf92948ebd92e476d6d3f08fabaea58d0d04bf73914f930958a7'}),'EXCLUSIONS_PIN');
 fail(same(pin(material.nonce_spec),{bytes:3000,sha256:'239e35f1fc8146cc0e20edab911178a097d4b914877c270254f7bf5c93bbcca0'}),'SPEC_PIN');
 fail(same(pin(material.generator),{bytes:22680,sha256:'7f479add963f2181f3ae8be23c9a82c9a083e2d9ef7c91776f4bcc2f4bc2b37e'}),'GENERATOR_PIN');
 const literal=material.generator.match(/^EXCLUDED = (\[.*\])$/m);
 fail(literal&&same(JSON.parse(literal[1]),excluded)&&n.excluded_count===609&&excluded.length===609&&
  new Set(excluded).size===609&&h.sha(JSON.stringify(excluded)+'\n')===n.excluded_sha256,'COMPLETE_EXCLUSION_LINEAGE');
 const labels=spec.labels;
 fail(n.generator==='secrets.token_hex(16)'&&n.no_redraw===true&&n.actual_helper_uid_bound===10156&&
  n.count===40&&same(n.labels,labels)&&labels.length===40&&new Set(labels).size===40&&
  n.values.length===40&&new Set(n.values).size===40&&n.values.every(v=>/^[0-9a-f]{32}$/.test(v)&&!excluded.includes(v))&&
  spec.minimum_exclusions.every(v=>excluded.includes(v)),'ACTUAL_FORTY_DISTINCT');
 const bound={...material.templates},edits=[];
 function replace(file,from,to,why){fail(bound[file].split(from).length===2,'EXACT_REPLACEMENT:'+file+':'+why);bound[file]=bound[file].replace(from,to);edits.push({file,from,to,why});}
 replace('coordinator','HELPER_UID=None  # Actual R3 install receipt required.','HELPER_UID='+w.owned_package_uid,'actual-helper-uid');
 replace('context','HELPER_UID=None  # Await actual R3 installation receipt.','HELPER_UID='+w.owned_package_uid,'actual-helper-uid');
 replace('coordinator','STATE_WIRE=None  # Actual R3 installation original required.','STATE_WIRE='+JSON.stringify(w.state.wire_sha256),'actual-state-wire');
 const installed=ll.losslessPython(ll.nodeField(roots.worker,['installed_before_state']));
 replace('coordinator','INSTALLED=None  # Actual R3 installation original required.','INSTALLED='+installed,'lossless-current-installed-tuple');
 const prior={coordinator:['result.json',ipins.coordinator.bytes,ipins.coordinator.sha256],
  stage:['stage-result.json',ipins.stage.bytes,ipins.stage.sha256],worker:['worker/result.json',ipins.worker.bytes,ipins.worker.sha256]};
 const priorPy='{'+Object.entries(prior).map(([k,v])=>JSON.stringify(k)+':('+v.map(x=>JSON.stringify(x)).join(',')+')').join(',')+'}';
 replace('coordinator','PRIOR=None  # Actual R3 installation original required.','PRIOR='+priorPy,'exact-python-tuple-prior-pins');
 const oldOps="'new_helper_operations':['state','inspect','click','state','state','inspect','click','state','state','inspect','state']";
 const newOps="'new_helper_operations':['bounded restored Search readiness','fresh Search click','fresh Destination click','fresh current-editor London set_text','independent post inspect']";
 replace('coordinator',oldOps,newOps,'accurate-plan-only-operation-summary');
 for(let i=0;i<labels.length;i++){
  const hole='__FRESH_'+labels[i].toUpperCase().replaceAll('.','_')+'__';
  replace('coordinator',hole,n.values[i],'fresh-actual-nonce-'+labels[i]);
  if(labels[i]==='flow')replace('stage',hole,n.values[i],'fresh-actual-nonce-flow');
 }
 for(const [key,source]of Object.entries(bound))fail(!source.includes('__FRESH_'),'NO_UNBOUND_NONCE:'+key);
 for(const [key,source]of Object.entries(bound))fail(h.utf8(source).length<=65536,'BOUNDED_SOURCE:'+key);
 const boundPins=Object.fromEntries(Object.entries(bound).map(([k,v])=>[k,pin(v)]));
 const receipt={job_id:'1a1b09cf731-fc05-71b4',git_blob:'0a444d90d780b9222e3d8260cf834815923246b3',
  ...pin(material.nonce_raw),count:40,excluded_count:609,excluded_sha256:n.excluded_sha256,
  generator:n.generator,no_redraw:true,actual_helper_uid:10156};
 return {sources:bound,source_pins:boundPins,edits,prior,installed_python:installed,nonce_receipt:receipt,
  fresh_nonces:n.values,nonce_exclusions:excluded,install_pins:ipins,actual_install_qualified:true,
  nonce_values_committed:true,UI_request_created:false,Python_controls_performed:false};
}