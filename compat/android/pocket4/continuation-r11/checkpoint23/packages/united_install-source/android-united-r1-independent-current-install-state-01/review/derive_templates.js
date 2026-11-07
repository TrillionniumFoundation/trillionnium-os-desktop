function deriveInstallTemplates(slug,parent,candidate,buildOriginal,stageOriginal,contextRaw,metadataRaw,h){
 const target=candidate.target,build=JSON.parse(buildOriginal.raw),stage=JSON.parse(stageOriginal.raw),edits={};
 const upper=slug.toUpperCase(),newRoot='/home/alex/work/pocket4-owned-'+slug+'-qa-r1-install-state-01';
 function editFile(name,raw,mutate){const steps=[];let out=raw;
 function rep(before,after,once=false){if(before===after)return;const parts=out.split(before),n=parts.length-1;if(!n||(once&&n!==1))throw Error(name+':'+before.slice(0,90)+':'+n);let pos=0;const positions=[];for(let i=0;i<n;i++){pos+=parts[i].length;positions.push(pos);pos+=after.length;}out=parts.join(after);steps.push({before,after,positions});}
 function one(a,b){rep(a,b,true)}
 function common(){for(const [a,b] of [['com.bestbuy.android',target.package],['bestbuy',slug],['BestBuy',target.label],['BESTBUY',upper]])if(out.includes(a))rep(a,b);}
 mutate({rep,one,common,value:()=>out});let inverse=out;for(const e of [...steps].reverse())for(const p of [...e.positions].reverse()){if(inverse.slice(p,p+e.after.length)!==e.after)throw Error('inverse '+name);inverse=inverse.slice(0,p)+e.before+inverse.slice(p+e.after.length);}if(inverse!==raw)throw Error('inverse parent '+name);
 edits[name]={parent_sha256:h.sha(raw),source_sha256:h.sha(out),inverse_exact:true,steps};return out;}
 function fn(raw,name){const s=raw.indexOf('\ndef '+name+'(')+1;if(!s)throw Error(name);const e=raw.indexOf('\ndef ',s+1);return raw.slice(s,e<0?undefined:e).trimEnd()+'\n';}
 const readerParent=parent['references/read_bestbuy.py'];
 const parser='"""Fixed target metadata parsers only; original parser bodies preserved."""\nimport re\nfrom pathlib import Path\nPACKAGE = '+JSON.stringify(target.package)+'\nUSER = 0\nFILE_COUNT = 16\n\n'+fn(readerParent,'need')+'\n'+fn(readerParent,'metadata')+'\n'+fn(readerParent,'apk_paths')+'\nif __name__ == "__main__":\n    raise SystemExit("PARSER_ONLY_NO_DEVICE_OR_FILESYSTEM_ENTRY")\n';
 const files={'references/target_metadata_parsers.py':parser,[slug+'_context.py']:contextRaw,
 'actual-target-metadata.json':metadataRaw,'target-artifact-reference.json':candidate.files['target-artifact-reference.json'],
 'current_discovery.py':parent['current_discovery.py'],'host/source-manifest.json':parent['host/source-manifest.json'],
 'host-stage-actual.json':parent['host-stage-actual.json']};
 files[slug+'_transport.py']=editFile('bestbuy_transport.py',parent['bestbuy_transport.py'],({one})=>{
  one('EXPECTED_PACKAGE = "com.bestbuy.android"','EXPECTED_PACKAGE = '+JSON.stringify(target.package));
  one('EXPECTED_UID = 10130','EXPECTED_UID = '+target.uid);
 });
 files['install_state.py']=editFile('install_state.py',parent['install_state.py'],({rep,one,common,value})=>{
  common();
  rep('pocket4-owned-'+slug+'-qa-r4-install-state-02','pocket4-owned-'+slug+'-qa-r1-install-state-01');
  rep('org.droidloom.qa.'+slug+'.r4','org.droidloom.qa.'+slug+'.r1');
  rep('pocket4-owned-'+slug+'-qa-r4-source-01','pocket4-owned-'+slug+'-qa-r1-source-01');
  rep('pocket4-owned-'+slug+'-qa-r4-build-01','pocket4-owned-'+slug+'-qa-r1-build-01');
  rep(slug+'_r4_transport',slug+'_r1_transport');
  one("NONCE = 'b6275faedda72f2dec85914ab42b2b7b'","NONCE = '__FRESH_INSTALL_FLOW__'");
  one("STATE_NONCE = 'a499f5a6a566ed0cebed5c98e234eede'","STATE_NONCE = '__FRESH_INSTALL_STATE__'");
  for(const [key,val] of Object.entries({QA_MANIFEST:h.sha(candidate.files['SOURCE_PINS.json']),BUILD_SHA:buildOriginal.sha256,BUILD_BYTES:buildOriginal.bytes,STAGE_SHA:stageOriginal.sha256,STAGE_BYTES:stageOriginal.bytes,APK_SHA:build.APK.sha256,APK_BYTES:build.APK.bytes,SIGNER_SHA:build.signer_certificate_sha256,READER_SHA:h.sha(parser)})){
   const old=value().match(new RegExp('^'+key+' = .+$','m'))?.[0];if(!old)throw Error(key);one(old,key+' = '+(typeof val==='number'?val:JSON.stringify(val)));
  }
  rep('PREVIOUS_HELPER_UID','PARENT_HELPER_UID');one('PARENT_HELPER_UID = 10155','PARENT_HELPER_UID = 10160');
  one('uid not in (10130,10121,10129,10117,10125,10164,10165,10166,10169,10170,10175,10184,10190,10137,10196,10198,10203)','uid != '+target.uid);
  rep('references/read_'+slug+'.py','references/target_metadata_parsers.py');
  one('qa.UID == 10130','qa.UID == '+target.uid);
  one('if len(artifacts.records)==3 and','if len(artifacts.records)=='+target.apks+' and');
  one("'current_discovery.py', 'check_current_discovery.py'}","'current_discovery.py', 'check_current_discovery.py', 'actual-target-metadata.json'}");
  one('its exact three current APKs','its exact '+target.apks+' current APKs');
 });
 files['stage_execute.py']=editFile('stage_execute.py',parent['stage_execute.py'],({rep,one,common})=>{
  common();rep('pocket4-owned-'+slug+'-qa-r4-install-state-02','pocket4-owned-'+slug+'-qa-r1-install-state-01');
  one("NONCE = 'b6275faedda72f2dec85914ab42b2b7b'","NONCE = '__FRESH_INSTALL_FLOW__'");
  rep('references/read_'+slug+'.py','references/target_metadata_parsers.py');
  one("'current_discovery.py', 'check_current_discovery.py'}","'current_discovery.py', 'check_current_discovery.py', 'actual-target-metadata.json'}");
 });
 files['make_request.py']=editFile('make_request.py',parent['make_request.py'],({rep,one,common})=>{
  common();rep('pocket4-owned-'+slug+'-qa-r4-current-r6-install-state-02','pocket4-owned-'+slug+'-qa-r1-current-r6-install-state-01');
  rep('pocket4-owned-'+slug+'-qa-r4-install-state-02','pocket4-owned-'+slug+'-qa-r1-install-state-01');
  one("NONCE = 'b6275faedda72f2dec85914ab42b2b7b'","NONCE = '__FRESH_INSTALL_FLOW__'");
 });
 files['check_current_discovery.py']=editFile('check_current_discovery.py',parent['check_current_discovery.py'],({one})=>{
  one('context_source = files[{"com.ihg.apps.android":"ihg_context.py",\n        "com.amazon.mShop.android.shopping":"amazon_context.py",\n        "com.bestbuy.android":"bestbuy_context.py"}[context_name]]',
      "need(context_name == "+JSON.stringify(target.package)+', "EXACT_INDEPENDENT_TARGET_CONTEXT_REQUIRED")\n    context_source = files['+JSON.stringify(slug+'_context.py')+']');
 });
 const proof={schema:'independent-target-installer-template-proof-v1',state:'SOURCE_ONLY_CONTROLS_PENDING_NONCES_UNBOUND',newRoot,helper_package:build.package,target,edits,
 parser:{parent: {bytes:h.utf8(readerParent).length,sha256:h.sha(readerParent)},source:{bytes:h.utf8(parser).length,sha256:h.sha(parser)},original_functions:['need','metadata','apk_paths'],bodies_exact:true,no_execution_entry:true},
 unchanged:['current_discovery.py','host/source-manifest.json','host-stage-actual.json','helper target-artifact-reference.json','all helper QA/Java sources'],
 installed_UID:null,scope_not_added_to_baseline:true,no_execution_request:true};
 return {files,proof,newRoot,key:'pocket4-owned-'+slug+'-qa-r1-current-r6-install-state-01-20261106'};
}
