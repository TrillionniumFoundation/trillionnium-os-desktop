function bindCurrentOwnerTaskInstallSources(template,qualified,h){
 const need=(x,m)=>{if(!x)throw Error(m);},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 const stable=v=>Array.isArray(v)?'['+v.map(stable).join(',')+']':v!==null&&typeof v==='object'?
  '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+stable(v[k])).join(',')+'}':JSON.stringify(v);
 const eq=(a,b)=>stable(a)===stable(b),app=template.app;
 need(['amazon','bestbuy'].includes(app)&&qualified.app===app&&qualified.install_retired===true&&
  qualified.eight_Main_maps_match===true&&qualified.source_controls===68&&qualified.new_current_owner_discovery_controls===18&&
  template.owner_discovery_revision===2&&template.owner_complete_inverse_exact===true&&
  qualified.source_manifest_sha256===template.actual_install_source_manifest&&
  qualified.current_host_manifest_sha256===template.host_manifest_sha256,'EXACT_QUALIFIED_CURRENT_OWNER_TEMPLATE');
 const sources={...template.sources},edits=[];
 for(const [name,raw]of Object.entries(sources))need(eq(pin(raw),template.source_pins[name]),'SOURCE_PIN:'+name);
 function replace(file,from,to,why){need(sources[file].split(from).length===2,'EXACT_INSTALL_BINDING:'+file+':'+why);
  sources[file]=sources[file].replace(from,to);edits.push({file,from,to,why,count:1});}
 const uid=qualified.UID;
 need(Number.isInteger(uid)&&uid>=10000&&uid<100000,'ACTUAL_INSTALL_UID');
 for(const file of ['coordinator','context',...(app==='bestbuy'?['business']:[])])
  replace(file,'HELPER_UID=None  # Actual R4 installation required.','HELPER_UID='+uid,'actual-helper-UID');
 replace('coordinator','STATE_WIRE=None  # Actual R4 installation closure required.',
  'STATE_WIRE='+JSON.stringify(qualified.state_wire_sha256),'actual-state-wire');
 replace('coordinator','INSTALLED=None  # Actual R4 installation closure required.',
  'INSTALLED='+qualified.installed_identity_python,'lossless-installed-identity');
 const priors={coordinator:['result.json',qualified.prior_receipts.coordinator.bytes,qualified.prior_receipts.coordinator.sha256],
  stage:['stage-result.json',qualified.prior_receipts.stage.bytes,qualified.prior_receipts.stage.sha256],
  worker:['worker/result.json',qualified.prior_receipts.worker.bytes,qualified.prior_receipts.worker.sha256]};
 const py='{'+Object.entries(priors).map(([k,v])=>JSON.stringify(k)+':('+v.map(x=>JSON.stringify(x)).join(',')+')').join(',')+'}';
 replace('coordinator','PRIOR=None  # Actual R4 installation closure required.','PRIOR='+py,'exact-parent-Python-tuples');
 const restore={...sources};for(const e of [...edits].reverse()){
  need(restore[e.file].split(e.to).length===2,'EXACT_INSTALL_BINDING_INVERSE:'+e.why);
  restore[e.file]=restore[e.file].replace(e.to,e.from);}
 need(Object.keys(sources).every(k=>restore[k]===template.sources[k]),'COMPLETE_INSTALL_BINDING_INVERSE');
 return{app,sources,source_pins:Object.fromEntries(Object.entries(sources).map(([k,v])=>[k,pin(v)])),
  install_binding_edits:edits,actual_binding:qualified,template,nonce_labels:template.nonce_labels,
  requires_actual_fresh_nonces:true,UI_request_created:false,Python_controls_executed:false};
}
