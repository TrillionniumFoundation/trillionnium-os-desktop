function bindBiliR10InstallSources(h, template, qualified, install) {
 const need=(v,c)=>{if(!v)throw Error(c)},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 need(template.owner_discovery_revision===2&&template.nonce_count===146&&qualified.ok===true&&qualified.schema==="pocket4-bili-r10-install02-independent-qualification-v1"&&qualified.source_manifest_sha256===install.manifest_sha256,"ACTUAL_R10_INSTALL_QUALIFICATION_REQUIRED");
 let files={...template.files};const edits=[],nav="owned_navigation.py";
 function edit(name,a,b){need(files[name].split(a).length-1===1,"EXACT_SINGLE_BIND:"+name+":"+a.slice(0,72));files[name]=files[name].replace(a,b);edits.push({file:name,old:a,next:b,count:1});}
 function constant(name,next){const hit=files[nav].match(new RegExp("^"+name+"=.*$","m"));need(hit,"EXACT_CONST:"+name);edit(nav,hit[0],name+"="+next);}
 const py=x=>JSON.stringify(x),path=x=>"Path("+py(x)+")";
 edit(nav,'SELF,UID=("org.droidloom.qa.bili.r10",None)  # Actual R10 installation required.','SELF,UID=("org.droidloom.qa.bili.r10",'+qualified.actual_UID+')');
 constant("OLD_STEP","OLD_FLOW/'steps/install-state-r10-02'");
 constant("OLD_PACKET",py(qualified.packet_sha256));
 constant("OLD_STATE_WIRE",py(qualified.state_wire_sha256));
 constant("INSTALL_JOB_ID",py(qualified.actual_install_job));
 constant("STATE_COMMAND_INDEX",String(qualified.state_command_index));
 constant("STATE_COMMAND_SHA",py(qualified.state_command_sha256));
 constant("EXPECTED_INSTALLED_IDENTITY",qualified.installed_identity_python);
 constant("INSTALL_RECORDS","{"+["coordinator","stage","worker","worker_command"].map(name=>py(name)+":("+path(qualified.paths[name])+","+qualified.records[name].bytes+","+py(qualified.records[name].sha256)+")").join(",")+"}");
 need(files[nav].includes('INSTALL_ROOT=Path("'+qualified.install_root+'")')&&files[nav].includes('OLD_FLOW=Path("'+qualified.flow_root+'")')&&files[nav].includes('OLD_STATE_NONCE="'+qualified.state_nonce+'"')&&files[nav].includes('INSTALL_MANIFEST_SHA="'+qualified.source_manifest_sha256+'"')&&files[nav].includes('SESSION_SHA="'+qualified.session_binding_sha256+'"')&&files[nav].includes('R6_MANIFEST="'+qualified.host_manifest_sha256+'"'),"INSTALLED_SOURCE_AUTHORITY_MATCH");
 const back={...files};for(const e of [...edits].reverse()){need(back[e.file].split(e.next).length-1===1,"INVERSE_BIND_COUNT");back[e.file]=back[e.file].replace(e.next,e.old);}
 need(Object.keys(files).every(n=>back[n]===template.files[n]),"FULL_INVERSE_TO_OWNER_TEMPLATE");
 return {...template,files,install_binding_edits:edits,install_binding_originals:template.files,
  helper_uid:qualified.actual_UID,actual_helper_UID:qualified.actual_UID,actual_install:qualified,
  pending_actual_install:false,pending_fresh_nonces:true,nonce_pool_consumed:false,UI_request_created:false,
  source_pins:Object.fromEntries(Object.entries(files).map(([n,s])=>[n,pin(s)])),
  binding_proof:{actual_UID:qualified.actual_UID,host_manifest_sha256:qualified.host_manifest_sha256,
   actual_install_source_manifest_sha256:qualified.source_manifest_sha256,actual_install_packet_sha256:qualified.packet_sha256,
   actual_step:qualified.step_root,actual_state_index:6,actual_mtime_ns:qualified.actual_mtime_ns,
   source_only_until_actual_new146:true,whole_app_production_ready:false}};
}
